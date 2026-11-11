#!/usr/bin/env python3
"""Final non-learning diagnostic: decompose the aged-CSI oracle headroom at extended range.

Regime: distance x2.0, load p=0.40, d_CSI in {1,3,5}; power rules {Pmin, MinFeasible-Stale};
plus the (OracleBeam + OraclePower) combination for the total-information upper bound.
Development/calibration seeds 10001-10008 only. FINAL TEST seeds are NOT opened.
No learning, no fitted parameters, no tuning on outcome metrics.
"""
from __future__ import annotations
import argparse, csv, json, os, time
from multiprocessing import Pool
from evaluation import journal_cfg, run_episodes, summarise
from baselines_v2 import ComponentAgent, ORACLE_RULES

SEEDS = [10001, 10002, 10003, 10004, 10005, 10006, 10007, 10008]
AGES = [1, 3, 5]
BEAMS = ["StaleBest", "LastBeam", "Fixed", "RandomBeam", "OracleBest"]
ARMS = ["Pmin", "MinFeasible-Stale"]
DSCALE, LOAD, R, T = 2.0, 0.40, 4, 250
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "headroom.jsonl")
CSV = os.path.join(RES, "headroom.csv")


def jobs_all():
    js = []
    for age in AGES:
        for s in SEEDS:
            for arm in ARMS:
                for b in BEAMS:
                    js.append((age, b, arm, s))
            js.append((age, "OracleBest", "MinFeasible-Oracle", s))   # total-information bound
    return js


def key(j): return "|".join(str(x) for x in j)


def one(job):
    age, beam, arm, seed = job
    cfg = journal_cfg(LOAD, t_meas=T, hall_x=300.0 * DSCALE, hall_y=150.0 * DSCALE,
                      d_csi_slots=age)
    mk = lambda env: ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule=beam,
                                    power_rule=arm)
    s = summarise(run_episodes(mk, cfg, seed=seed, R=R))
    s.update(d_csi=age, beam_rule=beam, power_rule=arm, seed=seed, R=R, T_meas=T,
             dist_scale=DSCALE, load=LOAD,
             method=f"EDF-{beam}-{arm}",
             uses_oracle=int(beam in ORACLE_RULES or arm in ORACLE_RULES))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    js = jobs_all()
    if a.csv:
        rows = [json.loads(x) for x in open(JSONL) if x.strip()]
        rows.sort(key=lambda r: (r["d_csi"], r["power_rule"], r["beam_rule"], r["seed"]))
        head = ["method", "beam_rule", "power_rule", "uses_oracle", "d_csi", "dist_scale", "load",
                "seed", "R", "T_meas"]
        cols = head + [k for k in rows[0] if k not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        for x in open(JSONL):
            if x.strip():
                r = json.loads(x)
                have.add(key((r["d_csi"], r["beam_rule"], r["power_rule"], r["seed"])))
    todo = [j for j in js if key(j) not in have]
    print(f"total={len(js)} done={len(have)} todo={len(todo)}")
    if not todo:
        print("ALL DONE"); return
    t0 = time.time(); n = 0
    with Pool(4) as pool, open(JSONL, "a") as f:
        for res in pool.imap_unordered(one, todo, chunksize=2):
            f.write(json.dumps(res) + "\n"); f.flush(); n += 1
            if time.time() - t0 > a.budget:
                break
    print(f"completed {n} this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
