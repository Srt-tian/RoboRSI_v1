"""Verify byte-identical research exports, including explicitly partial caches."""
import hashlib
import json
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[1]
    manifests = sorted(
        path
        for area in ("mujoco", "system_one")
        for path in (repo / "experiments" / area).glob("*/*/manifest.json")
    )
    if not manifests:
        raise SystemExit("No research manifests found")
    files = 0
    partial = 0
    for manifest in manifests:
        record = json.loads(manifest.read_text())
        root = manifest.parent.resolve()
        entries = record["files"]
        seen = set()
        for entry in entries:
            name = entry["path"]
            path = (root / name).resolve()
            if not path.is_relative_to(root) or name in seen:
                raise ValueError(f"Invalid or duplicate path in {manifest}: {name}")
            seen.add(name)
            data = path.read_bytes()
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError(f"Evidence mismatch: {path}")
            files += 1
        if record["schema"] == "roborsi.mujoco.local-cache.v1":
            partial += 1
            remote = json.loads((root / "remote_manifest.json").read_text())
            remote_files = {entry["path"]: entry for entry in remote["files"]}
            for entry in entries:
                if entry["path"] == "remote_manifest.json":
                    continue
                if remote_files.get(entry["path"]) != entry:
                    raise ValueError(f"Cache differs from archive: {root / entry['path']}")
        elif record["schema"] in {"roborsi.rsi.local-cache.v1", "roborsi.queue.local-cache.v1", "roborsi.fetch.local-cache.v1"}:
            partial += 1
            originals = set()
            archive_names = set()
            for archive in record["remote_archives"]:
                archive_names.add(archive["manifest"])
                remote = json.loads((root / archive["manifest"]).read_text())
                for entry in remote["files"]:
                    originals.add((archive["prefix"] + entry["path"], entry["bytes"], entry["sha256"]))
            derived = set(record.get("derived_files", []))
            for entry in entries:
                if entry["path"] in archive_names | derived:
                    continue
                if (entry["path"], entry["bytes"], entry["sha256"]) not in originals:
                    raise ValueError(f"Cache differs from archives: {root / entry['path']}")
    print(json.dumps({"manifests": len(manifests), "files_verified": files,
                      "partial_caches": partial, "status": "passed",
                      "scope": "Exported bytes only; absent remote traces are not locally verified."}))


if __name__ == "__main__":
    main()
