# Configuration Schema (aligned to the central model)

All experiments are driven by YAML configs validated against this schema. Aligned to
`../06_mathematical_model/model_decisions.yaml`. Unknown keys rejected; ranges enforced.

**Primary locked numeric defaults (r34)** — the committed values live in
`primary_experiment_config.json` and are mirrored by
`../06_mathematical_model/primary_design_parameter_register.md`:
`slot_duration_s=1e-3` (τ=1 ms), `subchannel_bw_hz=1e6` (W=1 MHz, N=8 ⇒ 8 MHz total),
`receiver_noise_figure_db=7`, `noise_temperature_k=290`, `shannon_threshold_bps_hz=1`,
channel InF-SH hall 300 m×150 m, `fc=3.5e9`, `rician_k_db=7`, `csi_delay_slots=1`,
arrival process **Bernoulli**, `load_grid=[0.05,0.10,0.20,0.30,0.40]` (ref 0.20 ⇒
Ā_static=1.20, Ā_mobile=0.40), `p_max_w=0.4`, `per_device_total_power_w=0.8`,
average-power budget P̄=1.6 W (=0.5·N·P_max), `measurement_slots=100`, `rollout_episodes=32`,
`n_seeds≥10`.

## Topology / devices
| Key | Type | Range | Notes |
|---|---|---|---|
| `seed` | int | ≥0 | master seed (independent unit) |
| `n_static`,`n_mobile` | int | ≥0 | $K_s,K_m$ |
| `n_subchannels` | int | ≥1 | $N$ — **preregistered primary $N_{\text{primary}} = 8$** (topology design parameter, fixed for the primary study; a configuration choice, NOT a result; `../06_mathematical_model/joint_autoregressive_ppo_objective.md` §7a rule 8) |
| `subchannel_bw_hz` | float | >0 | $W$ — **primary 1e6 (1 MHz)** |
| `slot_duration_s` | float | >0 | $\tau$ — **primary 1e-3 (1 ms)** |

## Receive array / beam (DFT/ULA — replaces old main/side-lobe mask)
| Key | Type | Range | Notes |
|---|---|---|---|
| `array_type` | enum | {ULA} | locked ULA |
| `n_antennas` | int | ≥1 | $M$ |
| `codebook_type` | enum | {DFT} | finite unit-norm DFT receive codebook |
| `codebook_size` | int | ≥1 | $B$ |
| `csi_mode` | enum | {perfect, delayed, noisy} | **CLOSED — primary = `delayed`** (stale CSI); perfect makes beam a trivial argmax and is the ORACLE baseline only (`../06_mathematical_model/beam_csi_decision.md`) |
| `csi_delay_slots` | int | ≥0 | $d_{\text{CSI}}$ — **primary 1** (sens {0,1,2,3}) |
| `rician_k_db` | float | — | $K_R$ — **primary 7 dB** (sens {3,7,13}) when `fading=rician` |
> Old `beamwidth_deg` / `gain_main` / `gain_side` mask fields are **removed**; beam gain
> is $G_{k,n,b}=M\,|w_b^H a(\phi)|^2\in[0,M]$ from the DFT codebook + ULA response.

## Channel / physical layer
| Key | Type | Range | Notes |
|---|---|---|---|
| `pathloss_exponent` | float | [2,6] | α (cite source) |
| `shadow_std_db` | float | ≥0 | $\sigma_\chi$ |
| `fading` | enum | {rayleigh,rician} | +`rician_k` |
| `noise_spectral_density_dbm_hz` | float | — | $N_0$ (or `noise_temperature_k`) |
| `receiver_noise_figure_db` | float | ≥0 | $NF$; $\sigma^2=N_0 W 10^{NF/10}$ |

## Power / spectrum / assignment
| Key | Type | Range | Notes |
|---|---|---|---|
| `p_max_w` | float | >0 | $P_{\max}$ per (k,n) |
| `power_levels` | int | ≥1 | discretized power set |
| `per_device_total_power_w` | float | >0 | $P^{\text{tot}}_k$ cap |
| `per_user_subchannel_cap` | int | [1,N] | $N^{\max}_k$ |

## Traffic / queue / deadlines
| Key | Type | Range | Notes |
|---|---|---|---|
| `packet_bits` | int | ≥1 | $Z$ |
| `queue_capacity` | int | ≥1 | $Q_{\max}$ |
| `max_retx` | int | ≥0 | retx after initial attempt (0 ⇒ 1 attempt) |
| `deadline_static`,`deadline_mobile` | int | ≥1 | $D$; `deadline_slot=arrival+D-1` |
| `hard_deadline` | bool | true | no delivery after deadline |
| `arrival_process` | enum | {bernoulli} | **LOCKED = bernoulli** (per-device per-slot; r34) |
| `arrival_rate_static`,`arrival_rate_mobile` | float | ≥0 | base loads |
| `load_grid` | list[float] | (0,1], sorted | Bernoulli per-device arrival-prob sweep — **primary `[0.05,0.10,0.20,0.30,0.40]`** (ref 0.20) |
| `v_max_mps` | float | ≥0 | mobile speed cap |

