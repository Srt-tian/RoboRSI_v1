# RoboTwin native-expert qualification

This is a fixed-seed development check of the simulator, assets, planner and
success predicate. It is not a trained-policy result or evidence for JEV/RSI.

- Upstream: RoboTwin commit `13c3c47ff4312dd62484bcd51be034af55c062d1`.
- CuRobo source: `d64c4b005459db10c5dd867d8b30a87d5bda9bdb`.
- `demo_clean`, Aloha-AgileX, original physics/material/planner settings.
- First tasks: `handover_block`, `lift_pot`, `stack_blocks_three`; seeds 0 and 1.
  Start with seed 0 of handover; retain failures and every compatibility fix.
- Call native `setup_demo` and `play_once`; no success-conditioned seed search.
- Do not combine these expert results with learned-policy benchmark scores.
- Record planner success separately from final task success. Record measured
  articulation qpos/qvel and commanded joint targets at 250 Hz; capture live
  head-camera frames at 5 Hz. Initialization and planning wall time are reported.
- Upstream `joint_action.vector` contains drive targets, **not** measured arm
  positions. Keep that distinction in all future model interfaces.
- The setup uses a relocated environment copy, not a modification of a shared
  environment. Validate imports, CUDA execution, rendering and planning before
  considering it ready. Keep original asset archive checksums and runtime
  package versions. Render-only success does not establish task success.

```bash
python scripts/robotwin_probe.py \
  --robotwin-root "$ROBOTWIN_ROOT" \
  --expected-upstream 13c3c47ff4312dd62484bcd51be034af55c062d1 \
  --task handover_block --seed 0 --output "$RUN_DIR"
```

The benchmark implementation and adapter must both have clean source trees.
Task output goes outside either checkout. Asset absolute paths are generated
with the upstream `script/update_embodiment_config_path.py` in the private
runtime; they are not committed to this repository.
