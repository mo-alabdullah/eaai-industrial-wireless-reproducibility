#!/usr/bin/env python3
"""ANTI-PSEUDOREPLICATION TESTS on SYNTHETIC DATA ONLY (2026-09-21).

Proves that the analysis pipeline cannot treat sub-seed execution units as independent
statistical replicates. Constructs the exact failure mode the protocol warns about — 20 seeds x
5 warm-ups = 100 rows per comparator in the primary cell — and asserts that the pipeline
collapses to n = 20 and enumerates 2^20, not 2^100.

No development value and no final value is used. Run:  python3 test_pairing.py
"""
from __future__ import annotations

import sys

import analyse_final as A
import schema as S

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def synth_rows(comparator, outcome, n_seeds=20, n_warm=5, regime="R3_aged", grid="G2_wide10",
               base=10.0, per_seed=0.1):
    rows = []
    for i, seed in enumerate(range(50002, 50002 + n_seeds)):
        for w in (20, 60, 100, 140, 180)[:n_warm]:
            r = S.blank_row()
            r.update(schema_version=S.SCHEMA_VERSION, experiment_id=f"x{seed}w{w}",
                     endpoint_id="H2", status="COMPLETED", seed=seed, regime=regime, grid=grid,
                     K=8, N=4, H=3, warmup=w, comparator=comparator)
            r[outcome] = base + i * per_seed
            S.fill_comparator_fields(r)
            rows.append(S.validate_row(r))
    return rows


def t_collapse():
    rows = synth_rows("EDF+ExactFixedDemand", "realised_delivery")
    check("synthetic set really is 100 execution units", len(rows) == 100, len(rows))
    sl = A.seed_level(rows, "EDF+ExactFixedDemand", "realised_delivery", "R3_aged", "G2_wide10")
    check("collapses 100 units -> 20 seed-level values", len(sl) == 20, len(sl))
    check("collapse preserves the per-seed value",
          abs(sl[50002] - 10.0) < 1e-12 and abs(sl[50021] - 11.9) < 1e-12,
          (sl[50002], sl[50021]))


def t_h2_enumeration_is_2pow20():
    a = synth_rows("EDF+ExactFixedDemand", "realised_delivery", base=10.0, per_seed=0.0)
    b = synth_rows("OfflineExactAgedGain", "realised_delivery", base=10.5, per_seed=0.0)
    res = A.run_endpoint(a + b, "H2")
    check("H2 n = 20 (not 100)", res["n"] == 20, res["n"])
    check("H2 enumerates 2^20 = 1,048,576 (not 2^100)",
          res["n_assignments"] == 1048576, res["n_assignments"])
    check("H2 sign convention recorded", "minus" in res["sign_convention"], res["sign_convention"])


def t_gate_blocks_inflated_n():
    """The failure mode: 100 distinct seeds reaching the primary endpoint."""
    a = synth_rows("EDF+ExactFixedDemand", "realised_delivery", n_seeds=20, n_warm=5)
    b = synth_rows("OfflineExactAgedGain", "realised_delivery", n_seeds=20, n_warm=5)
    # forge distinct seeds per warm-up, i.e. exactly the pseudoreplication error
    for r in a + b:
        r["seed"] = r["seed"] * 100 + r["warmup"]
    try:
        A.run_endpoint(a + b, "H2")
        check("gate blocks n > 20 at the primary endpoint", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError) as e:
        check("gate blocks n > 20 at the primary endpoint", True)
        print(f"        raised: {type(e).__name__}: {str(e)[:84]}...")


def t_gate_blocks_short_n():
    a = synth_rows("EDF+ExactFixedDemand", "realised_delivery", n_seeds=12)
    b = synth_rows("OfflineExactAgedGain", "realised_delivery", n_seeds=12)
    try:
        A.run_endpoint(a + b, "H2")
        check("gate blocks n < 20 at the primary endpoint", False, "no error raised")
    except (A.PseudoreplicationError, A.SeedSetError):
        # Either gate is a correct rejection; the A3 seed-set gate fires first.
        check("gate blocks n < 20 at the primary endpoint", True)


def t_gate_blocks_excess_warmups():
    rows = synth_rows("EDF+ExactFixedDemand", "realised_delivery", n_warm=5)
    rows += synth_rows("EDF+ExactFixedDemand", "realised_delivery", n_warm=5)  # duplicated units
    try:
        A.seed_level(rows, "EDF+ExactFixedDemand", "realised_delivery", "R3_aged", "G2_wide10")
        check("gate blocks an unexpected replication structure", False, "no error raised")
    except A.PseudoreplicationError:
        check("gate blocks an unexpected replication structure", True)


def t_estimation_endpoints_have_no_test():
    for eid, left, right in (("E1", "EDF-StaleBeam-MinFeasible", "ExactFixedDemandRadio"),
                             ("E2", "OfflineExactAgedGain", "OfflineExactCurrentGain")):
        out = "aggregate_power_w" if eid == "E1" else "realised_delivery"
        a = synth_rows(left, out, base=5.0, per_seed=0.0)
        b = synth_rows(right, out, base=4.0, per_seed=0.0)
        for r in a + b:
            r["endpoint_id"] = eid
        res = A.run_endpoint(a + b, eid)
        check(f"{eid} n = 20", res["n"] == 20, res["n"])
        check(f"{eid} has NO p-value", res["p_value"] is None, res["p_value"])
        check(f"{eid} performs NO enumeration", res["n_assignments"] is None, res["n_assignments"])


def main():
    print("ANTI-PSEUDOREPLICATION TESTS  (synthetic data only)\n")
    for fn in (t_collapse, t_h2_enumeration_is_2pow20, t_gate_blocks_inflated_n,
               t_gate_blocks_short_n, t_gate_blocks_excess_warmups,
               t_estimation_endpoints_have_no_test):
        print(f"{fn.__name__}:")
        fn()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL ANTI-PSEUDOREPLICATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
