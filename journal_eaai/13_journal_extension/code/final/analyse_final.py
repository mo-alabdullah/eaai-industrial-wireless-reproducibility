#!/usr/bin/env python3
"""POST-FINAL-TEST ANALYSIS PIPELINE — single entry point (master pass, 2026-09-21).

There is NO manual step between raw final results and the manuscript numbers. This script is the
only path from results_final/raw/ to the tables and figures, and it never modifies a raw file.

    python3 analyse_final.py --check          # verify integrity/completeness only
    python3 analyse_final.py --run            # full analysis (requires a complete dataset)
    python3 analyse_final.py --templates      # emit EMPTY manuscript tables (no data needed)

Order of operations when --run:
  1. verify the C13 freeze manifest;
  2. verify ledger completeness; reject a partial dataset unless --exploratory is given;
  3. load raw results and validate every row against the canonical schema;
  4. E1  estimation   (no test);
  5. H2  inference    (exact sign-flip, 2^20 enumerated, BCa CI, d_z);
  6. E2  estimation   (no test);
  7. Q1  decomposition tables;
  8. Q5  runtime summaries;
  9. write machine-readable outputs, manuscript tables, figures and an audit report.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent
RAW = JX / "results_final" / "raw"
OUT = JX / "results_final" / "analysis"
TABLES = JX / "journal_eaai" / "tables"
FIGURES = JX / "journal_eaai" / "figures"

sys.path.insert(0, str(HERE))
import freeze_manifest as fm      # noqa: E402
import ledger as L                # noqa: E402
import schema as S                # noqa: E402
import stats as ST                # noqa: E402

# Endpoint definitions bound to the frozen Section 6.3 / Stage-7D endpoint table.
ENDPOINT_SPEC = {
    "E1": dict(left="EDF-StaleBeam-MinFeasible", right="ExactFixedDemandRadio",
               outcome="aggregate_power_w", kind="estimation",
               sign="exact reference minus heuristic (negative = heuristic spends more)",
               regime="R3_aged", grid="G2_wide10"),
    "H2": dict(left="EDF+ExactFixedDemand", right="OfflineExactAgedGain",
               outcome="realised_delivery", kind="inference",
               sign="offline aged-gain reference minus causal EDF-with-exact-radio",
               regime="R3_aged", grid="G2_wide10"),
    "E2": dict(left="OfflineExactAgedGain", right="OfflineExactCurrentGain",
               outcome="realised_delivery", kind="estimation",
               sign="current-beam-gain reference minus aged-beam-gain reference",
               regime="R3_aged", grid="G2_wide10"),
}


def load_rows() -> List[Dict[str, Any]]:
    if not RAW.exists():
        return []
    rows = []
    for p in sorted(RAW.rglob("*.json")):
        obj = json.loads(p.read_text())
        for r in (obj if isinstance(obj, list) else [obj]):
            S.validate_row(r)
            rows.append(r)
    return rows


EXPECTED_FINAL_SEEDS = 20
EXPECTED_WARMUPS = 5
# Amendment A3 (2026-09-21): 50001 procedurally exposed by incident I-01 and excluded.
VALID_FINAL_SEEDS = frozenset(range(50002, 50022))
EXCLUDED_INCIDENT_SEEDS = frozenset({50001})


# ---------------------------------------------------------------- mixed-provenance gate (E-18)
# The final campaign is NOT single-provenance. 399 units were executed under the original frozen
# commit/manifest; one unit is resumed under the E-18 numerical-validation commit, which carries a
# different runner hash and a different manifest digest. That is a legitimate, declared condition —
# but it must be DECLARED, not inferred, and never silently assumed away.
#
# Rules enforced below:
#   * every row must carry a complete provenance pair (runner hash + manifest digest)  -> else REJECT
#   * every observed provenance pair must appear in the declared registry              -> else REJECT
#   * a declared entry still marked PENDING blocks --run                               -> REJECT
#   * config digest, seed set, regime/grid definitions and endpoint schema are NOT relaxed:
#     the config digest must be IDENTICAL across all rows regardless of provenance.
PROVENANCE_REGISTRY = JX / "results_final" / "PROVENANCE_REGISTRY.json"

PROVENANCE_KEYS = ("runner_sha256", "freeze_manifest_sha256")


class ProvenanceError(RuntimeError):
    """Raised when final rows carry an undeclared, incomplete or unresolved execution provenance."""


def provenance_of(row: Dict[str, Any]) -> tuple:
    return tuple(row.get(k) for k in PROVENANCE_KEYS)


def registry_bytes_sha256() -> str:
    """SHA-256 over the EXACT bytes of the registry file.

    The registry is a runtime artefact: it is deliberately NOT tracked by git and NOT in the C13
    freeze set, because its content depends on the very commit and manifest digest that a freeze
    would hash — tracking it would create a circular dependency. Recording its byte hash in the
    audit report is what makes the ignored file independently traceable after the fact.
    """
    if not PROVENANCE_REGISTRY.exists():
        raise ProvenanceError(f"provenance registry absent: {PROVENANCE_REGISTRY}")
    import hashlib
    return hashlib.sha256(PROVENANCE_REGISTRY.read_bytes()).hexdigest()


# Fields lifted into the audit snapshot, in a fixed order. `freeze_manifest_digest` is the audit
# name for the registry's `freeze_manifest_sha256` field; both names refer to the same digest.
SNAPSHOT_FIELDS = ("commit_sha", "runner_sha256", "freeze_manifest_digest", "units", "status")

# Audit field  ->  runtime registry field. The audit schema name is NOT changed; only the source
# field it is read from is corrected (erratum E-21). An earlier version read `commit_sha` straight
# out of the registry, where that key does not exist, so both snapshot rows recorded null while the
# execution provenance itself was present and correct all along.
SNAPSHOT_SOURCE_FIELDS = {
    "commit_sha": ("git_commit", "commit_sha"),
    "freeze_manifest_digest": ("freeze_manifest_digest", "freeze_manifest_sha256"),
}

_GIT_SHA_RE = __import__("re").compile(r"^[0-9a-f]{40}$")


def _registry_field(entry: Dict[str, Any], audit_field: str) -> Any:
    for src in SNAPSHOT_SOURCE_FIELDS.get(audit_field, (audit_field,)):
        if src in entry:
            return entry[src]
    return None


def canonical_registry_snapshot(declared: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic, canonical snapshot of the accepted registry entries.

    Deterministic by construction: labels sorted, fields in a fixed order, no timestamps, no
    dict-iteration dependence. Two calls on equal input produce byte-equal JSON.

    The commit SHA is validated here, not merely copied: a missing, PENDING or malformed value is
    a provenance defect and raises rather than being recorded as null.
    """
    snap = []
    for label in sorted(declared):
        e = declared[label]
        commit = _registry_field(e, "commit_sha")
        if commit is None:
            raise ProvenanceError(
                f"declared provenance {label!r} carries no commit SHA "
                f"(looked for {' / '.join(SNAPSHOT_SOURCE_FIELDS['commit_sha'])}). "
                "A provenance without a commit is never recorded as null.")
        if not isinstance(commit, str) or not _GIT_SHA_RE.match(commit):
            why = ("still PENDING" if isinstance(commit, str) and commit.strip().upper() == "PENDING"
                   else "not a lowercase 40-hex git SHA")
            raise ProvenanceError(
                f"declared provenance {label!r} has an unusable commit SHA {commit!r}: {why}.")
        row = {"label": label}
        for f in SNAPSHOT_FIELDS:
            row[f] = commit if f == "commit_sha" else _registry_field(e, f)
        snap.append(row)
    return snap


