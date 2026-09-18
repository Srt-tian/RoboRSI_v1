# Provenance and redistribution boundaries

- `ik.py`, geometry checks, smoothing/retiming, hold helpers, program compiler, execution adapter and report tools were consolidated from this project's supervised Piper experiments.
- The original inference I/O implementation lives in a separate internal checkout and is an **external dependency**. Neither its source nor its action-buffer implementation is included here.
- The commissioned dual-system URDF and robot mesh assets are not redistributed. Supply your own authorized rig description. Historical numerical joint trajectories and measured TCP coordinates remain in the evidence files.
- No model weights, credentials, SSH identities, private host addresses or deployment configs are included.
- `metrics.json` covers multiple experimental attempts, including failures and resumed execution. `servo20` is the final successful three-object trial.
- `examples/three_objects.json` preserves the original coarse waypoints and adds explicit historical-replay metadata. It cannot be treated as a fresh hardware plan.
- `raw_logs/` stores compressed original event/command/feedback JSONL logs from the 20 recorded controller sessions. `manifest.json` records original and compressed hashes. These are data records, not runnable scripts.
- The public package removes workstation-specific paths and generates the same 17,046-target final stream in offline comparison. The reorganized hardware adapter has **not** been revalidated on the robot after refactoring.
- No new license is asserted for external inference, SDK, vendor descriptions or third-party methods. A repository-wide redistribution license has not yet been selected by the owner.

## Claims boundary

The planning role in the session was referred to as GPT6. The logs do not independently establish an exact model API identifier, token count or precisely one API request. Report a fixed scene-grounded program with no new vision/model calls during the recorded stream, not a measured one-call autonomous benchmark.

RSI here means supervised cross-trial refinement; no automatic learned online RSI update or validated small-VLM residual improvement was demonstrated. The final trial is one 3/3 result, not a population success rate.
