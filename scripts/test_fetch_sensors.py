"""Validate delayed correction against a chronological batch reference."""
import unittest

import numpy as np
from fetch_sensors import REGIMES, EstimatorBank, LaggedBiasFilter, Packet, SensorTape


class SensorTest(unittest.TestCase):
    def test_delayed_filter_equals_chronological_available_messages(self):
        c = REGIMES['drift']
        tape = SensorTape(913, 'drift', 30)
        filt = LaggedBiasFilter(c, .5)
        rng = np.random.default_rng(13)
        for t in range(30):
            p = tape.sample(np.r_[[1.3, .75], .425] + rng.normal(size=3) * .01)
            filt.ingest(p)
            mean, cov = filt.initial_mean.copy(), filt.initial_cov.copy()
            for k in range(t + 1):
                if k:
                    mean = filt.transition @ mean
                    cov = filt.transition @ cov @ filt.transition.T + filt.process
                mean, cov = filt.update(mean, cov, filt.fast[k], filt.hfast, filt.rfast)
                mean, cov = filt.update(mean, cov, filt.precise[k], filt.hprecise, filt.rprecise)
            np.testing.assert_allclose(filt.means[-1], mean, rtol=0, atol=1e-12)
            np.testing.assert_allclose(filt.covs[-1], cov, rtol=0, atol=1e-12)

    def test_only_delivered_data_affects_current_estimate(self):
        c = REGIMES['occlusion']
        a, b = EstimatorBank(c), EstimatorBank(c)
        for t in range(15):
            fast = np.array([1.3 + .001 * t, .75, .425]) if t not in [6, 7] else None
            precise = np.array([1.3 + .001 * (t - 8), .75, .425]) if t >= 8 else None
            packet = Packet(t, fast, t - 8 if t >= 8 else None, precise)
            np.testing.assert_array_equal(a.ingest(packet), b.ingest(packet))
        before = a.estimates.copy()
        b.ingest(Packet(15, np.array([9., 9., 9.]), None, None))
        np.testing.assert_array_equal(a.estimates, before)

    def test_clean_sensor_is_an_identity_control(self):
        tape = SensorTape(31, 'clean', 20)
        bank = EstimatorBank(REGIMES['clean'])
        for t in range(20):
            position = np.array([1.3 + .002 * t, .75, .425])
            estimates = bank.ingest(tape.sample(position))
            np.testing.assert_allclose(estimates, np.broadcast_to(position, (4, 3)), atol=2e-8, rtol=0)


if __name__ == '__main__':
    unittest.main()
