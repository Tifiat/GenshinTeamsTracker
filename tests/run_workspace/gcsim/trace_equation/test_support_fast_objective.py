from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    build_support_projection_cache,
    compile_support_aware_fast_objective,
    evaluate_artifact_variable_objective,
    evaluate_support_aware_control_objective,
    evaluate_support_aware_fast_objective,
    replay_support_state,
)

from .test_support_objective import _trace_with_hit_binding


class SupportAwareFastObjectiveTests(unittest.TestCase):
    def test_cached_support_correction_matches_single_hit_control(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        candidate = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.10),)
        )
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective)

        direct = evaluate_artifact_variable_objective(
            objective.direct_fast,
            candidate,
        )
        control = evaluate_support_aware_control_objective(
            objective.control,
            candidate,
        )
        first = evaluate_support_aware_fast_objective(
            objective,
            candidate,
            cache=cache,
        )
        second = evaluate_support_aware_fast_objective(
            objective,
            candidate,
            cache=cache,
        )

        self.assertGreater(first.support_correction_damage, 0.0)
        self.assertAlmostEqual(first.candidate_damage, control.candidate_damage)
        self.assertAlmostEqual(
            first.support_correction_damage,
            control.candidate_damage - direct.candidate_damage,
        )
        self.assertEqual(first.support_changed_hit_count, 1)
        self.assertFalse(first.support_cache_hit)
        self.assertTrue(second.support_cache_hit)
        self.assertEqual(first.candidate_damage, second.candidate_damage)
        self.assertEqual(cache.miss_count, 1)
        self.assertEqual(cache.hit_count, 1)
        self.assertEqual(first.engine_call_count, 0)
        self.assertFalse(first.authoritative)
        self.assertFalse(first.hard_prune_allowed)

    def test_cached_projection_revalues_changed_direct_damage_stats(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        support_only = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.10),)
        )
        support_plus_crit = ArtifactStatVector.build(
            (
                ArtifactStatValue("furina", "cr", 0.10),
                ArtifactStatValue("furina", "hp%", 0.10),
            )
        )
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective)

        first = evaluate_support_aware_fast_objective(
            objective,
            support_only,
            cache=cache,
        )
        second = evaluate_support_aware_fast_objective(
            objective,
            support_plus_crit,
            cache=cache,
        )
        control = evaluate_support_aware_control_objective(
            objective.control,
            support_plus_crit,
        )

        self.assertTrue(second.support_cache_hit)
        self.assertEqual(cache.miss_count, 1)
        self.assertEqual(cache.hit_count, 1)
        self.assertNotEqual(
            first.support_correction_damage,
            second.support_correction_damage,
        )
        self.assertAlmostEqual(second.candidate_damage, control.candidate_damage)

    def test_candidate_relevant_opaque_boundary_freezes_and_reports(self) -> None:
        trace = _trace_with_hit_binding(
            modifier_input_event_id="state-event:19",
            opaque_modifier_input=True,
        )
        incumbent = ArtifactStatVector(())
        candidate = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.10),)
        )
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective)

        score = evaluate_support_aware_fast_objective(
            objective,
            candidate,
            cache=cache,
        )

        self.assertAlmostEqual(score.support_correction_damage, 0.0)
        self.assertTrue(
            any(
                code == "frozen_numeric_source_expression:state-event:19"
                for code in score.uncertainty_codes
            )
        )
        self.assertFalse(score.authoritative)
        self.assertFalse(score.hard_prune_allowed)

    def test_two_candidate_actors_combine_before_one_hit_modifier(self) -> None:
        trace = _trace_with_hit_binding(multiple_providers=True)
        incumbent = ArtifactStatVector(())
        candidate = ArtifactStatVector.build(
            (
                ArtifactStatValue("bennett", "hp%", 0.10),
                ArtifactStatValue("furina", "hp%", 0.10),
            )
        )
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective)

        score = evaluate_support_aware_fast_objective(
            objective,
            candidate,
            cache=cache,
        )
        control = evaluate_support_aware_control_objective(
            objective.control,
            candidate,
        )

        self.assertGreater(score.support_correction_damage, 0.0)
        self.assertAlmostEqual(score.candidate_damage, control.candidate_damage)
        self.assertIn(("bennett", "hp%"), objective.support_coordinates)
        self.assertIn(("furina", "hp%"), objective.support_coordinates)
        self.assertEqual(score.engine_call_count, 0)

    def test_source_healing_bonus_reaches_team_damage_without_engine(self) -> None:
        trace = _trace_with_hit_binding(
            modifier_input_event_id="state-event:14",
            healing_source=True,
        )
        incumbent = ArtifactStatVector(())
        candidate = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "heal", 0.25),)
        )
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective)

        score = evaluate_support_aware_fast_objective(
            objective,
            candidate,
            cache=cache,
        )
        control = evaluate_support_aware_control_objective(
            objective.control,
            candidate,
        )
        replay = replay_support_state(trace, {("furina", "heal"): 0.25})
        healing = replay.health_operation("health-operation:1")

        self.assertIn(("furina", "heal"), objective.support_coordinates)
        self.assertAlmostEqual(healing["source_bonus"], 0.25)
        self.assertAlmostEqual(healing["base_amount"], 600.0)
        self.assertAlmostEqual(healing["raw_amount"], 750.0)
        self.assertAlmostEqual(replay.event_value("state-event:14"), 6.25)
        self.assertGreater(score.support_correction_damage, 0.0)
        self.assertAlmostEqual(score.candidate_damage, control.candidate_damage)
        self.assertEqual(score.engine_call_count, 0)

    def test_support_projection_cache_is_attempt_bounded(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        objective = compile_support_aware_fast_objective(trace, incumbent)
        cache = build_support_projection_cache(objective, max_entries=1)
        first = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.10),)
        )
        second = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.20),)
        )

        evaluate_support_aware_fast_objective(objective, first, cache=cache)
        evaluate_support_aware_fast_objective(objective, second, cache=cache)
        repeated = evaluate_support_aware_fast_objective(
            objective,
            first,
            cache=cache,
        )

        self.assertFalse(repeated.support_cache_hit)
        self.assertEqual(len(cache.entries), 1)
        self.assertEqual(cache.miss_count, 3)
        self.assertEqual(cache.eviction_count, 2)

    def test_frozen_direct_residual_is_exposed_in_score(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        objective = compile_support_aware_fast_objective(trace, incumbent)
        actor = objective.direct_fast.fixed_actor_formulas[0]
        frozen_damage = 10.0
        direct = replace(
            objective.direct_fast,
            fixed_actor_formulas=(
                replace(
                    actor,
                    frozen_damage=actor.frozen_damage + frozen_damage,
                    baseline_damage=actor.baseline_damage + frozen_damage,
                ),
            ),
            baseline_damage=objective.direct_fast.baseline_damage + frozen_damage,
            fixed_context_damage=(
                objective.direct_fast.fixed_context_damage + frozen_damage
            ),
        )
        objective = replace(objective, direct_fast=direct)
        cache = build_support_projection_cache(objective)

        score = evaluate_support_aware_fast_objective(
            objective,
            incumbent,
            cache=cache,
        )

        self.assertAlmostEqual(score.frozen_baseline_damage, frozen_damage)
        self.assertAlmostEqual(
            score.frozen_baseline_share,
            frozen_damage / direct.baseline_damage,
        )
        self.assertIn(
            "direct_fast_frozen_residual_present",
            score.uncertainty_codes,
        )


if __name__ == "__main__":
    unittest.main()
