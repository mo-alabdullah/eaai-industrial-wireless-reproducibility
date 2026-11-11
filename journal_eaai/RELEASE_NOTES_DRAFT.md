# EAAI Reproducibility Archive v2.0.0

Tag: `v2.0.0-eaai-reproducibility` (branch `journal-eaai-extension`).
Archive author: Mohammed Alabdullah (ORCID 0009-0001-0826-4380).

## Scope

Reproducibility archive for the journal extension *Exact Optimization References for Joint Radio
Resource Allocation in Industrial Wireless Uplinks*. The conference artifact on `main` is unchanged.
Everything added is under `journal_eaai/`, together with the archive citation metadata at the
repository root.

## Contents

The exact optimisation references are:

- a fixed-demand exact radio-allocation solver;
- a continuous-power mathematical lower reference;
- offline finite-horizon exact references on aged and on current beam gain. These are noncausal
  and non-deployable diagnostic references.

The frozen confirmatory campaign consists of:

- **Size:** 400 execution units and 2,400 result rows.
- **Regimes and grids:** two regimes (R1, R3) × two power grids (nominal and wide sensitivity grid).
- **Seeds:** 20 paired seeds, 50002–50021; seed 50001 is excluded under Amendment A3.
- **Provenance:** 2,394 rows from the original execution and 6 rows from the single E18-resumed unit.

The archive also includes the final analysis, the descriptive extraction, a deterministic figure
generator for Figures 1–3, the final table records, the exactness and E18 numerical-tolerance
tests, the simulator, and the protocol, incident and correction records.

## Endpoint snapshot (R3 × wide grid, n = 20)

| endpoint | estimate | 95 % BCa | d_z | +/−/0 | inference |
|---|---|---|---|---|---|
| H2: offline aged-gain reference − causal EDF with exact fixed-demand allocation | +0.47 deliveries | [0.22, 0.71] | 0.799 | 14/3/3 | exact paired two-sided sign-flip, p = 0.00320435 (sole test) |
| E1: exact fixed-demand − heuristic (aggregate power) | −0.10271 W | [−0.13657, −0.07498] | −1.425 | 0/20/0 | estimation only |
| E2: offline current-gain − offline aged-gain reference | +1.58 deliveries | [1.28, 1.84] | 2.412 | 20/0/0 | estimation only |

## Integrity

- **Canonical raw-tree digest v1:** `5b31e54dbe6c6a2b897768ee100cadb0248cedf8edc50497cf5dea7bf935852b` (400 files)
- **endpoints.json:** `14da718a03a1823b152e53ebc5aacf7d028f07aea0ee4b262d2e2434174aafc7`
- **AUDIT_REPORT.json:** `3328a8550567f7dadd54fd2089a398e17c63947ea73cb6dc9887a02cfbf32f14`
- **FINAL_RUN_LEDGER.jsonl:** `6ece57ef8edadad9a38d9b9cfe9c4c0a5f4dc11612a569dc6cb7e4a58ce2ca73`

Verify:

```bash
python3 journal_eaai/tools/verify_archive.py
python3 journal_eaai/tools/reproduce_endpoints.py
```

Details are in `journal_eaai/README.md` and `journal_eaai/REPRODUCIBILITY.md`.
