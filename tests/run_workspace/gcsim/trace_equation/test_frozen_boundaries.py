from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    CandidateStatCoordinate,
    ExactFinalistObservation,
    TraceContractError,
    TraceDocument,
    canonical_json,
    decode_engine_trace,
    build_candidate_dependency_slice,
    reconcile_exact_finalist,
    score_with_frozen_boundaries,
)

from test_contracts import _document
from test_ranking import (
    _with_amplifying_reaction,
    _with_unresolved_flat_damage,
)
from test_state_evidence_v6 import _v6_fixture


class FrozenBoundaryScoringTests(unittest.TestCase):
    def test_fully_known_formula_reconciles_without_frozen_exposure(self) -> None:
        score = score_with_frozen_boundaries(
            _document(),
            (_replacement("atk%", 0.20, 0.25),),
        )

        self.assertTrue(score.orderable)
        self.assertFalse(score.publishable)
        self.assertFalse(score.hard_prune_allowed)
        self.assertEqual(score.engine_call_count, 0)
        self.assertTrue(score.coverage.baseline_reconciled)
        self.assertAlmostEqual(score.coverage.whole_frozen_share, 0.0)
        self.assertAlmostEqual(score.coverage.frozen_input_exposure_share, 0.0)
        self.assertAlmostEqual(score.coverage.topology_exposure_share, 0.0)
        self.assertTrue(score.coverage.fully_modeled_response)
        self.assertGreater(score.estimated_delta, 0.0)

    def test_partial_frozen_input_keeps_known_crit_response(self) -> None:
        document = _with_unresolved_flat_damage(_document(), 100.0)
        score = score_with_frozen_boundaries(
            document,
            (_replacement("cr", 0.5, 0.6),),
        )

        self.assertTrue(score.orderable)
        self.assertGreater(score.estimated_delta, 0.0)
        self.assertAlmostEqual(score.coverage.whole_frozen_share, 0.0)
        self.assertAlmostEqual(
            score.coverage.frozen_input_exposure_share,
            1.0,
        )
        self.assertTrue(score.coverage.baseline_reconciled)
        self.assertIn(
            "flat_damage_dependency_unresolved",
            score.coverage.hits[0].input_uncertainty_codes,
        )

    def test_small_whole_frozen_slice_does_not_block_numeric_ranking(self) -> None:
        document = _mixed_document(modeled_count=3, frozen_count=1)
        score = score_with_frozen_boundaries(
            document,
            (_replacement("atk%", 0.20, 0.25),),
        )

        self.assertTrue(score.orderable)
        self.assertGreater(score.estimated_delta, 0.0)
        self.assertGreater(score.coverage.whole_frozen_share, 0.0)
        self.assertLess(score.coverage.whole_frozen_share, 0.5)
        self.assertFalse(score.coverage.majority_whole_frozen)
        self.assertTrue(score.coverage.baseline_reconciled)

    def test_majority_and_fully_frozen_inputs_still_return_best_effort(self) -> None:
        majority = score_with_frozen_boundaries(
            _mixed_document(modeled_count=1, frozen_count=3),
            (_replacement("atk%", 0.20, 0.25),),
        )
        fully = score_with_frozen_boundaries(
            _mixed_document(modeled_count=0, frozen_count=2),
            (_replacement("atk%", 0.20, 0.25),),
        )

        self.assertTrue(majority.orderable)
        self.assertTrue(majority.coverage.majority_whole_frozen)
        self.assertGreater(majority.estimated_delta, 0.0)
        self.assertTrue(fully.orderable)
        self.assertAlmostEqual(fully.coverage.whole_frozen_share, 1.0)
        self.assertAlmostEqual(fully.estimated_delta, 0.0)
        self.assertTrue(fully.coverage.baseline_reconciled)

    def test_schedule_uncertainty_is_separate_from_frozen_damage(self) -> None:
        score = score_with_frozen_boundaries(
            _with_amplifying_reaction(_document()),
            (_replacement("em", 0.0, 300.0),),
        )

        self.assertGreater(score.estimated_delta, 0.0)
        self.assertAlmostEqual(score.coverage.whole_frozen_share, 0.0)
        self.assertAlmostEqual(score.coverage.topology_exposure_share, 1.0)
        self.assertTrue(
            any(
                "reaction_schedule_assumed_fixed" in row.topology_uncertainty_codes
                for row in score.coverage.hits
            )
        )

    def test_exact_finalist_residual_measures_only_post_ranking_observation(self) -> None:
        score = score_with_frozen_boundaries(
            _document(),
            (_replacement("atk%", 0.20, 0.25),),
        )
        observation = ExactFinalistObservation(
            candidate_sha256=score.candidate_sha256,
            exact_baseline_damage=score.baseline_estimate + 5.0,
            exact_candidate_damage=score.candidate_estimate + 8.0,
            fidelity_sha256="a" * 64,
            seed_panel_sha256="b" * 64,
        )

        residual = reconcile_exact_finalist(score, observation)

        self.assertAlmostEqual(residual.baseline_missed_response, 5.0)
        self.assertAlmostEqual(residual.candidate_missed_response, 8.0)
        self.assertAlmostEqual(residual.change_in_missed_response, 3.0)
        self.assertEqual(residual.engine_call_count, 0)

    def test_v6_candidate_slice_separates_reachable_from_trace_wide_exposure(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

        score = score_with_frozen_boundaries(
            trace,
            (
                ArtifactStatReplacement(
                    actor_key="furina",
                    stat_key="hp%",
                    baseline_artifact_value=0.0,
                    candidate_artifact_value=0.0496,
                ),
            ),
        )

        self.assertIsNotNone(score.coverage.candidate_dependency_slice_sha256)
        self.assertGreater(score.coverage.candidate_affected_hit_count, 0)
        self.assertGreater(score.coverage.candidate_reachable_boundary_count, 0)
        self.assertGreater(score.coverage.candidate_unresolved_boundary_count, 0)
        self.assertLessEqual(
            score.coverage.candidate_reachable_frozen_input_damage,
            score.coverage.frozen_input_exposed_damage,
        )
        self.assertLessEqual(
            score.coverage.candidate_reachable_topology_damage,
            score.coverage.topology_exposed_damage,
        )

    def test_prebuilt_candidate_slice_must_match_replacement_coordinates(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        wrong_slice = build_candidate_dependency_slice(
            trace,
            (CandidateStatCoordinate("furina", "cr"),),
        )

        with self.assertRaisesRegex(
            TraceContractError,
            "coordinates do not match replacements",
        ):
            score_with_frozen_boundaries(
                trace,
                (
                    ArtifactStatReplacement(
                        actor_key="furina",
                        stat_key="hp%",
                        baseline_artifact_value=0.0,
                        candidate_artifact_value=0.0496,
                    ),
                ),
                candidate_dependency_slice=wrong_slice,
            )


def _replacement(
    stat_key: str,
    baseline: float,
    candidate: float,
) -> ArtifactStatReplacement:
    return ArtifactStatReplacement(
        actor_key="hero",
        stat_key=stat_key,
        baseline_artifact_value=baseline,
        candidate_artifact_value=candidate,
    )


def _mixed_document(*, modeled_count: int, frozen_count: int) -> TraceDocument:
    baseline = _document()
    frozen = _with_unresolved_flat_damage(baseline, 100.0)
    rows = []
    for index in range(modeled_count):
        rows.append(
            replace(
                baseline.hits[0],
                event_id=f"hit:modeled:{index}",
                frame=baseline.hits[0].frame + index,
            )
        )
    for index in range(frozen_count):
        sequence = modeled_count + index
        rows.append(
            replace(
                frozen.hits[0],
                event_id=f"hit:frozen:{index}",
                frame=baseline.hits[0].frame + sequence,
            )
        )
    return TraceDocument.build(
        request=baseline.request,
        hits=tuple(rows),
        topology=baseline.topology,
    )


if __name__ == "__main__":
    unittest.main()
