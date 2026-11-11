# E-18 — POST-OPENING NUMERICAL-VALIDATION CORRECTION AND RESUME PREFLIGHT

Stage date: 2026-10-05. Scope: floating-point validation robustness and resume preflight **only**.

No completed scientific outcome was inspected. The 399 completed units were not summarised, read
or parsed. `analyse_final.py` was not invoked. No endpoint (E1, H2, E2), interval, p-value or
effect size was computed. No final seed was executed in this stage.

---

## 1. FAILURE CLASSIFICATION

**Classification: NUMERICAL ROUND-OFF. Not a scientific defect, not a model defect, not a bug in
the exact solver.**

The failing unit is `R3_aged|G2_wide10|K8N4H3|w100|ALL|s50011`, which failed schema validation with

```
SchemaError: term_distortion must be non-negative, got -6.938893903907228e-18
```

`term_distortion = C_AG − C` is the third element of the frozen three-term identity

```
H_G − C = (H_G − E_G) + (E_G − C_AG) + (C_AG − C)
```

and is structurally non-negative by construction. The observed negative value arises because the
two operands are **the same multiset of per-cell continuous power demands summed in two different
orders**:

* `continuous_cost_of_assignment` accumulates in **subchannel order** — `for n, t in
  enumerate(alloc.tokens)`;
* `solve_continuous_fixed_demand` accumulates in **multiset order** — `for k, n in zip(multiset,
  positions)`.

IEEE-754 float64 addition is not associative, so the two accumulations of an identical multiset can
differ by a few units in the last place, and the difference can carry either sign.

**Magnitude evidence.** `6.938893903907228e-18` is exactly `2**-57`, which at the relevant operand
scale (`≈5.97e-02`) is exactly **1.00 ULP**. A synthetic demonstration summing one fixed 4-term
multiset in all 24 orders yields 3 distinct float64 results spanning `1.387779e-17` — the same
order of magnitude, produced without reference to any observed value.

**What it is not.** It is not an infeasibility, not a budget exhaustion, not a censoring event, not
a solver inexactness, and not a violation of the dominance lemmas. The 14/14 exactness benchmark
continues to pass unchanged.

---

## 2. FLOAT64 TOLERANCE RULE

> **CORRECTED 2026-10-05 (erratum E-20).** The rule first adopted here,
> `K_EPS * eps * max(1.0, |operands|)` with `K_EPS = 128`, is **withdrawn**. Its `max(1.0, …)`
> floor admits 4096 ULP at order-1e-2 operand scale and 131072 ULP at order 1e-3, so the headroom
> claim that accompanied it was mathematically false. See
> `E18_MICRO_CORRECTION_ULP_RULE.md` for the corrected ULP-based policy, which supersedes the
> block below.

The rule adopted is **not** `if x < 0: x = 0`, and its threshold is **not** chosen to clear the
observed value.

```
K_ULP    = 32      # structural non-negativity, in ULP of the parent operands
K_ID_ULP = 32      # three-term identity residual, in ULP of LHS/RHS

structural_ulp_tolerance(*operands) = K_ULP * max(math.ulp(|operand_i|)) over finite operands
```

Applied to a structurally non-negative difference `x` formed from parent quantities `operands`:

| condition | action |
|---|---|
| `x >= 0` | returned untouched, including exact `0.0` |
| `-tol <= x < 0` | canonicalised to `+0.0` (numerical zero) |
| `x < -tol` | **SchemaError** — a structural violation, never canonicalised |

Two column classes are distinguished, and only one is given the tolerance:

* **Counts, accumulated sums and timings** (`generated`, `delivered`, `gap_H_G`, `gap_E_G`,
  `gap_C_AG`, `gap_C`, powers, `runtime_s`, `nodes`, `states`, drop counts) are never formed by
  subtractive cancellation. These keep the **strict** `x >= 0` check. A negative value there is
  always a real defect.
* **Structurally non-negative differences** — and only these three — get the scale-aware check:

  | column | formed as | scale operands |
  |---|---|---|
  | `term_allocation` | `H_G − E_G` | `gap_H_G`, `gap_E_G` |
  | `term_quantisation` | `E_G − C_AG` | `gap_E_G`, `gap_C_AG` |
  | `term_distortion` | `C_AG − C` | `gap_C_AG`, `gap_C` |

