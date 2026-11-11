# TABLE R3 — E2 aged versus current beam-gain reference

**Evidence class: ESTIMATION.** No hypothesis test and no p-value: the sign is determined by
construction within this reference problem. Estimand: the effect of beam-gain-information
FRESHNESS within one common offline exact finite-horizon formulation. Cell: R3_aged x G2_wide10,
n = 20. Frozen sign convention: current-beam-gain reference MINUS aged-beam-gain reference.
Sources: delivery row from `endpoints.json` key `E2` (locked); power row and believed-delivery
column from the frozen raw outputs.

| quantity | aged-gain reference | current-gain reference | paired difference | 95% BCa CI | Cohen d_z | + | − | ties | n |
|---|---|---|---|---|---|---|---|---|---|
| realised delivery | 9.03 | 10.61 | **1.58** | **[1.28, 1.84]** | **2.412** | 20 | 0 | 0 | 20 |
| aggregate power (W) | 0.109439 | 0.112965 | 0.003526 (sd 0.012396) | not computed | — | 11 | 8 | 1 | 20 |
| believed delivery (planning value) | 10.61 | 10.61 | 0.00 | — | — | — | — | — | 20 |

**Computational cross-check (arithmetic identity, not a new result).** The two references differ in
exactly one input on an identical recorded trace. Seed by seed, the aged reference's *believed*
delivery equals the current reference's *realised* delivery, and its realised delivery is never
above its believed delivery in any of the 400 execution units. E2 therefore equals, seed by seed,
the aged reference's believed-minus-realised shortfall (mean 1.58 in both forms). This equality is
reported as an observed consistency property of the frozen outputs; no mechanism is attributed to it
here.

**Notes.** This is NOT "the value of CSI": the large-scale gain beta_k(t) is current on both sides
and only the beam/effective gain is delayed. It is not a causal benefit of channel information in
general, and it is not a deployable online improvement — both sides receive the complete future
trace and neither is a controller.
