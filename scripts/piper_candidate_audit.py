"""Audit local correction candidates on fixed historical measured Piper states.

No CAN/SDK imports or writes. Historical frames are correlated, not independent
trials, and offline admission is not a live execution clearance.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roborsi.ik import URDFIK
from roborsi.observations import piper_measurement
from roborsi.piper_candidates import compile_relative_motion


CANDIDATES = {"probe_up_20mm": [0, 0, 0.020], "shift_x_plus_15mm": [0.015, 0, 0],
              "shift_x_minus_15mm": [-0.015, 0, 0], "shift_y_plus_15mm": [0, 0.015, 0],
              "shift_y_minus_15mm": [0, -0.015, 0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--tcp-floor-m", type=float, required=True)
    args = parser.parse_args()
    own = Path(__file__).resolve().parents[1]
    def git(*argv):
        return subprocess.check_output(["git", "-C", str(own), *argv], text=True).strip()
    if git("status", "--porcelain"):
        raise ValueError("Commit the evaluation source first")
    raw = args.feedback.read_bytes()
    source = [json.loads(line) for line in raw.splitlines() if line]
    if not 1 <= args.frames <= len(source):
        raise ValueError("Invalid fixed frame count")
    indices = np.linspace(0, len(source) - 1, args.frames, dtype=int).tolist()
    kin = {side: URDFIK(args.urdf, side + "_base_link", side + "_tcp")
           for side in ("left", "right")}
    names = {side: obj.joint_names for side, obj in kin.items()}
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index in indices:
        source_row = source[index]
        q = np.asarray(source_row["q14"], dtype=float)
        current = kin["left"].fk(q[:6])
        frame = {"source_index": index, "historical": True,
                 "historical_monotonic_s": source_row["monotonic"],
                 "q14": q.tolist(), "measured": piper_measurement(q, names),
                 "tcp_xyz": current[:3, 3].tolist(),
                 "recorded_fk_error_m": float(np.linalg.norm(current[:3, 3] - source_row["tcp_xyz"])),
                 "candidates": []}
        for name, offset in CANDIDATES.items():
            start = time.monotonic()
            record = {"id": name, "offset_base_m": offset}
            try:
                points, metadata = compile_relative_motion(kin, q, "left", offset,
                                                          tcp_floor_m=args.tcp_floor_m)
                assert np.array_equal(points[:, 6], np.full(len(points), q[6]))
                assert np.array_equal(points[:, 7:], np.broadcast_to(q[7:], (len(points), 7)))
                record.update(admitted=True, **metadata)
                if len(rows) == 0:
                    np.savez_compressed(args.output / (name + ".npz"), q14=points)
            except ValueError as exc:
                record.update(admitted=False, reason=str(exc), execution_authorized=False)
            record["compile_wall_s"] = time.monotonic() - start
            frame["candidates"].append(record)
        rows.append(frame)
        print(json.dumps({"frame": index, "admitted": sum(c["admitted"] for c in frame["candidates"])}), flush=True)
    candidates = [c for row in rows for c in row["candidates"]]
    admitted = [c for c in candidates if c["admitted"]]
    report = {
        "schema": "roborsi.piper-candidate-audit.v1", "commit": git("rev-parse", "HEAD"),
        "scope": "Offline admission on fixed correlated historical frames; not task success, live clearance or timing guarantee",
        "selection": "24 equally spaced historical rows by default; no selection on IK outcome",
        "urdf_sha256": hashlib.sha256(args.urdf.read_bytes()).hexdigest(),
        "feedback_sha256": hashlib.sha256(raw).hexdigest(),
        "tcp_floor_m": args.tcp_floor_m, "frame_count": len(rows),
        "candidate_count": len(candidates), "admitted_count": len(admitted),
        "rejections": dict(collections.Counter(c["reason"] for c in candidates if not c["admitted"])),
        "max_recorded_fk_error_m": max(row["recorded_fk_error_m"] for row in rows),
        "all_accepted_samples_checked": True,
        "control_hz": 200, "physical_execution": False,
        "rows": rows,
    }
    (args.output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}), flush=True)


if __name__ == "__main__":
    main()
