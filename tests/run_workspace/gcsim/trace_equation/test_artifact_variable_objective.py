from __future__ import annotations

import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    RotationFormulaMode,
    ScalingKind,
    TraceContractError,
    artifact_replacements_between,
    compile_artifact_variable_objective,
    compile_rotation_formula_filters,
    evaluate_artifact_variable_objective,
    evaluate_rotation_formula_filter,
)

from test_contracts import _document
from test_ranking import _with_amplifying_reaction, _with_scaling
from test_state_evidence_v6 import _decode, _v6_fixture


class ArtifactVariableObjectiveTests(unittest.TestCase):
    def test_absolute_incumbent_and_candidate_match_delta_fast(self) -> None:
        filters = compile_rotation_formula_filters(_document())
        incumbent = _vector(
            ("hero", "anemo%", 0.20),
            ("hero", "atk", 50.0),
            ("hero", "atk%", 0.20),
            ("hero", "cd", 0.20),
            ("hero", "cr", 0.10),
        )
        candidate = _vector(
            ("hero", "anemo%", 0.10),
            ("hero", "atk", 40.0),
            ("hero", "atk%", 0.30),
            ("hero", "cd", 0.10),
            ("hero", "cr", 0.20),
        )

        objective = compile_artifact_variable_objective(filters.fast, incumbent)
        incumbent_score = evaluate_artifact_variable_objective(objective, incumbent)
        candidate_score = evaluate_artifact_variable_objective(objective, candidate)
        delta_score = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            artifact_replacements_between(incumbent, candidate),
        )

        self.assertAlmostEqual(
            incumbent_score.candidate_damage,
            filters.fast.baseline_damage,
        )
        self.assertAlmostEqual(
            candidate_score.candidate_damage,
            delta_score.candidate_damage,
        )
        self.assertEqual(candidate_score.engine_call_count, 0)
        self.assertFalse(candidate_score.authoritative)

        channel = objective.fixed_actor_formulas[0].normal_channels[0]
        self.assertAlmostEqual(channel.average_scaling_value, 1350.0)
        self.assertAlmostEqual(channel.average_damage_bonus, 0.0)
        self.assertAlmostEqual(channel.average_raw_crit_rate, 0.40)
        self.assertAlmostEqual(channel.average_crit_damage, 0.30)

    def test_empty_candidate_removes_all_incumbent_artifact_stats(self) -> None:
        filters = compile_rotation_formula_filters(_document())
        incumbent = _vector(
            ("hero", "anemo%", 0.20),
            ("hero", "atk", 100.0),
            ("hero", "atk%", 0.50),
            ("hero", "cd", 0.20),
            ("hero", "cr", 0.10),
        )
        empty = ArtifactStatVector(())
        objective = compile_artifact_variable_objective(filters.fast, incumbent)

        absolute = evaluate_artifact_variable_objective(objective, empty)
        delta = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            artifact_replacements_between(incumbent, empty),
        )

        self.assertAlmostEqual(absolute.candidate_damage, delta.candidate_damage)
        self.assertAlmostEqual(
            absolute.candidate_damage,
            objective.fixed_context_damage,
        )

    def test_endpoint_vector_is_independent_of_replacement_path(self) -> None:
        filters = compile_rotation_formula_filters(_document())
        incumbent = _vector(
            ("hero", "atk", 50.0),
            ("hero", "atk%", 0.20),
            ("hero", "cr", 0.10),
        )
        intermediate = _vector(
            ("hero", "atk", 75.0),
            ("hero", "atk%", 0.10),
            ("hero", "cr", 0.20),
        )
        candidate = _vector(
            ("hero", "atk", 25.0),
            ("hero", "atk%", 0.30),
            ("hero", "cr", 0.15),
        )
        objective = compile_artifact_variable_objective(filters.fast, incumbent)

        direct = evaluate_artifact_variable_objective(objective, candidate)
        via_intermediate_values = _apply_replacements(
            intermediate,
            artifact_replacements_between(intermediate, candidate),
        )
        via_intermediate = evaluate_artifact_variable_objective(
            objective,
            via_intermediate_values,
        )

        self.assertEqual(candidate, via_intermediate_values)
        self.assertAlmostEqual(direct.candidate_damage, via_intermediate.candidate_damage)

    def test_amplifying_em_uses_absolute_artifact_value(self) -> None:
        document = _with_amplifying_reaction(_document())
        filters = compile_rotation_formula_filters(document)
        incumbent = ArtifactStatVector(())
        candidate = _vector(("hero", "em", 200.0))
        objective = compile_artifact_variable_objective(filters.fast, incumbent)

        absolute = evaluate_artifact_variable_objective(objective, candidate)
        delta = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            artifact_replacements_between(incumbent, candidate),
        )

        self.assertAlmostEqual(absolute.candidate_damage, delta.candidate_damage)
        self.assertGreater(absolute.candidate_damage, objective.baseline_damage)

    def test_all_direct_scaling_kinds_match_delta_fast(self) -> None:
        cases = (
            (
                ScalingKind.ATTACK,
                {"atk%": 0.50, "atk": 100.0},
                _vector(("hero", "atk", 40.0), ("hero", "atk%", 0.20)),
                _vector(("hero", "atk", 80.0), ("hero", "atk%", 0.35)),
            ),
            (
                ScalingKind.HP,
                {"hp%": 0.50, "hp": 1000.0},
                _vector(("hero", "hp", 500.0), ("hero", "hp%", 0.20)),
                _vector(("hero", "hp", 800.0), ("hero", "hp%", 0.40)),
            ),
            (
                ScalingKind.DEFENSE,
                {"def%": 0.40, "def": 100.0},
                _vector(("hero", "def", 40.0), ("hero", "def%", 0.15)),
                _vector(("hero", "def", 80.0), ("hero", "def%", 0.30)),
            ),
            (
                ScalingKind.ELEMENTAL_MASTERY,
                {"em": 300.0},
                _vector(("hero", "em", 100.0)),
                _vector(("hero", "em", 250.0)),
            ),
        )
        for scaling_kind, snapshot, incumbent, candidate in cases:
            with self.subTest(scaling_kind=scaling_kind.value):
                document = _with_scaling(_document(), scaling_kind, snapshot)
                filters = compile_rotation_formula_filters(document)
                objective = compile_artifact_variable_objective(
                    filters.fast,
                    incumbent,
                )
                absolute = evaluate_artifact_variable_objective(objective, candidate)
                delta = evaluate_rotation_formula_filter(
                    filters,
                    RotationFormulaMode.FAST,
                    artifact_replacements_between(incumbent, candidate),
                )
                self.assertAlmostEqual(
                    absolute.candidate_damage,
                    delta.candidate_damage,
                )

    def test_common_and_type_damage_bonus_are_separate_absolute_inputs(self) -> None:
        filters = compile_rotation_formula_filters(_document())
        incumbent = _vector(
            ("hero", "anemo%", 0.15),
            ("hero", "dmg%", 0.05),
        )
        candidate = _vector(
            ("hero", "anemo%", 0.05),
            ("hero", "dmg%", 0.25),
        )
        objective = compile_artifact_variable_objective(filters.fast, incumbent)

        absolute = evaluate_artifact_variable_objective(objective, candidate)
        delta = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            artifact_replacements_between(incumbent, candidate),
        )

        self.assertAlmostEqual(absolute.candidate_damage, delta.candidate_damage)
        channel = objective.fixed_actor_formulas[0].normal_channels[0]
        self.assertAlmostEqual(channel.average_damage_bonus, 0.0)

    def test_nested_source_slope_is_rebased_to_absolute_hp(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = _decode(request, raw, binding)
        filters = compile_rotation_formula_filters(trace)
        incumbent = _vector(("furina", "hp%", 0.20))
        candidate = _vector(("furina", "hp%", 0.2496))
        objective = compile_artifact_variable_objective(filters.fast, incumbent)

        absolute = evaluate_artifact_variable_objective(objective, candidate)
        delta = evaluate_rotation_formula_filter(
            filters,
            RotationFormulaMode.FAST,
            artifact_replacements_between(incumbent, candidate),
        )

        self.assertAlmostEqual(absolute.candidate_damage, delta.candidate_damage)
        self.assertGreater(absolute.candidate_damage, objective.baseline_damage)

    def test_vector_contract_rejects_noncanonical_or_foreign_input(self) -> None:
        with self.assertRaises(TraceContractError):
            ArtifactStatValue("hero", "atk%", -0.1)
        with self.assertRaises(TraceContractError):
            ArtifactStatVector(
                (
                    ArtifactStatValue("hero", "cr", 0.1),
                    ArtifactStatValue("hero", "atk%", 0.2),
                )
            )

        filters = compile_rotation_formula_filters(_document())
        foreign = _vector(("not-in-team", "atk%", 0.2))
        with self.assertRaises(TraceContractError):
            compile_artifact_variable_objective(filters.fast, foreign)


def _vector(*rows: tuple[str, str, float]) -> ArtifactStatVector:
    return ArtifactStatVector.build(
        tuple(ArtifactStatValue(actor, stat, value) for actor, stat, value in rows)
    )


def _apply_replacements(
    start: ArtifactStatVector,
    replacements,
) -> ArtifactStatVector:
    values = {
        (row.actor_key, row.stat_key): row.value
        for row in start.values
    }
    for row in replacements:
        key = (row.actor_key, row.stat_key)
        if row.candidate_artifact_value == 0.0:
            values.pop(key, None)
        else:
            values[key] = row.candidate_artifact_value
    return ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, value)
            for (actor, stat), value in values.items()
        )
    )


if __name__ == "__main__":
    unittest.main()
