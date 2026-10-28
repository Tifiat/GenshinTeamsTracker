from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    FormulaValue,
    PruneSafety,
    RankingStatDelta,
    RankingStatValue,
    RankingSupport,
    ReactionOperator,
    ReplayStatus,
    ScalingKind,
    SnapshotStat,
    TraceDamageMode,
    TraceDocument,
    canonical_json,
    decode_engine_trace_v1,
    estimate_candidate_expected_damage,
    estimate_candidate_expected_damage_deltas,
    score_observed_artifact_replacement,
)

from .test_contracts import _document, _raw_engine_trace


class ExpectedRankingTests(unittest.TestCase):
    def test_raw_engine_trace_produces_heuristic_ranking_not_exact_authority(self) -> None:
        request = _document().request
        raw = _raw_engine_trace(request)
        decoded = decode_engine_trace_v1(canonical_json(raw), request=request)
        assert isinstance(decoded, TraceDocument)

        estimate = estimate_candidate_expected_damage(
            decoded,
            (RankingStatValue("hero", "atk%", 0.55),),
        )

        self.assertTrue(estimate.orderable)
        self.assertEqual(estimate.support, RankingSupport.HEURISTIC)
        self.assertEqual(estimate.prune_safety, PruneSafety.KEEP)
        self.assertFalse(estimate.publishable)
        self.assertIn("provider_identity_incomplete", estimate.uncertainty_codes)

    def test_analytic_crit_ignores_captured_roll_and_caps_cr(self) -> None:
        document = _document()

        baseline = estimate_candidate_expected_damage(document, ())
        cr_095 = _score(document, "cr", 0.95)
        cr_100 = _score(document, "cr", 1.0)
        cr_105 = _score(document, "cr", 1.05)

        # The captured roll is 0.8 and the observed hit did not crit. Ranking
        # intentionally uses expectation: pre-crit 864 * (1 + .5 * .5).
        self.assertAlmostEqual(baseline.candidate_score or 0.0, 1080.0)
        self.assertAlmostEqual(cr_095, 864.0 * 1.475)
        self.assertAlmostEqual(cr_100, 1296.0)
        self.assertAlmostEqual(cr_105, cr_100)
        self.assertEqual(baseline.support, RankingSupport.MODELED_EXPECTATION)
        self.assertEqual(baseline.prune_safety, PruneSafety.KEEP)
        self.assertFalse(baseline.publishable)

    def test_attack_and_damage_bonus_use_absolute_candidate_stats(self) -> None:
        document = _document()

        attack = estimate_candidate_expected_damage(
            document,
            (RankingStatValue("hero", "atk%", 0.55),),
        )
        anemo = estimate_candidate_expected_damage(
            document,
            (RankingStatValue("hero", "anemo%", 0.30),),
        )

        # 1000 base, 55% ATK, 100 flat = 1650.  Then 20% Anemo,
        # DEF=.5, RES=.9 and expected crit=1.25.
        self.assertAlmostEqual(attack.candidate_score or 0.0, 1113.75)
        # Candidate Anemo bonus is 30%, replacing the baseline 20%.
        self.assertAlmostEqual(anemo.candidate_score or 0.0, 1170.0)

    def test_artifact_delta_is_added_to_each_observed_snapshot(self) -> None:
        baseline = _document()
        buffed = _with_scaling(
            baseline,
            ScalingKind.ATTACK,
            {"atk%": 0.8},
        )

        baseline_delta = estimate_candidate_expected_damage_deltas(
            baseline,
            (RankingStatDelta("hero", "atk%", 0.05),),
        )
        buffed_delta = estimate_candidate_expected_damage_deltas(
            buffed,
            (RankingStatDelta("hero", "atk%", 0.05),),
        )
        baseline_absolute = estimate_candidate_expected_damage(
            baseline,
            (RankingStatValue("hero", "atk%", 0.55),),
        )
        buffed_absolute = estimate_candidate_expected_damage(
            buffed,
            (RankingStatValue("hero", "atk%", 0.55),),
        )

        self.assertAlmostEqual(
            baseline_delta.candidate_score or 0.0,
            baseline_absolute.candidate_score or 0.0,
        )
        self.assertGreater(
            buffed_delta.candidate_score or 0.0,
            baseline_delta.candidate_score or 0.0,
        )
        self.assertLess(
            buffed_absolute.candidate_score or 0.0,
            buffed_delta.candidate_score or 0.0,
        )

    def test_delta_crit_caps_per_observed_hit(self) -> None:
        document = _document()

        cr_100 = estimate_candidate_expected_damage_deltas(
            document,
            (RankingStatDelta("hero", "cr", 0.5),),
        )
        cr_105 = estimate_candidate_expected_damage_deltas(
            document,
            (RankingStatDelta("hero", "cr", 0.55),),
        )

        self.assertAlmostEqual(
            cr_100.candidate_score or 0.0,
            cr_105.candidate_score or 0.0,
        )

    def test_observed_artifact_replacement_is_offline_and_non_authoritative(self) -> None:
        document = _document()

        observed = score_observed_artifact_replacement(
            document,
            (
                ArtifactStatReplacement(
                    "hero",
                    "atk%",
                    baseline_artifact_value=0.20,
                    candidate_artifact_value=0.25,
                ),
            ),
        )
        direct = estimate_candidate_expected_damage_deltas(
            document,
            (RankingStatDelta("hero", "atk%", 0.05),),
        )

        self.assertEqual(observed.engine_call_count, 0)
        self.assertFalse(observed.authoritative)
        self.assertFalse(observed.publishable)
        self.assertIsNone(observed.duration_frames)
        self.assertIsNone(observed.baseline_expected_dps)
        self.assertIsNone(observed.candidate_expected_dps)
        self.assertTrue(observed.grouping_preserves_scores)
        self.assertAlmostEqual(
            observed.ranking.candidate_score or 0.0,
            direct.candidate_score or 0.0,
        )
        self.assertAlmostEqual(
            observed.modeled_baseline_share + observed.frozen_baseline_share,
            1.0,
        )

    def test_formula_grouping_preserves_two_identical_expected_hits(self) -> None:
        document = _duplicate_hit_document(_document())

        observed = score_observed_artifact_replacement(document, ())

        self.assertEqual(len(observed.ranking.hits), 2)
        self.assertEqual(len(observed.groups), 1)
        self.assertEqual(observed.groups[0].multiplicity, 2)
        self.assertEqual(len(observed.groups[0].event_ids), 2)
        self.assertTrue(observed.grouping_preserves_scores)
        self.assertAlmostEqual(
            observed.grouped_candidate_score or 0.0,
            observed.ranking.candidate_score or 0.0,
        )

    def test_hp_def_and_em_scaling_are_direct_formula_dimensions(self) -> None:
        hp_document = _with_scaling(
            _document(),
            ScalingKind.HP,
            {"base_hp": 10000.0, "hp": 1000.0, "hp%": 0.2},
        )
        def_document = _with_scaling(
            _document(),
            ScalingKind.DEFENSE,
            {"base_def": 800.0, "def": 100.0, "def%": 0.25},
        )
        em_document = _with_scaling(
            _document(),
            ScalingKind.ELEMENTAL_MASTERY,
            {"em": 100.0},
        )

        hp = _score(hp_document, "hp%", 0.3)
        defense = _score(def_document, "def%", 0.35)
        em = _score(em_document, "em", 200.0)

        self.assertAlmostEqual(hp, 9450.0)
        self.assertAlmostEqual(defense, 796.5)
        self.assertAlmostEqual(em, 135.0)

    def test_amplifying_em_is_ranked_with_diminishing_marginal_value(self) -> None:
        document = _with_amplifying_reaction(_document())

        score_0 = estimate_candidate_expected_damage(document, ()).candidate_score
        score_300 = _score(document, "em", 300.0)
        score_1000 = _score(document, "em", 1000.0)

        assert score_0 is not None
        self.assertGreater(score_300, score_0)
        self.assertGreater(score_1000, score_300)
        self.assertGreater(
            (score_300 - score_0) / 300.0,
            (score_1000 - score_300) / 700.0,
        )
        estimate = estimate_candidate_expected_damage(
            document,
            (RankingStatValue("hero", "em", 300.0),),
        )
        self.assertEqual(estimate.support, RankingSupport.HEURISTIC)
        self.assertIn(
            "reaction_schedule_assumed_fixed",
            estimate.uncertainty_codes,
        )
        self.assertEqual(estimate.prune_safety, PruneSafety.KEEP)

    def test_reachable_unknown_flat_dependency_freezes_scaling_candidate(self) -> None:
        document = _with_unresolved_flat_damage(_document(), 100.0)

        estimate = estimate_candidate_expected_damage(
            document,
            (RankingStatValue("hero", "atk%", 0.55),),
        )

        self.assertFalse(estimate.orderable)
        self.assertIsNotNone(estimate.candidate_score)
        self.assertEqual(estimate.expected_delta, 0.0)
        self.assertEqual(estimate.support, RankingSupport.BASELINE_FROZEN)
        self.assertEqual(estimate.prune_safety, PruneSafety.KEEP)
        self.assertIn(
            "flat_damage_dependency_unresolved",
            estimate.uncertainty_codes,
        )

    def test_unknown_flat_base_still_allows_known_crit_multiplier_delta(self) -> None:
        document = _with_unresolved_flat_damage(_document(), 100.0)

        estimate = estimate_candidate_expected_damage_deltas(
            document,
            (RankingStatDelta("hero", "cr", 0.1),),
        )

        self.assertTrue(estimate.orderable)
        self.assertGreater(estimate.expected_delta or 0.0, 0.0)
        self.assertEqual(estimate.prune_safety, PruneSafety.KEEP)


