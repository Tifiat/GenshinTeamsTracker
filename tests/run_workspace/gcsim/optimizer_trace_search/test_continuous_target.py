from __future__ import annotations

import itertools
import unittest

from run_workspace.gcsim.artifact_investment_rules import (
    ARTIFACT_INVESTMENT_RULES_SHA256,
    FIVE_STAR_MAX_ROLLS_PER_ARTIFACT,
    FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER,
    FIVE_STAR_SUBSTAT_ROLL_RULES,
    ROLL_VALUE_QUALITIES,
    five_star_substat_coordinate_cap,
)
from run_workspace.gcsim.optimizer_trace_search import (
    ContinuousMainStatLane,
    ContinuousTargetConfig,
    MainStatSelection,
    solve_continuous_main_stat_lanes,
    solve_continuous_target,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    ArtifactVariableObjective,
    CoarseActorFormula,
    CoarseNormalChannel,
    ScalingKind,
    evaluate_artifact_variable_objective,
)


class ArtifactInvestmentRulesTests(unittest.TestCase):
    def test_confirmed_five_star_roll_table_and_budget(self) -> None:
        self.assertEqual(ROLL_VALUE_QUALITIES, (0.7, 0.8, 0.9, 1.0))
        self.assertEqual(FIVE_STAR_MAX_ROLLS_PER_ARTIFACT, 9)
        self.assertEqual(FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER, 45)
        self.assertEqual(
            FIVE_STAR_SUBSTAT_ROLL_RULES["hp"].values,
            (209.13, 239.00, 268.88, 298.75),
        )
        self.assertEqual(
            FIVE_STAR_SUBSTAT_ROLL_RULES["atk%"].values,
            (0.0408, 0.0466, 0.0525, 0.0583),
        )
        self.assertEqual(
            FIVE_STAR_SUBSTAT_ROLL_RULES["cr"].values,
            (0.0272, 0.0311, 0.0350, 0.0389),
        )
        self.assertEqual(
            FIVE_STAR_SUBSTAT_ROLL_RULES["cd"].values,
            (0.0544, 0.0622, 0.0699, 0.0777),
        )
        self.assertEqual(len(ARTIFACT_INVESTMENT_RULES_SHA256), 64)

    def test_main_stat_exclusion_reduces_coordinate_cap(self) -> None:
        no_crit_main = ("hp", "atk", "atk%", "anemo%", "cd")
        crit_circlet = ("hp", "atk", "atk%", "anemo%", "cr")
        self.assertEqual(
            five_star_substat_coordinate_cap("cr", no_crit_main),
            30.0,
        )
        self.assertEqual(
            five_star_substat_coordinate_cap("cr", crit_circlet),
            24.0,
        )


