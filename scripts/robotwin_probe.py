"""Record a fixed-seed RoboTwin native-expert qualification, without hardware."""
from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import importlib
import importlib.metadata
import json
import os
import random
import subprocess
import sys
import time
import traceback
from contextlib import ExitStack
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def convert(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): convert(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [convert(v) for v in value]
    return value


def write_json(path: Path, value):
    path.write_text(json.dumps(convert(value), indent=2, allow_nan=False) + "\n")


def close_simulation(task):
    """Release native resources while Python/CUDA modules are still alive.

    RoboTwin's close_env delegates to gym.Env.close, which is a no-op in the
    pinned source. In particular, do not defer Scene.__del__ to interpreter
    shutdown, and do not retain the recording callback's scene/task cycle.
    This helper is specific to simulation and must never be used for hardware.
    """
    if task is None:
        return
    import torch

    scene = getattr(task, "scene", None)
    renderer = getattr(task, "renderer", None)
    engine = getattr(task, "engine", None)
    viewer = getattr(task, "viewer", None)
    if scene is not None and "step" in vars(scene):
        del scene.step
    if viewer is not None:
        viewer.close()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    # Keep the scene and rendering backend alive while robot/camera references,
    # planners and CUDA graphs are released. No simulation steps occur here.
    task.__dict__.clear()
    gc.collect()
    if scene is not None:
        scene.clear()
    scene = viewer = None
    gc.collect()
    renderer = engine = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--robotwin-root", type=Path, required=True)
    p.add_argument("--expected-upstream", required=True)
    p.add_argument("--task", choices=["handover_block", "lift_pot", "stack_blocks_three"], required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    upstream = args.robotwin_root.resolve()
    own = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if git(upstream, "rev-parse", "HEAD") != args.expected_upstream:
        raise ValueError("RoboTwin commit differs from the registered source")
    for repo in (upstream, own):
        if git(repo, "status", "--porcelain"):
            raise ValueError(f"Refusing an uncommitted source tree: {repo.name}")
    output.mkdir(parents=True, exist_ok=False)
    protocol = {
        "schema": "roborsi.robotwin.native-expert.v2",
        "scope": "Infrastructure qualification only; privileged scripted expert, no learned policy or JEV/RSI effect",
        "task": args.task, "seed": args.seed, "split": "development",
        "upstream": "https://github.com/RoboTwin-Platform/RoboTwin.git",
        "upstream_commit": args.expected_upstream,
        "adapter_commit": git(own, "rev-parse", "HEAD"),
        "config": "demo_clean", "embodiment": "aloha-agilex",
        "physics_hz": 250, "video_hz": 5,
        "video_semantics": "Live rendered observations every 50 physics steps after setup; planning wall time is excluded from simulation time",
        "joint_semantics": "qpos/qvel are measured full articulations; upstream joint_action.vector contains drive targets, not measured arm joints",
        "observation_semantics": "Measured arm and finger joints use named articulation coordinates and URDF units; no inferred gripper opening width. Commands remain separate. No object state enters measured observations.",
        "clock_semantics": "Camera and feedback share the recorded physics step because physics is paused during rendering; render wall duration and process monotonic timestamps are also retained. This is not an asynchronous-camera latency benchmark.",
        "selection": "Fixed task/seed chosen before execution; failures are retained, no successful-seed resampling",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cleanup": "Explicit callback removal, native-reference release and scene clear before interpreter shutdown; parent exit status must still be checked",
    }
    write_json(output / "protocol.json", protocol)
    (output / "source.py").write_bytes(Path(__file__).read_bytes())
    start = time.monotonic()
    task = writer = trace = scene_step = feedback = None
    handles = ExitStack()
    frame_rows = []
    result = {"status": "started", "task": args.task, "seed": args.seed}
    counter = {"physics_steps": 0, "frames": 0}
    try:
        os.chdir(upstream)
        sys.path.insert(0, str(upstream))
        import imageio.v2 as imageio
        import numpy as np
        import torch
        import yaml
        sys.path.insert(0, str(own / "src"))
        from roborsi.robotwin_feedback import RobotwinFeedback

        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        versions = {name: importlib.metadata.version(name) for name in
                    ("numpy", "torch", "sapien", "mplib", "toppra", "imageio")}
        write_json(output / "environment.json", versions)
        config = yaml.safe_load((upstream / "task_config/demo_clean.yml").read_text())
        embodiment = upstream / "assets/embodiments/aloha-agilex"
        robot_config = yaml.safe_load((embodiment / "config.yml").read_text())
        config.update(task_name=args.task, task_config="demo_clean", save_data=False,
                      collect_data=False, save_path=str(output / "upstream"), render_freq=0,
                      eval_mode=False, need_plan=True, dual_arm_embodied=True,
                      left_robot_file=str(embodiment), right_robot_file=str(embodiment),
                      left_embodiment_config=robot_config, right_embodiment_config=robot_config)
        # Public export omits deployment-specific absolute paths.
        export_config = {k: v for k, v in config.items() if k not in
                         {"save_path", "left_robot_file", "right_robot_file"}}
        write_json(output / "config.json", export_config)
        cls = getattr(importlib.import_module(f"envs.{args.task}"), args.task)
        task = cls()
        task.setup_demo(now_ep_num=0, seed=args.seed, **config)
        feedback = RobotwinFeedback(task.robot, {
            side: embodiment / robot_config["urdf_path"] for side in ("left", "right")})
        write_json(output / "joint_layout.json", feedback.layout)
        result["setup_wall_s"] = time.monotonic() - start
        writer = handles.enter_context(imageio.get_writer(output / "head.mp4", fps=5, codec="libx264", quality=7))
        trace = handles.enter_context(gzip.open(output / "physics.jsonl.gz", "wt"))  # noqa: SIM115 -- owned by ExitStack

        def capture():
            render_started = time.monotonic()
            obs = task.get_obs()
            render_finished = time.monotonic()
            measured = feedback.measured()
            feedback_sampled = time.monotonic()
            rgb = obs["observation"]["head_camera"]["rgb"]
            writer.append_data(rgb)
            frame_rows.append({"frame": counter["frames"], "physics_step": counter["physics_steps"],
                               "simulation_time_s": counter["physics_steps"] / 250,
                               "render_wall_s": render_finished - render_started,
                               "image_available_monotonic_s": render_finished,
                               "feedback_sampled_monotonic_s": feedback_sampled,
                               "measured": measured, "commands": feedback.commands(),
                               "command_targets": convert(obs["joint_action"]["vector"]),
                               "endpose": convert(obs["endpose"])})
            counter["frames"] += 1

        capture()
        scene_step = task.scene.step

        def recorded_step():
            scene_step()
            counter["physics_steps"] += 1
            entities = {"left": task.robot.left_entity, "right": task.robot.right_entity}
            row = {"physics_step": counter["physics_steps"],
                   "simulation_time_s": counter["physics_steps"] / 250,
                   "sampled_monotonic_s": time.monotonic(),
                   "measured": feedback.measured(), "commands": feedback.commands(),
                   "articulations": {name: {"qpos": ent.get_qpos().tolist(),
                                             "qvel": ent.get_qvel().tolist()}
                                     for name, ent in entities.items()},
                   "command_targets": convert(task.robot.get_left_arm_jointState() +
                                              task.robot.get_right_arm_jointState())}
            trace.write(json.dumps(row, allow_nan=False) + "\n")
            if counter["physics_steps"] % 50 == 0:
                capture()

        task.scene.step = recorded_step
        execution_start = time.monotonic()
        info = task.play_once()
        result.update(status="completed", plan_success=bool(task.plan_success),
                      task_success=bool(task.check_success()),
                      execution_wall_s=time.monotonic() - execution_start)
        write_json(output / "plans.json", {"left": task.left_joint_path, "right": task.right_joint_path})
        write_json(output / "task_info.json", info)
        obs = task.get_obs()
        imageio.imwrite(output / "final.png", obs["observation"]["head_camera"]["rgb"])
    except Exception as exc:  # noqa: BLE001 -- archive every failed qualification; exit nonzero below
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        (output / "error.txt").write_text(traceback.format_exc())
        traceback.print_exc()
    finally:
        handles.close()
        result.update(counter, total_wall_s=time.monotonic() - start,
                      simulation_time_s=counter["physics_steps"] / 250)
        # Archive outcomes before native cleanup, including cleanup failures.
        result["cleanup_status"] = "started"
        write_json(output / "frames.json", frame_rows)
        write_json(output / "result.json", result)
        scene_step = None  # bound native method otherwise prolongs Scene lifetime
        feedback = None  # release the reader's robot/planner references before native cleanup
        try:
            close_simulation(task)
            task = None
            result["cleanup_status"] = "completed"
        except Exception as exc:  # noqa: BLE001 -- preserve cleanup diagnostics
            result.update(cleanup_status="failed", cleanup_error=str(exc))
            (output / "cleanup_error.txt").write_text(traceback.format_exc())
        result["total_wall_s"] = time.monotonic() - start
        write_json(output / "result.json", result)
        print(json.dumps(result, allow_nan=False), flush=True)
    if result["status"] != "completed" or result["cleanup_status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
