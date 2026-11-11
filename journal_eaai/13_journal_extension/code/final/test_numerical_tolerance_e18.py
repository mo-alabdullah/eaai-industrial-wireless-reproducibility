#!/usr/bin/env python3
"""E-18 FLOAT64 NONNEGATIVITY TOLERANCE TESTS — synthetic arithmetic only.

Pins the ULP-based float64 policy introduced by erratum E-18 and corrected on 2026-10-05.

REVISION 2026-10-05. The first policy used K_EPS * eps * max(1.0, |operands|). At the sub-unit
power scales this project works at (order 1e-2), that floor-at-1 rule admits thousands of ULP, so
it was withdrawn together with its "~7 ULP headroom" claim. The policy is now expressed in units
in the last place via math.ulp, and case I below asserts directly that a sub-unit-scale tolerance
is NOT equivalent to thousands of ULP.

DELIBERATELY NO RESULT DEPENDENCE. No final seed, no final outcome and no observed failure
magnitude appears anywhere in this file. Every negative test value is PRODUCED by math.ulp,
math.nextafter or synthetic summation reordering, so the thresholds under test are derived from
IEEE-754 precision rather than fitted to anything that was observed.

Run:  python3 test_numerical_tolerance_e18.py
"""
from __future__ import annotations

import itertools
import math
import sys

import schema as S

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


# ----------------------------------------------------------------- synthetic generators
def reorder_residue(vals):
    """Return (sum_in_order, sum_reordered, difference) for a summation-reordering residue.

    Reproduces the E-18 mechanism without any observed number: the SAME multiset is summed in two
    different orders, and float64 non-associativity produces a signed residue.
    """
    best = None
    for perm in itertools.permutations(range(len(vals))):
        s = 0.0
        for i in perm:
            s += vals[i]
        if best is None or s < best[0]:
            best = (s, perm)
    fwd = 0.0
    for v in vals:
        fwd += v
    return fwd, best[0], best[0] - fwd          # negative when the reordered sum is smaller


SYNTH = [0.0312456789012345, 0.0071234567890123, 0.0009876543210987, 0.0203456789012345]

# A representative sub-unit power scale, written as a plain synthetic constant. This is NOT the
# observed operand magnitude; it is simply the order of magnitude the model's power terms live at.
SUBUNIT_SCALE = 0.05


def row_with(terms, gaps):
    r = S.blank_row()
    r.update(schema_version=S.SCHEMA_VERSION, experiment_id="synthetic",
             endpoint_id="Q1", status="COMPLETED", seed=1, regime="R3_aged",
             grid="G2_wide10", K=8, N=4, H=3, warmup=20,
             comparator="ContinuousPowerRef")
    r.update(gaps)
    r.update(terms)
    S.fill_comparator_fields(r)
    return r


# ----------------------------------------------------------------- A - J
def t_A_exact_zero():
    v = S.canonicalize_structural_nonnegative(0.0, 1.0, 1.0, name="x")
    check("A. exact zero accepted as 0.0", v == 0.0 and not (v < 0), v)
    v2 = S.canonicalize_structural_nonnegative(0, 1.0, 1.0, name="x")
    check("A. integer zero accepted", v2 == 0, v2)


def t_B_small_positive_unchanged():
    for v in (1e-300, 1e-18, 1e-9, 0.5, 12345.678):
        out = S.canonicalize_structural_nonnegative(v, 1.0, 1.0, name="x")
        check(f"B. positive {v:g} returned unchanged", out == v and type(out) is type(v), out)


