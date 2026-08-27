from __future__ import annotations

from dataclasses import replace
from itertools import combinations
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_profile_config import (
    GCSIM_AUTOMATIC_RESPONSE_STAT_AXES,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeStatProfile,
)
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_main_response import (
    gcsim_optimizer_main_layout_id,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerTargetPackageKind,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from run_workspace.gcsim.optimizer_set_impact import (
    GcsimOptimizerSetImpactClassification,
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSetImpactRow,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimStatResponseEstimate,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_candidates import (
    THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS,
    GcsimOptimizerTheoreticalAnytimeCandidateError,
    GcsimOptimizerTheoreticalAnytimeCandidatePlan,
    build_gcsim_optimizer_theoretical_anytime_candidate_domain,
)
from run_workspace.gcsim.optimizer_theoretical_packages import (
    gcsim_theoretical_pair_package_key,
)


class GcsimOptimizerTheoreticalAnytimeCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wearers = _wearers()
        self.profiles = _profiles(self.wearers)
        self.plan = GcsimOptimizerTheoreticalAnytimeCandidatePlan(
            max_layouts_per_wearer=10,
            max_profiles_per_wearer=7,
            max_package_anchors_per_wearer=6,
            max_wearer_alternatives=18,
            max_joint_package_anchor_proposals=20,
            max_joint_proposals=40,
        )

    def test_four_piece_domain_is_bounded_deterministic_and_diverse(
        self,
    ) -> None:
        context = _context()

        first = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=self.profiles,
            set_impact=_set_impact(context, self.wearers),
            plan=self.plan,
        )
        reordered = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=context,
                wearers=self.wearers,
                response_profiles=tuple(reversed(self.profiles)),
                set_impact=_set_impact(context, self.wearers),
                plan=self.plan,
            )
        )
        changed_evidence = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=context,
                wearers=self.wearers,
                response_profiles=(
                    replace(
                        self.profiles[0],
                        evidence_sha256="f" * 64,
                    ),
                    *self.profiles[1:],
                ),
                set_impact=_set_impact(context, self.wearers),
                plan=self.plan,
            )
        )

        self.assertEqual(first.identity_sha256, reordered.identity_sha256)
        self.assertEqual(first.to_dict(), reordered.to_dict())
        self.assertNotEqual(
            first.response_profiles_sha256,
            changed_evidence.response_profiles_sha256,
        )
        self.assertNotEqual(
            first.identity_sha256,
            changed_evidence.identity_sha256,
        )
        self.assertEqual(
            first.engine_binding_sha256,
            context.binding_sha256,
        )
        self.assertEqual(
            first.catalog_fingerprint,
            context.catalog.source_fingerprint,
        )
        self.assertEqual(
            first.package_kind,
            GcsimOptimizerTargetPackageKind.FOUR_PIECE,
        )
        self.assertEqual(
            first.package_keys,
            ("alpha", "beta", "delta", "epsilon", "gamma", "zeta"),
        )
        self.assertNotIn("fourstar", first.package_keys)
        self.assertNotIn("incomplete", first.package_keys)
        self.assertEqual(
            first.profile_bank.axes,
            GCSIM_AUTOMATIC_RESPONSE_STAT_AXES,
        )
        self.assertEqual(len(first.profile_bank.profiles), 4)
        self.assertEqual(
            {
                profile.profile_id
                for profile in first.profile_bank.profiles
            },
            {
                profile_id
                for pool in first.wearer_pools
                for profile_id in pool.profile_ids
            },
        )
        self.assertTrue(
            all(
                weight.axis_key != "er"
                for profile in first.profile_bank.profiles
                for weight in profile.weights
            )
        )

        bank_ids = {
            profile.profile_id for profile in first.profile_bank.profiles
        }
        for expected_slot, pool in enumerate(first.wearer_pools, start=1):
            self.assertEqual(pool.wearer.team_slot, expected_slot)
            self.assertEqual(len(pool.anchor_package_keys), 6)
            self.assertEqual(
                set(pool.anchor_package_keys),
                set(first.package_keys),
            )
            self.assertLessEqual(
                len(pool.layouts),
                self.plan.max_layouts_per_wearer,
            )
            self.assertLessEqual(
                len(pool.alternatives),
                self.plan.max_wearer_alternatives,
            )
            self.assertTrue(set(pool.profile_ids).issubset(bank_ids))
            self.assertTrue(
                all(layout.sands != "er" for _layout_id, layout in pool.layouts)
            )
            for source_id in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS:
                self.assertIn(
                    f"theoretical_slot{expected_slot}_{source_id}",
                    pool.profile_ids,
                )

        for pool_index, pool in enumerate(first.wearer_pools):
            self.assertTrue(
                set(pool.anchor_package_keys).issubset(
                    {
                        proposal.state.choices[
                            pool_index
                        ].state.set_key
                        for proposal in first.proposals
                    }
                )
            )

        self.assertGreaterEqual(len(first.proposals), 1)
        self.assertLessEqual(
            len(first.proposals),
            self.plan.max_joint_proposals,
        )
        self.assertLessEqual(
            sum(
                "package_anchor_probe" in proposal.diversity_labels
                for proposal in first.proposals
            ),
            self.plan.max_joint_package_anchor_proposals,
        )
        for proposal in first.proposals:
            self.assertEqual(
                tuple(
                    choice.state.wearer_id
                    for choice in proposal.state.choices
                ),
                ("alpha", "beta", "gamma", "delta"),
            )
            self.assertEqual(len(proposal.proposal_sha256), 64)
            self.assertEqual(
                proposal.surrogate_score,
                proposal.score,
            )
            self.assertTrue(
                all(
                    choice.profile_id in bank_ids
                    for choice in proposal.state.choices
                )
            )

    def test_profile_bank_normalizes_equal_crit_utility_per_roll_equally(
        self,
    ) -> None:
        profiles = tuple(
            replace(
                profile,
                stat_weights=tuple(
                    (
                        1.0 / GCSIM_STAT_RESPONSE_ROLL_VALUES[axis]
                        if axis in {"cr", "cd"}
                        else 0.0
                    )
                    for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                stat_classifications=tuple(
                    (
                        axis,
                        "secondary" if axis in {"cr", "cd"} else "negligible",
                    )
                    for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
            )
            for profile in self.profiles
        )

        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=_context(),
            wearers=self.wearers,
            response_profiles=profiles,
            set_impact=_set_impact(_context(), self.wearers),
            plan=self.plan,
        )

        first_profile = next(
            profile
            for profile in domain.profile_bank.profiles
            if profile.profile_id == "theoretical_slot1_balanced"
        )
        weights = {
            weight.axis_key: weight.weight
            for weight in first_profile.weights
        }
        self.assertAlmostEqual(weights["cr"], 0.5)
        self.assertAlmostEqual(weights["cd"], 0.5)

    def test_measured_late_package_is_the_baseline_not_hash_order(self) -> None:
        context = _context()
        impact = _set_impact(
            context,
            self.wearers,
            score_by_key={"zeta": 10_000.0},
        )
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=self.profiles,
            set_impact=impact,
            plan=self.plan,
        )

        self.assertEqual(
            tuple(
                choice.state.set_key
                for choice in domain.proposals[0].state.choices
            ),
            ("zeta", "zeta", "zeta", "zeta"),
        )

    def test_each_package_keeps_balanced_and_material_full_layout_witnesses(
        self,
    ) -> None:
        context = _context()
        profiles = _profiles_with_em_focus(self.wearers)
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=profiles,
            set_impact=_set_impact(context, self.wearers),
        )

        for pool in domain.wearer_pools:
            layout_by_id = dict(pool.layouts)
            for package_key in domain.package_keys:
                package_rows = tuple(
                    item for item in pool.alternatives
                    if item.package_key == package_key
                )
                anchors = tuple(
                    item for item in package_rows
                    if item.package_anchor
                )
                self.assertEqual(len(anchors), 1)
                self.assertTrue(anchors[0].profile_id.endswith("_balanced"))
                self.assertTrue(
                    any(
                        "package_witness" in item.diversity_tags
                        for item in package_rows
                    )
                )
                self.assertGreaterEqual(
                    len({item.layout_id for item in package_rows}),
                    4,
                )
                self.assertTrue(
                    any(
                        item.profile_id.endswith("_focus_em")
                        for item in package_rows
                    )
                )
                self.assertTrue(
                    any(
                        (
                            layout_by_id[item.layout_id].sands == "em"
                            and layout_by_id[item.layout_id].goblet
                            == "dendro%"
                            and layout_by_id[item.layout_id].circlet
                            == "cr"
                        )
                        for item in package_rows
                    ),
                    "mixed reaction/direct triple must reach the package pool",
                )
                self.assertEqual(
                    {
                        layout_by_id[item.layout_id].circlet
                        for item in package_rows
                        if layout_by_id[item.layout_id].circlet
                        in {"cr", "cd"}
                    },
                    {"cr", "cd"},
                    "every screened package must keep both crit balances",
                )

    def test_noisy_crit_response_keeps_both_mixed_crit_circlets(self) -> None:
        context = _context(modeled_keys=("alpha",))
        plan = GcsimOptimizerTheoreticalAnytimeCandidatePlan(
            max_layouts_per_wearer=3,
            max_profiles_per_wearer=1,
            max_package_anchors_per_wearer=1,
            max_quick_four_piece_anchors_per_wearer=1,
            max_quick_two_plus_two_anchors_per_wearer=1,
            max_wearer_alternatives=3,
            max_joint_package_anchor_proposals=3,
            max_joint_proposals=4,
        )
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=self.wearers,
            response_profiles=(
                _profiles_with_noisy_crit_and_em_crowding(self.wearers)
            ),
            set_impact=_set_impact(context, self.wearers),
            plan=plan,
        )

        expected_layouts = {
            ("em", "em", "em"),
            ("atk%", "dendro%", "cr"),
            ("atk%", "dendro%", "cd"),
        }
        for pool in domain.wearer_pools:
            layouts = {
                (layout.sands, layout.goblet, layout.circlet)
                for _layout_id, layout in pool.layouts
            }
            self.assertEqual(layouts, expected_layouts)
            package_rows = tuple(
                item
                for item in pool.alternatives
                if item.package_key == "alpha"
            )
            self.assertEqual(
                {item.layout_id for item in package_rows},
                {layout_id for layout_id, _layout in pool.layouts},
            )
            self.assertEqual(
                {
                    layout.circlet
                    for _layout_id, layout in pool.layouts
                    if layout.circlet in {"cr", "cd"}
                },
                {"cr", "cd"},
            )
            self.assertTrue(
                all(
                    "main_archetype_scaling_direct"
                    in item.diversity_tags
                    for item in package_rows
                    if item.layout.circlet in {"cr", "cd"}
                )
            )

    def test_pair_representatives_are_canonical_and_inventory_independent(
        self,
    ) -> None:
        context = _context()
        pair_ab = _pair(context, "alpha", "beta")
        pair_bg = _pair(context, "beta", "gamma")
        packages = {
            gcsim_theoretical_pair_package_key(pair_bg): pair_bg,
            gcsim_theoretical_pair_package_key(pair_ab): pair_ab,
        }
        pair_plan = replace(
            self.plan,
            max_package_anchors_per_wearer=2,
            max_wearer_alternatives=10,
        )

        domain = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=context,
                wearers=self.wearers,
                response_profiles=self.profiles,
                set_impact=_set_impact(
                    context,
                    self.wearers,
                    packages=packages,
                ),
                two_plus_two_packages=packages,
                plan=pair_plan,
            )
        )

        self.assertEqual(
            domain.package_kind,
            GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO,
        )
        self.assertEqual(domain.package_keys, tuple(sorted(packages)))
        self.assertTrue(
            all(
                alternative.package_key in packages
                for pool in domain.wearer_pools
                for alternative in pool.alternatives
            )
        )
        self.assertEqual(
            tuple(domain.layout_catalog),
            ("alpha", "beta", "gamma", "delta"),
        )

    def test_er_response_weight_and_er_main_score_fail_closed(self) -> None:
        er_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("er")
        source = self.profiles[0]
        er_weights = list(source.stat_weights)
        er_weights[er_index] = 1.0
        er_classifications = tuple(
            (
                axis,
                "secondary" if axis == "er" else classification,
            )
            for axis, classification in source.stat_classifications
        )
        weighted = (
            replace(
                source,
                stat_weights=tuple(er_weights),
                stat_classifications=er_classifications,
            ),
            *self.profiles[1:],
        )

        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "cannot weight ER",
        ):
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=_context(),
                wearers=self.wearers,
                response_profiles=weighted,
                set_impact=_set_impact(_context(), self.wearers),
                plan=self.plan,
            )

        er_main_rows = (*source.main_scores, ("sands", "er", 1.0))
        er_main_classifications = (
            *source.main_classifications,
            ("sands", "er", "secondary"),
        )
        main_scored = (
            replace(
                source,
                main_scores=er_main_rows,
                main_classifications=er_main_classifications,
            ),
            *self.profiles[1:],
        )
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "cannot score an ER main",
        ):
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=_context(),
                wearers=self.wearers,
                response_profiles=main_scored,
                set_impact=_set_impact(_context(), self.wearers),
                plan=self.plan,
            )

    def test_caps_cannot_remove_required_diversity(self) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "positive integer",
        ):
            GcsimOptimizerTheoreticalAnytimeCandidatePlan(
                max_layouts_per_wearer=0,
            )
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "at least 3",
        ):
            GcsimOptimizerTheoreticalAnytimeCandidatePlan(
                max_layouts_per_wearer=2,
            )
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "package/layout witnesses",
        ):
            replace(self.plan, max_wearer_alternatives=2)
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeCandidateError,
            "screen-64",
        ):
            replace(
                self.plan,
                max_quick_two_plus_two_anchors_per_wearer=31,
            )


