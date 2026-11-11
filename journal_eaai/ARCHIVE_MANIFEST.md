# Archive manifest

Every file is listed with its SHA-256 in `SHA256SUMS`. This page maps paths to roles. Paths are
relative to `journal_eaai/`. Original project-relative paths are preserved because the freeze
manifest, the runner and the analysis resolve them from the project root.

## Logical map

| role | path |
|---|---|
| **Final code**: runner | `13_journal_extension/code/final/run_final.py` |
| **Final code**: analysis | `13_journal_extension/code/final/analyse_final.py` (E21 version) |
| **Final code**: descriptive extraction | `13_journal_extension/code/final/extract_descriptive.py` |
| **Final code**: statistics, schema, ledger, freeze manifest | `13_journal_extension/code/final/{stats,schema,ledger,freeze_manifest}.py` |
| **Exact fixed-demand solver** | `13_journal_extension/code/optimization/radio.py` — `solve_exact_radio_fixed_demand`, `brute_force_fixed_demand` |
| **Continuous-power reference** | `13_journal_extension/code/optimization/radio.py` — `solve_continuous_fixed_demand`, `continuous_cost_of_assignment` |
| **Offline finite-horizon aged-gain / current-gain references** | `13_journal_extension/code/optimization/joint.py` — `solve_exact_joint(use_true=False / True)`, `execute_plan`, `record_trace` |
| Free-selection exact reference, grids, state capture | `13_journal_extension/code/optimization/{radio,grids,capture}.py` |
| Heuristic and component agents | `13_journal_extension/code/baselines_v2.py`, `code/run_stage_ib.py` (`edf_then_exact_radio`, imported by the runner) |
| Development-stage runners and analyses | `13_journal_extension/code/run_*.py`, `code/optimization/analyse_*.py`, `code/make_headroom_shares.py` |
| Simulator | `07_simulation/` (environment, channel, mobility, token codec, mask oracle, 165 unit tests) |
| **Tests**: exactness | `13_journal_extension/tests/test_optimization_benchmark.py` (14 tests) |
| **Tests**: E18 numerical tolerance | `13_journal_extension/code/final/test_numerical_tolerance_e18.py` |
| **Tests**: statistics, pairing, seed reseal, provenance gate, integration | `13_journal_extension/code/final/test_*.py` |
| **Configuration** | `07_simulation/primary_experiment_config.json`, `10_confirmatory/CONFIRMATORY_PROTOCOL_LOCK.json`, `13_journal_extension/FINAL_CONFIRMATORY_PROTOCOL_V2.md` (together they form the configuration digest `2edbdf13…`); study definition (seeds, regimes, grids, K = 8, N = 4, H = 3) in `run_final.py` |
| Dependency lock | `13_journal_extension/code/final/requirements-final.lock.txt` |
| **FINAL raw results** | `13_journal_extension/results_final/raw/{R1_nominal,R3_aged}/{G0_icame,G2_wide10}/s<seed>_w<warm-up>.json` (400 files, 2,400 rows) |
| **FINAL analysis** | `13_journal_extension/results_final/analysis/endpoints.json`, `AUDIT_REPORT.json`, `descriptive/DESCRIPTIVE_SUMMARIES.json` |
| Ledger, manifests, registry | `13_journal_extension/results_final/{FINAL_RUN_LEDGER.jsonl, FREEZE_MANIFEST.json, PRE_E18_COMPLETED_OUTPUT_DIGEST.json, PROVENANCE_REGISTRY.json, RUN_METADATA.json}` |
| Runtime evidence | FINAL: `runtime_s` in each raw row and `descriptive/DESCRIPTIVE_SUMMARIES.json`; DEVELOPMENT: `13_journal_extension/EXACT_SOLVER_LATENCY.md`, `results/solver_latency.csv`, `results/solver_latency_env.json` |
| DEVELOPMENT results | `13_journal_extension/results/*.csv, *.jsonl` |
| **Figures**: generator, outputs, provenance, canonical environment | `13_journal_extension/journal_eaai/figures/` |
| **Tables** (final records R1–R6) | `13_journal_extension/journal_eaai/tables/TABLE_R{1..6}_*.md` |
| Protocol and incident records | `13_journal_extension/{FINAL_CONFIRMATORY_PROTOCOL_V2, PRIMARY_HYPOTHESES_REGISTER, JOURNAL_PROTOCOL_V1, AMENDMENT_A3_FINAL_SEED_RESEAL, INCIDENT_I01_RECORD, E18_MICRO_CORRECTION_ULP_RULE, E18_NUMERICAL_CORRECTION_AND_RESUME_PREFLIGHT, CONTINUOUS_POWER_REFERENCE}.md` |
| Verification tools | `tools/verify_archive.py`, `tools/reproduce_endpoints.py`, `tools/test_reproduce_endpoints_comparison.py` |

## Study definition (frozen)

| item | value |
|---|---|
| R1 | distance × 1, beam-gain delay d_CSI = 1, offered load 0.40 |
| R3 | distance × 2, beam-gain delay d_CSI = 5, offered load 0.40 |
| Nominal grid (G0_icame) | {0.05, 0.10, 0.20, 0.40} W |
| Wide sensitivity grid (G2_wide10) | 10 log-spaced levels, 10⁻⁵–0.4 W; not a refinement of the nominal grid |
| Primary cell | R3 × G2_wide10, K = 8, N = 4, H = 3 |
| Final paired seeds | 50002–50021 inclusive (n = 20); 5 warm-up offsets per seed |
| Excluded seed | 50001 (incident I-01; Amendment A3) |

## Files from the freeze manifest not included in this archive

| freeze-manifest group | file | reason |
|---|---|---|
| frozen_manuscript_sections | `13_journal_extension/journal_eaai/_stage5d_intro_body.txt`, `_stage6e_related_work_body.txt`, `_stage7a_system_model_body.txt`, `_stage7b_framework_body.txt`, `_stage7c_controller_body.txt`, `_stage7d_experimental_design_body.txt` | Manuscript text, not software or data. They are not execution inputs. |
| protocol | `13_journal_extension/FINAL_TEST_READINESS_CHECKLIST.md` | Internal pre-run readiness checklist. It is not an execution input and is not read by any script. |
| protocol | `13_journal_extension/ERRATA_APPEND_ONLY.md` | Internal append-only errata log. It is not an execution input. Some code comments and records refer to it by erratum number; the release-relevant content is covered by `INCIDENT_I01_RECORD.md`, `AMENDMENT_A3_FINAL_SEED_RESEAL.md` and the two E18 records. |

Because these files are absent, `freeze_manifest.verify()` reports them as missing. It also
reports the post-freeze E21 hash differences (`analyse_final.py`, `test_provenance_gate.py`) and a git-commit difference, because the public branch
history is not the private provenance repository. `tools/verify_archive.py` checks every archived
file that appears in the freeze manifest and reports withheld files separately.

## Excluded by policy

Caches (`__pycache__`, `.pyc`), OS files, virtual environments, manuscript files, editorial
drafts, and historical project snapshots.
