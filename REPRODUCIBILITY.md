# Reproducibility

## Environment

Python dependencies are listed in `requirements.txt`. The scientific simulator and PPO implementation are under `simulation/`.

## Tests

Run:

```bash
python3 tools/verify_release.py
```

The verifier runs the scientific unit/regression suites and checks the archived confirmatory result inventory. It does not modify result files.

## Confirmatory results

The confirmatory campaign uses matched seeds 20001–20010 and the five-load grid stored in `configs/confirmatory_protocol_lock.json`. Seed-level metrics and paired statistical comparisons are archived in `results/confirmatory/`.

## Re-running the campaign

The campaign runner is `tools/run_confirmatory.py`. Re-running is optional and can be computationally expensive. The archived result files should be treated as immutable reference outputs when validating the published analysis.
