#!/usr/bin/env python3
"""Exactness validation for the Stage-I optimisation benchmarks (I-H).

Run:  python3 -m pytest 13_journal_extension/tests/test_optimization_benchmark.py -q
or:   python3 13_journal_extension/tests/test_optimization_benchmark.py
"""
from __future__ import annotations
import os, sys, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "code"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "07_simulation"))

from optimization.radio import (SlotState, solve_exact_radio, brute_force_radio,
                                solve_exact_radio_fixed_demand, brute_force_fixed_demand,
                                solve_continuous_fixed_demand, continuous_cost_of_assignment,
                                cell_cost_continuous,
                                p_required, quantise_up, cell_cost, INF)
from optimization.capture import random_tiny_state


def test_quantise_up_semantics():
    g = (0.05, 0.1, 0.2, 0.4)
    assert quantise_up(g, 0.0) == 0
    assert quantise_up(g, 0.05) == 0
    assert quantise_up(g, 0.050000001) == 1
    assert quantise_up(g, 0.4) == 3
    assert quantise_up(g, 0.41) is None


def test_success_threshold_matches_channel_model():
    """p_required must be the exact inverse of the simulator's capacity test."""
    from m2 import channel as ch
    rng = np.random.default_rng(7)
    for _ in range(200):
        st = random_tiny_state(rng)
        k, n, b = 0, 0, 0
        pr = p_required(st, k, n, b)
        if not math.isfinite(pr):
            continue
        just_below = pr * (1 - 1e-9)
        just_above = pr * (1 + 1e-9)
        lo = ch.link_success(just_below, st.beta[k], st.gain_info[k, n, b], st.noise_w,
                             st.bandwidth_hz, st.tau_s, st.pkt_bits[k])
        hi = ch.link_success(just_above, st.beta[k], st.gain_info[k, n, b], st.noise_w,
                             st.bandwidth_hz, st.tau_s, st.pkt_bits[k])
        assert not lo.success and hi.success, (pr, lo.success, hi.success)


def test_exact_equals_brute_force_tiny():
    """I-H: >=20 random tiny states, exact equality of objective AND feasibility."""
    rng = np.random.default_rng(20260914)
    checked = 0
    for _ in range(60):
        st = random_tiny_state(rng)
        if sum(st.queue_len) == 0:
            continue
        for use_true in (False, True):
            fast = solve_exact_radio(st, use_true=use_true)
            ref = brute_force_radio(st, use_true=use_true)
            assert fast.served == ref.served, (fast.served, ref.served)
            assert abs(fast.power_w - ref.power_w) < 1e-12, (fast.power_w, ref.power_w)
        checked += 1
        if checked >= 25:
            break
    assert checked >= 20, f"only {checked} non-trivial states checked"


def test_service_frontier_matches_brute_force():
    """The per-service-level frontier (min power to serve exactly j packets) must equal the
    unrestricted brute-force frontier on tiny states. >=20 states."""
    import itertools
    from optimization.radio import p_required as _pr
    rng = np.random.default_rng(99)
    ok = 0
    for _ in range(60):
        st = random_tiny_state(rng)
        if sum(st.queue_len) == 0:
            continue
        a = solve_exact_radio(st)
        ref = {}
        P = len(st.power_grid)
        toks = [None] + [(k, b, p) for k in range(st.K) for b in range(st.B) for p in range(P)]
        for combo in itertools.product(toks, repeat=st.N):
            cnt, pw, tot, srv, good = {}, {}, 0.0, 0, True
            for n, t in enumerate(combo):
                if t is None:
                    continue
                k, b, pi = t
                p = st.power_grid[pi]
                if p + 1e-18 < _pr(st, k, n, b):
                    good = False; break
                c = cnt.get(k, 0) + 1
                if c > min(st.n_max[k], st.queue_len[k]):
                    good = False; break
                w = pw.get(k, 0.0) + p
                if w > st.per_device_cap_w + 1e-12:
                    good = False; break
                cnt[k], pw[k] = c, w; tot += p; srv += 1
            if not good:
                continue
            if srv not in ref or tot < ref[srv] - 1e-15:
                ref[srv] = tot
        assert set(a.frontier) == set(ref)
        for s_ in ref:
            assert abs(a.frontier[s_] - ref[s_]) < 1e-12
        ok += 1
        if ok >= 20:
            break
    assert ok >= 20


