"""Build a local review demo with explicitly synthetic provider responses."""

import argparse
import json
import time
from pathlib import Path

from roborsi.rsi.artifacts import digest, load_json, write_json
from roborsi.rsi.calibration import calibrate
from roborsi.rsi.contracts import checkpoint
from roborsi.rsi.evaluation import sweep
from roborsi.rsi.evidence import analyze
from roborsi.rsi.judgment import judge, prepare
from roborsi.rsi.providers import DemoProvider
from roborsi.rsi.report import render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new iteration path")
    root = Path(__file__).resolve().parents[1]
    program = load_json(root / "examples/three_objects.json")
    evidence = analyze(root / "experiments/2026-09-17/metrics.json")
    candidates = sweep(program, tcp_floor=0)
    scope = {
        "robot": "historical-piper",
        "setup": "offline-review-example",
        "task": "three-objects",
    }
    trial = next(
        t["trial_id"] for t in evidence["trials"] if t["execution_status"] == "failed"
    )
    request = prepare(
        evidence,
        candidates["candidates"],
        trial_id=trial,
        scope=scope,
        numerical_only=True,
    )
    provider = DemoProvider()
    judgment = judge(request, provider)
    contract = {
        "schema": "roborsi-phase-contract-v1",
        "execution_authorized": False,
        "scope": scope,
        "program_sha256": digest(program),
        "phase": "synthetic_close_fixture",
        "max_observation_age_s": 1.0,
        "expected": {"grip_width_m": [0.012, 0.06]},
        "hard_limits": {"tracking_rad": [0, 0.15]},
    }
    now = time.time()
    observation = {
        "program_sha256": digest(program),
        "phase": contract["phase"],
        "revision": 1,
        "observed_at_s": now,
        "metrics": {"grip_width_m": 0.001, "tracking_rad": 0.01},
    }
    dataset = load_json(root / "examples/decision_dataset.synthetic.json")
    artifacts = {
        "evidence.json": evidence,
        "sweep.json": candidates,
        "scope.json": scope,
        "request.json": request,
        "reply.synthetic.json": provider.predict(request, timeout_s=5),
        "judgment.json": judgment,
        "contract.synthetic.json": contract,
        "observation.synthetic.json": observation,
        "checkpoint.synthetic.json": checkpoint(contract, observation, now=now),
        "calibration.synthetic.json": calibrate(dataset, min_accepted=2),
    }
    for c in candidates["candidates"]:
        artifacts[f"profile_{c['policy']['candidate_speed']}x.json"] = c
    args.output.mkdir(parents=True, exist_ok=False)
    for name, artifact in artifacts.items():
        write_json(args.output / name, artifact)
    page = args.output / "index.html"
    page.write_text(render(evidence, candidates, judgment), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(page),
                "provider": provider.name,
                "decision": judgment["decision"],
                "model_calls": 0,
                "fixture_note": "Checkpoint and calibration observations are synthetic; historical evidence remains separate.",
            }
        )
    )


if __name__ == "__main__":
    main()
