from __future__ import annotations

from dataclasses import replace
import unittest

import run_workspace.gcsim as gcsim_api
from hoyolab_export.artifact_stats import (
    CRIT_DAMAGE,
    ELEMENTAL_MASTERY,
    ENERGY_RECHARGE,
    HYDRO_DAMAGE,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
)
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from run_workspace.gcsim.optimizer_main_response import (
    GcsimOptimizerFourPieceMainDomain,
    GcsimOptimizerReachableMainLayout,
    GcsimOptimizerResponseBranchKind,
    GcsimOptimizerResponseMeasurement,
    GcsimOptimizerResponseObservation,
    GcsimOptimizerResponsePlanningLimits,
    GcsimOptimizerResponseProbeKind,
    analyze_gcsim_optimizer_response_observations,
    build_gcsim_optimizer_reference_probes,
    build_gcsim_optimizer_response_probe_plan,
    build_gcsim_optimizer_response_probe_stat_profile,
    enumerate_gcsim_optimizer_reachable_four_piece_main_domain,
    run_gcsim_optimizer_main_response_discovery,
)
from run_workspace.gcsim.optimizer_oracle import (
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)

from ._optimizer_oracle_fixtures import (
    build_oracle_account_environment,
)


class GcsimOptimizerMainResponseTests(unittest.TestCase):
    def test_public_facade_exports_milestone_four_boundary(self) -> None:
        expected = {
            "GcsimOptimizerFourPieceMainDomain",
            "GcsimOptimizerResponseProbePlan",
            "GcsimOptimizerMainResponseResult",
            "enumerate_gcsim_optimizer_reachable_four_piece_main_domain",
            "build_gcsim_optimizer_response_probe_plan",
            "build_gcsim_optimizer_reference_probes",
            "run_gcsim_optimizer_main_response_discovery",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_database_reachability_is_package_scoped_and_fail_closed(self) -> None:
        environment = build_oracle_account_environment()

        domain = enumerate_gcsim_optimizer_reachable_four_piece_main_domain(
            environment.run_input,
            target=environment.targets[0],
        )

        self.assertEqual(domain.wearer, environment.wearers[0])
        self.assertEqual(domain.package, environment.targets[0].package)
        self.assertEqual(
            tuple(item.layout_id for item in domain.reachable_layouts),
            ("main/atkpct-pyropct-cr",),
        )
        self.assertEqual(
            domain.reachable_layouts[0].maximum_target_piece_count,
            5,
        )
        self.assertGreaterEqual(
            dict(domain.excluded_artifact_counts)[
                "artifact_calculation_invalid"
            ],
            1,
        )

        impossible = replace(
            environment.targets[0],
            package=GcsimFourPieceTargetPackage(
                GcsimOptimizerSetReference(
                    set_uid="AbsentSet",
                    gcsim_set_key="absentset",
                    engine_binding_sha256="3" * 64,
                    catalog_fingerprint="4" * 64,
                )
            ),
        )
        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "no reachable legal 4p main-stat layout",
        ):
            enumerate_gcsim_optimizer_reachable_four_piece_main_domain(
                environment.run_input,
                target=impossible,
            )

    def test_reachability_proves_set_count_without_complete_builds(self) -> None:
        environment = build_oracle_account_environment()
        run_input = _extended_main_layout_run_input(environment)

        domain = enumerate_gcsim_optimizer_reachable_four_piece_main_domain(
            run_input,
            target=environment.targets[0],
        )
        reachable_ids = {item.layout_id for item in domain.reachable_layouts}

        self.assertIn("main/em-em-em", reachable_ids)
        self.assertIn("main/em-hydropct-em", reachable_ids)
        self.assertNotIn("main/er-hydropct-cd", reachable_ids)
        triple_em = next(
            item
            for item in domain.reachable_layouts
            if item.layout_id == "main/em-em-em"
        )
        self.assertEqual(triple_em.maximum_target_piece_count, 5)

    def test_probe_plan_uses_exact_equal_budget_multiscale_exchanges(self) -> None:
        plan = build_gcsim_optimizer_response_probe_plan(
            _domain(),
            frozen_team_context_sha256="a" * 64,
        )
        reference_only = build_gcsim_optimizer_reference_probes(
            plan.domain,
            frozen_team_context_sha256="a" * 64,
        )

        reference_count = sum(
            item.kind is GcsimOptimizerResponseProbeKind.REFERENCE
            for item in plan.probes
        )
        self.assertEqual(reference_count, len(plan.domain.reachable_layouts))
        self.assertEqual(
            reference_only,
            tuple(
                item
                for item in plan.probes
                if item.kind is GcsimOptimizerResponseProbeKind.REFERENCE
            ),
        )
        self.assertEqual(plan.exchange_scales, (1, 4, 8))
        self.assertTrue(
            all("er" not in axes for axes in plan.interaction_axes)
        )
        self.assertTrue(
            all(
                "er" not in probe.focus_axes
                for probe in plan.probes
                if probe.kind is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
            )
        )
        self.assertIn(("atk%", "em"), plan.interaction_axes)
        signatures = {
            item.allocation.investment_signature for item in plan.probes
        }
        self.assertEqual(len(signatures), 1)
        self.assertTrue(
            all(
                sum(
                    roll.liquid_rolls
                    for roll in probe.allocation.rolls
                )
                == probe.allocation.total_liquid_substats
                for probe in plan.probes
            )
        )
        for probe in plan.probes:
            profile = build_gcsim_optimizer_response_probe_stat_profile(probe)
            self.assertTrue(profile.weights)
        em_scales = {
            item.exchange_rolls
            for item in plan.probes
            if item.kind is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
            and item.focus_axes == ("em",)
        }
        self.assertTrue({1, 4, 8}.issubset(em_scales))
        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "max_planned_probes",
        ):
            build_gcsim_optimizer_response_probe_plan(
                _domain(),
                frozen_team_context_sha256="a" * 64,
                limits=GcsimOptimizerResponsePlanningLimits(
                    max_planned_probes=10,
                ),
            )

    def test_joint_em_winner_survives_when_isolated_em_layouts_lose(self) -> None:
        result = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                _domain(),
                frozen_team_context_sha256="a" * 64,
            ),
            evaluator=_adversarial_measurement,
        )

        triple_em = "main/em-em-em"
        triple_branches = tuple(
            item for item in result.branches if item.layout_id == triple_em
        )
        self.assertTrue(
            any(
                item.kind is GcsimOptimizerResponseBranchKind.COUPLED_EM
                and "joint_em_beats_isolated_em" in item.reasons
                for item in triple_branches
            )
        )
        self.assertTrue(
            any(
                "em_safeguard_forced_reachable_mixed_or_joint_layout"
                in item.reasons
                for item in triple_branches
            )
        )
        isolated_ids = {
            "main/em-pyropct-cr",
            "main/atkpct-em-cr",
            "main/atkpct-pyropct-em",
        }
        reference_scores = {
            item.probe.layout_id: item.measurement.score.objective_value
            for item in result.observations
            if item.probe.kind is GcsimOptimizerResponseProbeKind.REFERENCE
        }
        self.assertTrue(
            all(
                reference_scores[layout_id]
                < reference_scores["main/atkpct-pyropct-cr"]
                for layout_id in isolated_ids
            )
        )
        self.assertGreater(
            reference_scores[triple_em],
            reference_scores["main/atkpct-pyropct-cr"],
        )
        self.assertEqual(len(result.trace_rows), len(result.branches))
        self.assertTrue(
            all(item.evidence_probe_sha256s for item in result.trace_rows)
        )

    def test_batch_evaluator_preserves_probe_order_and_skips_scalar_path(self) -> None:
        plan = build_gcsim_optimizer_response_probe_plan(
            _domain(),
            frozen_team_context_sha256="a" * 64,
        )

        class BatchEvaluator:
            def __call__(self, _probe):
                raise AssertionError("scalar evaluator path must not run")

            def evaluate_many(self, probes):
                return tuple(
                    GcsimOptimizerResponseObservation(
                        probe=probe,
                        measurement=_adversarial_measurement(probe),
                    )
                    for probe in probes
                )

        result = run_gcsim_optimizer_main_response_discovery(
            plan,
            evaluator=BatchEvaluator(),
        )

        self.assertEqual(
            tuple(item.probe.probe_sha256 for item in result.observations),
            tuple(item.probe_sha256 for item in plan.probes),
        )

    def test_support_and_unusual_regions_survive_without_automatic_er_axis(self) -> None:
        result = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                _domain(),
                frozen_team_context_sha256="b" * 64,
            ),
            evaluator=_adversarial_measurement,
        )

        branch_kinds_by_layout = {}
        for branch in result.branches:
            branch_kinds_by_layout.setdefault(branch.layout_id, set()).add(
                branch.kind
            )
        self.assertIn(
            GcsimOptimizerResponseBranchKind.SUPPORT,
            branch_kinds_by_layout["main/hppct-hppct-heal"],
        )
        self.assertIn(
            GcsimOptimizerResponseBranchKind.SUPPORT,
            branch_kinds_by_layout["main/defpct-defpct-defpct"],
        )
        self.assertTrue(all("er" not in branch.focus_axes for branch in result.branches))
        self.assertTrue(
            any(
                branch.kind
                is GcsimOptimizerResponseBranchKind.UNUSUAL_MAIN
                for branch in result.branches
            )
        )

    def test_set_effect_reopens_response_without_character_rules(self) -> None:
        first_domain = _domain()
        second_domain = replace(
            first_domain,
            package=_package("responseb"),
        )
        first = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                first_domain,
                frozen_team_context_sha256="c" * 64,
            ),
            evaluator=_set_aware_measurement,
        )
        second = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                second_domain,
                frozen_team_context_sha256="c" * 64,
            ),
            evaluator=_set_aware_measurement,
        )

        def has_def_exchange(result) -> bool:
            return any(
                item.focus_axes == ("def%",)
                and "material_roll_exchange" in item.reasons
                for item in result.branches
            )

        self.assertFalse(has_def_exchange(first))
        self.assertTrue(has_def_exchange(second))

        renamed = replace(
            first_domain,
            wearer=GcsimOptimizerWearerIdentity(
                team_slot=1,
                account_character_id=99_999,
                gcsim_character_key="renamed",
            ),
        )
        renamed_result = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                renamed,
                frozen_team_context_sha256="c" * 64,
            ),
            evaluator=_set_aware_measurement,
        )
        self.assertEqual(
            first.decision_signature,
            renamed_result.decision_signature,
        )

    def test_upstream_seed_cannot_delete_independent_main_regions(self) -> None:
        domain = _domain()
        base_plan = build_gcsim_optimizer_response_probe_plan(
            domain,
            frozen_team_context_sha256="d" * 64,
        )
        reference = next(
            item
            for item in base_plan.probes
            if item.kind is GcsimOptimizerResponseProbeKind.REFERENCE
        )
        seeded_plan = build_gcsim_optimizer_response_probe_plan(
            domain,
            frozen_team_context_sha256="d" * 64,
            upstream_seed_allocations={
                reference.layout_id: reference.allocation,
            },
        )
        base = run_gcsim_optimizer_main_response_discovery(
            base_plan,
            evaluator=_adversarial_measurement,
        )
        seeded = run_gcsim_optimizer_main_response_discovery(
            seeded_plan,
            evaluator=_adversarial_measurement,
        )

        base_decisions = set(base.decision_signature)
        seeded_non_upstream = {
            item.decision_key
            for item in seeded.branches
            if item.kind
            is not GcsimOptimizerResponseBranchKind.UPSTREAM_SEED
        }
        self.assertEqual(base_decisions, seeded_non_upstream)
        self.assertTrue(
            any(
                item.kind
                is GcsimOptimizerResponseBranchKind.UPSTREAM_SEED
                for item in seeded.branches
            )
        )

    def test_missing_reaction_ownership_fails_open_for_em(self) -> None:
        result = run_gcsim_optimizer_main_response_discovery(
            build_gcsim_optimizer_response_probe_plan(
                _domain(),
                frozen_team_context_sha256="9" * 64,
            ),
            evaluator=lambda probe: _measurement(probe, 100.0, ""),
        )

        self.assertTrue(
            any(
                item.focus_axes == ("em",)
                and "reaction_ownership_unavailable" in item.reasons
                for item in result.branches
            )
        )
        em_layout_ids = {
            item.layout_id
            for item in result.plan.domain.reachable_layouts
            if item.em_main_count >= 1
        }
        safeguarded_ids = {
            item.layout_id
            for item in result.branches
            if (
                "em_safeguard_forced_reachable_mixed_or_joint_layout"
                in item.reasons
            )
        }
        self.assertEqual(safeguarded_ids, em_layout_ids)

    def test_observation_domain_must_be_complete_and_ordered(self) -> None:
        plan = build_gcsim_optimizer_response_probe_plan(
            _domain(),
            frozen_team_context_sha256="e" * 64,
        )
        result = run_gcsim_optimizer_main_response_discovery(
            plan,
            evaluator=_adversarial_measurement,
        )

        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "cover the response plan exactly",
        ):
            analyze_gcsim_optimizer_response_observations(
                plan,
                result.observations[:-1],
            )