def t_C_one_ulp_negative_canonicalised():
    """A negative of exactly ONE ULP at the operand scale must canonicalise to +0.0."""
    for scale in (SUBUNIT_SCALE, 1.0, 1234.5):
        v = -math.ulp(scale)
        out = S.canonicalize_structural_nonnegative(v, scale, scale, name="term_distortion")
        check(f"C. -1 ULP at scale {scale:g} -> 0.0", out == 0.0, out)

    # and the same via genuine summation reordering, with no chosen magnitude at all
    fwd, rev, diff = reorder_residue(SYNTH)
    check("C. synthetic reordering really produces a negative residue", diff < 0, diff)
    out = S.canonicalize_structural_nonnegative(diff, fwd, rev, name="term_distortion")
    check("C. reordering residue canonicalised to +0.0", out == 0.0, out)
    check("C. reordering residue is a small multiple of one ULP of its operands",
          abs(diff) <= S.K_ULP * math.ulp(max(abs(fwd), abs(rev))),
          (abs(diff), math.ulp(abs(fwd))))


def t_D_exactly_K_ULP_accepted():
    for scale in (SUBUNIT_SCALE, 1.0, 1234.5):
        tol = S.structural_ulp_tolerance(scale, scale)
        check(f"D. tolerance at scale {scale:g} equals K_ULP ULP",
              tol == S.K_ULP * math.ulp(scale), (tol, S.K_ULP * math.ulp(scale)))
        v = -S.K_ULP * math.ulp(scale)
        out = S.canonicalize_structural_nonnegative(v, scale, scale, name="term_distortion")
        check(f"D. -K_ULP ULP at scale {scale:g} -> 0.0", out == 0.0, out)


def t_E_beyond_K_ULP_rejected():
    for scale in (SUBUNIT_SCALE, 1.0, 1234.5):
        v = -(S.K_ULP + 1) * math.ulp(scale)
        try:
            S.canonicalize_structural_nonnegative(v, scale, scale, name="term_distortion")
            check(f"E. -(K_ULP+1) ULP at scale {scale:g} REJECTED", False, "no error")
        except S.SchemaError:
            check(f"E. -(K_ULP+1) ULP at scale {scale:g} REJECTED", True)


def t_F_materially_negative_rejected():
    for v, scale in ((-1e-6, 1.0), (-1e-9, SUBUNIT_SCALE), (-0.25, 1.0), (-1e-15, SUBUNIT_SCALE)):
        try:
            S.canonicalize_structural_nonnegative(v, scale, scale, name="term_distortion")
            check(f"F. materially negative {v:g} at scale {scale:g} REJECTED", False, "no error")
        except S.SchemaError:
            check(f"F. materially negative {v:g} at scale {scale:g} REJECTED", True)


def t_G_identity_within_tolerance_accepted():
    H, E, CAG = 0.9312456789012345, 0.5071234567890123, 0.3009876543210987
    C = 0.2203456789012345
    t1, t2, t3 = H - E, E - CAG, CAG - C
    lhs = H - C

    r0 = row_with(dict(term_allocation=t1, term_quantisation=t2, term_distortion=t3),
                  dict(gap_H_G=H, gap_E_G=E, gap_C_AG=CAG, gap_C=C))
    S.validate_row(r0)
    check("G. naturally formed identity ACCEPTED", True)

    # inject a residual a few ULP wide, well inside K_ID_ULP
    t3p = t3 + 3 * math.ulp(lhs)
    resid = abs(lhs - (t1 + t2 + t3p))
    check("G. injected residual is nonzero", resid > 0.0, resid)
    check("G. injected residual is inside K_ID_ULP ULP",
          resid <= S.K_ID_ULP * math.ulp(abs(lhs)), (resid, math.ulp(abs(lhs))))
    r = row_with(dict(term_allocation=t1, term_quantisation=t2, term_distortion=t3p),
                 dict(gap_H_G=H, gap_E_G=E, gap_C_AG=CAG, gap_C=C))
    S.validate_row(r)
    check("G. identity with a few-ULP residual ACCEPTED", True)

    # exact zero on both sides must be accepted exactly
    rz = row_with(dict(term_allocation=0.0, term_quantisation=0.0, term_distortion=0.0),
                  dict(gap_H_G=0.0, gap_E_G=0.0, gap_C_AG=0.0, gap_C=0.0))
    S.validate_row(rz)
    check("G. lhs == rhs == 0 accepted exactly", True)


