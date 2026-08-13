#!/usr/bin/env python3
""" publication figures + exact table/claim numbers — derived PROGRAMMATICALLY from the frozen
confirmatory CSVs (10_confirmatory/). No hand-typed result values. No experiments are run.
Outputs: 11_final_paper/figures/*.png (Fig 1-7) and 11_final_paper/_paper_numbers.json.
"""
from __future__ import annotations
import csv, json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "results" / "confirmatory"
FIG = ROOT / "11_final_paper" / "figures"; FIG.mkdir(parents=True, exist_ok=True)
TAB = ROOT / "11_final_paper" / "tables"; TAB.mkdir(parents=True, exist_ok=True)
LOADS = [0.05, 0.10, 0.20, 0.30, 0.40]

rows = list(csv.DictReader((CONF / "per_seed_metrics.csv").open()))
for r in rows:
    for k, v in r.items():
        if k not in ("method",):
            try: r[k] = float(v)
            except (ValueError, TypeError): pass

def mean(method, load, key):
    vs = [r[key] for r in rows if r["method"] == method and abs(r["load"] - load) < 1e-9]
    return float(np.mean(vs)) if vs else float("nan")

def pooled(method, load, gk, dk):
    rs = [r for r in rows if r["method"] == method and abs(r["load"] - load) < 1e-9]
    g = sum(r[gk] for r in rs); d = sum(r[dk] for r in rs)
    return d / max(g, 1)

EMPH = ["L1-Fixed-Random", "L1-Fixed-BasePPO", "EDF", "StaleMaxGain", "MaxSINROracle",
        "BSA-Unconstrained-PPO", "BSA-Penalty-PPO", "BSA-C-PPO"]
LAB = {"L1-Fixed-Random": "L1 Fixed-Radio Random", "L1-Fixed-BasePPO": "L1 Fixed-Radio Base PPO",
       "EDF": "EDF", "StaleMaxGain": "Stale-Max-Gain", "MaxSINROracle": "Current-CSI Max-SINR",
       "BSA-Unconstrained-PPO": "BSA-Unconstrained-PPO", "BSA-Penalty-PPO": "BSA-Penalty-PPO",
       "BSA-C-PPO": "BSA-C-PPO"}
STY = {m: st for m, st in zip(EMPH, ["o--", "s--", "^-", "v-", "D-", "P-", "X-", "*-"])}
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 150})


def line_fig(fname, key, ylab, title, methods, pooledkeys=None, hline=None, hlabel=None, ylim=None):
    plt.figure(figsize=(5.2, 3.4))
    for m in methods:
        ys = [pooled(m, p, *pooledkeys) if pooledkeys else mean(m, p, key) for p in LOADS]
        plt.plot(LOADS, ys, STY.get(m, "o-"), label=LAB.get(m, m), linewidth=1.2, markersize=4)
    if hline is not None:
        plt.axhline(hline, color="k", ls=":", lw=1.0, label=hlabel)
    plt.xlabel("Offered load $p$ (Bernoulli arrival prob.)"); plt.ylabel(ylab)
    plt.title(title, fontsize=9)
    if ylim: plt.ylim(*ylim)
    plt.legend(fontsize=6, ncol=2, loc="best"); plt.tight_layout()
    plt.savefig(FIG / fname); plt.close()


# Fig 2: PDR vs load (static + mobile), key methods (pooled ratio-of-sums)
key2 = ["L1-Fixed-Random", "L1-Fixed-BasePPO", "EDF", "MaxSINROracle", "BSA-C-PPO"]
plt.figure(figsize=(7.4, 3.2))
for i, (cls, gk, dk, ttl) in enumerate([("static", "gen_static", "dlv_static", "(a) Static sensors"),
                                        ("mobile", "gen_mobile", "dlv_mobile", "(b) Mobile AMR/AGV")]):
    ax = plt.subplot(1, 2, i + 1)
    for m in key2:
        ys = [pooled(m, p, gk, dk) for p in LOADS]
        ax.plot(LOADS, ys, STY.get(m, "o-"), label=LAB.get(m, m), linewidth=1.2, markersize=4)
    ax.set_xlabel("Offered load $p$"); ax.set_ylabel("Packet delivery ratio"); ax.set_title(ttl, fontsize=9)
    ax.grid(alpha=0.3)
    if i == 1: ax.legend(fontsize=6, loc="lower left")
plt.tight_layout(); plt.savefig(FIG / "fig2_pdr_vs_load.png"); plt.close()

