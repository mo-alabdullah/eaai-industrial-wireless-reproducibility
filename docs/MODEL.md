# Model Summary

The environment models mixed static-sensor and mobile AMR/AGV traffic in an indoor-factory mmWave scenario. The control action is constructed autoregressively over orthogonal subchannels. Each non-idle token selects a device, receive beam, and discrete power level subject to packet availability, per-device allocation limits, and power caps.

The confirmatory model uses a finite DFT/ULA beam codebook, stale-CSI observations, queue/deadline accounting, Bernoulli arrivals, full-drain packet accounting, and a fixed-window average-power constraint. The learning family includes an unconstrained PPO variant, a fixed-penalty variant, and a Lagrangian constrained PPO variant with one shared vector cost critic.

The scientific results and limitations are described in the manuscript under `paper/`.
