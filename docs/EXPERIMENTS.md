# Experimental record · 2026-09-17

## What succeeded

- Final three-object run: pepper → carrot → eggplant, 3/3 in basket, **85.4158 s**, measured **200.00004 Hz**, no mid-run replanning/protection stop. Final RGB and operator agree.
- Single-object 2× profile: **31.5376 s**, no interruption. Operator confirmed carrot placement and then replaced the carrot with an eggplant before the final photograph; that photograph is not visual proof of the carrot outcome.
- Earlier fixed full program: carrot in basket, **104.0349 s**. Different scene/path and stage waits: not a controlled speed benchmark.

## Preserve failures and interventions

| Sessions | Stage | Outcome |
|---|---|---|
| 01–04 | Supervised commissioning | Initial CAN side mismatch; correction and recovery; carrot success and return |
| 05–06 | Small VLM residual exploration | Two high-clearance nominal chunks; no nonzero residual executed; unit/sign error rejected and token-limit service error |
| 07–08 | Fixed full program | Successful single-object task, 104.03 s |
| 09–10 | First continuous stream | Startup watchdog issue corrected; subsequent empty grasp stopped |
| 11–13 | Recovery and retry | Returned; next attempt stopped on measured TCP floor before completing grasp |
| 14–16 | Operator-approved continuation | Grip/lift recovery then remaining trajectory completed in 45.43 s; not total task time |
| 17 | 2× single-object | Continuous success, 31.54 s |
| 18–19 | First three-object attempt | Pepper empty grasp; other objects not attempted; returned |
| 20 | Deeper three-object attempt | 3/3 success, 85.42 s, returned |

Final gripper widths after closure: **39.3 / 41.6 / 38.9 mm**. Measured command interval P99 **5.116 ms**, max **5.614 ms**. Maximum recorded joint tracking error **0.05543 rad**. Measurements do not imply a guaranteed future bound.

## Final settings

- TCP grasp targets: base z=6 mm for all three objects; measured floor=0 mm.
- Earlier failed three-object targets: 16–18 mm. Final trial changed both depth and pepper orientation; not an isolated depth ablation.
- 200 Hz commands; ~50 Hz supervision; queue size 512; gripper dwell 0.8 s.
- 2× retiming constraints: v≤0.5 rad/s, a≤4 rad/s²; inference transport cap 0.6 rad/s. Actual final plan peaks are lower.
- Planned J5 cap 1.17 rad. Earlier single-object run briefly measured 1.221416 rad against URDF 1.22 rad; retain this limitation.
- Camera localization used nominal extrinsics and previous residual correction, not a separately validated calibrated perception system.

## Data and measurement semantics

[Metrics](../experiments/2026-09-17/metrics.json), [manifest](../experiments/2026-09-17/manifest.json), [compressed raw logs](../experiments/2026-09-17/raw_logs/), and the final success images are versioned. Command `monotonic_sec` measures host-side writes; q14 feedback is in true radians and metres. Early sessions have endpoint feedback only.

The task was visually open loop during the final stream. Low-level joint tracking and feedback guards remained active. Nonzero closure width alone is not evidence that an object reached the basket.

For research evaluation, repeat a fixed reset protocol, separate object-level and task-level outcomes, record interventions and total wall time, and distinguish frozen-plan execution from cross-trial refinement. No aggregate success-rate claim is supported by this small, adapted sequence.
