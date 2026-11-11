#!/usr/bin/env python3
"""I-A: EXACT slot-level radio-allocation benchmark.

Problem (one slot, fixed device priority set supplied by the scheduler):
    choose, for each subchannel n in 0..N-1, either IDLE or a triple (k, b, p)
    minimising total transmit power subject to every scheduled transmission succeeding,
    lexicographically after maximising the number of successful transmissions.

Constraints enforced (identical to M2Env.fast_id_mask / _validate_action):
    * subchannel exclusivity          - one token per subchannel by construction
    * per-device assignment cap       - count_k <= min(n_max_k, eligible packets in queue_k)
    * per-device total power cap      - sum of powers assigned to k <= per_device_total_cap_w
    * packet availability             - count_k <= len(queue_k)
    * beam codebook feasibility       - b in 0..B-1
    * discrete power grid             - p in the supplied grid

EXACTNESS ARGUMENT (two dominance lemmas, both verified in tests/test_optimization_benchmark.py
against unrestricted brute-force enumeration over the full (k, b, p) token alphabet):

  Success is deterministic and monotone in received power:
      success(k,n,b,p)  <=>  W*tau*log2(1 + p*beta_k*G[k,n,b]/sigma^2) >= L_k
                        <=>  p >= p_req(k,n,b) := sigma^2 * (2^(L_k/(W*tau)) - 1) / (beta_k*G[k,n,b])

  Lemma 1 (beam dominance). p_req is strictly decreasing in G[k,n,b], so for any (k,n) the
  gain-maximising beam b*(k,n) = argmax_b G[k,n,b] minimises the required power. No other beam can
  achieve a success at a lower grid level.

  Lemma 2 (power dominance). Given b*, the smallest grid level >= p_req is optimal: it minimises the
  objective contribution AND consumes the least per-device budget, so it can never be strictly worse
  under any feasible completion.

  Hence an optimal solution exists in which every used subchannel carries (k, b*(k,n), p*(k,n)), and
  the search collapses from (1 + K*B*P)^N tokens to (K+1)^N device-to-subchannel assignments.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

INF = float("inf")


@dataclass(frozen=True)
class SlotState:
    """Immutable frozen slot state. `gain_info` is what the OPTIMISER may look at;
    `gain_true` is what the environment will use to realise the outcome."""
    K: int
    N: int
    B: int
    beta: Tuple[float, ...]
    gain_info: np.ndarray            # (K, N, B) - stale or current, per deployability
    gain_true: np.ndarray            # (K, N, B) - current (realisation)
    pkt_bits: Tuple[int, ...]        # per device
    queue_len: Tuple[int, ...]       # eligible packets per device
    n_max: Tuple[int, ...]           # per-device subchannel cap
    power_grid: Tuple[float, ...]
    per_device_cap_w: float
    noise_w: float
    bandwidth_hz: float
    tau_s: float

    def sinr_req(self, k: int) -> float:
        return 2.0 ** (self.pkt_bits[k] / (self.bandwidth_hz * self.tau_s)) - 1.0


def p_required(st: SlotState, k: int, n: int, b: int, use_true: bool = False) -> float:
    g = (st.gain_true if use_true else st.gain_info)[k, n, b]
    if g <= 0.0:
        return INF
    return st.noise_w * st.sinr_req(k) / (st.beta[k] * g)


def quantise_up(grid: Sequence[float], p_req: float) -> Optional[int]:
    """Smallest grid index with grid[i] >= p_req, or None if the grid cannot reach it."""
    for i, v in enumerate(grid):
        if v >= p_req - 1e-18:
            return i
    return None


def cell_cost(st: SlotState, k: int, n: int, use_true: bool = False
              ) -> Tuple[Optional[int], Optional[int], float]:
    """(best beam, power index, power W) for serving device k on subchannel n, or (None,None,inf)."""
    g = (st.gain_true if use_true else st.gain_info)[k, n, :]
    b = int(np.argmax(g))
    pi = quantise_up(st.power_grid, p_required(st, k, n, b, use_true))
    if pi is None:
        return None, None, INF
    return b, pi, st.power_grid[pi]


@dataclass
class Allocation:
    tokens: List[Optional[Tuple[int, int, int]]]     # per subchannel: None = IDLE, else (k,b,p_idx)
    served: int = 0
    power_w: float = 0.0
    nodes: int = 0
    # frontier[j] = minimum total power over all feasible allocations serving exactly j packets
    frontier: Dict[int, float] = field(default_factory=dict)
    frontier_tokens: Dict[int, list] = field(default_factory=dict)
    def as_env_tokens(self):
        return [("idle" if t is None else (f"d{t[0]}", f"b{t[1]}", f"p{t[2]}")) for t in self.tokens]


def solve_exact_radio(st: SlotState, use_true: bool = False,
                      allowed: Optional[Sequence[int]] = None) -> Allocation:
    """Exhaustive enumeration over device-to-subchannel assignments after the dominance reduction.

    `allowed` restricts which devices the scheduler has made eligible (e.g. the EDF-priority set).
    Objective: lexicographic  (max served, then min total power).
    Returns the optimal allocation; `nodes` counts enumerated assignment tuples.
    """
    devs = list(range(st.K)) if allowed is None else list(allowed)
    cost = {}
    for k in devs:
        for n in range(st.N):
            cost[(k, n)] = cell_cost(st, k, n, use_true)
    options: List[List[Optional[int]]] = []
    for n in range(st.N):
        opt: List[Optional[int]] = [None]
        for k in devs:
            if st.queue_len[k] > 0 and cost[(k, n)][0] is not None:
                opt.append(k)
        options.append(opt)

    best = Allocation(tokens=[None] * st.N, served=0, power_w=0.0)
    frontier: Dict[int, float] = {}
    frontier_tokens: Dict[int, list] = {}
    nodes = 0
    for combo in itertools.product(*options):
        nodes += 1
        cnt: Dict[int, int] = {}
        pw: Dict[int, float] = {}
        total = 0.0
        ok = True
        for n, k in enumerate(combo):
            if k is None:
                continue
            c = cnt.get(k, 0) + 1
            if c > min(st.n_max[k], st.queue_len[k]):
                ok = False
                break
            w = pw.get(k, 0.0) + cost[(k, n)][2]
            if w > st.per_device_cap_w + 1e-12:
                ok = False
                break
            cnt[k], pw[k] = c, w
            total += cost[(k, n)][2]
        if not ok:
            continue
        served = sum(1 for k in combo if k is not None)
        if served not in frontier or total < frontier[served] - 1e-15:
            toks0: List[Optional[Tuple[int, int, int]]] = []
            for n, k in enumerate(combo):
                toks0.append(None if k is None else (k, cost[(k, n)][0], cost[(k, n)][1]))
            frontier[served] = total
            frontier_tokens[served] = toks0
        if (served > best.served) or (served == best.served and total < best.power_w - 1e-15):
            toks: List[Optional[Tuple[int, int, int]]] = []
            for n, k in enumerate(combo):
                toks.append(None if k is None else (k, cost[(k, n)][0], cost[(k, n)][1]))
            best = Allocation(tokens=toks, served=served, power_w=total)
    best.nodes = nodes
    best.frontier = frontier
    best.frontier_tokens = frontier_tokens
    return best


def brute_force_radio(st: SlotState, use_true: bool = False,
                      allowed: Optional[Sequence[int]] = None) -> Allocation:
    """Unrestricted reference enumeration over the FULL token alphabet (1 + K*B*P per subchannel).

    Exponential - for validation on tiny instances only. Applies no dominance reduction, so it is an
    independent check of solve_exact_radio."""
    devs = list(range(st.K)) if allowed is None else list(allowed)
    P = len(st.power_grid)
    toks: List[Optional[Tuple[int, int, int]]] = [None]
    for k in devs:
        for b in range(st.B):
            for pi in range(P):
                toks.append((k, b, pi))
    best = Allocation(tokens=[None] * st.N, served=0, power_w=0.0)
    nodes = 0
    for combo in itertools.product(toks, repeat=st.N):
        nodes += 1
        cnt: Dict[int, int] = {}
        pw: Dict[int, float] = {}
        total = 0.0
        served = 0
        ok = True
        for n, t in enumerate(combo):
            if t is None:
                continue
            k, b, pi = t
            p = st.power_grid[pi]
            # a transmission counts only if it SUCCEEDS on the optimiser's information
            if p + 1e-18 < p_required(st, k, n, b, use_true):
                ok = False
                break
            c = cnt.get(k, 0) + 1
            if c > min(st.n_max[k], st.queue_len[k]):
                ok = False
                break
            w = pw.get(k, 0.0) + p
            if w > st.per_device_cap_w + 1e-12:
                ok = False
                break
            cnt[k], pw[k] = c, w
            total += p
            served += 1
        if not ok:
            continue
        if (served > best.served) or (served == best.served and total < best.power_w - 1e-15):
            best = Allocation(tokens=list(combo), served=served, power_w=total)
    best.nodes = nodes
    return best


def realised_success(st: SlotState, alloc: Allocation) -> int:
    """How many of the allocation's transmissions actually succeed against gain_true."""
    ok = 0
    for n, t in enumerate(alloc.tokens):
        if t is None:
            continue
        k, b, pi = t
        if st.power_grid[pi] + 1e-18 >= p_required(st, k, n, b, use_true=True):
            ok += 1
    return ok


