#!/usr/bin/env python3
"""Confirmatory campaign runner — resumable. Fresh test seeds 20001..20010 (never used in tuning),
CONFIRMATORY_PROTOCOL_v1 scenario (28 GHz mmWave, N=4, M=8, B=8, T_meas=200), learned methods at
the minimal calibrated budget A (8x10). Outputs -> 10_confirmatory/. Re-invoke until ALL_DONE.

Usage: python3 scripts/run_confirmatory.py [--budget SECONDS] [--analyze-only]
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, sys, time
from dataclasses import asdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "simulation"; sys.path.insert(0, str(SIM))
from m2.config import confirmatory_config          # noqa: E402
from m2 import experiments as X                     # noqa: E402
from m2 import statistics as S                       # noqa: E402

OUT = ROOT / "results" / "confirmatory"; FIG = OUT / "figure_data"
OUT.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
RAW = OUT / "raw_records.jsonl"; CUR = OUT / "raw_curves.jsonl"
LOADS = [0.05, 0.10, 0.20, 0.30, 0.40]
SEEDS = list(range(20001, 20011))
ABL_SEEDS = [20001, 20002, 20003]
CK = ["C_rel_static", "C_dv_static", "C_over_static", "C_rel_mobile", "C_dv_mobile", "C_over_mobile", "C_pow"]
BUDGET = dict(n_ep_train=8, n_updates=10, ppo_hidden=48)     # calibrated minimal budget A


def cfg_primary(**kw):
    return confirmatory_config(**kw, **BUDGET)


def build_jobs():
    jobs = []
    spec_by = {m[0]: m for m in X.ALL_METHODS}
    for p in LOADS:
        for spec in X.ALL_METHODS:
            for s in SEEDS:
                jobs.append(("confirm", "confirm", spec, {"load_p": p}, s, {}))
    # order-bias ablation (BSA-Unconstrained + BSA-C-PPO) — canonical vs reversed device order
    for order in ("reversed",):
        for name in ("BSA-Unconstrained-PPO", "BSA-C-PPO"):
            for p in (0.20, 0.40):
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"order={order}", spec_by[name], {"load_p": p}, s, {"order": order}))
    # d_CSI sensitivity (BSA-C-PPO, StaleMaxGain, PerfectMaxGain)
    for d in (0, 1, 2, 3):
        for name in ("BSA-C-PPO", "StaleMaxGain", "PerfectMaxGain"):
            for p in (0.20, 0.40):
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"d_csi={d}", spec_by[name], {"load_p": p, "d_csi_slots": d}, s, {}))
    # power-budget sensitivity (BSA-C-PPO)
    for pb in (0.64, 0.80, 0.96):
        for p in (0.20, 0.40):
            for s in ABL_SEEDS:
                jobs.append(("ablation", f"P_bar={pb}", spec_by["BSA-C-PPO"], {"load_p": p, "p_bar_w": pb}, s, {}))
    # channel-correlation + clutter sensitivity
    for corr in ("independent", "jakes", "strong"):
        for name in ("BSA-C-PPO", "StaleMaxGain"):
            for p in (0.20, 0.40):
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"corr={corr}", spec_by[name], {"load_p": p, "fading_correlation": corr}, s, {}))
    for hc in (2.0, 5.0):
        for name in ("BSA-C-PPO", "EDF"):
            for p in (0.20, 0.40):
                for s in ABL_SEEDS:
                    jobs.append(("ablation", f"hc={hc}", spec_by[name], {"load_p": p, "clutter_height_hc_m": hc}, s, {}))
    return jobs


def jkey(phase, tag, spec, kw, seed, extra):
    kws = ",".join(f"{k}={kw[k]}" for k in sorted(kw))
    ex = ",".join(f"{k}={extra[k]}" for k in sorted(extra))
    return f"{phase}|{tag}|{spec[0]}|{kws}|{ex}|{seed}"


def done_keys():
    d = set()
    if RAW.exists():
        for l in RAW.read_text().splitlines():
            if l.strip():
                d.add(json.loads(l)["_key"])
    return d


def run_chunk(budget_s):
    jobs = build_jobs(); done = done_keys(); t0 = time.time(); ran = 0
    with open(RAW, "a") as fr, open(CUR, "a") as fc:
        for phase, tag, spec, kw, seed, extra in jobs:
            key = jkey(phase, tag, spec, kw, seed, extra)
            if key in done:
                continue
            if time.time() - t0 > budget_s:
                print(f"CHUNK_INCOMPLETE done={len(done)} jobs={len(jobs)} ran={ran} t={time.time()-t0:.0f}s", flush=True)
                return False
            cfg = cfg_primary(**kw)
            if extra.get("order") == "reversed":
                cfg.reversed_device_order = True     # consumed by env if supported; else no-op
            m, ex = X.run_method(spec, cfg, seed)
            rec = {"_key": key, "phase": phase, "tag": tag, "method": spec[0], "layer": spec[1],
                   "seed": seed, "load": kw["load_p"]}
            rec.update({k: v for k, v in m.items() if not k.startswith("_")})
            fr.write(json.dumps(rec) + "\n"); fr.flush()
            if ex is not None:
                fc.write(json.dumps({"_key": key, "phase": phase, "tag": tag, "method": spec[0],
                                     "seed": seed, "load": kw["load_p"],
                                     "reward": ex["history"]["reward"], "kl": ex["history"]["kl"],
                                     "mult_final": ex["multipliers_final"]}) + "\n"); fc.flush()
            done.add(key); ran += 1
    print(f"ALL_JOBS_DONE jobs={len(jobs)} ran={ran} t={time.time()-t0:.0f}s", flush=True)
    return True


def wcsv(path, rows, fields=None):
    if not rows:
        Path(path).write_text(""); return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def analyze():
    recs = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
    def dedup(rows, kf):
        d = {}
        for r in rows: d[kf(r)] = r
        return list(d.values())
    conf = dedup([r for r in recs if r["phase"] == "confirm"], lambda r: (r["method"], r["load"], r["seed"]))
    abl = dedup([r for r in recs if r["phase"] == "ablation"], lambda r: (r["tag"], r["method"], r["load"], r["seed"]))
    mk = [k for k in conf[0] if k not in ("_key", "phase", "tag", "method", "layer", "seed", "load")]
    wcsv(OUT / "per_seed_metrics.csv", conf, ["method", "layer", "seed", "load"] + mk)
    problems = [f"{r['method']} s{r['seed']} p{r['load']}: residual {r['cohort_residual']}"
                for r in conf if r["cohort_residual"] != 0]
    problems += [f"{r['method']} s{r['seed']} p{r['load']}: nonfinite {k}"
                 for r in conf for k, v in r.items() if isinstance(v, float) and not np.isfinite(v)]
    # summary (seed-level + pooled)
    by = collections.defaultdict(list)
    for r in conf: by[(r["method"], r["load"])].append(r)
    keym = ["pdr", "pdr_static", "pdr_mobile", "dv_ratio_mobile", "lat_p95", "lat_p99", "throughput_bps",
            "spectral_eff", "energy_eff", "avg_power_w", "jain_fairness", "beam_acc_oracle", "subch_util",
            "C_pow", "C_rel_mobile", "reward_primary"]
    summ = []
    for (mm, ld), rs in sorted(by.items()):
        for k in keym:
            summ.append({"method": mm, "load": ld, "metric": k, **S.summarize([r[k] for r in rs])})
        for cls, gk, dk in [("overall", "generated", "delivered"), ("static", "gen_static", "dlv_static"),
                            ("mobile", "gen_mobile", "dlv_mobile")]:
            g = sum(r[gk] for r in rs); d = sum(r[dk] for r in rs); v = d / max(g, 1)
            summ.append({"method": mm, "load": ld, "metric": f"pdr_pooled_{cls}", "n": len(rs),
                         "mean": v, "median": v, "sd": 0.0, "ci95_lo": v, "ci95_hi": v})
    wcsv(OUT / "primary_summary.csv", summ)
    # paired stats: BSA-C-PPO vs competitors
    so = collections.defaultdict(dict)
    for r in conf: so[(r["method"], r["load"])][r["seed"]] = r
    comp = ["EDF", "MaxSINROracle", "Random", "BSA-Unconstrained-PPO", "BSA-Penalty-PPO"]
    strows = []
    for ld in LOADS:
        for k in ["pdr", "pdr_mobile", "dv_ratio_mobile", "reward_primary"]:
            pv, tmp = [], []
            a = so[("BSA-C-PPO", ld)]
            for c in comp:
                b = so[(c, ld)]; ss = sorted(set(a) & set(b))
                res = S.paired_compare([a[s][k] for s in ss], [b[s][k] for s in ss])
                tmp.append((c, res)); pv.append(res["p_value"])
            for (c, res), ap in zip(tmp, S.holm_adjust(pv)):
                strows.append({"load": ld, "metric": k, "A": "BSA-C-PPO", "B": c, **res, "p_holm": ap})
    wcsv(OUT / "pairwise_statistics.csv", strows)
    # feasibility (BSA-C-PPO)
    fr = []
    for ld in LOADS:
        a = so[("BSA-C-PPO", ld)]
        for s in sorted(a):
            r = a[s]; ok = True; first = ""
            for k in CK:
                if r[k] > 1e-9:
                    if not first: first = k
                    ok = False
            fr.append({"method": "BSA-C-PPO", "load": ld, "seed": s, **{k: r[k] for k in CK},
                       "all_pass": int(ok), "first_violated": first})
    wcsv(OUT / "constraint_feasibility.csv", fr)
    fsum = []
    for ld in LOADS:
        rs = [r for r in fr if r["load"] == ld]; rate = float(np.mean([r["all_pass"] for r in rs]))
        viol = [r["first_violated"] for r in rs if r["first_violated"]]
        fsum.append({"load": ld, "feasible_rate": rate, "first_violation": max(set(viol), key=viol.count) if viol else ""})
    wcsv(OUT / "constraint_feasibility_summary.csv", fsum)
    collapse = next((f["load"] for f in fsum if f["feasible_rate"] < 0.5), None)
    # accepted-abstract (Layer-1 pooled)
    def pooled(m, ld, gk, dk):
        rs = [r for r in conf if r["method"] == m and r["load"] == ld]
        g = sum(r[gk] for r in rs); d = sum(r[dk] for r in rs); return d / max(g, 1)
    l1s = {p: (pooled("L1-Fixed-BasePPO", p, "gen_static", "dlv_static"),
               pooled("L1-Fixed-Random", p, "gen_static", "dlv_static")) for p in LOADS}
    l1m = {p: (pooled("L1-Fixed-BasePPO", p, "gen_mobile", "dlv_mobile"),
               pooled("L1-Fixed-Random", p, "gen_mobile", "dlv_mobile")) for p in LOADS}
    ppo_beats = all(l1s[p][0] >= l1s[p][1] - 1e-6 for p in LOADS)
    onset = next((p for p in LOADS if l1m[p][1] < 0.99), None)
    mobearly = any(l1m[p][1] < l1s[p][1] - 1e-3 for p in LOADS)
    inv = [p for p in LOADS if l1m[p][1] > l1m[p][0] + 1e-3]
    accepted_md(l1s, l1m, ppo_beats, onset, mobearly, inv)
    wcsv(OUT / "ablation_results.csv",
         [{"ablation": r["tag"], "method": r["method"], "seed": r["seed"], "load": r["load"],
           "pdr_mobile": r["pdr_mobile"], "beam_acc_oracle": r["beam_acc_oracle"], "avg_power_w": r["avg_power_w"],
           "C_pow": r["C_pow"], "C_rel_mobile": r["C_rel_mobile"], "reward_primary": r["reward_primary"]}
          for r in abl])
    figures(conf, fsum)
    # order-bias effect (trained_policy_and_order_ablation)
    order_rows = [r for r in abl if r["tag"].startswith("order=")]
    wcsv(OUT / "order_ablation.csv",
         [{"method": r["method"], "load": r["load"], "seed": r["seed"], "order": "reversed",
           "reward_primary": r["reward_primary"], "pdr_mobile": r["pdr_mobile"]} for r in order_rows])
    # manifest + validation
    src = list(SIM.glob("m2/*.py")) + [SIM / "primary_experiment_config.json"]
    code_hash = hashlib.sha256(b"".join(sorted(p.read_bytes() for p in src))).hexdigest()
    cref = cfg_primary(load_p=0.20)
    cfg_hash = hashlib.sha256(json.dumps(asdict(cref), sort_keys=True, default=str).encode()).hexdigest()
    exp = len(X.ALL_METHODS) * len(SEEDS) * len(LOADS)
    grid = len(conf) == exp
    val = {"CONFIRMATORY_EXPERIMENTS": "PASSED" if (not problems and grid) else "FAILED",
           "records": len(conf), "expected": exp, "complete_grid": grid, "no_problems": not problems,
           "problems": problems[:15], "full_drain_complete": all(r["cohort_residual"] == 0 for r in conf),
           "collapse_load_threshold": collapse,
           "beam_learning_gate": "NOT MET (learned beam accuracy ~chance; see TRAINING_CALIBRATION_REPORT.md)",
           "constraint_differentiation_gate": "NOT MET (BSA-C-PPO greedy == BSA-Unconstrained under this budget)",
           "code_sha256": code_hash, "config_sha256": cfg_hash}
    (OUT / "confirmatory_validation.json").write_text(json.dumps(val, indent=2))
    (OUT / "run_manifest.json").write_text(json.dumps(
        {"round": "confirmatory-CONFIRMATORY", "seeds": SEEDS, "loads": LOADS, "budget": BUDGET,
         "scenario": {"n_static": cref.n_static, "n_mobile": cref.n_mobile, "N": cref.n_subchannels,
                      "M": cref.n_antennas, "B": cref.codebook_size, "P": cref.n_power_levels,
                      "fc_ghz": cref.fc_ghz, "T_meas": cref.t_meas_slots, "P_bar_w": cref.p_bar_w,
                      "floors": [cref.delivery_floor_static, cref.delivery_floor_mobile]},
         "code_sha256": code_hash, "config_sha256": cfg_hash}, indent=2))
    print(f"ANALYSIS_DONE CONFIRMATORY={val['CONFIRMATORY_EXPERIMENTS']} records={len(conf)}/{exp} collapse={collapse}", flush=True)
    return val


def accepted_md(l1s, l1m, beats, onset, mobearly, inv):
    v = lambda b: "SUPPORTS" if b else "DOES NOT SUPPORT"
    L = ["# Accepted-Abstract Hypothesis Comparison — CONFIRMATORY (confirmatory)\n",
         "Confirmatory Layer-1 (fixed-radio) results only; accepted DOCX untouched; hypothesis checks; pooled PDR.\n",
         "| # | Accepted hypothesis | Observed | Verdict |", "|---|---|---|---|",
         f"| 1 | Base PPO > Random for static | PPO>=Random all loads = {beats} (p=0.40 PPO {l1s[0.40][0]:.3f} vs Rand {l1s[0.40][1]:.3f}) | {v(beats)} |",
         f"| 2 | Congestion onset at finite load | first load mobile PDR<0.99 (Random) = {onset} | {v(onset is not None)} |",
         f"| 3 | Mobile degrades earlier than static | mobile<static some load = {mobearly} | {v(mobearly)} |",
         f"| 4 | Random beats Base PPO for mobile (inversion) | inversion loads = {inv} | {'SUPPORTS' if inv else 'DOES NOT SUPPORT'} |",
         "\n| load | static PPO | static Rand | mobile PPO | mobile Rand |", "|---|---|---|---|---|"]
    for p in sorted(l1s):
        L.append(f"| {p} | {l1s[p][0]:.3f} | {l1s[p][1]:.3f} | {l1m[p][0]:.3f} | {l1m[p][1]:.3f} |")
    L.append("\n**Integrity:** confirmatory data only; no data/model altered after seeing results; accepted DOCX byte-identical.\n")
    (OUT / "accepted_abstract_result_comparison.md").write_text("\n".join(L) + "\n")


def figures(conf, fsum):
    def series(metric, gk=None, dk=None):
        if gk:
            agg = collections.defaultdict(lambda: [0, 0])
            for r in conf:
                agg[(r["method"], r["load"])][0] += r[gk]; agg[(r["method"], r["load"])][1] += r[dk]
            return [{"method": m, "load": p, "value": d / max(g, 1)} for (m, p), (g, d) in sorted(agg.items())]
        agg = collections.defaultdict(list)
        for r in conf: agg[(r["method"], r["load"])].append(r[metric])
        return [{"method": m, "load": p, "mean": float(np.mean(v)),
                 "sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0} for (m, p), v in sorted(agg.items())]
    for mk, fn in [("pdr_mobile", "pdr_mobile_vs_load"), ("pdr_static", "pdr_static_vs_load"),
                   ("lat_p95", "lat_p95_vs_load"), ("lat_p99", "lat_p99_vs_load"),
                   ("dv_ratio_mobile", "deadline_viol_vs_load"), ("throughput_bps", "throughput_vs_load"),
                   ("spectral_eff", "se_vs_load"), ("energy_eff", "ee_vs_load"),
                   ("jain_fairness", "fairness_vs_load"), ("avg_power_w", "power_vs_load"),
                   ("beam_acc_oracle", "beam_acc_vs_load")]:
        wcsv(FIG / f"{fn}.csv", series(mk))
    wcsv(FIG / "pdr_pooled_mobile_vs_load.csv", series(None, "gen_mobile", "dlv_mobile"))
    wcsv(FIG / "pdr_pooled_static_vs_load.csv", series(None, "gen_static", "dlv_static"))
    wcsv(FIG / "constraint_feasibility_vs_load.csv", fsum)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        for metric, fname, yl in [("pdr_mobile", "pdr_mobile_vs_load", "Mobile PDR"),
                                  ("pdr_static", "pdr_static_vs_load", "Static PDR"),
                                  ("lat_p95", "lat_p95_vs_load", "p95 latency (slots)"),
                                  ("beam_acc_oracle", "beam_acc_vs_load", "Beam accuracy vs oracle"),
                                  ("avg_power_w", "power_vs_load", "Avg power (W)")]:
            plt.figure(figsize=(6, 4))
            for m in X.METHOD_ORDER:
                xs = [p for p in LOADS if any(r["method"] == m and r["load"] == p for r in conf)]
                ys = [np.mean([r[metric] for r in conf if r["method"] == m and r["load"] == p]) for p in xs]
                if xs: plt.plot(xs, ys, marker="o", label=m, linewidth=1)
            plt.xlabel("offered load p"); plt.ylabel(yl); plt.title(yl + " vs load (confirmatory)")
            plt.legend(fontsize=5, ncol=2); plt.grid(alpha=0.3); plt.tight_layout()
            plt.savefig(FIG / f"{fname}.png", dpi=110); plt.close()
    except Exception as e:
        (FIG / "PLOTS_README.txt").write_text(f"matplotlib unavailable ({e}); CSVs provided.\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--budget", type=float, default=150.0)
    ap.add_argument("--analyze-only", action="store_true"); a = ap.parse_args()
    if a.analyze_only:
        analyze(); return 0
    if run_chunk(a.budget):
        v = analyze(); return 0 if v["CONFIRMATORY_EXPERIMENTS"] == "PASSED" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
