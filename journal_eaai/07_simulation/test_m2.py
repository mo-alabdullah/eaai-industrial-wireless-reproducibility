#!/usr/bin/env python3
"""M2 acceptance + regression tests (r35 repaired) — executable form of test_plan.md.

Directly catches every independent-review defect from r34. Runner: unittest.
Run:  python3 -m unittest -v test_m2   (from 07_simulation/)
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from m2 import channel as ch
from m2 import baselines as B
from m2.config import load_primary, small_config, campaign_config, ScenarioConfig
from m2.env import IDLE, M2Env, InvalidActionError
from m2.agents_ppo import PPOAgent, masked_softmax
import token_codec as tc


def _cfg(p=0.4):
    return small_config(p)


# ---------------------------------------------------------- channel / PHY
class TestChannel(unittest.TestCase):
    def test_noise_power_formula(self):
        self.assertAlmostEqual(ch.noise_power_w(290.0, 1e6, 7.0),
                               1.380649e-23 * 290.0 * 1e6 * 10 ** 0.7, places=25)

    def test_infsh_nlos_exact(self):
        d, fc = 100.0, 3.5
        sh = 32.4 + 23.0 * math.log10(d) + 20.0 * math.log10(fc)
        self.assertAlmostEqual(ch.pl_nlos_infsh_db(d, fc), max(sh, ch.pl_los_db(d, fc)), places=9)
        self.assertEqual(ch.SF_NLOS_SH_DB, 5.9)

    def test_infdh_distinct_from_infsh(self):
        d, fc = 100.0, 3.5
        dh = 33.63 + 21.9 * math.log10(d) + 20.0 * math.log10(fc)
        self.assertAlmostEqual(ch.pl_nlos_infdh_db(d, fc), max(dh, ch.pl_los_db(d, fc)), places=9)
        self.assertNotAlmostEqual(ch.pl_nlos_infsh_db(d, fc), ch.pl_nlos_infdh_db(d, fc), places=3)

    def test_derived_los_probability_parameter(self):
        k = ch.infsh_k_subce(0.20, 10.0, 5.0, 8.0, 1.5)
        expect = (-10.0 / math.log(0.8)) * (6.5 / 3.5)
        self.assertAlmostEqual(k, expect, places=6)
        self.assertAlmostEqual(load_primary().k_subce_m, expect, places=6)
        self.assertNotAlmostEqual(k, 76.0, places=1)     # replaced the unexplained 76 m

    def test_packet_bits_thresholds(self):
        cfg = load_primary()
        self.assertAlmostEqual(ch.required_spectral_efficiency(cfg.pkt_bits_static, cfg.bandwidth_hz, cfg.tau_s), 2.048)
        self.assertAlmostEqual(ch.required_spectral_efficiency(cfg.pkt_bits_mobile, cfg.bandwidth_hz, cfg.tau_s), 0.512)

    def test_packet_success_boundary(self):
        cfg = load_primary(); nw = ch.noise_power_w(cfg.temperature_k, cfg.bandwidth_hz, cfg.noise_figure_db)
        # SINR giving SE just above/below 2.048 for static (2048 bits)
        sinr_hi = 2 ** 2.048 - 1 + 1e-6
        sinr_lo = 2 ** 2.048 - 1 - 1e-3
        # build power*beta*G to hit those SINRs
        for sinr, ok in [(sinr_hi, True), (sinr_lo, False)]:
            pbg = sinr * nw
            r = ch.link_success(pbg, 1.0, 1.0, nw, cfg.bandwidth_hz, cfg.tau_s, cfg.pkt_bits_static)
            self.assertEqual(r.success, ok)
        # mobile threshold 0.512
        sinr_m = 2 ** 0.512 - 1 + 1e-6
        r = ch.link_success(sinr_m * nw, 1.0, 1.0, nw, cfg.bandwidth_hz, cfg.tau_s, cfg.pkt_bits_mobile)
        self.assertTrue(r.success)

    def test_correlated_channel_determinism(self):
        e1 = M2Env(_cfg(), 4); e2 = M2Env(_cfg(), 4)
        for _ in range(6):
            e1._advance_channel(); e2._advance_channel()
        self.assertTrue(np.allclose(e1.cur_gain, e2.cur_gain))

    def test_fading_correlation_modes(self):
        indep = ch_jakes = None
        rho_j = ch.jakes_ar1_coeff(2.0, 3.5, 1e-3)
        self.assertTrue(0.9 < rho_j <= 1.0)          # slow fading at 1ms/2mps
        self.assertAlmostEqual(ch.jakes_ar1_coeff(0.0, 3.5, 1e-3), 1.0)


# ---------------------------------------------------------- slot order / feasibility
class TestSlotAndFeasibility(unittest.TestCase):
    def test_same_slot_arrivals_visible_before_action(self):
        cfg = ScenarioConfig(**{**_cfg().__dict__, "arrival_p": 1.0})
        env = M2Env(cfg, 3); env.reset()
        env.begin_slot()
        feas = env.feasible_tokens([], 1)
        self.assertTrue(any(t != IDLE for t in feas), "arrivals at slot start not visible to action")

    def test_reject_wrong_length(self):
        env = M2Env(_cfg(), 1); env.reset(); env.begin_slot()
        with self.assertRaises(InvalidActionError):
            env.commit_action([IDLE] * (env.N - 1))

    def test_reject_malformed_token(self):
        env = M2Env(_cfg(), 1); env.reset(); env.begin_slot()
        with self.assertRaises(InvalidActionError):
            env.commit_action([("d0", "b0")] + [IDLE] * (env.N - 1))

    def test_reject_nmax_and_cap_violation(self):
        # arrival_p=1 so d0 has packets; N_max_static=2 in small cfg -> 3 tokens for d0 illegal
        cfg = ScenarioConfig(**{**_cfg().__dict__, "arrival_p": 1.0})
        env = M2Env(cfg, 2); env.reset(); env.begin_slot()
        with self.assertRaises(InvalidActionError):
            env.commit_action([("d0", "b0", "p1"), ("d0", "b0", "p1"), ("d0", "b0", "p1")])

    def test_reject_packet_surplus(self):
        # a device with only 1 queued packet cannot get 2 non-idle tokens
        cfg = ScenarioConfig(**{**_cfg().__dict__, "arrival_p": 1.0})
        env = M2Env(cfg, 9); env.reset(); env.begin_slot()
        # find a device with exactly 1 packet
        k = next((k for k in range(env.K) if len(env.queues[k]) == 1), None)
        if k is not None:
            tok = (f"d{k}", "b0", "p0")
            with self.assertRaises(InvalidActionError):
                env.commit_action([tok, tok] + [IDLE] * (env.N - 2))

    def test_env_is_final_authority(self):
        # even if an agent hands the env a plausible but over-cap action, env must reject
        env = M2Env(_cfg(), 1); env.reset(); env.begin_slot()
        with self.assertRaises(InvalidActionError):
            env.commit_action([("d0", "b0", "p1")] * env.N)


# ---------------------------------------------------------- observation / beam info
class TestObservation(unittest.TestCase):
    def test_full_stale_beam_info_present(self):
        env = M2Env(_cfg(), 1); env.reset(); obs = env.begin_slot()
        # base obs contains K*N*B stale beam values
        self.assertGreaterEqual(len(obs), 1 + env.FEATS_PER_DEV * env.K + env.K * env.N * env.B)

    def test_same_max_different_best_beam_changes_obs(self):
        env = M2Env(_cfg(), 1); env.reset()
        g1 = np.zeros((env.K, env.N, env.B)); g2 = np.zeros((env.K, env.N, env.B))
        # identical max value (1.0) but different argmax beam
        g1[:, :, 0] = 1.0; g1[:, :, 1] = 0.5
        g2[:, :, 1] = 1.0; g2[:, :, 0] = 0.5
        env.csi_buffer[0] = g1; o1 = env.slot_observation()
        env.csi_buffer[0] = g2; o2 = env.slot_observation()
        self.assertFalse(np.allclose(o1, o2), "decoder cannot distinguish best-beam identity")


# ---------------------------------------------------------- costs / drain / scales
class TestCostsDrain(unittest.TestCase):
    def test_delivery_floor_cost_semantics(self):
        env = M2Env(_cfg(), 5); env.reset(); env.begin_slot()
        pend = {"arr": [3, 0], "ovf": [0, 0], "dvl": [0, 0]}
        env._pending = pend
        cost = env._cost_vector(pend, [2, 0], 0.0)
        # C_rel_static = floor*arrivals - delivered = 0.99*3 - 2
        self.assertAlmostEqual(cost[0], env.cfg.delivery_floor_static * 3 - 2)

    def test_full_drain_zero_residual_and_no_drain_arrivals(self):
        env = M2Env(_cfg(0.4), 6)
        m = B.run_episode(env, B.EDFAgent(env, 0))
        self.assertEqual(m["cohort_residual"], 0)
        # generated only during measurement: generated == cohort_gen
        self.assertEqual(m["generated"], sum(env.m["cohort_gen"]))

    def test_c_pow_measurement_only(self):
        env = M2Env(_cfg(0.4), 5); env.reset(); obs = env.begin_slot(); ag = B.MaxSINROracleAgent(env, 0)
        done = False; drain_cpow = 0.0
        while not done:
            phase_before = env.phase
            obs, rp, rb, cost, done, info = env.commit_action(ag.act(obs))
            if phase_before == "drain":
                drain_cpow += abs(cost[6])
        self.assertEqual(drain_cpow, 0.0)

    def test_c_pow_non_vacuous_confirmatory(self):
        # r36 §4: with N=4, P_max=0.4, P_bar=0.8 there exist FEASIBLE actions with P_t > P_bar,
        # so C_pow is non-vacuous; a deliberately high-power fixture violates C_pow (cost > 0).
        from m2.config import confirmatory_config
        cfg = ScenarioConfig(**{**confirmatory_config(0.4).__dict__, "arrival_p": 1.0})
        self.assertAlmostEqual(cfg.p_bar_w, 0.8)
        env = M2Env(cfg, 20001); env.reset(); env.begin_slot()
        # four devices each with >=1 queued packet, one 0.4 W token each on the 4 subchannels
        pmax_idx = cfg.n_power_levels - 1
        devs = [k for k in range(env.K) if len(env.queues[k]) >= 1][:env.N]
        self.assertEqual(len(devs), env.N)
        tokens = [(f"d{devs[n]}", "b0", f"p{pmax_idx}") for n in range(env.N)]
        # feasible (each device under its 0.8 W cap; distinct devices) and P_t = 4*0.4 = 1.6 > 0.8
        obs, rp, rb, cost, done, info = env.commit_action(tokens)
        self.assertAlmostEqual(info["power_w"], env.N * cfg.p_max_w)
        self.assertGreater(info["power_w"], cfg.p_bar_w)             # feasible action exceeds P_bar
        self.assertAlmostEqual(cost[6], env.N * cfg.p_max_w - cfg.p_bar_w)  # C_pow violated (>0)
        self.assertGreater(cost[6], 0.0)

    def test_cost_scales_frozen_across_loads(self):
        base = None
        for p in (0.05, 0.10, 0.20, 0.30, 0.40):
            s = campaign_config(p).frozen_cost_scales()
            if base is None:
                base = s
            self.assertTrue(np.allclose(s, base), f"cost scales changed at load {p}")


# ---------------------------------------------------------- mobility
class TestMobility(unittest.TestCase):
    def test_waypoint_determinism_and_bounds(self):
        e1 = M2Env(_cfg(), 4); e2 = M2Env(_cfg(), 4)
        for _ in range(30):
            e1.mob.step(e1.rng); e2.mob.step(e2.rng)
        for d1, d2 in zip(e1.mob.devices, e2.mob.devices):
            self.assertAlmostEqual(d1.x, d2.x); self.assertAlmostEqual(d1.y, d2.y)
            self.assertTrue(0 <= d1.x <= e1.cfg.hall_x and 0 <= d1.y <= e1.cfg.hall_y)

    def test_displacement_respects_speed(self):
        cfg = _cfg()
        env = M2Env(cfg, 7); env.reset()
        mob = env.mob
        for d in mob.devices:
            if d.is_mobile:
                px, py = d.x, d.y
                mob.step(env.rng)
                disp = math.hypot(d.x - px, d.y - py)
                self.assertLessEqual(disp, cfg.v_max_mps * cfg.tau_s + 1e-6)

    def test_turns_only_at_waypoints(self):
        cfg = _cfg(); env = M2Env(cfg, 7); env.reset()
        d = next(x for x in env.mob.devices if x.is_mobile)
        turns0 = d.seg_turns
        for _ in range(200):
            env.mob.step(env.rng)
        self.assertGreaterEqual(d.seg_turns, turns0)     # turns accumulate at waypoints, deterministic


# ---------------------------------------------------------- layers
class TestLayers(unittest.TestCase):
    def test_layer1_actions_fixed_radio(self):
        cfg = _cfg(0.4); env = M2Env(cfg, 5, layer1_fixed=True)
        ag = B.Layer1RandomAgent(env, 0); env.reset(); obs = env.begin_slot()
        done = False
        while not done:
            tokens = ag.act(obs)
            for tok in tokens:
                if tok != IDLE:
                    self.assertEqual(int(tok[1][1:]), env.fixed_beam)
                    self.assertEqual(int(tok[2][1:]), env.fixed_power)
            obs, *rest, done, info = env.commit_action(tokens)

    def test_bsa_unconstrained_uses_full_action(self):
        cfg = _cfg(0.4); ag = PPOAgent(cfg, 3, "unconstrained", layer1=False)
        env = M2Env(cfg, 3); env.reset(); obs = env.begin_slot()
        seen_nonfixed = False
        for _ in range(10):
            prefix, *_ = ag.act_slot(env, obs)
            for tok in prefix:
                if tok != IDLE and (int(tok[1][1:]) != env.fixed_beam or int(tok[2][1:]) != env.fixed_power):
                    seen_nonfixed = True
            obs, *rest, done, info = env.commit_action(prefix)
            if done:
                break
        self.assertTrue(seen_nonfixed, "unconstrained PPO restricted to fixed radio")

    def test_layer1_ppo_only_fixed_radio(self):
        cfg = _cfg(0.4); ag = PPOAgent(cfg, 3, "unconstrained", layer1=True)
        env = M2Env(cfg, 3, layer1_fixed=True); env.reset(); obs = env.begin_slot()
        for _ in range(6):
            prefix, *_ = ag.act_slot(env, obs)
            for tok in prefix:
                if tok != IDLE:
                    self.assertEqual((int(tok[1][1:]), int(tok[2][1:])), (env.fixed_beam, env.fixed_power))
            obs, *rest, done, info = env.commit_action(prefix)
            if done:
                break


# ---------------------------------------------------------- PPO config binding
class TestPPOConfig(unittest.TestCase):
    def test_config_propagation(self):
        cfg = _cfg()
        ag = PPOAgent(cfg, 1, "lagrangian")
        self.assertEqual(ag.gamma_cost, cfg.lppo["gamma_cost"])
        self.assertEqual(ag.lambda_cost, cfg.lppo["lambda_cost"])
        self.assertEqual(ag.clip, cfg.lppo["ppo_clip_eps"])
        self.assertEqual(ag.target_kl, cfg.lppo["target_kl"])
        # tamper: change the config value -> runtime agent changes
        cfg2 = ScenarioConfig(**{**cfg.__dict__, "lppo": {**cfg.lppo, "ppo_clip_eps": 0.111}})
        ag2 = PPOAgent(cfg2, 1, "lagrangian")
        self.assertEqual(ag2.clip, 0.111)

    def test_overflow_guard(self):
        cfg = _cfg(); ag = PPOAgent(cfg, 1, "lagrangian")
        # a huge log-ratio must not overflow exp (guard clips to +/-20)
        r = np.exp(np.clip(1e6, -ag.log_ratio_clip, ag.log_ratio_clip))
        self.assertTrue(np.isfinite(r))

    def test_vector_cost_critic_and_multiplier(self):
        cfg = _cfg(); ag = PPOAgent(cfg, 2, "lagrangian")
        env = M2Env(cfg, 2); env.reset(); obs = env.begin_slot()
        self.assertEqual(ag.v_cost.forward(obs)[0].ravel().shape, (cfg.j_cost,))
        self.assertEqual(ag.multipliers.shape, (cfg.j_cost,))
        for u in range(2):
            ag.update(ag.collect(u), epochs=1)
            self.assertTrue(np.all(ag.multipliers >= 0.0))

    def test_joint_logp_sum(self):
        cfg = _cfg(); ag = PPOAgent(cfg, 7, "lagrangian")
        env = M2Env(cfg, 7); env.reset(); obs = env.begin_slot()
        prefix, dobs, acts, masks, bfeats, jlp, ent = ag.act_slot(env, obs)
        recomputed = sum(float(np.log(masked_softmax(ag._logits(d) + ag.w_beam * bf, m)[a] + 1e-12))
                         for d, a, m, bf in zip(dobs, acts, masks, bfeats))
        self.assertAlmostEqual(jlp, recomputed, places=9)


# ---------------------------------------------------------- metrics + codec + determinism
class TestMetricsCodec(unittest.TestCase):
    def test_complete_metrics_schema(self):
        env = M2Env(_cfg(0.4), 8); m = B.run_episode(env, B.RandomAgent(env, 0))
        required = ["pdr", "pdr_static", "pdr_mobile", "drop_deadline", "drop_overflow", "drop_retx",
                    "cohort_residual", "lat_mean", "lat_p50", "lat_p95", "lat_p99", "jitter",
                    "dv_ratio", "q_mean", "q_p95", "q_max", "hol_mean", "overflow_ratio",
                    "throughput_bps", "spectral_eff", "energy_eff", "avg_power_w", "drain_energy_j",
                    "subch_util", "jain_fairness", "beam_acc_oracle", "beam_acc_stale",
                    "beam_switch_rate", "gain_ratio", "reward_primary",
                    "C_rel_static", "C_dv_static", "C_over_static", "C_rel_mobile", "C_dv_mobile",
                    "C_over_mobile", "C_pow"]
        for key in required:
            self.assertIn(key, m)
            self.assertTrue(np.isfinite(m[key]))

    def test_pdr_and_delivered_bounds(self):
        env = M2Env(_cfg(0.4), 8); m = B.run_episode(env, B.RandomAgent(env, 0))
        self.assertLessEqual(m["delivered"], m["generated"])
        self.assertTrue(0.0 <= m["pdr"] <= 1.0)

    def test_codec_roundtrip(self):
        cfg = _cfg(); K, Bc, P = cfg.n_devices, cfg.codebook_size, cfg.n_power_levels
        for tid in range(cfg.alphabet_size):
            dec = tc.decode_token(tid, K, Bc, P)
            if dec != "idle":
                self.assertEqual(tc.encode_token(*dec, K, Bc, P), tid)

    def test_no_post_hoc_repair_baselines(self):
        for A in B.ALL_LAYER2_BASELINES:
            env = M2Env(_cfg(0.4), 7); obs = None; env.reset(); obs = env.begin_slot(); ag = A(env, 0)
            done = False
            while not done:
                tokens = ag.act(obs)
                prefix = []
                for n, tok in enumerate(tokens, start=1):
                    self.assertIn(tok, env.feasible_tokens(prefix, n))
                    prefix.append(tok)
                obs, *rest, done, info = env.commit_action(tokens)

    def test_baseline_determinism(self):
        for A in B.ALL_LAYER2_BASELINES:
            def run():
                e = M2Env(_cfg(0.4), 5); a = A(e, 2); return B.run_episode(e, a)
            r1, r2 = run(), run()
            self.assertEqual(r1["pdr"], r2["pdr"], A.name)

    def test_j_cost_order(self):
        cfg = _cfg(); self.assertEqual(cfg.j_cost, 7)

    def test_primary_config_executes(self):
        cfg = load_primary()
        self.assertEqual((cfg.n_devices, cfg.codebook_size, cfg.n_power_levels, cfg.n_subchannels),
                         (8, 8, 4, 8))
        env = M2Env(cfg, 0); env.reset(); obs = env.begin_slot(); ag = B.MaxSINROracleAgent(env, 0)
        for _ in range(3):
            obs, *rest, done, info = env.commit_action(ag.act(obs))

    def test_smoke_training_runs(self):
        cfg = _cfg(0.4)
        for mode in ("unconstrained", "penalty", "lagrangian"):
            ag = PPOAgent(cfg, 3, mode)
            for u in range(3):
                info = ag.update(ag.collect(u), epochs=2)
                self.assertTrue(math.isfinite(info["mean_reward"]))
            ev = ag.evaluate_metrics(n_ep=2)
            self.assertTrue(0.0 <= ev["pdr"] <= 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
