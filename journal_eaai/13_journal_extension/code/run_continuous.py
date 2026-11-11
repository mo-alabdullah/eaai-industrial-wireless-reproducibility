#!/usr/bin/env python3
"""STAGE I-CLOSEOUT task 3 - continuous-power mathematical reference and gap decomposition.

For each visited slot state and the demand the EDF heuristic actually served:
    H_G   heuristic power on grid G
    E_G   exact fixed-demand optimum on grid G
    C_AG  continuous cost of the grid-optimal ASSIGNMENT A_G
    C     exact continuous optimum (assignment free)

Exact identity, all terms non-negative (asserted in tests):
    H_G - C  =  (H_G - E_G)   allocation gap
             +  (E_G - C_AG)  pure quantisation / rounding
             +  (C_AG - C)    quantisation-induced assignment distortion
"""
from __future__ import annotations
import argparse, csv, json, math, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

from evaluation import journal_cfg
from baselines_v2 import ComponentAgent
from m2.env import M2Env, IDLE
from optimization.grids import with_grid
from optimization.capture import freeze
from optimization.radio import (solve_exact_radio_fixed_demand, solve_continuous_fixed_demand,
                                continuous_cost_of_assignment, INF)

REGIMES = {"R1_nominal": (1.0, 1), "R4_moderate": (1.5, 3), "R2_range": (2.0, 1), "R3_aged": (2.0, 5)}
GRIDS = ("G0_icame", "G2_wide10")
SEEDS = list(range(10001, 10009))
T_SLOTS = 250
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "continuous_ref.jsonl")
CSV = os.path.join(RES, "continuous_ref.csv")


def run_one(job):
    regime, gk, seed = job
    dist, age = REGIMES[regime]
    cfg = journal_cfg(0.40, t_meas=T_SLOTS, hall_x=300.0 * dist, hall_y=150.0 * dist,
                      d_csi_slots=age)
    cfg = with_grid(cfg, gk)
    env = M2Env(cfg, 700_000_000 + seed * 100)
    ag = ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule="StaleBest",
                        power_rule="MinFeasible-Stale")
    env.reset(); ag.reset()
    obs = env.begin_slot(); done = False
    rows = []
    while not done:
        st = freeze(env)
        toks = ag.act(obs)
        demand = {}
        hp = 0.0
        for t in toks:
            if t != IDLE:
                k, _b, p = int(t[0][1:]), int(t[1][1:]), int(t[2][1:])
                demand[k] = demand.get(k, 0) + 1
                hp += st.power_grid[p]
        if demand:
            eg = solve_exact_radio_fixed_demand(st, demand, use_true=False)
            cc = solve_continuous_fixed_demand(st, demand, use_true=False)
            c_ag = continuous_cost_of_assignment(st, eg) if not math.isinf(eg.power_w) else INF
            rows.append(dict(slot=env.t, served=sum(demand.values()),
                             n_elig=sum(1 for k in range(st.K) if st.queue_len[k] > 0),
                             h_power=hp,
                             e_grid=(None if math.isinf(eg.power_w) else eg.power_w),
                             c_ag=(None if math.isinf(c_ag) else c_ag),
                             c_cont=(None if math.isinf(cc.power_w) else cc.power_w),
                             grid_infeasible=int(math.isinf(eg.power_w)),
                             cont_infeasible=int(math.isinf(cc.power_w))))
        nxt, *_r = env.commit_action(toks)
        obs = nxt if nxt is not None else obs
        done = _r[3]
    return dict(regime=regime, grid=gk, seed=seed, dist_scale=dist, d_csi=age, rows=rows)


def jobs_all(): return [(r, g, s) for r in REGIMES for g in GRIDS for s in SEEDS]
def key(j): return "|".join(str(x) for x in j)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    if a.csv:
        out = []
        for line in open(JSONL):
            if not line.strip():
                continue
            d = json.loads(line)
            for r in d["rows"]:
                r2 = dict(regime=d["regime"], grid=d["grid"], seed=d["seed"],
                          dist_scale=d["dist_scale"], d_csi=d["d_csi"])
                r2.update(r); out.append(r2)
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
        print(f"CSV: {len(out)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        for x in open(JSONL):
            if x.strip():
                d = json.loads(x); have.add(key((d["regime"], d["grid"], d["seed"])))
    todo = [j for j in jobs_all() if key(j) not in have]
    print(f"total={len(jobs_all())} done={len(have)} todo={len(todo)}")
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
