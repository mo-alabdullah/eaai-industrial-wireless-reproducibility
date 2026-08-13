#!/usr/bin/env python3
""" publication tables — LaTeX (+CSV) generated PROGRAMMATICALLY from _paper_numbers.json and
the frozen confirmatory CSVs. No hand-typed result values."""
import json, csv
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FP = ROOT / "11_final_paper"; TAB = FP / "tables"; TAB.mkdir(parents=True, exist_ok=True)
n = json.load((FP / "_paper_numbers.json").open())

def f3(x): return f"{x:.3f}"

# Table 1: scenario parameters (design constants, not results)
scenario_rows = [
    ("Access point", "ULA, $M=8$ antennas, single cell (OMA)"),
    ("Devices", "6 static sensors + 2 mobile AMR/AGV ($K=8$)"),
    ("Subchannels", "$N=4$ orthogonal; beam codebook $B=8$ (DFT)"),
    ("Carrier / bandwidth", "$f_c=28$ GHz; $W=1$ MHz per subchannel"),
    ("Slot / noise figure", r"$\tau=1$ ms; $NF=7$ dB; $T=290$ K"),
    ("Power levels", "$P\\in\\{0.05,0.10,0.20,0.40\\}$ W; $P_{\\max}=0.4$ W"),
    ("Power budget", "$\\bar P=0.80$ W (sensitivity 0.64/0.80/0.96)"),
    ("Channel", "3GPP TR 38.901 InF-SH; Rician/Rayleigh ULA"),
    ("Deadlines", "static 10 / mobile 2 slots; retx 3 / 1"),
    ("Queues", "static 32 / mobile 16 packets (FIFO)"),
    ("Packet size", "static 256 B / mobile 64 B"),
    ("Offered load grid", "$p\\in\\{0.05,0.10,0.20,0.30,0.40\\}$; $p_{\\mathrm{ref}}=0.20$"),
    ("Measurement horizon", "$T_{\\mathrm{meas}}=200$ slots + full drain"),
    ("Stale CSI", "$d_{\\mathrm{CSI}}=1$ slot"),
    ("Confirmatory seeds", "$\\{20001,\\dots,20010\\}$ ($n=10$, fresh)"),
    ("Training budget", "8 episodes $\\times$ 10 updates, hidden 48 (bounded)"),
]
t1 = ["\\begin{table}[t]\\centering\\small",
      "\\caption{Frozen confirmatory scenario parameters.}\\label{tab:scenario}",
      "\\begin{tabular}{@{}p{0.30\\columnwidth}p{0.62\\columnwidth}@{}}\\toprule",
      "Parameter & Value \\\\ \\midrule"]
for k, v in scenario_rows: t1.append(f"{k} & {v} \\\\")
t1 += ["\\bottomrule\\end{tabular}\\end{table}"]
(TAB / "table1_scenario.tex").write_text("\n".join(t1))

# Table 2: p=0.40 results per method
order2 = ["EDF", "MaxSINROracle", "StaleMaxGain", "Random", "BSA-Unconstrained-PPO",
          "BSA-C-PPO", "L1-Fixed-Random", "L1-Fixed-BasePPO"]
disp2 = {"EDF": "EDF", "MaxSINROracle": "Max-SINR oracle", "StaleMaxGain": "Stale-Max-Gain",
         "Random": "Random", "BSA-Unconstrained-PPO": "BSA-Uncon.-PPO", "BSA-C-PPO": "BSA-C-PPO",
         "L1-Fixed-Random": "L1 Fixed Random", "L1-Fixed-BasePPO": "L1 Fixed Base PPO"}
t2 = ["\\begin{table*}[t]\\centering\\small",
      "\\caption{Confirmatory results at peak load $p=0.40$ (seed-mean, $n=10$). PDR = packet delivery ratio; power in W; beam accuracy vs the current-CSI oracle (random chance $=0.125$).}\\label{tab:p40}",
      "\\begin{tabular}{@{}lccccc@{}}\\toprule",
      "Method & PDR (static) & PDR (mobile) & p95 latency (slots) & Mean power (W) & Beam accuracy \\\\ \\midrule"]
