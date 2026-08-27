from __future__ import annotations

from decimal import Decimal
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.optimizer_account_oracle import (
    run_gcsim_optimizer_account_four_piece_oracle,
)
from run_workspace.gcsim.optimizer_oracle import (
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
    GcsimOptimizerReducedOracleLimits,
)

from ._optimizer_oracle_fixtures import (
    build_oracle_account_environment,
)


class GcsimOptimizerAccountFourPieceOracleTests(unittest.TestCase):
    def test_public_facade_exports_milestone_three_oracles(self) -> None:
        expected = {
            "GcsimOptimizerReducedOracleLimits",
            "GcsimOptimizerOracleScore",
            "GcsimOptimizerAccountFourPieceOracleResult",
            "GcsimOptimizerTheoreticalFourPieceOracleResult",
            "audit_gcsim_optimizer_oracle_winner_survival",
            "run_gcsim_optimizer_account_four_piece_oracle",
            "run_gcsim_optimizer_theoretical_four_piece_oracle",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(
            [name for name in gcsim_api.__all__ if not hasattr(gcsim_api, name)],
            [],
        )
        namespace: dict[str, object] = {}
        exec("from run_workspace.gcsim import *", namespace)
        self.assertTrue(set(gcsim_api.__all__).issubset(namespace))

    def test_hand_checkable_domain_is_exhaustive_and_disjoint(self) -> None:
        environment = build_oracle_account_environment()
        evaluator_calls = 0

        def evaluator(candidate):
            nonlocal evaluator_calls
            evaluator_calls += 1
            coefficients = {
                "alpha": Decimal(1),
                "beta": Decimal(4),
                "gamma": Decimal(2),
                "delta": Decimal(3),
            }
            score = Decimal(0)
            for build in candidate.builds:
                stats = {
                    key: Decimal(value)
                    for key, value in build.normalized_stats
                }
                score += stats.get("cr", Decimal(0)) * Decimal(1000)
                score += (
                    stats.get("em", Decimal(0))
                    * coefficients[build.wearer.gcsim_character_key]
                )
            return GcsimOptimizerOracleScore(
                objective_name="synthetic_team_value",
                objective_value=float(score),
                evidence_sha256=candidate.compiled_config_sha256,
            )

        result = run_gcsim_optimizer_account_four_piece_oracle(
            environment.run_input,
            targets=environment.targets,
            execution_identity_sha256="e" * 64,
            evaluator=evaluator,
        )

        wearer_counts = tuple(
            item.legal_build_count for item in result.coverage.wearer_coverage
        )
        self.assertEqual(wearer_counts, (8, 7, 7, 7))
        self.assertEqual(
            tuple(
                item.raw_cartesian_assignment_count
                for item in result.coverage.wearer_coverage
            ),
            (72, 48, 48, 48),
        )
        self.assertEqual(result.coverage.joint_cartesian_state_count, 2744)
        self.assertEqual(result.coverage.joint_conflict_count, 260)
        self.assertEqual(
            result.coverage.joint_disjoint_assignment_count,
            2484,
        )
        self.assertEqual(result.coverage.equivalent_assignment_count, 324)
        self.assertEqual(result.coverage.unique_simulation_count, 2160)
        self.assertEqual(evaluator_calls, 2160)

        winner_rows = {
            row.wearer.gcsim_character_key: row
            for row in result.winner.candidate.assignment_witness.wearer_assignments
        }
        self.assertIn(
            environment.shared_goblet_id,
            winner_rows["beta"].artifact_ids,
        )
        self.assertNotIn(
            environment.shared_goblet_id,
            winner_rows["alpha"].artifact_ids,
        )
        winner_ids = tuple(
            artifact_id
            for row in winner_rows.values()
            for artifact_id in row.artifact_ids
        )
        self.assertEqual(len(winner_ids), 20)
        self.assertEqual(len(set(winner_ids)), 20)

    def test_offpiece_five_piece_malformed_and_replacements_are_audited(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        result = run_gcsim_optimizer_account_four_piece_oracle(
            environment.run_input,
            targets=environment.targets,
            execution_identity_sha256="e" * 64,
            evaluator=lambda candidate: GcsimOptimizerOracleScore(
                objective_name="stable",
                objective_value=1.0,
                evidence_sha256=candidate.compiled_config_sha256,
            ),
        )

        alpha = result.coverage.wearer_coverage[0]
        self.assertEqual(alpha.five_piece_build_count, 1)
        self.assertEqual(
            dict(alpha.offpiece_build_counts),
            {
                "flower": 1,
                "plume": 1,
                "sands": 1,
                "goblet": 2,
                "circlet": 2,
            },
        )
        for coverage in result.coverage.wearer_coverage[1:]:
            self.assertEqual(coverage.five_piece_build_count, 1)
            self.assertEqual(
                dict(coverage.offpiece_build_counts),
                {
                    "flower": 1,
                    "plume": 1,
                    "sands": 1,
                    "goblet": 2,
                    "circlet": 1,
                },
            )
        self.assertGreaterEqual(
            dict(alpha.excluded_artifact_counts)[
                "artifact_calculation_invalid"
            ],
            1,
        )
        self.assertIn(
            (
                environment.malformed_artifact_id,
                "artifact_calculation_invalid",
            ),
            alpha.excluded_artifacts,
        )
        self.assertNotIn(
            environment.malformed_artifact_id,
            {
                artifact_id
                for _slot, artifact_ids in alpha.eligible_artifact_ids_by_slot
                for artifact_id in artifact_ids
            },
        )
        replacement_buckets = tuple(
            item.witness_bucket
            for item in result.evaluations
            if item.witness_bucket.observed_assignment_count == 2
        )
        self.assertEqual(len(replacement_buckets), 324)
        self.assertTrue(
            all(len(item.stored_witnesses) == 2 for item in replacement_buckets)
        )
        duplicate_ids = set(environment.duplicate_alpha_circlet_ids)
        example = replacement_buckets[0]
        self.assertEqual(
            {
                next(
                    row.artifact_ids_by_slot["circlet"]
                    for row in witness.wearer_assignments
                    if row.wearer.team_slot == 1
                )
                for witness in example.stored_witnesses
            },
            duplicate_ids,
        )

    def test_reduced_limits_fail_before_account_sized_enumeration(self) -> None:
        environment = build_oracle_account_environment()

        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "max_legal_builds_per_wearer",
        ):
            run_gcsim_optimizer_account_four_piece_oracle(
                environment.run_input,
                targets=environment.targets,
                execution_identity_sha256="e" * 64,
                evaluator=lambda candidate: GcsimOptimizerOracleScore(
                    objective_name="unused",
                    objective_value=0.0,
                    evidence_sha256=candidate.compiled_config_sha256,
                ),
                limits=GcsimOptimizerReducedOracleLimits(
                    max_legal_builds_per_wearer=7,
                ),
            )


if __name__ == "__main__":
    unittest.main()
