#!/usr/bin/env python3
"""Regenerate the beam-share table of ORACLE_HEADROOM_DECOMPOSITION.md §4 from raw results.
Shares are computed from unrounded seed-level means; no value is typed by hand.
Usage: python3 make_headroom_shares.py
"""
import csv, os
HERE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.normpath(os.path.join(HERE,'..','results','headroom.csv'))
rows=list(csv.DictReader(open(CSV)))
def mean(beam,power,age,metric):
    v=[float(r[metric]) for r in rows
       if r['beam_rule']==beam and r['power_rule']==power and int(r['d_csi'])==age]
    return sum(v)/len(v)
print("| d_CSI | PDR share | retx share |")
print("|---|---|---|")
for age in (1,3,5):
    out=[]
    for m in ('pdr_mobile','drop_retx'):
        stale=mean('StaleBest','MinFeasible-Stale',age,m)
        beam =mean('OracleBest','MinFeasible-Stale',age,m)
        total=mean('OracleBest','MinFeasible-Oracle',age,m)
        out.append(100.0*(beam-stale)/(total-stale))
    print(f"| {age} | {out[0]:.1f}% | {out[1]:.1f}% |")