def _score(document: TraceDocument, stat_key: str, value: float) -> float:
    estimate = estimate_candidate_expected_damage(
        document,
        (RankingStatValue("hero", stat_key, value),),
    )
    assert estimate.candidate_score is not None
    return estimate.candidate_score


def _with_scaling(
    document: TraceDocument,
    kind: ScalingKind,
    replacements: dict[str, float],
) -> TraceDocument:
    hit = document.hits[0]
    inputs = hit.formula_inputs
    stats = {row.stat_key: row.value for row in inputs.snapshot_stats}
    stats.update(replacements)
    if kind is ScalingKind.ATTACK:
        scaling = stats["base_atk"] * (1.0 + stats["atk%"]) + stats["atk"]
    elif kind is ScalingKind.HP:
        scaling = stats["base_hp"] * (1.0 + stats["hp%"]) + stats["hp"]
    elif kind is ScalingKind.DEFENSE:
        scaling = stats["base_def"] * (1.0 + stats["def%"]) + stats["def"]
    elif kind is ScalingKind.ELEMENTAL_MASTERY:
        scaling = stats["em"]
    else:
        raise AssertionError(kind)
    provenance = inputs.scaling_value.provenance_ids
    new_inputs = replace(
        inputs,
        scaling_kind=kind,
        scaling_value=FormulaValue(scaling, provenance),
        snapshot_stats=tuple(
            SnapshotStat(key, value, provenance)
            for key, value in sorted(stats.items())
        ),
        elemental_mastery=FormulaValue(stats["em"], provenance),
        base_damage=FormulaValue(
            inputs.mult.value * scaling * (1.0 + inputs.base_dmg_bonus.value)
            + inputs.flat_dmg.value,
            inputs.base_damage.provenance_ids,
        ),
    )
    return _replace_formula_hit(document, new_inputs)


