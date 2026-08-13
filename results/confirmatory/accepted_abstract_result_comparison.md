# Accepted-Abstract Hypothesis Comparison — CONFIRMATORY (confirmatory)

Confirmatory Layer-1 (fixed-radio) results only; accepted DOCX untouched; hypothesis checks; pooled PDR.

| # | Accepted hypothesis | Observed | Verdict |
|---|---|---|---|
| 1 | Base PPO > Random for static | PPO>=Random all loads = False (p=0.40 PPO 0.580 vs Rand 0.989) | DOES NOT SUPPORT |
| 2 | Congestion onset at finite load | first load mobile PDR<0.99 (Random) = 0.05 | SUPPORTS |
| 3 | Mobile degrades earlier than static | mobile<static some load = True | SUPPORTS |
| 4 | Random beats Base PPO for mobile (inversion) | inversion loads = [0.05, 0.1, 0.2, 0.3, 0.4] | SUPPORTS |

| load | static PPO | static Rand | mobile PPO | mobile Rand |
|---|---|---|---|---|
| 0.05 | 0.651 | 0.995 | 0.511 | 0.977 |
| 0.1 | 0.632 | 0.998 | 0.486 | 0.984 |
| 0.2 | 0.625 | 1.000 | 0.501 | 0.967 |
| 0.3 | 0.619 | 1.000 | 0.487 | 0.935 |
| 0.4 | 0.580 | 0.989 | 0.463 | 0.815 |

**Integrity:** confirmatory data only; no data/model altered after seeing results; accepted DOCX byte-identical.

