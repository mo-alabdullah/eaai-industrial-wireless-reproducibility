#!/usr/bin/env python3
"""M2 scientific environment (r35 repaired).

Clean two-call physical-slot API enforcing the locked event order:

  begin_slot():   arrivals -> overflow -> deadline expiry -> freeze & expose immutable s_t
  commit_action(tokens):
                  validate the joint action token-by-token against the SAME canonical conditional
                  mask (RAISE on any infeasible/malformed/wrong-length action — the env, not the
                  agent, is the final feasibility authority) -> transmit (packet-bits success under
                  the CURRENT channel) -> delivery/retry/exhaustion -> reward/cost -> mobility &
                  correlated-channel update -> advance t.

The action at slot t sees the queues produced by arrivals/expiry at the START of slot t.
Full-drain episode: T_meas measurement slots (arrivals on, C_pow active) then a drain phase
(arrivals off, C_pow=0) until every measurement-cohort packet is terminal.
"""
from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import conditional_mask_oracle as cmo   # noqa: E402
import token_codec as tc                # noqa: E402

from . import channel as ch             # noqa: E402
from .config import ScenarioConfig      # noqa: E402
from .mobility import Geometry, MobilityModel   # noqa: E402

IDLE = "idle"


class InvalidActionError(ValueError):
    """Raised when a committed joint action is infeasible/malformed (never silently repaired)."""


@dataclass
class Packet:
    arrival_slot: int
    cohort: bool          # generated during the measurement phase
    retx: int = 0


