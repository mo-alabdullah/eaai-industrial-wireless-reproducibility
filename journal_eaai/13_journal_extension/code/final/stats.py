#!/usr/bin/env python3
"""Frozen statistical functions for the final confirmatory analysis (master pass, 2026-09-21).

Implements exactly the plan frozen in FINAL_CONFIRMATORY_PROTOCOL_V2 §6 and the hypotheses
register, and nothing more:

  * paired mean difference with an explicit sign convention;
  * 95% BCa paired bootstrap interval (10,000 resamples, seed recorded);
  * EXACT paired two-sided sign-flip (randomisation) test, all 2^n assignments enumerated;
  * Cohen's d_z with direction.

DELIBERATELY ABSENT, per the frozen protocol:
  * TOST / equivalence / non-inferiority  -- DECLINED by the author; delta NOT SET;
  * any multiplicity correction            -- m = 1 (H2 is the sole inferential test).

A non-rejection is a non-rejection. Nothing in this module may be used to support an
"equivalent", "equal", "non-inferior" or "near-optimal" statement.

SIGN CONVENTION (frozen): differences are formed as  b_i - a_i  where `a` is the first
(reference/left) sample and `b` the second. Callers must state which is which; the returned
`sign_convention` string travels with the result so a table cannot silently invert it.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260921          # recorded, fixed, never tuned
EXACT_ENUMERATION_MAX_N = 24       # 2^24 = 16.7M; n=20 -> 1,048,576


class PairingError(ValueError):
    """Raised on malformed paired input. Never repaired silently."""


@dataclass
class PairedResult:
    n: int
    mean_diff: float
    sd_diff: float
    ci_low: float
    ci_high: float
    ci_method: str
    p_value: float | None
    p_method: str
    n_assignments: int | None
    d_z: float | None
    n_positive: int
    n_negative: int
    n_ties: int
    sign_convention: str
    bootstrap_seed: int | None = None
    notes: List[str] = field(default_factory=list)

    def as_row(self) -> Dict[str, object]:
        return {k: getattr(self, k) for k in
                ("n", "mean_diff", "sd_diff", "ci_low", "ci_high", "ci_method",
                 "p_value", "p_method", "n_assignments", "d_z",
                 "n_positive", "n_negative", "n_ties", "sign_convention", "bootstrap_seed")}


def _check_pairs(a: Sequence[float], b: Sequence[float],
                 keys_a: Sequence | None = None, keys_b: Sequence | None = None) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise PairingError(f"unequal sample lengths: {a.shape} vs {b.shape}")
    if a.size == 0:
        raise PairingError("empty paired sample")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise PairingError("non-finite value in paired sample; missing pairs must be rejected, "
                           "not imputed")
    if keys_a is not None or keys_b is not None:
        if keys_a is None or keys_b is None:
            raise PairingError("supply both key sequences or neither")
        ka, kb = list(keys_a), list(keys_b)
        if len(ka) != len(a) or len(kb) != len(b):
            raise PairingError("key length does not match sample length")
        if len(set(ka)) != len(ka):
            raise PairingError(f"duplicate keys in first sample: "
                               f"{sorted(k for k in set(ka) if ka.count(k) > 1)}")
        if len(set(kb)) != len(kb):
            raise PairingError(f"duplicate keys in second sample: "
                               f"{sorted(k for k in set(kb) if kb.count(k) > 1)}")
        if ka != kb:
            raise PairingError("pairing keys differ or are misordered between samples")
    return b - a


def cohens_dz(diff: np.ndarray) -> float | None:
    """Cohen's d_z = mean(diff)/sd(diff), sample sd (ddof=1). Undefined when sd == 0."""
    if diff.size < 2:
        return None
    sd = float(np.std(diff, ddof=1))
    if sd == 0.0:
        return None                      # undefined, NOT infinite, NOT zero
    return float(np.mean(diff) / sd)


def exact_sign_flip_p(diff: np.ndarray) -> Tuple[float, int]:
    """EXACT paired two-sided sign-flip (randomisation) test.

    Enumerates all 2^n sign assignments of the observed differences and returns
    p = #{|T*| >= |T_obs|} / 2^n with T the sum of differences.

    All-ties input gives p = 1.0 by construction (every assignment reproduces T_obs = 0).
    """
    n = diff.size
    if n > EXACT_ENUMERATION_MAX_N:
        raise PairingError(f"exact enumeration refused for n={n} (> {EXACT_ENUMERATION_MAX_N}); "
                           "the frozen protocol enumerates exactly and never samples")
    total = 1 << n
    t_obs = abs(float(np.sum(diff)))
    signs = np.array(list(itertools.product((1.0, -1.0), repeat=n)), dtype=float)
    stats = np.abs(signs @ diff)
    count = int(np.sum(stats >= t_obs - 1e-12))
    return count / total, total