def _wearers() -> tuple[GcsimOptimizerWearerIdentity, ...]:
    return tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=slot,
            account_character_id=None,
            gcsim_character_key=key,
        )
        for slot, key in enumerate(
            ("alpha", "beta", "gamma", "delta"),
            start=1,
        )
    )


def _profiles(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    return tuple(
        _profile(wearer, profile_id)
        for wearer in wearers
        for profile_id in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
    )


def _profiles_with_em_focus(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    result = []
    em_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("em")
    for wearer in wearers:
        balanced = _profile(wearer, "balanced")
        weights = list(balanced.stat_weights)
        weights[em_index] = 100.0
        main_scores = tuple(
            (
                slot,
                axis,
                1_000.0 if axis == "em" else score,
            )
            for slot, axis, score in balanced.main_scores
        )
        result.extend(
            (
                balanced,
                replace(
                    balanced,
                    profile_id="focus_em",
                    stat_weights=tuple(weights),
                    main_scores=main_scores,
                    feature_labels=("fixture", "response_focus:em"),
                ),
            )
        )
    return tuple(result)


def _profiles_with_noisy_crit_and_em_crowding(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    useful_main_scores = {
        ("sands", "atk%"): 100.0,
        ("sands", "em"): 1_000.0,
        ("goblet", "dendro%"): 100.0,
        ("goblet", "em"): 1_000.0,
        ("circlet", "cr"): 10.0,
        ("circlet", "em"): 1_000.0,
    }
    legal = {
        "sands": ("hp%", "atk%", "def%", "em"),
        "goblet": (
            "hp%",
            "atk%",
            "def%",
            "em",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
            "phys%",
        ),
        "circlet": ("hp%", "atk%", "def%", "em", "cr", "cd", "heal"),
    }
    stat_weight_by_axis = {
        "atk%": 1.0,
        "em": 10.0,
        "cr": 1.0,
    }
    result = []
    for wearer in wearers:
        main_scores = tuple(
            (
                slot,
                axis,
                useful_main_scores.get((slot, axis), 0.0),
            )
            for slot, axes in legal.items()
            for axis in axes
        )
        result.append(
            GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id="balanced",
                stat_weights=tuple(
                    stat_weight_by_axis.get(axis, 0.0)
                    for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_scores=main_scores,
                evidence_sha256="e" * 64,
                feature_labels=("fixture", "noisy_crit"),
                stat_classifications=tuple(
                    (
                        axis,
                        (
                            "secondary"
                            if stat_weight_by_axis.get(axis, 0.0) > 0
                            else "negligible"
                        ),
                    )
                    for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_classifications=tuple(
                    (
                        slot,
                        axis,
                        (
                            "secondary"
                            if score > 0
                            else "negligible"
                        ),
                    )
                    for slot, axis, score in main_scores
                ),
            )
        )
    return tuple(result)


def _profile(
    wearer: GcsimOptimizerWearerIdentity,
    profile_id: str,
) -> GcsimOptimizerAnytimeStatProfile:
    weights = {
        "atk%": 1.0,
        "cr": 1.0,
        "cd": 1.0,
        "em": 0.5,
        "hp%": 0.25,
        "def%": 0.25,
    }
    if profile_id != "balanced":
        raise AssertionError(f"unexpected fixture profile: {profile_id}")
    preferred = ("atk%", "dendro%", "cr")
    legal = {
        "sands": ("hp%", "atk%", "def%", "em"),
        "goblet": (
            "hp%",
            "atk%",
            "def%",
            "em",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
            "phys%",
        ),
        "circlet": ("hp%", "atk%", "def%", "em", "cr", "cd", "heal"),
    }
    main_scores = tuple(
        (
            slot,
            axis,
            20.0 if axis == preferred[index] else 1.0,
        )
        for index, slot in enumerate(("sands", "goblet", "circlet"))
        for axis in legal[slot]
    )
    return GcsimOptimizerAnytimeStatProfile(
        wearer=wearer,
        profile_id=profile_id,
        stat_weights=tuple(
            0.0 if axis == "er" else weights.get(axis, 0.0)
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        ),
        main_scores=main_scores,
        evidence_sha256="e" * 64,
        feature_labels=("fixture",),
    )


def _context(
    *,
    modeled_keys: tuple[str, ...] = (
        "zeta",
        "alpha",
        "epsilon",
        "beta",
        "delta",
        "gamma",
    ),
) -> GcsimOptimizerEngineContext:
    capabilities = tuple(
        _capability(key, max_rarity=5, modeled=True)
        for key in modeled_keys
    ) + (
        _capability("fourstar", max_rarity=4, modeled=True),
        _capability("incomplete", max_rarity=5, modeled=False),
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=capabilities,
    )
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root="fixture",
        engine_version="fixture",
        optimizer_contract_version="fixture",
        artifact_path="fixture.exe",
        artifact_sha256="a" * 64,
        engine_tree_sha256="b" * 64,
        catalog=catalog,
        manifest_artifact_sha256="a" * 64,
        manifest_engine_tree_sha256="b" * 64,
        binding_sha256="d" * 64,
        trusted=True,
    )


def _set_impact(
    context: GcsimOptimizerEngineContext,
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    *,
    packages: dict[str, GcsimTwoPlusTwoTargetPackage] | None = None,
    score_by_key: dict[str, float] | None = None,
) -> GcsimOptimizerSetImpactResult:
    score_index = score_by_key or {}
    if packages is None:
        package_rows = tuple(
            (
                capability.key,
                GcsimFourPieceTargetPackage(
                    GcsimOptimizerSetReference(
                        set_uid=capability.key,
                        gcsim_set_key=capability.key,
                        engine_binding_sha256=context.binding_sha256,
                        catalog_fingerprint=(
                            context.catalog.source_fingerprint
                        ),
                    )
                ),
            )
            for capability in context.catalog.sets
            if capability.max_rarity == 5
            and capability.optimizer_four_piece_ready
        )
    else:
        package_rows = tuple(packages.items())
    estimate = GcsimStatResponseEstimate(
        count=8,
        mean=1.0,
        sample_sd=0.0,
        standard_error=0.0,
    )
    rows = tuple(
        GcsimOptimizerSetImpactRow(
            target=GcsimOptimizerWearerTarget(
                wearer=wearer,
                package=package,
            ),
            classification=(
                GcsimOptimizerSetImpactClassification.TEAM_POSITIVE
            ),
            team_delta=estimate,
            personal_delta=estimate,
            character_deltas=(estimate,) * 4,
            surrogate_dps=float(score_index.get(package_key, 1.0)),
            evidence_sha256=(
                f"{wearer.team_slot:02x}"
                + package.identity_sha256
            )[-64:],
        )
        for wearer in wearers
        for package_key, package in package_rows
    )
    return GcsimOptimizerSetImpactResult(
        rows=rows,
        plan=GcsimOptimizerSetImpactPlan(),
        response_evidence_sha256="e" * 64,
        elapsed_seconds=0.0,
        batch_count=1,
    )


def _capability(
    key: str,
    *,
    max_rarity: int,
    modeled: bool,
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=max_rarity,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=modeled,
        two_piece_modeled=True,
        four_piece_modeled=modeled,
    )


def _pair(
    context: GcsimOptimizerEngineContext,
    left: str,
    right: str,
) -> GcsimTwoPlusTwoTargetPackage:
    def reference(key: str) -> GcsimOptimizerSetReference:
        return GcsimOptimizerSetReference(
            set_uid=f"uid-{key}",
            gcsim_set_key=key,
            engine_binding_sha256=context.binding_sha256,
            catalog_fingerprint=context.catalog.source_fingerprint,
        )

    return GcsimTwoPlusTwoTargetPackage(
        set_a=reference(left),
        set_b=reference(right),
    )


def _wide_pair_packages(
    context: GcsimOptimizerEngineContext,
    set_keys: tuple[str, ...],
) -> dict[str, GcsimTwoPlusTwoTargetPackage]:
    result = {}
    for left, right in combinations(set_keys, 2):
        package = _pair(context, left, right)
        result[gcsim_theoretical_pair_package_key(package)] = package
    return result


if __name__ == "__main__":
    unittest.main()
