#!/usr/bin/env python3
"""Primary action-spec tests (r27 §5): the PRIMARY spec is generated deterministically from the
locked scenario config, matches config_schema's N_primary, and a reference/toy spec cannot be
passed where the primary spec is required."""
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import codec_mask_integration as ci
import generate_primary_action_spec as gen

HERE = Path(__file__).resolve().parent


class TestPrimaryActionSpec(unittest.TestCase):
    def test_generation_is_deterministic(self):
        cfg = json.loads((HERE / "primary_scenario_config.json").read_text())
        a = gen.build_spec(cfg)
        b = gen.build_spec(cfg)
        self.assertEqual(a, b)
        onfile = json.loads((HERE / "primary_action_spec.json").read_text())
        # the committed artifact matches a fresh generation (idempotent)
        for k in ("canonical_signature", "config_hash", "device_order", "beam_order",
                  "power_order", "N_primary", "K", "B", "P"):
            self.assertEqual(onfile[k], a[k], k)

    def test_primary_matches_config_schema_N(self):
        spec = ci.build_primary_ordered_spec()
        self.assertEqual(spec.n_primary, 8)  # config_schema.md preregistered N_primary=8
        cfg = ci.load_primary_config()
        self.assertEqual(spec.n_primary, int(cfg["n_primary"]))
        ci.assert_is_primary_spec(spec)  # full consistency (no raise)

    def test_KBP_match_scenario_config(self):
        spec = ci.build_primary_ordered_spec()
        cfg = ci.load_primary_config()
        self.assertEqual(spec.K, int(cfg["n_static"]) + int(cfg["n_mobile"]))
        self.assertEqual(spec.B, int(cfg["codebook_size"]))
        self.assertEqual(spec.P, int(cfg["power_levels"]))

    def test_reference_spec_rejected_as_primary(self):
        # the REFERENCE/toy spec must NOT pass as the primary spec
        from test_codec_mask_integration import base_spec
        with self.assertRaises(ValueError):
            ci.assert_is_primary_spec(base_spec())

    def test_primary_N_mismatch_detected(self):
        # a spec whose N differs from the scenario config must be rejected
        s = ci.load_primary_spec()
        bad = ci.OrderedModelSpec(
            device_order=tuple(s["device_order"]), beam_order=tuple(s["beam_order"]),
            power_order=tuple(s["power_order"]), version=s["version"],
            powers={k: float(v) for k, v in s["powers"].items()},
            n_max={d: 5 for d in s["device_order"]}, n_primary=5)  # wrong N (config says 8)
        with self.assertRaises(ValueError):
            ci.assert_is_primary_spec(bad)

    def test_ordering_rule_not_hardcoded_ids(self):
        # the primary device order follows the static-first rule with generated ids (not d0/d1)
        spec = ci.build_primary_ordered_spec()
        self.assertTrue(spec.device_order[0].startswith("static_"))
        self.assertTrue(spec.device_order[-1].startswith("mobile_"))
        self.assertNotIn("d0", spec.device_order)


class TestPrimaryScenarioCompleteness(unittest.TestCase):
    """r28 §5: the primary scenario config/spec carries the required fields and an explicit
    per-class N_max rule (not silently N_max = N_primary)."""
    def test_per_device_n_max_is_per_class_not_N_primary(self):
        s = ci.load_primary_spec()
        cfg = ci.load_primary_config()
        self.assertEqual(s["per_device_n_max"]["static_0"], int(cfg["n_max_static"]))
        self.assertEqual(s["per_device_n_max"]["mobile_0"], int(cfg["n_max_mobile"]))
        # at least one device's N_max must differ from N_primary (proves it isn't silently N)
        self.assertTrue(any(v != s["N_primary"] for v in s["per_device_n_max"].values()))

    def test_codebook_size_must_equal_n_antennas(self):
        # r30 §10 (option A): the generator enforces B == n_antennas (no 8==8 coincidence)
        cfg = dict(json.loads((HERE / "primary_scenario_config.json").read_text()))
        cfg["codebook_size"] = 6            # != n_antennas (8)
        with self.assertRaises(ValueError):
            gen.build_spec(cfg)

    def test_required_scenario_fields_present(self):
        s = ci.load_primary_spec()
        for k in ("scenario_id", "class_map", "per_device_n_max", "per_device_power_cap_w",
                  "beam_forbidden", "power_forbidden"):
            self.assertIn(k, s, k)
        cfg = ci.load_primary_config()
        for k in ("class_map_rule", "n_max_rule", "per_device_total_power_cap_rule",
                  "beam_validity_rule", "power_cap_state_schema", "design_justification",
                  "design_parameter_register"):
            self.assertIn(k, cfg, k)
        reg = cfg["design_parameter_register"]
        for k in ("sourced", "preregistered_design_factors", "sensitivity_values", "unresolved"):
            self.assertIn(k, reg, k)