def solve_exact_radio_fixed_demand(st: SlotState, demand: Dict[int, int],
                                   use_true: bool = False) -> Allocation:
    """EXACT radio allocation with the SCHEDULING DECISION HELD COMPLETELY FIXED.

    `demand[k]` = the number of transmissions device k must receive. Only the assignment of those
    transmissions to subchannels, and their beam and power, may change. This is the pure
    radio-allocation subproblem of I-A: it cannot change which packets are served, so any power
    difference against the heuristic is attributable to subchannel/beam/power allocation alone.

    Exhaustive over assignments of the demand multiset to distinct subchannels; the beam/power
    dominance reduction of solve_exact_radio applies unchanged.
    """
    slots = st.N
    multiset: List[int] = []
    for k, c in sorted(demand.items()):
        multiset.extend([k] * c)
    if len(multiset) > slots:
        return Allocation(tokens=[None] * slots, served=0, power_w=INF)
    cost = {(k, n): cell_cost(st, k, n, use_true) for k in set(multiset) for n in range(slots)}
    best = Allocation(tokens=[None] * slots, served=0, power_w=INF)
    nodes = 0
    for positions in itertools.permutations(range(slots), len(multiset)):
        nodes += 1
        pw: Dict[int, float] = {}
        total = 0.0
        ok = True
        for k, n in zip(multiset, positions):
            b, pi, w = cost[(k, n)]
            if pi is None:
                ok = False
                break
            nw_ = pw.get(k, 0.0) + w
            if nw_ > st.per_device_cap_w + 1e-12:
                ok = False
                break
            pw[k] = nw_
            total += w
        if not ok:
            continue
        if total < best.power_w - 1e-15:
            toks: List[Optional[Tuple[int, int, int]]] = [None] * slots
            for k, n in zip(multiset, positions):
                b, pi, _ = cost[(k, n)]
                toks[n] = (k, b, pi)
            best = Allocation(tokens=toks, served=len(multiset), power_w=total)
    best.nodes = nodes
    return best


