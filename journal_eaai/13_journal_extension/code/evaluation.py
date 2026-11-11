#!/usr/bin/env python3
"""Stage-F evaluation harness: R independent evaluation episodes of T slots per seed.

Implements JOURNAL_PROTOCOL_V1 decisions D1-D4 (10 x 250 measurement slots per seed) so that the
CMDP constraints are statistically resolvable, and reports the packet-level slack alongside every
constraint value. Archived ICAME results are never modified.
"""
from __future__ import annotations
import dataclasses, math
from typing import Dict, List
import numpy as np
from m2.config import confirmatory_config, ScenarioConfig
from m2.env import M2Env

EVAL_V2_NAMESPACE = 700_000_000          # distinct from the archived eval namespace (9e8)
BUDGET_ARCHIVED = dict(n_ep_train=8, n_updates=10, ppo_hidden=48)   # ICAME budget, unchanged

# Journal thresholds (protocol D2/D3). Static unchanged; mobile dv/ovf redesigned to be resolvable.
EPS_JOURNAL = {"static": 0.01, "mobile": 5e-3}
ETA_JOURNAL = {"static": 0.01, "mobile": 5e-3}
RHO         = {"static": 0.99, "mobile": 0.995}


def journal_cfg(load_p: float, t_meas: int = 250, **overrides) -> ScenarioConfig:
    cfg = confirmatory_config(load_p=load_p, **BUDGET_ARCHIVED)
    return dataclasses.replace(cfg, t_meas_slots=t_meas, **overrides)


def _per_class(v):
    """env.m entries may be per-class sequences or scalars; normalise to [static, mobile]."""
    if isinstance(v, (list, tuple, np.ndarray)):
        return float(v[0]), float(v[1])
    return float(v), 0.0


def run_episodes(agent_factory, cfg: ScenarioConfig, seed: int, R: int = 10) -> Dict:
    """Run R independent episodes; aggregate raw counts (not ratios) across episodes."""
    agg = dict(gen_s=0.0, gen_m=0.0, dlv_s=0.0, dlv_m=0.0, dv_s=0.0, dv_m=0.0,
               ov_s=0.0, ov_m=0.0, power=[], beam_acc=[], se=[], lat_p95=[], resid=0.0,
               sinr_lin=[], attempts=0.0, drop_retx=0.0, subch_util=[], power_hist=None)
    for r in range(R):
        env = M2Env(cfg, EVAL_V2_NAMESPACE + seed * 100 + r)
        ag = agent_factory(env)
        env.reset()
        if hasattr(ag, "reset"):
            ag.reset()
        obs = env.begin_slot(); done = False
        while not done:
            toks = ag.act(obs)
            nxt, rp, rb, cost, done, info = env.commit_action(toks)
            obs = nxt if nxt is not None else obs
        m = env.episode_metrics()
        agg["drop_retx"] += m.get("drop_retx", 0.0)
        agg["subch_util"].append(m.get("subch_util", 0.0))
        ph = getattr(ag, "power_hist", None)          # Stage-D.1 power-selection diagnostic
        if ph is not None:
            agg["power_hist"] = ph if agg["power_hist"] is None else \
                [a + b for a, b in zip(agg["power_hist"], ph)]
        agg["gen_s"] += m["gen_static"]; agg["gen_m"] += m["gen_mobile"]
        agg["dlv_s"] += m["dlv_static"]; agg["dlv_m"] += m["dlv_mobile"]
        dv_s, dv_m = _per_class(env.m.get("deadline_viol", env.m.get("drop_deadline", 0)))
        ov_s, ov_m = _per_class(env.m.get("overflow", 0))
        agg["dv_s"] += dv_s; agg["dv_m"] += dv_m
        agg["ov_s"] += ov_s; agg["ov_m"] += ov_m
        agg["power"].append(m["avg_power_w"]); agg["beam_acc"].append(m["beam_acc_oracle"])
        agg["se"].append(m["spectral_eff"]); agg["lat_p95"].append(m["lat_p95"])
        agg["resid"] += m["cohort_residual"]
    return agg


def summarise(agg: Dict) -> Dict:
    """Deterministic summary + constraint values with packet-level slack (protocol D4)."""
    gs, gm = agg["gen_s"], agg["gen_m"]
    out = {
        "gen_static": gs, "gen_mobile": gm,
        "dlv_static": agg["dlv_s"], "dlv_mobile": agg["dlv_m"],
        "pdr_static": agg["dlv_s"] / max(gs, 1), "pdr_mobile": agg["dlv_m"] / max(gm, 1),
        "pdr": (agg["dlv_s"] + agg["dlv_m"]) / max(gs + gm, 1),
        "avg_power_w": float(np.mean(agg["power"])), "power_sd": float(np.std(agg["power"], ddof=1)) if len(agg["power"]) > 1 else 0.0,
        "beam_acc_oracle": float(np.mean(agg["beam_acc"])),
        "spectral_eff": float(np.mean(agg["se"])), "lat_p95": float(np.mean(agg["lat_p95"])),
        "cohort_residual": agg["resid"],
        "dv_static": agg["dv_s"], "dv_mobile": agg["dv_m"],
        "ov_static": agg["ov_s"], "ov_mobile": agg["ov_m"],
        "drop_retx": agg["drop_retx"],
        "subch_util": float(np.mean(agg["subch_util"])) if agg["subch_util"] else 0.0,
    }
    ph = agg.get("power_hist")
    if ph:
        tot = max(sum(ph), 1)
        for i, lvl in enumerate(("p05", "p10", "p20", "p40")[:len(ph)]):
            out[f"frac_{lvl}"] = ph[i] / tot
        out["n_tx"] = sum(ph)
        out["mean_tx_power_w"] = (sum(ph[i] * w for i, w in enumerate([0.05, 0.10, 0.20, 0.40][:len(ph)]))
                                  / tot)
    # constraint values (feasible when <= 0) and slack in packets
    for c, g, d, dv, ov in (("static", gs, agg["dlv_s"], agg["dv_s"], agg["ov_s"]),
                            ("mobile", gm, agg["dlv_m"], agg["dv_m"], agg["ov_m"])):
        out[f"C_rel_{c}"] = RHO[c] * g - d
        out[f"C_dv_{c}"] = dv - EPS_JOURNAL[c] * g
        out[f"C_over_{c}"] = ov - ETA_JOURNAL[c] * g
        out[f"slack_rel_{c}_pkts"] = (1 - RHO[c]) * g
        out[f"slack_dv_{c}_pkts"] = EPS_JOURNAL[c] * g
        out[f"slack_ov_{c}_pkts"] = ETA_JOURNAL[c] * g
    out["feasible_all"] = int(all(out[f"C_{x}_{c}"] <= 0
                                  for x in ("rel", "dv", "over") for c in ("static", "mobile")))
    return out
