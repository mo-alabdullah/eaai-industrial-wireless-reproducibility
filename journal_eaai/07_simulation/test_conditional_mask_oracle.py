#!/usr/bin/env python3
"""Tests for the pure conditional-mask oracle (Gate-M1 design artifact).

Run: python3 -m unittest -v test_conditional_mask_oracle
"""
from __future__ import annotations

import unittest

from conditional_mask_oracle import IDLE, compute_token_mask

# A small model: 2 devices, 2 beams, 2 power levels (p1=1.0, p2=2.0); N=3 subchannels.
MODEL = {
    "devices": ["D1", "D2"],
    "beams": {"b1": 2.0, "b2": 0.5},
    "powers": {"p1": 1.0, "p2": 2.0},
    "N": 3,
    "n_max": {"D1": 3, "D2": 3},
    "beam_forbidden": set(),
    "power_forbidden": set(),
}


def _nonidle_for(mask, k):
    return {t for t in mask if t != IDLE and t[0] == k}


class TestConditionalMaskOracle(unittest.TestCase):
    def test_idle_always_available(self):
        # r29 §4: eligible/power_cap must cover every device; an all-zero-eligible state yields
        # only idle.
        mask = compute_token_mask({"eligible": {"D1": 0, "D2": 0},
                                   "power_cap": {"D1": 5.0, "D2": 5.0}}, [], 1, MODEL)
        self.assertIn(IDLE, mask)
        self.assertEqual(mask, frozenset({IDLE}))

    def test_after_all_eligible_reserved_no_nonidle_for_user(self):
        # D1 has exactly 1 eligible packet; a prefix already reserved it -> at the next
        # subchannel every non-idle D1 token is ABSENT (surplus must be explicit idle).
        state = {"eligible": {"D1": 1, "D2": 0}, "power_cap": {"D1": 5.0, "D2": 5.0}}
        prefix = [("D1", "b1", "p1")]           # D1's only packet reserved on subchannel 1
        mask = compute_token_mask(state, prefix, 2, MODEL)
        self.assertEqual(_nonidle_for(mask, "D1"), set())   # none for D1
        self.assertIn(IDLE, mask)                            # only idle remains for the surplus

    def test_no_masked_token_is_a_repair_case(self):
        # POSITIVE property: every token in the mask genuinely satisfies all feasibility rules,
        # so a sampled token never needs environment-side repair.
        state = {"eligible": {"D1": 2, "D2": 1}, "power_cap": {"D1": 2.0, "D2": 2.0}}
        prefix = [("D1", "b1", "p1")]           # D1 committed 1.0 W, 1 packet used
        mask = compute_token_mask(state, prefix, 2, MODEL)
        for tok in mask:
            if tok == IDLE:
                continue
            k, b, p = tok
            # remaining eligibility > 0
            used = sum(1 for t in prefix if t != IDLE and t[0] == k)
            self.assertGreater(state["eligible"][k] - used, 0, tok)
            # N_max respected
            self.assertLess(used, MODEL["n_max"][k], tok)
            # power cap respected (committed + this power <= cap)
            committed = sum(MODEL["powers"][t[2]] for t in prefix if t != IDLE and t[0] == k)
            self.assertLessEqual(committed + MODEL["powers"][p],
                                 state["power_cap"][k] + 1e-12, tok)
            # beam/power valid (no forbidden here)
            self.assertNotIn((2, b), MODEL["beam_forbidden"])
            self.assertNotIn((2, p), MODEL["power_forbidden"])

    def test_repeated_user_available_while_packet_and_nmax_remain(self):
        # D1 has 3 eligible packets and N_max 3; after one assignment both capacities remain,
        # so repeated-user (D1,*,*) tokens are STILL feasible.
        state = {"eligible": {"D1": 3, "D2": 0}, "power_cap": {"D1": 10.0, "D2": 10.0}}
        prefix = [("D1", "b1", "p1")]
        mask = compute_token_mask(state, prefix, 2, MODEL)
        self.assertTrue(_nonidle_for(mask, "D1"))          # repeated-user still allowed

    def test_repeated_user_blocked_when_nmax_reached(self):
        state = {"eligible": {"D1": 5, "D2": 0}, "power_cap": {"D1": 99.0, "D2": 99.0}}
        model = dict(MODEL); model["n_max"] = {"D1": 2, "D2": 2}
        prefix = [("D1", "b1", "p1"), ("D1", "b1", "p1")]   # 2 assigned == N_max
        mask = compute_token_mask(state, prefix, 3, model)
        self.assertEqual(_nonidle_for(mask, "D1"), set())   # cap reached -> only idle

    def test_power_cap_accounts_for_prefix_tokens(self):
        # cap D1 = 2.0; prefix committed p1=1.0. Then p2 (2.0) would give 3.0>2.0 -> masked;
        # p1 (1.0) gives 2.0<=2.0 -> allowed.
        state = {"eligible": {"D1": 3, "D2": 0}, "power_cap": {"D1": 2.0, "D2": 2.0}}
        prefix = [("D1", "b1", "p1")]
        mask = compute_token_mask(state, prefix, 2, MODEL)
        self.assertIn(("D1", "b1", "p1"), mask)             # 1.0+1.0=2.0 ok
        self.assertNotIn(("D1", "b1", "p2"), mask)          # 1.0+2.0=3.0 > cap
        self.assertNotIn(("D1", "b2", "p2"), mask)

    def test_beam_and_power_validity_masks(self):
        state = {"eligible": {"D1": 2, "D2": 0}, "power_cap": {"D1": 9.0, "D2": 9.0}}
        model = dict(MODEL)
        model["beam_forbidden"] = {(1, "b1")}
        model["power_forbidden"] = {(1, "p2")}
        mask = compute_token_mask(state, [], 1, model)
        self.assertFalse(any(t != IDLE and t[1] == "b1" for t in mask))   # b1 forbidden on n1
        self.assertFalse(any(t != IDLE and t[2] == "p2" for t in mask))   # p2 forbidden on n1
        self.assertIn(("D1", "b2", "p1"), mask)                            # the surviving token

    def test_matches_fixture4_surplus_semantics(self):
        # Fixture 4: D1 has 2 eligible packets on N=3 subchannels. After n1,n2 reserve both
        # packets, the ORACLE at n3 admits NO non-idle D1 token -> the surplus MUST be idle,
        # exactly what Fixture 4's explicit idle_action encodes (no post-hoc repair).
        state = {"eligible": {"D1": 2, "D2": 0}, "power_cap": {"D1": 5.0, "D2": 5.0}}
        prefix = [("D1", "b1", "p1"), ("D1", "b1", "p1")]   # both packets reserved on n1,n2
        mask = compute_token_mask(state, prefix, 3, MODEL)
        self.assertEqual(_nonidle_for(mask, "D1"), set())
        self.assertEqual(mask, frozenset({IDLE}))


