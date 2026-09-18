"""Compile coarse left-arm joint programs into bounded 200 Hz target streams."""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .smoothing import ARM, retime
from .ik import URDFIK
from .geometry import check_geometry
from .hold import REFERENCE_HASH


def compile_program(program, *, speed=1.0, urdf=None, tcp_floor=0.004):
    if speed not in (1.0, 2.0):
        raise ValueError("validated profiles are 1x and 2x")
    if not np.isfinite(tcp_floor) or not 0 <= tcp_floor <= 0.1:
        raise ValueError("floor must be finite and within [0, 0.1] m")
    initial = np.asarray(program["initial_state"]["q14"], float)
    if initial.shape != (14,) or not np.isfinite(initial).all():
        raise ValueError("finite q14 initial state required")
    if np.any(initial[[6, 13]] < 0) or np.any(initial[[6, 13]] > 0.071):
        raise ValueError("invalid initial gripper width")
    q = initial.copy()
    pending = []
    phases = []
    points = []
    events = []
    reports = []
    ik = URDFIK(urdf, "left_base_link", "left_tcp") if urdf else None
    other = URDFIK(urdf, "right_base_link", "right_tcp") if urdf else None

    def flush():
        nonlocal q, pending, phases
        if not pending:
            return
        dense, report = retime(q, pending, velocity=0.25 * speed, acceleration=speed**2)
        if ik:
            for row in np.vstack([q, dense]):
                if np.any(row[:6] < ik.lower) or np.any(row[:6] > ik.upper):
                    raise ValueError("joint limits")
                check_geometry(ik, row[:6], other, row[7:13], "left", tcp_floor)
        events.append(
            {"kind": "phase", "index": len(points), "phase": "+".join(phases)}
        )
        points.extend(dense.tolist())
        q = dense[-1].copy()
        reports.append(dict(report, phases=phases))
        pending = []
        phases = []

    for stage in program["program"]:
        c = stage["command"]
        if c["op"] == "trajectory":
            path = np.asarray(c["joint_waypoints"], float)
            if (
                path.ndim != 2
                or path.shape[1] != 6
                or len(path) < 2
                or not np.isfinite(path).all()
            ):
                raise ValueError("finite Nx6 path including seed required")
            seed = pending[-1][:6] if pending else q[:6]
            if not np.allclose(path[0], seed, atol=1e-7, rtol=0):
                raise ValueError("discontinuous coarse path seed")
            phases.append(stage["phase"])
            for waypoint in path[1:]:
                row = q.copy()
                row[:6] = waypoint
                pending.append(row)
        elif c["op"] == "gripper":
            flush()
            width = float(c["width_m"])
            bounds = np.asarray(stage["check_width_m"], float)
            if not np.isfinite(width) or not 0 <= width <= 0.07:
                raise ValueError("invalid gripper target")
            if (
                bounds.shape != (2,)
                or not np.isfinite(bounds).all()
                or not 0 <= bounds[0] <= bounds[1] <= 0.071
            ):
                raise ValueError("invalid gripper guard")
            if stage["phase"] not in ("close_gripper", "release"):
                raise ValueError("explicit close_gripper/release event required")
            start = len(points)
            q[6] = width
            points.extend([q.tolist() for _ in range(160)])
            events.extend(
                [
                    {"kind": "phase", "index": start, "phase": stage["phase"]},
                    {
                        "kind": "gripper_check",
                        "index": len(points) - 1,
                        "phase": stage["phase"],
                        "width_range": bounds.tolist(),
                    },
                ]
            )
        else:
            raise ValueError("unknown coarse operation")
    flush()
    if not points:
        raise ValueError("empty program")
    a = np.asarray(points)
    delta = np.diff(np.vstack([initial, a])[:, ARM], axis=0) * 200
    acceleration = np.diff(delta, axis=0) * 200
    if np.max(abs(delta)) > 0.25 * speed + 1e-3 or (
        len(acceleration) and np.max(abs(acceleration)) > speed**2 + 0.02
    ):
        raise ValueError("full-stream kinematic limits exceeded")
    return {
        "version": "roborsi-stream-v1",
        "initial_state": program["initial_state"],
        "control_hz": 200,
        "queue_capacity": 512,
        "targets": points,
        "events": sorted(events, key=lambda e: e["index"]),
        "estimated_duration_s": len(points) / 200,
        "max_joint_vel_rad_s": 0.3 * speed,
        "robot_io_sha256": REFERENCE_HASH,
        "tcp_floor_m": tcp_floor,
        "geometry_verified": bool(ik),
        "urdf_sha256": hashlib.sha256(Path(urdf).read_bytes()).hexdigest()
        if urdf
        else None,
        "requires_fresh_scene_and_seed": program.get("execution_intent") != "live",
        "scene": program.get("scene"),
        "simulation": reports,
        "max_sample_velocity_rad_s": float(np.max(abs(delta))),
        "max_sample_acceleration_rad_s2": float(np.max(abs(acceleration)))
        if len(acceleration)
        else 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("program", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--speed", type=float, choices=[1, 2], default=1)
    p.add_argument("--urdf", type=Path)
    p.add_argument("--tcp-floor", type=float, default=0.004)
    a = p.parse_args()
    source = a.program.read_bytes()
    stream = compile_program(
        json.loads(source), speed=a.speed, urdf=a.urdf, tcp_floor=a.tcp_floor
    )
    stream["source_program_sha256"] = hashlib.sha256(source).hexdigest()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x") as f:
        json.dump(stream, f, separators=(",", ":"))
    print(
        json.dumps(
            {
                "targets": len(stream["targets"]),
                "expected_s": stream["estimated_duration_s"],
                "geometry_verified": stream["geometry_verified"],
                "historical": stream["requires_fresh_scene_and_seed"],
                "sha256": hashlib.sha256(a.output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
