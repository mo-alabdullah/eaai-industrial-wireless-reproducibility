# JOURNAL_PROTOCOL_V1 — pre-registration for the IJOCTA extension

> **EFFECTIVE VERSION: JOURNAL_PROTOCOL_V1 + Amendment A2 (2026-09-14).**
> Sections 1–9 below are the **original V1 text, unmodified**. Amendment A2 is additive and appears
> in full in §11; it is logged in §10. Nothing in the original text has been rewritten, deleted or
> silently changed.
> SHA-256 of this file immediately **before** Amendment A2 was appended:
> `790281df55f90efc8b066254174de53403566c30678be2d8a07bc25de5caf6ea`

Frozen before any algorithm change or final experiment. Amendments require a dated entry in §10.
The ICAME'26 confirmatory artifacts (`10_confirmatory/`, seeds 20001–20010, T = 200) are **read-only**
and are never regenerated; all journal work is additive under `13_journal_extension/`.

---

## 1. Central scientific question

> Can an online, structure-aware constrained controller **minimise aggregate transmit power** while
> satisfying class-specific **reliability, deadline-violation and overflow** constraints, subject to
> hard radio-resource feasibility, in a heterogeneous industrial 6G uplink with static sensors and
> mobile AMR/AGVs under aged CSI?

This replaces the ICAME framing (maximise a delivery-shaped reward subject to a power budget). The
change is motivated by (a) IJOCTA scope — optimization and control with a comprehensive computational
study — and (b) the audit finding that the previous power "advantage" was an artefact of max-power
baselines and an untrained power head, not an optimised quantity.

## 2. Formal problem (derived from the implementation, not assumed)

**Slot structure.** Per physical slot `t`: arrivals → overflow → deadline expiry → state frozen →
the controller emits a length-`N` joint action → transmissions resolved → costs accrue.
Episode = `T_meas` measurement slots (arrivals on) followed by a drain phase (arrivals off) until
every measurement-cohort packet is terminal.

**Decision.** `a_t = (a_{t,1},…,a_{t,N})`, each `a_{t,n} ∈ {idle} ∪ (k,b,p)` with
`k ∈ {1..K}`, `b ∈ {1..B}`, `p ∈ {0.05,0.10,0.20,0.40} W`.

**Hard feasible set `A(s_t)`** (enforced by the environment's conditional mask *before* sampling; the
environment re-validates and rejects violations — no post-hoc repair):
1. subchannel exclusivity — at most one device per subchannel;
2. per-device subchannel cap `N_max`;
3. per-device total power cap `Σ_n p_{k,n} ≤ P_tot = 0.8 W`;
4. packet availability — a non-idle token requires a queued packet;
5. beam/codebook feasibility `b ∈ {1..B}`.

**Link model (unchanged).** `SINR_{k,n,b} = p·β_{k,n}·G_{k,n,b}/σ_n²`,
`σ_n² = k_B T W 10^{NF/10}`; delivery iff `W·τ·log₂(1+SINR) ≥ L_k`; OMA, no intra-cell interference.

**Objective (new).** With `P_t = Σ_{(k,n) active} p_{k,n}` the aggregate slot power,

&nbsp;&nbsp;&nbsp;&nbsp;**minimise over π:  J(π) = E_π[ (1/T_meas) · Σ_{t∈W} P_t ]**

**Constraints (episode-sum shortfalls, feasible when ≤ 0), for each class c ∈ {static, mobile}:**

&nbsp;&nbsp;&nbsp;&nbsp;`C_rel,c = ρ_c·a_c − d_c ≤ 0`  (delivery floor)
&nbsp;&nbsp;&nbsp;&nbsp;`C_dv,c = v_c − ε_c·a_c ≤ 0`  (deadline violations)
&nbsp;&nbsp;&nbsp;&nbsp;`C_over,c = o_c − η_c·a_c ≤ 0`  (overflow)

where `a_c` = cohort arrivals (incl. overflow-dropped), `d_c` deliveries, `v_c` deadline violations,
`o_c` overflows. **`J_cost = 3|C| = 6`** — the former `C_pow` channel is removed because power has
moved into the objective.

**Lagrangian (mechanism, not a convergence claim).**
`L(π,λ) = J(π) + Σ_{i=1..6} λ_i s_i E[C_i]`, minimised in `π`, maximised in `λ ≥ 0`, with fixed
deterministic per-class scales `s_i` and one multiplier trajectory per training run. No theoretical
feasibility or convergence guarantee is claimed; feasibility is reported empirically only.

**Deployability constraint.** The online controller may use only **aged CSI (`d_CSI`)**, queue/
deadline/retransmission state and class labels at inference. Current-CSI quantities may be used as
**training-time supervision only** (disclosed) and in explicitly labelled oracle upper bounds.

## 3. Evaluation horizon and constraint thresholds (from Stage F)

Adopted from `CONSTRAINT_RESOLUTION_ANALYSIS.md`:

- **D1** `T_train = 200` slots; **evaluation = R = 10 independent episodes × T = 250 slots per seed**
  (2,500 measurement slots/seed). Raises mobile arrivals/seed from ≈159 to ≈2,000 at p = 0.40.