class ContinuousTargetTests(unittest.TestCase):
    def test_target_obeys_budget_and_has_no_authority_or_engine_calls(self) -> None:
        objective = _attack_objective()
        lane = _lane("attack", "hero", "atk%", "anemo%", "cr")
        result = solve_continuous_target(
            objective,
            lane,
            ContinuousTargetConfig(roll_units_per_wearer=20.0),
        )

        self.assertLessEqual(result.spent_roll_units, 20.0)
        self.assertEqual(result.engine_call_count, 0)
        self.assertEqual(result.target_score.engine_call_count, 0)
        self.assertFalse(result.authoritative)
        self.assertFalse(result.prune_authority)
        self.assertGreater(result.target_score.candidate_damage, 0.0)
        self.assertGreater(result.evaluation_count, 0)
        self.assertTrue(result.curve)

    def test_crit_cap_redirects_later_rolls(self) -> None:
        objective = _attack_objective(raw_crit_rate=0.05, crit_damage=0.50)
        lane = _lane("crit-cap", "hero", "atk%", "anemo%", "cr")
        result = solve_continuous_target(
            objective,
            lane,
            ContinuousTargetConfig(roll_units_per_wearer=45.0),
        )
        units = {(row.actor_key, row.stat_key): row.roll_units for row in result.allocations}

        self.assertGreater(units.get(("hero", "cd"), 0.0), 0.0)
        self.assertLess(units.get(("hero", "cr"), 0.0), 20.0)
        self.assertNotIn(("hero", "def%"), units)

    def test_discrete_damage_bonus_lane_beats_second_attack_main(self) -> None:
        objective = _attack_objective(raw_crit_rate=0.50, crit_damage=1.00)
        attack_goblet = _lane("atk-goblet", "hero", "atk%", "atk%", "cr")
        bonus_goblet = _lane("bonus-goblet", "hero", "atk%", "anemo%", "cr")

        ranked = solve_continuous_main_stat_lanes(
            objective,
            (attack_goblet, bonus_goblet),
            ContinuousTargetConfig(roll_units_per_wearer=12.0),
        )

        self.assertEqual(ranked[0].lane_id, "bonus-goblet")
        self.assertGreater(
            ranked[0].target_score.candidate_damage,
            ranked[1].target_score.candidate_damage,
        )

    def test_hp_scaling_and_amplifying_em_are_discovered_from_formula(self) -> None:
        hp_objective = _single_channel_objective(
            scaling_kind=ScalingKind.HP,
            damage_type_key="hydro",
            element_bonus_key="hydro%",
        )
        hp_lane = _lane("hp", "hero", "hp%", "hydro%", "cr")
        hp_result = solve_continuous_target(
            hp_objective,
            hp_lane,
            ContinuousTargetConfig(roll_units_per_wearer=12.0),
        )
        hp_stats = {row.stat_key for row in hp_result.allocations}
        self.assertTrue({"hp", "hp%"} & hp_stats)
        self.assertFalse({"atk", "atk%"} & hp_stats)

        amp_objective = _single_channel_objective(
            scaling_kind=ScalingKind.ATTACK,
            damage_type_key="pyro",
            element_bonus_key="pyro%",
            amplifying=True,
            average_elemental_mastery=0.0,
        )
        amp_lane = _lane("amp", "hero", "atk%", "pyro%", "cr")
        amp_result = solve_continuous_target(
            amp_objective,
            amp_lane,
            ContinuousTargetConfig(roll_units_per_wearer=20.0),
        )
        amp_units = {row.stat_key: row.roll_units for row in amp_result.allocations}
        self.assertGreater(amp_units.get("em", 0.0), 0.0)

    def test_teamwide_formula_can_allocate_rolls_to_support(self) -> None:
        carry = _normal_channel(
            actor_key="carry",
            scaling_kind=ScalingKind.ATTACK,
            damage_type_key="anemo",
            element_bonus_key="anemo%",
            flat_response_slopes=(("support", "hp%", 15000.0),),
        )
        objective = _objective(
            (
                _actor("carry", carry),
                _actor("support", None),
            )
        )
        lane = ContinuousMainStatLane.build(
            "team",
            _selections("carry", "atk%", "anemo%", "cr")
            + _selections("support", "hp%", "hp%", "heal"),
        )
        result = solve_continuous_target(
            objective,
            lane,
            ContinuousTargetConfig(roll_units_per_wearer=6.0),
        )
        units = {(row.actor_key, row.stat_key): row.roll_units for row in result.allocations}
        self.assertGreater(units.get(("support", "hp%"), 0.0), 0.0)

    def test_small_integer_roll_domain_matches_exhaustive_best(self) -> None:
        objective = _attack_objective(raw_crit_rate=0.25, crit_damage=0.75)
        lane = _lane("small-domain", "hero", "atk%", "anemo%", "cr")
        result = solve_continuous_target(
            objective,
            lane,
            ContinuousTargetConfig(
                roll_units_per_wearer=4.0,
                allocation_step=1.0,
                exchange_step=1.0,
            ),
        )

        best_exhaustive = -1.0
        main_values = {
            (row.actor_key, row.stat_key): row.value
            for row in lane.main_stat_vector.values
        }
        for atk_units, cr_units in itertools.product(range(5), repeat=2):
            cd_units = 4 - atk_units - cr_units
            if cd_units < 0:
                continue
            values = dict(main_values)
            values[("hero", "atk%")] = values.get(("hero", "atk%"), 0.0) + (
                FIVE_STAR_SUBSTAT_ROLL_RULES["atk%"].maximum * atk_units
            )
            values[("hero", "cr")] = values.get(("hero", "cr"), 0.0) + (
                FIVE_STAR_SUBSTAT_ROLL_RULES["cr"].maximum * cr_units
            )
            values[("hero", "cd")] = values.get(("hero", "cd"), 0.0) + (
                FIVE_STAR_SUBSTAT_ROLL_RULES["cd"].maximum * cd_units
            )
            score = evaluate_artifact_variable_objective(
                objective,
                _vector(values),
            )
            best_exhaustive = max(best_exhaustive, score.candidate_damage)

        self.assertAlmostEqual(
            result.target_score.candidate_damage,
            best_exhaustive,
            places=7,
        )


