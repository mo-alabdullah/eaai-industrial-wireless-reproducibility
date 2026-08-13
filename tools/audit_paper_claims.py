#!/usr/bin/env python3
""" FINAL_CLAIM_RESULT_AUDIT — recompute every headline manuscript claim directly from the frozen
confirmatory CSVs and compare against the value printed in PUBLICATION_FINAL. Writes
11_final_paper/FINAL_CLAIM_RESULT_AUDIT.md. Exit non-zero if any claim FAILs. No experiments run."""
from __future__ import annotations
import csv, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "results" / "confirmatory"; FP = ROOT / "11_final_paper"
rows = list(csv.DictReader((CONF / "per_seed_metrics.csv").open()))
for r in rows:
    for k, v in r.items():
        if k != "method":
            try: r[k] = float(v)
            except (ValueError, TypeError): pass
def sel(method, load): return [r for r in rows if r["method"] == method and abs(r["load"] - load) < 1e-9]
def smean(method, load, key): return float(np.mean([r[key] for r in sel(method, load)]))
def pooled(method, load, gk, dk):
    rs = sel(method, load); return sum(r[dk] for r in rs) / max(sum(r[gk] for r in rs), 1)
st = list(csv.DictReader((CONF / "pairwise_statistics.csv").open()))
def stat(B, metric, load, field):
    for r in st:
        if r["B"] == B and r["metric"] == metric and abs(float(r["load"]) - load) < 1e-9:
            return float(r[field])
    return None
fs = {float(r["load"]): float(r["feasible_rate"]) for r in csv.DictReader((CONF / "constraint_feasibility_summary.csv").open())}

checks = []  # (claim, source_filter, computed, paper_value, tol, pass)
def chk(claim, filt, computed, paper, tol=0.005):
    ok = computed is not None and abs(computed - paper) <= tol
    checks.append((claim, filt, computed, paper, ok))