class TestOracleHardening(unittest.TestCase):
    """r24 §11: a malformed prefix / bad index / unknown ID must be REJECTED, never used."""
    STATE = {"eligible": {"D1": 3, "D2": 3}, "power_cap": {"D1": 9.0, "D2": 9.0}}

    def test_subchannel_index_out_of_range(self):
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 0, MODEL)          # < 1
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [("D1", "b1", "p1")] * 4, 4, MODEL)  # > N (=3)

    def test_prefix_length_must_equal_index_minus_one(self):
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 2, MODEL)          # need len 1 at index 2
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [("D1", "b1", "p1")], 1, MODEL)  # need len 0 at idx 1

    def test_missing_N_rejected(self):
        m = dict(MODEL); m.pop("N")
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_n_primary_mismatch_rejected(self):
        m = dict(MODEL); m["n_primary"] = 8   # config says 8 but N=3
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_unknown_prefix_ids_rejected(self):
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [("D9", "b1", "p1")], 2, MODEL)   # unknown device
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [("D1", "b9", "p1")], 2, MODEL)   # unknown beam
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [("D1", "b1", "p9")], 2, MODEL)   # unknown power

    def test_prefix_token_infeasible_at_its_own_position_rejected(self):
        # D1 has only 1 eligible packet; a prefix that reserved it TWICE is infeasible at pos 2.
        state = {"eligible": {"D1": 1, "D2": 0}, "power_cap": {"D1": 9.0, "D2": 9.0}}
        bad_prefix = [("D1", "b1", "p1"), ("D1", "b1", "p1")]  # 2nd token had no eligible packet
        with self.assertRaises(ValueError):
            compute_token_mask(state, bad_prefix, 3, MODEL)

    def test_valid_prefix_still_works(self):
        # a well-formed prefix (feasible at every position) returns a mask normally
        state = {"eligible": {"D1": 3, "D2": 0}, "power_cap": {"D1": 9.0, "D2": 9.0}}
        mask = compute_token_mask(state, [("D1", "b1", "p1")], 2, MODEL)
        self.assertIn(IDLE, mask)


