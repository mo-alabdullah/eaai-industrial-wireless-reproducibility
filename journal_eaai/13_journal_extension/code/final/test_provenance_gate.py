#!/usr/bin/env python3
"""MIXED-PROVENANCE ANALYSIS GATE — metadata-only synthetic tests (2026-10-05, erratum E-18).

The final campaign spans two execution provenances (399 units under the original frozen commit,
1 resumed unit under the E-18 commit). The analysis pipeline must accept that ONLY when it is
declared, and must reject an undeclared third provenance or a missing provenance.

Every row here is SYNTHETIC METADATA. No outcome column is populated, no final result file is
read, and no final-band seed or observed numeric literal appears.

Run:  python3 test_provenance_gate.py
"""
from __future__ import annotations

import hashlib
import json
import sys

import analyse_final as A

FAILS = []

# synthetic hash pairs — obviously fabricated placeholders, never real digests
OLD = ("a" * 64, "b" * 64)
E18 = ("c" * 64, "d" * 64)
THIRD = ("e" * 64, "f" * 64)
CFG = "9" * 64


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def declared(resolve_e18=True):
    d = {
        "ORIGINAL": {"status": "RESOLVED",
                     "runner_sha256": OLD[0], "freeze_manifest_sha256": OLD[1]},
        "E18": {"status": "RESOLVED" if resolve_e18 else "PENDING",
                "runner_sha256": E18[0] if resolve_e18 else "PENDING",
                "freeze_manifest_sha256": E18[1] if resolve_e18 else "PENDING"},
    }
    return d


def meta_rows(spec, config=CFG):
    """spec: list of (hash_pair, count). Metadata only — no outcome fields."""
    out = []
    for pair, n in spec:
        for _ in range(n):
            out.append({"runner_sha256": pair[0], "freeze_manifest_sha256": pair[1],
                        "config_sha256": config})
    return out


def expect_error(name, fn):
    try:
        fn()
        check(name, False, "no ProvenanceError raised")
    except A.ProvenanceError:
        check(name, True)


# ------------------------------------------------------------------ cases
def t_two_declared_accepted():
    rows = meta_rows([(OLD, 399), (E18, 1)])
    tally = A.assert_declared_provenance(rows, declared())
    check("declared set {OLD, E18} ACCEPTED", tally == {"ORIGINAL": 399, "E18": 1}, tally)


def t_single_provenance_not_assumed():
    """The gate must not require all rows to share one runner hash."""
    rows = meta_rows([(OLD, 399), (E18, 1)])
    hashes = {r["runner_sha256"] for r in rows}
    check("the accepted dataset really contains TWO runner hashes", len(hashes) == 2, hashes)
    A.assert_declared_provenance(rows, declared())
    check("gate does not collapse the campaign to one provenance", True)


def t_undeclared_third_rejected():
    rows = meta_rows([(OLD, 10), (E18, 1), (THIRD, 1)])
    expect_error("undeclared THIRD provenance REJECTED",
                 lambda: A.assert_declared_provenance(rows, declared()))


def t_missing_provenance_rejected():
    rows = meta_rows([(OLD, 5)])
    rows.append({"runner_sha256": None, "freeze_manifest_sha256": None, "config_sha256": CFG})
    expect_error("missing provenance REJECTED",
                 lambda: A.assert_declared_provenance(rows, declared()))
    rows2 = meta_rows([(OLD, 5)])
    rows2.append({"runner_sha256": OLD[0], "freeze_manifest_sha256": None, "config_sha256": CFG})
    expect_error("HALF-missing provenance pair REJECTED",
                 lambda: A.assert_declared_provenance(rows2, declared()))


def t_pending_entry_blocks():
    rows = meta_rows([(OLD, 399)])
    expect_error("a PENDING declared entry BLOCKS analysis",
                 lambda: A.assert_declared_provenance(rows, declared(resolve_e18=False)))


def t_config_digest_still_enforced():
    rows = meta_rows([(OLD, 5)]) + meta_rows([(E18, 1)], config="7" * 64)
    expect_error("differing config digest REJECTED despite declared provenance",
                 lambda: A.assert_declared_provenance(rows, declared()))


def t_ambiguous_registry_rejected():
    d = declared()
    d["E18"]["runner_sha256"] = OLD[0]
    d["E18"]["freeze_manifest_sha256"] = OLD[1]
    expect_error("registry with duplicate hash pairs REJECTED",
                 lambda: A.assert_declared_provenance(meta_rows([(OLD, 2)]), d))


