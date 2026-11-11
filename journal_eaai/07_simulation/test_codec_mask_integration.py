#!/usr/bin/env python3
"""Integration tests: token codec <-> conditional-mask oracle (r25 §8).

Proves the integer-index codec and the string-tuple oracle agree exactly through the single
canonical `OrderedModelSpec` bridge.
"""
import unittest

import codec_mask_integration as ci
import conditional_mask_oracle as oracle
import token_codec as codec
from codec_mask_integration import OrderedModelSpec


def base_spec(**over):
    kw = dict(
        device_order=("d0", "d1"),
        beam_order=("b0", "b1", "b2"),
        power_order=("p_lo", "p_hi"),
        version="v1",
        powers={"p_lo": 1.0, "p_hi": 2.0},
        n_max={"d0": 3, "d1": 3},
        n_primary=3,
    )
    kw.update(over)
    return OrderedModelSpec(**kw)


def base_state():
    return {"eligible": {"d0": 5, "d1": 5}, "power_cap": {"d0": 100.0, "d1": 100.0}}


class TestCodecMaskIntegration(unittest.TestCase):
    # 1. tuple mask and integer mask are identical
    def test_tuple_mask_equals_integer_mask(self):
        spec = base_spec()
        state = base_state()
        mp = spec.oracle_model_parameters(spec.n_primary)
        for idx, prefix_ids in ((1, []), (2, [0]), (2, [codec.encode_token(0, 1, 1, 2, 3, 2)]),
                                (3, [codec.encode_token(0, 0, 0, 2, 3, 2), 0])):
            prefix_tuples = [ci.decode_id(t, spec) for t in prefix_ids]
            oracle_set = oracle.compute_token_mask(state, prefix_tuples, idx, mp)
            oracle_ids = {ci.encode_tuple(t, spec) for t in oracle_set}
            mask = ci.compute_reference_boolean_token_mask(state, prefix_ids, idx, spec)
            int_ids = {i for i, on in enumerate(mask) if on}
            self.assertEqual(int_ids, oracle_ids,
                             f"tuple-mask != integer-mask at idx={idx} prefix={prefix_ids}")

    # 2. ordering changes are rejected unless the version is bumped
    def test_ordering_change_rejected_without_version_bump(self):
        spec = base_spec()
        sig = spec.canonical_signature()
        # same version, DIFFERENT device order -> must reject
        reordered = base_spec(device_order=("d1", "d0"))
        with self.assertRaises(ValueError):
            ci.require_spec_version(reordered, sig, "v1")
        # a genuine version bump is accepted
        reordered_v2 = base_spec(device_order=("d1", "d0"), version="v2")
        ci.require_spec_version(reordered_v2, sig, "v1")  # no raise
        # and reordering actually changes token semantics (different id for same tuple)
        self.assertNotEqual(ci.encode_tuple(("d1", "b0", "p_lo"), spec),
                            ci.encode_tuple(("d1", "b0", "p_lo"), reordered))

    # 3. dictionary insertion order cannot change token semantics
    def test_dict_insertion_order_invariant(self):
        spec_a = base_spec(powers={"p_lo": 1.0, "p_hi": 2.0})
        # same ordered tuples, powers dict built in the OPPOSITE insertion order
        spec_b = base_spec(powers={"p_hi": 2.0, "p_lo": 1.0})
        self.assertEqual(spec_a.canonical_signature(), spec_b.canonical_signature())
        state = base_state()
        for idx, prefix in ((1, []), (2, [0]), (3, [0, 0])):
            self.assertEqual(ci.compute_reference_boolean_token_mask(state, prefix, idx, spec_a),
                             ci.compute_reference_boolean_token_mask(state, prefix, idx, spec_b))

    # 4. encode/decode/mask round-trip holds for every token
    def test_round_trip_all_tokens(self):
        spec = base_spec()
        n = codec.alphabet_size(spec.K, spec.B, spec.P)
        self.assertEqual(n, 1 + spec.K * spec.B * spec.P)
        for tid in range(n):
            tok = ci.decode_id(tid, spec)
            self.assertEqual(ci.encode_tuple(tok, spec), tid)
        # mask length is exactly 1+K*B*P
        mask = ci.compute_reference_boolean_token_mask(base_state(), [], 1, spec)
        self.assertEqual(len(mask), n)

    # 5. malformed prefix ids fail
    def test_malformed_prefix_ids_fail(self):
        spec = base_spec()
        state = base_state()
        n = codec.alphabet_size(spec.K, spec.B, spec.P)
        # out-of-range integer id
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(state, [n + 5], 2, spec)
        # wrong prefix length for the position (oracle rejects)
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(state, [0, 0], 2, spec)
        # a prefix token that was NOT feasible at its own position (device with 0 eligible)
        starved = {"eligible": {"d0": 0, "d1": 5}, "power_cap": {"d0": 100.0, "d1": 100.0}}
        bad_id = codec.encode_token(0, 0, 0, spec.K, spec.B, spec.P)  # (d0,...) but d0 starved
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(starved, [bad_id], 2, spec)

    # ---- r26 §7: canonical-artifact order/version enforcement in the NORMAL mask path ----
    def test_changed_order_unchanged_version_rejected_in_mask_path(self):
        # reordered devices, SAME version -> compute_reference_boolean_token_mask itself must reject
        bad = base_spec(device_order=("d1", "d0"), n_max={"d1": 3, "d0": 3})
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(base_state(), [], 1, bad)

    def test_changed_signature_rejected(self):
        bad = base_spec(beam_order=("b0", "b1", "bX"))  # different id set -> different signature
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(base_state(), [], 1, bad)

    def test_changed_n_primary_rejected(self):
        bad = base_spec(n_primary=5)  # != canonical N_primary=3
        with self.assertRaises(ValueError):
            ci.compute_reference_boolean_token_mask(base_state(), [], 1, bad)

    def test_missing_canonical_spec_rejected(self):
        import codec_mask_integration as m
        from pathlib import Path
        with self.assertRaises(ValueError):
            m.verify_against_reference(base_spec(), path=Path("/no/such/reference_action_spec.json"))

    # ---- r26 §6: OrderedModelSpec + state hardening ----
    def test_spec_requires_n_max_for_every_device(self):
        with self.assertRaises(ValueError):
            base_spec(n_max={"d0": 3})            # d1 missing
        with self.assertRaises(ValueError):
            base_spec(n_max={"d0": 3, "d1": 9})   # 9 > N_primary
        with self.assertRaises(ValueError):
            base_spec(powers={"p_lo": 0.0, "p_hi": 2.0})  # non-positive power

    def test_state_requires_complete_eligible_and_power_cap(self):
        spec = base_spec()
        with self.assertRaises(ValueError):        # missing power_cap
            ci.compute_reference_boolean_token_mask({"eligible": {"d0": 5, "d1": 5}}, [], 1, spec)
        with self.assertRaises(ValueError):        # missing a device in eligible
            ci.compute_reference_boolean_token_mask(
                {"eligible": {"d0": 5}, "power_cap": {"d0": 1.0, "d1": 1.0}}, [], 1, spec)
        with self.assertRaises(ValueError):        # unknown device key
            ci.compute_reference_boolean_token_mask(
                {"eligible": {"d0": 5, "d1": 5, "dX": 1},
                 "power_cap": {"d0": 1.0, "d1": 1.0}}, [], 1, spec)
        with self.assertRaises(ValueError):        # non-integer eligible
            ci.compute_reference_boolean_token_mask(
                {"eligible": {"d0": 5, "d1": 2.5}, "power_cap": {"d0": 1.0, "d1": 1.0}}, [], 1, spec)
        with self.assertRaises(ValueError):        # infinite power cap (no inf default allowed)
            ci.compute_reference_boolean_token_mask(
                {"eligible": {"d0": 5, "d1": 5},
                 "power_cap": {"d0": float("inf"), "d1": 1.0}}, [], 1, spec)

    def test_illegal_forbidden_pair_rejected(self):
        with self.assertRaises(ValueError):
            base_spec(beam_forbidden=frozenset({(9, "b0")}))   # subchannel 9 > N_primary
        with self.assertRaises(ValueError):
            base_spec(power_forbidden=frozenset({(1, "pX")}))  # unknown power id

    # sanity: idle is always feasible and maps to id 0
    def test_idle_always_present(self):
        spec = base_spec()
        mask = ci.compute_reference_boolean_token_mask(base_state(), [], 1, spec)
        self.assertTrue(mask[codec.IDLE_ID])
        self.assertEqual(ci.encode_tuple(oracle.IDLE, spec), codec.IDLE_ID)
        self.assertEqual(ci.decode_id(codec.IDLE_ID, spec), oracle.IDLE)


if __name__ == "__main__":
    unittest.main()
