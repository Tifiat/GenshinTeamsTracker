"""Reviewed numerical baseline for the immutable public button fixture.

Formula results are deterministic. Ordinary GCSIM results are compared using
their reported sampling error, not against formula DPS or a fixed percentage.
No observation silently replaces the reviewed baseline.
"""
from __future__ import annotations

from decimal import Decimal


def assert_button_runtime(elapsed_ms: int, reference_ms: int) -> None:
    if elapsed_ms < 0 or reference_ms < 0:
        raise AssertionError("Invalid button runtime measurement")
    if elapsed_ms > reference_ms + 5000:
        raise AssertionError(
            f"TIMING_RECHECK_REQUIRED: {elapsed_ms} ms vs {reference_ms} ms "
            "(over 5 seconds slower). Confirm the computer is idle and rerun "
            "this case alone before diagnosing a regression. Do not update the baseline.")


def assert_button_baseline(observation: dict, baseline: dict) -> None:
    if baseline.get("schema") != "gtt_optimizer_button_baseline_v1":
        raise AssertionError("Missing or unsupported reviewed button baseline")
    if observation["fixture_sha256"] != baseline["fixture_sha256"]:
        raise AssertionError("Public fixture changed; review the baseline explicitly")
    for field in ("engine_id", "artifact_sha256", "binding_sha256"):
        if observation["engine"][field] != baseline["engine"][field]:
            raise AssertionError(f"Selected engine {field} changed; review the baseline explicitly")
    case = observation["mode"] + ("_fast" if observation["fast_mode"] else "_verified")
    expected = baseline["cases"][case]
    formula = Decimal(observation["formula_dps"])
    expected_formula = Decimal(expected["formula_dps"])
    if not formula.is_finite():
        raise AssertionError("Invalid formula DPS")
    tolerance = max(Decimal("0.000001"), abs(expected_formula) * Decimal("0.0000000001"))
    if abs(formula - expected_formula) > tolerance:
        direction = "lower" if formula < expected_formula else "higher"
        raise AssertionError(
            f"{case} formula DPS is {direction}: {formula} vs {expected_formula}; "
            "a changed result requires review, not automatic baseline replacement")
    measured = observation["measured"]
    if observation["fast_mode"]:
        if measured is not None:
            raise AssertionError("Fast mode must not perform finalist simulations")
        if "elapsed_ms" in expected:
            assert_button_runtime(observation["elapsed_ms"], expected["elapsed_ms"])
        return
    if not isinstance(measured, dict):
        raise AssertionError("Verified mode must include a measured finalist")
    reference = expected["measured"]
    if measured["iterations"] != reference["iterations"]:
        raise AssertionError("Finalist iteration policy changed; review the baseline explicitly")
    values = [Decimal(str(row[key])) for row in (measured, reference)
              for key in ("dps", "standard_error")]
    actual, error, prior, prior_error = values
    if any(not value.is_finite() for value in values) or error < 0 or prior_error < 0:
        raise AssertionError("Invalid measured DPS or sampling error")
    # Independent ordinary runs: combine both means' reported sampling error.
    allowed_gap = max(Decimal("0.000001"), 6 * (error * error + prior_error * prior_error).sqrt())
    if abs(actual - prior) > allowed_gap:
        raise AssertionError(
            f"{case} measured DPS changed beyond sampling error: {actual} vs {prior}; "
            f"allowed gap {allowed_gap}; review instead of updating automatically")
    if "elapsed_ms" in expected:
        assert_button_runtime(observation["elapsed_ms"], expected["elapsed_ms"])
