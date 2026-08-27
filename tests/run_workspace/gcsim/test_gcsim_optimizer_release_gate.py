from __future__ import annotations

from decimal import Decimal
import hashlib
import unittest

from run_workspace.gcsim.optimizer_oracle import GcsimOptimizerOraclePruningStage
from run_workspace.gcsim.optimizer_release_gate import (
    GcsimOptimizerProvisionalReleasePolicy,
    GcsimOptimizerQualityCase,
    GcsimOptimizerQualityRank,
    GcsimOptimizerReleaseGateError,
    GcsimOptimizerRuntimeEvidence,
    GcsimOptimizerRuntimeKind,
    assess_gcsim_optimizer_release,
    build_gcsim_optimizer_release_gate_report,
    measure_gcsim_optimizer_quality_case,
)


def _identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GcsimOptimizerReleaseGateTest(unittest.TestCase):
    def test_exact_reduced_ranking_passes_strict_gate(self) -> None:
        identities = tuple(_identity(str(index)) for index in range(4))
        stages = (
            GcsimOptimizerOraclePruningStage("legality", identities),
            GcsimOptimizerOraclePruningStage("finalists", identities[:3]),
        )
        case = GcsimOptimizerQualityCase(
            case_id="exact_fixture",
            oracle_ranking=tuple(
                GcsimOptimizerQualityRank(identity, Decimal(100 - index * 10))
                for index, identity in enumerate(identities)
            ),
            production_ranking_sha256s=identities[:3],
            pruning_stages=stages,
            top_n=3,
        )

        metrics = measure_gcsim_optimizer_quality_case(case)
        report = build_gcsim_optimizer_release_gate_report((case,))

        self.assertTrue(metrics.strict_gate_passed)
        self.assertEqual(metrics.top_n_recall, Decimal(1))
        self.assertEqual(metrics.best_dps_regret, Decimal(0))
        self.assertTrue(report.strict_gate_passed)

    def test_miss_records_regret_recall_and_first_removal_stage(self) -> None:
        identities = tuple(_identity(str(index)) for index in range(4))
        case = GcsimOptimizerQualityCase(
            case_id="miss_fixture",
            oracle_ranking=tuple(
                GcsimOptimizerQualityRank(identity, Decimal(100 - index * 10))
                for index, identity in enumerate(identities)
            ),
            production_ranking_sha256s=(identities[1], identities[3]),
            pruning_stages=(
                GcsimOptimizerOraclePruningStage("legality", identities),
                GcsimOptimizerOraclePruningStage("bound", identities[1:]),
                GcsimOptimizerOraclePruningStage("finalists", identities[1:3]),
            ),
            top_n=3,
        )

        metrics = measure_gcsim_optimizer_quality_case(case)

        self.assertFalse(metrics.strict_gate_passed)
        self.assertEqual(metrics.oracle_winner_removed_at_stage, "bound")
        self.assertEqual(metrics.top_n_recall, Decimal(1) / Decimal(3))
        self.assertEqual(metrics.best_dps_regret, Decimal(10))
        self.assertEqual(metrics.best_dps_regret_ratio, Decimal("0.1"))
        self.assertEqual(metrics.maximum_rankwise_dps_miss, Decimal(80))

    def test_user_approved_provisional_policy_is_typed_and_serialized(
        self,
    ) -> None:
        policy = GcsimOptimizerProvisionalReleasePolicy()

        self.assertTrue(policy.provisional)
        self.assertEqual(
            policy.selected_cold_first_saveable_seconds,
            Decimal("150"),
        )
        self.assertEqual(
            policy.selected_cold_terminal_seconds,
            Decimal("300"),
        )
        self.assertEqual(
            policy.theoretical_cold_terminal_seconds,
            Decimal("180"),
        )
        self.assertEqual(
            policy.randomized_exact_top1_rate,
            Decimal("0.95"),
        )
        self.assertEqual(
            policy.randomized_mean_regret_ratio,
            Decimal("0.005"),
        )
        self.assertEqual(
            policy.randomized_maximum_regret_ratio,
            Decimal("0.02"),
        )
        self.assertEqual(
            policy.runtime_limit(
                GcsimOptimizerRuntimeKind.SELECTED_WARM_TERMINAL
            ),
            Decimal("30"),
        )
        self.assertEqual(policy.to_dict()["provisional"], True)

    def test_complete_evidence_passes_provisional_assessment(self) -> None:
        exact = _quality_case("exact")

        assessment = assess_gcsim_optimizer_release(
            mandatory_cases=(exact,),
            randomized_cases=tuple(
                _quality_case(f"random_{index}") for index in range(20)
            ),
            runtime_evidence=_runtime_evidence(),
        )

        self.assertTrue(assessment.passed)
        self.assertTrue(assessment.mandatory_quality_passed)
        self.assertTrue(assessment.randomized_quality_passed)
        self.assertTrue(assessment.runtime_passed)
        self.assertEqual(assessment.missing_runtime_kinds, ())
        self.assertEqual(assessment.over_limit_runtime_kinds, ())

    def test_recorded_real_runtime_matrix_is_within_provisional_limits(
        self,
    ) -> None:
        exact = _quality_case("recorded_runtime_fixture")

        assessment = assess_gcsim_optimizer_release(
            mandatory_cases=(exact,),
            randomized_cases=(exact,),
            runtime_evidence=_recorded_runtime_evidence(),
        )

        self.assertTrue(assessment.runtime_passed)
        self.assertEqual(assessment.missing_runtime_kinds, ())
        self.assertEqual(assessment.over_limit_runtime_kinds, ())

    def test_missing_or_slow_runtime_and_random_miss_fail_gate(self) -> None:
        exact = _quality_case("mandatory")
        missed = _quality_case("random_miss", miss=True)
        runtime = tuple(
            item
            for item in _runtime_evidence()
            if item.kind
            is not GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_WARM_TERMINAL
        )
        runtime = tuple(
            GcsimOptimizerRuntimeEvidence(
                item.kind,
                Decimal("301")
                if item.kind
                is GcsimOptimizerRuntimeKind.SELECTED_COLD_TERMINAL
                else item.elapsed_seconds,
            )
            for item in runtime
        )

        assessment = assess_gcsim_optimizer_release(
            mandatory_cases=(exact,),
            randomized_cases=(missed,),
            runtime_evidence=runtime,
        )

        self.assertFalse(assessment.passed)
        self.assertFalse(assessment.randomized_quality_passed)
        self.assertFalse(assessment.runtime_passed)
        self.assertEqual(
            assessment.missing_runtime_kinds,
            (
                GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_WARM_TERMINAL,
            ),
        )
        self.assertEqual(
            assessment.over_limit_runtime_kinds,
            (GcsimOptimizerRuntimeKind.SELECTED_COLD_TERMINAL,),
        )

    def test_duplicate_runtime_kind_fails_closed(self) -> None:
        exact = _quality_case("exact")
        duplicate = GcsimOptimizerRuntimeEvidence(
            GcsimOptimizerRuntimeKind.SELECTED_WARM_TERMINAL,
            Decimal("1"),
        )

        with self.assertRaisesRegex(
            GcsimOptimizerReleaseGateError,
            "unique",
        ):
            assess_gcsim_optimizer_release(
                mandatory_cases=(exact,),
                randomized_cases=(exact,),
                runtime_evidence=(*_runtime_evidence(), duplicate),
            )