def _domain() -> GcsimOptimizerFourPieceMainDomain:
    wearer = GcsimOptimizerWearerIdentity(
        team_slot=1,
        account_character_id=30_001,
        gcsim_character_key="alpha",
    )
    layouts = (
        GcsimFiveStarMainStatLayout("atk%", "pyro%", "cr"),
        GcsimFiveStarMainStatLayout("em", "pyro%", "cr"),
        GcsimFiveStarMainStatLayout("atk%", "em", "cr"),
        GcsimFiveStarMainStatLayout("atk%", "pyro%", "em"),
        GcsimFiveStarMainStatLayout("em", "em", "em"),
        GcsimFiveStarMainStatLayout("er", "electro%", "cr"),
        GcsimFiveStarMainStatLayout("hp%", "hp%", "heal"),
        GcsimFiveStarMainStatLayout("def%", "def%", "def%"),
        GcsimFiveStarMainStatLayout("atk%", "dendro%", "cd"),
    )
    evidence = tuple(
        (slot, (index,))
        for index, slot in enumerate(
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
            start=1,
        )
    )
    reachable = tuple(
        sorted(
            (
                GcsimOptimizerReachableMainLayout(
                    layout=layout,
                    supporting_artifact_ids_by_slot=evidence,
                    maximum_target_piece_count=4,
                )
                for layout in layouts
            ),
            key=lambda item: item.layout_id,
        )
    )
    return GcsimOptimizerFourPieceMainDomain(
        run_input_sha256="f" * 64,
        wearer=wearer,
        package=_package("responsea"),
        reachable_layouts=reachable,
        eligible_artifact_ids_by_slot=evidence,
        excluded_artifact_counts=(),
    )


