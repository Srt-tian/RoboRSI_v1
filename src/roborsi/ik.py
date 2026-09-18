"""URDF FK and bounded local IK. Pure computation: no SDK or hardware writes.

All transforms are base_T_tip; distances in metres, joint angles in radians.
Joint vectors follow ``joint_names`` (chain order, never XML document order).
"""

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def vector(value, size):
    a = np.asarray(value, dtype=float)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise ValueError(f"expected finite vector of shape ({size},)")
    return a.copy()


def transform(value):
    t = np.asarray(value, dtype=float)
    if t.shape != (4, 4) or not np.isfinite(t).all():
        raise ValueError("expected finite 4x4 transform")
    r = t[:3, :3]
    if (
        not np.allclose(t[3], [0, 0, 0, 1], atol=1e-8)
        or not np.allclose(r.T @ r, np.eye(3), atol=1e-7)
        or not np.isclose(np.linalg.det(r), 1, atol=1e-7)
    ):
        raise ValueError(
            "transform must contain a proper rotation and homogeneous last row"
        )
    return t.copy()


@dataclass
class IKResult:
    success: bool
    q: np.ndarray | None
    position_error_m: float
    orientation_error_rad: float
    evaluations: int
    message: str


class URDFIK:
    def __init__(
        self, urdf: str | Path, base_link: str, tip_link: str, tcp_transform=None
    ):
        root = ET.parse(urdf).getroot()
        links = {x.attrib["name"] for x in root.findall("link")}
        if base_link not in links or tip_link not in links:
            raise ValueError("base_link or tip_link missing from URDF")
        parents = {}
        for j in root.findall("joint"):
            child = j.find("child").attrib["link"]
            if child in parents:
                raise ValueError(f"multiple parents for {child}")
            parents[child] = j
        chain, seen, current = [], set(), tip_link
        while current != base_link:
            if current in seen or current not in parents:
                raise ValueError("tip must be a descendant of base in an acyclic chain")
            seen.add(current)
            j = parents[current]
            chain.append(j)
            current = j.find("parent").attrib["link"]
        self.chain, names, lower, upper = [], [], [], []
        for j in reversed(chain):
            kind = j.attrib["type"]
            if kind not in ("fixed", "revolute", "continuous", "prismatic"):
                raise ValueError(f"unsupported joint type: {kind}")
            if j.find("mimic") is not None:
                raise ValueError("mimic joints on the selected chain are unsupported")
            origin = j.find("origin")
            attrs = {} if origin is None else origin.attrib
            xyz = vector(np.fromstring(attrs.get("xyz", "0 0 0"), sep=" "), 3)
            rpy = vector(np.fromstring(attrs.get("rpy", "0 0 0"), sep=" "), 3)
            t = np.eye(4)
            t[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()
            t[:3, 3] = xyz
            axis_node = j.find("axis")
            axis = vector(
                np.fromstring(
                    "1 0 0" if axis_node is None else axis_node.attrib["xyz"], sep=" "
                ),
                3,
            )
            if np.linalg.norm(axis) < 1e-12:
                raise ValueError("zero joint axis")
            axis /= np.linalg.norm(axis)
            if kind != "fixed":
                names.append(j.attrib["name"])
                if kind == "continuous":
                    lo, hi = -np.inf, np.inf
                else:
                    limit = j.find("limit")
                    if limit is None:
                        raise ValueError("moving joint missing limit")
                    lo, hi = float(limit.attrib["lower"]), float(limit.attrib["upper"])
                    if not np.isfinite([lo, hi]).all() or lo >= hi:
                        raise ValueError("invalid joint limits")
                lower.append(lo)
                upper.append(hi)
            self.chain.append((kind, t, axis))
        self.joint_names = tuple(names)
        self.lower, self.upper = np.array(lower), np.array(upper)
        self.dof = len(names)
        if self.dof == 0:
            raise ValueError("selected chain has no movable joints")
        self.tcp = np.eye(4) if tcp_transform is None else transform(tcp_transform)

    def _fk(self, q):
        t, frames, index = np.eye(4), [], 0
        for kind, origin, axis in self.chain:
            t = t @ origin
            if kind == "fixed":
                continue
            # Axis is expressed in the joint frame AFTER its origin rotation.
            frames.append((kind, t[:3, 3].copy(), t[:3, :3] @ axis))
            motion = np.eye(4)
            if kind == "prismatic":
                motion[:3, 3] = axis * q[index]
            else:
                motion[:3, :3] = Rotation.from_rotvec(axis * q[index]).as_matrix()
            t = t @ motion
            index += 1
        return t @ self.tcp, frames

    def fk(self, q):
        return self._fk(vector(q, self.dof))[0]

    def jacobian(self, q):
        """Base-frame geometric Jacobian [linear; angular] at the TCP."""
        t, frames = self._fk(vector(q, self.dof))
        jac = np.zeros((6, self.dof))
        for i, (kind, p, axis) in enumerate(frames):
            if kind == "prismatic":
                jac[:3, i] = axis
            else:
                jac[:3, i] = np.cross(axis, t[:3, 3] - p)
                jac[3:, i] = axis
        return jac

    def solve(
        self,
        target,
        seed,
        *,
        position_only=False,
        max_joint_delta=0.35,
        position_tolerance=1e-4,
        orientation_tolerance=1e-3,
        max_evaluations=150,
        seed_regularization=0.0,
    ):
        """Bounded trust-region least squares with SO(3) log error.

        Local seed box prevents branch jumps. No random restarts or relaxed
        orientation fallback. Failure returns q=None, including unreachable goals.
        max_joint_delta is radians (metres for a prismatic chain joint).
        """
        target, seed = transform(target), vector(seed, self.dof)
        if np.any(seed < self.lower) or np.any(seed > self.upper):
            raise ValueError("seed outside URDF limits")
        if (
            not np.isfinite(
                [max_joint_delta, position_tolerance, orientation_tolerance]
            ).all()
            or min(max_joint_delta, position_tolerance, orientation_tolerance) <= 0
            or max_evaluations < 1
            or not np.isfinite(seed_regularization)
            or seed_regularization < 0
        ):
            raise ValueError("solver bounds, tolerances and budget must be positive")

        def errors(q):
            actual = self.fk(q)
            return (
                actual[:3, 3] - target[:3, 3],
                Rotation.from_matrix(target[:3, :3] @ actual[:3, :3].T).as_rotvec(),
            )

        def residual(q):
            p, r = errors(q)
            error = (
                p / position_tolerance
                if position_only
                else np.r_[p / position_tolerance, r / orientation_tolerance]
            )
            if seed_regularization:
                error = np.r_[error, seed_regularization * (q - seed) / max_joint_delta]
            return error

        opt = least_squares(
            residual,
            seed,
            jac="3-point",
            method="trf",
            bounds=(
                np.maximum(self.lower, seed - max_joint_delta),
                np.minimum(self.upper, seed + max_joint_delta),
            ),
            max_nfev=max_evaluations,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        p, r = errors(opt.x)
        pe, re = float(np.linalg.norm(p)), float(np.linalg.norm(r))
        success = bool(
            pe <= position_tolerance and (position_only or re <= orientation_tolerance)
        )
        return IKResult(
            success,
            opt.x.copy() if success else None,
            pe,
            re,
            opt.nfev,
            "reached" if success else "target not reached within local bounds/budget",
        )

    def solve_delta(
        self,
        seed,
        translation=(0, 0, 0),
        rotation_vector=(0, 0, 0),
        *,
        frame="base",
        **kwargs,
    ):
        """Rotate about current TCP, translate in base or current TCP axes."""
        target = self.fk(seed)
        dp, dr = (
            vector(translation, 3),
            Rotation.from_rotvec(vector(rotation_vector, 3)).as_matrix(),
        )
        if frame == "base":
            target[:3, 3] += dp
            target[:3, :3] = dr @ target[:3, :3]
        elif frame == "tool":
            target[:3, 3] += target[:3, :3] @ dp
            target[:3, :3] = target[:3, :3] @ dr
        else:
            raise ValueError("frame must be base or tool")
        return self.solve(target, seed, **kwargs)

    def solve_position(
        self,
        position,
        seed,
        *,
        reference_pose,
        orientation_slack_rad=np.deg2rad(5),
        seed_regularization=1.0,
        **kwargs,
    ):
        """Position-priority IK with bounded deviation from a FIXED reference.

        Capture reference_pose once (e.g. FK at initialization) and reuse it for
        repeated steps. Replacing it with every new achieved pose would allow
        cumulative orientation drift. Both position and angular acceptance tests
        must pass; joint limits and the local seed box remain enforced. A seed
        displacement cost discourages large wrist swings to save tiny rotations.
        """
        if (
            not np.isfinite(orientation_slack_rad)
            or not 0 < orientation_slack_rad <= np.pi
        ):
            raise ValueError("orientation slack must be in (0, pi] radians")
        if "position_only" in kwargs or "orientation_tolerance" in kwargs:
            raise ValueError("solve_position controls its own orientation constraint")
        target = transform(reference_pose)
        target[:3, 3] = vector(position, 3)
        return self.solve(
            target,
            seed,
            orientation_tolerance=float(orientation_slack_rad),
            seed_regularization=seed_regularization,
            **kwargs,
        )

    def plan_linear(
        self,
        seed,
        target,
        *,
        translation_step=0.002,
        rotation_step=0.02,
        max_waypoints=2000,
        **kwargs,
    ):
        """Return complete joint waypoints including seed, or raise; never partial.

        These are geometric samples, NOT a time-parameterized/collision-checked
        trajectory. The executor must enforce velocity/acceleration constraints.
        """
        target, seed = transform(target), vector(seed, self.dof)
        if (
            not np.isfinite([translation_step, rotation_step]).all()
            or min(translation_step, rotation_step) <= 0
            or max_waypoints < 2
        ):
            raise ValueError("invalid path resolution/budget")
        start = self.fk(seed)
        dp = target[:3, 3] - start[:3, 3]
        rv = Rotation.from_matrix(target[:3, :3] @ start[:3, :3].T).as_rotvec()
        n = max(
            1,
            int(np.ceil(np.linalg.norm(dp) / translation_step)),
            int(np.ceil(np.linalg.norm(rv) / rotation_step)),
        )
        if n + 1 > max_waypoints:
            raise ValueError("path exceeds waypoint budget")
        path = [seed.copy()]
        for i in range(1, n + 1):
            t = start.copy()
            t[:3, 3] += dp * (i / n)
            t[:3, :3] = Rotation.from_rotvec(rv * (i / n)).as_matrix() @ start[:3, :3]
            result = self.solve(t, path[-1], **kwargs)
            if not result.success:
                raise RuntimeError(
                    f"path rejected at waypoint {i}/{n}: {result.message}"
                )
            path.append(result.q)
        return np.asarray(path)
