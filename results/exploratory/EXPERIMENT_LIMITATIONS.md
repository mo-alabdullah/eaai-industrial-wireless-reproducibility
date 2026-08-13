# confirmatory Experiment Limitations (honest disclosure)

These limitations are recorded verbatim so the paper-writing step reports them faithfully. No data
or model parameter was altered to improve any method's apparent performance; the accepted DOCX is
byte-identical.

## 1. Preregistered computationally-bounded scenario
The multi-seed × multi-load × all-method campaign runs a **reduced congestion topology**
(8 static + 3 mobile devices over 4 subchannels, 4-beam DFT codebook, 4 power levels,
T_meas = 50 slots) so the full design is tractable in **pure numpy on CPU (no GPU/torch)**. The
full locked primary scenario (K=8 static+2 mobile-class per the register, B=8, P=4, N=8) is
**validated executable** by `test_m2` but is not trained at scale in this environment. All locked
PHYSICS (τ=1 ms, W=1 MHz, NF=7 dB, InF-SH large-scale model, packet-bits success thresholds
2.048 / 0.512 bit/s/Hz, P̄=1.6 W, d_CSI=1, delivery floors, frozen cost scales) are unchanged.

## 2. Bounded PPO training budget → under-trained learned policies
The learned methods use a **preregistered bounded budget** (`n_ep_train=3`, `n_updates=5`,
hidden=20). Under this budget:
- the learned beam-selection accuracy is ≈ random (≈0.18–0.22 vs a 1/B chance level of 0.25) — the
  policies do **not** learn effective beam prediction in the allotted updates;
- the learned schedulers **do not outperform** the strong deadline-aware heuristics (EDF,
  Stale-Max-Gain, Max-SINR oracle), which reach the best mobile reliability;
- **Layer-1 Fixed-Radio Base PPO does not beat Fixed-Radio Random** (accepted-abstract
  hypothesis #1 is **NOT supported** here) — a direct consequence of under-training.

This is a **compute-bounded outcome**, not a claim about the methods' asymptotic behaviour. A
full-scale training budget (GPU, more updates) is required to characterise the learned policies and
is deferred to the subsequent stage.

## 3. Constraint mechanism binds weakly under the bounded budget
The BSA-C-PPO dual variable responds to violated constraints (the pilot and the multiplier
trajectories confirm `λ` grows on the mobile reliability/deadline channels), but under the frozen
cost scales `s_c = 1/(Ā_c^ref · T_meas)` (≈0.033 for the mobile class) the multiplier magnitudes
reached in `n_updates` updates (`λ ≈ 0.02–0.12`) give an effective cost weight `λ·s_c ≈ 10⁻³`,
which is **too small to reshape the greedy-evaluated policy** relative to the reward advantage.
Consequently **BSA-Unconstrained-PPO, BSA-Penalty-PPO and BSA-C-PPO are not differentiated** at
this budget (their greedy-evaluation metrics coincide). The constraint **mechanism is implemented
and runs correctly** (verified by `test_m2` and the multiplier trajectories); its **effect on the
policy is not yet observable** at this budget. Differentiating the constraint variants requires
either a larger training budget or a preregistered increase of `η_λ` (sensitivity {1e-3,1e-2,1e-1})
— deferred, not silently applied, to avoid result-shaping.

## 4. What IS scientifically established here
- The repaired M2 environment is **behaviourally correct**: same-slot arrivals visible to the
  action; the env is the final feasibility authority (invalid actions raise); packet success uses
  W·τ·log2(1+SINR) ≥ packet-bits; full-drain episodes terminate with **zero residual cohort
  packets**; C_pow is measurement-window-only; frozen cost scales are identical across all loads.
- **Congestion is real and load/class-dependent**: mobile (deadline 2) reliability degrades before
  static (deadline 10); the collapse of BSA-C-PPO constraint feasibility occurs at **p ≈ 0.30**.
- The deadline-aware heuristics are **strong, honest baselines** that the learned methods must beat
  at full scale to substantiate the paper's contribution.