def t_live_registry_shape():
    """The on-disk registry must parse, declare exactly {ORIGINAL, E18}, and block while PENDING."""
    try:
        d = A.load_declared_provenance()
    except A.ProvenanceError as e:
        check("live registry loads", False, str(e)[:90])
        return
    check("live registry declares exactly ORIGINAL and E18",
          set(d) == {"ORIGINAL", "E18"}, sorted(d))
    check("live registry ORIGINAL is resolved to concrete hashes",
          all(len(str(d["ORIGINAL"][k])) == 64 for k in A.PROVENANCE_KEYS))
    # 2026-10-06: the author has committed E-18 and regenerated the manifest, so this entry is
    # now RESOLVED. The earlier assertion that it is PENDING was correct only before that and is
    # replaced by the right post-resolution invariant; the PENDING-blocks behaviour is still
    # covered, on a synthetic registry, by t_pending_entry_blocks.
    check("live registry E18 is RESOLVED", d["E18"].get("status") == "RESOLVED",
          d["E18"].get("status"))
    check("live registry E18 is resolved to concrete hashes",
          all(len(str(d["E18"][k])) == 64 for k in A.PROVENANCE_KEYS))
    check("live registry declares a usable commit SHA for every label",
          all(r["commit_sha"] and len(r["commit_sha"]) == 40
              for r in A.canonical_registry_snapshot(d)),
          [r["commit_sha"] for r in A.canonical_registry_snapshot(d)])
    check("live registry declares two DISTINCT commits",
          len({r["commit_sha"] for r in A.canonical_registry_snapshot(d)}) == 2)


def t_no_final_literals():
    src = open(__file__).read()
    band = [str(s) for s in range(50001, 50022)]
    hits = [s for s in band if s in src and f"range({s}" not in src]
    check("test file contains no final-band seed literal", not hits, hits)
    # The real campaign digest prefixes are assembled from halves so that no forbidden prefix
    # appears verbatim in this file — otherwise this very assertion would make the check fail.
    forbidden = ["82df" + "6ed1", "56e2" + "a357", "2edb" + "df13"]
    present = [f for f in forbidden if f in src]
    check("test file contains no real campaign digest", not present, present)
    # the declared registry must of course still hold them; this file must not
    check("synthetic hash pairs are obvious placeholders",
          set(OLD + E18 + THIRD) <= {c * 64 for c in "abcdef"})


# ------------------------------------------------------------------ audit snapshot (§1)
def _out_inventory():
    """Byte-hash inventory of the analysis output directory. Read-only; parses nothing."""
    if not A.OUT.exists():
        return {}
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(A.OUT.rglob("*")) if p.is_file()}


def _with_temp_registry(payload_bytes, fn):
    """Point the module at a temporary synthetic registry, run fn(), always restore.

    The real registry file is never written, moved or modified by these tests.
    """
    import tempfile
    from pathlib import Path
    original = A.PROVENANCE_REGISTRY
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "PROVENANCE_REGISTRY.json"
        p.write_bytes(payload_bytes)
        A.PROVENANCE_REGISTRY = p
        try:
            return fn(p)
        finally:
            A.PROVENANCE_REGISTRY = original