def _quality_case(case_id: str, *, miss: bool = False):
    identities = (_identity(f"{case_id}:winner"), _identity(f"{case_id}:second"))
    production = tuple(reversed(identities)) if miss else identities
    return GcsimOptimizerQualityCase(
        case_id=case_id,
        oracle_ranking=(
            GcsimOptimizerQualityRank(identities[0], Decimal("100")),
            GcsimOptimizerQualityRank(identities[1], Decimal("99")),
        ),
        production_ranking_sha256s=production,
        pruning_stages=(
            GcsimOptimizerOraclePruningStage("production", production),
        ),
        top_n=1,
    )


def _runtime_evidence():
    elapsed = {
        GcsimOptimizerRuntimeKind.SELECTED_COLD_FIRST_SAVEABLE: "120",
        GcsimOptimizerRuntimeKind.SELECTED_COLD_TERMINAL: "240",
        GcsimOptimizerRuntimeKind.SELECTED_WARM_TERMINAL: "20",
        GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_COLD_TERMINAL: "120",
        GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_WARM_TERMINAL: "15",
        GcsimOptimizerRuntimeKind.THEORETICAL_TWO_PLUS_TWO_COLD_TERMINAL: "120",
        GcsimOptimizerRuntimeKind.THEORETICAL_TWO_PLUS_TWO_WARM_TERMINAL: "15",
    }
    return tuple(
        GcsimOptimizerRuntimeEvidence(kind, Decimal(value))
        for kind, value in elapsed.items()
    )


def _recorded_runtime_evidence():
    elapsed = {
        GcsimOptimizerRuntimeKind.SELECTED_COLD_FIRST_SAVEABLE: "117.64",
        GcsimOptimizerRuntimeKind.SELECTED_COLD_TERMINAL: "236.859",
        GcsimOptimizerRuntimeKind.SELECTED_WARM_TERMINAL: "20.000",
        GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_COLD_TERMINAL: (
            "106.36"
        ),
        GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_WARM_TERMINAL: (
            "6.234"
        ),
        GcsimOptimizerRuntimeKind.THEORETICAL_TWO_PLUS_TWO_COLD_TERMINAL: (
            "124.00"
        ),
        GcsimOptimizerRuntimeKind.THEORETICAL_TWO_PLUS_TWO_WARM_TERMINAL: (
            "11.594"
        ),
    }
    return tuple(
        GcsimOptimizerRuntimeEvidence(kind, Decimal(value))
        for kind, value in elapsed.items()
    )


if __name__ == "__main__":
    unittest.main()
