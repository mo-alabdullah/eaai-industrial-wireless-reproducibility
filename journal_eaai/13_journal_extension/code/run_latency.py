#!/usr/bin/env python3
"""STAGE I-CLOSEOUT task 2 - rigorous per-solve latency of the exact radio solver.

SINGLE PROCESS by design: the Stage-I campaigns ran four workers on four cores, so their timings
include scheduling contention. Latency is measured here with one worker and `time.perf_counter`
around the solve call only (state capture and bookkeeping excluded), on development states only.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

from evaluation import journal_cfg
from baselines_v2 import ComponentAgent
from m2.env import M2Env, IDLE
from optimization.grids import with_grid
from optimization.capture import freeze
from optimization.radio import solve_exact_radio, solve_exact_radio_fixed_demand

REGIMES = {"R1_nominal": (1.0, 1), "R4_moderate": (1.5, 3), "R2_range": (2.0, 1), "R3_aged": (2.0, 5)}
GRIDS = ("G0_icame", "G2_wide10")
SEEDS = list(range(10001, 10009))
T_SLOTS = 120
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
CSV = os.path.join(RES, "solver_latency.csv")


def environment():
    import platform, numpy
    env = dict(python=sys.version.split()[0], numpy=numpy.__version__,
               platform=platform.platform(), machine=platform.machine(),
               cpu_count=os.cpu_count(), implementation=platform.python_implementation())
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                env["mem_total"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    env["blas"] = "not used in the solve path (pure Python/NumPy indexing only)"
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=T_SLOTS)
    a = ap.parse_args()
    rows = []
    for regime, (dist, age) in REGIMES.items():
        for gk in GRIDS:
            for seed in SEEDS:
                cfg = journal_cfg(0.40, t_meas=a.slots, hall_x=300.0 * dist,
                                  hall_y=150.0 * dist, d_csi_slots=age)
                cfg = with_grid(cfg, gk)
                env = M2Env(cfg, 700_000_000 + seed * 100)
                ag = ComponentAgent(env, seed=seed, scheduler="EDF",
                                    beam_rule="StaleBest", power_rule="MinFeasible-Stale")
                env.reset(); ag.reset()
                obs = env.begin_slot(); done = False
                while not done:
                    st = freeze(env)
                    toks = ag.act(obs)
                    demand = {}
                    for t in toks:
                        if t != IDLE:
                            k = int(t[0][1:]); demand[k] = demand.get(k, 0) + 1
                    n_elig = sum(1 for k in range(st.K) if st.queue_len[k] > 0)

                    t0 = time.perf_counter(); r_full = solve_exact_radio(st, use_true=False)
                    lat_full = time.perf_counter() - t0

                    lat_fix = float("nan"); nodes_fix = 0
                    if demand:
                        t0 = time.perf_counter()
                        r_fix = solve_exact_radio_fixed_demand(st, demand, use_true=False)
                        lat_fix = time.perf_counter() - t0
                        nodes_fix = r_fix.nodes

                    rows.append(dict(regime=regime, grid=gk, seed=seed, slot=env.t,
                                     dist_scale=dist, d_csi=age, n_elig=n_elig,
                                     served=sum(demand.values()),
                                     lat_free_s=lat_full, nodes_free=r_full.nodes,
                                     lat_fixed_s=lat_fix, nodes_fixed=nodes_fix))
                    nxt, *_r = env.commit_action(toks)
                    obs = nxt if nxt is not None else obs
                    done = _r[3]
    os.makedirs(RES, exist_ok=True)
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump(environment(), open(os.path.join(RES, "solver_latency_env.json"), "w"), indent=1)
    print(f"{len(rows)} solve records -> {CSV}")
    print(json.dumps(environment(), indent=1))


if __name__ == "__main__":
    main()
