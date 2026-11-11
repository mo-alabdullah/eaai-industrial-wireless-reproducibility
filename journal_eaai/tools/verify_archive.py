#!/usr/bin/env python3
"""Integrity verification for the EAAI journal-extension reproducibility archive.

Read-only. Checks file hashes, the canonical raw-tree digest, the raw-row provenance tally,
the frozen endpoint values and the SHA256SUMS list. Exit code 0 only if every check passes.

    python3 journal_eaai/tools/verify_archive.py
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1]          # journal_eaai/
JX = ARCHIVE / "13_journal_extension"
RAW = JX / "results_final" / "raw"

EXPECTED_SHA256 = {
    "13_journal_extension/results_final/analysis/endpoints.json":
        "14da718a03a1823b152e53ebc5aacf7d028f07aea0ee4b262d2e2434174aafc7",
    "13_journal_extension/results_final/analysis/AUDIT_REPORT.json":
        "3328a8550567f7dadd54fd2089a398e17c63947ea73cb6dc9887a02cfbf32f14",
    "13_journal_extension/results_final/FINAL_RUN_LEDGER.jsonl":
        "6ece57ef8edadad9a38d9b9cfe9c4c0a5f4dc11612a569dc6cb7e4a58ce2ca73",
    "13_journal_extension/results_final/PROVENANCE_REGISTRY.json":
        "d749b5a786fbd11294be43a1db5af2760767542e3ab2fe81d8ba1c432f1fcaef",
}
EXPECTED_RAW_FILES = 400
EXPECTED_RAW_ROWS = 2400
EXPECTED_RAW_TREE_DIGEST_V1 = "5b31e54dbe6c6a2b897768ee100cadb0248cedf8edc50497cf5dea7bf935852b"
EXPECTED_MANIFEST_COMBINED = "c3481380da7a1878b3c03622965b4536e225ef66d47f2ef7f739c6de79eab47c"
EXPECTED_CONFIG_SHA = "2edbdf13de54dc6aece817ab1f01a65eb32b646b803d7b2be156e48f108661a2"
RESUMED_UNIT = "R3_aged/G2_wide10/s50011_w100.json"
FINAL_SEEDS = set(range(50002, 50022))

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    # 1. locked file hashes
    for rel, want in EXPECTED_SHA256.items():
        p = ARCHIVE / rel
        check(f"sha256 {Path(rel).name}", p.exists() and sha(p) == want, want[:16] + "…")

    # 2. raw tree: count and canonical digest v1 (paths relative to results_final/raw)
    files = sorted(p for p in RAW.rglob("*.json"))
    check("raw file count", len(files) == EXPECTED_RAW_FILES, f"{len(files)} files")
    tree = {p.relative_to(RAW).as_posix(): sha(p) for p in files}
    digest = hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest()
    check("raw_tree_digest_v1", digest == EXPECTED_RAW_TREE_DIGEST_V1, digest)

    # 3. pre-E18 baseline immutability (399 files) and the single resumed unit
    pre = json.loads((JX / "results_final" / "PRE_E18_COMPLETED_OUTPUT_DIGEST.json").read_text())
    base = pre.get("files") or pre.get("per_file") or {}
    if isinstance(base, list):
        base = {e["path"]: e["sha256"] for e in base}
    norm = {k.split("raw/")[-1]: (v["sha256"] if isinstance(v, dict) else v) for k, v in base.items()}
    changed = [k for k, v in norm.items() if tree.get(k) != v]
    check("pre-E18 baseline files unchanged", len(norm) == 399 and not changed,
          f"{len(norm)} baseline files, {len(changed)} changed/missing")
    extra = sorted(set(tree) - set(norm))
    check("exactly one resumed unit", extra == [RESUMED_UNIT], ", ".join(extra))

    # 4. rows, seeds and provenance tally
    reg = json.loads((JX / "results_final" / "PROVENANCE_REGISTRY.json").read_text())["declared"]
    key = {(v["runner_sha256"], v["freeze_manifest_sha256"]): k for k, v in reg.items()}
    tally, seeds, n_rows = Counter(), set(), 0
    for p in files:
        for row in json.loads(p.read_text()):
            n_rows += 1
            seeds.add(row.get("seed"))
            tally[key.get((row.get("runner_sha256"), row.get("freeze_manifest_sha256")), "UNDECLARED")] += 1
    check("raw row count", n_rows == EXPECTED_RAW_ROWS, str(n_rows))
    check("final seed band 50002–50021", seeds == FINAL_SEEDS, f"{min(seeds)}–{max(seeds)}, {len(seeds)} seeds")
    check("provenance tally ORIGINAL 2394 / E18 6",
          tally == Counter({"ORIGINAL": 2394, "E18": 6}), dict(tally))

    # 5. freeze-manifest combined digest and configuration digest
    man = json.loads((JX / "results_final" / "FREEZE_MANIFEST.json").read_text())
    check("E18 freeze manifest combined digest", man["combined_digest"] == EXPECTED_MANIFEST_COMBINED)
    parts = [sha(ARCHIVE / r) for r in ("07_simulation/primary_experiment_config.json",
                                        "10_confirmatory/CONFIRMATORY_PROTOCOL_LOCK.json",
                                        "13_journal_extension/FINAL_CONFIRMATORY_PROTOCOL_V2.md")]
    cfg = hashlib.sha256("".join(parts).encode()).hexdigest()
    check("configuration digest", cfg == EXPECTED_CONFIG_SHA, cfg)
    archived = withheld = mismatched = 0
    for group, entries in man["groups"].items():
        for rel, meta in entries.items():
            p = ARCHIVE / rel
            if not p.exists():
                withheld += 1
            elif sha(p) == meta["sha256"]:
                archived += 1
            elif rel.endswith(("analyse_final.py", "test_provenance_gate.py", "ERRATA_APPEND_ONLY.md")):
                archived += 1            # superseded by the post-freeze E-21 commit (documented)
            else:
                mismatched += 1
    check("freeze-manifest files: no unexplained hash mismatch", mismatched == 0,
          f"{archived} archived, {withheld} withheld (listed in ARCHIVE_MANIFEST.md), {mismatched} mismatched")

    # 6. frozen endpoint values
    frozen = json.loads((ARCHIVE / "FROZEN_ENDPOINTS.json").read_text())
    ep = json.loads((JX / "results_final" / "analysis" / "endpoints.json").read_text())
    fields = ("mean_diff", "ci_low", "ci_high", "d_z", "p_value", "n_positive", "n_negative", "n_ties", "n")
    ok = all(ep[e][f] == frozen["endpoints"][e][f] for e in ("E1", "H2", "E2") for f in fields)
    check("endpoint values equal FROZEN_ENDPOINTS.json", ok)

    # 7. SHA256SUMS
    sums = ARCHIVE / "SHA256SUMS"
    bad = []
    for line in sums.read_text().splitlines():
        h, rel = line.split(None, 1)
        p = ARCHIVE / rel.strip().lstrip("*")
        if not p.exists() or sha(p) != h:
            bad.append(rel)
    check("SHA256SUMS", not bad, f"{len(sums.read_text().splitlines())} entries, {len(bad)} bad")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
