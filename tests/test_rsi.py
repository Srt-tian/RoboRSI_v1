"""Offline gates and evidence semantics, with no robot or model dependencies."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from roborsi.rsi.artifacts import digest, load_json, seal, write_json
from roborsi.rsi.evaluation import evaluate, sweep
from roborsi.rsi.evidence import analyze
from roborsi.rsi.memory import review, select_context
from roborsi.rsi.report import render


def program():
    seed = [0.0] * 14
    seed[6] = 0.07
    return {
        "scene": "synthetic_test_scene",
        "execution_intent": "historical_replay_only",
        "initial_state": {"q14": seed},
        "program": [
            {
                "phase": "approach",
                "command": {
                    "op": "trajectory",
                    "joint_waypoints": [
                        [0.0] * 6,
                        [0.04, 0, 0, 0, 0, 0],
                        [0.08, 0, 0, 0, 0, 0],
                    ],
                },
            },
            {
                "phase": "close_gripper",
                "command": {"op": "gripper", "width_m": 0},
                "check_width_m": [0.012, 0.06],
            },
        ],
    }


class RSITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metrics = self.root / "metrics.json"
        self.rows = [
            {
                "log": "failed_grasp",
                "execution_status": "failed",
                "elapsed_s": 2.0,
                "command_rows": 400,
                "feedback_rows": 100,
                "failure": "gripper check failed: close_gripper",
            },
            {
                "log": "finished",
                "execution_status": "complete",
                "elapsed_s": 3.0,
                "command_rows": 600,
                "feedback_rows": 150,
                "failure": None,
            },
        ]
        self.scope = {
            "robot": "synthetic-piper",
            "setup": "test-v1",
            "task": "pick-place",
        }
        self.save_metrics()

    def save_metrics(self):
        self.metrics.write_text(json.dumps(self.rows))

    def reviewed(self):
        p = program()
        return review(
            analyze(self.metrics),
            evaluate(p, p),
            trial_id="failed_grasp",
            scope=self.scope,
            lesson="Inspect contact geometry before revising depth.",
            reviewer="unit-test fixture",
            decision="accept_for_planning",
        )

    def test_completion_and_nonzero_grip_do_not_label_success(self):
        self.rows[1]["closed_widths_mm"] = [40]
        self.save_metrics()
        a = analyze(self.metrics)
        self.assertEqual(a["trials"][1]["task_outcome"]["status"], "unknown")
        self.assertIsNone(a["summary"]["task_success_rate"])
        self.assertEqual(a["trials"][0]["diagnosis"]["attribution"], "unresolved")

    def test_reported_text_is_preserved_not_converted_to_success(self):
        self.rows[1]["task_result"] = "operator reports success"
        self.save_metrics()
        a = analyze(self.metrics)
        self.assertEqual(a["trials"][1]["task_outcome"]["status"], "reported")
        self.assertEqual(a["summary"]["task_reports"], 1)

    def test_fingerprints_are_deterministic_and_record_specific(self):
        a = analyze(self.metrics)
        self.assertEqual(a, analyze(self.metrics))
        self.rows[0]["elapsed_s"] = 2.5
        self.save_metrics()
        b = analyze(self.metrics)
        self.assertNotEqual(a["artifact_sha256"], b["artifact_sha256"])
        self.assertEqual(
            a["trials"][1]["record_sha256"], b["trials"][1]["record_sha256"]
        )

    def test_invalid_and_conflicting_metrics_are_rejected(self):
        variants = [
            dict(self.rows[0], elapsed_s=-1),
            dict(self.rows[0], feedback_rows=True),
            dict(self.rows[0], command_rows=2.5),
            dict(self.rows[0], execution_status="complete"),
            dict(self.rows[0], actual_command_hz=float("nan")),
        ]
        for row in variants:
            with self.subTest(row=row):
                self.metrics.write_text(json.dumps([row]))
                with self.assertRaises(ValueError):
                    analyze(self.metrics)
        self.rows.append(copy.deepcopy(self.rows[0]))
        self.save_metrics()
        with self.assertRaisesRegex(ValueError, "duplicate trial"):
            analyze(self.metrics)

    def test_duplicate_json_keys_are_rejected(self):
        self.metrics.write_text('{"scene": "a", "scene": "b"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            load_json(self.metrics)

    def test_sweep_ranks_duration_without_physical_success_claim(self):
        s = sweep(program())
        one, two = s["candidates"]
        self.assertEqual(s["selected_comparison_sha256"], two["artifact_sha256"])
        self.assertLess(two["candidate"]["duration_s"], one["candidate"]["duration_s"])
        self.assertEqual(two["geometry_status"], "not_checked")
        self.assertEqual(two["physical_success"], "not_evaluated")
        self.assertFalse(two["execution_authorized"])
        self.assertNotIn("targets", two)

    def test_bounded_interior_revision_passes(self):
        p, c = program(), program()
        c["program"][0]["command"]["joint_waypoints"][1][0] += 0.01
        r = evaluate(p, c)
        self.assertEqual(r["status"], "offline_validated")
        self.assertEqual(r["changes"][0]["changed_values"], 1)
        self.assertNotEqual(r["baseline_program_sha256"], r["candidate_program_sha256"])

    def test_guard_and_context_changes_rejected_before_compile(self):
        for field in ("scene", "intent", "seed", "guard", "gripper", "phase"):
            p, c = program(), program()
            if field == "scene":
                c["scene"] = "other"
            elif field == "intent":
                c["execution_intent"] = "live"
            elif field == "seed":
                c["initial_state"]["q14"][7] = 0.1
            elif field == "guard":
                c["program"][1]["check_width_m"] = [0, 0.071]
            elif field == "gripper":
                c["program"][1]["command"]["width_m"] = 0.04
            else:
                c["program"][0]["phase"] = "other"
            with (
                self.subTest(field=field),
                patch("roborsi.rsi.evaluation.compile_program") as compile_mock,
            ):
                r = evaluate(p, c)
                self.assertEqual(r["status"], "rejected")
                compile_mock.assert_not_called()

    def test_excessive_edit_and_changed_return_state_are_rejected(self):
        p, c = program(), program()
        c["program"][0]["command"]["joint_waypoints"][1][0] = 0.5
        self.assertIn("budget exceeded", evaluate(p, c)["errors"][0])
        c = program()
        c["program"][0]["command"]["joint_waypoints"][-1][0] += 0.01
        self.assertIn("terminal return", evaluate(p, c)["errors"][0])

    def test_discontinuous_path_is_not_validated(self):
        p, c = program(), program()
        c["program"][0]["command"]["joint_waypoints"][0][0] = 0.01
        r = evaluate(p, c)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("discontinuous", r["errors"][0])

    def test_geometry_failure_stays_rejected(self):
        urdf = self.root / "fixture.urdf"
        urdf.write_text("<robot name='fixture'/>")
        with patch(
            "roborsi.rsi.evaluation.compile_program",
            side_effect=ValueError("geometry failure"),
        ):
            r = evaluate(program(), program(), urdf=urdf)
        self.assertEqual(r["status"], "rejected")
        self.assertNotEqual(r["geometry_status"], "passed")

    def test_live_source_only_produces_offline_reports(self):
        p = program()
        p["execution_intent"] = "live"
        r = evaluate(p, p)
        self.assertEqual(r["status"], "offline_validated")
        self.assertFalse(r["execution_authorized"])
        self.assertEqual(p["execution_intent"], "live")

    def test_review_rejects_tampered_evidence_and_bad_candidate(self):
        e = analyze(self.metrics)
        e["trials"][0]["execution_status"] = "complete"
        kw = dict(
            trial_id="failed_grasp",
            scope=self.scope,
            lesson="test",
            reviewer="test",
            decision="accept_for_planning",
        )
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            review(e, evaluate(program(), program()), **kw)
        c = program()
        c["scene"] = "other"
        with self.assertRaisesRegex(ValueError, "rejected comparison"):
            review(analyze(self.metrics), evaluate(program(), c), **kw)

    def test_context_filters_scope_and_rejected_reviews_and_deduplicates(self):
        record = self.reviewed()
        c = select_context([record, record], self.scope)
        self.assertEqual(len(c["selected"]), 1)
        self.assertFalse(c["execution_authorized"])
        c = select_context([record], dict(self.scope, setup="different-calibration"))
        self.assertEqual(c["selected"], [])
        self.assertEqual(c["excluded"][0]["reason"], "scope_mismatch")
        rejected = seal(dict(record, decision="reject"))
        self.assertEqual(select_context([rejected], self.scope)["selected"], [])
        with self.assertRaises(ValueError):
            select_context([record], dict(self.scope, task="*"))

    def test_no_overwrite_and_no_script_injection(self):
        path = self.root / "artifact.json"
        write_json(path, {"a": 1})
        with self.assertRaises(FileExistsError):
            write_json(path, {"a": 2})
        self.assertEqual(load_json(path), {"a": 1})
        payload = '</script><script>alert("x")</script>'
        self.rows[0]["log"] = payload
        self.save_metrics()
        page = render(analyze(self.metrics), sweep(program()))
        self.assertNotIn(payload, page)
        self.assertIn("\\u003c/script>", page)

    def test_workbench_cli_complete_offline_path(self):
        plan = self.root / "plan.json"
        write_json(plan, program())
        out = self.root / "workbench"
        # Any socket creation or hardware-driver import makes this subprocess fail.
        code = """
