#!/usr/bin/env python3
"""Stage-D campaign: component-decomposed baselines at the journal evaluation horizon.

Protocol: JOURNAL_PROTOCOL_V1 (R=10 evaluation episodes x T=250 slots per seed).
Seeds = ARCHIVED confirmatory seeds 20001-20010, for like-for-like comparison with ICAME results.
FINAL TEST seeds (50001-50020) are NOT touched.

Resumable: results are appended to a JSONL keyed by (method, load, seed); re-running skips completed
jobs. Use --budget to bound wall time per invocation (tool-call ceiling ~178 s).
  python3 run_stage_d.py --budget 150
  python3 run_stage_d.py --csv          # emit the CSV once all jobs are done
"""
from __future__ import annotations
import argparse, csv, json, os, time
from multiprocessing import Pool
from evaluation import journal_cfg, run_episodes, summarise
from baselines_v2 import make_agent, METHODS_V2, ORACLE_RULES

LOADS = [0.05, 0.10, 0.20, 0.30, 0.40]
SEEDS = list(range(20001, 20011))
R, T = 10, 250
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_d_baselines.jsonl")
CSV = os.path.join(RES, "stage_d_baselines.csv")


def key(m, l, s):
    return f"{m}|{l}|{s}"


def one(job):
    method, load, seed = job
    spec = METHODS_V2[method]
    cfg = journal_cfg(load, t_meas=T)
    agg = run_episodes(lambda env: make_agent(method, env, seed=seed), cfg, seed=seed, R=R)
    s = summarise(agg)
    s.update(method=method, load=load, seed=seed, R=R, T_meas=T,
             scheduler=spec["scheduler"], beam_rule=spec["beam_rule"], power_rule=spec["power_rule"],
             uses_oracle=int(spec["beam_rule"] in ORACLE_RULES or spec["power_rule"] in ORACLE_RULES))
    return s


def done_keys():
    if not os.path.exists(JSONL):
        return set()
    out = set()
    with open(JSONL) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out.add(key(r["method"], r["load"], r["seed"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    jobs = [(m, l, s) for m in METHODS_V2 for l in LOADS for s in SEEDS]

    if a.csv:
        rows = [json.loads(x) for x in open(JSONL) if x.strip()]
        rows.sort(key=lambda r: (r["method"], r["load"], r["seed"]))
        head = ["method", "scheduler", "beam_rule", "power_rule", "uses_oracle", "load", "seed", "R", "T_meas"]
        cols = head + [k for k in rows[0] if k not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}")
        return

    have = done_keys()
    todo = [j for j in jobs if key(*j) not in have]
    print(f"total={len(jobs)} done={len(have)} todo={len(todo)}")
    if not todo:
        print("ALL DONE"); return
    t0 = time.time(); n = 0
    with Pool(4) as pool, open(JSONL, "a") as f:
        for res in pool.imap_unordered(one, todo, chunksize=1):
            f.write(json.dumps(res) + "\n"); f.flush(); n += 1
            if time.time() - t0 > a.budget:
                break
    print(f"completed {n} jobs this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
