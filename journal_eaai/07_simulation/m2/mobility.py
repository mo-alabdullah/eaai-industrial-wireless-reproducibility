#!/usr/bin/env python3
"""Seeded geometry + grid-constrained waypoint AMR/AGV mobility (M2, r35 repaired).

Static sensors keep a fixed position. AMR/AGV follow a reproducible, seeded, grid-constrained
piecewise-linear route on an orthogonal waypoint network inside the InF-SH hall: motion is
axis-aligned segment-to-segment; turns occur ONLY at waypoint intersections; speed is drawn per
segment from the locked range; displacement per slot = speed*tau; devices never teleport and
never leave the hall. The AP sits at the hall centre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class Device:
    idx: int
    is_mobile: bool
    x: float
    y: float
    target: Tuple[float, float] = (0.0, 0.0)
    speed: float = 0.0
    seg_turns: int = 0            # number of waypoint turns taken (trajectory metadata)


@dataclass
class Geometry:
    hall_x: float
    hall_y: float
    ap_x: float
    ap_y: float
    ap_h: float
    ut_h: float

    def d2d_d3d(self, dev: Device):
        dx = dev.x - self.ap_x
        dy = dev.y - self.ap_y
        d2d = math.hypot(dx, dy)
        d3d = math.sqrt(d2d ** 2 + (self.ap_h - self.ut_h) ** 2)
        return max(d2d, 1e-3), max(d3d, 1e-3), math.sin(math.atan2(dy, dx))


@dataclass
class MobilityModel:
    geom: Geometry
    n_static: int
    n_mobile: int
    v_max: float
    tau_s: float
    grid_step_m: float = 50.0
    devices: List[Device] = field(default_factory=list)
    waypoints: List[Tuple[float, float]] = field(default_factory=list)

    def _build_waypoints(self):
        gx, gy, s = self.geom.hall_x, self.geom.hall_y, self.grid_step_m
        xs = [min(i * s, gx) for i in range(int(gx // s) + 1)]
        ys = [min(j * s, gy) for j in range(int(gy // s) + 1)]
        self.nx, self.ny = len(xs), len(ys)
        self.xs, self.ys = xs, ys
        self.waypoints = [(x, y) for x in xs for y in ys]

    def _neighbors(self, ix: int, iy: int):
        out = []
        if ix > 0:
            out.append((ix - 1, iy))
        if ix < self.nx - 1:
            out.append((ix + 1, iy))
        if iy > 0:
            out.append((ix, iy - 1))
        if iy < self.ny - 1:
            out.append((ix, iy + 1))
        return out

    def reset(self, rng: np.random.Generator) -> None:
        self._build_waypoints()
        self.devices = []
        for k in range(self.n_static):
            self.devices.append(Device(k, False, rng.uniform(0, self.geom.hall_x),
                                       rng.uniform(0, self.geom.hall_y)))
        for j in range(self.n_mobile):
            ix = int(rng.integers(0, self.nx)); iy = int(rng.integers(0, self.ny))
            x, y = self.xs[ix], self.ys[iy]
            d = Device(self.n_static + j, True, x, y)
            d._ix, d._iy = ix, iy            # current waypoint indices
            self._assign_next_waypoint(d, rng)
            self.devices.append(d)

    def _assign_next_waypoint(self, d: Device, rng: np.random.Generator):
        nbrs = self._neighbors(d._ix, d._iy)
        nix, niy = nbrs[int(rng.integers(0, len(nbrs)))]
        d._nix, d._niy = nix, niy
        d.target = (self.xs[nix], self.ys[niy])
        d.speed = float(rng.uniform(0.2 * self.v_max, self.v_max))   # nonzero segment speed

    def step(self, rng: np.random.Generator) -> None:
        for d in self.devices:
            if not d.is_mobile:
                continue
            tx, ty = d.target
            dx, dy = tx - d.x, ty - d.y
            dist = math.hypot(dx, dy)
            move = d.speed * self.tau_s
            if move >= dist or dist < 1e-9:
                # reached the waypoint this slot -> snap, turn, pick next segment
                d.x, d.y = tx, ty
                d._ix, d._iy = d._nix, d._niy
                d.seg_turns += 1
                self._assign_next_waypoint(d, rng)
            else:
                d.x += move * dx / dist
                d.y += move * dy / dist
            d.x = min(max(d.x, 0.0), self.geom.hall_x)
            d.y = min(max(d.y, 0.0), self.geom.hall_y)