class TestOracleStrictInputs(unittest.TestCase):
    """r29 §4: eligible/power_cap/n_max must each cover EVERY canonical device — no missing
    value may silently default to 0/+inf, and unknown devices are rejected. Independent review
    found that an eligible device with no power_cap and empty n_max wrongly accepted a non-idle
    token; these tests lock that shut at the oracle level."""

    def test_missing_power_cap_rejected(self):
        # eligible present for both devices but NO power_cap at all -> reject (was +inf default)
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2}}, [], 1, MODEL)

    def test_partial_power_cap_rejected(self):
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2}, "power_cap": {"D1": 5.0}},
                               [], 1, MODEL)

    def test_missing_n_max_rejected(self):
        m = dict(MODEL); m.pop("n_max")
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2},
                                "power_cap": {"D1": 5.0, "D2": 5.0}}, [], 1, m)

    def test_partial_n_max_rejected(self):
        m = dict(MODEL); m["n_max"] = {"D1": 3}   # D2 missing
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2},
                                "power_cap": {"D1": 5.0, "D2": 5.0}}, [], 1, m)

    def test_partial_eligible_rejected(self):
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2}, "power_cap": {"D1": 5.0, "D2": 5.0}},
                               [], 1, MODEL)

    def test_unknown_device_in_state_rejected(self):
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2, "D9": 1},
                                "power_cap": {"D1": 5.0, "D2": 5.0, "D9": 5.0}}, [], 1, MODEL)

    def test_infinite_power_cap_rejected(self):
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2},
                                "power_cap": {"D1": float("inf"), "D2": 5.0}}, [], 1, MODEL)

    def test_eligible_device_without_cap_cannot_pass_nonidle(self):
        # the EXACT independent finding: an eligible device with no cap and empty n_max must NOT
        # yield a non-idle token — now it raises instead of silently accepting.
        m = dict(MODEL); m["n_max"] = {}
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {"D1": 2, "D2": 2}}, [], 1, m)


class TestOracleDomainSafety(unittest.TestCase):
    """r30 §2: the STANDALONE oracle validates its own mathematical domain — it must not accept
    an out-of-domain model even if a caller (or a spec) would have caught it upstream."""
    STATE = {"eligible": {"D1": 3, "D2": 3}, "power_cap": {"D1": 9.0, "D2": 9.0}}

    def test_n_max_greater_than_N_rejected(self):
        m = dict(MODEL); m["N"] = 1; m["n_max"] = {"D1": 999, "D2": 1}
        st = {"eligible": {"D1": 1, "D2": 1}, "power_cap": {"D1": 9.0, "D2": 9.0}}
        with self.assertRaises(ValueError):
            compute_token_mask(st, [], 1, m)

    def test_n_max_zero_rejected(self):
        # r31 §4: canonical domain is 1..N; N_max=0 (a disabled device) is not permitted here
        m = dict(MODEL); m["n_max"] = {"D1": 0, "D2": 3}
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_negative_power_value_rejected(self):
        m = dict(MODEL); m["powers"] = {"p1": -1.0, "p2": 2.0}
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_nan_power_value_rejected(self):
        m = dict(MODEL); m["powers"] = {"p1": float("nan"), "p2": 2.0}
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_inf_power_value_rejected(self):
        m = dict(MODEL); m["powers"] = {"p1": float("inf"), "p2": 2.0}
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_zero_power_value_rejected(self):
        m = dict(MODEL); m["powers"] = {"p1": 0.0, "p2": 2.0}
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_unknown_forbidden_beam_rejected(self):
        m = dict(MODEL); m["beam_forbidden"] = {(1, "bX")}   # bX not canonical
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_unknown_forbidden_power_rejected(self):
        m = dict(MODEL); m["power_forbidden"] = {(1, "pX")}  # pX not canonical
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)

    def test_out_of_range_forbidden_subchannel_rejected(self):
        m = dict(MODEL); m["beam_forbidden"] = {(9, "b1")}   # subchannel 9 > N (=3)
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)
        m2 = dict(MODEL); m2["power_forbidden"] = {(0, "p1")}  # subchannel 0 < 1
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m2)

    def test_empty_devices_rejected(self):
        m = dict(MODEL); m["devices"] = []
        with self.assertRaises(ValueError):
            compute_token_mask({"eligible": {}, "power_cap": {}}, [], 1, m)

    def test_duplicate_beam_ids_rejected(self):
        m = dict(MODEL); m["beams"] = ["b1", "b1"]
        with self.assertRaises(ValueError):
            compute_token_mask(self.STATE, [], 1, m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
