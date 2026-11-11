# Pre-release checklist — v2.0.0-eaai-reproducibility

The tag and the GitHub release are created only if every item passes.

| gate | check | how |
|---|---|---|
| A | Working branch is `journal-eaai-extension` | `git rev-parse --abbrev-ref HEAD` |
| B | 400 raw result files | `tools/verify_archive.py` |
| C | Final seeds 50002–50021 (20 paired seeds) | `tools/verify_archive.py` |
| D | Seed 50001 excluded and documented | `INCIDENT_I01_RECORD.md`, `AMENDMENT_A3_FINAL_SEED_RESEAL.md`, `run_final.py` seed guard |
| E | Endpoints equal the frozen values | `tools/verify_archive.py`, `tools/reproduce_endpoints.py` |
| F | raw_tree_digest_v1 = `5b31e54d…935852b` | `tools/verify_archive.py` |
| G | endpoints.json SHA-256 = `14da718a…4aafc7` | `tools/verify_archive.py` |
| H | AUDIT_REPORT.json SHA-256 = `3328a855…4f32f14` | `tools/verify_archive.py` |
| I | FINAL_RUN_LEDGER.jsonl SHA-256 = `6ece57ef…2ca73` | `tools/verify_archive.py` |
| J | Final runner, analysis, descriptive extraction, exact references, figure generator, tests and configuration present | `ARCHIVE_MANIFEST.md` |
| K | No secret, credential file, cache or file larger than 50 MB | repository scan |
| L | No manuscript file required by any script | `ARCHIVE_MANIFEST.md` |
| M | Documentation and metadata limited to the study, its code and its data | repository scan |
| N | Archive author metadata: Mohammed Alabdullah only | `CITATION.cff`, `.zenodo.json` |
| O | README and REPRODUCIBILITY commands execute as documented | run each command on a fresh clone |
| P | `git status` clean | `git status --porcelain` |
| Q | `main` unchanged; branch adds only `journal_eaai/`, `CITATION.cff`, `.zenodo.json`, `LICENSE` | `git diff --name-status origin/main...HEAD` |
| R | Figures 1–3 regenerate byte-identically | `REPRODUCIBILITY.md` §4 |
