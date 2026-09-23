"""Frozen-model screen of context-dependent, cancellable evidence requests.

A deadline is selected BEFORE a request. It is not a learned recurrent policy.
Arrival time is independent of latent object state conditional on the given queue
law. The simulator keeps advancing while evidence is pending. This experiment
does not launch processes, sensors, hardware, or real inference requests.
"""

import argparse
import gzip
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from .effect import EffectNet
from .network import DecisionNet
from .study import bootstrap_delta, digest, utc, write_json
from .world import features, generate_contexts, simulate

DEADLINES = np.asarray([0, .08, .14, .24, .40, .70, 1.0])
ARRIVALS = DEADLINES[1:]


def contexts_and_queue(count, seed, shift):
    contexts = generate_contexts(count, seed)
    rng = np.random.default_rng(seed+151)
    congestion = rng.uniform(.0, .7, count) if shift != "tail" else rng.uniform(.7, 1, count)
    if shift == "motion":
        contexts = [replace(c, velocity_std=float(rng.uniform(.048, .080))) for c in contexts]
    fast = np.asarray([.35, .35, .20, .07, .025, .005])
    slow = np.asarray([.02, .03, .08, .17, .30, .40])
    queue = (1-congestion[:, None])*fast+congestion[:, None]*slow
    return contexts, queue


def branch_bank(contexts, draws, seed, *, outcomes=False):
    """Look at each arrival time, or act from the prior after a timeout.

    Prior-only waiting is exactly represented under THIS ballistic model by
    scaling velocity_std by (0.22+wait)/0.22. Only macro 0 of that transformed
    world is used. Common random numbers retain the original latent trajectory.
    """
    look, prior, look_y, prior_y = [], [], [], []
    for delay in DEADLINES:
        seeing = [replace(c, look_delay=max(.06, float(delay))) for c in contexts]
        data = simulate(seeing, draws, seed)
        look.append(data["success"][:, 1])
        look_y.append(data["outcomes"][..., 1])
        waiting = [replace(c, velocity_std=c.velocity_std*(.22+delay)/.22) for c in contexts]
        data = simulate(waiting, draws, seed)
        prior.append(data["success"][:, 0])
        prior_y.append(data["outcomes"][..., 0])
    result = {"look": np.stack(look, axis=1), "prior": np.stack(prior, axis=1)}
    if outcomes:
        result.update(look_outcomes=np.stack(look_y, axis=1), prior_outcomes=np.stack(prior_y, axis=1))
    return result


def model_bank(contexts, trial, model):
    def predict(c):
        return model.success(features(c)) if trial["physical"] is None else model.predict(c)
    look, prior = [], []
    for delay in DEADLINES:
        look.append(predict([replace(c, look_delay=max(.06, float(delay))) for c in contexts])[:, 1])
        prior.append(predict([replace(c, velocity_std=c.velocity_std*(.22+delay)/.22) for c in contexts])[:, 0])
    return {"look": np.stack(look, axis=1), "prior": np.stack(prior, axis=1)}


def deadline_values(bank, contexts, queue):
    n = len(contexts)
    success, duration, cancellation = np.zeros((n, 7)), np.zeros((n, 7)), np.zeros((n, 7))
    for k, deadline in enumerate(DEADLINES):
        arrived = ARRIVALS <= deadline
        tail = queue[:, ~arrived].sum(axis=1)
        success[:, k] = (bank["look"][:, 1:][:, arrived]*queue[:, arrived]).sum(axis=1)+tail*bank["prior"][:, k]
        duration[:, k] = (queue[:, arrived]*(.22+ARRIVALS[arrived])).sum(axis=1)+tail*(.22+deadline)
        cancellation[:, k] = tail if k else 0
    cost = 1-success+np.asarray([c.time_price for c in contexts])[:, None]*duration
    return {"cost": cost, "success": success, "duration": duration, "cancellation": cancellation}