def load_declared_provenance() -> Dict[str, Dict[str, Any]]:
    if not PROVENANCE_REGISTRY.exists():
        raise ProvenanceError(
            f"provenance registry absent: {PROVENANCE_REGISTRY}. The campaign spans more than one "
            "execution commit, so the accepted provenance set must be declared explicitly. "
            "Analysis is refused rather than assuming a single runner hash.")
    reg = json.loads(PROVENANCE_REGISTRY.read_text())
    entries = reg.get("declared")
    if not isinstance(entries, dict) or not entries:
        raise ProvenanceError("provenance registry contains no 'declared' entries")
    return entries


def assert_declared_provenance(rows: List[Dict[str, Any]],
                               declared: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Metadata-only gate. Returns the per-label row tally. Raises ProvenanceError otherwise.

    Pure function of metadata: it reads provenance and config columns only and never touches an
    outcome column, so it is exercisable on synthetic rows.
    """
    pending = [lbl for lbl, e in declared.items() if e.get("status") == "PENDING"
               or any(e.get(k) in (None, "", "PENDING") for k in PROVENANCE_KEYS)]
    if pending:
        raise ProvenanceError(
            f"declared provenance entr(y/ies) {sorted(pending)} are still PENDING (the commit "
            "and/or freeze manifest do not exist yet). Resolve them to concrete hashes before "
            "analysis; a PENDING provenance is never accepted as a match.")

    index = {tuple(e[k] for k in PROVENANCE_KEYS): lbl for lbl, e in declared.items()}
    if len(index) != len(declared):
        raise ProvenanceError("two declared provenance labels share one hash pair; "
                              "the registry must be unambiguous")

    tally: Dict[str, int] = {lbl: 0 for lbl in declared}
    undeclared, incomplete = {}, 0
    for r in rows:
        prov = provenance_of(r)
        if any(v in (None, "") for v in prov):
            incomplete += 1
            continue
        lbl = index.get(prov)
        if lbl is None:
            undeclared[prov] = undeclared.get(prov, 0) + 1
        else:
            tally[lbl] += 1
    if incomplete:
        raise ProvenanceError(
            f"{incomplete} row(s) carry an incomplete provenance pair "
            f"({' / '.join(PROVENANCE_KEYS)}). A missing provenance is REJECTED, never defaulted.")
    if undeclared:
        shown = [(f"{str(a)[:12]}…", f"{str(b)[:12]}…") for a, b in list(undeclared)[:3]]
        raise ProvenanceError(
            f"{sum(undeclared.values())} row(s) carry an UNDECLARED execution provenance "
            f"{shown}. The declared set is {sorted(declared)}. A third provenance is refused: "
            "every executed unit must be attributable to a declared commit and manifest.")

    # Scientific consistency is NOT relaxed by the provenance split.
    cfgs = {r.get("config_sha256") for r in rows}
    if len(cfgs) != 1 or None in cfgs or "" in cfgs:
        raise ProvenanceError(
            f"config digest is not identical across all rows: {sorted(str(c)[:12] for c in cfgs)}. "
            "A provenance split may differ in CODE hash only; the frozen configuration must be "
            "byte-identical for every unit.")
    return tally


def provenance_audit_block(rows: List[Dict[str, Any]],
                           declared: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Build the AUDIT_REPORT provenance block. ONLY called after the gate has passed.

    Reads provenance and config columns only — never an outcome column — so the whole block is
    exercisable on synthetic metadata rows.
    """
    tally = assert_declared_provenance(rows, declared)      # validation FIRST; raises on failure
    cfgs = {r.get("config_sha256") for r in rows}
    return {
        "registry_path": (str(PROVENANCE_REGISTRY.relative_to(JX))
                          if JX in PROVENANCE_REGISTRY.parents else PROVENANCE_REGISTRY.name),
        "registry_tracked_by_git": False,
        "registry_in_freeze_set": False,
        "registry_excluded_reason": (
            "runtime artefact: its content depends on the commit and freeze-manifest digest that a "
            "freeze would hash, so tracking it would create a circular dependency. Traceability is "
            "provided by the byte hash and canonical snapshot recorded here."),
        "registry_sha256": registry_bytes_sha256(),                       # (A)
        "registry_snapshot": canonical_registry_snapshot(declared),       # (B)
        "observed_tally": dict(sorted(tally.items())),                    # (C)
        "config_sha256_common": cfgs.pop(),                               # (D)
        "n_rows_audited": len(rows),
    }


class PseudoreplicationError(RuntimeError):
    """Raised when an analysis would treat sub-seed execution units as independent replicates."""


class SeedSetError(RuntimeError):
    """Raised when the seeds reaching a primary endpoint are not exactly the resealed A3 set."""


def assert_valid_final_seed_set(eid: str, seeds) -> None:
    """Amendment A3 gate: the primary endpoints accept EXACTLY 50002-50021, nothing else.

    Rejects the excluded incident seed 50001, a short set, an extra seed, and duplicates.
    """
    s = list(seeds)
    if len(set(s)) != len(s):
        raise SeedSetError(f"{eid}: duplicate seed(s) in the paired sample: "
                           f"{sorted({x for x in s if s.count(x) > 1})}")
    got = set(s)
    bad = got & EXCLUDED_INCIDENT_SEEDS
    if bad:
        raise SeedSetError(
            f"{eid}: EXCLUDED incident seed(s) {sorted(bad)} present. Seed 50001 was "
            "procedurally exposed (incident I-01) and is permanently excluded by Amendment A3.")
    if got != VALID_FINAL_SEEDS:
        missing = sorted(VALID_FINAL_SEEDS - got)
        extra = sorted(got - VALID_FINAL_SEEDS)
        raise SeedSetError(
            f"{eid}: seed set is not the resealed A3 set 50002-50021 "
            f"(n={len(got)}; missing={missing[:5]}; unexpected={extra[:5]}).")


def seed_level(rows, comparator, outcome, regime, grid):
    """Collapse execution units to ONE value per seed — the frozen experimental unit.

    ANTI-PSEUDOREPLICATION GATE. The runner emits one row per (seed, warm-up); the frozen
    statistical plan declares the SEED as the experimental unit, with n = 20. Warm-ups are
    within-seed replication used for variance reduction, NOT independent observations. This
    function averages them away and then asserts that the collapse actually happened.
    """
    acc: Dict[int, List[float]] = {}
    for r in rows:
        if (r["comparator"] == comparator and r["regime"] == regime
                and r["grid"] == grid and r["status"] == "COMPLETED"
                and r.get(outcome) is not None):
            acc.setdefault(r["seed"], []).append(float(r[outcome]))
    out = {s: sum(v) / len(v) for s, v in sorted(acc.items())}

    if out:
        n_units = sum(len(v) for v in acc.values())
        if len(out) > EXPECTED_FINAL_SEEDS:
            raise PseudoreplicationError(
                f"{comparator}/{regime}/{grid}: {len(out)} distinct seeds exceeds the frozen "
                f"n = {EXPECTED_FINAL_SEEDS}. The seed is the experimental unit.")
        if n_units > len(out) * EXPECTED_WARMUPS:
            raise PseudoreplicationError(
                f"{comparator}/{regime}/{grid}: {n_units} execution units over {len(out)} seeds "
                f"exceeds {EXPECTED_WARMUPS} per seed; refusing to aggregate an unexpected "
                "replication structure.")
    return out


def run_endpoint(rows, eid):
    spec = ENDPOINT_SPEC[eid]
    a = seed_level(rows, spec["left"], spec["outcome"], spec["regime"], spec["grid"])
    b = seed_level(rows, spec["right"], spec["outcome"], spec["regime"], spec["grid"])
    keys = sorted(set(a) & set(b))
    if not keys:
        return {"endpoint": eid, "status": "NO DATA"}
    if set(a) != set(b):
        raise ST.PairingError(f"{eid}: unpaired seeds {sorted(set(a) ^ set(b))}")
    # ---- hard gates on the PRIMARY endpoints ----
    if eid in ("E1", "H2", "E2"):
        # Amendment A3: the seed set must be exactly 50002-50021
        assert_valid_final_seed_set(eid, keys)
        if len(keys) != EXPECTED_FINAL_SEEDS:
            raise PseudoreplicationError(
                f"{eid}: paired sample has n = {len(keys)}, but the frozen plan declares "
                f"n = {EXPECTED_FINAL_SEEDS} (one paired observation per final seed). "
                "Refusing to proceed: this is the anti-pseudoreplication gate.")
        if len(set(keys)) != len(keys):
            raise PseudoreplicationError(f"{eid}: duplicate seed in the paired sample")

    res = ST.paired_inference([a[k] for k in keys], [b[k] for k in keys],
                              keys_a=keys, keys_b=keys,
                              sign_convention=spec["sign"],
                              run_test=(spec["kind"] == "inference"))

    if eid == "H2" and res.n_assignments is not None and res.n_assignments != 2 ** EXPECTED_FINAL_SEEDS:
        raise PseudoreplicationError(
            f"H2: sign-flip enumeration was 2^{len(keys)} = {res.n_assignments:,}, "
            f"expected 2^{EXPECTED_FINAL_SEEDS} = {2 ** EXPECTED_FINAL_SEEDS:,}")
    out = {"endpoint": eid, "kind": spec["kind"], "outcome": spec["outcome"],
           "regime": spec["regime"], "grid": spec["grid"],
           "left": spec["left"], "right": spec["right"], "status": "OK"}
    out.update(res.as_row())
    out["report"] = ST.report_nonrejection(res)
    out["notes"] = res.notes
    return out


TABLE_TEMPLATES = {
    "TABLE_R1_H2_primary.md": """# TABLE R1 — Final H2 primary outcome
Endpoint H2. Sole inferential test. Tier 2 (FINAL CONFIRMATORY). Cell: R3_aged x G2_wide10.
Sign convention: offline aged-beam-gain reference MINUS causal EDF-with-exact-radio.

| comparator / reference | mean realised delivery | paired mean difference | 95% BCa CI | exact sign-flip p | Cohen d_z | + pairs | - pairs | ties | n |
|---|---|---|---|---|---|---|---|---|---|
| causal EDF + exact fixed-demand radio | [FINAL_H2_MEAN_LEFT] | — | — | — | — | — | — | — | [FINAL_H2_N] |
| offline exact aged-beam-gain reference | [FINAL_H2_MEAN_RIGHT] | [FINAL_H2_MEAN_DIFF] | [[FINAL_H2_CI_LOW], [FINAL_H2_CI_HIGH]] | [FINAL_H2_P] | [FINAL_H2_DZ] | [FINAL_H2_NPOS] | [FINAL_H2_NNEG] | [FINAL_H2_TIES] | [FINAL_H2_N] |

Notes. Exact paired two-sided sign-flip, all 2^20 = 1,048,576 assignments enumerated. m = 1; no
multiplicity correction. A non-rejection is reported as "did not reject" with its interval and is
NOT evidence of equivalence. The right-hand row is an OFFLINE, NONCAUSAL, NON-DEPLOYABLE reference,
not a controller.
""",
    "TABLE_R2_E1_power_gap.md": """# TABLE R2 — E1 fixed-demand radio power-gap estimates
Endpoint E1. ESTIMATION ONLY — no p-value (the sign is fixed by solver construction).
Tier 2. Transmission demand identical on both sides.

| regime | grid | mean gap | median gap | p95 gap | max gap | fraction exactly zero | 95% BCa CI on the mean | states | grid-infeasible states (excluded) |
|---|---|---|---|---|---|---|---|---|---|
| R3_aged | G2_wide10 | [FINAL_E1_MEAN] | [FINAL_E1_MEDIAN] | [FINAL_E1_P95] | [FINAL_E1_MAX] | [FINAL_E1_FRACZERO] | [[FINAL_E1_CI_LOW], [FINAL_E1_CI_HIGH]] | [FINAL_E1_NSTATES] | [FINAL_E1_NINFEAS] |
| R1_nominal | G2_wide10 | [FINAL_E1_R1_MEAN] | [FINAL_E1_R1_MEDIAN] | [FINAL_E1_R1_P95] | [FINAL_E1_R1_MAX] | [FINAL_E1_R1_FRACZERO] | [[FINAL_E1_R1_CI_LOW], [FINAL_E1_R1_CI_HIGH]] | [FINAL_E1_R1_NSTATES] | [FINAL_E1_R1_NINFEAS] |

Notes. Infeasible states are excluded and counted, never imputed. Secondary rows are descriptive.
""",
    "TABLE_R3_E2_information.md": """# TABLE R3 — E2 aged versus current beam-gain reference
Endpoint E2. ESTIMATION ONLY — no p-value against a structurally constrained zero.
Estimand: the effect of BEAM-GAIN FRESHNESS within a common OFFLINE finite-horizon reference
problem. NOT the value of all channel information. Both sides are non-deployable.

| quantity | aged-gain reference | current-gain reference | paired difference | 95% BCa CI | effect size | ties | n |
|---|---|---|---|---|---|---|---|
| realised delivery | [FINAL_E2_DLV_AGED] | [FINAL_E2_DLV_CURRENT] | [FINAL_E2_DLV_DIFF] | [[FINAL_E2_DLV_CI_LOW], [FINAL_E2_DLV_CI_HIGH]] | [FINAL_E2_DLV_DZ] | [FINAL_E2_TIES] | [FINAL_E2_N] |
| aggregate power (W) | [FINAL_E2_PW_AGED] | [FINAL_E2_PW_CURRENT] | [FINAL_E2_PW_DIFF] | [[FINAL_E2_PW_CI_LOW], [FINAL_E2_PW_CI_HIGH]] | — | — | [FINAL_E2_N] |
""",
    "TABLE_R4_decomposition.md": """# TABLE R4 — Three-term power-gap decomposition
Endpoint Q1. DESCRIPTIVE / STRUCTURAL. The identity is analytic; no p-value is attached.
Grids are reported SEPARATELY and are not nested refinement levels.

| regime | grid | total gap H_G - C | allocation (H_G - E_G) | pure quantisation (E_G - C_AG) | quantisation-induced distortion (C_AG - C) | allocation share | quantisation share | distortion share | median H_G/C | IQR H_G/C | states |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1_nominal | G0_icame | [Q1_R1G0_TOTAL] | [Q1_R1G0_ALLOC] | [Q1_R1G0_QUANT] | [Q1_R1G0_DIST] | [Q1_R1G0_SH_A] | [Q1_R1G0_SH_Q] | [Q1_R1G0_SH_D] | [Q1_R1G0_MED] | [Q1_R1G0_IQR] | [Q1_R1G0_N] |
| R1_nominal | G2_wide10 | [Q1_R1G2_TOTAL] | [Q1_R1G2_ALLOC] | [Q1_R1G2_QUANT] | [Q1_R1G2_DIST] | [Q1_R1G2_SH_A] | [Q1_R1G2_SH_Q] | [Q1_R1G2_SH_D] | [Q1_R1G2_MED] | [Q1_R1G2_IQR] | [Q1_R1G2_N] |
| R3_aged | G0_icame | [Q1_R3G0_TOTAL] | [Q1_R3G0_ALLOC] | [Q1_R3G0_QUANT] | [Q1_R3G0_DIST] | [Q1_R3G0_SH_A] | [Q1_R3G0_SH_Q] | [Q1_R3G0_SH_D] | [Q1_R3G0_MED] | [Q1_R3G0_IQR] | [Q1_R3G0_N] |
| R3_aged | G2_wide10 | [Q1_R3G2_TOTAL] | [Q1_R3G2_ALLOC] | [Q1_R3G2_QUANT] | [Q1_R3G2_DIST] | [Q1_R3G2_SH_A] | [Q1_R3G2_SH_Q] | [Q1_R3G2_SH_D] | [Q1_R3G2_MED] | [Q1_R3G2_IQR] | [Q1_R3G2_N] |

Notes. The ratio H_G/C is summarised by MEDIAN and IQR, never by a mean. Every term is non-negative
under the conditions stated in the exact-framework section. The continuous reference is a
MATHEMATICAL LOWER / REFERENCE BOUND, never an achievable saving.
""",
    "TABLE_R5_runtime.md": """# TABLE R5 — Computational cost
Endpoint Q5. DESCRIPTIVE. Single-process, timed around the solve call only.

| solver / reference | n solves | mean (us) | median (us) | p95 (us) | p99 (us) | max (us) | censored | fraction < 1 ms |
|---|---|---|---|---|---|---|---|---|
| fixed-demand exact radio | [Q5_FD_N] | [Q5_FD_MEAN] | [Q5_FD_MED] | [Q5_FD_P95] | [Q5_FD_P99] | [Q5_FD_MAX] | [Q5_FD_CENS] | [Q5_FD_SUB1MS] |
| free-selection exact radio | [Q5_FS_N] | [Q5_FS_MEAN] | [Q5_FS_MED] | [Q5_FS_P95] | [Q5_FS_P99] | [Q5_FS_MAX] | [Q5_FS_CENS] | [Q5_FS_SUB1MS] |
| offline finite-horizon reference (K8 N4 H3) | [Q5_FH_N] | [Q5_FH_MEAN] | [Q5_FH_MED] | [Q5_FH_P95] | [Q5_FH_P99] | [Q5_FH_MAX] | [Q5_FH_CENS] | — |

Notes. No real-time claim is made from a mean. The free-selection solver does not meet a 1 ms
budget consistently. No portability claim to other hardware, compiled implementations or larger
K/N. Budget-exhausted solves are reported as censored and are never replaced by a heuristic value.
""",
    "TABLE_R6_context.md": """# TABLE R6 — Learned-controller and heuristic context
EVIDENCE TIER MUST BE STATED PER ROW. Development and final values are NEVER mixed in one column.

| tier | method | regime | grid | source | per-class PDR | mean aggregate power (W) | beam-selection rate | note |
|---|---|---|---|---|---|---|---|---|
| DEVELOPMENT | inherited constrained autoregressive PPO controller (BSA-C-PPO) | [CTX_DEV_REGIME] | [CTX_DEV_GRID] | development seeds | [CTX_DEV_PDR] | [CTX_DEV_POWER] | [CTX_DEV_BEAM] | development only; not confirmatory |
| DEVELOPMENT | EDF-StaleBeam-MinFeasible | [CTX_DEV2_REGIME] | [CTX_DEV2_GRID] | development seeds | [CTX_DEV2_PDR] | [CTX_DEV2_POWER] | — | development only |
| FINAL | [CTX_FINAL_METHOD] | R3_aged | G2_wide10 | final seeds | [CTX_FINAL_PDR] | [CTX_FINAL_POWER] | [CTX_FINAL_BEAM] | tier 2 |

Notes. All learned-method conclusions are conditional on the executed training budget of 80
episodes (8 per update round x 10 rounds). The three learned variants were separately trained.
""",
}


def emit_templates() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    for name, body in TABLE_TEMPLATES.items():
        (TABLES / name).write_text(body)
    print(f"wrote {len(TABLE_TEMPLATES)} EMPTY table templates -> {TABLES}")


def check() -> int:
    print("INTEGRITY / COMPLETENESS CHECK")
    ok, probs = fm.verify()
    print("  C13 freeze manifest :", "MATCH" if ok else "MISMATCH")
    for p in probs[:10]:
        print("     -", p)
    rows = load_rows()
    print(f"  raw result rows     : {len(rows)}")
    led = L.read_all()
    print(f"  ledger rows         : {len(led)}")
    if rows:
        try:
            blk = provenance_audit_block(rows, load_declared_provenance())
            print(f"  provenance gate     : OK {blk['observed_tally']}")
            print(f"  registry sha256     : {blk['registry_sha256']}")
        except ProvenanceError as e:
            print(f"  provenance gate     : BLOCKED — {e}")
    if not rows:
        print("\n  NO FINAL RESULTS PRESENT — the confirmatory run has not been executed.")
        print("  This is the expected state before author unlock.")
    return 0


def run(exploratory: bool) -> int:
    ok, probs = fm.verify()
    if not ok and not exploratory:
        print("REFUSING: C13 freeze manifest mismatch:", *probs, sep="\n  - ")
        return 2
    rows = load_rows()
    if not rows:
        print("REFUSING: no final results present. Run the confirmatory campaign first.")
        return 2
    # Mixed-provenance gate (E-18). Never bypassed by --exploratory: an undeclared or unresolved
    # execution provenance is a provenance defect, not a dataset-completeness question.
    try:
        prov_audit = provenance_audit_block(rows, load_declared_provenance())
    except ProvenanceError as e:
        print(f"REFUSING: mixed-provenance gate: {e}")
        return 2
    print(f"provenance gate OK: {prov_audit['observed_tally']} "
          f"registry sha256 {prov_audit['registry_sha256'][:12]}…")
    OUT.mkdir(parents=True, exist_ok=True)
    results = {eid: run_endpoint(rows, eid) for eid in ("E1", "H2", "E2")}
    (OUT / "endpoints.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    audit = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": S.SCHEMA_VERSION,
        "n_raw_rows": len(rows),
        "freeze_manifest_match": ok,
        "provenance": prov_audit,
        "exploratory_mode": exploratory,
        "endpoints": results,
    }
    (OUT / "AUDIT_REPORT.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(f"analysis written -> {OUT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--templates", action="store_true")
    ap.add_argument("--exploratory", action="store_true",
                    help="permit a partial dataset; output is labelled EXPLORATORY, never final")
    a = ap.parse_args()
    if a.templates:
        emit_templates()
        return 0
    if a.check:
        return check()
    return run(a.exploratory)


if __name__ == "__main__":
    sys.exit(main())
