"""Second hypothesis screen: learn an execution-time evidence response surface."""

import argparse
import gzip
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from .effect import EFFECT_FEATURES, EffectNet, effect_features
from .network import DecisionNet, train
from .study import bootstrap_delta, digest, measure, select, utc, write_json
from .world import costs, features, generate_contexts, simulate


def develop(root, first_study, *, epochs=140):
    root.mkdir(parents=True, exist_ok=False)
    (root/"models").mkdir()
    config = {"created_utc": utc(), "predecessor": str(first_study), "train_context_seed": 61001,
              "validation_context_seed": 62002, "train_branch_seed": 610019,
              "validation_branch_seed": 620029, "train_contexts": 6000,
              "validation_contexts": 1500, "training_draws": 128, "epochs": epochs,
              "model_seeds": [11, 22, 33], "features": list(EFFECT_FEATURES),
              "motivation": "Round 1 found no significant paired-head benefit; test execution-time/task-tolerance representation on new holdouts.",
              "source_sha256": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    write_json(root/"config.json", config)
    training, validation = generate_contexts(6000, 61001), generate_contexts(1500, 62002)
    train_ref, valid_ref = simulate(training, 128, 610019), simulate(validation, 512, 620029)
    np.savez_compressed(root/"training.npz", contexts=np.asarray([[*c.to_dict().values()] for c in training]), outcomes=train_ref["outcomes"], success=train_ref["success"])
    np.savez_compressed(root/"validation.npz", contexts=np.asarray([[*c.to_dict().values()] for c in validation]), outcomes=valid_ref["outcomes"], success=valid_ref["success"])
    trials = []
    variants = [("effect32", True, 32), ("effect64", True, 64), ("effect128", True, 128),
                ("raw_candidate64", False, 64), ("raw_candidate128", False, 128),
                ("outcome64", None, 64), ("outcome128", None, 128)]
    for variant, physical, width in variants:
        for seed in config["model_seeds"]:
            start = time.perf_counter()
            if physical is None:
                model = DecisionNet(18, width, seed=seed)
                xt, xv = features(training), features(validation)
                target = train_ref["success"]
                network = model
                predict = lambda: model.success(xv)
            else:
                model = EffectNet(width, seed, physical=physical)
                xt = effect_features(training, physical=physical).reshape(-1, 13)
                xv = effect_features(validation, physical=physical).reshape(-1, 13)
                target = train_ref["success"].reshape(-1, 1)
                network = model.network
                predict = lambda: network.forward(xv).reshape(-1, 3)
            tag = f"{variant}_seed{seed}"
            path = root/"models"/f"{tag}.npz"
            best, curve = {"cost": float("inf")}, []

            def callback(epoch, loss, current):
                if epoch != 1 and epoch % 5:
                    return
                action = np.argmin(costs(predict(), validation), axis=1)
                metrics, _ = measure(action, validation, valid_ref)
                curve.append({"epoch": epoch, "train_loss": loss, **metrics})
                if metrics["mean_cost"] < best["cost"]:
                    best.update(cost=metrics["mean_cost"], epoch=epoch)
                    current.save(path)

            train(network, xt, target, epochs=epochs, seed=1000+seed, callback=callback)
            row = {"id": tag, "variant": variant, "physical": physical, "width": width, "seed": seed,
                   "parameters": sum(p.size for p in network.params.values()), "best_validation_cost": best["cost"],
                   "best_epoch": best["epoch"], "curve": curve, "training_wall_s": time.perf_counter()-start,
                   "checkpoint": str(path.relative_to(root)), "checkpoint_sha256": digest(path)}
            trials.append(row)
            write_json(root/"trials.json", trials)
            print(json.dumps({k: v for k, v in row.items() if k != "curve"}), flush=True)
    mean = {v: float(np.mean([t["best_validation_cost"] for t in trials if t["variant"] == v])) for v, _, _ in variants}
    selected = [min(("effect32", "effect64", "effect128"), key=mean.get),
                min(("raw_candidate64", "raw_candidate128"), key=mean.get),
                min(("outcome64", "outcome128"), key=mean.get)]
    protocol = {"frozen_utc": utc(), "test_not_constructed_yet": True,
                "config_sha256": digest(root/"config.json"), "trials_sha256": digest(root/"trials.json"),
                "selection": selected, "validation_average_cost": mean, "test_contexts": 1200,
                "test_specification": [{"name": "iid", "seed": 63003, "shift": "iid"},
                                       {"name": "delay", "seed": 64004, "shift": "delay"},
                                       {"name": "cost", "seed": 65005, "shift": "cost"}],
                "evaluation_draws": 512, "known_model_draws": [128, 2048],
                "profile_seed": 66006, "profile_contexts": 40,
                "profile_delays": np.linspace(.06, 1.0, 32).tolist(),
                "comparison": "Matched training data and seed count. Shared heads receive 3x rows, 1/3 outputs; wall time is reported."}
    write_json(root/"frozen_protocol.json", protocol)
    (root/"frozen_protocol.sha256").write_text(digest(root/"frozen_protocol.json")+"\n")
    print(json.dumps({"phase": "frozen", "selected": selected, "validation_cost": mean}), flush=True)


def _predict(trial, model, contexts):
    return model.success(features(contexts)) if trial["physical"] is None else model.predict(contexts)


def evaluate(root):
    if (root/"test_started.json").exists():
        raise ValueError("test already opened")
    protocol = json.loads((root/"frozen_protocol.json").read_text())
    for file, checksum in (("frozen_protocol.json", (root/"frozen_protocol.sha256").read_text().strip()),
                           ("config.json", protocol["config_sha256"]), ("trials.json", protocol["trials_sha256"])):
        if digest(root/file) != checksum:
            raise ValueError("frozen artifact changed")
    trials = [t for t in json.loads((root/"trials.json").read_text()) if t["variant"] in protocol["selection"]]
    models = []
    for trial in trials:
        path = root/trial["checkpoint"]
        if digest(path) != trial["checkpoint_sha256"]:
            raise ValueError("checkpoint changed")
        model = DecisionNet.load(path) if trial["physical"] is None else EffectNet.load(path, physical=trial["physical"])
        models.append((trial, model))
    write_json(root/"test_started.json", {"started_utc": utc(), "protocol_sha256": digest(root/"frozen_protocol.json")})
    summaries, records = [], []
    for spec in protocol["test_specification"]:
        contexts = generate_contexts(protocol["test_contexts"], spec["seed"], shift=spec["shift"])
        ref = simulate(contexts, 512, spec["seed"]*10+9, details=True)
        np.savez_compressed(root/f"test_{spec['name']}.npz", contexts=np.asarray([[*c.to_dict().values()] for c in contexts]), outcomes=ref["outcomes"], success=ref["success"], paired=ref["paired"])
        predictions = {trial["id"]: _predict(trial, model, contexts) for trial, model in models}
        choices = {name: np.argmin(costs(p, contexts), axis=1) for name, p in predictions.items()}
        for draw_count in protocol["known_model_draws"]:
            probs = []
            for offset in range(0, len(contexts), 80):
                branch = simulate(contexts[offset:offset+80], draw_count, spec["seed"]*100+draw_count+offset)
                probs.append(branch["success"])
            key = f"known_model_mc{draw_count}"
            predictions[key] = np.concatenate(probs)
            choices[key] = np.argmin(costs(predictions[key], contexts), axis=1)
        choices.update(always_act=np.zeros(len(contexts), dtype=int), always_look=np.ones(len(contexts), dtype=int), always_probe=np.full(len(contexts), 2))
        method_metrics, losses = {}, {}
        for name, action in choices.items():
            method_metrics[name], losses[name] = measure(action, contexts, ref)
            if name in predictions:
                method_metrics[name]["probability_mse_vs_mc"] = float(np.mean((predictions[name]-ref["success"])**2))
        means, variant_cost = {}, {}
        for variant in protocol["selection"]:
            keys = [t["id"] for t in trials if t["variant"] == variant]
            variant_cost[variant] = np.mean([losses[k] for k in keys], axis=0)
            means[variant] = {name: float(np.mean([method_metrics[k][name] for k in keys])) for name in ("mean_cost", "success_rate", "sense_rate", "mean_duration_s", "rescue_rate", "spoil_rate")}
            means[variant]["training_seed_costs"] = [method_metrics[k]["mean_cost"] for k in keys]
        effect, raw, outcome = protocol["selection"]
        contrasts = {"effect_minus_outcome": bootstrap_delta(variant_cost[effect], variant_cost[outcome]),
                     "effect_minus_raw_candidate": bootstrap_delta(variant_cost[effect], variant_cost[raw]),
                     "effect_minus_mc2048": bootstrap_delta(variant_cost[effect], losses["known_model_mc2048"])}
        summaries.append({"cohort": spec["name"], "contexts": len(contexts), "draws_per_context": 512,
                          "methods": method_metrics, "variant_means": means, "paired_cost_differences": contrasts})
        for i, c in enumerate(contexts):
            records.append({"cohort": spec["name"], "index": i, "context": c.to_dict(),
                            "choices": {k: int(a[i]) for k, a in choices.items()}, "predictions": {k: p[i].tolist() for k, p in predictions.items()},
                            "success_mc": ref["success"][i].tolist(), "paired_mc": ref["paired"][i].tolist(), "joint_predictions": {},
                            "replay": {"x0": float(ref["x0"][i, 0]), "velocity": float(ref["velocity"][i, 0]),
                                       "kick": float(ref["kick"][i, 0]), "damaged": bool(ref["damaged"][i, 0]),
                                       "look_dropped": bool(ref["dropped"][i, 0]), "actuator": float(ref["actuator"][i, 0]),
                                       "target": ref["target"][i, 0].tolist(), "actual": ref["actual"][i, 0].tolist(),
                                       "success": ref["outcomes"][i, 0].tolist(),
                                       "measurement": [None if not np.isfinite(v) else float(v) for v in ref["measurement"][i, 0]]}})
        print(json.dumps({"cohort": spec["name"], "variants": means, "contrasts": contrasts}), flush=True)
    profiles = []
    for index, c in enumerate(generate_contexts(protocol["profile_contexts"], protocol["profile_seed"])):
        contexts = [replace(c, look_delay=d) for d in protocol["profile_delays"]]
        truth = simulate(contexts, 2048, protocol["profile_seed"]+index*19)
        profile_predictions = {t["id"]: _predict(t, m, contexts).tolist() for t, m in models}
        profiles.append({"index": index, "context": c.to_dict(), "delays": protocol["profile_delays"],
                         "success_mc": truth["success"].tolist(), "predictions": profile_predictions,
                         "paired_mc": truth["paired"].tolist()})
    write_json(root/"profiles.json", profiles)
    with gzip.open(root/"decisions.json.gz", "wt", encoding="utf-8") as f:
        json.dump(records, f, separators=(",", ":"), allow_nan=False)
    write_json(root/"results.json", {"completed_utc": utc(), "scope": "analytic grasp micro-simulator, not physics, language or official Jev",
                                    "protocol_sha256": digest(root/"frozen_protocol.json"), "summaries": summaries,
                                    "bootstrap_note": "Independent contexts; three seeds averaged before resampling. Profiles are a separate diagnostic population.",
                                    "coupling_audit": []})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("develop", "test"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-study", type=Path, default=Path("experiments/system_one/2026-09-23/run_001"))
    args = parser.parse_args()
    if args.command == "develop":
        develop(args.output, args.first_study)
    else:
        evaluate(args.output)


if __name__ == "__main__":
    main()