def _with_amplifying_reaction(document: TraceDocument) -> TraceDocument:
    hit = document.hits[0]
    inputs = hit.formula_inputs
    new_inputs = replace(
        inputs,
        amplifying=True,
        amp_multiplier=FormulaValue(1.5, inputs.amp_multiplier.provenance_ids),
    )
    new_lineage = replace(
        hit.lineage,
        reaction_type="vaporize",
        reaction_operator_id=ReactionOperator.MULTIPLY_PARENT_HIT.value,
    )
    return _replace_formula_hit(document, new_inputs, lineage=new_lineage)


def _with_unresolved_flat_damage(
    document: TraceDocument,
    flat_damage: float,
) -> TraceDocument:
    hit = document.hits[0]
    inputs = hit.formula_inputs
    new_inputs = replace(
        inputs,
        flat_dmg=FormulaValue(flat_damage, inputs.flat_dmg.provenance_ids),
        base_damage=FormulaValue(
            inputs.base_damage.value + flat_damage,
            inputs.base_damage.provenance_ids,
        ),
    )
    completeness = replace(hit.completeness, flat_dmg_provenance_complete=False)
    return _replace_formula_hit(
        document,
        new_inputs,
        completeness=completeness,
        unsupported_feature_codes=("flat_dmg_expression_collapsed",),
        formula_replay_status=ReplayStatus.NEEDS_EXACT,
        formula_replay_reason_codes=("flat_damage_dependency_unresolved",),
    )


def _replace_formula_hit(
    document: TraceDocument,
    inputs,
    **changes,
) -> TraceDocument:
    hit = document.hits[0]
    rolled = _rolled_damage(inputs, crit=hit.crit)
    hp_damage = min(rolled, hit.target_hp_before)
    killed = (
        hit.damage_mode is TraceDamageMode.DAMAGE
        and hp_damage == hit.target_hp_before
    )
    reported = hp_damage if killed else rolled
    replacement = replace(
        hit,
        formula_inputs=inputs,
        uncapped_rolled_damage=rolled,
        hp_damage_applied=hp_damage,
        reported_damage=reported,
        target_hp_after=max(0.0, hit.target_hp_before - hp_damage),
        target_killed=killed,
        **changes,
    )
    return TraceDocument.build(
        request=document.request,
        hits=(replacement,),
        topology=document.topology,
    )


def _duplicate_hit_document(document: TraceDocument) -> TraceDocument:
    hit = document.hits[0]
    duplicate = replace(
        hit,
        event_id=f"{hit.event_id}:duplicate",
        frame=hit.frame + 1,
    )
    return TraceDocument.build(
        request=document.request,
        hits=(hit, duplicate),
        topology=document.topology,
    )


def _rolled_damage(inputs, *, crit: bool) -> float:
    damage = inputs.base_damage.value * (1.0 + inputs.dmg_bonus.value)
    damage *= inputs.defense_multiplier.value
    damage *= inputs.resistance_multiplier.value
    if crit:
        damage *= 1.0 + inputs.crit_damage.value
    if inputs.amplifying:
        damage *= inputs.amp_multiplier.value * (
            1.0 + inputs.em_bonus.value + inputs.reaction_bonus.value
        )
    damage *= inputs.group_multiplier.value
    damage *= inputs.elevation_multiplier.value
    return damage


if __name__ == "__main__":
    unittest.main()
