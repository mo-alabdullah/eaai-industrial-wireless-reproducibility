#!/usr/bin/env python3
"""Journal-extension-only power-grid definitions (Stage I0).

The archived ICAME configuration is NEVER modified globally: every alternative grid is applied by
dataclasses.replace on a fresh config object, so 07_simulation/m2/config.py and every archived
result remain untouched.
"""
from __future__ import annotations
import dataclasses
from typing import Dict, Sequence

#   G0  the ICAME'26 primary grid, unchanged (reference)
#   G1  the extended grid proposed in the Stage-I0 instruction (0.005 W = 7 dBm floor)
#   G2  a wide ~5 dB log grid spanning the measured p_req distribution down to 1e-5 W (-20 dBm)
GRIDS: Dict[str, Sequence[float]] = {
    "G0_icame":  (0.05, 0.10, 0.20, 0.40),
    "G1_ext7":   (0.005, 0.010, 0.020, 0.050, 0.100, 0.200, 0.400),
    "G2_wide10": (1e-5, 3.1623e-5, 1e-4, 3.1623e-4, 1e-3,
                  3.1623e-3, 1e-2, 3.1623e-2, 1e-1, 4e-1),
}

GRID_NOTE = {
    "G0_icame":  "ICAME'26 primary grid. Floor 0.05 W = 17 dBm.",
    "G1_ext7":   "Instruction-proposed extension. Floor 0.005 W = 7 dBm.",
    "G2_wide10": ("~5 dB log grid chosen to span the analytically measured p_req distribution; "
                  "floor 1e-5 W = -20 dBm, within the documented control range of commercial "
                  "mmWave front-ends and numerically well-conditioned (SINR ~ 0.7 at the floor "
                  "for the best-placed static link)."),
}


def with_grid(cfg, grid_key: str):
    g = [float(x) for x in GRIDS[grid_key]]
    return dataclasses.replace(cfg, power_grid_w=g, n_power_levels=len(g), p_max_w=max(g))


def hist_stats(power_hist, grid) -> dict:
    """Grid-aware selected-power statistics. Kept local to Stage I0 so that evaluation.summarise()
    - used by Stages D/E/F - is not modified and earlier results stay reproducible."""
    if not power_hist:
        return {}
    tot = max(sum(power_hist), 1)
    out = {"n_tx": int(sum(power_hist)),
           "mean_tx_power_w_grid": sum(h * w for h, w in zip(power_hist, grid)) / tot}
    for i, w in enumerate(grid):
        out[f"frac_lvl{i}_{w:g}W"] = power_hist[i] / tot
    out["frac_at_floor"] = power_hist[0] / tot
    out["frac_at_ceiling"] = power_hist[-1] / tot
    return out
