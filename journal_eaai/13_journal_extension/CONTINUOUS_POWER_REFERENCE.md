# CONTINUOUS_POWER_REFERENCE — Stage I-CLOSEOUT task 3

**Status: internal development evidence. MATHEMATICAL REFERENCE ONLY.** Development seeds
10001–10008; FINAL TEST seeds not opened. No hardware-realism claim is attached to continuous power
control, and none should be read into any number in this file.

Source: `results/continuous_ref.csv` (15,882 slot states), produced by `code/run_continuous.py`;
tables by `code/optimization/analyse_continuous.py`. Solver:
`optimization.radio.solve_continuous_fixed_demand`.

## 1. Definition and status

For each (device, subchannel) pair the exact analytic requirement is

    p_req(k,n,b) = σ²·(2^(L_k/(W·τ)) − 1) / (β_k·G[k,n,b])

The continuous reference replaces the grid step `quantise_up(p_req)` by `p_req` itself, subject to
the **same** per-device total-power cap, the same per-device assignment cap, the same subchannel
exclusivity and the same packet availability. Beam dominance (Lemma 1) is unchanged, so the
gain-maximising beam remains optimal; only the assignment of the fixed demand multiset to
subchannels is searched, exhaustively.

**This is a lower bound, not a method.** It presumes arbitrarily fine transmit-power control. No
component of this project establishes that such control is available on any target hardware, and
the reference is used here only to separate what the *grid* costs from what the *algorithm* costs.
Where the discrete grids and the continuous reference appear in the same table they are labelled.

Validated in `tests/test_optimization_benchmark.py`:
- `test_continuous_is_a_valid_lower_bound` — the continuous optimum never exceeds the grid optimum
  for the same demand, and refining a grid moves the grid optimum monotonically towards it;
- `test_gap_decomposition_is_exact_and_nonnegative` — the identity in §2 holds to 1e-15 with every
  term non-negative.

## 2. Exact gap decomposition

With `H_G` the heuristic's power on grid `G`, `E_G` the exact fixed-demand optimum on `G`, `A_G` the
assignment that attains `E_G`, `C_AG` the continuous cost of that same assignment, and `C` the
continuous optimum over all assignments:

    H_G − C  =  (H_G − E_G)  +  (E_G − C_AG)  +  (C_AG − C)
                allocation      pure rounding    quantisation-induced
                                                 assignment distortion

Each term is non-negative: `E_G` is optimal on the grid, every grid level is ≥ its `p_req`, and `C`
is optimal over assignments. The **quantisation share** reported below is
`(E_G − C_AG) + (C_AG − C)`, i.e. rounding plus the assignment distortion that rounding induces.

## 3. Results

### C1 — mean slot power: heuristic, exact-on-grid, and the continuous reference (W)

| regime | grid | slots | H_G heuristic | E_G exact on grid | C_AG continuous cost of A_G | C continuous optimum | E_G / C |
|---|---|---|---|---|---|---|---|
| R1 ×1.0 age1 | G0_icame | 1,977 | 0.159636 | 0.159636 | 0.006074 | 0.004195 | **38.1×** |
| R1 ×1.0 age1 | G2_wide10 | 1,987 | 0.012561 | 0.008473 | 0.005234 | 0.004428 | **1.9×** |
| R4 ×1.5 age3 | G0_icame | 1,982 | 0.162513 | 0.160898 | 0.016602 | 0.012275 | **13.1×** |
| R4 ×1.5 age3 | G2_wide10 | 1,989 | 0.034895 | 0.025660 | 0.015332 | 0.012778 | **2.0×** |
| R2 ×2.0 age1 | G0_icame | 1,981 | 0.174483 | 0.165169 | 0.030474 | 0.024174 | **6.8×** |
| R2 ×2.0 age1 | G2_wide10 | 1,988 | 0.074151 | 0.042886 | 0.027702 | 0.024484 | **1.8×** |
| R3 ×2.0 age5 | G0_icame | 1,984 | 0.177016 | 0.168170 | 0.031547 | 0.025291 | **6.6×** |
| R3 ×2.0 age5 | G2_wide10 | 1,994 | 0.074455 | 0.044911 | 0.028920 | 0.025701 | **1.7×** |

### C2 — exact three-way decomposition of the total gap H_G − C

All three terms are non-negative and sum exactly to the total (asserted in
`test_gap_decomposition_is_exact_and_nonnegative`). Shares are of the mean total gap.

