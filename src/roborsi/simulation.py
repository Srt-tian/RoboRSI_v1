"""Seeded kinematic tabletop sandbox for decision timing, not robot physics.

No model, robot driver, URDF, contact solver, or wall-clock control is used.
The same observation/repair rule is shared by all reactive policies; only timing
and revalidation differ. Semantic revisions use a privileged event detector.
"""

import argparse
import gzip
import json
import math
import random
from pathlib import Path

from .rsi.artifacts import digest, seal, source_ref, write_json
from .rsi.contracts import checkpoint, matches_current

METHODS = ("fixed_plan", "instant_rules", "delayed_unchecked", "delayed_checked")
SCENARIOS = (
    "nominal",
    "shift",
    "shift_during_wait",
    "occluded_shift",
    "slip",
    "tracking_fault",
)
DT = 0.005
BASKET = [0.20, 0.10]
PHASES = (
    "approach",
    "pregrasp",
    "await_decision",
    "repair_motion",
    "descend",
    "lift",
    "transfer",
    "release",
)
PROCESS_COLUMNS = (
    "time_s",
    "grip_x_m",
    "grip_y_m",
    "grip_z_m",
    "object_x_m",
    "object_y_m",
    "object_z_m",
    "target_x_m",
    "target_y_m",
    "closed",
    "attached",
    "semantic_revision",
    "phase_index",
    "pending_revision",
    "visible",
)


def _distance(a, b):
    return math.dist(a[:2], b[:2])