def main_run(root, source):
    root.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((source/"frozen_protocol.json").read_text())
    trials = [t for t in json.loads((source/"trials.json").read_text()) if t["variant"] in frozen["selection"]]
    models = []
    for trial in trials:
        path = source/trial["checkpoint"]
        if digest(path) != trial["checkpoint_sha256"]:
            raise ValueError("frozen checkpoint changed")
        models.append((trial, DecisionNet.load(path) if trial["physical"] is None else EffectNet.load(path, physical=trial["physical"])))
    config = {"created_utc": utc(), "source_study": str(source), "source_protocol_sha256": digest(source/"frozen_protocol.json"),
              "new_training_trials": 0, "reused_models": [{k: t[k] for k in ("id", "variant", "checkpoint", "checkpoint_sha256")} for t in trials],
              "deadlines_s": DEADLINES.tolist(), "arrival_times_s": ARRIVALS.tolist(),
              "validation_seed": 77002, "validation_contexts": 1000,
              "test_specification": [{"name": "iid_queue", "seed": 88003, "shift": "iid"},
                                     {"name": "tail_queue", "seed": 99004, "shift": "tail"},
                                     {"name": "fast_motion", "seed": 101005, "shift": "motion"}],
              "test_contexts_per_cohort": 1000, "evaluation_draws": 512, "planner_draws": 1024,
              "scope": "pre-request state-dependent timeout; no repeated observation or recurrent learned stopping",
              "source_sha256": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    write_json(root/"config.json", config)
    validation, qv = contexts_and_queue(1000, 77002, "iid")
    bv = branch_bank(validation, 512, 770029, outcomes=True)
    vv = deadline_values(bv, validation, qv)
    fixed = int(np.argmin(vv["cost"].mean(axis=0)))
    np.savez_compressed(root/"validation.npz", queue=qv, **bv)
    protocol = {"frozen_utc": utc(), "test_not_constructed_yet": True,
                "config_sha256": digest(root/"config.json"), "fixed_timeout_index": fixed,
                "validation_cost_by_timeout": vv["cost"].mean(axis=0).tolist(),
                "training_or_test_selection": "only fixed timeout tuned; all pretrained selected seeds evaluated"}
    write_json(root/"frozen_protocol.json", protocol)
    (root/"frozen_protocol.sha256").write_text(digest(root/"frozen_protocol.json")+"\n")
    summaries, records = [], []
    for spec in config["test_specification"]:
        contexts, queue = contexts_and_queue(1000, spec["seed"], spec["shift"])
        bank = branch_bank(contexts, 512, spec["seed"]*10+9, outcomes=True)
        truth = deadline_values(bank, contexts, queue)
        np.savez_compressed(root/f"test_{spec['name']}.npz", contexts=np.asarray([[*c.to_dict().values()] for c in contexts]), queue=queue, **bank)
        predicted_values = {}
        choices = {"always_act": np.zeros(1000, dtype=int), "always_wait": np.full(1000, 6), "fixed_timeout": np.full(1000, fixed)}
        for trial, model in models:
            pred = deadline_values(model_bank(contexts, trial, model), contexts, queue)
            name = trial["id"]
            choices[name] = pred["cost"].argmin(axis=1)
            predicted_values[name] = pred["cost"]
            if name.startswith("effect"):
                nc_name = "no_cancel_"+name
                choices[nc_name] = np.where(pred["cost"][:, 0] <= pred["cost"][:, -1], 0, 6)
                predicted_values[nc_name] = pred["cost"]
        planning = []
        for offset in range(0, 1000, 80):
            cp = contexts[offset:offset+80]
            bp = branch_bank(cp, 1024, spec["seed"]*100+offset)
            planning.append(deadline_values(bp, cp, queue[offset:offset+80])["cost"])
        predicted_values["known_model_mc1024"] = np.concatenate(planning)
        choices["known_model_mc1024"] = predicted_values["known_model_mc1024"].argmin(axis=1)
        methods, losses = {}, {}
        row = np.arange(1000)
        for name, action in choices.items():
            losses[name] = truth["cost"][row, action]
            methods[name] = {"mean_cost": float(losses[name].mean()), "success_rate": float(truth["success"][row, action].mean()),
                             "mean_duration_s": float(truth["duration"][row, action].mean()),
                             "request_rate": float((action > 0).mean()),
                             "cancellation_rate": float(truth["cancellation"][row, action].mean()),
                             "deadline_counts": [int((action == k).sum()) for k in range(7)]}
        groups, group_losses = {}, {}
        for prefix in (*frozen["selection"], "no_cancel_"+frozen["selection"][0]):
            keys = [k for k in methods if k.startswith(prefix+"_seed")]
            group_losses[prefix] = np.mean([losses[k] for k in keys], axis=0)
            groups[prefix] = {metric: float(np.mean([methods[k][metric] for k in keys])) for metric in ("mean_cost", "success_rate", "mean_duration_s", "request_rate", "cancellation_rate")}
            groups[prefix]["training_seed_costs"] = [methods[k]["mean_cost"] for k in keys]
        effect, raw, outcome = frozen["selection"]
        differences = {"effect_minus_fixed": bootstrap_delta(group_losses[effect], losses["fixed_timeout"]),
                       "effect_minus_no_cancel": bootstrap_delta(group_losses[effect], group_losses["no_cancel_"+effect]),
                       "effect_minus_raw": bootstrap_delta(group_losses[effect], group_losses[raw]),
                       "effect_minus_known_model": bootstrap_delta(group_losses[effect], losses["known_model_mc1024"])}
        summaries.append({"cohort": spec["name"], "contexts": 1000, "methods": methods, "variant_means": groups, "paired_cost_differences": differences})
        rng = np.random.default_rng(spec["seed"]*10+77)
        actual_arrivals = np.asarray([rng.choice(6, p=p) for p in queue])
        for i, c in enumerate(contexts):
            arrival_index = int(actual_arrivals[i])
            arrival_time = float(ARRIVALS[arrival_index])
            replays = {}
            for name, actions in choices.items():
                k = int(actions[i])
                received = k > 0 and arrival_time <= DEADLINES[k]
                wait = arrival_time if received else float(DEADLINES[k])
                hit = bool(bank["look_outcomes"][i, arrival_index+1, 0] if received else bank["prior_outcomes"][i, k, 0])
                event = "returned" if received else "cancelled" if k else "no_request"
                replays[name] = {"deadline_s": float(DEADLINES[k]), "arrival_s": arrival_time, "event": event,
                                 "grasp_time_s": .22+wait, "success": hit,
                                 "events": [[0, "request" if k else "act"], [wait, event], [.22+wait, "grasp_success" if hit else "grasp_failed"]]}
            records.append({"cohort": spec["name"], "index": i, "context": c.to_dict(), "queue": queue[i].tolist(),
                            "choices": {k: int(v[i]) for k, v in choices.items()}, "cost_mc": truth["cost"][i].tolist(),
                            "success_mc": truth["success"][i].tolist(), "predicted_cost": {k: v[i].tolist() for k, v in predicted_values.items()},
                            "replay": replays})
        print(json.dumps({"cohort": spec["name"], "variants": groups, "contrasts": differences}), flush=True)
    with gzip.open(root/"decisions.json.gz", "wt", encoding="utf-8") as f:
        json.dump(records, f, separators=(",", ":"), allow_nan=False)
    write_json(root/"results.json", {"completed_utc": utc(), "protocol_sha256": digest(root/"frozen_protocol.json"), "scope": config["scope"],
                                    "summaries": summaries, "known_limitations": ["Known queue law independent of latent state", "Ballistic 1D dynamics", "No real asynchronous worker", "Timeout selected before request", "MC expected cost integrates queue probabilities"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=Path("experiments/system_one/2026-09-23/run_002"))
    args = parser.parse_args()
    main_run(args.output, args.source)


if __name__ == "__main__":
    main()
