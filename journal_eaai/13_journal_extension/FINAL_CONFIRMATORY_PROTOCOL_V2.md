# FINAL_CONFIRMATORY_PROTOCOL_V2 — design, 2026-09-14

**Status: FROZEN — AUTHOR-APPROVED — NOT EXECUTED. Date: 2026-09-14.**

Author approval received explicitly in project chat on 2026-09-14
(`AMENDMENT_V2_AUTHOR_DECISION.md`). FINAL TEST seeds **50001–50020 remain unopened**. No RL/ML
method designed or trained, and **none will be introduced**. Manuscript and title untouched.
Governing protocol: **JOURNAL_PROTOCOL_V1 + Amendment A2 (2026-09-14)**.

**This protocol is frozen. It may not be edited further without a dated amendment.** It is
nevertheless **NOT executable**: gate **A9 (IJOCTA AI-policy compliance) is unresolved**, and gates
C10/C11/C13 (runner, ledger, hash workflow) are unimplemented. See
`FINAL_TEST_READINESS_CHECKLIST.md`.

**Equivalence testing was DECLINED by the author (OPTION E2).** δ_delivery and δ_power are NOT SET;
**TOST is removed from this protocol**; and no equivalence, non-inferiority, equality or
near-optimality claim may be inferred from an H2 non-rejection.

**Revision 2026-09-14 (pre-freeze protocol correction).** Two of the three originally proposed
primary hypotheses were **structurally dominated by solver construction** and are reclassified as
estimation endpoints; the Holm family is removed because a single inferential test remains.
Reasoning and verification: `PRE_FREEZE_PROTOCOL_AUDIT.md`.

---

## 1. Scope change

The confirmatory study is **substantially narrower** than the development campaign, and its subject
has changed. The exploratory work produced 1,152 Stage-I0 runs, 16,035 Stage-I-A states, 640
Stage-I-B traces and a 16-comparison family. None of that is repeated.

**This is no longer a reinforcement-learning study.** No learned controller is introduced, so there
are no hyperparameters, no training seeds, no validation seeds and no tuning stage. What remains is
an optimisation-and-control question about how far a simple deadline-aware, structure-aware rule sits
from exact optimisation, and when the binding limitation is the *problem configuration* rather than
the *algorithm*.

### Primary scientific question

> How close does a simple deadline-aware, structure-aware controller come to exact radio and joint
> optimisation, and when do power-grid resolution and aged CSI — rather than algorithmic complexity —
> dominate performance?

## 2. Regimes (pre-declared, minimal)

| id | distance | d_CSI | load | role |
|---|---|---|---|---|
| **R1** | ×1.0 | 1 | 0.40 | nominal — tests the quantisation-limited regime |
| **R3** | ×2.0 | 5 | 0.40 | extended range + aged CSI — tests the information-limited regime |
| ~~R4~~ | ×1.5 | 3 | 0.40 | **EXCLUDED from the confirmatory core by author decision, 2026-09-14.** Retained as DEVELOPMENT / EXPLORATORY context only |

**Confirmatory regimes are R1 and R3 only** (author decision, 2026-09-14).

Two grids, **reported separately and never merged in one table**: `G0_icame` (conference /
reproducibility grid) and `G2_wide10` (**non-binding numerical sensitivity grid only — no
hardware-realism claim**). The continuous `p_req` reference appears as its own labelled column and
is a **mathematical lower / reference bound only**. `G1_ext7` is **omitted** (author decision).

The exploratory factorial (4 regimes × 2 grids × 2 scales) is **not** restored. R2 (×2.0, age 1) is
dropped: its development behaviour sits between R1 and R3 and it carries no primary hypothesis.

## 3. Comparators

| # | comparator | scheduling | radio allocation | information | label |
|---|---|---|---|---|---|
| 1 | `EDF-StaleBeam-MinFeasible` | EDF greedy | greedy best-stale-beam, min-feasible power | aged | deployable reference |
| 2 | EDF + exact fixed-demand radio allocator | EDF (held fixed) | **exact** | aged | deployable |
| 3 | exact joint controller | **exact, finite-horizon** | **exact** | aged | deployable |
| 4 | exact joint ORACLE | **exact, finite-horizon** | **exact** | **current CSI** | **NON-DEPLOYABLE UPPER / INFORMATION REFERENCE** |
| 5 | continuous-power reference | as applicable | exact, unquantised `p_req` | aged | **MATHEMATICAL LOWER / REFERENCE BOUND** |

