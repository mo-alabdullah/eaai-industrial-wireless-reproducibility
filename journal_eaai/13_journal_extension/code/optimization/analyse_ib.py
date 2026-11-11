#!/usr/bin/env python3
"""Generate the Stage I-B tables from results/stage_ib_joint_final.csv (Stage-I-B merged with the
Stage-I-CLOSEOUT re-runs). No value typed by hand."""
from __future__ import annotations
import csv, itertools, math, os
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','..','results','stage_ib_joint_final.csv'))
rows=list(csv.DictReader(open(CSV)))
def F(r,k):
    v=r.get(k,'')
    if v in ('','nan','None',None): return float('nan')
    try: return float(v)
    except (TypeError,ValueError): return float('nan')
LBL={'R1_nominal':'R1 ×1.0 age1','R4_moderate':'R4 ×1.5 age3','R2_range':'R2 ×2.0 age1','R3_aged':'R3 ×2.0 age5'}
REG=('R1_nominal','R4_moderate','R2_range','R3_aged'); GK=('G0_icame','G2_wide10')
def paired(rs,ka,kb):
    d=[F(r,kb)-F(r,ka) for r in rs if not math.isnan(F(r,ka)) and not math.isnan(F(r,kb))]
    n=len(d); m=sum(d)/n
    if n>22: return m,float('nan'),n
    c=sum(1 for s in itertools.product([1,-1],repeat=n)
          if abs(sum(x*y for x,y in zip(s,d))/n)>=abs(m)-1e-15)
    return m,c/2**n,n
def bysd(rs):
    """collapse the 5 warmup traces per seed to one seed-level mean, for paired seed-level stats"""
    out={}
    for r in rs: out.setdefault(r['seed'],[]).append(r)
    agg=[]
    for s,g in sorted(out.items()):
        a={'seed':s}
        for k in g[0]:
            vs=[F(x,k) for x in g if not math.isnan(F(x,k))]
            if vs: a[k]=sum(vs)/len(vs)
        agg.append(a)
    return agg

for scale,title in (('full_K8N4_H3','full scale K = 8, N = 4, H = 3'),
                    ('red_K4N2_H6','reduced scale K = 4, N = 2, H = 6')):
    print(f"\n### Stage I-B — {title}\n")
    print("Packets delivered over the horizon (mean per trace) and cumulative transmit power (W).\n")
    print("| regime | grid | EDF greedy | EDF + exact radio | exact joint (aged) | exact joint ORACLE |")
    print("|---|---|---|---|---|---|")
    for reg in REG:
        for g in GK:
            rs=[r for r in rows if r['scale']==scale and r['regime']==reg and r['grid']==g]
            if not rs: continue
            ok=[r for r in rs if r.get('joint_status')=='exact' and r.get('oracle_status')=='exact']
            nex=len(rs)-len(ok)
            m=lambda k: (sum(F(r,k) for r in ok)/len(ok)) if ok else float('nan')
            me=lambda k: sum(F(r,k) for r in rs)/len(rs)
            if not ok:
                print(f"| {LBL[reg]} | {g} | {me('edf_dlv'):.2f} / {me('edf_pw'):.5f} | "
                      f"{me('edfrad_dlv'):.2f} / {me('edfrad_pw'):.5f} | "
                      f"BARRIER ({nex}/{len(rs)}) | BARRIER |")
                continue
            print(f"| {LBL[reg]} | {g} | {m('edf_dlv'):.2f} / {m('edf_pw'):.5f} | "
                  f"{m('edfrad_dlv'):.2f} / {m('edfrad_pw'):.5f} | "
                  f"{m('joint_dlv'):.2f} / {m('joint_pw'):.5f} | "
                  f"{m('oracle_dlv'):.2f} / {m('oracle_pw'):.5f} |"
                  + (f"  <!-- {nex}/{len(rs)} traces hit the enumeration budget and are excluded -->" if nex else ""))
    print(f"\n**Delivery decomposition, {title}** (paired over 8 seeds, seed-level means):\n")
    print("| regime | grid | radio-allocation gain (EDF→+exact radio) | p | scheduling/temporal gain (→exact joint) | p | information gain (→ORACLE) | p |")
    print("|---|---|---|---|---|---|---|---|")
    for reg in REG:
        for g in GK:
            rs=bysd([r for r in rows if r['scale']==scale and r['regime']==reg and r['grid']==g
                     and r.get('joint_status')=='exact' and r.get('oracle_status')=='exact'])
            if len(rs)<4:
                print(f"| {LBL[reg]} | {g} | — enumeration budget exceeded — | | | | | |"); continue
            a=paired(rs,'edf_dlv','edfrad_dlv'); b=paired(rs,'edfrad_dlv','joint_dlv'); c=paired(rs,'joint_dlv','oracle_dlv')
            f=lambda t: f"{t[0]:+.3f} | {t[1]:.4f}"
            print(f"| {LBL[reg]} | {g} | {f(a)} | {f(b)} | {f(c)} |")

print("\n### Stage I-B — exact-solver cost (I-I)\n")
print("| scale | grid | mean nodes | max nodes | mean states | mean CPU s | max CPU s | budget exceeded |")
print("|---|---|---|---|---|---|---|---|")
for scale in ('full_K8N4_H3','red_K4N2_H6'):
    for g in GK:
        rs=[r for r in rows if r['scale']==scale and r['grid']==g]
        if not rs: continue
        nd=[F(r,'joint_nodes') for r in rs]; cp=[F(r,'joint_cpu') for r in rs]
        st=[F(r,'joint_states') for r in rs]
        nd=[x for x in nd if not math.isnan(x)]; cp=[x for x in cp if not math.isnan(x)]
        st=[x for x in st if not math.isnan(x)]
        be=sum(1 for r in rs if r.get('joint_status')!='exact')
        print(f"| {scale} | {g} | {sum(nd)/len(nd):,.0f} | {max(nd):,.0f} | {sum(st)/len(st):,.0f} | "
              f"{sum(cp)/len(cp):.2f} | {max(cp):.2f} | {be}/{len(rs)} |")
