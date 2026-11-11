#!/usr/bin/env python3
"""Deterministic scenario/config loader for the M2 simulator (r35 repaired).

Loads the LOCKED primary numeric config (`../primary_experiment_config.json`) into a flat,
fully-explicit `ScenarioConfig`. Every physics/PHY/traffic/power/beam/mobility/LPPO value is bound
from the JSON — the agents and env carry NO hidden defaults (§13). Delivery floors are stored
explicitly (§5); LPPO cost scales use the FROZEN preregistered Ā references (§7).

ACTIVE CONFIRMATORY CONFIGURATION (what the manuscript reports and what the 600 primary
method×load×seed records were produced with): `confirmatory_config(...)` below — 6 static + 2 mobile
devices, **N = 4 subchannels**, M = 8 antennas, B = 8 DFT beams, P = 4 power levels, f_c = 28 GHz,
T_meas = 200 (+ drain). This is the r36 post-pilot amendment and is the value recorded in
`../../10_confirmatory/CONFIRMATORY_PROTOCOL_LOCK.json` (N_subchannels = 4) and `run_manifest.json`
(N = 4).

HISTORICAL DESIGN-STAGE RECORD (archival, NOT the executed confirmatory experiment): the earlier
Gate-M1 mathematical design spec used a larger locked primary (K=8, B=8, P=4, **N=8 subchannels**),
preserved in `../primary_experiment_config.json` / `../primary_action_spec.json` and validated
executable by `test_m2`. The N=8 value is the design-stage number only; it is superseded for the
reported study by the N=4 confirmatory configuration above and must not be read as the executed
experiment.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent
PRIMARY_CONFIG_PATH = _HERE.parent / "primary_experiment_config.json"

# InF-SH clutter assumptions (§9) — SELECTED sparse-clutter high-BS values (documented design
# factors consistent with the InF-SH sub-scenario, TR 38.901 Table 7.2-4 / §7.4.2).
CLUTTER_DENSITY_R = 0.20         # sparse clutter
CLUTTER_SIZE_M = 10.0           # d_clutter (sparse, large machinery)
CLUTTER_HEIGHT_M = 5.0          # h_c (below the 8 m high BS)
SHADOW_DECORR_M = 10.0          # shadowing decorrelation distance (Gauss-Markov)


@dataclass
class ScenarioConfig:
    # topology
    n_static: int
    n_mobile: int
    n_subchannels: int
    n_antennas: int
    codebook_size: int
    n_power_levels: int
    n_max_static: int
    n_max_mobile: int
    # phy
    tau_s: float
    bandwidth_hz: float
    noise_figure_db: float
    temperature_k: float
    # channel / geometry
    fc_ghz: float
    hall_x: float
    hall_y: float
    ap_h: float
    ut_h: float
    scenario: str
    clutter_density_r: float
    d_clutter_m: float
    clutter_height_hc_m: float
    k_subce_m: float
    shadow_decorr_m: float
    sf_los_db: float
    sf_nlos_db: float
    kr_db: float
    fading_correlation: str          # "jakes" | "independent" | "strong"
    # power
    power_grid_w: List[float]
    p_max_w: float
    per_device_total_cap_w: float
    p_bar_w: float
    t_meas_slots: int
    drain_cap_slots: int
    # traffic
    arrival_p: float
    queue_cap_static: int
    queue_cap_mobile: int
    deadline_static: int
    deadline_mobile: int
    max_retx_static: int
    max_retx_mobile: int
    pkt_bytes_static: int
    pkt_bytes_mobile: int
    delivery_floor_static: float
    delivery_floor_mobile: float
    abar_static_ref: float
    abar_mobile_ref: float
    # csi / mobility
    d_csi_slots: int
    v_max_mps: float
    # targets (deadline/overflow)
    eps_static: float
    eps_mobile: float
    eta_static: float
    eta_mobile: float
    # LPPO (§13 — all bound from JSON, no hidden defaults)
    lppo: Dict = field(default_factory=dict)
    # campaign knobs
    n_ep_train: int = 8
    n_updates: int = 10
    ppo_hidden: int = 32
    # spectral-efficiency reward weight (w7); 0 = reliability-only (r35 exploratory);
    # >0 = confirmatory multi-objective reliability+SE reward (r36, mmWave) that makes beam
    # selection identifiable in the learning signal.
    w7_se: float = 0.0

    @property
    def n_devices(self) -> int:
        return self.n_static + self.n_mobile

    @property
    def alphabet_size(self) -> int:
        return 1 + self.n_devices * self.codebook_size * self.n_power_levels

    @property
    def j_cost(self) -> int:
        return 3 * 2 + 1     # [rel,dv,over]*2 + C_pow

    @property
    def pkt_bits_static(self) -> int:
        return self.pkt_bytes_static * 8

    @property
    def pkt_bits_mobile(self) -> int:
        return self.pkt_bytes_mobile * 8

    def frozen_cost_scales(self):
        """FROZEN per-constraint scales s_c = 1/(max(Ā_c^ref, A_floor)*T_meas) — identical across
        ALL loads/methods/seeds (§7). Order = J_cost: [rel,dv,over]*(static,mobile), C_pow."""
        import numpy as np
        Tm = self.t_meas_slots
        Af = self.lppo["A_floor"]
        As = max(self.abar_static_ref, Af)
        Am = max(self.abar_mobile_ref, Af)
        return np.array([1 / (As * Tm)] * 3 + [1 / (Am * Tm)] * 3 + [1 / (max(self.p_bar_w, Af) * Tm)])


def _k_subce():
    from . import channel as ch
    return ch.infsh_k_subce(CLUTTER_DENSITY_R, CLUTTER_SIZE_M, CLUTTER_HEIGHT_M, 8.0, 1.5)


def load_primary(path: Path = PRIMARY_CONFIG_PATH) -> ScenarioConfig:
    c = json.loads(Path(path).read_text())
    phy, ch, tr, po, bc, mob, lp = (c["phy"], c["channel"], c["traffic"], c["power"],
                                    c["beam_csi"], c["mobility"], c["lppo"])
    tg = c["targets"]
    return ScenarioConfig(
        n_static=6, n_mobile=2,
        n_subchannels=phy["n_subchannels"], n_antennas=bc["n_antennas"],
        codebook_size=bc["codebook_size"], n_power_levels=len(po["primary_power_grid_w"]),
        n_max_static=3, n_max_mobile=2,
        tau_s=phy["slot_duration_tau_s"], bandwidth_hz=phy["subchannel_bandwidth_W_hz"],
        noise_figure_db=phy["receiver_noise_figure_db"], temperature_k=phy["temperature_k"],
        fc_ghz=ch["carrier_fc_ghz"], hall_x=ch["hall_x_m"], hall_y=ch["hall_y_m"],
        ap_h=ch["ap_height_m"], ut_h=ch["ut_height_m"], scenario="SH",
        clutter_density_r=CLUTTER_DENSITY_R, d_clutter_m=CLUTTER_SIZE_M,
        clutter_height_hc_m=CLUTTER_HEIGHT_M, k_subce_m=_k_subce(), shadow_decorr_m=SHADOW_DECORR_M,
        sf_los_db=4.0, sf_nlos_db=5.9, kr_db=ch["K_R_ricean_db"], fading_correlation="jakes",
        power_grid_w=list(po["primary_power_grid_w"]), p_max_w=po["P_max_w"],
        per_device_total_cap_w=po["per_device_total_cap_w"], p_bar_w=po["P_bar_w"],
        t_meas_slots=po["T_meas_slots"], drain_cap_slots=2000,
        arrival_p=tr["scale_reference_load_p"],
        queue_cap_static=tr["queue_capacity_static"], queue_cap_mobile=tr["queue_capacity_mobile"],
        deadline_static=tr["deadline_slots_static"], deadline_mobile=tr["deadline_slots_mobile"],
        max_retx_static=tr["max_retx_static"], max_retx_mobile=tr["max_retx_mobile"],
        pkt_bytes_static=tr["packet_size_bytes_static"], pkt_bytes_mobile=tr["packet_size_bytes_mobile"],
        delivery_floor_static=1.0 - tg["rho_static"], delivery_floor_mobile=1.0 - tg["rho_mobile"],
        abar_static_ref=tr["Abar_static_scale_ref_pkts_per_slot"],
        abar_mobile_ref=tr["Abar_mobile_scale_ref_pkts_per_slot"],
        d_csi_slots=bc["d_CSI_primary_slots"], v_max_mps=mob["speed_max_mps"],
        eps_static=tg["epsilon_static"], eps_mobile=tg["epsilon_mobile"],
        eta_static=tg["eta_static"], eta_mobile=tg["eta_mobile"],
        lppo=dict(lp), n_ep_train=lp["N_ep_primary"], n_updates=12, ppo_hidden=48,
    )


def campaign_config(load_p: float, fading_correlation: str = "jakes",
                    d_csi_slots: int = None, p_bar_w: float = None,
                    v_max_mps: float = None, n_static: int = 8, n_mobile: int = 3) -> ScenarioConfig:
    """Preregistered computationally-bounded campaign scenario (locked physics; K>>N congestion
    topology: static-majority devices contend for a smaller set of subchannels so congestion,
    class-dependent degradation, and scheduling/beam decisions become material)."""
    base = load_primary()
    lp = dict(base.lppo)
    K_static, K_mobile = n_static, n_mobile
    return ScenarioConfig(
        n_static=K_static, n_mobile=K_mobile, n_subchannels=4, n_antennas=4, codebook_size=4,
        n_power_levels=4, n_max_static=3, n_max_mobile=2,
        tau_s=base.tau_s, bandwidth_hz=base.bandwidth_hz, noise_figure_db=base.noise_figure_db,
        temperature_k=base.temperature_k,
        fc_ghz=base.fc_ghz, hall_x=base.hall_x, hall_y=base.hall_y, ap_h=base.ap_h, ut_h=base.ut_h,
        scenario="SH", clutter_density_r=base.clutter_density_r, d_clutter_m=base.d_clutter_m,
        clutter_height_hc_m=base.clutter_height_hc_m, k_subce_m=base.k_subce_m,
        shadow_decorr_m=base.shadow_decorr_m, sf_los_db=4.0, sf_nlos_db=5.9, kr_db=base.kr_db,
        fading_correlation=fading_correlation,
        power_grid_w=list(base.power_grid_w), p_max_w=base.p_max_w,
        per_device_total_cap_w=base.per_device_total_cap_w,
        p_bar_w=(p_bar_w if p_bar_w is not None else base.p_bar_w),
        t_meas_slots=50, drain_cap_slots=2000,
        arrival_p=load_p,
        queue_cap_static=base.queue_cap_static, queue_cap_mobile=base.queue_cap_mobile,
        deadline_static=base.deadline_static, deadline_mobile=base.deadline_mobile,
        max_retx_static=base.max_retx_static, max_retx_mobile=base.max_retx_mobile,
        pkt_bytes_static=base.pkt_bytes_static, pkt_bytes_mobile=base.pkt_bytes_mobile,
        delivery_floor_static=base.delivery_floor_static, delivery_floor_mobile=base.delivery_floor_mobile,
        # frozen Ā refs recomputed for the campaign topology at p_ref=0.20 (NOT the current load)
        abar_static_ref=K_static * 0.20, abar_mobile_ref=K_mobile * 0.20,
        d_csi_slots=(d_csi_slots if d_csi_slots is not None else base.d_csi_slots),
        v_max_mps=(v_max_mps if v_max_mps is not None else base.v_max_mps),
        eps_static=base.eps_static, eps_mobile=base.eps_mobile,
        eta_static=base.eta_static, eta_mobile=base.eta_mobile,
        lppo=lp, n_ep_train=3, n_updates=5, ppo_hidden=20,
    )


def confirmatory_config(load_p: float, fading_correlation: str = "jakes",
                        d_csi_slots: int = 1, p_bar_w: float = 0.8, v_max_mps: float = 2.0,
                        clutter_height_hc_m: float = 5.0, fc_ghz: float = 28.0,
                        n_ep_train: int = 16, n_updates: int = 20, ppo_hidden: int = 48,
                        eta_lambda: float = None, penalty_coeff: float = None) -> ScenarioConfig:
    """CONFIRMATORY_PROTOCOL_v1 (r36) — frozen BEFORE confirmatory seeds.

    6 static + 2 mobile devices, N=4 subchannels (post-pilot amendment for identifiability/
    congestion, chosen before any confirmatory seed), M=8 antennas, B=8 DFT beams, P=4 power
    levels [0.05,0.10,0.20,0.40] W, P_max=0.4, per-device cap 0.8 W, T_meas=200, τ=1 ms,
    W=1 MHz, NF=7 dB, fc=3.5 GHz, InF-SH hall 300×150 m, d_CSI=1.
    Power: P_envelope = N·P_max = 1.6 W; P̄ = 0.8 W (50%); sensitivity {0.64,0.80,0.96}.
    Delivery floors (EMPIRICAL_OPERATIONAL, PREREGISTERED_DESIGN_FACTOR): static 0.99, mobile 0.995
    — the 3GPP URLLC ~1e-5 loss order is a STANDARD_REFERENCE only, NOT an empirically-certified
    finite-sample threshold here.
    """
    base = load_primary()
    lp = dict(base.lppo)
    if eta_lambda is not None:
        lp["eta_lambda"] = eta_lambda
    r = CLUTTER_DENSITY_R
    from . import channel as ch
    k_sub = ch.infsh_k_subce(r, CLUTTER_SIZE_M, clutter_height_hc_m, 8.0, 1.5)
    cfg = ScenarioConfig(
        n_static=6, n_mobile=2, n_subchannels=4, n_antennas=8, codebook_size=8, n_power_levels=4,
        n_max_static=3, n_max_mobile=2,
        tau_s=1e-3, bandwidth_hz=1e6, noise_figure_db=7.0, temperature_k=290.0,
        fc_ghz=fc_ghz, hall_x=300.0, hall_y=150.0, ap_h=8.0, ut_h=1.5, scenario="SH",
        clutter_density_r=r, d_clutter_m=CLUTTER_SIZE_M, clutter_height_hc_m=clutter_height_hc_m,
        k_subce_m=k_sub, shadow_decorr_m=SHADOW_DECORR_M, sf_los_db=4.0, sf_nlos_db=5.9, kr_db=7.0,
        fading_correlation=fading_correlation,
        power_grid_w=[0.05, 0.10, 0.20, 0.40], p_max_w=0.4, per_device_total_cap_w=0.8,
        p_bar_w=p_bar_w, t_meas_slots=200, drain_cap_slots=4000,
        arrival_p=load_p,
        queue_cap_static=32, queue_cap_mobile=16, deadline_static=10, deadline_mobile=2,
        max_retx_static=3, max_retx_mobile=1, pkt_bytes_static=256, pkt_bytes_mobile=64,
        delivery_floor_static=0.99, delivery_floor_mobile=0.995,
        abar_static_ref=6 * 0.20, abar_mobile_ref=2 * 0.20,
        d_csi_slots=d_csi_slots, v_max_mps=v_max_mps,
        eps_static=0.01, eps_mobile=1e-4, eta_static=0.01, eta_mobile=1e-3,
        lppo=lp, n_ep_train=n_ep_train, n_updates=n_updates, ppo_hidden=ppo_hidden,
        w7_se=0.0,   # confirmatory = exact locked BSA reliability reward (r=w1*d - w4*hol + w6*util)
    )
    return cfg


def small_config(arrival_p: float = 0.4) -> ScenarioConfig:
    """Tiny scenario for unit tests + smoke training (alphabet 1+3*2*2 = 13)."""
    return campaign_config(arrival_p, n_static=2, n_mobile=1).__class__(
        **{**campaign_config(arrival_p, n_static=2, n_mobile=1).__dict__,
           "n_subchannels": 3, "n_antennas": 2, "codebook_size": 2, "n_power_levels": 2,
           "power_grid_w": [0.2, 0.4], "t_meas_slots": 20, "n_max_static": 2, "n_max_mobile": 1,
           "abar_static_ref": 2 * 0.20, "abar_mobile_ref": 1 * 0.20,
           "n_ep_train": 4, "n_updates": 4, "ppo_hidden": 16})
