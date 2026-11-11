# E-18 MICRO-CORRECTION — ULP-BASED TOLERANCE (pre-commit)

Stage date: 2026-10-05. Not committed. Final unit not resumed. No completed final outcome inspected.
Recorded as erratum **E-20**, which supersedes the tolerance formula stated in E-18. The E-18
*classification* — **NUMERICAL ROUND-OFF** — is unchanged.

---

## 1. CORRECTED ULP RULE

```python
import math

K_ULP    = 32      # structural non-negativity, in ULP of the parent operands
K_ID_ULP = 32      # three-term identity residual, in ULP of LHS/RHS

def structural_ulp_tolerance(*operands):
    finite = [abs(float(v)) for v in operands if v is not None and math.isfinite(float(v))]
    if not finite:
        raise SchemaError("a tolerance is never invented without a scale")
    return K_ULP * max(math.ulp(v) for v in finite)
```

**Structural non-negativity**, applied to `term_allocation`, `term_quantisation`,
`term_distortion` only:

```python
if x >= 0:                      return x          # untouched, including exact 0.0
tol = structural_ulp_tolerance(parent_1, parent_2)
if x >= -tol:                   return 0.0        # numerical zero
raise SchemaError(...)                            # structural violation
```

No `abs(x)`. No blanket clipping. No fixed decimal tolerance. No seed-specific exception.

**Three-term identity**: `|lhs − rhs| <= K_ID_ULP * max(ulp(|lhs|), ulp(|rhs|))`, with
`lhs == rhs == 0` accepted exactly. The previous fixed `1e-9` is removed. No value is rounded to
decimal places anywhere.

**Unchanged and strictly non-negative, with no tolerance:** counts (`generated`, `delivered`,
`realised_delivery`, `believed_delivery`, drop counts), raw accumulated sums (`gap_H_G`, `gap_E_G`,
`gap_C_AG`, `gap_C`), powers, timings (`runtime_s`) and state counts (`nodes`, `states`,
`skipped_entries`).

**Why `K_ULP = 32`.** Each side of a structural difference is a sum of at most `N = 4` non-negative
per-cell power terms — the frozen problem has four subchannels — and the two sides accumulate the
**same multiset in different orders**. Worst-case float64 accumulation error grows like `(m−1)` ULP
per side, so a handful of ULP suffices; 32 ULP leaves roughly an order of magnitude of headroom
over that bound while remaining far tighter than the withdrawn rule. The constant is derived from
the problem's addition count, **not** from the observed failing magnitude.

**Reported with synthetic arithmetic only:** the observed failure magnitude corresponds to **1 ULP**
at its parent scale; the accepted tolerance under the corrected rule is **32 ULP**; a residual
beyond 32 ULP is **rejected**.

---

## 2. OLD VS NEW TOLERANCE AT REPRESENTATIVE SUB-UNIT SCALE

| operand scale | 1 ULP | withdrawn `128·eps·max(1,s)` | that, in ULP | corrected `32·ulp(s)` | in ULP | tightening |
|---|---|---|---|---|---|---|
| 1e-3 | 2.168404e-19 | 2.842171e-14 | **131072** | 6.938894e-18 | 32 | 4096× |
| ~6e-2 | 6.938894e-18 | 2.842171e-14 | **4096** | 2.220446e-16 | 32 | 128× |
| 1.0 | 2.220446e-16 | 2.842171e-14 | 128 | 7.105427e-15 | 32 | 4× |
| 1234.5 | 2.273737e-13 | 3.508730e-11 | 128 | 7.275958e-12 | 32 | 4× |

The withdrawn rule was *looser* at exactly the scales this model's power quantities occupy, which is
the opposite of what a tolerance should do. The corrected rule is a constant 32 ULP at every scale,
by construction.

---

## 3. CODE CHANGES

