"""Explicit review records and exact-scope planning context, without execution."""

from .artifacts import nonempty, seal, verify
from .evaluation import SCHEMA as COMPARISON_SCHEMA
from .evidence import SCHEMA as EVIDENCE_SCHEMA

SCHEMA = "roborsi-review-v1"


def validate_scope(scope):
    if not isinstance(scope, dict) or set(scope) != {"robot", "setup", "task"}:
        raise ValueError("scope must contain exactly robot, setup, task")
    for key, value in scope.items():
        nonempty(value, key)
        if value.strip() == "*":
            raise ValueError("wildcard scopes are unsupported")


def review(
    evidence, comparison, *, trial_id, scope, lesson, reviewer, decision, judgment=None
):
    verify(evidence, EVIDENCE_SCHEMA)
    verify(comparison, COMPARISON_SCHEMA)
    validate_scope(scope)
    nonempty(lesson, "lesson")
    nonempty(reviewer, "reviewer")
    if decision not in {"accept_for_planning", "reject"}:
        raise ValueError("explicit review decision required")
    trials = [t for t in evidence["trials"] if t["trial_id"] == trial_id]
    if len(trials) != 1:
        raise ValueError("trial ID must identify one evidence record")
    if (
        decision == "accept_for_planning"
        and comparison["status"] != "offline_validated"
    ):
        raise ValueError("rejected comparison cannot enter planning memory")
    if judgment is not None:
        verify(judgment, "roborsi-judgment-v1")
        if (
            judgment["evidence_sha256"] != evidence["artifact_sha256"]
            or judgment["scope"] != scope
            or judgment["trial_id"] != trial_id
        ):
            raise ValueError("judgment evidence, scope or trial mismatch")
        if (
            judgment["decision"] != "review_candidate"
            or judgment["selected_comparison_sha256"] != comparison["artifact_sha256"]
        ):
            raise ValueError("judgment does not select this comparison")
    return seal(
        {
            "schema": SCHEMA,
            "execution_authorized": False,
            "decision": decision,
            "scope": scope,
            "lesson": lesson,
            "reviewer": reviewer,
            "evidence_sha256": evidence["artifact_sha256"],
            "trial": trials[0],
            "comparison": comparison,
            "judgment": judgment,
            "association": "reviewer-declared; not a causal or matched-trial validation",
            "evidence_level": "offline_only; physical effectiveness unverified",
        }
    )


def select_context(records, scope):
    validate_scope(scope)
    selected, excluded, seen = [], [], set()
    for record in records:
        verify(record, SCHEMA)
        verify(record["comparison"], COMPARISON_SCHEMA)
        validate_scope(record["scope"])
        identity = record["artifact_sha256"]
        if identity in seen:
            continue
        seen.add(identity)
        reason = None
        if record["decision"] != "accept_for_planning":
            reason = "not_accepted"
        elif record["scope"] != scope:
            reason = "scope_mismatch"
        elif record["comparison"]["status"] != "offline_validated":
            reason = "comparison_not_validated"
        if reason:
            excluded.append({"review_sha256": identity, "reason": reason})
            continue
        selected.append(
            {
                "review_sha256": identity,
                "lesson": record["lesson"],
                "trial_id": record["trial"]["trial_id"],
                "evidence_sha256": record["evidence_sha256"],
                "comparison_sha256": record["comparison"]["artifact_sha256"],
                "geometry_status": record["comparison"]["geometry_status"],
                "evidence_level": record["evidence_level"],
                "judgment_sha256": (record.get("judgment") or {}).get(
                    "artifact_sha256"
                ),
            }
        )
    return seal(
        {
            "schema": "roborsi-context-v1",
            "execution_authorized": False,
            "scope": scope,
            "selected": sorted(selected, key=lambda x: x["review_sha256"]),
            "excluded": sorted(excluded, key=lambda x: x["review_sha256"]),
            "use": "Advisory planning context. Reobserve, replan and validate; not executable instructions.",
        }
    )
