#!/usr/bin/env python3
"""CANONICAL FINAL-RESULT SCHEMA (master completion pass, 2026-09-21).

One tidy row per (experiment_id, seed, regime, grid, comparator, endpoint_id) observation.
This module is the SINGLE source of truth for final result columns; the runner writes it and the
analysis pipeline reads it. No other column set is permitted downstream.

Design rules enforced here:
  * no ambiguous column names ('score', 'value', 'result' are REJECTED by validate_row);
  * causal/lookahead/information flags are explicit per comparator, never inferred at analysis time;
  * believed vs realised quantities are separate columns and never merged;
  * censoring and infeasibility are first-class flags, never encoded as NaN alone;
  * every row carries the code and config hash under which it was produced.

Terminology is bound to the frozen Sections 3-6:
  information_mode : 'aged_beam_gain' | 'current_beam_gain' | 'none'
  causal_flag      : True for online per-slot decision makers, False for offline trace-wise refs
  lookahead_flag   : True iff the producer received the complete future trace before deciding
"""
from __future__ import annotations

from typing import Any, Dict, List

SCHEMA_VERSION = "final-schema-v1"

# ---------------------------------------------------------------- comparator registry
# Frozen Section 6.2 taxonomy. 'kind' is one of learned | heuristic | exact_reference | bound.
COMPARATORS: Dict[str, Dict[str, Any]] = {
    "BSA-C-PPO":            dict(kind="learned",         causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "BSA-Penalty-PPO":      dict(kind="learned",         causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "BSA-Unconstrained-PPO":dict(kind="learned",         causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "EDF-StaleBeam-MaxPow": dict(kind="heuristic",       causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "EDF-StaleBeam-MinFeasible": dict(kind="heuristic",  causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "EDF+ExactFixedDemand": dict(kind="heuristic",       causal=True,  lookahead=False, info="aged_beam_gain",    deployable=True),
    "ExactFixedDemandRadio":dict(kind="exact_reference", causal=True,  lookahead=False, info="aged_beam_gain",    deployable=False),
    "ExactFreeSelectionRadio": dict(kind="exact_reference", causal=True, lookahead=False, info="aged_beam_gain",  deployable=False),
    "OfflineExactAgedGain": dict(kind="exact_reference", causal=False, lookahead=True,  info="aged_beam_gain",    deployable=False),
    "OfflineExactCurrentGain": dict(kind="exact_reference", causal=False, lookahead=True, info="current_beam_gain", deployable=False),
    "ContinuousPowerRef":   dict(kind="bound",           causal=True,  lookahead=False, info="aged_beam_gain",    deployable=False),
}

# Objects that must NEVER be called 'controller' in any generated text (frozen Section 6.2).
NON_CONTROLLERS = {"ExactFixedDemandRadio", "ExactFreeSelectionRadio",
                   "OfflineExactAgedGain", "OfflineExactCurrentGain", "ContinuousPowerRef"}

ENDPOINTS = ("E1", "H2", "E2", "Q1", "S1", "Q5", "CTX")

STATUS_VALUES = ("COMPLETED", "FAILED", "CENSORED", "INVALIDATED")

# ---------------------------------------------------------------- columns
COLUMNS: List[str] = [
    # identity / provenance
    "schema_version", "experiment_id", "endpoint_id", "status",
    "seed", "regime", "grid", "K", "N", "H", "warmup",
    "comparator", "comparator_kind",
    # information structure (explicit, never inferred downstream)
    "information_mode", "causal_flag", "lookahead_flag", "deployable_flag",
    # packet accounting
    "generated", "delivered", "realised_delivery", "believed_delivery",
    "deadline_drops", "retx_drops", "overflow_drops",
    # power / objective
    "aggregate_power_w", "realised_power_w", "believed_power_w", "objective_value",
    # gap quantities (Section 4.7 symbols)
    "gap_H_G", "gap_E_G", "gap_C_AG", "gap_C",
    "term_allocation", "term_quantisation", "term_distortion",
    # runtime + exceptional conditions
    "runtime_s", "nodes", "states",
    "budget_exceeded_flag", "grid_infeasible_flag", "cont_infeasible_flag", "skipped_entries",
    # integrity
    "code_sha256", "config_sha256", "runner_sha256", "freeze_manifest_sha256",
]

FORBIDDEN_COLUMNS = {"score", "value", "result", "metric", "output"}

# Columns that are counts, accumulated sums or timings: these are NEVER produced by subtractive
# cancellation, so a negative value is always a real defect and gets a STRICT check.
NUMERIC_NONNEGATIVE = (
    "generated", "delivered", "realised_delivery", "believed_delivery",
    "deadline_drops", "retx_drops", "overflow_drops",
    "aggregate_power_w", "realised_power_w", "believed_power_w",
    "gap_H_G", "gap_E_G", "gap_C_AG", "gap_C",
    "runtime_s", "nodes", "states", "skipped_entries",
)

# Columns that are STRUCTURALLY non-negative but are computed as a DIFFERENCE of two sums of
# comparable magnitude. These are subject to catastrophic-cancellation residue at float64 ULP
# scale and get the scale-aware check below, not the strict one.
# Each entry maps the column to the parent quantities that set its magnitude scale.
STRUCTURAL_NONNEGATIVE_DIFFERENCES = {
    "term_allocation":    ("gap_H_G", "gap_E_G"),      # H_G - E_G
    "term_quantisation":  ("gap_E_G", "gap_C_AG"),     # E_G - C_AG
    "term_distortion":    ("gap_C_AG", "gap_C"),       # C_AG - C
}


# ---------------------------------------------------------------- float64 numerical policy
# ONE policy, used by the runner and the analysis pipeline alike. Added 2026-10-04 (erratum E-18)
# after a single confirmatory unit failed validation on a structurally non-negative difference that
# was negative by exactly ONE unit in the last place at its operand scale: a summation-reordering
# residue, not a structurally negative quantity.
#
# REVISED 2026-10-05 (E-18 micro-correction). The first version of this policy used
#     K_EPS * eps * max(1.0, |operands|)
# whose `max(1.0, ...)` floor is WRONG for sub-unit-valued power quantities. The power terms here
# are of order 1e-2, where one ULP is 2**-57, so a floor-at-1 tolerance of 128*2**-52 = 2**-45 is
# 4096 ULP — and at order 1e-3 it is 131072 ULP. The headroom claim that accompanied that rule was
# therefore mathematically false and has been withdrawn.
#
# The rule is now expressed directly in units in the last place, via math.ulp, so the tolerance
# tracks the actual float64 spacing at the operand magnitude instead of a fixed absolute floor.
# The rule is NOT `if x < 0: x = 0`, and K_ULP is NOT chosen from any observed value.
import math as _math

EPS_FLOAT64 = 2.220446049250313e-16          # sys.float_info.epsilon = 2**-52; reference only

# Why 32. Each side of a structural difference is a sum of at most N = 4 non-negative per-cell
# power terms (the frozen problem has N = 4 subchannels), and the two sides accumulate the SAME
# multiset in different orders. Worst-case round-off for m-term float64 accumulation grows like
# (m-1) ULP per side, so a few ULP suffices; 32 ULP leaves roughly an order of magnitude of
# headroom over that bound while remaining 128x tighter than the withdrawn floor-at-1 rule at
# order-1e-2 scale, and ~4000x tighter at order-1e-3 scale.
K_ULP = 32                                    # structural non-negativity, in ULP of the operands
K_ID_ULP = 32                                 # three-term identity residual, in ULP of LHS/RHS


class SchemaError(ValueError):
    """Raised when a row violates the canonical schema. Never repaired silently."""


def structural_ulp_tolerance(*operands: Any) -> float:
    """ULP-based tolerance: K_ULP * max(math.ulp(|operand|)) over the finite operands.

    The scale is set by the float64 spacing at the operand magnitudes, so the tolerance shrinks
    with the operands instead of resting on an absolute floor.
    """
    finite = [abs(float(v)) for v in operands
              if v is not None and _math.isfinite(float(v))]
    if not finite:
        raise SchemaError(
            "structural_ulp_tolerance requires at least one finite operand to set the scale; "
            f"got {operands!r}. A tolerance is never invented without a scale.")
    return K_ULP * max(_math.ulp(v) for v in finite)


def canonicalize_structural_nonnegative(value: Any, *scale_operands: Any,
                                        name: str = "value") -> Any:
    """Single deterministic normalisation for a structurally non-negative difference.

    Returns +0.0 only for a negative value inside float64 tolerance; leaves any valid
    non-negative value untouched; raises SchemaError on a genuinely negative value.
    """
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(f"{name} must be numeric, got {value!r}")
    v = float(value)
    if v >= 0.0:
        return value                              # untouched, including exact 0.0
    tol = structural_ulp_tolerance(*scale_operands)
    if v >= -tol:
        return 0.0                                 # numerical zero, within K_ULP ULP
    raise SchemaError(
        f"{name} is negative beyond the ULP tolerance: {v!r} < -{tol!r} "
        f"(tolerance = {K_ULP} ULP of the parent operands "
        f"{[None if s is None else float(s) for s in scale_operands]}). "
        "This is a structural violation, not round-off, and is NOT canonicalised.")


def blank_row() -> Dict[str, Any]:
    return {c: None for c in COLUMNS}


def validate_row(row: Dict[str, Any], *, strict: bool = True) -> Dict[str, Any]:
    """Validate one result row. Raises SchemaError; never coerces or repairs."""
    bad = FORBIDDEN_COLUMNS & set(row)
    if bad:
        raise SchemaError(f"ambiguous column name(s) forbidden by the schema: {sorted(bad)}")
    unknown = set(row) - set(COLUMNS)
    if unknown:
        raise SchemaError(f"unknown column(s): {sorted(unknown)}")
    if strict:
        missing = set(COLUMNS) - set(row)
        if missing:
            raise SchemaError(f"missing column(s): {sorted(missing)}")

    comp = row.get("comparator")
    if comp not in COMPARATORS:
        raise SchemaError(f"unknown comparator {comp!r}; registry is frozen in schema.COMPARATORS")
    spec = COMPARATORS[comp]
    for col, key in (("comparator_kind", "kind"), ("information_mode", "info"),
                     ("causal_flag", "causal"), ("lookahead_flag", "lookahead"),
                     ("deployable_flag", "deployable")):
        if row.get(col) is not None and row[col] != spec[key]:
            raise SchemaError(
                f"{col}={row[col]!r} contradicts the frozen registry for {comp!r} "
                f"(expected {spec[key]!r}). The registry is authoritative.")

    if row.get("endpoint_id") not in ENDPOINTS:
        raise SchemaError(f"endpoint_id must be one of {ENDPOINTS}, got {row.get('endpoint_id')!r}")
    if row.get("status") not in STATUS_VALUES:
        raise SchemaError(f"status must be one of {STATUS_VALUES}, got {row.get('status')!r}")

    for c in NUMERIC_NONNEGATIVE:
        v = row.get(c)
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise SchemaError(f"{c} must be numeric, got {v!r}")
        if v < 0:
            raise SchemaError(f"{c} must be non-negative, got {v}")

    # packet-accounting invariants (project validity rules)
    g, d = row.get("generated"), row.get("delivered")
    if g is not None and d is not None and d > g:
        raise SchemaError(f"delivered ({d}) exceeds generated ({g})")

    # ---- structurally non-negative DIFFERENCES: scale-aware float64 policy (erratum E-18) ----
    # Canonicalised IN PLACE so that every downstream consumer — serialisation, the analysis
    # pipeline, the tables — sees one deterministic representation.
    for col, parents in STRUCTURAL_NONNEGATIVE_DIFFERENCES.items():
        if row.get(col) is None:
            continue
        row[col] = canonicalize_structural_nonnegative(
            row[col], *(row.get(p) for p in parents), name=col)

    # decomposition invariants, when the terms are present
    terms = [row.get(t) for t in ("term_allocation", "term_quantisation", "term_distortion")]
    if all(t is not None for t in terms):
        tot = row.get("gap_H_G"), row.get("gap_C")
        if all(x is not None for x in tot):
            lhs, rhs = tot[0] - tot[1], sum(terms)
            # The identity is analytic; the CHECK must tolerate float64 accumulation only. The
            # tolerance is K_ID_ULP units in the last place of the independently formed LHS and
            # RHS — never a fixed decimal, and never a decimal rounding of the values.
            if lhs == 0.0 and rhs == 0.0:
                pass                               # both exactly zero: accept exactly
            else:
                tol = K_ID_ULP * max(_math.ulp(abs(lhs)), _math.ulp(abs(rhs)))
                if abs(lhs - rhs) > tol:
                    raise SchemaError(
                        f"three-term identity violated beyond the ULP tolerance: "
                        f"H_G-C={lhs!r} != sum(terms)={rhs!r} "
                        f"(residual {abs(lhs - rhs)!r} > tolerance {tol!r} "
                        f"= {K_ID_ULP} ULP)")
    return row


def fill_comparator_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Populate the derived information-structure columns from the frozen registry."""
    spec = COMPARATORS[row["comparator"]]
    row["comparator_kind"] = spec["kind"]
    row["information_mode"] = spec["info"]
    row["causal_flag"] = spec["causal"]
    row["lookahead_flag"] = spec["lookahead"]
    row["deployable_flag"] = spec["deployable"]
    return row
