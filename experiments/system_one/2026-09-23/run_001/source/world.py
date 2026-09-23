"""A partially observed grasp micro-simulator with costly evidence acquisition.

The latent object has a bimodal position and a constant random lateral velocity.
All macros use the same Bayesian estimator and candidate grasp optimizer. Units
are meters and seconds. This is a stochastic analytical model, not rigid-body
simulation, camera perception, or a robot controller.
"""

from dataclasses import asdict, dataclass

import numpy as np
from scipy.special import ndtr

ACTIONS = ("grasp_now", "look_then_grasp", "probe_then_grasp")
GRASP_TIME = 0.22
LOOK_CAPTURE = 0.04
PROBE_CAPTURE = 0.10
ACTUATOR_STD = 0.001


@dataclass(frozen=True)
class Context:
    left_probability: float
    separation: float
    position_std: float
    tolerance: float
    velocity_std: float
    look_std: float
    look_delay: float
    look_dropout: float
    probe_std: float
    probe_delay: float
    probe_kick_std: float
    fragility: float
    time_price: float

    def to_dict(self):
        return asdict(self)


FEATURES = tuple(f for f in Context.__dataclass_fields__ if f != "time_price") + (
    "prior_std_over_tolerance", "look_drift_over_tolerance",
    "probe_drift_over_tolerance", "look_noise_over_tolerance",
    "probe_noise_over_tolerance", "kick_over_tolerance",
)


def generate_contexts(count, seed, *, shift="iid"):
    rng = np.random.default_rng(seed)
    contexts = []
    for _ in range(count):
        context = Context(
            left_probability=float(rng.uniform(0.08, 0.92)),
            separation=float(rng.uniform(0.004, 0.052)),
            position_std=float(rng.uniform(0.001, 0.012)),
            tolerance=float(rng.uniform(0.004, 0.020)),
            velocity_std=float(rng.uniform(0.001, 0.048)),
            look_std=float(rng.uniform(0.0008, 0.007)),
            look_delay=float(rng.uniform(0.06, 0.55) if shift != "delay" else rng.uniform(0.55, 1.0)),
            look_dropout=float(rng.uniform(0, 0.40)),
            probe_std=float(rng.uniform(0.0006, 0.003)),
            probe_delay=float(rng.uniform(0.11, 0.30)),
            probe_kick_std=float(rng.uniform(0.0003, 0.008)),
            fragility=float(rng.uniform(0, 0.30)),
            time_price=float(rng.uniform(0.03, 0.45) if shift != "cost" else rng.uniform(0.60, 1.40)),
        )
        contexts.append(context)
    return contexts


def features(contexts):
    """Only pre-action belief/sensor specifications; never latent outcomes."""
    rows = []
    for c in contexts:
        prior_std = np.sqrt(c.position_std**2 + c.left_probability * (1-c.left_probability) * c.separation**2)
        rows.append([getattr(c, name) for name in FEATURES[:12]] + [
            prior_std/c.tolerance, c.velocity_std*(c.look_delay+GRASP_TIME)/c.tolerance,
            c.velocity_std*(c.probe_delay+GRASP_TIME)/c.tolerance,
            c.look_std/c.tolerance, c.probe_std/c.tolerance,
            c.probe_kick_std/c.tolerance,
        ])
    return np.asarray(rows, dtype=np.float64)


def times(contexts):
    return np.asarray([[GRASP_TIME, GRASP_TIME+c.look_delay, GRASP_TIME+c.probe_delay] for c in contexts])


def costs(success_probability, contexts):
    """Failure costs 1; known time prices are composed at decision time."""
    return 1-np.asarray(success_probability) + times(contexts)*np.asarray([c.time_price for c in contexts])[:, None]


def _target(means, variance, left_p, tolerance):
    """Choose one of 17 common grasp centers by posterior capture probability.

    This is a finite shared macro, not an exact continuous optimal controller.
    Arrays have shape [context, stochastic draw, mixture component].
    """
    fractions = np.linspace(0, 1, 17)
    candidates = means[..., 0, None]*(1-fractions) + means[..., 1, None]*fractions
    sigma = np.sqrt(np.maximum(variance, 1e-12))[..., None]
    tol = tolerance[:, None, None]
    prob_left = ndtr((candidates+tol-means[..., 0, None])/sigma) - ndtr((candidates-tol-means[..., 0, None])/sigma)
    prob_right = ndtr((candidates+tol-means[..., 1, None])/sigma) - ndtr((candidates-tol-means[..., 1, None])/sigma)
    probability = left_p[..., None]*prob_left+(1-left_p[..., None])*prob_right
    index = np.argmax(probability, axis=-1)
    return np.take_along_axis(candidates, index[..., None], axis=-1)[..., 0]


