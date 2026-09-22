"""Episode-disjoint selective-decision evaluation; no training or success labels."""

import math

from .artifacts import digest, nonempty, seal
from .judgment import distribution, number


def _choice(row):
    ordered = sorted(row["probabilities"].items(), key=lambda x: (-x[1], x[0]))
    return ordered[0][0], ordered[0][1], ordered[0][1] - ordered[1][1]


def _accepted(rows, threshold, margin):
    if threshold is None:
        return []
    accepted = []
    for row in rows:
        choice, probability, gap = _choice(row)
        if choice != "abstain" and probability >= threshold and gap >= margin:
            accepted.append(row)
    return accepted


def _metrics(rows, threshold, margin):
    selected = _accepted(rows, threshold, margin)
    errors = sum(_choice(r)[0] != r["label"] for r in selected)
    bins = []
    for i in range(10):
        members = [r for r in rows if min(int(_choice(r)[1] * 10), 9) == i]
        bins.append(
            {
                "lower": i / 10,
                "upper": (i + 1) / 10,
                "count": len(members),
                "mean_probability": sum(_choice(r)[1] for r in members) / len(members)
                if members
                else None,
                "accuracy": sum(_choice(r)[0] == r["label"] for r in members)
                / len(members)
                if members
                else None,
            }
        )
    return {
        "count": len(rows),
        "groups": len({r["group_id"] for r in rows}),
        "accuracy": sum(_choice(r)[0] == r["label"] for r in rows) / len(rows),
        "brier": sum(
            sum(
                (p - float(k == r["label"])) ** 2 for k, p in r["probabilities"].items()
            )
            for r in rows
        )
        / len(rows),
        "nll_clipped_1e_15": sum(
            -math.log(max(1e-15, r["probabilities"][r["label"]])) for r in rows
        )
        / len(rows),
        "ece_10_bins": sum(
            b["count"] * abs(b["mean_probability"] - b["accuracy"])
            for b in bins
            if b["count"]
        )
        / len(rows),
        "reliability_bins": bins,
        "accepted": len(selected),
        "coverage": len(selected) / len(rows),
        "accepted_errors": errors,
        "selective_error": errors / len(selected) if selected else None,
    }


def calibrate(dataset, *, max_validation_error=0.1, min_accepted=10, min_margin=0.15):
    if dataset.get("schema") != "roborsi-decision-dataset-v1":
        raise ValueError("decision dataset schema required")
    if dataset.get("source_kind") not in {"synthetic", "annotated_observations"}:
        raise ValueError("explicit label source kind required")
    for field in ("model", "question_family", "label_provenance"):
        nonempty(dataset.get(field), field)
    number(max_validation_error, "max_validation_error")
    number(min_margin, "min_margin")
    if type(min_accepted) is not int or min_accepted < 1:
        raise ValueError("positive min_accepted required")
    splits, groups, cases = {"validation": [], "test": []}, {}, set()
    for row in dataset["records"]:
        case = nonempty(row["case_id"], "case_id")
        group = nonempty(row["group_id"], "group_id")
        split = row["split"]
        if case in cases or split not in splits:
            raise ValueError("unique cases and validation/test splits required")
        cases.add(case)
        if group in groups and groups[group] != split:
            raise ValueError("episode/group leakage between validation and test")
        groups[group] = split
        probs = row["probabilities"]
        if not isinstance(probs, dict) or not 2 <= len(probs) <= 255:
            raise ValueError("2 to 255 options required")
        for key in probs:
            nonempty(key, "option")
        distribution(probs, probs)
        if row["label"] not in probs:
            raise ValueError("label must be a declared option")
        splits[split].append(row)
    if not all(splits.values()):
        raise ValueError("both validation and held-out test records required")
    # Threshold selection sees only validation labels; test labels enter only
    # the final report. This is empirical selection, NOT a finite-sample bound.
    operating_points = []
    for threshold in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0):
        rows = _accepted(splits["validation"], threshold, min_margin)
        risk = (
            sum(_choice(r)[0] != r["label"] for r in rows) / len(rows) if rows else None
        )
        operating_points.append(
            {
                "threshold": threshold,
                "accepted": len(rows),
                "empirical_error": risk,
                "eligible": len(rows) >= min_accepted and risk <= max_validation_error,
            }
        )
    eligible = [p for p in operating_points if p["eligible"]]
    best = (
        min(eligible, key=lambda p: (-p["accepted"], p["threshold"]))
        if eligible
        else None
    )
    threshold = best["threshold"] if best else None
    return seal(
        {
            "schema": "roborsi-calibration-v1",
            "execution_authorized": False,
            "dataset_sha256": digest(dataset),
            "model": dataset["model"],
            "question_family": dataset["question_family"],
            "source_kind": dataset["source_kind"],
            "label_provenance": dataset["label_provenance"],
            "policy": {
                "max_validation_error": max_validation_error,
                "min_accepted": min_accepted,
                "min_margin": min_margin,
            },
            "selected_threshold": threshold,
            "operating_points": operating_points,
            "validation": _metrics(splits["validation"], threshold, min_margin),
            "test": _metrics(splits["test"], threshold, min_margin),
            "claim": "Empirical held-out decision evaluation; no robot-success calibration or statistical risk guarantee. No threshold is installed automatically.",
        }
    )
