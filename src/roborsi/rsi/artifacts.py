"""Deterministic JSON artifacts; fingerprints detect changes, not authorship."""

import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(path):
    def invalid(token):
        raise ValueError(f"nonfinite JSON value: {token}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=invalid,
        object_pairs_hook=unique,
    )


def source_ref(path):
    p = Path(path)
    return {"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def seal(payload):
    body = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    return dict(body, artifact_sha256=digest(body))


def verify(artifact, kind):
    if not isinstance(artifact, dict) or artifact.get("schema") != kind:
        raise ValueError(f"expected {kind} artifact")
    if artifact.get("artifact_sha256") != seal(artifact)["artifact_sha256"]:
        raise ValueError("artifact fingerprint mismatch")
    if artifact.get("execution_authorized") is not False:
        raise ValueError("RSI artifacts cannot authorize execution")


def write_json(path, value):
    # Validate before creating a file, and never overwrite a previous iteration.
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        f.write(encoded)


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"nonempty {name} required")
    return value