| file | change |
|---|---|
| `code/final/schema.py` | `structural_ulp_tolerance()` replaces `structural_tolerance()`; `K_ULP = 32`, `K_ID_ULP = 32` replace `K_EPS = 128`; `canonicalize_structural_nonnegative()` rewritten to the `x >= -tol` form; identity check switched to `K_ID_ULP` ULP with exact-zero short-circuit; the false headroom claim removed; `EPS_FLOAT64` retained as a reference constant only |
| `code/final/analyse_final.py` | **new** mixed-provenance gate: `ProvenanceError`, `provenance_of()`, `load_declared_provenance()`, `assert_declared_provenance()`; wired into `--run` (hard refusal, not bypassable by `--exploratory`) and reported in `--check`; provenance tally recorded in `AUDIT_REPORT.json` |
| `results_final/PROVENANCE_REGISTRY.json` | **new** — declares `ORIGINAL` (399 units, resolved) and `E18` (1 unit, `PENDING`) |
| `code/final/test_numerical_tolerance_e18.py` | rewritten for the ULP rule, cases A–J |
| `code/final/test_provenance_gate.py` | **new** — synthetic metadata-only provenance tests |
| `code/final/freeze_manifest.py` | the new test added to the tracked set |
| `ERRATA_APPEND_ONLY.md` | erratum **E-20** appended |
| `E18_NUMERICAL_CORRECTION_AND_RESUME_PREFLIGHT.md` | §2 marked superseded, pointing here |

Unchanged: the model, every endpoint, every statistic, every comparator, the seed set, the regimes,
the grids, the solver, the horizon, the row schema and the protocol objective.

---

## 4. E-18 TEST RESULTS

`test_numerical_tolerance_e18.py` — **65 assertions, 65 PASS, 0 FAIL**, exit 0.

| case | assertion | result |
|---|---|---|
| A | exact zero (float and int) accepted as zero | PASS |
| B | small positives `1e-300 … 12345.678` returned unchanged, type preserved | PASS |
| C | `−1 ULP` at scales 0.05 / 1.0 / 1234.5 → `0.0`; plus a genuine summation-reordering residue → `0.0`, confirmed to be within `K_ULP` ULP of its operands | PASS |
| D | tolerance equals exactly `K_ULP · ulp(scale)`; `−K_ULP ULP` → `0.0` at all three scales | PASS |
| E | `−(K_ULP+1) ULP` → **REJECT** at all three scales | PASS |
| F | materially negative `−1e-6`, `−1e-9`, `−0.25`, `−1e-15` → **REJECT** | PASS |
| G | identity accepted when naturally formed, with a 3-ULP injected residual, and when `lhs == rhs == 0` exactly | PASS |
| H | identity residual at `K_ID_ULP+8` ULP → **REJECT**, message naming ULP not a decimal; materially violated identity → **REJECT** | PASS |
| I | tolerance at 0.05 / 0.01 / 0.001 is exactly 32 ULP and `< 100` ULP; strictly tighter than the withdrawn rule at each; the withdrawn rule confirmed to have admitted `>1000` ULP at sub-unit scale; tolerance monotone in operand magnitude; `math.nextafter` step equals `math.ulp` | PASS |
| J | neither the policy module nor the test file contains the observed magnitude (reconstructed as `repr(2.0**-57)`, never a literal) or any final-band seed; tolerance confirmed ULP-derived; the withdrawn floor-at-1 expression and headroom claim confirmed absent | PASS |

Plus: `K_ULP`/`K_ID_ULP` are small documented integers; a tolerance request with no finite operand
is **refused** rather than defaulted; all three difference columns are canonicalised; and the strict
columns still reject a negative packet count, a negative accumulated sum, and a negative timing
**even at 1 ULP**.

---

## 5. MIXED-PROVENANCE ANALYSIS AUDIT

**Finding: the pipeline previously had no provenance check at all.** `analyse_final.py` verified the
freeze manifest and the ledger, then loaded every row and ran the endpoints. Nothing compared
`runner_sha256` or `freeze_manifest_sha256` across rows, so a two-provenance campaign would have
been analysed silently as though it were single-provenance.

Gate now enforced, metadata-only:

| condition | behaviour |
|---|---|
| declared set `{ORIGINAL, E18}` observed | **ACCEPT**, with a per-label row tally recorded in `AUDIT_REPORT.json` |
| any undeclared third provenance pair | **REJECT** |
| a row with a missing or half-missing provenance pair | **REJECT** — never defaulted |
| a declared entry still `PENDING` | **REJECT** — blocks `--run` until the E-18 commit and manifest exist |
| two declared labels sharing one hash pair | **REJECT** — the registry must be unambiguous |
| `config_sha256` not identical across all rows | **REJECT** — a provenance split may differ in code hash only |

Not weakened: the config digest is still required to be byte-identical; the A3 seed-set gate, the
anti-pseudoreplication gate, the regime/grid definitions and the endpoint schema are untouched. The
gate is **not** bypassable by `--exploratory`, because an undeclared provenance is a provenance
defect rather than a dataset-completeness question.

`test_provenance_gate.py` — **16 assertions, 16 PASS, 0 FAIL**, exit 0. It covers every row of the
table above on synthetic placeholder hashes (`"a"*64` and similar), asserts that the accepted
dataset really does contain two distinct runner hashes so the gate cannot be passing by collapsing
them, and asserts against the live registry that `E18` is `PENDING` and therefore currently blocks
analysis. No outcome column is populated anywhere in the file and no real campaign digest appears
in it.

Live check: `analyse_final.py --run` on the present tree returns **2** and refuses at the C13
manifest stage, before any row is loaded — so no final outcome was read in this stage.

---

## 6. 399-OUTPUT IMMUTABILITY AUDIT

```
baseline : 2c422a18cf5042b757b7369737ea0fdeaa87d5cb5b13f6f159c474e76ce1d486  (399 files)
current  : 2c422a18cf5042b757b7369737ea0fdeaa87d5cb5b13f6f159c474e76ce1d486  (399 files)

CHANGED = 0        ADDED = 0        MISSING = 0        VERDICT: BYTE-IDENTICAL
```

Bytes only; no file parsed, no scientific value read. `results_final/analysis` does not exist — no
endpoint has been computed and `analyse_final.py` has never completed a run.

---

## 7. FULL NON-FINAL TEST RESULTS

Python 3.10.12, NumPy 2.2.6. No final seed executed.

| suite | result | exit |
|---|---|---|
| `tests/test_optimization_benchmark.py` (exactness) | **14/14 passed** | 0 |
| `test_numerical_tolerance_e18.py` | ALL E-18 NUMERICAL-TOLERANCE TESTS PASSED (65/65) | 0 |
| `test_provenance_gate.py` | ALL MIXED-PROVENANCE GATE TESTS PASSED (16/16) | 0 |
| `test_stats.py` | ALL SYNTHETIC STATISTICAL TESTS PASSED | 0 |
| `test_pairing.py` | ALL ANTI-PSEUDOREPLICATION TESTS PASSED | 0 |
| `test_seed_reseal_a3.py` | ALL A3 SEED-RESEAL TESTS PASSED | 0 |
| `test_integration_nonfinal.py` | ALL END-TO-END INTEGRATION TESTS PASSED (non-final data only) | 0 |

---

## 8. READY / NOT READY FOR E-18 COMMIT

**READY FOR E-18 COMMIT.**

All conditions of this micro-correction are met: the tolerance is ULP-based and 32 ULP at every
scale; the false headroom claim and the floor-at-1 rule are removed from code and documentation;
strict columns retain zero tolerance; the identity check is ULP-based with exact-zero handling; the
mixed-provenance gate exists, is wired in, and is proven to reject an undeclared or unresolved
provenance without weakening any scientific consistency check; the 399 outputs are byte-identical;
and the full non-final suite passes under the locked environment.

Not done, by instruction: **nothing was committed and the final unit was not resumed.** Two author
actions remain, in this order — commit the E-18 changes and regenerate the freeze manifest to
`MATCH` (which also resolves erratum E-19), then replace the `PENDING` hashes in
`PROVENANCE_REGISTRY.json` with the resulting commit, runner and manifest digests. The registry
deliberately blocks analysis until that second step is done.