def test_fixed_demand_exact_equals_brute_force():
    """Pure radio-allocation subproblem (scheduling held fixed) against unrestricted brute force."""
    rng = np.random.default_rng(2026)
    ok = 0
    for _ in range(200):
        st = random_tiny_state(rng)
        elig = [k for k in range(st.K) if st.queue_len[k] > 0]
        if not elig:
            continue
        demand = {}
        room = st.N
        for k in elig:
            c = int(rng.integers(0, min(st.n_max[k], st.queue_len[k], room) + 1))
            if c:
                demand[k] = c; room -= c
            if room == 0:
                break
        if not demand:
            continue
        for use_true in (False, True):
            a = solve_exact_radio_fixed_demand(st, demand, use_true=use_true)
            b = brute_force_fixed_demand(st, demand, use_true=use_true)
            assert (math.isinf(a.power_w) and math.isinf(b.power_w)) or \
                   abs(a.power_w - b.power_w) < 1e-12, (a.power_w, b.power_w)
        ok += 1
        if ok >= 20:
            break
    assert ok >= 20, ok


def test_continuous_is_a_valid_lower_bound():
    """The continuous-power optimum must never exceed the grid optimum for the same demand, and
    refining the grid must move the grid optimum towards it (monotone squeeze)."""
    import dataclasses
    rng = np.random.default_rng(4242)
    ok = 0
    for _ in range(200):
        st = random_tiny_state(rng)
        elig = [k for k in range(st.K) if st.queue_len[k] > 0]
        if not elig:
            continue
        demand, room = {}, st.N
        for k in elig:
            c = int(rng.integers(0, min(st.n_max[k], st.queue_len[k], room) + 1))
            if c:
                demand[k] = c; room -= c
            if room == 0:
                break
        if not demand:
            continue
        g = solve_exact_radio_fixed_demand(st, demand)
        c = solve_continuous_fixed_demand(st, demand)
        if math.isinf(g.power_w) or math.isinf(c.power_w):
            continue
        assert c.power_w <= g.power_w + 1e-15, (c.power_w, g.power_w)
        finer = dataclasses.replace(st, power_grid=tuple(sorted(
            set(st.power_grid) | {v / m for v in st.power_grid for m in (2, 4, 8, 16, 32)})))
        gf = solve_exact_radio_fixed_demand(finer, demand)
        if not math.isinf(gf.power_w):
            assert gf.power_w <= g.power_w + 1e-15
            assert c.power_w <= gf.power_w + 1e-15
        ok += 1
        if ok >= 20:
            break
    assert ok >= 20, ok


def test_gap_decomposition_is_exact_and_nonnegative():
    """H_G - C  ==  (H_G - E_G) + (E_G - C_AG) + (C_AG - C), every term >= 0."""
    rng = np.random.default_rng(777)
    ok = 0
    for _ in range(300):
        st = random_tiny_state(rng)
        elig = [k for k in range(st.K) if st.queue_len[k] > 0]
        if not elig:
            continue
        demand, room = {}, st.N
        for k in elig:
            c = int(rng.integers(0, min(st.n_max[k], st.queue_len[k], room) + 1))
            if c:
                demand[k] = c; room -= c
            if room == 0:
                break
        if not demand:
            continue
        eg = solve_exact_radio_fixed_demand(st, demand)
        cc = solve_continuous_fixed_demand(st, demand)
        if math.isinf(eg.power_w) or math.isinf(cc.power_w):
            continue
        c_ag = continuous_cost_of_assignment(st, eg)
        assert eg.power_w - c_ag >= -1e-15, "rounding term negative"
        assert c_ag - cc.power_w >= -1e-15, "distortion term negative"
        total = eg.power_w - cc.power_w
        parts = (eg.power_w - c_ag) + (c_ag - cc.power_w)
        assert abs(total - parts) < 1e-15
        ok += 1
        if ok >= 25:
            break
    assert ok >= 25, ok


