#!/usr/bin/env python3
"""C13 — DETERMINISTIC FREEZE MANIFEST (master pass, 2026-09-21).

Captures the exact state of every artefact the final confirmatory run depends on. The runner
REFUSES to execute unless the current files reproduce this manifest byte for byte.

Usage:
    python3 freeze_manifest.py --write      # create/refresh the manifest (an author action)
    python3 freeze_manifest.py --verify     # compare the working tree against the manifest

Rule (binding): hashes are NEVER silently refreshed after a code change. A mismatch stops final
execution. Re-freezing is an explicit, dated author action and must be accompanied by a protocol
amendment if any scientific file changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
JX = HERE.parent.parent                      # 13_journal_extension
ROOT = JX.parent                             # project root
SIM = ROOT / "07_simulation"
MANIFEST = JX / "results_final" / "FREEZE_MANIFEST.json"

MANIFEST_VERSION = "freeze-manifest-v1"

# Every file whose content can change a final number, plus the governing protocol documents.
TRACKED = {
    "simulator": [
        SIM / "m2" / "env.py", SIM / "m2" / "channel.py", SIM / "m2" / "config.py",
        SIM / "m2" / "mobility.py", SIM / "m2" / "agents_ppo.py", SIM / "m2" / "metrics.py",
        SIM / "token_codec.py", SIM / "conditional_mask_oracle.py",
        SIM / "primary_experiment_config.json",
    ],
    "exact_framework": [
        JX / "code" / "optimization" / "radio.py",
        JX / "code" / "optimization" / "joint.py",
        JX / "code" / "optimization" / "grids.py",
        JX / "code" / "optimization" / "capture.py",
        JX / "code" / "baselines_v2.py",
        JX / "code" / "evaluation.py",
    ],
    "final_pipeline": [
        HERE / "schema.py", HERE / "stats.py", HERE / "ledger.py",
        HERE / "run_final.py", HERE / "analyse_final.py", HERE / "test_stats.py",
        HERE / "test_pairing.py", HERE / "test_integration_nonfinal.py",
        HERE / "test_seed_reseal_a3.py",
        HERE / "test_numerical_tolerance_e18.py",
        HERE / "test_provenance_gate.py",
        HERE / "requirements-final.lock.txt",
    ],
    "exactness_tests": [
        JX / "tests" / "test_optimization_benchmark.py",
    ],
    "protocol": [
        JX / "JOURNAL_PROTOCOL_V1.md",
        JX / "FINAL_CONFIRMATORY_PROTOCOL_V2.md",
        JX / "PRIMARY_HYPOTHESES_REGISTER.md",
        JX / "FINAL_TEST_READINESS_CHECKLIST.md",
        JX / "AMENDMENT_A3_FINAL_SEED_RESEAL.md",
        JX / "INCIDENT_I01_RECORD.md",
        JX / "ERRATA_APPEND_ONLY.md",
    ],
    "frozen_manuscript_sections": [
        JX / "journal_eaai" / "_stage5d_intro_body.txt",
        JX / "journal_eaai" / "_stage6e_related_work_body.txt",
        JX / "journal_eaai" / "_stage7a_system_model_body.txt",
        JX / "journal_eaai" / "_stage7b_framework_body.txt",
        JX / "journal_eaai" / "_stage7c_controller_body.txt",
        JX / "journal_eaai" / "_stage7d_experimental_design_body.txt",
    ],
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


_SHA_RE = __import__("re").compile(r"^[0-9a-f]{40}$")


def git_state() -> dict:
    """Capture VCS state. A commit SHA is accepted ONLY if it is a real 40-hex object id.

    2026-09-21: hardened. On an unborn branch `git rev-parse HEAD` writes the literal string
    "HEAD" to stdout while failing on stderr, which an earlier version would have recorded as a
    commit SHA. The return code is now checked AND the output is format-validated, so a
    repository with no commits can never masquerade as an anchored one.
    """
    def run(*a):
        try:
            p = subprocess.run(a, cwd=ROOT, capture_output=True, text=True, timeout=20)
            return (p.returncode == 0), p.stdout.strip()
        except Exception:
            return False, ""

    ok_c, commit = run("git", "rev-parse", "HEAD")
    ok_b, branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    ok_s, status = run("git", "status", "--porcelain")
    ok_r, root = run("git", "rev-parse", "--show-toplevel")

    valid = ok_c and bool(_SHA_RE.match(commit))
    if not valid:
        reason = ("no repository" if not ok_r
                  else "repository exists but has no commits (unborn HEAD)")
        return {
            "git_available": False,
            "commit_sha": "NO_AUTHORITATIVE_COMMIT",
            "reason": reason,
            "branch": branch if ok_b else None,
            "repo_root": root if ok_r else None,
            "worktree_clean": None,
            "worktree_dirty_files": [],
        }
    return {
        "git_available": True,
        "commit_sha": commit,
        "branch": branch if ok_b else None,
        "repo_root": root if ok_r else None,
        "worktree_clean": (status == "") if ok_s else None,
        "worktree_dirty_files": [l[3:] for l in status.splitlines()] if status else [],
    }


def environment() -> dict:
    try:
        import numpy
        npv = numpy.__version__
    except Exception:
        npv = "UNAVAILABLE"
    return {
        "python_version": sys.version.split()[0],
        "numpy_version": npv,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "cpu_count": __import__("os").cpu_count(),
    }


def build() -> dict:
    groups, missing = {}, []
    for group, paths in TRACKED.items():
        entries = {}
        for p in paths:
            rel = str(p.relative_to(ROOT))
            if not p.exists():
                missing.append(rel)
                entries[rel] = None
                continue
            entries[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
        groups[group] = entries
    group_digests = {
        g: hashlib.sha256(
            json.dumps({k: v for k, v in sorted(e.items())}, sort_keys=True).encode()
        ).hexdigest()
        for g, e in groups.items()
    }
    combined = hashlib.sha256(
        json.dumps(group_digests, sort_keys=True).encode()).hexdigest()
    return {
        "manifest_version": MANIFEST_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "environment": environment(),
        "groups": groups,
        "group_digests": group_digests,
        "combined_digest": combined,
        "missing_files": missing,
    }


def verify() -> tuple[bool, list[str]]:
    if not MANIFEST.exists():
        return False, [f"freeze manifest absent: {MANIFEST}"]
    stored = json.loads(MANIFEST.read_text())
    current = build()
    problems = []
    if stored.get("manifest_version") != MANIFEST_VERSION:
        problems.append(f"manifest version mismatch: {stored.get('manifest_version')}")
    for group, entries in stored.get("groups", {}).items():
        cur = current["groups"].get(group, {})
        for rel, meta in entries.items():
            c = cur.get(rel)
            if meta is None and c is None:
                problems.append(f"{group}: {rel} MISSING in both manifest and worktree")
            elif meta is None:
                problems.append(f"{group}: {rel} absent from the manifest but present now")
            elif c is None:
                problems.append(f"{group}: {rel} MISSING from the worktree")
            elif c["sha256"] != meta["sha256"]:
                problems.append(f"{group}: {rel} CHANGED "
                                f"({meta['sha256'][:12]} -> {c['sha256'][:12]})")
    if current["combined_digest"] != stored.get("combined_digest"):
        problems.append("combined digest mismatch")

    # ---- C13 VCS REQUIREMENT (2026-09-21) --------------------------------------------------
    # A content-hash manifest proves the files did not change since it was written. It does NOT
    # provide an authoritative, externally verifiable provenance anchor. The final confirmatory
    # run requires a real commit SHA, so the absence of a repository is a HARD BLOCKER and is
    # reported as such rather than passing silently.
    g = current["git"]
    if not g["git_available"]:
        problems.append(
            f"C13 BLOCKED — NO AUTHORITATIVE GIT COMMIT AVAILABLE ({g.get('reason')}). "
            "The manifest is a CONTENT-HASH manifest only and is NOT a provenance anchor. "
            "Commit the study tree (an author action), then rebuild the manifest.")
    elif not g["worktree_clean"]:
        problems.append(f"git worktree DIRTY: {g['worktree_dirty_files'][:10]}")
    else:
        stored_git = stored.get("git", {})
        if stored_git.get("commit_sha") != g["commit_sha"]:
            problems.append(
                f"C13 HEAD MISMATCH: manifest was frozen at "
                f"{str(stored_git.get('commit_sha'))[:12]} but HEAD is now "
                f"{g['commit_sha'][:12]}. The manifest is never silently refreshed.")
    return (not problems), problems


def main() -> int:
    ap = argparse.ArgumentParser(description="C13 freeze manifest")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="create/refresh (explicit author action)")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.write:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        m = build()
        MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
        print(f"FREEZE MANIFEST WRITTEN: {MANIFEST}")
        print(f"  combined digest : {m['combined_digest']}")
        print(f"  files tracked   : {sum(len(v) for v in m['groups'].values())}")
        if m["missing_files"]:
            print(f"  MISSING         : {m['missing_files']}")
        return 0
    if a.show:
        print(json.dumps(build(), indent=2, sort_keys=True))
        return 0
    ok, problems = verify()
    print("FREEZE MANIFEST VERIFY:", "MATCH" if ok else "MISMATCH")
    for p in problems:
        print("  -", p)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
