#!/usr/bin/env python3
"""STAGE-I SCIENTIFIC FREEZE task 1 - Holm correction over the declared comparison families.

No simulation. Reads results/stage_ib_joint_final.csv only.

Family definition (declared before correction, not selected after seeing p-values):
  SCHED : the 16 scheduling/temporal comparisons  edfrad -> joint
          = 2 scales x 4 regimes x 2 grids
  RADIO : the 16 radio-allocation comparisons     edf    -> edfrad
  INFO  : the 16 information comparisons          joint  -> oracle

Test: exact paired two-sided sign-flip (randomisation) test on seed-level means, n = 8.
Effect size: Cohen's d_z (mean paired difference / SD of paired differences), reported with the
mean paired difference itself. The exact p-value floor at n = 8 is 2/2^8 = 0.0078125.
"""
from __future__ import annotations
import csv, itertools, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.normpath(os.path.join(HERE, '..', '..', 'results', 'stage_ib_joint_final.csv'))
rows = list(csv.DictReader(open(CSV)))

LBL = {'R1_nominal': 'R1 ×1.0 age1', 'R4_moderate': 'R4 ×1.5 age3',
       'R2_range': 'R2 ×2.0 age1', 'R3_aged': 'R3 ×2.0 age5'}
REG = ('R1_nominal', 'R4_moderate', 'R2_range', 'R3_aged')
GK = ('G0_icame', 'G2_wide10')
SCALES = ('full_K8N4_H3', 'red_K4N2_H6')
P_FLOOR = 2 / 2 ** 8


def F(r, k):
    v = r.get(k, '')
    if v in ('', 'nan', 'None', None):
        return float('nan')
    try:
        return float(v)
    except ValueError:
        return float('nan')


def seed_means(rs, key):
    """collapse the 5 warm-up traces per seed to one seed-level mean"""
    by = {}
    for r in rs:
        v = F(r, key)
        if not math.isnan(v):
            by.setdefault(r['seed'], []).append(v)
    return {s: sum(v) / len(v) for s, v in sorted(by.items())}


def signflip(d):
    n = len(d)
    m = sum(d) / n
    c = sum(1 for s in itertools.product([1, -1], repeat=n)
            if abs(sum(x * y for x, y in zip(s, d)) / n) >= abs(m) - 1e-15)
    return c / 2 ** n


def dz(d):
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    return m / sd if sd > 0 else (0.0 if abs(m) < 1e-15 else float('inf'))


def comparisons(a_key, b_key):
    out = []
    for scale in SCALES:
        for reg in REG:
            for g in GK:
                rs = [r for r in rows if r['scale'] == scale and r['regime'] == reg
                      and r['grid'] == g and r['joint_status'] == 'exact'
                      and r['oracle_status'] == 'exact']
                A = seed_means(rs, a_key); B = seed_means(rs, b_key)
                ks = sorted(set(A) & set(B))
                d = [B[k] - A[k] for k in ks]
                out.append(dict(scale=scale, regime=reg, grid=g, n=len(d),
                                mean_diff=sum(d) / len(d), dz=dz(d), p_raw=signflip(d)))
    return out


def holm(items):
    """Holm-Bonferroni step-down across the declared family; adjusted p is monotone non-decreasing."""
    order = sorted(range(len(items)), key=lambda i: items[i]['p_raw'])
    m = len(items)
    running = 0.0
    for rank, i in enumerate(order):
        adj = (m - rank) * items[i]['p_raw']
        running = max(running, adj)
        items[i]['p_holm'] = min(1.0, running)
        items[i]['rank'] = rank + 1
    return items


def emit(name, a_key, b_key, caption):
    items = holm(comparisons(a_key, b_key))
    print(f"\n### {name} — {caption}\n")
    print(f"Family size m = {len(items)}. Exact sign-flip p-value floor at n = 8 is "
          f"**{P_FLOOR:.7f}**; the Holm threshold for the smallest p in a family of "
          f"{len(items)} is 0.05/{len(items)} = **{0.05/len(items):.6f}**.\n")
    print("| scale | regime | grid | n | mean paired diff | Cohen's d_z | raw p | Holm-adj p | significant after Holm |")
    print("|---|---|---|---|---|---|---|---|---|")
    for it in items:
        sig = "**yes**" if it['p_holm'] <= 0.05 else "no"
        sc = 'full' if it['scale'] == 'full_K8N4_H3' else 'reduced'
        print(f"| {sc} | {LBL[it['regime']]} | {it['grid']} | {it['n']} | {it['mean_diff']:+.3f} | "
              f"{it['dz']:+.2f} | {it['p_raw']:.4f} | {it['p_holm']:.4f} | {sig} |")
    nsig = sum(1 for it in items if it['p_holm'] <= 0.05)
    nraw = sum(1 for it in items if it['p_raw'] <= 0.05)
    verdict = ("**INCONCLUSIVE FOR FAMILY-WISE INFERENCE DUE TO RESOLUTION** — at this n the exact "
               "p-floor exceeds the Holm threshold, so non-significance is NOT evidence of absence"
               if P_FLOOR > 0.05 / len(items) else
               "resolution adequate: non-significance is informative")
    print(f"\nRaw p ≤ 0.05: **{nraw}/{len(items)}**.  Survive Holm: **{nsig}/{len(items)}**.")
    print(f"\nClassification: {verdict}.")
    return items


if __name__ == '__main__':
    print("# Holm-corrected paired comparisons — Stage I-B (development seeds 10001–10008)")
    s = emit("FAMILY SCHED", 'edfrad_dlv', 'joint_dlv',
             "scheduling / temporal effect: EDF + exact radio → exact joint (packets delivered)")
    r = emit("FAMILY RADIO", 'edf_dlv', 'edfrad_dlv',
             "radio-allocation effect: EDF greedy → EDF + exact radio (packets delivered)")
    i = emit("FAMILY INFO", 'joint_dlv', 'oracle_dlv',
             "information effect: exact joint (aged CSI) → exact joint (ORACLE current CSI)")
    print("\n### Structural note on resolution\n")
    print(f"With n = 8 seeds the exact paired sign-flip test cannot return a p-value below "
          f"{P_FLOOR:.7f}. Holm requires the smallest p in a family of 16 to satisfy "
          f"p ≤ 0.05/16 = {0.05/16:.6f}. Since {P_FLOOR:.7f} > {0.05/16:.6f}, **no comparison in a "
          f"16-member family can attain family-wise significance at this sample size, whatever the "
          f"effect**. Any claim of a family-wise significant effect in these families is therefore "
          f"unattainable by construction and would require more seeds, not a different test.")
