#!/usr/bin/env python3
"""Non-learning baselines + Layer separation (M2, r35 repaired).

All baselines drive the env through begin_slot()/commit_action() and select only tokens the env's
canonical conditional mask reports feasible (the env re-validates and RAISES on any infeasible
action). Layer-1 agents are FIXED-RADIO: they only choose scheduling; beam and power are held at
the documented fixed configuration (beam index 0, max power) identically across Layer-1 methods.

Layer 2 (extended, full beam/spectrum/power action):
  Random, RoundRobin, EDF, StaleMaxGain (stale Max-SINR/Gain), MaxSINROracle (current-CSI oracle),
  PerfectMaxGain (perfect current-CSI beam oracle), LastBeam.
"""
from __future__ import annotations

from typing import List

import numpy as np

from .env import IDLE, M2Env


# ------------------------------------------------------------- Layer 2 heuristics
class BaselineAgent:
    name = "base"
    layer = 2

    def __init__(self, env: M2Env, seed: int = 0):
        self.env = env
        self.rng = np.random.default_rng(seed)
        self.last_beam = {}

    def reset(self):
        self.last_beam = {}

    def _score(self, n, k, b, p):
        raise NotImplementedError

    def act(self, base_obs) -> List:
        env = self.env
        prefix, tokens = [], []
        for n in range(1, env.N + 1):
            feas = env.feasible_tokens(prefix, n)
            non_idle = [t for t in feas if t != IDLE]
            if not non_idle:
                choice = IDLE
            else:
                choice = max(non_idle, key=lambda t: self._score(n, int(t[0][1:]),
                                                                 int(t[1][1:]), int(t[2][1:])))
            tokens.append(choice); prefix.append(choice)
            if choice != IDLE:
                self.last_beam[int(choice[0][1:])] = int(choice[1][1:])
        return tokens


class RandomAgent(BaselineAgent):
    name = "Random"

    def act(self, base_obs):
        env = self.env
        prefix, tokens = [], []
        for n in range(1, env.N + 1):
            feas = sorted(env.feasible_tokens(prefix, n), key=lambda t: (t != IDLE, str(t)))
            choice = feas[int(self.rng.integers(0, len(feas)))]
            tokens.append(choice); prefix.append(choice)
        return tokens


class RoundRobinAgent(BaselineAgent):
    name = "RoundRobin"

    def _score(self, n, k, b, p):
        pr = (k - (self.env.t % self.env.K)) % self.env.K
        return (self.env.K - pr) * 100 + p - b * 0.01


class EDFAgent(BaselineAgent):
    name = "EDF"

    def _dl_remaining(self, k):
        q = self.env.queues[k]
        return 1e9 if not q else (q[0].arrival_slot + self.env._deadline(k) - 1) - self.env.t

    def _score(self, n, k, b, p):
        stale = self.env.stale_gain()[k, n - 1, :]
        return -self._dl_remaining(k) * 100 + (1.0 if b == int(np.argmax(stale)) else 0.0) + p * 0.1


class StaleMaxGainAgent(BaselineAgent):
    name = "StaleMaxGain"

    def _score(self, n, k, b, p):
        best = int(np.argmax(self.env.stale_gain()[k, n - 1, :]))
        return len(self.env.queues[k]) * 10 + (1.0 if b == best else 0.0) + p * 0.1


class MaxSINROracleAgent(BaselineAgent):
    name = "MaxSINROracle"

    def _score(self, n, k, b, p):
        # current-CSI channel-aware scheduler (oracle SINR maximisation)
        return self.env.beta[k] * self.env.cur_gain[k, n - 1, b] * self.env.cfg.power_grid_w[p]


class PerfectMaxGainAgent(BaselineAgent):
    name = "PerfectMaxGain"

    def _score(self, n, k, b, p):
        best = int(np.argmax(self.env.cur_gain[k, n - 1, :]))
        return len(self.env.queues[k]) * 10 + (1.0 if b == best else 0.0) + p * 0.1


class LastBeamAgent(BaselineAgent):
    name = "LastBeam"

    def _score(self, n, k, b, p):
        pref = self.last_beam.get(k, int(np.argmax(self.env.stale_gain()[k, n - 1, :])))
        return len(self.env.queues[k]) * 10 + (1.0 if b == pref else 0.0) + p * 0.1


# ------------------------------------------------------------- Layer 1 (fixed radio)
class Layer1FixedRadioMixin:
    layer = 1

    def _fixed_feasible(self, prefix, n):
        """feasible tokens restricted to the FIXED radio (beam=fixed_beam, power=fixed_power)."""
        env = self.env
        out = [IDLE]
        for t in env.feasible_tokens(prefix, n):
            if t == IDLE:
                continue
            if int(t[1][1:]) == env.fixed_beam and int(t[2][1:]) == env.fixed_power:
                out.append(t)
        return out


class Layer1RandomAgent(Layer1FixedRadioMixin, BaselineAgent):
    name = "L1-Fixed-Random"

    def act(self, base_obs):
        env = self.env
        prefix, tokens = [], []
        for n in range(1, env.N + 1):
            feas = sorted(self._fixed_feasible(prefix, n), key=lambda t: (t != IDLE, str(t)))
            choice = feas[int(self.rng.integers(0, len(feas)))]
            tokens.append(choice); prefix.append(choice)
        return tokens


ALL_LAYER2_BASELINES = [RandomAgent, RoundRobinAgent, EDFAgent, StaleMaxGainAgent,
                        MaxSINROracleAgent, PerfectMaxGainAgent, LastBeamAgent]


def run_episode(env: M2Env, agent):
    """Roll one deterministic full-drain episode; return env.episode_metrics()."""
    env.reset()
    if hasattr(agent, "reset"):
        agent.reset()
    obs = env.begin_slot()
    done = False
    while not done:
        tokens = agent.act(obs)
        obs, rp, rb, cost, done, info = env.commit_action(tokens)
    return env.episode_metrics()
