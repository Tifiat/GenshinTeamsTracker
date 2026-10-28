from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from run_workspace.gcsim.farming_search import (
    PROFILE_AXIS_PAIR,
    PROFILE_BALANCED,
    PROFILE_SINGLE_AXIS,
    SURVIVOR_NOVEL_BRANCH,
    SURVIVOR_PROFILE_COVERAGE,
    SURVIVOR_REQUIRED_PROFILE,
    SURVIVOR_UNCERTAIN,
    SURVIVOR_WEARER_COVERAGE,
    CandidateEvaluation,
    FourPieceCandidateCoverage,
    FourPieceSetState,
    ScreeningSurvivorBudget,
    SearchWearer,
    SearchSurvivor,
    SetProfileCandidate,
    StatAxis,
    StatProfile,
    StatProfileBank,
    StatWeight,
    SurvivorSelectionResult,
    WearerProfileSelection,
    generate_stat_profile_bank,
    build_four_piece_candidate_coverage,
    select_screening_survivors,
)
from run_workspace.gcsim.artifact_set_catalog import GcsimArtifactSetCapability


class FarmingSearchProfileBankTest(unittest.TestCase):
    def test_profiles_and_banks_detach_from_caller_owned_lists(self) -> None:
        source_weights = [StatWeight("axis", 1.0)]
        source_focus_axes = ["axis"]
        profile = StatProfile(
            profile_id="focus/axis",
            kind=PROFILE_SINGLE_AXIS,
            weights=source_weights,  # type: ignore[arg-type]
            focus_axes=source_focus_axes,  # type: ignore[arg-type]
        )
        source_axes = [StatAxis("axis", 1.0)]
        source_profiles = [profile]
        bank = StatProfileBank(
            axes=source_axes,  # type: ignore[arg-type]
            profiles=source_profiles,  # type: ignore[arg-type]
        )

        source_weights.clear()
        source_focus_axes.append("mutated")
        source_axes.append(StatAxis("mutated", 2.0))
        source_profiles.clear()

        self.assertEqual(profile.weights, (StatWeight("axis", 1.0),))
        self.assertEqual(profile.focus_axes, ("axis",))
        self.assertEqual(bank.axes, (StatAxis("axis", 1.0),))
        self.assertEqual(bank.profiles, (profile,))
        self.assertEqual(bank.profile("focus/axis"), profile)

    def test_profile_tuple_fields_reject_strings_and_wrong_element_types(self) -> None:
        with self.assertRaisesRegex(ValueError, "focus axes.*iterable"):
            StatProfile(
                profile_id="focus/axis",
                kind=PROFILE_SINGLE_AXIS,
                weights=(StatWeight("axis", 1.0),),
                focus_axes="axis",  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(ValueError, "only StatWeight"):
            StatProfile(
                profile_id="focus/axis",
                kind=PROFILE_SINGLE_AXIS,
                weights=["axis"],  # type: ignore[list-item]
            )

        with self.assertRaisesRegex(ValueError, "only StatAxis"):
            StatProfileBank(
                axes=["axis"],  # type: ignore[list-item]
                profiles=[
                    StatProfile(
                        profile_id="baseline",
                        kind="baseline",
                    )
                ],  # type: ignore[arg-type]
            )

    def test_generic_profile_bank_is_deterministic_and_materializable(self) -> None:
        axes = (
            StatAxis("axis_z", 10.0, "z-unit"),
            StatAxis("axis_a", 20.0, "a-unit"),
            StatAxis("axis_m", 40.0, "m-unit"),
        )

        bank = generate_stat_profile_bank(
            axes,
            include_axis_pairs=True,
            axis_pair_limit=2,
        )

        self.assertEqual(
            tuple(profile.profile_id for profile in bank.profiles),
            (
                "baseline",
                "balanced",
                "focus/axis_z",
                "focus/axis_a",
                "focus/axis_m",
                "pair/axis_z+axis_a",
                "pair/axis_z+axis_m",
            ),
        )
        self.assertEqual(bank.profile("balanced").kind, PROFILE_BALANCED)
        self.assertEqual(bank.profile("focus/axis_m").kind, PROFILE_SINGLE_AXIS)
        self.assertEqual(
            bank.profile("pair/axis_z+axis_a").kind,
            PROFILE_AXIS_PAIR,
        )
        deltas = bank.profile("pair/axis_z+axis_a").materialize(
            bank.axes,
            reference_weights=(
                StatWeight("axis_z", 1 / 3),
                StatWeight("axis_a", 1 / 3),
                StatWeight("axis_m", 1 / 3),
            ),
            exchange_rolls=2.0,
        )
        delta_by_axis = {delta.axis_key: delta.value for delta in deltas}
        self.assertAlmostEqual(delta_by_axis["axis_z"], 10.0 / 3.0)
        self.assertAlmostEqual(delta_by_axis["axis_a"], 20.0 / 3.0)
        self.assertAlmostEqual(delta_by_axis["axis_m"], -80.0 / 3.0)
        self.assertAlmostEqual(
            sum(
                delta.value / next(
                    axis.probe_delta
                    for axis in bank.axes
                    if axis.key == delta.axis_key
                )
                for delta in deltas
            ),
            0.0,
        )

        with self.assertRaises(FrozenInstanceError):
            bank.axes[0].probe_delta = 11.0  # type: ignore[misc]

    def test_pair_profiles_are_bounded_explicitly(self) -> None:
        axes = tuple(StatAxis(f"axis_{index}", 1.0) for index in range(10))

        without_pairs = generate_stat_profile_bank(axes)
        with_bounded_pairs = generate_stat_profile_bank(
            axes,
            include_axis_pairs=True,
            axis_pair_limit=4,
        )

        self.assertEqual(len(without_pairs.profiles), 12)
        self.assertEqual(len(with_bounded_pairs.profiles), 16)


class FarmingSearchCoverageTest(unittest.TestCase):
    def test_selection_detaches_from_caller_owned_profile_id_lists(self) -> None:
        source_profile_ids = ["baseline", "focus/axis"]
        source_required_ids = ["focus/axis"]

        selection = WearerProfileSelection(
            wearer_id="slot_0",
            profile_ids=source_profile_ids,  # type: ignore[arg-type]
            required_profile_ids=source_required_ids,  # type: ignore[arg-type]
        )
        source_profile_ids.clear()
        source_required_ids.append("mutated")

        self.assertEqual(selection.profile_ids, ("baseline", "focus/axis"))
        self.assertEqual(selection.required_profile_ids, ("focus/axis",))

    def test_coverage_detaches_its_entire_nested_domain_from_caller_lists(self) -> None:
        bank = generate_stat_profile_bank(
            (StatAxis("axis", 1.0),),
            include_balanced=False,
            include_single_axis=False,
        )
        base = build_four_piece_candidate_coverage(
            (SearchWearer("slot_0"),),
            (_set_capability("modeled", four_piece_modeled=True),),
            bank,
            main_stat_layout_ids_by_wearer={"slot_0": ("layout/default",)},
        )
        wearer_ids = list(base.wearer_ids)
        ready_set_keys = list(base.optimizer_ready_set_keys)
        rarity_row: list[object] = list(base.optimizer_ready_set_rarities[0])
        rarity_rows = [rarity_row]
        excluded_set_keys = list(base.excluded_set_keys)
        profile_ids = list(base.available_profile_ids)
        layout_ids = list(base.main_stat_layout_ids_by_wearer[0][1])
        layout_row: list[object] = ["slot_0", layout_ids]
        layout_rows = [layout_row]
        selections = list(base.wearer_profile_selections)
        states = list(base.states)
        candidates = list(base.candidates)
        coverage = FourPieceCandidateCoverage(
            wearer_ids=wearer_ids,  # type: ignore[arg-type]
            optimizer_ready_set_keys=ready_set_keys,  # type: ignore[arg-type]
            optimizer_ready_set_rarities=rarity_rows,  # type: ignore[arg-type]
            excluded_set_keys=excluded_set_keys,  # type: ignore[arg-type]
            available_profile_ids=profile_ids,  # type: ignore[arg-type]
            main_stat_layout_ids_by_wearer=layout_rows,  # type: ignore[arg-type]
            wearer_profile_selections=selections,  # type: ignore[arg-type]
            states=states,  # type: ignore[arg-type]
            candidates=candidates,  # type: ignore[arg-type]
        )
        domain_before = (
            coverage.expected_state_count,
            coverage.expected_candidate_count,
            tuple(candidate.key for candidate in coverage.candidates),
        )

        wearer_ids.append("mutated")
        ready_set_keys.clear()
        rarity_row[1] = 4
        rarity_rows.clear()
        excluded_set_keys.append("mutated")
        profile_ids.append("mutated")
        layout_ids.append("layout/mutated")
        layout_row[0] = "mutated"
        layout_rows.clear()
        selections.clear()
        states.clear()
        candidates.clear()

        self.assertEqual(
            (
                coverage.expected_state_count,
                coverage.expected_candidate_count,
                tuple(candidate.key for candidate in coverage.candidates),
            ),
            domain_before,
        )
        self.assertEqual(
            coverage.main_stat_layout_ids_by_wearer,
            (("slot_0", ("layout/default",)),),
        )

    def test_coverage_contains_every_modeled_set_wearer_profile_product(self) -> None:
        bank = generate_stat_profile_bank(
            (StatAxis("first", 1.0), StatAxis("second", 2.0)),
            include_balanced=False,
            include_single_axis=False,
        )
        capabilities = (
            _set_capability("modeled_a", four_piece_modeled=True),
            _set_capability(
                "not_modeled",
                four_piece_modeled=False,
                issues=("effect unavailable in pinned engine",),
            ),
            _set_capability("modeled_b", four_piece_modeled=True),
        )

        coverage = build_four_piece_candidate_coverage(
            (SearchWearer("slot_0"), SearchWearer("slot_1")),
            capabilities,
            bank,
            main_stat_layout_ids_by_wearer={
                "slot_0": ("layout/default",),
                "slot_1": ("layout/default",),
            },
        )

        self.assertEqual(
            coverage.optimizer_ready_set_keys,
            ("modeled_a", "modeled_b"),
        )
        self.assertEqual(coverage.excluded_set_keys, ("not_modeled",))
        self.assertEqual(coverage.expected_state_count, 4)
        self.assertEqual(coverage.expected_candidate_count, 4)
        self.assertTrue(coverage.uses_full_profile_bank)
        self.assertEqual(
            coverage.candidate_counts_by_wearer,
            (("slot_0", 2), ("slot_1", 2)),
        )
        self.assertEqual(len(coverage.states), coverage.expected_state_count)
        self.assertEqual(
            len(coverage.candidates),
            coverage.expected_candidate_count,
        )
        self.assertEqual(
            tuple(candidate.key for candidate in coverage.candidates),
            (
                ("slot_0", "modeled_a", "layout/default", "", "baseline"),
                ("slot_0", "modeled_b", "layout/default", "", "baseline"),
                ("slot_1", "modeled_a", "layout/default", "", "baseline"),
                ("slot_1", "modeled_b", "layout/default", "", "baseline"),
            ),
        )

    def test_duplicate_set_capabilities_are_rejected(self) -> None:
        bank = generate_stat_profile_bank(
            (StatAxis("axis", 1.0),),
            include_balanced=False,
            include_single_axis=False,
        )

        with self.assertRaisesRegex(ValueError, "capability keys"):
            build_four_piece_candidate_coverage(
                (SearchWearer("slot_0"),),
                (
                    _set_capability("same", four_piece_modeled=True),
                    _set_capability("same", four_piece_modeled=False),
                ),
                bank,
                main_stat_layout_ids_by_wearer={"slot_0": ("layout/default",)},
            )

    def test_adaptive_profile_subset_avoids_the_full_cartesian_product(self) -> None:
        bank = generate_stat_profile_bank(
            (
                StatAxis("first", 1.0),
                StatAxis("second", 2.0),
                StatAxis("third", 3.0),
            ),
        )
        capabilities = (
            _set_capability("modeled_a", four_piece_modeled=True),
            _set_capability("modeled_b", four_piece_modeled=True),
        )

        coverage = build_four_piece_candidate_coverage(
            (SearchWearer("slot_0"), SearchWearer("slot_1")),
            capabilities,
            bank,
            main_stat_layout_ids_by_wearer={
                "slot_0": ("layout/default",),
                "slot_1": ("layout/default",),
            },
            wearer_profile_selections=(
                WearerProfileSelection(
                    wearer_id="slot_1",
                    profile_ids=("focus/third", "baseline"),
                    required_profile_ids=("focus/third",),
                ),
                WearerProfileSelection(
                    wearer_id="slot_0",
                    profile_ids=("focus/first", "baseline"),
                    required_profile_ids=("focus/first",),
                ),
            ),
        )

        self.assertFalse(coverage.uses_full_profile_bank)
        self.assertEqual(coverage.expected_state_count, 4)
        self.assertEqual(coverage.expected_candidate_count, 8)
        self.assertEqual(
            coverage.candidate_counts_by_wearer,
            (("slot_0", 4), ("slot_1", 4)),
        )
        self.assertEqual(
            tuple(candidate.key for candidate in coverage.candidates),
            (
                ("slot_0", "modeled_a", "layout/default", "", "baseline"),
                ("slot_0", "modeled_a", "layout/default", "", "focus/first"),
                ("slot_0", "modeled_b", "layout/default", "", "baseline"),
                ("slot_0", "modeled_b", "layout/default", "", "focus/first"),
                ("slot_1", "modeled_a", "layout/default", "", "baseline"),
                ("slot_1", "modeled_a", "layout/default", "", "focus/third"),
                ("slot_1", "modeled_b", "layout/default", "", "baseline"),
                ("slot_1", "modeled_b", "layout/default", "", "focus/third"),
            ),
        )

    def test_four_star_set_expands_every_offpiece_slot_in_candidate_identity(self) -> None:
        bank = generate_stat_profile_bank(
            (StatAxis("axis", 1.0),),
            include_balanced=False,
            include_single_axis=False,
        )
        capability = _set_capability(
            "four_star",
            four_piece_modeled=True,
            max_rarity=4,
        )

        coverage = build_four_piece_candidate_coverage(
            (SearchWearer("slot_0"),),
            (capability,),
            bank,
            main_stat_layout_ids_by_wearer={"slot_0": ("layout/a", "layout/b")},
        )

        self.assertEqual(len(coverage.states), 10)
        self.assertEqual(
            {state.offpiece_slot for state in coverage.states},
            {"flower", "plume", "sands", "goblet", "circlet"},
        )
        self.assertEqual(len({candidate.key for candidate in coverage.candidates}), 10)

    def test_adaptive_subset_cannot_drop_an_upstream_required_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "large/uncertain"):
            WearerProfileSelection(
                wearer_id="slot_0",
                profile_ids=("baseline",),
                required_profile_ids=("focus/first",),
            )