Comparator 4 must carry the label **NON-DEPLOYABLE UPPER/INFORMATION REFERENCE** at every occurrence
— in tables, figures, captions and prose. Comparator 5 must never be described as an achievable
hardware saving.

## 4. Primary questions and how each is answered

Q1, Q2, Q4 and Q5 are answered by **direct measurement, decomposition and estimation with
confidence intervals** — none carries a hypothesis test. **Q3 alone is inferential** (§5).

### Q1 — Quantisation *(descriptive; no hypothesis test)*

*How much of the `G0_icame` energy gap to the continuous reference is caused by power-grid
quantisation?*

Report the exact identity per state, aggregated per regime:

    H_G − C = (H_G − E_G) + (E_G − C_AG) + (C_AG − C)
              allocation      pure rounding   rounding-induced assignment distortion

All terms are non-negative (machine-checked). Report absolute watts and shares, with the
distribution of the per-slot ratio `H_G / C` summarised by **median and IQR**, never by the mean —
the development data show a heavy right tail (max > 10⁶) that makes the mean meaningless.
**Primary output: the decomposition table. No p-value is attached to Q1.**

### Q2 — Radio allocation *(PRIMARY ESTIMATION ENDPOINT E1 — no significance test)*

*On `G2_wide10`, how much power does exact fixed-demand radio allocation save relative to
`EDF-StaleBeam-MinFeasible` while serving the same demand?*

**This is an estimation question, not a hypothesis test.** By construction the exact solver
minimises power over the *identical* demand multiset, so `E_G ≤ H_G` always and the optimality gap
is non-negative by mathematical necessity — verified with 0 violations in 15,878 development states
(`PRE_FREEZE_PROTOCOL_AUDIT.md` D1). Testing that gap against zero would be vacuous.

Primary metric: the seed-level **power optimality gap** `(H_G − E_G)/E_G`, demand held identical so
scheduling cannot contribute. Report **mean, median, p95, max, fraction exactly zero**, and a
**95% paired bootstrap CI on the mean gap**. **No p-value is attached.** The scientific question is
the *magnitude* of suboptimality.

### Q3 — Scheduling *(THE SOLE PRIMARY INFERENTIAL TEST, H2; equivalence-capable)*

*Does exact finite-horizon scheduling materially improve over EDF once radio allocation is held
exact?* — comparator 2 vs 3.

**Failure to reject must not be reported as equality.** Three outputs are required together:

1. paired **delivery** gap (packets) with 95% bootstrap CI;
2. paired **power** gap (W) with 95% bootstrap CI;
3. the **exact optimality-gap distribution** — the direct per-state gap between comparator 2 and
   comparator 3, which is a measurement rather than a non-rejection.

This is the only comparison in the study that is **genuinely uncertain**: neither side dominates,
because the joint controller optimises its *believed* (aged) model and is then executed truthfully.
On development data the joint controller was better in 70 of 640 traces, **worse in 51**, and tied
in 519 (`PRE_FREEZE_PROTOCOL_AUDIT.md` D3).

### Equivalence: DECLINED (author decision, 2026-09-14)

The author selected **OPTION E2 — decline equivalence / non-inferiority testing**, on the ground
that there is currently no independent engineering basis for a defensible δ and no margin would be
invented from development results.

| field | value |
|---|---|
| δ_delivery | **NOT SET — declined** |
| δ_power | **NOT SET — declined** |
| TOST | **REMOVED from this protocol** |

**H2 therefore reports exactly and only:**

1. mean paired delivery difference;
2. 95% BCa paired bootstrap CI;
3. exact paired two-sided sign-flip p-value;
4. Cohen's d_z;
5. paired power difference, **descriptively**;
6. direct optimality-gap distributions where applicable.

**No "equivalent", "non-inferior", "equal" or "near-optimal" claim may be inferred from an H2
non-rejection.** A non-rejection is reported as *"did not reject; 95% CI [lo, hi]"* and nothing more.

### Q4 — CSI information *(PRIMARY ESTIMATION ENDPOINT E2 — no significance test)*

*How much realised delivery is lost because the controller acts on aged rather than current CSI?* —
comparator 3 vs comparator 4 (**ORACLE / NON-DEPLOYABLE INFORMATION REFERENCE**).

**This is an information-value estimation question, not a hypothesis test.** The ORACLE maximises
delivery over *all* feasible action sequences on the true trace, so any executed aged plan is one
such sequence and `oracle ≥ aged` by construction — verified with 0 violations in 640 development
traces (`PRE_FREEZE_PROTOCOL_AUDIT.md` D2). No p-value is required to show that an information
upper bound differs from an information-limited controller.

