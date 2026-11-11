#!/usr/bin/env python3
"""AMENDMENT A3 SEED-RESEAL REGRESSION TESTS — synthetic data only (2026-09-21).

Amendment A3 excludes seed 50001 (procedurally exposed by incident I-01) and reseals the
confirmatory set to 50002-50021. n remains 20.

These tests pin that reseal so it cannot silently regress, and confirm that NOTHING in the
statistical implementation changed: n = 20 and the exact sign-flip enumeration remains 2^20.

No final seed is executed. All rows are synthetic.

Run:  python3 test_seed_reseal_a3.py
"""
from __future__ import annotations

import sys

import analyse_final as A
import run_final as R
import schema as S

VALID = tuple(range(50002, 50022))        # the resealed set
EXCLUDED = 50001                          # incident seed, permanently out
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def rows_for(seeds, comparator, outcome, value=10.0):
    out = []
    for i, seed in enumerate(seeds):
        for w in (20, 60, 100, 140, 180):
            r = S.blank_row()
            r.update(schema_version=S.SCHEMA_VERSION, experiment_id=f"x{seed}w{w}",
                     endpoint_id="H2", status="COMPLETED", seed=seed,
                     regime="R3_aged", grid="G2_wide10", K=8, N=4, H=3, warmup=w,
                     comparator=comparator)
            r[outcome] = value + i * 0.01
            S.fill_comparator_fields(r)
            out.append(S.validate_row(r))
    return out


def endpoint_on(seeds):
    a = rows_for(seeds, "EDF+ExactFixedDemand", "realised_delivery", 10.0)
    b = rows_for(seeds, "OfflineExactAgedGain", "realised_delivery", 10.5)
    return A.run_endpoint(a + b, "H2")


# ------------------------------------------------------------------ A-G
def t_A_valid_set_accepted():
    res = endpoint_on(VALID)
    check("A. 50002-50021 ACCEPTED", res["status"] == "OK", res.get("status"))
    check("A. n = 20", res["n"] == 20, res["n"])


def t_B_incident_seed_rejected():
    mixed = (EXCLUDED,) + VALID[:19]      # 50001 + 19 valid members = 20 seeds
    check("B. fixture really has 20 seeds", len(set(mixed)) == 20, len(set(mixed)))
    try:
        endpoint_on(mixed)
        check("B. 50001 + 19 valid REJECTED", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError):
        check("B. 50001 + 19 valid REJECTED", True)


def t_C_short_set_rejected():
    try:
        endpoint_on(VALID[:19])           # 50002-50020 -> n = 19
        check("C. n = 19 REJECTED", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError):
        check("C. n = 19 REJECTED", True)


def t_D_extra_seed_rejected():
    try:
        endpoint_on(VALID + (50022,))     # 21 seeds
        check("D. extra seed REJECTED", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError):
        check("D. extra seed REJECTED", True)


def t_E_duplicate_rejected():
    dup = VALID[:19] + (VALID[0],)        # 50002 twice -> 19 unique
    try:
        endpoint_on(dup)
        check("E. duplicate final seed REJECTED", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError):
        check("E. duplicate final seed REJECTED", True)


def t_F_n_unchanged():
    res = endpoint_on(VALID)
    check("F. H2 sample size remains n = 20", res["n"] == 20, res["n"])
    check("F. EXPECTED_FINAL_SEEDS still 20", A.EXPECTED_FINAL_SEEDS == 20)


def t_G_enumeration_unchanged():
    res = endpoint_on(VALID)
    check("G. exact sign-flip assignments remain 2^20 = 1,048,576",
          res["n_assignments"] == 1048576, res["n_assignments"])
    check("G. statistical method unchanged (exact sign-flip)",
          "sign-flip" in res["p_method"], res["p_method"])


# ------------------------------------------------------------------ guard-level
def t_guard_band():
    check("guard band is [50002, 50021]",
          (R.SEED_GUARD_LO, R.SEED_GUARD_HI) == (50002, 50021),
          (R.SEED_GUARD_LO, R.SEED_GUARD_HI))
    check("FINAL_SEEDS == 50002..50021", R.FINAL_SEEDS == VALID, R.FINAL_SEEDS[:3])
    check("FINAL_SEEDS has exactly 20 members", len(R.FINAL_SEEDS) == 20, len(R.FINAL_SEEDS))
    check("50001 NOT in FINAL_SEEDS", EXCLUDED not in R.FINAL_SEEDS)
    try:
        R.guard_seed(EXCLUDED)
        check("seed guard REJECTS the excluded incident seed 50001", False, "accepted!")
    except R.SeedGuardError as e:
        check("seed guard REJECTS the excluded incident seed 50001", True)
        check("rejection message names Amendment A3", "A3" in str(e), str(e)[:80])
    for s in (50002, 50011, 50021):
        try:
            R.guard_seed(s)
            check(f"seed guard accepts {s}", True)
        except R.SeedGuardError:
            check(f"seed guard accepts {s}", False)
    for s in (10001, 20001, 50000, 50022):
        try:
            R.guard_seed(s)
            check(f"seed guard rejects {s}", False, "accepted!")
        except R.SeedGuardError:
            check(f"seed guard rejects {s}", True)


def t_unit_count_unchanged():
    u = R.study_units()
    check("unit count unchanged at 400", len(u) == 400, len(u))
    check("all unit seeds in the resealed band",
          all(50002 <= x["seed"] <= 50021 for x in u))
    check("no unit uses the excluded seed", not any(x["seed"] == EXCLUDED for x in u))
    check("primary-cell units unchanged at 100",
          sum(1 for x in u if x["is_primary_cell"]) == 100)


def t_analysis_registry():
    check("VALID_FINAL_SEEDS recorded in the analysis module",
          A.VALID_FINAL_SEEDS == frozenset(VALID))
    check("EXCLUDED_INCIDENT_SEEDS records 50001",
          A.EXCLUDED_INCIDENT_SEEDS == frozenset({EXCLUDED}))


def main():
    print("AMENDMENT A3 SEED-RESEAL REGRESSION TESTS (synthetic data only)\n")
    for fn in (t_A_valid_set_accepted, t_B_incident_seed_rejected, t_C_short_set_rejected,
               t_D_extra_seed_rejected, t_E_duplicate_rejected, t_F_n_unchanged,
               t_G_enumeration_unchanged, t_guard_band, t_unit_count_unchanged,
               t_analysis_registry):
        print(f"{fn.__name__}:")
        fn()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL A3 SEED-RESEAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
