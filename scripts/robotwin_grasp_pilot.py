"""A deliberately small, custom grasp-recovery development pilot.

The initial grasp proposal uses the native privileged expert. Recovery uses only
a fixed relative displacement from measured end-effector pose. No judge is
trained here; labels and perturbation metadata must not become judge inputs.
"""
from __future__ import annotations

import json
import hashlib


def play_grasp_pilot(task, *, error_x_m, repair_x_m, output, capture,
                     physics_steps, prefix_digest, frozen_prefix=None):
    from envs.utils import ArmTag
    import numpy as np

    arm = ArmTag("left")
    initial = task.box.get_pose()
    initial_xyz = list(map(float, initial.p))
    if frozen_prefix is not None:
        # Replay both position AND velocity from the original coarse proposal.
        # Subsequent recovery remains planned from measured state.
        task.left_joint_path = [dict(path) for path in frozen_prefix["left"]]
        for path in task.left_joint_path:
            for key in ("position", "velocity"):
                path[key] = np.asarray(path[key], dtype=float)
                if path[key].ndim != 2 or path[key].shape[1] != 6 or not np.isfinite(path[key]).all():
                    raise ValueError("Invalid frozen prefix coordinates")
            if path["position"].shape != path["velocity"].shape or path["status"] != "Success":
                raise ValueError("Incomplete frozen prefix")
        task.left_cnt = 0
        task.need_plan = False
    actions = task.grasp_actor(task.box, arm_tag=arm, pre_grasp_dis=0.07,
                               grasp_dis=0.0, contact_point_id=[0, 1, 2, 3])
    for action in actions[1]:
        if action.action == "move":
            action.target_pose[0] += error_x_m
    task.move(actions)
    if frozen_prefix is not None:
        if task.left_cnt != len(frozen_prefix["left"]):
            raise ValueError("Frozen prefix was not consumed exactly")
        task.need_plan = True
    capture()
    pose = task.box.get_pose()
    event = {"phase": "before_recovery", "physics_step": physics_steps(),
             "prefix_digest": prefix_digest(),
             "audit_only_object_pose": list(map(float, pose.p)) + list(map(float, pose.q)),
             "policy_observation": "Latest frames.json measured/RGB record; no object pose or injected error",
             "error_x_m_audit_only": error_x_m, "fixed_repair_x_m": repair_x_m}
    if frozen_prefix is not None:
        event["frozen_prefix_sha256"] = hashlib.sha256(json.dumps(frozen_prefix, sort_keys=True).encode()).hexdigest()
        event["reference_prefix_digest"] = frozen_prefix["source_prefix_digest"]
        event["matches_reference_prefix"] = event["prefix_digest"] == event["reference_prefix_digest"]
    (output / "pilot_branch.json").write_text(json.dumps(event, indent=2) + "\n")
    if repair_x_m != 0:
        # No object pose lookup or privileged target recomputation in recovery.
        task.move(task.open_gripper(arm))
        task.move(task.move_by_displacement(arm, x=repair_x_m))
        task.move(task.close_gripper(arm))
    task.move(task.move_by_displacement(arm, z=0.1))
    for _ in range(100):  # 0.4 s retention check; included in the common budget
        task.scene.step()
    capture()
    final_xyz = list(map(float, task.box.get_pose().p))
    gain = final_xyz[2] - initial_xyz[2]
    result = {"custom_subtask": "left grasp then lift 10 cm and hold 0.4 s",
              "full_handover_evaluated": False,
              "pilot_success": bool(task.plan_success and gain > 0.06),
              "height_gain_m_audit_label": gain, "initial_object_xyz_audit_only": initial_xyz,
              "final_object_xyz_audit_only": final_xyz,
              "prefix_steps": event["physics_step"], "total_physics_steps": physics_steps(),
              "selection": "Fixed development grid, not independent test episodes"}
    (output / "pilot_result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