def synthetic_registry_bytes(resolve_e18=True, pad=""):
    d = declared(resolve_e18)
    payload = {
        "registry_version": "synthetic",
        "note": "synthetic test registry" + pad,
        "declared": {
            "ORIGINAL": {**d["ORIGINAL"], "commit_sha": "1" * 40, "units": 399},
            "E18": {**d["E18"], "commit_sha": "2" * 40 if resolve_e18 else "PENDING", "units": 1},
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode()


def t_audit_registry_hash_is_exact_bytes():
    raw = synthetic_registry_bytes()
    expect = hashlib.sha256(raw).hexdigest()

    def body(p):
        rows = meta_rows([(OLD, 399), (E18, 1)])
        blk = A.provenance_audit_block(rows, json.loads(raw)["declared"])
        check("audit: recorded sha256 equals sha256 of the exact registry bytes",
              blk["registry_sha256"] == expect, (blk["registry_sha256"][:16], expect[:16]))
        check("audit: recorded sha256 is a full 64-hex digest",
              len(blk["registry_sha256"]) == 64)
        return blk

    blk = _with_temp_registry(raw, body)

    # (C) observed tally, (D) common config digest
    check("audit: observed tally per label recorded",
          blk["observed_tally"] == {"E18": 1, "ORIGINAL": 399}, blk["observed_tally"])
    check("audit: common config digest recorded",
          blk["config_sha256_common"] == CFG, blk["config_sha256_common"])
    check("audit: row count recorded", blk["n_rows_audited"] == 400, blk["n_rows_audited"])
    check("audit: registry declared NOT tracked and NOT in the freeze set",
          blk["registry_tracked_by_git"] is False and blk["registry_in_freeze_set"] is False)
    check("audit: exclusion reason recorded", "circular" in blk["registry_excluded_reason"])


def t_audit_snapshot_is_deterministic_and_complete():
    d = json.loads(synthetic_registry_bytes())["declared"]
    s1 = A.canonical_registry_snapshot(d)
    s2 = A.canonical_registry_snapshot(dict(reversed(list(d.items()))))
    check("audit: snapshot is byte-identical across two calls and insertion orders",
          json.dumps(s1, sort_keys=False) == json.dumps(s2, sort_keys=False), (s1, s2))
    check("audit: snapshot labels are sorted", [r["label"] for r in s1] == ["E18", "ORIGINAL"],
          [r["label"] for r in s1])
    required = {"label", "commit_sha", "runner_sha256", "freeze_manifest_digest", "units"}
    for r in s1:
        check(f"audit: snapshot row {r['label']} carries every required field",
              required <= set(r), sorted(set(r)))
    check("audit: freeze_manifest_digest is populated from the registry field",
          all(r["freeze_manifest_digest"] for r in s1), s1)
    check("audit: snapshot carries no timestamp",
          not any("time" in k or "utc" in k for r in s1 for k in r))


def t_audit_one_byte_change_changes_the_hash():
    a = synthetic_registry_bytes()
    b = synthetic_registry_bytes(pad=" ")           # one extra byte, same declared content
    check("audit: the two synthetic registries differ by exactly one byte",
          len(b) - len(a) == 1, (len(a), len(b)))

    def grab(_p):
        return A.registry_bytes_sha256()

    ha = _with_temp_registry(a, grab)
    hb = _with_temp_registry(b, grab)
    check("audit: a one-byte change changes the recorded hash", ha != hb, (ha[:12], hb[:12]))
    check("audit: hash a matches hashlib over bytes a", ha == hashlib.sha256(a).hexdigest())
    check("audit: hash b matches hashlib over bytes b", hb == hashlib.sha256(b).hexdigest())


def t_audit_blocked_while_pending():
    raw = synthetic_registry_bytes(resolve_e18=False)

    def body(_p):
        rows = meta_rows([(OLD, 399)])
        try:
            A.provenance_audit_block(rows, json.loads(raw)["declared"])
            check("audit: PENDING registry still BLOCKS the audit block", False, "no error")
        except A.ProvenanceError:
            check("audit: PENDING registry still BLOCKS the audit block", True)

    _with_temp_registry(raw, body)


def t_audit_reads_no_final_data():
    """The audit block must be computable from metadata alone — never from raw final files."""
    raw = synthetic_registry_bytes()
    before = sorted(p.name for p in A.RAW.rglob("*.json")) if A.RAW.exists() else []
    out_inv = _out_inventory()

    def body(_p):
        rows = meta_rows([(OLD, 2), (E18, 1)])
        blk = A.provenance_audit_block(rows, json.loads(raw)["declared"])
        # no outcome column was ever present in the synthetic rows
        outcome_cols = {"realised_delivery", "aggregate_power_w", "gap_H_G", "term_distortion"}
        check("audit: synthetic rows carry no outcome column",
              not any(outcome_cols & set(r) for r in rows))
        check("audit: block computed from metadata alone", blk["n_rows_audited"] == 3)
        return blk

    _with_temp_registry(raw, body)
    after = sorted(p.name for p in A.RAW.rglob("*.json")) if A.RAW.exists() else []
    check("audit: the raw final directory was neither read into nor modified",
          before == after, (len(before), len(after)))
    # 2026-10-06: the analysis has now legitimately run once, so OUT exists. The invariant is no
    # longer "it must not exist" but "this test must not add to or alter it".
    check("audit: the analysis output directory was neither added to nor altered",
          out_inv == _out_inventory(), (len(out_inv), len(_out_inventory())))


# ------------------------------------------------------------------ E-21 commit-field mapping
SYN_COMMIT_ORIGINAL = "1" * 40
SYN_COMMIT_E18 = "2" * 40


def e21_declared(original_commit=SYN_COMMIT_ORIGINAL, e18_commit=SYN_COMMIT_E18,
                 omit_original_commit=False):
    """Synthetic registry entries using the RUNTIME field name `git_commit`."""
    d = {
        "ORIGINAL": {"status": "RESOLVED", "units": 399,
                     "runner_sha256": OLD[0], "freeze_manifest_sha256": OLD[1],
                     "git_commit": original_commit},
        "E18": {"status": "RESOLVED", "units": 1,
                "runner_sha256": E18[0], "freeze_manifest_sha256": E18[1],
                "git_commit": e18_commit},
    }
    if omit_original_commit:
        del d["ORIGINAL"]["git_commit"]
    return d


def t_e21_git_commit_mapped_to_commit_sha():
    d = e21_declared()
    check("E-21 A. registry entries use git_commit, not commit_sha",
          all("git_commit" in e and "commit_sha" not in e for e in d.values()))
    snap = {r["label"]: r for r in A.canonical_registry_snapshot(d)}
    check("E-21 A. audit schema still exposes commit_sha",
          all("commit_sha" in r for r in snap.values()), sorted(snap["E18"]))
    check("E-21 B. ORIGINAL synthetic commit appears exactly in commit_sha",
          snap["ORIGINAL"]["commit_sha"] == SYN_COMMIT_ORIGINAL, snap["ORIGINAL"]["commit_sha"])
    check("E-21 C. E18 synthetic commit appears exactly in commit_sha",
          snap["E18"]["commit_sha"] == SYN_COMMIT_E18, snap["E18"]["commit_sha"])
    check("E-21 . other snapshot fields unaffected by the mapping",
          snap["ORIGINAL"]["runner_sha256"] == OLD[0]
          and snap["ORIGINAL"]["freeze_manifest_digest"] == OLD[1]
          and snap["ORIGINAL"]["units"] == 399
          and snap["ORIGINAL"]["status"] == "RESOLVED", snap["ORIGINAL"])
    check("E-21 . no snapshot commit_sha is null",
          all(r["commit_sha"] is not None for r in snap.values()))


def t_e21_bad_commit_rejected():
    expect_error("E-21 D. missing git_commit REJECTED",
                 lambda: A.canonical_registry_snapshot(e21_declared(omit_original_commit=True)))
    expect_error("E-21 E. git_commit == PENDING REJECTED",
                 lambda: A.canonical_registry_snapshot(e21_declared(e18_commit="PENDING")))
    for bad, label in (("" , "empty"), ("abc123", "too short"), ("3" * 41, "too long"),
                       ("A" * 40, "uppercase"), ("g" * 40, "non-hex"), (None, "None"),
                       (12345, "non-string")):
        expect_error(f"E-21 F. malformed git_commit ({label}) REJECTED",
                     lambda b=bad: A.canonical_registry_snapshot(e21_declared(e18_commit=b)))


def t_e21_snapshot_still_deterministic():
    d = e21_declared()
    s1 = A.canonical_registry_snapshot(d)
    s2 = A.canonical_registry_snapshot(dict(reversed(list(d.items()))))
    check("E-21 G. snapshot byte-equivalent across insertion orders",
          json.dumps(s1) == json.dumps(s2), (s1, s2))
    check("E-21 G. snapshot stable across repeated calls",
          json.dumps(A.canonical_registry_snapshot(d)) == json.dumps(s1))
    check("E-21 G. labels still sorted", [r["label"] for r in s1] == ["E18", "ORIGINAL"])


def t_e21_no_outcome_field_needed():
    d = e21_declared()
    outcome_cols = {"realised_delivery", "aggregate_power_w", "gap_H_G", "term_distortion",
                    "objective_value"}
    check("E-21 H. registry entries contain no outcome field",
          not any(outcome_cols & set(e) for e in d.values()))
    snap = A.canonical_registry_snapshot(d)
    check("E-21 H. snapshot built with no outcome field present",
          not any(outcome_cols & set(r) for r in snap))
    check("E-21 H. snapshot exposes only provenance metadata",
          all(set(r) == {"label", *A.SNAPSHOT_FIELDS} for r in snap), sorted(snap[0]))


def t_registry_not_tracked_not_frozen():
    """The exclusion must be real, not merely asserted in the audit block."""
    import subprocess
    root = A.JX.parent
    rel = str(A.PROVENANCE_REGISTRY.relative_to(root))
    p = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                       cwd=root, capture_output=True, text=True)
    check("registry is NOT tracked by git", p.returncode != 0, p.stdout.strip())
    q = subprocess.run(["git", "check-ignore", rel], cwd=root, capture_output=True, text=True)
    check("registry IS git-ignored", q.returncode == 0, q.stdout.strip())
    fm = open(A.HERE / "freeze_manifest.py").read()
    check("registry is NOT in the C13 freeze set", "PROVENANCE_REGISTRY" not in fm)


def main():
    print("MIXED-PROVENANCE GATE TESTS (synthetic metadata only)\n")
    for fn in (t_two_declared_accepted, t_single_provenance_not_assumed,
               t_undeclared_third_rejected, t_missing_provenance_rejected,
               t_pending_entry_blocks, t_config_digest_still_enforced,
               t_ambiguous_registry_rejected, t_live_registry_shape,
               t_audit_registry_hash_is_exact_bytes,
               t_audit_snapshot_is_deterministic_and_complete,
               t_audit_one_byte_change_changes_the_hash,
               t_audit_blocked_while_pending, t_audit_reads_no_final_data,
               t_e21_git_commit_mapped_to_commit_sha, t_e21_bad_commit_rejected,
               t_e21_snapshot_still_deterministic, t_e21_no_outcome_field_needed,
               t_registry_not_tracked_not_frozen, t_no_final_literals):
        print(f"{fn.__name__}:")
        fn()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {FAILS}")
        return 1
    print("ALL MIXED-PROVENANCE GATE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