## Cohort / drain / evaluation
| Key | Type | Range | Notes |
|---|---|---|---|
| `warmup_slots` | int | ≥0 | discarded |
| `measurement_slots` | int | ≥1 | $T_{\text{meas}}$ — cohort generation window AND the **FIXED power-constraint measurement window** $\mathcal W=\{1..T_{\text{meas}}\}$ (identical for all methods/seeds); the average-power constraint $C_{\text{pow}}=\sum_{t\in\mathcal W}(P_t-\bar P)$ sums over exactly these slots, **excluding** full-drain tail slots (r28 §6; `../06_mathematical_model/bsa_lppo_specification.md` §4) |
| `drain_mode` | enum | {full, bounded} | **full = primary evaluation** |
| `max_drain_slots` | int | ≥0 | bounded-drain horizon (diagnostics only) |
| `n_seeds` | int | ≥1 (target ≥10) | full-experiment seeds |
| `rollout_episodes` | int | ≥1 | $N_{\text{ep}}$ — **primary 32 (r34 LOCKED)**; dual-update batch size, NOT beam-codebook $B$ |
| `train_steps`,`eval_episodes` | int | ≥1 | separated |

## RL / reward / constraints
| Key | Type | Range | Notes |
|---|---|---|---|
| `action_credit_formulation` | enum | {slot_joint_autoregressive, pending} | **SELECTED = slot_joint_autoregressive** (SLOT-LEVEL JOINT-AUTOREGRESSIVE PPO ACTION FORMULATION; `../06_mathematical_model/macro_aware_return_equations.md`); the policy is a JOINT AUTOREGRESSIVE length-N token sequence, NOT a bare `Discrete(1+K*B*P)` |
| `policy_action_representation` | enum | {joint_autoregressive_tokens} | length-N conditional token sequence; token alphabet `Discrete(1+K*B*P)`; conditional masks; summed joint log-prob; one PPO ratio per slot; joint entropy/KL; custom rollout or one-macro-step env |
| `n_subchannels_fixed` | bool | {true} | **LOCKED true** — the PPO objective uses a **fixed $N$**; not compared across $N$ without recalibration (`../06_mathematical_model/joint_autoregressive_ppo_objective.md` §7a) |
| `entropy_scope` | enum | {slot_sum} | **slot_sum** — entropy = sum of $N$ per-token conditional entropies; $c_e$ is a per-slot weight (NOT per-token mean) |
| `kl_scope` | enum | {slot_sum} | **slot_sum** — approximate KL and `target_kl` are the slot-level summed-joint-log-prob difference (NOT per-token normalised) |
| `clip_range_scope` | enum | {per_slot} | **per_slot** — one PPO ratio and clip $\varepsilon$ per slot; $\varepsilon$ NOT scaled by $N$ |
| `log_ratio_clip` | list[float]×2 | e.g. [-20,20] | numerical clip of the **summed** slot log-ratio before exponentiation (overflow guard only; not a per-token discount) |
| `clip_fraction_warn` | float | [0,1] | default **0.30** — flag instability if the fraction of slot ratios clipped exceeds this |
| `log_ratio_guard_warn` | float | [0,1] | default **0.001** — the summed-log-ratio overflow guard should be negligibly active; if the guard-hit fraction exceeds this, flag the update **UNSTABLE** (guarded samples not treated as normal PPO samples; `../06_mathematical_model/joint_autoregressive_ppo_objective.md` §7a rule 5) |
| `deterministic_token_entropy_kl` | enum | {excluded} | **excluded** — a one-feasible-option masked token (log-prob 0, entropy 0) is excluded from the entropy/KL sums |
| `n_scaling_preregistered_metrics` | list | slot_kl, kl_per_n, entropy, entropy_per_n, clip_fraction, summed_logratio_dist | reported **only** if a scaling study varies $N$ (§7a rule 8) |
| `reward_weights` | list[float]×**6** | ≥0 | $w_1..w_6$ (delivered, deadline-viol, overflow, HOL-age, energy, utilization) |
| `constraint_bounds` | map | ≥0 | per-class ratio budgets $\rho_c,\epsilon_c,\eta_c$ + **average-power budget $\bar P$ (watts)** — the SELECTED single energy/power constraint is $C_{\text{pow}}=\sum_t(P_t-\bar P)\le 0$; the energy budget is the derived transform $\bar E_{\text{slot}}=\bar P\tau$ (r27 §6; `../06_mathematical_model/energy_model.md`) |
| `constraint_mechanism` | enum | {pending, penalty, lagrangian, cpo} | **SELECTED = lagrangian** (`SELECTED_LAGRANGIAN_PPO`; primary BSA-LPPO, baseline `penalty`, Base-PPO reference; `../06_mathematical_model/bsa_lppo_specification.md`); **implementation MET (r35/r36)**; final method name BSA-C-PPO |
| `collapse_rule` | enum | {A_level} | reliability-feasibility level rule (B_maxdrop removed as primary; may appear only as a secondary diagnostic) |
| `collapse_rho` | float | [0,1] | per-class reliability floor |

## Validation
`validate_config()` checks types/ranges and cross-field constraints
(`per_device_total_power_w ≥ p_max_w`; `n_static+n_mobile≥1`; `load_grid` sorted;
`reward_weights` length 6; `array_type=ULA`, `codebook_type=DFT`;
`drain_mode=full` for primary results). Invalid configs abort before computation.
