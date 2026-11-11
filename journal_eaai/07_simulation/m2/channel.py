#!/usr/bin/env python3
"""InF channel + finite DFT/ULA receive-beam codebook (M2, r35 repaired).

Large-scale model = SOURCED to 3GPP TR 38.901 / ETSI TR 138 901 V18.1.0 (2026-02, Rel-18),
Indoor Factory. Path loss Table 7.4.1-1; LOS probability §7.4.2 / clutter Table 7.2-4.

  InF LOS   : PL = 31.84 + 21.50 log10(d3D) + 19.00 log10(fc[GHz]),  SF = 4.0 dB.
  InF-SH NLOS: PL' = 32.4 + 23.0 log10(d3D) + 20.0 log10(fc); PL = max(PL', PL_LOS), SF = 5.9 dB.
  InF-DH NLOS: PL' = 33.63 + 21.9 log10(d3D) + 20.0 log10(fc); PL = max(PL', PL_LOS), SF = 4.0 dB.
  (SH and DH are DISTINCT — the primary sub-scenario is InF-SH.)

LOS probability (InF high-BS sub-scenario, §7.4.2):
  P_LOS = exp(-d2D / k_subce),  k_subce = (-d_clutter / ln(1-r)) * (hBS - hUT)/(hc - hUT).

Spatial Rician(LOS)/Rayleigh(NLOS) ULA channel + Rician K-factor + the temporal correlation
(Gauss-Markov shadowing, AR(1)/Jakes fading) are a PREREGISTERED_DESIGN_MODEL — NOT the full
TR 38.901 clustered (CDL/TDL) channel or the full spatial-consistency procedure.

Packet success (r35): capacity_bits = W*tau*log2(1+SINR); success iff capacity_bits >= packet_bits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BOLTZMANN_K = 1.380649e-23     # J/K
SPEED_OF_LIGHT = 299792458.0   # m/s


def noise_power_w(temperature_k: float, bandwidth_hz: float, noise_figure_db: float) -> float:
    return BOLTZMANN_K * temperature_k * bandwidth_hz * 10.0 ** (noise_figure_db / 10.0)


def pl_los_db(d3d_m: float, fc_ghz: float) -> float:
    return 31.84 + 21.50 * math.log10(d3d_m) + 19.00 * math.log10(fc_ghz)


def pl_nlos_infsh_db(d3d_m: float, fc_ghz: float) -> float:
    """InF-SH NLOS (Table 7.4.1-1): max(32.4 + 23.0 log10(d3D) + 20 log10(fc), PL_LOS)."""
    sh = 32.4 + 23.0 * math.log10(d3d_m) + 20.0 * math.log10(fc_ghz)
    return max(sh, pl_los_db(d3d_m, fc_ghz))


def pl_nlos_infdh_db(d3d_m: float, fc_ghz: float) -> float:
    """InF-DH NLOS (Table 7.4.1-1) — kept DISTINCT from InF-SH to prevent formula swap."""
    dh = 33.63 + 21.9 * math.log10(d3d_m) + 20.0 * math.log10(fc_ghz)
    return max(dh, pl_los_db(d3d_m, fc_ghz))


SF_LOS_DB = 4.0
SF_NLOS_SH_DB = 5.9
SF_NLOS_DH_DB = 4.0


def infsh_k_subce(clutter_density_r: float, d_clutter_m: float, clutter_height_hc_m: float,
                  h_bs_m: float, h_ut_m: float) -> float:
    """InF-SH (high-BS) LOS-probability decay constant (§7.4.2):
       k_subce = (-d_clutter / ln(1-r)) * (hBS - hUT)/(hc - hUT)."""
    base = -d_clutter_m / math.log(1.0 - clutter_density_r)
    return base * (h_bs_m - h_ut_m) / (clutter_height_hc_m - h_ut_m)


def los_probability(d2d_m: float, k_subce_m: float) -> float:
    return math.exp(-d2d_m / k_subce_m)


def large_scale_gain_db(d3d_m: float, fc_ghz: float, los: bool, scenario: str = "SH") -> float:
    if los:
        return pl_los_db(d3d_m, fc_ghz)
    return pl_nlos_infsh_db(d3d_m, fc_ghz) if scenario == "SH" else pl_nlos_infdh_db(d3d_m, fc_ghz)


def beta_from_pl(pl_db: float, shadow_db: float) -> float:
    """Linear large-scale path gain beta = 10^(-(PL + shadow)/10)  (no beam gain)."""
    return 10.0 ** (-(pl_db + shadow_db) / 10.0)


def ula_steering(sin_phi: float, n_antennas: int) -> np.ndarray:
    m = np.arange(n_antennas)
    return np.exp(1j * math.pi * m * sin_phi)          # ||a||^2 = M


def dft_codebook(n_antennas: int) -> np.ndarray:
    m = np.arange(n_antennas)
    return np.exp(1j * 2.0 * math.pi * np.outer(m, m) / n_antennas) / math.sqrt(n_antennas)


def rician_spatial(sin_phi: float, kr_linear: float, los: bool, z: np.ndarray) -> np.ndarray:
    """Normalised spatial signature hbar (E||hbar||^2 = M) given a fading innovation state z."""
    if los:
        a = ula_steering(sin_phi, len(z))
        return math.sqrt(kr_linear / (kr_linear + 1.0)) * a + math.sqrt(1.0 / (kr_linear + 1.0)) * z
    return z


def beam_gains(hbar: np.ndarray, codebook: np.ndarray) -> np.ndarray:
    return np.abs(codebook.conj().T @ hbar) ** 2


def jakes_ar1_coeff(speed_mps: float, fc_ghz: float, tau_s: float) -> float:
    """AR(1) fading correlation rho = J0(2*pi*f_d*tau), f_d = v/lambda (Clarke/Jakes)."""
    lam = SPEED_OF_LIGHT / (fc_ghz * 1e9)
    fd = speed_mps / lam
    x = 2.0 * math.pi * fd * tau_s
    return float(_besselj0(x))


def _besselj0(x: float) -> float:
    # scipy-free J0: use the integral/series; numpy has no jn, so use a compact approximation
    # Abramowitz & Stegun 9.4.1 (|x|<=3) — accurate to ~1e-8, ample for x<<1 here.
    if abs(x) < 3.0:
        t = (x / 3.0) ** 2
        return (1 - 2.2499997 * t + 1.2656208 * t ** 2 - 0.3163866 * t ** 3
                + 0.0444479 * t ** 4 - 0.0039444 * t ** 5 + 0.0002100 * t ** 6)
    ax = abs(x)
    z = 3.0 / ax
    p0 = (1 - 0.1098628627e-2 * z ** 2 + 0.2734510407e-4 * z ** 4
          - 0.2073370639e-5 * z ** 6 + 0.2093887211e-6 * z ** 8)
    q0 = (-0.1562499995e-1 * z + 0.1430488765e-3 * z ** 3 - 0.6911147651e-5 * z ** 5
          + 0.7621095161e-6 * z ** 7 - 0.934935152e-7 * z ** 9)
    return math.sqrt(0.636619772 / ax) * (math.cos(ax - 0.785398164) * p0 - z * math.sin(ax - 0.785398164) * q0)


def shadow_ar1_coeff(speed_mps: float, tau_s: float, decorr_distance_m: float) -> float:
    """Gauss-Markov shadowing correlation a = exp(-v*tau / d_corr) (TR 38.901 §7.6.3.1 form)."""
    return math.exp(-(speed_mps * tau_s) / decorr_distance_m)


@dataclass(frozen=True)
class LinkResult:
    sinr_linear: float
    spectral_eff_bps_hz: float
    capacity_bits: float
    success: bool


def link_success(power_w: float, beta: float, beam_gain: float, noise_w: float,
                 bandwidth_hz: float, slot_s: float, packet_bits: int) -> LinkResult:
    """OMA single-user-per-subchannel (no intra-cell interference): SINR = p*beta*G/sigma_n^2.
    Shannon capacity over one slot: capacity_bits = W*tau*log2(1+SINR); success iff it carries
    the whole packet: capacity_bits >= packet_bits."""
    sinr = power_w * beta * beam_gain / noise_w
    se = math.log2(1.0 + sinr)
    cap_bits = bandwidth_hz * slot_s * se
    return LinkResult(sinr, se, cap_bits, cap_bits >= packet_bits)


def required_spectral_efficiency(packet_bits: int, bandwidth_hz: float, slot_s: float) -> float:
    return packet_bits / (bandwidth_hz * slot_s)
