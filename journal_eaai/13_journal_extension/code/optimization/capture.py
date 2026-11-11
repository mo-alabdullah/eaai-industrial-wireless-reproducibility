#!/usr/bin/env python3
"""Freeze live M2Env slot states into immutable SlotState records for the exact benchmarks."""
from __future__ import annotations
from typing import List, Optional, Sequence
import numpy as np
from m2.env import M2Env
from .radio import SlotState


def freeze(env: M2Env) -> SlotState:
    """Capture the CURRENT open slot of `env`. Must be called after begin_slot()."""
    K, N, B = env.K, env.N, env.cfg.codebook_size
    return SlotState(
        K=K, N=N, B=B,
        beta=tuple(float(x) for x in env.beta),
        gain_info=np.array(env.stale_gain(), dtype=float),
        gain_true=np.array(env.cur_gain, dtype=float),
        pkt_bits=tuple(int(env._pktbits(k)) for k in range(K)),
        queue_len=tuple(len(env.queues[k]) for k in range(K)),
        n_max=tuple(int(env.n_max[f"d{k}"]) for k in range(K)),
        power_grid=tuple(float(p) for p in env.cfg.power_grid_w),
        per_device_cap_w=float(env.cfg.per_device_total_cap_w),
        noise_w=float(env.noise_w),
        bandwidth_hz=float(env.cfg.bandwidth_hz),
        tau_s=float(env.cfg.tau_s),
    )


def edf_priority(env: M2Env, limit: Optional[int] = None) -> List[int]:
    """Devices ordered by head-of-line slack (earliest deadline first); queue-empty devices dropped.

    Mirrors 07_simulation/m2/baselines.py EDFAgent priority (-remaining_deadline), so the exact
    radio benchmark is solved on the SAME eligible set the EDF heuristic schedules from."""
    scored = []
    for k in range(env.K):
        q = env.queues[k]
        if not q:
            continue
        rem = (q[0].arrival_slot + env._deadline(k) - 1) - env.t
        scored.append((rem, k))
    scored.sort()
    out = [k for _, k in scored]
    return out if limit is None else out[:limit]


def random_tiny_state(rng: np.random.Generator, K=3, N=2, B=4, P=4) -> SlotState:
    """Small random but PHYSICALLY SHAPED state for brute-force exactness validation."""
    beta = tuple(float(10.0 ** rng.uniform(-11.5, -9.5)) for _ in range(K))
    gain_info = rng.gamma(shape=1.0, scale=2.0, size=(K, N, B)) + 1e-3
    gain_true = gain_info * np.exp(rng.normal(0.0, 0.4, size=(K, N, B)))
    grid = tuple(sorted(float(x) for x in 10.0 ** rng.uniform(-3.5, -0.4, size=P)))
    return SlotState(
        K=K, N=N, B=B, beta=beta,
        gain_info=gain_info, gain_true=gain_true,
        pkt_bits=tuple(int(rng.choice([512, 1024, 2048])) for _ in range(K)),
        queue_len=tuple(int(rng.integers(0, 4)) for _ in range(K)),
        n_max=tuple(int(rng.integers(1, 3)) for _ in range(K)),
        power_grid=grid,
        per_device_cap_w=float(rng.choice([0.2, 0.4, 0.8, 1e9])),
        noise_w=2.0066945934687534e-14,
        bandwidth_hz=1e6, tau_s=1e-3,
    )
