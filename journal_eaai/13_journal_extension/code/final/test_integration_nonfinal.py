#!/usr/bin/env python3
"""END-TO-END C10 INTEGRATION TEST on NON-FINAL DATA ONLY (2026-09-21).

Exercises the REAL execution core — `run_final.run_unit_core` — with an explicitly NON-FINAL
development seed. The production CLI's final-seed guard is NOT weakened or bypassed: the guard
lives in `run_unit`, and this test calls the shared core underneath it, so the same environment
construction, trace recording, comparator evaluation, exact references, schema construction,
serialisation and pairing identifiers are used without duplicating the implementation.

SEED USED: 10001 — a declared DEVELOPMENT seed. Never 50002-50021 (the resealed band).
Outputs go to a temporary directory and never enter results_final/raw/.

Run:  python3 test_integration_nonfinal.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import analyse_final as A            # noqa: E402
import ledger as L                   # noqa: E402
import run_final as R                # noqa: E402
import schema as S                   # noqa: E402

NON_FINAL_SEEDS = (10001, 10002)     # development band; asserted below
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def tiny_unit(seed: int, warmup: int):
    """Smallest scientifically representative fixture: reduced K/N/H, short warm-up."""
    assert not (50002 <= seed <= 50021), "integration fixture must never use a final seed"
    return dict(regime="R3_aged", grid="G2_wide10", seed=seed, warmup=warmup,
                K=4, N=2, H=2, load=0.40, dist=2.0, d_csi=5, is_primary_cell=True)


def tiny_cfg(u):
    """Reduced-scale config; mirrors build_cfg but at integration size."""
    import dataclasses
    from evaluation import journal_cfg
    from optimization.grids import with_grid
    cfg = journal_cfg(u["load"], t_meas=200, hall_x=300.0 * u["dist"], hall_y=150.0 * u["dist"],
                      d_csi_slots=u["d_csi"])
    cfg = with_grid(cfg, u["grid"])
    return dataclasses.replace(cfg, n_static=3, n_mobile=1, n_subchannels=2,
                               n_max_static=2, n_max_mobile=1)


PF = dict(runner_sha256="integration-test", config_sha256="integration-test", n_units=0)
DIGEST = "integration-test-digest"


def run_fixture(seed, warmup, monkeypatched_build=True):
    if monkeypatched_build:
        R.build_cfg = tiny_cfg                      # reduced scale for the integration run
    return R.run_unit_core(tiny_unit(seed, warmup), PF, DIGEST)


# ------------------------------------------------------------------ tests
def _raw_inventory():
    """Byte-level inventory of results_final/raw. Hashes only; no file is parsed."""
    import hashlib
    rf = Path(R.OUTDIR) / "raw"
    if not rf.exists():
        return {}
    return {str(p.relative_to(rf)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(rf.rglob("*.json"))}


def _fixture_rejects_final_seed() -> bool:
    try:
        tiny_unit(50002, 20)
        return False
    except AssertionError:
        return True


def t_guard_still_enforced():
    """Production entry point must refuse ad-hoc invocation, and must reject non-final seeds.

    NOTE (incident I-01): an earlier version of this test asserted that run_unit() rejects a final
    seed. That assertion was WRONG — the guard ACCEPTS final seeds, which the guard is designed
    to accept — and probing it executed the core on a final seed. The interlock added afterwards
    makes that impossible, and the assertions below are the correct ones.
    """
    # 1. ad-hoc invocation is refused BEFORE any seed logic, so no final-band work can start.
    #    The probe dict is built directly: tiny_unit() asserts non-final seeds, which is itself a
    #    third protection layer and would otherwise mask the interlock under test.
    probe = dict(regime="R3_aged", grid="G2_wide10", seed=50002, warmup=20,
                 K=4, N=2, H=2, load=0.40, dist=2.0, d_csi=5, is_primary_cell=True)
    try:
        R.run_unit(probe, PF, DIGEST)
        check("run_unit refuses ad-hoc invocation (interlock)", False, "no error raised")
    except R.ExecutionNotSanctionedError:
        check("run_unit refuses ad-hoc invocation (interlock)", True)
    except Exception as e:
        check("run_unit refuses ad-hoc invocation (interlock)", False, f"{type(e).__name__}: {e}")
    check("tiny_unit() itself refuses a final seed (defence in depth)",
          _fixture_rejects_final_seed())

    # 2. even once sanctioned, a NON-FINAL seed is rejected by the seed guard
    saved = R._EXECUTION_SANCTIONED
    try:
        R._sanction_execution()
        try:
            R.run_unit(tiny_unit(10001, 20), PF, DIGEST)
            check("sanctioned run_unit still rejects a NON-FINAL seed", False, "no error raised")
        except R.SeedGuardError:
            check("sanctioned run_unit still rejects a NON-FINAL seed", True)
    finally:
        R._EXECUTION_SANCTIONED = saved
    check("interlock restored after the probe", R._EXECUTION_SANCTIONED is False)

    # 3. the documented test path uses a NON-FINAL seed
    check("integration fixture seeds are all NON-FINAL",
          all(not (50002 <= s <= 50021) for s in NON_FINAL_SEEDS))


def t_end_to_end(rows):
    check("execution core produced rows", len(rows) > 0, len(rows))
    comps = {r["comparator"] for r in rows}
    for needed in ("EDF-StaleBeam-MinFeasible", "EDF+ExactFixedDemand", "ExactFixedDemandRadio",
                   "OfflineExactAgedGain", "OfflineExactCurrentGain"):
        check(f"comparator exercised: {needed}", needed in comps)
    eids = {r["endpoint_id"] for r in rows}
    for e in ("E1", "H2", "E2"):
        check(f"endpoint fields produced: {e}", e in eids)
    for r in rows:
        S.validate_row(r)
    check("every row validates against the canonical schema", True)
    rt = [r for r in rows if r.get("runtime_s") is not None]
    check("runtime fields populated", len(rt) == len(rows), f"{len(rt)}/{len(rows)}")
    check("status fields populated", all(r["status"] == "COMPLETED" for r in rows))


def t_shared_trace(rows):
    ids = {r["experiment_id"] for r in rows}
    check("ALL comparators share ONE trace identifier", len(ids) == 1, sorted(ids))


def t_trace_sequences_identical():
    """Two recordings with the same seed/warm-up must be bit-identical -> one trace per unit."""
    import numpy as np
    from optimization.joint import record_trace
    u = tiny_unit(NON_FINAL_SEEDS[0], 20)
    cfg = tiny_cfg(u)
    ts = R.TRACE_SEED_NAMESPACE + u["seed"] * 100
    a = record_trace(cfg, seed=ts, H=u["H"], warmup=u["warmup"])
    b = record_trace(cfg, seed=ts, H=u["H"], warmup=u["warmup"])
    check("identical arrival sequence", a.arrivals == b.arrivals)
    check("identical beta sequence", a.beta == b.beta)
    check("identical realised beam-gain sequence",
          all(np.array_equal(x, y) for x, y in zip(a.gain_true, b.gain_true)))
    check("identical aged beam-gain sequence",
          all(np.array_equal(x, y) for x, y in zip(a.gain_info, b.gain_info)))
    check("aged and realised tensors genuinely DIFFER (d_CSI > 0)",
          not all(np.array_equal(x, y) for x, y in zip(a.gain_info, a.gain_true)))


def t_offline_reference_inputs():
    """Aged plans on gain_info only; current plans on gain_true. All else identical."""
    import dataclasses as dc
    import numpy as np
    from optimization.joint import record_trace, solve_exact_joint
    u = tiny_unit(NON_FINAL_SEEDS[0], 20)
    cfg = tiny_cfg(u)
    tr = record_trace(cfg, seed=R.TRACE_SEED_NAMESPACE + u["seed"] * 100, H=u["H"],
                      warmup=u["warmup"])
    _, _, _, _, plan_aged = solve_exact_joint(tr, use_true=False, return_plan=True)
    # perturb ONLY gain_true; the aged plan must be unchanged
    rng = np.random.default_rng(3)
    pert = dc.replace(tr, gain_true=tuple(g * np.exp(rng.normal(0, 0.9, size=g.shape))
                                          for g in tr.gain_true))
    _, _, _, _, plan_aged2 = solve_exact_joint(pert, use_true=False, return_plan=True)
    check("AGED reference does not read gain_true for planning", plan_aged == plan_aged2)
    _, _, _, _, plan_cur = solve_exact_joint(tr, use_true=True, return_plan=True)
    _, _, _, _, plan_cur2 = solve_exact_joint(pert, use_true=True, return_plan=True)
    check("CURRENT reference DOES read gain_true (plan changes when it changes)",
          plan_cur != plan_cur2)
    check("both references see the same complete trace (same H, arrivals, beta)",
          tr.H == pert.H and tr.arrivals == pert.arrivals and tr.beta == pert.beta)


def t_aggregation_pipeline(all_rows):
    """Real analysis aggregation: warm-ups collapse to one observation per seed."""
    sl = A.seed_level(all_rows, "EDF+ExactFixedDemand", "realised_delivery",
                      "R3_aged", "G2_wide10")
    n_units = sum(1 for r in all_rows
                  if r["comparator"] == "EDF+ExactFixedDemand" and r["status"] == "COMPLETED")
    check(f"H2 left side: {n_units} units -> {len(sl)} seed-level observations",
          len(sl) == len(NON_FINAL_SEEDS) and n_units > len(sl), (n_units, len(sl)))
    sr = A.seed_level(all_rows, "OfflineExactAgedGain", "realised_delivery",
                      "R3_aged", "G2_wide10")
    check("H2 observations = unique seeds, never seeds x warm-ups",
          len(sl) == len(sr) == len(NON_FINAL_SEEDS), (len(sl), len(sr)))

    e1 = A.seed_level(all_rows, "ExactFixedDemandRadio", "aggregate_power_w",
                      "R3_aged", "G2_wide10")
    check("E1: state-level gaps collapse to one seed-level estimate per seed",
          len(e1) == len(NON_FINAL_SEEDS), len(e1))

    ea = A.seed_level(all_rows, "OfflineExactAgedGain", "realised_delivery", "R3_aged", "G2_wide10")
    ec = A.seed_level(all_rows, "OfflineExactCurrentGain", "realised_delivery", "R3_aged", "G2_wide10")
    check("E2: aged/current pair on identical seed keys", set(ea) == set(ec), (sorted(ea), sorted(ec)))
    check("E2: one paired difference per seed", len(ea) == len(NON_FINAL_SEEDS))

    # the n=20 gate must fire on this small fixture -> proves the gate is live end-to-end
    try:
        A.run_endpoint(all_rows, "H2")
        check("primary-endpoint gate fires on a non-final fixture", False, "no error")
    except (A.PseudoreplicationError, A.SeedSetError) as e:
        # Development seeds are not the resealed A3 set, so the seed-set gate fires first;
        # either rejection proves the primary-endpoint gates are live end-to-end.
        check("primary-endpoint gate fires on a non-final fixture", True)
        print(f"        raised: {type(e).__name__}")


def t_serialization_round_trip(rows, tmp: Path):
    p = tmp / "R3_aged" / "G2_wide10" / "s10001_w20.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    orig_raw = A.RAW
    try:
        A.RAW = tmp
        back = A.load_rows()
    finally:
        A.RAW = orig_raw
    check("round-trip row count preserved", len(back) == len(rows), (len(back), len(rows)))
    b0 = {r["comparator"]: r for r in back}
    a0 = {r["comparator"]: r for r in rows}
    check("seed stays an integer after round-trip",
          all(isinstance(r["seed"], int) for r in back))
    check("comparator labels remain canonical",
          all(r["comparator"] in S.COMPARATORS for r in back))
    check("causal/lookahead/deployable flags match the registry",
          all(r["causal_flag"] == S.COMPARATORS[r["comparator"]]["causal"]
              and r["lookahead_flag"] == S.COMPARATORS[r["comparator"]]["lookahead"]
              and r["deployable_flag"] == S.COMPARATORS[r["comparator"]]["deployable"]
              for r in back))
    check("required hashes present", all(r["freeze_manifest_sha256"] for r in back))
    check("no ambiguous columns", not any(S.FORBIDDEN_COLUMNS & set(r) for r in back))
    check("no silent NaN imputation (None stays None)",
          all((a0[c].get("believed_delivery") is None) == (b0[c].get("believed_delivery") is None)
              for c in a0))
    check("numeric values preserved exactly",
          all(a0[c]["realised_delivery"] == b0[c]["realised_delivery"]
              for c in a0 if a0[c].get("realised_delivery") is not None))


def t_failure_and_censor_paths(tmp: Path):
    """Exercise FAILED and CENSORED without final data, on an isolated ledger."""
    orig = L.LEDGER
    try:
        L.LEDGER = tmp / "TEST_LEDGER.jsonl"
        uid = L.unit_id(seed=10001, regime="R3_aged", grid="G2_wide10", comparator="ALL",
                        K=4, N=2, H=2, warmup=20)
        common = dict(unit=uid, seed=10001, regime="R3_aged", grid="G2_wide10",
                      comparator="ALL", K=4, N=2, H=2, warmup=20,
                      freeze_digest=DIGEST, runner_sha256="t", config_sha256="t")
        L.append("PLANNED", **common)
        L.append("STARTED", **common)
        L.append("FAILED", failure_reason="synthetic integration failure", **common)
        n_after_fail = len(L.read_all())
        L.append("CENSORED", censor_reason="synthetic budget exhaustion", **common)
        rows = L.read_all()
        check("ledger appends FAILED and CENSORED rows", len(rows) == 4, len(rows))
        check("FAILED history is retained after CENSORED is appended",
              any(r["state"] == "FAILED" for r in rows) and len(rows) > n_after_fail)
        check("censored unit produced no substituted value",
              all(r.get("output_path") is None for r in rows))
        # rerun requires an explicit supersession reason
        try:
            L.append("COMPLETED", supersedes=uid, **common)
            check("supersession without a reason is rejected", False, "no error")
        except L.LedgerError:
            check("supersession without a reason is rejected", True)
        L.append("COMPLETED", supersedes=uid, supersession_reason="synthetic rerun after fix",
                 **common)
        check("supersession is append-only (old rows survive)", len(L.read_all()) == 5)
        # analysis must reject an incomplete primary dataset
        rep = L.completeness_report([uid, uid + "|missing"])
        check("completeness report flags an incomplete dataset", not rep["complete"], rep)
    finally:
        L.LEDGER = orig


def main():
    print("END-TO-END INTEGRATION TEST — NON-FINAL DATA ONLY (development seeds 10001/10002)\n")
    tmp = Path(tempfile.mkdtemp(prefix="integration_nonfinal_"))
    raw_before = _raw_inventory()
    try:
        print("t_guard_still_enforced:"); t_guard_still_enforced()

        print("\nrunning the REAL execution core on non-final fixtures ...")
        all_rows = []
        first = None
        for seed in NON_FINAL_SEEDS:
            for w in (20, 40, 60, 80, 100):          # five warm-ups, as in the real design
                rws = run_fixture(seed, w)
                all_rows += rws
                if first is None:
                    first = rws
        print(f"  produced {len(all_rows)} rows "
              f"from {len(NON_FINAL_SEEDS)} seeds x 5 warm-ups\n")

        print("t_end_to_end:"); t_end_to_end(first)
        print("t_shared_trace:"); t_shared_trace(first)
        print("t_trace_sequences_identical:"); t_trace_sequences_identical()
        print("t_offline_reference_inputs:"); t_offline_reference_inputs()
        print("t_aggregation_pipeline:"); t_aggregation_pipeline(all_rows)
        print("t_serialization_round_trip:"); t_serialization_round_trip(first, tmp)
        print("t_failure_and_censor_paths:"); t_failure_and_censor_paths(tmp)

        print("\nt_no_final_contamination:")
        # NOTE: results_final/raw legitimately EXISTS once the real campaign has run, so its
        # mere presence is not contamination. The correct invariant is that THIS TEST adds
        # nothing to it and alters nothing in it.
        check("integration test added no file to results_final/raw",
              _raw_inventory() == raw_before, "raw/ inventory changed")
        check("no final seed in any produced row",
              not any(50002 <= r["seed"] <= 50021 for r in all_rows))
        check("no row was written under results_final/",
              not (Path(R.OUTDIR) / "raw" / "R3_aged" / "G2_wide10"
                   / "s10001_w20.json").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL END-TO-END INTEGRATION TESTS PASSED (non-final data only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
