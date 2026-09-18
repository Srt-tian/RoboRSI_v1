"""Validate an execution artifact before any driver or CAN initialization."""

import numpy as np
from .hold import REFERENCE_HASH
from .smoothing import ARM


def validate_stream(plan):
    points = np.asarray(plan["targets"], float)
    initial = np.asarray(plan["initial_state"]["q14"], float)
    if (
        initial.shape != (14,)
        or not np.isfinite(initial).all()
        or points.ndim != 2
        or points.shape[1] != 14
        or not len(points)
        or not np.isfinite(points).all()
    ):
        raise ValueError("finite q14 initial state and nonempty Nx14 targets required")
    if plan["control_hz"] != 200 or plan["queue_capacity"] != 512:
        raise ValueError("unsupported control frequency or queue capacity")
    if plan["robot_io_sha256"] != REFERENCE_HASH:
        raise ValueError("unsupported inference implementation")
    if not np.isfinite(plan["tcp_floor_m"]) or not 0 <= plan["tcp_floor_m"] <= 0.1:
        raise ValueError("invalid TCP floor")
    speed = plan["max_joint_vel_rad_s"] / 0.3
    if speed not in (1.0, 2.0):
        raise ValueError("unsupported speed profile")
    if not np.allclose(points[:, 7:], initial[7:], atol=1e-12, rtol=0):
        raise ValueError("this executor requires an unchanged right arm")
    if np.any(points[:, [6, 13]] < 0) or np.any(points[:, [6, 13]] > 0.071):
        raise ValueError("gripper range")
    velocity = np.diff(np.vstack([initial, points])[:, ARM], axis=0) * 200
    acceleration = np.diff(velocity, axis=0) * 200
    if np.max(abs(velocity)) > 0.25 * speed + 0.001 or (
        len(acceleration) and np.max(abs(acceleration)) > speed**2 + 0.02
    ):
        raise ValueError("stream velocity/acceleration limits")
    if abs(plan["estimated_duration_s"] - len(points) / 200) > 0.005:
        raise ValueError("duration disagrees with stream length")
    last = -1
    for event in plan["events"]:
        i = event["index"]
        if not isinstance(i, int) or not last <= i < len(points):
            raise ValueError("event ordering/index")
        last = i
        if event["kind"] == "gripper_check":
            lo, hi = event["width_range"]
            if not np.isfinite([lo, hi]).all() or not 0 <= lo <= hi <= 0.071:
                raise ValueError("gripper guard range")
            if event["phase"] not in ("close_gripper", "release"):
                raise ValueError("unknown gripper phase")
        elif event["kind"] != "phase":
            raise ValueError("unknown event")
    return points, initial