class M2Env:
    FEATS_PER_DEV = 6

    def __init__(self, cfg: ScenarioConfig, seed: int, layer1_fixed: bool = False):
        self.cfg = cfg
        self.seed = seed
        self.layer1_fixed = layer1_fixed
        self.fixed_beam = 0
        self.fixed_power = cfg.n_power_levels - 1     # max power index
        self.K, self.N = cfg.n_devices, cfg.n_subchannels
        self.B, self.P = cfg.codebook_size, cfg.n_power_levels
        self.kr_lin = 10.0 ** (cfg.kr_db / 10.0)
        self.noise_w = ch.noise_power_w(cfg.temperature_k, cfg.bandwidth_hz, cfg.noise_figure_db)
        self.codebook = ch.dft_codebook(cfg.n_antennas)
        self.geom = Geometry(cfg.hall_x, cfg.hall_y, cfg.hall_x / 2, cfg.hall_y / 2, cfg.ap_h, cfg.ut_h)
        self.mob = MobilityModel(self.geom, cfg.n_static, cfg.n_mobile, cfg.v_max_mps, cfg.tau_s)
        self.dev_ids = [f"d{k}" for k in range(self.K)]
        self.beam_ids = [f"b{b}" for b in range(self.B)]
        self.power_ids = [f"p{p}" for p in range(self.P)]
        self.powers = {f"p{p}": float(cfg.power_grid_w[p]) for p in range(self.P)}
        self.n_max = {f"d{k}": (cfg.n_max_static if k < cfg.n_static else cfg.n_max_mobile)
                      for k in range(self.K)}
        self.model_parameters = {
            "devices": list(self.dev_ids), "beams": {b: 0.0 for b in self.beam_ids},
            "powers": dict(self.powers), "N": self.N, "n_primary": self.N, "n_max": dict(self.n_max),
            "beam_forbidden": set(), "power_forbidden": set(),
        }
        self.obs_dim = 1 + self.FEATS_PER_DEV * self.K + self.K * self.N * self.B + self.K + self.K + self.N
        self.reset()

    # ------------------------------------------------------------- lifecycle
    def reset(self):
        self.rng = np.random.default_rng(self.seed)
        self.mob.reset(self.rng)
        self.t = 0
        self.phase = "measure"
        self.queues: List[deque] = [deque() for _ in range(self.K)]
        self.los = [False] * self.K
        self.shadow = [0.0] * self.K
        # AR(1) fading state z[k,n] in C^M
        self.z = [[self._draw_cn() for _ in range(self.N)] for _ in range(self.K)]
        self._init_geometry_los()
        self._recompute_beta()
        self._draw_gains()
        self.csi_buffer = deque([self.cur_gain.copy() for _ in range(self.cfg.d_csi_slots + 1)],
                                maxlen=self.cfg.d_csi_slots + 1)
        self._reset_metrics()
        self._slot_open = False
        self._s_frozen = None
        return None

    def _draw_cn(self):
        return (self.rng.standard_normal(self.cfg.n_antennas)
                + 1j * self.rng.standard_normal(self.cfg.n_antennas)) / math.sqrt(2.0)

    def _is_mobile(self, k): return k >= self.cfg.n_static
    def _cls(self, k): return 1 if self._is_mobile(k) else 0
    def _deadline(self, k): return self.cfg.deadline_mobile if self._is_mobile(k) else self.cfg.deadline_static
    def _qcap(self, k): return self.cfg.queue_cap_mobile if self._is_mobile(k) else self.cfg.queue_cap_static
    def _maxretx(self, k): return self.cfg.max_retx_mobile if self._is_mobile(k) else self.cfg.max_retx_static
    def _pktbits(self, k): return self.cfg.pkt_bits_mobile if self._is_mobile(k) else self.cfg.pkt_bits_static
    def _speed(self, k):
        d = self.mob.devices[k]
        return math.hypot(d.vx, d.vy) if hasattr(d, "vx") and not self._is_mobile(k) else \
            (d.speed if self._is_mobile(k) else 0.0)

    # ------------------------------------------------------------- channel
    def _init_geometry_los(self):
        self.d3d = [0.0] * self.K; self.sin_phi = [0.0] * self.K
        for k, dev in enumerate(self.mob.devices):
            d2d, d3d, sphi = self.geom.d2d_d3d(dev)
            self.d3d[k] = d3d; self.sin_phi[k] = sphi
            p_los = ch.los_probability(d2d, self.cfg.k_subce_m)
            self.los[k] = bool(self.rng.random() < p_los)      # spatial consistency: fixed per episode
            self.shadow[k] = self.rng.normal(0.0, self.cfg.sf_los_db if self.los[k] else self.cfg.sf_nlos_db)

    def _recompute_beta(self):
        self.beta = [0.0] * self.K; self.pl_db = [0.0] * self.K
        for k, dev in enumerate(self.mob.devices):
            d2d, d3d, sphi = self.geom.d2d_d3d(dev)
            self.d3d[k] = d3d; self.sin_phi[k] = sphi
            self.pl_db[k] = ch.large_scale_gain_db(d3d, self.cfg.fc_ghz, self.los[k], self.cfg.scenario)
            self.beta[k] = ch.beta_from_pl(self.pl_db[k], self.shadow[k])

    def _fading_rho(self, k):
        mode = self.cfg.fading_correlation
        if mode == "independent":
            return 0.0
        if mode == "strong":
            return 0.99
        return ch.jakes_ar1_coeff(self._speed(k), self.cfg.fc_ghz, self.cfg.tau_s)  # jakes

    def _advance_channel(self):
        # Gauss-Markov shadowing + AR(1)/Jakes fading, both tied to per-device speed
        for k in range(self.K):
            a = ch.shadow_ar1_coeff(self._speed(k), self.cfg.tau_s, self.cfg.shadow_decorr_m)
            sf = self.cfg.sf_los_db if self.los[k] else self.cfg.sf_nlos_db
            self.shadow[k] = a * self.shadow[k] + math.sqrt(max(1 - a * a, 0.0)) * self.rng.normal(0, sf)
            rho = self._fading_rho(k)
            for n in range(self.N):
                innov = self._draw_cn()
                self.z[k][n] = rho * self.z[k][n] + math.sqrt(max(1 - rho * rho, 0.0)) * innov
        self._recompute_beta()
        self._draw_gains()

    def _draw_gains(self):
        self.cur_gain = np.zeros((self.K, self.N, self.B))
        for k in range(self.K):
            for n in range(self.N):
                hbar = ch.rician_spatial(self.sin_phi[k], self.kr_lin, self.los[k], self.z[k][n])
                self.cur_gain[k, n, :] = ch.beam_gains(hbar, self.codebook)

    def stale_gain(self):
        return self.csi_buffer[0]

    # ------------------------------------------------------------- mask
    def _slot_start_state(self):
        return {"eligible": {f"d{k}": len(self.queues[k]) for k in range(self.K)},
                "power_cap": {f"d{k}": float(self.cfg.per_device_total_cap_w) for k in range(self.K)}}

    def feasible_tokens(self, prefix, subchannel_index) -> FrozenSet:
        return cmo.compute_token_mask(self._s_frozen or self._slot_start_state(),
                                      prefix, subchannel_index, self.model_parameters)

    def feasible_id_mask(self, prefix, subchannel_index):
        mask = np.zeros(self.cfg.alphabet_size, dtype=bool)
        for tok in self.feasible_tokens(prefix, subchannel_index):
            mask[self.token_to_id(tok)] = True
        return mask

    def fast_id_mask(self, assigned, committed):
        """Fast feasible-id boolean mask from running per-device (assigned_count, committed_power)
        — the incremental prefix is valid by construction, so the O(2^N) prefix re-validation of
        the strict oracle is skipped in the rollout hot loop. Equivalent feasibility rules:
        remaining eligible > 0; assigned < N_max; committed + power <= cap; forbidden sets empty."""
        mask = np.zeros(self.cfg.alphabet_size, dtype=bool)
        mask[tc.IDLE_ID] = True
        elig = self.queues
        cap = self.cfg.per_device_total_cap_w
        pgrid = self.cfg.power_grid_w
        eps = 1e-12
        for k in range(self.K):
            ak = assigned.get(k, 0)
            if len(elig[k]) - ak <= 0:
                continue
            if ak >= self.n_max[f"d{k}"]:
                continue
            ck = committed.get(k, 0.0)
            base = 1 + k * self.B * self.P
            for b in range(self.B):
                bp = base + b * self.P
                for p in range(self.P):
                    if ck + pgrid[p] <= cap + eps:
                        mask[bp + p] = True
        return mask

    def token_to_id(self, tok):
        if tok == IDLE:
            return tc.IDLE_ID
        return tc.encode_token(int(tok[0][1:]), int(tok[1][1:]), int(tok[2][1:]), self.K, self.B, self.P)

    def id_to_token(self, tid):
        dec = tc.decode_token(tid, self.K, self.B, self.P)
        return IDLE if dec == "idle" else (f"d{dec[0]}", f"b{dec[1]}", f"p{dec[2]}")

    # ------------------------------------------------------------- slot: begin
    def begin_slot(self):
        """arrivals -> overflow -> deadline expiry -> freeze & expose immutable s_t."""
        gen = [0, 0]; arr = [0, 0]; ovf = [0, 0]; dvl = [0, 0]
        if self.phase == "measure":
            for k in range(self.K):
                c = self._cls(k)
                if self.rng.random() < self.cfg.arrival_p:
                    gen[c] += 1
                    if len(self.queues[k]) >= self._qcap(k):
                        ovf[c] += 1
                    else:
                        self.queues[k].append(Packet(self.t, cohort=True))
                        arr[c] += 1
        for k in range(self.K):
            c = self._cls(k); D = self._deadline(k); keep = deque()
            while self.queues[k]:
                pkt = self.queues[k].popleft()
                if self.t > pkt.arrival_slot + D - 1:
                    dvl[c] += 1
                    if pkt.cohort:
                        self.m["drop_deadline"][c] += 1
                        self.m["cohort_terminal"][c] += 1
                else:
                    keep.append(pkt)
            self.queues[k] = keep
        self._pending = {"gen": gen, "arr": arr, "ovf": ovf, "dvl": dvl}
        for c in (0, 1):
            self.m["generated"][c] += gen[c]; self.m["overflow"][c] += ovf[c]
            if self.phase == "measure":
                self.m["cohort_gen"][c] += gen[c]
            # overflow-dropped cohort packets are terminal at generation
            self.m["cohort_terminal"][c] += ovf[c] if self.phase == "measure" else 0
        self._s_frozen = self._slot_start_state()
        self._slot_open = True
        return self.slot_observation()

    def cohort_outstanding(self):
        return sum(1 for k in range(self.K) for p in self.queues[k] if p.cohort)

    # ------------------------------------------------------------- slot: commit
    def _validate_action(self, tokens):
        if len(tokens) != self.N:
            raise InvalidActionError(f"joint action length {len(tokens)} != N={self.N}")
        prefix = []
        for n, tok in enumerate(tokens, start=1):
            if tok != IDLE and not (isinstance(tok, tuple) and len(tok) == 3):
                raise InvalidActionError(f"malformed token at position {n}: {tok!r}")
            feas = self.feasible_tokens(prefix, n)
            if tok not in feas:
                raise InvalidActionError(
                    f"infeasible token {tok!r} at subchannel {n} "
                    f"(N_max/P_tot/packet-surplus/structure violation)")
            prefix.append(tok)

    def commit_action(self, tokens):
        if not self._slot_open:
            raise InvalidActionError("commit_action called before begin_slot")
        self._validate_action(tokens)                 # env is the final feasibility authority
        by_dev: Dict[int, List[Tuple[int, int, int]]] = {}
        power_total = 0.0; used = 0
        for n, tok in enumerate(tokens):
            if tok == IDLE:
                continue
            used += 1
            k, b, p = int(tok[0][1:]), int(tok[1][1:]), int(tok[2][1:])
            by_dev.setdefault(k, []).append((n, b, p))
        deliv = [0, 0]; rexh = [0, 0]; se_sum = 0.0
        for k, assigns in by_dev.items():
            c = self._cls(k)
            for (n, b, p) in assigns:
                if not self.queues[k]:
                    break
                pw = float(self.cfg.power_grid_w[p]); power_total += pw
                res = ch.link_success(pw, self.beta[k], self.cur_gain[k, n, b], self.noise_w,
                                      self.cfg.bandwidth_hz, self.cfg.tau_s, self._pktbits(k))
                se_sum += res.spectral_eff_bps_hz
                # beam-behaviour metrics
                oracle_b = int(np.argmax(self.cur_gain[k, n, :]))
                stale_b = int(np.argmax(self.stale_gain()[k, n, :]))
                self.m["beam_attempts"] += 1
                self.m["beam_match_oracle"] += int(b == oracle_b)
                self.m["beam_match_stale"] += int(b == stale_b)
                if self._last_beam.get(k) is not None and self._last_beam[k] != b:
                    self.m["beam_switches"] += 1
                self._last_beam[k] = b
                if res.sinr_linear > 0:
                    self.m["gain_ratio_sum"] += self.cur_gain[k, n, b] / max(self.cur_gain[k, n, oracle_b], 1e-12)
                    self.m["gain_ratio_n"] += 1
                pkt = self.queues[k][0]
                if res.success:
                    self.queues[k].popleft()
                    deliv[c] += 1
                    lat = self.t - pkt.arrival_slot + 1
                    self.m["latency"][c].append(lat)
                    self.m["throughput_bits"] += self._pktbits(k)
                    if pkt.cohort:
                        self.m["cohort_delivered"][c] += 1; self.m["cohort_terminal"][c] += 1
                else:
                    pkt.retx += 1
                    if pkt.retx > self._maxretx(k):
                        self.queues[k].popleft(); rexh[c] += 1
                        self.m["drop_retx"][c] += 1
                        if pkt.cohort:
                            self.m["cohort_terminal"][c] += 1
        pend = self._pending
        rp, rb = self._rewards(deliv, used, power_total, se_sum)
        cost = self._cost_vector(pend, deliv, power_total)
        for c in (0, 1):
            self.m["delivered"][c] += deliv[c]; self.m["retx_exhausted"][c] += rexh[c]
            self.m["deadline_viol"][c] += pend["dvl"][c]
        self.m["reward_primary"] += rp; self.m["reward_base"] += rb
        self.m["cost_sum"] += cost
        if self.phase == "measure":
            self.m["meas_power_sum"] += power_total; self.m["subch_used"] += used
            self.m["meas_slots"] += 1
            for k in by_dev:
                self.m["alloc_count"][k] += len(by_dev[k])
        else:
            self.m["drain_energy_j"] += power_total * self.cfg.tau_s
        # queue metrics
        for k in range(self.K):
            self.m["qlen_samples"].append(len(self.queues[k]))
            if self.queues[k]:
                self.m["hol_samples"].append(self.t - self.queues[k][0].arrival_slot)
            self.m["qmax"] = max(self.m["qmax"], len(self.queues[k]))
        # advance
        self._advance_channel_and_mobility()
        self.t += 1
        self._slot_open = False; self._s_frozen = None
        # phase transition + termination
        if self.phase == "measure" and self.t >= self.cfg.t_meas_slots:
            self.phase = "drain"; self._drain_start = self.t
        done = False
        if self.phase == "drain":
            if self.cohort_outstanding() == 0 or (self.t - self._drain_start) >= self.cfg.drain_cap_slots:
                done = True
        info = {"reward_primary": rp, "reward_base": rb, "cost": cost, "phase": self.phase,
                "pending": pend, "deliv": deliv, "power_w": power_total, "used": used}
        return (None if done else self.begin_slot()), rp, rb, cost, done, info

    def _advance_channel_and_mobility(self):
        self.mob.step(self.rng)
        self._advance_channel()
        self.csi_buffer.append(self.cur_gain.copy())

    # ------------------------------------------------------------- reward/cost
    def _rewards(self, deliv, used, power_total, se_sum=0.0):
        d = sum(deliv)
        util = used / self.N
        hol = (sum((self.t - self.queues[k][0].arrival_slot) for k in range(self.K) if self.queues[k])
               / (self.K * max(self.cfg.deadline_static, 1)))
        energy = power_total / (self.N * self.cfg.p_max_w)
        # spectral-efficiency shaping (w7): normalised mean SE over the N subchannels; rewards good
        # beam/power selection (SE depends on SINR hence beam) — a preregistered confirmatory
        # objective aligned with the accepted title ('Beamforming and Dynamic Spectrum Allocation').
        se_norm = se_sum / (self.N * max(math.log2(1 + self.cfg.n_antennas), 1e-9))
        w7 = getattr(self.cfg, "w7_se", 0.0)
        rp = 1.0 * d - 0.1 * hol + 0.1 * util + w7 * se_norm
        dv = self._pending["dvl"]; ov = self._pending["ovf"]
        rb = 1.0 * d - 0.5 * sum(dv) - 0.5 * sum(ov) - 0.1 * hol - 0.1 * energy + 0.1 * util
        return rp, rb

    def _cost_vector(self, pend, deliv, power_total):
        cfg = self.cfg
        floor = (cfg.delivery_floor_static, cfg.delivery_floor_mobile)
        eps = (cfg.eps_static, cfg.eps_mobile)
        eta = (cfg.eta_static, cfg.eta_mobile)
        out = []
        for c in (0, 1):
            a = pend["arr"][c] + pend["ovf"][c]     # generated cohort arrivals for this class
            out.append(floor[c] * a - deliv[c])      # C_rel,c = delivery_floor*arrivals - deliveries
            out.append(pend["dvl"][c] - eps[c] * a)  # C_dv,c
            out.append(pend["ovf"][c] - eta[c] * a)  # C_over,c
        c_pow = (power_total - cfg.p_bar_w) if self.phase == "measure" else 0.0   # C_pow measurement-only
        out.append(c_pow)
        return np.array(out, dtype=float)

    # ------------------------------------------------------------- observation
    def slot_observation(self):
        cfg = self.cfg
        stale = self.stale_gain()
        feats = [self.t / max(cfg.t_meas_slots, 1)]
        for k in range(self.K):
            q = self.queues[k]
            feats += [len(q) / max(self._qcap(k), 1),
                      ((self.t - q[0].arrival_slot) / max(self._deadline(k), 1)) if q else 0.0,
                      1.0 if self._is_mobile(k) else 0.0, 1.0 if self.los[k] else 0.0,
                      self.d3d[k] / max(cfg.hall_x, 1.0), self.pl_db[k] / 150.0]
        feats += list((stale / max(cfg.n_antennas, 1)).ravel())    # full K x N x B stale beam info
        feats += [0.0] * self.K + [0.0] * self.K + [0.0] * self.N   # decode context slots
        return np.array(feats, dtype=float)

    def beam_feature_vector(self, n_index):
        """Per-token stale-beam-gain feature over the alphabet: for token (k,b,p) the value is the
        observed STALE gain g_stale[k, n, b] (normalised by M); idle = 0. This gives a beam-aware
        policy a direct, learnable inductive bias to prefer high-stale-gain beams."""
        stale = self.stale_gain()
        feat = np.zeros(self.cfg.alphabet_size)
        n = n_index - 1
        norm = max(self.cfg.n_antennas, 1)
        for k in range(self.K):
            base = 1 + k * self.B * self.P
            for b in range(self.B):
                val = stale[k, n, b] / norm
                bp = base + b * self.P
                feat[bp:bp + self.P] = val
        return feat

    def decoder_observation(self, base_obs, prefix, n_index):
        obs = base_obs.copy()
        off = 1 + self.FEATS_PER_DEV * self.K + self.K * self.N * self.B
        counts, committed = {}, {}
        for tok in prefix:
            if tok == IDLE:
                continue
            k, p = int(tok[0][1:]), int(tok[2][1:])
            counts[k] = counts.get(k, 0) + 1
            committed[k] = committed.get(k, 0.0) + float(self.cfg.power_grid_w[p])
        for k in range(self.K):
            obs[off + k] = counts.get(k, 0) / max(self.n_max[f"d{k}"], 1)
            obs[off + self.K + k] = committed.get(k, 0.0) / max(self.cfg.per_device_total_cap_w, 1e-9)
        obs[off + 2 * self.K + (n_index - 1)] = 1.0
        return obs

    # ------------------------------------------------------------- metrics
    def _reset_metrics(self):
        z2 = lambda: [0, 0]
        self._last_beam = {}
        self.m = {
            "generated": z2(), "delivered": z2(), "overflow": z2(), "deadline_viol": z2(),
            "retx_exhausted": z2(), "drop_deadline": z2(), "drop_retx": z2(),
            "cohort_gen": z2(), "cohort_delivered": z2(), "cohort_terminal": z2(),
            "latency": [[], []], "qlen_samples": [], "hol_samples": [], "qmax": 0,
            "meas_power_sum": 0.0, "subch_used": 0, "meas_slots": 0, "drain_energy_j": 0.0,
            "alloc_count": {k: 0 for k in range(self.K)}, "throughput_bits": 0.0,
            "beam_attempts": 0, "beam_match_oracle": 0, "beam_match_stale": 0, "beam_switches": 0,
            "gain_ratio_sum": 0.0, "gain_ratio_n": 0,
            "reward_primary": 0.0, "reward_base": 0.0, "cost_sum": np.zeros(self.cfg.j_cost),
        }

    @staticmethod
    def _pct(x, q):
        return float(np.percentile(x, q)) if len(x) else 0.0

    def episode_metrics(self):
        m = self.m; cfg = self.cfg
        gen = sum(m["generated"]); dvd = sum(m["delivered"])
        lat_all = m["latency"][0] + m["latency"][1]
        meas_slots = max(m["meas_slots"], 1)
        avg_power = m["meas_power_sum"] / meas_slots
        se = m["throughput_bits"] / (meas_slots * cfg.n_subchannels * cfg.bandwidth_hz * cfg.tau_s)
        ee = m["throughput_bits"] / max(m["meas_power_sum"] * cfg.tau_s + m["drain_energy_j"], 1e-12)
        alloc = np.array([m["alloc_count"][k] for k in range(self.K)], dtype=float)
        jain = (alloc.sum() ** 2) / (self.K * (alloc ** 2).sum()) if (alloc ** 2).sum() > 0 else 1.0
        out = {
            "generated": gen, "delivered": dvd,
            "gen_static": m["generated"][0], "gen_mobile": m["generated"][1],
            "dlv_static": m["delivered"][0], "dlv_mobile": m["delivered"][1],
            "pdr": dvd / max(gen, 1),
            "pdr_static": m["delivered"][0] / max(m["generated"][0], 1),
            "pdr_mobile": m["delivered"][1] / max(m["generated"][1], 1),
            "drop_deadline": sum(m["drop_deadline"]), "drop_overflow": sum(m["overflow"]),
            "drop_retx": sum(m["drop_retx"]),
            "cohort_residual": self.cohort_outstanding(),
            "lat_mean": float(np.mean(lat_all)) if lat_all else 0.0,
            "lat_p50": self._pct(lat_all, 50), "lat_p95": self._pct(lat_all, 95),
            "lat_p99": self._pct(lat_all, 99),
            "jitter": float(np.std(lat_all)) if lat_all else 0.0,
            "dv_ratio": sum(m["deadline_viol"]) / max(gen, 1),
            "dv_ratio_static": m["deadline_viol"][0] / max(m["generated"][0], 1),
            "dv_ratio_mobile": m["deadline_viol"][1] / max(m["generated"][1], 1),
            "q_mean": float(np.mean(m["qlen_samples"])) if m["qlen_samples"] else 0.0,
            "q_p95": self._pct(m["qlen_samples"], 95), "q_max": m["qmax"],
            "hol_mean": float(np.mean(m["hol_samples"])) if m["hol_samples"] else 0.0,
            "overflow_ratio": sum(m["overflow"]) / max(gen, 1),
            "throughput_bps": m["throughput_bits"] / (meas_slots * cfg.tau_s),
            "spectral_eff": se, "energy_eff": ee,
            "avg_power_w": avg_power, "drain_energy_j": m["drain_energy_j"],
            "subch_util": m["subch_used"] / (meas_slots * cfg.n_subchannels),
            "jain_fairness": float(jain),
            "beam_acc_oracle": m["beam_match_oracle"] / max(m["beam_attempts"], 1),
            "beam_acc_stale": m["beam_match_stale"] / max(m["beam_attempts"], 1),
            "beam_switch_rate": m["beam_switches"] / max(m["beam_attempts"], 1),
            "gain_ratio": m["gain_ratio_sum"] / max(m["gain_ratio_n"], 1),
            "reward_primary": m["reward_primary"], "reward_base": m["reward_base"],
        }
        cs = m["cost_sum"]
        for i, name in enumerate(["C_rel_static", "C_dv_static", "C_over_static",
                                  "C_rel_mobile", "C_dv_mobile", "C_over_mobile", "C_pow"]):
            out[name] = float(cs[i])
        return out
