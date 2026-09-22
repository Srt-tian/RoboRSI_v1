"""Export local MP4 comparisons and paper assets from saved simulation traces.

Requires Pillow and a local ffmpeg binary. No downloads, generated imagery, or
robot commands. Refuses to replace an already sealed run manifest.
"""

import argparse
import csv
import hashlib
import html
import json
import math
import platform
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from roborsi.rsi.artifacts import load_json, seal, source_ref, verify, write_json
from roborsi.simulation_report import render_simulation

METHOD_NAMES = {
    "fixed_plan": "Fixed plan",
    "instant_rules": "Instant rules",
    "delayed_unchecked": "Delayed / unchecked",
    "delayed_checked": "Delayed / version checked",
}
COLORS = {
    "fixed_plan": "#97a9bf",
    "instant_rules": "#59d7c4",
    "delayed_unchecked": "#ffba78",
    "delayed_checked": "#b9a0ff",
}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def movie_frame(episodes, t, scenario):
    img = Image.new("RGB", (1280, 850), "#0b1220")
    draw = ImageDraw.Draw(img)
    title, regular, small = [ImageFont.truetype(FONT, n) for n in (26, 19, 15)]
    draw.text((30, 18), "RoboRSI | Decision timing sandbox", font=title, fill="#e6edf6")
    draw.text(
        (30, 57),
        f"{scenario} | seed {episodes[0]['seed']} | world time {t:.2f} s",
        font=regular,
        fill="#a5b7cc",
    )
    for index, ep in enumerate(episodes):
        x, y = 25 + (index % 2) * 635, 98 + (index // 2) * 345
        draw.rounded_rectangle(
            (x, y, x + 610, y + 325), radius=12, fill="#142035", outline="#304159"
        )
        draw.text(
            (x + 18, y + 12),
            METHOD_NAMES[ep["method"]],
            font=regular,
            fill=COLORS[ep["method"]],
        )
        frames = [f for f in ep["frames"] if f["t"] <= t]
        frame = frames[-1] if frames else ep["frames"][0]

        def xy(p, x=x, y=y):
            return (
                x + 30 + (p[0] + 0.35) / 0.7 * 490,
                y + 258 - (p[1] + 0.20) / 0.4 * 195,
            )

        for i in range(8):
            gx = x + 30 + i * 70
            draw.line((gx, y + 58, gx, y + 260), fill="#243953")
        b, b2 = xy([0.16, 0.135]), xy([0.24, 0.065])
        draw.rectangle((*b, *b2), outline="#699ce5", width=2)
        if len(frames) > 1:
            draw.line([xy(f["grip"]) for f in frames], fill="#87694e", width=2)
        ox, oy = xy(frame["object"])
        draw.ellipse((ox - 9, oy - 6, ox + 9, oy + 6), fill="#59d7c4")
        gx, gy = xy(frame["grip"])
        width = 7 if frame["closed"] else 16
        draw.line(
            (
                gx - width,
                gy + 10,
                gx - width,
                gy - 10,
                gx + width,
                gy - 10,
                gx + width,
                gy + 10,
            ),
            fill="#ffba78",
            width=3,
        )
        draw.text((x + 530, y + 65), "z (m)", font=small, fill="#a5b7cc")
        draw.rectangle((x + 550, y + 95, x + 566, y + 245), outline="#304159")
        h = min(150, frame["grip"][2] / 0.25 * 150)
        draw.rectangle((x + 551, y + 245 - h, x + 565, y + 244), fill="#ffba78")
        terminal = t >= ep["simulated_duration_s"]
        draw.text(
            (x + 18, y + 272),
            ep["status"] if terminal else frame["phase"],
            font=regular,
            fill="#59d7c4" if terminal and ep["success"] else "#e6edf6",
        )
        events = [
            e
            for e in ep["events"]
            if e["t"] <= t and e["kind"] not in {"phase", "checkpoint"}
        ]
        draw.text(
            (x + 18, y + 302),
            events[-1]["kind"] if events else "No intervention",
            font=small,
            fill="#a5b7cc",
        )
    draw.text(
        (30, 797),
        "Kinematic contact proxy. Analytic rules + injected delay. No robot or model inference.",
        font=regular,
        fill="#ffba78",
    )
    draw.text(
        (30, 825),
        "Clock-aligned comparisons; terminated episodes freeze. Not validated Piper physics.",
        font=small,
        fill="#a5b7cc",
    )
    return img


def export_video(episodes, scenario, output):
    duration = max(e["simulated_duration_s"] for e in episodes) + 0.75
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "1280x850",
        "-r",
        "20",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        for frame_index in range(math.ceil(duration * 20)):
            proc.stdin.write(
                movie_frame(episodes, frame_index / 20, scenario).tobytes()
            )
        proc.stdin.close()
        proc.stdin = None
        _, stderr = proc.communicate(timeout=60)
        if proc.returncode:
            raise RuntimeError(
                "ffmpeg failed: " + stderr.decode(errors="replace")[:500]
            )


def table_svg(rows):
    width, height = 1220, 200 + len(rows) * 32
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="DejaVu Sans,sans-serif" fill="#20374c">',
        '<text x="30" y="42" font-size="24">RoboRSI: kinematic decision-timing benchmark</text>',
        '<text x="30" y="72" font-size="15">Analytic rules, simulated delay; no model inference or physical robot validation</text>',
    ]
    headers = [
        (30, "Scenario"),
        (245, "Method"),
        (610, "Success / N"),
        (775, "Mean sim s"),
        (950, "Stale accept"),
        (1090, "Discard"),
    ]
    for x, value in headers:
        parts.append(f'<text x="{x}" y="116" font-size="16">{value}</text>')
    for i, row in enumerate(rows):
        y = 149 + 32 * i
        values = (
            row["scenario"],
            METHOD_NAMES[row["method"]],
            f"{row['successes']} / {row['episodes']}",
            f"{row['mean_simulated_duration_s']:.3f}",
            str(row["stale_adopted"]),
            str(row["stale_discarded"]),
        )
        if i % 2 == 0:
            parts.append(
                f'<rect x="20" y="{y - 22}" width="1180" height="31" fill="#f0f4f8"/>'
            )
        for (x, _), value in zip(headers, values):
            parts.append(
                f'<text x="{x}" y="{y}" font-size="15">{html.escape(value)}</text>'
            )
    parts.append("</g></svg>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = args.run
    if (run / "manifest.json").exists():
        parser.error("run is already sealed; create a new run instead")
    data = load_json(run / "benchmark.json")
    verify(data, "roborsi-kinematic-benchmark-v1")
    if not data["process_log"]["recorded"] or not (run / "process.jsonl.gz").is_file():
        parser.error("full process log is required for a paper run")
    (run / "videos").mkdir(exist_ok=True)
    for scenario in data["config"]["scenarios"]:
        episodes = [
            e for e in data["episodes"] if e["scenario"] == scenario and e["frames"]
        ]
        export_video(episodes, scenario, run / "videos" / f"{scenario}.mp4")
        print(f"video: {scenario}", flush=True)
    with (run / "summary.csv").open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(data["summaries"][0]))
        writer.writeheader()
        writer.writerows(data["summaries"])
    (run / "summary.svg").write_text(table_svg(data["summaries"]), encoding="utf-8")
    data["paper_assets"] = True
    data = seal(data)
    (run / "benchmark.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run / "index.html").write_text(render_simulation(data), encoding="utf-8")
    summary = [s for s in data["summaries"] if s["scenario"] == "all"]
    lines = [
        "# Kinematic decision-timing experiment",
        "",
        "This is a logic sandbox, not a physical robot result.",
        "",
        f"Configuration: `{json.dumps(data['config'])}`",
        "",
        "## Aggregate results",
        "",
        "| Method | Success / episodes | Mean simulated seconds | Stale adoptions | Stale discards |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in summary:
        lines.append(
            f"| {r['method']} | {r['successes']} / {r['episodes']} | {r['mean_simulated_duration_s']:.3f} | {r['stale_adopted']} | {r['stale_discarded']} |"
        )
    lines += [
        "",
        "All injected protection stops count in the denominator. Mean time includes successes and failures.",
        "No inference calls, trained judgments, or learned RSI updates are evaluated. Instant rules are a strong baseline.",
        "",
        "## Files",
        "",
        "- `benchmark.json`: configuration, source hashes, every episode's events and metrics; 20 Hz visual traces for the first seed.",
        "- `process.jsonl.gz`: every episode's complete 200 Hz simulated states, named columns, phase encoding and pending revision.",
        "- `summary.csv` and `summary.svg`: editable result table.",
        "- `videos/*.mp4`: six four-method comparisons at 20 fps, aligned by world time.",
        "- `index.html`: local interactive player, timeline, event records, videos and downloads.",
        "- `manifest.json`: file hashes, renderer and source provenance.",
        "",
        "## Reproduce from the repository root",
        "",
        "```bash",
        f"python -m roborsi.simulation --seeds {data['config']['seeds']} --start-seed {data['config']['start_seed']} --decision-delay {data['config']['decision_delay_s']} --output runs/new_simulation",
        "python scripts/export_simulation_media.py runs/new_simulation",
        "python scripts/verify_paper_run.py runs/new_simulation",
        "```",
        "",
        "Simulation requires the project environment. Media export additionally needs Pillow and ffmpeg.",
        "",
        "## Limitations",
        "",
        *["- " + x for x in data["limitations"]],
        "",
    ]
    (run / "README.md").write_text("\n".join(lines), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ffmpeg = subprocess.run(
        ["ffmpeg", "-version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    files = [
        {
            "path": str(p.relative_to(run)),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(run.rglob("*"))
        if p.is_file()
    ]
    write_json(
        run / "manifest.json",
        {
            "schema": "roborsi-paper-run-v1",
            "execution_authorized": False,
            "git_base_commit": base,
            "source_state": "working-tree implementation identified by content hashes",
            "benchmark_sha256": data["artifact_sha256"],
            "simulation_sources": data["implementation"],
            "export_sources": [
                source_ref(__file__),
                source_ref(root / "src/roborsi/simulation_report.py"),
            ],
            "python": platform.python_version(),
            "ffmpeg": ffmpeg,
            "files": files,
        },
    )
    print(
        json.dumps(
            {
                "sealed_run": str(run),
                "files": len(files),
                "bytes": sum(f["bytes"] for f in files),
            }
        )
    )


if __name__ == "__main__":
    main()
