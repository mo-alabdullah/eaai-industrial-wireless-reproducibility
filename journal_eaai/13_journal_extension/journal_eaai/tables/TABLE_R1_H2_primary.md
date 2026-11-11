# TABLE R1 — Final H2 primary outcome

**Evidence class: INFERENTIAL (sole inferential endpoint).** Tier 2 (FINAL CONFIRMATORY).
Cell: R3_aged x G2_wide10. n = 20 seed-level paired observations.
Sign convention: offline aged-beam-gain reference MINUS causal EDF-with-exact-radio.
Source: `results_final/analysis/endpoints.json` key `H2` (locked; not recomputed).

| comparator / reference | information | causal | mean realised delivery | paired mean difference | 95% BCa CI | exact sign-flip p | Cohen d_z | + | − | ties | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| causal EDF + exact fixed-demand radio | aged beam gain | yes | 8.56 | — | — | — | — | — | — | — | 20 |
| offline exact aged-beam-gain reference | aged beam gain, full future trace | no | 9.03 | **0.47** | **[0.22, 0.71]** | **0.00320435** | **0.799** | 14 | 3 | 3 | 20 |

Descriptive companion (no test): the paired difference in aggregate power, same sign convention, is
−0.055740 W (sd 0.088407; negative on 19 of 20 seeds, positive on none, one tie) — the offline
reference reaches its higher realised delivery at lower aggregate power.

**Notes.** Exact paired two-sided sign-flip, all 2^20 = 1,048,576 assignments enumerated; m = 1, no
multiplicity correction. BCa interval from 10,000 resamples, bootstrap seed 20260921. The
right-hand row is an OFFLINE, TRACE-WISE, NONCAUSAL, NON-DEPLOYABLE reference, not a controller.
Radio allocation is exact on both sides, so this is not a measurement of radio allocation. The
endpoint quantifies the **combined** difference between causal slotwise deadline-priority
scheduling with exact fixed-demand allocation and an offline exact finite-horizon aged-gain
reference that receives the complete future trace and jointly optimises device selection,
scheduling and aged-gain planning before truthful replay. It does not isolate scheduling, does not
isolate lookahead, is not a controller-versus-controller comparison, and licenses no statement
about reinforcement-learning headroom.
