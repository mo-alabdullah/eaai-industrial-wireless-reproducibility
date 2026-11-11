# M2 Acceptance Test Plan — CONTRACT (ACTIVE)

**Gate M1 = PASSED (r33/r34).** M2 acceptance contract is **ACTIVE**; the M2 simulator is
implemented under `07_simulation/m2/` and tested by `test_m2.py`. Runner: **`unittest`** (not
pytest). Deterministic fixtures + fixed seeds only. Channel provenance:
`../06_mathematical_model/primary_channel_model_provenance.md` (3GPP TR 38.901 InF-SH). Locked
numeric config: `primary_experiment_config.json`.

## Locked numeric constants (r34) the M2 code + tests must honor
- PHY: `tau = 1 ms`, `W = 1 MHz`, `N_subchannels = 8` (total 8 MHz), `NF = 7 dB`, `T = 290 K`,
  `sigma_n^2 = k_B*T*W*10^(NF/10)`, Shannon threshold `Z = 1 bit/s/Hz`.
- Channel: InF-SH, hall `300 m x 150 m` (primary geometry; d3D≈600 m is model **applicability** /
  distance stress-test, NOT the hall size), high AP; LOS PL `31.84+21.5log10(d3D)+19log10(fc)`;
  spatial Rician(LOS)/Rayleigh(NLOS) with ULA steering, `K_R = 7 dB` design factor.
- Traffic: independent **Bernoulli** arrivals; load grid `p ∈ {0.05,0.10,0.20,0.30,0.40}`; scale
  ref `p=0.20` → `Abar_static=1.20`, `Abar_mobile=0.40` pkts/slot/class (frozen).
- Power: `P_max=0.4 W`, `P_envelope=N*P_max=3.2 W`, `P_bar=0.5*3.2=1.6 W` (sens {1.28,1.60,1.92}).
- Deadlines: `D_mobile = 2 slots = 2 ms`; `D_static = 10 slots`. Beam: stale CSI `d_CSI=1`.
- PPO: `N_ep = 32`, `gamma_cost=1`, `lambda_cost=0.95`.

## 0. Integrity / governance (must run first, fail-fast)
- Title/abstract integrity: `01_governance/check_immutable_content.py` exits 0 (accepted DOCX hash unchanged).
- All current M1 validators/suites still pass in the extracted candidate.

## 1. Action-spec tier separation
- `reference_action_spec.json` (toy) and `primary_action_spec.json` (N_primary=8) are distinct tiers.
- `compute_reference_boolean_token_mask` uses the reference tier; `compute_primary_boolean_token_mask` the primary.
- The generic `compute_boolean_token_mask` raises (no silent tier fallback).
- Runtime `OrderedModelSpec` is fully bound to the committed primary artifact incl. `beam_forbidden`/`power_forbidden`.

## 2. DFT/ULA finite-codebook gain model
- `codebook_type == "DFT"` and `array_type == "ULA"` enforced; `codebook_size == n_antennas`.
- Receive-beam gain is a **finite-codebook selection** `g(k,n,b)` over `B` steering vectors — described
  accurately as codebook selection, NOT unrestricted continuous beamforming.
- Gain bounded in `[0, M]` (M = antenna elements); deterministic given (k,n,b) and channel.

## 3. Token codec (exact bijection)
- `encode_token`/`decode_token` round-trip for every id in `[0, 1+K*B*P)`; `IDLE_ID=0`; mask length `1+K*B*P`.

## 4. Strict conditional mask (oracle)
- Every device covered by `eligible`, `power_cap`, `n_max`; missing/unknown device rejected.
- `1 <= N_max_k <= N` (N_max=0 rejected); powers finite `> 0`; forbidden (subchannel,beam/power) in-domain.
- No selected non-idle token is ever repaired post-hoc (`post_hoc_action_repair = forbidden`).

## 5. Power grid + caps (distinct quantities)
- Every chosen `p_{k,n}` is a member of `primary_power_grid_w = [0.05,0.1,0.2,0.4]` W.
- Per-subchannel cap: `p_{k,n} <= P_max_primary = 0.4` W.
- Per-device total cap: `sum_n p_{k,n} <= P_tot,k = 0.8` W (caller cannot override the locked cap).
- `P_max_primary != P_tot,k`; both enforced independently.

## 6. Queue / deadline / FIFO accounting
- `delivered <= generated`; `delivered + dropped <= generated`; `0 <= q_k <= Q_max`.
- FIFO service; no delivered packet older than `D_k`; deadline violations counted, not delivered.
- Drop precedence (expiry/overflow/retx-exhausted) mutually exclusive; CENSORED status handled.

## 7. J_cost ordered cost channels
- Cost vector length `J_cost = 3|C|+1`; ordering per `bsa_lppo_specification.md` §2a:
  for each class c: [rel, dv, over]; then `C_pow` last. Critic/advantage/multiplier share this order.
- `C_pow` is present (index `J_cost`); no summary omits it. `M` (antennas) never used as the cost index.
- Rollout mean uses `N_ep` (never `B`).

## 8. C_pow fixed-window accounting
- `C_pow = sum_{t in W_meas}(P_t - P_bar)`, W_meas a FIXED window identical across methods/seeds; drain excluded.

## 9. Reward / constraint (no double-count) — per method
- Base/Penalty PPO use the six-weight shaping reward; BSA-LPPO uses `r = w1*d - w4*h + w6*u`
  (no v/o/e duplication of the explicit cost channels). Machine-check the primary reward has no
  constrained-quantity soft penalty.

## 10. Channel-model equations (B1 CLOSED — TR 38.901 InF-SH)
- Path loss / shadowing / fading per the audited `06_mathematical_model/model_channel_provenance.md`
  primary sub-scenario; SINR/packet-success formulas match the audited forms; `0 <= P_success <= 1`.

## 11. Mobility / CSI update (B2/B6 CLOSED)
- Reproducible AMR/AGV trajectories (seeded); CSI/beam evolution driven by mobility per the closed model.
- Beam decision behaves per the closed B2 decision (learned selection vs deterministic Max-Gain).

## 12. Determinism
- Fixed seed ⇒ identical rollouts/results; multiple independent seeds supported; no hidden global RNG.

## 13. Statistical protocol (E1, not M2)
- ≥10 seeds where compute permits; means/SD/CIs/effect sizes; algorithmic collapse threshold; no single-curve claims.

Gate M1 = PASSED; this contract is ACTIVE and implemented under `m2/` (see `test_m2.py`).
