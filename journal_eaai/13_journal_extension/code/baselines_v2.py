#!/usr/bin/env python3
"""Stage-D component-decomposed baselines for the IJOCTA journal extension.

Every method is (scheduler x subchannel_rule x beam_rule x power_rule) with explicit CSI and budget
assumptions, per 13_journal_extension/BASELINE_DESIGN_SPEC.md. This module is NEW; the archived
07_simulation/m2/baselines.py is not modified, preserving ICAME'26 reproducibility.

Deployability: rules tagged ORACLE use current CSI and are upper bounds only, never practical methods.
"""
from __future__ import annotations
import math
from typing import List
import numpy as np
from m2.env import IDLE, M2Env

# ------------------------------------------------------------------ component rules
SCHEDULERS = ("Random", "RoundRobin", "EDF")
BEAM_RULES = ("Fixed", "RandomBeam", "LastBeam", "StaleBest", "OracleBest")   # OracleBest = upper bound
POWER_RULES = ("MaxPower", "UniformRandom", "MinFeasible-Stale", "MinFeasible-Oracle", "Budgeted",
               "Pmin")
ORACLE_RULES = {"OracleBest", "MinFeasible-Oracle"}


def _tok_parts(t):
    return int(t[0][1:]), int(t[1][1:]), int(t[2][1:])      # (k, b, p)


class ComponentAgent:
    """Composable baseline. Only tokens the env reports feasible are ever selected."""
    layer = 2

    def __init__(self, env: M2Env, seed: int = 0, scheduler="EDF", beam_rule="StaleBest",
                 power_rule="MaxPower", fixed_beam: int = 0, p_bar_w: float | None = None):
        assert scheduler in SCHEDULERS and beam_rule in BEAM_RULES and power_rule in POWER_RULES
        self.env, self.rng = env, np.random.default_rng(seed)
        self.scheduler, self.beam_rule, self.power_rule = scheduler, beam_rule, power_rule
        self.fixed_beam = fixed_beam
        self.p_bar_w = p_bar_w if p_bar_w is not None else env.cfg.p_bar_w
        self.name = f"{scheduler}-{beam_rule}-{power_rule}"
        self.uses_oracle = (beam_rule in ORACLE_RULES) or (power_rule in ORACLE_RULES)
        self.reset()

    def reset(self):
        self.last_beam = {}
        self._acc_power = 0.0        # aggregate power accumulated over measurement slots
        self._meas_slots = 0
        # Stage-D.1 diagnostic: histogram of the power INDEX actually committed (measurement phase)
        self.power_hist = [0] * len(self.env.cfg.power_grid_w)

    # ---------------- scheduler priority (higher = served first)
    def _dl_remaining(self, k):
        q = self.env.queues[k]
        return 1e9 if not q else (q[0].arrival_slot + self.env._deadline(k) - 1) - self.env.t

    def _sched_score(self, k, n):
        if self.scheduler == "EDF":
            return -self._dl_remaining(k) * 100.0 + len(self.env.queues[k]) * 0.01
        if self.scheduler == "RoundRobin":
            return float((self.env.K - ((k - (self.env.t % self.env.K)) % self.env.K)) * 100)
        return float(self.rng.random())                                   # Random

    # ---------------- beam choice among beams available for device k on subchannel n
    def _beam_choice(self, k, n, avail_b):
        if self.beam_rule == "Fixed":
            return self.fixed_beam if self.fixed_beam in avail_b else min(avail_b)
        if self.beam_rule == "RandomBeam":
            return int(self.rng.choice(sorted(avail_b)))
        if self.beam_rule == "StaleBest":
            g = self.env.stale_gain()[k, n - 1, :]
        elif self.beam_rule == "OracleBest":
            g = self.env.cur_gain[k, n - 1, :]
        elif self.beam_rule == "LastBeam":
            pref = self.last_beam.get(k)
            if pref is not None and pref in avail_b:
                return pref
            g = self.env.stale_gain()[k, n - 1, :]
        else:
            g = self.env.stale_gain()[k, n - 1, :]
        order = np.argsort(-g)
        for b in order:
            if int(b) in avail_b:
                return int(b)
        return min(avail_b)

    # ---------------- power choice
    def _predicted_success(self, k, n, b, p_idx, oracle=False):
        env = self.env
        gain = (env.cur_gain if oracle else env.stale_gain())[k, n - 1, b]
        pw = env.cfg.power_grid_w[p_idx]
        sinr = pw * env.beta[k] * gain / env.noise_w
        cap = env.cfg.bandwidth_hz * env.cfg.tau_s * math.log2(1.0 + max(sinr, 0.0))
        return cap >= env._pktbits(k)

    def _min_feasible_p(self, k, n, b, avail_p, oracle=False):
        for p in sorted(avail_p):
            if self._predicted_success(k, n, b, p, oracle=oracle):
                return p
        return max(avail_p)                    # none predicted to work -> strongest available

    def _budget_allowance(self):
        """Per-slot aggregate-power allowance that keeps the window mean <= p_bar."""
        T = self.env.cfg.t_meas_slots
        remaining_slots = max(T - self._meas_slots, 1)
        remaining_budget = self.p_bar_w * T - self._acc_power
        return max(remaining_budget / remaining_slots, 0.0)

    def _power_choice(self, k, n, b, avail_p, slot_power_so_far):
        if self.power_rule == "MaxPower":
            return max(avail_p)
        if self.power_rule == "Pmin":
            return min(avail_p)                 # fixed lowest available level (0.05 W)
        if self.power_rule == "UniformRandom":
            return int(self.rng.choice(sorted(avail_p)))
        if self.power_rule == "MinFeasible-Stale":
            return self._min_feasible_p(k, n, b, avail_p, oracle=False)
        if self.power_rule == "MinFeasible-Oracle":
            return self._min_feasible_p(k, n, b, avail_p, oracle=True)
        # Budgeted: min-feasible (stale), then throttle / defer to respect the aggregate budget
        p = self._min_feasible_p(k, n, b, avail_p, oracle=False)
        if self.env.phase != "measure":
            return p
        allow = self._budget_allowance()
        grid = self.env.cfg.power_grid_w
        for cand in sorted(avail_p, reverse=True):
            if cand <= p and slot_power_so_far + grid[cand] <= allow:
                return cand
        return None                             # defer this subchannel (idle) to stay in budget

    # ---------------- slot action
    def act(self, base_obs) -> List:
        env = self.env
        prefix, tokens, slot_power = [], [], 0.0
        for n in range(1, env.N + 1):
            feas = env.feasible_tokens(prefix, n)
            non_idle = [t for t in feas if t != IDLE]
            choice = IDLE
            if non_idle:
                devices = {}
                for t in non_idle:
                    k, b, p = _tok_parts(t)
                    devices.setdefault(k, []).append((b, p))
                kbest = max(devices, key=lambda k: self._sched_score(k, n))
                avail_b = {b for b, _ in devices[kbest]}
                b = self._beam_choice(kbest, n, avail_b)
                avail_p = {p for bb, p in devices[kbest] if bb == b}
                p = self._power_choice(kbest, n, b, avail_p, slot_power)
                if p is not None:
                    cand = (f"d{kbest}", f"b{b}", f"p{p}")
                    if cand in feas:
                        choice = cand
                        slot_power += env.cfg.power_grid_w[p]
                        self.last_beam[kbest] = b
                        if env.phase == "measure":
                            self.power_hist[p] += 1
            tokens.append(choice); prefix.append(choice)
        if env.phase == "measure":
            self._acc_power += slot_power
            self._meas_slots += 1
        return tokens


