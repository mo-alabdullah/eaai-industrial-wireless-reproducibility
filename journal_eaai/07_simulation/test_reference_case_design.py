#!/usr/bin/env python3
"""Cross-check: the independent recomputation must match the hand-authored expected
transitions and metrics for BOTH deterministic design fixtures. Tamper tests prove the
independently computed results react to changes in assignment, packet deadline, W, tau,
and power. Tamper tests are SIDE-EFFECT-FREE (operate on TemporaryDirectory copies).

Run: python3 -m unittest -v test_reference_case_design
"""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import reference_case_independent_check as ic

HERE = Path(__file__).resolve().parent

FIXTURES = {
    "case1": ("reference_case_inputs.csv",
              "reference_case_expected_metrics.json",
              "reference_case_expected_transitions.csv"),
    "case2": ("reference_case2_inputs.csv",
              "reference_case2_expected_metrics.json",
              "reference_case2_expected_transitions.csv"),
    "case3": ("reference_case3_inputs.csv",
              "reference_case3_expected_metrics.json",
              "reference_case3_expected_transitions.csv"),
    "case3_fulldrain": ("reference_case3_fulldrain_inputs.csv",
                        "reference_case3_fulldrain_expected_metrics.json",
                        "reference_case3_fulldrain_expected_transitions.csv"),
    "case4": ("reference_case4_inputs.csv",
              "reference_case4_expected_metrics.json",
              "reference_case4_expected_transitions.csv"),
}


def _s(v):
    return "" if v is None else str(v)


def _norm(rows):
    out = []
    for r in rows:
        r = list(r) + [""] * (9 - len(r))
        nr = []
        for c in r:
            try:
                nr.append(str(float(c)))
            except (ValueError, TypeError):
                nr.append(_s(c))
        out.append(nr)
    return out


class TestFixturesMatchExpected(unittest.TestCase):
    def _check(self, name):
        inp, mfile, tfile = FIXTURES[name]
        tr, m = ic.recompute(HERE / inp)
        exp = json.loads((HERE / mfile).read_text())
        for k, v in m.items():
            self.assertIn(k, exp, f"{name}:{k}")
            self.assertAlmostEqual(float(v), float(exp[k]), places=4,
                                   msg=f"{name} metric {k}: got {v}, expected {exp[k]}")
        with (HERE / tfile).open() as f:
            rows = list(csv.reader(f))
        got = [[_s(x) for x in row] for row in tr]
        self.assertEqual(_norm(got), _norm(rows[1:]), f"{name} transitions")

    def test_case1(self):
        self._check("case1")

    def test_case2(self):
        self._check("case2")

    def test_case4(self):
        self._check("case4")