Report: **ORACLE − aged realised-delivery difference** and **power difference**; mean, median, 95%
bootstrap CI, the full across-seed distribution, and effect size. The quantity being estimated is
the **value of perfect channel information**, not the performance of any deployable method. The
ORACLE label appears at every occurrence.

### Q5 — Runtime *(descriptive; no hypothesis test)*

*Can the fixed-demand exact allocator satisfy the 1 ms slot budget on the specified
implementation and hardware?*

Report mean, median, p95, p99, max and **fraction < 1 ms**, measured **single-process** with
`time.perf_counter` around the solve call only, with the full environment record. Report the free-
selection allocator separately and state explicitly that it does not satisfy 1 ms consistently.
**No portability claim to other hardware, compiled implementations, or larger K/N.**

## 5. Endpoint set and multiplicity

**One inferential test. No multiplicity correction.**

| id | comparison | type | metric | regime/grid |
|---|---|---|---|---|
| **E1** | comparator 1 vs 2 | **estimation** | paired power optimality gap + 95% CI | R3 × `G2_wide10` |
| **H2** | comparator 2 vs 3 | **inferential (sole)** | paired delivery difference + CI + exact sign-flip p | R3 × `G2_wide10` |
| **E2** | comparator 3 vs 4 (ORACLE) | **estimation** | paired delivery and power differences + CI | R3 × `G2_wide10` |

Because E1 and E2 are estimation endpoints, **H2 is the only primary significance test**, so m = 1
and **there is no multiple-testing correction to apply**. A Holm family is deliberately *not*
retained for symmetry: correcting a single test does nothing, and retaining two vacuous tests to
populate a family would misrepresent the design.

**Test for admitting any future hypothesis test.** A comparison may enter the inferential set only
if it tests a genuinely uncertain scientific proposition. It may **not** enter if one side is weakly
better than the other by solver construction. The three-way check is in
`PRE_FREEZE_PROTOCOL_AUDIT.md` §2 and was applied to all three original hypotheses.

Resolution, for the record: at n = 20 the exact paired sign-flip p-floor is 2/2²⁰ = **1.907e-6**,
far below α = 0.05 for a single test — ample. (Contrast the development campaign: n = 8 with m = 16
gave a floor of 0.0078 against a Holm threshold of 0.003125, making family-wise inference impossible
by construction.)

Every other regime, grid and comparator combination is **secondary and descriptive**, reported with
effect sizes and CIs but without inferential claims.

## 6. Statistical plan

- **Experimental unit:** the seed. One value per seed per comparator; 20 seeds.
- **Test:** exact paired two-sided sign-flip (randomisation) test on seed-level differences.
  2²⁰ = 1,048,576 sign assignments — enumerated exactly, not sampled.
- **Effect size:** Cohen's d_z and the mean paired difference, both always reported.
- **Intervals:** 95% paired bootstrap CI (BCa, 10,000 resamples, fixed seed recorded) on every
  primary and secondary paired difference.
- **Correction:** none — m = 1 (H2 only).
- **Equivalence:** **DECLINED.** TOST is removed. No equivalence conclusion is drawn anywhere.
- **Estimation endpoints:** E1 and E2 are reported as estimates with 95% BCa CIs and never as tests.
- **Reporting rule:** every non-rejection is reported as *"did not reject; CI [lo, hi]"*, never as
  *"equivalent"*, *"equal"* or *"near-optimal"*.

## 7. Evidence hierarchy for the final paper

Four categories, **never mixed in wording or in a table**:

| tier | label | admissible content |
|---|---|---|
| 1 | **EXACT MATHEMATICAL** | `p_req` inversion; beam dominance; power dominance; action-space reduction; fixed-demand solver optimality; DP de-duplication correctness; continuous-gap identity. Machine-checked, seed-independent. |
| 2 | **FINAL CONFIRMATORY EMPIRICAL** | Results from seeds 50001–50020 under this protocol only. |
| 3 | **DEVELOPMENT / EXPLORATORY** | Everything from seeds 10001–10008 and 20001–20010 — all of Stage I0, I-A, I-B, the closeout and the freeze. Never presented as confirmatory. |
| 4 | **ORACLE / NON-DEPLOYABLE** | Comparator 4, and the continuous reference as a mathematical bound. Never presented as an achievable method or saving. |

Tables must not place a Tier-2 and a Tier-3 number in the same column without an explicit tier
column. Prose must not move between tiers within a sentence.

## 8. Execution rules for FINAL TEST

