#!/usr/bin/env python3
"""Generate the EXACT_SOLVER_LATENCY.md tables from results/solver_latency.csv."""
from __future__ import annotations
import csv, math, os
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','..','results','solver_latency.csv'))
rows=list(csv.DictReader(open(CSV)))
def F(r,k):
    v=r.get(k,'')
    if v in ('','nan','None'): return float('nan')
    try: return float(v)
    except ValueError: return float('nan')
LBL={'R1_nominal':'nominal ×1.0 (age 1)','R4_moderate':'moderate ×1.5 (age 3)',
     'R2_range':'extended ×2.0 (age 1)','R3_aged':'extended ×2.0 (age 5)'}
ORD=('R1_nominal','R4_moderate','R2_range','R3_aged')

def stats(vals):
    v=np.array([x for x in vals if not math.isnan(x)])*1e6      # microseconds
    return dict(n=len(v),mean=v.mean(),med=np.median(v),p90=np.percentile(v,90),
                p95=np.percentile(v,95),p99=np.percentile(v,99),mx=v.max(),
                sub_ms=float((v<1000).mean()))

def table(title,col,groupfn,order):
    print(f"\n### {title}\n")
    print("| group | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for g in order:
        vs=[F(r,col) for r in rows if groupfn(r)==g]
        if not vs: continue
        s=stats(vs)
        print(f"| {g} | {s['n']:,} | {s['mean']:.0f} | {s['med']:.0f} | {s['p90']:.0f} | "
              f"{s['p95']:.0f} | {s['p99']:.0f} | {s['mx']:,.0f} | {100*s['sub_ms']:.2f}% |")

print("## Free-selection exact radio solve  (`solve_exact_radio`, (K+1)^N enumeration)")
table("By power grid","lat_free_s",lambda r:r['grid'],('G0_icame','G2_wide10'))
table("By regime (both grids pooled)","lat_free_s",lambda r:LBL[r['regime']],[LBL[x] for x in ORD])
print("\n### By grid × regime\n")
print("| grid | regime | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |")
print("|---|---|---|---|---|---|---|---|---|---|")
for gk in ('G0_icame','G2_wide10'):
    for reg in ORD:
        vs=[F(r,'lat_free_s') for r in rows if r['grid']==gk and r['regime']==reg]
        s=stats(vs)
        print(f"| {gk} | {LBL[reg]} | {s['n']:,} | {s['mean']:.0f} | {s['med']:.0f} | {s['p90']:.0f} | "
              f"{s['p95']:.0f} | {s['p99']:.0f} | {s['mx']:,.0f} | {100*s['sub_ms']:.2f}% |")

print("\n## Fixed-demand exact radio solve  (`solve_exact_radio_fixed_demand`, permutation enumeration)")
table("By power grid","lat_fixed_s",lambda r:r['grid'],('G0_icame','G2_wide10'))
table("By regime","lat_fixed_s",lambda r:LBL[r['regime']],[LBL[x] for x in ORD])

print("\n## Overall\n")
for col,name in (('lat_free_s','free selection'),('lat_fixed_s','fixed demand')):
    s=stats([F(r,col) for r in rows])
    print(f"- **{name}**: n = {s['n']:,}; mean {s['mean']:.0f} µs, median {s['med']:.0f} µs, "
          f"p90 {s['p90']:.0f} µs, p95 {s['p95']:.0f} µs, p99 {s['p99']:.0f} µs, max {s['mx']:,.0f} µs; "
          f"**{100*s['sub_ms']:.2f}% below 1 ms**.")

print("\n### Latency vs number of simultaneously eligible devices (free selection)\n")
print("| eligible devices | n | median µs | p95 µs | max µs | % < 1 ms |")
print("|---|---|---|---|---|---|")
for e in range(0,9):
    vs=[F(r,'lat_free_s') for r in rows if int(r['n_elig'])==e]
    if len(vs)<20: continue
    s=stats(vs)
    print(f"| {e} | {s['n']:,} | {s['med']:.0f} | {s['p95']:.0f} | {s['mx']:,.0f} | {100*s['sub_ms']:.2f}% |")