class TestModelledProperties(unittest.TestCase):
    def test_outage_not_one_minus_pdr(self):
        _, m = ic.recompute(HERE / "reference_case_inputs.csv")
        self.assertAlmostEqual(m["link_outage_rate_D1"], 0.5)
        self.assertAlmostEqual(m["PDR_D1"], 1.0)

    def test_hard_deadline_no_late_delivery(self):
        _, m = ic.recompute(HERE / "reference_case_inputs.csv")
        self.assertEqual(m["PDR_D2"], 0.0)
        self.assertEqual(m["deadline_violation_D2"], 1.0)

    def test_case2_mutually_exclusive_drop_precedence(self):
        # Q2 expires by deadline; Q1 exhausts retransmission — distinct, non-overlapping.
        _, m = ic.recompute(HERE / "reference_case2_inputs.csv")
        self.assertAlmostEqual(m["deadline_violation_D1"], 1 / 3)
        self.assertAlmostEqual(m["retx_exhausted_D1"], 1 / 3)
        self.assertAlmostEqual(m["PDR_D1"], 1 / 3)

    def test_case2_masked_action_and_idle_present(self):
        tr, _ = ic.recompute(HERE / "reference_case2_inputs.csv")
        events = {row[8] for row in tr}
        self.assertIn("masked_forbidden_action", events)
        self.assertIn("idle_queue_empty", events)

    def test_case3_full_action_parsed(self):
        # the checker parses beam + power from the action (not fixed g_beam/equal split)
        tr, m = ic.recompute(HERE / "reference_case3_inputs.csv")
        self.assertEqual(m["beam_mask_violation"], 1)
        self.assertEqual(m["power_mask_violation"], 1)
        self.assertEqual(m["power_cap_violation"], 1)
        self.assertEqual(m["beam_suboptimal"], 1)
        # max-gain beam b1 (gain 2.0) at p1 -> gamma 2.0; at p2 -> gamma 4.0
        gammas = {(r[0], r[1]): r[7] for r in tr if r[9] == "deliver"}
        self.assertAlmostEqual(gammas[(0, "n1")], 2.0)
        self.assertAlmostEqual(gammas[(2, "n1")], 4.0)
        # the inferior beam b2 (gain 0.5) produced the sub-optimal failing attempt
        infer = [r for r in tr if r[4] == "b2"]
        self.assertEqual(len(infer), 1)
        self.assertAlmostEqual(infer[0][7], 0.5)

    def test_case3_censored_vs_full_drain_accounting(self):
        # bounded drain: Q3 CENSORED -> no bare PDR; report lb/resolved/censored fraction
        _, mb = ic.recompute(HERE / "reference_case3_inputs.csv")
        self.assertNotIn("PDR_D1", mb)                     # no bare/denominator-less PDR
        self.assertAlmostEqual(mb["PDR_lb_D1"], 2 / 3)     # censored counted as failure
        self.assertAlmostEqual(mb["PDR_resolved_D1"], 1.0)  # exclude censored
        self.assertAlmostEqual(mb["censored_fraction_D1"], 1 / 3)
        # full drain: Q3 delivered -> censored set empty, lb == resolved == 1.0
        _, mf = ic.recompute(HERE / "reference_case3_fulldrain_inputs.csv")
        self.assertAlmostEqual(mf["censored_fraction_D1"], 0.0)
        self.assertAlmostEqual(mf["PDR_lb_D1"], 1.0)
        self.assertAlmostEqual(mf["PDR_resolved_D1"], 1.0)

    def test_case3_fulldrain_exact_N_and_util_denominator(self):
        # every slot has exactly N=2 tokens (incl. explicit idle); util denominator is N
        tr, m = ic.recompute(HERE / "reference_case3_fulldrain_inputs.csv")
        self.assertAlmostEqual(m["spectrum_utilization_avg"], 0.5)   # NOT 0.625
        self.assertIn("idle_action", {r[9] for r in tr})
        # per slot, exactly 2 transition rows and both subchannels present
        from collections import Counter
        per_slot = Counter(r[0] for r in tr)
        for t, c in per_slot.items():
            self.assertEqual(c, 2, f"slot {t} has {c} tokens, expected N=2")

    def _tamper_action_fixture(self, mutate):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "07_simulation"
            shutil.copytree(HERE, root)
            p = root / "reference_case3_fulldrain_inputs.csv"
            p.write_text(mutate(p.read_text(encoding="utf-8")), encoding="utf-8")
            with self.assertRaises(ValueError):
                ic.recompute(p)

    def test_tamper_missing_subchannel(self):
        # remove the slot-3 idle token -> slot 3 has only 1 of N tokens -> FAIL
        self._tamper_action_fixture(lambda t: t.replace(
            "action,3,n2,D1,idle,idle,explicit idle token (exactly N=2 tokens per slot)\n", ""))

    def test_tamper_duplicate_subchannel(self):
        # duplicate n1 in slot 3 -> duplicate subchannel token -> FAIL
        self._tamper_action_fixture(lambda t: t.replace(
            "action,3,n2,D1,idle,idle,explicit idle token (exactly N=2 tokens per slot)",
            "action,3,n1,D1,idle,idle,duplicate n1 token"))

    def test_tamper_extra_token(self):
        # add a third token in slot 3 -> more than N -> FAIL
        self._tamper_action_fixture(lambda t: t.replace(
            "action,3,n2,D1,idle,idle,explicit idle token (exactly N=2 tokens per slot)",
            "action,3,n2,D1,idle,idle,idle\naction,3,n3,D1,idle,idle,extra token"))

    def test_case4_surplus_subchannel_is_explicit_idle_not_repaired(self):
        # SELECTED-POLICY packet-aware mask: with 2 eligible packets on 3 subchannels, the
        # surplus subchannel carries an EXPLICIT idle token (idle_action) and there is NO
        # environment-side idle_queue_empty conversion and NO packet_mask_violation.
        tr, m = ic.recompute(HERE / "reference_case4_inputs.csv")
        self.assertEqual(m["packet_mask_violation"], 0)
        events = {r[9] for r in tr}
        self.assertIn("idle_action", events)
        self.assertNotIn("idle_queue_empty", events)   # no env-side repair in the action path
        self.assertEqual(sum(1 for r in tr if r[9] == "deliver"), 2)

    def test_case4_surplus_nonidle_token_is_packet_mask_violation(self):
        # Flip the surplus n3 idle token to a non-idle token -> exhausted queue ->
        # packet_mask_violation (never silently repaired to idle).
        with _TempFixture() as t:
            t.replace("reference_case4_inputs.csv",
                      "action,0,n3,D1,idle,idle,SURPLUS subchannel -> explicit idle token (no packet left) -> idle_action",
                      "action,0,n3,D1,b1,p1,tampered non-idle surplus -> packet_mask_violation")
            tr, m = t.recompute("reference_case4_inputs.csv")
            self.assertEqual(m["packet_mask_violation"], 1)
            evs = {(r[0], r[1]): r[9] for r in tr}
            self.assertEqual(evs[(0, "n3")], "packet_mask_violation")
            self.assertNotIn("idle_queue_empty", {r[9] for r in tr})

    def test_nonidle_token_to_empty_queue_is_packet_mask_violation(self):
        # A non-idle token to a device with NO remaining eligible packet must be flagged
        # `packet_mask_violation` and never silently repaired into an idle transmission.
        base_tr, base_m = ic.recompute(HERE / "reference_case3_fulldrain_inputs.csv")
        self.assertEqual(base_m["packet_mask_violation"], 0)
        with _TempFixture() as t:
            # slot 3 n1 already delivers Q3 (last eligible packet); make n2 non-idle -> the
            # device has no remaining eligible packet -> packet_mask_violation, not idle.
            t.replace("reference_case3_fulldrain_inputs.csv",
                      "action,3,n2,D1,idle,idle,explicit idle token (exactly N=2 tokens per slot)",
                      "action,3,n2,D1,b1,p1,non-idle to empty queue -> packet_mask_violation")
            tr, m = t.recompute("reference_case3_fulldrain_inputs.csv")
            self.assertEqual(m["packet_mask_violation"], 1)
            evs = {(r[0], r[1]): r[9] for r in tr}
            self.assertEqual(evs[(3, "n2")], "packet_mask_violation")
            self.assertNotEqual(evs[(3, "n2")], "idle_action")

    def test_case2_power_cap_enforced_as_mask_no_equal_split(self):
        # Cap is a FEASIBILITY MASK: fixed p_w=1.0, cumulative 1.0/2.0 fit, the 3rd
        # subchannel (would-be cum 3.0>2.0) is a power_cap_violation (no transmit). There
        # is NO equal-power split: the slot-2 delivery uses fixed p_w (gamma = p_w*H2 = 1.0),
        # not a cap concentrated onto one subchannel.
        tr, m = ic.recompute(HERE / "reference_case2_inputs.csv")
        self.assertEqual(m["power_cap_violation"], 2)                # n3 in slots 0 and 1
        self.assertIn("power_cap_violation", {r[8] for r in tr})
        deliver = [r for r in tr if r[8] == "deliver"]
        self.assertEqual(len(deliver), 1)
        self.assertEqual(deliver[0][0], 2)                          # slot 2
        self.assertAlmostEqual(float(deliver[0][5]), 1.0)           # gamma = p_w*H2 = 1.0
        # energy = 5 fixed-power transmissions * p_w * tau (never a split fraction)
        self.assertAlmostEqual(m["energy_joules_total"], 0.005)

    def test_case2_no_equal_split_fraction_in_energy(self):
        # Under the removed equal-split rule energy would have been 0.006 (a 2.0 W burst);
        # with fixed p_w it is 0.005. Guards against re-introducing the equal-power default.
        _, m = ic.recompute(HERE / "reference_case2_inputs.csv")
        self.assertNotAlmostEqual(m["energy_joules_total"], 0.006)


