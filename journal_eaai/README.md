# Exact Optimization References for Industrial Wireless Uplinks — Reproducibility Archive

Archive author and maintainer: **Mohammed Alabdullah** (ORCID [0009-0001-0826-4380](https://orcid.org/0009-0001-0826-4380)),
Iran University of Science and Technology, Computer Networks Engineering, Tehran, Iran — m.w@sudo-gate.com

This directory is the reproducibility archive for the journal extension of the study. It contains
the exact optimisation references (fixed-demand allocation, continuous-power reference, offline
finite-horizon aged-gain and current-gain references), the frozen confirmatory campaign
(400 execution units, 2,400 result rows), the final analysis, the descriptive extraction, the
deterministic figure generator and the integrity records.

## Branch separation

| branch | content |
|---|---|
| `main` | Conference artifact (original reproducibility package). Unchanged by this archive. |
| `journal-eaai-extension` | This journal-extension archive, added under `journal_eaai/`. |

## What the archive supports

1. **Integrity verification** of every frozen output (seconds).
2. **Recomputation of the three endpoints E1, H2 and E2** from the archived raw results, in
   memory, with a comparison against the frozen values (seconds). No confirmatory unit is rerun.
3. **Byte-identical regeneration of Figures 1–3** from the frozen outputs.
4. **Regeneration of the descriptive summaries** from the raw results.
5. **The exactness and numerical-tolerance test suites.**

A full rerun of the confirmatory campaign is not required to reproduce any reported value; see
`REPRODUCIBILITY.md` §5.

## Directory structure

Original project-relative paths are preserved below `journal_eaai/`. The freeze manifest, the
runner and the analysis pipeline resolve paths relative to the project root, so moving files
would break provenance verification. `ARCHIVE_MANIFEST.md` maps each path to its role.

```
journal_eaai/
  README.md  REPRODUCIBILITY.md  ARCHIVE_MANIFEST.md  PRE_RELEASE_CHECKLIST.md
  RELEASE_NOTES_DRAFT.md  FROZEN_ENDPOINTS.json  SHA256SUMS
  tools/                         verify_archive.py, reproduce_endpoints.py
  07_simulation/                 simulator (channel, mobility, environment, codec, mask oracle)
  10_confirmatory/               configuration lock read by the runner's configuration digest
  13_journal_extension/
    code/final/                  run_final.py, analyse_final.py, extract_descriptive.py,
                                 stats.py, schema.py, ledger.py, freeze_manifest.py, tests,
                                 requirements-final.lock.txt
    code/optimization/           exact references: radio.py (fixed-demand, continuous),
                                 joint.py (offline finite-horizon), grids.py, capture.py, audits
    code/                        baselines_v2.py, evaluation.py, development-stage runners
    tests/                       exactness test suite (14 tests)
    results_final/               FINAL evidence: raw/ (400 files), analysis/, ledger, manifests,
                                 provenance registry
    results/                     DEVELOPMENT evidence (development seeds only)
    journal_eaai/figures/        generate_final_figures.py, Figures 1–3, FIGURE_PROVENANCE.json
    journal_eaai/tables/         TABLE_R1 … TABLE_R6 (final table records)
    *.md                         protocol, hypotheses register, seed-reseal amendment,
                                 incident record, E18 correction records
```

## Install

Python 3.10 and NumPy 2.2.6 reproduce the frozen environment (`requirements-final.lock.txt`).
Matplotlib is needed only to render figures (byte identity was verified with Matplotlib 3.10.9).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r journal_eaai/13_journal_extension/code/final/requirements-final.lock.txt
pip install matplotlib==3.10.9        # figures only
```

## Verify and reproduce (from the repository root)

```bash
python3 journal_eaai/tools/verify_archive.py          # hashes, raw-tree digest, seeds, provenance
python3 journal_eaai/tools/reproduce_endpoints.py     # E1, H2, E2 recomputed in memory
```

Further steps (figures, descriptive summaries, tests) are in `REPRODUCIBILITY.md`.

## FINAL versus DEVELOPMENT evidence

| tier | location | seeds | role |
|---|---|---|---|
| FINAL (confirmatory) | `13_journal_extension/results_final/` | 50002–50021 (20 paired seeds) | Only source of E1, H2, E2, the decomposition and final runtimes |
| DEVELOPMENT | `13_journal_extension/results/` | development seeds only | Design, learned-controller context and per-solve latency; never pooled with FINAL values |

Seed 50001 is permanently excluded (procedural incident I-01, Amendment A3); 50021 replaced it.

## Frozen endpoint snapshot (R3 × wide grid, n = 20 paired seeds)

| endpoint | contrast | estimate | 95 % BCa | d_z | +/−/0 | test |
|---|---|---|---|---|---|---|
| H2 (sole inferential) | offline aged-gain reference − causal EDF with exact fixed-demand allocation | +0.47 deliveries | [0.22, 0.71] | 0.799 | 14/3/3 | exact paired two-sided sign-flip, p = 0.00320435 |
| E1 (estimation) | exact fixed-demand − heuristic (aggregate power) | −0.10271 W | [−0.13657, −0.07498] | −1.425 | 0/20/0 | none |
| E2 (estimation) | offline current-gain − offline aged-gain reference | +1.58 deliveries | [1.28, 1.84] | 2.412 | 20/0/0 | none |

Full-precision values: `FROZEN_ENDPOINTS.json`. The finite-horizon references are offline,
noncausal and non-deployable; the continuous-power reference is a mathematical lower reference.

## Licence and citation

Code and data are released under the MIT licence (see `CITATION.cff` and `.zenodo.json` at the
repository root for the archive citation record).
