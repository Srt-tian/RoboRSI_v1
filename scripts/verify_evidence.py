"""Verify archived evidence hashes and recompute final-trial cadence (no hardware)."""

from pathlib import Path
import gzip, hashlib, json

r = Path(__file__).resolve().parents[1] / "experiments/2026-09-17"
manifest = json.loads((r / "manifest.json").read_text())
for entry in manifest:
    compressed = (r / entry["file"]).read_bytes()
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(compressed).hexdigest() == entry["gzip_sha256"], entry["file"]
    assert hashlib.sha256(raw).hexdigest() == entry["original_sha256"], entry["file"]
    assert len(raw) == entry["original_bytes"], entry["file"]
name = r / "raw_logs/servo20_three_deep.jsonl.commands.jsonl.gz"
rows = [json.loads(line) for line in gzip.decompress(name.read_bytes()).splitlines()]
t = [x["monotonic_sec"] for x in rows]
hz = (len(t) - 1) / (t[-1] - t[0])
metric = json.loads((r / "metrics.json").read_text())[-1]
assert abs(hz - metric["actual_command_hz"]) < 1e-8
assert len(rows) == metric["command_rows"]
print(
    json.dumps(
        {
            "verified_archives": len(manifest),
            "final_command_count": len(rows),
            "final_hz": hz,
        }
    )
)
