# TABLE R2 — E1 fixed-demand radio power gap

**Evidence class: ESTIMATION (primary cell) / DESCRIPTIVE (other cells).** No hypothesis test and
no p-value: the sign is fixed by solver construction. Transmission demand is held identical on both
sides, so the quantity is attributable to subchannel placement, beam and power selection alone.
Frozen sign convention: exact fixed-demand reference MINUS heuristic (negative = heuristic spends
more). Unit of analysis for the interval: the seed (n = 20); the distributional columns are over the
100 execution units per cell (20 seeds x 5 warm-up offsets).

Sources: primary row from `endpoints.json` key `E1` (locked); all other cells from
`results_final/analysis/descriptive/DESCRIPTIVE_SUMMARIES.json` key `power_gap_E1_descriptive`
(digest c67599938d3d9efb).

| regime | grid | class | mean gap (W) | sd | median | min | max | exactly zero | 95% BCa CI (W) | heuristic mean power (W) | exact mean power (W) | units | infeasible |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **R3_aged** | **G2_wide10** | ESTIMATION | **−0.10271** | 0.07208 | −0.04883 | −0.61389 | 0.00000 | 2 % | **[−0.13657, −0.07498]** | 0.264536 | 0.161826 | 100 | 0 |
| R3_aged | G0_icame | DESCRIPTIVE | −0.02950 | 0.04236 | 0.00000 | −0.40000 | 0.00000 | 7 % | not computed | 0.563500 | 0.534000 | 100 | 0 |
| R1_nominal | G2_wide10 | DESCRIPTIVE | −0.02581 | 0.05674 | −0.00911 | −0.60622 | 0.00000 | 2 % | not computed | 0.055143 | 0.029333 | 100 | 0 |
| R1_nominal | G0_icame | DESCRIPTIVE | −0.00350 | 0.01349 | 0.00000 | −0.10000 | 0.00000 | 6 % | not computed | 0.482500 | 0.479000 | 100 | 0 |

All 20 paired seed-level differences in the primary cell have the same sign (20 negative, 0
positive, 0 ties); Cohen's d_z = −1.425. For reader-facing prose the verbal direction may be
reversed while the numeric definition above is preserved: the heuristic consumed 0.10271 W more
aggregate power than the exact fixed-demand reference, 95 % BCa CI [0.07498, 0.13657] W.

**Notes.** "not computed" means a bias-corrected bootstrap interval was deliberately NOT formed for
the secondary cells: they lie outside the frozen endpoint plan, and no interval was added after the
fact. No state was excluded: `grid_infeasible_flag` and `cont_infeasible_flag` are zero in all four
cells, so no state is imputed and none is dropped. This is not a comparison involving any learned
controller.
