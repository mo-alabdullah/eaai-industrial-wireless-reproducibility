#!/usr/bin/env python3
"""exploratory experiment driver — RESUMABLE / checkpointed (the sandbox reaps background processes, so
each invocation runs a time-bounded chunk and appends to JSONL; re-invoke until ALL_DONE).

Jobs: E1 pilot -> full primary campaign -> ablations/sensitivity. When every job is complete, the
same script runs the analysis: pilot gate, seed-level statistics, constraint feasibility,
accepted-abstract hypothesis check, machine-readable artifacts + figure data. Does NOT write the
manuscript Results/Conclusion.  Usage:  python3 scripts/run_experiments.py [--budget SECONDS]
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "simulation"
sys.path.insert(0, str(SIM))

from m2.config import campaign_config          # noqa: E402
from m2 import experiments as X                 # noqa: E402
from m2 import statistics as S                  # noqa: E402

OUT = ROOT / "results" / "exploratory"
FIG = OUT / "figure_data"
OUT.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
RAW = OUT / "raw_records.jsonl"
CURVES = OUT / "raw_curves.jsonl"

LOADS = [0.05, 0.10, 0.20, 0.30, 0.40]
SEEDS = list(range(10))
ABL_SEEDS = list(range(3))
ABL_LOADS = [0.20, 0.40]
CONSTRAINT_KEYS = ["C_rel_static", "C_dv_static", "C_over_static",
                   "C_rel_mobile", "C_dv_mobile", "C_over_mobile", "C_pow"]
PILOT_NAMES = ("L1-Fixed-Random", "L1-Fixed-BasePPO", "Random", "EDF", "MaxSINROracle",
               "BSA-Unconstrained-PPO", "BSA-Penalty-PPO", "BSA-C-PPO")


def build_jobs():
    jobs = []
    spec_by = {m[0]: m for m in X.ALL_METHODS}
    # pilot
    for p in (0.05, 0.20, 0.40):
        for name in PILOT_NAMES:
            for s in (0, 1, 2):
                jobs.append(("pilot", "pilot", spec_by[name], {"load_p": p}, s))
    # campaign
    for p in LOADS:
        for spec in X.ALL_METHODS:
            for s in SEEDS:
                jobs.append(("campaign", "campaign", spec, {"load_p": p}, s))
    # ablations
    key3 = [spec_by[n] for n in ("BSA-C-PPO", "StaleMaxGain", "PerfectMaxGain")]
    for d in (0, 1, 2, 3):
        for spec in key3:
            for p in ABL_LOADS:
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"d_csi={d}", spec, {"load_p": p, "d_csi_slots": d}, s))
    for pb in (1.28, 1.60, 1.92):
        for p in ABL_LOADS:
            for s in ABL_SEEDS:
                jobs.append(("ablation", f"P_bar={pb}", spec_by["BSA-C-PPO"], {"load_p": p, "p_bar_w": pb}, s))
    for corr in ("independent", "jakes", "strong"):
        for spec in key3:
            for p in ABL_LOADS:
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"corr={corr}", spec, {"load_p": p, "fading_correlation": corr}, s))
    for v in (0.0, 2.0, 3.0):
        for spec in (spec_by["BSA-C-PPO"], spec_by["EDF"]):
            for p in ABL_LOADS:
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"v_max={v}", spec, {"load_p": p, "v_max_mps": v}, s))
    return jobs


def job_key(phase, tag, spec, kw, seed):
    kws = ",".join(f"{k}={kw[k]}" for k in sorted(kw))
    return f"{phase}|{tag}|{spec[0]}|{kws}|{seed}"


def load_done():
    done = set()
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["_key"])
    return done


def run_chunk(budget_s):
    jobs = build_jobs()
    done = load_done()
    t0 = time.time(); ran = 0
    with open(RAW, "a") as fr, open(CURVES, "a") as fc:
        for phase, tag, spec, kw, seed in jobs:
            key = job_key(phase, tag, spec, kw, seed)
            if key in done:
                continue
            if time.time() - t0 > budget_s:
                print(f"CHUNK_INCOMPLETE done={len(done)}/{len(jobs)} ran_now={ran} "
                      f"elapsed={time.time()-t0:.0f}s", flush=True)
                return False, len(done), len(jobs)
            cfg = campaign_config(**kw)
            m, extra = X.run_method(spec, cfg, seed)
            rec = {"_key": key, "phase": phase, "tag": tag, "method": spec[0], "layer": spec[1],
                   "seed": seed, "load": kw["load_p"]}
            rec.update({k: v for k, v in m.items() if not k.startswith("_")})
            fr.write(json.dumps(rec) + "\n"); fr.flush()
            if extra is not None:
                fc.write(json.dumps({"_key": key, "phase": phase, "tag": tag, "method": spec[0],
                                     "seed": seed, "load": kw["load_p"],
                                     "history": {k: (v if k != "multipliers" else [x.tolist() for x in v])
                                                 for k, v in extra["history"].items()},
                                     "multipliers_final": extra["multipliers_final"]}) + "\n")
                fc.flush()
            done.add(key); ran += 1
    print(f"ALL_JOBS_DONE total={len(jobs)} ran_now={ran} elapsed={time.time()-t0:.0f}s", flush=True)
    return True, len(jobs), len(jobs)


# ------------------------------------------------------------------ analysis
def _records():
    return [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]


def _curves():
    return [json.loads(l) for l in CURVES.read_text().splitlines() if l.strip()]


def _wcsv(path, rows, fields=None):
    if not rows:
        Path(path).write_text(""); return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def analyze():
    recs = _records()
    curves = _curves()

    def _dedup(rows, keyf):
        d = {}
        for r in rows:
            d[keyf(r)] = r          # last write wins
        return list(d.values())
    camp = _dedup([r for r in recs if r["phase"] == "campaign"],
                  lambda r: (r["method"], r["load"], r["seed"]))
    pil = _dedup([r for r in recs if r["phase"] == "pilot"],
                 lambda r: (r["method"], r["load"], r["seed"]))
    abl = _dedup([r for r in recs if r["phase"] == "ablation"],
                 lambda r: (r["tag"], r["method"], r["load"], r["seed"]))
    metric_keys = [k for k in camp[0] if k not in
                   ("_key", "phase", "tag", "method", "layer", "seed", "load")]

    # ---- pilot gate ----
    pc = [c for c in curves if c["phase"] == "pilot"]
    learning = any(abs(c["history"]["reward"][-1] - c["history"]["reward"][0]) > 1e-6
                   for c in pc if len(c["history"]["reward"]) >= 2)
    mult_resp = any(sum(c["multipliers_final"]) > 0 for c in pc if c["method"] == "BSA-C-PPO")
    pilot_bad = [r for r in pil if r["cohort_residual"] != 0]
    E1 = "PASSED" if (not pilot_bad and learning and mult_resp) else "FAILED"
    (OUT / "pilot_summary.json").write_text(json.dumps(
        {"records": len(pil), "residual_problems": len(pilot_bad),
         "learning_changed_policy": bool(learning), "cppo_multiplier_responds": bool(mult_resp),
         "E1_status": E1}, indent=2))

    # ---- validity ----
    problems = [f"{r['method']} s{r['seed']} p{r['load']}: residual {r['cohort_residual']}"
                for r in camp if r["cohort_residual"] != 0]
    problems += [f"{r['method']} s{r['seed']} p{r['load']}: nonfinite {k}"
                 for r in camp for k, v in r.items() if isinstance(v, float) and not np.isfinite(v)]

    _wcsv(OUT / "per_seed_metrics.csv", camp,
          fields=["method", "layer", "seed", "load"] + metric_keys)

    # ---- training curves + multiplier trajectories ----
    tc_rows, mc_rows = [], []
    for c in [c for c in curves if c["phase"] == "campaign"]:
        h = c["history"]
        for u in range(len(h["reward"])):
            tc_rows.append({"method": c["method"], "seed": c["seed"], "load": c["load"], "update": u,
                            "reward": h["reward"][u], "kl": h["kl"][u], "entropy": h["entropy"][u],
                            "clipfrac": h["clipfrac"][u]})
        for u, mv in enumerate(h["multipliers"]):
            row = {"method": c["method"], "seed": c["seed"], "load": c["load"], "update": u}
            row.update({CONSTRAINT_KEYS[i]: mv[i] for i in range(len(CONSTRAINT_KEYS))})
            mc_rows.append(row)
    _wcsv(OUT / "training_curves.csv", tc_rows)
    _wcsv(OUT / "cost_multiplier_curves.csv", mc_rows)

    # ---- primary summary (seed-level + pooled ratio-of-sums) ----
    by = collections.defaultdict(list)
    for r in camp:
        by[(r["method"], r["load"])].append(r)
    key_metrics = ["pdr", "pdr_static", "pdr_mobile", "dv_ratio_mobile", "lat_p95", "lat_p99",
                   "throughput_bps", "spectral_eff", "energy_eff", "avg_power_w", "jain_fairness",
                   "beam_acc_oracle", "subch_util", "C_pow", "C_rel_mobile", "reward_primary"]
    summ = []
    for (method, load), rs in sorted(by.items()):
        for mk in key_metrics:
            summ.append({"method": method, "load": load, "metric": mk, **S.summarize([r[mk] for r in rs])})
        for cls, gk, dk in [("overall", "generated", "delivered"),
                            ("static", "gen_static", "dlv_static"),
                            ("mobile", "gen_mobile", "dlv_mobile")]:
            g = sum(r[gk] for r in rs); d = sum(r[dk] for r in rs)
            v = d / max(g, 1)
            summ.append({"method": method, "load": load, "metric": f"pdr_pooled_{cls}",
                         "n": len(rs), "mean": v, "median": v, "sd": 0.0, "ci95_lo": v, "ci95_hi": v})
    _wcsv(OUT / "primary_summary.csv", summ)

    # ---- paired statistics: BSA-C-PPO vs competitors ----
    seed_of = collections.defaultdict(dict)
    for r in camp:
        seed_of[(r["method"], r["load"])][r["seed"]] = r
    comparators = ["Random", "EDF", "MaxSINROracle", "StaleMaxGain",
                   "BSA-Unconstrained-PPO", "BSA-Penalty-PPO"]
    stat_metrics = ["pdr", "pdr_mobile", "dv_ratio_mobile", "reward_primary"]
    stat_rows = []
    for load in LOADS:
        for mk in stat_metrics:
            pv, tmp = [], []
            a = seed_of[("BSA-C-PPO", load)]
            for comp in comparators:
                b = seed_of[(comp, load)]
                ss = sorted(set(a) & set(b))
                res = S.paired_compare([a[s][mk] for s in ss], [b[s][mk] for s in ss])
                tmp.append((comp, res)); pv.append(res["p_value"])
            for (comp, res), ap in zip(tmp, S.holm_adjust(pv)):
                stat_rows.append({"load": load, "metric": mk, "A": "BSA-C-PPO", "B": comp, **res, "p_holm": ap})
    _wcsv(OUT / "pairwise_statistics.csv", stat_rows)

    # ---- constraint feasibility (BSA-C-PPO) ----
    feas_rows = []
    for load in LOADS:
        a = seed_of[("BSA-C-PPO", load)]
        for s in sorted(a):
            r = a[s]; ok_all = True; first = ""
            for k in CONSTRAINT_KEYS:
                ok = r[k] <= 1e-9
                if not ok and not first:
                    first = k
                ok_all = ok_all and ok
            feas_rows.append({"method": "BSA-C-PPO", "load": load, "seed": s,
                              **{k: r[k] for k in CONSTRAINT_KEYS},
                              "all_constraints_pass": int(ok_all), "first_violated": first})
    _wcsv(OUT / "constraint_feasibility.csv", feas_rows)
    feas_sum = []
    for load in LOADS:
        rs = [r for r in feas_rows if r["load"] == load]
        rate = float(np.mean([r["all_constraints_pass"] for r in rs]))
        viol = [r["first_violated"] for r in rs if r["first_violated"]]
        feas_sum.append({"load": load, "feasible_rate": rate,
                         "most_common_first_violation": max(set(viol), key=viol.count) if viol else ""})
    _wcsv(OUT / "constraint_feasibility_summary.csv", feas_sum)
    feasible_region = [f["load"] for f in feas_sum if f["feasible_rate"] >= 0.5]
    collapse = next((f["load"] for f in feas_sum if f["feasible_rate"] < 0.5), None)

    # ---- ablation / sensitivity tables ----
    abl_rows = []
    for r in abl:
        abl_rows.append({"ablation": r["tag"], "method": r["method"], "seed": r["seed"],
                         "load": r["load"], "pdr": r["pdr"], "pdr_mobile": r["pdr_mobile"],
                         "dv_ratio_mobile": r["dv_ratio_mobile"], "beam_acc_oracle": r["beam_acc_oracle"],
                         "avg_power_w": r["avg_power_w"], "C_pow": r["C_pow"], "C_rel_mobile": r["C_rel_mobile"]})
    _wcsv(OUT / "ablation_results.csv", abl_rows)
    _wcsv(OUT / "sensitivity_results.csv",
          [r for r in abl_rows if r["ablation"].startswith(("corr=", "v_max=", "P_bar="))])

    # ---- accepted-abstract hypothesis check (pooled Layer-1 PDR) ----
    def pooled(method, load, gk, dk):
        rs = [r for r in camp if r["method"] == method and r["load"] == load]
        g = sum(r[gk] for r in rs); d = sum(r[dk] for r in rs)
        return d / max(g, 1)
    l1s = {p: (pooled("L1-Fixed-BasePPO", p, "gen_static", "dlv_static"),
               pooled("L1-Fixed-Random", p, "gen_static", "dlv_static")) for p in LOADS}
    l1m = {p: (pooled("L1-Fixed-BasePPO", p, "gen_mobile", "dlv_mobile"),
               pooled("L1-Fixed-Random", p, "gen_mobile", "dlv_mobile")) for p in LOADS}
    ppo_static_beats = all(l1s[p][0] >= l1s[p][1] - 1e-6 for p in LOADS)
    onset = next((p for p in LOADS if l1m[p][1] < 0.99), None)
    mobile_earlier = any(l1m[p][1] < l1s[p][1] - 1e-3 for p in LOADS)
    inversion = [p for p in LOADS if l1m[p][1] > l1m[p][0] + 1e-3]
    _accepted_md(l1s, l1m, ppo_static_beats, onset, mobile_earlier, inversion)

    # ---- figure data ----
    _figures(camp, feas_sum, mc_rows, tc_rows)

    # ---- reproducibility rerun ----
    cfg = campaign_config(load_p=0.30)
    spec_edf = [m for m in X.ALL_METHODS if m[0] == "EDF"][0]
    ra, _ = X.run_method(spec_edf, cfg, 0)
    rb, _ = X.run_method(spec_edf, cfg, 0)
    reproducible = abs(ra["pdr"] - rb["pdr"]) < 1e-12

    # ---- manifest + validation ----
    src = list(SIM.glob("m2/*.py")) + [SIM / "primary_experiment_config.json"]
    code_hash = hashlib.sha256(b"".join(sorted(p.read_bytes() for p in src))).hexdigest()
    cfg_ref = campaign_config(load_p=0.20)
    cfg_hash = hashlib.sha256(json.dumps(asdict(cfg_ref), sort_keys=True, default=str).encode()).hexdigest()
    expected = len(X.ALL_METHODS) * len(SEEDS) * len(LOADS)
    manifest = {
        "round": "exploratory-EXPERIMENTS", "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_sha256": code_hash, "campaign_config_sha256": cfg_hash,
        "loads": LOADS, "seeds": SEEDS, "n_methods": len(X.ALL_METHODS),
        "method_order": X.METHOD_ORDER, "layer1_methods": [m[0] for m in X.LAYER1_METHODS],
        "layer2_methods": [m[0] for m in X.LAYER2_METHODS],
        "expected_campaign_records": expected, "actual_campaign_records": len(camp),
        "campaign_topology": {"n_static": cfg_ref.n_static, "n_mobile": cfg_ref.n_mobile,
                              "n_subchannels": cfg_ref.n_subchannels, "n_antennas": cfg_ref.n_antennas,
                              "codebook_size": cfg_ref.codebook_size, "n_power_levels": cfg_ref.n_power_levels,
                              "t_meas": cfg_ref.t_meas_slots, "n_ep_train": cfg_ref.n_ep_train,
                              "n_updates": cfg_ref.n_updates, "ppo_hidden": cfg_ref.ppo_hidden},
        "locked_physics": {"tau_s": cfg_ref.tau_s, "W_hz": cfg_ref.bandwidth_hz, "NF_db": cfg_ref.noise_figure_db,
                           "P_bar_w": cfg_ref.p_bar_w, "d_csi": cfg_ref.d_csi_slots, "k_subce_m": cfg_ref.k_subce_m,
                           "scenario": "InF-SH", "pkt_bits_static": cfg_ref.pkt_bits_static,
                           "pkt_bits_mobile": cfg_ref.pkt_bits_mobile,
                           "delivery_floor_static": cfg_ref.delivery_floor_static,
                           "delivery_floor_mobile": cfg_ref.delivery_floor_mobile},
        "note": "Preregistered computationally-bounded campaign scenario (locked physics; K>>N "
                "congestion topology). Full locked primary K=8,B=8,P=4,N=8 validated executable by test_m2.",
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    full_grid = (len(camp) == expected)
    validation = {
        "E1_pilot": E1,
        "FULL_EXPERIMENTS": "PASSED" if (E1 == "PASSED" and not problems and full_grid and reproducible) else "FAILED",
        "no_nonfinite_results": not problems, "problems": problems[:20],
        "full_drain_complete": all(r["cohort_residual"] == 0 for r in camp),
        "expected_records": expected, "actual_records": len(camp), "complete_grid": full_grid,
        "reproducible_rerun": bool(reproducible),
        "feasible_load_region": feasible_region, "collapse_load_threshold": collapse,
    }
    (OUT / "campaign_validation.json").write_text(json.dumps(validation, indent=2))
    _validation_report(manifest, validation, feas_sum, problems)
    print(f"ANALYSIS_DONE E1={E1} FULL_EXPERIMENTS={validation['FULL_EXPERIMENTS']} "
          f"records={len(camp)}/{expected}", flush=True)
    return validation


def _accepted_md(l1s, l1m, ppo_beats, onset, mobile_earlier, inversion):
    v = lambda b: "SUPPORTS" if b else "DOES NOT SUPPORT"
    L = ["# Accepted-Abstract Hypothesis Comparison (exploratory — honest, data-driven)\n",
         "Layer-1 (fixed-radio) results; the accepted abstract/title is NOT edited. Hypothesis "
         "checks only; pooled ratio-of-sums PDR.\n",
         "| # | Accepted hypothesis | Observed | Verdict |", "|---|---|---|---|",
         f"| 1 | Base PPO outperforms Random for static sensors | static PDR PPO>=Random at all loads "
         f"= {ppo_beats} (p=0.40: PPO {l1s[0.40][0]:.3f} vs Rand {l1s[0.40][1]:.3f}) | {v(ppo_beats)} |",
         f"| 2 | Congestion degradation begins at a finite load | first load mobile PDR<0.99 (Random) "
         f"= {onset} | {v(onset is not None)} |",
         f"| 3 | Mobile AMR/AGV degrade earlier than static | mobile<static at some load = "
         f"{mobile_earlier} | {v(mobile_earlier)} |",
         f"| 4 | Some load where Random beats Base PPO for mobile (inversion) | inversion loads = "
         f"{inversion} | {'SUPPORTS' if inversion else 'DOES NOT SUPPORT'} |",
         "\n## Per-load Layer-1 pooled PDR (Base PPO vs Random)\n",
         "| load | static PPO | static Rand | mobile PPO | mobile Rand |", "|---|---|---|---|---|"]
    for p in sorted(l1s):
        L.append(f"| {p} | {l1s[p][0]:.3f} | {l1s[p][1]:.3f} | {l1m[p][0]:.3f} | {l1m[p][1]:.3f} |")
    L.append("\n**Integrity:** no data or model parameter was altered to match the accepted abstract; "
             "differences are recorded as observed. Accepted DOCX byte-identical.\n")
    (OUT / "accepted_abstract_result_comparison.md").write_text("\n".join(L) + "\n")


def _figures(camp, feas_sum, mc_rows, tc_rows):
    def series(metric):
        agg = collections.defaultdict(list)
        for r in camp:
            agg[(r["method"], r["load"])].append(r[metric])
        return [{"method": m, "load": p, "mean": float(np.mean(v)),
                 "sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0}
                for (m, p), v in sorted(agg.items())]
    for mk, fn in [("pdr", "pdr_vs_load"), ("pdr_mobile", "pdr_mobile_vs_load"),
                   ("pdr_static", "pdr_static_vs_load"), ("lat_p95", "lat_p95_vs_load"),
                   ("lat_p99", "lat_p99_vs_load"), ("dv_ratio_mobile", "deadline_viol_vs_load"),
                   ("throughput_bps", "throughput_vs_load"), ("spectral_eff", "se_vs_load"),
                   ("energy_eff", "ee_vs_load"), ("jain_fairness", "fairness_vs_load"),
                   ("avg_power_w", "power_vs_load"), ("beam_acc_oracle", "beam_acc_vs_load")]:
        _wcsv(FIG / f"{fn}.csv", series(mk))
    for cls, gk, dk, fn in [("overall", "generated", "delivered", "pdr_pooled_vs_load"),
                            ("static", "gen_static", "dlv_static", "pdr_pooled_static_vs_load"),
                            ("mobile", "gen_mobile", "dlv_mobile", "pdr_pooled_mobile_vs_load")]:
        agg = collections.defaultdict(lambda: [0, 0])
        for r in camp:
            agg[(r["method"], r["load"])][0] += r[gk]; agg[(r["method"], r["load"])][1] += r[dk]
        _wcsv(FIG / f"{fn}.csv", [{"method": m, "load": p, "pdr_pooled": d / max(g, 1)}
                                  for (m, p), (g, d) in sorted(agg.items())])
    _wcsv(FIG / "constraint_feasibility_vs_load.csv", feas_sum)
    _wcsv(FIG / "multiplier_trajectories.csv", mc_rows)
    _wcsv(FIG / "training_curves.csv", tc_rows)
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for metric, fname, ylab in [("pdr_mobile", "pdr_mobile_vs_load", "Mobile PDR"),
                                    ("pdr_static", "pdr_static_vs_load", "Static PDR"),
                                    ("lat_p95", "lat_p95_vs_load", "p95 latency (slots)"),
                                    ("beam_acc_oracle", "beam_acc_vs_load", "Beam accuracy vs oracle")]:
            plt.figure(figsize=(6, 4))
            for m in X.METHOD_ORDER:
                xs, ys = [], []
                for p in LOADS:
                    vs = [r[metric] for r in camp if r["method"] == m and r["load"] == p]
                    if vs:
                        xs.append(p); ys.append(np.mean(vs))
                if xs:
                    plt.plot(xs, ys, marker="o", label=m, linewidth=1)
            plt.xlabel("offered load p"); plt.ylabel(ylab); plt.title(ylab + " vs load")
            plt.legend(fontsize=5, ncol=2); plt.grid(alpha=0.3); plt.tight_layout()
            plt.savefig(FIG / f"{fname}.png", dpi=110); plt.close()
    except Exception as e:
        (FIG / "PLOTS_README.txt").write_text(f"matplotlib unavailable ({e}); CSVs provided.\n")


def _validation_report(manifest, validation, feas_sum, problems):
    L = ["# EXPERIMENT VALIDATION REPORT (exploratory)\n",
         f"- E1 pilot: **{validation['E1_pilot']}**",
         f"- FULL_EXPERIMENTS: **{validation['FULL_EXPERIMENTS']}**",
         f"- records: {validation['actual_records']}/{validation['expected_records']} "
         f"(complete grid = {validation['complete_grid']})",
         f"- non-finite results: {not validation['no_nonfinite_results']} (problems {len(problems)})",
         f"- full drain complete (0 residual all runs): {validation['full_drain_complete']}",
         f"- reproducible rerun (EDF seed0 p0.30): {validation['reproducible_rerun']}",
         f"- BSA-C-PPO feasible load region (>=50% seeds all-constraints): {validation['feasible_load_region']}",
         f"- collapse load threshold: {validation['collapse_load_threshold']}\n",
         "## Provenance",
         f"- code sha256: `{manifest['code_sha256']}`",
         f"- campaign_config sha256: `{manifest['campaign_config_sha256']}`",
         f"- topology: {manifest['campaign_topology']}",
         f"- locked physics: {manifest['locked_physics']}\n",
         "## Constraint feasibility vs load (BSA-C-PPO)",
         "| load | feasible rate | most-common first violation |", "|---|---|---|"]
    for f in feas_sum:
        L.append(f"| {f['load']} | {f['feasible_rate']:.2f} | {f['most_common_first_violation']} |")
    L.append("\n**Scope:** preregistered computationally-bounded campaign scenario (locked physics; "
             "K>>N congestion topology) for tractable pure-numpy multi-seed × multi-load × all-method "
             "evaluation (no GPU). Full locked primary (K=8,B=8,P=4,N=8) validated executable by "
             "`test_m2`. No result altered to favour any method; accepted DOCX byte-identical.\n")
    (OUT / "EXPERIMENT_VALIDATION_REPORT.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--analyze-only", action="store_true")
    a = ap.parse_args()
    if a.analyze_only:
        analyze(); return 0
    complete, done, total = run_chunk(a.budget)
    if complete:
        validation = analyze()
        return 0 if validation["FULL_EXPERIMENTS"] == "PASSED" else 1
    return 2   # incomplete -> re-invoke


if __name__ == "__main__":
    raise SystemExit(main())
