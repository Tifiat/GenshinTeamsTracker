from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from run_workspace.gcsim import optimizer_anytime_candidates as candidate_kernel
from run_workspace.gcsim.optimizer_account_oracle import (
    run_gcsim_optimizer_account_four_piece_oracle,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeStatProfile,
    build_gcsim_optimizer_anytime_joint_proposals,
    build_gcsim_optimizer_coordinate_refinement_proposals,
    build_gcsim_optimizer_dense_artifact_catalog,
    build_gcsim_optimizer_uncertainty_refinement_profiles,
    generate_gcsim_optimizer_anytime_wearer_pool,
)
from run_workspace.gcsim.optimizer_oracle import (
    GcsimOptimizerOraclePruningStage,
    GcsimOptimizerOracleScore,
)
from run_workspace.gcsim.optimizer_release_gate import (
    GcsimOptimizerQualityCase,
    GcsimOptimizerQualityRank,
    measure_gcsim_optimizer_quality_case,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerAnytimeCandidateQualityTests(unittest.TestCase):
    def test_crit_cap_zero_response_gets_bounded_mixed_profiles(self) -> None:
        environment = build_oracle_account_environment()
        wearer = environment.wearers[0]
        # A local response probe taken at the CR cap can report zero marginal
        # CR utility.  That zero must mean "uncertain/non-linear", not "delete
        # CR from the exact-search domain".
        weights = tuple(
            2.0 if axis == "em" else 1.0 if axis == "cd" else 0.0
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        balanced = GcsimOptimizerAnytimeStatProfile(
            wearer=wearer,
            profile_id="balanced",
            stat_weights=weights,
            main_scores=(
                ("circlet", "cr", 0.0),
                ("goblet", "pyro%", 10.0),
            ),
            evidence_sha256="a" * 64,
            stat_classifications=tuple(
                (
                    axis,
                    "uncertain"
                    if axis == "cr"
                    else "secondary"
                    if weights[index] > 0
                    else "negligible",
                )
                for index, axis in enumerate(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                )
            ),
            main_classifications=(
                ("circlet", "cr", "uncertain"),
                ("goblet", "pyro%", "secondary"),
            ),
        )

        profiles = build_gcsim_optimizer_uncertainty_refinement_profiles(
            (balanced,)
        )

        self.assertEqual(len(profiles), 4)
        self.assertIn(
            "uncertainty_focus_em_main_pyro_pct",
            {item.profile_id for item in profiles},
        )
        cr_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("cr")
        self.assertTrue(all(item.stat_weights[cr_index] > 0 for item in profiles))
        self.assertTrue(
            all(
                "uncertainty_coordinate_refinement" in item.feature_labels
                for item in profiles
            )
        )

    def test_selected_hard_main_pool_keeps_normalized_profile_coverage(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        wearer = environment.wearers[0]
        target = environment.targets[0]
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )

        def profile(profile_id: str, axis: str, coefficient: float):
            return GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id=profile_id,
                stat_weights=tuple(
                    coefficient if item == axis else 0.0
                    for item in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_scores=(),
                evidence_sha256=(
                    "a" * 64
                    if profile_id == "selected_primary"
                    else "b" * 64
                ),
                feature_labels=(profile_id,),
            )

        pool = generate_gcsim_optimizer_anytime_wearer_pool(
            environment.run_input,
            catalog=catalog,
            wearer=wearer,
            targets=(target,),
            profiles=(
                profile("selected_primary", "cr", 1000.0),
                profile("weak_alternate", "em", 0.0001),
            ),
            hard_main_pruning=True,
            plan=GcsimOptimizerAnytimeCandidatePlan(
                max_frontier_per_group=8,
                shadow_per_group=2,
                per_profile_slot_count=4,
                max_slot_pool=32,
                wearer_beam_width=64,
                max_builds_per_target=2,
                max_builds_per_wearer=2,
                max_seconds=30.0,
            ),
        )

        self.assertEqual(len(pool.candidates), 2)
        self.assertEqual(
            {
                next(
                    label
                    for label in candidate.feature_labels
                    if label.startswith("profile:")
                )
                for candidate in pool.candidates
            },
            {"profile:selected_primary", "profile:weak_alternate"},
        )

    def test_partial_beam_keeps_a_lower_score_variable_main_layout(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        primary = next(
            artifact
            for artifact in catalog.artifacts
            if artifact.slot == "sands"
        )

        def physical_clone(artifact_id: int, main_key: str):
            return replace(
                primary,
                record=replace(primary.record, artifact_id=artifact_id),
                main_key=main_key,
            )

        alternate = physical_clone(20_000, "em")

        def state(artifact, score):
            piece = candidate_kernel._ScoredPiece(
                artifact=artifact,
                profile_scores=(score,),
                base_score=score,
                package_index=0,
            )
            return candidate_kernel._WearerBeamState(
                chosen=(piece,),
                stats=artifact.stats,
                package_counts=(1,),
                score=score,
            )

        rows = [
            state(
                physical_clone(10_000 + index, primary.main_key),
                100.0 - index,
            )
            for index in range(6)
        ]
        rows.append(state(alternate, 1.0))
        retained = candidate_kernel._retain_hybrid_wearer_beam_states(
            rows,
            limit=4,
        )

        self.assertIn(
            alternate.artifact_id,
            {
                row.chosen[0].artifact.artifact_id for row in retained
            },
        )

    def test_complete_cap_normalizes_incompatible_profile_scales(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        artifacts = catalog.artifacts[:6]

        def state(artifact, score):
            piece = candidate_kernel._ScoredPiece(
                artifact=artifact,
                profile_scores=(score, score),
                base_score=score,
                package_index=0,
            )
            return candidate_kernel._WearerBeamState(
                chosen=(piece,),
                stats=artifact.stats,
                package_counts=(1,),
                score=score,
            )

        rows = [
            (state(artifact, 10_000.0 - index), 0)
            for index, artifact in enumerate(artifacts[:3])
        ]
        rows.extend(
            (state(artifact, 1.0 - index * 0.1), 1)
            for index, artifact in enumerate(artifacts[3:])
        )
        retained = candidate_kernel._retain_hybrid_complete_states(
            rows,
            limit=2,
        )

        self.assertEqual({row[1] for row in retained}, {0, 1})

    def test_alternate_profile_reaches_the_joint_screen(self) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        plan = GcsimOptimizerAnytimeCandidatePlan(
            max_frontier_per_group=8,
            shadow_per_group=2,
            per_profile_slot_count=4,
            max_slot_pool=32,
            wearer_beam_width=64,
            max_builds_per_target=2,
            max_builds_per_wearer=2,
            joint_beam_width=32,
            max_joint_proposals=4,
            local_search_seed_count=2,
            max_seconds=30.0,
        )

        def response_profile(wearer, profile_id, axis, coefficient):
            return GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id=profile_id,
                stat_weights=tuple(
                    coefficient if item == axis else 0.0
                    for item in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_scores=(),
                evidence_sha256=(
                    "a" * 64 if profile_id == "balanced" else "b" * 64
                ),
                feature_labels=(profile_id,),
            )

        pools = []
        for index, (wearer, target) in enumerate(
            zip(
                environment.wearers,
                environment.targets,
                strict=True,
            )
        ):
            profiles = (
                (
                    response_profile(wearer, "balanced", "cr", 1000.0),
                    response_profile(
                        wearer,
                        "weak_alternate",
                        "em",
                        0.0001,
                    ),
                )
                if index == 0
                else (
                    response_profile(wearer, "balanced", "cr", 1.0),
                )
            )
            pools.append(
                generate_gcsim_optimizer_anytime_wearer_pool(
                    environment.run_input,
                    catalog=catalog,
                    wearer=wearer,
                    targets=(target,),
                    profiles=profiles,
                    hard_main_pruning=True,
                    plan=plan,
                )
            )
        proposals, _coverage = (
            build_gcsim_optimizer_anytime_joint_proposals(
                environment.run_input,
                catalog=catalog,
                wearer_pools=tuple(pools),
                plan=plan,
                execution_identity_sha256="e" * 64,
            )
        )

        self.assertTrue(proposals)
        self.assertTrue(
            any(
                "profile:weak_alternate"
                in proposal.wearer_candidates[0].feature_labels
                for proposal in proposals
            )
        )

    def test_coordinate_refinement_emits_bounded_disjoint_swaps(self) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        plan = GcsimOptimizerAnytimeCandidatePlan(
            max_frontier_per_group=8,
            shadow_per_group=2,
            per_profile_slot_count=4,
            max_slot_pool=32,
            wearer_beam_width=64,
            max_builds_per_target=3,
            max_builds_per_wearer=3,
            joint_beam_width=32,
            max_joint_proposals=4,
            local_search_seed_count=2,
            max_seconds=30.0,
        )
        pools = []
        for wearer, target in zip(
            environment.wearers,
            environment.targets,
            strict=True,
        ):
            profile = GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id="balanced",
                stat_weights=tuple(
                    1.0 if axis in {"cr", "cd"} else 0.0
                    for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_scores=(),
                evidence_sha256="a" * 64,
            )
            pools.append(
                generate_gcsim_optimizer_anytime_wearer_pool(
                    environment.run_input,
                    catalog=catalog,
                    wearer=wearer,
                    targets=(target,),
                    profiles=(profile,),
                    plan=plan,
                    hard_main_pruning=False,
                )
            )
        seeds, _coverage = build_gcsim_optimizer_anytime_joint_proposals(
            environment.run_input,
            catalog=catalog,
            wearer_pools=tuple(pools),
            plan=plan,
            execution_identity_sha256="b" * 64,
        )

        proposals = build_gcsim_optimizer_coordinate_refinement_proposals(
            environment.run_input,
            catalog=catalog,
            seed_proposals=(seeds[0],),
            wearer_pools=tuple(pools),
            execution_identity_sha256="c" * 64,
            max_candidates_per_wearer=3,
            conflict_beam_width=2,
        )

        self.assertTrue(proposals)
        self.assertLessEqual(len(proposals), 12)
        self.assertNotIn(
            seeds[0].compiled_candidate.compiled_config_sha256,
            {
                item.compiled_candidate.compiled_config_sha256
                for item in proposals
            },
        )
        for proposal in proposals:
            artifact_ids = tuple(
                artifact_id
                for candidate in proposal.wearer_candidates
                for artifact_id in candidate.assignment.artifact_ids
            )
            self.assertEqual(len(artifact_ids), len(set(artifact_ids)))

    def test_uncertain_main_survives_but_proven_negligible_main_is_pruned(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        wearer = environment.wearers[0]
        target = environment.targets[0]
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )

        def profile(pyro_classification: str):
            return GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id="main_uncertainty",
                stat_weights=(0.0,) * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES),
                main_scores=(
                    ("goblet", "hydro%", 1.0),
                    ("goblet", "pyro%", 0.0),
                ),
                main_classifications=(
                    ("goblet", "hydro%", "secondary"),
                    ("goblet", "pyro%", pyro_classification),
                ),
                evidence_sha256="9" * 64,
            )

        uncertain = generate_gcsim_optimizer_anytime_wearer_pool(
            environment.run_input,
            catalog=catalog,
            wearer=wearer,
            targets=(target,),
            profiles=(profile("uncertain"),),
            plan=GcsimOptimizerAnytimeCandidatePlan(max_seconds=30.0),
        )
        negligible = generate_gcsim_optimizer_anytime_wearer_pool(
            environment.run_input,
            catalog=catalog,
            wearer=wearer,
            targets=(target,),
            profiles=(profile("negligible"),),
            plan=GcsimOptimizerAnytimeCandidatePlan(max_seconds=30.0),
        )

        self.assertTrue(uncertain.candidates)
        self.assertFalse(negligible.candidates)

    def test_current_kernel_matches_reduced_exhaustive_account_winner(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        coefficients = (Decimal(1), Decimal(4), Decimal(2), Decimal(3))
        plan = GcsimOptimizerAnytimeCandidatePlan(max_seconds=30.0)
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        pools = tuple(
            generate_gcsim_optimizer_anytime_wearer_pool(
                environment.run_input,
                catalog=catalog,
                wearer=wearer,
                targets=(target,),
                profiles=(
                    _profile(wearer, coefficient),
                ),
                plan=plan,
            )
            for wearer, target, coefficient in zip(
                environment.wearers,
                environment.targets,
                coefficients,
                strict=True,
            )
        )
        proposals, coverage = build_gcsim_optimizer_anytime_joint_proposals(
            environment.run_input,
            catalog=catalog,
            wearer_pools=pools,
            plan=plan,
            execution_identity_sha256="e" * 64,
        )
        oracle = run_gcsim_optimizer_account_four_piece_oracle(
            environment.run_input,
            targets=environment.targets,
            execution_identity_sha256="e" * 64,
            evaluator=lambda candidate: _oracle_score(
                candidate,
                coefficients,
            ),
        )

        self.assertTrue(proposals)
        self.assertGreater(coverage.conflict_state_count, 0)
        production_ids = tuple(
            proposal.compiled_candidate.simulation_sha256
            for proposal in proposals
        )
        production_winner_ids = tuple(
            artifact_id
            for row in proposals[0].wearer_candidates
            for artifact_id in row.assignment.artifact_ids
        )
        oracle_winner_ids = tuple(
            artifact_id
            for row in (
                oracle.winner.candidate.assignment_witness.wearer_assignments
            )
            for artifact_id in row.artifact_ids
        )
        self.assertIn(
            oracle.winner_candidate_sha256,
            production_ids,
            (
                "oracle winner was removed by the anytime kernel",
                production_winner_ids,
                oracle_winner_ids,
                proposals[0].surrogate_score,
                oracle.winner.score.objective_value,
            ),
        )
        self.assertEqual(
            production_ids[0],
            oracle.winner_candidate_sha256,
        )
        winner_ids = production_winner_ids
        self.assertEqual(len(winner_ids), 20)
        self.assertEqual(len(set(winner_ids)), 20)
        self.assertIn(environment.shared_goblet_id, winner_ids)

        oracle_ranking = tuple(
            GcsimOptimizerQualityRank(
                evaluation.candidate_identity_sha256,
                Decimal(str(evaluation.score.objective_value)),
            )
            for evaluation in sorted(
                oracle.evaluations,
                key=lambda row: (
                    -row.score.objective_value,
                    row.candidate_identity_sha256,
                ),
            )
        )
        metrics = measure_gcsim_optimizer_quality_case(
            GcsimOptimizerQualityCase(
                case_id="anytime_account_reduced_oracle",
                oracle_ranking=oracle_ranking,
                production_ranking_sha256s=production_ids,
                pruning_stages=(
                    GcsimOptimizerOraclePruningStage(
                        "anytime_joint_proposals",
                        production_ids,
                    ),
                ),
                top_n=1,
            )
        )
        self.assertTrue(metrics.strict_gate_passed)
        self.assertEqual(metrics.best_dps_regret, Decimal(0))

    def test_one_exact_config_covers_multiple_marginal_targets_once(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        plan = GcsimOptimizerAnytimeCandidatePlan(max_seconds=30.0)
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        pools = tuple(
            generate_gcsim_optimizer_anytime_wearer_pool(
                environment.run_input,
                catalog=catalog,
                wearer=wearer,
                targets=(target,),
                profiles=(_profile(wearer, Decimal(1)),),
                plan=plan,
            )
            for wearer, target in zip(
                environment.wearers,
                environment.targets,
                strict=True,
            )
        )
        seed_proposals, _coverage = (
            build_gcsim_optimizer_anytime_joint_proposals(
                environment.run_input,
                catalog=catalog,
                wearer_pools=pools,
                plan=plan,
                execution_identity_sha256="e" * 64,
            )
        )
        self.assertTrue(seed_proposals)
        seed = seed_proposals[0]
        singleton_pools = tuple(
            replace(pool, candidates=(seed.wearer_candidates[index],))
            for index, pool in enumerate(pools)
        )

        proposals, coverage = build_gcsim_optimizer_anytime_joint_proposals(
            environment.run_input,
            catalog=catalog,
            wearer_pools=singleton_pools,
            marginal_required_targets=tuple(
                candidate.target for candidate in seed.wearer_candidates
            ),
            plan=plan,
            execution_identity_sha256="e" * 64,
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(coverage.marginal_required_target_count, 4)
        self.assertEqual(len(coverage.marginal_covered_targets), 4)
        self.assertEqual(coverage.marginal_coverage_proposal_count, 1)
        self.assertEqual(
            sum(
                label.startswith("marginal_package_coverage:")
                for label in proposals[0].diversity_labels
            ),
            4,
        )


def _profile(wearer, em_coefficient: Decimal):
    return GcsimOptimizerAnytimeStatProfile(
        wearer=wearer,
        profile_id="reduced_oracle",
        stat_weights=tuple(
            1000.0
            if axis == "cr"
            else float(em_coefficient)
            if axis == "em"
            else 0.0
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        ),
        main_scores=(),
        evidence_sha256="f" * 64,
        feature_labels=("reduced_oracle",),
    )


def _oracle_score(candidate, coefficients):
    score = Decimal(0)
    for build, coefficient in zip(
        candidate.builds,
        coefficients,
        strict=True,
    ):
        stats = {
            key: Decimal(value) for key, value in build.normalized_stats
        }
        score += stats.get("cr", Decimal(0)) * Decimal(1000)
        score += stats.get("em", Decimal(0)) * coefficient
    return GcsimOptimizerOracleScore(
        objective_name="anytime_reduced_oracle",
        objective_value=float(score),
        evidence_sha256=candidate.compiled_config_sha256,
    )


if __name__ == "__main__":
    unittest.main()
