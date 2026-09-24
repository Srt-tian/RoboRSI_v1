#!/usr/bin/env python3
"""Read-only LeRobot v3 audit and fixed-task demonstration previews.

This does not execute a policy, reconstruct simulator states, or measure success.
The dataset remains on the execution host; only the small report is exportable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview-tasks", type=int, nargs="*", default=[0, 2, 8])
    args = parser.parse_args()
    root, out = args.dataset.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("Audit requires a clean, committed checkout")
    info = json.loads((root / "meta/info.json").read_text())
    assert info["codebase_version"] == "v3.0"
    fps = float(info["fps"])
    cameras = [k for k, v in info["features"].items() if v["dtype"] == "video"]
    assert len(cameras) == 2, "This preview supports exactly two cameras"
    files = sorted(p for p in root.rglob("*") if p.is_file())
    inventory = [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
                  "sha256": sha256(p)} for p in files]
    write_json(out / "source_files.json", inventory)
    data_files = sorted((root / "data").rglob("*.parquet"))
    tables = [pq.read_table(p) for p in data_files]
    table = pa.concat_tables(tables)
    episodes = pa.concat_tables([pq.read_table(p) for p in sorted((root / "meta/episodes").rglob("*.parquet"))]).to_pylist()
    tasks = pq.read_table(root / "meta/tasks.parquet").to_pylist()
    tasks = {int(t["task_index"]): t.get("task", t.get("__index_level_0__")) for t in tasks}
    columns = {k: table[k].to_numpy() for k in ["index", "episode_index", "frame_index", "task_index", "timestamp"]}
    action = np.asarray(table["action"].to_pylist())
    state = np.asarray(table["observation.state"].to_pylist())
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    n = table.num_rows
    check(n == info["total_frames"], "frame count differs from info.json")
    check(len(episodes) == info["total_episodes"], "episode count differs from info.json")
    check(len(tasks) == info["total_tasks"], "task count differs from info.json")
    check(np.array_equal(columns["index"], np.arange(n)), "global row indices are not contiguous")
    check(np.array_equal(sorted(e["episode_index"] for e in episodes), np.arange(len(episodes))), "episode IDs are not contiguous")
    check(np.isfinite(action).all() and np.isfinite(state).all(), "non-finite action or state")
    check(list(action.shape) == [n, *info["features"]["action"]["shape"]], "action shape differs")
    check(list(state.shape) == [n, *info["features"]["observation.state"]["shape"]], "state shape differs")
    data_ranges = {str(p.relative_to(root)): (int(t["index"][0].as_py()), int(t["index"][-1].as_py()) + 1)
                   for p, t in zip(data_files, tables)}
    video_ends, counts, first_by_task = {}, Counter(), {}
    cursor = 0
    for e in episodes:
        eid, lo, hi = e["episode_index"], e["dataset_from_index"], e["dataset_to_index"]
        valid = 0 <= lo < hi <= n
        check(valid, f"invalid row bounds episode {eid}")
        if not valid:
            continue
        check(lo == cursor and hi - lo == e["length"], f"noncontiguous episode {eid}")
        cursor = hi
        check(np.all(columns["episode_index"][lo:hi] == eid), f"row episode mismatch {eid}")
        check(np.array_equal(columns["frame_index"][lo:hi], np.arange(e["length"])), f"frame indices episode {eid}")
        check(np.allclose(columns["timestamp"][lo:hi], np.arange(e["length"]) / fps, atol=1e-4), f"timestamps episode {eid}")
        tid = int(columns["task_index"][lo])
        check(tid in tasks and np.all(columns["task_index"][lo:hi] == tid), f"task changes inside episode {eid}")
        counts[tid] += 1
        first_by_task.setdefault(tid, e)
        dp = info["data_path"].format(chunk_index=e["data/chunk_index"], file_index=e["data/file_index"])
        bounds = data_ranges.get(dp)
        check(bounds is not None and bounds[0] <= lo < bounds[1], f"data pointer episode {eid}")
        for camera in cameras:
            prefix = "videos/" + camera
            vp = info["video_path"].format(video_key=camera, chunk_index=e[prefix + "/chunk_index"], file_index=e[prefix + "/file_index"])
            start, end = e[prefix + "/from_timestamp"], e[prefix + "/to_timestamp"]
            check(abs((end - start) * fps - e["length"]) < 0.02, f"video length episode {eid} {camera}")
            check(abs(video_ends.get(vp, 0) - start) < 1e-3, f"video timestamp gap {eid} {camera}")
            video_ends[vp] = end
    check(cursor == n, "episode metadata does not cover all rows")
    video_rows = []
    for relative, end in sorted(video_ends.items()):
        p = root / relative
        check(p.exists(), f"missing video {relative}")
        if not p.exists():
            continue
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(p)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            errors.append(f"ffprobe failed {relative}")
            continue
        stream = json.loads(result.stdout)["streams"][0]
        duration = float(stream["duration"])
        frames = int(stream["nb_frames"]) if stream.get("nb_frames", "N/A") != "N/A" else None
        check(abs(duration - end) <= 1 / fps + 1e-3, f"duration mismatch {relative}")
        if frames is not None:
            check(abs(frames - round(end * fps)) <= 1, f"frame count mismatch {relative}")
        check((stream["width"], stream["height"]) == (256, 256), f"resolution mismatch {relative}")
        video_rows.append({"path": relative, "duration": duration, "frames": frames, "codec": stream["codec_name"]})
    write_json(out / "video_headers.json", video_rows)
    summary = {"created_at": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
               "scope": "Existing training demonstrations; no policy execution or task-success measurement",
               "codebase_version": info["codebase_version"], "robot_type": info["robot_type"], "fps": fps,
               "files": len(files), "bytes": sum(x["bytes"] for x in inventory),
               "frames": n, "episodes": len(episodes), "task_count": len(tasks), "video_files": len(video_rows),
               "source_info_sha256": sha256(root / "meta/info.json"), "action_dim": action.shape[1], "state_dim": state.shape[1],
               "cameras": cameras, "splits": info["splits"],
               "action_min": action.min(0).tolist(), "action_max": action.max(0).tolist(),
               "tasks": [{"id": i, "name": tasks[i], "episodes": counts[i]} for i in sorted(tasks)],
               "passed": not errors, "errors": errors,
               "limits": ["State and action coordinate conventions are not yet verified against simulator conversion code.",
                          "Only train split is declared; a simulator test protocol must be frozen separately.",
                          "Video headers are checked for all files; full decoding is checked only for the fixed preview episodes.",
                          "This is 1693 demonstrations, not a claim of a complete 2000-demonstration benchmark release."]}
    write_json(out / "audit.json", summary)
    if errors:
        raise RuntimeError(f"Audit failed: {len(errors)} errors; see audit.json")
    previews = []
    for tid in args.preview_tasks:
        e = first_by_task[tid]
        output = out / f"task-{tid:02d}_episode-{e['episode_index']:04d}.mp4"
        cmd = ["ffmpeg", "-nostdin", "-v", "error"]
        for camera in cameras:
            prefix = "videos/" + camera
            source = root / info["video_path"].format(video_key=camera, chunk_index=e[prefix + "/chunk_index"], file_index=e[prefix + "/file_index"])
            cmd += ["-ss", str(e[prefix + "/from_timestamp"]), "-i", str(source)]
        cmd += ["-filter_complex", "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]hstack=inputs=2[v]", "-map", "[v]", "-frames:v", str(e["length"]), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
        subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL)
        preview_probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(output)], text=True))["streams"][0]
        assert int(preview_probe["nb_read_frames"]) == e["length"]
        lo, hi = e["dataset_from_index"], e["dataset_to_index"]
        trace_name = output.stem + ".json"
        write_json(out / trace_name, {"fps": fps, "state": state[lo:hi].tolist(), "action": action[lo:hi].tolist()})
        previews.append({"task_id": tid, "task": tasks[tid], "episode_id": e["episode_index"], "frames": e["length"], "duration": e["length"] / fps,
                         "video": output.name, "trace": trace_name, "camera_order": cameras,
                         "selection": "First episode of prespecified task, selected without viewing outcome", "type": "training_demonstration"})
    write_json(out / "previews.json", previews)
    manifest = {"files": [{"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(out.iterdir()) if p.is_file()],
                "scope": summary["scope"], "source_commit": commit}
    write_json(out / "manifest.json", manifest)
    print(json.dumps({"passed": True, "frames": n, "episodes": len(episodes), "videos": len(video_rows), "previews": len(previews), "export_bytes": sum(x["bytes"] for x in manifest["files"])}), flush=True)


if __name__ == "__main__":
    main()
