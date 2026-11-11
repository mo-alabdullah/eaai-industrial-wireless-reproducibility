# Reproducibility guide

All commands are run from the repository root. None of them writes into
`13_journal_extension/results_final/raw/` or overwrites `endpoints.json` / `AUDIT_REPORT.json`.

## 1. Environment

| item | frozen value (confirmatory campaign) |
|---|---|
| Python | 3.10.12 |
| NumPy | 2.2.6 (`code/final/requirements-final.lock.txt`) |
| Platform of the campaign | Darwin arm64, 12 CPUs (recorded in `results_final/FREEZE_MANIFEST.json`) |
| Matplotlib (figures only) | 3.10.9 used for the byte-identity check |

The exact references use only the Python standard library and NumPy.

## 2. Integrity (read-only, seconds)

```bash
python3 journal_eaai/tools/verify_archive.py
```

Checks:

- the SHA-256 of `endpoints.json`, `AUDIT_REPORT.json`, `FINAL_RUN_LEDGER.jsonl` and
  `PROVENANCE_REGISTRY.json`;
- the raw-file count (400) and the canonical raw-tree digest v1;
- the 399 pre-E18 baseline files and the single resumed unit;
- the row count (2,400), the seed band, and the provenance tally (ORIGINAL 2,394 / E18 6);
- the configuration digest;
- the frozen endpoint values;
- `SHA256SUMS`.

Canonical raw-tree digest v1:

```
sha256( json.dumps({<path relative to results_final/raw>: <file sha256>}, sort_keys=True) )
= 5b31e54dbe6c6a2b897768ee100cadb0248cedf8edc50497cf5dea7bf935852b
```

## 3. Endpoints E1, H2, E2 (in memory, seconds)

```bash
python3 journal_eaai/tools/reproduce_endpoints.py
```

The script loads the 2,400 raw rows and applies the mixed-provenance gate, then recomputes each
endpoint with the archived analysis functions. Each comparator's seed value is the mean over its
five warm-up offsets, so the twenty seeds are the replicates. The script then compares every
field with the frozen `endpoints.json`.

- **BCa intervals:** 10,000 resamples with the fixed bootstrap seed 20260921.
- **H2 test:** exact paired two-sided sign-flip test, enumerating all 2^20 = 1,048,576 sign
  assignments.
- **E1 and E2:** estimation endpoints, with no test.

Comparison rule: counts, endpoint roles, null-versus-non-null p-values, the row count and the
provenance tally must match exactly. The floating-point estimates (mean, BCa limits, d_z and the
H2 p-value) must agree within `math.isclose(rel_tol=1e-12, abs_tol=1e-12)`, because the platform's
floating-point library can move the last bits (differences of order 1e-17). The script prints the
recomputed value, the frozen value and their absolute difference for every field. The rule is
tested by `journal_eaai/tools/test_reproduce_endpoints_comparison.py`.

Do **not** run `analyse_final.py --run` to reproduce values. It writes `endpoints.json` and
`AUDIT_REPORT.json` in place, and it is gated on the private provenance repository (§5).

## 4. Figures, descriptive summaries and tests

Run the commands on a copy if you want to keep the archived files untouched. The outputs are
byte-identical.

```bash
# Figures 1–3 (deterministic: no random numbers, no resampling, PDF CreationDate suppressed)
cd journal_eaai/13_journal_extension/journal_eaai/figures && python3 generate_final_figures.py && cd -
#   -> regenerates figure1/2/3 .pdf/.png and FIGURE_PROVENANCE.json; compare with SHA256SUMS
#   Canonical environment (FIGURE_CANONICAL_ENVIRONMENT.json): Python 3.10.12, NumPy 2.2.6,
#   Matplotlib 3.10.9, Linux. Elsewhere the generator is still deterministic and reads the same
#   inputs, but PNG/PDF bytes can differ through font rasterisation and serialisation.

# Descriptive summaries (decomposition terms, runtimes); prints only, writes nothing
python3 journal_eaai/13_journal_extension/code/final/extract_descriptive.py --print

# Tests
python3 journal_eaai/13_journal_extension/tests/test_optimization_benchmark.py      # exactness, 14 tests
python3 journal_eaai/13_journal_extension/code/final/test_numerical_tolerance_e18.py # E18 tolerance
python3 journal_eaai/13_journal_extension/code/final/test_stats.py
python3 journal_eaai/13_journal_extension/code/final/test_pairing.py
python3 journal_eaai/13_journal_extension/code/final/test_seed_reseal_a3.py
python3 journal_eaai/13_journal_extension/code/final/test_integration_nonfinal.py   # non-final seeds only
python3 journal_eaai/13_journal_extension/code/final/test_provenance_gate.py
(cd journal_eaai/07_simulation && python3 -m unittest discover -p "test_*.py")   # 165 simulator tests
```

