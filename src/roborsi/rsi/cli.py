"""Offline RSI: evidence triage, candidate checks, review, and scoped context."""

import argparse
import json
from pathlib import Path

from .artifacts import load_json, write_json
from .calibration import calibrate
from .contracts import checkpoint
from .evaluation import evaluate, sweep
from .evidence import analyze
from .judgment import judge, prepare
from .memory import review, select_context
from .providers import DemoProvider, DisabledProvider, ReplayProvider, TypeSafeProvider
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
    p.add_argument("--judgment", type=Path)
    p.add_argument(
        "--decision", choices=["accept_for_planning", "reject"], required=True
    )
    p = commands.add_parser(
        "context", help="select reviewed records with exactly matching scope"
    )
    p.add_argument("reviews", nargs="+", type=Path)
    p.add_argument("--scope", type=Path, required=True)
    p = commands.add_parser("checkpoint", help="evaluate phase expectations offline")
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--observation", type=Path, required=True)
    p = commands.add_parser("prepare-judgment", help="build a bounded candidate menu")
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--comparison", type=Path, action="append", required=True)
    p.add_argument("--trial-id", required=True)
    p.add_argument("--scope", type=Path, required=True)
    p.add_argument("--numerical-only", action="store_true")
    p.add_argument("--checkpoint", type=Path)
    p.add_argument("--max-age", type=float, default=600)
    p.add_argument("--min-probability", type=float, default=0.8)
    p.add_argument("--min-margin", type=float, default=0.15)
    p = commands.add_parser("judge", help="request typed advice; default is disabled")
    p.add_argument("--request", type=Path, required=True)
    p.add_argument(
        "--provider",
        choices=["disabled", "demo", "replay", "typesafe"],
        default="disabled",
    )
    p.add_argument("--response", type=Path)
    p.add_argument("--current-checkpoint", type=Path)
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--model", default="jev-1.13.0")
    p.add_argument("--timeout", type=float, default=5)
    p = commands.add_parser(
        "calibrate", help="select on validation, evaluate on held-out episodes"
    )
    p.add_argument("dataset", type=Path)
    p.add_argument("--max-validation-error", type=float, default=0.1)
    p.add_argument("--min-accepted", type=int, default=10)
    p.add_argument("--min-margin", type=float, default=0.15)
    p = commands.add_parser(
        "report-judgment", help="render evidence and typed decisions locally"
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--sweep", type=Path, required=True)
    p.add_argument("--judgment", type=Path, required=True)
    for name, p in commands.choices.items():
        p.add_argument("--output", type=Path, required=True)
        if name in {"evaluate", "sweep", "workbench"}:
            p.add_argument("--urdf", type=Path)
            p.add_argument("--tcp-floor", type=float, default=0.004)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new iteration path")
    if args.command == "checkpoint":
        result = checkpoint(load_json(args.contract), load_json(args.observation))
    elif args.command == "prepare-judgment":
        result = prepare(
            load_json(args.evidence),
            [load_json(p) for p in args.comparison],
            trial_id=args.trial_id,
            scope=load_json(args.scope),
            numerical_only=args.numerical_only,
            max_age_s=args.max_age,
            min_probability=args.min_probability,
            min_margin=args.min_margin,
            checkpoint_event=load_json(args.checkpoint) if args.checkpoint else None,
        )
    elif args.command == "judge":
        if args.provider == "replay":
            if not args.response:
                parser.error("--provider replay requires --response")
            provider = ReplayProvider(load_json(args.response))
        elif args.provider == "typesafe":
            if not args.allow_network:
                parser.error("--provider typesafe requires --allow-network")
            provider = TypeSafeProvider(allow_network=True, model=args.model)
        else:
            provider = DemoProvider() if args.provider == "demo" else DisabledProvider()
        result = judge(
            load_json(args.request),
            provider,
            timeout_s=args.timeout,
            context_probe=(lambda: load_json(args.current_checkpoint))
            if args.current_checkpoint
            else None,
        )
    elif args.command == "calibrate":
        result = calibrate(
            load_json(args.dataset),
            max_validation_error=args.max_validation_error,
            min_accepted=args.min_accepted,
            min_margin=args.min_margin,
        )
    elif args.command == "report-judgment":
        page = render(
            load_json(args.evidence), load_json(args.sweep), load_json(args.judgment)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(page)
        print(json.dumps({"report": str(args.output)}))
        return
    elif args.command == "analyze":
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
            judgment=load_json(args.judgment) if args.judgment else None,
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
