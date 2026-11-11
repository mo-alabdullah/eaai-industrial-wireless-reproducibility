#!/usr/bin/env python3
"""Discrete per-subchannel token bijection (Gate-M1 DESIGN artifact — r24 §10).

The per-token action alphabet is `Discrete(1 + K*B*P)`:
    0                      = idle
    1 .. K*B*P             = (device_index, beam_index, power_index)
with the CANONICAL, stable ordering device-major, then beam, then power:
    token_id = 1 + (device_index * B + beam_index) * P + power_index
    device_index in [0, K), beam_index in [0, B), power_index in [0, P).

Pure functions only (no simulator, no RNG). Deterministic bijection used by the mathematical
action model and the conditional-mask oracle.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple, Union

IDLE_ID = 0
Decoded = Union[str, Tuple[int, int, int]]   # "idle" or (device, beam, power)


def alphabet_size(K: int, B: int, P: int) -> int:
    _check_dims(K, B, P)
    return 1 + K * B * P


def _check_dims(K: int, B: int, P: int) -> None:
    for name, v in (("K", K), ("B", B), ("P", P)):
        if not isinstance(v, int) or v < 1:
            raise ValueError(f"{name} must be a positive int, got {v!r}")


def encode_token(device: int, beam: int, power: int, K: int, B: int, P: int) -> int:
    """(device, beam, power) 0-based indices -> token id in 1..K*B*P."""
    _check_dims(K, B, P)
    if not (0 <= device < K):
        raise ValueError(f"device index {device} out of range [0,{K})")
    if not (0 <= beam < B):
        raise ValueError(f"beam index {beam} out of range [0,{B})")
    if not (0 <= power < P):
        raise ValueError(f"power index {power} out of range [0,{P})")
    return 1 + (device * B + beam) * P + power


def decode_token(token_id: int, K: int, B: int, P: int) -> Decoded:
    """token id -> 'idle' (id 0) or (device, beam, power)."""
    _check_dims(K, B, P)
    if not isinstance(token_id, int):
        raise ValueError(f"token id must be int, got {token_id!r}")
    if token_id == IDLE_ID:
        return "idle"
    if not (1 <= token_id <= K * B * P):
        raise ValueError(f"token id {token_id} out of range [0,{K * B * P}]")
    z = token_id - 1
    power = z % P
    z //= P
    beam = z % B
    device = z // B
    return (device, beam, power)


def tokens_to_boolean_mask(feasible_tokens: Iterable[int], K: int, B: int, P: int) -> List[bool]:
    """Feasible token ids -> boolean mask of length exactly 1 + K*B*P."""
    n = alphabet_size(K, B, P)
    mask = [False] * n
    for t in feasible_tokens:
        if not isinstance(t, int) or not (0 <= t < n):
            raise ValueError(f"feasible token id {t!r} out of range [0,{n})")
        mask[t] = True
    return mask