def _extended_main_layout_run_input(environment):
    alpha_ref = environment.set_refs[0]
    templates = {
        artifact.position_key: artifact
        for artifact in environment.database.artifacts
        if artifact.set_uid == alpha_ref.set_uid
    }
    next_id = max(
        item.artifact_id for item in environment.database.artifacts
    ) + 1
    additions = []

    def add(
        slot: str,
        property_type: int,
        property_name: str,
        property_value: str,
        *,
        target_set: bool,
    ) -> None:
        nonlocal next_id
        template = templates[slot]
        set_uid = (
            alpha_ref.set_uid
            if target_set
            else f"OffpieceMain{next_id}"
        )
        additions.append(
            replace(
                template,
                artifact_id=next_id,
                set_uid=set_uid,
                gcsim_set_key=(
                    alpha_ref.gcsim_set_key if target_set else ""
                ),
                set_mapping_status=("ready" if target_set else "unmapped"),
                rarity=(4 if target_set else 5),
                level=(16 if target_set else 20),
                main_property_type=property_type,
                main_property_name=property_name,
                main_property_value=property_value,
                main_numeric_value=float(property_value.rstrip("%")),
                substats=(),
                default_eligible=not target_set,
                raw_columns=(
                    ("id", next_id),
                    ("set_uid", set_uid),
                    ("pos", template.position),
                    ("rarity", 4 if target_set else 5),
                    ("level", 16 if target_set else 20),
                    ("main_property_type", property_type),
                    ("main_property_name", property_name),
                    ("main_property_value", property_value),
                ),
            )
        )
        next_id += 1

    add("sands", ELEMENTAL_MASTERY, "Elemental Mastery", "187", target_set=True)
    add("goblet", ELEMENTAL_MASTERY, "Elemental Mastery", "187", target_set=True)
    add(
        "circlet",
        ELEMENTAL_MASTERY,
        "Elemental Mastery",
        "187",
        target_set=True,
    )
    add(
        "sands",
        ENERGY_RECHARGE,
        "Energy Recharge",
        "51.8%",
        target_set=False,
    )
    add(
        "goblet",
        HYDRO_DAMAGE,
        "Hydro DMG",
        "46.6%",
        target_set=False,
    )
    add(
        "circlet",
        CRIT_DAMAGE,
        "CRIT DMG",
        "62.2%",
        target_set=False,
    )
    artifacts = tuple(
        sorted(
            (*environment.database.artifacts, *additions),
            key=lambda item: item.artifact_id,
        )
    )
    database = GcsimOptimizerArtifactDatabaseInput(
        database_path=environment.database.database_path,
        artifact_database_input_sha256=(
            environment.database.artifact_database_input_sha256
        ),
        engine_binding_sha256=environment.database.engine_binding_sha256,
        catalog_fingerprint=environment.database.catalog_fingerprint,
        artifact_columns=environment.database.artifact_columns,
        substat_columns=environment.database.substat_columns,
        artifacts=artifacts,
        raw_substat_row_count=sum(len(item.substats) for item in artifacts),
        issues=environment.database.issues,
    )
    result = build_gcsim_optimizer_run_input(
        request=environment.request,
        config_shell=environment.shell,
        artifact_database=database,
        engine_context=environment.engine,
    )
    assert result.ready and result.run_input is not None
    return result.run_input


