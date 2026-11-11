#!/usr/bin/env python3
"""Recompute E1, H2 and E2 from the archived raw results IN MEMORY and compare them with the
frozen endpoints file. Nothing is written: the frozen analysis outputs are never touched.

It reuses the archived analysis functions (load_rows, provenance gate, run_endpoint) without
calling analyse_final.py's command-line entry point, which would overwrite the frozen outputs.
The BCa bootstrap uses its fixed seed (20260921) and the sign-flip test enumerates all 2^20
assignments, so the recomputation is deterministic. Runtime: a few seconds.

Comparison rule
  * floating-point estimates (mean_diff, ci_low, ci_high, d_z, and p_value when non-null) must
    agree within math.isclose(rel_tol=1e-12, abs_tol=1e-12). Summation order in the platform's
    floating-point library can move the last bits (differences of order 1e-17);
  * everything else is compared exactly: counts (n, n_positive, n_negative, n_ties,
    n_assignments), endpoint identity and role (endpoint, kind), and null versus non-null test
    status (an estimation endpoint must have no p-value, an inferential endpoint must have one);
  * the row count and the provenance tally are compared exactly.

    python3 journal_eaai/tools/reproduce_endpoints.py
"""
import json
import math
import sys
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1]
FINAL = ARCHIVE / "13_journal_extension" / "code" / "final"

REL_TOL = 1e-12
ABS_TOL = 1e-12
FLOAT_FIELDS = ("mean_diff", "ci_low", "ci_high", "d_z")
EXACT_FIELDS = ("endpoint", "kind", "n", "n_positive", "n_negative", "n_ties", "n_assignments")
EXPECTED_ROWS = 2400
EXPECTED_TALLY = {"ORIGINAL": 2394, "E18": 6}
ENDPOINTS = ("E1", "H2", "E2")


def floats_match(got, want) -> bool:
    if isinstance(got, bool) or isinstance(want, bool):
        return got is want
    if not isinstance(got, (int, float)) or not isinstance(want, (int, float)):
        return False
    return math.isclose(float(got), float(want), rel_tol=REL_TOL, abs_tol=ABS_TOL)


def compare_endpoint(got: dict, frozen: dict) -> list:
    """Return a list of human-readable problems; empty means the endpoint reproduces."""
    problems = []
    for f in EXACT_FIELDS:
        if got.get(f) != frozen.get(f):
            problems.append(f"{f}: recomputed {got.get(f)!r} != frozen {frozen.get(f)!r} (exact)")
    for f in FLOAT_FIELDS:
        g, w = got.get(f), frozen.get(f)
        if not floats_match(g, w):
            diff = abs(g - w) if isinstance(g, (int, float)) and isinstance(w, (int, float)) else "n/a"
            problems.append(f"{f}: recomputed {g!r} vs frozen {w!r}, |diff| = {diff}")
    g, w = got.get("p_value"), frozen.get("p_value")
    if (g is None) != (w is None):
        problems.append(f"p_value test status: recomputed {g!r} vs frozen {w!r} (null vs non-null)")
    elif g is not None and not floats_match(g, w):
        problems.append(f"p_value: recomputed {g!r} vs frozen {w!r}, |diff| = {abs(g - w)}")
    return problems


def main() -> int:
    sys.path.insert(0, str(FINAL))
    import analyse_final as A  # noqa: E402

    frozen = json.loads((A.OUT / "endpoints.json").read_text())
    rows = A.load_rows()
    audit = A.provenance_audit_block(rows, A.load_declared_provenance())
    tally = dict(audit["observed_tally"])
    print(f"rows: {len(rows)}; provenance tally: {tally}")
    failures = 0
    if len(rows) != EXPECTED_ROWS:
        print(f"ROWS: recomputed {len(rows)} != expected {EXPECTED_ROWS}"); failures += 1
    if tally != EXPECTED_TALLY:
        print(f"TALLY: recomputed {tally} != expected {EXPECTED_TALLY}"); failures += 1
    for eid in ENDPOINTS:
        got = A.run_endpoint(rows, eid)
        problems = compare_endpoint(got, frozen[eid])
        failures += bool(problems)
        status = "REPRODUCED" if not problems else "DIFFERS"
        print(f"{eid}: {status}")
        for f in FLOAT_FIELDS + ("p_value",):
            g, w = got.get(f), frozen[eid].get(f)
            d = abs(g - w) if isinstance(g, (int, float)) and isinstance(w, (int, float)) else None
            print(f"    {f:9s} recomputed {g!r:24s} frozen {w!r:24s} |diff| {d!r}")
        print(f"    counts    +{got.get('n_positive')}/-{got.get('n_negative')}/0:{got.get('n_ties')} n={got.get('n')}")
        for p in problems:
            print(f"    !! {p}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