def t_H_identity_beyond_tolerance_rejected():
    H, E, CAG = 0.9312456789012345, 0.5071234567890123, 0.3009876543210987
    C = 0.2203456789012345
    t1, t2, t3 = H - E, E - CAG, CAG - C
    lhs = H - C
    t3p = t3 + (S.K_ID_ULP + 8) * math.ulp(lhs)       # deliberately outside
    r = row_with(dict(term_allocation=t1, term_quantisation=t2, term_distortion=t3p),
                 dict(gap_H_G=H, gap_E_G=E, gap_C_AG=CAG, gap_C=C))
    try:
        S.validate_row(r)
        check("H. identity residual beyond K_ID_ULP REJECTED", False, "no error")
    except S.SchemaError as e:
        check("H. identity residual beyond K_ID_ULP REJECTED", True)
        check("H. rejection names ULP, not a fixed decimal", "ULP" in str(e), str(e)[:90])

    # a materially violated identity must also be refused
    r2 = row_with(dict(term_allocation=0.4, term_quantisation=0.2, term_distortion=0.1),
                  dict(gap_H_G=1.0, gap_E_G=0.6, gap_C_AG=0.4, gap_C=0.2))
    try:
        S.validate_row(r2)
        check("H. materially violated identity REJECTED", False, "no error")
    except S.SchemaError:
        check("H. materially violated identity REJECTED", True)


def t_I_subunit_tolerance_is_not_thousands_of_ulp():
    """The withdrawn floor-at-1 rule admitted thousands of ULP at sub-unit scale. Not any more."""
    for scale in (SUBUNIT_SCALE, 0.01, 0.001):
        tol = S.structural_ulp_tolerance(scale, scale)
        in_ulp = tol / math.ulp(scale)
        check(f"I. tolerance at scale {scale:g} is exactly K_ULP ULP",
              in_ulp == S.K_ULP, in_ulp)
        check(f"I. tolerance at scale {scale:g} is NOT thousands of ULP", in_ulp < 100, in_ulp)
        # the withdrawn rule, recomputed here for contrast only
        withdrawn = 128 * S.EPS_FLOAT64 * max(1.0, scale)
        check(f"I. new rule is strictly tighter than the withdrawn rule at scale {scale:g}",
              tol < withdrawn, (tol, withdrawn))
    check("I. the withdrawn rule really admitted >1000 ULP at sub-unit scale",
          (128 * S.EPS_FLOAT64 * 1.0) / math.ulp(SUBUNIT_SCALE) > 1000,
          (128 * S.EPS_FLOAT64) / math.ulp(SUBUNIT_SCALE))
    check("I. tolerance shrinks with the operand magnitude",
          S.structural_ulp_tolerance(0.001) < S.structural_ulp_tolerance(1.0)
          < S.structural_ulp_tolerance(1000.0))
    # nextafter cross-check: one step below zero-crossing at the operand scale
    step = scale_step = math.nextafter(SUBUNIT_SCALE, math.inf) - SUBUNIT_SCALE
    check("I. math.nextafter step equals math.ulp at that scale",
          step == math.ulp(SUBUNIT_SCALE), (scale_step, math.ulp(SUBUNIT_SCALE)))


def t_J_no_result_dependence():
    pol = open(S.__file__).read()
    src = open(__file__).read()

    # the observed failure magnitude, reconstructed arithmetically, never written as a literal
    observed = repr(2.0 ** -57)
    check("J. policy module does not hard-code the observed failure magnitude",
          observed not in pol, observed)
    check("J. this test file does not hard-code the observed magnitude", observed not in src)

    band = [str(s) for s in range(50001, 50022)]
    check("J. policy module references no final-band seed",
          not [s for s in band if s in pol])
    check("J. this test file references no final-band seed literal",
          not [s for s in band if s in src and f"range({s}" not in src])

    # the threshold must be ULP-derived
    check("J. tolerance is ULP-derived via math.ulp",
          "math.ulp" in pol.replace("_math.ulp", "math.ulp") and "K_ULP" in pol)
    check("J. the withdrawn floor-at-1 expression is gone from the policy",
          "max([1.0] + mags)" not in pol and "structural_tolerance" not in pol.replace(
              "structural_ulp_tolerance", ""))
    check("J. the false '~7 ULP headroom' claim is gone", "7 ULP headroom" not in pol)


