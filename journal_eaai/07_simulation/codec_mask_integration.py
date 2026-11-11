#!/usr/bin/env python3
"""Canonical codec <-> oracle integration (Gate-M1 DESIGN artifact — r25 §8).

The **token codec** (`token_codec.py`) speaks **integer indices** `(device_index, beam_index,
power_index)`; the **conditional-mask oracle** (`conditional_mask_oracle.py`) speaks **string
tuples** `(device_id, beam_id, power_id)`. This module is the **single canonical bridge** between
them so the two representations can never silently disagree.

Canonical ordered specification (`OrderedModelSpec`):
    device_order : ordered tuple of device ids      -> device_index = position in this tuple
    beam_order   : ordered tuple of beam ids         -> beam_index   = position in this tuple
    power_order  : ordered tuple of power ids        -> power_index  = position in this tuple
    version      : explicit spec version string
The **ordered tuples are the sole source of index<->id mapping** — never Python dict insertion
order — so re-ordering the beams/powers *dicts* cannot change token semantics. A change to any
ordered tuple changes token IDs and therefore MUST be accompanied by a version bump
(`require_spec_version`), otherwise it is rejected.

Tier-explicit mask APIs (r29 §3 — no generic alias that silently selects the reference model):
`compute_reference_boolean_token_mask(...)` (toy/reference tier) and
`compute_primary_boolean_token_mask(...)` (primary study tier). Each:
    1. decode the integer prefix token ids -> oracle string tuples (via the ordered spec);
    2. validate them through the oracle (`conditional_mask_oracle.compute_token_mask`);
    3. encode the oracle's feasible string tuples -> integer token ids;
    4. return a Boolean mask of length exactly `1 + K*B*P` (index 0 = idle).

Pure functions only (no simulator, RNG, channel, or training).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import conditional_mask_oracle as oracle
import token_codec as codec

IDLE_ID = codec.IDLE_ID
# r27 §5: the toy artifact used by unit tests is the REFERENCE spec; the primary study spec
# (N_primary=8, generated from primary_scenario_config.json) is separate.
REFERENCE_SPEC_PATH = Path(__file__).resolve().parent / "reference_action_spec.json"
PRIMARY_SPEC_PATH = Path(__file__).resolve().parent / "primary_action_spec.json"
PRIMARY_CONFIG_PATH = Path(__file__).resolve().parent / "primary_scenario_config.json"
# r28 §4: the tier-ambiguous CANONICAL_SPEC_PATH alias is REMOVED. Use REFERENCE_SPEC_PATH /
# PRIMARY_SPEC_PATH and the explicit reference/primary mask functions.


@dataclass(frozen=True)
class OrderedModelSpec:
    """Immutable canonical ordering + physical values shared by codec and oracle."""
    device_order: Tuple[str, ...]
    beam_order: Tuple[str, ...]
    power_order: Tuple[str, ...]
    version: str
    powers: Mapping[str, float]                 # watt value per power id
    n_max: Mapping[str, int] = None             # REQUIRED: N_max per device (r26 §6)
    n_primary: int = None                       # REQUIRED: number of subchannels
    beam_gains: Mapping[str, float] = field(default_factory=dict)
    beam_forbidden: frozenset = field(default_factory=frozenset)
    power_forbidden: frozenset = field(default_factory=frozenset)

    def __post_init__(self):
        for name, seq in (("device_order", self.device_order),
                          ("beam_order", self.beam_order),
                          ("power_order", self.power_order)):
            if not isinstance(seq, tuple) or len(seq) < 1:
                raise ValueError(f"{name} must be a non-empty tuple, got {seq!r}")
            if len(set(seq)) != len(seq):
                raise ValueError(f"{name} has duplicate ids: {seq!r}")
        # r26 §6: powers must be positive finite; every power id needs a value
        for p in self.power_order:
            if p not in self.powers:
                raise ValueError(f"power id {p!r} missing a watt value in powers")
            v = self.powers[p]
            if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
                raise ValueError(f"power {p!r} value must be positive finite, got {v!r}")
        # r26 §6: N_primary is REQUIRED and must be a positive int (no infinity default)
        if not isinstance(self.n_primary, int) or self.n_primary < 1:
            raise ValueError(f"n_primary must be a positive int, got {self.n_primary!r}")
        # r26 §6 / r30 §4 canonical domain: EVERY canonical device must have an N_max, an int in
        # 1..N_primary (no inf default; NOT 0 — a canonical/participating device occupies at least
        # one subchannel; to disable a device remove it from the canonical set, do not set N_max=0).
        if not isinstance(self.n_max, Mapping):
            raise ValueError("n_max is REQUIRED: a mapping {device: N_max int in 1..N_primary}")
        if set(self.n_max) != set(self.device_order):
            raise ValueError(f"n_max must cover exactly the canonical devices "
                             f"{list(self.device_order)}, got keys {sorted(self.n_max)}")
        for k, nm in self.n_max.items():
            if not isinstance(nm, int) or isinstance(nm, bool) or not (1 <= nm <= self.n_primary):
                raise ValueError(f"n_max[{k!r}]={nm!r} must be an int in 1..{self.n_primary} "
                                 f"(canonical devices have N_max>=1; N_max=0 is not permitted)")
        # r26 §6: forbidden pairs must use a legal subchannel index (1..N) and a legal beam/power id
        for (sc, b) in self.beam_forbidden:
            if not (isinstance(sc, int) and 1 <= sc <= self.n_primary):
                raise ValueError(f"beam_forbidden subchannel {sc!r} not in 1..{self.n_primary}")
            if b not in self.beam_order:
                raise ValueError(f"beam_forbidden beam id {b!r} not in beam_order")
        for (sc, p) in self.power_forbidden:
            if not (isinstance(sc, int) and 1 <= sc <= self.n_primary):
                raise ValueError(f"power_forbidden subchannel {sc!r} not in 1..{self.n_primary}")
            if p not in self.power_order:
                raise ValueError(f"power_forbidden power id {p!r} not in power_order")

    @property
    def K(self) -> int: return len(self.device_order)

    @property
    def B(self) -> int: return len(self.beam_order)

    @property
    def P(self) -> int: return len(self.power_order)

    def canonical_signature(self) -> str:
        """Stable hash of ONLY the ordered id tuples (what fixes token semantics)."""
        payload = repr((tuple(self.device_order), tuple(self.beam_order),
                        tuple(self.power_order)))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def oracle_model_parameters(self, N: int) -> Dict:
        """Build oracle model_parameters from the ORDERED tuples (not dict order)."""
        return {
            "devices": list(self.device_order),
            "beams": list(self.beam_order),
            "powers": {p: float(self.powers[p]) for p in self.power_order},
            "N": N,
            "n_primary": self.n_primary,
            "n_max": dict(self.n_max),
            "beam_forbidden": set(self.beam_forbidden),
            "power_forbidden": set(self.power_forbidden),
        }


# --------------------------------------------------------------------------- #
# id <-> tuple mapping (via the ordered spec ONLY)
# --------------------------------------------------------------------------- #
def encode_tuple(tok, spec: OrderedModelSpec) -> int:
    """oracle token ('idle' or (dev_id,beam_id,power_id)) -> integer token id."""
    if tok == oracle.IDLE:
        return IDLE_ID
    if not (isinstance(tok, tuple) and len(tok) == 3):
        raise ValueError(f"oracle token must be 'idle' or (device,beam,power): {tok!r}")
    k, b, p = tok
    try:
        di = spec.device_order.index(k)
        bi = spec.beam_order.index(b)
        pi = spec.power_order.index(p)
    except ValueError:
        raise ValueError(f"token {tok!r} uses an id not in the ordered spec")
    return codec.encode_token(di, bi, pi, spec.K, spec.B, spec.P)


def decode_id(token_id: int, spec: OrderedModelSpec):
    """integer token id -> oracle token ('idle' or (dev_id,beam_id,power_id))."""
    dec = codec.decode_token(token_id, spec.K, spec.B, spec.P)
    if dec == "idle":
        return oracle.IDLE
    di, bi, pi = dec
    return (spec.device_order[di], spec.beam_order[bi], spec.power_order[pi])


def require_spec_version(spec: OrderedModelSpec, expected_signature: str,
                         expected_version: str) -> None:
    """Reject a silent ordering change: if the ordered-id signature changed, the version MUST
    have changed too (r25 §8 'ordering changes are rejected or versioned')."""
    sig_changed = spec.canonical_signature() != expected_signature
    ver_changed = spec.version != expected_version
    if sig_changed and not ver_changed:
        raise ValueError(
            "ordered-id signature changed but spec.version did not — token semantics would "
            "change silently; bump the version to accept the new ordering")


# --------------------------------------------------------------------------- #
# reference-spec identity verification (used by the REFERENCE mask path)
# --------------------------------------------------------------------------- #
def load_reference_spec(path: Path = REFERENCE_SPEC_PATH) -> Dict:
    """Load the REFERENCE (toy) ordered-action artifact. Missing artifact is an error."""
    if not path.exists():
        raise ValueError(f"reference action spec artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_against_reference(spec: OrderedModelSpec, path: Path = REFERENCE_SPEC_PATH) -> None:
    """Enforce that `spec` matches the REFERENCE artifact — version, ordered-id signature, orders
    and N_primary. Called inside the reference mask path (non-bypassable)."""
    canon = load_reference_spec(path)
    if spec.version != canon["version"]:
        raise ValueError(f"spec.version {spec.version!r} != reference {canon['version']!r}")
    if spec.canonical_signature() != canon["canonical_signature"]:
        raise ValueError("spec ordered-id signature does not match the reference action spec "
                         "(order changed without a matching reference artifact)")
    if list(spec.device_order) != list(canon["device_order"]) \
            or list(spec.beam_order) != list(canon["beam_order"]) \
            or list(spec.power_order) != list(canon["power_order"]):
        raise ValueError("spec order does not match the reference action spec orders")
    if spec.n_primary != canon["N_primary"]:
        raise ValueError(f"spec.n_primary {spec.n_primary} != reference N_primary "
                         f"{canon['N_primary']}")


def build_reference_ordered_spec() -> OrderedModelSpec:
    """Build an OrderedModelSpec from the REFERENCE (toy) artifact (used by reference tests)."""
    s = load_reference_spec()
    return OrderedModelSpec(
        device_order=tuple(s["device_order"]), beam_order=tuple(s["beam_order"]),
        power_order=tuple(s["power_order"]), version=s["version"],
        powers={k: float(v) for k, v in s["powers"].items()},
        n_max={d: s["N_primary"] for d in s["device_order"]}, n_primary=s["N_primary"])


# --------------------------------------------------------------------------- #
# r27 §5: PRIMARY action spec (generated from the locked scenario config)
# --------------------------------------------------------------------------- #
def load_primary_config(path: Path = PRIMARY_CONFIG_PATH) -> Dict:
    if not path.exists():
        raise ValueError(f"primary scenario config missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_primary_spec(path: Path = PRIMARY_SPEC_PATH) -> Dict:
    if not path.exists():
        raise ValueError(f"primary action spec missing: {path} "
                         f"(run generate_primary_action_spec.py)")
    return json.loads(path.read_text(encoding="utf-8"))


def build_primary_ordered_spec() -> OrderedModelSpec:
    """Build an OrderedModelSpec from the generated PRIMARY action spec (N_primary=8), using the
    EXPLICIT per-device N_max (per-class rule, r28 §5) — not a silent N_max=N_primary."""
    s = load_primary_spec()
    return OrderedModelSpec(
        device_order=tuple(s["device_order"]),
        beam_order=tuple(s["beam_order"]),
        power_order=tuple(s["power_order"]),
        version=s["version"],
        powers={k: float(v) for k, v in s["powers"].items()},
        n_max={d: int(v) for d, v in s["per_device_n_max"].items()},
        n_primary=s["N_primary"],
        beam_forbidden=frozenset(tuple(x) for x in s.get("beam_forbidden", [])),
        power_forbidden=frozenset(tuple(x) for x in s.get("power_forbidden", [])),
    )


def primary_default_state():
    """The primary per-device state (eligible + power_cap) schema-filled from the primary spec's
    per-device power caps — a convenience for callers/tests (eligible counts are runtime data)."""
    s = load_primary_spec()
    return {"power_cap": {d: float(v) for d, v in s["per_device_power_cap_w"].items()}}


# r29 §1: every decision-relevant field of the committed primary artifact is bound to a fresh
# regeneration from the locked scenario config — a subset check (signature + N/K/B/P only) let a
# spec with wrong physical values (power_3, per-device N_max, power cap) pass. These are ALL the
# fields build_spec() emits that fix the primary study's physics/topology.
_PRIMARY_BOUND_FIELDS = (
    "scenario_id", "version", "config_hash", "canonical_signature",
    "N_primary", "K", "B", "P", "n_static", "n_mobile",
    "device_order", "beam_order", "power_order", "powers",
    "class_map", "per_device_n_max", "per_device_power_cap_w",
    "beam_forbidden", "power_forbidden",
)


def assert_is_primary_spec(spec: OrderedModelSpec) -> None:
    """r27 §5 / r29 §1: reject a REFERENCE/toy spec passed where the PRIMARY spec is required, and
    FULLY bind the committed primary artifact to a fresh regeneration from the locked scenario
    config — comparing ALL decision-relevant fields (not a subset). A wrong power value, wrong
    per-device N_max, wrong power cap, wrong class map, or wrong forbidden set in
    primary_action_spec.json is therefore rejected, and the passed OrderedModelSpec's physical
    fields (orders, exact powers, per-device N_max, N/K/B/P, version, signature) must match too."""
    import generate_primary_action_spec as gen
    prim = load_primary_spec()
    cfg = load_primary_config()
    ref = load_reference_spec()
    # (0) a reference-tier spec (identity == the REFERENCE artifact) is rejected outright
    if spec.canonical_signature() == ref.get("canonical_signature"):
        raise ValueError("a REFERENCE/toy action spec was passed where the PRIMARY spec is required")

    # (A) committed artifact == fresh regeneration from the LOCKED scenario config, ALL fields
    expected = gen.build_spec(cfg)
    for f in _PRIMARY_BOUND_FIELDS:
        if prim.get(f) != expected.get(f):
            raise ValueError(
                f"primary_action_spec.json field {f!r} does not match a fresh regeneration from "
                f"primary_scenario_config.json (committed={prim.get(f)!r} expected={expected.get(f)!r}) "
                f"— regenerate with generate_primary_action_spec.py or fix the config")

    # (B) the passed OrderedModelSpec must match the committed primary artifact's decision fields
    if spec.version != prim["version"]:
        raise ValueError(f"spec.version {spec.version!r} != primary {prim['version']!r}")
    if spec.canonical_signature() != prim["canonical_signature"]:
        raise ValueError("spec ordered-id signature does not match the PRIMARY action spec")
    if list(spec.device_order) != list(prim["device_order"]) \
            or list(spec.beam_order) != list(prim["beam_order"]) \
            or list(spec.power_order) != list(prim["power_order"]):
        raise ValueError("spec order does not match the PRIMARY action spec orders")
    if spec.n_primary != int(prim["N_primary"]):
        raise ValueError(f"spec.n_primary {spec.n_primary} != primary N_primary {prim['N_primary']}")
    if {k: float(v) for k, v in spec.powers.items()} != \
            {k: float(v) for k, v in prim["powers"].items()}:
        raise ValueError("spec power values do not match the PRIMARY action spec exact watts")
    if {k: int(v) for k, v in spec.n_max.items()} != \
            {k: int(v) for k, v in prim["per_device_n_max"].items()}:
        raise ValueError("spec per-device N_max does not match the PRIMARY action spec")
    # r30 §1: the RUNTIME spec's forbidden sets must ALSO match the committed artifact — a spec
    # with tampered beam_forbidden/power_forbidden changes the feasible-token set and must fail.
    spec_beam_forbidden = {tuple(x) for x in spec.beam_forbidden}
    spec_power_forbidden = {tuple(x) for x in spec.power_forbidden}
    prim_beam_forbidden = {tuple(x) for x in prim.get("beam_forbidden", [])}
    prim_power_forbidden = {tuple(x) for x in prim.get("power_forbidden", [])}
    if spec_beam_forbidden != prim_beam_forbidden:
        raise ValueError("spec beam_forbidden does not match the PRIMARY action spec "
                         f"(spec={sorted(spec_beam_forbidden)} primary={sorted(prim_beam_forbidden)})")
    if spec_power_forbidden != prim_power_forbidden:
        raise ValueError("spec power_forbidden does not match the PRIMARY action spec "
                         f"(spec={sorted(spec_power_forbidden)} primary={sorted(prim_power_forbidden)})")
    # r30 §1: beam/power ORDER already checked above; version + signature pin the id ordering.
    if spec.B != len(prim["beam_order"]) or spec.P != len(prim["power_order"]) \
            or spec.K != len(prim["device_order"]):
        raise ValueError("spec K/B/P cardinality does not match the PRIMARY action spec")

    # (C) N/K/B/P also equal the locked scenario config (independent cross-check)
    if spec.n_primary != int(cfg["n_primary"]):
        raise ValueError(f"primary N {spec.n_primary} != scenario config n_primary {cfg['n_primary']}")
    if spec.K != int(cfg["n_static"]) + int(cfg["n_mobile"]):
        raise ValueError(f"primary K {spec.K} != n_static+n_mobile "
                         f"{int(cfg['n_static']) + int(cfg['n_mobile'])}")
    if spec.B != int(cfg["codebook_size"]):
        raise ValueError(f"primary B {spec.B} != codebook_size {cfg['codebook_size']}")
    if spec.P != int(cfg["power_levels"]):
        raise ValueError(f"primary P {spec.P} != power_levels {cfg['power_levels']}")


def primary_locked_power_caps() -> Dict[str, float]:
    """r29 §2: the LOCKED per-device total-power caps from the committed primary artifact. The
    primary mask path uses these; a caller may not loosen them."""
    prim = load_primary_spec()
    return {k: float(v) for k, v in prim["per_device_power_cap_w"].items()}


def validate_state(slot_start_state: Dict, spec: OrderedModelSpec) -> None:
    """r26 §6: reject incomplete/malformed state. Every canonical device must have a nonnegative
    integer eligible count and a nonnegative finite power cap; no unknown state keys."""
    if not isinstance(slot_start_state, Mapping):
        raise ValueError("slot_start_state must be a mapping")
    eligible = slot_start_state.get("eligible")
    power_cap = slot_start_state.get("power_cap")
    if not isinstance(eligible, Mapping):
        raise ValueError("slot_start_state['eligible'] is REQUIRED (mapping device->count)")
    if not isinstance(power_cap, Mapping):
        raise ValueError("slot_start_state['power_cap'] is REQUIRED (mapping device->cap; "
                         "no infinity default in the locked design)")
    devs = set(spec.device_order)
    for m, name in ((eligible, "eligible"), (power_cap, "power_cap")):
        unknown = set(m) - devs
        if unknown:
            raise ValueError(f"unknown device keys in {name}: {sorted(unknown)}")
        missing = devs - set(m)
        if missing:
            raise ValueError(f"{name} missing required devices: {sorted(missing)}")
    for k, c in eligible.items():
        if not isinstance(c, int) or isinstance(c, bool) or c < 0:
            raise ValueError(f"eligible[{k!r}]={c!r} must be a nonnegative integer")
    for k, cap in power_cap.items():
        if not (isinstance(cap, (int, float)) and math.isfinite(cap) and cap >= 0):
            raise ValueError(f"power_cap[{k!r}]={cap!r} must be nonnegative finite (no infinity)")


def _feasible_ids(slot_start_state: Dict, prefix_token_ids: Sequence[int],
                  subchannel_index: int, spec: OrderedModelSpec, verify_fn) -> frozenset:
    """Oracle feasible set as integer token ids, gated by `verify_fn(spec)` (identity check) +
    `validate_state` — neither is bypassable by the caller."""
    verify_fn(spec)                                      # identity check (reference OR primary)
    validate_state(slot_start_state, spec)               # r26 §6 state validation
    mp = spec.oracle_model_parameters(spec.n_primary)
    prefix_tuples = [decode_id(int(t), spec) for t in prefix_token_ids]  # malformed ids raise
    feas = oracle.compute_token_mask(slot_start_state, prefix_tuples, subchannel_index, mp)
    return frozenset(encode_tuple(tok, spec) for tok in feas)


# r28 §4: EXPLICIT reference vs primary mask APIs (no ambiguous alias).
def reference_feasible_ids(slot_start_state, prefix_token_ids, subchannel_index, spec):
    """Feasible token ids under the REFERENCE (toy) spec — verifies against reference_action_spec.json."""
    return _feasible_ids(slot_start_state, prefix_token_ids, subchannel_index, spec,
                         verify_against_reference)


def primary_feasible_ids(slot_start_state, prefix_token_ids, subchannel_index, spec):
    """Feasible token ids under the PRIMARY spec — verifies against primary_action_spec.json +
    the locked scenario config (N/K/B/P) and REJECTS a reference/toy spec.

    r29 §2: the per-device total-power cap is the LOCKED primary value; a caller may NOT silently
    override it. If the caller supplies `power_cap` it must equal the locked caps exactly (else
    ValueError); if omitted, the locked caps are injected. This makes it impossible to loosen the
    0.8 W primary cap by passing e.g. power_cap=100 W."""
    if not isinstance(slot_start_state, Mapping):
        raise ValueError("slot_start_state must be a mapping")
    locked = primary_locked_power_caps()
    st = dict(slot_start_state)
    caller_cap = st.get("power_cap")
    if caller_cap is not None:
        if {k: float(v) for k, v in caller_cap.items()} != locked:
            raise ValueError(
                "primary mask path: a caller may not override the LOCKED per-device power cap "
                f"(locked={locked}); omit power_cap or pass exactly the locked caps")
    st["power_cap"] = dict(locked)
    return _feasible_ids(st, prefix_token_ids, subchannel_index, spec, assert_is_primary_spec)


def compute_reference_boolean_token_mask(slot_start_state, prefix_token_ids, subchannel_index,
                                         spec) -> List[bool]:
    """Boolean mask (length 1+K*B*P) under the REFERENCE (toy) spec. Reference tests call this
    explicitly with `build_reference_ordered_spec()` / `reference_action_spec.json`."""
    ids = reference_feasible_ids(slot_start_state, prefix_token_ids, subchannel_index, spec)
    return codec.tokens_to_boolean_mask(ids, spec.K, spec.B, spec.P)


def compute_primary_boolean_token_mask(slot_start_state, prefix_token_ids, subchannel_index,
                                       spec) -> List[bool]:
    """Boolean mask (length 1+K*B*P) under the PRIMARY spec (N_primary=8 -> length 1+8*8*4=257).
    Verifies against primary_action_spec.json + the scenario config; a reference/toy spec is
    rejected."""
    ids = primary_feasible_ids(slot_start_state, prefix_token_ids, subchannel_index, spec)
    return codec.tokens_to_boolean_mask(ids, spec.K, spec.B, spec.P)


# r29 §3: the generic historical names must NOT silently select the REFERENCE (toy) tier.
# A caller must pick a tier explicitly via compute_reference_boolean_token_mask / reference_feasible_ids
# or compute_primary_boolean_token_mask / primary_feasible_ids.
def _tier_required(*_args, **_kwargs):
    raise NotImplementedError(
        "compute_boolean_token_mask/oracle_feasible_ids are removed (r29 §3): the generic API "
        "may not silently select the REFERENCE model. Call compute_reference_boolean_token_mask(...) "
        "for the toy/reference tier or compute_primary_boolean_token_mask(...) for the primary study.")


def compute_boolean_token_mask(*args, **kwargs):
    """Removed generic alias — choose a tier (r29 §3)."""
    return _tier_required(*args, **kwargs)


def oracle_feasible_ids(*args, **kwargs):
    """Removed generic alias — choose a tier (r29 §3)."""
    return _tier_required(*args, **kwargs)
