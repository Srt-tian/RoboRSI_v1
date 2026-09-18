# Hardware adapter

The default compiler and viewer never import the Piper SDK or write CAN. The hardware adapter is derived from the tested experimental runner, but its new packaging/configuration boundary has only been tested offline.

## External dependencies

Provide a commissioned inference checkout with `robot_io.PiperDualArm`, its normal Python dependencies, and its existing configuration. The supported `robot_io.py` SHA256 is:

```
8727832976b4968d12283c8cb6cdef945f1eace8e472c080c6272c464514a782
```

This pin intentionally rejects other versions. Do not update it merely to bypass a mismatch. Audit CAN/SDK units, start/stop, queue, logger and close semantics before adapting another version. Internal source is not vendored.

The URDF must provide `left_base_link`, `left_tcp`, `right_base_link`, `right_tcp`. Geometry checks currently encode this commissioned mount arrangement (±0.30266 m in Y), workspace and link-distance thresholds. Changing robots requires updating and validating these assumptions, not just providing an arbitrary URDF.

## Prepare a fresh plan

1. Verify on-site stop availability, workspace clearance and supported arm hold.
2. Read fresh scene and physical-arm joint/gripper feedback. Do not infer side from a CAN name.
3. Generate a new coarse plan with the correct current scene, targets and initial state. Only such a reviewed plan may use `"execution_intent": "live"`; renaming a historical example does not make it safe.
4. Compile with `--urdf /path/to/commissioned.urdf` and a justified `--tcp-floor`. The last trial used 0 m floor and 6 mm grasp targets; these are **recorded rig parameters, not universal defaults**.
5. Review the output and SHA256. Initial live-state mismatch >0.015 rad or left gripper mismatch >5 mm is rejected on startup.

Mapping file schema (replace every placeholder from actual USB inspection):

```json
{
  "left": {"interface": "PHYSICAL_LEFT_CAN", "usb_path": "USB_PATH_LEFT"},
  "right": {"interface": "PHYSICAL_RIGHT_CAN", "usb_path": "USB_PATH_RIGHT"}
}
```

The adapter verifies both sysfs USB identity and inference arm `can_name`. Existing CAN interfaces must be active; configuration `can.activate` must be false. Motors must already be enabled and holding; automatic enabling is disabled.

## Explicit execution interface

After commissioning and reviewing the fresh plan:

```bash
roborsi-execute --stream runs/fresh.stream.json --sha256 REVIEWED_STREAM_SHA256 \
  --inference-dir /path/to/inference/client/inference \
  --config /path/to/local_client.yaml --mapping /path/to/local_mapping.json \
  --urdf /path/to/commissioned.urdf --log runs/new_trial.jsonl --execute
```

Omit `--execute` for a dry inspection. A terminal is required for hardware mode. Existing log files are never overwritten. Geometry is checked before SDK connection; target state and status are checked before streaming.

## Execution and stopping

The original inference worker writes targets at 200 Hz. A 512-target queue is prefilled and replenished. Joint feedback/status, joint limits, floor, tracking error, inactive-arm drift, gripper width and worker health are checked by a ~50 Hz supervisor.

On completion, fault, SIGINT or SIGTERM: stop and join the sole writer, clear pending targets, read one fresh measured state, freeze it once, and preserve motor support and gripper. Never use motor disable, emergency/reset commands, release-on-stop or drift-following hold as cleanup. If joining or obtaining valid state fails, the software does not invent a new hold target; operator intervention is required. Do not automatically resume a protection stop.

The supervisor is not hard real time. A guard can be detected a few command ticks after its event, and a missed object can still satisfy a width test. Final visual/task validation is separate. No full mesh/environment collision model or visual servoing is provided.