class TestPrimaryMaskIntegration(unittest.TestCase):
    """r28 §4: the PRIMARY spec passes the COMPLETE mask oracle through the primary mask path.
    r29 §2: the primary path injects the LOCKED per-device power cap; callers supply only the
    per-device eligible counts (no power_cap override)."""
    def _primary_state(self, spec, eligible=3):
        return {"eligible": {d: eligible for d in spec.device_order}}   # cap injected internally

    def test_primary_mask_length_is_257(self):
        spec = ci.build_primary_ordered_spec()
        mask = ci.compute_primary_boolean_token_mask(self._primary_state(spec), [], 1, spec)
        self.assertEqual(len(mask), 1 + 8 * 8 * 4)   # 257
        self.assertEqual(len(mask), 1 + spec.K * spec.B * spec.P)
        self.assertTrue(mask[0])                      # idle always feasible

    def test_primary_prefix_and_reservation(self):
        spec = ci.build_primary_ordered_spec()
        st = self._primary_state(spec, eligible=1)    # one eligible packet per device
        # reserve the single eligible packet of device static_0 at subchannel 1
        import token_codec as codec
        di = spec.device_order.index("static_0")
        tok = codec.encode_token(di, 0, 0, spec.K, spec.B, spec.P)
        ids = set(i for i, on in enumerate(
            ci.compute_primary_boolean_token_mask(st, [tok], 2, spec)) if on)
        # after reserving static_0's only packet, no non-idle static_0 token remains feasible
        for i in ids:
            dec = codec.decode_token(i, spec.K, spec.B, spec.P)
            self.assertFalse(dec != "idle" and spec.device_order[dec[0]] == "static_0")

    def test_reference_spec_rejected_by_primary_mask(self):
        ref = ci.build_reference_ordered_spec()
        st = {"eligible": {d: 1 for d in ref.device_order}}
        with self.assertRaises(ValueError):
            ci.compute_primary_boolean_token_mask(st, [], 1, ref)

    def test_reference_mask_path_still_works(self):
        ref = ci.build_reference_ordered_spec()
        st = {"eligible": {d: 2 for d in ref.device_order},
              "power_cap": {d: 9.0 for d in ref.device_order}}
        mask = ci.compute_reference_boolean_token_mask(st, [], 1, ref)
        self.assertEqual(len(mask), 1 + ref.K * ref.B * ref.P)


class TestPrimaryLockedPowerCap(unittest.TestCase):
    """r29 §2: the locked 0.8 W per-device total-power cap is enforced by the primary mask path
    and cannot be loosened by the caller."""
    def _mask_ids(self, spec, st, prefix, idx):
        import token_codec as codec
        mask = ci.compute_primary_boolean_token_mask(st, prefix, idx, spec)
        return {i for i, on in enumerate(mask) if on}, codec

    def test_locked_cap_blocks_third_max_power_allocation(self):
        # two 0.4 W allocations of static_0 commit 0.8 W == cap; a third 0.4 W token is infeasible.
        spec = ci.build_primary_ordered_spec()
        import token_codec as codec
        di = spec.device_order.index("static_0")
        pi_hi = spec.power_order.index("power_3")           # 0.4 W (the max level)
        self.assertEqual(spec.powers["power_3"], 0.4)
        self.assertEqual(ci.primary_locked_power_caps()["static_0"], 0.8)
        hi = codec.encode_token(di, 0, pi_hi, spec.K, spec.B, spec.P)
        st = {"eligible": {d: 5 for d in spec.device_order}}  # plenty of packets; cap is the bind
        ids, codec = self._mask_ids(spec, st, [hi, hi], 3)    # two 0.4 W already committed
        for i in ids:
            dec = codec.decode_token(i, spec.K, spec.B, spec.P)
            if dec != "idle" and spec.device_order[dec[0]] == "static_0":
                self.fail("a positive-power static_0 token remained feasible after 0.8 W committed")

    def test_caller_cannot_override_locked_cap(self):
        spec = ci.build_primary_ordered_spec()
        st = {"eligible": {d: 5 for d in spec.device_order},
              "power_cap": {d: 100.0 for d in spec.device_order}}   # attempt to loosen to 100 W
        with self.assertRaises(ValueError):
            ci.compute_primary_boolean_token_mask(st, [], 1, spec)


class TestGenericAliasRemoved(unittest.TestCase):
    """r29 §3: the generic mask/feasible-ids names must not silently select the reference tier."""
    def test_generic_mask_alias_raises(self):
        spec = ci.build_reference_ordered_spec()
        st = {"eligible": {d: 1 for d in spec.device_order},
              "power_cap": {d: 9.0 for d in spec.device_order}}
        with self.assertRaises(NotImplementedError):
            ci.compute_boolean_token_mask(st, [], 1, spec)
        with self.assertRaises(NotImplementedError):
            ci.oracle_feasible_ids(st, [], 1, spec)


