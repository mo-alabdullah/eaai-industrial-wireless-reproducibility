#!/usr/bin/env python3
"""Statistical-implementation tests on SYNTHETIC DATA ONLY (master pass, 2026-09-21).

No development H2 value and no final-seed value is used anywhere in this file. Every input is
constructed analytically so that the correct answer is known in advance. This satisfies the
requirement to validate the statistical code before any final data exists.

Run:  python3 test_stats.py
"""
from __future__ import annotations

import math
import sys

import numpy as np

from schema import COMPARATORS, NON_CONTROLLERS, SchemaError, blank_row, fill_comparator_fields, validate_row
from stats import (PairingError, bca_bootstrap_ci, cohens_dz, exact_sign_flip_p,
                   paired_inference, report_nonrejection)

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILS.append(name)


def t_sign_convention():
    a = [1.0, 2.0, 3.0]
    b = [2.0, 4.0, 6.0]
    r = paired_inference(a, b, sign_convention="b minus a", run_test=True)
    check("sign convention: mean_diff = mean(b-a)", abs(r.mean_diff - 2.0) < 1e-12, r.mean_diff)
    r2 = paired_inference(b, a, sign_convention="a minus b", run_test=True)
    check("sign convention: inverting the arguments flips the sign",
          abs(r2.mean_diff + 2.0) < 1e-12, r2.mean_diff)


def t_enumeration_count():
    for n in (1, 5, 12):
        d = np.arange(1.0, n + 1.0)
        _, total = exact_sign_flip_p(d)
        check(f"enumeration count n={n} -> 2^{n}", total == 2 ** n, total)
    # the frozen final case, asserted explicitly
    d20 = np.arange(1.0, 21.0)
    _, total20 = exact_sign_flip_p(d20)
    check("FROZEN: n=20 enumerates 2^20 = 1,048,576", total20 == 1048576, total20)
    check("FROZEN: p-floor at n=20 is 2/2^20", abs(2 / total20 - 1.9073486328125e-06) < 1e-18)


def t_all_ties():
    d = np.zeros(6)
    p, total = exact_sign_flip_p(d)
    check("all ties -> p = 1.0", abs(p - 1.0) < 1e-12, p)
    r = paired_inference([1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1],
                         sign_convention="b minus a", run_test=True)
    check("all ties -> n_ties = n", r.n_ties == 6, r.n_ties)
    check("all ties -> d_z undefined (None)", r.d_z is None, r.d_z)
    check("all ties -> CI collapses to the point estimate",
          abs(r.ci_low) < 1e-12 and abs(r.ci_high) < 1e-12, (r.ci_low, r.ci_high))
    check("all ties -> note recorded", any("undefined" in s for s in r.notes), r.notes)


def t_all_positive():
    n = 10
    d = np.ones(n)
    p, total = exact_sign_flip_p(d)
    # only the all-plus and all-minus assignments attain |T| = n; p = 2/2^n
    check("all positive, equal magnitudes -> p = 2/2^n",
          abs(p - 2.0 / total) < 1e-15, (p, 2.0 / total))
    r = paired_inference(np.zeros(n), d, sign_convention="b minus a", run_test=True)
    check("all positive -> n_positive = n, n_negative = 0",
          r.n_positive == n and r.n_negative == 0, (r.n_positive, r.n_negative))
    check("all positive, zero variance -> d_z undefined", r.d_z is None, r.d_z)


def t_symmetric():
    d = np.array([3.0, -3.0, 1.0, -1.0])
    p, _ = exact_sign_flip_p(d)
    check("symmetric differences -> T_obs = 0 -> p = 1.0", abs(p - 1.0) < 1e-12, p)
    r = paired_inference(np.zeros(4), d, sign_convention="b minus a", run_test=True)
    check("symmetric -> mean_diff = 0", abs(r.mean_diff) < 1e-12, r.mean_diff)
    check("symmetric -> d_z = 0 (sd > 0)", r.d_z is not None and abs(r.d_z) < 1e-12, r.d_z)