### Expected result of `test_provenance_gate.py`

All checks pass except two environment-specific ones: "registry is NOT tracked by git" and
"registry IS git-ignored". Both assert a property of the authors' private provenance repository.
There, the registry was kept out of version control to avoid a hash circularity with the freeze
manifest. In this public archive the registry is deliberately included as a data file, so those
two checks report FAIL by design. It is still absent from the freeze manifest.

## 5. Full campaign rerun (optional, not needed for any reported value)

`run_final.py` refuses to execute unless three conditions hold:

1. the C13 freeze manifest matches exactly, including the git commit at which it was frozen (the
   E18 commit `c77a3df1976c9b942c7480f0ec55c6ced3b7e075` in the private provenance repository);
2. the author-unlock environment variable is set;
3. the explicit authorisation flag is given.

These gates protect the sealed seed band, so a public rerun of the confirmatory campaign is not
supported as an identical-provenance reproduction.

The finite-horizon references are expensive: one execution unit took a median of 0.86 s and a
maximum of 332.5 s. To study the solvers independently, use the exact references in
`code/optimization/` directly, with development seeds, as the exactness tests do.

## 6. Provenance anchors

The commit identifiers below refer to the authors' private provenance repository. They do not
exist in this public branch's history. Each one is bound to file contents through SHA-256 values
recorded in the manifests and the provenance registry, all of which are archived here.

| item | value |
|---|---|
| initial repository commit | `95cc76105cb4e1b643fde5eca33a6e85c0d6186d` |
| environment-freeze commit (ORIGINAL runs) | `c50879685be2173d06dd4dfd7be70a4fd39bfc40` |
| E18 commit (resumed unit) | `c77a3df1976c9b942c7480f0ec55c6ced3b7e075` |
| E21 audit-serialisation correction | `5900777f8e5833f8a9d467140f798e9ae9733538` |
| configuration digest | `2edbdf13de54dc6aece817ab1f01a65eb32b646b803d7b2be156e48f108661a2` |
| ORIGINAL runner SHA-256 | `82df6ed18e54cbf567b20b1d90eb05af566629f93fdd2284c62cafcf891b9fec` |
| E18 runner SHA-256 | `4823aa1222787f4cc5383a3268beb69b20cc612f6f389b75c5cb7b0cc46d88ef` |
| E18 freeze-manifest digest | `c3481380da7a1878b3c03622965b4536e225ef66d47f2ef7f739c6de79eab47c` |
| provenance registry SHA-256 | `d749b5a786fbd11294be43a1db5af2760767542e3ab2fe81d8ba1c432f1fcaef` |
| endpoints.json SHA-256 | `14da718a03a1823b152e53ebc5aacf7d028f07aea0ee4b262d2e2434174aafc7` |
| AUDIT_REPORT.json SHA-256 (corrected, E21) | `3328a8550567f7dadd54fd2089a398e17c63947ea73cb6dc9887a02cfbf32f14` |
| FINAL_RUN_LEDGER.jsonl SHA-256 | `6ece57ef8edadad9a38d9b9cfe9c4c0a5f4dc11612a569dc6cb7e4a58ce2ca73` |

`analyse_final.py` and `test_provenance_gate.py` are the E21 versions, committed after the E18
freeze manifest was written (E21 corrected only how the audit report serialises the provenance
commit fields; no endpoint value changed). Their hashes therefore differ from the E18 manifest
entries. The project's append-only errata log is not part of this archive; the incident, seed
reseal and E18 correction records are included as separate files.

## 7. E18 floating-point policy

Structurally non-negative decomposition differences, and the identity tolerance, are validated
against 32 units in the last place of the parent operands (K_ULP = 32, K_ID_ULP = 32). A value
negative within that tolerance is canonicalised to numerical zero. Counts, sums, powers and
timings keep a strict non-negativity check. The resulting rules are tested in
`test_numerical_tolerance_e18.py`; the full records are `E18_MICRO_CORRECTION_ULP_RULE.md` and
`E18_NUMERICAL_CORRECTION_AND_RESUME_PREFLIGHT.md`. Exactly one unit was produced under E18:
`R3_aged/G2_wide10/s50011_w100.json`, which contributes 6 rows.
