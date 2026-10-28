"""Recall-first response-profile selection for farming-set screening.

The response scan runs one frozen physical artifact state per wearer through a
small, generic equal-investment profile bank.  This module turns those typed
outcomes into the bounded ``WearerProfileSelection`` values consumed by the
complete set scan.  It is deliberately pure: it does not know character names,
stat roles, artifact-set effects, or how GCSIM was executed.

Selection is fail closed.  The neutral baseline, the strongest successful
directions, statistically unresolved near-ties, profiles with unknown error,
and profiles whose run failed or did not resolve are mandatory.  If those rows
do not fit the caller's per-wearer cap, the selector raises instead of silently
discarding the branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from math import isfinite, sqrt
from typing import Iterable

from .farming_search import (
    PROFILE_BASELINE,
    CandidateEvaluation,
    FourPieceSetState,
    SetProfileCandidate,
    StatProfileBank,
    WearerProfileSelection,
)


RESPONSE_PROFILE_BASELINE = "response_baseline"
RESPONSE_PROFILE_TOP = "response_top"
RESPONSE_PROFILE_CONFIDENCE_OVERLAP = "response_confidence_overlap"
RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY = "response_unknown_uncertainty"
RESPONSE_PROFILE_FAILED = "response_failed"
RESPONSE_PROFILE_TIMEOUT = "response_timeout"
RESPONSE_PROFILE_UNRESOLVED = "response_unresolved"
RESPONSE_PROFILE_IMMATERIAL = "response_immaterial"
RESPONSE_PROFILE_MATERIAL_UPLIFT = "response_material_uplift"
RESPONSE_PROFILE_MATERIAL_NEGATIVE = "response_material_negative"
RESPONSE_PROFILE_MATERIALITY_UNRESOLVED = "response_materiality_unresolved"


class FarmingResponseSelectionError(ValueError):
    """Raised when response evidence cannot be reduced without losing recall."""


class ResponseProfileOutcomeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ResponseProfileOutcome:
    """One planned wearer/profile probe and its semantic outcome.

    Failed, timed-out, and otherwise unresolved probes still carry the exact
    candidate and equal-investment signature.  That provenance is required to
    validate complete coverage even though no ``CandidateEvaluation`` exists.
    """

    candidate: SetProfileCandidate
    status: ResponseProfileOutcomeStatus
    investment_signature: str
    comparison_context_sha256: str
    request_identity_sha256: str
    evaluation: CandidateEvaluation | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, SetProfileCandidate):
            raise ValueError("candidate must be a SetProfileCandidate")
        if not isinstance(self.status, ResponseProfileOutcomeStatus):
            raise ValueError("status must be a ResponseProfileOutcomeStatus")
        _require_identifier(
            self.investment_signature,
            field_name="investment_signature",
        )
        _require_sha256(
            self.comparison_context_sha256,
            field_name="comparison_context_sha256",
        )
        _require_sha256(
            self.request_identity_sha256,
            field_name="request_identity_sha256",
        )
        if not isinstance(self.detail, str):
            raise ValueError("detail must be a string")
        if self.status is ResponseProfileOutcomeStatus.PASSED:
            if not isinstance(self.evaluation, CandidateEvaluation):
                raise ValueError("a passed response outcome requires an evaluation")
            if self.evaluation.candidate.key != self.candidate.key:
                raise ValueError("response evaluation candidate does not match outcome")
            if self.evaluation.investment_signature != self.investment_signature:
                raise ValueError(
                    "response evaluation investment signature does not match outcome"
                )
        elif self.evaluation is not None:
            raise ValueError("only a passed response outcome may carry an evaluation")

    @classmethod
    def from_evaluation(
        cls,
        evaluation: CandidateEvaluation,
        *,
        comparison_context_sha256: str,
        request_identity_sha256: str,
    ) -> "ResponseProfileOutcome":
        if not isinstance(evaluation, CandidateEvaluation):
            raise ValueError("evaluation must be a CandidateEvaluation")
        return cls(
            candidate=evaluation.candidate,
            status=ResponseProfileOutcomeStatus.PASSED,
            investment_signature=evaluation.investment_signature,
            comparison_context_sha256=comparison_context_sha256,
            request_identity_sha256=request_identity_sha256,
            evaluation=evaluation,
        )


@dataclass(frozen=True, slots=True)
class ResponseProfileSelectionBudget:
    """Hard per-wearer cap and statistical retention policy.

    ``top_profiles_per_wearer`` counts successful non-baseline directions.  The
    mandatory baseline is additional, so the cap must accommodate both.
    """

    max_profiles_per_wearer: int
    top_profiles_per_wearer: int = 2
    confidence_sigma: float = 2.0
    relative_uncertainty_margin: float = 0.01
    practical_materiality_relative: float = 0.005

    def __post_init__(self) -> None:
        for field_name in (
            "max_profiles_per_wearer",
            "top_profiles_per_wearer",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if self.max_profiles_per_wearer <= 0:
            raise ValueError("max_profiles_per_wearer must be positive")
        if self.top_profiles_per_wearer <= 0:
            raise ValueError("top_profiles_per_wearer must be positive")
        if self.max_profiles_per_wearer < self.top_profiles_per_wearer + 1:
            raise ValueError(
                "max_profiles_per_wearer must fit the baseline and top profiles"
            )
        if (
            isinstance(self.confidence_sigma, bool)
            or not isfinite(self.confidence_sigma)
            or self.confidence_sigma < 0
        ):
            raise ValueError("confidence_sigma must be finite and non-negative")
        if (
            isinstance(self.relative_uncertainty_margin, bool)
            or not isfinite(self.relative_uncertainty_margin)
            or self.relative_uncertainty_margin < 0
        ):
            raise ValueError(
                "relative_uncertainty_margin must be finite and non-negative"
            )
        if (
            isinstance(self.practical_materiality_relative, bool)
            or not isfinite(self.practical_materiality_relative)
            or self.practical_materiality_relative < 0
        ):
            raise ValueError(
                "practical_materiality_relative must be finite and non-negative"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_profiles_per_wearer": self.max_profiles_per_wearer,
            "top_profiles_per_wearer": self.top_profiles_per_wearer,
            "confidence_sigma": self.confidence_sigma,
            "relative_uncertainty_margin": self.relative_uncertainty_margin,
            "practical_materiality_relative": self.practical_materiality_relative,
        }


@dataclass(frozen=True, slots=True)
class ResponseProfileAuditRow:
    wearer_id: str
    profile_id: str
    status: ResponseProfileOutcomeStatus
    expected_dps: float | None
    standard_error: float | None
    carried: bool
    required: bool
    reasons: tuple[str, ...]
    detail: str = ""
    candidate_key: tuple[str, str, str, str, str] = ()
    physical_state_key: tuple[str, str, str, str] = ()
    request_identity_sha256: str = ""

    def __post_init__(self) -> None:
        _require_identifier(self.wearer_id, field_name="wearer_id")
        _require_identifier(self.profile_id, field_name="profile_id")
        if not isinstance(self.status, ResponseProfileOutcomeStatus):
            raise ValueError("status must be a ResponseProfileOutcomeStatus")
        for field_name in ("expected_dps", "standard_error"):
            value = getattr(self, field_name)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{field_name} must be finite and non-negative")
        if self.status is ResponseProfileOutcomeStatus.PASSED:
            if self.expected_dps is None:
                raise ValueError("passed audit rows require expected_dps")
        elif self.expected_dps is not None or self.standard_error is not None:
            raise ValueError("non-passed audit rows cannot carry DPS metrics")
        if self.required and not self.carried:
            raise ValueError("a required audit row must be carried")
        if len(self.candidate_key) != 5 or len(self.physical_state_key) != 4:
            raise ValueError("audit candidate keys have an invalid shape")
        if self.candidate_key[:4] != self.physical_state_key:
            raise ValueError("audit candidate and physical state keys disagree")
        if (
            self.candidate_key[0] != self.wearer_id
            or self.candidate_key[4] != self.profile_id
        ):
            raise ValueError("audit candidate key disagrees with wearer/profile")
        _require_sha256(
            self.request_identity_sha256,
            field_name="request_identity_sha256",
        )


@dataclass(frozen=True, slots=True)
class ResponseProfileSelectionResult:
    budget: ResponseProfileSelectionBudget
    investment_signature: str
    profile_ids: tuple[str, ...]
    baseline_profile_id: str
    profile_bank_sha256: str
    selections: tuple[WearerProfileSelection, ...]
    audit_rows: tuple[ResponseProfileAuditRow, ...]
    frozen_states: tuple[FourPieceSetState, ...]
    comparison_context_sha256: str
    request_identity_sha256s: tuple[str, ...]
    outcome_domain_sha256: str
    budget_sha256: str
    provenance_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.budget, ResponseProfileSelectionBudget):
            raise ValueError("budget must be a ResponseProfileSelectionBudget")
        _require_identifier(
            self.investment_signature,
            field_name="investment_signature",
        )
        _require_identifier(
            self.baseline_profile_id,
            field_name="baseline_profile_id",
        )
        if self.baseline_profile_id not in self.profile_ids:
            raise ValueError("baseline_profile_id is absent from profile_ids")
        _require_unique(self.profile_ids, field_name="profile_ids")
        for field_name in (
            "comparison_context_sha256",
            "profile_bank_sha256",
            "outcome_domain_sha256",
            "budget_sha256",
            "provenance_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        if self.budget_sha256 != _sha256_payload(self.budget.to_dict()):
            raise ValueError("budget_sha256 does not match the frozen budget")
        wearer_ids = tuple(selection.wearer_id for selection in self.selections)
        if not wearer_ids or len(set(wearer_ids)) != len(wearer_ids):
            raise ValueError("selections must cover unique wearer ids")
        if tuple(state.wearer_id for state in self.frozen_states) != wearer_ids:
            raise ValueError("frozen states do not match selection wearer order")
        expected_pairs = tuple(
            (wearer_id, profile_id)
            for wearer_id in wearer_ids
            for profile_id in self.profile_ids
        )
        actual_pairs = tuple(
            (row.wearer_id, row.profile_id)
            for row in self.audit_rows
        )
        if actual_pairs != expected_pairs:
            raise ValueError("audit rows do not cover the canonical response domain")
        selection_by_wearer = {
            selection.wearer_id: selection
            for selection in self.selections
        }
        for selection in self.selections:
            if self.baseline_profile_id not in selection.profile_ids:
                raise ValueError("every selection must retain the baseline profile")
            if any(
                profile_id not in self.profile_ids
                for profile_id in (
                    *selection.profile_ids,
                    *selection.required_profile_ids,
                )
            ):
                raise ValueError("selection contains a profile outside profile_ids")
        for row in self.audit_rows:
            selection = selection_by_wearer[row.wearer_id]
            if row.carried != (row.profile_id in selection.profile_ids):
                raise ValueError("audit carried flags disagree with selections")
            if row.required != (row.profile_id in selection.required_profile_ids):
                raise ValueError("audit required flags disagree with selections")
        frozen_by_wearer = {
            state.wearer_id: state.key
            for state in self.frozen_states
        }
        if any(
            row.physical_state_key != frozen_by_wearer[row.wearer_id]
            for row in self.audit_rows
        ):
            raise ValueError("audit rows disagree with frozen physical states")
        if self.request_identity_sha256s != tuple(
            row.request_identity_sha256 for row in self.audit_rows
        ):
            raise ValueError("request identity order disagrees with audit rows")
        expected_domain = _response_domain_sha256(
            comparison_context_sha256=self.comparison_context_sha256,
            investment_signature=self.investment_signature,
            profile_bank_sha256=self.profile_bank_sha256,
            baseline_profile_id=self.baseline_profile_id,
            profile_ids=self.profile_ids,
            audit_rows=self.audit_rows,
        )
        if self.outcome_domain_sha256 != expected_domain:
            raise ValueError("outcome_domain_sha256 does not match response evidence")
        expected_provenance = _response_provenance_sha256(
            outcome_domain_sha256=self.outcome_domain_sha256,
            budget_sha256=self.budget_sha256,
            selections=self.selections,
            frozen_states=self.frozen_states,
            audit_rows=self.audit_rows,
        )
        if self.provenance_sha256 != expected_provenance:
            raise ValueError("provenance_sha256 does not match selection evidence")

    def selection_for(self, wearer_id: str) -> WearerProfileSelection:
        for selection in self.selections:
            if selection.wearer_id == wearer_id:
                return selection
        raise KeyError(wearer_id)


def select_wearer_response_profiles(
    outcomes: Iterable[ResponseProfileOutcome],
    *,
    wearer_ids: Iterable[str],
    profile_bank: StatProfileBank,
    budget: ResponseProfileSelectionBudget,
    baseline_profile_id: str = PROFILE_BASELINE,
) -> ResponseProfileSelectionResult:
    """Select a bounded, deterministic profile subset for every wearer.

    Coverage must be the exact ``wearer_ids x profile_bank`` product, with one
    frozen physical state per wearer.  Input order has no effect on the result;
    wearer order and profile-bank order define the canonical output order.
    """

    if not isinstance(profile_bank, StatProfileBank):
        raise FarmingResponseSelectionError(
            "profile_bank must be a StatProfileBank"
        )
    if not isinstance(budget, ResponseProfileSelectionBudget):
        raise FarmingResponseSelectionError(
            "budget must be a ResponseProfileSelectionBudget"
        )
    _require_identifier(baseline_profile_id, field_name="baseline_profile_id")

    canonical_wearers = tuple(wearer_ids)
    if not canonical_wearers:
        raise FarmingResponseSelectionError(
            "response selection requires at least one wearer"
        )
    for wearer_id in canonical_wearers:
        _require_identifier(wearer_id, field_name="wearer_id")
    _require_unique(canonical_wearers, field_name="wearer_ids")

    profile_ids = tuple(profile.profile_id for profile in profile_bank.profiles)
    if baseline_profile_id not in profile_ids:
        raise FarmingResponseSelectionError(
            "profile bank does not contain the required baseline profile"
        )
    profile_position = {
        profile_id: position
        for position, profile_id in enumerate(profile_ids)
    }

    normalized = tuple(outcomes)
    if not normalized or any(
        not isinstance(outcome, ResponseProfileOutcome)
        for outcome in normalized
    ):
        raise FarmingResponseSelectionError(
            "response outcomes must be non-empty ResponseProfileOutcome values"
        )
    signatures = {outcome.investment_signature for outcome in normalized}
    if len(signatures) != 1:
        raise FarmingResponseSelectionError(
            "response outcomes must share one equal-investment signature"
        )
    investment_signature = next(iter(signatures))
    comparison_contexts = {
        outcome.comparison_context_sha256
        for outcome in normalized
    }
    if len(comparison_contexts) != 1:
        raise FarmingResponseSelectionError(
            "response outcomes must share one comparison context"
        )
    comparison_context_sha256 = next(iter(comparison_contexts))

    outcome_by_pair: dict[tuple[str, str], ResponseProfileOutcome] = {}
    duplicate_pairs: list[tuple[str, str]] = []
    for outcome in normalized:
        pair = (
            outcome.candidate.state.wearer_id,
            outcome.candidate.profile_id,
        )
        if pair in outcome_by_pair and pair not in duplicate_pairs:
            duplicate_pairs.append(pair)
        outcome_by_pair[pair] = outcome
    if duplicate_pairs:
        raise FarmingResponseSelectionError(
            "response wearer/profile outcomes must be unique; "
            f"duplicates={tuple(sorted(duplicate_pairs))!r}"
        )

    expected_pairs = {
        (wearer_id, profile_id)
        for wearer_id in canonical_wearers
        for profile_id in profile_ids
    }
    observed_pairs = set(outcome_by_pair)
    if observed_pairs != expected_pairs:
        missing = tuple(sorted(expected_pairs.difference(observed_pairs)))
        extra = tuple(sorted(observed_pairs.difference(expected_pairs)))
        raise FarmingResponseSelectionError(
            "response outcomes must cover exactly wearer_ids x profile_bank; "
            f"missing={missing!r}; extra={extra!r}"
        )

    for wearer_id in canonical_wearers:
        physical_keys = {
            outcome_by_pair[(wearer_id, profile_id)].candidate.state.key
            for profile_id in profile_ids
        }
        if len(physical_keys) != 1:
            raise FarmingResponseSelectionError(
                "response profiles must share one frozen physical state per wearer; "
                f"wearer_id={wearer_id!r}"
            )

    selections: list[WearerProfileSelection] = []
    audit_rows: list[ResponseProfileAuditRow] = []
    for wearer_id in canonical_wearers:
        wearer_outcomes = tuple(
            outcome_by_pair[(wearer_id, profile_id)]
            for profile_id in profile_ids
        )
        reasons_by_profile: dict[str, list[str]] = {
            profile_id: []
            for profile_id in profile_ids
        }
        carry_by_profile = {profile_id: False for profile_id in profile_ids}
        reasons_by_profile[baseline_profile_id].append(RESPONSE_PROFILE_BASELINE)
        carry_by_profile[baseline_profile_id] = True

        baseline_outcome = outcome_by_pair[(wearer_id, baseline_profile_id)]
        plausible_uplifts: list[ResponseProfileOutcome] = []
        if baseline_outcome.status is ResponseProfileOutcomeStatus.PASSED:
            baseline_evaluation = _require_passed_evaluation(baseline_outcome)
            materiality_threshold = (
                abs(baseline_evaluation.expected_dps)
                * budget.practical_materiality_relative
            )
            for outcome in wearer_outcomes:
                profile_id = outcome.candidate.profile_id
                if (
                    profile_id == baseline_profile_id
                    or outcome.status is not ResponseProfileOutcomeStatus.PASSED
                ):
                    continue
                evaluation = _require_passed_evaluation(outcome)
                if (
                    baseline_evaluation.standard_error is None
                    or evaluation.standard_error is None
                ):
                    reasons_by_profile[profile_id].append(
                        RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY
                    )
                    carry_by_profile[profile_id] = True
                    continue
                delta = evaluation.expected_dps - baseline_evaluation.expected_dps
                delta_error = sqrt(
                    evaluation.standard_error ** 2
                    + baseline_evaluation.standard_error ** 2
                )
                uncertainty = budget.confidence_sigma * delta_error
                if abs(delta) + uncertainty <= materiality_threshold:
                    reasons_by_profile[profile_id].append(
                        RESPONSE_PROFILE_IMMATERIAL
                    )
                    continue
                if delta + uncertainty < -materiality_threshold:
                    reasons_by_profile[profile_id].append(
                        RESPONSE_PROFILE_MATERIAL_NEGATIVE
                    )
                    continue
                if delta - uncertainty > materiality_threshold:
                    reasons_by_profile[profile_id].append(
                        RESPONSE_PROFILE_MATERIAL_UPLIFT
                    )
                else:
                    reasons_by_profile[profile_id].append(
                        RESPONSE_PROFILE_MATERIALITY_UNRESOLVED
                    )
                    carry_by_profile[profile_id] = True
                if delta + uncertainty > materiality_threshold:
                    plausible_uplifts.append(outcome)
        else:
            # Without the physical baseline no passed direction can be reduced
            # safely: each remains a mandatory unresolved comparison.
            for outcome in wearer_outcomes:
                if outcome.status is ResponseProfileOutcomeStatus.PASSED:
                    profile_id = outcome.candidate.profile_id
                    if profile_id != baseline_profile_id:
                        reasons_by_profile[profile_id].append(
                            RESPONSE_PROFILE_MATERIALITY_UNRESOLVED
                        )
                        carry_by_profile[profile_id] = True

        ranked_uplifts = tuple(
            sorted(
                plausible_uplifts,
                key=lambda outcome: _passed_rank_key(
                    outcome,
                    profile_position=profile_position,
                ),
            )
        )
        for outcome in ranked_uplifts[: budget.top_profiles_per_wearer]:
            profile_id = outcome.candidate.profile_id
            reasons_by_profile[profile_id].append(RESPONSE_PROFILE_TOP)
            carry_by_profile[profile_id] = True

        if ranked_uplifts:
            best_evaluation = _require_passed_evaluation(ranked_uplifts[0])
            best_lower_bound = best_evaluation.lower_bound(budget.confidence_sigma)
            absolute_margin = (
                best_evaluation.expected_dps
                * budget.relative_uncertainty_margin
            )
            if best_evaluation.standard_error is not None:
                for outcome in ranked_uplifts[1:]:
                    evaluation = _require_passed_evaluation(outcome)
                    if (
                        evaluation.standard_error is not None
                        and evaluation.upper_bound(budget.confidence_sigma)
                        + absolute_margin
                        >= best_lower_bound
                    ):
                        profile_id = outcome.candidate.profile_id
                        reasons_by_profile[profile_id].append(
                            RESPONSE_PROFILE_CONFIDENCE_OVERLAP
                        )
                        carry_by_profile[profile_id] = True

        for outcome in wearer_outcomes:
            reason = _unresolved_reason(outcome.status)
            if reason is not None:
                profile_id = outcome.candidate.profile_id
                reasons_by_profile[profile_id].append(reason)
                carry_by_profile[profile_id] = True

        carried_profile_ids = tuple(
            profile_id
            for profile_id in profile_ids
            if carry_by_profile[profile_id]
        )
        required_profile_ids = tuple(
            profile_id
            for profile_id in carried_profile_ids
            if profile_id != baseline_profile_id
        )
        if len(carried_profile_ids) > budget.max_profiles_per_wearer:
            raise FarmingResponseSelectionError(
                "required response profiles exceed max_profiles_per_wearer; "
                f"wearer_id={wearer_id!r}; "
                f"required={carried_profile_ids!r}; "
                f"cap={budget.max_profiles_per_wearer}"
            )

        selections.append(
            WearerProfileSelection(
                wearer_id=wearer_id,
                profile_ids=carried_profile_ids,
                required_profile_ids=required_profile_ids,
            )
        )
        carried_set = set(carried_profile_ids)
        required_set = set(required_profile_ids)
        for outcome in wearer_outcomes:
            evaluation = outcome.evaluation
            profile_id = outcome.candidate.profile_id
            audit_rows.append(
                ResponseProfileAuditRow(
                    wearer_id=wearer_id,
                    profile_id=profile_id,
                    status=outcome.status,
                    expected_dps=(
                        None if evaluation is None else evaluation.expected_dps
                    ),
                    standard_error=(
                        None if evaluation is None else evaluation.standard_error
                    ),
                    carried=profile_id in carried_set,
                    required=profile_id in required_set,
                    reasons=tuple(reasons_by_profile[profile_id]),
                    detail=outcome.detail,
                    candidate_key=outcome.candidate.key,
                    physical_state_key=outcome.candidate.state.key,
                    request_identity_sha256=outcome.request_identity_sha256,
                )
            )

    frozen_states = tuple(
        outcome_by_pair[(wearer_id, baseline_profile_id)].candidate.state
        for wearer_id in canonical_wearers
    )
    canonical_outcomes = tuple(
        outcome_by_pair[(wearer_id, profile_id)]
        for wearer_id in canonical_wearers
        for profile_id in profile_ids
    )
    request_identity_sha256s = tuple(
        outcome.request_identity_sha256
        for outcome in canonical_outcomes
    )
    profile_bank_sha256 = _profile_bank_sha256(profile_bank)
    outcome_domain_sha256 = _response_domain_sha256(
        comparison_context_sha256=comparison_context_sha256,
        investment_signature=investment_signature,
        profile_bank_sha256=profile_bank_sha256,
        baseline_profile_id=baseline_profile_id,
        profile_ids=profile_ids,
        audit_rows=tuple(audit_rows),
    )
    budget_sha256 = _sha256_payload(budget.to_dict())
    provenance_sha256 = _response_provenance_sha256(
        outcome_domain_sha256=outcome_domain_sha256,
        budget_sha256=budget_sha256,
        selections=tuple(selections),
        frozen_states=frozen_states,
        audit_rows=tuple(audit_rows),
    )
    return ResponseProfileSelectionResult(
        budget=budget,
        investment_signature=investment_signature,
        profile_ids=profile_ids,
        baseline_profile_id=baseline_profile_id,
        profile_bank_sha256=profile_bank_sha256,
        selections=tuple(selections),
        audit_rows=tuple(audit_rows),
        frozen_states=frozen_states,
        comparison_context_sha256=comparison_context_sha256,
        request_identity_sha256s=request_identity_sha256s,
        outcome_domain_sha256=outcome_domain_sha256,
        budget_sha256=budget_sha256,
        provenance_sha256=provenance_sha256,
    )


def _passed_rank_key(
    outcome: ResponseProfileOutcome,
    *,
    profile_position: dict[str, int],
) -> tuple[float, float, int, str]:
    evaluation = _require_passed_evaluation(outcome)
    return (
        -evaluation.expected_dps,
        (
            float("inf")
            if evaluation.standard_error is None
            else evaluation.standard_error
        ),
        profile_position[outcome.candidate.profile_id],
        outcome.candidate.profile_id,
    )


def _require_passed_evaluation(
    outcome: ResponseProfileOutcome,
) -> CandidateEvaluation:
    evaluation = outcome.evaluation
    if evaluation is None:
        raise AssertionError("validated passed response outcome lost its evaluation")
    return evaluation


def _unresolved_reason(
    status: ResponseProfileOutcomeStatus,
) -> str | None:
    return {
        ResponseProfileOutcomeStatus.PASSED: None,
        ResponseProfileOutcomeStatus.FAILED: RESPONSE_PROFILE_FAILED,
        ResponseProfileOutcomeStatus.TIMEOUT: RESPONSE_PROFILE_TIMEOUT,
        ResponseProfileOutcomeStatus.UNRESOLVED: RESPONSE_PROFILE_UNRESOLVED,
    }[status]


def _require_identifier(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FarmingResponseSelectionError(
            f"{field_name} must be a non-empty trimmed string"
        )


def _require_sha256(value: object, *, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FarmingResponseSelectionError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _sha256_payload(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _profile_bank_sha256(profile_bank: StatProfileBank) -> str:
    return _sha256_payload(
        {
            "schema_version": 1,
            "axes": [
                {
                    "key": axis.key,
                    "probe_delta": axis.probe_delta,
                    "unit": axis.unit,
                }
                for axis in profile_bank.axes
            ],
            "profiles": [
                {
                    "profile_id": profile.profile_id,
                    "kind": profile.kind,
                    "weights": [
                        {
                            "axis_key": weight.axis_key,
                            "weight": weight.weight,
                        }
                        for weight in profile.weights
                    ],
                    "focus_axes": list(profile.focus_axes),
                }
                for profile in profile_bank.profiles
            ],
        }
    )


def _audit_payload(row: ResponseProfileAuditRow) -> dict[str, object]:
    return {
        "wearer_id": row.wearer_id,
        "profile_id": row.profile_id,
        "status": row.status.value,
        "expected_dps": row.expected_dps,
        "standard_error": row.standard_error,
        "carried": row.carried,
        "required": row.required,
        "reasons": list(row.reasons),
        "detail": row.detail,
        "candidate_key": list(row.candidate_key),
        "physical_state_key": list(row.physical_state_key),
        "request_identity_sha256": row.request_identity_sha256,
    }


def _response_domain_sha256(
    *,
    comparison_context_sha256: str,
    investment_signature: str,
    profile_bank_sha256: str,
    baseline_profile_id: str,
    profile_ids: tuple[str, ...],
    audit_rows: tuple[ResponseProfileAuditRow, ...],
) -> str:
    return _sha256_payload(
        {
            "schema_version": 2,
            "comparison_context_sha256": comparison_context_sha256,
            "investment_signature": investment_signature,
            "profile_bank_sha256": profile_bank_sha256,
            "baseline_profile_id": baseline_profile_id,
            "profile_ids": list(profile_ids),
            "audit_rows": [_audit_payload(row) for row in audit_rows],
        }
    )


def _response_provenance_sha256(
    *,
    outcome_domain_sha256: str,
    budget_sha256: str,
    selections: tuple[WearerProfileSelection, ...],
    frozen_states: tuple[FourPieceSetState, ...],
    audit_rows: tuple[ResponseProfileAuditRow, ...],
) -> str:
    return _sha256_payload(
        {
            "schema_version": 2,
            "outcome_domain_sha256": outcome_domain_sha256,
            "budget_sha256": budget_sha256,
            "selections": [
                {
                    "wearer_id": selection.wearer_id,
                    "profile_ids": list(selection.profile_ids),
                    "required_profile_ids": list(selection.required_profile_ids),
                }
                for selection in selections
            ],
            "frozen_states": [list(state.key) for state in frozen_states],
            "audit_rows": [_audit_payload(row) for row in audit_rows],
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _require_unique(values: Iterable[object], *, field_name: str) -> None:
    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise FarmingResponseSelectionError(
            f"{field_name} must be unique; duplicates={duplicates!r}"
        )


__all__ = [
    "RESPONSE_PROFILE_BASELINE",
    "RESPONSE_PROFILE_CONFIDENCE_OVERLAP",
    "RESPONSE_PROFILE_FAILED",
    "RESPONSE_PROFILE_IMMATERIAL",
    "RESPONSE_PROFILE_MATERIAL_NEGATIVE",
    "RESPONSE_PROFILE_MATERIAL_UPLIFT",
    "RESPONSE_PROFILE_MATERIALITY_UNRESOLVED",
    "RESPONSE_PROFILE_TIMEOUT",
    "RESPONSE_PROFILE_TOP",
    "RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY",
    "RESPONSE_PROFILE_UNRESOLVED",
    "FarmingResponseSelectionError",
    "ResponseProfileAuditRow",
    "ResponseProfileOutcome",
    "ResponseProfileOutcomeStatus",
    "ResponseProfileSelectionBudget",
    "ResponseProfileSelectionResult",
    "select_wearer_response_profiles",
]