def test_beam_dominance_lemma():
    """Lemma 1: the gain-maximising beam minimises required power for every (k,n)."""
    rng = np.random.default_rng(11)
    for _ in range(50):
        st = random_tiny_state(rng)
        for k in range(st.K):
            for n in range(st.N):
                pr = [p_required(st, k, n, b) for b in range(st.B)]
                assert int(np.argmin(pr)) == int(np.argmax(st.gain_info[k, n, :]))


def test_power_dominance_lemma():
    """Lemma 2: the chosen level is the smallest grid level that succeeds."""
    rng = np.random.default_rng(12)
    for _ in range(50):
        st = random_tiny_state(rng)
        for k in range(st.K):
            for n in range(st.N):
                b, pi, w = cell_cost(st, k, n)
                if pi is None:
                    assert all(p + 1e-18 < p_required(st, k, n, bb)
                               for bb in range(st.B) for p in st.power_grid)
                    continue
                assert st.power_grid[pi] + 1e-18 >= p_required(st, k, n, b)
                if pi > 0:
                    assert st.power_grid[pi - 1] < p_required(st, k, n, b)


def test_constraints_respected():
    rng = np.random.default_rng(13)
    for _ in range(80):
        st = random_tiny_state(rng)
        a = solve_exact_radio(st)
        cnt, pw = {}, {}
        for n, t in enumerate(a.tokens):
            if t is None:
                continue
            k, b, pi = t
            cnt[k] = cnt.get(k, 0) + 1
            pw[k] = pw.get(k, 0.0) + st.power_grid[pi]
            assert 0 <= b < st.B
        for k in cnt:
            assert cnt[k] <= min(st.n_max[k], st.queue_len[k])
            assert pw[k] <= st.per_device_cap_w + 1e-12
        assert len(a.tokens) == st.N


def test_optimality_is_monotone_in_grid():
    """Adding lower power levels can never increase the optimal objective."""
    rng = np.random.default_rng(14)
    import dataclasses
    for _ in range(40):
        st = random_tiny_state(rng)
        if sum(st.queue_len) == 0:
            continue
        base = solve_exact_radio(st)
        finer = dataclasses.replace(st, power_grid=tuple(sorted(
            set(st.power_grid) | {st.power_grid[0] / 4.0, st.power_grid[0] / 16.0})))
        f = solve_exact_radio(finer)
        assert f.served >= base.served
        if f.served == base.served:
            assert f.power_w <= base.power_w + 1e-12


def test_aged_planner_uses_no_future_information():
    """The aged planner must not consult the realised channel: its plan, and the plan's believed
    value, must be invariant to gain_true. Perturbing gain_true alone must not change the plan."""
    import dataclasses as _dc
    import numpy as _np
    from optimization.joint import record_trace, solve_exact_joint
    cfg = _small_cfg()
    tr = record_trace(cfg, seed=700_000_000 + 10001 * 100, H=4, warmup=40)
    dl1, pw1, _n, _s, plan1 = solve_exact_joint(tr, use_true=False, return_plan=True)
    rng = _np.random.default_rng(5)
    perturbed = _dc.replace(tr, gain_true=tuple(
        g * _np.exp(rng.normal(0, 0.8, size=g.shape)) for g in tr.gain_true))
    dl2, pw2, _n, _s, plan2 = solve_exact_joint(perturbed, use_true=False, return_plan=True)
    assert plan1 == plan2, "aged plan changed when only the realised channel changed"
    assert dl1 == dl2 and abs(pw1 - pw2) < 1e-12