1. Seeds **50001–50020 only**. Opened **once**.
2. Opening is permitted only after every gate in `FINAL_TEST_READINESS_CHECKLIST.md` is green,
   including author approval of the amendment (`AMENDMENT_V2_AUTHOR_DECISION.md`) and author
   selection of δ.
3. **No method may be modified after FINAL TEST is opened.** There is no tuning stage because there
   is no learned controller.
4. **If a bug is discovered after opening: STOP. Document it. Do not silently re-run.** A re-run
   requires a dated amendment recording what was wrong, what changed, and that the seeds were
   re-opened — and the fact of the re-open must appear in the manuscript.
5. Every run writes to an append-only ledger with seed, regime, grid, comparator, git commit,
   configuration hash and result path. Nothing is deleted.
6. The exactness suite must pass immediately before and immediately after the campaign, with both
   results recorded.

## 9. Compute estimate (not yet spent)

Based on measured development costs, and deliberately conservative:

| component | scale | estimate |
|---|---|---|
| comparators 1–2 + continuous reference | **2 regimes** × 2 grids × 20 seeds × 250 slots | ≈2–3 min wall (4 workers) |
| comparator 3–4 exact joint, full K=8 N=4 H=3 | **2 regimes** × 2 grids × 20 seeds × 5 warm-ups | ≈20–30 min wall (4 workers) |
| latency benchmark, single process | as §4 Q5 | ≈2–3 min |
| **total** | | **≈25–40 min wall, ≈2 core-hours** |

Node budget for the exact joint solver: **2 × 10⁸ nodes / 600 s per solve** (the closeout budget,
under which 0 of 640 development traces were censored; worst case needed 5.45 M nodes). Any trace
exceeding it is reported as a barrier and **never** replaced by a heuristic value.

## 10. Title / positioning hold

**The manuscript title is unchanged and must not be changed now.** It remains:

> *AI-Enabled Beamforming and Dynamic Spectrum Allocation for Reliable Long-Range IoT over 6G*

**Flagged for author attention.** If the final journal method contains no substantive AI component —
which is the current trajectory, since no learned controller is being introduced and the
contribution is an exact-optimisation benchmark — then **"AI-Enabled" may no longer accurately
describe the journal manuscript**. This is a research-integrity matter, not a presentational one.

Two further points the authors should weigh:

- The **ICAME'26 accepted title and abstract are immutable** and must remain exactly as accepted for
  the conference record, the Abstracts Book and the presentation. A journal-title change would create
  a deliberate, disclosable divergence between the conference artifact and the journal manuscript,
  which is normal for an extended paper but must be stated explicitly in the journal submission.
- The project instructions require the paper to support its title. If the title keeps "AI-Enabled",
  the method must contain a substantive AI component; if it does not, the title should change. Those
  are the only two consistent options.

Alternative titles prepared **for later author review only — none is applied**:

1. *Exact Benchmarks for Beam and Spectrum Allocation in Long-Range Industrial IoT over 6G*
2. *How Far from Optimal? Exact Radio-Allocation Benchmarks for Deadline-Constrained 6G Industrial IoT*
3. *Quantisation, Channel Ageing and Algorithmic Headroom in Joint Beam–Subchannel–Power Allocation*
4. *Optimality Gaps in Deadline-Aware Uplink Scheduling with Codebook Beam Selection and Discrete Power Control*
5. *When Does Control Complexity Pay? Exact Optimisation Benchmarks for 6G Industrial IoT Uplinks*

Titles 2 and 5 match the primary scientific question most closely; title 1 is the most conservative
change. **No title is adopted and no manuscript text is altered by this document.**

## 11. What this protocol does not do

It does not design a controller and **no learned controller will be introduced**. It does not tune
anything. It does not open FINAL TEST seeds. It does not change the manuscript or its title. It
performs no equivalence testing — that was declined by the author.

## 12. Freeze record

| field | value |
|---|---|
| Status | **FROZEN — AUTHOR-APPROVED — NOT EXECUTED** |
| Frozen on | 2026-09-14 |
| Approval record | *Author approval received explicitly in project chat on 2026-09-14* |
| Governing protocol | **JOURNAL_PROTOCOL_V1 + Amendment A2 (2026-09-14)** |
| Confirmatory regimes | R1, R3 (R4 excluded; `G1_ext7` omitted) |
| Endpoints | E1 estimation · **H2 sole inferential test** · E2 estimation |
| Multiplicity | none — m = 1 |
| Equivalence | **declined — TOST removed** |
| Learned controller | none |
| FINAL TEST | **LOCKED** — A9 unresolved; C10/C11/C13 unimplemented |