All three are covered, not only the one that failed. Canonicalisation happens **in place** inside
`validate_row`, so serialisation, the analysis pipeline and the tables all see one deterministic
representation. The three-term identity check uses the same scale-aware tolerance in place of the
previous fixed `1e-9`, so its threshold is likewise derived from float64 precision rather than from
a decimal rounding of the scientific values.

**Reporting consequence.** A canonicalised value is an exact `0.0`, so a decomposition term that
was a sub-ULP negative is reported as zero — never as a small positive number, and never dropped.

---

## 3. CODE FILES CHANGED

| file | change | touches experiment logic? |
|---|---|---|
| `code/final/schema.py` | `EPS_FLOAT64`, `K_EPS`, `structural_tolerance`, `canonicalize_structural_nonnegative`; `NUMERIC_NONNEGATIVE` narrowed to counts/sums/timings; `STRUCTURAL_NONNEGATIVE_DIFFERENCES` added; identity check made scale-aware | no — validation only |
| `code/final/run_final.py` | preflight resume accounting; completed-output immutability verification against the E-18 baseline | no — guard/reporting only |
| `code/final/test_numerical_tolerance_e18.py` | **new** regression suite (synthetic arithmetic only) | no |
| `code/final/freeze_manifest.py` | the new test added to the tracked set | no |
| `code/final/test_integration_nonfinal.py` | a stale assertion that `results_final/raw` must not exist, corrected to the right invariant (the test must not add to or alter that directory) | no |
| `ERRATA_APPEND_ONLY.md` | E-18 and E-19 entries appended | no |
| `.gitignore` | the E-18 output-digest baseline is a runtime artefact and is ignored | no |

Unchanged: the model, every endpoint, every statistic, every comparator, the seed set, the regimes,
the grids, the solver, the horizon and the protocol objective.

---

## 4. E-18 ERRATA ENTRY

Appended to `ERRATA_APPEND_ONLY.md` as entry **E-18 — 2026-10-04 — FLOATING-POINT NONNEGATIVITY
VALIDATION CORRECTION**. It records: the failing unit; the classification as summation-reordering
round-off at exactly 1 ULP; the two differing accumulation orders; the tolerance rule and its
derivation from `eps`; the strict/tolerant column split; the files changed; and the
execution-provenance consequence that the 400 units are **not** all produced under one code hash.

A second entry, **E-19 — 2026-10-05**, was appended during this stage's audit; see §9.

---

## 5. REGRESSION TEST RESULTS

`test_numerical_tolerance_e18.py` — **39 assertions, 39 PASS, 0 FAIL**, exit 0.

Coverage: exact zero; small positives returned unchanged; a synthetic summation-reordering residue
canonicalised, with its magnitude independently confirmed to be at ULP scale; negatives just inside
and exactly at `−tol` accepted; negatives marginally, 10× and 10⁶× outside `−tol` rejected; a
materially negative value at unit scale rejected; identity accepted with an injected ULP-scale
residual; identity materially violated rejected, with the message naming the tolerance rather than a
fixed decimal; strict columns still strict for a negative packet count and a negative accumulated
sum; all three difference columns canonicalised; the tolerance shown to scale with operand
magnitude and to floor at `K_EPS·eps`.

**Result-independence is itself tested.** The suite asserts that neither the policy module nor the
test file contains the observed failure magnitude — reconstructed arithmetically as `repr(2.0**-57)`
rather than written as a literal — and that neither references any final-band seed. Every negative
test value is produced by synthetic subtraction or summation reordering.

Two self-inflicted test defects were found and fixed before this result: an earlier version listed
the banned literals inline in its own source so could never pass; and an earlier identity case
happened to close exactly, so the "must have a nonzero residual" assertion was replaced by an
injected `3*math.ulp(lhs)` perturbation.

---

## 6. NON-FINAL FULL TEST RESULTS

Python 3.10.12, NumPy 2.2.6. No final seed, no final outcome read.

| suite | result |
|---|---|
| `tests/test_optimization_benchmark.py` (exactness) | **14/14 passed** |
| `test_stats.py` | ALL SYNTHETIC STATISTICAL TESTS PASSED |
| `test_pairing.py` | ALL ANTI-PSEUDOREPLICATION TESTS PASSED |
| `test_seed_reseal_a3.py` | ALL A3 SEED-RESEAL TESTS PASSED (cases A–G) |
| `test_numerical_tolerance_e18.py` | ALL E-18 NUMERICAL-TOLERANCE TESTS PASSED |
| `test_integration_nonfinal.py` | ALL END-TO-END INTEGRATION TESTS PASSED (non-final data only) |

