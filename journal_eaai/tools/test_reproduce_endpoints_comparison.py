#!/usr/bin/env python3
"""Regression test for the endpoint-reproduction comparison rule (synthetic values only).

    python3 journal_eaai/tools/test_reproduce_endpoints_comparison.py
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reproduce_endpoints import compare_endpoint  # noqa: E402

BASE = {"endpoint": "E1", "kind": "estimation", "mean_diff": -0.10271015387000001,
        "ci_low": -0.13656984388172527, "ci_high": -0.07497526179382613, "d_z": -1.4249696059493875,
        "p_value": None, "n": 20, "n_positive": 0, "n_negative": 20, "n_ties": 0, "n_assignments": None}
H2 = {"endpoint": "H2", "kind": "inference", "mean_diff": 0.4699999999999999,
      "ci_low": 0.21999999999999997, "ci_high": 0.7100000000000002, "d_z": 0.7985382421760168,
      "p_value": 0.003204345703125, "n": 20, "n_positive": 14, "n_negative": 3, "n_ties": 3,
      "n_assignments": 1048576}

failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


def variant(base, **kw):
    v = copy.deepcopy(base); v.update(kw); return v


print("ENDPOINT COMPARISON RULE")
# 1. last-bit representation differences pass
check("identical values pass", compare_endpoint(BASE, BASE) == [])
check("ci_low differing by 5e-17 passes",
      compare_endpoint(variant(BASE, ci_low=-0.13656984388172522), BASE) == [])
check("every float field differing by ~1e-17 passes",
      compare_endpoint(variant(H2, mean_diff=0.47, ci_low=0.22, ci_high=0.71,
                               d_z=0.7985382421760168 + 1e-16, p_value=0.003204345703125 + 1e-17), H2) == [])
# 2. meaningful numerical differences fail
for f in ("mean_diff", "ci_low", "ci_high", "d_z"):
    check(f"{f} differing by 1e-8 fails", compare_endpoint(variant(BASE, **{f: BASE[f] + 1e-8}), BASE) != [])
check("p_value differing by 1e-8 fails", compare_endpoint(variant(H2, p_value=H2["p_value"] + 1e-8), H2) != [])
# 3. counts, identity and test status are exact
for f, v in (("n_positive", 1), ("n_negative", 19), ("n_ties", 1), ("n", 19)):
    check(f"{f} off by one fails", compare_endpoint(variant(BASE, **{f: v}), BASE) != [])
check("n_assignments mismatch fails", compare_endpoint(variant(H2, n_assignments=1048575), H2) != [])
check("endpoint role mismatch fails", compare_endpoint(variant(BASE, kind="inference"), BASE) != [])
check("estimation endpoint acquiring a p-value fails", compare_endpoint(variant(BASE, p_value=0.5), BASE) != [])
check("inferential endpoint losing its p-value fails", compare_endpoint(variant(H2, p_value=None), H2) != [])
check("integer count given as float with tiny offset fails (exact)",
      compare_endpoint(variant(BASE, n_negative=20.0000000000001), BASE) != [])

print("\nALL COMPARISON-RULE TESTS PASSED" if not failures else f"\nFAILED {len(failures)}: {failures}")
sys.exit(1 if failures else 0)