def _package(key: str) -> GcsimFourPieceTargetPackage:
    return GcsimFourPieceTargetPackage(
        GcsimOptimizerSetReference(
            set_uid=key.title(),
            gcsim_set_key=key,
            engine_binding_sha256="3" * 64,
            catalog_fingerprint="4" * 64,
        )
    )


def _adversarial_measurement(probe) -> GcsimOptimizerResponseMeasurement:
    reference_scores = {
        "main/atkpct-pyropct-cr": 100.0,
        "main/em-pyropct-cr": 90.0,
        "main/atkpct-em-cr": 91.0,
        "main/atkpct-pyropct-em": 92.0,
        "main/em-em-em": 150.0,
        "main/er-electropct-cr": 108.0,
        "main/hppct-hppct-heal": 112.0,
        "main/defpct-defpct-defpct": 109.0,
        "main/atkpct-dendropct-cd": 106.0,
    }
    value = reference_scores[probe.layout_id]
    reaction = "ordinary_owner"
    if probe.kind is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE:
        axes = set(probe.focus_axes)
        if "em" in axes:
            value += -1.0 if probe.exchange_rolls == 1 else (
                probe.exchange_rolls**2
            )
            if probe.exchange_rolls >= 4:
                reaction = "em_reaction_owner"
        elif axes.intersection({"er", "cr"}):
            value += 2.0 * probe.exchange_rolls
        elif axes.intersection({"hp%", "def%"}):
            value += 1.5 * probe.exchange_rolls
        else:
            value += 1.0 * probe.exchange_rolls
    elif (
        probe.kind
        is GcsimOptimizerResponseProbeKind.UPSTREAM_OPTIMIZED_SEED
    ):
        value = 1.0
    return _measurement(probe, value, reaction)


def _set_aware_measurement(probe) -> GcsimOptimizerResponseMeasurement:
    value = 100.0
    if (
        probe.kind is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
        and probe.focus_axes == ("def%",)
        and probe.package.set_ref.gcsim_set_key == "responseb"
    ):
        value += 3.0 * probe.exchange_rolls
    return _measurement(probe, value, "stable_owner")


def _measurement(
    probe,
    value: float,
    reaction_signature: str,
) -> GcsimOptimizerResponseMeasurement:
    return GcsimOptimizerResponseMeasurement(
        score=GcsimOptimizerOracleScore(
            objective_name="synthetic_team_dps",
            objective_value=value,
            standard_error=0.1,
            iterations=1000,
            evidence_sha256=probe.probe_sha256,
        ),
        reaction_signature=reaction_signature,
    )


if __name__ == "__main__":
    unittest.main()