# ------------------------------------------------------------------ registry (BASELINE_DESIGN_SPEC §2)
METHODS_V2 = {
    "Random":                    dict(scheduler="Random",     beam_rule="RandomBeam", power_rule="UniformRandom"),
    "RoundRobin":                dict(scheduler="RoundRobin", beam_rule="StaleBest",  power_rule="MaxPower"),
    "EDF-FixedBeam-MaxPow":      dict(scheduler="EDF", beam_rule="Fixed",      power_rule="MaxPower"),
    "EDF-RandBeam-MaxPow":       dict(scheduler="EDF", beam_rule="RandomBeam", power_rule="MaxPower"),
    "EDF-StaleBeam-MaxPow":      dict(scheduler="EDF", beam_rule="StaleBest",  power_rule="MaxPower"),
    "EDF-OracleBeam-MaxPow":     dict(scheduler="EDF", beam_rule="OracleBest", power_rule="MaxPower"),
    "EDF-StaleBeam-MinPow":      dict(scheduler="EDF", beam_rule="StaleBest",  power_rule="MinFeasible-Stale"),
    "EDF-StaleBeam-Budgeted":    dict(scheduler="EDF", beam_rule="StaleBest",  power_rule="Budgeted"),
    "EDF-OracleBeam-MinPowOr":   dict(scheduler="EDF", beam_rule="OracleBest", power_rule="MinFeasible-Oracle"),
    # --- Stage D.1: fixed-P_min diagnostics (is dynamic power selection needed at all?) ---
    "EDF-StaleBeam-Pmin":        dict(scheduler="EDF", beam_rule="StaleBest",  power_rule="Pmin"),
    "EDF-OracleBeam-Pmin":       dict(scheduler="EDF", beam_rule="OracleBest", power_rule="Pmin"),
    "EDF-RandomBeam-Pmin":       dict(scheduler="EDF", beam_rule="RandomBeam", power_rule="Pmin"),
    "EDF-FixedBeam-Pmin":        dict(scheduler="EDF", beam_rule="Fixed",      power_rule="Pmin"),
}


def make_agent(name: str, env: M2Env, seed: int = 0) -> ComponentAgent:
    return ComponentAgent(env, seed=seed, **METHODS_V2[name])
