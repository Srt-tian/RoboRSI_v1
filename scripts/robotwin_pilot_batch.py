"""Run a predeclared 3 x 3 grasp pilot sequentially on one development GPU."""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robotwin-root", type=Path, required=True)
    parser.add_argument("--expected-upstream", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    def git(*argv):
        return subprocess.check_output(["git", "-C", str(root), *argv], text=True).strip()
    if git("rev-parse", "HEAD") != args.expected_commit or git("status", "--porcelain"):
        raise ValueError("Execution tree differs from the frozen commit")
    if git("rev-parse", "@{u}") != args.expected_commit:
        raise ValueError("Execution commit must already be published")
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {"seed": 0, "error_x_m": [-0.04, 0.0, 0.04],
                "repair_x_m": [0.0, -0.02, 0.02], "physics_budget_steps": 2500,
                "commit": args.expected_commit, "native_upstream": args.expected_upstream,
                "scope": "Three development parent conditions, nine custom grasp branches; not full-task success or an independent statistical evaluation",
                "gate": "Verify successful cleanup and prefix pairing. Train no selector unless candidates show outcome complementarity beyond the best fixed candidate."}
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    rows = []
    for index, (error, repair) in enumerate(itertools.product(protocol["error_x_m"], protocol["repair_x_m"])):
        out = args.output / f"branch_{index:02d}"
        command = [sys.executable, str(root / "scripts/robotwin_probe.py"),
                   "--robotwin-root", str(args.robotwin_root), "--expected-upstream", args.expected_upstream,
                   "--task", "handover_block", "--seed", "0", "--output", str(out),
                   "--grasp-pilot", "--error-x-m", str(error), "--repair-x-m", str(repair)]
        started = time.monotonic()
        print(json.dumps({"started": index, "error_x_m": error, "repair_x_m": repair}), flush=True)
        with (args.output / f"branch_{index:02d}.log").open("x") as log:
            try:
                child = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=os.environ.copy(), timeout=360)
                code = child.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        record = {"id": index, "error_x_m": error, "repair_x_m": repair,
                  "process_exit": code, "wall_s": time.monotonic() - started}
        for name in ("result", "pilot_result", "pilot_branch"):
            path = out / (name + ".json")
            record[name] = json.loads(path.read_text()) if path.exists() else None
        rows.append(record)
        (args.output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(json.dumps({"finished": index, "process_exit": code,
                          "pilot_result": record["pilot_result"]}), flush=True)
        if code != 0:
            raise SystemExit("Stopped scaling after a process failure; records retained")


if __name__ == "__main__":
    main()
