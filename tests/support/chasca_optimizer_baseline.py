"""Reviewed statistical gate for the immutable public Chasca button fixture."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json

def assert_chasca_button_baseline(observation: dict, baseline: dict, *, selected_case: str | None = None) -> None:
    """Check one or both measured Chasca buttons against reviewed public input.

    A different winner or formula estimate is allowed while its ordinary
    measured DPS remains statistically compatible. Neither direction silently
    changes the baseline; a larger gain receives a separate review label.
    """
    if baseline.get("schema") != "gtt_chasca_full_account_button_baseline_v1":
        raise AssertionError("Missing or unsupported reviewed Chasca baseline")
    if observation.get("status") != "chasca_regression_observation_v1":
        raise AssertionError("Missing complete Chasca button observation")
    fixture = observation.get("fixture") or {}
    for field in ("spec_sha256", "content_fingerprints_sha256", "rotation_sha256",
                  "artifact_count", "seed"):
        if fixture.get(field) != baseline["fixture"][field]:
            raise AssertionError(f"Chasca fixture {field} changed; review the input explicitly")
    for actual, expected, field in (
        (fixture.get("engine_id"), baseline["engine"]["engine_id"], "engine_id"),
        (fixture.get("engine_artifact_sha256"), baseline["engine"]["artifact_sha256"], "artifact_sha256"),
        (fixture.get("engine_binding_sha256"), baseline["engine"]["binding_sha256"], "binding_sha256"),
    ):
        if actual != expected:
            raise AssertionError(f"Selected Chasca engine {field} changed; review explicitly")
    if len(fixture.get("set_uids") or []) != 24 or len(fixture.get("selected") or []) != 4:
        raise AssertionError("Chasca fixture lost its 24 sets or four selected builds")
    for field, value in (("set_uids_sha256", fixture["set_uids"]),
                         ("selected_builds_sha256", fixture["selected"])):
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        if digest != baseline["fixture"][field]:
            raise AssertionError(f"Chasca fixture {field} changed; review the input explicitly")
    cases = observation.get("cases")
    if not isinstance(cases, list):
        raise AssertionError("Chasca button cases are missing")
    wanted = {selected_case} if selected_case else set(baseline["cases"])
    if wanted - set(baseline["cases"]):
        raise AssertionError("Unknown Chasca button case")
    if len(cases) != len(wanted) or {row.get("mode") for row in cases} != wanted:
        raise AssertionError("Chasca observation contains missing or duplicate button cases")
    for case in cases:
        assert_chasca_button_case(case, baseline["cases"][case["mode"]],
                                  baseline["fixture"], baseline["engine"])


def assert_chasca_button_case(case: dict, reference: dict, fixture: dict, engine: dict) -> None:
    mode = str(case["mode"])
    for field in ("set_groups", "total_rows_per_group"):
        if int(case[field]) != int(reference[field]):
            raise AssertionError(f"{mode} {field} changed; review result options")
    options = case.get("input") or {}
    expected_input = {
        "artifact_count": fixture["artifact_count"], "wearer_count": 4,
        "rotation_sha256": fixture["rotation_sha256"],
        "set_group_limit": reference["set_groups"],
        "builds_per_group": reference["total_rows_per_group"], "fast_mode": False,
    }
    if options != expected_input or case.get("engine_artifact_sha256") != engine["artifact_sha256"]:
        raise AssertionError(f"{mode} backend inventory, rotation, options, or engine changed")
    ids = case.get("winner_artifact_ids")
    if (not isinstance(ids, list) or len(ids) != 20 or
            any(type(value) is not int or value not in range(1, 601) for value in ids) or
            len(set(ids)) != 20):
        raise AssertionError(f"{mode} winner is not 20 unique owned synthetic artifacts")
    formula = Decimal(str(case["formula_dps"]))
    actual = Decimal(str(case["measured_dps"]))
    error = Decimal(str(case["standard_error"]))
    prior = Decimal(reference["measured"]["dps"])
    prior_error = Decimal(reference["measured"]["standard_error"])
    if (any(not value.is_finite() for value in (formula, actual, error, prior, prior_error)) or
            formula <= 0 or actual <= 0 or error < 0 or prior_error < 0):
        raise AssertionError(f"{mode} has invalid formula, measured DPS, or standard error")
    if int(case["iterations"]) != int(reference["measured"]["iterations"]):
        raise AssertionError(f"{mode} changed its normal n=500 finalist policy")
    allowed = max(Decimal("0.000001"), 6 * (error * error + prior_error * prior_error).sqrt())
    if actual < prior - allowed:
        raise AssertionError(f"{mode} LOWER_QUALITY_REGRESSION: {actual} vs {prior}; six-SE gap {allowed}")
    if actual > prior + allowed:
        raise AssertionError(f"{mode} HIGHER_QUALITY_REVIEW_REQUIRED: {actual} vs {prior}; six-SE gap {allowed}")
    elapsed_ms = Decimal(str(case["elapsed_seconds"])) * 1000
    if not elapsed_ms.is_finite() or elapsed_ms < 0:
        raise AssertionError(f"{mode} has invalid runtime")
    reference_ms = Decimal(reference["elapsed_ms"])
    if elapsed_ms > reference_ms + 5000:
        raise AssertionError(
            f"{mode} TIMING_RECHECK_REQUIRED: {elapsed_ms} ms vs {reference_ms} ms "
            f"(over 5 seconds slower). Confirm the computer is idle and rerun --case {mode}; "
            "do not update the baseline.")
