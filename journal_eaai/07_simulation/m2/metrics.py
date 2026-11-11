#!/usr/bin/env python3
"""Metric definitions + validity checks (M2, r34).

The ordered J_cost = 3|C|+1 cost channels (bsa_lppo_specification.md §2a): for each class c in
(static, mobile): [C_rel, C_dv, C_over]; then C_pow last.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

COST_CHANNEL_NAMES: List[str] = [
    "C_rel_static", "C_dv_static", "C_over_static",
    "C_rel_mobile", "C_dv_mobile", "C_over_mobile",
    "C_pow",
]


def assert_episode_validity(tot: Dict) -> None:
    """No impossible value may appear in an aggregated episode result."""
    assert tot["deliv"] <= tot["gen"], f"delivered {tot['deliv']} > generated {tot['gen']}"
    assert 0.0 <= tot["pdr"] <= 1.0, f"PDR out of range: {tot['pdr']}"
    assert tot["deliv"] >= 0 and tot["gen"] >= 0
    cv = tot.get("cost_vector")
    if cv is not None:
        assert len(cv) == len(COST_CHANNEL_NAMES), "cost vector length != J_cost"
        assert np.all(np.isfinite(cv)), "non-finite cost channel"
