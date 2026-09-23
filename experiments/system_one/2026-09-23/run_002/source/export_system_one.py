"""Archive learned-decision experiments, state replays, and local paper assets.

Run with Python + Pillow and local ffmpeg. No downloads or robot access.
"""

import argparse
import csv
import gzip
import hashlib
import html
import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
NAMES = ("GRASP NOW", "LOOK THEN GRASP", "PROBE THEN GRASP")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(record, t):
    image = Image.new("RGB", (1280, 800), "#0b1220")
    draw = ImageDraw.Draw(image)
    title, body, small = [ImageFont.truetype(FONT, n) for n in (30, 22, 17)]
    draw.text((28, 20), "RoboRSI | The execution-time value of evidence", font=title, fill="#e6edf6")
    draw.text((28, 65), f"{record['cohort']} / context {record['index']} / stochastic sample 0 / t = {t:.3f} s", font=body, fill="#a5b7cc")
    c, z = record["context"], record["replay"]
    extent = max(.055, *map(abs, z["actual"]), abs(z["x0"]), *map(abs, z["target"]))+2*c["tolerance"]
    xpos = lambda x: 640+x/extent*520
    for a in range(3):
        y = 126+a*187
        draw.rounded_rectangle((24, y, 1256, y+173), radius=12, fill="#142238", outline="#304159")
        draw.text((44, y+14), NAMES[a], font=body, fill="#ffba78")
        duration = .22+[0, c["look_delay"], c["probe_delay"]][a]
        arrival = [0, c["look_delay"], c["probe_delay"]][a]
        tau = min(t, duration)
        done = t >= duration
        status = ("SUCCESS" if z["success"][a] else "FAILED") if done else ("WAITING FOR EVIDENCE" if t < arrival else "EXECUTING GRASP")
        draw.text((740, y+15), status, font=body, fill="#59d7c4" if done and z["success"][a] else "#e6edf6")
        draw.line((95, y+89, 1185, y+89), fill="#405673", width=2)
        for k in range(-2, 3):
            x = extent*k/2
            draw.text((xpos(x)-18, y+107), f"{x*1000:.0f}", font=small, fill="#a5b7cc")
        ox = z["x0"]+z["velocity"]*tau+(z["kick"] if a == 2 and tau >= .1 else 0)
        color = "#ef7188" if a == 2 and tau >= .1 and z["damaged"] else "#59d7c4"
        draw.ellipse((xpos(ox)-9, y+80, xpos(ox)+9, y+98), fill=color)
        if t >= arrival:
            center = z["target"][a]+z["actuator"]
            draw.rectangle((xpos(center-c["tolerance"]), y+69, xpos(center+c["tolerance"]), y+104), outline="#ffba78", width=3)
        draw.text((44, y+143), f"MC success: {record['success_mc'][a]:.3f} | action duration: {duration:.3f} s | x in mm", font=small, fill="#a5b7cc")
    draw.text((28, 711), "Analytical probabilistic simulator. State replay, not robot joint motion or rendered physics.", font=small, fill="#ffba78")
    draw.text((28, 741), "Teal: hidden truth (audit only). Orange: capture tolerance. Shared latent noise. Playback at 0.25x.", font=small, fill="#a5b7cc")
    draw.text((28, 770), "A single sample illustrates mechanics; quantitative results use all independent evaluation branches.", font=small, fill="#a5b7cc")
    return image


