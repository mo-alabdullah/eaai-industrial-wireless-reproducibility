#!/usr/bin/env python3
"""PPO family (M2, r35 repaired) — pure numpy, fully bound to the locked LPPO config (§13).

Modes / methods:
  unconstrained  — BSA-Unconstrained-PPO (full Layer-2 action; primary reward; no constraints).
  penalty        — BSA-Penalty-PPO (full action; primary reward minus soft constraint penalty).
  lagrangian     — BSA-C-PPO / SELECTED_LAGRANGIAN_PPO (full action; primal-dual constraint).
  + layer1=True  — Layer-1 Fixed-Radio Base PPO scheduler (radio fixed; only scheduling learned).

Structural guarantees: slot-level joint-autoregressive N-token action; ONE joint slot log-prob;
ONE PPO ratio/slot; ONE reward critic; ONE shared VECTOR cost critic (J_cost outputs);
gamma_cost=1; lambda_cost from config; projected multiplier update on raw episode-sum shortfalls;
FROZEN cost scales; ONE multiplier trajectory per seed; target-KL early stop; slot-sum entropy;
numerically-guarded joint log-ratio (no exp overflow). NO hidden hyperparameter defaults.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from .config import ScenarioConfig
from .env import IDLE, M2Env
import token_codec as tc


class MLP:
    def __init__(self, n_in, n_hidden, n_out, rng):
        self.W1 = rng.normal(0, np.sqrt(1.0 / n_in), (n_in, n_hidden)); self.b1 = np.zeros(n_hidden)
        self.W2 = rng.normal(0, np.sqrt(1.0 / n_hidden), (n_hidden, n_out)); self.b2 = np.zeros(n_out)

    def forward(self, x):
        h = np.tanh(x @ self.W1 + self.b1)
        return h @ self.W2 + self.b2, (x, h)

    def backward(self, cache, dout):
        x, h = cache
        x = np.atleast_2d(x); h = np.atleast_2d(h); dout = np.atleast_2d(dout)
        dW2 = h.T @ dout; db2 = dout.sum(0)
        dz1 = (dout @ self.W2.T) * (1 - h ** 2)
        return {"W1": x.T @ dz1, "b1": dz1.sum(0), "W2": dW2, "b2": db2}

    def apply(self, g, lr):
        self.W1 += lr * g["W1"]; self.b1 += lr * g["b1"]; self.W2 += lr * g["W2"]; self.b2 += lr * g["b2"]


def masked_softmax(logits, mask):
    z = np.where(mask, logits, -1e9); z = z - z.max()
    e = np.exp(z) * mask; s = e.sum()
    return e / s if s > 0 else mask / mask.sum()


class SlotRecord:
    __slots__ = ("base_obs", "dec_obs", "actions", "masks", "bfeats",
                 "joint_logp", "reward", "cost", "v_r", "v_c")

    def __init__(self, base_obs, dec_obs, actions, masks, bfeats, joint_logp, reward, cost, v_r, v_c):
        self.base_obs = base_obs; self.dec_obs = dec_obs; self.actions = actions; self.masks = masks
        self.bfeats = bfeats
        self.joint_logp = joint_logp; self.reward = reward; self.cost = cost; self.v_r = v_r; self.v_c = v_c


class PPOAgent:
    def __init__(self, cfg: ScenarioConfig, base_seed: int, mode: str = "lagrangian",
                 layer1: bool = False, hidden: int = None, lr: float = 3e-3, penalty_coeff: float = 5.0):
        assert mode in ("unconstrained", "penalty", "lagrangian")
        self.cfg = cfg
        self.base_seed = base_seed
        self.mode = mode
        self.layer1 = layer1
        self.lr = lr
        self.penalty_coeff = penalty_coeff
        lp = cfg.lppo                                  # §13: bind ALL params from the locked config
        self.gamma_slot = lp["gamma_slot"]; self.gae_lambda = lp["gae_lambda"]
        self.gamma_cost = lp["gamma_cost"]; self.lambda_cost = lp["lambda_cost"]
        self.clip = lp["ppo_clip_eps"]; self.entropy_coeff = lp["entropy_coeff"]
        self.value_coeff = lp["value_coeff"]; self.target_kl = lp["target_kl"]
        self.eta_lambda = lp["eta_lambda"]; self.A_floor = lp["A_floor"]
        self.n_ep = cfg.n_ep_train
        self.log_ratio_clip = 20.0
        self.rng = np.random.default_rng(base_seed)
        probe = M2Env(cfg, base_seed, layer1_fixed=layer1)
        self.obs_dim = probe.obs_dim; self.A = cfg.alphabet_size; self.J = cfg.j_cost
        h = hidden if hidden is not None else cfg.ppo_hidden
        self.policy = MLP(self.obs_dim, h, self.A, self.rng)
        self.v_reward = MLP(self.obs_dim, h, 1, self.rng)
        self.v_cost = MLP(self.obs_dim, h, self.J, self.rng)
        self.w_beam = 0.0                      # learnable beam-aware logit weight (inductive bias)
        self.multipliers = np.zeros(self.J)
        self.cost_scales = cfg.frozen_cost_scales()
        self._fixed_mask = self._build_fixed_radio_mask(probe) if layer1 else None
        self.history = {"reward": [], "kl": [], "entropy": [], "clipfrac": [], "multipliers": []}

    def _build_fixed_radio_mask(self, env):
        m = np.zeros(self.A, dtype=bool); m[tc.IDLE_ID] = True
        for k in range(env.K):
            tid = tc.encode_token(k, env.fixed_beam, env.fixed_power, env.K, env.B, env.P)
            m[tid] = True
        return m

    def _logits(self, obs):
        return self.policy.forward(obs)[0].ravel()

    def act_slot(self, env, base_obs, greedy=False):
        prefix, dec_obs, actions, masks, bfeats = [], [], [], [], []
        joint_logp = 0.0; ent = 0.0
        assigned, committed = {}, {}
        for n in range(1, env.N + 1):
            dobs = env.decoder_observation(base_obs, prefix, n)
            bfeat = env.beam_feature_vector(n)
            mask = env.fast_id_mask(assigned, committed)          # fast hot-loop mask
            if self._fixed_mask is not None:
                mask = mask & self._fixed_mask
                if not mask.any():
                    mask = np.zeros(self.A, dtype=bool); mask[tc.IDLE_ID] = True
            probs = masked_softmax(self._logits(dobs) + self.w_beam * bfeat, mask)
            aid = int(np.argmax(probs)) if greedy else int(self.rng.choice(self.A, p=probs))
            joint_logp += float(np.log(probs[aid] + 1e-12))
            lp = np.log(probs + 1e-12); ent += -float((probs * lp)[mask].sum())
            tok = env.id_to_token(aid)
            if tok != "idle":
                k, p = int(tok[0][1:]), int(tok[2][1:])
                assigned[k] = assigned.get(k, 0) + 1
                committed[k] = committed.get(k, 0.0) + float(env.cfg.power_grid_w[p])
            prefix.append(tok); dec_obs.append(dobs); actions.append(aid); masks.append(mask)
            bfeats.append(bfeat)
        return prefix, dec_obs, actions, masks, bfeats, joint_logp, ent

    def _reward_of(self, rp, rb, cost):
        if self.layer1:
            return rb
        if self.mode == "penalty":
            scaled = np.maximum(cost * self.cost_scales, 0.0).sum()
            return rp - self.penalty_coeff * scaled
        return rp   # unconstrained + lagrangian both shape on the primary reward

    def collect(self, update_idx=0):
        episodes = []
        for ep in range(self.n_ep):
            env = M2Env(self.cfg, self.base_seed * 100000 + update_idx * 1000 + ep, layer1_fixed=self.layer1)
            env.reset(); base_obs = env.begin_slot()
            recs = []; done = False
            while not done:
                prefix, dobs, acts, masks, bfeats, jlp, ent = self.act_slot(env, base_obs)
                vr = float(self.v_reward.forward(base_obs)[0].ravel()[0])
                vc = self.v_cost.forward(base_obs)[0].ravel().copy()
                nxt, rp, rb, cost, done, info = env.commit_action(prefix)
                recs.append(SlotRecord(base_obs, dobs, acts, masks, bfeats, jlp,
                                       self._reward_of(rp, rb, cost), cost, vr, vc))
                base_obs = nxt if nxt is not None else base_obs
            episodes.append(recs)
        return episodes

    def _gae(self, rewards, values, gamma, lam):
        T = len(rewards); adv = np.zeros(T); last = 0.0
        for t in reversed(range(T)):
            vnext = values[t + 1] if t + 1 < T else 0.0
            delta = rewards[t] + gamma * vnext - values[t]
            last = delta + gamma * lam * last; adv[t] = last
        return adv, adv + np.array(values)

    def update(self, episodes, epochs=4):
        slots, adv_r, ret_r, adv_c, ret_c = [], [], [], [], []
        for recs in episodes:
            ar, rr = self._gae([r.reward for r in recs], [r.v_r for r in recs], self.gamma_slot, self.gae_lambda)
            AC = np.zeros((len(recs), self.J)); RC = np.zeros((len(recs), self.J))
            for j in range(self.J):
                a, rt = self._gae([r.cost[j] for r in recs], [r.v_c[j] for r in recs],
                                  self.gamma_cost, self.lambda_cost)
                AC[:, j] = a; RC[:, j] = rt
            for i, r in enumerate(recs):
                slots.append(r); adv_r.append(ar[i]); ret_r.append(rr[i]); adv_c.append(AC[i]); ret_c.append(RC[i])
        adv_r = np.array(adv_r); ret_r = np.array(ret_r); adv_c = np.array(adv_c); ret_c = np.array(ret_c)
        old_logp = np.array([r.joint_logp for r in slots])
        if self.mode == "lagrangian" and not self.layer1:
            A = adv_r - adv_c @ (self.multipliers * self.cost_scales)
        else:
            A = adv_r
        A = (A - A.mean()) / (A.std() + 1e-8)

        # ---- flatten all decoder steps for a VECTORISED update ----
        DEC, ACT, MASK, BFEAT, slot_id = [], [], [], [], []
        for si, r in enumerate(slots):
            for dobs, aid, mask, bf in zip(r.dec_obs, r.actions, r.masks, r.bfeats):
                DEC.append(dobs); ACT.append(aid); MASK.append(mask); BFEAT.append(bf); slot_id.append(si)
        DEC = np.asarray(DEC); ACT = np.asarray(ACT, dtype=int)
        MASK = np.asarray(MASK, dtype=bool); BFEAT = np.asarray(BFEAT); slot_id = np.asarray(slot_id, dtype=int)
        S = len(ACT); nslot = len(slots)
        rows = np.arange(S)
        last_kl = last_clip = last_ent = 0.0
        for _ in range(epochs):
            logits, cache = self.policy.forward(DEC)              # [S, A] one matmul
            logits = logits + self.w_beam * BFEAT                 # beam-aware inductive bias
            z = np.where(MASK, logits, -1e9)
            z = z - z.max(axis=1, keepdims=True)
            e = np.exp(z) * MASK
            probs = e / np.clip(e.sum(axis=1, keepdims=True), 1e-12, None)
            logp = np.log(probs + 1e-12)
            step_logp = logp[rows, ACT]
            new_logp = np.bincount(slot_id, weights=step_logp, minlength=nslot)
            Hrow = -(probs * logp * MASK).sum(axis=1)
            lr_ratio = np.clip(new_logp - old_logp, -self.log_ratio_clip, self.log_ratio_clip)
            ratio = np.exp(lr_ratio)
            unclipped = ratio * A
            clipped = np.clip(ratio, 1 - self.clip, 1 + self.clip) * A
            coeff = np.where(unclipped <= clipped, ratio * A, 0.0)     # PPO min-branch
            last_clip = float(np.mean(unclipped > clipped))
            csel = coeff[slot_id]                                    # [S]
            dlog = -csel[:, None] * probs
            dlog[rows, ACT] += csel
            dent = self.entropy_coeff * probs * (-logp - Hrow[:, None]) * MASK
            dout = dlog + dent
            g = self.policy.backward(cache, dout)
            self.policy.apply({k: v / max(S, 1) for k, v in g.items()}, self.lr)
            self.w_beam += 20.0 * self.lr * float((dout * BFEAT).sum()) / max(S, 1)   # dedicated beam-weight lr
            last_kl = float(np.mean(old_logp - new_logp)); last_ent = float(np.mean(Hrow))
            if abs(last_kl) > 1.5 * self.target_kl:
                break

        self._fit_critic(self.v_reward, [r.base_obs for r in slots], ret_r.reshape(-1, 1))
        self._fit_critic(self.v_cost, [r.base_obs for r in slots], ret_c)
        if self.mode == "lagrangian" and not self.layer1:
            ep_short = np.array([np.sum([r.cost for r in recs], axis=0) for recs in episodes])
            Chat = ep_short.mean(0)
            self.multipliers = np.maximum(0.0, self.multipliers + self.eta_lambda * self.cost_scales * Chat)
        mr = float(np.mean([sum(r.reward for r in recs) for recs in episodes]))
        self.history["reward"].append(mr); self.history["kl"].append(last_kl)
        self.history["entropy"].append(last_ent); self.history["clipfrac"].append(last_clip)
        self.history["multipliers"].append(self.multipliers.copy())
        return {"mean_reward": mr, "kl": last_kl, "clipfrac": last_clip, "entropy": last_ent,
                "multipliers": self.multipliers.copy()}

    def _fit_critic(self, critic, obs_list, targets, steps=2, lr=5e-3):
        X = np.asarray(obs_list); T = np.asarray(targets)          # [N, obs], [N, out]
        for _ in range(steps):
            out, cache = critic.forward(X)                          # [N, out] one matmul
            err = out - T
            g = critic.backward(cache, err)
            critic.apply({k: -v / len(X) for k, v in g.items()}, lr)

    def train(self, n_updates=None):
        n = n_updates if n_updates is not None else self.cfg.n_updates
        for u in range(n):
            self.update(self.collect(u), epochs=4)
        return self.history

    def evaluate_metrics(self, n_ep=3, seed_offset=777):
        agg = None
        for ep in range(n_ep):
            env = M2Env(self.cfg, self.base_seed + seed_offset + ep, layer1_fixed=self.layer1)
            env.reset(); base_obs = env.begin_slot(); done = False
            while not done:
                prefix, *_ = self.act_slot(env, base_obs, greedy=True)
                nxt, rp, rb, cost, done, info = env.commit_action(prefix)
                base_obs = nxt if nxt is not None else base_obs
            m = env.episode_metrics()
            agg = {k: [v] for k, v in m.items()} if agg is None else \
                {k: agg[k] + [m[k]] for k in agg}
        return {k: float(np.mean(v)) for k, v in agg.items()}