def run_episode(
    seed, scenario, method, *, decision_delay_s=0.35, trace=False, record_process=False
):
    if scenario not in SCENARIOS or method not in METHODS:
        raise ValueError("unknown scenario or method")
    if type(seed) is not int or not 0 <= seed < 1_000_000:
        raise ValueError("seed must be an integer in [0, 1000000)")
    if (
        isinstance(decision_delay_s, bool)
        or not math.isfinite(decision_delay_s)
        or not 0 <= decision_delay_s <= 2
    ):
        raise ValueError("decision delay must be in [0, 2] seconds")
    rng = random.Random(seed)
    obj = [-0.13 + rng.uniform(-0.025, 0.025), rng.uniform(-0.04, 0.04), 0.025]
    offset = [
        rng.choice((-1, 1)) * rng.uniform(0.025, 0.035),
        rng.uniform(-0.007, 0.007),
    ]
    late_offset = [0, rng.choice((-1, 1)) * rng.uniform(0.025, 0.035)]
    grip = [-0.25, -0.14, 0.20]
    target = list(obj[:2])
    revision = 0
    plan = digest(
        {"seed": seed, "initial_xy": target, "kind": "free_cartesian_gripper"}
    )
    phase, phase_start, origin = "approach", 0.0, grip[:]
    attached, closed, dropped, shifted, shifted_late = False, False, False, False, False
    pending = None
    requests = interventions = stale_discarded = stale_adopted = recoveries = 0
    events, frames, samples = [], [], []
    t, status = 0.0, "timeout"

    def record(kind, **values):
        events.append({"t": round(t, 4), "kind": kind, **values})

    def transition(next_phase):
        nonlocal phase, phase_start, origin
        phase, phase_start, origin = next_phase, t, grip[:]
        record("phase", phase=phase)

    def sample():
        if record_process:
            visible = not (scenario == "occluded_shift" and 0.45 <= t < 1.05)
            samples.append(
                [
                    t,
                    *grip,
                    *obj,
                    *target,
                    int(closed),
                    int(attached),
                    revision,
                    PHASES.index(phase),
                    pending["event"]["revision"] if pending else -1,
                    int(visible),
                ]
            )

    def observation():
        # Counter-based sensor noise: all methods see the same noise at a given
        # world time. Controller call count cannot change the disturbance stream.
        sensor = random.Random(seed * 100_003 + round(t / 0.05))
        visible = not (scenario == "occluded_shift" and 0.45 <= t < 1.05)
        position = (
            [obj[i] + sensor.uniform(-0.001, 0.001) for i in (0, 1)]
            if visible
            else None
        )
        return position

    def event(position):
        metrics = {"tracking_m": 0.0}
        if position is not None:
            metrics["target_error_m"] = _distance(target, position)
        contract = {
            "schema": "roborsi-phase-contract-v1",
            "execution_authorized": False,
            "scope": {
                "robot": "virtual-cartesian-gripper",
                "setup": "kinematic-v1",
                "task": "pick-place",
            },
            "program_sha256": plan,
            "phase": "pregrasp",
            "expected": {"target_error_m": [0, 0.008]},
            "hard_limits": {"tracking_m": [0, 0.03]},
            "max_observation_age_s": 1.0,
        }
        observed = {
            "program_sha256": plan,
            "phase": "pregrasp",
            "revision": revision,
            "observed_at_s": t,
            "metrics": metrics,
        }
        return checkpoint(contract, observed, now=t)

    def move(destination, duration):
        u = min(1.0, (t - phase_start) / duration)
        blend = u * u * (3 - 2 * u)
        grip[:] = [a + blend * (b - a) for a, b in zip(origin, destination)]
        return u >= 1.0 - 1e-9

    for tick in range(1601):
        t = tick * DT
        if (
            scenario in {"shift", "shift_during_wait", "occluded_shift"}
            and t >= 0.45
            and not shifted
        ):
            obj[0] += offset[0]
            obj[1] += offset[1]
            revision += 1
            shifted = True
            record("world_shift", revision=revision)
        if scenario == "shift_during_wait" and t >= 0.70 and not shifted_late:
            obj[0] += late_offset[0]
            obj[1] += late_offset[1]
            revision += 1
            shifted_late = True
            record("world_shift", revision=revision)
        # All baselines have the same deterministic protection, including the
        # fixed-plan baseline. No policy can ignore the injected hard fault.
        if scenario == "tracking_fault" and t >= 0.50:
            status = "protection_stop"
            record("protection_stop")
            sample()
            break
        if phase == "approach":
            if move([*target, 0.08], 0.60):
                transition("pregrasp")
        elif phase == "pregrasp" and tick % 10 == 0:
            if method == "fixed_plan":
                transition("descend")
            else:
                position = observation()
                current = event(position)
                record(
                    "checkpoint",
                    route=current["route"],
                    metrics=current["metrics"],
                    revision=revision,
                )
                if current["route"] == "collect_evidence":
                    if not events or events[-1]["kind"] != "wait_for_observation":
                        record("wait_for_observation")
                elif current["route"] == "continue":
                    transition("descend")
                elif current["route"] == "request_judgment":
                    if requests >= 3:
                        status = "repair_budget_exhausted"
                        sample()
                        break
                    # Analytic proposer, not Jev. Bounded candidate generation
                    # and selection use only observed (noisy) xy, never labels.
                    if _distance(target, position) > 0.08 or any(
                        abs(x) > 0.35 for x in position
                    ):
                        status = "candidate_out_of_bounds"
                        sample()
                        break
                    requests += 1
                    delay = 0 if method == "instant_rules" else decision_delay_s
                    pending = {"event": current, "xy": position, "due": t + delay}
                    record("request", revision=revision, due=round(t + delay, 4))
                    transition("await_decision")
                else:
                    status = "contract_rejected"
                    sample()
                    break
        elif phase == "await_decision":
            if t + 1e-9 >= pending["due"]:
                current = event(observation())
                valid = matches_current(pending["event"], current, t)
                if method != "delayed_unchecked" and not valid:
                    stale_discarded += 1
                    record(
                        "discard_stale",
                        requested_revision=pending["event"]["revision"],
                        current_revision=revision,
                    )
                    pending = None
                    transition("pregrasp")
                else:
                    stale_adopted += int(not valid)
                    target = list(pending["xy"])
                    interventions += 1
                    plan = digest(
                        {"previous": plan, "target": target, "repair": interventions}
                    )
                    record("apply_repair", stale=not valid, target=target)
                    pending = None
                    transition("repair_motion")
        elif phase == "repair_motion":
            if move([*target, 0.08], 0.20):
                # The unchecked ablation commits descent with its stale reply.
                transition("descend" if method == "delayed_unchecked" else "pregrasp")
        elif phase == "descend":
            if move([*target, 0.025], 0.25):
                closed = True
                # Contact proxy only: fixed elliptical capture region, no
                # friction or deformation model, no arm reach/collision model.
                attached = ((grip[0] - obj[0]) / 0.012) ** 2 + (
                    (grip[1] - obj[1]) / 0.008
                ) ** 2 <= 1
                record("close", captured=attached)
                transition("lift")
        elif phase == "lift":
            done = move([*target, 0.18], 0.35)
            if (
                scenario == "slip"
                and attached
                and not dropped
                and t - phase_start >= 0.18
            ):
                attached = False
                dropped = True
                obj[:] = [grip[0] + 0.006, grip[1], 0.025]
                revision += 1
                record("injected_slip")
            if done:
                if not attached and method != "fixed_plan" and recoveries < 1:
                    position = observation()
                    if position is not None:
                        recoveries += 1
                        closed = False
                        target = position
                        plan = digest(
                            {"previous": plan, "recovery": recoveries, "target": target}
                        )
                        record("recovery_replan", target=target)
                        transition("approach")
                    else:
                        status = "missing_recovery_observation"
                        sample()
                        break
                else:
                    transition("transfer")
        elif phase == "transfer":
            if move([*BASKET, 0.18], 0.65):
                transition("release")
        elif phase == "release":
            if move([*BASKET, 0.055], 0.25):
                if attached:
                    obj[:] = [*grip[:2], 0.025]
                attached, closed = False, False
                status = (
                    "success"
                    if abs(obj[0] - BASKET[0]) <= 0.04
                    and abs(obj[1] - BASKET[1]) <= 0.035
                    else "missed_basket"
                )
                record("terminal", status=status)
                sample()
                if trace:
                    frames.append(
                        {
                            "t": round(t, 4),
                            "phase": phase,
                            "grip": grip[:],
                            "object": obj[:],
                            "closed": closed,
                        }
                    )
                break
        if attached:
            obj[:] = [grip[0], grip[1], max(0.025, grip[2] - 0.015)]
        sample()
        if trace and tick % 10 == 0:
            frames.append(
                {
                    "t": round(t, 4),
                    "phase": phase,
                    "grip": grip[:],
                    "object": obj[:],
                    "closed": closed,
                }
            )
    return {
        "episode_id": f"seed_{seed:04d}__{scenario}__{method}",
        "seed": seed,
        "scenario": scenario,
        "method": method,
        "status": status,
        "success": status == "success",
        "simulated_duration_s": round(t, 4),
        "simulated_control_ticks": tick + 1,
        "analytic_requests": requests,
        "local_repairs": interventions,
        "stale_discarded": stale_discarded,
        "stale_adopted": stale_adopted,
        "recovery_replans": recoveries,
        "events": events,
        "frames": frames,
        "real_model_calls": 0,
        "process": samples,
    }