- **D2** Reliability floors unchanged: `ρ_static = 0.99`, `ρ_mobile = 0.995`. Mobile reliability at
  p = 0.05 remains weakly resolved and **must be reported as such**.
- **D3** `ε_mobile = 1e-4` and `η_mobile = 1e-3` are **unmeasurable at any affordable horizon**
  (10⁵–10⁶ slots). They are replaced for the journal study by
  **`ε_mobile = η_mobile = 5e-3`** (≥10-packet slack at 2,500 slots), and the original values and the
  reason for the change are stated explicitly in the manuscript. Static thresholds
  (`ε_static = η_static = 0.01`) are retained.
- **D4** Every constraint result is reported with its packet-level slack.

## 4. Seed protocol (strict separation)

| Role | Seeds | Use | Rule |
|---|---|---|---|
| ARCHIVE (ICAME) | 20001–20010 | frozen conference results | never regenerated, never reused for journal training |
| **TRAIN** | 30001–30005 | 5 independent training runs per configuration | policies are fitted here only |
| **VALIDATION** | 40001–40005 | budget/convergence selection, hyperparameters, Gates G1–G3 | may be inspected freely |
| **FINAL TEST** | 50001–50020 | final reported results | **sealed** until the algorithm *and* all hyperparameters are frozen; opened once |

**Generalisation design (changed from ICAME).** A policy trained on a TRAIN seed is evaluated on
**held-out** VALIDATION/TEST seeds — i.e. unseen arrival, mobility and channel realisations. (In the
ICAME study each policy was trained and evaluated under the same seed index, which measures fitting
rather than generalisation.) Inference unit = **test seed**; training-seed variability is reported
separately as a spread across the 5 trained policies.

## 5. Stage-gated training and convergence rule

Budgets are escalated on VALIDATION seeds only:
`80 → 160 → 320 → 640 → 1280 → 2560` rollout episodes (→ 3200+ only if the rule below is unmet).

At every checkpoint record: objective (mean aggregate power), per-class PDR, deadline-violation and
overflow ratios, constraint slacks, all six multipliers `λ_i`, beam accuracy, policy entropy, KL,
clip fraction, and action-distribution statistics.

**Convergence rule (pre-registered).** A configuration is *converged* when, across the last two
budget doublings, on VALIDATION seeds:
1. the relative change in mean objective is < 5%, **and**
2. the relative change in each binding constraint metric is < 5%, **and**
3. every multiplier trajectory is stationary (no monotone drift over the final 25% of updates), **and**
4. policy entropy has neither collapsed to ~0 nor remained at the uniform-policy value.

Reaching a preset episode count is **not** convergence. If the rule is unmet at 3200 episodes, the
result is reported as non-converged and Success Criterion E fails.

## 6. Critical gates (must pass in order, on VALIDATION seeds only)

**G1 — Does learning exist?** The proposed policy must be demonstrably non-random:
(i) its action distribution differs from uniform-over-feasible (χ²/TV distance, plus beam accuracy
above the `1/B = 0.125` chance line with a paired test), **and**
(ii) at least one primary optimization/control metric improves materially over `Random` without
unacceptable constraint violation.
*Failure ⇒ STOP; diagnose and redesign. No final campaign.*
*(Context: the archived BSA-C-PPO fails this gate today — indistinguishable from Random at p = 0.40,
p = 0.58/0.09/0.70 on mobile PDR/static PDR/power.)*

**G2 — Do constraints matter?** The constrained method must differ measurably from its unconstrained
counterpart in a regime where constraints bind (paired test on constraint slack and on the objective).
*Failure ⇒ STOP; do not claim constrained RL as the main contribution; reframe.*

**G3 — Fair power comparison.** The proposed method must be compared against
`EDF-StaleBeam-MinPow` and `EDF-StaleBeam-Budgeted`. Comparison against max-power EDF is **not**
sufficient. *If power-aware EDF dominates, that result is reported as the finding.*

## 7. Success criteria (pre-registered, applied before writing)

A. constrained mechanism beats unconstrained/penalty on feasibility or power at equal reliability;
B. at comparable reliability/deadline performance, the method beats power-aware EDF on power **or**
   exhibits a clearly characterised different trade-off;
C. the beam component exceeds chance **and** provides measurable value in ≥1 physically meaningful
   regime (per `BEAM_ISOLATION_SPEC.md`);
D. a quantified optimality gap versus the Stage-I benchmark on tractable instances;
E. convergence per §5;
F. conclusions hold across held-out seeds and ≥1 unseen configuration;
G. every claimed component earns its place in the ablation, else it is removed from the contribution.

Any failed criterion is reported, not hidden; the contribution is reframed accordingly.

## 8. Statistical plan

Seed-level inference on FINAL TEST seeds (n = 20). Report mean, median, SD, 95% CI; matched-seed
paired differences; exact paired sign-flip permutation tests; Cohen's `d_z`; Holm correction within
each pre-declared family. Packets are never treated as independent observations. Within-seed
replication (R = 10 episodes) is used for variance decomposition, not to inflate n. The test set is
opened once; no metric or hyperparameter is selected on it.

