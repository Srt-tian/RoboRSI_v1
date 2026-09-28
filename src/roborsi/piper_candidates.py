"""Compile bounded relative motions for the commissioned dual-Piper geometry.

Pure offline computation. These candidates do not authorize execution; the
runtime still requires a fresh scene, feedback, calibration and physical mapping.
"""
from __future__ import annotations

import numpy as np

from .geometry import check_geometry
from .smoothing import retime


def compile_relative_motion(ik_by_side, q14, side, offset_m, *, tcp_floor_m,
                            max_offset_m=0.03, velocity=0.3, acceleration=1.0):
    if side not in {"left", "right"} or set(ik_by_side) != {"left", "right"}:
        raise ValueError("Explicit left/right kinematics required")
    q = np.asarray(q14, dtype=float)
    offset = np.asarray(offset_m, dtype=float)
    if q.shape != (14,) or offset.shape != (3,) or not np.isfinite(q).all() or not np.isfinite(offset).all():
        raise ValueError("Finite q14 and base-frame xyz offset required")
    if not np.isfinite(max_offset_m) or not 0 < max_offset_m <= 0.03:
        raise ValueError("Candidate range exceeds the 3 cm offline envelope")
    if np.linalg.norm(offset) > max_offset_m or not np.isfinite(tcp_floor_m):
        raise ValueError("Offset or floor outside the specified envelope")
    for name, start in (("left", 0), ("right", 7)):
        kin = ik_by_side[name]
        if kin.dof != 6 or np.any(q[start:start + 6] < kin.lower) or np.any(q[start:start + 6] > kin.upper):
            raise ValueError("Seed outside the six-DOF joint envelope")
    start, other_start = (0, 7) if side == "left" else (7, 0)
    other_side = "right" if side == "left" else "left"
    ik, other_ik = ik_by_side[side], ik_by_side[other_side]
    arm, other = q[start:start + 6], q[other_start:other_start + 6]
    check_geometry(ik, arm, other_ik, other, side, tcp_floor_m)
    target = ik.fk(arm)
    target[:3, 3] += offset
    solved = ik.solve(target, arm, max_joint_delta=0.25, position_tolerance=0.001,
                      orientation_tolerance=0.03, max_evaluations=150)
    if not solved.success:
        raise ValueError("Bounded pose IK failed: " + solved.message)
    endpoint = q.copy()
    endpoint[start:start + 6] = solved.q
    points, timing = retime(q, endpoint[None, :], velocity=velocity, acceleration=acceleration)
    for point in points:
        moving = point[start:start + 6]
        if np.any(moving < ik.lower) or np.any(moving > ik.upper):
            raise ValueError("Interpolated joint limit violation")
        check_geometry(ik, moving, other_ik, other, side, tcp_floor_m)
    return points, {
        "execution_authorized": False, "requires_fresh_scene_and_seed": True,
        "geometry_scope": "Commissioned Piper centerline checks; not full mesh or scene collision checking",
        "side": side, "offset_base_m": offset.tolist(), "target_pose": target.tolist(),
        "control_hz": 200, "targets": len(points), "timing": timing,
        "position_error_m": solved.position_error_m,
        "orientation_error_rad": solved.orientation_error_rad,
        "endpoint_q14": endpoint.tolist(),
    }
