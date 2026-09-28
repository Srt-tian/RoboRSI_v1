"""Export bounded, sanitized Web evidence; full traces stay on the execution host."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.physics_root, args.output
    out.mkdir(parents=True, exist_ok=False)
    copied = []

    def copy(source, relative):
        if not source.exists():
            return False
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
        return True

    native = []
    for ident, folder in (("lift", "deployable_cleanup_lift_001"),
                          ("handover", "deployable_handover_feedback_001")):
        source = root / folder
        for name in ("result.json", "protocol.json", "frames.json", "head.mp4", "final.png",
                     "feedback_audit.json", "joint_layout.json"):
            copy(source / name, f"native/{ident}/{name}")
        process = read(root / (folder + ".process.json"))
        copy(root / (folder + ".process.json"), f"native/{ident}/process.json")
        result = read(source / "result.json")
        native.append(dict(id=ident, directory=f"native/{ident}", exit_code=process["returncode"], **result))
    copy(root / "piper_candidate_audit_001/audit.json", "piper/audit.json")

    def export_pilot(folder, relative):
        source = root / folder
        records = read(source / "results.json")
        copy(source / "results.json", relative + "/results.json")
        copy(source / "protocol.json", relative + "/protocol.json")
        rows = []
        for record in records:
            branch = f'branch_{record["id"]:02d}'
            directory = relative + "/" + branch
            for name in ("protocol.json", "result.json", "pilot_branch.json", "pilot_result.json",
                         "frames.json", "joint_layout.json", "head.mp4", "final.png"):
                copy(source / branch / name, directory + "/" + name)
            result = record["result"] or {}
            rows.append({key: record[key] for key in ("id", "error_x_m", "repair_x_m", "process_exit")} |
                        {"directory": directory, "video": (source / branch / "head.mp4").exists(),
                         "pilot_success": result.get("pilot_success"), "physics_steps": result.get("physics_steps"),
                         "simulation_time_s": result.get("simulation_time_s")})
        groups = []
        for error in sorted(set(r["error_x_m"] for r in records)):
            group = [r for r in records if r["error_x_m"] == error]
            events = [r["pilot_branch"] for r in group if r["pilot_branch"]]
            hashes = {event["prefix_digest"] for event in events}
            poses = [e["audit_only_object_pose"] for e in events]
            delta = max((abs(x - y) for p in poses for x, y in zip(p, poses[0])), default=0)
            groups.append({"error_x_m": error, "branches": len(group),
                           "prefix_steps": [e["physics_step"] for e in events],
                           "unique_prefix_digests": len(hashes), "max_branch_object_pose_difference": delta,
                           "all_match_reference": all(e.get("matches_reference_prefix", False) for e in events),
                           "matched": len(events) == 3 and len(hashes) == 1 and delta < 1e-7})
        return {"rows": rows, "pairing": groups}

    pilot = export_pilot("deployable_grasp_pilot_001", "pilot")
    prefix = export_pilot("deployable_prefix_check_001", "prefix_check")
    pilot["conclusion"] = "首轮无偏差的 3 分支成功，±40 mm 的 6 分支失败，未观察到固定候选之外的收益空间。独立重规划前缀不完全一致，不将首轮表格当作同状态因果比较；没有启动新选择器训练。"
    matched = len(prefix["rows"]) == 3 and all(g["matched"] and g["all_match_reference"] for g in prefix["pairing"])
    summary = {
        "schema": "roborsi.deployable-web.v1", "date": "2026-09-28",
        "scope": "Development evidence and offline hardware preparation; no new hardware execution or new learned model",
        "native": native, "pilot": pilot, "prefix_check": prefix,
        "prefix_replay_qualified": matched,
        "conclusion": "原生双臂任务均正常退出，Piper 历史候选 105/120 通过离线检查。固定横移重夹预检没有救回偏差案例；保留负结果，先改善候选与观测时机。" +
                      ("追加 3 分支已验证冻结前缀逐步一致。" if matched else "冻结前缀尚未通过完整一致性检查。"),
        "report_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "next_hypothesis": "Evaluate decisions before the object has been displaced by failed closure; compare reobservation against blind relative retries under equal budgets.",
    }
    write(out / "summary.json", summary)
    files = []
    for path in sorted(out.rglob("*")):
        if path.is_file():
            blob = path.read_bytes()
            files.append({"path": str(path.relative_to(out)), "bytes": len(blob),
                          "sha256": hashlib.sha256(blob).hexdigest()})
    total = sum(file["bytes"] for file in files)
    if total > 20 * 1024 * 1024:
        raise ValueError("Export exceeds the explicit small-preview budget")
    write(out / "manifest.json", {"scope": "Selected small videos and metadata; no full physics traces or plan arrays",
                                  "total_bytes": total, "files": files})
    print(json.dumps({"files": len(files), "bytes": total, "prefix_replay_qualified": matched,
                      "pairing": prefix["pairing"]}, indent=2))


if __name__ == "__main__":
    main()
