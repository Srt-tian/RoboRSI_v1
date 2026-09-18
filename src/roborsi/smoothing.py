"""Pure C1 trajectory interpolation, analytic time scaling, fixed 200 Hz sampling."""

import math
import numpy as np

ARM = np.array([0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12])
CONTROL_HZ = 200


def retime(seed, targets, velocity=0.25, acceleration=1.0):
    """C1 monotone interpolation with zero endpoint velocity, sampled at 200 Hz.
    Global time dilation bounds the exact polynomial velocity/acceleration extrema.
    """
    if (
        not np.isfinite([velocity, acceleration]).all()
        or min(velocity, acceleration) <= 0
    ):
        raise ValueError("positive finite limits required")
    from scipy.interpolate import PchipInterpolator

    seed = np.asarray(seed, float)
    targets = np.asarray(targets, float)
    if (
        seed.shape != (14,)
        or targets.ndim != 2
        or targets.shape[1] != 14
        or not np.isfinite(seed).all()
        or not np.isfinite(targets).all()
    ):
        raise ValueError("finite q14 seed and Nx14 targets required")
    if np.any(targets[:, [6, 13]] != seed[[6, 13]]):
        raise ValueError("gripper transitions must be explicit events, not smoothed")
    p = np.vstack([seed, targets])
    keep = np.r_[True, np.max(np.abs(np.diff(p, axis=0)), axis=1) > 1e-10]
    p = p[keep]
    if len(p) < 2:
        return np.array([seed]), {
            "duration_s": 0.005,
            "max_velocity": 0,
            "max_acceleration": 0,
        }
    dt = np.maximum(np.max(np.abs(np.diff(p[:, ARM], axis=0)), axis=1) / velocity, 0.03)
    t = np.r_[0, np.cumsum(dt)]
    tx = np.r_[-dt[0], t, t[-1] + dt[-1]]
    px = np.vstack([p[0], p, p[-1]])

    def extrema(poly, knots):
        vmax = amax = 0.0
        for i, h in enumerate(np.diff(knots)):
            c = poly.c[:, i, ARM]
            a, b, c1 = c[0], c[1], c[2]
            acc0 = 2 * b
            acc1 = 6 * a * h + 2 * b
            amax = max(amax, float(np.max(np.abs(np.r_[acc0, acc1]))))
            safe = np.where(np.abs(a) > 1e-15, a, 1)
            z = np.clip(-b / (3 * safe), 0, h)
            vals = np.r_[
                c1, 3 * a * h * h + 2 * b * h + c1, 3 * a * z * z + 2 * b * z + c1
            ]
            vmax = max(vmax, float(np.max(np.abs(vals))))
        return vmax, amax

    poly = PchipInterpolator(tx, px, axis=0)
    v, a = extrema(poly, tx)
    scale = max(1.0, v / velocity, math.sqrt(a / acceleration)) * 1.02
    tx *= scale
    t *= scale
    poly = PchipInterpolator(tx, px, axis=0)
    duration = math.ceil(t[-1] * 200) / 200  # stretch to an exact control tick
    factor = duration / t[-1]
    tx *= factor
    t *= factor
    poly = PchipInterpolator(tx, px, axis=0)
    sample = poly(np.arange(1, round(duration * 200) + 1) / 200)
    v, a = extrema(poly, tx)
    if v > velocity + 1e-9 or a > acceleration + 1e-9:
        raise ValueError("retiming limits")
    sample[-1] = p[-1]
    return sample, {
        "duration_s": duration,
        "max_velocity": v,
        "max_acceleration": a,
        "continuous_velocity": True,
        "endpoint_velocity_zero": True,
    }
