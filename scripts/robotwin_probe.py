"""Record a fixed-seed RoboTwin native-expert qualification, without hardware."""
from __future__ import annotations

import argparse
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
        "schema": "roborsi.robotwin.native-expert.v1",
        "scope": "Infrastructure qualification only; privileged scripted expert, no learned policy or JEV/RSI effect",
        "task": args.task, "seed": args.seed, "split": "development",
        "upstream": "https://github.com/RoboTwin-Platform/RoboTwin.git",
        "upstream_commit": args.expected_upstream,
        "adapter_commit": git(own, "rev-parse", "HEAD"),
        "config": "demo_clean", "embodiment": "aloha-agilex",
        "physics_hz": 250, "video_hz": 5,
        "video_semantics": "Live rendered observations every 50 physics steps after setup; planning wall time is excluded from simulation time",
        "joint_semantics": "qpos/qvel are measured full articulations; upstream joint_action.vector contains drive targets, not measured arm joints",
        "selection": "Fixed task/seed chosen before execution; failures are retained, no successful-seed resampling",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    write_json(output / "protocol.json", protocol)
    (output / "source.py").write_bytes(Path(__file__).read_bytes())
    start = time.monotonic()
    task = writer = trace = None
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
        result["setup_wall_s"] = time.monotonic() - start
        writer = handles.enter_context(imageio.get_writer(output / "head.mp4", fps=5, codec="libx264", quality=7))
        trace = handles.enter_context(gzip.open(output / "physics.jsonl.gz", "wt"))  # noqa: SIM115 -- owned by ExitStack

        def capture():
            obs = task.get_obs()
            rgb = obs["observation"]["head_camera"]["rgb"]
            writer.append_data(rgb)
            frame_rows.append({"frame": counter["frames"], "physics_step": counter["physics_steps"],
                               "simulation_time_s": counter["physics_steps"] / 250,
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
        if task is not None and hasattr(task, "scene"):
            task.close_env()
        result.update(counter, total_wall_s=time.monotonic() - start,
                      simulation_time_s=counter["physics_steps"] / 250)
        write_json(output / "frames.json", frame_rows)
        write_json(output / "result.json", result)
        print(json.dumps(result, allow_nan=False), flush=True)
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
