#!/usr/bin/env python3
"""Generate the Stage I-A tables from results/stage_i_radio_v2.csv. No value typed by hand."""
from __future__ import annotations
import csv, math, os, statistics as S
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','..','results','stage_i_radio_v2.csv'))
rows=list(csv.DictReader(open(CSV)))
def F(r,k):
    v=r.get(k,''); return float('nan') if v in ('','nan','None') else float(v)
act=[r for r in rows if int(r['h_served'])>0]
REG=('R1_nominal','R4_moderate','R2_range','R3_aged')
LBL={'R1_nominal':'R1 ×1.0 age1','R4_moderate':'R4 ×1.5 age3',
     'R2_range':'R2 ×2.0 age1','R3_aged':'R3 ×2.0 age5'}
GK=('G0_icame','G2_wide10')
def gap(rs,hk,ek):
    g=[]
    for r in rs:
        h,e=F(r,hk),F(r,ek)
        if math.isnan(e) or e<=0 or math.isinf(e): continue
        g.append((h-e)/e)
    g.sort(); n=len(g)
    return dict(n=n,mean=sum(g)/n,med=g[n//2],p95=g[int(.95*(n-1))],mx=g[-1],
                zero=sum(1 for x in g if x<1e-12)/n)

print("### T7 — PURE radio-allocation optimality gap (scheduling held completely fixed)\n")
print("Heuristic `EDF-StaleBeam-MinFeasible` vs the exact aged-CSI allocator serving **the same")
print("packets from the same devices**; only subchannel, beam and power may differ.\n")
print("| regime | grid | slots | mean gap | median | p95 | max | % slots exactly optimal |")
print("|---|---|---|---|---|---|---|---|")
for reg in REG:
    for g_ in GK:
        rs=[r for r in act if r['regime']==reg and r['grid']==g_]
        d=gap(rs,'h_power','x_power')
        print(f"| {LBL[reg]} | {g_} | {d['n']} | {d['mean']*100:.2f}% | {d['med']*100:.2f}% | "
              f"{d['p95']*100:.1f}% | {d['mx']*100:.0f}% | **{d['zero']*100:.1f}%** |")

print("\n### T8 — where the gap comes from: fixed-scheduling vs free-selection exact optima\n")
print("| regime | grid | heuristic W | exact radio (sched fixed) | exact free selection | exact ORACLE free |")
print("|---|---|---|---|---|---|")
for reg in REG:
    for g_ in GK:
        rs=[r for r in act if r['regime']==reg and r['grid']==g_]
        rs=[r for r in rs if not math.isnan(F(r,'x_power')) and not math.isinf(F(r,'x_power'))
            and not math.isnan(F(r,'f_at_h')) and not math.isnan(F(r,'o_at_h'))]
        m=lambda k: sum(F(r,k) for r in rs)/len(rs)
        print(f"| {LBL[reg]} | {g_} | {m('h_power'):.6f} | {m('x_power'):.6f} | {m('f_at_h'):.6f} | {m('o_at_h'):.6f} |")

print("\n### T9 — information loss vs algorithmic loss (same fixed schedule)\n")
print("| regime | grid | algorithmic gap (heur − exact aged)/exact aged | information gap (exact aged − exact oracle)/exact oracle |")
print("|---|---|---|---|")
for reg in REG:
    for g_ in GK:
        rs=[r for r in act if r['regime']==reg and r['grid']==g_]
        rs=[r for r in rs if not math.isnan(F(r,'x_power')) and not math.isinf(F(r,'x_power'))
            and not math.isnan(F(r,'xo_power')) and not math.isinf(F(r,'xo_power')) and F(r,'xo_power')>0]
        h=sum(F(r,'h_power') for r in rs)/len(rs)
        a=sum(F(r,'x_power') for r in rs)/len(rs)
        o=sum(F(r,'xo_power') for r in rs)/len(rs)
        print(f"| {LBL[reg]} | {g_} | {(h-a)/a*100:+.1f}% | {(a-o)/o*100:+.1f}% |")

print("\n### T10 — service level: did any exact optimiser serve more packets than EDF?\n")
print("| regime | grid | EDF heuristic | exact aged (free) | exact ORACLE (free) |")
print("|---|---|---|---|---|")
for reg in REG:
    for g_ in GK:
        rs=[r for r in act if r['regime']==reg and r['grid']==g_]
        m=lambda k: sum(F(r,k) for r in rs)/len(rs)
        print(f"| {LBL[reg]} | {g_} | {m('h_served'):.4f} | {m('f_served'):.4f} | {m('o_served'):.4f} |")

print("\n### T11 — realised success rate of each allocation against the true channel\n")
print("| regime | grid | heuristic | exact radio (aged) | exact ORACLE radio |")
print("|---|---|---|---|---|")
for reg in REG:
    for g_ in GK:
        rs=[r for r in act if r['regime']==reg and r['grid']==g_]
        def rate(ok,srv):
            a=sum(F(r,ok) for r in rs); b=sum(F(r,srv) for r in rs); return a/b if b else float('nan')
        print(f"| {LBL[reg]} | {g_} | {rate('h_real_ok','h_served'):.4f} | "
              f"{rate('x_real_ok','h_served'):.4f} | {rate('xo_real_ok','h_served'):.4f} |")