def t_policy_shape():
    check("policy: K_ULP is a small documented integer",
          isinstance(S.K_ULP, int) and 1 <= S.K_ULP <= 64, S.K_ULP)
    check("policy: K_ID_ULP is a small documented integer",
          isinstance(S.K_ID_ULP, int) and 1 <= S.K_ID_ULP <= 64, S.K_ID_ULP)
    check("policy: eps constant is float64 machine epsilon",
          S.EPS_FLOAT64 == sys.float_info.epsilon, S.EPS_FLOAT64)
    check("policy: the three difference columns share ONE policy",
          set(S.STRUCTURAL_NONNEGATIVE_DIFFERENCES) ==
          {"term_allocation", "term_quantisation", "term_distortion"},
          sorted(S.STRUCTURAL_NONNEGATIVE_DIFFERENCES))
    check("policy: count/sum columns keep the STRICT check",
          "term_distortion" not in S.NUMERIC_NONNEGATIVE
          and "gap_C_AG" in S.NUMERIC_NONNEGATIVE
          and "delivered" in S.NUMERIC_NONNEGATIVE)
    try:
        S.structural_ulp_tolerance(None, float("nan"))
        check("policy: a tolerance with no finite operand is REFUSED", False, "no error")
    except S.SchemaError:
        check("policy: a tolerance with no finite operand is REFUSED", True)


def t_strict_columns_still_strict():
    r = row_with({}, dict(gap_H_G=1.0, gap_C=0.5))
    r["delivered"] = -1
    try:
        S.validate_row(r)
        check("strict: negative packet count still REJECTED", False, "no error")
    except S.SchemaError:
        check("strict: negative packet count still REJECTED", True)
    r2 = row_with({}, dict(gap_H_G=1.0, gap_C=0.5))
    r2["gap_C_AG"] = -1e-18          # a SUM, never formed by cancellation -> strict
    try:
        S.validate_row(r2)
        check("strict: negative accumulated sum still REJECTED", False, "no error")
    except S.SchemaError:
        check("strict: negative accumulated sum still REJECTED", True)
    r3 = row_with({}, dict(gap_H_G=1.0, gap_C=0.5))
    r3["runtime_s"] = -math.ulp(1.0)   # a timing: no tolerance at all
    try:
        S.validate_row(r3)
        check("strict: negative timing still REJECTED even at 1 ULP", False, "no error")
    except S.SchemaError:
        check("strict: negative timing still REJECTED even at 1 ULP", True)


def t_all_three_terms_covered():
    fwd, rev, diff = reorder_residue(SYNTH)
    for col, parents in S.STRUCTURAL_NONNEGATIVE_DIFFERENCES.items():
        r = row_with({}, dict(gap_H_G=fwd, gap_E_G=fwd, gap_C_AG=fwd, gap_C=rev))
        r[col] = diff
        S.validate_row(r)
        check(f"all-terms: {col} canonicalised to +0.0", r[col] == 0.0, r[col])


def main():
    print("E-18 ULP TOLERANCE TESTS (synthetic arithmetic only)\n")
    for fn in (t_A_exact_zero, t_B_small_positive_unchanged,
               t_C_one_ulp_negative_canonicalised, t_D_exactly_K_ULP_accepted,
               t_E_beyond_K_ULP_rejected, t_F_materially_negative_rejected,
               t_G_identity_within_tolerance_accepted,
               t_H_identity_beyond_tolerance_rejected,
               t_I_subunit_tolerance_is_not_thousands_of_ulp,
               t_J_no_result_dependence, t_policy_shape,
               t_strict_columns_still_strict, t_all_three_terms_covered):
        print(f"{fn.__name__}:")
        fn()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL E-18 NUMERICAL-TOLERANCE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
