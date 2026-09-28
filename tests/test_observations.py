import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from roborsi.observations import observation_age, piper_measurement, select_joints
from roborsi.robotwin_feedback import RobotwinFeedback


class Joint:
    def __init__(self, name, target):
        self.name, self.target = name, target

    def get_name(self):
        return self.name

    def get_drive_target(self):
        return [self.target]


class ObservationTests(unittest.TestCase):
    def test_commands_cannot_substitute_for_measured_gripper(self):
        # Closure was commanded, but contact has stopped the physical finger.
        finger, arm = Joint("finger", -0.01), Joint("arm", 1.0)
        entity = SimpleNamespace(get_active_joints=lambda: [finger, arm],
                                 get_qpos=lambda: [0.025, 0.8], get_qvel=lambda: [0.0, 0.1])
        robot = SimpleNamespace()
        for side in ("left", "right"):
            for name, value in {"entity": entity, "arm_joints_name": ["arm"],
                                "arm_joints": [arm], "gripper": [(finger, 1, 0)],
                                "gripper_val": 0.0}.items():
                setattr(robot, side + "_" + name, value)
        with tempfile.TemporaryDirectory() as directory:
            urdf = Path(directory) / "robot.urdf"
            urdf.write_text('<robot><joint name="arm" type="revolute"/>'
                            '<joint name="finger" type="prismatic"/></robot>')
            reader = RobotwinFeedback(robot, {side: urdf for side in ("left", "right")})
            measured, commands = reader.measured(), reader.commands()
        for side in ("left", "right"):
            self.assertEqual(measured["arms"][side]["arm"]["position"], [0.8])
            grip = measured["arms"][side]["gripper"]
            self.assertEqual(grip["joints"]["position"], [0.025])
            self.assertEqual(grip["joints"]["position_units"], ["m"])
            self.assertIsNone(grip["opening_width_m"])
            self.assertEqual(commands[side]["gripper_joint_position"], [-0.01])

    def test_no_multidof_or_nonfinite_index_guessing(self):
        for names, pos, vel in [(["a", "a"], [0, 1], [0, 0]),
                                (["a"], [0, 1], [0]), (["a"], [float("nan")], [0])]:
            with self.assertRaises(ValueError):
                select_joints(names, pos, vel, ["a"], {"a": "rad"})

    def test_late_image_cannot_be_made_fresh_by_arrival(self):
        values = dict(image_time_s=1.0, feedback_time_s=1.0, available_time_s=2.0,
                      decision_time_s=2.01, observation_clock="monotonic",
                      decision_clock="monotonic", max_age_s=0.2, max_skew_s=0.05)
        with self.assertRaisesRegex(ValueError, "Stale"):
            observation_age(**values)
        values.update(image_time_s=1.98, feedback_time_s=1.99)
        self.assertAlmostEqual(observation_age(**values)["age_s"], 0.03)
        for update in ({"decision_clock": "simulation"}, {"available_time_s": 3},
                       {"feedback_time_s": 1.7}):
            with self.assertRaises(ValueError):
                observation_age(**(values | update))

    def test_historical_piper_width_is_not_a_joint_coordinate(self):
        names = {side: [f"{side}_joint{i}" for i in range(1, 7)] for side in ("left", "right")}
        data = piper_measurement([0.1] * 6 + [0.033] + [0.2] * 6 + [0.07], names)
        self.assertEqual(data["arms"]["left"]["gripper"]["opening_width_m"], 0.033)
        self.assertIsNone(data["arms"]["right"]["gripper"]["joints"])
        self.assertEqual(data["arms"]["right"]["arm"]["position"], [0.2] * 6)


if __name__ == "__main__":
    unittest.main()