def simulate(contexts, draws, seed, *, details=False):
    """Paired potential outcomes with an explicit shared-noise structural model.

    A policy sees only Context. Hidden x, velocity, sensor and actuator noise
    below are branch/evaluation data. No selected policy sees them before action.
    Fresh calls with independent seeds are required for planning vs evaluation.
    """
    rng = np.random.default_rng(seed)
    n = len(contexts)
    column = lambda name: np.asarray([getattr(c, name) for c in contexts])[:, None]
    p = column("left_probability")
    half = column("separation")/2
    sig2 = column("position_std")**2
    vel2 = column("velocity_std")**2
    mode = np.where(rng.random((n, draws)) < p, -half, half)
    x0 = mode + np.sqrt(sig2)*rng.normal(size=(n, draws))
    velocity = np.sqrt(vel2)*rng.normal(size=(n, draws))
    actuator = ACTUATOR_STD*rng.normal(size=(n, draws))
    look_noise = rng.normal(size=(n, draws))
    touch_noise = rng.normal(size=(n, draws))
    kick = column("probe_kick_std")*rng.normal(size=(n, draws))
    dropped = rng.random((n, draws)) < column("look_dropout")
    damaged = rng.random((n, draws)) < column("fragility")
    tol = np.asarray([c.tolerance for c in contexts])
    success, target, actual, measurements = [], [], [], []
    durations = times(contexts)
    prior_means = np.stack((-half[:, 0], half[:, 0]), axis=-1)[:, None, :]
    for action in range(3):
        duration = durations[:, action, None]
        var_t = sig2+vel2*duration**2 + ACTUATOR_STD**2
        unobserved_target = _target(prior_means, var_t, p, tol)
        if action == 0:
            chosen_target = np.broadcast_to(unobserved_target, (n, draws))
            position = x0+velocity*duration
            measurement = np.full((n, draws), np.nan)
        else:
            capture = LOOK_CAPTURE if action == 1 else PROBE_CAPTURE
            sensor_std = column("look_std" if action == 1 else "probe_std")
            noise = look_noise if action == 1 else touch_noise
            measurement = x0+velocity*capture+sensor_std*noise
            measurement_var = sig2+vel2*capture**2+sensor_std**2
            cross_cov = sig2+vel2*capture*duration
            means = prior_means + (cross_cov/measurement_var)[..., None]*(measurement[..., None]-prior_means)
            variance = var_t-cross_cov**2/measurement_var
            log_odds = np.log(p/(1-p)) - ((measurement+half)**2-(measurement-half)**2)/(2*measurement_var)
            weights = 1/(1+np.exp(-np.clip(log_odds, -50, 50)))
            if action == 2:
                variance = variance+column("probe_kick_std")**2
            chosen_target = _target(means, variance, weights, tol)
            if action == 1:
                chosen_target = np.where(dropped, unobserved_target, chosen_target)
            position = x0+velocity*duration+(kick if action == 2 else 0)
        hit = np.abs(chosen_target+actuator-position) <= tol[:, None]
        if action == 2:
            hit = hit & ~damaged
        success.append(hit)
        target.append(chosen_target)
        actual.append(position)
        measurements.append(measurement)
    outcomes = np.stack(success, axis=-1)
    baseline = outcomes[..., 0]
    rescue = ((~baseline[..., None]) & outcomes[..., 1:]).mean(axis=1)
    spoil = (baseline[..., None] & ~outcomes[..., 1:]).mean(axis=1)
    result = {
        "success": outcomes.mean(axis=1),
        "paired": np.column_stack((outcomes[..., 0].mean(axis=1), rescue[:, 0], spoil[:, 0], rescue[:, 1], spoil[:, 1])),
        "outcomes": outcomes,
    }
    if details:
        result.update(x0=x0, velocity=velocity, kick=kick, damaged=damaged, dropped=dropped,
                      target=np.stack(target, axis=-1), actual=np.stack(actual, axis=-1),
                      measurement=np.stack(measurements, axis=-1), actuator=actuator)
    return result


def unpaired_labels(outcomes):
    """Independence coupling: same marginals, different rescue/spoil joint law."""
    p = outcomes.mean(axis=1)
    return np.column_stack((p[:, 0], (1-p[:, 0])*p[:, 1], p[:, 0]*(1-p[:, 1]),
                            (1-p[:, 0])*p[:, 2], p[:, 0]*(1-p[:, 2])))
