"""Candidate-independent effects at execution time, in task-tolerance units.

This experimental representation is derived from the simulator's Gaussian belief
and ballistic motion assumptions. It is NOT a general robot invariance theorem.
"""

import numpy as np

from .network import DecisionNet
from .world import ACTUATOR_STD, GRASP_TIME, LOOK_CAPTURE, PROBE_CAPTURE

EFFECT_FEATURES = (
    "left_probability", "separation_per_tolerance", "prior_std_per_tolerance",
    "execution_drift_per_tolerance", "capture_drift_per_tolerance",
    "sensor_std_per_tolerance", "actuator_std_per_tolerance",
    "contact_kick_per_tolerance", "dropout", "fragility",
    "conditional_std_per_tolerance", "residual_mode_separation_per_tolerance",
    "mode_separation_per_measurement_std",
)


def effect_features(contexts, *, physical=True):
    """[context, candidate, feature]; no menu softmax or candidate identity."""
    rows = []
    for c in contexts:
        actions = []
        for action in range(3):
            delay = (0, c.look_delay, c.probe_delay)[action]
            capture = (0, LOOK_CAPTURE, PROBE_CAPTURE)[action]
            sensor = (0, c.look_std, c.probe_std)[action]
            kick = c.probe_kick_std if action == 2 else 0
            drop = 1.0 if action == 0 else c.look_dropout if action == 1 else 0
            fragility = c.fragility if action == 2 else 0
            duration = GRASP_TIME+delay
            if physical:
                var_t = c.position_std**2+(c.velocity_std*duration)**2+ACTUATOR_STD**2
                var_y = c.position_std**2+(c.velocity_std*capture)**2+sensor**2
                cov = c.position_std**2+c.velocity_std**2*capture*duration
                residual_var = var_t-cov**2/var_y if action else var_t
                residual_sep = (1-cov/var_y)*c.separation if action else c.separation
                actions.append([c.left_probability, c.separation/c.tolerance,
                    c.position_std/c.tolerance, c.velocity_std*duration/c.tolerance,
                    c.velocity_std*capture/c.tolerance, sensor/c.tolerance,
                    ACTUATOR_STD/c.tolerance, kick/c.tolerance, drop, fragility,
                    np.sqrt(max(residual_var+kick**2, 1e-12))/c.tolerance,
                    residual_sep/c.tolerance, c.separation/np.sqrt(var_y)])
            else:
                actions.append([c.left_probability, c.separation, c.position_std,
                    c.tolerance, c.velocity_std, duration, capture, sensor,
                    ACTUATOR_STD, kick, drop, fragility, float(action != 0)])
        rows.append(actions)
    return np.asarray(rows)


class EffectNet:
    """One shared scalar outcome head scores every candidate separately."""

    def __init__(self, hidden=64, seed=0, *, physical=True):
        self.physical = physical
        self.network = DecisionNet(13, hidden, seed=seed)
        rng = np.random.default_rng(seed+123)
        self.network.params["w3"] = rng.normal(0, np.sqrt(1/hidden), (hidden, 1))
        self.network.params["b3"] = np.zeros(1)

    def predict(self, contexts):
        x = effect_features(contexts, physical=self.physical)
        return self.network.forward(x.reshape(-1, x.shape[-1])).reshape(len(contexts), 3)

    def save(self, path):
        self.network.save(path)

    @classmethod
    def load(cls, path, *, physical=True):
        value = cls(physical=physical)
        value.network = DecisionNet.load(path)
        return value
