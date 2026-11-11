#!/usr/bin/env python3
"""Stage-E causal beam isolation (BEAM_ISOLATION_SPEC.md).

Scheduler / subchannel rule / traffic / seeds held fixed; ONLY beam_rule varies.
Two power arms: MaxPower (link saturated) and MinFeasible-Stale (not saturated) — beam quality is
expected to matter more in the second.
Distance scaling uses the hall geometry; capped at 2.0x because 3GPP TR 38.901 InF applicability is
~600 m 3-D separation. CALIBRATION seeds only (10001-10005). FINAL TEST seeds untouched.

Blocks: 'dist' (distance x beam x power arm) and 'age' (CSI age x beam, at 2.0x distance, MinPow).
"""
from __future__ import annotations
import argparse, csv, json, os, time
from multiprocessing import Pool
from evaluation import journal_cfg, run_episodes, summarise
from baselines_v2 import ComponentAgent

SEEDS = [10001, 10002, 10003, 10004, 10005]
BEAMS = ["Fixed", "RandomBeam", "LastBeam", "StaleBest", "OracleBest"]
DIST = [1.0, 1.5, 2.0]
AGES = [0, 1, 3, 5]
R, T = 4, 250
HALL_X, HALL_Y = 300.0, 150.0
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "stage_e_beam_isolation.jsonl")
CSV = os.path.join(RES, "stage_e_beam_isolation.csv")


def jobs_all():
    js = []
    for d in DIST:                       # distance x beam x power-arm, at p=0.40, d_csi=1
        for b in BEAMS:
            for arm in ("MaxPower", "MinFeasible-Stale"):
                for s in SEEDS:
                    js.append(("dist", 0.40, d, 1, b, arm, s))
    for age in AGES:                     # CSI-age x beam, at 2.0x distance, MinPow arm
        for b in BEAMS:
            for s in SEEDS:
                js.append(("age", 0.40, 2.0, age, b, "MinFeasible-Stale", s))
    return js


def key(j): return "|".join(str(x) for x in j)


def one(job):
    block, load, dscale, age, beam, arm, seed = job
    cfg = journal_cfg(load, t_meas=T, hall_x=HALL_X * dscale, hall_y=HALL_Y * dscale,
                      d_csi_slots=age)
    mk = lambda env: ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule=beam, power_rule=arm)
    s = summarise(run_episodes(mk, cfg, seed=seed, R=R))
    s.update(block=block, load=load, dist_scale=dscale, d_csi=age, beam_rule=beam,
             power_arm=arm, seed=seed, R=R, T_meas=T,
             uses_oracle=int(beam == "OracleBest"))
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
        rows.sort(key=lambda r: (r["block"], r["dist_scale"], r["d_csi"], r["beam_rule"], r["power_arm"], r["seed"]))
        head = ["block", "load", "dist_scale", "d_csi", "beam_rule", "power_arm", "uses_oracle", "seed", "R", "T_meas"]
        cols = head + [k for k in rows[0] if k not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        for x in open(JSONL):
            if x.strip():
                r = json.loads(x)
                have.add(key((r["block"], r["load"], r["dist_scale"], r["d_csi"], r["beam_rule"],
                              r["power_arm"], r["seed"])))
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
