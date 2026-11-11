# INCIDENT I-01 — APPEND-ONLY RECORD

**Date: 2026-09-21. Status: CLOSED by Amendment A3.**
**Classification: PROTOCOL / REPRODUCIBILITY DEVIATION. Not a result-driven design change.**

This record is append-only. It does not overwrite any historical artefact.

---

## 1. Title

**I-01 — Accidental pre-authorisation execution of final seed 50001.**

## 2. Statement of record

> Seed 50001 was accidentally executed through the integration core before author unlock. No
> scientific endpoint value was inspected. Only the returned row count and elapsed execution time
> were observed. No result file or ledger entry was produced.

## 3. Facts

| fact | detail |
|---|---|
| seed | **50001**, a member of the then-sealed set 50001–50020 |
| invocations | **two** — `run_unit()` called directly during diagnosis of a failing test assertion |
| output | 6 schema rows returned **in memory**, ~0.6 s |
| raw result file written | **NO** |
| ledger row written | **NO** |
| `results_final/raw` created | **NO** |
| `RUN_METADATA.json` written | **NO** |
| scientific endpoint value printed or inspected | **NO** |
| non-scientific information observed | **row count and elapsed execution time only** |
| execution fixture | **NOT** the frozen final configuration (reduced ad-hoc fixture, H = 2) |
| analysis, estimate, interval, p-value, table or figure produced | **NONE** |

## 4. Cause

A test assertion claimed that `run_unit()` rejects seed 50001. **The assertion was wrong**: 50001
was the first final seed, and the seed guard is designed to *accept* final seeds and reject
everything else. Diagnosing the failing assertion invoked the production entry point directly.

**Underlying design defect.** The seed guard asserts that a seed *is* final. It is therefore the
wrong control for preventing *unsanctioned* execution: any caller holding a valid final seed could
reach the execution core.

## 5. Consequence for the record

**The statement "no final seed was executed" is FALSE and is withdrawn.**

The correct statement, mandatory from here on:

> Seed 50001 was procedurally exposed before authorisation and was excluded before any scientific
> endpoint value was inspected. The resealed confirmatory set is 50002–50021, none of which has
> been executed or opened.

## 6. Containment

No value from the exposed computation entered any file, any analysis, or any decision. **No
scientific endpoint value was observed or inspected. The only information observed from the exposed
execution was the returned row count and elapsed execution time.** The sealed band's scientific
function — that final results are seen once and cannot retro-fit any earlier choice — is therefore
preserved.

## 7. Corrective actions

| # | action | status |
|---|---|---|
| 1 | **Execution interlock.** `_EXECUTION_SANCTIONED` is `False` at import and released **only** inside `execute()`, after preflight and both authorisation gates. `run_unit()` raises `ExecutionNotSanctionedError` otherwise, **before any seed logic**. | **IMPLEMENTED, VERIFIED** |
| 2 | **Reseal.** Amendment A3 excludes 50001 permanently; the confirmatory set becomes 50002–50021. `50001 → 50021`, mechanical. n remains 20. | **APPLIED** |
| 3 | **Analysis gate.** `assert_valid_final_seed_set()` rejects 50001, a short set, an extra seed and duplicates at every primary endpoint. | **IMPLEMENTED, VERIFIED** |
| 4 | **Regression tests.** `test_seed_reseal_a3.py` pins cases A–G plus guard-band and unit-count invariants. | **ALL PASS** |
| 5 | **Test corrected.** The inverted assertion is replaced, with a comment recording why. | **DONE** |
| 6 | **Defence in depth.** The integration fixture itself asserts non-final seeds — three independent layers. | **VERIFIED** |

## 8. Verification of the corrective actions

```
ad-hoc run_unit(50002)  -> refused at INTERLOCK
ad-hoc run_unit(50001)  -> refused at INTERLOCK
ad-hoc run_unit(10001)  -> refused at INTERLOCK
once sanctioned, guard_seed(50001) -> SeedGuardError naming Amendment A3
run_unit_core exposed on the CLI  -> False
```

## 9. What was NOT done

**No persistent result artefact was deleted, altered or suppressed. The six returned rows existed
only in memory and were not inspected for scientific endpoint values.** No historical artefact was
rewritten. No seed was selected by inspecting an outcome. No statistical method, endpoint,
comparator, regime, grid or sample size was changed.

## 10. Protocol treatment and residual scope

For protocol purposes, the execution is treated conservatively as procedural exposure of seed
50001. Amendment A3 closes the incident by permanently excluding 50001 and resealing the
confirmatory set as 50002-50021.

**Residual scope:** no scientific endpoint value was inspected and no persistent result artefact was
produced; the procedural exposure is fully carried in the incident record and Amendment A3.
