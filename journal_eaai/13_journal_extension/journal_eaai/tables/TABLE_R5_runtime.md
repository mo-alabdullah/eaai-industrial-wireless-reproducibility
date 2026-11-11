# TABLE R5 — Computational cost

**Evidence class: DESCRIPTIVE.** Single-process, timed around the solve call only. Two tiers appear
and are never mixed in one row: FINAL (the confirmatory campaign, 400 units per comparator) and
DEVELOPMENT (the pre-registration per-solve latency benchmark, `EXACT_SOLVER_LATENCY.md`). Sources:
FINAL rows from `DESCRIPTIVE_SUMMARIES.json` key `runtime_Q5` (digest c67599938d3d9efb);
DEVELOPMENT rows from `EXACT_SOLVER_LATENCY.md`.

| tier | solver / reference | n solves | mean µs | median µs | p95 µs | p99 µs | max µs | censored | fraction < 1 ms |
|---|---|---|---|---|---|---|---|---|---|
| FINAL | fixed-demand exact radio + continuous reference (one shared timed region) | 400 | 394.6 | 398.0 | 511.8 | 556.0 | 583.6 | 0 | 100 % |
| FINAL | causal EDF + exact fixed-demand radio (per unit) | 400 | 256.3 | 252.9 | 359.8 | 393.6 | 439.7 | 0 | 100 % |
| FINAL | EDF-StaleBeam-MinFeasible heuristic (per unit) | 400 | 135.2 | 125.8 | 220.7 | 255.0 | 290.6 | 0 | 100 % |
| FINAL | offline finite-horizon reference, aged gain (K8 N4 H3) | 400 | 5 066 538 | 859 001 | 19 770 442 | 59 554 051 | 332 472 146 | 0 | 0 % |
| FINAL | offline finite-horizon reference, current gain (K8 N4 H3) | 400 | 5 051 646 | 855 320 | 19 365 273 | 60 231 336 | 326 979 470 | 0 | 0 % |
| DEVELOPMENT | fixed-demand exact radio, per solve | 7 661 | 37 | 39 | 50 | 54 | 66 | 0 | 100 % |
| DEVELOPMENT | free-selection exact radio, per solve ((K+1)^N enumeration) | 7 704 | 855 | 571 | 2 609 | 4 641 | 8 184 | 0 | 69.09 % |

Finite-horizon search effort, FINAL: mean 397 046 nodes, maximum 23 786 376 nodes against a
declared budget of 200 000 000; mean 261.2 states, maximum 5 568; `skipped_entries` zero in every
unit.

**Notes.** No solve was censored: no unit exhausted the declared node budget (max 23.8 M of 200 M)
or the 600 s time budget (max 332.5 s), `skipped_entries` is zero throughout, and the
`budget_exceeded_flag` column was never written in the final campaign — censoring is therefore
evidenced by the node, time and skip counters rather than by that flag. No censored solve is
replaced by a heuristic value anywhere.

**Three cautions.** (i) In the final campaign the fixed-demand exact solver and the continuous
reference share a single timed region, so their timings are one measurement reported once, not two
independent measurements; the per-solve cost of the fixed-demand solver alone is the DEVELOPMENT row
(median 39 µs). (ii) The FINAL rows aggregate all solve activity within one execution unit over the
horizon, which is why they exceed the DEVELOPMENT per-solve figures; the two tiers answer different
questions and must not be compared across rows. (iii) The free-selection exact solver does NOT meet
a 1 ms budget consistently — it was sub-millisecond in 69.09 % of development solves — so no
"real-time at 1 ms" claim is made for all exact variants. No real-time claim is drawn from a mean
latency, and no portability claim is made to other hardware, to compiled implementations, or to
larger device or subchannel counts.
