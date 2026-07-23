from __future__ import annotations

import hashlib
from dataclasses import replace
import unittest

from run_workspace.gcsim.farming_response import (
    RESPONSE_PROFILE_BASELINE,
    RESPONSE_PROFILE_CONFIDENCE_OVERLAP,
    RESPONSE_PROFILE_FAILED,
    RESPONSE_PROFILE_IMMATERIAL,
    RESPONSE_PROFILE_MATERIAL_NEGATIVE,
    RESPONSE_PROFILE_TIMEOUT,
    RESPONSE_PROFILE_TOP,
    RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY,
    RESPONSE_PROFILE_UNRESOLVED,
    FarmingResponseSelectionError,
    ResponseProfileOutcome,
    ResponseProfileOutcomeStatus,
    ResponseProfileSelectionBudget,
    select_wearer_response_profiles,
)
from run_workspace.gcsim.farming_search import (
    CandidateEvaluation,
    FourPieceSetState,
    SetProfileCandidate,
    StatAxis,
    WearerProfileSelection,
    generate_stat_profile_bank,
)


INVESTMENT_SIGNATURE = "equal-investment/test-v1"
COMPARISON_CONTEXT_SHA256 = "c" * 64


class FarmingResponseSelectionTest(unittest.TestCase):
    def test_selection_is_deterministic_recall_first_and_auditable(self) -> None:
        bank = _profile_bank("a", "b", "c", "d")
        outcomes = (
            _passed("wearer_a", "baseline", 100.0, error=1.0),
            _passed("wearer_a", "focus/a", 110.0, error=1.0),
            _passed("wearer_a", "focus/b", 107.0, error=2.0),
            _passed("wearer_a", "focus/c", 20.0, error=None),
            _passed("wearer_a", "focus/d", 20.0, error=0.1),
            _passed("wearer_b", "baseline", 80.0, error=0.1),
            _passed("wearer_b", "focus/a", 82.0, error=0.1),
            _unresolved(
                "wearer_b",
                "focus/b",
                ResponseProfileOutcomeStatus.FAILED,
                detail="process failed",
            ),
            _unresolved(
                "wearer_b",
                "focus/c",
                ResponseProfileOutcomeStatus.TIMEOUT,
            ),
            _unresolved(
                "wearer_b",
                "focus/d",
                ResponseProfileOutcomeStatus.UNRESOLVED,
            ),
        )
        budget = ResponseProfileSelectionBudget(
            max_profiles_per_wearer=5,
            top_profiles_per_wearer=1,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.0,
        )

        result = select_wearer_response_profiles(
            reversed(outcomes),
            wearer_ids=("wearer_a", "wearer_b"),
            profile_bank=bank,
            budget=budget,
        )
        result_again = select_wearer_response_profiles(
            outcomes,
            wearer_ids=("wearer_a", "wearer_b"),
            profile_bank=bank,
            budget=budget,
        )

        self.assertEqual(result, result_again)
        self.assertEqual(result.investment_signature, INVESTMENT_SIGNATURE)
        self.assertEqual(
            result.selection_for("wearer_a").profile_ids,
            ("baseline", "focus/a", "focus/b", "focus/c"),
        )
        self.assertEqual(
            result.selection_for("wearer_a").required_profile_ids,
            ("focus/a", "focus/b", "focus/c"),
        )
        self.assertEqual(
            result.selection_for("wearer_b").profile_ids,
            ("baseline", "focus/a", "focus/b", "focus/c", "focus/d"),
        )
        self.assertEqual(
            result.selection_for("wearer_b").required_profile_ids,
            ("focus/a", "focus/b", "focus/c", "focus/d"),
        )

        audit = {
            (row.wearer_id, row.profile_id): row
            for row in result.audit_rows
        }
        self.assertEqual(
            audit[("wearer_a", "baseline")].reasons,
            (RESPONSE_PROFILE_BASELINE,),
        )
        self.assertIn(
            RESPONSE_PROFILE_TOP,
            audit[("wearer_a", "focus/a")].reasons,
        )
        self.assertIn(
            RESPONSE_PROFILE_CONFIDENCE_OVERLAP,
            audit[("wearer_a", "focus/b")].reasons,
        )
        self.assertIn(
            RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY,
            audit[("wearer_a", "focus/c")].reasons,
        )
        self.assertFalse(audit[("wearer_a", "focus/d")].carried)
        self.assertEqual(
            audit[("wearer_a", "focus/d")].reasons,
            (RESPONSE_PROFILE_MATERIAL_NEGATIVE,),
        )
        self.assertEqual(
            audit[("wearer_b", "focus/b")].reasons,
            (RESPONSE_PROFILE_FAILED,),
        )
        self.assertEqual(audit[("wearer_b", "focus/b")].detail, "process failed")
        self.assertEqual(
            audit[("wearer_b", "focus/c")].reasons,
            (RESPONSE_PROFILE_TIMEOUT,),
        )
        self.assertEqual(
            audit[("wearer_b", "focus/d")].reasons,
            (RESPONSE_PROFILE_UNRESOLVED,),
        )

    def test_required_evidence_over_cap_fails_closed(self) -> None:
        bank = _profile_bank("a", "b", "c")
        outcomes = (
            _passed("wearer", "baseline", 100.0),
            _passed("wearer", "focus/a", 110.0),
            _unresolved(
                "wearer",
                "focus/b",
                ResponseProfileOutcomeStatus.FAILED,
            ),
            _unresolved(
                "wearer",
                "focus/c",
                ResponseProfileOutcomeStatus.TIMEOUT,
            ),
        )

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "required response profiles exceed",
        ):
            select_wearer_response_profiles(
                outcomes,
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=ResponseProfileSelectionBudget(
                    max_profiles_per_wearer=3,
                    top_profiles_per_wearer=1,
                    confidence_sigma=0.0,
                    relative_uncertainty_margin=0.0,
                ),
            )

    def test_exact_wearer_profile_coverage_is_required(self) -> None:
        bank = _profile_bank("a")
        baseline = _passed("wearer", "baseline", 100.0)

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "cover exactly",
        ):
            select_wearer_response_profiles(
                (baseline,),
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=_small_budget(),
            )

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "must be unique",
        ):
            select_wearer_response_profiles(
                (
                    baseline,
                    baseline,
                    _passed("wearer", "focus/a", 101.0),
                ),
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=_small_budget(),
            )

    def test_each_wearer_must_use_one_frozen_physical_baseline(self) -> None:
        bank = _profile_bank("a")
        outcomes = (
            _passed("wearer", "baseline", 100.0, set_key="set/a"),
            _passed("wearer", "focus/a", 101.0, set_key="set/b"),
        )

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "frozen physical state",
        ):
            select_wearer_response_profiles(
                outcomes,
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=_small_budget(),
            )

    def test_all_outcomes_must_share_equal_investment_identity(self) -> None:
        bank = _profile_bank("a")
        outcomes = (
            _passed("wearer", "baseline", 100.0),
            _unresolved(
                "wearer",
                "focus/a",
                ResponseProfileOutcomeStatus.UNRESOLVED,
                investment_signature="equal-investment/other-v1",
            ),
        )

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "one equal-investment signature",
        ):
            select_wearer_response_profiles(
                outcomes,
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=_small_budget(),
            )

    def test_raw_candidate_evaluations_are_rejected_without_execution_provenance(self) -> None:
        bank = _profile_bank("a")
        evaluations = (
            _evaluation("wearer", "baseline", 100.0),
            _evaluation("wearer", "focus/a", 101.0),
        )

        with self.assertRaisesRegex(
            FarmingResponseSelectionError,
            "ResponseProfileOutcome",
        ):
            select_wearer_response_profiles(
                evaluations,
                wearer_ids=("wearer",),
                profile_bank=bank,
                budget=_small_budget(),
            )

    def test_unknown_error_on_the_best_profile_keeps_all_competitors(self) -> None:
        bank = _profile_bank("a", "b", "c")
        outcomes = (
            _passed("wearer", "baseline", 100.0, error=0.1),
            _passed("wearer", "focus/a", 110.0, error=None),
            _passed("wearer", "focus/b", 1.0, error=0.1),
            _passed("wearer", "focus/c", 0.0, error=0.1),
        )

        result = select_wearer_response_profiles(
            outcomes,
            wearer_ids=("wearer",),
            profile_bank=bank,
            budget=ResponseProfileSelectionBudget(
                max_profiles_per_wearer=4,
                top_profiles_per_wearer=1,
                confidence_sigma=2.0,
                relative_uncertainty_margin=0.0,
            ),
        )

        self.assertEqual(
            result.selection_for("wearer").profile_ids,
            ("baseline", "focus/a"),
        )
        reasons = {
            row.profile_id: row.reasons
            for row in result.audit_rows
        }
        self.assertIn(RESPONSE_PROFILE_UNKNOWN_UNCERTAINTY, reasons["focus/a"])
        self.assertIn(RESPONSE_PROFILE_MATERIAL_NEGATIVE, reasons["focus/b"])
        self.assertIn(RESPONSE_PROFILE_MATERIAL_NEGATIVE, reasons["focus/c"])

    def test_proven_equal_profiles_are_dropped_as_immaterial_without_hardcoding(self) -> None:
        bank = _profile_bank("a", "b", "c", "d")
        outcomes = tuple(
            _passed("wearer", profile_id, 100.0, error=0.0)
            for profile_id in ("baseline", "focus/a", "focus/b", "focus/c", "focus/d")
        )

        result = select_wearer_response_profiles(
            outcomes,
            wearer_ids=("wearer",),
            profile_bank=bank,
            budget=ResponseProfileSelectionBudget(
                max_profiles_per_wearer=2,
                top_profiles_per_wearer=1,
                confidence_sigma=2.0,
                practical_materiality_relative=0.005,
            ),
        )

        self.assertEqual(result.selection_for("wearer").profile_ids, ("baseline",))
        self.assertTrue(
            all(
                row.reasons == (RESPONSE_PROFILE_IMMATERIAL,)
                for row in result.audit_rows
                if row.profile_id != "baseline"
            )
        )

    def test_result_provenance_changes_with_frozen_physical_state(self) -> None:
        bank = _profile_bank("a")
        first = select_wearer_response_profiles(
            (
                _passed("wearer", "baseline", 100.0, set_key="set/a"),
                _passed("wearer", "focus/a", 101.0, set_key="set/a"),
            ),
            wearer_ids=("wearer",),
            profile_bank=bank,
            budget=_small_budget(),
        )
        second = select_wearer_response_profiles(
            (
                _passed("wearer", "baseline", 100.0, set_key="set/b"),
                _passed("wearer", "focus/a", 101.0, set_key="set/b"),
            ),
            wearer_ids=("wearer",),
            profile_bank=bank,
            budget=_small_budget(),
        )

        self.assertNotEqual(first, second)
        self.assertNotEqual(first.outcome_domain_sha256, second.outcome_domain_sha256)
        self.assertNotEqual(first.provenance_sha256, second.provenance_sha256)
        self.assertEqual(first.frozen_states[0].set_key, "set/a")

        changed_metrics = select_wearer_response_profiles(
            (
                _passed("wearer", "baseline", 100.0, set_key="set/a"),
                _passed("wearer", "focus/a", 102.0, set_key="set/a"),
            ),
            wearer_ids=("wearer",),
            profile_bank=bank,
            budget=_small_budget(),
        )
        self.assertNotEqual(
            first.outcome_domain_sha256,
            changed_metrics.outcome_domain_sha256,
        )
        forged_rows = (
            first.audit_rows[0],
            replace(first.audit_rows[1], expected_dps=999.0),
        )
        with self.assertRaisesRegex(ValueError, "outcome_domain_sha256"):
            replace(first, audit_rows=forged_rows)
        with self.assertRaisesRegex(ValueError, "baseline profile|outside profile_ids"):
            replace(
                first,
                selections=(
                    WearerProfileSelection("wearer", ("evil/profile",)),
                ),
            )

    def test_outcome_rejects_mismatched_passed_provenance(self) -> None:
        evaluation = _evaluation("wearer", "baseline", 100.0)

        with self.assertRaisesRegex(ValueError, "candidate does not match"):
            ResponseProfileOutcome(
                candidate=_candidate("wearer", "focus/a"),
                status=ResponseProfileOutcomeStatus.PASSED,
                investment_signature=INVESTMENT_SIGNATURE,
                comparison_context_sha256=COMPARISON_CONTEXT_SHA256,
                request_identity_sha256=_request_identity("wearer", "focus/a"),
                evaluation=evaluation,
            )
        with self.assertRaisesRegex(ValueError, "investment signature"):
            ResponseProfileOutcome(
                candidate=evaluation.candidate,
                status=ResponseProfileOutcomeStatus.PASSED,
                investment_signature="equal-investment/other-v1",
                comparison_context_sha256=COMPARISON_CONTEXT_SHA256,
                request_identity_sha256=_request_identity("wearer", "baseline"),
                evaluation=evaluation,
            )


