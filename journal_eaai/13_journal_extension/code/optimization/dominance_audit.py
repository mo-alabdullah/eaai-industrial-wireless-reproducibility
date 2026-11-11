#!/usr/bin/env python3
"""PRE-FREEZE audit: which planned comparisons are STRUCTURALLY DOMINATED by solver construction?

No simulation. Reads the frozen Stage-I CSVs only. A comparison is structurally dominated when one
side is guaranteed weakly better than the other by the construction of the exact solver, so a
null-vs-zero significance test is vacuous.
"""
from __future__ import annotations
import csv, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, '..', '..', 'results'))


def F(r, k):
    v = r.get(k, '')
    if v in ('', 'nan', 'None', None):
        return float('nan')
    try:
        return float(v)
    except ValueError:
        return float('nan')


print("## D1 — H1: exact fixed-demand radio optimum vs heuristic, identical demand")
print("    claim: E_G <= H_G by construction (E_G minimises power over the SAME demand multiset)")
rows = list(csv.DictReader(open(os.path.join(RES, 'stage_i_radio_v2.csv'))))
n = viol = zero = 0
worst = 0.0
for r in rows:
    h, e = F(r, 'h_power'), F(r, 'x_power')
    if math.isnan(h) or math.isnan(e) or math.isinf(e):
        continue
    n += 1
    if e > h + 1e-15:
        viol += 1
    if abs(e - h) < 1e-15:
        zero += 1
    worst = max(worst, e - h)
print(f"    states checked         : {n:,}")
print(f"    violations (E_G > H_G) : {viol}   <-- must be 0")
print(f"    exactly equal (gap = 0): {zero:,} ({100*zero/n:.1f}%)")
print(f"    max (E_G - H_G)        : {worst:.3e}")
print(f"    VERDICT                : {'STRUCTURALLY DOMINATED' if viol == 0 else 'NOT DOMINATED'}\n")

print("## D2 — H3: exact joint ORACLE (current CSI) vs exact joint aged, realised delivery")
print("    claim: ORACLE maximises delivered over ALL feasible action sequences on the true trace,")
print("           so any executed aged plan is one such sequence => oracle_dlv >= joint_dlv")
rows = list(csv.DictReader(open(os.path.join(RES, 'stage_ib_joint_final.csv'))))
ok = [r for r in rows if r.get('joint_status') == 'exact' and r.get('oracle_status') == 'exact']
n = viol = tie = 0
for r in ok:
    a, o = F(r, 'joint_dlv'), F(r, 'oracle_dlv')
    if math.isnan(a) or math.isnan(o):
        continue
    n += 1
    if o < a - 1e-12:
        viol += 1
    if abs(o - a) < 1e-12:
        tie += 1
print(f"    traces checked          : {n:,}")
print(f"    violations (oracle < aged): {viol}   <-- must be 0")
print(f"    ties (oracle == aged)   : {tie:,} ({100*tie/n:.1f}%)")
print(f"    VERDICT                 : {'STRUCTURALLY DOMINATED' if viol == 0 else 'NOT DOMINATED'}\n")

print("## D3 — H2: EDF + exact radio vs exact joint (aged CSI), realised delivery")
print("    claim: NEITHER dominates. The joint controller optimises its BELIEVED (aged) model and is")
print("           then executed truthfully, so it can realise fewer packets than the greedy schedule.")
n = up = down = tie = 0
for r in ok:
    a, b = F(r, 'edfrad_dlv'), F(r, 'joint_dlv')
    if math.isnan(a) or math.isnan(b):
        continue
    n += 1
    if b > a + 1e-12:
        up += 1
    elif b < a - 1e-12:
        down += 1
    else:
        tie += 1
print(f"    traces checked          : {n:,}")
print(f"    joint better            : {up:,} ({100*up/n:.1f}%)")
print(f"    joint WORSE             : {down:,} ({100*down/n:.1f}%)   <-- non-zero => not dominated")
print(f"    tied                    : {tie:,} ({100*tie/n:.1f}%)")
print(f"    VERDICT                 : {'GENUINELY UNCERTAIN (not dominated)' if up and down else 'DOMINATED'}\n")

print("## D4 — H1 power gap: is the heuristic ever strictly worse, and by how much?")
rows2 = list(csv.DictReader(open(os.path.join(RES, 'stage_i_radio_v2.csv'))))
for grid in ('G0_icame', 'G2_wide10'):
    g = []
    for r in rows2:
        if r['grid'] != grid:
            continue
        h, e = F(r, 'h_power'), F(r, 'x_power')
        if math.isnan(h) or math.isnan(e) or math.isinf(e) or e <= 0:
            continue
        g.append((h - e) / e)
    g.sort()
    nz = sum(1 for x in g if x > 1e-12)
    print(f"    {grid}: n={len(g):,}  strictly positive gap in {nz:,} ({100*nz/len(g):.1f}%)  "
          f"mean={sum(g)/len(g)*100:.2f}%  median={g[len(g)//2]*100:.2f}%  max={g[-1]*100:.0f}%")