def bca_bootstrap_ci(diff: np.ndarray, alpha: float = 0.05,
                     resamples: int = BOOTSTRAP_RESAMPLES,
                     seed: int = BOOTSTRAP_SEED) -> Tuple[float, float, str]:
    """95% bias-corrected and accelerated bootstrap CI for the mean paired difference."""
    n = diff.size
    theta_hat = float(np.mean(diff))
    if n < 2:
        return theta_hat, theta_hat, "degenerate(n<2)"
    if float(np.std(diff, ddof=1)) == 0.0:
        # every resample reproduces the same mean; the interval is the point itself
        return theta_hat, theta_hat, "BCa(degenerate: zero variance)"
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(resamples, n))
    boot = diff[idx].mean(axis=1)

    prop = float(np.mean(boot < theta_hat))
    prop = min(max(prop, 1.0 / (2 * resamples)), 1.0 - 1.0 / (2 * resamples))
    z0 = _norm_ppf(prop)

    jack = np.array([np.mean(np.delete(diff, i)) for i in range(n)])
    jbar = jack.mean()
    num = float(np.sum((jbar - jack) ** 3))
    den = 6.0 * (float(np.sum((jbar - jack) ** 2)) ** 1.5)
    acc = 0.0 if den == 0 else num / den

    zl, zu = _norm_ppf(alpha / 2.0), _norm_ppf(1.0 - alpha / 2.0)
    def adj(z):
        d = 1.0 - acc * (z0 + z)
        if d == 0:
            return 0.5
        return _norm_cdf(z0 + (z0 + z) / d)
    a1, a2 = adj(zl), adj(zu)
    lo = float(np.quantile(boot, min(max(a1, 0.0), 1.0)))
    hi = float(np.quantile(boot, min(max(a2, 0.0), 1.0)))
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi, f"BCa({resamples} resamples, seed {seed})"


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |err| < 1.15e-9)."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"p must lie in (0,1), got {p}")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def paired_inference(a: Sequence[float], b: Sequence[float], *,
                     sign_convention: str,
                     keys_a: Sequence | None = None, keys_b: Sequence | None = None,
                     run_test: bool = True,
                     seed: int = BOOTSTRAP_SEED) -> PairedResult:
    """Full frozen paired analysis. `run_test=False` for ESTIMATION endpoints (E1, E2)."""
    diff = _check_pairs(a, b, keys_a, keys_b)
    n = diff.size
    notes: List[str] = []
    p, n_assign, p_method = None, None, "none (estimation endpoint; no test performed)"
    if run_test:
        p, n_assign = exact_sign_flip_p(diff)
        p_method = f"exact paired two-sided sign-flip, all {n_assign:,} assignments enumerated"
    lo, hi, method = bca_bootstrap_ci(diff, seed=seed)
    dz = cohens_dz(diff)
    if dz is None and n >= 2:
        notes.append("Cohen's d_z undefined: zero variance in the paired differences")
    return PairedResult(
        n=n, mean_diff=float(np.mean(diff)),
        sd_diff=float(np.std(diff, ddof=1)) if n > 1 else 0.0,
        ci_low=lo, ci_high=hi, ci_method=method,
        p_value=p, p_method=p_method, n_assignments=n_assign, d_z=dz,
        n_positive=int(np.sum(diff > 0)), n_negative=int(np.sum(diff < 0)),
        n_ties=int(np.sum(diff == 0)),
        sign_convention=sign_convention,
        bootstrap_seed=seed, notes=notes)


def report_nonrejection(res: PairedResult, alpha: float = 0.05) -> str:
    """Frozen reporting wording. A non-rejection is never reported as equivalence."""
    if res.p_value is None:
        return (f"estimate {res.mean_diff:.6g}, 95% CI [{res.ci_low:.6g}, {res.ci_high:.6g}] "
                f"({res.sign_convention}); estimation endpoint, no test performed")
    verdict = "rejected" if res.p_value < alpha else "did not reject"
    return (f"{verdict}; mean paired difference {res.mean_diff:.6g}, "
            f"95% CI [{res.ci_low:.6g}, {res.ci_high:.6g}], p = {res.p_value:.6g} "
            f"({res.sign_convention})")