# Fig 3: p95 latency vs load
line_fig("fig3_latency_vs_load.png", "lat_p95", "p95 latency (slots)",
         "p95 uplink latency vs load", ["EDF", "StaleMaxGain", "MaxSINROracle", "BSA-C-PPO", "L1-Fixed-BasePPO"])

# Fig 4: avg power vs load with P_bar=0.8 budget line
line_fig("fig4_power_vs_load.png", "avg_power_w", "Mean transmit power (W)",
         "Average transmit power vs load", ["EDF", "MaxSINROracle", "Random", "BSA-C-PPO",
         "BSA-Unconstrained-PPO"], hline=0.8, hlabel=r"$\bar P = 0.80$ W budget")

# Fig 5: beam accuracy vs load with chance line 1/B
line_fig("fig5_beam_acc_vs_load.png", "beam_acc_oracle", "Beam accuracy vs current-CSI oracle",
         "Learned vs heuristic beam accuracy", ["PerfectMaxGain", "StaleMaxGain", "EDF",
         "Random", "BSA-C-PPO"], hline=0.125, hlabel="random chance $1/B=0.125$", ylim=(0, 1.05))

# Fig 6: constraint feasibility vs load (BSA-C-PPO)
fs = list(csv.DictReader((CONF / "constraint_feasibility_summary.csv").open()))
plt.figure(figsize=(5.2, 3.4))
xs = [float(r["load"]) for r in fs]; ys = [float(r["feasible_rate"]) for r in fs]
plt.plot(xs, ys, "P-", color="C3", linewidth=1.4, markersize=6, label="BSA-C-PPO all-constraints feasible")
plt.axhline(0.5, color="k", ls=":", lw=1.0, label="0.5 feasibility reference")
plt.xlabel("Offered load $p$"); plt.ylabel("Fraction of seeds feasible"); plt.ylim(-0.05, 1.05)
plt.title("BSA-C-PPO constraint feasibility vs load", fontsize=9)
plt.legend(fontsize=7); plt.tight_layout(); plt.savefig(FIG / "fig6_feasibility_vs_load.png"); plt.close()

# Fig 7: BSA-C-PPO multiplier trajectory (mobile reliability/deadline channels) at p=0.4
mc = list(csv.DictReader((CONF / "raw_curves.jsonl").open())) if (CONF / "raw_curves.jsonl").exists() else []
import json as _json
curves = [_json.loads(l) for l in (CONF / "raw_curves.jsonl").read_text().splitlines() if l.strip()]
cp = [c for c in curves if c["method"] == "BSA-C-PPO" and abs(c["load"] - 0.4) < 1e-9]
plt.figure(figsize=(5.2, 3.4))
if cp:
    reward = np.mean([c["reward"] for c in cp], axis=0)
    plt.plot(range(len(reward)), reward, "o-", color="C0", label="mean training return (10 seeds)")
plt.xlabel("PPO update"); plt.ylabel("Mean episodic return")
plt.title("BSA-C-PPO training return (p=0.40)", fontsize=9)
plt.legend(fontsize=7); plt.tight_layout(); plt.savefig(FIG / "fig7_training_curve.png"); plt.close()

# Fig 1: system/model architecture schematic
fig, ax = plt.subplots(figsize=(7.0, 3.6)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 6)
def box(x, y, w, h, text, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=fc, ec="k", lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8)
box(0.3, 4.4, 2.2, 1.1, "6 static\nsensors", "#cfe8ff")
box(0.3, 0.5, 2.2, 1.1, "2 mobile\nAMR/AGV\n(waypoint, 0-2 m/s)", "#ffe0cc")
box(6.9, 2.4, 2.8, 1.4, "6G Access Point\nULA M=8 antennas\nDFT beam codebook B=8\nN=4 subchannels", "#d8f5d8")
box(3.6, 3.7, 2.7, 1.6, "InF-SH mmWave (28 GHz)\npath loss + shadowing\nRician/Rayleigh\nstale CSI $d_{CSI}=1$", "#f5f0d0")
box(3.6, 0.4, 2.7, 1.4, "CMDP: reliability,\ndeadline, overflow,\naverage-power budget\nBSA-C-PPO", "#efe0f5")
for y in (4.95, 1.05):
    ax.add_patch(FancyArrowPatch((2.5, y), (3.6, 2.6 if y > 3 else 3.0),
                 arrowstyle="->", mutation_scale=12, lw=1))