def movie(record, path):
    duration = .22+max(record["context"]["look_delay"], record["context"]["probe_delay"])+.25
    fps, speed = 25, .25
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1280x800", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for i in range(math.ceil(duration/speed*fps)):
            process.stdin.write(frame(record, i/fps*speed).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg export failed")


def figure(root, results):
    rows = []
    for cohort in results["summaries"]:
        for key, metrics in cohort["variant_means"].items():
            rows.append((cohort["cohort"], key, metrics))
    height = 160+len(rows)*46
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" viewBox="0 0 1400 {height}"><rect width="1400" height="{height}" fill="#0b1220"/><g fill="#e6edf6" font-family="sans-serif">', '<text x="32" y="42" font-size="27">System One / held-out evaluation / three training seeds</text>']
    for x, label in ((32, "Cohort"), (190, "Model"), (550, "Cost (lower)"), (780, "Success"), (975, "Acquire evidence"), (1200, "Time / s")):
        elements.append(f'<text x="{x}" y="95" font-size="19" fill="#a5b7cc">{label}</text>')
    for i, (cohort, name, metrics) in enumerate(rows):
        y = 134+i*46
        for x, text in ((32, cohort), (190, name), (550, f"{metrics['mean_cost']:.6f}"), (780, f"{metrics['success_rate']*100:.2f}%"), (975, f"{metrics['sense_rate']*100:.2f}%"), (1200, f"{metrics['mean_duration_s']:.3f}")):
            elements.append(f'<text x="{x}" y="{y}" font-size="19">{html.escape(text)}</text>')
        elements.append(f'<path d="M32 {y+14} H1368" stroke="#304159"/>')
    elements.append(f'<text x="32" y="{height-12}" fill="#ffba78" font-size="16">Analytical macro simulator; no official Jev, visual encoder, robot physics, or hardware performance claim.</text></g></svg>')
    (root/"results.svg").write_text("".join(elements))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    if (root/"manifest.json").exists():
        raise ValueError("sealed runs are immutable; export into a new run")
    results = json.loads((root/"results.json").read_text())
    config = json.loads((root/"config.json").read_text())
    records = json.loads(gzip.decompress((root/"decisions.json.gz").read_bytes()))
    videos = []
    for cohort in ("iid", "delay", "cost"):
        record = next(r for r in records if r["cohort"] == cohort and r["index"] == 0)
        path = root/f"{cohort}_sample0.mp4"
        if not path.exists():
            movie(record, path)
        videos.append({"path": path.name, "cohort": cohort, "context_index": 0, "draw_index": 0,
                       "selection_rule": "first context, first draw; no success filtering",
                       "caption": f"{cohort} · 场景 0 / 随机样本 0 · 三个候选分支 · 0.25× 回放"})
    (root/"media.json").write_text(json.dumps({"videos": videos}, ensure_ascii=False, indent=2)+"\n")
    figure(root, results)
    if not (root/"summary.csv").exists():
        with (root/"summary.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            keys = ("mean_cost", "success_rate", "sense_rate", "mean_duration_s", "rescue_rate", "spoil_rate")
            writer.writerow(("cohort", "method", *keys))
            for cohort in results["summaries"]:
                for name, metrics in cohort["methods"].items():
                    writer.writerow((cohort["cohort"], name, *(metrics[k] for k in keys)))
    sources = root/"source"
    sources.mkdir(exist_ok=True)
    for name, expected in config["source_sha256"].items():
        source = ROOT/"src/roborsi/system_one"/name
        if sha(source) != expected:
            raise ValueError(f"source changed since training: {name}; archive original source before export")
        shutil.copyfile(source, sources/name)
    shutil.copyfile(Path(__file__), sources/"export_system_one.py")
    viewer = "../../../../paper/system-one.html?run=../"+str(root.relative_to(ROOT))+"/"
    (root/"index.html").write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={html.escape(viewer)}"><a href="{html.escape(viewer)}">打开本地实验工作台</a>')
    (root/"README.md").write_text("# Standalone System One study\n\nAnalytical probabilistic grasp simulation. Learned NumPy models; no official Jev, language encoder, rigid-body physics or hardware validation.\n\n- `config.json`: seeds, training configuration and source hashes.\n- `trials.json`, `models/`: every training run and its validation-selected checkpoint.\n- `frozen_protocol.json`: choices frozen before test contexts were constructed.\n- `results.json`, `summary.csv`, `results.svg`: all held-out results and context-bootstrap intervals.\n- `decisions.json.gz`: every test context, predictions, selected macro and first-draw state replay.\n- `*.npz`: all saved branch outcome arrays; hidden rollout values never enter policy input.\n- `*_sample0.mp4`: first context / first draw of each cohort, no success-based filtering.\n- `source/`: exact sources used for this run, preserved across later refactors.\n\nRun records are sealed and must not be overwritten. The browser viewer is a maintained shared tool, not a frozen dependency of the results.\n")
    manifest = {"schema": "roborsi.system_one_run.v1", "run": str(root.relative_to(ROOT)),
                "contexts": len(records), "training_trials": len(json.loads((root/"trials.json").read_text())),
                "candidate_branches": sum(s["contexts"]*s["draws_per_context"]*3 for s in results["summaries"]),
                "files": [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(root.rglob("*")) if p.is_file()]}
    (root/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({"run": str(root.relative_to(ROOT)), "files": len(manifest["files"]), "videos": len(videos), "contexts": len(records), "bytes": sum(f["bytes"] for f in manifest["files"])}))


if __name__ == "__main__":
    main()
