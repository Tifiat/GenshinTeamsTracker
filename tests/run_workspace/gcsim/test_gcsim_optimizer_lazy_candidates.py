from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_lazy_candidates import (
    GcsimOptimizerCandidateResponseModel,
    GcsimOptimizerCandidateRetentionPolicy,
    GcsimOptimizerCandidateStatThreshold,
    GcsimOptimizerCandidateStatWeight,
    GcsimOptimizerLazyCandidateError,
    build_gcsim_optimizer_lazy_wearer_candidate_generator,
)
from run_workspace.gcsim.optimizer_main_response import (
    GcsimOptimizerResponseBranch,
    GcsimOptimizerResponseBranchKind,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerMinimumStatConstraint,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerLazyCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        self.target = self.environment.targets[0]
        self.branch = GcsimOptimizerResponseBranch(
            wearer=self.target.wearer,
            package=self.target.package,
            layout=GcsimFiveStarMainStatLayout(
                sands="atk%",
                goblet="pyro%",
                circlet="cr",
            ),
            kind=GcsimOptimizerResponseBranchKind.DAMAGE,
            focus_axes=("cr",),
            reasons=("material_roll_exchange",),
            evidence_probe_sha256s=("a" * 64,),
        )
        self.response_model = GcsimOptimizerCandidateResponseModel(
            response_branch=self.branch,
            stat_weights=(
                GcsimOptimizerCandidateStatWeight("cr", "1"),
            ),
        )

    def test_public_facade_exports_milestone_five_boundary(self) -> None:
        expected = {
            "GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION",
            "GcsimOptimizerCandidateResponseModel",
            "GcsimOptimizerLazyWearerCandidateGenerator",
            "build_gcsim_optimizer_lazy_wearer_candidate_generator",
            "materialize_gcsim_optimizer_artifact_stat_vector",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_exact_top_k_matches_exhaustive_reduced_fixture(self) -> None:
        generator = self._generator()

        batch = generator.take(100)
        actual = tuple(
            candidate.assignment.artifact_ids
            for candidate in batch.candidates
        )
        shared = self.environment.shared_goblet_id
        expected = (
            (1, 2, 3, 4, 10),
            (1, 2, 3, 4, 11),
            (1, 2, 3, 9, 5),
            (1, 2, 8, 4, 5),
            (1, 7, 3, 4, 5),
            (6, 2, 3, 4, 5),
            (1, 2, 3, 4, 5),
            (1, 2, 3, shared, 5),
        )

        self.assertEqual(actual, expected)
        self.assertTrue(batch.exhausted)
        self.assertEqual(
            tuple(
                Decimal(item.proposal_score)
                for item in batch.candidates
            ),
            tuple(
                sorted(
                    (
                        Decimal(item.proposal_score)
                        for item in batch.candidates
                    ),
                    reverse=True,
                )
            ),
        )

    def test_first_leader_does_not_materialize_deferred_losing_states(self) -> None:
        batch = self._generator().take(2)

        self.assertEqual(len(batch.candidates), 2)
        self.assertEqual(batch.coverage.materialized_candidate_count, 2)
        self.assertGreater(batch.coverage.deferred_state_count, 0)
        self.assertIsNotNone(batch.next_upper_bound)
        self.assertLess(
            Decimal(batch.next_upper_bound),
            Decimal(batch.candidates[-1].proposal_score),
        )

    def test_shape_quotas_retain_5p_and_every_offpiece_slot(self) -> None:
        batch = self._generator().take_retained(
            GcsimOptimizerCandidateRetentionPolicy(
                leader_count=1,
                per_offpiece_shape_count=1,
            )
        )

        self.assertEqual(
            {item.offpiece_shape for item in batch.candidates},
            {"5p", "flower", "plume", "sands", "goblet", "circlet"},
        )

    def test_crit_quota_survives_a_non_crit_response_leader(self) -> None:
        em_model = GcsimOptimizerCandidateResponseModel(
            response_branch=self.branch,
            stat_weights=(
                GcsimOptimizerCandidateStatWeight("em", "1"),
            ),
        )
        batch = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            self.environment.run_input,
            target=self.target,
            response_model=em_model,
        ).take_retained(
            GcsimOptimizerCandidateRetentionPolicy(
                leader_count=1,
                per_offpiece_shape_count=0,
                useful_stat_count=0,
                crit_value_count=1,
            )
        )

        self.assertEqual(len(batch.candidates), 2)
        self.assertEqual(
            {
                item.assignment.artifact_ids_by_slot["goblet"]
                for item in batch.candidates
            },
            {4, self.environment.shared_goblet_id},
        )
        self.assertTrue(
            any(
                "quota:crit_value" in item.feature_labels
                for item in batch.candidates
            )
        )

    def test_threshold_critical_low_crit_candidate_survives(self) -> None:
        response_model = GcsimOptimizerCandidateResponseModel(
            response_branch=self.branch,
            stat_weights=(
                GcsimOptimizerCandidateStatWeight("cr", "1"),
            ),
            thresholds=(
                GcsimOptimizerCandidateStatThreshold(
                    "em",
                    minimum="100",
                ),
            ),
        )
        batch = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            self.environment.run_input,
            target=self.target,
            response_model=response_model,
        ).take(10)

        self.assertEqual(len(batch.candidates), 1)
        candidate = batch.candidates[0]
        self.assertEqual(
            candidate.assignment.artifact_ids_by_slot["goblet"],
            self.environment.shared_goblet_id,
        )
        self.assertIn("threshold:em", candidate.feature_labels)
        self.assertGreater(
            batch.coverage.threshold_feasibility_pruned,
            0,
        )

    def test_request_minimum_stat_prunes_before_materialization(self) -> None:
        request = replace(
            self.environment.request,
            minimum_stat_constraints=(
                GcsimOptimizerMinimumStatConstraint(
                    wearer=self.target.wearer,
                    axis_key="em",
                    minimum="100",
                ),
            ),
        )
        run_input_result = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=self.environment.shell,
            artifact_database=self.environment.database,
            engine_context=self.environment.engine,
        )
        self.assertTrue(run_input_result.ready)
        run_input = run_input_result.run_input
        assert run_input is not None

        batch = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            run_input,
            target=self.target,
            response_model=self.response_model,
        ).take(10)

        self.assertEqual(len(batch.candidates), 1)
        self.assertEqual(
            batch.candidates[0].assignment.artifact_ids_by_slot["goblet"],
            self.environment.shared_goblet_id,
        )
        self.assertIn(
            "threshold:em",
            batch.candidates[0].feature_labels,
        )
        self.assertGreater(batch.coverage.threshold_feasibility_pruned, 0)
        self.assertEqual(
            batch.coverage.materialized_candidate_count,
            1,
        )

    def test_floor_counts_engine_proved_unconditional_two_piece_stat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = Path("internal/artifacts/oraclesetalpha/set.go")
            source = root / relative
            source.parent.mkdir(parents=True)
            source.write_text(
                """
package oraclesetalpha
func NewSet(char *character.CharWrapper, count int) {
    if count >= 2 {
        m := make([]float64, attributes.EndStatType)
        m[attributes.ER] = 0.20
        char.AddStatMod(character.StatMod{
            Base: modifier.NewBase("oracle-er-2pc", -1),
            AffectedStat: attributes.ER,
            Amount: func() []float64 { return m },
        })
    }
    if count >= 4 {}
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            capabilities = list(self.environment.engine.catalog.sets)
            capabilities[0] = replace(
                capabilities[0],
                source_files=(relative.as_posix(),),
            )
            catalog = replace(
                self.environment.engine.catalog,
                source_root=str(root),
                sets=tuple(capabilities),
            )
            engine = replace(self.environment.engine, catalog=catalog)
            request = replace(
                self.environment.request,
                minimum_stat_constraints=(
                    GcsimOptimizerMinimumStatConstraint(
                        wearer=self.target.wearer,
                        axis_key="er",
                        minimum="0.2",
                    ),
                ),
            )
            run_input_result = build_gcsim_optimizer_run_input(
                request=request,
                config_shell=self.environment.shell,
                artifact_database=self.environment.database,
                engine_context=engine,
            )
            too_high_request = replace(
                request,
                minimum_stat_constraints=(
                    GcsimOptimizerMinimumStatConstraint(
                        wearer=self.target.wearer,
                        axis_key="er",
                        minimum="0.21",
                    ),
                ),
            )
            too_high_result = build_gcsim_optimizer_run_input(
                request=too_high_request,
                config_shell=self.environment.shell,
                artifact_database=self.environment.database,
                engine_context=engine,
            )

        self.assertTrue(run_input_result.ready)
        run_input = run_input_result.run_input
        assert run_input is not None
        self.assertEqual(
            tuple(
                (item.set_key, item.semantic_terms)
                for item in run_input.guaranteed_two_piece_stat_effects
            ),
            (("oraclesetalpha", (("ER", "0.2"),)),),
        )
        batch = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            run_input,
            target=self.target,
            response_model=self.response_model,
        ).take(1)
        self.assertEqual(len(batch.candidates), 1)

        too_high_input = too_high_result.run_input
        assert too_high_input is not None
        rejected = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            too_high_input,
            target=self.target,
            response_model=self.response_model,
        ).take(1)
        self.assertFalse(rejected.candidates)

    def test_conflict_repair_uses_dominated_physical_shadow(self) -> None:
        generator = self._generator()
        leader = generator.take(1).candidates[0]

        repaired = generator.request_conflict_repair(
            blocked_artifact_ids=(
                leader.assignment.artifact_ids_by_slot["circlet"],
            ),
            count=1,
        )

        self.assertEqual(
            repaired.candidates[0].assignment.artifact_ids_by_slot["circlet"],
            11,
        )
        self.assertEqual(
            repaired.candidates[0].content_fingerprint,
            leader.content_fingerprint,
        )
        self.assertIn(
            "shadow_alternative",
            repaired.candidates[0].feature_labels,
        )
        self.assertGreater(repaired.coverage.shadow_artifact_count, 0)
        self.assertEqual(repaired.coverage.conflict_repair_request_count, 1)
        self.assertEqual(repaired.coverage.conflict_blocked_artifact_count, 1)

    def test_database_row_order_does_not_change_stream(self) -> None:
        canonical = self._generator().take(100)
        reversed_rows = tuple(
            reversed(self.environment.run_input.artifact_database.artifacts)
        )
        reordered = build_gcsim_optimizer_lazy_wearer_candidate_generator(
            self.environment.run_input,
            target=self.target,
            response_model=self.response_model,
            artifact_rows=reversed_rows,
        ).take(100)

        self.assertEqual(
            tuple(item.candidate_sha256 for item in canonical.candidates),
            tuple(item.candidate_sha256 for item in reordered.candidates),
        )

    def test_rejects_non_permutation_and_non_4p_target(self) -> None:
        rows = self.environment.run_input.artifact_database.artifacts[:-1]
        with self.assertRaisesRegex(
            GcsimOptimizerLazyCandidateError,
            "exact permutation",
        ):
            build_gcsim_optimizer_lazy_wearer_candidate_generator(
                self.environment.run_input,
                target=self.target,
                response_model=self.response_model,
                artifact_rows=rows,
            )

    def _generator(self):
        return build_gcsim_optimizer_lazy_wearer_candidate_generator(
            self.environment.run_input,
            target=self.target,
            response_model=self.response_model,
        )


if __name__ == "__main__":
    unittest.main()
