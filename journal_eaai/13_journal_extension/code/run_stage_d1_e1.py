#!/usr/bin/env python3
"""Stage D.1 + E.1 cheap diagnostics.

D.1  Is dynamic discrete power control actually needed, or is fixed P_min sufficient?
     Adds EDF-*-Pmin baselines and records the selected-power histogram for MinFeasible-Stale.
E.1  Strengthen the decisive beam cells from n=5 to n=8 calibration seeds.

CALIBRATION/DEVELOPMENT seeds only (10001-10008). FINAL TEST seeds (50001-50020) are NOT opened.
No learning algorithm is designed and no RL hyperparameter is tuned here.
"""
from __future__ import annotations
import argparse, csv, json, os, time
from multiprocessing import Pool
from evaluation import journal_cfg, run_episodes, summarise
from baselines_v2 import ComponentAgent, METHODS_V2, ORACLE_RULES

SEEDS8 = [10001, 10002, 10003, 10004, 10005, 10006, 10007, 10008]
HALL_X, HALL_Y = 300.0, 150.0
R, T = 4, 250

D1_METHODS = ["EDF-StaleBeam-Pmin", "EDF-OracleBeam-Pmin", "EDF-RandomBeam-Pmin",
              "EDF-FixedBeam-Pmin", "EDF-StaleBeam-MinPow", "EDF-StaleBeam-MaxPow",
              "EDF-OracleBeam-MinPowOr"]
D1_LOADS = [0.20, 0.40]
D1_DIST = [1.0, 1.5, 2.0]
D1_AGES = [1, 5]

E1_BEAMS = ["StaleBest", "Fixed", "RandomBeam", "OracleBest"]
E1_ARMS = ["MinFeasible-Stale", "Pmin"]
E1_DIST = [1.0, 2.0]
E1_AGES = [1, 5]

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_d1_e1.jsonl")
CSV = os.path.join(RES, "stage_d1_e1.csv")


def jobs_all():
    js = []
    for m in D1_METHODS:                                   # D.1 grid
        for l in D1_LOADS:
            for d in D1_DIST:
                for age in D1_AGES:
                    for s in SEEDS8:
                        js.append(("D1", m, None, None, l, d, age, s))
    for b in E1_BEAMS:                                     # E.1 grid (component form)
        for arm in E1_ARMS:
            for d in E1_DIST:
                for age in E1_AGES:
                    for s in SEEDS8:
                        js.append(("E1", None, b, arm, 0.40, d, age, s))
    return js


def key(j): return "|".join("" if x is None else str(x) for x in j)


def one(job):
    block, method, beam, arm, load, dscale, age, seed = job
    cfg = journal_cfg(load, t_meas=T, hall_x=HALL_X * dscale, hall_y=HALL_Y * dscale,
                      d_csi_slots=age)
    if block == "D1":
        spec = METHODS_V2[method]
        mk = lambda env: ComponentAgent(env, seed=seed, **spec)
        beam_r, pow_r = spec["beam_rule"], spec["power_rule"]
        name = method
    else:
        mk = lambda env: ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule=beam,
                                        power_rule=arm)
        beam_r, pow_r = beam, arm
        name = f"EDF-{beam}-{arm}"
    s = summarise(run_episodes(mk, cfg, seed=seed, R=R))
    s.update(block=block, method=name, beam_rule=beam_r, power_rule=pow_r, load=load,
             dist_scale=dscale, d_csi=age, seed=seed, R=R, T_meas=T,
             uses_oracle=int(beam_r in ORACLE_RULES or pow_r in ORACLE_RULES))
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
        rows.sort(key=lambda r: (r["block"], r["method"], r["load"], r["dist_scale"], r["d_csi"], r["seed"]))
        head = ["block", "method", "beam_rule", "power_rule", "uses_oracle", "load", "dist_scale",
                "d_csi", "seed", "R", "T_meas"]
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
                blk = r["block"]
                m = r["method"] if blk == "D1" else None
                b = None if blk == "D1" else r["beam_rule"]
                ar = None if blk == "D1" else r["power_rule"]
                have.add(key((blk, m, b, ar, r["load"], r["dist_scale"], r["d_csi"], r["seed"])))
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
