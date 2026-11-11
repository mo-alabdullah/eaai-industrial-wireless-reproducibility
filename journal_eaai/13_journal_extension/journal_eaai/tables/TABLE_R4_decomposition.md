# TABLE R4 — Three-term power-gap decomposition

**Evidence class: DESCRIPTIVE / STRUCTURAL.** The identity is analytic, so no p-value is attached
and none is reported. Grids are reported SEPARATELY and are not nested refinement levels: the
nominal grid contains levels absent from the wide sensitivity grid, so no monotone improvement of
one over the other is claimed. Unit of analysis: the 100 execution units per cell (20 seeds x 5
warm-up offsets). Source: `results_final/analysis/descriptive/DESCRIPTIVE_SUMMARIES.json` key
`decomposition_Q1` (digest c67599938d3d9efb), derived from the frozen `ContinuousPowerRef` rows
(endpoint Q1).

Identity: H_G − C = (H_G − E_G) + (E_G − C_AG) + (C_AG − C) = allocation + pure quantisation +
quantisation-induced assignment distortion. All quantities in watts.

| regime | grid | total gap H_G − C | allocation (H_G − E_G) | pure quantisation (E_G − C_AG) | distortion (C_AG − C) | alloc. share | quant. share | dist. share | median H_G/C | IQR H_G/C | units |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1_nominal | G0_icame | 0.466622 (sd 0.093909) | 0.003500 | 0.453916 | 0.009206 | 0.75 % | **97.28 %** | 1.97 % | 47.02 | [27.40, 76.79] | 100 |
| R1_nominal | G2_wide10 | 0.039722 (sd 0.084488) | 0.025810 | 0.011112 | 0.002799 | **64.98 %** | 27.98 % | 7.05 % | 2.80 | [2.33, 3.47] | 100 |
| R3_aged | G0_icame | 0.463499 (sd 0.108053) | 0.029500 | 0.407492 | 0.026507 | 6.36 % | **87.92 %** | 5.72 % | 7.44 | [5.32, 13.78] | 100 |
| **R3_aged** | **G2_wide10** | **0.169885** (sd 0.164706) | **0.102710** | **0.058130** | **0.009045** | **60.46 %** | 34.22 % | 5.32 % | 2.73 | [2.04, 3.49] | 100 |

Per-term medians and maxima, primary cell (R3_aged x G2_wide10): allocation median 0.048827, max
0.613892, exactly zero in 2 % of units; pure quantisation median 0.039182, max 0.420351, never
exactly zero; distortion median 0.005176, max 0.082738, exactly zero in 6 % of units.

**Computational cross-check.** The allocation term is, by definition, the fixed-demand gap of
endpoint E1. Its mean in the primary cell, 0.102710 W, reproduces the locked E1 estimate
(|−0.10271015387| W) and its extreme value (0.613892 W) reproduces the magnitude of the most
negative E1 value (−0.613892 W under the frozen exact-minus-heuristic sign convention), computed by
two independent paths through the pipeline.

**Notes.** The ratio H_G/C is summarised by median and interquartile range, never by a mean, because
the distribution has a heavy right tail. Every term is non-negative under the conditions stated in
the exact-framework section. The continuous construction is a MATHEMATICAL LOWER REFERENCE BOUND
presuming arbitrarily fine transmit-power control that this work does not establish; it is never an
achievable saving. Zero states were excluded: `grid_infeasible` and `cont_infeasible` are zero in
all four cells. G2_wide10 is a numerical sensitivity instrument and carries no hardware, realism or
deployment interpretation. The telescoping identity itself is elementary; what is reported here is
its measured decomposition in this model.
