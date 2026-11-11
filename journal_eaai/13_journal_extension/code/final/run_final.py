#!/usr/bin/env python3
"""C10 — FINAL CONFIRMATORY RUNNER (rebuilt 2026-09-21, execution bodies implemented).

Executes the frozen final study on FINAL TEST seeds 50002-50021 and nothing else.
(Amendment A3, 2026-09-21: 50001 was procedurally exposed by incident I-01 and is
permanently excluded; 50021 replaces it mechanically. n remains 20.)

2026-09-21 AMENDMENT: the pre-execution development barrier was removed after author approval;
the scientific configuration is unchanged. Seeds, regimes, grids, comparators, endpoints, budgets
and the statistical plan are identical to the frozen protocol. See ERRATA_APPEND_ONLY.md E-13.

UNIT OF EXECUTION = (regime, grid, seed, warm-up).
Each unit records ONE trace and evaluates EVERY comparator on that same trace, so the paired
endpoints are paired on an identical realisation BY CONSTRUCTION rather than by convention. This
is what makes H2 and E2 legitimate paired comparisons.
    2 regimes x 2 grids x 20 seeds x 5 warm-ups = 400 units -> up to 2,400 schema rows.

SAFETY PROPERTIES, enforced in code:
  * SEED GUARD    - anything outside 50002-50021 raises; no override flag exists;
                    50001 is PERMANENTLY EXCLUDED (incident I-01 / Amendment A3);
  * FREEZE GUARD  - refuses to run unless the C13 manifest matches exactly;
  * NO DEFAULTS   - a missing frozen configuration input raises;
  * NO MUTATION   - per-unit config copies; nothing writes back;
  * NO OVERWRITE  - an existing unit output is never clobbered;
  * METADATA/PLAN FIRST - run metadata and PLANNED ledger rows precede any result;
  * CENSOR EXPLICIT - budget exhaustion records CENSORED; never substituted by a heuristic value.

    python3 run_final.py --dry-run
    FINAL_TEST_AUTHOR_UNLOCK=1 python3 run_final.py --execute --i-have-author-authorisation
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent
ROOT = JX.parent
SIM = ROOT / "07_simulation"
OUTDIR = JX / "results_final"
RUN_METADATA = OUTDIR / "RUN_METADATA.json"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JX / "code"))
sys.path.insert(0, str(SIM))

import freeze_manifest as fm            # noqa: E402
import ledger as L                      # noqa: E402
import schema as S                      # noqa: E402

# ----------------------------------------------------------------- FROZEN STUDY DEFINITION
FINAL_SEEDS = tuple(range(50002, 50022))   # A3 reseal: 50001 excluded (incident I-01)
SEED_GUARD_LO, SEED_GUARD_HI = 50002, 50021

PRIMARY_CELL = dict(regime="R3_aged", grid="G2_wide10")
REGIMES = {"R1_nominal": (1.0, 1), "R3_aged": (2.0, 5)}     # (distance multiplier, d_CSI)
GRIDS = ("G0_icame", "G2_wide10")
LOAD = 0.40
SCALE = dict(Ks=6, Km=2, N=4, H=3)
WARMUPS = (20, 60, 100, 140, 180)

COMPARATORS = ("EDF-StaleBeam-MinFeasible", "EDF+ExactFixedDemand", "ExactFixedDemandRadio",
               "OfflineExactAgedGain", "OfflineExactCurrentGain", "ContinuousPowerRef")

NODE_BUDGET = 200_000_000
TIME_BUDGET_S = 600.0
TRACE_SEED_NAMESPACE = 700_000_000      # identical construction to the development traces


class SeedGuardError(RuntimeError):
    """A non-final seed reached the final runner. There is no override."""


class ExecutionNotSanctionedError(RuntimeError):
    """`run_unit` was called outside a sanctioned campaign. See the interlock below."""


# ---------------------------------------------------------------------------------------------
# EXECUTION INTERLOCK (added 2026-09-21 after incident I-01; see ERRATA E-16).
#
# The seed guard alone proved insufficient: it asserts that a seed IS final, so an ad-hoc call to
# run_unit() with a valid final seed executed the experiment core outside any sanctioned campaign.
# This flag is set ONLY inside execute(), after preflight has passed and both authorisation gates
# have been satisfied. Any other caller of run_unit() is refused.
#
# The integration test is unaffected: it calls run_unit_core() with a NON-FINAL seed, which is the
# documented test path and never touches the final band.
# ---------------------------------------------------------------------------------------------
_EXECUTION_SANCTIONED = False


def _sanction_execution() -> None:
    global _EXECUTION_SANCTIONED
    _EXECUTION_SANCTIONED = True


class BudgetExceededSignal(RuntimeError):
    """Node/time budget exhausted. Recorded as CENSORED, never substituted."""


def guard_seed(seed: int) -> int:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SeedGuardError(f"seed must be int, got {seed!r}")
    if not (SEED_GUARD_LO <= seed <= SEED_GUARD_HI):
        raise SeedGuardError(
            f"SEED GUARD: {seed} is outside the FINAL TEST band [{SEED_GUARD_LO},{SEED_GUARD_HI}]. "
            "Development (10001-10008), conference (20001-20010) and the EXCLUDED incident seed "
            "50001 (Amendment A3) may never enter the final runner. There is no override flag.")
    return seed


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def config_digest() -> str:
    parts = []
    for p in (SIM / "primary_experiment_config.json",
              ROOT / "10_confirmatory" / "CONFIRMATORY_PROTOCOL_LOCK.json",
              JX / "FINAL_CONFIRMATORY_PROTOCOL_V2.md"):
        if not p.exists():
            raise FileNotFoundError(f"frozen configuration input missing: {p}")
        parts.append(sha256_file(p))
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def study_units() -> List[Dict[str, Any]]:
    """Deterministic unit list: (regime, grid, seed, warm-up). Primary cell first."""
    units: List[Dict[str, Any]] = []
    ordered = [(PRIMARY_CELL["regime"], PRIMARY_CELL["grid"])]
    ordered += [(r, g) for r in REGIMES for g in GRIDS
                if (r, g) != (PRIMARY_CELL["regime"], PRIMARY_CELL["grid"])]
    for regime, grid in ordered:
        for seed in FINAL_SEEDS:
            guard_seed(seed)
            for warm in WARMUPS:
                units.append(dict(
                    regime=regime, grid=grid, seed=seed, warmup=warm,
                    K=SCALE["Ks"] + SCALE["Km"], N=SCALE["N"], H=SCALE["H"], load=LOAD,
                    dist=REGIMES[regime][0], d_csi=REGIMES[regime][1],
                    is_primary_cell=(regime == PRIMARY_CELL["regime"]
                                     and grid == PRIMARY_CELL["grid"])))
    return units


def unit_output_path(u: Dict[str, Any]) -> Path:
    return OUTDIR / "raw" / u["regime"] / u["grid"] / f"s{u['seed']}_w{u['warmup']}.json"


# ----------------------------------------------------------------- execution
def build_cfg(u: Dict[str, Any]):
    """Frozen scenario config for one unit. Deep-copied; nothing writes back."""
    from evaluation import journal_cfg
    from optimization.grids import with_grid
    cfg = journal_cfg(u["load"], t_meas=400,
                      hall_x=300.0 * u["dist"], hall_y=150.0 * u["dist"],
                      d_csi_slots=u["d_csi"])
    cfg = with_grid(cfg, u["grid"])
    return dataclasses.replace(cfg, n_static=SCALE["Ks"], n_mobile=SCALE["Km"],
                               n_subchannels=SCALE["N"],
                               n_max_static=min(cfg.n_max_static, SCALE["N"]),
                               n_max_mobile=min(cfg.n_max_mobile, SCALE["N"]))


def run_unit(u: Dict[str, Any], pf: Dict[str, Any], freeze_digest: str) -> List[Dict[str, Any]]:
    """PRODUCTION entry point: enforce the final-seed guard, then delegate to the core.

    The guard lives HERE and only here. `run_unit_core` holds the experiment logic and is shared
    verbatim with the integration test, which calls it with a NON-FINAL development seed. The
    guard is therefore never weakened or bypassed in the production CLI.

    TWO checks, not one: the seed must be in the final band, AND execution must have been
    sanctioned by execute() after preflight and both authorisation gates. See incident I-01.
    """
    if not _EXECUTION_SANCTIONED:
        raise ExecutionNotSanctionedError(
            "run_unit() called outside a sanctioned campaign. Final-band units may only be "
            "executed from execute(), after preflight and both authorisation gates have passed. "
            "For testing, call run_unit_core() with a NON-FINAL seed.")
    guard_seed(u["seed"])
    return run_unit_core(u, pf, freeze_digest)


def run_unit_core(u: Dict[str, Any], pf: Dict[str, Any], freeze_digest: str,
                  *, trace_seed_override: int | None = None) -> List[Dict[str, Any]]:
    """Record ONE trace and evaluate every comparator on it. Returns validated schema rows.

    NO SEED GUARD HERE BY DESIGN — this is the shared execution core. Production reaches it only
    through `run_unit`, which guards first. The integration test reaches it directly with an
    explicitly non-final seed, so the real execution path is exercised without duplicating it and
    without weakening the production guard.
    """
    from optimization.joint import (record_trace, rollout_policy, edf_min_feasible,
                                    solve_exact_joint, execute_plan, slot_state, ReplayModel,
                                    BudgetExceeded)
    from optimization.radio import (solve_exact_radio_fixed_demand, solve_continuous_fixed_demand,
                                    continuous_cost_of_assignment, cell_cost, INF)
    from run_stage_ib import edf_then_exact_radio

    cfg = build_cfg(u)
    trace_seed = (trace_seed_override if trace_seed_override is not None
                  else TRACE_SEED_NAMESPACE + u["seed"] * 100)
    # ONE trace per unit; every comparator below is evaluated on THIS object, so the paired
    # endpoints are paired on an identical realisation by construction.
    tr = record_trace(cfg, seed=trace_seed, H=u["H"], warmup=u["warmup"])
    trace_id = f"{u['regime']}|{u['grid']}|s{u['seed']}|w{u['warmup']}|ts{trace_seed}"

    base = dict(schema_version=S.SCHEMA_VERSION,
                experiment_id=trace_id,
                seed=u["seed"], regime=u["regime"], grid=u["grid"],
                K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                code_sha256=pf["runner_sha256"], config_sha256=pf["config_sha256"],
                runner_sha256=pf["runner_sha256"], freeze_manifest_sha256=freeze_digest)

    def row(comparator, endpoint_id, **kw):
        r = S.blank_row()
        r.update(base)
        r["comparator"] = comparator
        r["endpoint_id"] = endpoint_id
        r["status"] = kw.pop("status", "COMPLETED")
        r.update(kw)
        S.fill_comparator_fields(r)
        return S.validate_row(r)

    rows: List[Dict[str, Any]] = []

    # --- causal comparators, rolled out slot by slot on the recorded trace -------------------
    t0 = time.perf_counter()
    d_edf, p_edf = rollout_policy(tr, edf_min_feasible(False))
    rows.append(row("EDF-StaleBeam-MinFeasible", "E1",
                    realised_delivery=float(d_edf), delivered=float(d_edf),
                    aggregate_power_w=float(p_edf), realised_power_w=float(p_edf),
                    runtime_s=time.perf_counter() - t0))

    t0 = time.perf_counter()
    d_er, p_er = rollout_policy(tr, edf_then_exact_radio(False))
    rows.append(row("EDF+ExactFixedDemand", "H2",
                    realised_delivery=float(d_er), delivered=float(d_er),
                    aggregate_power_w=float(p_er), realised_power_w=float(p_er),
                    runtime_s=time.perf_counter() - t0))

    # --- per-slot exact radio references + three-term decomposition -------------------------
    m = ReplayModel(tr, believe_info=False)
    h_tot = e_tot = cag_tot = c_tot = 0.0
    n_states = n_grid_infeas = n_cont_infeas = 0
    t0 = time.perf_counter()
    greedy = edf_min_feasible(False)
    for _ in range(tr.H):
        m.begin_slot()
        st = slot_state(tr, m.i, m.queues)
        act = greedy(tr, st, m)
        demand: Dict[int, int] = {}
        hp = 0.0
        for a in act:
            if a is not None:
                demand[a[0]] = demand.get(a[0], 0) + 1
                hp += st.power_grid[a[2]]
        if demand:
            eg = solve_exact_radio_fixed_demand(st, demand, use_true=False)
            cc = solve_continuous_fixed_demand(st, demand, use_true=False)
            gi = not (eg.power_w < INF)
            ci = not (cc.power_w < INF)
            n_grid_infeas += int(gi)
            n_cont_infeas += int(ci)
            if not gi and not ci:
                c_ag = continuous_cost_of_assignment(st, eg)
                if c_ag < INF:
                    h_tot += hp; e_tot += eg.power_w; cag_tot += c_ag; c_tot += cc.power_w
                    n_states += 1
        m.commit(act)
    rt_radio = time.perf_counter() - t0

    rows.append(row("ExactFixedDemandRadio", "E1",
                    aggregate_power_w=e_tot, gap_H_G=h_tot, gap_E_G=e_tot,
                    runtime_s=rt_radio,
                    grid_infeasible_flag=n_grid_infeas, cont_infeasible_flag=n_cont_infeas))

    if n_states:
        rows.append(row("ContinuousPowerRef", "Q1",
                        aggregate_power_w=c_tot,
                        gap_H_G=h_tot, gap_E_G=e_tot, gap_C_AG=cag_tot, gap_C=c_tot,
                        term_allocation=h_tot - e_tot,
                        term_quantisation=e_tot - cag_tot,
                        term_distortion=cag_tot - c_tot,
                        runtime_s=rt_radio,
                        grid_infeasible_flag=n_grid_infeas, cont_infeasible_flag=n_cont_infeas))

    # --- offline finite-horizon references ---------------------------------------------------
    for comparator, use_true in (("OfflineExactAgedGain", False),
                                 ("OfflineExactCurrentGain", True)):
        t0 = time.perf_counter()
        try:
            dl, pw, nodes, states, plan = solve_exact_joint(
                tr, use_true=use_true, max_nodes=NODE_BUDGET,
                max_seconds=TIME_BUDGET_S, return_plan=True)
        except BudgetExceeded as e:
            raise BudgetExceededSignal(
                f"{comparator}: {e}. Reported as a barrier; never replaced by a heuristic value."
            ) from e
        rdl, rpw, skipped = execute_plan(tr, plan)
        rows.append(row(comparator, "E2" if use_true else "H2",
                        realised_delivery=float(rdl), delivered=float(rdl),
                        believed_delivery=float(dl),
                        realised_power_w=float(rpw), believed_power_w=float(pw),
                        aggregate_power_w=float(rpw),
                        nodes=float(nodes), states=float(states),
                        skipped_entries=float(skipped),
                        runtime_s=time.perf_counter() - t0))

    # Shared-trace invariant, asserted rather than assumed: every row from this unit carries the
    # same experiment_id, which encodes the single trace all comparators were evaluated on.
    ids = {r["experiment_id"] for r in rows}
    if len(ids) != 1:
        raise RuntimeError(f"shared-trace invariant violated: {len(ids)} trace ids in one unit: "
                           f"{sorted(ids)}")
    return rows


def preflight(execute_mode: bool) -> Dict[str, Any]:
    problems: List[str] = []
    notes: List[str] = []

    ok, fproblems = fm.verify()
    if not ok:
        problems += [f"C13 freeze manifest: {p}" for p in fproblems]
    else:
        notes.append("C13 freeze manifest matches the working tree")

    try:
        cfg_hash = config_digest()
        notes.append(f"frozen config digest {cfg_hash[:16]}")
    except FileNotFoundError as e:
        problems.append(str(e)); cfg_hash = None

    units = study_units()
    seeds = sorted({u["seed"] for u in units})
    if seeds != list(FINAL_SEEDS):
        problems.append("seed list mismatch")
    else:
        notes.append(f"seed guard: {len(seeds)} seeds, all within "
                     f"[{SEED_GUARD_LO},{SEED_GUARD_HI}]")
    # A3: 50001 is the EXCLUDED incident seed; 50022 is out of band.
    for bad in (10001, 20001, 50000, 50001, 50022):
        try:
            guard_seed(bad); problems.append(f"SEED GUARD FAILED TO REJECT {bad}")
        except SeedGuardError:
            pass
    notes.append("seed guard rejects development, conference, out-of-band and the "
                 "EXCLUDED incident seed 50001 (Amendment A3)")

    try:
        import numpy  # noqa: F401
        notes.append("dependency numpy present")
    except Exception as e:
        problems.append(f"dependency numpy missing: {e}")
    for p in (JX / "code" / "optimization" / "radio.py",
              JX / "code" / "optimization" / "joint.py",
              JX / "code" / "run_stage_ib.py", SIM / "m2" / "env.py"):
        if not p.exists():
            problems.append(f"required source missing: {p}")

    # ---- resume accounting (informational; added with erratum E-18) ----------------------
    latest = L.latest_state_by_unit()

    done, incomplete, state_tally = [], [], {}
    for u in units:
        uid = L.unit_id(seed=u["seed"], regime=u["regime"], grid=u["grid"], comparator="ALL",
                        K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"])
        st = latest.get(uid)
        state_tally[st] = state_tally.get(st, 0) + 1
        (done if st == "COMPLETED" else incomplete).append(uid)
    notes.append(f"planned units {len(units)}; latest ledger state tally {state_tally}")
    notes.append(f"already COMPLETED: {len(done)}  ->  skipped on resume")
    notes.append(f"eligible for retry: {len(incomplete)}"
                 + (f"  -> {incomplete}" if 0 < len(incomplete) <= 3 else ""))
    censored = sum(1 for r in L.read_all() if r["state"] == "CENSORED")
    notes.append(f"CENSORED rows in ledger: {censored}")

    existing = [u for u in units if unit_output_path(u).exists()]
    if existing:
        notes.append(f"{len(existing)} unit output file(s) present -> never overwritten")
    notes.append(f"ledger rows present: {len(L.read_all())}")

    # ---- completed-output immutability against the E-18 baseline ------------------------
    base = OUTDIR / "PRE_E18_COMPLETED_OUTPUT_DIGEST.json"
    if base.exists():
        rec = json.loads(base.read_text())
        changed, missing_now = [], []
        for rel, meta in rec["files"].items():
            p = OUTDIR / "raw" / rel
            if not p.exists():
                missing_now.append(rel)
                continue
            if hashlib.sha256(p.read_bytes()).hexdigest() != meta["sha256"]:
                changed.append(rel)
        if changed or missing_now:
            problems.append(f"completed-output immutability BROKEN: "
                            f"{len(changed)} changed, {len(missing_now)} missing")
        else:
            notes.append(f"completed-output hashes unchanged vs E-18 baseline "
                         f"({rec['n_files']} files, digest {rec['combined_digest'][:16]})")
    else:
        notes.append("no E-18 completed-output baseline present")

    if execute_mode and not os.environ.get("FINAL_TEST_AUTHOR_UNLOCK"):
        problems.append("author unlock absent: set FINAL_TEST_AUTHOR_UNLOCK=1 to execute")

    return dict(ok=not problems, problems=problems, notes=notes, n_units=len(units),
                config_sha256=cfg_hash, runner_sha256=sha256_file(Path(__file__)))


def write_run_metadata(pf: Dict[str, Any]) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    RUN_METADATA.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "study": "FINAL CONFIRMATORY (JOURNAL_PROTOCOL_V1 + A2; FINAL_CONFIRMATORY_PROTOCOL_V2)",
        "primary_cell": PRIMARY_CELL, "scale": SCALE, "load": LOAD,
        "seeds": list(FINAL_SEEDS), "warmups": list(WARMUPS),
        "regimes": {k: {"dist": v[0], "d_csi": v[1]} for k, v in REGIMES.items()},
        "grids": list(GRIDS), "comparators": list(COMPARATORS),
        "node_budget": NODE_BUDGET, "time_budget_s": TIME_BUDGET_S,
        "schema_version": S.SCHEMA_VERSION, "unit_definition": "(regime, grid, seed, warm-up)",
        "runner_sha256": pf["runner_sha256"], "config_sha256": pf["config_sha256"],
        "n_units": pf["n_units"],
    }, indent=2, sort_keys=True) + "\n")


def execute(pf: Dict[str, Any]) -> int:
    _sanction_execution()          # the ONLY place the interlock is released
    write_run_metadata(pf)
    units = study_units()
    freeze_digest = json.loads((OUTDIR / "FREEZE_MANIFEST.json").read_text())["combined_digest"]

    latest = L.latest_state_by_unit()
    planned = 0
    for u in units:
        uid = L.unit_id(seed=u["seed"], regime=u["regime"], grid=u["grid"], comparator="ALL",
                        K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"])
        if latest.get(uid) == "COMPLETED":
            continue
        L.append("PLANNED", unit=uid, seed=u["seed"], regime=u["regime"], grid=u["grid"],
                 comparator="ALL", K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                 freeze_digest=freeze_digest, runner_sha256=pf["runner_sha256"],
                 config_sha256=pf["config_sha256"])
        planned += 1
    print(f"\nPLANNED {planned} unit(s); {len(units) - planned} already COMPLETED (resume).")

    done = fail = censored = 0
    t_start = time.time()
    for u in units:
        uid = L.unit_id(seed=u["seed"], regime=u["regime"], grid=u["grid"], comparator="ALL",
                        K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"])
        if L.latest_state_by_unit().get(uid) == "COMPLETED":
            continue
        out_path = unit_output_path(u)
        if out_path.exists():
            print(f"  SKIP (output exists, never overwritten): {out_path.name}")
            continue
        guard_seed(u["seed"])
        L.append("STARTED", unit=uid, seed=u["seed"], regime=u["regime"], grid=u["grid"],
                 comparator="ALL", K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                 freeze_digest=freeze_digest, runner_sha256=pf["runner_sha256"],
                 config_sha256=pf["config_sha256"])
        try:
            rows = run_unit(u, pf, freeze_digest)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
            L.append("COMPLETED", unit=uid, seed=u["seed"], regime=u["regime"], grid=u["grid"],
                     comparator="ALL", K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                     freeze_digest=freeze_digest, runner_sha256=pf["runner_sha256"],
                     config_sha256=pf["config_sha256"], output_path=str(out_path))
            done += 1
        except BudgetExceededSignal as e:
            L.append("CENSORED", unit=uid, seed=u["seed"], regime=u["regime"], grid=u["grid"],
                     comparator="ALL", K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                     freeze_digest=freeze_digest, runner_sha256=pf["runner_sha256"],
                     config_sha256=pf["config_sha256"], censor_reason=str(e))
            censored += 1
        except Exception as e:
            L.append("FAILED", unit=uid, seed=u["seed"], regime=u["regime"], grid=u["grid"],
                     comparator="ALL", K=u["K"], N=u["N"], H=u["H"], warmup=u["warmup"],
                     freeze_digest=freeze_digest, runner_sha256=pf["runner_sha256"],
                     config_sha256=pf["config_sha256"],
                     failure_reason=f"{type(e).__name__}: {e}")
            fail += 1
            print(f"  FAILED {uid}: {type(e).__name__}: {e}")
    print(f"\nCOMPLETED {done} | CENSORED {censored} | FAILED {fail} "
          f"in {time.time() - t_start:.0f}s")
    print("A censored unit is reported as a barrier and is NEVER replaced by a heuristic value.")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="C10 final confirmatory runner")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="validate only; never instantiates or runs a final experiment")
    g.add_argument("--execute", action="store_true")
    ap.add_argument("--i-have-author-authorisation", action="store_true")
    a = ap.parse_args()

    print("=" * 72)
    print("FINAL CONFIRMATORY RUNNER  (C10)")
    print("=" * 72)
    pf = preflight(execute_mode=a.execute)
    print(f"\nplanned units          : {pf['n_units']}  (regime x grid x seed x warm-up)")
    print(f"runner sha256          : {pf['runner_sha256'][:16]}")
    print(f"config sha256          : {(pf['config_sha256'] or 'UNAVAILABLE')[:16]}")
    print("\npreflight notes:")
    for n in pf["notes"]:
        print("  -", n)
    if pf["problems"]:
        print("\npreflight PROBLEMS:")
        for p in pf["problems"]:
            print("  !", p)

    if a.dry_run:
        print("\nDRY RUN COMPLETE — no experiment instantiated, no final outcome produced, "
              "no final result file read.")
        print("STATUS:", "READY (subject to author unlock)" if pf["ok"] else "NOT READY")
        return 0 if pf["ok"] else 2

    if not pf["ok"]:
        print("\nREFUSING TO EXECUTE: preflight failed.")
        return 2
    if not a.i_have_author_authorisation:
        print("\nREFUSING TO EXECUTE: --i-have-author-authorisation not supplied.")
        return 3
    return execute(pf)


if __name__ == "__main__":
    sys.exit(main())
