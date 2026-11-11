#!/usr/bin/env python3
"""Merge the Stage-I-CLOSEOUT re-runs over the original Stage-I-B results.

Closeout rows (solved at the raised budget) replace the censored originals; every other row is kept
verbatim. Writes results/stage_ib_joint_final.csv, which is the table source for all I-B reporting.
"""
from __future__ import annotations
import csv, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, '..', '..', 'results'))


def key(r): return (r["scale"], r["regime"], r["grid"], r["seed"], r["warmup"])


def load(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def main():
    base = {key(r): r for r in load(os.path.join(RES, "stage_ib_joint.jsonl"))}
    n_censored = sum(1 for r in base.values()
                     if r.get("joint_status") != "exact" or r.get("oracle_status") != "exact")
    close = load(os.path.join(RES, "stage_ib_closeout.jsonl"))
    replaced = 0
    for r in close:
        k = key(r)
        assert k in base, f"closeout row {k} not in base"
        r["closeout_rerun"] = 1
        base[k] = r
        replaced += 1
    rows = list(base.values())
    for r in rows:
        r.setdefault("closeout_rerun", 0)
    still = [key(r) for r in rows
             if r.get("joint_status") != "exact" or r.get("oracle_status") != "exact"]
    cols = sorted({c for r in rows for c in r})
    head = ["scale", "regime", "grid", "seed", "warmup", "H", "K", "N", "P",
            "dist_scale", "d_csi", "closeout_rerun", "joint_status", "oracle_status"]
    cols = head + [c for c in cols if c not in head]
    out = os.path.join(RES, "stage_ib_joint_final.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=key))
    print(f"base rows            : {len(base)}")
    print(f"censored in base     : {n_censored}")
    print(f"replaced by closeout : {replaced}")
    print(f"STILL censored       : {len(still)}  {still if still else '-> NONE'}")
    print(f"written              : {out}")


if __name__ == "__main__":
    main()
