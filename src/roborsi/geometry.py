"""Commissioned dual-Piper geometry checks, not a general collision engine."""

import numpy as np


def segment_distance(a, b, c, d):
    # Convex segment distance: interior stationary point plus four boundaries.
    u, v, w = b - a, d - c, a - c
    aa, bb, cc = u @ u, u @ v, v @ v
    dd, ee = u @ w, v @ w
    pairs = []
    for s in (0.0, 1.0):
        pairs.append((s, np.clip((ee + s * bb) / max(cc, 1e-15), 0, 1)))
    for t in (0.0, 1.0):
        pairs.append((np.clip((t * bb - dd) / max(aa, 1e-15), 0, 1), t))
    det = aa * cc - bb * bb
    if det > 1e-15:
        s, t = (bb * ee - cc * dd) / det, (aa * ee - bb * dd) / det
        if 0 <= s <= 1 and 0 <= t <= 1:
            pairs.append((s, t))
    return min(float(np.linalg.norm(w + s * u - t * v)) for s, t in pairs)


def check_geometry(ik, q, other_ik, other_q, side, tcp_floor=0.04):
    pose, frames = ik._fk(q)
    other_pose, other_frames = other_ik._fk(other_q)
    # Both URDF chains use each arm's local base. Nominal rig mount separation.
    mount = np.array([0.01794, 0.30266 if side == "left" else -0.30266, 0.006])
    other_mount = np.array([0.01794, -mount[1], 0.006])
    points = [f[1] + mount for f in frames] + [pose[:3, 3] + mount]
    other = [f[1] + other_mount for f in other_frames] + [
        other_pose[:3, 3] + other_mount
    ]
    tcp = pose[:3, 3]
    if tcp[2] < 0.01 and pose[2, 2] > -np.cos(np.deg2rad(8)):
        raise ValueError("near-table TCP requires downward tool within 8 degrees")
    if not (
        0.05 <= tcp[0] <= 0.60
        and -0.45 <= tcp[1] <= 0.45
        and tcp_floor <= tcp[2] <= 0.55
    ):
        raise ValueError("TCP outside conservative commissioning box")
    if min(p[2] for p in points[3:-1]) < 0.035:
        raise ValueError("distal link too close to nominal mounting plane")
    for i in range(len(points) - 1):
        for j in range(len(other) - 1):
            if (
                segment_distance(points[i], points[i + 1], other[j], other[j + 1])
                < 0.10
            ):
                raise ValueError("nominal inter-arm capsule clearance below 10cm")
    # Conservative non-adjacent arm-centerline clearance. Not a mesh collision model.
    for i in range(len(points) - 1):
        for j in range(i + 3, len(points) - 1):
            if (
                segment_distance(points[i], points[i + 1], points[j], points[j + 1])
                < 0.055
            ):
                raise ValueError("non-adjacent centerlines below 5.5cm")
