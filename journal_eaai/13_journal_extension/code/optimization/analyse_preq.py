#!/usr/bin/env python3
"""Analytic p_req distribution (Stage I0 §1). Deterministic; no simulation."""
import sys,os,numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..')); sys.path.insert(0,os.path.join(HERE,'..','..','..','07_simulation'))
from evaluation import journal_cfg
from m2.env import M2Env
print("| dist | min | p25 | median | p95 | max | frac needing > 0.05 W |")
print("|---|---|---|---|---|---|---|")
for scale in (1.0,1.5,2.0):
    vals=[]
    for seed in range(10001,10009):
        cfg=journal_cfg(0.40,hall_x=300.0*scale,hall_y=150.0*scale)
        env=M2Env(cfg,seed=seed); env.reset(); nw=env.noise_w
        for k in range(env.K):
            bits=cfg.pkt_bits_mobile if env._cls(k) else cfg.pkt_bits_static
            sinr=2**(bits/(cfg.bandwidth_hz*cfg.tau_s))-1
            for n in range(env.N):
                vals.append(nw*sinr/(env.beta[k]*float(env.cur_gain[k,n].max())))
    v=np.array(vals)
    print(f"| ×{scale} | {v.min():.2e} | {np.percentile(v,25):.2e} | {np.median(v):.2e} | "
          f"{np.percentile(v,95):.2e} | {v.max():.2e} | {(v>0.05).mean():.4f} |")
