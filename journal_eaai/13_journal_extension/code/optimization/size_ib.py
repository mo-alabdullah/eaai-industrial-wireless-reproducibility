#!/usr/bin/env python3
"""I-B sizing study: choose the largest instance for which exhaustive optimisation is verifiable."""
import sys, os, dataclasses, time, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..')); sys.path.insert(0,os.path.join(HERE,'..','..','..','07_simulation'))
from evaluation import journal_cfg
from optimization.grids import with_grid
from optimization.joint import record_trace, size_instance, solve_exact_joint

def small_cfg(K_static, K_mobile, N, grid, load=0.40, dist=2.0, age=1, B=None):
    cfg=journal_cfg(load,t_meas=400,hall_x=300.0*dist,hall_y=150.0*dist,d_csi_slots=age)
    cfg=with_grid(cfg,grid)
    kw=dict(n_static=K_static,n_mobile=K_mobile,n_subchannels=N,
            n_max_static=min(cfg.n_max_static,N),n_max_mobile=min(cfg.n_max_mobile,N))
    if B is not None: kw['codebook_size']=B
    return dataclasses.replace(cfg,**kw)

print(f"{'K':>2} {'N':>2} {'B':>2} {'P':>3} {'H':>2} | {'raw tokens/slot':>16} {'reduced':>8} {'feas mean':>10} {'naive seq':>12} | {'nodes':>9} {'states':>7} {'CPU s':>7}")
for (Ks,Km,N,B,grid,H) in [(2,1,2,8,'G0_icame',3),(2,1,2,8,'G0_icame',4),(2,1,2,8,'G2_wide10',4),
                           (3,1,2,8,'G2_wide10',4),(2,1,2,8,'G2_wide10',5),
                           (3,1,2,8,'G2_wide10',5),(2,2,3,8,'G2_wide10',4),(3,1,3,8,'G2_wide10',4)]:
    cfg=small_cfg(Ks,Km,N,grid)
    tr=record_trace(cfg,seed=700_000_000+10001*100,H=H)
    sz=size_instance(tr)
    t=time.perf_counter(); dl,pw,nodes,states=solve_exact_joint(tr,use_true=False); cpu=time.perf_counter()-t
    print(f"{Ks+Km:>2} {N:>2} {B:>2} {len(tr.power_grid):>3} {H:>2} | {sz['raw_tokens_per_slot']:>16,} "
          f"{sz['reduced_assignments_per_slot']:>8,} {sz['feasible_per_slot_mean']:>10.1f} "
          f"{sz['naive_sequences']:>12,} | {nodes:>9,} {states:>7,} {cpu:>7.2f}")