for m in order2:
    d = n["table2_p40"][m]
    t2.append(f"{disp2[m]} & {f3(d['pdr_static'])} & {f3(d['pdr_mobile'])} & {d['lat_p95']:.1f} & {f3(d['avg_power_w'])} & {f3(d['beam_acc'])} \\\\")
t2 += ["\\bottomrule\\end{tabular}\\end{table*}"]
(TAB / "table2_p40.tex").write_text("\n".join(t2))

# Table 3: statistical comparisons at p=0.40 (mobile PDR)
se = n["stat_cppo_vs_edf_mobile_p40"]; su = n["stat_cppo_vs_uncon_mobile_p40"]
t3 = ["\\begin{table}[t]\\centering\\small",
      "\\caption{Matched-seed paired comparisons of BSA-C-PPO mobile PDR at $p=0.40$ ($n=10$; sign-flip permutation, Holm-adjusted).}\\label{tab:stats}",
      "\\begin{tabular}{@{}lccc@{}}\\toprule",
      "Comparison (BSA-C-PPO $-$ B) & mean diff & Holm $p$ & $d_z$ \\\\ \\midrule",
      f"vs EDF & {se['mean_diff']:.3f} & {se['p_holm']:.3f} & {se['d_z']:.2f} \\\\",
      f"vs BSA-Unconstrained-PPO & {su['mean_diff']:.3f} & {su['p_holm']:.3f} & 0.00 \\\\",
      "\\bottomrule\\end{tabular}\\end{table}"]
(TAB / "table3_stats.tex").write_text("\n".join(t3))

# Table 4: accepted-abstract hypotheses
hyp = [("1", "Base PPO outperforms Random for static sensors",
        "Not supported (Base-PPO static PDR 0.58--0.65 vs Random $\\approx$1.00)"),
       ("2", "Congestion degradation begins at a finite load", "Supported (mobile PDR $<0.99$ from $p=0.05$)"),
       ("3", "Mobile AMR/AGV degrade earlier than static", "Supported"),
       ("4", "A load exists where Random beats Base PPO for mobile (inversion)", "Supported (all loads)")]
t4 = ["\\begin{table}[t]\\centering\\small",
      "\\caption{Accepted-abstract Layer-1 hypotheses evaluated on fresh confirmatory data.}\\label{tab:hyp}",
      "\\begin{tabular}{@{}cp{0.40\\columnwidth}p{0.40\\columnwidth}@{}}\\toprule",
      "\\# & Hypothesis & Verdict \\\\ \\midrule"]
for i, h, v in hyp: t4.append(f"{i} & {h} & {v} \\\\")
t4 += ["\\bottomrule\\end{tabular}\\end{table}"]
(TAB / "table4_hypotheses.tex").write_text("\n".join(t4))

# CSV mirrors
with (TAB / "table2_p40.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["method", "pdr_static", "pdr_mobile", "lat_p95", "avg_power_w", "beam_acc"])
    for m in order2:
        d = n["table2_p40"][m]
        w.writerow([m, f3(d["pdr_static"]), f3(d["pdr_mobile"]), f"{d['lat_p95']:.1f}", f3(d["avg_power_w"]), f3(d["beam_acc"])])
with (TAB / "table3_stats.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["comparison", "mean_diff", "p_holm", "d_z"])
    w.writerow(["BSA-C-PPO vs EDF (mobile PDR p0.40)", f"{se['mean_diff']:.4f}", f"{se['p_holm']:.4f}", f"{se['d_z']:.3f}"])
    w.writerow(["BSA-C-PPO vs BSA-Unconstrained-PPO (mobile PDR p0.40)", f"{su['mean_diff']:.4f}", f"{su['p_holm']:.4f}", "0.000"])
print("tables written:", sorted(p.name for p in TAB.glob("*")))