def _lane(
    lane_id: str,
    actor_key: str,
    sands: str,
    goblet: str,
    circlet: str,
) -> ContinuousMainStatLane:
    return ContinuousMainStatLane.build(
        lane_id,
        _selections(actor_key, sands, goblet, circlet),
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


def _attack_objective(
    *,
    raw_crit_rate: float = 0.05,
    crit_damage: float = 0.50,
) -> ArtifactVariableObjective:
    return _single_channel_objective(
        scaling_kind=ScalingKind.ATTACK,
        damage_type_key="anemo",
        element_bonus_key="anemo%",
        raw_crit_rate=raw_crit_rate,
        crit_damage=crit_damage,
    )


def _single_channel_objective(
    *,
    scaling_kind: ScalingKind,
    damage_type_key: str,
    element_bonus_key: str,
    raw_crit_rate: float = 0.05,
    crit_damage: float = 0.50,
    amplifying: bool = False,
    average_elemental_mastery: float = 0.0,
) -> ArtifactVariableObjective:
    channel = _normal_channel(
        actor_key="hero",
        scaling_kind=scaling_kind,
        damage_type_key=damage_type_key,
        element_bonus_key=element_bonus_key,
        raw_crit_rate=raw_crit_rate,
        crit_damage=crit_damage,
        amplifying=amplifying,
        average_elemental_mastery=average_elemental_mastery,
    )
    return _objective((_actor("hero", channel),))


def _normal_channel(
    *,
    actor_key: str,
    scaling_kind: ScalingKind,
    damage_type_key: str,
    element_bonus_key: str,
    raw_crit_rate: float = 0.05,
    crit_damage: float = 0.50,
    amplifying: bool = False,
    average_elemental_mastery: float = 0.0,
    flat_response_slopes: tuple[tuple[str, str, float], ...] = (),
) -> CoarseNormalChannel:
    channel = CoarseNormalChannel(
        actor_key=actor_key,
        attack_tag=1,
        damage_type_key=damage_type_key,
        response_coordinates=(),
        scaling_kind=scaling_kind,
        amplifying=amplifying,
        event_count=1,
        activation_rate_per_second=1.0,
        average_scaling_value=1000.0,
        average_scaling_base=1000.0,
        average_scale_coefficient=1.0,
        average_flat_damage=0.0,
        flat_response_slopes=flat_response_slopes,
        average_damage_bonus=0.0,
        element_bonus_weights=((element_bonus_key, 1.0),),
        average_raw_crit_rate=raw_crit_rate,
        average_crit_damage=crit_damage,
        weak_point_fraction=0.0,
        average_post_multiplier=1.0,
        average_elemental_mastery=average_elemental_mastery,
        average_amp_multiplier=1.5,
        average_reaction_bonus=0.0,
        baseline_damage=0.0,
        calibration=1.0,
        unresolved_input_event_count=0,
    )
    return channel


def _actor(
    actor_key: str,
    channel: CoarseNormalChannel | None,
) -> CoarseActorFormula:
    channels = () if channel is None else (channel,)
    baseline = sum(row.evaluate({}) for row in channels)
    return CoarseActorFormula(
        actor_key=actor_key,
        normal_channels=channels,
        reaction_channel=None,
        frozen_damage=0.0,
        baseline_damage=baseline,
    )


def _objective(
    actors: tuple[CoarseActorFormula, ...],
) -> ArtifactVariableObjective:
    baseline = sum(actor.evaluate({}) for actor in actors)
    coordinates = tuple(
        sorted(
            {
                coordinate
                for actor in actors
                for coordinate in actor.relevant_coordinates
            }
        )
    )
    return ArtifactVariableObjective(
        objective_sha256="1" * 64,
        fast_objective_sha256="2" * 64,
        evidence_sha256="3" * 64,
        character_keys=tuple(actor.actor_key for actor in actors),
        duration_frames=60,
        fixed_actor_formulas=actors,
        incumbent_artifact_vector=ArtifactStatVector(()),
        baseline_damage=baseline,
        fixed_context_damage=baseline,
        relevant_coordinates=coordinates,
    )


def _vector(values: dict[tuple[str, str], float]) -> ArtifactStatVector:
    return ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, value)
            for (actor, stat), value in values.items()
            if value > 0.0
        )
    )


if __name__ == "__main__":
    unittest.main()