def brute_force_fixed_demand(st: SlotState, demand: Dict[int, int],
                             use_true: bool = False) -> Allocation:
    """Unrestricted reference for solve_exact_radio_fixed_demand (validation only)."""
    slots = st.N
    multiset: List[int] = []
    for k, c in sorted(demand.items()):
        multiset.extend([k] * c)
    P = len(st.power_grid)
    best = Allocation(tokens=[None] * slots, served=0, power_w=INF)
    nodes = 0
    for positions in itertools.permutations(range(slots), len(multiset)):
        for choice in itertools.product(
                *[[(b, p) for b in range(st.B) for p in range(P)] for _ in multiset]):
            nodes += 1
            pw: Dict[int, float] = {}
            total = 0.0
            ok = True
            for k, n, (b, pi) in zip(multiset, positions, choice):
                p = st.power_grid[pi]
                if p + 1e-18 < p_required(st, k, n, b, use_true):
                    ok = False
                    break
                nw_ = pw.get(k, 0.0) + p
                if nw_ > st.per_device_cap_w + 1e-12:
                    ok = False
                    break
                pw[k] = nw_
                total += p
            if not ok:
                continue
            if total < best.power_w - 1e-15:
                toks: List[Optional[Tuple[int, int, int]]] = [None] * slots
                for k, n, (b, pi) in zip(multiset, positions, choice):
                    toks[n] = (k, b, pi)
                best = Allocation(tokens=toks, served=len(multiset), power_w=total)
    best.nodes = nodes
    return best