class FarmingSearchSurvivorSelectionTest(unittest.TestCase):
    def test_evaluations_and_results_detach_from_caller_owned_lists(self) -> None:
        novelty_tags = ["nonlinear"]
        evaluation = CandidateEvaluation(
            candidate=SetProfileCandidate(
                state=FourPieceSetState(
                    wearer_id="wearer",
                    set_key="set",
                    main_stat_layout_id="layout/default",
                ),
                profile_id="baseline",
            ),
            expected_dps=100.0,
            investment_signature="equal-rolls/test-v1",
            novelty_tags=novelty_tags,  # type: ignore[arg-type]
        )
        reasons = ["top_score"]
        survivor = SearchSurvivor(
            evaluation=evaluation,
            reasons=reasons,  # type: ignore[arg-type]
        )
        survivors = [survivor]
        required_group: list[str] = ["wearer", "baseline"]
        required_groups = [required_group]
        result = SurvivorSelectionResult(
            budget=ScreeningSurvivorBudget(
                max_survivors=1,
                top_slots=1,
                wearer_coverage_slots=0,
                uncertain_slots=0,
                profile_coverage_slots=0,
                novelty_slots=0,
                confidence_sigma=1.0,
                relative_uncertainty_margin=0.0,
            ),
            evaluated_count=1,
            survivors=survivors,  # type: ignore[arg-type]
            dropped_count=0,
            required_profile_groups=required_groups,  # type: ignore[arg-type]
        )

        novelty_tags.append("mutated")
        reasons.clear()
        survivors.clear()
        required_group[1] = "mutated"
        required_groups.clear()

        self.assertEqual(evaluation.novelty_tags, ("nonlinear",))
        self.assertEqual(survivor.reasons, ("top_score",))
        self.assertEqual(result.survivors, (survivor,))
        self.assertEqual(
            result.required_profile_groups,
            (("wearer", "baseline"),),
        )

    def test_required_response_profile_survives_even_without_profile_slots(self) -> None:
        evaluations = (
            _evaluation("wearer", "leader", "baseline", 100.0),
            _evaluation("wearer", "near", "baseline", 99.0),
            _evaluation("wearer", "em_branch", "focus/em", 1.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=2,
            top_slots=1,
            wearer_coverage_slots=0,
            uncertain_slots=0,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=1.0,
            relative_uncertainty_margin=0.0,
        )

        result = select_screening_survivors(
            evaluations,
            budget,
            required_profile_ids_by_wearer={"wearer": ("focus/em",)},
        )

        self.assertEqual(
            tuple(item.state.set_key for item in result.survivor_candidates),
            ("leader", "em_branch"),
        )
        em_survivor = next(
            row
            for row in result.survivors
            if row.evaluation.candidate.profile_id == "focus/em"
        )
        self.assertIn(SURVIVOR_REQUIRED_PROFILE, em_survivor.reasons)
        self.assertEqual(
            result.required_profile_groups,
            (("wearer", "focus/em"),),
        )

    def test_required_response_profiles_fail_closed_when_cap_is_too_small(self) -> None:
        evaluations = (
            _evaluation("wearer", "em", "focus/em", 10.0),
            _evaluation("wearer", "hp", "focus/hp", 9.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=1,
            top_slots=0,
            wearer_coverage_slots=0,
            uncertain_slots=0,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=1.0,
            relative_uncertainty_margin=0.0,
        )

        with self.assertRaisesRegex(ValueError, "required.*exceed"):
            select_screening_survivors(
                evaluations,
                budget,
                required_profile_ids_by_wearer={
                    "wearer": ("focus/em", "focus/hp")
                },
            )

    def test_selection_preserves_uncertain_profile_wearer_and_novel_branches(self) -> None:
        evaluations = (
            _evaluation("wearer_a", "set_alpha", "baseline", 100.0, error=0.2),
            _evaluation("wearer_a", "set_beta", "baseline", 96.0, error=2.1),
            _evaluation("wearer_a", "set_gamma", "focus/em", 95.0),
            _evaluation("wearer_a", "set_delta", "focus/hp", 70.0),
            _evaluation("wearer_b", "set_alpha", "baseline", 90.0),
            _evaluation("wearer_b", "set_beta", "focus/em", 89.0),
            _evaluation(
                "wearer_b",
                "set_novel",
                "focus/hp",
                60.0,
                novelty_score=50.0,
                novelty_tags=("nonlinear_response",),
            ),
            _evaluation("wearer_b", "set_delta", "baseline", 55.0),
            _evaluation("wearer_b", "set_gamma", "focus/em", 50.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=7,
            top_slots=1,
            wearer_coverage_slots=2,
            uncertain_slots=1,
            profile_coverage_slots=2,
            novelty_slots=1,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.005,
        )

        selected = select_screening_survivors(reversed(evaluations), budget)
        selected_again = select_screening_survivors(evaluations, budget)

        self.assertEqual(
            tuple(candidate.key for candidate in selected.survivor_candidates),
            tuple(candidate.key for candidate in selected_again.survivor_candidates),
        )
        self.assertEqual(selected.evaluated_count, 9)
        self.assertEqual(len(selected.survivors), 7)
        self.assertEqual(selected.dropped_count, 2)

        reasons_by_key = {
            survivor.evaluation.candidate.key: survivor.reasons
            for survivor in selected.survivors
        }
        self.assertIn(
            SURVIVOR_UNCERTAIN,
            reasons_by_key[
                ("wearer_a", "set_beta", "layout/default", "", "baseline")
            ],
        )
        self.assertIn(
            SURVIVOR_WEARER_COVERAGE,
            reasons_by_key[
                ("wearer_b", "set_alpha", "layout/default", "", "baseline")
            ],
        )
        self.assertIn(
            SURVIVOR_PROFILE_COVERAGE,
            reasons_by_key[
                ("wearer_a", "set_gamma", "layout/default", "", "focus/em")
            ],
        )
        self.assertIn(
            SURVIVOR_NOVEL_BRANCH,
            reasons_by_key[
                ("wearer_b", "set_novel", "layout/default", "", "focus/hp")
            ],
        )

    def test_relative_margin_keeps_a_zero_error_near_tie(self) -> None:
        evaluations = (
            _evaluation("wearer", "best", "baseline", 100.0),
            _evaluation("wearer", "near", "baseline", 99.2),
            _evaluation("wearer", "far", "baseline", 95.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=2,
            top_slots=1,
            wearer_coverage_slots=0,
            uncertain_slots=1,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=0.0,
            relative_uncertainty_margin=0.01,
        )

        result = select_screening_survivors(evaluations, budget)

        self.assertEqual(
            tuple(candidate.state.set_key for candidate in result.survivor_candidates),
            ("best", "near"),
        )

    def test_unknown_uncertainty_is_not_treated_as_zero_error(self) -> None:
        evaluations = (
            _evaluation("wearer", "best", "baseline", 100.0, error=0.1),
            _evaluation("wearer", "unknown", "baseline", 50.0, error=None),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=2,
            top_slots=1,
            wearer_coverage_slots=0,
            uncertain_slots=1,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.0,
        )

        result = select_screening_survivors(evaluations, budget)

        self.assertEqual(
            tuple(candidate.state.set_key for candidate in result.survivor_candidates),
            ("best", "unknown"),
        )

    def test_profile_coverage_is_scoped_to_each_wearer(self) -> None:
        evaluations = (
            _evaluation("wearer_a", "a_best", "focus/em", 100.0),
            _evaluation("wearer_a", "a_other", "focus/em", 99.0),
            _evaluation("wearer_b", "b_best", "focus/em", 20.0),
            _evaluation("wearer_b", "b_other", "focus/em", 19.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=2,
            top_slots=0,
            wearer_coverage_slots=0,
            uncertain_slots=0,
            profile_coverage_slots=2,
            novelty_slots=0,
            confidence_sigma=0.0,
            relative_uncertainty_margin=0.0,
        )

        result = select_screening_survivors(evaluations, budget)

        self.assertEqual(
            tuple(candidate.state.set_key for candidate in result.survivor_candidates),
            ("a_best", "b_best"),
        )

    def test_reserved_coverage_slot_skips_an_already_selected_candidate(self) -> None:
        evaluations = (
            _evaluation("wearer", "top", "profile_a", 100.0),
            _evaluation("wearer", "next", "profile_a", 99.0),
            _evaluation("wearer", "needed", "profile_b", 1.0),
        )
        budget = ScreeningSurvivorBudget(
            max_survivors=2,
            top_slots=1,
            wearer_coverage_slots=0,
            uncertain_slots=0,
            profile_coverage_slots=1,
            novelty_slots=0,
            confidence_sigma=0.0,
            relative_uncertainty_margin=0.0,
        )

        result = select_screening_survivors(evaluations, budget)

        self.assertEqual(
            tuple(candidate.state.set_key for candidate in result.survivor_candidates),
            ("top", "needed"),
        )

    def test_duplicate_candidate_evaluations_are_rejected(self) -> None:
        duplicate = _evaluation("wearer", "set", "profile", 10.0)
        budget = ScreeningSurvivorBudget(
            max_survivors=1,
            top_slots=1,
            wearer_coverage_slots=0,
            uncertain_slots=0,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=1.0,
            relative_uncertainty_margin=0.0,
        )

        with self.assertRaisesRegex(ValueError, "evaluation keys"):
            select_screening_survivors((duplicate, duplicate), budget)

    def test_reserved_slots_cannot_silently_overrun_the_survivor_cap(self) -> None:
        with self.assertRaisesRegex(ValueError, "reserved survivor slots"):
            ScreeningSurvivorBudget(
                max_survivors=2,
                top_slots=1,
                wearer_coverage_slots=1,
                uncertain_slots=1,
                profile_coverage_slots=0,
                novelty_slots=0,
                confidence_sigma=1.0,
                relative_uncertainty_margin=0.0,
            )

    def test_survivor_slot_budgets_require_real_integers(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_slots must be an integer"):
            ScreeningSurvivorBudget(
                max_survivors=2,
                top_slots=0.5,  # type: ignore[arg-type]
                wearer_coverage_slots=0,
                uncertain_slots=0,
                profile_coverage_slots=0,
                novelty_slots=0,
                confidence_sigma=1.0,
                relative_uncertainty_margin=0.0,
            )


def _evaluation(
    wearer_id: str,
    set_key: str,
    profile_id: str,
    expected_dps: float,
    *,
    error: float | None = 0.0,
    novelty_score: float = 0.0,
    novelty_tags: tuple[str, ...] = (),
) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate=SetProfileCandidate(
            state=FourPieceSetState(
                wearer_id=wearer_id,
                set_key=set_key,
                main_stat_layout_id="layout/default",
            ),
            profile_id=profile_id,
        ),
        expected_dps=expected_dps,
        investment_signature="equal-rolls/test-v1",
        standard_error=error,
        novelty_score=novelty_score,
        novelty_tags=novelty_tags,
    )


def _set_capability(
    key: str,
    *,
    four_piece_modeled: bool,
    max_rarity: int = 5,
    issues: tuple[str, ...] = (),
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key,
        max_rarity=max_rarity,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=four_piece_modeled,
        two_piece_modeled=True,
        four_piece_modeled=four_piece_modeled,
        issues=issues,
    )


if __name__ == "__main__":
    unittest.main()