| regime | grid | total gap (W) | allocation H_G−E_G | rounding E_G−C_AG | assignment distortion C_AG−C | allocation % | quantisation % |
|---|---|---|---|---|---|---|---|
| R1 ×1.0 age1 | G0_icame | 0.155440 | 0.000000 | 0.153562 | 0.001878 | **0.0%** | **100.0%** |
| R1 ×1.0 age1 | G2_wide10 | 0.008133 | 0.004087 | 0.003240 | 0.000806 | **50.3%** | **49.7%** |
| R4 ×1.5 age3 | G0_icame | 0.150238 | 0.001615 | 0.144296 | 0.004327 | **1.1%** | **98.9%** |
| R4 ×1.5 age3 | G2_wide10 | 0.022117 | 0.009234 | 0.010329 | 0.002554 | **41.8%** | **58.2%** |
| R2 ×2.0 age1 | G0_icame | 0.150308 | 0.009313 | 0.134695 | 0.006300 | **6.2%** | **93.8%** |
| R2 ×2.0 age1 | G2_wide10 | 0.049668 | 0.031266 | 0.015183 | 0.003219 | **62.9%** | **37.1%** |
| R3 ×2.0 age5 | G0_icame | 0.151725 | 0.008846 | 0.136623 | 0.006256 | **5.8%** | **94.2%** |
| R3 ×2.0 age5 | G2_wide10 | 0.048754 | 0.029544 | 0.015991 | 0.003218 | **60.6%** | **39.4%** |

### C3 — per-slot gap ratios H_G / C (distribution)

| regime | grid | median | mean | p95 | max |
|---|---|---|---|---|---|
| R1 ×1.0 age1 | G0_icame | 76.9× | 583.7× | 1540.1× | 61,087× |
| R1 ×1.0 age1 | G2_wide10 | 2.7× | 3.1× | 6.1× | 12× |
| R4 ×1.5 age3 | G0_icame | 22.9× | 235.5× | 429.0× | 57,658× |
| R4 ×1.5 age3 | G2_wide10 | 2.5× | 2.9× | 5.5× | 14× |
| R2 ×2.0 age1 | G0_icame | 12.0× | 1113.6× | 231.4× | 1,154,806× |
| R2 ×2.0 age1 | G2_wide10 | 2.9× | 3.2× | 5.9× | 231× |
| R3 ×2.0 age5 | G0_icame | 11.9× | 582.9× | 225.2× | 917,784× |
| R3 ×2.0 age5 | G2_wide10 | 2.8× | 3.0× | 5.8× | 17× |

### C4 — feasibility: demands the grid cannot serve but continuous power can

| regime | grid | slots with demand | grid infeasible | continuous infeasible |
|---|---|---|---|---|
| R1 ×1.0 age1 | G0_icame | 1,977 | 0 (0.00%) | 0 (0.00%) |
| R1 ×1.0 age1 | G2_wide10 | 1,987 | 0 (0.00%) | 0 (0.00%) |
| R4 ×1.5 age3 | G0_icame | 1,982 | 0 (0.00%) | 0 (0.00%) |
| R4 ×1.5 age3 | G2_wide10 | 1,989 | 0 (0.00%) | 0 (0.00%) |
| R2 ×2.0 age1 | G0_icame | 1,981 | 0 (0.00%) | 0 (0.00%) |
| R2 ×2.0 age1 | G2_wide10 | 1,988 | 0 (0.00%) | 0 (0.00%) |
| R3 ×2.0 age5 | G0_icame | 1,984 | 0 (0.00%) | 0 (0.00%) |
| R3 ×2.0 age5 | G2_wide10 | 1,994 | 0 (0.00%) | 0 (0.00%) |

## 4. Reading

**On the conference grid the power gap is overwhelmingly quantisation.** At nominal range the
allocation term is exactly **0.0%** — the heuristic already attains the grid optimum in every tested
state — while quantisation accounts for **100.0%** of a gap that is itself large: the exact grid
optimum spends **38.1×** the analytic minimum. At extended range allocation rises only to 5.8–6.2%.
Optimising allocation on `G0_icame` therefore cannot recover a meaningful fraction of the available
power; only changing the grid can.

**On the fine grid the two causes are comparable, and allocation dominates at range.** Allocation is
50.3% of the gap at ×1.0 and 60.6–62.9% at ×2.0. The residual quantisation share (37.1–49.7%) is
what remains of a ~5 dB grid step after the floor is removed.

**The grid never restricted feasibility.** In all 15,882 states, across both grids and all four
regimes, there was no demand that continuous power could serve and the discrete grid could not
(C4: 0.00% in every cell). The grid's cost is entirely in the power spent, not in packets lost.

**Caution on C3.** The per-slot ratio `H_G / C` has a very heavy right tail on `G0_icame`
(max 1.15 × 10⁶ at R2) because `C` can be arbitrarily small when a well-placed device needs
microwatts while the grid charges 0.05 W. The median (11.9–76.9×) is the meaningful summary there;
the mean is not. On `G2_wide10` the distribution is well behaved (median 2.5–2.9×, p95 5.5–6.1×).

## 5. Limits

Development seeds only. Continuous power is a mathematical device: it is not claimed to be
implementable, and no result in this project should be reported as an achievable power saving on
that basis. The reference shares every other assumption of the model — deterministic success,
no interference, codebook-restricted beams, the same caps — so it bounds only the quantisation
effect, not the modelling error. Nothing here is final-test evidence and nothing has been written
into the manuscript.
