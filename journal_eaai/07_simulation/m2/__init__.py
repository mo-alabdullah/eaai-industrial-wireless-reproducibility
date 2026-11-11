"""M2 scientific simulator (r34 Phase 2).

Numpy-only, deterministic (per-seed) implementation of the repaired M1 model:
InF-SH geometry + LOS probability + LOS/NLOS path loss + shadowing, a transparent
spatial Rician/Rayleigh ULA channel (PREREGISTERED_DESIGN_MODEL) with a finite DFT
receive-beam codebook, static sensors + seeded AMR/AGV mobility, a stale-CSI observation
buffer (d_CSI slots), Bernoulli traffic with FIFO queues / deadlines / retransmissions,
orthogonal subchannel allocation, discrete power, the strict conditional-mask token decoder
(reusing `conditional_mask_oracle` + `token_codec`), fixed-window C_pow accounting, and the
ordered J_cost = 3|C|+1 cost channels.

torch is NOT available in this environment, so the PPO family (Base PPO, BSA-Penalty-PPO,
BSA-C-PPO) is a pure-numpy MLP implementation.
"""
