"""Bounded coarse-plan comparisons using the offline compiler, not a simulator."""

import copy
import math
from pathlib import Path

import numpy as np

from ..compiler import compile_program
from ..validation import validate_stream
from .artifacts import digest, seal, source_ref

SCHEMA = "roborsi-comparison-v1"


def check_revision(baseline, candidate, max_joint_delta):
    if not math.isfinite(max_joint_delta) or not 0 < max_joint_delta <= 0.25:
        raise ValueError("joint edit budget must be in (0, 0.25] rad")
    # Only joint waypoint values can change; context, stage order and all guards
    # are fixed. Timing profiles are explicit arguments to the evaluator.
    left, right = copy.deepcopy(baseline), copy.deepcopy(candidate)
    if len(left["program"]) != len(right["program"]):
        raise ValueError("stage count changed")
    changes = []
    for i, (a, b) in enumerate(zip(left["program"], right["program"])):
        if a["command"]["op"] == b["command"]["op"] == "trajectory":
            x = np.asarray(a["command"].pop("joint_waypoints"), float)
            y = np.asarray(b["command"].pop("joint_waypoints"), float)
            if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 6 or len(x) < 2:
                raise ValueError("waypoint layout changed or invalid")
            if not np.isfinite(x).all() or not np.isfinite(y).all():
                raise ValueError("finite waypoints required")
            delta = float(np.max(np.abs(x - y)))
            if delta > max_joint_delta:
                raise ValueError("joint edit budget exceeded")
            if delta:
                changes.append(
                    {
                        "stage_index": i,
                        "phase": a["phase"],
                        "max_joint_delta_rad": delta,
                        "changed_values": int(np.count_nonzero(x != y)),
                    }
                )
    if digest(left) != digest(right):
        raise ValueError("context, stage metadata, gripper events or guards changed")
    return changes


def _compile(program, speed, urdf, tcp_floor):
    offline = copy.deepcopy(program)
    offline["execution_intent"] = "historical_replay_only"
    stream = compile_program(offline, speed=speed, urdf=urdf, tcp_floor=tcp_floor)
    points, _ = validate_stream(stream)
    return {
        "speed_profile": speed,
        "target_count": len(points),
        "duration_s": stream["estimated_duration_s"],
        "max_velocity_rad_s": stream["max_sample_velocity_rad_s"],
        "max_acceleration_rad_s2": stream["max_sample_acceleration_rad_s2"],
        "geometry_verified": stream["geometry_verified"],
        "terminal_q14": points[-1].tolist(),
        "stream_sha256": digest(stream),
    }


def evaluate(
    baseline,
    candidate,
    *,
    baseline_speed=1,
    candidate_speed=1,
    urdf=None,
    tcp_floor=0.004,
    max_joint_delta=0.12,
):
    """Return a report even for rejected candidates; never emit an executable stream."""
    root = Path(__file__).resolve().parents[1]
    report = {
        "schema": SCHEMA,
        "execution_authorized": False,
        "baseline_program_sha256": digest(baseline),
        "candidate_program_sha256": digest(candidate),
        "policy": {
            "baseline_speed": baseline_speed,
            "candidate_speed": candidate_speed,
            "tcp_floor_m": tcp_floor,
            "max_joint_delta_rad": max_joint_delta,
            "urdf": source_ref(urdf) if urdf else None,
        },
        "implementation": [
            source_ref(root / name)
            for name in (
                "compiler.py",
                "smoothing.py",
                "validation.py",
                "geometry.py",
                "ik.py",
                "rsi/evaluation.py",
            )
        ],
        "status": "rejected",
        "baseline": None,
        "candidate": None,
        "changes": [],
        "errors": [],
        "duration_delta_s": None,
        "geometry_status": "not_checked",
        "physical_success": "not_evaluated",
        "validation_scope": "numerical_recompilation",
    }
    try:
        if isinstance(baseline_speed, bool) or isinstance(candidate_speed, bool):
            raise ValueError("numeric speed profiles required")
        report["changes"] = check_revision(baseline, candidate, max_joint_delta)
        report["baseline"] = _compile(baseline, baseline_speed, urdf, tcp_floor)
        report["candidate"] = _compile(candidate, candidate_speed, urdf, tcp_floor)
        if not np.allclose(
            report["baseline"]["terminal_q14"],
            report["candidate"]["terminal_q14"],
            atol=1e-7,
            rtol=0,
        ):
            raise ValueError("terminal return state changed")
        report["status"] = "offline_validated"
        report["geometry_status"] = "passed" if urdf else "not_checked"
        report["validation_scope"] = (
            "numerical_and_rig_geometry" if urdf else "numerical_recompilation"
        )
        report["duration_delta_s"] = (
            report["candidate"]["duration_s"] - report["baseline"]["duration_s"]
        )
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    return seal(report)


def sweep(program, *, urdf=None, tcp_floor=0.004):
    """Enumerate the two supported profiles; rank only numerically valid reports."""
    reports = [
        evaluate(
            program, program, candidate_speed=speed, urdf=urdf, tcp_floor=tcp_floor
        )
        for speed in (1, 2)
    ]
    valid = [r for r in reports if r["status"] == "offline_validated"]
    best = min(valid, key=lambda r: r["candidate"]["duration_s"]) if valid else None
    return seal(
        {
            "schema": "roborsi-sweep-v1",
            "execution_authorized": False,
            "objective": "minimum predicted duration among existing timing profiles",
            "candidates": reports,
            "selected_comparison_sha256": best["artifact_sha256"] if best else None,
            "selection_scope": "offline_timing_only",
            "physical_success": "not_evaluated",
        }
    )
