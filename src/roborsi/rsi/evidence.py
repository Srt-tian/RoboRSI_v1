"""Convert metrics into evidence-linked observations, never causal verdicts."""

import math

from .artifacts import digest, load_json, nonempty, seal, source_ref

SCHEMA = "roborsi-evidence-v1"


def diagnose(failure):
    """Rule-based triage. Hypotheses require a separate verification step."""
    failure = (failure or "").lower()
    if "gripper check failed" in failure:
        return {
            "observation": "gripper_guard_failed",
            "attribution": "unresolved",
            "hypotheses": [
                "contact or grasp geometry",
                "object moved",
                "guard or sensing mismatch",
            ],
            "next_checks": [
                "inspect contact images and measured width",
                "review pose and depth with fresh geometry",
            ],
            "do_not_infer": "A failed width guard alone does not establish an empty grasp or its cause.",
        }
    if "tcp" in failure and "floor" in failure:
        return {
            "observation": "tcp_floor_guard_failed",
            "attribution": "unresolved",
            "hypotheses": [
                "planned clearance",
                "tracking deviation",
                "frame or floor calibration",
            ],
            "next_checks": [
                "compare planned and measured TCP in the same frame",
                "verify calibration before revising the path",
            ],
            "do_not_infer": "Do not lower the floor to make the failure disappear.",
        }
    if any(x in failure for x in ("tracking", "watchdog", "stale", "queue")):
        return {
            "observation": "execution_guard_failed",
            "attribution": "unresolved",
            "hypotheses": [
                "transport or feedback timing",
                "motion tracking",
                "configuration mismatch",
            ],
            "next_checks": [
                "inspect command and feedback timing before blaming task planning"
            ],
            "do_not_infer": "A transport symptom is not proof of a bad grasp plan.",
        }
    return {
        "observation": "unclassified_failure" if failure else "no_failure_reported",
        "attribution": "unresolved",
        "hypotheses": [],
        "next_checks": [
            "obtain independent task outcome and inspect original evidence"
        ],
        "do_not_infer": "Program completion does not establish task success.",
    }


def analyze(metrics_path):
    rows = load_json(metrics_path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty metrics list required")
    trials, ids = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("metric record must be an object")
        trial_id = nonempty(row.get("log"), "trial ID")
        if trial_id in ids:
            raise ValueError(f"duplicate trial ID: {trial_id}")
        ids.add(trial_id)
        status = row.get("execution_status")
        if status not in {"complete", "failed", "interrupted", "unknown"}:
            raise ValueError("unsupported execution status")
        for field in ("elapsed_s", "command_rows", "feedback_rows"):
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"invalid {field}")
            if field.endswith("_rows") and not isinstance(value, int):
                raise ValueError(f"integer {field} required")
        # Canonicalization also rejects nonfinite values in optional fields.
        record_hash = digest(row)
        failure = row.get("failure")
        if failure is not None and not isinstance(failure, str):
            raise ValueError("failure must be text or null")
        if status == "complete" and failure:
            raise ValueError("complete execution conflicts with a failure reason")
        report = row.get("task_result")
        if report is not None:
            nonempty(report, "task result report")
        trials.append(
            {
                "trial_id": trial_id,
                "record_sha256": record_hash,
                "execution_status": status,
                "task_outcome": {
                    "status": "reported" if report else "unknown",
                    "report": report,
                },
                "metrics": row,
                "diagnosis": diagnose(failure),
            }
        )
    return seal(
        {
            "schema": SCHEMA,
            "execution_authorized": False,
            "source": source_ref(metrics_path),
            "trials": trials,
            "summary": {
                "trials": len(trials),
                "execution_complete": sum(
                    t["execution_status"] == "complete" for t in trials
                ),
                "execution_failed": sum(
                    t["execution_status"] == "failed" for t in trials
                ),
                "task_reports": sum(
                    t["task_outcome"]["status"] == "reported" for t in trials
                ),
                "task_success_rate": None,
            },
            "limitations": [
                "Metrics are reported summaries; raw-log integrity is checked separately.",
                "No automatic visual task evaluator or causal attribution is used.",
                "Missing task labels remain unknown; no aggregate success rate is computed.",
            ],
        }
    )