def t_dz_known():
    # mean = 5; sum of squared deviations = 32; SAMPLE sd (ddof=1) = sqrt(32/7) = 2.138...
    # POPULATION sd (ddof=0) = sqrt(32/8) = 2.0.  Cohen's d_z takes the SAMPLE sd.
    d = np.array([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    expect = 5.0 / math.sqrt(32.0 / 7.0)
    check("d_z uses the SAMPLE sd (ddof=1) on a known sample",
          abs(cohens_dz(d) - expect) < 1e-12, (cohens_dz(d), expect))
    check("d_z is NOT the population-sd value (ddof guard)",
          abs(cohens_dz(d) - 5.0 / 2.0) > 1e-3, cohens_dz(d))
    check("d_z sd=0 -> None (not inf, not 0)", cohens_dz(np.array([3.0, 3.0, 3.0])) is None)


def t_bca_sanity():
    rng = np.random.default_rng(7)
    d = rng.normal(loc=1.0, scale=1.0, size=200)
    lo, hi, m = bca_bootstrap_ci(d)
    check("BCa brackets the point estimate", lo <= d.mean() <= hi, (lo, d.mean(), hi))
    check("BCa records resamples and seed", "10000" in m and "seed" in m, m)
    lo2, hi2, _ = bca_bootstrap_ci(d)
    check("BCa is deterministic under the fixed seed", (lo, hi) == (lo2, hi2))
    lo3, hi3, m3 = bca_bootstrap_ci(np.full(9, 2.0))
    check("BCa zero-variance -> degenerate point interval",
          abs(lo3 - 2.0) < 1e-12 and abs(hi3 - 2.0) < 1e-12 and "degenerate" in m3, m3)


def t_rejects_bad_pairs():
    try:
        paired_inference([1, 2, 3], [1, 2], sign_convention="b minus a")
        check("unequal lengths rejected", False)
    except PairingError:
        check("unequal lengths rejected", True)
    try:
        paired_inference([1, 2, float("nan")], [1, 2, 3], sign_convention="b minus a")
        check("missing/NaN pair rejected (never imputed)", False)
    except PairingError:
        check("missing/NaN pair rejected (never imputed)", True)
    try:
        paired_inference([1, 2, 3], [4, 5, 6], keys_a=[1, 1, 2], keys_b=[1, 1, 2],
                         sign_convention="b minus a")
        check("duplicate seed key rejected", False)
    except PairingError:
        check("duplicate seed key rejected", True)
    try:
        paired_inference([1, 2, 3], [4, 5, 6], keys_a=[1, 2, 3], keys_b=[3, 2, 1],
                         sign_convention="b minus a")
        check("misordered pairing keys rejected", False)
    except PairingError:
        check("misordered pairing keys rejected", True)
    try:
        paired_inference([], [], sign_convention="b minus a")
        check("empty sample rejected", False)
    except PairingError:
        check("empty sample rejected", True)


def t_estimation_endpoint_has_no_p():
    r = paired_inference([1, 2, 3], [2, 4, 6], sign_convention="b minus a", run_test=False)
    check("estimation endpoint -> p_value is None", r.p_value is None)
    check("estimation endpoint -> no enumeration performed", r.n_assignments is None)
    check("estimation endpoint wording contains no test verdict",
          "did not reject" not in report_nonrejection(r) and "rejected" not in report_nonrejection(r),
          report_nonrejection(r))


def t_reporting_wording():
    r = paired_inference([1, 2, 3, 4], [1, 2, 3, 4], sign_convention="b minus a", run_test=True)
    txt = report_nonrejection(r)
    for banned in ("equivalent", "equal to", "non-inferior", "near-optimal", "no difference"):
        check(f"non-rejection wording avoids '{banned}'", banned not in txt.lower(), txt)
    check("non-rejection wording reports the interval", "95% CI" in txt, txt)


def t_schema():
    row = fill_comparator_fields({**blank_row(), "comparator": "OfflineExactAgedGain"})
    check("registry: offline aged reference is noncausal", row["causal_flag"] is False)
    check("registry: offline aged reference has lookahead", row["lookahead_flag"] is True)
    check("registry: offline aged reference is NOT deployable", row["deployable_flag"] is False)
    row2 = fill_comparator_fields({**blank_row(), "comparator": "BSA-C-PPO"})
    check("registry: learned controller is causal", row2["causal_flag"] is True)
    check("registry: learned controller has no lookahead", row2["lookahead_flag"] is False)
    check("registry: both horizon refs are non-deployable",
          not COMPARATORS["OfflineExactAgedGain"]["deployable"]
          and not COMPARATORS["OfflineExactCurrentGain"]["deployable"])
    check("registry: exactly the five non-controllers are flagged",
          NON_CONTROLLERS == {"ExactFixedDemandRadio", "ExactFreeSelectionRadio",
                              "OfflineExactAgedGain", "OfflineExactCurrentGain",
                              "ContinuousPowerRef"})
    try:
        validate_row({**blank_row(), "comparator": "BSA-C-PPO", "score": 1.0})
        check("ambiguous column 'score' rejected", False)
    except SchemaError:
        check("ambiguous column 'score' rejected", True)
    try:
        r = fill_comparator_fields({**blank_row(), "comparator": "OfflineExactAgedGain"})
        r["causal_flag"] = True
        validate_row(r)
        check("contradicting the frozen registry is rejected", False)
    except SchemaError:
        check("contradicting the frozen registry is rejected", True)
    try:
        r = fill_comparator_fields({**blank_row(), "comparator": "BSA-C-PPO"})
        r.update(endpoint_id="H2", status="COMPLETED", generated=10, delivered=11)
        validate_row(r)
        check("delivered > generated rejected", False)
    except SchemaError:
        check("delivered > generated rejected", True)
    try:
        r = fill_comparator_fields({**blank_row(), "comparator": "ExactFixedDemandRadio"})
        r.update(endpoint_id="Q1", status="COMPLETED",
                 gap_H_G=10.0, gap_C=4.0,
                 term_allocation=3.0, term_quantisation=2.0, term_distortion=0.5)  # sums to 5.5, not 6
        validate_row(r)
        check("three-term identity violation rejected", False)
    except SchemaError:
        check("three-term identity violation rejected", True)
    r = fill_comparator_fields({**blank_row(), "comparator": "ExactFixedDemandRadio"})
    r.update(endpoint_id="Q1", status="COMPLETED",
             gap_H_G=10.0, gap_C=4.0,
             term_allocation=3.0, term_quantisation=2.0, term_distortion=1.0)
    validate_row(r)
    check("valid three-term row accepted", True)


def main():
    print("SYNTHETIC-DATA STATISTICAL VALIDATION  (no development or final values used)\n")
    for fn in (t_sign_convention, t_enumeration_count, t_all_ties, t_all_positive,
               t_symmetric, t_dz_known, t_bca_sanity, t_rejects_bad_pairs,
               t_estimation_endpoint_has_no_p, t_reporting_wording, t_schema):
        print(f"{fn.__name__}:")
        fn()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL SYNTHETIC STATISTICAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
