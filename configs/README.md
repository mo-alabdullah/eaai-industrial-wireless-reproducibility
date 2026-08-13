# Configuration Guide

## Executed confirmatory configuration

The reported confirmatory campaign uses the frozen configuration recorded in
`confirmatory_protocol_lock.json` and the archived `results/confirmatory/run_manifest.json`:

- 6 static sensors + 2 mobile AMR/AGV devices (`K=8`)
- 4 orthogonal subchannels (`N=4`)
- 8 receive antennas (`M=8`)
- 8 DFT receive beams (`B=8`)
- power levels `0.05, 0.10, 0.20, 0.40 W`
- 28 GHz carrier
- 200 measurement slots followed by full drain
- confirmatory seeds `20001`–`20010` across five offered loads

The simulator constructs this runtime scenario through `simulation/m2/config.py::confirmatory_config`.

## Retained design-stage specifications

`primary_scenario_config.json`, `primary_action_spec.json`, and `reference_action_spec.json` are
retained deterministic design/specification artifacts used by action-space and masking tests. Their
`N_primary=8` value belongs to that earlier specification tier and is **not** the subchannel count used
for the reported confirmatory campaign.

The two tiers are intentionally retained because they serve different reproducibility purposes;
reported scientific results use the executed confirmatory configuration above.
