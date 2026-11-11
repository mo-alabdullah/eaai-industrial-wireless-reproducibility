# EXACT_SOLVER_LATENCY — Stage I-CLOSEOUT task 2

**Status: internal development measurement.** Development states only; FINAL TEST seeds not opened.
No real-time feasibility claim is made beyond what the measured distribution supports.

Source: `results/solver_latency.csv` (**7,704 timed solves**), produced by `code/run_latency.py`,
tables by `code/optimization/analyse_latency.py`. Environment record:
`results/solver_latency_env.json`.

## Method

- **Single process, one worker.** The Stage-I campaigns ran four workers on four cores, so their
  timings include scheduling contention and are *not* latency measurements. Everything below is
  measured with a single process.
- `time.perf_counter` brackets the solve call only. State capture (`freeze`), environment stepping,
  metric bookkeeping and I/O are excluded.
- States are those actually visited by the deployable reference policy
  `EDF-StaleBeam-MinFeasible`: 4 regimes × 2 grids × 8 seeds × 120 slots.
- Two solvers are timed separately because they solve different problems:
  - `solve_exact_radio` — **free selection**, enumerates `(K+1)^N` device-to-subchannel assignments;
  - `solve_exact_radio_fixed_demand` — **fixed demand**, enumerates assignments of the already-chosen
    demand multiset to subchannels (the pure radio-allocation subproblem of I-A).
- No warm-up discarding, no trimming, no outlier removal. Reported percentiles are over all solves.

## Environment

| item | value |
|---|---|
| platform | Linux 6.8.0-136-generic, glibc 2.35 |
| architecture | aarch64 |
| logical CPUs | 4 |
| memory | 4,000,488 kB (≈3.8 GiB) |
| Python | CPython 3.10.12 |
| NumPy | 2.2.6 |
| BLAS | not used in the solve path (pure Python control flow + NumPy element indexing only) |
| concurrency during measurement | single process, single thread |

The solve path performs no matrix algebra: it is Python-level enumeration over tuples with NumPy
used only for `argmax` over a length-`B` gain vector. Latency is therefore interpreter-bound and
would change substantially under a compiled implementation. **No claim is made that these figures
represent an optimised or production implementation.**

## Results

## Free-selection exact radio solve  (`solve_exact_radio`, (K+1)^N enumeration)

### By power grid

| group | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|---|---|---|
| G0_icame | 3,847 | 717 | 556 | 1398 | 2421 | 4309 | 7,322 | 73.67% |
| G2_wide10 | 3,857 | 993 | 586 | 2469 | 3051 | 6791 | 8,184 | 64.53% |

### By regime (both grids pooled)

| group | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|---|---|---|
| nominal ×1.0 (age 1) | 1,924 | 770 | 574 | 2265 | 2536 | 4476 | 7,349 | 72.45% |
| moderate ×1.5 (age 3) | 1,927 | 885 | 571 | 2338 | 2654 | 4611 | 7,410 | 67.72% |
| extended ×2.0 (age 1) | 1,924 | 782 | 564 | 2275 | 2469 | 4386 | 7,030 | 70.84% |
| extended ×2.0 (age 5) | 1,929 | 983 | 576 | 2460 | 3988 | 7040 | 8,184 | 65.37% |

### By grid × regime

| grid | regime | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|---|---|---|---|
| G0_icame | nominal ×1.0 (age 1) | 961 | 715 | 328 | 1403 | 2491 | 4440 | 7,322 | 75.13% |
| G0_icame | moderate ×1.5 (age 3) | 962 | 692 | 554 | 1352 | 2352 | 4110 | 6,830 | 73.70% |
| G0_icame | extended ×2.0 (age 1) | 961 | 698 | 554 | 1367 | 2374 | 4161 | 7,019 | 73.99% |
| G0_icame | extended ×2.0 (age 5) | 963 | 764 | 558 | 2242 | 2430 | 4389 | 7,258 | 71.86% |
| G2_wide10 | nominal ×1.0 (age 1) | 963 | 825 | 575 | 2291 | 2572 | 4567 | 7,349 | 69.78% |
| G2_wide10 | moderate ×1.5 (age 3) | 965 | 1077 | 593 | 2554 | 4115 | 6962 | 7,410 | 61.76% |
| G2_wide10 | extended ×2.0 (age 1) | 963 | 867 | 583 | 2325 | 2584 | 4498 | 7,030 | 67.71% |
| G2_wide10 | extended ×2.0 (age 5) | 966 | 1201 | 622 | 2715 | 4296 | 7334 | 8,184 | 58.90% |