All six exit 0.

---

## 7. PRE-E18 399-OUTPUT DIGEST

```
file    : 13_journal_extension/results_final/PRE_E18_COMPLETED_OUTPUT_DIGEST.json
created : 2026-10-05T09:31:38Z
n_files : 399
digest  : 2c422a18cf5042b757b7369737ea0fdeaa87d5cb5b13f6f159c474e76ce1d486
method  : sha256 over raw file BYTES only; no file parsed, no scientific value read
```

The baseline is git-ignored as a runtime artefact.

---

## 8. GIT COMMIT / HEAD

```
HEAD          : c50879685be2173d06dd4dfd7be70a4fd39bfc40   ("Freeze final-test runtime environment")
parent        : 95cc76105cb4e1b643fde5eca33a6e85c0d6186d   (repository initialised from the audited post-A3 snapshot)
branch        : master
worktree      : DIRTY — 7 paths (the E-18 changes of §3)
```

**The E-18 changes are uncommitted.** Committing is an author action; no commit was created and
none is invented here.

**Execution provenance, as recorded in the ledger itself:** all 1200 ledger rows carry
`git.commit_sha = c508796`, so the 399 completed units were produced under `c508796`. The single
resumed unit will be produced under the forthcoming E-18 commit. Both identities must be retained
in the reproducibility record; the record must not claim all 400 units share one code hash.

---

## 9. NEW FREEZE MANIFEST DIGEST

**No valid new manifest exists, and none can be written in this stage.** `--write` requires a clean
worktree to be meaningful, and the worktree holds the uncommitted E-18 changes.

This stage's audit also found that the manifest **currently on disk is invalid** — recorded as
erratum **E-19**:

| record | combined digest |
|---|---|
| stamped into all 1200 ledger rows (campaign time) | `56e2a35714e17a4a…` |
| manifest file now on disk | `b2b1ce7e2c23e9a5…` |

The on-disk file was written at `2026-10-05T09:32:44Z`, after the E-18 edits, so it hashes E-18
contents while recording `commit_sha = c508796`, which does not contain them; it also records
`worktree_clean: false`. `freeze_manifest.py --verify` correctly refuses it.

**The campaign anchor is nevertheless fully recoverable.** Recomputing the manifest digest over the
**committed** blob contents at `c508796`, using the **pre-E-18** tracked set, reproduces
`56e2a35714e17a4a…` exactly — the digest stamped in all 1200 ledger rows. The provenance of the 399
units is therefore verifiable from committed content and is not lost.

Required author sequence: commit the E-18 changes → confirm a clean worktree →
`python3 freeze_manifest.py --write` → `--verify` must print **MATCH** → record the new digest and
commit SHA as the provenance of the single resumed unit, alongside the retained `c508796` /
`56e2a35714e17a4a…` anchor for the 399.

An open hardening item is recorded: `--write` should refuse a dirty worktree outright. It was
deliberately **not** changed in this stage, because editing the manifest tool again would alter the
very file set awaiting commit.

---

## 10. LEDGER PRESERVATION AUDIT

```
rows                     : 1200        (unchanged)
bytes                    : 1,214,303
sha256                   : 7f71bb91bb005db699927f805d4a99a53145ca8fbb816c98a6a17016255d3e4d
state rows, all history  : PLANNED 400, STARTED 400, COMPLETED 399, FAILED 1
distinct unit_id         : 400
latest-state tally       : COMPLETED 399, FAILED 1
CENSORED rows            : 0
superseded rows          : 0
rows deleted             : 0
```

The FAILED row is **retained verbatim**, including its `failure_reason`, its timestamp
`2026-10-04T09:11:15Z`, and its `freeze_manifest_digest = 56e2a357…`. No ledger history was
deleted, rewritten or superseded. The ledger remains append-only.

---

## 11. 399-OUTPUT IMMUTABILITY AUDIT

Recomputed over `results_final/raw` and compared against the §7 baseline:

```
baseline files   : 399        current files : 399
CHANGED          : 0
ADDED            : 0
MISSING          : 0
recomputed digest: 2c422a18cf5042b757b7369737ea0fdeaa87d5cb5b13f6f159c474e76ce1d486
VERDICT          : BYTE-IDENTICAL
```

Bytes only. No output file was parsed and no scientific value was read. `results_final/analysis` is
empty: no endpoint has been computed and `analyse_final.py` has never been invoked.

