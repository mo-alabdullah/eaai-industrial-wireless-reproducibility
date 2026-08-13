# AI-Enabled Beamforming and Dynamic Spectrum Allocation for Reliable Long-Range IoT over 6G

Reproducibility repository for the research implementation, confirmatory data, tests, and manuscript by **Mohammed Alabdullah**.

- ORCID: 0009-0001-0826-4380
- Correspondence: m.w@sudo-gate.com
- Affiliation: Department of Network Engineering, School of Computer Engineering, Iran University of Science and Technology (IUST), Tehran, Iran

## Study overview

This repository evaluates resource allocation for mixed static-sensor and mobile AMR/AGV traffic in an indoor industrial mmWave setting. The implementation combines finite-codebook receive-beam selection, dynamic subchannel allocation, discrete power control, queue/deadline accounting, and PPO-based constrained control.

The confirmatory campaign uses fresh matched seeds across five offered loads. In the evaluated regime, deadline-aware heuristics provide the strongest packet-delivery reliability. The learned policies operate at lower average transmit power, while learned beam selection remains weak under the bounded training budget and the Lagrangian variant is not measurably differentiated from the unconstrained PPO variant in the primary results.

## Repository layout

- `simulation/`: environment, channel, mobility, action codec/mask, baselines, and PPO agents.
- `tests/`: deterministic unit and regression tests.
- `configs/`: scenario, action-specification, and confirmatory-protocol configuration.
- `tools/`: confirmatory runner and publication-data utilities.
- `results/confirmatory/`: frozen confirmatory seed-level results and statistics.
- `results/exploratory/`: exploratory/pilot summaries kept separate from confirmatory inference.
- `figures/`: publication figures.
- `paper/`: manuscript source, generated PDF, document file, and document class.
- `docs/`: reproducibility and integrity notes.

## Quick verification

Create an environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the test suite:

```bash
python3 tools/verify_release.py
```

The verifier is read-only with respect to archived experiment results.

## Confirmatory design

Primary confirmatory seeds: `20001`–`20010`.

Offered-load grid:

```text
0.05, 0.10, 0.20, 0.30, 0.40
```

The archived confirmatory result files are the basis for the manuscript's headline statistics. Exploratory results are stored separately and are not used for confirmatory inference.

## License

Software and repository tooling are released under the MIT License. Third-party standards and cited publications are not redistributed by this repository.
