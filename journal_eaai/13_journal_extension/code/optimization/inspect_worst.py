#!/usr/bin/env python3
"""Manual inspection of a single worst-case slot state (I-E)."""
import sys, os, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..')); sys.path.insert(0,os.path.join(HERE,'..','..','..','07_simulation'))
from evaluation import journal_cfg
from baselines_v2 import ComponentAgent
from m2.env import M2Env, IDLE
from optimization.grids import with_grid
from optimization.capture import freeze
from optimization.radio import solve_exact_radio, cell_cost, p_required

def inspect(regime_dist, age, load, grid, seed, target_slot):
    cfg=journal_cfg(load,t_meas=250,hall_x=300.0*regime_dist,hall_y=150.0*regime_dist,d_csi_slots=age)
    cfg=with_grid(cfg,grid)
    env=M2Env(cfg,700_000_000+seed*100)
    ag=ComponentAgent(env,seed=seed,scheduler="EDF",beam_rule="StaleBest",power_rule="MinFeasible-Stale")
    env.reset(); ag.reset()
    obs=env.begin_slot(); done=False
    while not done:
        if env.t==target_slot:
            st=freeze(env); toks=ag.act(obs)
            ex=solve_exact_radio(st,use_true=False)
            print(f"--- slot {env.t}  grid={grid} dist=x{regime_dist} age={age} seed={seed}")
            print("eligible devices (k, class, queue, HOL slack):")
            for k in range(st.K):
                if st.queue_len[k]:
                    q=env.queues[k]
                    print(f"   d{k} {'mobile' if env._cls(k) else 'static'} q={st.queue_len[k]} "
                          f"slack={(q[0].arrival_slot+env._deadline(k)-1)-env.t} L={st.pkt_bits[k]}b")
            print("\nper-(device,subchannel) minimum feasible power on STALE info (W):")
            hdr="        "+"".join(f"   sc{n}    " for n in range(st.N)); print(hdr)
            for k in range(st.K):
                if not st.queue_len[k]: continue
                cells=""
                for n in range(st.N):
                    b,pi,w=cell_cost(st,k,n)
                    cells+=f" b{b} {w:9.2e}" if pi is not None else "     infeas"
                print(f"   d{k}:{cells}")
            print("\nheuristic action (greedy: best EDF device per subchannel, in subchannel order):")
            hp=0.0
            for n,t in enumerate(toks):
                if t==IDLE: print(f"   sc{n}: IDLE"); continue
                k,b,p=int(t[0][1:]),int(t[1][1:]),int(t[2][1:])
                hp+=st.power_grid[p]
                print(f"   sc{n}: d{k} b{b} p={st.power_grid[p]:.3e} W")
            print(f"   total = {hp:.6f} W, served = {sum(1 for t in toks if t!=IDLE)}")
            print("\nexact aged-CSI optimum:")
            for n,t in enumerate(ex.tokens):
                if t is None: print(f"   sc{n}: IDLE"); continue
                k,b,p=t; print(f"   sc{n}: d{k} b{b} p={st.power_grid[p]:.3e} W")
            print(f"   total = {ex.power_w:.6f} W, served = {ex.served}, nodes = {ex.nodes}")
            print(f"\n   ratio heuristic/exact = {hp/ex.power_w:.1f}x")
            print("   cause: the greedy rule fixes the device for subchannel 0 before seeing that the")
            print("   same device is far cheaper on another subchannel; the exact allocator permutes")
            print("   the device-to-subchannel assignment.")
            return
        toks=ag.act(obs)
        nxt,rp,rb,cost,done,info=env.commit_action(toks)
        obs=nxt if nxt is not None else obs
        if not done: env.begin_slot() if False else None

if __name__=="__main__":
    inspect(2.0,5,0.40,'G2_wide10',10002,180)