## 9. Scope, deferrals and compute

**In scope:** converged training protocol; power-matched baselines; causal beam isolation;
constrained power-minimisation reformulation; small-instance optimisation benchmark; reduced regime
map over load × distance × CSI age × power budget.

**Deferred (environment-limited, to be disclosed as a limitation, not concealed):** PyTorch/GPU port
(torch is not installable — PyPI blocked); K = 32 scalability; interference model; 20–30 seeds at
every grid point; full-factorial regime grid.

**Compute reality:** 4 CPU cores, 3 GB RAM, no GPU; ≈0.156 s per 200-slot training episode. A
converged campaign at 2560 episodes ≈ 400 s/run. Live accounting in `COMPUTE_LEDGER.md`.

**Hard stop:** if adequate convergence cannot be reached on a scientifically useful scope with these
resources, the project stops and reports that external compute is required before submission — under-
training the final proposed method is not an acceptable outcome.

## 10. Amendment log

| Date | Amendment | Reason |
|---|---|---|
| 2026-09-13 | v1 frozen | initial pre-registration |
| **2026-09-14** | **A2 — power-grid roles** (§11): `G0_icame` retained as the conference/reproducibility grid; `G2_wide10` added as a **numerical sensitivity grid only**; continuous `p_req` added as a **mathematical reference bound only**; every power conclusion must name its grid; prior `G0` results remain valid but **grid-conditional**; **no archived ICAME result is recomputed or superseded** | Stage-I0 established that the `G0_icame` floor sits **24.8 dB above the median link requirement**, making the transmit-power objective degenerate at nominal range and 93.8–100.0% of the power gap attributable to quantisation rather than allocation. Evidence: `POWER_GRID_SENSITIVITY.md`, `CONTINUOUS_POWER_REFERENCE.md`. Approved by the author in project chat on 2026-09-14 (`AMENDMENT_V2_AUTHOR_DECISION.md`) |

---

## 11. Amendment A2 — power-grid roles (effective 2026-09-14)

**Status: APPROVED AND APPLIED.** Author approval received explicitly in project chat on 2026-09-14
and recorded in `AMENDMENT_V2_AUTHOR_DECISION.md`. This section is **additive**: §§1–9 above are the
original V1 text and are unchanged.

### A2.1 — `G0_icame` is the conference / reproducibility grid

`P = {0.05, 0.10, 0.20, 0.40} W` is retained unchanged as the reference for every ICAME'26
comparison and for reproducibility. **Archived ICAME results are not recomputed, not reinterpreted
and not superseded.** Every conclusion in the conference artifact stands as a statement about this
grid.

### A2.2 — `G2_wide10` is a NON-BINDING NUMERICAL SENSITIVITY GRID ONLY

`P_ext = {1e-5, 3.1623e-5, 1e-4, 3.1623e-4, 1e-3, 3.1623e-3, 1e-2, 3.1623e-2, 1e-1, 0.4} W`
(~5 dB steps) exists to separate properties of the control problem from properties of the grid
floor. **No hardware-realism or deployment claim is permitted** for its −20 dBm floor: this project
holds no external engineering reference for it. It must be described as a *numerical sensitivity
grid* — never *realistic*, never *practical*, never a deployment target. This restriction is binding
and does not expire.

### A2.3 — continuous `p_req` is a MATHEMATICAL LOWER / REFERENCE BOUND ONLY

The analytic requirement used without quantisation under identical caps is the bound against which
both grids are measured. It presumes arbitrarily fine transmit-power control, which this project
does not establish. It may appear as a bound and **must never be reported as an achievable saving**.

### A2.4 — every power conclusion must name its grid

All results carry an explicit `grid` label, with the continuous reference as its own labelled
column. Grids are never combined in one table without that column.

### A2.5 — prior results remain valid but grid-conditional

Stages D, E, F, D.1, E.1 and the oracle-headroom decomposition are **not invalidated**. Their
power-related conclusions become explicitly `G0_icame`-conditional. In particular the Stage-D.1
conclusion is restated as: *dynamic power control provides no measurable value **on the ICAME grid**
at nominal range because the grid floor is 24.8 dB above the median requirement* — not *because
power control is unnecessary*.

### A2.6 — assumptions register

`P_min` is recorded as a configuration choice, and every minimum-power statement in the journal
manuscript must name the grid it is conditional on.

### What A2 does NOT change

Constraint thresholds (ε, η, ρ); the seed protocol of §4 including the sealed FINAL TEST seeds
50001–50020; evaluation horizons; Gates G1–G3; the statistical plan of §8; and every archived ICAME
artifact. A2 touches the **action space and the reporting rules only**.

### Confirmatory study governed by A2

The final confirmatory design is `FINAL_CONFIRMATORY_PROTOCOL_V2.md` with
`PRIMARY_HYPOTHESES_REGISTER.md`, both frozen on 2026-09-14. Note that the confirmatory study
introduces **no learned controller**, so §5 (stage-gated training and convergence) and the
training/validation seed bands of §4 are **not exercised** by it; the FINAL TEST seed seal is
unaffected and remains in force.