def benchmark(*, seeds=24, start_seed=0, decision_delay_s=0.35, process_sink=None):
    if type(seeds) is not int or not 1 <= seeds <= 1000:
        raise ValueError("seeds must be an integer in [1, 1000]")
    episodes = []
    sample_count = 0
    for seed in range(start_seed, start_seed + seeds):
        for scenario in SCENARIOS:
            for method in METHODS:
                episode = run_episode(
                    seed,
                    scenario,
                    method,
                    decision_delay_s=decision_delay_s,
                    trace=seed == start_seed,
                    record_process=process_sink is not None,
                )
                samples = episode.pop("process")
                sample_count += len(samples)
                if process_sink is not None:
                    process_sink(
                        {
                            "episode_id": episode["episode_id"],
                            "columns": PROCESS_COLUMNS,
                            "phases": PHASES,
                            "samples": samples,
                        }
                    )
                episodes.append(episode)
    summaries = []
    for scenario in (*SCENARIOS, "all"):
        for method in METHODS:
            rows = [
                r
                for r in episodes
                if r["method"] == method
                and (scenario == "all" or r["scenario"] == scenario)
            ]
            summaries.append(
                {
                    "scenario": scenario,
                    "method": method,
                    "episodes": len(rows),
                    "successes": sum(r["success"] for r in rows),
                    "mean_simulated_duration_s": sum(
                        r["simulated_duration_s"] for r in rows
                    )
                    / len(rows),
                    "analytic_requests": sum(r["analytic_requests"] for r in rows),
                    "stale_discarded": sum(r["stale_discarded"] for r in rows),
                    "stale_adopted": sum(r["stale_adopted"] for r in rows),
                }
            )
    return seal(
        {
            "schema": "roborsi-kinematic-benchmark-v1",
            "execution_authorized": False,
            "config": {
                "seeds": seeds,
                "start_seed": start_seed,
                "decision_delay_s": decision_delay_s,
                "simulation_dt_s": DT,
                "trace_dt_s": 10 * DT,
                "scenarios": SCENARIOS,
                "methods": METHODS,
            },
            "implementation": [
                source_ref(__file__),
                source_ref(Path(__file__).parent / "rsi/contracts.py"),
            ],
            "process_log": {
                "recorded": process_sink is not None,
                "samples": sample_count,
                "columns": PROCESS_COLUMNS,
                "phases": PHASES,
                "sampling_hz": 1 / DT,
            },
            "limitations": [
                "Kinematic contact proxy; not Piper dynamics or a validated physical simulator.",
                "Analytic proposals with injected delay, no GPT/Jev/VLM inference or learned RSI.",
                "Privileged semantic revision detector and simplified visibility/grasp observations.",
                "Seed variation covers small position/noise changes; not independent real-world trials.",
                "200 Hz is virtual simulation sampling; no measured host scheduling guarantee.",
            ],
            "summaries": summaries,
            "episodes": episodes,
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--decision-delay", type=float, default=0.35)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new iteration path")
    from .simulation_report import render_simulation

    args.output.mkdir(parents=True, exist_ok=False)
    with gzip.open(args.output / "process.jsonl.gz", "wt", encoding="utf-8") as log:
        result = benchmark(
            seeds=args.seeds,
            start_seed=args.start_seed,
            decision_delay_s=args.decision_delay,
            process_sink=lambda row: log.write(
                json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
            ),
        )
    write_json(args.output / "benchmark.json", result)
    (args.output / "index.html").write_text(render_simulation(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(args.output / "index.html"),
                "episodes": len(result["episodes"]),
                "summary": [s for s in result["summaries"] if s["scenario"] == "all"],
            }
        )
    )


if __name__ == "__main__":
    main()