class TestPrimarySpecFullBinding(unittest.TestCase):
    """r29 §1: every decision-relevant field of primary_action_spec.json is bound to a fresh
    regeneration from primary_scenario_config.json. A wrong physical value in the artifact — even
    with correct ordered ids/N/K/B/P/version — must be rejected."""
    def setUp(self):
        self.good = ci.build_primary_ordered_spec()   # built from the true committed artifact
        self.prim = ci.load_primary_spec()

    def _assert_tampered_field_rejected(self, mutate):
        import copy
        tampered = copy.deepcopy(self.prim)
        mutate(tampered)
        with mock.patch.object(ci, "load_primary_spec", return_value=tampered):
            with self.assertRaises(ValueError):
                ci.assert_is_primary_spec(self.good)

    def test_wrong_power_value_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s["powers"].__setitem__("power_3", 9.9))

    def test_wrong_per_device_n_max_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s["per_device_n_max"].__setitem__("static_0", 7))

    def test_wrong_power_cap_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s["per_device_power_cap_w"].__setitem__("static_0", 99.0))

    def test_wrong_class_map_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s["class_map"].__setitem__("static_0", "mobile"))

    def test_wrong_beam_forbidden_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s.__setitem__("beam_forbidden", [[1, "beam_0"]]))

    def test_wrong_power_forbidden_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s.__setitem__("power_forbidden", [[1, "power_0"]]))

    def test_wrong_scenario_id_rejected(self):
        self._assert_tampered_field_rejected(
            lambda s: s.__setitem__("scenario_id", "OTHER"))

    def test_untampered_artifact_accepted(self):
        ci.assert_is_primary_spec(self.good)          # no raise on the true artifact


class TestPrimaryScenarioConfigValidator(unittest.TestCase):
    """r31 §5: build_spec must reject an invalid primary scenario config (independently confirmed
    cases: negative cap, negative/duplicate power levels, zero-device scenario)."""
    def _cfg(self, **over):
        cfg = dict(json.loads((HERE / "primary_scenario_config.json").read_text()))
        cfg.update(over)
        return cfg

    def test_negative_power_cap_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(per_device_total_power_cap_w=-1))

    def test_negative_power_level_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(power_level_watts=[-0.4, 0.1, 0.2, 0.05],
                                     primary_power_grid_w=[-0.4, 0.1, 0.2, 0.05]))

    def test_nan_power_level_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(power_level_watts=[float("nan"), 0.1, 0.2, 0.4],
                                     primary_power_grid_w=[float("nan"), 0.1, 0.2, 0.4]))

    def test_duplicate_power_levels_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(power_level_watts=[0.1, 0.1, 0.2, 0.4],
                                     primary_power_grid_w=[0.1, 0.1, 0.2, 0.4]))

    def test_zero_device_scenario_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(n_static=0, n_mobile=0))

    def test_nmax_zero_rejected(self):
        # r31 §4 canonical domain 1..N: N_max=0 is not permitted
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(n_max_static=0))

    def test_B_not_equal_n_antennas_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(codebook_size=6))

    def test_empty_scenario_id_rejected(self):
        with self.assertRaises(ValueError):
            gen.build_spec(self._cfg(scenario_id=""))

    def test_good_config_accepted(self):
        gen.build_spec(self._cfg())          # no raise


class TestNmaxCanonicalDomain(unittest.TestCase):
    """r31 §4: OrderedModelSpec rejects N_max=0 (canonical domain 1..N_primary)."""
    def test_ordered_spec_rejects_nmax_zero(self):
        with self.assertRaises(ValueError):
            ci.OrderedModelSpec(
                device_order=("static_0", "static_1"), beam_order=("beam_0",),
                power_order=("power_0",), version="x",
                powers={"power_0": 0.05}, n_max={"static_0": 0, "static_1": 2}, n_primary=8)


class TestRuntimeSpecFullBinding(unittest.TestCase):
    """r30 §1: the RUNTIME OrderedModelSpec passed to the mask must be semantically identical to
    the committed primary artifact — not merely share orders/powers/N_max. A tampered
    beam_forbidden/power_forbidden on the passed spec must be rejected by assert_is_primary_spec
    AND by the primary mask path."""
    def setUp(self):
        self.good = ci.build_primary_ordered_spec()

    def test_runtime_beam_forbidden_mismatch_rejected(self):
        bad = replace(self.good, beam_forbidden=frozenset({(1, "beam_0")}))
        with self.assertRaises(ValueError):
            ci.assert_is_primary_spec(bad)
        st = {"eligible": {d: 2 for d in bad.device_order}}
        with self.assertRaises(ValueError):
            ci.compute_primary_boolean_token_mask(st, [], 1, bad)

    def test_runtime_power_forbidden_mismatch_rejected(self):
        bad = replace(self.good, power_forbidden=frozenset({(1, "power_0")}))
        with self.assertRaises(ValueError):
            ci.assert_is_primary_spec(bad)
        st = {"eligible": {d: 2 for d in bad.device_order}}
        with self.assertRaises(ValueError):
            ci.compute_primary_boolean_token_mask(st, [], 1, bad)

    def test_good_runtime_spec_has_empty_forbidden_and_passes(self):
        self.assertEqual(set(self.good.beam_forbidden), set())
        self.assertEqual(set(self.good.power_forbidden), set())
        ci.assert_is_primary_spec(self.good)          # no raise


if __name__ == "__main__":
    unittest.main()
