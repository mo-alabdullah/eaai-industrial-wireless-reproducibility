#!/usr/bin/env python3
"""Generate every table in POWER_GRID_SENSITIVITY.md from results/stage_i0.csv.
No value is typed by hand. Usage: python3 analyse_i0.py"""
from __future__ import annotations
import csv, itertools, math, os, sys
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','..','results','stage_i0.csv'))
rows=list(csv.DictReader(open(CSV)))
G2=[1e-5,3.1623e-5,1e-4,3.1623e-4,1e-3,3.1623e-3,1e-2,3.1623e-2,1e-1,4e-1]
def fv(r,k):
    v=r.get(k,'');  return float(v) if v not in ('','None') else float('nan')
def sel(**kw): return [r for r in rows if all(str(r[k])==str(v) for k,v in kw.items())]
def mean(rs,k):
    v=[fv(r,k) for r in rs if not math.isnan(fv(r,k))]; return sum(v)/len(v) if v else float('nan')
def paired(a,b,k):
    da={r['seed']:fv(r,k) for r in a}; db={r['seed']:fv(r,k) for r in b}
    ks=sorted(set(da)&set(db)); d=[db[s]-da[s] for s in ks]; n=len(d); m=sum(d)/n
    c=sum(1 for s in itertools.product([1,-1],repeat=n)
          if abs(sum(x*y for x,y in zip(s,d))/n)>=abs(m)-1e-15)
    return m,c/2**n,n
GK=('G0_icame','G1_ext7','G2_wide10')

print("### T1 — mean transmit power per active transmission, `EDF-StaleBest-MinFeasible`\n")
print("| dist | load | d_CSI | G0 (0.05 W floor) | G1 (0.005 W) | G2 (1e-5 W) | G0/G2 |")
print("|---|---|---|---|---|---|---|")
for dist in ('1.0','1.5','2.0'):
    for load in ('0.2','0.4'):
        for age in ('1','5'):
            v={g:mean(sel(grid=g,beam_rule='StaleBest',power_rule='MinFeasible-Stale',
                          dist_scale=dist,load=load,d_csi=age),'mean_tx_power_w_grid') for g in GK}
            print(f"| ×{dist} | {load} | {age} | {v['G0_icame']:.6f} | {v['G1_ext7']:.6f} | "
                  f"{v['G2_wide10']:.6f} | **{v['G0_icame']/v['G2_wide10']:.1f}×** |")

print("\n### T2 — fraction of transmissions at the grid floor (`MinFeasible`, load 0.40, d_CSI 1)\n")
print("| grid | floor | ×1.0 | ×1.5 | ×2.0 |")
print("|---|---|---|---|---|")
for g,fl in zip(GK,('0.05 W','0.005 W','1e-5 W')):
    c=[mean(sel(grid=g,beam_rule='StaleBest',power_rule='MinFeasible-Stale',
                dist_scale=d,load='0.4',d_csi='1'),'frac_at_floor') for d in ('1.0','1.5','2.0')]
    print(f"| {g} | {fl} | {c[0]:.4f} | {c[1]:.4f} | {c[2]:.4f} |")

print("\n### T3 — G2 selected-power histogram (`StaleBest-MinFeasible`, load 0.40, d_CSI 1)\n")
print("| dist | "+" | ".join(f"{w:.1e} W" for w in G2)+" |")
print("|---"*(len(G2)+1)+"|")
for dist in ('1.0','1.5','2.0'):
    rs=sel(grid='G2_wide10',beam_rule='StaleBest',power_rule='MinFeasible-Stale',
           dist_scale=dist,load='0.4',d_csi='1')
    print(f"| ×{dist} | "+" | ".join(f"{mean(rs,f'frac_lvl{i}_{w:g}W'):.4f}" for i,w in enumerate(G2))+" |")

print("\n### T4 — realised reliability under each grid (`StaleBest-MinFeasible`, load 0.40)\n")
print("| dist | d_CSI | grid | PDR mobile | PDR static | retx drops | mean power (W) |")
print("|---|---|---|---|---|---|---|")
for dist in ('1.0','2.0'):
    for age in ('1','5'):
        for g in GK:
            rs=sel(grid=g,beam_rule='StaleBest',power_rule='MinFeasible-Stale',
                   dist_scale=dist,load='0.4',d_csi=age)
            print(f"| ×{dist} | {age} | {g} | {mean(rs,'pdr_mobile'):.4f} | {mean(rs,'pdr_static'):.4f} "
                  f"| {mean(rs,'drop_retx'):.1f} | {mean(rs,'mean_tx_power_w_grid'):.6f} |")

print("\n### T5 — beam-information gap `OracleBest − StaleBest` under `MinFeasible`, by grid (load 0.40)\n")
print("| grid | dist | d_CSI | stale PDR_m | oracle PDR_m | ΔPDR_m | p | stale retx | oracle retx |")
print("|---|---|---|---|---|---|---|---|---|")
for g in GK:
    for dist in ('1.0','2.0'):
        for age in ('1','5'):
            a=sel(grid=g,beam_rule='StaleBest',power_rule='MinFeasible-Stale',dist_scale=dist,load='0.4',d_csi=age)
            b=sel(grid=g,beam_rule='OracleBest',power_rule='MinFeasible-Stale',dist_scale=dist,load='0.4',d_csi=age)
            m,p,n=paired(a,b,'pdr_mobile')
            star='**' if p<=0.05 else ''
            print(f"| {g} | ×{dist} | {age} | {mean(a,'pdr_mobile'):.4f} | {mean(b,'pdr_mobile'):.4f} "
                  f"| {star}{m:+.4f}{star} | {p:.4f} | {mean(a,'drop_retx'):.1f} | {mean(b,'drop_retx'):.1f} |")

print("\n### T6 — paired G0→G2 change, `StaleBest-MinFeasible`, load 0.40, d_CSI 1 (n = 8)\n")
print("| dist | Δ mean power (W) | p | Δ PDR mobile | p |")
print("|---|---|---|---|---|")
for dist in ('1.0','1.5','2.0'):
    a=sel(grid='G0_icame',beam_rule='StaleBest',power_rule='MinFeasible-Stale',dist_scale=dist,load='0.4',d_csi='1')
    b=sel(grid='G2_wide10',beam_rule='StaleBest',power_rule='MinFeasible-Stale',dist_scale=dist,load='0.4',d_csi='1')
    mp,pp,_=paired(a,b,'mean_tx_power_w_grid'); md,pd,_=paired(a,b,'pdr_mobile')
    print(f"| ×{dist} | {mp:+.6f} | {pp:.4f} | {md:+.4f} | {pd:.4f} |")
