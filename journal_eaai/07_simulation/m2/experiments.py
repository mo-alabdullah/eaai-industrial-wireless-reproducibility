#!/usr/bin/env python3
"""Experiment orchestration (M2, r35): Layer-1 / Layer-2 method registry, paired-seed runners,
pilot + full campaign + ablations. Produces long-form per-(method, seed, load) metric records.

Pairing: every method at a given (seed, load) is evaluated on the SAME held-out scenario seed
`eval_seed(seed)`, disjoint from the PPO training rollout seed namespace (no train/eval leakage).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from .config import ScenarioConfig, campaign_config
from .env import M2Env
from .baselines import (RandomAgent, RoundRobinAgent, EDFAgent, StaleMaxGainAgent,
                        MaxSINROracleAgent, PerfectMaxGainAgent, LastBeamAgent,
                        Layer1RandomAgent, run_episode)
from .agents_ppo import PPOAgent

EVAL_NAMESPACE = 900_000_000


def eval_seed(seed: int) -> int:
    return EVAL_NAMESPACE + seed


# (name, layer, kind, spec)   kind: "heuristic" -> AgentCls ; "ppo" -> (mode, layer1)
LAYER1_METHODS = [
    ("L1-Fixed-Random", 1, "heuristic", Layer1RandomAgent),
    ("L1-Fixed-BasePPO", 1, "ppo", ("unconstrained", True)),
]
LAYER2_METHODS = [
    ("Random", 2, "heuristic", RandomAgent),
    ("RoundRobin", 2, "heuristic", RoundRobinAgent),
    ("EDF", 2, "heuristic", EDFAgent),
    ("StaleMaxGain", 2, "heuristic", StaleMaxGainAgent),
    ("MaxSINROracle", 2, "heuristic", MaxSINROracleAgent),
    ("PerfectMaxGain", 2, "heuristic", PerfectMaxGainAgent),
    ("LastBeam", 2, "heuristic", LastBeamAgent),
    ("BSA-Unconstrained-PPO", 2, "ppo", ("unconstrained", False)),
    ("BSA-Penalty-PPO", 2, "ppo", ("penalty", False)),
    ("BSA-C-PPO", 2, "ppo", ("lagrangian", False)),
]
ALL_METHODS = LAYER1_METHODS + LAYER2_METHODS

# canonical display order (used everywhere)
METHOD_ORDER = [m[0] for m in ALL_METHODS]


def _eval_ppo(ag: PPOAgent, cfg: ScenarioConfig, seed: int, layer1: bool):
    env = M2Env(cfg, eval_seed(seed), layer1_fixed=layer1)
    env.reset(); obs = env.begin_slot(); done = False
    while not done:
        prefix, *_ = ag.act_slot(env, obs, greedy=True)
        nxt, rp, rb, cost, done, info = env.commit_action(prefix)
        obs = nxt if nxt is not None else obs
    return env.episode_metrics()


def run_method(spec, cfg: ScenarioConfig, seed: int):
    """Return (metrics_dict, extra) for one (method, seed). extra carries PPO training curves."""
    name, layer, kind, payload = spec
    if kind == "heuristic":
        env = M2Env(cfg, eval_seed(seed), layer1_fixed=(layer == 1))
        m = run_episode(env, payload(env, 0))
        return m, None
    mode, layer1 = payload
    ag = PPOAgent(cfg, base_seed=seed, mode=mode, layer1=layer1)
    ag.train()
    m = _eval_ppo(ag, cfg, seed, layer1)
    extra = {"history": ag.history, "multipliers_final": ag.multipliers.tolist()}
    return m, extra


def run_campaign(loads: List[float], seeds: List[int], methods=ALL_METHODS,
                 cfg_factory=campaign_config, progress=None):
    """Return (records, curves). records: long-form list of dicts; curves: PPO training histories."""
    records: List[Dict] = []
    curves: List[Dict] = []
    for p in loads:
        cfg = cfg_factory(p)
        for spec in methods:
            name, layer = spec[0], spec[1]
            for s in seeds:
                m, extra = run_method(spec, cfg, s)
                rec = {"method": name, "layer": layer, "seed": s, "load": p}
                rec.update({k: v for k, v in m.items() if not k.startswith("_")})
                records.append(rec)
                if extra is not None:
                    curves.append({"method": name, "seed": s, "load": p,
                                   "reward": extra["history"]["reward"],
                                   "kl": extra["history"]["kl"],
                                   "entropy": extra["history"]["entropy"],
                                   "clipfrac": extra["history"]["clipfrac"],
                                   "multipliers": [mm.tolist() for mm in extra["history"]["multipliers"]],
                                   "multipliers_final": extra["multipliers_final"]})
                if progress:
                    progress(name, p, s)
    return records, curves


def run_pilot(seeds=(0, 1, 2), loads=(0.05, 0.20, 0.40)):
    """Small end-to-end validation across Layer-1 + key Layer-2 + full PPO family."""
    key = [m for m in ALL_METHODS if m[0] in
           ("L1-Fixed-Random", "L1-Fixed-BasePPO", "Random", "EDF", "MaxSINROracle",
            "BSA-Unconstrained-PPO", "BSA-Penalty-PPO", "BSA-C-PPO")]
    return run_campaign(list(loads), list(seeds), methods=key)