import sys
def audit(event, args):
    if event == 'socket.__new__' or (event == 'import' and args[0] in {'robot_io', 'piper_sdk'}):
        raise RuntimeError('unexpected hardware/network access')
sys.addaudithook(audit)
from roborsi.rsi.cli import main
main()
"""
        cmd = [
            sys.executable,
            "-c",
            code,
            "workbench",
            "--metrics",
            str(self.metrics),
            "--program",
            str(plan),
            "--output",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((out / "index.html").is_file())
        self.assertEqual(load_json(out / "evidence.json")["summary"]["trials"], 2)
        repeated = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(repeated.returncode, 0)

    def test_historical_final_target_count_and_metrics_remain_reproducible(self):
        root = Path(__file__).resolve().parents[1]
        p = load_json(root / "examples/three_objects.json")
        r = evaluate(p, p, candidate_speed=2, tcp_floor=0)
        self.assertEqual(r["candidate"]["target_count"], 17046)
        self.assertEqual(r["candidate"]["duration_s"], 85.23)
        a = analyze(root / "experiments/2026-09-17/metrics.json")
        self.assertEqual(a["summary"]["trials"], 6)
        self.assertEqual(a["summary"]["execution_failed"], 3)
        self.assertEqual(a["summary"]["task_reports"], 1)
        self.assertIsNone(a["summary"]["task_success_rate"])
        self.assertEqual(digest(p), r["candidate_program_sha256"])

    def test_all_rejected_sweep_reports_failure_exit_code(self):
        p = program()
        p["program"][0]["command"]["joint_waypoints"][0][0] = 0.01
        plan, output = self.root / "bad.json", self.root / "sweep.json"
        write_json(plan, p)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "roborsi.rsi",
                "sweep",
                str(plan),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIsNone(load_json(output)["selected_comparison_sha256"])


if __name__ == "__main__":
    unittest.main()
