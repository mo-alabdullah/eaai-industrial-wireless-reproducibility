#!/usr/bin/env python3
"""Seed-level statistics (M2, r35). Seed is the statistical unit.

Primary paired comparisons use matched seeds. The p-value is an EXACT paired sign-flip
permutation test (all 2^n sign patterns for n<=14, else Monte-Carlo) — assumption-light and fully
reproducible with pure numpy (no scipy). We also report the paired-t statistic, Cohen's d_z effect
size, and the Wilcoxon signed-rank statistic. Multiple primary comparisons are Holm-corrected.
"""
from __future__ import annotations

import itertools
import math
from typing import Dict, List, Sequence

import numpy as np


def summarize(values: Sequence[float]) -> Dict[str, float]:
    v = np.asarray(values, dtype=float)
    n = len(v)
    mean = float(v.mean()); sd = float(v.std(ddof=1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 0 else 0.0
    # 95% CI via t multiplier approximation (small-n); use 1.96 fallback for n>30
    tmult = _t_crit_95(n - 1) if n > 1 else 0.0
    return {"n": n, "mean": mean, "median": float(np.median(v)), "sd": sd,
            "ci95_lo": mean - tmult * se, "ci95_hi": mean + tmult * se}


_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        20: 2.086, 25: 2.060, 30: 2.042}


def _t_crit_95(df: int) -> float:
    if df <= 0:
        return 0.0
    if df in _T95:
        return _T95[df]
    keys = sorted(_T95)
    if df > keys[-1]:
        return 1.96
    lo = max(k for k in keys if k <= df); hi = min(k for k in keys if k >= df)
    return _T95[lo] + (_T95[hi] - _T95[lo]) * (df - lo) / (hi - lo)


def paired_compare(a: Sequence[float], b: Sequence[float], mc_samples: int = 20000,
                   rng_seed: int = 0) -> Dict[str, float]:
    """Paired comparison of matched-seed samples a (method A) vs b (method B). d = a - b."""
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    assert len(a) == len(b), "paired comparison requires matched seeds"
    d = a - b; n = len(d)
    mean_d = float(d.mean())
    sd_d = float(d.std(ddof=1)) if n > 1 else 0.0
    t_stat = mean_d / (sd_d / math.sqrt(n)) if sd_d > 0 else 0.0
    dz = mean_d / sd_d if sd_d > 0 else 0.0
    obs = abs(mean_d)
    if np.allclose(d, 0.0):
        p = 1.0
    elif n <= 14:
        cnt = 0; tot = 0
        for signs in itertools.product([1.0, -1.0], repeat=n):
            tot += 1
            if abs(float((np.array(signs) * d).mean())) >= obs - 1e-12:
                cnt += 1
        p = cnt / tot
    else:
        rng = np.random.default_rng(rng_seed)
        signs = rng.choice([1.0, -1.0], size=(mc_samples, n))
        perm = np.abs((signs * d).mean(axis=1))
        p = float((perm >= obs - 1e-12).mean())
    # Wilcoxon signed-rank statistic (report only)
    nz = d[d != 0]
    if len(nz):
        ranks = _rankdata(np.abs(nz))
        w = float(min(ranks[nz > 0].sum(), ranks[nz < 0].sum()))
    else:
        w = 0.0
    return {"n": n, "mean_diff": mean_d, "sd_diff": sd_d, "t_stat": t_stat,
            "cohens_dz": dz, "wilcoxon_w": w, "p_value": p,
            "test": "paired sign-flip permutation (exact n<=14)"}


def _rankdata(x):
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x)); ranks[order] = np.arange(1, len(x) + 1)
    # average ties
    x_sorted = x[order]; i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x_sorted[j + 1] == x_sorted[i]:
            j += 1
        if j > i:
            avg = (ranks[order[i]] + ranks[order[j]]) / 2.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
        i = j + 1
    return ranks


def holm_adjust(pvals: List[float]) -> List[float]:
    """Holm-Bonferroni step-down adjusted p-values."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m; running = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * pvals[idx]
        running = max(running, val)
        adj[idx] = min(running, 1.0)
    return adj
