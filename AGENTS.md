# Repository rules

- Default workflows are offline. Never send CAN commands in tests, CI, import, report, or compile.
- Hardware is opt-in via explicit execution, verified external inference code/config, fresh state, scene and URDF checks.
- Never disable/reset Piper motors or release the gripper in cleanup. Stop the sole writer, clear the queue, freeze one fresh measured target, retain support. Do not automatically resume a protection stop.
- The physical left/right CAN naming on the experimental rig was reversed. Verify USB identity, never infer physical side from interface label.
- Keep private inference source, secrets, machine addresses, and local configs out of Git.
- Historical examples cannot be marked live or replayed on hardware without a new scene and initial state.
- Separate observed task success from program completion. Do not claim automatic RSI learning or exact single-API inference from these records.
