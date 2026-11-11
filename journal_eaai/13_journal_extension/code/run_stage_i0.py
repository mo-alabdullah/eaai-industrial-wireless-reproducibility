#!/usr/bin/env python3
"""STAGE I0 - power-grid floor sensitivity.  Development seeds 10001-10008 only.

Resumable: appends JSONL, skips completed keys, honours --budget (tool-call wall-clock ceiling).
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

from evaluation import journal_cfg, run_episodes, summarise
from baselines_v2 import ComponentAgent, ORACLE_RULES
from optimization.grids import GRIDS, with_grid, hist_stats

SEEDS = list(range(10001, 10009))
LOADS = (0.20, 0.40)
DISTS = (1.0, 1.5, 2.0)
AGES = (1, 5)
GRID_KEYS = ("G0_icame", "G1_ext7", "G2_wide10")
METHODS = (("StaleBest", "MinFeasible-Stale"),
           ("OracleBest", "MinFeasible-Stale"),
           ("StaleBest", "Pmin"),
           ("OracleBest", "Pmin"))
R, T = 4, 250
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_i0.jsonl")
CSV = os.path.join(RES, "stage_i0.csv")


def jobs_all():
    return [(gk, beam, power, load, dist, age, seed)
            for gk in GRID_KEYS for (beam, power) in METHODS
            for load in LOADS for dist in DISTS for age in AGES for seed in SEEDS]


def key(j): return "|".join(str(x) for x in j)


def one(job):
    gk, beam, power, load, dist, age, seed = job
    cfg = journal_cfg(load, t_meas=T, hall_x=300.0 * dist, hall_y=150.0 * dist, d_csi_slots=age)
    cfg = with_grid(cfg, gk)
    mk = lambda env: ComponentAgent(env, seed=seed, scheduler="EDF",
                                    beam_rule=beam, power_rule=power)
    agg = run_episodes(mk, cfg, seed=seed, R=R)
    s = summarise(agg)
    for stale in [k for k in s if k.startswith("frac_p") or k in ("mean_tx_power_w",)]:
        s.pop(stale)                      # drop the 4-level-hard-coded fields; recompute grid-aware
    s.update(hist_stats(agg.get("power_hist"), cfg.power_grid_w))
    s.update(grid=gk, grid_floor_w=cfg.power_grid_w[0], n_levels=len(cfg.power_grid_w),
             beam_rule=beam, power_rule=power, load=load, dist_scale=dist, d_csi=age,
             seed=seed, R=R, T_meas=T, method=f"EDF-{beam}-{power}",
             uses_oracle=int(beam in ORACLE_RULES or power in ORACLE_RULES))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    js = jobs_all()
    if a.csv:
        rows = [json.loads(x) for x in open(JSONL) if x.strip()]
        rows.sort(key=lambda r: (r["grid"], r["power_rule"], r["beam_rule"], r["load"],
                                 r["dist_scale"], r["d_csi"], r["seed"]))
        head = ["method", "grid", "grid_floor_w", "n_levels", "beam_rule", "power_rule",
                "uses_oracle", "load", "dist_scale", "d_csi", "seed", "R", "T_meas"]
        cols = head + [k for k in sorted({k for r in rows for k in r}) if k not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
            w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        for x in open(JSONL):
            if x.strip():
                r = json.loads(x)
                have.add(key((r["grid"], r["beam_rule"], r["power_rule"], r["load"],
                              r["dist_scale"], r["d_csi"], r["seed"])))
    todo = [j for j in js if key(j) not in have]
    print(f"total={len(js)} done={len(have)} todo={len(todo)}")
    if not todo:
        print("ALL DONE"); return
    t0 = time.time(); n = 0
    with Pool(a.workers) as pool, open(JSONL, "a") as f:
        for res in pool.imap_unordered(one, todo, chunksize=2):
            f.write(json.dumps(res) + "\n"); f.flush(); n += 1
            if time.time() - t0 > a.budget:
                break
    print(f"completed {n} this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
