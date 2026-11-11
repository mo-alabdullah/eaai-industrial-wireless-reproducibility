#!/usr/bin/env python3
"""Deterministically generate the PRIMARY action spec from the locked primary scenario config
(r27 §5). The ordering RULE (not hard-coded device ids) maps the scenario to canonical ordered
id tuples; a config hash + ordered-id signature + version pin the identity.

Usage:  python3 07_simulation/generate_primary_action_spec.py
Writes: 07_simulation/primary_action_spec.json  (idempotent — same config -> same bytes)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "primary_scenario_config.json"
OUT = HERE / "primary_action_spec.json"


def _canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _pos_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _nonneg_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def validate_primary_scenario_config(cfg: dict) -> None:
    """r31 §5: reject an invalid primary scenario config BEFORE building the action spec.
    Independent review found build_spec accepted negative caps, negative/duplicate power levels,
    and a zero-device scenario — all now rejected here."""
    import math as _math
    if not isinstance(cfg, dict):
        raise ValueError("primary scenario config must be a mapping")
    for key in ("scenario_id", "config_version"):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    ks, km = cfg.get("n_static"), cfg.get("n_mobile")
    if not _nonneg_int(ks) or not _nonneg_int(km):
        raise ValueError("n_static and n_mobile must be nonnegative integers")
    if ks + km < 1:
        raise ValueError("K = n_static + n_mobile must be >= 1 (a zero-device scenario is invalid)")
    for key in ("codebook_size", "power_levels", "n_primary", "n_antennas"):
        if not _pos_int(cfg.get(key)):
            raise ValueError(f"{key} must be a positive integer")
    N, B, P = int(cfg["n_primary"]), int(cfg["codebook_size"]), int(cfg["power_levels"])
    if B != int(cfg["n_antennas"]):
        raise ValueError(f"codebook_size ({B}) must equal n_antennas ({cfg['n_antennas']}) — "
                         "one DFT beam per ULA steering index (r30 §10)")
    watts = cfg.get("power_level_watts")
    if not isinstance(watts, list) or len(watts) != P:
        raise ValueError(f"power_level_watts must be a list of length power_levels ({P})")
    for w in watts:
        if not (isinstance(w, (int, float)) and not isinstance(w, bool)
                and _math.isfinite(w) and w > 0):
            raise ValueError(f"every power level must be finite and > 0, got {w!r}")
    if len(set(watts)) != len(watts):
        raise ValueError(f"power_level_watts must be unique, got {watts!r}")
    for key in ("n_max_static", "n_max_mobile"):
        nm = cfg.get(key)
        if not (_pos_int(nm) and 1 <= nm <= N):
            raise ValueError(f"{key}={cfg.get(key)!r} must be an int in the canonical domain "
                             f"1..N_primary ({N}) — N_max=0 is not permitted (r30 §4)")
    cap = cfg.get("per_device_total_power_cap_w")
    if not (isinstance(cap, (int, float)) and not isinstance(cap, bool)
            and _math.isfinite(cap) and cap > 0):
        raise ValueError(f"per_device_total_power_cap_w must be finite and > 0, got {cap!r}")
    # r31 §6: the committed alphabet must use the PRIMARY power grid, not a sensitivity variant.
    if "primary_power_grid_w" in cfg and list(cfg["primary_power_grid_w"]) != list(watts):
        raise ValueError("power_level_watts must equal primary_power_grid_w (the committed spec "
                         "always uses the PRIMARY grid, never a sensitivity variant — r31 §6)")


def build_spec(cfg: dict) -> dict:
    validate_primary_scenario_config(cfg)                # r31 §5: fail-fast on an invalid config
    ks, km = int(cfg["n_static"]), int(cfg["n_mobile"])
    B, P, N = int(cfg["codebook_size"]), int(cfg["power_levels"]), int(cfg["n_primary"])
    watts = list(cfg["power_level_watts"])
    n_antennas = int(cfg["n_antennas"])
    # ORDERING RULE (deterministic; not hard-coded ids): static-first then mobile; beams by
    # codebook index; powers by ascending watts.
    device_order = [f"static_{i}" for i in range(ks)] + [f"mobile_{j}" for j in range(km)]
    beam_order = [f"beam_{b}" for b in range(B)]
    power_pairs = sorted(range(P), key=lambda i: watts[i])
    power_order = [f"power_{i}" for i in power_pairs]
    powers = {f"power_{i}": float(watts[i]) for i in range(P)}
    config_hash = hashlib.sha256(_canonical_json(cfg).encode()).hexdigest()
    signature = hashlib.sha256(
        repr((tuple(device_order), tuple(beam_order), tuple(power_order))).encode()).hexdigest()
    # r28 §5 / r30 §4: explicit per-device N_max (per-class rule; canonical domain 1..N_primary).
    nmax_static, nmax_mobile = int(cfg["n_max_static"]), int(cfg["n_max_mobile"])
    cap = float(cfg["per_device_total_power_cap_w"])
    class_of = {f"static_{i}": "static" for i in range(ks)}
    class_of.update({f"mobile_{j}": "mobile" for j in range(km)})
    per_device_n_max = {d: (nmax_static if class_of[d] == "static" else nmax_mobile)
                        for d in device_order}
    per_device_power_cap_w = {d: cap for d in device_order}
    return {
        "_comment": "PRIMARY action spec generated from primary_scenario_config.json by "
                    "generate_primary_action_spec.py (r27 §5 / r28 §5). Do not hand-edit.",
        "tier": "primary",
        "scenario_id": cfg["scenario_id"],
        "version": cfg["config_version"],
        "config_hash": config_hash,
        "canonical_signature": signature,
        "N_primary": N,
        "K": ks + km, "B": B, "P": P,
        "n_static": ks, "n_mobile": km,
        "device_order": device_order,
        "beam_order": beam_order,
        "power_order": power_order,
        "powers": powers,
        "class_map": class_of,
        "per_device_n_max": per_device_n_max,
        "per_device_power_cap_w": per_device_power_cap_w,
        "beam_forbidden": [],
        "power_forbidden": [],
        "ordering_rule": cfg["ordering_rule"],
    }


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    spec = build_spec(cfg)
    OUT.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"primary_action_spec.json written: N_primary={spec['N_primary']} "
          f"K={spec['K']} B={spec['B']} P={spec['P']} sig={spec['canonical_signature'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
