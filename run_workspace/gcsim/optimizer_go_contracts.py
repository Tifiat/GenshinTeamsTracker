"""Shared GOB-1 process-contract identities and canonical JSON helpers.

This module is intentionally transport-only. It does not start the Go binary,
read SQLite, call GCSIM, evaluate formulas, search artifacts, or bind UI. The
Go implementation owns strict semantic validation; these helpers keep Python
serialization and identity bytes identical to Go for shared fixtures and the
future single-request process adapter.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


GCSIM_OPTIMIZER_GO_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_GO_STRATEGY_ID = "gtt_gcsim_optimizer_go_v1"
GCSIM_OPTIMIZER_GO_REQUEST_KIND = "gtt_gcsim_optimizer_request_v1"
GCSIM_OPTIMIZER_GO_PROGRESS_KIND = "gtt_gcsim_optimizer_progress_v1"
GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND = "gtt_gcsim_optimizer_compact_ir_v1"
GCSIM_OPTIMIZER_GO_RESULT_KIND = "gtt_gcsim_optimizer_result_v1"


class GcsimOptimizerGoContractError(ValueError):
    """Raised when the shared process envelope is not the accepted schema."""


def canonical_json_bytes(payload: Any) -> bytes:
    """Return bytes matching contracts.CanonicalJSON in the Go module."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    # encoding/json deliberately escapes these two separators even when HTML
    # escaping is disabled. Mirror that behavior for cross-language identity.
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return encoded.encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_contract(
    path: str | Path,
    *,
    expected_kind: str,
) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GcsimOptimizerGoContractError("contract root must be an object")
    if payload.get("schema_version") != GCSIM_OPTIMIZER_GO_SCHEMA_VERSION:
        raise GcsimOptimizerGoContractError("unsupported schema_version")
    if payload.get("schema_kind") != expected_kind:
        raise GcsimOptimizerGoContractError("unsupported schema_kind")
    return payload


__all__ = [
    "GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND",
    "GCSIM_OPTIMIZER_GO_PROGRESS_KIND",
    "GCSIM_OPTIMIZER_GO_REQUEST_KIND",
    "GCSIM_OPTIMIZER_GO_RESULT_KIND",
    "GCSIM_OPTIMIZER_GO_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_GO_STRATEGY_ID",
    "GcsimOptimizerGoContractError",
    "canonical_json_bytes",
    "canonical_sha256",
    "load_contract",
    "text_sha256",
]
