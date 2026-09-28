"""Read SAPIEN feedback by joint name; imports neither SAPIEN nor hardware."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from roborsi.observations import finite_vector, select_joints


class RobotwinFeedback:
    def __init__(self, robot, urdf_paths):
        self.robot = robot
        self.layout = {}
        for side in ("left", "right"):
            entity = getattr(robot, side + "_entity")
            active = [joint.get_name() for joint in entity.get_active_joints()]
            arm = list(getattr(robot, side + "_arm_joints_name"))
            gripper = [joint.get_name() for joint, _, _ in getattr(robot, side + "_gripper")]
            root = ET.parse(urdf_paths[side]).getroot()
            types = {joint.attrib["name"]: joint.attrib["type"] for joint in root.findall("joint")}
            units = {}
            for name in arm + gripper:
                kind = types[name]
                if kind not in {"revolute", "continuous", "prismatic"}:
                    raise ValueError(f"Unsupported measured joint type: {kind}")
                units[name] = "m" if kind == "prismatic" else "rad"
            # Explicitly reject multi-DOF layouts rather than assume indices.
            select_joints(active, entity.get_qpos(), entity.get_qvel(), arm + gripper, units)
            self.layout[side] = {"active_names": active, "arm_names": arm,
                                 "gripper_names": gripper, "units": units,
                                 "gripper_opening_width": "not calibrated; use raw joint coordinates"}

    def measured(self):
        arms = {}
        for side, layout in self.layout.items():
            entity = getattr(self.robot, side + "_entity")
            active = [joint.get_name() for joint in entity.get_active_joints()]
            if active != layout["active_names"]:
                raise ValueError("Articulation layout changed during recording")
            position, velocity = entity.get_qpos(), entity.get_qvel()
            args = active, position, velocity
            arms[side] = {
                "arm": select_joints(*args, layout["arm_names"], layout["units"]),
                "gripper": {"opening_width_m": None,
                            "joints": select_joints(*args, layout["gripper_names"], layout["units"])} }
        return {"schema": "roborsi.measured-proprioception.v1", "arms": arms}

    def commands(self):
        result = {}
        for side in ("left", "right"):
            arm = getattr(self.robot, side + "_arm_joints")
            gripper = getattr(self.robot, side + "_gripper")
            result[side] = {
                "arm_position": finite_vector([joint.get_drive_target()[0] for joint in arm],
                                              len(arm), "arm drive target"),
                "gripper_joint_position": finite_vector([joint.get_drive_target()[0]
                                                         for joint, _, _ in gripper],
                                                        len(gripper), "gripper drive target"),
                "gripper_normalized_request": float(getattr(self.robot, side + "_gripper_val")),
            }
        return result
