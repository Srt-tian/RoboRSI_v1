"""Measured-only proprioception and timing checks; no hardware connections.

Command targets belong in a separate record. A gripper joint coordinate is not
an opening width, and a measured width alone is not proof of object retention.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def finite_vector(values: Sequence[float], size: int, label: str) -> list[float]:
    result = [float(value) for value in values]
    if len(result) != size or not all(math.isfinite(value) for value in result):
        raise ValueError(f"Invalid {label}: expected {size} finite coordinates")
    return result


def select_joints(active_names, qpos, qvel, selected_names, units):
    """Select named single-DOF coordinates, independently of storage order."""
    names, selected = list(active_names), list(selected_names)
    if len(set(names)) != len(names) or len(set(selected)) != len(selected):
        raise ValueError("Duplicate joint names")
    position = finite_vector(qpos, len(names), "single-DOF qpos")
    velocity = finite_vector(qvel, len(names), "single-DOF qvel")
    if not selected or any(name not in names for name in selected):
        raise ValueError("Requested joint is absent")
    joint_units = [units[name] for name in selected]
    if any(unit not in {"m", "rad"} for unit in joint_units):
        raise ValueError("Unspecified joint units")
    indices = [names.index(name) for name in selected]
    return {"joint_names": selected, "position": [position[i] for i in indices],
            "velocity": [velocity[i] for i in indices], "position_units": joint_units,
            "velocity_units": [unit + "/s" for unit in joint_units]}


def piper_measurement(q14, arm_joint_names: Mapping[str, Sequence[str]]):
    """Adapt a *measured*, already-normalized runtime q14 (rad, opening m).

    This function never reads a robot or converts SDK command units. The caller
    must use the commissioned runtime's fresh_state normalization first.
    """
    q = finite_vector(q14, 14, "Piper measured q14")
    if set(arm_joint_names) != {"left", "right"}:
        raise ValueError("Explicit physical left/right names are required")
    arms = {}
    for side, start in (("left", 0), ("right", 7)):
        names = list(arm_joint_names[side])
        if len(names) != 6 or len(set(names)) != 6 or q[start + 6] < 0:
            raise ValueError("Invalid measured Piper arm or gripper")
        arms[side] = {"arm": {"joint_names": names, "position": q[start:start + 6],
                              "position_units": ["rad"] * 6, "velocity": None,
                              "velocity_units": None},
                      "gripper": {"opening_width_m": q[start + 6], "joints": None}}
    return {"schema": "roborsi.measured-proprioception.v1", "arms": arms}


def observation_age(*, image_time_s, feedback_time_s, available_time_s,
                    decision_time_s, observation_clock, decision_clock,
                    max_age_s, max_skew_s):
    """Reject unavailable, stale, skewed or differently clocked observations.

    All stamps must be in one explicit clock domain. Arrival time is distinct
    from acquisition time; receipt cannot make an old image fresh.
    """
    times = finite_vector([image_time_s, feedback_time_s, available_time_s,
                           decision_time_s, max_age_s, max_skew_s], 6, "timing")
    image, feedback, available, decision, max_age, max_skew = times
    if not observation_clock or observation_clock != decision_clock:
        raise ValueError("Clock domains differ")
    if min(max_age, max_skew) < 0 or not max(image, feedback) <= available <= decision:
        raise ValueError("Observation was not available at decision time")
    age, skew = decision - min(image, feedback), abs(image - feedback)
    if age > max_age or skew > max_skew:
        raise ValueError("Stale or misaligned observation")
    return {"age_s": age, "sensor_skew_s": skew,
            "delivery_s": available - max(image, feedback)}
