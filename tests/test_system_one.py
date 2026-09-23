import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from roborsi.system_one.network import DecisionNet
from roborsi.system_one.study import model_input
from roborsi.system_one.world import costs, features, generate_contexts, simulate, unpaired_labels


class LearnedDecisionTests(unittest.TestCase):
    def test_gradients_for_all_training_objectives(self):
        rng = np.random.default_rng(91)
        x = rng.normal(size=(7, 3))
        outcomes = simulate(generate_contexts(7, 13), 20, 14)
        for kind in ("outcome", "paired", "choice"):
            model = DecisionNet(3, 5, kind=kind, seed=2)
            y = outcomes["paired" if kind == "paired" else "success"]
            if kind == "choice":
                y = np.eye(3)[np.argmax(y, axis=1)]
            _, gradients = model.loss_grad(x, y)
            for key, index in (("w1", (1, 2)), ("w2", (2, 3)), ("w3", (2, 1)), ("b3", (0,))):
                old = model.params[key][index]
                model.params[key][index] = old+1e-5
                plus, _ = model.loss_grad(x, y)
                model.params[key][index] = old-1e-5
                minus, _ = model.loss_grad(x, y)
                model.params[key][index] = old
                self.assertAlmostEqual(gradients[key][index], (plus-minus)/2e-5, places=6)

    def test_counterfactual_identity_and_coupling_audit(self):
        data = simulate(generate_contexts(30, 1), 400, 2)
        for joint in (data["paired"], unpaired_labels(data["outcomes"])):
            np.testing.assert_allclose(data["success"][:, 1]-data["success"][:, 0], joint[:, 1]-joint[:, 2], atol=1e-15)
            np.testing.assert_allclose(data["success"][:, 2]-data["success"][:, 0], joint[:, 3]-joint[:, 4], atol=1e-15)
        self.assertGreater(np.abs(data["paired"]-unpaired_labels(data["outcomes"])).mean(), 0.005)

    def test_features_do_not_include_outcome_or_cost(self):
        contexts = generate_contexts(8, 77)
        changed = [replace(c, time_price=10) for c in contexts]
        np.testing.assert_array_equal(features(contexts), features(changed))
        self.assertFalse(np.array_equal(costs(np.full((8, 3), .6), contexts), costs(np.full((8, 3), .6), changed)))
        no_delay = model_input(features(contexts), contexts, "no_delay64")
        later = [replace(c, look_delay=c.look_delay+2, probe_delay=c.probe_delay+2) for c in contexts]
        np.testing.assert_array_equal(no_delay, model_input(features(later), later, "no_delay64"))

    def test_frozen_model_roundtrip_and_probability_semantics(self):
        model = DecisionNet(18, 6, kind="paired", seed=44)
        x = features(generate_contexts(10, 2))
        model.fit_scaler(x)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"model.npz"
            model.save(p)
            restored = DecisionNet.load(p)
            np.testing.assert_array_equal(model.success(x), restored.success(x))
        s = model.success(x)
        self.assertTrue(np.all((s >= 0) & (s <= 1)))
        pair = model.rescue_spoil(x)
        np.testing.assert_allclose(s[:, 1]-s[:, 0], pair[:, 0]-pair[:, 1], atol=1e-15)
        with self.assertRaises(ValueError):
            DecisionNet(18, kind="choice").success(x)

    def test_simulator_branch_outputs_match_geometry(self):
        c = generate_contexts(15, 981)
        data = simulate(c, 32, 193, details=True)
        error = np.abs(data["target"]+data["actuator"][..., None]-data["actual"])
        expected = error <= np.asarray([v.tolerance for v in c])[:, None, None]
        expected[..., 2] &= ~data["damaged"]
        np.testing.assert_array_equal(expected, data["outcomes"])
        self.assertTrue(np.isfinite(data["success"]).all())


if __name__ == "__main__":
    unittest.main()
