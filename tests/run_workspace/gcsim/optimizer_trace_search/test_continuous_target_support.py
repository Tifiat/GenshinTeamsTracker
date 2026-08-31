from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_trace_search import (
    ContinuousGuideCandidate,
    ContinuousMainStatLane,
    ContinuousTargetConfig,
    MainStatSelection,
    rank_candidates_by_support_continuous_target,
    solve_support_aware_continuous_target,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    ArtifactVariableObjective,
    CoarseActorFormula,
    CoarseNormalChannel,
    ScalingKind,
    SupportAwareFastObjective,
    SupportAwareFastScore,
)


class SupportContinuousTargetTests(unittest.TestCase):
    def test_support_only_coordinate_can_receive_continuous_investment(self) -> None:
        objective = _support_objective()
        lane = _team_lane()
        with patch(
            "run_workspace.gcsim.optimizer_trace_search."
            "continuous_target_support.evaluate_support_aware_fast_objective",
            side_effect=_fake_support_score,
        ):
            result = solve_support_aware_continuous_target(
                objective,
                lane,
                ContinuousTargetConfig(
                    roll_units_per_wearer=4.0,
                    allocation_step=1.0,
                    exchange_step=1.0,
                ),
            )

        allocations = {
            (row.actor_key, row.stat_key): row.roll_units
            for row in result.allocations
        }
        self.assertIn(("bennett", "hp%"), result.relevant_coordinates)
        self.assertGreater(allocations.get(("bennett", "hp%"), 0.0), 0.0)
        self.assertEqual(result.engine_call_count, 0)
        self.assertFalse(result.authoritative)
        self.assertFalse(result.prune_authority)

    def test_separable_guide_ranks_target_vector_before_main_stats_only(self) -> None:
        objective = _support_objective()
        lane = _team_lane()
        with patch(
            "run_workspace.gcsim.optimizer_trace_search."
            "continuous_target_support.evaluate_support_aware_fast_objective",
            side_effect=_fake_support_score,
        ):
            target = solve_support_aware_continuous_target(
                objective,
                lane,
                ContinuousTargetConfig(
                    roll_units_per_wearer=4.0,
                    allocation_step=1.0,
                    exchange_step=1.0,
                ),
            )
            guide = rank_candidates_by_support_continuous_target(
                objective,
                (target,),
                (
                    ContinuousGuideCandidate(
                        "target-vector",
                        lane.lane_sha256,
                        target.target_artifact_vector,
                    ),
                    ContinuousGuideCandidate(
                        "main-stats-only",
                        lane.lane_sha256,
                        lane.main_stat_vector,
                    ),
                ),
            )

        self.assertEqual(guide.predictions[0].candidate_id, "target-vector")
        self.assertGreater(
            guide.predictions[0].predicted_damage,
            guide.predictions[1].predicted_damage,
        )
        self.assertGreater(guide.response_evaluation_count, 0)
        self.assertEqual(guide.engine_call_count, 0)
        self.assertFalse(guide.prune_authority)


def _team_lane() -> ContinuousMainStatLane:
    return ContinuousMainStatLane.build(
        "support-team",
        _selections("carry", "atk%", "anemo%", "cr")
        + _selections("bennett", "hp%", "hp%", "heal"),
    )


def _selections(
    actor_key: str,
    sands: str,
    goblet: str,
    circlet: str,
) -> tuple[MainStatSelection, ...]:
    return (
        MainStatSelection(actor_key, "flower", "hp"),
        MainStatSelection(actor_key, "plume", "atk"),
        MainStatSelection(actor_key, "sands", sands),
        MainStatSelection(actor_key, "goblet", goblet),
        MainStatSelection(actor_key, "circlet", circlet),
    )


def _support_objective() -> SupportAwareFastObjective:
    channel = CoarseNormalChannel(
        actor_key="carry",
        attack_tag=1,
        damage_type_key="anemo",
        response_coordinates=(),
        scaling_kind=ScalingKind.ATTACK,
        amplifying=False,
        event_count=1,
        activation_rate_per_second=1.0,
        average_scaling_value=1000.0,
        average_scaling_base=1000.0,
        average_scale_coefficient=1.0,
        average_flat_damage=0.0,
        flat_response_slopes=(),
        average_damage_bonus=0.0,
        element_bonus_weights=(("anemo%", 1.0),),
        average_raw_crit_rate=0.05,
        average_crit_damage=0.50,
        weak_point_fraction=0.0,
        average_post_multiplier=1.0,
        average_elemental_mastery=0.0,
        average_amp_multiplier=1.5,
        average_reaction_bonus=0.0,
        baseline_damage=0.0,
        calibration=1.0,
        unresolved_input_event_count=0,
    )
    carry = CoarseActorFormula(
        actor_key="carry",
        normal_channels=(channel,),
        reaction_channel=None,
        frozen_damage=0.0,
        baseline_damage=channel.evaluate({}),
    )
    bennett = CoarseActorFormula(
        actor_key="bennett",
        normal_channels=(),
        reaction_channel=None,
        frozen_damage=0.0,
        baseline_damage=0.0,
    )
    direct = ArtifactVariableObjective(
        objective_sha256="1" * 64,
        fast_objective_sha256="2" * 64,
        evidence_sha256="3" * 64,
        character_keys=("carry", "bennett"),
        duration_frames=60,
        fixed_actor_formulas=(carry, bennett),
        incumbent_artifact_vector=ArtifactStatVector(()),
        baseline_damage=carry.baseline_damage,
        fixed_context_damage=carry.baseline_damage,
        relevant_coordinates=carry.relevant_coordinates,
    )
    return SupportAwareFastObjective(
        objective_sha256="4" * 64,
        control=SimpleNamespace(),
        direct_fast=direct,
        support_coordinates=(("bennett", "hp%"),),
    )


def _fake_support_score(objective, vector, *, cache) -> SupportAwareFastScore:
    values = {
        (row.actor_key, row.stat_key): row.value for row in vector.values
    }
    carry_attack = values.get(("carry", "atk%"), 0.0)
    bennett_hp = values.get(("bennett", "hp%"), 0.0)
    damage = 1000.0 * (1.0 + carry_attack) * (1.0 + 2.0 * bennett_hp)
    key = tuple(sorted((actor, stat, value) for (actor, stat), value in values.items()))
    cache_hit = key in cache.entries
    if cache_hit:
        cache.hit_count += 1
    else:
        cache.entries[key] = object()
        cache.miss_count += 1
    return SupportAwareFastScore(
        objective_sha256=objective.objective_sha256,
        artifact_vector_sha256=vector.vector_sha256,
        baseline_damage=1000.0,
        candidate_damage=damage,
        expected_delta=damage - 1000.0,
        baseline_dps=1000.0,
        candidate_dps=damage,
        candidate_damage_by_actor=(("carry", damage), ("bennett", 0.0)),
        support_correction_damage=damage - 1000.0 * (1.0 + carry_attack),
        support_changed_hit_count=1,
        support_cache_hit=cache_hit,
        support_cache_entry_count=len(cache.entries),
        uncertainty_codes=(),
    )


if __name__ == "__main__":
    unittest.main()
