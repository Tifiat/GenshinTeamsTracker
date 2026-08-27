from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    RotationFormulaMode,
    TraceDocument,
    compile_rotation_formula_filters,
    evaluate_rotation_formula_filter,
)

from test_ranking import (
    _document,
    _duplicate_hit_document,
    _with_amplifying_reaction,
)
from test_state_evidence_v6 import _decode, _v6_fixture


class CoarseRotationObjectiveTests(unittest.TestCase):
    def test_standard_and_fast_are_explicit_parallel_modes(self) -> None:
        filters = compile_rotation_formula_filters(_document())

        standard = filters.objective(RotationFormulaMode.STANDARD)
        fast = filters.objective(RotationFormulaMode.FAST)

        self.assertNotEqual(standard.objective_sha256, fast.objective_sha256)
        self.assertEqual(fast.standard_objective_sha256, standard.objective_sha256)
        self.assertAlmostEqual(fast.baseline_damage, standard.baseline_damage)

    def test_identical_hits_fold_into_activation_rate_and_weighted_scale(self) -> None:
        filters = compile_rotation_formula_filters(
            _duplicate_hit_document(_document())
        )
        fast = filters.fast
        actor = fast.actor_formulas[0]
        channel = actor.normal_channels[0]

        self.assertEqual(channel.event_count, 2)
        self.assertIsNone(channel.activation_rate_per_second)
        self.assertEqual(fast.coarse_channel_count, 1)

        replacements = (
            ArtifactStatReplacement("hero", "atk%", 0.0, 0.25),
        )
        standard_score = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.STANDARD, replacements
        )
        fast_score = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.FAST, replacements
        )
        self.assertAlmostEqual(
            fast_score.candidate_damage,
            standard_score.candidate_damage,
        )

    def test_different_engine_attack_tags_are_not_folded_together(self) -> None:
        document = _duplicate_with_type(_document(), attack_tag=999)

        fast = compile_rotation_formula_filters(document).fast

        self.assertEqual(fast.coarse_channel_count, 2)
        self.assertEqual(
            {channel.attack_tag for channel in fast.actor_formulas[0].normal_channels},
            {1, 999},
        )

    def test_unknown_damage_type_is_not_folded_without_hardcoding(self) -> None:
        document = _duplicate_with_type(_document(), element="future-unknown-type")

        fast = compile_rotation_formula_filters(document).fast

        self.assertEqual(fast.coarse_channel_count, 2)
        self.assertEqual(
            {
                channel.damage_type_key
                for channel in fast.actor_formulas[0].normal_channels
            },
            {"anemo", "future-unknown-type"},
        )

    def test_fast_amplifying_channel_responds_to_em(self) -> None:
        filters = compile_rotation_formula_filters(
            _with_amplifying_reaction(_document())
        )
        baseline = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.FAST, ()
        )
        changed = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            (ArtifactStatReplacement("hero", "em", 0.0, 300.0),),
        )

        self.assertGreater(changed.candidate_damage, baseline.candidate_damage)
        self.assertEqual(changed.engine_call_count, 0)
        self.assertFalse(changed.authoritative)

    def test_nested_v6_source_is_reduced_to_fast_response_slope(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = _decode(request, raw, binding)
        filters = compile_rotation_formula_filters(trace)
        replacements = (
            ArtifactStatReplacement("furina", "hp%", 0.0, 0.0496),
        )

        baseline = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.FAST, ()
        )
        changed = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.FAST, replacements
        )

        self.assertGreater(changed.candidate_damage, baseline.candidate_damage)
        self.assertIn(("furina", "hp%"), filters.fast.relevant_coordinates)


def _duplicate_with_type(
    document: TraceDocument,
    *,
    attack_tag: int | None = None,
    element: str | None = None,
) -> TraceDocument:
    hit = document.hits[0]
    duplicate = replace(
        hit,
        event_id=f"{hit.event_id}:different-type",
        frame=hit.frame + 1,
        attack_tag=hit.attack_tag if attack_tag is None else attack_tag,
        element=hit.element if element is None else element,
    )
    return TraceDocument.build(
        request=document.request,
        hits=(hit, duplicate),
        topology=document.topology,
    )


if __name__ == "__main__":
    unittest.main()
