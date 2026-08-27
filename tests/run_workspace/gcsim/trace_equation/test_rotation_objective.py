from __future__ import annotations

import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    compile_rotation_objective,
    evaluate_rotation_objective,
    score_observed_artifact_replacement,
)

from test_ranking import (
    _document,
    _duplicate_hit_document,
    _with_amplifying_reaction,
    _with_scaling,
    _with_unresolved_flat_damage,
)
from test_state_evidence_v6 import _decode, _v6_fixture
from run_workspace.gcsim.trace_equation import ScalingKind


class RotationObjectiveTests(unittest.TestCase):
    def test_duplicate_identical_hits_compile_to_one_group(self) -> None:
        document = _duplicate_hit_document(_document())

        objective = compile_rotation_objective(document)
        score = evaluate_rotation_objective(objective, ())

        self.assertEqual(objective.source_hit_count, 2)
        self.assertEqual(objective.group_count, 1)
        self.assertTrue(objective.compilation_preserves_baseline)
        self.assertAlmostEqual(score.candidate_damage, objective.baseline_damage)
        self.assertEqual(score.engine_call_count, 0)
        self.assertFalse(score.authoritative)

    def test_crit_cap_matches_detailed_expected_value(self) -> None:
        document = _document()
        objective = compile_rotation_objective(document)
        replacements = (
            ArtifactStatReplacement("hero", "cd", 0.0, 0.25),
            ArtifactStatReplacement("hero", "cr", 0.0, 0.75),
        )

        compact = evaluate_rotation_objective(objective, replacements)
        detailed = score_observed_artifact_replacement(document, replacements)

        self.assertAlmostEqual(
            compact.candidate_damage,
            detailed.ranking.candidate_score or 0.0,
        )
        self.assertIn(("hero", "cr"), objective.relevant_coordinates)
        self.assertIn(("hero", "cd"), objective.relevant_coordinates)

    def test_scaling_and_amplifying_em_match_detailed_score(self) -> None:
        cases = (
            (
                _with_scaling(
                    _document(),
                    ScalingKind.HP,
                    {"base_hp": 10000.0, "hp": 1000.0, "hp%": 0.2},
                ),
                (ArtifactStatReplacement("hero", "hp%", 0.0, 0.25),),
            ),
            (
                _with_amplifying_reaction(_document()),
                (ArtifactStatReplacement("hero", "em", 0.0, 300.0),),
            ),
        )
        for document, replacements in cases:
            with self.subTest(stat=replacements[0].stat_key):
                objective = compile_rotation_objective(document)
                compact = evaluate_rotation_objective(objective, replacements)
                detailed = score_observed_artifact_replacement(document, replacements)
                self.assertAlmostEqual(
                    compact.candidate_damage,
                    detailed.ranking.candidate_score or 0.0,
                )

    def test_unresolved_flat_scaling_change_freezes_like_detailed_score(self) -> None:
        document = _with_unresolved_flat_damage(_document(), 100.0)
        objective = compile_rotation_objective(document)
        replacements = (
            ArtifactStatReplacement("hero", "atk%", 0.0, 0.25),
        )

        compact = evaluate_rotation_objective(objective, replacements)
        detailed = score_observed_artifact_replacement(document, replacements)

        self.assertAlmostEqual(
            compact.candidate_damage,
            detailed.ranking.candidate_score or 0.0,
        )
        self.assertEqual(compact.fallback_hit_count, 1)

    def test_nested_source_flat_damage_matches_v6_detailed_score(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = _decode(request, raw, binding)
        objective = compile_rotation_objective(trace)
        replacements = (
            ArtifactStatReplacement("furina", "hp%", 0.0, 0.0496),
        )

        compact = evaluate_rotation_objective(objective, replacements)
        detailed = score_observed_artifact_replacement(trace, replacements)

        self.assertAlmostEqual(
            compact.candidate_damage,
            detailed.ranking.candidate_score or 0.0,
        )
        self.assertIn(("furina", "hp%"), objective.relevant_coordinates)


if __name__ == "__main__":
    unittest.main()
