"""Offline RSI: evidence triage, candidate checks, review, and scoped context."""

import argparse
import json
from pathlib import Path

from .artifacts import load_json, write_json
from .evaluation import evaluate, sweep
from .evidence import analyze
from .memory import review, select_context
from .report import render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser(
        "analyze", help="triage metric records without inferring task success"
    )
    p.add_argument("metrics", type=Path)
    p = commands.add_parser(
        "evaluate", help="compare a bounded revision against its baseline"
    )
    p.add_argument("baseline", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--baseline-speed", type=int, choices=[1, 2], default=1)
    p.add_argument("--candidate-speed", type=int, choices=[1, 2], default=1)
    p.add_argument("--max-joint-delta", type=float, default=0.12)
    p = commands.add_parser("sweep", help="enumerate the two existing timing profiles")
    p.add_argument("program", type=Path)
    p = commands.add_parser(
        "workbench", help="create evidence, a timing sweep, and local HTML"
    )
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--program", type=Path, required=True)
    p = commands.add_parser(
        "review", help="record an explicit human review, not execution approval"
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--comparison", type=Path, required=True)
    p.add_argument("--trial-id", required=True)
    p.add_argument("--scope", type=Path, required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument(
        "--decision", choices=["accept_for_planning", "reject"], required=True
    )
    p = commands.add_parser(
        "context", help="select reviewed records with exactly matching scope"
    )
    p.add_argument("reviews", nargs="+", type=Path)
    p.add_argument("--scope", type=Path, required=True)
    for name, p in commands.choices.items():
        p.add_argument("--output", type=Path, required=True)
        if name in {"evaluate", "sweep", "workbench"}:
            p.add_argument("--urdf", type=Path)
            p.add_argument("--tcp-floor", type=float, default=0.004)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new iteration path")
    if args.command == "analyze":
        result = analyze(args.metrics)
    elif args.command == "evaluate":
        result = evaluate(
            load_json(args.baseline),
            load_json(args.candidate),
            baseline_speed=args.baseline_speed,
            candidate_speed=args.candidate_speed,
            max_joint_delta=args.max_joint_delta,
            urdf=args.urdf,
            tcp_floor=args.tcp_floor,
        )
    elif args.command in {"sweep", "workbench"}:
        result = sweep(
            load_json(args.program), urdf=args.urdf, tcp_floor=args.tcp_floor
        )
        if args.command == "workbench":
            evidence = analyze(args.metrics)
            page = render(evidence, result)
            args.output.mkdir(parents=True, exist_ok=False)
            write_json(args.output / "evidence.json", evidence)
            write_json(args.output / "sweep.json", result)
            for candidate in result["candidates"]:
                speed = candidate["policy"]["candidate_speed"]
                write_json(args.output / f"profile_{speed}x.json", candidate)
            (args.output / "index.html").write_text(page, encoding="utf-8")
            print(
                json.dumps(
                    {
                        "report": str(args.output / "index.html"),
                        "trials": evidence["summary"]["trials"],
                        "selection_scope": result["selection_scope"],
                    }
                )
            )
            if result["selected_comparison_sha256"] is None:
                raise SystemExit(2)
            return
    elif args.command == "review":
        result = review(
            load_json(args.evidence),
            load_json(args.comparison),
            trial_id=args.trial_id,
            scope=load_json(args.scope),
            lesson=args.lesson,
            reviewer=args.reviewer,
            decision=args.decision,
        )
    else:
        result = select_context(
            [load_json(p) for p in args.reviews], load_json(args.scope)
        )
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "schema": result["schema"],
                "sha256": result["artifact_sha256"],
            }
        )
    )
    if result.get("status") == "rejected" or (
        args.command == "sweep" and result["selected_comparison_sha256"] is None
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
