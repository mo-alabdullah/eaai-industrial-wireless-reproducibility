#!/usr/bin/env python3
"""DESCRIPTIVE EXTRACTION FROM FROZEN FINAL OUTPUTS — read-only (2026-10-07).

Supplies the DESCRIPTIVE quantities that tables R2 (secondary rows), R4 and R5 need and that
endpoints.json does not carry. It does NOT run any experiment, does NOT touch the endpoint plan,
and does NOT recompute E1, H2 or E2.

Guarantees, enforced below:
  * reads results_final/raw/ only, never writes into it;
  * never writes endpoints.json or AUDIT_REPORT.json;
  * computes NO p-value, NO bootstrap interval and NO effect size — descriptive summaries only;
  * output is deterministic (sorted keys, no timestamps in the payload digest).

Usage:  python3 extract_descriptive.py            # write results_final/analysis/descriptive/
        python3 extract_descriptive.py --print    # stdout only, writes nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent
RAW = JX / "results_final" / "raw"
OUT = JX / "results_final" / "analysis" / "descriptive"

PROTECTED = {"endpoints.json", "AUDIT_REPORT.json"}

CELLS = [("R1_nominal", "G0_icame"), ("R1_nominal", "G2_wide10"),
         ("R3_aged", "G0_icame"), ("R3_aged", "G2_wide10")]

TERMS = ("term_allocation", "term_quantisation", "term_distortion")


def load_rows():
    rows = []
    for p in sorted(RAW.rglob("*.json")):
        obj = json.loads(p.read_text())
        rows += obj if isinstance(obj, list) else [obj]
    return rows


def q(xs, p):
    """Linear-interpolation percentile on a sorted copy. No external dependency."""
    s = sorted(xs)
    if not s:
        return None
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summary(xs):
    xs = [float(x) for x in xs if x is not None]
    if not xs:
        return None
    return {
        "n": len(xs), "mean": st.mean(xs), "sd": st.stdev(xs) if len(xs) > 1 else 0.0,
        "median": st.median(xs), "p95": q(xs, 0.95), "p99": q(xs, 0.99),
        "min": min(xs), "max": max(xs),
        "fraction_exactly_zero": sum(1 for x in xs if x == 0.0) / len(xs),
    }


def seed_mean(rows, comparator, outcome, regime, grid):
    acc = {}
    for r in rows:
        if (r["comparator"] == comparator and r["regime"] == regime and r["grid"] == grid
                and r["status"] == "COMPLETED" and r.get(outcome) is not None):
            acc.setdefault(r["seed"], []).append(float(r[outcome]))
    return {s: sum(v) / len(v) for s, v in sorted(acc.items())}


def build(rows):
    out = {"source": "results_final/raw", "n_rows": len(rows),
           "method": "descriptive summaries only; no test, no bootstrap, no effect size"}

    # ---- R4: three-term decomposition, per cell, from the ContinuousPowerRef rows -------------
    dec = {}
    for reg, grid in CELLS:
        sub = [r for r in rows if r["comparator"] == "ContinuousPowerRef"
               and r["regime"] == reg and r["grid"] == grid and r["status"] == "COMPLETED"]
        if not sub:
            dec[f"{reg}|{grid}"] = None
            continue
        total = [r["gap_H_G"] - r["gap_C"] for r in sub]
        cell = {"n_units": len(sub),
                "total_gap": summary(total),
                "ratio_HG_over_C": None,
                "terms": {t: summary([r[t] for r in sub]) for t in TERMS},
                "grid_infeasible": sum(1 for r in sub if r.get("grid_infeasible_flag")),
                "cont_infeasible": sum(1 for r in sub if r.get("cont_infeasible_flag"))}
        ratios = [r["gap_H_G"] / r["gap_C"] for r in sub if r.get("gap_C")]
        if ratios:
            cell["ratio_HG_over_C"] = {"n": len(ratios), "median": st.median(ratios),
                                       "q1": q(ratios, 0.25), "q3": q(ratios, 0.75)}
        tot_mean = cell["total_gap"]["mean"]
        cell["shares_of_mean_total"] = {
            t: (cell["terms"][t]["mean"] / tot_mean if tot_mean else None) for t in TERMS}
        dec[f"{reg}|{grid}"] = cell
    out["decomposition_Q1"] = dec

    # ---- R2 secondary: fixed-demand power gap per cell, unit level and seed level -------------
    gaps = {}
    for reg, grid in CELLS:
        h = seed_mean(rows, "EDF-StaleBeam-MinFeasible", "aggregate_power_w", reg, grid)
        e = seed_mean(rows, "ExactFixedDemandRadio", "aggregate_power_w", reg, grid)
        keys = sorted(set(h) & set(e))
        if not keys:
            gaps[f"{reg}|{grid}"] = None
            continue
        seed_diff = [e[k] - h[k] for k in keys]            # frozen sign: exact minus heuristic
        unit = []
        for r in rows:
            if r["regime"] == reg and r["grid"] == grid and r["status"] == "COMPLETED":
                pass
        # unit-level gap needs the pair within one (seed, warm-up); rebuild explicitly
        idx = {}
        for r in rows:
            if (r["regime"] == reg and r["grid"] == grid and r["status"] == "COMPLETED"
                    and r["comparator"] in ("EDF-StaleBeam-MinFeasible", "ExactFixedDemandRadio")):
                idx.setdefault((r["seed"], r["warmup"]), {})[r["comparator"]] = r
        for k, pair in sorted(idx.items()):
            if len(pair) == 2:
                unit.append(pair["ExactFixedDemandRadio"]["aggregate_power_w"]
                            - pair["EDF-StaleBeam-MinFeasible"]["aggregate_power_w"])
        gaps[f"{reg}|{grid}"] = {
            "sign_convention": "exact fixed-demand reference minus heuristic (W)",
            "n_seeds": len(keys), "seed_level": summary(seed_diff),
            "n_units": len(unit), "unit_level": summary(unit),
            "heuristic_mean_power_w": st.mean([h[k] for k in keys]),
            "exact_mean_power_w": st.mean([e[k] for k in keys]),
        }
    out["power_gap_E1_descriptive"] = gaps

    # ---- R5: runtime, per solver/reference, pooled over cells and per cell -------------------
    rt = {}
    for comp in sorted({r["comparator"] for r in rows}):
        sub = [r for r in rows if r["comparator"] == comp and r.get("runtime_s") is not None]
        us = [r["runtime_s"] * 1e6 for r in sub]
        entry = {"n_solves_recorded": len(us), "microseconds": summary(us),
                 "fraction_under_1ms": (sum(1 for x in us if x < 1000.0) / len(us)) if us else None,
                 "budget_exceeded_rows": sum(1 for r in sub if r.get("budget_exceeded_flag")),
                 "budget_flag_recorded": sum(1 for r in sub
                                             if r.get("budget_exceeded_flag") is not None)}
        nodes = [r["nodes"] for r in sub if r.get("nodes") is not None]
        states = [r["states"] for r in sub if r.get("states") is not None]
        skipped = [r["skipped_entries"] for r in sub if r.get("skipped_entries") is not None]
        if nodes:
            entry["nodes"] = summary(nodes)
        if states:
            entry["states"] = summary(states)
        if skipped:
            entry["skipped_entries_total"] = sum(skipped)
        entry["per_cell_median_us"] = {}
        for reg, grid in CELLS:
            cu = [r["runtime_s"] * 1e6 for r in sub if r["regime"] == reg and r["grid"] == grid]
            entry["per_cell_median_us"][f"{reg}|{grid}"] = st.median(cu) if cu else None
        rt[comp] = entry
    out["runtime_Q5"] = rt

    # ---- coverage: which planned columns have NO data in the final campaign ------------------
    never = []
    for col in ("generated", "deadline_drops", "retx_drops", "overflow_drops",
                "objective_value", "budget_exceeded_flag"):
        if all(r.get(col) is None for r in rows):
            never.append(col)
    out["columns_never_populated"] = sorted(never)
    out["comparators_present"] = sorted({r["comparator"] for r in rows})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="only_print", action="store_true")
    a = ap.parse_args()
    rows = load_rows()
    payload = build(rows)
    blob = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(blob.encode()).hexdigest()
    if a.only_print:
        print(blob)
        print("digest:", digest)
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name in PROTECTED:                       # belt and braces
        assert not (OUT / name).exists(), f"refusing to write near {name}"
    (OUT / "DESCRIPTIVE_SUMMARIES.json").write_text(blob)
    print(f"wrote {OUT / 'DESCRIPTIVE_SUMMARIES.json'}")
    print("digest:", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
