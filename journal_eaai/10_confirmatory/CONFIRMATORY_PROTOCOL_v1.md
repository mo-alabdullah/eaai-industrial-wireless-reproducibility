# CONFIRMATORY_PROTOCOL_v1 (r36) — frozen BEFORE any confirmatory seed

This protocol is the **preregistered confirmatory design**, frozen before inspecting any
confirmatory (test) seed. r35 is reclassified as **EXPLORATORY / PILOT / PROTOCOL-DEVELOPMENT**
(its topology and training budget were adjusted after observing behaviour) and is preserved under
`09_experiments/` as exploratory evidence only — it is **not** confirmatory.

## Scenario (frozen)
- Devices: **6 static sensors + 2 mobile AMR/AGV** (static-majority, accepted-abstract structure).
- Subchannels **N = 4** — a *post-pilot protocol amendment* (chosen before confirmatory seeds) to
  create meaningful spectrum contention (K > N) and make scheduling/spectrum decisions identifiable.
- Antennas **M = 8** (ULA), beam codebook **B = 8** (DFT), power levels **P = 4** = [0.05,0.10,0.20,0.40] W.
- Per-subchannel cap P_max = 0.4 W; per-device total cap 0.8 W.
- τ = 1 ms, W = 1 MHz/subchannel, NF = 7 dB, T = 290 K, fc = **28 GHz (mmWave amendment)**.
- Channel: InF-SH hall 300×150 m (ETSI TR 138 901 V18.1.0): LOS PL = 31.84+21.50log10(d3D)+19log10(fc),
  SF 4 dB; NLOS PL = max(PL_LOS, 32.4+23.0log10(d3D)+20log10(fc)), SF 5.9 dB; InF LOS-probability
  k_subce derived from clutter (r=0.20, d_clutter=10 m, h_c=5 m preregistered design factor; h_c=2 m
  calibration sensitivity). Spatial Rician(LOS)/Rayleigh(NLOS) ULA abstraction (PREREGISTERED_DESIGN_MODEL);
  Gauss-Markov shadowing + AR(1)/Jakes fading. d_CSI = 1 slot.
- **mmWave amendment rationale (preregistered):** at 3.5 GHz the 8-antenna array gain leaves a ~7.6×
  SNR margin so beam selection does not affect packet delivery. 28 GHz (already in the fc/K_R
  sensitivity set and the natural 6G-beamforming band) increases path loss so beam alignment
  materially affects link SINR/spectral efficiency. This amendment was decided BEFORE any
  confirmatory seed was inspected.

## Traffic / reliability (frozen)
- Bernoulli per-device arrivals; load grid p ∈ {0.05,0.10,0.20,0.30,0.40}; scale-reference p_ref=0.20;
  frozen cost scales across all loads/seeds. Packet sizes 256 B (static) / 64 B (mobile); queues 32/16;
  deadlines 10/2 slots; retx 3/1.
- **Reliability semantics (r36 §5):** the 3GPP URLLC ~1e-5 loss order is a **STANDARD_REFERENCE**
  only — a finite 10-seed simulation cannot empirically certify 1e-5. The study's
  **EMPIRICAL_OPERATIONAL delivery floors** (PREREGISTERED_DESIGN_FACTORs) are **static 0.99,
  mobile 0.995**. These, not 1e-5, are the empirical feasibility targets. C_rel,c = floor_c·arrivals − deliveries.

## Power constraint (frozen, non-vacuous for N=4)
- P_envelope = N·P_max = 1.6 W; **P̄ = 0.8 W** (50 % rule); sensitivity {0.64, 0.80, 0.96} W.
- C_pow = Σ_{t∈W_meas}(P_t − P̄) over the fixed measurement window; drain excluded.

## Evaluation / training (frozen)
- T_meas = 200 slots + full drain (0 residual cohort). Seed = statistical unit.
- Calibration seeds {10001,10002,10003} (tuning only). Confirmatory seeds {20001..20010}, matched
  across methods, never used for tuning.
- Reward: exact locked BSA reliability reward r = w1·delivered − w4·HOL + w6·util (w7_se = 0). The
  spectral-efficiency reward option was evaluated in calibration and NOT adopted for the confirmatory
  reward (see TRAINING_CALIBRATION_REPORT.md).

## Methods (frozen)
- Layer 1 (fixed radio): Fixed-Radio Random, Fixed-Radio Base PPO.
- Layer 2 (full action): Random, RoundRobin, EDF, Stale-Max-Gain, Current-CSI Max-SINR oracle,
  Perfect-current-CSI beam oracle, Last-Beam, BSA-Unconstrained-PPO, BSA-Penalty-PPO, BSA-C-PPO.

## Statistics (frozen)
- Seed-level mean/median/SD/95% CI; paired matched-seed differences; effect sizes; exact paired
  sign-flip permutation tests; Holm correction. Pooled ratio-of-sums is descriptive only. Binomial
  bounds where useful. No empirical 1e-5 certification claim.
