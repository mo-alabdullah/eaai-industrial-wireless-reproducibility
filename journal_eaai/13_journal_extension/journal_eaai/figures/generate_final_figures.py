#!/usr/bin/env python3
"""DETERMINISTIC FIGURE GENERATION FROM FROZEN OUTPUTS — read-only (2026-10-13).

Produces exactly three main figures from artefacts that already exist. It runs no experiment,
never invokes the analysis pipeline, derives no new inferential statistic, performs no resampling
and uses no random number generator at all.

INPUTS (read-only; hashes printed at run time)
  ../../results_final/raw/**.json                      frozen per-unit result rows
  ../../results_final/analysis/endpoints.json          locked E1 / H2 / E2 endpoint values
  ../../results_final/analysis/descriptive/DESCRIPTIVE_SUMMARIES.json
                                                       frozen descriptive summaries (Q1, Q5)
  ../../EXACT_SOLVER_LATENCY.md                        DEVELOPMENT per-solve latency benchmark

OUTPUTS (this directory)
  figure1_h2_paired_differences.{pdf,png}
  figure2_decomposition_watts.{pdf,png}
  figure3_runtime_by_tier.{pdf,png}
  FIGURE_PROVENANCE.json

The inferential numbers quoted in captions (mean, BCa interval, exact sign-flip p, sign counts) are
READ from endpoints.json; none is recomputed here. The DEVELOPMENT latency constants are read from
the benchmark document named above and are tagged as development-tier wherever they appear.

NOTE ON DEPENDENCIES. matplotlib is used for rendering only. It is deliberately NOT added to the
C13 freeze set or to requirements-final.lock.txt, because no figure artefact can change a
scientific value: the frozen pipeline remains NumPy-only.

Usage:  python3 generate_final_figures.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent
RAW = JX / "results_final" / "raw"
ENDPOINTS = JX / "results_final" / "analysis" / "endpoints.json"
DESCRIPTIVE = JX / "results_final" / "analysis" / "descriptive" / "DESCRIPTIVE_SUMMARIES.json"
LATENCY_DOC = JX / "EXACT_SOLVER_LATENCY.md"

PRIMARY = ("R3_aged", "G2_wide10")
CELLS = [("R1_nominal", "G0_icame"), ("R1_nominal", "G2_wide10"),
         ("R3_aged", "G0_icame"), ("R3_aged", "G2_wide10")]
TERMS = ("term_allocation", "term_quantisation", "term_distortion")
TERM_LABEL = {"term_allocation": "allocation (H_G − E_G)",
              "term_quantisation": "pure quantisation (E_G − C_AG)",
              "term_distortion": "quantisation-induced distortion (C_AG − C)"}

# DEVELOPMENT-tier per-solve latency, read from EXACT_SOLVER_LATENCY.md (microseconds).
DEV_LATENCY = {
    "fixed-demand exact, per solve (DEV)": dict(median=39.0, p95=50.0, p99=54.0, max=66.0),
    "free-selection exact, per solve (DEV)": dict(median=571.0, p95=2609.0, p99=4641.0, max=8184.0),
}

plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 120, "savefig.bbox": "tight"})

_hashes: dict[str, str] = {}


def sha(p: Path) -> str:
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    _hashes[str(p.relative_to(JX))] = h
    return h


def raw_rows():
    rows = []
    for p in sorted(RAW.rglob("*.json")):
        sha(p)
        obj = json.loads(p.read_text())
        rows += obj if isinstance(obj, list) else [obj]
    return rows


def seed_mean(rows, comparator, outcome, regime, grid):
    acc: dict[int, list[float]] = {}
    for r in rows:
        if (r["comparator"] == comparator and r["regime"] == regime and r["grid"] == grid
                and r["status"] == "COMPLETED" and r.get(outcome) is not None):
            acc.setdefault(r["seed"], []).append(float(r[outcome]))
    return {s: sum(v) / len(v) for s, v in sorted(acc.items())}


def save(fig, stem):
    """Write PDF + PNG. CreationDate is suppressed so the bytes are reproducible run to run."""
    out = []
    for ext in ("pdf", "png"):
        p = HERE / f"{stem}.{ext}"
        fig.savefig(p, dpi=400 if ext == "png" else None,
                    metadata={"CreationDate": None} if ext == "pdf" else None)
        out.append(p)
    plt.close(fig)
    return out


# ----------------------------------------------------------------- Figure 1
def figure1(rows, ep):
    h2 = ep["H2"]
    a = seed_mean(rows, "EDF+ExactFixedDemand", "realised_delivery", *PRIMARY)
    b = seed_mean(rows, "OfflineExactAgedGain", "realised_delivery", *PRIMARY)
    seeds = sorted(set(a) & set(b))
    diff = [b[s] - a[s] for s in seeds]

    fig, ax = plt.subplots(figsize=(6.3, 3.0))
    x = range(len(seeds))
    colours = ["#2d6a4f" if d > 0 else ("#9d2c2c" if d < 0 else "#808080") for d in diff]
    ax.axhline(0.0, color="black", lw=0.9, zorder=1)
    ax.vlines(x, 0, diff, color=colours, lw=1.4, zorder=2)
    ax.scatter(x, diff, s=26, c=colours, zorder=3)
    ax.axhline(h2["mean_diff"], color="#1f4e79", lw=1.2, ls="--", zorder=2,
               label=f"mean {h2['mean_diff']:.2f}")
    ax.axhspan(h2["ci_low"], h2["ci_high"], color="#1f4e79", alpha=0.10, zorder=0,
               label=f"95% BCa [{h2['ci_low']:.2f}, {h2['ci_high']:.2f}]")
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(s) for s in seeds], rotation=90, fontsize=6)
    ax.set_xlabel("confirmatory seed")
    ax.set_ylabel("paired difference in realised delivery\n(packets over the horizon)")
    ax.set_title("Offline exact aged-gain reference (noncausal, non-deployable)\n"
                 "minus causal EDF with exact fixed-demand allocation", fontsize=8.5)
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    npos, nneg, nties = h2["n_positive"], h2["n_negative"], h2["n_ties"]
    ax.text(0.99, 0.03,
            f"n = {h2['n']}   {npos} positive / {nneg} negative / {nties} ties\n"
            f"exact paired two-sided sign-flip p = {h2['p_value']:.8f}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
    return save(fig, "figure1_h2_paired_differences")


# ----------------------------------------------------------------- Figure 2
def figure2(desc):
    dec = desc["decomposition_Q1"]
    labels, stacks = [], {t: [] for t in TERMS}
    for reg, grid in CELLS:
        cell = dec[f"{reg}|{grid}"]
        labels.append(f"{reg}\n{grid}")
        for t in TERMS:
            stacks[t].append(cell["terms"][t]["mean"])

    fig, ax = plt.subplots(figsize=(6.3, 3.4))
    bottom = [0.0] * len(labels)
    colours = {"term_allocation": "#1f4e79", "term_quantisation": "#c98a2b",
               "term_distortion": "#6a8e3a"}
    for t in TERMS:
        ax.bar(labels, stacks[t], bottom=bottom, color=colours[t], label=TERM_LABEL[t],
               width=0.58, edgecolor="white", linewidth=0.6)
        bottom = [x + y for x, y in zip(bottom, stacks[t])]
    for i, tot in enumerate(bottom):
        ax.text(i, tot, f"  {tot:.3f} W", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("mean gap to the continuous reference (W)")
    ax.set_title("Three-term decomposition of the gap to the continuous-power reference\n"
                 "absolute watts; the two grids are NOT nested refinement levels", fontsize=8.5)
    ax.legend(fontsize=7, frameon=False, loc="upper center", ncol=1)
    ax.set_ylim(0, max(bottom) * 1.32)
    return save(fig, "figure2_decomposition_watts")


# ----------------------------------------------------------------- Figure 3
def figure3(desc):
    rt = desc["runtime_Q5"]
    final_rows = [
        ("EDF-StaleBeam-MinFeasible (FINAL)", "EDF-StaleBeam-MinFeasible"),
        ("causal EDF + exact fixed demand (FINAL)", "EDF+ExactFixedDemand"),
        ("fixed-demand exact + continuous,\nshared timed region (FINAL)", "ExactFixedDemandRadio"),
        ("offline aged-gain reference (FINAL)", "OfflineExactAgedGain"),
        ("offline current-gain reference (FINAL)", "OfflineExactCurrentGain"),
    ]
    names, med, p95, p99, mx, tier = [], [], [], [], [], []
    for label, key in final_rows:
        m = rt[key]["microseconds"]
        names.append(label); med.append(m["median"]); p95.append(m["p95"])
        p99.append(m["p99"]); mx.append(m["max"]); tier.append("FINAL")
    for label, v in DEV_LATENCY.items():
        names.append(label); med.append(v["median"]); p95.append(v["p95"])
        p99.append(v["p99"]); mx.append(v["max"]); tier.append("DEVELOPMENT")

    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    y = list(range(len(names)))[::-1]
    for i, yy in enumerate(y):
        c = "#1f4e79" if tier[i] == "FINAL" else "#8a6d3b"
        ax.hlines(yy, med[i], mx[i], color=c, lw=1.0, alpha=0.45)
        ax.plot([p95[i], p99[i]], [yy, yy], color=c, lw=2.4, alpha=0.65)
        ax.scatter([med[i]], [yy], s=36, color=c, zorder=3)
        ax.scatter([mx[i]], [yy], s=14, marker="|", color=c, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xscale("log")
    ax.set_xlabel("wall-clock runtime (µs, log scale) — median, p95–p99 bar, maximum tick")
    ax.axvline(1000.0, color="#9d2c2c", lw=0.9, ls=":", zorder=1)
    ax.text(1000.0, -0.75, " 1 ms", color="#9d2c2c", fontsize=7, va="bottom")
    ax.set_ylim(-1.0, len(names) - 0.4)
    ax.set_title("Runtime by evidence tier — FINAL rows are per execution unit,\n"
                 "DEVELOPMENT rows are per solve; the two are not the same measurement",
                 fontsize=8.5)
    return save(fig, "figure3_runtime_by_tier")


def main() -> int:
    print("INPUT HASHES")
    rows = raw_rows()
    ep = json.loads(ENDPOINTS.read_text()); sha(ENDPOINTS)
    desc = json.loads(DESCRIPTIVE.read_text()); sha(DESCRIPTIVE)
    sha(LATENCY_DOC)
    # CANONICAL raw-tree digest, algorithm `raw_tree_digest_v1` (2026-10-13):
    #   sha256( json.dumps({<path relative to results_final/raw>: <file sha256>}, sort_keys=True) )
    # This is the algorithm used by the campaign-closure records, and it is now the only one used
    # here. An earlier version of this script hashed the SAME per-file digests under keys prefixed
    # with "results_final/raw/", which produced a different aggregate over byte-identical files and
    # was mistakable for a mismatch. The per-file hashes were never in question.
    raw_only = {k.split("results_final/raw/", 1)[1]: v
                for k, v in _hashes.items() if "results_final/raw/" in k}
    raw_tree_digest_v1 = hashlib.sha256(
        json.dumps(dict(sorted(raw_only.items())), sort_keys=True).encode()).hexdigest()
    for k in sorted(_hashes):
        if "/raw/" not in k:
            print(f"  {k}\n    {_hashes[k]}")
    print(f"  results_final/raw/  ({len(raw_only)} files) raw_tree_digest_v1\n"
          f"    {raw_tree_digest_v1}")

    produced = []
    produced += figure1(rows, ep)
    produced += figure2(desc)
    produced += figure3(desc)

    print("\nOUTPUT HASHES")
    out = {}
    for p in produced:
        d = hashlib.sha256(p.read_bytes()).hexdigest()
        out[p.name] = d
        print(f"  {p.name}\n    {d}")

    (HERE / "FIGURE_PROVENANCE.json").write_text(json.dumps({
        "generator": "journal_eaai/figures/generate_final_figures.py",
        "deterministic": True,
        "random_resampling": False,
        "new_inferential_statistics_derived": False,
        "inputs": {k: v for k, v in sorted(_hashes.items()) if "/raw/" not in k},
        "raw_tree_digest_v1": raw_tree_digest_v1,
        "raw_tree_digest_algorithm": ("sha256(json.dumps({path relative to results_final/raw: file sha256}, sort_keys=True)) — canonical; identical to the campaign-closure records"),
        "raw_tree_files": len(raw_only),
        "development_latency_source": "EXACT_SOLVER_LATENCY.md (DEVELOPMENT tier, per solve)",
        "outputs": out,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {HERE / 'FIGURE_PROVENANCE.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
