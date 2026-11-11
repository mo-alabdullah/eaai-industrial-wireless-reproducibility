#!/usr/bin/env python3
"""STAGE I-CLOSEOUT task 1 - resolve the traces that exceeded the Stage-I-B enumeration budget.

Re-runs ONLY the censored traces with a substantially larger node/time budget. A heuristic result is
never substituted for an exact one: a trace that still exceeds the raised budget is written with
status 'barrier' and stays censored in every table.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

import run_stage_ib as IB
from optimization.joint import (record_trace, solve_exact_joint, execute_plan, rollout_policy,
                                edf_min_feasible, BudgetExceeded)

MAX_NODES = 200_000_000          # raised from 3e6
MAX_SECONDS = 600.0              # raised from 45 s
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_ib_closeout.jsonl")
CSV = os.path.join(RES, "stage_ib_closeout.csv")


def censored_jobs():
    src = os.path.join(RES, "stage_ib_joint.jsonl")
    out = []
    for line in open(src):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("joint_status") != "exact" or d.get("oracle_status") != "exact":
            out.append((d["scale"], d["regime"], d["grid"], d["seed"], d["warmup"]))
    return sorted(set(out))


def key(j): return "|".join(str(x) for x in j)


def run_one(job):
    scale, regime, grid, seed, warm = job
    cfg = IB.build_cfg(scale, regime, grid)
    H = IB.SCALES[scale]["H"]
    tr = record_trace(cfg, seed=700_000_000 + seed * 100, H=H, warmup=warm)
    out = dict(scale=scale, regime=regime, grid=grid, seed=seed, warmup=warm, H=H,
               K=tr.K, N=tr.N, P=len(tr.power_grid),
               dist_scale=IB.REGIMES[regime][0], d_csi=IB.REGIMES[regime][1],
               max_nodes=MAX_NODES, max_seconds=MAX_SECONDS)
    d, p = rollout_policy(tr, edf_min_feasible(False)); out.update(edf_dlv=d, edf_pw=p)
    d, p = rollout_policy(tr, IB.edf_then_exact_radio(False)); out.update(edfrad_dlv=d, edfrad_pw=p)
    for tag, ut in (("joint", False), ("oracle", True)):
        t0 = time.perf_counter()
        try:
            dl, pw, nodes, states, plan = solve_exact_joint(
                tr, use_true=ut, max_nodes=MAX_NODES, max_seconds=MAX_SECONDS, return_plan=True)
            rdl, rpw, skipped = execute_plan(tr, plan)
            out.update({f"{tag}_dlv": rdl, f"{tag}_pw": rpw,
                        f"{tag}_planned_dlv": dl, f"{tag}_planned_pw": pw,
                        f"{tag}_skipped": skipped, f"{tag}_nodes": nodes, f"{tag}_states": states,
                        f"{tag}_cpu": time.perf_counter() - t0, f"{tag}_status": "exact"})
        except BudgetExceeded as e:
            out.update({f"{tag}_dlv": None, f"{tag}_pw": None, f"{tag}_nodes": e.nodes,
                        f"{tag}_states": e.states, f"{tag}_cpu": e.seconds,
                        f"{tag}_status": "barrier"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    js = censored_jobs()
    if a.csv:
        rows = [json.loads(x) for x in open(JSONL) if x.strip()]
        rows.sort(key=lambda r: (r["regime"], r["grid"], r["seed"], r["warmup"]))
        cols = sorted({k for r in rows for k in r})
        head = ["scale", "regime", "grid", "seed", "warmup", "joint_status", "oracle_status"]
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
    print(f"censored={len(js)} done={len(have)} todo={len(todo)}")
    if not todo:
        print("ALL DONE"); return
    t0 = time.time(); n = 0
    with Pool(a.workers) as pool, open(JSONL, "a") as f:
        for res in pool.imap_unordered(run_one, todo, chunksize=1):
            f.write(json.dumps(res) + "\n"); f.flush(); n += 1
            print(f"  {res['regime']}/{res['grid']}/s{res['seed']}/w{res['warmup']}: "
                  f"joint={res['joint_status']} ({res.get('joint_nodes'):,} nodes, "
                  f"{res.get('joint_cpu',0):.0f}s)  oracle={res['oracle_status']}")
            if time.time() - t0 > a.budget:
                break
    print(f"completed {n} this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
