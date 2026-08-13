#!/usr/bin/env python3
"""Read-only verification for the public reproducibility repository."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "simulation"
TESTS = ROOT / "tests"
CONF = ROOT / "results" / "confirmatory"

SUITES = [
    "test_token_codec",
    "test_conditional_mask_oracle",
    "test_codec_mask_integration",
    "test_primary_action_spec",
    "test_reference_case_design",
    "test_reliability_estimand",
    "test_m2",
]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(SIM) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    ok = True
    for suite in SUITES:
        p = subprocess.run([sys.executable, "-m", "unittest", "-v", suite], cwd=TESTS, env=env)
        ok &= p.returncode == 0

    required = [
        "per_seed_metrics.csv",
        "primary_summary.csv",
        "pairwise_statistics.csv",
        "constraint_feasibility.csv",
        "run_manifest.json",
        "confirmatory_validation.json",
    ]
    print("\nConfirmatory archive:")
    for name in required:
        p = CONF / name
        if not p.exists():
            print(f"  MISSING  {name}")
            ok = False
        else:
            print(f"  {sha256(p)}  {name}")

    if (ROOT / "SHA256SUMS").exists():
        print("\nRelease checksum file: SHA256SUMS")
    print("\nVERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
