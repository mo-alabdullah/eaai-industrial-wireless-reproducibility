# PRIMARY_HYPOTHESES_REGISTER — final confirmatory study

**Status: FROZEN — AUTHOR-APPROVED — NOT EXECUTED. Date: 2026-09-14.**

Author approval received explicitly in project chat on 2026-09-14. FINAL TEST seeds
**50001–50020 unopened**. No simulation has been run against this register.
Governing protocol: **JOURNAL_PROTOCOL_V1 + Amendment A2 (2026-09-14)**.

**This register is frozen.** Endpoints, metrics, tests and the equivalence decision may not be
changed after FINAL TEST is opened; any change before then requires a dated amendment entry in §11.

**Revision 2026-09-14 (pre-freeze protocol correction).** The earlier draft declared a three-member
Holm family (H1, H2, H3). Two of those three were **structurally dominated by solver construction**,
so testing them against zero was vacuous. They are reclassified as **estimation endpoints**. One
genuinely uncertain inferential question remains. Evidence and reasoning:
`PRE_FREEZE_PROTOCOL_AUDIT.md`.

All fields are now filled and the register is frozen: endpoints, metrics, margins and tests may not
change after FINAL TEST is opened.

---

## 1. Endpoint classification

All endpoints are evaluated in the pre-declared cell **R3 (×2.0, d_CSI = 5, load 0.40) ×
`G2_wide10`**, full scale K = 8, N = 4, H = 3, on seeds 50001–50020.

| id | comparison | type | why |
|---|---|---|---|
| **E1** *(was H1)* | `EDF-StaleBeam-MinFeasible` vs exact fixed-demand radio allocator | **PRIMARY ESTIMATION ENDPOINT** | `E_G ≤ H_G` holds **by construction** — the exact solver minimises power over the *identical* demand multiset. Verified: 0 violations in 15,878 development states. A test against zero would be vacuous. |
| **H2** | EDF + exact fixed-demand radio vs exact finite-horizon joint controller (aged CSI) | **PRIMARY INFERENTIAL HYPOTHESIS — the only one** | Neither side dominates. The joint controller optimises its *believed* (aged) model and is then executed truthfully, so it can realise fewer packets. Verified: joint better in 70/640 traces, **worse in 51/640**, tied in 519. |
| **E2** *(was H3)* | exact joint (aged CSI) vs exact joint **ORACLE** (current CSI) | **PRIMARY ESTIMATION ENDPOINT** | The ORACLE maximises delivery over *all* feasible action sequences on the true trace, so any executed aged plan is one such sequence and `oracle ≥ aged` **by construction**. Verified: 0 violations in 640 traces. Its role is to estimate the **value of perfect channel information**, not to win a comparison. |

## 2. E1 — magnitude of radio-allocation suboptimality *(estimation, no significance test)*

Quantity: the seed-level **power optimality gap** `(H_G − E_G)/E_G`, demand held identical so
scheduling cannot contribute.

Reported: **mean, median, p95, max, fraction exactly zero**, and a **95% paired bootstrap CI on the
mean gap**. Also the same statistics per grid and per regime as secondary description.

**No p-value is attached.** The scientific question is *how large* the suboptimality is, not whether
an exact minimiser beats a heuristic on the heuristic's own objective — which it must.

## 3. H2 — scheduling *(the sole primary inferential test)*

Comparison: EDF + exact fixed-demand radio **vs** exact finite-horizon joint controller under aged
CSI. Primary metric: **realised packet-delivery difference** over the horizon, paired by seed.

Reported in all cases:

- paired mean difference;
- **95% BCa paired bootstrap CI**;
- **exact paired two-sided sign-flip p** (all 2²⁰ = 1,048,576 sign assignments enumerated);
- effect size (Cohen's d_z) and the direction;
- the exact optimality-gap distribution between the two controllers as supporting description.

**Equivalence handling: DECLINED (§5).** TOST is removed. H2 reports exactly the six items listed
above and nothing more. **Equivalence is never inferred from non-rejection.**

## 4. E2 — value of perfect channel information *(estimation, no significance test)*

Comparison: exact joint (aged CSI) vs exact joint **ORACLE / NON-DEPLOYABLE INFORMATION REFERENCE**
(current CSI).

Reported: **ORACLE − aged realised-delivery difference** and **power difference**; mean, median,
95% CI, the full across-seed distribution, and effect size.

**No p-value is required** to show that an information upper bound differs from an
information-limited controller. The ORACLE label appears at every occurrence — table, figure,
caption and prose.

## 5. Equivalence margin δ — **OPTION E2 SELECTED: DECLINED** (author, 2026-09-14)

δ would have applied to **H2 only**; E1 and E2 are estimation endpoints and never needed one.

**Decision: equivalence / non-inferiority testing is DECLINED.**

**Reason, as given by the author:** there is currently no independent engineering basis for a
defensible δ margin, and no margin will be invented from development results.

| field | value |
|---|---|
| δ_delivery | **NOT SET — equivalence testing declined** |
| δ_power | **NOT SET — equivalence testing declined** |
| TOST | **REMOVED from the confirmatory statistical plan** |

**Binding consequence.** No **"equivalent"**, **"non-inferior"**, **"equal"** or **"near-optimal"**
claim may be inferred from an H2 non-rejection, anywhere in the paper. A non-rejection is reported
as *"did not reject; 95% CI [lo, hi]"* and nothing further.

This was the right call on the evidence available: a margin chosen now could only have been
calibrated against the development results, which would have made any equivalence claim
retrospective and void.

## 6. Multiplicity

**None required.** With E1 and E2 reclassified as estimation endpoints, **H2 is the only primary
significance test**, so m = 1 and there is no multiple-testing correction to apply.

A Holm family is **not** retained for symmetry. Any additional hypothesis test proposed later must
first be justified as testing a genuinely uncertain scientific proposition rather than a dominance
property implied by solver construction — the test `PRE_FREEZE_PROTOCOL_AUDIT.md` §2 applies.

Resolution, for the record: at n = 20 the exact paired sign-flip p-floor is 2/2²⁰ = **1.907e-6**,
far below α = 0.05 for a single test. Resolution is ample. (Contrast the development campaign:
n = 8, m = 16, floor 0.0078 > threshold 0.003125, which made family-wise inference impossible by
construction.)

## 7. Secondary / descriptive outputs (no inferential claims)

| id | content |
|---|---|
| S1 | Quantisation decomposition `H_G − C = (H_G − E_G) + (E_G − C_AG) + (C_AG − C)`, both grids, **both confirmatory regimes (R1, R3)**; absolute watts and shares; median and IQR of `H_G / C` (never the mean — heavy right tail) |
| S2 | All comparators in R1, both grids — effect sizes and 95% CIs only |
| S3 | Full exact optimality-gap distributions for every regime/grid |
| S4 | Latency distributions for both solvers with the environment record |
| S5 | Continuous-power reference columns throughout, labelled **MATHEMATICAL LOWER / REFERENCE BOUND** |

No secondary result may be described as significant, and none may be promoted into the primary
endpoint set after the fact.

## 8. Author decisions — **RECORDED 2026-09-14**

| field | value |
|---|---|
| Endpoint classification (E1 estimation, H2 sole inferential test, E2 estimation) | **☑ APPROVED** |
| Primary cell R3 × `G2_wide10` | **☑ APPROVED** |
| Confirmatory regimes | **☑ R1 and R3 only**; R4 excluded (development context only) |
| Grids | **☑ `G0_icame` conference/reproducibility · `G2_wide10` numerical sensitivity only · continuous `p_req` mathematical bound only**; `G1_ext7` omitted |
| δ option selected | **☑ OPTION E2 — DECLINED** |
| δ_delivery / δ_power | **NOT SET — declined** |
| TOST | **REMOVED** |
| No multiplicity correction (m = 1) | **☑ APPROVED** |
| New RL/ML method | **☑ none will be introduced** |
| Amendment V2 (`AMENDMENT_V2_AUTHOR_DECISION.md`) | **☑ APPROVED AS PROPOSED — applied as Amendment A2** |
| Register frozen on | **2026-09-14** |
| Approval record | *Author approval received explicitly in project chat on 2026-09-14* |

## 9. Statistical specification (frozen on sign-off)

- Experimental unit: the seed. n = 20 (50001–50020).
- H2 test: exact paired two-sided sign-flip, all 2²⁰ sign assignments enumerated. α = 0.05. m = 1.
- Effect size: Cohen's d_z **and** the mean paired difference, always both.
- Intervals: 95% BCa paired bootstrap, 10,000 resamples, bootstrap seed recorded in the ledger.
  Applied to E1, E2 and H2 alike.
- Equivalence: **none — declined.** TOST is removed from the plan.

## 10. Reporting rules (frozen on sign-off)

1. Non-rejection is reported as **"did not reject; 95% CI [lo, hi]"** — never "equivalent", "equal",
   "no difference" or "near-optimal".
2. E1 and E2 are reported as **estimates with intervals**, never as tests.
3. Development results (seeds 10001–10008, 20001–20010) are labelled **DEVELOPMENT / EXPLORATORY**
   and never share a table column with confirmatory results.
4. The ORACLE carries **NON-DEPLOYABLE UPPER / INFORMATION REFERENCE** at every occurrence.
5. The continuous reference carries **MATHEMATICAL LOWER / REFERENCE BOUND** and is never described
   as an achievable saving.
6. `G2_wide10` is a **non-binding numerical sensitivity grid** — never "realistic", "practical", or
   a deployment target.
7. Near-optimality claims require direct exact optimality gaps with CIs and, for practical
   equivalence, a pre-specified δ. They may not be inferred from non-significance.

## 11. Change log

| date | change | authority |
|---|---|---|
| 2026-09-14 | Register created; H1–H3 proposed as a 3-member Holm family; δ left blank | confirmatory design task |
| 2026-09-14 | **H1 → E1 and H3 → E2 reclassified as estimation endpoints** (structurally dominated by solver construction, verified on frozen data); H2 retained as the sole inferential test; **Holm family removed (m = 1)**; δ restructured into two explicit author options with no recommended value | pre-freeze protocol correction |
| **2026-09-14** | **AUTHOR DECISIONS RECORDED AND REGISTER FROZEN**: endpoint structure approved; R1/R3 only, R4 excluded, `G1_ext7` omitted; grid roles fixed; **equivalence DECLINED (OPTION E2), TOST removed, δ NOT SET**; m = 1 confirmed; no RL/ML method; Amendment V2 approved and applied as Amendment A2 to the protocol | author approval, project chat 2026-09-14 |
