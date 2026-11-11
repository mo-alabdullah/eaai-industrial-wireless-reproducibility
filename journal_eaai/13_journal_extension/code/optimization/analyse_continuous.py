#!/usr/bin/env python3
"""Generate the CONTINUOUS_POWER_REFERENCE.md tables from results/continuous_ref.csv."""
from __future__ import annotations
import csv, math, os
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','..','results','continuous_ref.csv'))
rows=list(csv.DictReader(open(CSV)))
def F(r,k):
    v=r.get(k,'')
    if v in ('','nan','None',None): return float('nan')
    try: return float(v)
    except ValueError: return float('nan')
LBL={'R1_nominal':'R1 ×1.0 age1','R4_moderate':'R4 ×1.5 age3','R2_range':'R2 ×2.0 age1','R3_aged':'R3 ×2.0 age5'}
ORD=('R1_nominal','R4_moderate','R2_range','R3_aged')
def ok(r):
    return (not math.isnan(F(r,'e_grid')) and not math.isnan(F(r,'c_cont'))
            and not math.isnan(F(r,'c_ag')) and int(r['served'])>0)

print("### C1 — mean slot power: heuristic, exact-on-grid, and the continuous reference (W)\n")
print("| regime | grid | slots | H_G heuristic | E_G exact on grid | C_AG continuous cost of A_G | C continuous optimum | E_G / C |")
print("|---|---|---|---|---|---|---|---|")
for reg in ORD:
    for g in ('G0_icame','G2_wide10'):
        rs=[r for r in rows if r['regime']==reg and r['grid']==g and ok(r)]
        m=lambda k: sum(F(r,k) for r in rs)/len(rs)
        print(f"| {LBL[reg]} | {g} | {len(rs):,} | {m('h_power'):.6f} | {m('e_grid'):.6f} | "
              f"{m('c_ag'):.6f} | {m('c_cont'):.6f} | **{m('e_grid')/m('c_cont'):.1f}×** |")

print("\n### C2 — exact three-way decomposition of the total gap H_G − C\n")
print("All three terms are non-negative and sum exactly to the total (asserted in")
print("`test_gap_decomposition_is_exact_and_nonnegative`). Shares are of the mean total gap.\n")
print("| regime | grid | total gap (W) | allocation H_G−E_G | rounding E_G−C_AG | assignment distortion C_AG−C | allocation % | quantisation % |")
print("|---|---|---|---|---|---|---|---|")
for reg in ORD:
    for g in ('G0_icame','G2_wide10'):
        rs=[r for r in rows if r['regime']==reg and r['grid']==g and ok(r)]
        tot=sum(F(r,'h_power')-F(r,'c_cont') for r in rs)/len(rs)
        alloc=sum(F(r,'h_power')-F(r,'e_grid') for r in rs)/len(rs)
        rnd=sum(F(r,'e_grid')-F(r,'c_ag') for r in rs)/len(rs)
        dist=sum(F(r,'c_ag')-F(r,'c_cont') for r in rs)/len(rs)
        print(f"| {LBL[reg]} | {g} | {tot:.6f} | {alloc:.6f} | {rnd:.6f} | {dist:.6f} | "
              f"**{100*alloc/tot:.1f}%** | **{100*(rnd+dist)/tot:.1f}%** |")

print("\n### C3 — per-slot gap ratios H_G / C (distribution)\n")
print("| regime | grid | median | mean | p95 | max |")
print("|---|---|---|---|---|---|")
for reg in ORD:
    for g in ('G0_icame','G2_wide10'):
        rs=[r for r in rows if r['regime']==reg and r['grid']==g and ok(r) and F(r,'c_cont')>0]
        v=np.array([F(r,'h_power')/F(r,'c_cont') for r in rs])
        print(f"| {LBL[reg]} | {g} | {np.median(v):.1f}× | {v.mean():.1f}× | "
              f"{np.percentile(v,95):.1f}× | {v.max():,.0f}× |")

print("\n### C4 — feasibility: demands the grid cannot serve but continuous power can\n")
print("| regime | grid | slots with demand | grid infeasible | continuous infeasible |")
print("|---|---|---|---|---|")
for reg in ORD:
    for g in ('G0_icame','G2_wide10'):
        rs=[r for r in rows if r['regime']==reg and r['grid']==g and int(r['served'])>0]
        gi=sum(int(r['grid_infeasible']) for r in rs); ci=sum(int(r['cont_infeasible']) for r in rs)
        print(f"| {LBL[reg]} | {g} | {len(rs):,} | {gi} ({100*gi/len(rs):.2f}%) | {ci} ({100*ci/len(rs):.2f}%) |")
