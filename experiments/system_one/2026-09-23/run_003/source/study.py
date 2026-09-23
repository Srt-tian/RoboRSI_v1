"""Develop on validation, freeze the protocol, then open independent test sets."""

import argparse
import csv
import gzip
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.special import ndtr

from .network import DecisionNet, train
from .world import ACTIONS, FEATURES, costs, features, generate_contexts, simulate, times, unpaired_labels


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def model_input(x, contexts, variant):
    value = x.copy()
    if variant.startswith("no_delay"):
        for feature in ("look_delay", "probe_delay", "look_drift_over_tolerance", "probe_drift_over_tolerance"):
            value[:, FEATURES.index(feature)] = 0
    if variant.startswith("choice"):
        value = np.column_stack((value, [c.time_price for c in contexts]))
    return value


def select(model, x, contexts):
    if model.kind == "choice":
        pred = model.forward(x)
        return np.argmax(pred, axis=1), pred
    pred = model.success(x)
    return np.argmin(costs(pred, contexts), axis=1), pred


def measure(actions, context, reference):
    row = np.arange(len(actions))
    p = reference["success"][row, actions]
    loss = costs(reference["success"], context)[row, actions]
    rescue, spoil = np.zeros(len(actions)), np.zeros(len(actions))
    for action in (1, 2):
        chosen = actions == action
        rescue[chosen] = reference["paired"][chosen, 2*action-1]
        spoil[chosen] = reference["paired"][chosen, 2*action]
    return {"mean_cost": float(loss.mean()), "success_rate": float(p.mean()),
            "sense_rate": float((actions != 0).mean()),
            "mean_duration_s": float(times(context)[row, actions].mean()),
            "rescue_rate": float(rescue.mean()), "spoil_rate": float(spoil.mean()),
            "action_counts": {name: int((actions == i).sum()) for i, name in enumerate(ACTIONS)}}, loss


def rule_actions(contexts, threshold, multiplier):
    """A task-scaled uncertainty trigger with simple sensor/delay cost estimates."""
    x = features(contexts)
    tol = x[:, 3]
    prior_std = x[:, 12]*tol
    direct_std = np.sqrt(prior_std**2+(0.22*x[:, 4])**2+0.001**2)
    look_std = np.sqrt(x[:, 5]**2+(x[:, 4]*(0.22+x[:, 6]-0.04))**2+0.001**2)
    probe_std = np.sqrt(x[:, 8]**2+(x[:, 4]*(0.22+x[:, 9]-0.10))**2+x[:, 10]**2+0.001**2)
    direct = 2*ndtr(tol/direct_std)-1
    look = (1-x[:, 7])*(2*ndtr(tol/look_std)-1)+x[:, 7]*direct
    probe = (1-x[:, 11])*(2*ndtr(tol/probe_std)-1)
    price = np.asarray([c.time_price for c in contexts])[:, None]
    loss = 1-np.column_stack((direct, look, probe))+multiplier*price*times(contexts)
    action = np.argmin(loss, axis=1)
    return np.where(prior_std/tol < threshold, 0, action)


