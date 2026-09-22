"""Replaceable decision providers; no SDK, model weights or robot imports."""

import os
import urllib.request
from typing import Protocol

from .artifacts import canonical, parse_json


class JudgmentProvider(Protocol):
    name: str

    def predict(self, request: dict, *, timeout_s: float) -> dict:
        """Return {request_sha256, response: {model, answers}} once, without retries."""
        ...


class DisabledProvider:
    name = "disabled"

    def predict(self, request, *, timeout_s):
        raise RuntimeError("disabled provider must not be called")


class ReplayProvider:
    name = "replay"

    def __init__(self, reply):
        self.reply = reply

    def predict(self, request, *, timeout_s):
        return self.reply


class DemoProvider:
    """Synthetic plumbing fixture. Always asks for evidence, never ranks plans."""

    name = "synthetic_demo"

    def predict(self, request, *, timeout_s):
        answers = {}
        for key, selected in (("route", "collect_evidence"), ("candidate", "abstain")):
            options = request["questions"][key]["criteria"]
            answers[key] = {
                "type": "choice",
                "choice": selected,
                "confidence": 0.5,
                "probabilities": {x: float(x == selected) for x in options},
            }
        answers["evidence_sufficient"] = {"type": "noul", "noul": 0.0}
        return {
            "request_sha256": request["artifact_sha256"],
            "response": {"model": "synthetic-fixture-not-a-model", "answers": answers},
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("provider redirects are unsupported")


class TypeSafeProvider:
    """Optional hosted Jev adapter, following the official System One HTTP API.

    Call outside control threads. A socket timeout cannot guarantee a wall-clock
    deadline; the judgment gate independently discards late replies.
    """

    name = "typesafe"
    endpoint = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, *, allow_network=False, model="jev-1.13.0"):
        if allow_network is not True:
            raise ValueError("TypeSafe requires explicit --allow-network")
        if (
            not isinstance(model, str)
            or not model.startswith("jev-")
            or len(model) > 80
        ):
            raise ValueError("provide a Jev model identifier")
        self.model = model

    def predict(self, request, *, timeout_s):
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("TYPESAFE_API_KEY is required")
        payload = canonical(
            {
                "model": self.model,
                "state": request["state"],
                "questions": request["questions"],
            }
        )
        if len(payload) > 128 * 1024:
            raise ValueError("provider request exceeds 128 KiB")
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
        )
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(req, timeout=timeout_s) as response:
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("provider response exceeds 1 MiB")
        return {
            "request_sha256": request["artifact_sha256"],
            "response": parse_json(body),
        }
