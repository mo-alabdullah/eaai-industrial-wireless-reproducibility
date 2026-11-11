#!/usr/bin/env python3
"""Tests for the discrete token bijection (r24 §10).

Run: python3 -m unittest -v test_token_codec
"""
from __future__ import annotations

import unittest

from token_codec import (IDLE_ID, alphabet_size, decode_token, encode_token,
                         tokens_to_boolean_mask)

K, B, P = 3, 2, 2   # 1 + 3*2*2 = 13 token ids (0..12)


class TestTokenCodec(unittest.TestCase):
    def test_idle_index_fixed(self):
        self.assertEqual(IDLE_ID, 0)
        self.assertEqual(decode_token(0, K, B, P), "idle")

    def test_alphabet_size(self):
        self.assertEqual(alphabet_size(K, B, P), 1 + K * B * P)

    def test_round_trip_identity(self):
        for d in range(K):
            for b in range(B):
                for p in range(P):
                    tid = encode_token(d, b, p, K, B, P)
                    self.assertEqual(decode_token(tid, K, B, P), (d, b, p))

    def test_all_token_ids_unique_and_cover_range(self):
        ids = {encode_token(d, b, p, K, B, P)
               for d in range(K) for b in range(B) for p in range(P)}
        self.assertEqual(ids, set(range(1, K * B * P + 1)))   # exactly 1..K*B*P, all unique

    def test_stable_device_beam_power_ordering(self):
        # device-major, then beam, then power: consecutive power indices are adjacent ids
        self.assertEqual(encode_token(0, 0, 0, K, B, P), 1)
        self.assertEqual(encode_token(0, 0, 1, K, B, P), 2)   # power increments by 1
        self.assertEqual(encode_token(0, 1, 0, K, B, P), 3)   # next beam
        self.assertEqual(encode_token(1, 0, 0, K, B, P), 1 + B * P)  # next device

    def test_mask_length_exactly_1_plus_kbp(self):
        mask = tokens_to_boolean_mask([0, 1, 5], K, B, P)
        self.assertEqual(len(mask), 1 + K * B * P)
        self.assertTrue(mask[0] and mask[1] and mask[5])
        self.assertFalse(mask[2])

    def test_invalid_ids_rejected(self):
        with self.assertRaises(ValueError):
            decode_token(K * B * P + 1, K, B, P)          # id too large
        with self.assertRaises(ValueError):
            decode_token(-1, K, B, P)                     # negative
        with self.assertRaises(ValueError):
            encode_token(K, 0, 0, K, B, P)                # device out of range
        with self.assertRaises(ValueError):
            encode_token(0, B, 0, K, B, P)                # beam out of range
        with self.assertRaises(ValueError):
            encode_token(0, 0, P, K, B, P)                # power out of range
        with self.assertRaises(ValueError):
            tokens_to_boolean_mask([1 + K * B * P], K, B, P)  # feasible id out of range
        with self.assertRaises(ValueError):
            alphabet_size(0, B, P)                        # bad dims


if __name__ == "__main__":
    unittest.main(verbosity=2)