def _save_dataset(root, name, contexts, labels, seed, draws):
    with gzip.open(root/f"{name}.contexts.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"seed": seed, "draws": draws, "contexts": [c.to_dict() for c in contexts]}, f, allow_nan=False)
    np.savez_compressed(root/f"{name}.labels.npz", x=features(contexts), success=labels["success"], paired=labels["paired"], outcomes=labels["outcomes"])


def develop(root, *, train_count=6000, validation_count=1500, draws=128, epochs=140, seeds=(11, 22, 33)):
    root.mkdir(parents=True, exist_ok=False)
    (root/"models").mkdir()
    config = {"created_utc": utc(), "phase": "validation_only", "train_context_seed": 11001,
              "validation_context_seed": 22002, "train_branch_seed": 110019,
              "validation_branch_seed": 220029, "train_contexts": train_count,
              "validation_contexts": validation_count, "label_draws": draws,
              "epochs": epochs, "model_seeds": list(seeds), "feature_names": list(FEATURES),
              "python": platform.python_version(), "numpy": np.__version__,
              "git_base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_sha256": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    write_json(root/"config.json", config)
    training = generate_contexts(train_count, 11001)
    validation = generate_contexts(validation_count, 22002)
    y_train = simulate(training, draws, 110019)
    y_valid = simulate(validation, 256, 220029)
    _save_dataset(root, "train", training, y_train, 11001, draws)
    _save_dataset(root, "validation", validation, y_valid, 22002, 256)
    x_train, x_valid = features(training), features(validation)
    rule_trials = []
    for threshold in (0, 0.4, 0.7, 1.0, 1.4, 2.0):
        for multiplier in (0.5, 1.0, 1.5, 2.0):
            metrics, _ = measure(rule_actions(validation, threshold, multiplier), validation, y_valid)
            rule_trials.append({"threshold": threshold, "multiplier": multiplier, **metrics})
    rule = min(rule_trials, key=lambda r: r["mean_cost"])
    write_json(root/"rule_validation.json", rule_trials)
    variants = [("outcome64", "outcome", 64), ("paired64", "paired", 64),
                ("outcome128", "outcome", 128), ("paired128", "paired", 128),
                ("no_delay64", "paired", 64), ("unpaired64", "paired", 64),
                ("choice128", "choice", 128)]
    trials = []
    for variant, kind, width in variants:
        for seed in seeds:
            started = time.perf_counter()
            xt, xv = model_input(x_train, training, variant), model_input(x_valid, validation, variant)
            model = DecisionNet(xt.shape[1], width, kind=kind, seed=seed)
            if kind == "choice":
                labels = np.eye(3)[np.argmin(costs(y_train["success"], training), axis=1)]
            elif variant.startswith("unpaired"):
                labels = unpaired_labels(y_train["outcomes"])
            else:
                labels = y_train["paired" if kind == "paired" else "success"]
            tag = f"{variant}_seed{seed}"
            checkpoint = root/"models"/f"{tag}.npz"
            best, curve = {"cost": float("inf"), "epoch": 0}, []

            def callback(epoch, loss, current):
                if epoch != 1 and epoch % 5:
                    return
                selected, _ = select(current, xv, validation)
                metrics, _ = measure(selected, validation, y_valid)
                curve.append({"epoch": epoch, "train_loss": loss, **metrics})
                if metrics["mean_cost"] < best["cost"]:
                    best.update(cost=metrics["mean_cost"], epoch=epoch)
                    current.save(checkpoint)

            train(model, xt, labels, epochs=epochs, seed=seed+1000, callback=callback)
            trial = {"id": tag, "variant": variant, "kind": kind, "width": width,
                     "seed": seed, "parameters": sum(p.size for p in model.params.values()),
                     "best_validation_cost": best["cost"], "best_epoch": best["epoch"],
                     "training_wall_s": time.perf_counter()-started, "curve": curve,
                     "checkpoint": str(checkpoint.relative_to(root)), "checkpoint_sha256": digest(checkpoint)}
            trials.append(trial)
            write_json(root/"trials.json", trials)
            print(json.dumps({k: v for k, v in trial.items() if k != "curve"}), flush=True)
    average = {variant: float(np.mean([t["best_validation_cost"] for t in trials if t["variant"] == variant])) for variant, _, _ in variants}
    selected = [min(("outcome64", "outcome128"), key=average.get), min(("paired64", "paired128"), key=average.get), "no_delay64", "unpaired64", "choice128"]
    protocol = {"frozen_utc": utc(), "test_not_constructed_yet": True, "config_sha256": digest(root/"config.json"),
                "trials_sha256": digest(root/"trials.json"), "selection": selected,
                "validation_average_cost": average, "rule": {key: rule[key] for key in ("threshold", "multiplier")},
                "test_specification": [dict(name="iid", seed=33003, shift="iid"), dict(name="delay", seed=44004, shift="delay"), dict(name="cost", seed=55005, shift="cost")],
                "evaluation_draws": 512, "planner_draws": 128,
                "selection_rule": "best epoch per seed; mean validation cost across seeds selects width; all selected seeds reported"}
    write_json(root/"frozen_protocol.json", protocol)
    (root/"frozen_protocol.sha256").write_text(digest(root/"frozen_protocol.json")+"\n")
    print(json.dumps({"phase": "frozen", "variants": selected, "validation_cost": average}), flush=True)


def bootstrap_delta(first, second, *, seed=713, repeats=1500):
    delta = np.asarray(first)-np.asarray(second)
    rng = np.random.default_rng(seed)
    means = np.asarray([delta[rng.integers(0, len(delta), len(delta))].mean() for _ in range(repeats)])
    return {"mean": float(delta.mean()), "ci95": np.quantile(means, [0.025, 0.975]).tolist(), "resampling_unit": "context", "repeats": repeats}


def evaluate(root, *, test_count=1200):
    if (root/"test_started.json").exists():
        raise ValueError("test already opened: use a new study for another development cycle")
    protocol = json.loads((root/"frozen_protocol.json").read_text())
    if digest(root/"frozen_protocol.json") != (root/"frozen_protocol.sha256").read_text().strip():
        raise ValueError("protocol changed after freezing")
    if digest(root/"trials.json") != protocol["trials_sha256"] or digest(root/"config.json") != protocol["config_sha256"]:
        raise ValueError("development artifacts changed after freezing")
    trials = json.loads((root/"trials.json").read_text())
    selected_trials = [t for t in trials if t["variant"] in protocol["selection"]]
    models = []
    for trial in selected_trials:
        if digest(root/trial["checkpoint"]) != trial["checkpoint_sha256"]:
            raise ValueError("checkpoint changed after freezing")
        models.append((trial, DecisionNet.load(root/trial["checkpoint"])))
    write_json(root/"test_started.json", {"started_utc": utc(), "contexts_per_cohort": test_count, "protocol_sha256": digest(root/"frozen_protocol.json")})
    summaries, all_records, audits = [], [], []
    for spec in protocol["test_specification"]:
        contexts = generate_contexts(test_count, spec["seed"], shift=spec["shift"])
        x = features(contexts)
        ref = simulate(contexts, protocol["evaluation_draws"], spec["seed"]*10+9, details=True)
        _save_dataset(root, "test_"+spec["name"], contexts, ref, spec["seed"], protocol["evaluation_draws"])
        started = time.perf_counter()
        planner = simulate(contexts, protocol["planner_draws"], spec["seed"]*10+3)
        planner_time = (time.perf_counter()-started)*1000/len(contexts)
        choices = {"always_act": np.zeros(test_count, dtype=int), "always_look": np.ones(test_count, dtype=int),
                   "always_probe": np.full(test_count, 2),
                   "tuned_rule": rule_actions(contexts, **protocol["rule"]),
                   "known_model_mc": np.argmin(costs(planner["success"], contexts), axis=1)}
        predictions = {"known_model_mc": planner["success"]}
        joint_predictions = {}
        latency = {"known_model_mc": {"batched_ms_per_context": planner_time}}
        for trial, model in models:
            value = model_input(x, contexts, trial["variant"])
            key = trial["id"]
            choices[key], predictions[key] = select(model, value, contexts)
            durations = []
            for i in range(min(test_count, 256)):
                start = time.perf_counter_ns()
                model.forward(value[i:i+1])
                durations.append((time.perf_counter_ns()-start)/1e6)
            latency[key] = {"single_context_forward_ms_median": float(np.median(durations)), "single_context_forward_ms_p95": float(np.quantile(durations, 0.95)), "samples": len(durations)}
            if model.kind == "paired":
                joint_predictions[key] = model.rescue_spoil(value)
        losses, method_metrics = {}, {}
        for key, action in choices.items():
            method_metrics[key], losses[key] = measure(action, contexts, ref)
            method_metrics[key]["latency"] = latency.get(key)
            if key in predictions and not key.startswith("choice"):
                probability = predictions[key]
                truth = ref["success"]
                method_metrics[key]["probability_mse_vs_mc"] = float(np.mean((probability-truth)**2))
                method_metrics[key]["brier_over_branch_outcomes"] = float(np.mean((probability-truth)**2+truth*(1-truth)))
        variant_costs = {}
        variant_metrics = {}
        for variant in protocol["selection"]:
            keys = [t["id"] for t in selected_trials if t["variant"] == variant]
            variant_costs[variant] = np.mean([losses[k] for k in keys], axis=0)
            variant_metrics[variant] = {name: float(np.mean([method_metrics[k][name] for k in keys])) for name in ("mean_cost", "success_rate", "sense_rate", "mean_duration_s", "rescue_rate", "spoil_rate")}
            variant_metrics[variant]["training_seed_costs"] = [method_metrics[k]["mean_cost"] for k in keys]
        paired_name = next(v for v in protocol["selection"] if v.startswith("paired"))
        outcome_name = next(v for v in protocol["selection"] if v.startswith("outcome"))
        contrasts = {"paired_minus_outcome": bootstrap_delta(variant_costs[paired_name], variant_costs[outcome_name]),
                     "paired_minus_rule": bootstrap_delta(variant_costs[paired_name], losses["tuned_rule"]),
                     "paired_minus_known_model": bootstrap_delta(variant_costs[paired_name], losses["known_model_mc"]),
                     "no_delay_minus_paired": bootstrap_delta(variant_costs["no_delay64"], variant_costs[paired_name]),
                     "choice_minus_paired": bootstrap_delta(variant_costs["choice128"], variant_costs[paired_name])}
        summary = {"cohort": spec["name"], "contexts": test_count, "draws_per_context": protocol["evaluation_draws"],
                   "methods": method_metrics, "variant_means": variant_metrics, "paired_cost_differences": contrasts}
        summaries.append(summary)
        independent = unpaired_labels(ref["outcomes"])
        coupling = {"cohort": spec["name"], "success_marginals_unchanged": True,
                    "shared_noise_spoil": ref["paired"][:, [2, 4]].mean(axis=0).tolist(),
                    "independence_spoil": independent[:, [2, 4]].mean(axis=0).tolist(),
                    "warning": "Joint harm is coupling-dependent, not identifiable from success marginals alone."}
        audits.append(coupling)
        for i, c in enumerate(contexts):
            record = {"cohort": spec["name"], "index": i, "context": c.to_dict(),
                      "success_mc": ref["success"][i].tolist(), "paired_mc": ref["paired"][i].tolist(),
                      "choices": {k: int(a[i]) for k, a in choices.items()},
                      "predictions": {k: p[i].tolist() for k, p in predictions.items()},
                      "joint_predictions": {k: p[i].tolist() for k, p in joint_predictions.items()},
                      "replay": {"x0": float(ref["x0"][i, 0]), "velocity": float(ref["velocity"][i, 0]),
                                 "kick": float(ref["kick"][i, 0]), "damaged": bool(ref["damaged"][i, 0]),
                                 "look_dropped": bool(ref["dropped"][i, 0]),
                                 "actuator": float(ref["actuator"][i, 0]),
                                 "target": ref["target"][i, 0].tolist(), "actual": ref["actual"][i, 0].tolist(),
                                 "success": ref["outcomes"][i, 0].tolist(),
                                 "measurement": [None if not np.isfinite(v) else float(v) for v in ref["measurement"][i, 0]]}}
            all_records.append(record)
        print(json.dumps({"cohort": spec["name"], "variants": variant_metrics, "contrasts": contrasts}), flush=True)
    with gzip.open(root/"decisions.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(all_records, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    write_json(root/"results.json", {"completed_utc": utc(), "protocol_sha256": digest(root/"frozen_protocol.json"),
                                    "scope": "analytical probabilistic macro simulator; no language encoder or official Jev; no robot physics",
                                    "summaries": summaries, "coupling_audit": audits,
                                    "bootstrap_note": "CIs resample independent test contexts after averaging three trained seeds. They do not cover all training-distribution uncertainty."})
    with (root/"summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("cohort", "method", "cost", "success_rate", "sense_rate", "duration_s", "rescue_rate", "spoil_rate"))
        for summary in summaries:
            for key, value in summary["methods"].items():
                writer.writerow([summary["cohort"], key]+[value[k] for k in ("mean_cost", "success_rate", "sense_rate", "mean_duration_s", "rescue_rate", "spoil_rate")])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    develop_parser = sub.add_parser("develop")
    develop_parser.add_argument("--output", required=True, type=Path)
    develop_parser.add_argument("--train", type=int, default=6000)
    develop_parser.add_argument("--validation", type=int, default=1500)
    develop_parser.add_argument("--draws", type=int, default=128)
    develop_parser.add_argument("--epochs", type=int, default=140)
    test_parser = sub.add_parser("test")
    test_parser.add_argument("--output", required=True, type=Path)
    test_parser.add_argument("--contexts", type=int, default=1200)
    args = parser.parse_args()
    if args.command == "develop":
        develop(args.output, train_count=args.train, validation_count=args.validation, draws=args.draws, epochs=args.epochs)
    else:
        evaluate(args.output, test_count=args.contexts)


if __name__ == "__main__":
    main()
