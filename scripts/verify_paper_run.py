"""Verify paper-run file hashes and process-log consistency without hardware."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def verify_run(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (
        manifest["schema"] != "roborsi-paper-run-v1"
        or manifest["execution_authorized"] is not False
    ):
        raise ValueError("paper-run manifest required")
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size != item["bytes"]:
            raise ValueError("invalid path or size")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("file fingerprint mismatch: " + item["path"])
    benchmark = json.loads((root / "benchmark.json").read_text())
    episodes = {e["episode_id"]: e for e in benchmark["episodes"]}
    seen, count = set(), 0
    with gzip.open(root / "process.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            key = record["episode_id"]
            if key in seen or key not in episodes:
                raise ValueError("unexpected process episode")
            seen.add(key)
            rows = record["samples"]
            if len(rows) != episodes[key]["simulated_control_ticks"]:
                raise ValueError("process count mismatch")
            for i, row in enumerate(rows):
                if len(row) != len(record["columns"]) or abs(row[0] - i * 0.005) > 1e-8:
                    raise ValueError("process timestamp or column mismatch")
            count += len(rows)
    if seen != episodes.keys() or count != benchmark["process_log"]["samples"]:
        raise ValueError("missing process samples")
    return {
        "verified_files": len(manifest["files"]),
        "episodes": len(seen),
        "samples": count,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(json.dumps(verify_run(parser.parse_args().run)))