def _profile_bank(*axis_keys: str):
    return generate_stat_profile_bank(
        tuple(StatAxis(axis_key, 1.0) for axis_key in axis_keys),
        include_balanced=False,
    )


def _small_budget() -> ResponseProfileSelectionBudget:
    return ResponseProfileSelectionBudget(
        max_profiles_per_wearer=2,
        top_profiles_per_wearer=1,
        confidence_sigma=0.0,
        relative_uncertainty_margin=0.0,
    )


def _candidate(
    wearer_id: str,
    profile_id: str,
    *,
    set_key: str = "frozen_set",
) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=wearer_id,
            set_key=set_key,
            main_stat_layout_id="layout/frozen",
        ),
        profile_id=profile_id,
    )


def _evaluation(
    wearer_id: str,
    profile_id: str,
    expected_dps: float,
    *,
    error: float | None = 0.0,
    set_key: str = "frozen_set",
    investment_signature: str = INVESTMENT_SIGNATURE,
) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate=_candidate(wearer_id, profile_id, set_key=set_key),
        expected_dps=expected_dps,
        investment_signature=investment_signature,
        standard_error=error,
    )


def _passed(
    wearer_id: str,
    profile_id: str,
    expected_dps: float,
    *,
    error: float | None = 0.0,
    set_key: str = "frozen_set",
    investment_signature: str = INVESTMENT_SIGNATURE,
) -> ResponseProfileOutcome:
    return ResponseProfileOutcome.from_evaluation(
        _evaluation(
            wearer_id,
            profile_id,
            expected_dps,
            error=error,
            set_key=set_key,
            investment_signature=investment_signature,
        ),
        comparison_context_sha256=COMPARISON_CONTEXT_SHA256,
        request_identity_sha256=_request_identity(
            wearer_id,
            profile_id,
            set_key=set_key,
        ),
    )


def _unresolved(
    wearer_id: str,
    profile_id: str,
    status: ResponseProfileOutcomeStatus,
    *,
    detail: str = "",
    investment_signature: str = INVESTMENT_SIGNATURE,
) -> ResponseProfileOutcome:
    return ResponseProfileOutcome(
        candidate=_candidate(wearer_id, profile_id),
        status=status,
        investment_signature=investment_signature,
        comparison_context_sha256=COMPARISON_CONTEXT_SHA256,
        request_identity_sha256=_request_identity(wearer_id, profile_id),
        detail=detail,
    )


def _request_identity(
    wearer_id: str,
    profile_id: str,
    *,
    set_key: str = "frozen_set",
) -> str:
    return hashlib.sha256(
        f"{wearer_id}|{set_key}|{profile_id}".encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
