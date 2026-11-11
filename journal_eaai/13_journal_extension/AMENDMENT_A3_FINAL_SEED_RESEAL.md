# AMENDMENT A3 — FINAL-SEED RESEAL AFTER ACCIDENTAL PRE-EXECUTION

**Date: 2026-09-21. Status: APPLIED.**
**Classification: PROTOCOL AMENDMENT CAUSED BY AN EXECUTION-PROCEDURE DEVIATION.**
**This is NOT documentation-only.**

Governing protocol: `JOURNAL_PROTOCOL_V1.md` + Amendment A2. This amendment is additive; no earlier
text is rewritten. Historical references to the old seed band remain as provenance and are
superseded by this amendment.

---

## 1. Incident

**I-01 — accidental pre-authorisation execution of final seed 50001.**

> Seed 50001 was accidentally executed through the integration core before author unlock. No
> scientific endpoint value was inspected. Only the returned row count and elapsed execution time
> were observed. No result file or ledger entry was produced.

The execution fixture was **not** the frozen final configuration.

## 2. Old and new seed sets

| | seed set | n |
|---|---|---|
| **OLD** | 50001 – 50020 | 20 |
| **NEW** | **50002 – 50021** | **20** |

**Replacement rule:** `50001 → 50021`, applied **mechanically** — the procedurally exposed seed is
replaced by the immediately following unused integer seed. No seed was chosen by inspection of any
outcome, because no outcome was inspected.

**50001 is permanently excluded** and appears from here on only as the **EXCLUDED INCIDENT SEED**.

## 3. Prior-use audit of the replacement seed

Seed **50021** was audited project-wide before adoption:

| check | result |
|---|---|
| present in any result file (structured `seed`-column scan, 25 files) | **0 occurrences** |
| any member of 50002–50021 present in any result file | **NONE** |
| present in the execution ledger | **0 rows (ledger empty)** |
| used in development | **NO** |
| used in training | **NO** |
| present in an evaluation outcome | **NO** |
| opened as an outcome | **NO** |
| training/evaluation/trace namespace collision with development or conference bands | **0** |

The four source files containing the literal `50021` did so only as the **exclusive upper bound**
of `range(50001, 50021)` and in report prose. Source and configuration mentions of an integer are
not contamination.

**Replacement seed is CLEAN.**

## 4. Timing

The reseal was applied **before any final scientific endpoint value was opened**. No confirmatory
endpoint estimate, confidence interval, p-value, effect size, table or figure was produced or
inspected from the exposed execution. No member of the resealed set 50002-50021 has been executed
or opened.

## 5. What this amendment does NOT change

| unchanged | value |
|---|---|
| n | **20** |
| R1 / R3 regime definitions | ×1.0 d_CSI 1 / ×2.0 d_CSI 5, load 0.40 |
| primary cell | R3_aged × G2_wide10 × K8 × N4 × H3 |
| E1 | estimation, no test |
| H2 | sole inferential endpoint |
| E2 | estimation, no test |
| comparator definitions | all ten unchanged |
| confidence interval | 95 % BCa paired bootstrap, 10,000 resamples, fixed seed |
| test | exact paired two-sided sign-flip |
| enumeration | **2²⁰ = 1,048,576** |
| effect size | Cohen's d_z |
| sign convention | unchanged |
| multiplicity rule | m = 1, no correction |
| δ | **NOT SET** |
| TOST | **absent** |
| endpoint hierarchy | unchanged |
| execution unit count | 400 units, 100 in the primary cell |

**Only the seed integers changed. The statistical implementation was not touched.**

## 6. Verification

`code/final/test_seed_reseal_a3.py` pins the reseal. All tests pass:

- **A** 50002–50021 → ACCEPT (n = 20)
- **B** 50001 + 19 valid members → REJECT
- **C** 50002–50020 (n = 19) → REJECT
- **D** resealed set + one extra seed → REJECT
- **E** duplicate final seed → REJECT
- **F** H2 sample size remains n = 20
- **G** exact sign-flip assignments remain 2²⁰ = 1,048,576

Plus: guard band is [50002, 50021]; the guard rejects 50001 with a message naming Amendment A3;
accepts 50002/50011/50021; rejects 10001/20001/50000/50022; unit count unchanged at 400.

## 7. Live files updated

`code/final/run_final.py` (FINAL_SEEDS, guard bounds, guard message, docstrings) ·
`code/final/analyse_final.py` (VALID_FINAL_SEEDS, EXCLUDED_INCIDENT_SEEDS,
`assert_valid_final_seed_set`, primary-endpoint gate) · `code/final/test_pairing.py` ·
`code/final/test_integration_nonfinal.py` · `code/final/test_seed_reseal_a3.py` (new).

Historical artefacts are **not** rewritten.

## 8. Mandatory wording

> Seed 50001 was procedurally exposed before authorisation and was excluded before any scientific
> endpoint value was inspected. The resealed confirmatory set is 50002–50021, none of which has
> been executed or opened.

The statement *"no final seed has ever been executed"* is **false** and must not be used.
