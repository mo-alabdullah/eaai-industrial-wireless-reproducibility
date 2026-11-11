#!/usr/bin/env python3
"""STAGE I-B - exact finite-horizon JOINT control benchmark on fixed realised traces.

Comparators per trace (all on the SAME trace, so differences are purely control decisions):
  1 edf      EDF greedy + best-stale-beam + min-feasible power          (deployable heuristic)
  2 edfrad   EDF scheduling, but the per-slot radio subproblem solved EXACTLY (aged CSI)
  3 joint    EXACT joint scheduling + radio over the horizon            (aged CSI, deployable info)
  4 oracle   EXACT joint over the horizon with CURRENT CSI              (ORACLE / NON-DEPLOYABLE)

Decomposition:  1->2 radio-allocation loss;  2->3 scheduling/temporal loss;  3->4 information loss.
Development seeds 10001-10008 only.
"""
from __future__ import annotations
import argparse, csv, dataclasses, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

from evaluation import journal_cfg
from optimization.grids import with_grid
from optimization.joint import (record_trace, solve_exact_joint, rollout_policy, edf_min_feasible,
                                execute_plan, ReplayModel, slot_state, BudgetExceeded)
from optimization.radio import solve_exact_radio_fixed_demand, cell_cost

SEEDS = list(range(10001, 10009))
WARMUPS = (20, 60, 100, 140, 180)
REGIMES = {"R1_nominal": (1.0, 1), "R4_moderate": (1.5, 3), "R2_range": (2.0, 1), "R3_aged": (2.0, 5)}
GRIDS = ("G0_icame", "G2_wide10")
SCALES = {"full_K8N4_H3": dict(Ks=6, Km=2, N=4, H=3),
          "red_K4N2_H6":  dict(Ks=3, Km=1, N=2, H=6)}
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_ib_joint.jsonl")
CSV = os.path.join(RES, "stage_ib_joint.csv")


def edf_then_exact_radio(use_true=False):
    """EDF picks WHICH packets; the exact allocator places them on subchannels/beams/powers."""
    greedy = edf_min_feasible(use_true)
    def chooser(tr, st, m):
        base = greedy(tr, st, m)
        demand = {}
        for a in base:
            if a is not None:
                demand[a[0]] = demand.get(a[0], 0) + 1
        if not demand:
            return base
        ex = solve_exact_radio_fixed_demand(st, demand, use_true=use_true)
        if ex.power_w == float("inf"):
            return base
        return tuple(ex.tokens)
    return chooser


def build_cfg(scale, regime, grid):
    dist, age = REGIMES[regime]
    s = SCALES[scale]
    cfg = journal_cfg(0.40, t_meas=400, hall_x=300.0 * dist, hall_y=150.0 * dist, d_csi_slots=age)
    cfg = with_grid(cfg, grid)
    return dataclasses.replace(cfg, n_static=s["Ks"], n_mobile=s["Km"], n_subchannels=s["N"],
                               n_max_static=min(cfg.n_max_static, s["N"]),
                               n_max_mobile=min(cfg.n_max_mobile, s["N"]))


def run_one(job):
    scale, regime, grid, seed, warm = job
    cfg = build_cfg(scale, regime, grid)
    H = SCALES[scale]["H"]
    tr = record_trace(cfg, seed=700_000_000 + seed * 100, H=H, warmup=warm)
    out = dict(scale=scale, regime=regime, grid=grid, seed=seed, warmup=warm, H=H,
               K=tr.K, N=tr.N, P=len(tr.power_grid),
               dist_scale=REGIMES[regime][0], d_csi=REGIMES[regime][1])
    d, p = rollout_policy(tr, edf_min_feasible(False)); out.update(edf_dlv=d, edf_pw=p)
    d, p = rollout_policy(tr, edf_then_exact_radio(False)); out.update(edfrad_dlv=d, edfrad_pw=p)
    for tag, ut in (("joint", False), ("oracle", True)):
        t0 = time.perf_counter()
        try:
            dl, pw, nodes, states, plan = solve_exact_joint(
                tr, use_true=ut, max_nodes=3_000_000, max_seconds=45.0, return_plan=True)
            rdl, rpw, skipped = execute_plan(tr, plan)
            out.update({f"{tag}_dlv": rdl, f"{tag}_pw": rpw,          # REALISED outcome
                        f"{tag}_planned_dlv": dl, f"{tag}_planned_pw": pw,
                        f"{tag}_skipped": skipped,
                        f"{tag}_nodes": nodes,
                        f"{tag}_states": states, f"{tag}_cpu": time.perf_counter() - t0,
                        f"{tag}_status": "exact"})
        except BudgetExceeded as e:
            out.update({f"{tag}_dlv": None, f"{tag}_pw": None, f"{tag}_nodes": e.nodes,
                        f"{tag}_states": e.states, f"{tag}_cpu": e.seconds,
                        f"{tag}_status": "budget_exceeded"})
    return out


def jobs_all():
    return [(sc, r, g, s, w) for sc in SCALES for r in REGIMES for g in GRIDS
            for s in SEEDS for w in WARMUPS]


def key(j): return "|".join(str(x) for x in j)


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
        rows.sort(key=lambda r: (r["scale"], r["grid"], r["regime"], r["seed"], r["warmup"]))
        cols = sorted({k for r in rows for k in r})
        head = ["scale", "regime", "grid", "seed", "warmup", "H", "K", "N", "P", "dist_scale", "d_csi"]
        cols = head + [c for c in cols if c not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        for x in open(JSONL):
            if x.strip():
                r = json.loads(x)
                have.add(key((r["scale"], r["regime"], r["grid"], r["seed"], r["warmup"])))
    todo = [j for j in js if key(j) not in have]
    print(f"total={len(js)} done={len(have)} todo={len(todo)}")
    if not todo:
        print("ALL DONE"); return
    t0 = time.time(); n = 0
    with Pool(a.workers) as pool, open(JSONL, "a") as f:
        for res in pool.imap_unordered(run_one, todo, chunksize=1):
            f.write(json.dumps(res) + "\n"); f.flush(); n += 1
            if time.time() - t0 > a.budget:
                break
    print(f"completed {n} this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