def _small_cfg(N=2, Ks=2, Km=1, grid="G2_wide10", dist=2.0, age=1):
    import dataclasses
    from evaluation import journal_cfg
    from optimization.grids import with_grid
    cfg = journal_cfg(0.40, t_meas=400, hall_x=300.0 * dist, hall_y=150.0 * dist, d_csi_slots=age)
    cfg = with_grid(cfg, grid)
    return dataclasses.replace(cfg, n_static=Ks, n_mobile=Km, n_subchannels=N,
                               n_max_static=min(cfg.n_max_static, N),
                               n_max_mobile=min(cfg.n_max_mobile, N))


def test_replay_model_matches_live_env():
    """I-H: the deterministic replay model must reproduce M2Env slot-for-slot under an IDENTICAL
    action sequence - otherwise the 'exact joint optimum' would be exact for the wrong system."""
    from m2.env import M2Env, IDLE
    from baselines_v2 import ComponentAgent
    from optimization.joint import record_trace, ReplayModel, slot_state, enumerate_actions
    H, WARM = 6, 20
    for seed_off in range(6):
        cfg = _small_cfg()
        seed = 700_000_000 + (10001 + seed_off) * 100
        tr = record_trace(cfg, seed=seed, H=H, warmup=WARM)

        rng = np.random.default_rng(1234 + seed_off)
        m = ReplayModel(tr)
        chosen = []
        for _ in range(H):
            m.begin_slot()
            st = slot_state(tr, m.i, m.queues)
            acts = enumerate_actions(tr, st, False)
            a = acts[int(rng.integers(0, len(acts)))] if acts else tuple([None] * tr.N)
            chosen.append(a)
            assert m.commit(a)

        env = M2Env(cfg, seed)
        ag = ComponentAgent(env, seed=seed, scheduler="EDF", beam_rule="StaleBest",
                            power_rule="MinFeasible-Stale")
        env.reset(); ag.reset()
        obs = env.begin_slot()
        for _ in range(WARM):
            nxt, *_r = env.commit_action(ag.act(obs))
            obs = nxt if nxt is not None else obs
        delivered = 0; power = 0.0
        for a in chosen:
            toks = [IDLE if x is None else (f"d{x[0]}", f"b{x[1]}", f"p{x[2]}") for x in a]
            nxt, rp, rb, cost, done, info = env.commit_action(toks)
            delivered += sum(info["deliv"]); power += info["power_w"]
            obs = nxt if nxt is not None else obs
            if done:
                break
        assert m.delivered == delivered, (m.delivered, delivered)
        assert abs(m.power - power) < 1e-12, (m.power, power)


def test_joint_dedup_matches_full_enumeration():
    """The de-duplicating breadth-first DP must equal exhaustive enumeration of every action
    sequence on instances small enough to enumerate in full (aged planner, believe_info=True)."""
    import itertools
    from optimization.joint import (record_trace, ReplayModel, slot_state, enumerate_actions,
                                    solve_exact_joint)
    for seed_off, H in ((0, 3), (1, 3), (2, 4)):
        cfg = _small_cfg(N=2, Ks=2, Km=1)
        tr = record_trace(cfg, seed=700_000_000 + (10001 + seed_off) * 100, H=H)
        dl, pw, _n, _s = solve_exact_joint(tr)

        best = (-1, float("inf"))

        def rec(model, depth):
            nonlocal best
            if depth == H:
                cand = (model.delivered, model.power)
                if cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1] - 1e-15):
                    best = cand
                return
            model.begin_slot()
            st = slot_state(tr, model.i, model.queues)
            for a in enumerate_actions(tr, st, False):
                m2 = ReplayModel(tr, believe_info=True)
                m2.queues = [[list(p) for p in q] for q in model.queues]
                m2.i, m2.delivered, m2.power = model.i, model.delivered, model.power
                if m2.commit(a):
                    rec(m2, depth + 1)

        rec(ReplayModel(tr, believe_info=True), 0)
        assert dl == best[0], (dl, best[0])
        assert abs(pw - best[1]) < 1e-12, (pw, best[1])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