## Fixed-demand exact radio solve  (`solve_exact_radio_fixed_demand`, permutation enumeration)

### By power grid

| group | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|---|---|---|
| G0_icame | 3,820 | 34 | 37 | 43 | 45 | 50 | 58 | 100.00% |
| G2_wide10 | 3,841 | 39 | 41 | 49 | 51 | 56 | 66 | 100.00% |

### By regime

| group | n | mean µs | median µs | p90 µs | p95 µs | p99 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|---|---|---|
| nominal ×1.0 (age 1) | 1,910 | 36 | 38 | 47 | 49 | 54 | 59 | 100.00% |
| moderate ×1.5 (age 3) | 1,917 | 36 | 39 | 48 | 49 | 54 | 65 | 100.00% |
| extended ×2.0 (age 1) | 1,913 | 37 | 39 | 48 | 50 | 53 | 65 | 100.00% |
| extended ×2.0 (age 5) | 1,921 | 37 | 40 | 49 | 51 | 56 | 66 | 100.00% |

## Overall

- **free selection**: n = 7,704; mean 855 µs, median 571 µs, p90 2317 µs, p95 2609 µs, p99 4641 µs, max 8,184 µs; **69.09% below 1 ms**.
- **fixed demand**: n = 7,661; mean 37 µs, median 39 µs, p90 48 µs, p95 50 µs, p99 54 µs, max 66 µs; **100.00% below 1 ms**.

### Latency vs number of simultaneously eligible devices (free selection)

| eligible devices | n | median µs | p95 µs | max µs | % < 1 ms |
|---|---|---|---|---|---|
| 0 | 43 | 50 | 63 | 72 | 100.00% |
| 1 | 516 | 65 | 74 | 94 | 100.00% |
| 2 | 1,227 | 114 | 131 | 194 | 100.00% |
| 3 | 1,652 | 257 | 299 | 396 | 100.00% |
| 4 | 1,885 | 590 | 685 | 797 | 100.00% |
| 5 | 1,398 | 1244 | 1424 | 1,699 | 0.00% |
| 6 | 704 | 2422 | 2751 | 3,152 | 0.00% |
| 7 | 227 | 4291 | 4819 | 5,149 | 0.00% |
| 8 | 52 | 7130 | 7814 | 8,184 | 0.00% |

## Interpretation

**The fixed-demand solver meets a 1 ms budget in this environment; the free-selection solver does
not.** Every one of 7,661 fixed-demand solves completed in under 66 µs (100.00% sub-millisecond,
p99 = 54 µs). By contrast the free-selection solver was sub-millisecond in only **69.09%** of solves,
with p95 = 2,609 µs, p99 = 4,641 µs and a maximum of 8,184 µs — that is, it **misses a 1 ms slot
budget roughly three times in ten**, and exceeds it by up to 8×.

The cause is visible in the eligibility breakdown and matches the `(K+1)^N` bound exactly:

| eligible devices | % of solves < 1 ms |
|---|---|
| 0–4 | **100.00%** |
| 5 | 0.00% |
| 6 | 0.00% |
| 7 | 0.00% |
| 8 | 0.00% |

The transition is sharp because the enumeration count is a step function of the number of eligible
devices, not because of system noise: at 4 eligible devices the maximum observed latency is 797 µs
and at 5 the minimum already exceeds 1 ms.

Grid and regime effects are second-order by comparison. `G2_wide10` is slower than `G0_icame`
(mean 993 µs vs 717 µs; 64.53% vs 73.67% sub-millisecond) because more power levels survive the
feasibility mask, and the aged/extended regime R3 is slowest (mean 1,201 µs on `G2_wide10`, 58.90%
sub-millisecond) because more devices are simultaneously eligible when retransmissions accumulate.

## What may and may not be claimed

**May be claimed**, with the environment named:
- The fixed-demand exact radio solve completed in **≤ 66 µs on every one of 7,661 development
  states**, i.e. comfortably inside a 1 ms slot in this environment.
- Free-selection exact solve latency scales as `(K+1)^N` and is sub-millisecond up to 4
  simultaneously eligible devices at K = 8, N = 4.

**May not be claimed**:
- That exact free-selection radio allocation is real-time feasible at 1 ms. It is not, in this
  environment: 30.91% of solves exceed 1 ms.
- That any of these figures transfer to other hardware, to a compiled implementation, or to larger
  `K` or `N`. The measurement is interpreter-bound on one aarch64 container with 4 logical CPUs.
- That latency measured on development states characterises worst-case latency in general. The
  maximum here is the maximum **over the states this policy visited**, not a bound.
