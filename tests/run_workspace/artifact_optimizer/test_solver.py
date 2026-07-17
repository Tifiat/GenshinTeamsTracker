from __future__ import annotations

import itertools
import random
import unittest

from run_workspace.artifact_optimizer import (
    ArtifactOptimizationRequest,
    ArtifactSetRequirement,
    OptimizerArtifact,
    optimize_artifacts,
)


CRIT_RATE = 20


class ArtifactOptimizerSolverTest(unittest.TestCase):
    def test_exact_search_returns_deterministic_top_builds(self) -> None:
        artifacts = _two_candidates_per_position()

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                top_k=3,
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
        )

        self.assertEqual(
            [candidate.artifact_ids() for candidate in report.candidates],
            [
                (2, 4, 6, 8, 10),
                (1, 4, 6, 8, 10),
                (2, 3, 6, 8, 10),
            ],
        )
        self.assertEqual(
            [candidate.score for candidate in report.candidates],
            [20.0, 19.0, 19.0],
        )
        self.assertTrue(report.diagnostics.search_complete)
        self.assertEqual(report.diagnostics.quality, "exact")

    def test_four_piece_requirement_keeps_one_off_piece(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(pos * 10 + 1, pos, "set-a", 5.0),
                    _artifact(pos * 10 + 2, pos, "set-b", 10.0),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                set_requirements=(ArtifactSetRequirement("set-a", 4),),
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
        )

        best = report.candidates[0]
        self.assertEqual(
            dict((item.set_key, item.count) for item in best.set_counts),
            {"set-a": 4, "set-b": 1},
        )
        self.assertEqual(best.score, 30.0)
        self.assertGreater(report.diagnostics.set_requirement_pruned_branches, 0)

    def test_two_plus_two_requirements_are_enforced(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(pos * 10 + 1, pos, "set-a", 4.0),
                    _artifact(pos * 10 + 2, pos, "set-b", 3.0),
                    _artifact(pos * 10 + 3, pos, "set-c", 20.0),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                set_requirements=(
                    ArtifactSetRequirement("set-a", 2),
                    ArtifactSetRequirement("set-b", 2),
                ),
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
        )

        counts = {
            item.set_key: item.count for item in report.candidates[0].set_counts
        }
        self.assertEqual(counts["set-a"], 2)
        self.assertEqual(counts["set-b"], 2)
        self.assertEqual(counts["set-c"], 1)

    def test_minimum_stat_filter_prunes_impossible_branches(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(pos * 10 + 1, pos, "set-a", 1.0),
                    _artifact(pos * 10 + 2, pos, "set-b", 10.0),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                minimum_stats={CRIT_RATE: 49.0},
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
        )

        self.assertEqual(report.candidates[0].score, 50.0)
        self.assertEqual(len(report.candidates), 1)
        self.assertGreater(report.diagnostics.minimum_stat_pruned_branches, 0)

    def test_fixed_excluded_main_stat_and_equipment_filters_compose(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(
                        pos * 10 + 1,
                        pos,
                        "set-a",
                        5.0,
                        main_property_type=6,
                    ),
                    _artifact(
                        pos * 10 + 2,
                        pos,
                        "set-b",
                        10.0,
                        main_property_type=9,
                        equipped_character_ids=(200,),
                    ),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                fixed_artifact_ids_by_pos={1: 11},
                excluded_artifact_ids=frozenset({32}),
                allowed_main_stats_by_pos={2: frozenset({6})},
                allow_equipped_artifacts=False,
                target_character_id=100,
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
        )

        self.assertEqual(report.candidates[0].artifact_ids(), (11, 21, 31, 41, 51))
        self.assertEqual(len(set(report.candidates[0].artifact_ids())), 5)

    def test_shortlist_preserves_per_set_candidates_and_reports_best_found(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(pos * 100 + 1, pos, "required", 1.0),
                    _artifact(pos * 100 + 2, pos, "other", 20.0),
                    _artifact(pos * 100 + 3, pos, "other", 19.0),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                set_requirements=(ArtifactSetRequirement("required", 4),),
                per_slot_limit=1,
                per_set_limit=1,
                max_combinations=None,
            ),
        )

        self.assertTrue(report.candidates)
        self.assertTrue(report.diagnostics.candidate_pool_truncated)
        self.assertFalse(report.diagnostics.search_complete)
        self.assertEqual(report.diagnostics.quality, "best_found")

    def test_per_set_shortlist_can_be_used_without_global_shortlist(self) -> None:
        artifacts = []
        for pos in range(1, 6):
            artifacts.extend(
                [
                    _artifact(pos * 100 + 1, pos, "set-a", 1.0),
                    _artifact(pos * 100 + 2, pos, "set-a", 2.0),
                    _artifact(pos * 100 + 3, pos, "set-b", 3.0),
                    _artifact(pos * 100 + 4, pos, "set-b", 4.0),
                ]
            )

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                per_slot_limit=None,
                per_set_limit=1,
                max_combinations=None,
            ),
        )

        self.assertEqual(
            dict(report.diagnostics.candidate_counts_after_shortlist),
            {1: 2, 2: 2, 3: 2, 4: 2, 5: 2},
        )
        self.assertTrue(report.diagnostics.candidate_pool_truncated)

    def test_combination_cap_is_visible_in_diagnostics(self) -> None:
        report = optimize_artifacts(
            _two_candidates_per_position(),
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=1,
            ),
        )

        self.assertTrue(report.diagnostics.stopped_by_combination_limit)
        self.assertFalse(report.diagnostics.search_complete)
        self.assertEqual(report.diagnostics.complete_builds_considered, 1)

    def test_optional_final_evaluator_reranks_proxy_pool(self) -> None:
        artifacts = _two_candidates_per_position()

        def prefer_low_ids(candidate, _artifacts_by_id) -> float:
            return -float(sum(candidate.artifact_ids()))

        report = optimize_artifacts(
            artifacts,
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                top_k=1,
                rerank_pool_size=32,
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
            final_evaluator=prefer_low_ids,
        )

        self.assertEqual(report.candidates[0].artifact_ids(), (1, 3, 5, 7, 9))
        self.assertEqual(report.diagnostics.reranked_builds, 32)

    def test_bounded_final_evaluator_does_not_claim_exact_result(self) -> None:
        report = optimize_artifacts(
            _two_candidates_per_position(),
            ArtifactOptimizationRequest(
                weights={CRIT_RATE: 1.0},
                top_k=1,
                rerank_pool_size=2,
                per_slot_limit=None,
                per_set_limit=None,
                max_combinations=None,
            ),
            final_evaluator=lambda candidate, _artifacts: candidate.score,
        )

        self.assertFalse(report.diagnostics.search_complete)
        self.assertEqual(report.diagnostics.quality, "best_found")

    def test_duplicate_stat_dimension_is_rejected(self) -> None:
        artifacts = _two_candidates_per_position()
        artifacts[0] = OptimizerArtifact(
            artifact_id=1,
            pos=1,
            set_key="set-a",
            stats=((CRIT_RATE, 1.0), (CRIT_RATE, 2.0)),
        )

        with self.assertRaisesRegex(ValueError, "repeats stat"):
            optimize_artifacts(
                artifacts,
                ArtifactOptimizationRequest(weights={CRIT_RATE: 1.0}),
            )

    def test_exact_solver_matches_bruteforce_on_small_random_inventories(self) -> None:
        rng = random.Random(20260717)
        for case_index in range(20):
            artifacts = []
            pools = []
            artifact_id = 1
            for pos in range(1, 6):
                pool = []
                for _ in range(3):
                    artifact = OptimizerArtifact(
                        artifact_id=artifact_id,
                        pos=pos,
                        set_key=rng.choice(("set-a", "set-b", "set-c")),
                        stats=(
                            (CRIT_RATE, float(rng.randrange(0, 11))),
                            (23, float(rng.randrange(0, 11))),
                        ),
                    )
                    artifact_id += 1
                    artifacts.append(artifact)
                    pool.append(artifact)
                pools.append(pool)

            minimum_er = float(rng.randrange(10, 31))
            report = optimize_artifacts(
                artifacts,
                ArtifactOptimizationRequest(
                    weights={CRIT_RATE: 2.0, 23: 0.5},
                    top_k=7,
                    minimum_stats={23: minimum_er},
                    set_requirements=(ArtifactSetRequirement("set-a", 2),),
                    per_slot_limit=None,
                    per_set_limit=None,
                    max_combinations=None,
                ),
            )

            expected = []
            for build in itertools.product(*pools):
                if sum(artifact.set_key == "set-a" for artifact in build) < 2:
                    continue
                energy_recharge = sum(
                    artifact.stat_value(23) for artifact in build
                )
                if energy_recharge < minimum_er:
                    continue
                crit_rate = sum(
                    artifact.stat_value(CRIT_RATE) for artifact in build
                )
                score = crit_rate * 2.0 + energy_recharge * 0.5
                expected.append(
                    (score, tuple(artifact.artifact_id for artifact in build))
                )
            expected.sort(key=lambda item: (-item[0], item[1]))

            self.assertEqual(
                [
                    (candidate.score, candidate.artifact_ids())
                    for candidate in report.candidates
                ],
                expected[:7],
                msg=f"random inventory case {case_index}",
            )
            self.assertTrue(report.diagnostics.search_complete)


def _two_candidates_per_position() -> list[OptimizerArtifact]:
    result = []
    for pos in range(1, 6):
        result.extend(
            [
                _artifact(pos * 2 - 1, pos, "set-a", float(pos)),
                _artifact(pos * 2, pos, "set-b", float(pos + 1)),
            ]
        )
    return result


def _artifact(
    artifact_id: int,
    pos: int,
    set_key: str,
    crit_rate: float,
    *,
    main_property_type: int = 6,
    equipped_character_ids: tuple[int, ...] = (),
) -> OptimizerArtifact:
    return OptimizerArtifact(
        artifact_id=artifact_id,
        pos=pos,
        set_key=set_key,
        set_uid=set_key,
        set_name=set_key,
        main_property_type=main_property_type,
        stats=((CRIT_RATE, crit_rate),),
        equipped_character_ids=equipped_character_ids,
    )


if __name__ == "__main__":
    unittest.main()
