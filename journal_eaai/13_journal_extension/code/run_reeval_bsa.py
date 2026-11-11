#!/usr/bin/env python3
"""Re-evaluate the ARCHIVED BSA policies against the corrected baselines, at the journal horizon.

This is REPRODUCTION, not new method design: the three archived PPO variants are retrained at the
ARCHIVED ICAME budget (8 rollout episodes x 10 updates, hidden 48) on the archived seeds, exactly as
in 10_confirmatory, and then evaluated with the Stage-F harness (R=10 episodes x T=250) so that they
are directly comparable with the Stage-D baselines. No hyperparameter is tuned. No new algorithm is
designed. FINAL TEST seeds are not touched.
"""
from __future__ import annotations
import argparse, csv, json, os, time
from multiprocessing import Pool
from evaluation import journal_cfg, summarise, EVAL_V2_NAMESPACE, BUDGET_ARCHIVED
from m2.env import M2Env
from m2.agents_ppo import PPOAgent
import numpy as np

LOADS = [0.05, 0.10, 0.20, 0.30, 0.40]
SEEDS = list(range(20001, 20011))
VARIANTS = {"BSA-Unconstrained-PPO": "unconstrained",
            "BSA-Penalty-PPO": "penalty",
            "BSA-C-PPO": "lagrangian"}
R, T = 10, 250
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))
JSONL = os.path.join(RES, "reeval_bsa.jsonl")
CSV = os.path.join(RES, "reeval_bsa.csv")


def _per_class(v):
    if isinstance(v, (list, tuple, np.ndarray)):
        return float(v[0]), float(v[1])
    return float(v), 0.0


def eval_ppo_multi(ag, cfg, seed, R):
    agg = dict(gen_s=0.0, gen_m=0.0, dlv_s=0.0, dlv_m=0.0, dv_s=0.0, dv_m=0.0,
               ov_s=0.0, ov_m=0.0, power=[], beam_acc=[], se=[], lat_p95=[], resid=0.0)
    for r in range(R):
        env = M2Env(cfg, EVAL_V2_NAMESPACE + seed * 100 + r)
        env.reset(); obs = env.begin_slot(); done = False
        while not done:
            prefix, *_ = ag.act_slot(env, obs, greedy=True)
            nxt, rp, rb, cost, done, info = env.commit_action(prefix)
            obs = nxt if nxt is not None else obs
        m = env.episode_metrics()
        agg["gen_s"] += m["gen_static"]; agg["gen_m"] += m["gen_mobile"]
        agg["dlv_s"] += m["dlv_static"]; agg["dlv_m"] += m["dlv_mobile"]
        dv_s, dv_m = _per_class(env.m.get("deadline_viol", env.m.get("drop_deadline", 0)))
        ov_s, ov_m = _per_class(env.m.get("overflow", 0))
        agg["dv_s"] += dv_s; agg["dv_m"] += dv_m; agg["ov_s"] += ov_s; agg["ov_m"] += ov_m
        agg["power"].append(m["avg_power_w"]); agg["beam_acc"].append(m["beam_acc_oracle"])
        agg["se"].append(m["spectral_eff"]); agg["lat_p95"].append(m["lat_p95"])
        agg["resid"] += m["cohort_residual"]
    return agg


def one(job):
    method, load, seed = job
    cfg = journal_cfg(load, t_meas=T)
    # train at the ARCHIVED budget on the archived training horizon (T_meas=200 as in ICAME)
    train_cfg = journal_cfg(load, t_meas=200)
    ag = PPOAgent(train_cfg, base_seed=seed, mode=VARIANTS[method], layer1=False)
    t0 = time.time(); ag.train(); train_s = time.time() - t0
    s = summarise(eval_ppo_multi(ag, cfg, seed, R))
    s.update(method=method, load=load, seed=seed, R=R, T_meas=T, train_seconds=round(train_s, 2),
             scheduler="Learned", beam_rule="Learned", power_rule="Learned", uses_oracle=0)
    return s


def key(m, l, s): return f"{m}|{l}|{s}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    jobs = [(m, l, s) for m in VARIANTS for l in LOADS for s in SEEDS]
    if a.csv:
        rows = [json.loads(x) for x in open(JSONL) if x.strip()]
        rows.sort(key=lambda r: (r["method"], r["load"], r["seed"]))
        head = ["method", "scheduler", "beam_rule", "power_rule", "uses_oracle", "load", "seed", "R", "T_meas"]
        cols = head + [k for k in rows[0] if k not in head]
        with open(CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
        print(f"CSV: {len(rows)} rows -> {CSV}"); return
    have = set()
    if os.path.exists(JSONL):
        have = {key(r["method"], r["load"], r["seed"]) for r in
                (json.loads(x) for x in open(JSONL) if x.strip())}
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
    print(f"completed {n} this call in {time.time()-t0:.1f}s; remaining={len(todo)-n}")


if __name__ == "__main__":
    main()
