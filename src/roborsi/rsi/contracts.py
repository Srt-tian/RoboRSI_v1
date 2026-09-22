"""Offline prototype of phase expectations and semantic observation revisions.

Produces routing evidence, never motor commands or a hardware safety guarantee.
An eventual observer must increment revision when decision-relevant state changes.
"""

import math
import time

from .artifacts import digest, nonempty, seal, verify
from .memory import validate_scope

SCHEMA = "roborsi-checkpoint-v1"


def finite(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("finite numeric observation required")
    return value


def checkpoint(contract, observation, *, now=None):
    if contract.get("schema") != "roborsi-phase-contract-v1":
        raise ValueError("phase contract schema required")
    if contract.get("execution_authorized") is not False:
        raise ValueError("contracts cannot authorize execution")
    validate_scope(contract["scope"])
    nonempty(contract["phase"], "phase")
    identity = contract["program_sha256"]
    if (
        not isinstance(identity, str)
        or len(identity) != 64
        or any(c not in "0123456789abcdef" for c in identity)
    ):
        raise ValueError("program SHA256 required")
    max_age = finite(contract["max_observation_age_s"])
    if not 0 < max_age <= 10:
        raise ValueError("observation age budget must be in (0, 10] seconds")
    for name in ("expected", "hard_limits"):
        ranges = contract[name]
        if not isinstance(ranges, dict) or not ranges:
            raise ValueError("nonempty expectation and hard-limit maps required")
        for key, bounds in ranges.items():
            nonempty(key, "metric")
            if (
                not isinstance(bounds, list)
                or len(bounds) != 2
                or finite(bounds[0]) > finite(bounds[1])
            ):
                raise ValueError("ordered finite interval required")
    for key in contract["expected"].keys() & contract["hard_limits"].keys():
        e, h = contract["expected"][key], contract["hard_limits"][key]
        if not h[0] <= e[0] <= e[1] <= h[1]:
            raise ValueError("expectation must fit inside its hard limit")
    revision = observation["revision"]
    if type(revision) is not int or revision < 0:
        raise ValueError("nonnegative semantic observation revision required")
    values = observation["metrics"]
    if not isinstance(values, dict):
        raise ValueError("metric object required")
    for key, value in values.items():
        nonempty(key, "metric")
        finite(value)
    observed_at = finite(observation["observed_at_s"])
    timestamp = finite(time.time() if now is None else now)
    missing = sorted(
        (contract["expected"].keys() | contract["hard_limits"].keys()) - values.keys()
    )
    deviations = {
        name: sorted(
            key
            for key, (lo, hi) in contract[name].items()
            if key in values and not lo <= values[key] <= hi
        )
        for name in ("expected", "hard_limits")
    }
    if (
        observation["program_sha256"] != identity
        or observation["phase"] != contract["phase"]
    ):
        route = "discard_context"
    elif not 0 <= timestamp - observed_at <= max_age:
        route = "collect_evidence"
    elif deviations["hard_limits"]:
        route = "stop_review"
    elif missing:
        route = "collect_evidence"
    elif deviations["expected"]:
        route = "request_judgment"
    else:
        route = "continue"
    return seal(
        {
            "schema": SCHEMA,
            "execution_authorized": False,
            "scope": contract["scope"],
            "program_sha256": identity,
            "phase": contract["phase"],
            "contract_sha256": digest(contract),
            "observation_sha256": digest(observation),
            "revision": revision,
            "observed_at_s": observed_at,
            "valid_until_s": observed_at + max_age,
            "route": route,
            "missing": missing,
            "deviations": deviations,
            "expected": contract["expected"],
            "metrics": values,
            "use": "Offline routing proposal; no runtime observer or motor operation.",
        }
    )


def context_token(event):
    verify(event, SCHEMA)
    return digest(
        {
            key: event[key]
            for key in (
                "scope",
                "program_sha256",
                "phase",
                "contract_sha256",
                "revision",
            )
        }
    )


def matches_current(expected, current, now):
    return (
        context_token(expected) == context_token(current)
        and current["route"] == "request_judgment"
        and current["observed_at_s"] <= now <= current["valid_until_s"]
    )
