"""Exact, prospective admission of the saved Chasca pair for one Nilou study."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re

from . import acceptance

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CONTINUATION_PATH = ROOT / "docs/optimizer-evidence/2026-10-09-theory-contrasts/CONTINUATION.md"
CONTINUATION_SHA256 = "af3bd4fc0f601f99f99b9e00ac1ba010bdc1f86fe8459b6d29e1f37a78068e40"
ORIGINAL_RECEIPT_SHA256 = "948eae29b90f5e3487a3f64af0a6eb3c79be4eb9be65238329fae81cab7ff4cb"
ORIGINAL_PROTOTYPE_SHA256 = "fcd10ac3779bbaf7fd2c20e9043c295c60590a686069ded65d8f37f8c6e1bf90"
ORIGINAL_PROTOCOL_SHA256 = "1f4d84377d1b725038585a2b4bbed8d622b5e61c3f7c4cfe214fae80edf26ff9"
ORIGINAL_PROTOCOL_PATH = "docs/optimizer-evidence/2026-10-09-theory-contrasts/PROTOCOL.md"
ORIGINAL_STAGE10_COMMIT = "47e13fa8c2bc79284b177978605a38570c841ac7"
ORIGINAL_OFFLINE_SECONDS = 134.9347829
MAX_PAIRED_OFFLINE_SECONDS = 480.0
MAX_NEW_CASE_OFFLINE_SECONDS = 240.0
QUALITY_FAILURE = "insufficient_demonstrated_diverse_choices"
SOURCE_TASK_ID = "01a0b9e5-7078-7160-ad7b-ba6255012de1"

# The original runner is the sole administrative exception. These six files
# remain byte-identical to the pinned Chasca prototype.
FROZEN_NON_RUNNER_FILES = (
    "acceptance.py",
    "adapter.py",
    "contract_test.go",
    "test_acceptance.py",
    "test_witness_audit.py",
    "witness_audit.py",
)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _is_sha256(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def decision_info() -> dict:
    """Return compact provenance after checking the prospective decision bytes."""
    try:
        actual_sha = _sha256_file(CONTINUATION_PATH)
    except OSError as exc:
        raise ValueError("Continuation decision document is unavailable") from exc
    _require(actual_sha == CONTINUATION_SHA256, "Continuation decision document hash differs")
    return {
        "kind": "prospective_nilou_admission_v1",
        "source_task_id": SOURCE_TASK_ID,
        "continuation_path": CONTINUATION_PATH.relative_to(ROOT).as_posix(),
        "continuation_sha256": CONTINUATION_SHA256,
        "authorized_case": "bountiful_core",
        "new_capture_members": 2,
        "original_receipt_sha256": ORIGINAL_RECEIPT_SHA256,
        "original_prototype_sha256": ORIGINAL_PROTOTYPE_SHA256,
        "original_protocol_sha256": ORIGINAL_PROTOCOL_SHA256,
        "original_offline_seconds": ORIGINAL_OFFLINE_SECONDS,
        "max_paired_offline_seconds": MAX_PAIRED_OFFLINE_SECONDS,
        "max_new_case_offline_seconds": MAX_NEW_CASE_OFFLINE_SECONDS,
        "preserve_original_quality_failure": QUALITY_FAILURE,
    }


def validate_prerequisite(result, receipt_sha, current_prototype_sha, current_protocol_sha) -> float:
    """Validate the exact original Chasca result and return its actual study time.

    The caller separately records the decision provenance and constrains the
    new study to Bountiful/Nilou. This function releases no other case or retry.
    """
    decision_info()
    _require(receipt_sha == ORIGINAL_RECEIPT_SHA256, "Chasca receipt digest differs from the authorized receipt")
    _require(_is_sha256(current_prototype_sha), "Current prototype digest must be a lowercase SHA256")
    _require(current_prototype_sha != ORIGINAL_PROTOTYPE_SHA256, "Current Stage11 prototype must include the admission runner")
    _require(current_protocol_sha == CONTINUATION_SHA256, "Current protocol is not the pinned continuation decision")
    _require(isinstance(result, dict), "Chasca prerequisite must be a receipt object")
    _require(result.get("kind") == "theory_contrasts_research_v1", "Prerequisite is not the original study receipt")
    _require(result.get("phase") == "study" and result.get("case") == "chasca", "Only the original Chasca study is admissible")
    _require(result.get("stage10_commit") == ORIGINAL_STAGE10_COMMIT, "Original Stage10 parent differs")
    _require(result.get("protocol_path") == ORIGINAL_PROTOCOL_PATH, "Original protocol path differs")
    _require(result.get("protocol_sha256") == ORIGINAL_PROTOCOL_SHA256, "Original protocol hash differs")
    try:
        actual_original_protocol_sha = _sha256_file(ROOT / ORIGINAL_PROTOCOL_PATH)
    except OSError as exc:
        raise ValueError("Original protocol file is unavailable") from exc
    _require(actual_original_protocol_sha == ORIGINAL_PROTOCOL_SHA256, "Original protocol file hash differs")

    prototype = result.get("prototype")
    _require(isinstance(prototype, dict), "Original prototype provenance is missing")
    _require(prototype.get("sha256") == ORIGINAL_PROTOTYPE_SHA256, "Original prototype identity differs")
    original_files = prototype.get("files")
    _require(isinstance(original_files, dict), "Original prototype file identities are missing")
    _require(_is_sha256(original_files.get("run.py")), "Pinned original runner identity is missing")
    for name in FROZEN_NON_RUNNER_FILES:
        expected = original_files.get(name)
        _require(_is_sha256(expected), "Pinned original file identity is missing: " + name)
        try:
            actual = _sha256_file(HERE / name)
        except OSError as exc:
            raise ValueError("Frozen original file is unavailable: " + name) from exc
        _require(actual == expected, "Frozen non-runner file changed: " + name)

    _require(result.get("status") == "pass" and result.get("process_status") == "pass",
             "Original managed study did not pass")
    _require(result.get("acceptance_complete") is True and result.get("acceptance_failures") == [],
             "Original technical completeness gate did not pass cleanly")
    _require(result.get("next_case_allowed") is False, "Original Chasca decision is not the saved quality failure")
    stored_quality = result.get("quality_gate")
    _require(isinstance(stored_quality, dict), "Original quality gate is missing")
    _require(stored_quality.get("pass") is False, "Original quality gate must remain failed")
    _require(stored_quality.get("failures") == [QUALITY_FAILURE], "Original quality failure differs")
    _require(stored_quality.get("missing_directions") == [], "Original result has missing 2% directions")

    # Re-run the original technical and quality checks using the unchanged
    # acceptance module; the administrative decision does not alter its result.
    checked = acceptance.evaluate(result)
    _require(checked.get("acceptance_complete") is True and checked.get("acceptance_failures") == [],
             "Original technical acceptance no longer passes")
    checked_quality = checked.get("quality_gate")
    _require(isinstance(checked_quality, dict) and checked_quality == stored_quality,
             "Re-evaluated original quality metrics differ")
    _require(checked_quality.get("pass") is False and checked_quality.get("failures") == [QUALITY_FAILURE],
             "Re-evaluation found a different quality outcome")
    _require(checked_quality.get("missing_directions") == [], "Re-evaluation found missing 2% directions")
    _require(checked.get("next_case_allowed") is False, "Original quality failure no longer reproduces")

    _require(result.get("capture_reservation_spent") == 2 and result.get("capture_members_actual") == 2,
             "Original capture budget was not exactly two members")
    _require(result.get("ordinary_finalists") == 0 and result.get("study_invocations") == 1,
             "Original study call budget differs")
    cleanup = result.get("cleanup")
    _require(isinstance(cleanup, dict) and cleanup.get("job_absent") is True
             and cleanup.get("remaining_jobs") == [], "Original managed scratch cleanup failed")

    try:
        summary = acceptance.one(result.get("records", []), "light_study_summary")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Original offline study summary is missing or duplicated") from exc
    seconds = summary.get("seconds")
    _require(isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds),
             "Original offline study duration is invalid")
    _require(seconds == ORIGINAL_OFFLINE_SECONDS, "Original offline duration differs from the saved study")
    _require(result.get("offline_study_seconds") == seconds and result.get("paired_offline_seconds") == seconds,
             "Original receipt timing aliases differ from its study summary")
    _require(seconds + MAX_NEW_CASE_OFFLINE_SECONDS <= MAX_PAIRED_OFFLINE_SECONDS,
             "Authorized remaining pair exceeds the offline budget")
    return float(seconds)
