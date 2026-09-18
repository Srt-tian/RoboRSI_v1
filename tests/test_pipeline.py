import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import numpy as np
from roborsi.smoothing import retime
from roborsi.compiler import compile_program
from roborsi.hold import freeze_measured


class PipelineTests(unittest.TestCase):
    def program(self):
        q = np.zeros(14)
        q[6] = 0.07
        p = np.tile(q[:6], (4, 1))
        p[:, 0] = [0, 0.03, 0.10, 0.12]
        return {
            "initial_state": {"q14": q.tolist()},
            "execution_intent": "historical_replay_only",
            "program": [
                {
                    "phase": "approach",
                    "command": {"op": "trajectory", "joint_waypoints": p.tolist()},
                },
                {
                    "phase": "close_gripper",
                    "command": {"op": "gripper", "width_m": 0},
                    "check_width_m": [0.012, 0.060],
                },
            ],
        }

    def test_time_scaling_and_endpoint(self):
        p = self.program()
        one = compile_program(p, speed=1)
        two = compile_program(p, speed=2)
        self.assertAlmostEqual(
            (one["estimated_duration_s"] - 0.8) / 2,
            two["estimated_duration_s"] - 0.8,
            delta=0.01,
        )
        np.testing.assert_allclose(one["targets"][-1], two["targets"][-1])
        self.assertEqual(two["control_hz"], 200)
        self.assertLessEqual(two["max_sample_acceleration_rad_s2"], 4.02)

    def test_no_gripper_smoothing_or_right_arm_motion(self):
        p = compile_program(self.program())
        q = np.array(p["targets"])
        self.assertEqual(set(q[:, 6]), {0.0, 0.07})
        self.assertTrue(np.all(q[:, 7:] == 0))
        self.assertEqual(p["events"][-1]["kind"], "gripper_check")

    def test_rejects_bad_inputs_and_path_discontinuity(self):
        for v in [0, -1, float("nan")]:
            with self.assertRaises(ValueError):
                retime(np.zeros(14), np.zeros((2, 14)), velocity=v)
        p = self.program()
        p["program"][0]["command"]["joint_waypoints"][0][0] = 1
        with self.assertRaises(ValueError):
            compile_program(p)

    def test_no_overshoot(self):
        seed = np.zeros(14)
        points = np.tile(seed, (4, 1))
        points[:, 0] = [0.05, 0.2, 0.08, 0.1]
        out, info = retime(seed, points)
        self.assertTrue(np.all((out[:, 0] >= 0) & (out[:, 0] <= 0.2)))
        self.assertLessEqual(info["max_acceleration"], 1.0)

    def test_historical_hardware_execution_is_rejected_before_import(self):
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stream.json"
            path.write_text(json.dumps(compile_program(self.program())))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "roborsi.runtime",
                    "--stream",
                    str(path),
                    "--sha256",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    "--log",
                    str(Path(tmp) / "log.jsonl"),
                    "--execute",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fresh scene and seed", result.stderr)
            self.assertFalse((Path(tmp) / "log.jsonl").exists())

    def test_measured_hold_stops_writer_before_single_measurement(self):
        from unittest.mock import patch
        from collections import deque
        import threading

        class Arm:
            def __init__(self):
                self.writes = []

            def apply_high_follow(self, *args):
                self.writes.append(args)

        class Arms:
            _high_follow_thread = None
            _high_follow_running = True
            _high_follow_lock = threading.Lock()
            gripper_effort = 1

            def __init__(self):
                self.left = Arm()
                self.right = Arm()
                self._high_follow_queue = deque([1])
                self._high_follow_metadata_queue = deque([1])

            def _reset_high_follow_segment_locked(self, reset_anchor):
                pass

        arms = Arms()
        q = np.arange(14, dtype=float)
        with patch("roborsi.hold.fresh_state", return_value=q) as read:
            freeze_measured(arms)
            read.assert_called_once()
        self.assertFalse(arms._high_follow_running)
        self.assertFalse(arms._high_follow_queue)
        self.assertEqual(len(arms.left.writes), 1)
        self.assertEqual(len(arms.right.writes), 1)
        np.testing.assert_array_equal(arms._high_follow_last_ref, q)


if __name__ == "__main__":
    unittest.main()
