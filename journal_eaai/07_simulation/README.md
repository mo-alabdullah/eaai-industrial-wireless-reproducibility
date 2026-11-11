# 07_simulation — Simulation Architecture (Design; Implementation Gated)

**Status:** Design only. **No experiments are run** until the model-validation gate
(`../06_mathematical_model/model_validation_report.md`) passes and the deterministic
reference case is green.

This folder specifies the software, dependencies, configuration schema, test plan,
and reference case for the Base PPO / baselines / BSA-*-PPO (provisional) simulation.

## Library decision (verified 2026-07-25)
- **Stable-Baselines3 2.9.0** (released 2026-06-15) — PPO supports **`Discrete`**
  action spaces and integrates **Gymnasium v1.0**. **Important:** `Discrete(1 + K*B*P)` is only
  the **per-subchannel decoder-token alphabet**. The **actual per-slot policy action is a
  length-$N$ JOINT AUTOREGRESSIVE sequence** (SLOT-LEVEL JOINT-AUTOREGRESSIVE PPO ACTION
  FORMULATION; `../06_mathematical_model/action_builder_mdp.md`,
  `macro_aware_return_equations.md`) — it is **not** a bare `Discrete` action. **Stock
  `sb3-contrib` MaskablePPO does NOT implement this joint autoregressive distribution** (it
  masks a single `Discrete` head); a **custom autoregressive policy** (joint log-prob/entropy/KL,
  one PPO ratio per slot) or a one-macro-step env is required — a **Gate-M2 implementation
  task**, not assumed to work on stock PPO.
  - **Gate-M2 tasks:** implement the joint autoregressive policy and **run the order-bias
    ablation** (`../06_mathematical_model/action_order_ablation_plan.md`); no permutation
    invariance is claimed.
- **Constrained RL (mechanism-neutral):** the constraint mechanism is **not selected**
  (BSA-Penalty-PPO / BSA-Lagrangian-PPO / BSA-CPO — `../06_mathematical_model/constraint_enforcement_options.md`).
  The **choice is a Gate-M1 mathematical comparison and selection on paper** (cost-value
  requirements, dual update, feasibility reporting, complexity, and compatibility with the
  joint autoregressive policy), currently **PENDING** — it is **not** deferred to a Gate-M2
  spike (that would be circular: M2 must not decide something M1 requires). Gate M2 only
  **implements** the M1-selected mechanism.
- **Policy is a joint autoregressive distribution, not stock MaskablePPO.** Categorical
  masking **utilities** (masked-logit / masked-categorical helpers) may be reused per token,
  but stock `sb3-contrib` MaskablePPO — which masks a single `Discrete` action per env step —
  **cannot** represent the length-N conditional joint policy and is **not** the algorithm.
- Versions to confirm at install time (see `requirements.txt`).

## Components
- `env/`: Gymnasium environment implementing the CMDP (channel, mobility, queues,
  SINR, packet success, energy).
- `agents/`: Base PPO, beam/spectrum-aware PPO, BSA-*-PPO (provisional), and heuristic baselines
  (Random, Round Robin, Max-SINR, EDF).
- `analysis/`: metrics, statistics, algorithmic collapse threshold.
- `figures/`, `tables/`: generation scripts (raw-data-driven only).
- `configs/`: validated against `config_schema.md`.

## Gates before large runs
1. Model-validation gate PASS.
2. Validity tests PASS (`test_plan.md`).
3. Deterministic reference case reproduces expected outputs.