---

## 12. RESUME DRY-RUN OUTPUT

```
planned units          : 400  (regime x grid x seed x warm-up)
runner sha256          : 4823aa1222787f4c
config sha256          : 2edbdf13de54dc6a

preflight notes:
  - frozen config digest 2edbdf13de54dc6a
  - seed guard: 20 seeds, all within [50002,50021]
  - seed guard rejects development, conference, out-of-band and the EXCLUDED incident seed 50001 (Amendment A3)
  - dependency numpy present
  - planned units 400; latest ledger state tally {'COMPLETED': 399, 'FAILED': 1}
  - already COMPLETED: 399  ->  skipped on resume
  - eligible for retry: 1  -> ['R3_aged|G2_wide10|K8N4H3|w100|ALL|s50011']
  - CENSORED rows in ledger: 0
  - 399 unit output file(s) present -> never overwritten
  - ledger rows present: 1200
  - completed-output hashes unchanged vs E-18 baseline (399 files, digest 2c422a18cf5042b7)

preflight PROBLEMS:
  ! C13 freeze manifest: protocol: ERRATA_APPEND_ONLY.md CHANGED (506941167a8f -> f3021d95f6e7)
  ! C13 freeze manifest: combined digest mismatch
  ! C13 freeze manifest: git worktree DIRTY: [.gitignore, ERRATA_APPEND_ONLY.md,
      freeze_manifest.py, run_final.py, schema.py, test_integration_nonfinal.py,
      test_numerical_tolerance_e18.py]

DRY RUN COMPLETE — no experiment instantiated, no final outcome produced, no final result file read.
STATUS: NOT READY
```

The only blocker is C13 — the uncommitted E-18 changes. It clears when the author commits and
regenerates the manifest.

---

## 13. NUMBER OF UNITS TO RETRY

**1.**

```
R3_aged | G2_wide10 | K8N4H3 | w100 | ALL | s50011
```

The other 399 are COMPLETED, are skipped on resume, and their output files are never overwritten.
Nothing is re-executed. Note that `w100` is one of the warm-up levels of seed 50011; the remaining
warm-up levels of that same seed completed normally, so seed 50011 contributes to the seed-level
collapse only once the resumed unit lands.

---

## 14. RESUME COMMAND

To be run by the author, from `13_journal_extension/code/final`, **after** §9 is satisfied:

```bash
FINAL_TEST_AUTHOR_UNLOCK=1 python3 run_final.py --execute --i-have-author-authorisation
```

This is the existing production runner. It is **not** a one-off script for seed 50011: the resume
set is derived from the ledger by the runner's own preflight, which is what guarantees that exactly
the incomplete unit runs and that the 399 completed outputs are untouched. No special-case script
for a single seed was written, and none should be.

Preconditions, all of which the runner itself enforces:

1. the E-18 changes are committed and the worktree is clean;
2. `freeze_manifest.py --write` has been re-run and `--verify` prints **MATCH**;
3. `numpy==2.2.6` under Python 3.10.12 (see `requirements-final.lock.txt`, `MAC_SETUP_ENV.sh`).

**This command was not executed in this stage.**

---

## 15. FINAL CAMPAIGN STATUS

```
COMPLETED              : 399 / 400
FAILED (active)        : 1
CENSORED               : 0
INVALIDATED            : 0
units to retry         : 1
endpoints computed     : 0   (analyse_final.py never invoked; results_final/analysis is empty)
```

**Status: RESUME-READY PENDING AUTHOR COMMIT (C13).**

Green: the numerical classification and its synthetic evidence; the tolerance policy and its 39
regression assertions; the full non-final suite including 14/14 exactness; byte-identical
preservation of the 399 outputs; an intact append-only ledger with the FAILED row retained; a
correctly scoped resume set of exactly 1 unit.

Red: C13. The E-18 changes are uncommitted and the on-disk freeze manifest is invalid (E-19). Both
are author actions.

After the author commits, regenerates the manifest to MATCH, and resumes, the campaign reaches
COMPLETED = 400 / FAILED-active = 0 / CENSORED = 0, at which point — and only then —
`analyse_final.py` may be run once. Until that point no endpoint, interval, p-value or effect size
may be computed, and the 399 completed units remain unexamined.

The final reproducibility record must state two execution identities: 399 units under `c508796`
with manifest digest `56e2a35714e17a4a…`, and 1 unit under the E-18 commit with its own manifest
digest.
