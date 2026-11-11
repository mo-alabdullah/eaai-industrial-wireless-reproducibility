> **SUPERSEDED (2026-07-27).** This early sketch (different subchannels, random
> fading, horizon, retransmission/deadline settings) is replaced by the single
> canonical M1 fixture: `reference_case_inputs.csv`,
> `reference_case_expected_transitions.csv`, `reference_case_expected_metrics.json`,
> `reference_case_hand_calculation.md`, verified by `reference_case_independent_check.py`
> + `test_reference_case_design.py`. Do not use the values below.

# Deterministic Reference Case (SUPERSEDED)

A tiny, fully specified scenario whose outputs can be computed/checked by hand and
used as a regression fixture. Must be green before large runs.

## Configuration
- `seed = 0`; `n_static = 1`, `n_mobile = 1`; `n_subchannels = 1`;
  `codebook_size = 1` (single beam); `power_levels = 1` (fixed power);
  strict exclusivity; `fading = rayleigh` with a fixed seeded draw;
  `queue_capacity = 4`; `max_retx = 1`; `deadline_static = 8`,
  `deadline_mobile = 2`; small fixed arrival pattern; short horizon (e.g., 20 slots).

## Expected checks (computed independently, not from the model under test)
1. With one subchannel and two devices, at most one device is served per slot →
   scheduling exclusivity holds every slot.
2. Given the fixed arrival pattern and service outcomes, the queue trajectory
   $q_k(t)$ matches a hand-computed reference sequence.
3. `delivered + dropped = generated` at horizon end for each device (measurement
   cohort residual = 0 after drain).
4. Any mobile packet older than `deadline_mobile = 2` is dropped as a deadline
   violation (never delivered late).
5. PDR, drop ratio, deadline-violation probability, **link outage**
   `P_out = Pr(SINR < gamma_th)`, and success probability each lie in $[0,1]$.
   **Link outage is computed independently and is NOT `1 − PDR`** (see
   `../06_mathematical_model/reliability_model.md`).
6. Re-running with `seed = 0` reproduces identical numbers (bit-for-bit on metrics);
   the training seed is the independent unit.

## Usage
Implemented as `tests/test_reference_case.py`. Serves as: (a) the model-validation
gate's numeric check, and (b) a permanent regression guard. Expected reference
sequences are stored as a fixture file with provenance (how they were derived).

## Status
**Pending implementation** — created when Phase J coding begins, after the
model-validation gate provenance items are closed.
