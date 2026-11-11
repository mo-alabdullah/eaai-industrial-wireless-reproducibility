#!/usr/bin/env python3
"""Independent recomputation of the deterministic M1 design fixtures.

Reads ONLY a `<fixture>_inputs.csv` and recomputes expected transitions and metrics
from first principles. It does NOT read the expected-transition or expected-metrics
files; test_reference_case_design.py cross-checks the hand-authored expected files
against this independent recomputation.

Modelled rules (all derived from the mathematical-model documents):
  * deadline_slot = arrival + D - 1 (hard deadline; no delivery after it).
  * Locked physical-slot event order: deadline expiry is applied BEFORE service.
  * OMA per-subchannel SINR gamma = p_alloc * beta * G / sigma^2, beta = link H2
    here, G = g_beam (fixed).
  * Shannon threshold gamma_th = 2^(Z/(W*tau)) - 1 is DERIVED from Z_bits, W_hz,
    tau_s; any supplied gamma_th is verified against the derived value.
  * One-distinct-packet service: at most ONE distinct FIFO packet is served per
    allocated subchannel in a slot (no packet is served on two subchannels at once).
  * Action masks: a masked (subchannel, device) pair is not served this slot.
  * Per-device total transmit-power cap enforced as a FEASIBILITY MASK: every attempt
    uses a FIXED per-attempt power p_w (there is NO equal-power split). A subchannel whose
    cumulative committed power would exceed the device cap is a `power_cap_violation` and
    transmits nothing (it does not consume a packet). With no cap, each attempt uses p_w.
  * Packet-aware feasibility (action fixture): a non-idle token to a device with no
    remaining eligible packet is a `packet_mask_violation`, never silently repaired to idle.
  * Mutually exclusive drop precedence: a packet dropped for DEADLINE_EXPIRED is never
    also RETRANSMISSION_EXHAUSTED (and vice-versa); each dropped packet has exactly one
    drop reason.

This is a design/verification artifact, not the scientific simulator.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "reference_case_inputs.csv"


def load_inputs(path: Path = INPUTS):
    params, packets, link, assign = {}, {}, {}, []
    masks, powercap = set(), {}
    # fixture-3 (full-action) tables:
    beams, powers, actions = {}, {}, []
    beammask, powermask = set(), set()
    with Path(path).open(encoding="utf-8") as f:
        for r in csv.reader(f):
            if not r or r[0] == "kind" or r[0].strip().startswith("#"):
                continue
            kind = r[0].strip()
            if kind == "param":
                params[r[1]] = r[2]
            elif kind == "packet":
                packets[r[1]] = {"device": r[2], "arrival": int(r[3]), "D": int(r[4])}
            elif kind == "link":
                link[(r[1], int(r[2]))] = float(r[3])
            elif kind == "assign":
                assign.append((r[1], r[2]))     # (subchannel, device) — PARSED, not hardcoded
            elif kind == "mask":
                slot = r[3].strip()
                masks.add((r[1], r[2], "all" if slot in ("", "all") else int(slot)))
            elif kind == "powercap":
                powercap[r[1]] = float(r[2])    # per-device total power cap in a slot
            elif kind == "beamgain":
                beams[r[1]] = float(r[2])       # beam_id -> receive-beam gain G_b
            elif kind == "powerlevel":
                powers[r[1]] = float(r[2])      # power_id -> transmit power (W)
            elif kind == "action":
                # slot, subchannel, device, beam_id, power_id  (PARSED, not defaulted)
                actions.append((int(r[1]), r[2], r[3], r[4], r[5]))
            elif kind == "beammask":
                beammask.add((int(r[1]), r[2], r[3]))    # (slot, subch, beam_id) forbidden
            elif kind == "powermask":
                powermask.add((int(r[1]), r[2], r[3]))   # (slot, subch, power_id) forbidden
    act = {"beams": beams, "powers": powers, "actions": actions,
           "beammask": beammask, "powermask": powermask}
    if not assign and not actions:
        raise ValueError("no 'assign' or 'action' rows in inputs")
    return params, packets, link, assign, masks, powercap, act


def _validate(params, packets, link, assign, masks, powercap):
    """Reject internally inconsistent inputs (used inputs must be present/consistent)."""
    devices = {pk["device"] for pk in packets.values()}
    assigned_devs = {d for _, d in assign}
    for sub, dev in assign:
        if dev not in devices:
            raise ValueError(f"assign references unknown device {dev}")
    for sub, dev, slot in masks:
        if (sub, dev) not in {(s, d) for s, d in assign}:
            raise ValueError(f"mask references unassigned pair {(sub, dev)}")
    for dev in powercap:
        if dev not in assigned_devs:
            raise ValueError(f"powercap references unassigned device {dev}")
        if powercap[dev] <= 0:
            raise ValueError(f"powercap[{dev}] must be > 0")
    # link presence is validated at point of use (only serviced slots are "used inputs").


def _recompute_action_fixture(params, packets, link, powercap, act):
    """Fixture-3: the action carries (device, receive-beam, power level) per subchannel.
    Beam gain and transmit power are PARSED from the action (not a fixed g_beam / equal
    split). Enforces beam-validity masks, power-validity masks, per-device total-power cap,
    and flags beam choices that are worse than the feasible Max-Gain-Beam baseline."""
    for k in ("sigma2", "Z_bits", "W_hz", "tau_s", "horizon_slots", "max_retx"):
        if k not in params:
            raise ValueError(f"missing input param: {k}")
    sigma2 = float(params["sigma2"]); tau = float(params["tau_s"])
    horizon = int(params["horizon_slots"]); max_retx = int(params["max_retx"])
    Z = float(params["Z_bits"]); W = float(params["W_hz"])
    gth = 2 ** (Z / (W * tau)) - 1
    if "gamma_th" in params and abs(float(params["gamma_th"]) - gth) > 1e-9:
        raise ValueError(f"supplied gamma_th {params['gamma_th']} != derived {gth}")
    beams, powers = act["beams"], act["powers"]
    beammask, powermask = act["beammask"], act["powermask"]
    devices_present = {pk["device"] for pk in packets.values()}
    for (t, sub, dev, bid, pid) in act["actions"]:
        if bid == "idle" or pid == "idle":
            continue   # explicit idle token: no beam/power lookup
        if bid not in beams:
            raise ValueError(f"action beam {bid} not in beamgain table")
        if pid not in powers:
            raise ValueError(f"action power {pid} not in powerlevel table")
        if dev not in devices_present:
            raise ValueError(f"action device {dev} has no packets")

    for pk in packets.values():
        pk["deadline_slot"] = pk["arrival"] + pk["D"] - 1
        pk["status"] = "QUEUED"; pk["retry"] = 0; pk["drop_reason"] = None

    def queue_of(dev, t, exclude):
        cand = [pid for pid, pk in packets.items()
                if pk["device"] == dev and pk["arrival"] <= t
                and pk["status"] == "QUEUED" and pid not in exclude]
        cand.sort(key=lambda pid: packets[pid]["arrival"])
        return cand[0] if cand else None

    transitions = []
    tx_count = defaultdict(int); outage = defaultdict(int)
    energy_j = 0.0; served_per_slot = []
    counts = {"beam_mask_violation": 0, "power_mask_violation": 0,
              "power_cap_violation": 0, "beam_suboptimal": 0,
              "packet_mask_violation": 0}
    # N is an EXPLICIT fixture input (`param,n_subchannels,N`) — NOT derived from the
    # subchannels that happen to appear in the action rows (which would silently miss a
    # subchannel absent from EVERY slot). The canonical set is {n1,...,nN}; every physical slot
    # must place exactly N tokens, one per canonical subchannel (no duplicate, none missing, no
    # unknown). An explicit idle token uses beam="idle".
    if "n_subchannels" not in params:
        raise ValueError("action fixture requires explicit `param,n_subchannels,N`")
    N = int(params["n_subchannels"])
    if N < 1:
        raise ValueError(f"n_subchannels must be >= 1, got {N}")
    canonical = {f"n{i}" for i in range(1, N + 1)}
    # reject any token referencing a subchannel outside the canonical set n1..nN
    unknown = {sub for (_t, sub, _d, _b, _p) in act["actions"]} - canonical
    if unknown:
        raise ValueError(f"unknown subchannel token(s) not in n1..n{N}: {sorted(unknown)}")

    for t in range(horizon):
        rows = [a for a in act["actions"] if a[0] == t]
        subs = [sub for (_t, sub, _d, _b, _p) in rows]
        if len(rows) != N:
            raise ValueError(f"slot {t}: has {len(rows)} action tokens, expected exactly N={N}")
        if len(set(subs)) != len(subs):
            raise ValueError(f"slot {t}: duplicate subchannel token(s) {subs}")
        if set(subs) != canonical:
            missing = canonical - set(subs)
            raise ValueError(f"slot {t}: missing canonical subchannel token(s) {sorted(missing)}")
        # deadline expiry before service
        expired_now = set()
        for pid, pk in packets.items():
            if pk["status"] == "QUEUED" and pk["arrival"] <= t and t > pk["deadline_slot"]:
                pk["status"] = "DROPPED"; pk["drop_reason"] = "DEADLINE_EXPIRED"
                expired_now.add(pk["device"])
        dev_pow = defaultdict(float)   # cumulative committed power per device this slot
        attempted = set(); served = 0
        for (_t, sub, dev, bid, pid_beam) in rows:
            # explicit idle token: occupies the subchannel's slot but transmits nothing
            if bid == "idle" or pid_beam == "idle":
                transitions.append([t, sub, dev, "", "idle", "idle", "", "", "", "idle_action"])
                continue
            g = beams[bid]; p = powers[pid_beam]
            # feasible Max-Gain-Beam baseline over beams not masked on (t, sub)
            feas_beams = {b: gg for b, gg in beams.items()
                          if (t, sub, b) not in beammask}
            max_gain_beam = max(feas_beams, key=feas_beams.get) if feas_beams else None
            if (t, sub, bid) in beammask:
                counts["beam_mask_violation"] += 1
                transitions.append([t, sub, dev, "", bid, pid_beam, "", "", "",
                                    "beam_mask_violation"]); continue
            if (t, sub, pid_beam) in powermask:
                counts["power_mask_violation"] += 1
                transitions.append([t, sub, dev, "", bid, pid_beam, "", "", "",
                                    "power_mask_violation"]); continue
            cap = powercap.get(dev)
            if cap is not None and dev_pow[dev] + p > cap + 1e-12:
                counts["power_cap_violation"] += 1
                transitions.append([t, sub, dev, "", bid, pid_beam, "", "", "",
                                    "power_cap_violation"]); continue
            # feasible: commit power, flag sub-optimal beam vs feasible max-gain
            if max_gain_beam is not None and bid != max_gain_beam:
                counts["beam_suboptimal"] += 1
            # PACKET-AWARE MASK: a non-idle token to a device with no remaining eligible
            # packet (remaining_service_eligible_k after earlier committed distinct packets
            # for k, and after deadline expiry) is a MASK VIOLATION — the policy should have
            # emitted `idle`. It is flagged, NOT silently repaired into an idle transmission.
            pid = queue_of(dev, t, attempted)
            if pid is None:
                counts["packet_mask_violation"] += 1
                transitions.append([t, sub, dev, "", bid, pid_beam, "", "", "",
                                    "packet_mask_violation"]); continue
            attempted.add(pid); dev_pow[dev] += p
            if (dev, t) not in link:
                raise ValueError(f"missing link for serviced slot {(dev, t)}")
            H2 = link[(dev, t)]
            gamma = p * H2 * g / sigma2
            ok = 1 if gamma >= gth else 0
            tx_count[dev] += 1; served += 1; energy_j += p * tau
            pk = packets[pid]
            if ok:
                pk["status"] = "DELIVERED"
                transitions.append([t, sub, dev, pid, bid, pid_beam, H2, gamma, 1, "deliver"])
            else:
                outage[dev] += 1; pk["retry"] += 1
                if pk["retry"] > max_retx:
                    pk["status"] = "DROPPED"; pk["drop_reason"] = "RETRANSMISSION_EXHAUSTED"
                    ev = "retx_exhausted"
                else:
                    ev = "fail_retry"
                transitions.append([t, sub, dev, pid, bid, pid_beam, H2, gamma, 0, ev])
        served_per_slot.append(served / N)   # denominator is N subchannels, never len(rows)

    # censored-aware accounting: a packet still QUEUED at horizon end is CENSORED
    # (fate undecided), never silently counted as delivered or dropped.
    devices = sorted(devices_present)
    metrics = {}
    tot_gen = tot_del = tot_cen = 0
    for dev in devices:
        gen = [pk for pk in packets.values() if pk["device"] == dev]
        n = len(gen)
        d = sum(1 for pk in gen if pk["status"] == "DELIVERED")
        cen = sum(1 for pk in gen if pk["status"] == "QUEUED")
        drp = sum(1 for pk in gen if pk["status"] == "DROPPED")
        resolved = n - cen
        tot_gen += n; tot_del += d; tot_cen += cen
        metrics[f"PDR_lb_{dev}"] = d / n if n else 0.0             # censored = failure
        metrics[f"PDR_resolved_{dev}"] = d / resolved if resolved else 0.0
        metrics[f"censored_fraction_{dev}"] = cen / n if n else 0.0
        metrics[f"drop_ratio_excl_censored_{dev}"] = drp / resolved if resolved else 0.0
        metrics[f"link_outage_rate_{dev}"] = (outage.get(dev, 0) / tx_count[dev]
                                              if tx_count.get(dev) else 0.0)
    metrics["PDR_lb_aggregate"] = tot_del / tot_gen if tot_gen else 0.0
    tot_res = tot_gen - tot_cen
    metrics["PDR_resolved_aggregate"] = tot_del / tot_res if tot_res else 0.0
    metrics["censored_fraction_aggregate"] = tot_cen / tot_gen if tot_gen else 0.0
    metrics["energy_joules_total"] = round(energy_j, 6)
    metrics["spectrum_utilization_avg"] = round(sum(served_per_slot) / horizon, 4)
    for k, val in counts.items():
        metrics[k] = val
    return transitions, metrics


def recompute(inputs_path: Path = INPUTS):
    params, packets, link, assign, masks, powercap, act = load_inputs(inputs_path)
    if act["actions"]:
        return _recompute_action_fixture(params, packets, link, powercap, act)
    for k in ("sigma2", "Z_bits", "W_hz", "tau_s", "p_w", "g_beam", "max_retx",
              "horizon_slots"):
        if k not in params:
            raise ValueError(f"missing input param: {k}")
    _validate(params, packets, link, assign, masks, powercap)

    sigma2 = float(params["sigma2"])
    p_w = float(params["p_w"]); g = float(params["g_beam"])
    tau = float(params["tau_s"]); horizon = int(params["horizon_slots"])
    max_retx = int(params["max_retx"])
    Z = float(params["Z_bits"]); W = float(params["W_hz"])
    # DERIVE gamma_th from Z, W, tau (Shannon threshold); verify any supplied value.
    gth = 2 ** (Z / (W * tau)) - 1
    if "gamma_th" in params:
        supplied = float(params["gamma_th"])
        if abs(supplied - gth) > 1e-9:
            raise ValueError(f"supplied gamma_th {supplied} != derived {gth}")

    # packet state
    for pid, pk in packets.items():
        pk["deadline_slot"] = pk["arrival"] + pk["D"] - 1
        pk["status"] = "QUEUED"; pk["retry"] = 0; pk["delivery_slot"] = None
        pk["drop_reason"] = None

    def masked(sub, dev, t):
        return (sub, dev, "all") in masks or (sub, dev, t) in masks

    def queue_of(dev, t, exclude):
        # head-of-line QUEUED packet for dev not already attempted this slot
        # (Option A: one distinct FIFO packet per allocated subchannel).
        cand = [pid for pid, pk in packets.items()
                if pk["device"] == dev and pk["arrival"] <= t
                and pk["status"] == "QUEUED" and pid not in exclude]
        cand.sort(key=lambda pid: packets[pid]["arrival"])
        return cand[0] if cand else None

    transitions = []
    tx_count = defaultdict(int); outage = defaultdict(int)
    used_subch_per_slot = []
    energy_j = 0.0
    cap_violations = 0   # power-cap enforced as a feasibility MASK (no equal-power split)

    for t in range(horizon):
        # step 3: deadline expiry BEFORE service — record which packets expire THIS slot
        expired_now = set()
        for pid, pk in packets.items():
            if pk["status"] == "QUEUED" and pk["arrival"] <= t \
                    and t > pk["deadline_slot"]:
                pk["status"] = "DROPPED"; pk["drop_reason"] = "DEADLINE_EXPIRED"
                pk["expired_slot"] = t
                expired_now.add(pk["device"])

        # steps 5-8: single pass in assign order, deciding feasibility BEFORE consuming a
        # packet: (1) action mask, (2) power-cap feasibility mask with a FIXED per-attempt
        # power p_w (NO equal-power split; a cap-exceeding subchannel is a power_cap_violation
        # and transmits nothing), (3) one distinct head-of-line packet per subchannel.
        attempted = set()
        dev_pow = defaultdict(float)   # cumulative committed power per device this slot
        used = 0
        for sub, dev in assign:
            if masked(sub, dev, t):
                transitions.append([t, sub, dev, "", "", "", "", "", "masked_forbidden_action"])
                continue
            cap = powercap.get(dev)
            if cap is not None and dev_pow[dev] + p_w > cap + 1e-12:
                cap_violations += 1
                transitions.append([t, sub, dev, "", "", "", "", "", "power_cap_violation"])
                continue
            pid = queue_of(dev, t, attempted)
            if pid is None:
                ev = ("deadline_expired_before_service" if dev in expired_now
                      else "idle_queue_empty")
                transitions.append([t, sub, dev, "", "", "", "", "", ev])
                continue
            # feasible: commit the fixed per-attempt power and serve the packet
            attempted.add(pid); dev_pow[dev] += p_w
            if (dev, t) not in link:
                raise ValueError(f"missing link for serviced slot {(dev, t)}")
            H2 = link[(dev, t)]
            gamma = p_w * H2 * g / sigma2
            success = 1 if gamma >= gth else 0
            tx_count[dev] += 1; used += 1
            energy_j += p_w * tau
            if not success:
                outage[dev] += 1
            pk = packets[pid]
            if success:
                pk["status"] = "DELIVERED"; pk["delivery_slot"] = t
                transitions.append([t, sub, dev, pid, H2, gamma, 1, pk["retry"], "deliver"])
            else:
                pk["retry"] += 1
                if pk["retry"] > max_retx:
                    pk["status"] = "DROPPED"; pk["drop_reason"] = "RETRANSMISSION_EXHAUSTED"
                    ev = "retx_exhausted"
                else:
                    ev = "fail_retry"
                transitions.append([t, sub, dev, pid, H2, gamma, 0, pk["retry"], ev])
        used_subch_per_slot.append(used / len(assign))

    # invariant: mutually exclusive drop precedence — one reason per dropped packet
    for pid, pk in packets.items():
        if pk["status"] == "DROPPED":
            assert pk["drop_reason"] in ("DEADLINE_EXPIRED", "RETRANSMISSION_EXHAUSTED"), pid

    # metrics — generic over the devices present
    devices = sorted({pk["device"] for pk in packets.values()})
    total_tx = sum(tx_count.get(dev, 0) for dev in devices)
    metrics = {}
    tot_gen = tot_del = 0
    for dev in devices:
        gen = [pk for pk in packets.values() if pk["device"] == dev]
        n = len(gen)
        d = sum(1 for pk in gen if pk["status"] == "DELIVERED")
        e = sum(1 for pk in gen if pk.get("drop_reason") == "DEADLINE_EXPIRED")
        rx = sum(1 for pk in gen if pk.get("drop_reason") == "RETRANSMISSION_EXHAUSTED")
        tot_gen += n; tot_del += d
        metrics[f"PDR_{dev}"] = d / n if n else 0.0
        metrics[f"deadline_violation_{dev}"] = e / n if n else 0.0
        metrics[f"retx_exhausted_{dev}"] = rx / n if n else 0.0
        metrics[f"link_outage_rate_{dev}"] = (outage.get(dev, 0) / tx_count[dev]
                                              if tx_count.get(dev) else 0.0)
        metrics[f"drop_ratio_{dev}_deadline"] = e / n if n else 0.0
    metrics["PDR_aggregate"] = tot_del / tot_gen if tot_gen else 0.0
    metrics["energy_joules_total"] = round(energy_j, 6)
    metrics["spectrum_utilization_avg"] = round(sum(used_subch_per_slot) / horizon, 4)
    metrics["power_cap_violation"] = cap_violations
    return transitions, metrics


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else INPUTS
    tr, m = recompute(path)
    print(json.dumps(m, indent=2))
    for row in tr:
        print(row)