# ------------------------------------------------------------------ continuous-power reference
def cell_cost_continuous(st: SlotState, k: int, n: int, use_true: bool = False
                         ) -> Tuple[Optional[int], float]:
    """(best beam, EXACT analytic p_req) with no quantisation.

    MATHEMATICAL REFERENCE ONLY. This assumes an arbitrarily fine transmit-power control that the
    discrete grids do not provide and that no hardware claim in this project supports. It is used
    solely as a lower bound on the achievable transmit power under the same caps and constraints."""
    g = (st.gain_true if use_true else st.gain_info)[k, n, :]
    b = int(np.argmax(g))
    pr = p_required(st, k, n, b, use_true)
    if not math.isfinite(pr) or pr > st.per_device_cap_w + 1e-18:
        return None, INF
    return b, pr


def solve_continuous_fixed_demand(st: SlotState, demand: Dict[int, int],
                                  use_true: bool = False) -> Allocation:
    """Continuous-power analogue of solve_exact_radio_fixed_demand.

    Exactness: with continuous power the per-cell cost is p_req itself, which is the infimum of
    feasible powers for that (k,n,b) and is attained. Beam dominance (Lemma 1) is unchanged, so the
    gain-maximising beam remains optimal. Only the assignment of the fixed demand multiset to
    subchannels is searched, exhaustively."""
    slots = st.N
    multiset: List[int] = []
    for k, c in sorted(demand.items()):
        multiset.extend([k] * c)
    if len(multiset) > slots:
        return Allocation(tokens=[None] * slots, served=0, power_w=INF)
    cost = {(k, n): cell_cost_continuous(st, k, n, use_true)
            for k in set(multiset) for n in range(slots)}
    best = Allocation(tokens=[None] * slots, served=0, power_w=INF)
    best_watts: List[float] = []
    nodes = 0
    for positions in itertools.permutations(range(slots), len(multiset)):
        nodes += 1
        pw: Dict[int, float] = {}
        total = 0.0
        ok = True
        for k, n in zip(multiset, positions):
            b, w = cost[(k, n)]
            if b is None:
                ok = False
                break
            nw_ = pw.get(k, 0.0) + w
            if nw_ > st.per_device_cap_w + 1e-18:
                ok = False
                break
            pw[k] = nw_
            total += w
        if not ok:
            continue
        if total < best.power_w - 1e-18:
            toks: List[Optional[Tuple[int, int, int]]] = [None] * slots
            watts = [0.0] * slots
            for k, n in zip(multiset, positions):
                b, w = cost[(k, n)]
                toks[n] = (k, b, -1)              # -1 = continuous power, value in .watts
                watts[n] = w
            best = Allocation(tokens=toks, served=len(multiset), power_w=total)
            best_watts = watts
    best.nodes = nodes
    best.frontier = {"watts": best_watts}          # per-subchannel continuous powers
    return best


def continuous_cost_of_assignment(st: SlotState, alloc: Allocation,
                                  use_true: bool = False) -> float:
    """Continuous (unquantised) cost of the device-to-subchannel assignment in `alloc`.

    Used to split the grid gap into pure rounding and quantisation-induced assignment distortion."""
    total = 0.0
    for n, t in enumerate(alloc.tokens):
        if t is None:
            continue
        k = t[0]
        b, w = cell_cost_continuous(st, k, n, use_true)
        if b is None:
            return INF
        total += w
    return total
