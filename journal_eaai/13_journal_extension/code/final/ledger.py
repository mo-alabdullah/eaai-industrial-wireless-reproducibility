#!/usr/bin/env python3
"""C11 — APPEND-ONLY REPRODUCIBILITY LEDGER (master pass, 2026-09-21).

One JSON line per state transition of a final-run unit. The file is opened in append mode only;
there is no update path and no delete path. A repeated run appends a new row carrying an explicit
supersession reason; the superseded row stays.

States: PLANNED -> STARTED -> COMPLETED | FAILED | CENSORED, plus INVALIDATED (post-hoc, by an
author action with a reason).

The ledger records execution facts only. It NEVER records a result interpretation, an endpoint
estimate, a p-value or any scientific conclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent
ROOT = JX.parent
LEDGER = JX / "results_final" / "FINAL_RUN_LEDGER.jsonl"

LEDGER_VERSION = "final-ledger-v1"
STATES = ("PLANNED", "STARTED", "COMPLETED", "FAILED", "CENSORED", "INVALIDATED")

# Interpretation-bearing keys that may never enter the ledger.
FORBIDDEN_KEYS = {"p_value", "mean_diff", "ci_low", "ci_high", "d_z", "conclusion",
                  "verdict", "significant", "estimate", "interpretation"}


class LedgerError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git() -> Dict[str, Any]:
    def run(*a):
        try:
            return subprocess.run(a, cwd=ROOT, capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except Exception:
            return ""
    commit = run("git", "rev-parse", "HEAD")
    status = run("git", "status", "--porcelain")
    return {"commit_sha": commit or "NOT_A_GIT_REPOSITORY",
            "worktree_clean": (status == "") if commit else None}


def _env() -> Dict[str, Any]:
    try:
        import numpy
        npv = numpy.__version__
    except Exception:
        npv = "UNAVAILABLE"
    return {"python": sys.version.split()[0], "numpy": npv,
            "os": platform.system(), "os_release": platform.release(),
            "machine": platform.machine(), "cpu_count": os.cpu_count()}


def sha256_file(p: Path) -> Optional[str]:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def unit_id(*, seed: int, regime: str, grid: str, comparator: str,
            K: int, N: int, H: int, warmup: int) -> str:
    """Deterministic identifier for one run unit."""
    return f"{regime}|{grid}|K{K}N{N}H{H}|w{warmup}|{comparator}|s{seed}"


def append(state: str, *, unit: str, seed: int, regime: str, grid: str,
           comparator: str, K: int, N: int, H: int, warmup: int,
           freeze_digest: str, runner_sha256: str, config_sha256: str,
           output_path: Optional[str] = None,
           log_reference: Optional[str] = None,
           supersedes: Optional[str] = None,
           supersession_reason: Optional[str] = None,
           failure_reason: Optional[str] = None,
           censor_reason: Optional[str] = None,
           extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append ONE immutable ledger row. Never updates or deletes an existing row."""
    if state not in STATES:
        raise LedgerError(f"unknown state {state!r}; permitted: {STATES}")
    if state == "INVALIDATED" and not supersession_reason:
        raise LedgerError("INVALIDATED requires an explicit supersession_reason")
    if supersedes and not supersession_reason:
        raise LedgerError("a superseding row requires supersession_reason")
    extra = dict(extra or {})
    bad = FORBIDDEN_KEYS & set(extra)
    if bad:
        raise LedgerError(f"the ledger records execution facts only; "
                          f"interpretation key(s) rejected: {sorted(bad)}")
    row = {
        "ledger_version": LEDGER_VERSION,
        "timestamp_utc": _utc(),
        "state": state,
        "unit_id": unit,
        "seed": seed, "regime": regime, "grid": grid, "comparator": comparator,
        "K": K, "N": N, "H": H, "warmup": warmup,
        "git": _git(),
        "environment": _env(),
        "freeze_manifest_digest": freeze_digest,
        "runner_sha256": runner_sha256,
        "config_sha256": config_sha256,
        "output_path": output_path,
        "output_sha256": sha256_file(Path(output_path)) if output_path else None,
        "log_reference": log_reference,
        "supersedes": supersedes,
        "supersession_reason": supersession_reason,
        "failure_reason": failure_reason,
        "censor_reason": censor_reason,
    }
    row.update(extra)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:                     # append-only, by construction
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def read_all() -> List[Dict[str, Any]]:
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]


def latest_state_by_unit() -> Dict[str, str]:
    """Last recorded state per unit (rows are append-only, so the last wins)."""
    out: Dict[str, str] = {}
    for r in read_all():
        out[r["unit_id"]] = r["state"]
    return out


def completeness_report(expected_units: List[str]) -> Dict[str, Any]:
    """Used by the analysis pipeline to reject partial datasets."""
    latest = latest_state_by_unit()
    done = [u for u in expected_units if latest.get(u) == "COMPLETED"]
    missing = [u for u in expected_units if u not in latest]
    failed = [u for u in expected_units if latest.get(u) == "FAILED"]
    censored = [u for u in expected_units if latest.get(u) == "CENSORED"]
    invalid = [u for u in expected_units if latest.get(u) == "INVALIDATED"]
    started = [u for u in expected_units if latest.get(u) == "STARTED"]
    return {
        "expected": len(expected_units), "completed": len(done),
        "missing": missing, "failed": failed, "censored": censored,
        "invalidated": invalid, "started_not_finished": started,
        "complete": not (missing or failed or invalid or started),
    }


if __name__ == "__main__":
    rows = read_all()
    print(f"ledger: {LEDGER}")
    print(f"rows  : {len(rows)}")
    if rows:
        from collections import Counter
        print("states:", dict(Counter(r["state"] for r in rows)))
    else:
        print("states: {} (no final run has been executed)")
