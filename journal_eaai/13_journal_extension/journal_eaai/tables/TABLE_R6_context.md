# TABLE R6 — Learned-controller and heuristic context

> ### DEVELOPMENT-TIER TABLE — NOT CONFIRMATORY EVIDENCE
> Every numerical row below comes from **development seeds 20001–20010**. None of these values was
> produced by the confirmatory campaign, none appears in any endpoint, and none may be compared with
> a confirmatory number in Tables R1–R5. The table is included for context about the inherited
> controller, not as evidence about it.

**Evidence class: DEVELOPMENT ONLY. EVIDENCE TIER IS STATED PER ROW.** Development and final values
are never mixed in one column. **No learned controller appears anywhere in the final confirmatory
campaign**, on either side of any endpoint; the six comparators actually executed are
`EDF-StaleBeam-MinFeasible`, `EDF+ExactFixedDemand`, `ExactFixedDemandRadio`, `ContinuousPowerRef`,
`OfflineExactAgedGain` and `OfflineExactCurrentGain`. Sources: learned rows from
`results/reeval_bsa.csv`; heuristic row from `results/stage_d_baselines.csv`; both at offered load
0.4, development seeds 20001–20010 (n = 10 each).

| tier | method | source | static PDR | mobile PDR | mean aggregate power (W) | beam-selection agreement with oracle | spectral efficiency |
|---|---|---|---|---|---|---|---|
| DEVELOPMENT | inherited constrained autoregressive PPO controller (BSA-C-PPO) | development seeds | 0.9672 | 0.9341 | 0.5967 | 0.1392 | 1.2866 |
| DEVELOPMENT | BSA-Penalty-PPO | development seeds | 0.9672 | 0.9342 | 0.5966 | 0.1392 | 1.2867 |
| DEVELOPMENT | BSA-Unconstrained-PPO | development seeds | 0.9672 | 0.9341 | 0.5967 | 0.1392 | 1.2866 |
| DEVELOPMENT | EDF-StaleBeam-MinPow (minimum-feasible-power deadline heuristic) | development seeds | 0.9999 | 1.0000 | 0.1650 | — | — |
| FINAL | *(none — no learned method was executed in the confirmatory campaign)* | — | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED |

**Notes.** All learned-method observations are conditional on the executed training budget of 80
episodes, collected as 8 episodes per update round over 10 update rounds, at policy learning rate
3e-3 and critic learning rate 5e-3. The three variants were separately trained from the same seed
with the same architecture, so a difference between them is a difference between training
mechanisms under that budget and nothing more. Under this budget the three variants are
indistinguishable to four decimal places on every column above, and the minimum-feasible-power
deadline heuristic delivered more packets in both classes at roughly 28 % of the learned family's
mean aggregate power. These are development diagnostics; they are never presented as confirmatory,
and they support no claim about the method's ceiling.

The implemented constrained formulation carries **seven cost components, of which five can become
binding** under the executed parameters; both overflow components are structurally unbindable
(per-class deadlines are strictly below queue capacity), their multipliers remain at zero for every
update, and they exert no policy pressure. The overflow constraints are therefore reported as
INACTIVE rather than as satisfied or enforced.
