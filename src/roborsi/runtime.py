"""Fixed continuous stream through unchanged inference high-follow worker."""

import argparse, json, hashlib, signal, sys, time
from pathlib import Path
from .hold import fresh_state, freeze_measured
from .ik import URDFIK
from .geometry import check_geometry
from .validation import validate_stream
import numpy as np

ARM = np.array([0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12])
TO_COMMAND = (180 / np.pi * 1000) / 57324.840764


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stream", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--inference-dir", type=Path)
    p.add_argument("--config", type=Path)
    p.add_argument("--urdf", type=Path)
    p.add_argument("--mapping", type=Path)
    a = p.parse_args()
    blob = Path(a.stream).read_bytes()
    if hashlib.sha256(blob).hexdigest() != a.sha256:
        raise ValueError("stream changed")
    plan = json.loads(blob)
    if a.execute and plan.get("requires_fresh_scene_and_seed", True):
        raise ValueError(
            "offline candidate: fresh scene and seed required before execution"
        )
    if plan.get("max_joint_vel_rad_s") not in (0.3, 0.6):
        raise ValueError("speed profile mismatch")
    points, initial = validate_stream(plan)
    cap = plan["queue_capacity"]
    if points.ndim != 2 or points.shape[1] != 14 or not np.isfinite(points).all():
        raise ValueError("invalid stream")
    if not a.execute:
        print(
            json.dumps(
                {
                    "mode": "dry",
                    "targets": len(points),
                    "expected_s": plan["estimated_duration_s"],
                }
            )
        )
        return
    if not sys.stdin.isatty():
        raise ValueError("TTY required for stop")
    if not all([a.inference_dir, a.config, a.urdf, a.mapping]):
        raise ValueError("hardware needs inference-dir, config, urdf, mapping")
    if not plan.get("geometry_verified"):
        raise ValueError("compile with the rig URDF before executing")
    if hashlib.sha256(a.urdf.read_bytes()).hexdigest() != plan.get("urdf_sha256"):
        raise ValueError("URDF changed")
    ref = a.inference_dir.resolve()
    if (
        hashlib.sha256((ref / "robot_io.py").read_bytes()).hexdigest()
        != plan["robot_io_sha256"]
    ):
        raise ValueError("I/O changed")
    mapping = json.loads(a.mapping.read_text())
    if set(mapping) != {"left", "right"}:
        raise ValueError("physical left and right mapping required")
    if mapping["left"]["interface"] == mapping["right"]["interface"]:
        raise ValueError("duplicate CAN interface")
    for side, m in mapping.items():
        if (
            Path("/sys/class/net", m["interface"], "device").resolve().name
            != m["usb_path"]
        ):
            raise ValueError("CAN USB mapping")
    sys.path.insert(0, str(ref))
    import yaml
    from robot_io import PiperDualArm

    cfg = yaml.safe_load(a.config.read_text())
    # The external inference configuration must retain commissioning setup.
    # Verify its actual connected interface names against the explicit mapping below.
    arm = cfg["arm"].copy()
    arm["auto_enable"] = False
    hf = dict(arm["high_follow"])
    hf.update(
        control_hz=200,
        max_queue_size=cap,
        max_joint_vel=[plan["max_joint_vel_rad_s"] * TO_COMMAND] * 6,
    )
    hf["interpolator"] = {
        "type": "waypoint_cubic",
        "tangent_mode": "centripetal",
        "tangent_alpha": 0.5,
        "monotone_projection": True,
        "monotone_projection_dims": "arm",
        "duration_scale": 1.0,
        "min_duration_s": 0.0,
        "max_duration_s": 0.0,
    }
    arm["high_follow"] = hf

    class Observer:
        def __init__(self, arms):
            self.arms = arms
            self.ik = URDFIK(a.urdf, "left_base_link", "left_tcp")

        def state(self):
            q = fresh_state(self.arms).copy()
            q[ARM] *= (np.pi / 180) / 0.017444
            return q

        def status(self):
            q = self.state()
            return {"q14": q.tolist(), "tcp_xyz": self.ik.fk(q[:6])[:3, 3].tolist()}

    # All geometry validation precedes SDK connection.
    ik = URDFIK(a.urdf, "left_base_link", "left_tcp")
    other = URDFIK(a.urdf, "right_base_link", "right_tcp")
    for row in np.vstack([initial, points]):
        if np.any(row[:6] < ik.lower) or np.any(row[:6] > ik.upper):
            raise ValueError("joint limits")
        check_geometry(ik, row[:6], other, row[7:13], "left", plan["tcp_floor_m"])
    native = points.copy()
    native[:, ARM] *= TO_COMMAND

    class Recorder:
        def __init__(self):
            self.rows = []
            self.index = -1
            self.last_tick = time.monotonic()

        def log_high_follow_command(self, row):
            self.rows.append(row)
            self.index = int(row["chunk_step_index"])
            self.last_tick = time.monotonic()

    recorder = Recorder()
    feedback = []
    arms = None
    connected = False
    exit_code = 0
    with open(a.log, "x") as out:

        def log(event, **kw):
            row = dict(event=event, time=time.time(), **kw)
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(json.dumps(row), flush=True)

        def stop(*_):
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            if cfg.get("can", {}).get("activate", False):
                raise ValueError(
                    "CAN activation must be disabled; interfaces must be commissioned first"
                )
            arms = PiperDualArm.from_config(arm, cfg["can"])
            if (
                arms.left.can_name != mapping["left"]["interface"]
                or arms.right.can_name != mapping["right"]["interface"]
            ):
                raise ValueError("config and physical mapping disagree")
            for x in [arms.left, arms.right]:
                x._piper.ConnectPort(piper_init=False, start_thread=True)
            connected = True
            time.sleep(0.5)
            if not arms.left.is_enabled() or not arms.right.is_enabled():
                raise RuntimeError("not enabled")
            servo = Observer(arms)
            current = servo.state()
            if (
                np.max(abs(current[ARM] - initial[ARM])) > 0.015
                or abs(current[6] - initial[6]) > 0.005
            ):
                raise RuntimeError("initial state changed")
            # Current measurement only initializes the hold; it is never used to chase drift.
            seed = current.copy()
            seed[ARM] *= TO_COMMAND
            arms._high_follow_last_ref = seed
            arms.runtime_logger = recorder
            for x in [arms.left, arms.right]:
                x.enter_high_follow_mode()
            submitted = 0

            def fill():
                nonlocal submitted
                with arms._high_follow_lock:
                    space = cap - len(arms._high_follow_queue)
                    count = min(space, len(native) - submitted)
                    for idx in range(submitted, submitted + count):
                        arms._high_follow_queue.append(native[idx].copy())
                        arms._high_follow_metadata_queue.append(
                            {"chunk_id": 0, "chunk_step_index": idx}
                        )
                    submitted += count

            fill()
            recorder.last_tick = time.monotonic()
            arms.start_high_follow_control()
            started = time.monotonic()
            deadline = started + plan["estimated_duration_s"] * 1.6 + 8
            last_watch = started
            event_idx = 0
            carry = False
            grasp_width = None
            settled = 0
            phase = "starting"
            last_progress = started
            log(
                "stream_started",
                sha256=a.sha256,
                targets=len(points),
                expected_s=plan["estimated_duration_s"],
                camera_calls=0,
                vlm_calls=0,
                **servo.status(),
            )
            while True:
                now = time.monotonic()
                if now - last_watch > 0.25:
                    raise RuntimeError("supervisor stalled")
                last_watch = now
                if not arms._high_follow_thread.is_alive():
                    raise RuntimeError("writer exited")
                if now > deadline:
                    raise RuntimeError("stream deadline exceeded")
                done = recorder.index >= len(points) - 1
                if not done and now - recorder.last_tick > 0.15:
                    raise RuntimeError("writer stalled or queue underrun")
                q = servo.state()
                if np.max(abs(q[7:13] - current[7:13])) > 0.03:
                    raise RuntimeError("inactive arm drift")
                if np.any(q[:6] < servo.ik.lower - 0.001) or np.any(
                    q[:6] > servo.ik.upper + 0.001
                ):
                    raise RuntimeError("measured joint limit")
                tcp = servo.ik.fk(q[:6])[:3, 3]
                if tcp[2] < plan["tcp_floor_m"]:
                    raise RuntimeError("measured TCP below floor")
                with arms._high_follow_lock:
                    command = arms._high_follow_last_ref.copy()
                    remaining = len(arms._high_follow_queue)
                command[ARM] /= TO_COMMAND
                tracking = float(np.max(abs(q[:6] - command[:6])))
                if tracking > 0.10:
                    raise RuntimeError("dynamic tracking error")
                feedback.append(
                    {
                        "time": time.time(),
                        "monotonic": now,
                        "index": recorder.index,
                        "q14": q.tolist(),
                        "tcp_xyz": tcp.tolist(),
                        "tracking_rad": tracking,
                        "queue_size": remaining,
                    }
                )
                while (
                    event_idx < len(plan["events"])
                    and recorder.index >= plan["events"][event_idx]["index"]
                ):
                    e = plan["events"][event_idx]
                    event_idx += 1
                    if e["kind"] == "phase":
                        phase = e["phase"]
                        log("phase", phase=phase, index=recorder.index)
                        if phase == "release":
                            carry = False
                    else:
                        lo, hi = e["width_range"]
                        if not lo <= q[6] <= hi:
                            raise RuntimeError("gripper check failed: " + e["phase"])
                        if e["phase"] == "close_gripper":
                            carry = True
                            grasp_width = q[6]
                        log(
                            "gripper_checked",
                            phase=e["phase"],
                            width_m=float(q[6]),
                            index=recorder.index,
                        )
                if carry and not (
                    0.012 <= q[6] <= 0.060 and abs(q[6] - grasp_width) < 0.01
                ):
                    raise RuntimeError("grasp width changed")
                if done and remaining == 0:
                    settled = (
                        settled + 1
                        if np.max(abs(q[ARM] - points[-1, ARM])) < 0.04
                        else 0
                    )
                    if settled >= 10:
                        break
                elif remaining < cap // 2:
                    fill()
                if now - last_progress > 10:
                    log(
                        "progress",
                        index=recorder.index,
                        total=len(points),
                        phase=phase,
                        tracking_rad=tracking,
                    )
                    last_progress = now
                time.sleep(0.02)
            log(
                "stream_complete",
                elapsed_s=time.monotonic() - started,
                **servo.status(),
            )
        except KeyboardInterrupt:
            exit_code = 130
            log("operator_stop")
        except Exception as e:
            exit_code = 1
            log("stream_failed", reason=str(e), error=type(e).__name__)
        finally:
            if arms is not None:
                try:
                    if connected:
                        log(
                            "frozen_measured_hold", state=freeze_measured(arms).tolist()
                        )
                finally:
                    arms.close()
            # Save bulk telemetry only after holding: never perform disk/Web work at 200 Hz.
            for suffix, rows in [("commands", recorder.rows), ("feedback", feedback)]:
                with Path(a.log + "." + suffix + ".jsonl").open("x") as f:
                    for row in rows:
                        f.write(json.dumps(row) + "\n")

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