class _TempFixture:
    """Copy 07_simulation into a temp dir so tamper edits never touch production."""
    def __enter__(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "07_simulation"
        shutil.copytree(HERE, self.root)
        return self
    def path(self, name):
        return self.root / name
    def replace(self, name, old, new):
        p = self.path(name); t = p.read_text(encoding="utf-8")
        assert old in t, f"pattern not found in {name}: {old!r}"
        p.write_text(t.replace(old, new, 1), encoding="utf-8")
    def append(self, name, line):
        p = self.path(name)
        p.write_text(p.read_text(encoding="utf-8") + line, encoding="utf-8")
    def recompute(self, name):
        return ic.recompute(self.path(name))
    def drop_lines(self, name, substr):
        p = self.path(name)
        kept = [l for l in p.read_text(encoding="utf-8").splitlines() if substr not in l]
        p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    def __exit__(self, *a):
        self.td.cleanup()


class TestExplicitNSubchannels(unittest.TestCase):
    """r23 §5: N is an explicit fixture input; the canonical set n1..nN is validated."""
    INP = "reference_case3_inputs.csv"   # N=2 (n1,n2)

    def test_subchannel_missing_from_every_slot_fails(self):
        # remove ALL n2 action rows -> every slot has 1 token != N=2, and n2 (in n1..nN) is
        # absent from every slot. With N derived from rows this would pass; with explicit N it fails.
        with _TempFixture() as t:
            t.drop_lines(self.INP, ",n2,")
            with self.assertRaises(ValueError):
                t.recompute(self.INP)

    def test_subchannel_missing_from_one_slot_fails(self):
        with _TempFixture() as t:
            t.drop_lines(self.INP, "action,0,n2,")   # drop only slot-0 n2
            with self.assertRaises(ValueError):
                t.recompute(self.INP)

    def test_unknown_subchannel_token_fails(self):
        with _TempFixture() as t:
            t.replace(self.INP, "action,0,n2,D1,b1,p1",
                      "action,0,n9,D1,b1,p1")   # n9 not in canonical n1..n2
            with self.assertRaises(ValueError):
                t.recompute(self.INP)

    def test_missing_n_subchannels_param_fails(self):
        with _TempFixture() as t:
            t.drop_lines(self.INP, "param,n_subchannels,")
            with self.assertRaises(ValueError):
                t.recompute(self.INP)

    def test_wrong_n_value_fails(self):
        # declare N=3 but only n1,n2 present -> canonical n3 missing every slot -> fail
        with _TempFixture() as t:
            t.replace(self.INP, "param,n_subchannels,2", "param,n_subchannels,3")
            with self.assertRaises(ValueError):
                t.recompute(self.INP)


class TestTamperChangesResult(unittest.TestCase):
    """Changing any used input must change the independently computed result."""
    INP = "reference_case_inputs.csv"

    def _baseline(self):
        return ic.recompute(HERE / self.INP)

    def test_change_assignment(self):
        base_tr, _ = self._baseline()
        with _TempFixture() as t:
            # give D1 both subchannels instead of one each -> different transitions
            t.replace(self.INP, "assign,n2,D2,,fixed subchannel->device",
                      "assign,n2,D1,,tampered subchannel->device")
            tr, _ = t.recompute(self.INP)
            self.assertNotEqual(_norm(base_tr), _norm(tr))

    def test_change_packet_deadline(self):
        _, base_m = self._baseline()
        with _TempFixture() as t:
            # extend D2 deadline so it no longer expires -> metrics change
            t.replace(self.INP, "packet,P2,D2,0,2", "packet,P2,D2,0,9")
            _, m = t.recompute(self.INP)
            self.assertNotEqual(base_m["deadline_violation_D2"],
                                m["deadline_violation_D2"])

    def test_change_W(self):
        _, base_m = self._baseline()
        with _TempFixture() as t:
            # halve bandwidth -> gamma_th rises -> supplied gamma_th mismatch caught,
            # so also update Z to keep it consistent but change the threshold.
            t.replace(self.INP, "param,W_hz,100000,,subchannel bandwidth",
                      "param,W_hz,50000,,tampered bandwidth")
            t.replace(self.INP, "param,gamma_th,1.0,,Shannon threshold 2^(Z/(W*tau))-1",
                      "param,gamma_th,3.0,,tampered threshold")
            # P1 now never succeeds and survives into slot 2 -> supply that link
            t.append(self.INP, "link,D1,2,2.0,\n")
            _, m = t.recompute(self.INP)
            # higher threshold -> the slot-1 D1 success (gamma 2.0) now fails
            self.assertNotEqual(base_m["PDR_D1"], m["PDR_D1"])

    def test_change_tau(self):
        with _TempFixture() as t:
            # change tau without updating supplied gamma_th -> verification must reject
            t.replace(self.INP, "param,tau_s,0.001,,slot duration (W*tau=100)",
                      "param,tau_s,0.002,,tampered slot duration")
            with self.assertRaises(ValueError):
                t.recompute(self.INP)

    def test_change_power(self):
        _, base_m = self._baseline()
        with _TempFixture() as t:
            # drop tx power so the slot-1 D1 gamma (was 2.0) falls below threshold
            t.replace(self.INP, "param,p_w,1.0,,fixed tx power per attempt",
                      "param,p_w,0.4,,tampered tx power")
            # P1 now never succeeds and survives into slot 2 -> supply that link
            t.append(self.INP, "link,D1,2,2.0,\n")
            _, m = t.recompute(self.INP)
            self.assertNotEqual(base_m["PDR_D1"], m["PDR_D1"])

    def test_change_powercap_case2(self):
        base_tr, base_m = ic.recompute(HERE / "reference_case2_inputs.csv")
        with _TempFixture() as t:
            # halve the cap -> only ONE subchannel fits the fixed p_w per device -> more
            # power_cap_violations and fewer transmissions -> different computed result
            t.replace("reference_case2_inputs.csv",
                      "powercap,D1,2.0,,per-device total tx power cap; enforced as a feasibility mask",
                      "powercap,D1,1.0,,tampered cap")
            tr, m = t.recompute("reference_case2_inputs.csv")
            self.assertNotEqual(base_m["power_cap_violation"], m["power_cap_violation"])
            self.assertNotEqual(_norm(base_tr), _norm(tr))
            self.assertNotAlmostEqual(base_m["energy_joules_total"], m["energy_joules_total"])


class TestInputValidation(unittest.TestCase):
    def test_bad_gamma_th_rejected(self):
        with _TempFixture() as t:
            t.replace("reference_case_inputs.csv",
                      "param,gamma_th,1.0,,Shannon threshold 2^(Z/(W*tau))-1",
                      "param,gamma_th,7.0,,wrong")
            with self.assertRaises(ValueError):
                t.recompute("reference_case_inputs.csv")

    def test_mask_unassigned_pair_rejected(self):
        with _TempFixture() as t:
            t.append("reference_case_inputs.csv", "\nmask,n9,D9,all,bad\n")
            with self.assertRaises(ValueError):
                t.recompute("reference_case_inputs.csv")


class TestNoProductionSideEffects(unittest.TestCase):
    def test_recompute_leaves_fixtures_unchanged(self):
        import hashlib
        def h(p):
            return hashlib.sha256(Path(p).read_bytes()).hexdigest()
        before = {f: h(HERE / f) for grp in FIXTURES.values() for f in grp}
        for inp, *_ in FIXTURES.values():
            ic.recompute(HERE / inp)
        after = {f: h(HERE / f) for grp in FIXTURES.values() for f in grp}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
