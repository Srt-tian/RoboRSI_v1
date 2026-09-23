"""Causal timestamped sensor messages and fixed-lag bias-state estimators.

Only SensorTape reads the simulated object's true position. EstimatorBank gets
delivered messages; it has no reference to the simulator or future noise.
"""
from dataclasses import dataclass

import numpy as np

REGIMES = {
    'clean': {'bias': .0, 'jitter': .0, 'drift': .0, 'precise': .0, 'delay': 0, 'occlusion': False},
    'jitter': {'bias': .015, 'jitter': .010, 'drift': .0005, 'precise': .002, 'delay': 5, 'occlusion': False},
    'drift': {'bias': .020, 'jitter': .006, 'drift': .003, 'precise': .002, 'delay': 8, 'occlusion': False},
    'occlusion': {'bias': .020, 'jitter': .004, 'drift': .001, 'precise': .002, 'delay': 8, 'occlusion': True},
}
ESTIMATORS = ['raw_fast', 'sensor_delta', 'kalman_smooth', 'kalman_reactive']
AXIS_SCALE = np.array([1.0, 1.0, .3])


@dataclass
class Packet:
    step: int
    fast: np.ndarray | None
    precise_step: int | None
    precise: np.ndarray | None


class SensorTape:
    def __init__(self, seed, regime, horizon=50):
        self.config = REGIMES[regime].copy()
        c = self.config
        rng = np.random.default_rng(seed + 87531)
        drift = np.cumsum(rng.normal(size=(horizon, 3)) * c['drift'] * AXIS_SCALE, axis=0)
        self.fast_error = (rng.normal(size=3) * c['bias'] * AXIS_SCALE + drift
                           + rng.normal(size=(horizon, 3)) * c['jitter'] * AXIS_SCALE)
        self.precise_error = rng.normal(size=(horizon, 3)) * c['precise'] * AXIS_SCALE
        self.visible = np.ones(horizon, dtype=bool)
        if c['occlusion']:
            # Synthetic camera outage; fixed before actions and shared by branches.
            start = int(rng.integers(10, 26))
            duration = int(rng.integers(5, 13))
            self.visible[start:start + duration] = False
        self.truth = []

    def sample(self, true_position):
        step = len(self.truth)
        self.truth.append(np.asarray(true_position).copy())
        assert step < len(self.visible)
        fast = self.truth[step] + self.fast_error[step] if self.visible[step] else None
        j = step - self.config['delay']
        available = j >= 0 and self.visible[j]
        return Packet(step, fast, j if available else None,
                      self.truth[j] + self.precise_error[j] if available else None)


class LaggedBiasFilter:
    """Linear [position, velocity, sensor bias] filter with delayed updates.

    When a precise sample from j arrives at t, redo the filtering recursion from
    the stored posterior at j-1 through t. All fast samples are used exactly once
    in the reconstructed recursion. No unavailable precise sample is inserted.
    """
    def __init__(self, config, acceleration_std):
        c = config
        dt = .04
        self.transition = np.eye(9)
        self.transition[:3, 3:6] = dt * np.eye(3)
        self.process = np.zeros((9, 9))
        v = acceleration_std ** 2
        self.process[:3, :3] = .25 * dt ** 4 * v * np.eye(3)
        self.process[:3, 3:6] = self.process[3:6, :3] = .5 * dt ** 3 * v * np.eye(3)
        self.process[3:6, 3:6] = dt ** 2 * v * np.eye(3)
        self.process[6:, 6:] = np.diag((c['drift'] * AXIS_SCALE) ** 2)
        self.hfast = np.c_[np.eye(3), np.zeros((3, 3)), np.eye(3)]
        self.hprecise = np.c_[np.eye(3), np.zeros((3, 6))]
        self.rfast = np.diag(np.maximum((c['jitter'] * AXIS_SCALE) ** 2, 1e-12))
        self.rprecise = np.diag(np.maximum((c['precise'] * AXIS_SCALE) ** 2, 1e-12))
        self.initial_mean = np.r_[[1.3, .75, .425], np.zeros(6)]
        self.initial_cov = np.diag(np.r_[np.full(3, .3 ** 2), np.full(3, .5 ** 2),
                                                np.maximum((c['bias'] * AXIS_SCALE) ** 2, 1e-12)])
        self.fast, self.precise, self.means, self.covs = [], [], [], []

    @staticmethod
    def update(mean, cov, y, h, noise):
        if y is None:
            return mean, cov
        innovation = y - h @ mean
        gain = np.linalg.solve(h @ cov @ h.T + noise, h @ cov).T
        mean = mean + gain @ innovation
        residual = np.eye(9) - gain @ h
        cov = residual @ cov @ residual.T + gain @ noise @ gain.T
        return mean, (cov + cov.T) * .5

    def ingest(self, packet):
        t = packet.step
        assert t == len(self.fast)
        self.fast.append(None if packet.fast is None else packet.fast.copy())
        self.precise.append(None)
        self.means.append(None)
        self.covs.append(None)
        start = t
        if packet.precise is not None:
            start = packet.precise_step
            assert start is not None and 0 <= start <= t
            assert self.precise[start] is None
            self.precise[start] = packet.precise.copy()
        for k in range(start, t + 1):
            if k == 0:
                mean, cov = self.initial_mean.copy(), self.initial_cov.copy()
            else:
                mean = self.transition @ self.means[k - 1]
                cov = self.transition @ self.covs[k - 1] @ self.transition.T + self.process
            mean, cov = self.update(mean, cov, self.fast[k], self.hfast, self.rfast)
            mean, cov = self.update(mean, cov, self.precise[k], self.hprecise, self.rprecise)
            self.means[k], self.covs[k] = mean, cov
        return self.means[-1][:3].copy()


class EstimatorBank:
    def __init__(self, config):
        self.config = config.copy()
        self.filters = [LaggedBiasFilter(config, .5), LaggedBiasFilter(config, 4.)]
        self.fast = []
        self.last_fast, self.last_fast_step = None, None
        self.last_precise, self.last_precise_step = None, None
        self.estimates = None

    def ingest(self, packet):
        assert packet.step == len(self.fast)
        self.fast.append(None if packet.fast is None else packet.fast.copy())
        if packet.fast is not None:
            self.last_fast, self.last_fast_step = packet.fast.copy(), packet.step
        if packet.precise is not None:
            self.last_precise = packet.precise.copy()
            self.last_precise_step = packet.precise_step
        assert self.last_fast is not None, 'the first camera frame must be available'
        delta = self.last_fast.copy()
        if self.last_precise is not None:
            old_fast = self.fast[self.last_precise_step]
            # Both samples must exist; otherwise retain the timestamped precise sample.
            delta = self.last_precise.copy()
            if old_fast is not None:
                delta += self.last_fast - old_fast
        self.estimates = np.asarray([self.last_fast.copy(), delta,
                                      *[f.ingest(packet) for f in self.filters]])
        assert self.estimates.shape == (4, 3) and np.isfinite(self.estimates).all()
        return self.estimates.copy()

    def ages(self, current):
        return [(current - self.last_fast_step) * .04,
                -1.0 if self.last_precise_step is None else (current - self.last_precise_step) * .04]