ax.add_patch(FancyArrowPatch((6.3, 4.5), (6.9, 3.6), arrowstyle="->", mutation_scale=12, lw=1))
ax.add_patch(FancyArrowPatch((6.3, 1.1), (6.9, 2.4), arrowstyle="->", mutation_scale=12, lw=1))
ax.text(5, 5.7, "Uplink scheduling / spectrum / beam / power over InF-SH mmWave 6G IIoT",
        ha="center", fontsize=9, weight="bold")
plt.tight_layout(); plt.savefig(FIG / "fig1_architecture.png"); plt.close()

# ---- exact numbers for tables + claim audit ----
nums = {
    "n_primary_records": len([r for r in rows]),
    "n_seeds": 10, "n_loads": len(LOADS), "n_methods": 12,
    "edf_mobile_pdr_by_load": {p: pooled("EDF", p, "gen_mobile", "dlv_mobile") for p in LOADS},
    "bsacppo_mobile_pdr_p40": pooled("BSA-C-PPO", 0.40, "gen_mobile", "dlv_mobile"),
    "bsacppo_mobile_pdr_p40_seedmean": mean("BSA-C-PPO", 0.40, "pdr_mobile"),
    "learned_mean_power_p40": mean("BSA-C-PPO", 0.40, "avg_power_w"),
    "heuristic_mean_power_p40_edf": mean("EDF", 0.40, "avg_power_w"),
    "beam_chance": 0.125,
    "bsacppo_beam_acc_range": [min(mean("BSA-C-PPO", p, "beam_acc_oracle") for p in LOADS),
                               max(mean("BSA-C-PPO", p, "beam_acc_oracle") for p in LOADS)],
    "variants_identical_p40": {
        m: {"pdr_mobile": mean(m, 0.40, "pdr_mobile"), "C_pow": mean(m, 0.40, "C_pow"),
            "beam_acc": mean(m, 0.40, "beam_acc_oracle")}
        for m in ("BSA-Unconstrained-PPO", "BSA-Penalty-PPO", "BSA-C-PPO")},
    "l1_static_pdr_by_load": {p: (pooled("L1-Fixed-BasePPO", p, "gen_static", "dlv_static"),
                                  pooled("L1-Fixed-Random", p, "gen_static", "dlv_static")) for p in LOADS},
    "l1_mobile_pdr_by_load": {p: (pooled("L1-Fixed-BasePPO", p, "gen_mobile", "dlv_mobile"),
                                  pooled("L1-Fixed-Random", p, "gen_mobile", "dlv_mobile")) for p in LOADS},
    "table2_p40": {m: {"pdr_static": mean(m, 0.40, "pdr_static"), "pdr_mobile": mean(m, 0.40, "pdr_mobile"),
                       "lat_p95": mean(m, 0.40, "lat_p95"), "avg_power_w": mean(m, 0.40, "avg_power_w"),
                       "beam_acc": mean(m, 0.40, "beam_acc_oracle")}
                   for m in ["EDF", "MaxSINROracle", "StaleMaxGain", "Random",
                             "BSA-Unconstrained-PPO", "BSA-C-PPO", "L1-Fixed-Random", "L1-Fixed-BasePPO"]},
}
# pairwise stats from CSV
st = list(csv.DictReader((CONF / "pairwise_statistics.csv").open()))
nums["stat_cppo_vs_edf_mobile_p40"] = next(
    ({"mean_diff": float(r["mean_diff"]), "p_holm": float(r["p_holm"]), "d_z": float(r["cohens_dz"])}
     for r in st if r["load"] == "0.4" and r["metric"] == "pdr_mobile" and r["B"] == "EDF"), {})
nums["stat_cppo_vs_uncon_mobile_p40"] = next(
    ({"mean_diff": float(r["mean_diff"]), "p_holm": float(r["p_holm"])}
     for r in st if r["load"] == "0.4" and r["metric"] == "pdr_mobile" and r["B"] == "BSA-Unconstrained-PPO"), {})
(ROOT / "11_final_paper" / "_paper_numbers.json").write_text(json.dumps(nums, indent=2, default=float))
print("figures + numbers written:", sorted(p.name for p in FIG.glob("*.png")))
print("primary records:", nums["n_primary_records"], "| EDF mobile PDR p0.40:",
      round(nums["edf_mobile_pdr_by_load"][0.40], 3), "| C-PPO mobile p0.40:",
      round(nums["bsacppo_mobile_pdr_p40"], 3))
