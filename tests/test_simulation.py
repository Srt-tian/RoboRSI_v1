"""Mechanism checks; proxy simulator results are not robot performance tests."""

import unittest

from roborsi.simulation import (
    METHODS,
    PROCESS_COLUMNS,
    SCENARIOS,
    benchmark,
    run_episode,
)
from roborsi.simulation_report import render_simulation


class SimulationTests(unittest.TestCase):
    def test_nominal_and_hard_protection_shared_by_every_baseline(self):
        for method in METHODS:
            with self.subTest(method=method):
                normal = run_episode(1, "nominal", method)
                self.assertTrue(normal["success"])
                self.assertEqual(normal["analytic_requests"], 0)
                fault = run_episode(1, "tracking_fault", method)
                self.assertEqual(fault["status"], "protection_stop")
                self.assertEqual(fault["simulated_duration_s"], 0.5)

    def test_version_check_prevents_stale_adoption_but_not_all_waiting(self):
        unchecked = run_episode(4, "shift_during_wait", "delayed_unchecked")
        checked = run_episode(4, "shift_during_wait", "delayed_checked")
        self.assertGreater(unchecked["stale_adopted"], 0)
        self.assertEqual(checked["stale_adopted"], 0)
        self.assertGreater(checked["stale_discarded"], 0)
        self.assertTrue(
            unchecked["success"]
        )  # Later recovery can rescue a stale grasp.
        self.assertTrue(checked["success"])
        self.assertLess(
            checked["simulated_duration_s"], unchecked["simulated_duration_s"]
        )

    def test_visibility_is_not_replaced_by_hidden_ground_truth(self):
        result = run_episode(7, "occluded_shift", "delayed_checked")
        requests = [e for e in result["events"] if e["kind"] == "request"]
        self.assertTrue(requests)
        self.assertGreaterEqual(requests[0]["t"], 1.05)
        self.assertTrue(
            any(e["kind"] == "wait_for_observation" for e in result["events"])
        )

    def test_slip_requires_observed_recovery_for_success(self):
        baseline = run_episode(2, "slip", "fixed_plan")
        reactive = run_episode(2, "slip", "instant_rules")
        self.assertFalse(baseline["success"])
        self.assertTrue(reactive["success"])
        self.assertEqual(reactive["recovery_replans"], 1)

    def test_every_control_sample_is_saved_with_a_monotonic_clock(self):
        for scenario in SCENARIOS:
            episode = run_episode(3, scenario, "delayed_checked", record_process=True)
            rows = episode["process"]
            self.assertEqual(len(rows), episode["simulated_control_ticks"])
            self.assertAlmostEqual(rows[-1][0], episode["simulated_duration_s"])
            for i, row in enumerate(rows):
                self.assertEqual(len(row), len(PROCESS_COLUMNS))
                self.assertAlmostEqual(row[0], i * 0.005)
                self.assertGreaterEqual(row[3], 0.025 - 1e-9)

    def test_seeded_runs_are_repeatable_and_include_failures(self):
        a, b = benchmark(seeds=2), benchmark(seeds=2)
        self.assertEqual(a, b)
        self.assertEqual(len(a["episodes"]), 2 * len(SCENARIOS) * len(METHODS))
        self.assertEqual(sum(e["real_model_calls"] for e in a["episodes"]), 0)
        page = render_simulation(a)
        self.assertIn('id="time"', page)
        self.assertIn('id="paper-assets" hidden', page)

    def test_zero_delay_does_not_invent_stale_events(self):
        result = run_episode(0, "shift", "delayed_checked", decision_delay_s=0)
        self.assertEqual(result["stale_discarded"], 0)
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
