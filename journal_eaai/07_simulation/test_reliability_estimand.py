#!/usr/bin/env python3
"""Deterministic proof that the two reliability estimands differ when seeds have unequal
arrival denominators, and that R_pooled (ratio-of-sums) is the selected primary estimand
(`../06_mathematical_model/cmdp_packet_accounting.md`).

    R_pooled          = (sum_s D_s) / (sum_s A_s)      # ratio of sums  (PRIMARY)
    mean_of_ratios    = mean_s( D_s / A_s )            # secondary only

Run: python3 -m unittest -v test_reliability_estimand
"""
from __future__ import annotations

import unittest


def r_pooled(pairs):
    D = sum(d for d, a in pairs)
    A = sum(a for d, a in pairs)
    return D / A if A else 0.0


def mean_of_ratios(pairs):
    rs = [d / a for d, a in pairs if a]
    return sum(rs) / len(rs) if rs else 0.0


class TestEstimand(unittest.TestCase):
    # per-seed (delivered, generated) count pairs with UNEQUAL denominators
    PAIRS = [(1, 1), (1, 99)]

    def test_two_estimands_differ(self):
        rp = r_pooled(self.PAIRS)          # (1+1)/(1+99) = 2/100 = 0.02
        mr = mean_of_ratios(self.PAIRS)    # (1.0 + 1/99)/2 ≈ 0.5051
        self.assertAlmostEqual(rp, 0.02, places=6)
        self.assertAlmostEqual(mr, (1.0 + 1 / 99) / 2, places=6)
        self.assertNotAlmostEqual(rp, mr, places=2)   # they are materially different

    def test_equal_denominators_agree(self):
        # sanity: with EQUAL denominators the two coincide
        pairs = [(3, 10), (7, 10)]
        self.assertAlmostEqual(r_pooled(pairs), mean_of_ratios(pairs), places=9)

    def test_pooled_is_bounded(self):
        for pairs in ([(0, 0)], [(5, 5)], self.PAIRS):
            self.assertTrue(0.0 <= r_pooled(pairs) <= 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