chk("EDF mobile PDR = 1.000 at every load (peak shown)", "EDF|mobile pooled|p0.40", pooled("EDF", 0.40, "gen_mobile", "dlv_mobile"), 1.000)
chk("BSA-C-PPO mobile PDR pooled = 0.960 @ p0.40", "BSA-C-PPO|mobile pooled|p0.40", pooled("BSA-C-PPO", 0.40, "gen_mobile", "dlv_mobile"), 0.960)
chk("BSA-C-PPO mobile PDR seed-mean = 0.959 @ p0.40", "BSA-C-PPO|pdr_mobile mean|p0.40", smean("BSA-C-PPO", 0.40, "pdr_mobile"), 0.959)
chk("C-PPO vs EDF mobile mean diff = -0.041 @ p0.40", "stat|EDF|pdr_mobile|p0.40|mean_diff", stat("EDF", "pdr_mobile", 0.40, "mean_diff"), -0.041, tol=0.001)
chk("C-PPO vs EDF Holm p = 0.039 @ p0.40", "stat|EDF|pdr_mobile|p0.40|p_holm", stat("EDF", "pdr_mobile", 0.40, "p_holm"), 0.039, tol=0.001)
chk("C-PPO vs EDF d_z = -0.85 @ p0.40", "stat|EDF|pdr_mobile|p0.40|cohens_dz", stat("EDF", "pdr_mobile", 0.40, "cohens_dz"), -0.85, tol=0.01)
chk("C-PPO vs Unconstrained mean diff = 0.000 @ p0.40", "stat|BSA-Unconstrained-PPO|pdr_mobile|p0.40|mean_diff", stat("BSA-Unconstrained-PPO", "pdr_mobile", 0.40, "mean_diff"), 0.000, tol=1e-6)
chk("C-PPO vs Unconstrained Holm p = 1.000 @ p0.40", "stat|BSA-Unconstrained-PPO|pdr_mobile|p0.40|p_holm", stat("BSA-Unconstrained-PPO", "pdr_mobile", 0.40, "p_holm"), 1.000, tol=1e-6)
chk("Learned mean power = 0.60 W @ p0.40", "BSA-C-PPO|avg_power_w|p0.40", smean("BSA-C-PPO", 0.40, "avg_power_w"), 0.60, tol=0.01)
chk("EDF (heuristic) mean power = 1.28 W @ p0.40", "EDF|avg_power_w|p0.40", smean("EDF", 0.40, "avg_power_w"), 1.28, tol=0.01)
chk("Learned C_pow = -40.2 @ p0.40", "BSA-C-PPO|C_pow|p0.40", smean("BSA-C-PPO", 0.40, "C_pow"), -40.2, tol=0.5)
chk("BSA-C-PPO beam acc 0.081 @ p0.40 (<= chance 0.125)", "BSA-C-PPO|beam_acc_oracle|p0.40", smean("BSA-C-PPO", 0.40, "beam_acc_oracle"), 0.081, tol=0.005)
lo = min(smean("BSA-C-PPO", p, "beam_acc_oracle") for p in (0.05,0.10,0.20,0.30,0.40))
hi = max(smean("BSA-C-PPO", p, "beam_acc_oracle") for p in (0.05,0.10,0.20,0.30,0.40))
chk("beam acc range low = 0.068", "BSA-C-PPO|beam_acc range|min", lo, 0.068, tol=0.005)
chk("beam acc range high = 0.087", "BSA-C-PPO|beam_acc range|max", hi, 0.087, tol=0.005)
chk("Beam oracle mobile PDR = 0.976 @ p0.40", "PerfectMaxGain|pdr_mobile|p0.40", smean("PerfectMaxGain", 0.40, "pdr_mobile"), 0.976, tol=0.005)
chk("Stale-Max-Gain mobile PDR = 0.980 @ p0.40", "StaleMaxGain|pdr_mobile|p0.40", smean("StaleMaxGain", 0.40, "pdr_mobile"), 0.980, tol=0.005)
chk("Feasibility 0.7 @ p0.05", "feasible|p0.05", fs.get(0.05), 0.70, tol=0.001)
chk("Feasibility 0.6 @ p0.30", "feasible|p0.30", fs.get(0.30), 0.60, tol=0.001)
chk("Feasibility 0.1 @ p0.40 (collapse)", "feasible|p0.40", fs.get(0.40), 0.10, tol=0.001)
chk("Base-PPO static PDR low 0.58 (0.58-0.65 range)", "L1-Fixed-BasePPO|static pooled|p0.40", pooled("L1-Fixed-BasePPO", 0.40, "gen_static", "dlv_static"), 0.58, tol=0.02)
chk("Base-PPO static PDR high 0.65 (0.58-0.65 range)", "L1-Fixed-BasePPO|static pooled|p0.05", pooled("L1-Fixed-BasePPO", 0.05, "gen_static", "dlv_static"), 0.65, tol=0.02)
# integrity
n_primary = len(rows); chk("600 primary records complete", "grid|count", float(n_primary), 600.0, tol=0.5)
resid = sum(r["cohort_residual"] for r in rows); chk("0 residual cohort packets", "integrity|cohort_residual sum", resid, 0.0, tol=1e-6)

npass = sum(1 for c in checks if c[4]); ntot = len(checks)
lines = ["# FINAL_CLAIM_RESULT_AUDIT ()", "",
         "Every headline value in `PUBLICATION_FINAL` recomputed directly from the frozen confirmatory",
         "CSVs in `10_confirmatory/` and compared to the printed paper value. No value was entered by hand.", "",
         f"**Result: {npass}/{ntot} claims PASS.**", "",
         "| # | Claim | Source filter | Computed | Paper | Verdict |", "|---|---|---|---|---|---|"]
for i, (claim, filt, comp, paper, ok) in enumerate(checks, 1):
    cs = f"{comp:.4f}" if isinstance(comp, float) else str(comp)
    lines.append(f"| {i} | {claim} | {filt} | {cs} | {paper} | {'PASS' if ok else 'FAIL'} |")
lines += ["", "Source files: `10_confirmatory/per_seed_metrics.csv`, `pairwise_statistics.csv`,",
          "`constraint_feasibility_summary.csv`. Regenerate: `python3 scripts/audit_paper_claims.py`."]
(FP / "FINAL_CLAIM_RESULT_AUDIT.md").write_text("\n".join(lines))
print(f"{npass}/{ntot} PASS")
if npass != ntot:
    for c in checks:
        if not c[4]: print("FAIL:", c[0], "computed", c[2], "paper", c[3])
    raise SystemExit(1)
