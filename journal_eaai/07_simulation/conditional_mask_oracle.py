#!/usr/bin/env python3
"""Pure conditional-mask ORACLE (Gate-M1 DESIGN artifact — NOT a simulator).

`compute_token_mask(...)` returns the **feasible token set** for one decoder position, computed
**before sampling**, from the slot-start environment state and the already-emitted decoder
prefix. It is the on-paper specification of the packet-aware conditional mask
(`../06_mathematical_model/action_builder_feasibility_rules.md`,
`../06_mathematical_model/multi_subchannel_packet_service.md`): the policy can only *sample* a
feasible token, so **no selected non-idle token ever needs environment-side repair**
(`post_hoc_action_repair = forbidden`).

This module has **no** channel, mobility, queue-dynamics, SINR, reward, or RNG — it is a
deterministic feasibility function only. It does NOT train, roll out, or simulate anything.

Token alphabet (one flat `Discrete(1+K*B*P)` per decoder position):
  - "idle"                      (always feasible)
  - (device_k, beam_b, power_p) (feasible iff all conditions below hold)

Feasibility conditions enforced BEFORE sampling, at decoder position `subchannel_index = n`,
given the prefix tokens already emitted for subchannels < n:
  1. Remaining eligible packets: remaining_eligible_k = eligible_k - (# non-idle prefix tokens
     for k). If <= 0, every non-idle token for k is masked out (surplus -> explicit idle only).
  2. Per-user subchannel cap N_max_k: if (# prefix tokens for k) >= N_max_k, mask out (k,*,*).
  3. Remaining per-device power: committed_power_k(prefix) + power(p) <= P_tot_k.
  4. Beam validity: (n, b) not in the subchannel's forbidden-beam set.
  5. Power-level validity: (n, p) not in the subchannel's forbidden-power set.
  6. Explicit idle is always available.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Sequence, Set, Tuple, Union

Token = Union[str, Tuple[str, str, str]]   # "idle" or (device, beam, power)
_EPS = 1e-12
IDLE: Token = "idle"


def _is_idle(tok: Token) -> bool:
    return tok == IDLE


def _prefix_stats(decoder_prefix: Sequence[Token]) -> Tuple[Dict[str, int], Dict[str, float]]:
    """Return (assigned_count_per_device, committed_power_per_device) from the prefix."""
    counts: Dict[str, int] = {}
    power: Dict[str, float] = {}
    for tok in decoder_prefix:
        if _is_idle(tok):
            continue
        if not (isinstance(tok, tuple) and len(tok) == 3):
            raise ValueError(f"prefix token must be 'idle' or (device,beam,power): {tok!r}")
        k, _b, _p = tok
        counts[k] = counts.get(k, 0) + 1
    return counts, power


def _require_full_device_map(m, devices: Set[str], name: str, *, kind: str) -> None:
    """r29 §4: a locked-semantics map must cover EVERY canonical device exactly — no missing
    device (which would silently default to 0 or +inf) and no unknown/extra device. `kind` is
    'count' (nonnegative int) or 'power' (nonnegative finite float)."""
    if not isinstance(m, dict):  # a real mapping is required (None/absent -> reject)
        raise ValueError(f"{name} is REQUIRED as a mapping covering every canonical device "
                         f"{sorted(devices)} (no missing-value default in the locked design)")
    missing = devices - set(m)
    if missing:
        raise ValueError(f"{name} missing required devices {sorted(missing)} — no default "
                         f"to zero/infinity is permitted in the locked mask authority")
    extra = set(m) - devices
    if extra:
        raise ValueError(f"{name} has unknown/extra devices {sorted(extra)}")
    for k, v in m.items():
        if kind == "count":
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{name}[{k!r}]={v!r} must be a nonnegative integer")
        else:  # power
            import math as _math
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and _math.isfinite(v) and v >= 0):
                raise ValueError(f"{name}[{k!r}]={v!r} must be nonnegative finite (no infinity)")


def _validate_model_domain(model_parameters: Dict, N: int) -> None:
    """r30 §2: the STANDALONE oracle validates its own mathematical domain (do NOT rely on
    OrderedModelSpec to keep the oracle safe):
      - devices/beams/powers non-empty and unique;
      - every power value finite and > 0;
      - 1 <= n_max[k] <= N for every canonical device (N_max=0 not permitted — r30 §4/r32 §7);
      - every forbidden subchannel index in 1..N;
      - every forbidden beam id canonical; every forbidden power id canonical."""
    import math as _math
    device_list = list(model_parameters["devices"])
    beam_ids = list(model_parameters["beams"])          # dict -> keys, list -> items
    powers = model_parameters["powers"]
    power_ids = list(powers)
    for name, seq in (("devices", device_list), ("beams", beam_ids), ("powers", power_ids)):
        if len(seq) < 1:
            raise ValueError(f"model_parameters['{name}'] must be non-empty")
        if len(set(seq)) != len(seq):
            raise ValueError(f"model_parameters['{name}'] has duplicate ids: {seq!r}")
    if not isinstance(powers, dict):
        raise ValueError("model_parameters['powers'] must map power id -> watts")
    for p, v in powers.items():
        if not (isinstance(v, (int, float)) and not isinstance(v, bool)
                and _math.isfinite(v) and v > 0):
            raise ValueError(f"power {p!r} value must be finite and > 0, got {v!r}")
    n_max = model_parameters["n_max"]
    for k, nm in n_max.items():
        # r30 §4 canonical domain: 1 <= N_max <= N (a canonical device participates in >=1
        # subchannel; N_max=0 is NOT permitted — disable a device by removing it from the set).
        if not isinstance(nm, int) or isinstance(nm, bool) or not (1 <= nm <= N):
            raise ValueError(f"n_max[{k!r}]={nm!r} must be an int in 1..N ({N}); "
                             f"N_max=0 is not permitted (remove the device to disable it)")
    beams_set, powers_set = set(beam_ids), set(power_ids)
    for pair in set(model_parameters.get("beam_forbidden", set())):
        if not (isinstance(pair, tuple) and len(pair) == 2):
            raise ValueError(f"beam_forbidden entry must be (subchannel, beam_id): {pair!r}")
        sc, b = pair
        if not (isinstance(sc, int) and not isinstance(sc, bool) and 1 <= sc <= N):
            raise ValueError(f"beam_forbidden subchannel {sc!r} not in 1..N ({N})")
        if b not in beams_set:
            raise ValueError(f"beam_forbidden beam id {b!r} is not a canonical beam")
    for pair in set(model_parameters.get("power_forbidden", set())):
        if not (isinstance(pair, tuple) and len(pair) == 2):
            raise ValueError(f"power_forbidden entry must be (subchannel, power_id): {pair!r}")
        sc, p = pair
        if not (isinstance(sc, int) and not isinstance(sc, bool) and 1 <= sc <= N):
            raise ValueError(f"power_forbidden subchannel {sc!r} not in 1..N ({N})")
        if p not in powers_set:
            raise ValueError(f"power_forbidden power id {p!r} is not a canonical power")


def _validate_inputs(slot_start_state: Dict, decoder_prefix: Sequence[Token],
                     subchannel_index: int, model_parameters: Dict) -> None:
    """r24 §11: a malformed prefix must NOT influence a supposedly valid mask — reject it.
    r29 §4: eligible, power_cap and n_max must each cover every canonical device exactly; no
    missing value may default to 0/+inf and no unknown device may be supplied.
    r30 §2: the oracle also validates its own mathematical domain (`_validate_model_domain`)."""
    devices = set(model_parameters["devices"])
    beams = set(model_parameters["beams"])
    powers = set(model_parameters["powers"])
    N = model_parameters.get("N")
    if N is None:
        raise ValueError("model_parameters must carry N (number of subchannels)")
    if not isinstance(N, int) or N < 1:
        raise ValueError(f"N must be a positive int, got {N!r}")
    # r29 §4: STRICT locked-semantics coverage (the oracle itself, not only the wrapper)
    if not isinstance(slot_start_state, dict):
        raise ValueError("slot_start_state must be a mapping")
    _require_full_device_map(slot_start_state.get("eligible"), devices, "eligible", kind="count")
    _require_full_device_map(slot_start_state.get("power_cap"), devices, "power_cap", kind="power")
    _require_full_device_map(model_parameters.get("n_max"), devices, "n_max", kind="count")
    _validate_model_domain(model_parameters, N)          # r30 §2 domain safety
    # N must match the configured primary/topology value if one is supplied
    n_primary = model_parameters.get("n_primary")
    if n_primary is not None and N != n_primary:
        raise ValueError(f"model N={N} does not match n_primary={n_primary}")
    if not isinstance(subchannel_index, int) or not (1 <= subchannel_index <= N):
        raise ValueError(f"subchannel_index {subchannel_index} not in 1..N ({N})")
    if len(decoder_prefix) != subchannel_index - 1:
        raise ValueError(f"decoder_prefix length {len(decoder_prefix)} != subchannel_index-1 "
                         f"({subchannel_index - 1})")
    # every prefix token must use canonical IDs, and must itself have been FEASIBLE at its own
    # decoder position (recompute the mask for the shorter prefix and check membership).
    for i, tok in enumerate(decoder_prefix, start=1):
        if _is_idle(tok):
            continue
        if not (isinstance(tok, tuple) and len(tok) == 3):
            raise ValueError(f"prefix token {i} malformed: {tok!r}")
        k, b, p = tok
        if k not in devices:
            raise ValueError(f"prefix token {i}: unknown device {k!r}")
        if b not in beams:
            raise ValueError(f"prefix token {i}: unknown beam {b!r}")
        if p not in powers:
            raise ValueError(f"prefix token {i}: unknown power {p!r}")
        feasible_here = compute_token_mask(slot_start_state, decoder_prefix[:i - 1], i,
                                           model_parameters)
        if tok not in feasible_here:
            raise ValueError(f"prefix token {i} ({tok!r}) was NOT feasible at its own "
                             f"decoder position {i}")


def compute_token_mask(slot_start_state: Dict,
                       decoder_prefix: Sequence[Token],
                       subchannel_index: int,
                       model_parameters: Dict) -> FrozenSet[Token]:
    """Feasible token set at decoder position `subchannel_index`, computed before sampling.

    slot_start_state (r29 §4 — every map REQUIRED and must cover every canonical device):
        eligible:  {device: eligible_packet_count_at_slot_start}  (REQUIRED; no default)
        power_cap: {device: P_tot}                                (REQUIRED; no +inf default)
    model_parameters:
        devices:   [device ids]
        beams:     {beam_id: gain}   (or iterable of beam ids)
        powers:    {power_id: watts} (power value used for the cap)
        N:         number of subchannels (REQUIRED; 1 <= subchannel_index <= N)
        n_primary: optional configured N to cross-check against (must equal N)
        n_max:     {device: cap}     (REQUIRED; must cover every device; no +inf default)
        beam_forbidden:  set of (subchannel_index, beam_id)
        power_forbidden: set of (subchannel_index, power_id)
    eligible, power_cap and n_max must each cover EXACTLY the canonical device set — a missing
    device is rejected (no silent 0/+inf default) and an unknown device is rejected.
    Returns a frozenset of feasible tokens (always includes "idle"). Raises ValueError on a
    malformed prefix / out-of-range index / unknown ID / incomplete device map (r24 §11, r29 §4).
    """
    _validate_inputs(slot_start_state, decoder_prefix, subchannel_index, model_parameters)
    eligible: Dict[str, int] = dict(slot_start_state["eligible"])
    power_cap: Dict[str, float] = dict(slot_start_state["power_cap"])
    devices: List[str] = list(model_parameters["devices"])
    beams = model_parameters["beams"]
    powers: Dict[str, float] = dict(model_parameters["powers"])
    n_max: Dict[str, float] = dict(model_parameters["n_max"])
    beam_forbidden: Set[Tuple[int, str]] = set(model_parameters.get("beam_forbidden", set()))
    power_forbidden: Set[Tuple[int, str]] = set(model_parameters.get("power_forbidden", set()))

    # committed power from the prefix (uses the model's power values, not the token label)
    assigned, _ = _prefix_stats(decoder_prefix)
    committed: Dict[str, float] = {}
    for tok in decoder_prefix:
        if _is_idle(tok):
            continue
        k, _b, p = tok
        committed[k] = committed.get(k, 0.0) + float(powers[p])

    feasible: Set[Token] = {IDLE}   # rule 6: explicit idle always available
    for k in devices:
        remaining_eligible = eligible[k] - assigned.get(k, 0)   # eligible[k] REQUIRED (r29 §4)
        if remaining_eligible <= 0:               # rule 1
            continue
        if assigned.get(k, 0) >= n_max[k]:        # rule 2 (n_max[k] REQUIRED; no +inf default)
            continue
        cap = power_cap[k]                         # rule 3 cap REQUIRED (no +inf default)
        for b in beams:
            if (subchannel_index, b) in beam_forbidden:        # rule 4
                continue
            for p in powers:
                if (subchannel_index, p) in power_forbidden:   # rule 5
                    continue
                if committed.get(k, 0.0) + float(powers[p]) > cap + _EPS:   # rule 3
                    continue
                feasible.add((k, b, p))
    return frozenset(feasible)


def token_is_feasible(tok: Token, slot_start_state, decoder_prefix,
                      subchannel_index, model_parameters) -> bool:
    """Convenience: is a specific token in the pre-sampling feasible set?"""
    return tok in compute_token_mask(slot_start_state, decoder_prefix,
                                     subchannel_index, model_parameters)
