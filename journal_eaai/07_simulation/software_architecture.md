# Software Architecture

## Layered design
```
configs/ (YAML, schema-validated)
   |
env/  IIoTUplinkEnv (Gymnasium)  <- channel, mobility, spectrum, SINR,
   |    packet-success, queues, deadlines, energy (from 06_mathematical_model)
   |
agents/  BasePPO | BeamSpectrumPPO | BSA-*-PPO (provisional) | Random | RoundRobin | MaxSINR | EDF
   |
runner/  seed-controlled training + evaluation (separated)
   |
analysis/  metrics, statistics (means/SD/CI/effect size), algorithmic collapse threshold
   |
figures/ + tables/  raw-data-driven generation scripts
   |
results/  raw artifacts (.npz/.parquet), logs, trained models (preserved)
```

## Environment (`IIoTUplinkEnv`) — action-builder (OMA)
- **Observation:** normalized state incl. the action-builder augmentation
  (`../06_mathematical_model/action_builder_mdp.md`); beam-gain vector / AoA features
  so a beam is choosable (`../06_mathematical_model/antenna_beam_model.md`).
- **Action:** the **internal token alphabet** is **`Discrete(1 + K*B*P)`** (`idle` or
  `(user,beam,power)`) — **not** flat MultiDiscrete. The **actual per-slot policy action** is a
  **length-$N$ joint autoregressive** token sequence (conditional masks, summed joint log-prob,
  one PPO ratio per slot, joint entropy/KL; `../06_mathematical_model/action_builder_mdp.md`) —
  implemented as a custom slot-level rollout **or a one-macro-step env**. $N$ tokens per
  physical slot with **conditional** feasibility masking
  (`action_builder_feasibility_rules.md`); the environment advances **once**
  per slot per the locked event order
  (`../06_mathematical_model/physical_slot_event_order.md`).
- **Slot step (macro):** commit allocation → compute SINR/success (β·G, no intra-cell
  interference) → update packet queues/deadlines/energy → reward + constraint costs
  once → advance mobility/channel.
- **Determinism:** all randomness from a seeded RNG; same seed ⇒ same trajectory.

## Agents
- **Base PPO** (reward only). **Beam/spectrum-aware PPO** (extended actions, partial
  constraints). **BSA-*-PPO (provisional)** — constrained method whose **mechanism is
  UNDECIDED** (BSA-Penalty-PPO / BSA-Lagrangian-PPO / BSA-CPO).
- **Heuristics/baselines:** Random, Round Robin, Max-SINR (channel-aware),
  EDF (deadline-aware), **Max-Gain Beam (mandatory)**.

## Constrained RL (mechanism-neutral)
The constraint-enforcement mechanism is **not yet selected** — it may be reward
penalties, PPO-Lagrangian, or CPO (`../06_mathematical_model/constraint_enforcement_options.md`).
Do **not** assume a penalty/Lagrangian wrapper. Constraint costs (deadline, per-class
reliability, overflow, power) are tracked as ratio-form costs regardless of mechanism.

## Reproducibility hooks
Config hash + seed recorded per run; `pip freeze` captured; figures/tables carry
input-file provenance (`figure-table-reproducibility-guard`).

## Complexity control
The autoregressive factorisation represents the $(1+KBP)^N$ joint slot action with $N$
conditional `Discrete(1+K*B*P)` heads, so per-slot representation/compute is **linear in $N$**,
not exponential (`../06_mathematical_model/sequence_length_scaling_analysis.md`). Capped
device/subchannel counts keep each token's alphabet small. This tractability is for the
**custom joint autoregressive policy** (custom slot-level rollout / one-macro-step env with
summed joint log-prob, one PPO ratio per slot, joint entropy/KL) — **not** for stock
`sb3-contrib` MaskablePPO, which masks a single `Discrete` action per env step and **cannot**
represent this conditional joint policy (only its per-token masked-categorical utility is
reused). See `../06_mathematical_model/joint_optimization_problem.md`,
`../06_mathematical_model/joint_autoregressive_ppo_objective.md`.
