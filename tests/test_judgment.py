"""Failure-focused checks for typed decisions, context changes and held-out scoring."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_rsi import program

from roborsi.rsi.artifacts import digest, seal
from roborsi.rsi.calibration import calibrate
from roborsi.rsi.contracts import checkpoint
from roborsi.rsi.evaluation import evaluate, sweep
from roborsi.rsi.evidence import analyze
from roborsi.rsi.judgment import judge, prepare
from roborsi.rsi.memory import review, select_context
from roborsi.rsi.providers import (
    DemoProvider,
    DisabledProvider,
    ReplayProvider,
    TypeSafeProvider,
    _NoRedirect,
)
from roborsi.rsi.report import render


def reply(request, route="review_candidate", sufficient=0.95):
    answers = {}
    for key, selected in (
        ("route", route),
        ("candidate", next(iter(request["comparisons"]))),
    ):
        options = request["questions"][key]["criteria"]
        answers[key] = {
            "type": "choice",
            "choice": selected,
            "confidence": 0.2,
            "probabilities": {
                x: 0.94 if x == selected else 0.06 / (len(options) - 1) for x in options
            },
        }
    answers["evidence_sufficient"] = {"type": "noul", "noul": sufficient}
    return {
        "request_sha256": request["artifact_sha256"],
        "response": {"model": "test-fixture", "answers": answers},
    }


class JudgmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        metrics = cls.root / "metrics.json"
        metrics.write_text(
            json.dumps(
                [
                    {
                        "log": "trial",
                        "execution_status": "failed",
                        "elapsed_s": 2.0,
                        "command_rows": 400,
                        "feedback_rows": 100,
                        "failure": "gripper check failed: close_gripper",
                        "task_result": "secret outcome",
                    }
                ]
            )
        )
        cls.evidence = analyze(metrics)
        cls.scope = {"robot": "fixture", "setup": "fixture-v1", "task": "pick-place"}
        cls.p = program()
        cls.comparison = evaluate(cls.p, cls.p)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def request(self, **kwargs):
        return prepare(
            self.evidence,
            [self.comparison],
            trial_id="trial",
            scope=self.scope,
            numerical_only=True,
            now=100,
            **kwargs,
        )

    def judge(self, request, response=None, **kwargs):
        return judge(
            request,
            ReplayProvider(reply(request) if response is None else response),
            clock=lambda: 100,
            **kwargs,
        )

    def contract(self):
        return {
            "schema": "roborsi-phase-contract-v1",
            "execution_authorized": False,
            "scope": self.scope,
            "program_sha256": digest(self.p),
            "phase": "close_gripper",
            "max_observation_age_s": 1.0,
            "expected": {"grip_width_m": [0.012, 0.06]},
            "hard_limits": {"tracking_rad": [0, 0.15]},
        }

    def observation(self):
        return {
            "program_sha256": digest(self.p),
            "phase": "close_gripper",
            "revision": 3,
            "observed_at_s": 100,
            "metrics": {"grip_width_m": 0.001, "tracking_rad": 0.01},
        }

    def test_default_geometry_gate_never_calls_provider(self):
        request = prepare(
            self.evidence,
            [self.comparison],
            trial_id="trial",
            scope=self.scope,
            now=100,
        )
        provider = MagicMock(name="provider")
        provider.name = "test-fixture"
        result = judge(request, provider, clock=lambda: 100)
        self.assertEqual(result["reason"], "no_admissible_candidates")
        provider.predict.assert_not_called()

    def test_invalid_candidates_cannot_be_rescued(self):
        p = copy.deepcopy(self.p)
        p["program"][1]["check_width_m"] = [0, 0.1]
        bad = evaluate(self.p, p)
        request = prepare(
            self.evidence,
            [bad],
            trial_id="trial",
            scope=self.scope,
            now=100,
            numerical_only=True,
        )
        self.assertEqual(request["excluded"][0]["reason"], "comparison_rejected")
        self.assertEqual(
            judge(request, DemoProvider(), clock=lambda: 100)["provider_calls"], 0
        )

    def test_disabled_and_demo_are_explicit(self):
        r = self.request()
        self.assertEqual(
            judge(r, DisabledProvider(), clock=lambda: 100)["provider_calls"], 0
        )
        demo = judge(r, DemoProvider(), clock=lambda: 100)
        self.assertEqual(demo["decision"], "collect_evidence")
        self.assertIn("not-a-model", demo["model"])

    def test_distribution_probability_is_not_vendor_confidence(self):
        result = self.judge(self.request())
        self.assertEqual(result["decision"], "review_candidate")
        self.assertEqual(result["answers"]["route"]["confidence"], 0.2)
        self.assertFalse(result["execution_authorized"])

    def test_malformed_responses_fail_closed(self):
        request = self.request()
        mutations = [
            lambda r: r["response"]["answers"]["route"]["probabilities"].update(
                unknown=0.0
            ),
            lambda r: r["response"]["answers"].pop("candidate"),
            lambda r: r["response"]["answers"]["route"].update(choice="abstain"),
            lambda r: r["response"]["answers"]["route"].update(confidence=float("nan")),
            lambda r: r["response"]["answers"]["route"]["probabilities"].update(
                abstain=True
            ),
            lambda r: r["response"]["answers"]["route"]["probabilities"].update(
                abstain=-0.1
            ),
            lambda r: r["response"]["answers"]["evidence_sufficient"].update(noul=1.5),
            lambda r: r["response"].update(model=""),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                response = reply(request)
                mutate(response)
                result = self.judge(request, response)
                self.assertEqual(result["reason"], "provider_error_or_invalid_response")
                self.assertIsNone(result["selected_comparison_sha256"])
        self.assertEqual(self.judge(request, ["bad"])["decision"], "abstain")

    def test_stale_future_mismatched_and_late_replies(self):
        request = self.request()
        for now in (99, 701):
            result = judge(request, DemoProvider(), clock=lambda now=now: now)
            self.assertEqual(result["reason"], "stale_request")
            self.assertEqual(result["provider_calls"], 0)
        response = reply(request)
        response["request_sha256"] = "other"
        self.assertEqual(self.judge(request, response)["reason"], "request_mismatch")
        timer = iter([0, 6])
        self.assertEqual(
            self.judge(request, timer=lambda: next(timer))["reason"], "late_response"
        )

    def test_provider_failure_does_not_leak_details(self):
        provider = MagicMock()
        provider.name = "failing_fixture"
        provider.predict.side_effect = RuntimeError("SECRET_PROVIDER_BODY")
        result = judge(self.request(), provider, clock=lambda: 100)
        self.assertEqual(result["decision"], "abstain")
        self.assertNotIn("SECRET_PROVIDER_BODY", json.dumps(result))
        self.assertEqual(provider.predict.call_count, 1)

    def test_probability_margin_and_evidence_gates(self):
        request = self.request(min_probability=0.5, min_margin=0.15)
        response = reply(request)
        response["response"]["answers"]["route"]["probabilities"] = {
            "review_candidate": 0.5,
            "collect_evidence": 0.49,
            "ask_planner": 0.01,
            "abstain": 0,
        }
        self.assertEqual(self.judge(request, response)["reason"], "uncertain_route")
        self.assertEqual(
            self.judge(request, reply(request, sufficient=0.2))["reason"],
            "insufficient_evidence",
        )
        self.assertEqual(
            self.judge(request, reply(request, route="ask_planner"))["decision"],
            "ask_planner",
        )

    def test_comparison_families_cannot_be_mixed(self):
        mixed = evaluate(self.p, self.p, tcp_floor=0)
        with self.assertRaisesRegex(ValueError, "share baseline"):
            prepare(
                self.evidence,
                [self.comparison, mixed],
                trial_id="trial",
                scope=self.scope,
            )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prepare(
                self.evidence,
                [self.comparison, self.comparison],
                trial_id="trial",
                scope=self.scope,
            )

    def test_terminal_outcome_not_exposed_as_decision_input(self):
        self.assertNotIn("secret outcome", json.dumps(self.request()["state"]))

    def test_checkpoint_routes_have_distinct_meanings(self):
        c, o = self.contract(), self.observation()
        self.assertEqual(checkpoint(c, o, now=100)["route"], "request_judgment")
        o["metrics"]["grip_width_m"] = 0.03
        self.assertEqual(checkpoint(c, o, now=100)["route"], "continue")
        del o["metrics"]["grip_width_m"]
        self.assertEqual(checkpoint(c, o, now=100)["route"], "collect_evidence")
        o["metrics"]["tracking_rad"] = 0.2
        self.assertEqual(checkpoint(c, o, now=100)["route"], "stop_review")
        self.assertEqual(checkpoint(c, o, now=102)["route"], "collect_evidence")
        o["phase"] = "lift"
        self.assertEqual(checkpoint(c, o, now=100)["route"], "discard_context")

    def test_checkpoint_invalid_values_and_ranges(self):
        c, o = self.contract(), self.observation()
        for value in (float("nan"), True):
            o["metrics"]["tracking_rad"] = value
            with self.assertRaises(ValueError):
                checkpoint(c, o, now=100)
        c["hard_limits"]["grip_width_m"] = [0, 0.001]
        with self.assertRaisesRegex(ValueError, "inside"):
            checkpoint(c, self.observation(), now=100)

    def test_context_is_rechecked_after_inference(self):
        c, o = self.contract(), self.observation()
        event = checkpoint(c, o, now=100)
        request = self.request(checkpoint_event=event)
        self.assertEqual(self.judge(request)["reason"], "checkpoint_context_invalid")
        self.assertEqual(
            self.judge(request, context_probe=lambda: event)["decision"],
            "review_candidate",
        )
        o["revision"] += 1
        changed = checkpoint(c, o, now=100)
        events = iter([event, changed])
        self.assertEqual(
            self.judge(request, context_probe=lambda: next(events))["reason"],
            "checkpoint_context_changed",
        )

    def test_expired_context_and_different_plan_rejected(self):
        event = checkpoint(self.contract(), self.observation(), now=100)
        request = self.request(checkpoint_event=event)
        result = judge(
            request, DemoProvider(), clock=lambda: 102, context_probe=lambda: event
        )
        self.assertEqual(result["provider_calls"], 0)
        event["program_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "baseline"):
            self.request(checkpoint_event=seal(event))

    def test_judgment_is_bound_to_review_and_memory(self):
        result = self.judge(self.request())
        kwargs = dict(
            trial_id="trial",
            scope=self.scope,
            lesson="Check contact.",
            reviewer="fixture",
            decision="accept_for_planning",
            judgment=result,
        )
        reviewed = review(self.evidence, self.comparison, **kwargs)
        context = select_context([reviewed], self.scope)
        self.assertEqual(
            context["selected"][0]["judgment_sha256"], result["artifact_sha256"]
        )
        with self.assertRaisesRegex(ValueError, "select this"):
            review(self.evidence, evaluate(self.p, self.p, candidate_speed=2), **kwargs)

    def test_http_contract_without_network(self):
        request = self.request()
        with self.assertRaisesRegex(ValueError, "allow-network"):
            TypeSafeProvider()
        with (
            patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}),
            patch("urllib.request.build_opener") as build,
        ):
            http = build.return_value.open.return_value.__enter__.return_value
            http.read.return_value = json.dumps(reply(request)["response"]).encode()
            provider = TypeSafeProvider(allow_network=True)
            result = judge(request, provider, clock=lambda: 100)
            self.assertEqual(result["decision"], "review_candidate")
            call = build.return_value.open.call_args
            self.assertEqual(
                call.args[0].full_url, "https://api.typesafe.ai/v1/systemone"
            )
            self.assertEqual(call.args[0].get_method(), "POST")
            self.assertEqual(
                set(json.loads(call.args[0].data)), {"model", "state", "questions"}
            )
            self.assertEqual(build.return_value.open.call_count, 1)
            self.assertNotIn("test-only", json.dumps(result))
        with self.assertRaisesRegex(ValueError, "redirect"):
            _NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://other.invalid"
            )

    def test_report_checks_binding_and_escapes_html(self):
        result = self.judge(self.request())
        result["model"] = "</script><script>alert(1)</script>"
        html = render(self.evidence, sweep(self.p), seal(result))
        self.assertNotIn(result["model"], html)
        self.assertIn("judgment-panel", html)
        result["evidence_sha256"] = "other"
        with self.assertRaises(ValueError):
            render(self.evidence, sweep(self.p), seal(result))

    def test_cli_demo_pipeline_has_no_network_calls(self):
        request = self.request()
        # Use a fresh timestamp because the CLI applies the real clock.
        import time

        request["created_at_s"] = time.time()
        src, dst = self.root / "request.json", self.root / "judgment.json"
        src.write_text(json.dumps(seal(request)))
        with patch(
            "urllib.request.build_opener",
            side_effect=AssertionError("network forbidden"),
        ):
            from roborsi.rsi.cli import main

            with patch.object(
                sys,
                "argv",
                [
                    "rsi",
                    "judge",
                    "--request",
                    str(src),
                    "--provider",
                    "demo",
                    "--output",
                    str(dst),
                ],
            ):
                main()
        self.assertEqual(json.loads(dst.read_text())["decision"], "collect_evidence")
        help_result = subprocess.run(
            [sys.executable, "-m", "roborsi.rsi", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("calibrate", help_result.stdout)


def dataset():
    return {
        "schema": "roborsi-decision-dataset-v1",
        "source_kind": "synthetic",
        "model": "fixture",
        "question_family": "route",
        "label_provenance": "Synthetic unit-test labels; no robot observations.",
        "records": [
            {
                "case_id": split,
                "group_id": split,
                "split": split,
                "probabilities": {"repair": 1.0, "inspect": 0.0},
                "label": "repair",
            }
            for split in ("validation", "test")
        ],
    }


class CalibrationTests(unittest.TestCase):
    def test_perfect_scores(self):
        result = calibrate(dataset(), min_accepted=1)
        self.assertEqual(result["selected_threshold"], 0.5)
        for metric in ("brier", "nll_clipped_1e_15", "ece_10_bins", "selective_error"):
            self.assertEqual(result["test"][metric], 0)
        self.assertEqual(result["test"]["coverage"], 1)

    def test_uniform_and_abstention(self):
        d = dataset()
        for r in d["records"]:
            r["probabilities"] = {"repair": 0.5, "inspect": 0.5}
        result = calibrate(d, min_accepted=1)
        self.assertEqual(result["test"]["brier"], 0.5)
        self.assertIsNone(result["selected_threshold"])
        self.assertEqual(result["test"]["coverage"], 0)
        self.assertIsNone(result["test"]["selective_error"])

    def test_test_labels_do_not_choose_threshold(self):
        d = dataset()
        before = calibrate(d, min_accepted=1)
        d["records"][1]["label"] = "inspect"
        after = calibrate(d, min_accepted=1)
        self.assertEqual(before["selected_threshold"], after["selected_threshold"])
        self.assertEqual(after["test"]["selective_error"], 1)

    def test_episode_leakage_and_duplicate_cases_rejected(self):
        for key in ("group_id", "case_id"):
            d = dataset()
            d["records"][1][key] = d["records"][0][key]
            with self.assertRaises(ValueError):
                calibrate(d, min_accepted=1)

    def test_insufficient_data_installs_no_threshold(self):
        result = calibrate(dataset())
        self.assertIsNone(result["selected_threshold"])
        self.assertFalse(result["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
