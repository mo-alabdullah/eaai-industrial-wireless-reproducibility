#!/usr/bin/env python3
"""I-B: EXACT finite-horizon JOINT control on a fixed realised trace (form A).

The simulator's per-slot randomness (arrivals, mobility, shadowing, fading) is consumed identically
in every slot regardless of the action taken - `begin_slot` draws exactly K arrival variates and
`_advance_channel_and_mobility` draws a fixed number of channel variates. The H-slot control problem
on a recorded trace is therefore fully DETERMINISTIC, and exhaustive search over action sequences
with state de-duplication is an exact finite-horizon optimisation, not a heuristic search.

Objective, lexicographic:
    1. maximise packets delivered within their deadline over the horizon,
    2. minimise cumulative transmit power.

`ReplayModel` reproduces M2Env's slot semantics exactly; `tests/test_optimization_benchmark.py`
asserts step-for-step equivalence against the live environment on random action sequences.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .radio import cell_cost, p_required, SlotState


class BudgetExceeded(RuntimeError):
    """Raised when exact enumeration exceeds the declared node/time budget. The benchmark reports
    the barrier rather than degrading silently into a heuristic search."""
    def __init__(self, nodes, states, seconds):
        super().__init__(f"exact enumeration exceeded budget at {nodes:,} nodes / "
                         f"{states:,} states / {seconds:.1f} s")
        self.nodes, self.states, self.seconds = nodes, states, seconds


@dataclass(frozen=True)
class Trace:
    """Everything the H-slot deterministic problem needs, recorded from one env rollout."""
    H: int
    K: int
    N: int
    B: int
    arrivals: Tuple[Tuple[int, ...], ...]              # [t][k] in {0,1}
    gain_true: Tuple[np.ndarray, ...]                  # [t] -> (K,N,B)
    gain_info: Tuple[np.ndarray, ...]                  # [t] -> (K,N,B) (stale view)
    beta: Tuple[Tuple[float, ...], ...]                # [t][k]
    pkt_bits: Tuple[int, ...]
    deadline: Tuple[int, ...]
    queue_cap: Tuple[int, ...]
    max_retx: Tuple[int, ...]
    n_max: Tuple[int, ...]
    power_grid: Tuple[float, ...]
    per_device_cap_w: float
    noise_w: float
    bandwidth_hz: float
    tau_s: float
    t0: int                                            # absolute slot index of trace position 0
    q0: Tuple[Tuple[Tuple[int, int], ...], ...]        # initial queues: per device, (arrival_slot, retx)


def slot_state(tr: Trace, t: int, queues) -> SlotState:
    return SlotState(K=tr.K, N=tr.N, B=tr.B, beta=tr.beta[t],
                     gain_info=tr.gain_info[t], gain_true=tr.gain_true[t],
                     pkt_bits=tr.pkt_bits,
                     queue_len=tuple(len(q) for q in queues),
                     n_max=tr.n_max, power_grid=tr.power_grid,
                     per_device_cap_w=tr.per_device_cap_w, noise_w=tr.noise_w,
                     bandwidth_hz=tr.bandwidth_hz, tau_s=tr.tau_s)


class ReplayModel:
    """Deterministic replay of M2Env slot semantics over a recorded trace."""

    def __init__(self, tr: Trace, believe_info: bool = False):
        """believe_info=True makes the model score success against the OPTIMISER'S aged view
        (gain_info) instead of the realised channel. Used only for PLANNING under aged CSI;
        the resulting plan is always re-executed on a believe_info=False model for scoring."""
        self.tr = tr
        self.believe_info = believe_info
        self.reset()

    def reset(self):
        self.queues: List[List[List[int]]] = [[list(p) for p in q] for q in self.tr.q0]
        self.i = 0                       # trace position
        self.delivered = 0
        self.deadline_drops = 0
        self.retx_drops = 0
        self.overflow = 0
        self.power = 0.0

    # ---- arrivals -> overflow -> deadline expiry  (mirrors M2Env.begin_slot)
    def begin_slot(self):
        tr = self.tr
        t = tr.t0 + self.i
        for k in range(tr.K):
            if tr.arrivals[self.i][k]:
                if len(self.queues[k]) >= tr.queue_cap[k]:
                    self.overflow += 1
                else:
                    self.queues[k].append([t, 0])
        for k in range(tr.K):
            keep = []
            for pkt in self.queues[k]:
                if t > pkt[0] + tr.deadline[k] - 1:
                    self.deadline_drops += 1
                else:
                    keep.append(pkt)
            self.queues[k] = keep

    # ---- commit (mirrors M2Env.commit_action for the metrics this benchmark uses)
    def commit(self, assign: Sequence[Optional[Tuple[int, int, int]]]) -> bool:
        """assign[n] = None | (k, b, power_index). Returns False if the action is infeasible."""
        tr = self.tr
        cnt: Dict[int, int] = {}
        pw: Dict[int, float] = {}
        for n, a in enumerate(assign):
            if a is None:
                continue
            k, b, pi = a
            cnt[k] = cnt.get(k, 0) + 1
            if cnt[k] > min(tr.n_max[k], len(self.queues[k])):
                return False
            pw[k] = pw.get(k, 0.0) + tr.power_grid[pi]
            if pw[k] > tr.per_device_cap_w + 1e-12:
                return False
        by_dev: Dict[int, List[Tuple[int, int, int]]] = {}
        for n, a in enumerate(assign):
            if a is None:
                continue
            by_dev.setdefault(a[0], []).append((n, a[1], a[2]))
        for k, lst in by_dev.items():
            for (n, b, pi) in lst:
                if not self.queues[k]:
                    break
                p = tr.power_grid[pi]
                self.power += p
                gsrc = tr.gain_info if self.believe_info else tr.gain_true
                sinr = p * tr.beta[self.i][k] * gsrc[self.i][k, n, b] / tr.noise_w
                cap = tr.bandwidth_hz * tr.tau_s * math.log2(1.0 + max(sinr, 0.0))
                if cap >= tr.pkt_bits[k]:
                    self.queues[k].pop(0)
                    self.delivered += 1
                else:
                    self.queues[k][0][1] += 1
                    if self.queues[k][0][1] > tr.max_retx[k]:
                        self.queues[k].pop(0)
                        self.retx_drops += 1
        self.i += 1
        return True

    def signature(self):
        return (self.i, tuple(tuple(tuple(p) for p in q) for q in self.queues))


def enumerate_actions(tr: Trace, st: SlotState, use_true: bool,
                      max_actions: Optional[int] = None):
    """All device-to-subchannel assignments after the beam/power dominance reduction of I-A.

    Beam and power are pinned to the dominant choice for the optimiser's information set, which is
    exact for a per-slot power-minimising objective (radio.py Lemmas 1-2); the remaining freedom is
    which device occupies which subchannel, plus idling."""
    cost = {}
    for k in range(tr.K):
        for n in range(tr.N):
            cost[(k, n)] = cell_cost(st, k, n, use_true)
    opts: List[List[Optional[int]]] = []
    for n in range(tr.N):
        o: List[Optional[int]] = [None]
        for k in range(tr.K):
            if st.queue_len[k] > 0 and cost[(k, n)][0] is not None:
                o.append(k)
        opts.append(o)
    out = []
    for combo in itertools.product(*opts):
        cnt: Dict[int, int] = {}
        pw: Dict[int, float] = {}
        ok = True
        act: List[Optional[Tuple[int, int, int]]] = []
        for n, k in enumerate(combo):
            if k is None:
                act.append(None)
                continue
            b, pi, w = cost[(k, n)]
            cnt[k] = cnt.get(k, 0) + 1
            if cnt[k] > min(tr.n_max[k], st.queue_len[k]):
                ok = False
                break
            pw[k] = pw.get(k, 0.0) + w
            if pw[k] > tr.per_device_cap_w + 1e-12:
                ok = False
                break
            act.append((k, b, pi))
        if ok:
            out.append(tuple(act))
        if max_actions and len(out) >= max_actions:
            break
    return out


def solve_exact_joint(tr: Trace, use_true: bool = False,
                      max_nodes: int = 2_000_000, max_seconds: float = 60.0,
                      return_plan: bool = False):
    """Exact finite-horizon optimisation by breadth-first expansion with state de-duplication.

    Returns (best_delivered, best_power, nodes_expanded, states_visited).
    Lexicographic objective: maximise delivered, then minimise cumulative power.
    De-duplication is sound because the trace is fixed: two branches sharing the same
    (slot, queue contents) signature face identical futures, so only the lexicographically best
    (delivered, power) prefix can lead to the overall optimum."""
    believe = not use_true          # aged planner reasons on its own (stale) view of success
    frontier: Dict[tuple, Tuple[int, float, ReplayModel, tuple]] = {}
    m0 = ReplayModel(tr, believe_info=believe)
    frontier[m0.signature()] = (0, 0.0, m0, ())
    nodes = 0
    states = 0
    import time as _time
    _t0 = _time.perf_counter()
    for step in range(tr.H):
        nxt: Dict[tuple, Tuple[int, float, ReplayModel, tuple]] = {}
        for sig, (dl, pw, model, plan) in frontier.items():
            states += 1
            model.begin_slot()
            st = slot_state(tr, model.i, model.queues)
            for act in enumerate_actions(tr, st, use_true):
                nodes += 1
                if nodes > max_nodes or (_time.perf_counter() - _t0) > max_seconds:
                    raise BudgetExceeded(nodes, states,
                                         _time.perf_counter() - _t0)
                m = ReplayModel(tr, believe_info=believe)
                m.queues = [[list(p) for p in q] for q in model.queues]
                m.i, m.delivered, m.power = model.i, dl, pw
                m.deadline_drops = model.deadline_drops
                m.retx_drops = model.retx_drops
                m.overflow = model.overflow
                if not m.commit(act):
                    continue
                s2 = m.signature()
                cur = nxt.get(s2)
                cand = (m.delivered, m.power, m, plan + (act,))
                if cur is None or (cand[0] > cur[0]) or (cand[0] == cur[0] and cand[1] < cur[1] - 1e-15):
                    nxt[s2] = cand
        frontier = nxt
        if not frontier:
            break
    best = (-1, math.inf, ())
    for _, (dl, pw, _m, plan) in frontier.items():
        if dl > best[0] or (dl == best[0] and pw < best[1] - 1e-15):
            best = (dl, pw, plan)
    if return_plan:
        return best[0], best[1], nodes, states, best[2]
    return best[0], best[1], nodes, states


def execute_plan(tr: Trace, plan: Sequence[tuple]) -> Tuple[int, float, int]:
    """Execute a planned action sequence against the REALISED channel.

    A plan produced under aged CSI is optimal for the planner's beliefs; this reports what it
    actually achieves. Actions that have become infeasible are skipped subchannel-by-subchannel."""
    m = ReplayModel(tr, believe_info=False)
    skipped = 0
    for act in plan:
        m.begin_slot()
        ok = m.commit(act)
        if not ok:
            skipped += 1
            m.commit(tuple([None] * tr.N))
    return m.delivered, m.power, skipped


def rollout_policy(tr: Trace, chooser) -> Tuple[int, float]:
    """Run a single-slot policy over the trace. `chooser(tr, st) -> action tuple`."""
    m = ReplayModel(tr)
    for _ in range(tr.H):
        m.begin_slot()
        st = slot_state(tr, m.i, m.queues)
        act = chooser(tr, st, m)
        if not m.commit(act):
            raise ValueError("policy produced an infeasible action")
    return m.delivered, m.power


def edf_min_feasible(use_true: bool = False):
    """Greedy EDF + best-beam + minimum-feasible-power, in subchannel order - the deployable
    reference heuristic, expressed on the replay model."""
    def chooser(tr: Trace, st: SlotState, m: ReplayModel):
        t = tr.t0 + m.i
        act: List[Optional[Tuple[int, int, int]]] = []
        cnt: Dict[int, int] = {}
        pw: Dict[int, float] = {}
        for n in range(tr.N):
            cands = []
            for k in range(tr.K):
                if not m.queues[k]:
                    continue
                if cnt.get(k, 0) >= min(tr.n_max[k], len(m.queues[k])):
                    continue
                b, pi, w = cell_cost(st, k, n, use_true)
                if pi is None:
                    continue
                if pw.get(k, 0.0) + w > tr.per_device_cap_w + 1e-12:
                    continue
                slack = (m.queues[k][0][0] + tr.deadline[k] - 1) - t
                cands.append((-slack * 100.0 + len(m.queues[k]) * 0.01, k, b, pi, w))
            if not cands:
                act.append(None)
                continue
            _, k, b, pi, w = max(cands)
            cnt[k] = cnt.get(k, 0) + 1
            pw[k] = pw.get(k, 0.0) + w
            act.append((k, b, pi))
        return tuple(act)
    return chooser


# ------------------------------------------------------------------ trace recording
def record_trace(cfg, seed: int, H: int, warmup: int = 20, agent_factory=None) -> Trace:
    """Roll a live M2Env forward `warmup` slots under a reference policy, then record the next H
    slots of realised randomness (arrivals, gains, beta) plus the queue state at the cut point.

    The recorded randomness is action-independent (see module docstring), so the recorded trace is a
    valid deterministic instance for ANY action sequence over the horizon."""
    from m2.env import M2Env, IDLE
    from baselines_v2 import ComponentAgent
    env = M2Env(cfg, seed)
    ag = (agent_factory(env) if agent_factory else
          ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule="StaleBest",
                         power_rule="MinFeasible-Stale"))
    env.reset()
    if hasattr(ag, "reset"):
        ag.reset()
    obs = env.begin_slot()
    for _ in range(warmup):
        toks = ag.act(obs)
        nxt, *_rest = env.commit_action(toks)
        obs = nxt if nxt is not None else obs
    t0 = env.t
    q0 = tuple(tuple((p.arrival_slot, p.retx) for p in env.queues[k]) for k in range(env.K))
    arrivals, gt, gi, betas = [], [], [], []
    probe = env
    for _h in range(H):
        # the slot is already open: its arrivals have been applied to the live queues, so the
        # recorded arrival vector for position 0 is empty and q0 already includes them.
        arrivals.append(tuple(0 for _ in range(env.K)) if _h == 0 else arrivals_pending)
        gt.append(np.array(env.cur_gain, dtype=float))
        gi.append(np.array(env.stale_gain(), dtype=float))
        betas.append(tuple(float(x) for x in env.beta))
        before = [len(env.queues[k]) for k in range(env.K)]
        toks = ag.act(obs)
        nxt, *_rest = env.commit_action(toks)
        obs = nxt if nxt is not None else obs
        arrivals_pending = tuple(
            1 if any(p.arrival_slot == env.t for p in env.queues[k]) else 0 for k in range(env.K))
    return Trace(
        H=H, K=env.K, N=env.N, B=env.cfg.codebook_size,
        arrivals=tuple(arrivals), gain_true=tuple(gt), gain_info=tuple(gi), beta=tuple(betas),
        pkt_bits=tuple(int(env._pktbits(k)) for k in range(env.K)),
        deadline=tuple(int(env._deadline(k)) for k in range(env.K)),
        queue_cap=tuple(int(env._qcap(k)) for k in range(env.K)),
        max_retx=tuple(int(env._maxretx(k)) for k in range(env.K)),
        n_max=tuple(int(env.n_max[f"d{k}"]) for k in range(env.K)),
        power_grid=tuple(float(p) for p in env.cfg.power_grid_w),
        per_device_cap_w=float(env.cfg.per_device_total_cap_w),
        noise_w=float(env.noise_w), bandwidth_hz=float(env.cfg.bandwidth_hz),
        tau_s=float(env.cfg.tau_s), t0=t0, q0=q0)


def size_instance(tr: Trace) -> dict:
    """I-B sizing: raw and feasible action counts, and the exhaustive-search bound."""
    m = ReplayModel(tr)
    raw = (1 + tr.K * tr.B * len(tr.power_grid)) ** tr.N
    reduced = (tr.K + 1) ** tr.N
    feas = []
    for _ in range(tr.H):
        m.begin_slot()
        st = slot_state(tr, m.i, m.queues)
        acts = enumerate_actions(tr, st, False)
        feas.append(len(acts))
        m.commit(acts[0] if acts else tuple([None] * tr.N))
    return dict(raw_tokens_per_slot=raw, reduced_assignments_per_slot=reduced,
                feasible_per_slot_mean=float(np.mean(feas)),
                feasible_per_slot_max=int(max(feas)),
                naive_sequences=int(np.prod([max(f, 1) for f in feas])))
