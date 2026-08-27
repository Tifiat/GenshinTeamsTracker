from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.artifact_set_catalog import GcsimArtifactSetCatalog
from run_workspace.gcsim.optimizer_account_evaluator import (
    build_gcsim_optimizer_account_candidate_keys,
)
from run_workspace.gcsim.optimizer_all_set_service import (
    GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
    GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
    GcsimOptimizerAllSetPlan,
    derive_gcsim_optimizer_all_database_set_refs,
    derive_gcsim_optimizer_source_package_anchor,
    run_gcsim_optimizer_all_database_sets,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeStatProfile,
    build_gcsim_optimizer_dense_artifact_catalog,
    build_gcsim_optimizer_soft_main_coverage_profiles,
    generate_gcsim_optimizer_anytime_wearer_pool,
)
from run_workspace.gcsim.optimizer_anytime_race import (
    GcsimOptimizerAnytimeRaceResult,
    GcsimOptimizerAnytimeRaceStatus,
    build_gcsim_optimizer_account_package_signature,
)
from run_workspace.gcsim.optimizer_anytime_selected_service import (
    GcsimOptimizerAnytimeSelectedSession,
    _AnytimeSelectedInterrupted,
    _retain_signature_coordinate_frontiers,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerAccountScope,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerWorkPlan,
    GcsimTwoPlusTwoTargetPackage,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)
from run_workspace.gcsim.optimizer_set_impact import (
    GcsimOptimizerSetImpactClassification,
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSetImpactRow,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimStatResponseEstimate,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment
from .test_gcsim_optimizer_anytime_selected_service import (
    _ImmediateSessionFactory,
    _ResponseDiscovery,
    _plan,
)


class GcsimOptimizerAllSetServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        base = _plan()
        self.plan = GcsimOptimizerAllSetPlan(
            account_plan=replace(
                base,
                candidates=replace(
                    base.candidates,
                    max_builds_per_target=16,
                    max_builds_per_wearer=64,
                ),
            )
        )
        self.environment = _all_set_environment(self.plan)

    def test_public_facade_exports_bounded_all_set_boundary(self) -> None:
        expected = {
            "GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION",
            "GcsimOptimizerAllSetPlan",
            "GcsimOptimizerAllSetResult",
            "GcsimOptimizerAllSetSession",
            "derive_gcsim_optimizer_all_database_set_refs",
            "run_gcsim_optimizer_all_database_sets",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_plan_uses_same_bounded_anytime_account_kernel(self) -> None:
        payload = self.plan.to_dict()

        self.assertEqual(payload["claim"], "best_found_under_frozen_budget")
        self.assertEqual(
            payload["account_plan"]["plan_id"],
            "anytime_approx_v2",
        )

    def test_derivation_uses_only_modeled_mapped_five_star_sets(self) -> None:
        refs = derive_gcsim_optimizer_all_database_set_refs(
            self.environment.run_input
        )

        self.assertEqual(
            tuple(item.set_uid for item in refs),
            tuple(sorted(item.set_uid for item in self.environment.set_refs)),
        )

    def test_all_sets_use_bounded_kernel_and_return_exact_account_build(
        self,
    ) -> None:
        result = self._run(self.environment)

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertEqual(len(result.derived_set_refs), 4)
        self.assertEqual(result.package_bounds, ())
        self.assertEqual(len(result.package_decisions), 16)
        self.assertTrue(
            any(
                item.status == "validated"
                for item in result.package_decisions
            )
        )
        self.assertTrue(
            all(
                item.status
                in {
                    "candidate_retained",
                    "exact_screened",
                    "refined",
                    "validated",
                }
                for item in result.package_decisions
            )
        )
        self.assertIsNotNone(result.account_result)
        self.assertIsNotNone(result.best_found)
        artifact_ids = tuple(
            artifact_id
            for assignment in (
                result.best_found.account_assignment.wearer_assignments
            )
            for artifact_id in assignment.artifact_ids
        )
        self.assertEqual(len(artifact_ids), 20)
        self.assertEqual(len(set(artifact_ids)), 20)

    def test_every_confirmed_signature_gets_configured_coordinate_rounds(
        self,
    ) -> None:
        result = self._run(self.environment)
        account_result = result.account_result
        self.assertIsNotNone(account_result)
        self.assertEqual(
            len(account_result.preliminary_race_results),
            2 + 2 * self.plan.account_plan.coordinate_refinement_rounds,
        )
        races = (
            *account_result.preliminary_race_results,
            account_result.race_result,
        )
        initial_race = races[0]
        refined_race = races[1]
        self.assertIsNotNone(initial_race.best_confirmed)
        self.assertIsNotNone(refined_race)

        confirmed_signatures = tuple(
            dict.fromkeys(
                build_gcsim_optimizer_account_package_signature(
                    item.proposal.compiled_candidate.targets
                )
                for item in initial_race.confirmed_evaluations
            )
        )[: self.plan.local_refinement_signature_limit]
        refined_screen = tuple(
            item
            for item in refined_race.trace_evaluations
            if item.tier_id == "screen_8"
        )
        refined_signatures = {
            build_gcsim_optimizer_account_package_signature(
                item.proposal.compiled_candidate.targets
            )
            for item in refined_screen
        }

        self.assertTrue(refined_screen)
        self.assertTrue(refined_signatures)
        self.assertTrue(
            refined_signatures.issubset(set(confirmed_signatures))
        )
        for previous, current in zip(races, races[1:]):
            leaders = {}
            for evaluation in previous.confirmed_evaluations:
                signature = build_gcsim_optimizer_account_package_signature(
                    evaluation.proposal.compiled_candidate.targets
                )
                if signature in confirmed_signatures:
                    leaders.setdefault(signature, evaluation.proposal)
            self.assertEqual(set(leaders), set(confirmed_signatures))
            for tier_id in (
                "screen_8",
                "refine_32",
                "validate_200",
                "rerace_1000",
            ):
                tier_ids = {
                    item.proposal.proposal_sha256
                    for item in current.trace_evaluations
                    if item.tier_id == tier_id
                }
                self.assertTrue(
                    {
                        item.proposal_sha256
                        for item in leaders.values()
                    }.issubset(tier_ids)
                )
        coordinate_races = races[3::2]
        self.assertEqual(
            len(coordinate_races),
            self.plan.account_plan.coordinate_refinement_rounds,
        )
        for coordinate_race in coordinate_races:
            coordinate_signatures = {
                build_gcsim_optimizer_account_package_signature(
                    item.proposal.compiled_candidate.targets
                )
                for item in coordinate_race.trace_evaluations
                if item.tier_id == "screen_8"
                and any(
                    label.startswith("coordinate_fixed_slot:")
                    for label in item.proposal.diversity_labels
                )
            }
            self.assertEqual(
                coordinate_signatures,
                set(confirmed_signatures),
            )
        consolidation_races = races[2::2]
        self.assertEqual(
            len(consolidation_races),
            1 + self.plan.account_plan.coordinate_refinement_rounds,
        )
        for consolidation_race in consolidation_races:
            confirmed_counts = {
                signature: sum(
                    build_gcsim_optimizer_account_package_signature(
                        item.proposal.compiled_candidate.targets
                    )
                    == signature
                    for item in consolidation_race.confirmed_evaluations
                )
                for signature in confirmed_signatures
            }
            self.assertTrue(
                all(count >= 2 for count in confirmed_counts.values())
            )
        self.assertGreater(
            result.terminal.coverage.counters[
                "all_set_local_refinement_proposal_count"
            ],
            0,
        )
        self.assertEqual(
            result.account_result.plan.response.iterations,
            self.plan.response_minimum_iterations,
        )

    def test_deadline_during_signature_pool_build_preserves_confirmed_top(
        self,
    ) -> None:
        interruption = _AnytimeSelectedInterrupted(
            "synthetic_all_set_refinement_deadline",
            cancelled=False,
        )
        with patch.object(
            GcsimOptimizerAnytimeSelectedSession,
            "_build_local_refinement_families",
            side_effect=interruption,
        ):
            result = self._run(self.environment)

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.DEADLINE,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "synthetic_all_set_refinement_deadline",
        )
        self.assertIsNotNone(result.best_found)
        self.assertTrue(result.terminal.top_n.entries)
        self.assertIsNotNone(result.account_result.race_result.best_confirmed)

    def test_empty_deadline_race_returns_last_confirmed_race_and_top(
        self,
    ) -> None:
        original = GcsimOptimizerAnytimeSelectedSession._run_race_phase
        call_count = 0

        def deadline_after_initial(session, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return GcsimOptimizerAnytimeRaceResult(
                    status=GcsimOptimizerAnytimeRaceStatus.DEADLINE,
                    confirmed_evaluations=(),
                    trace_evaluations=(),
                    requested_by_tier=(),
                    successful_by_tier=(),
                    cache_hits_by_tier=(),
                    evidence_sha256="f" * 64,
                    elapsed_seconds=0.0,
                )
            return original(session, **kwargs)

        with patch.object(
            GcsimOptimizerAnytimeSelectedSession,
            "_run_race_phase",
            new=deadline_after_initial,
        ):
            result = self._run(self.environment)

        account_result = result.account_result
        self.assertEqual(call_count, 2)
        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.DEADLINE,
        )
        self.assertIsNotNone(result.best_found)
        self.assertTrue(account_result.race_result.confirmed_evaluations)
        self.assertTrue(
            any(
                item.status is GcsimOptimizerAnytimeRaceStatus.DEADLINE
                and not item.confirmed_evaluations
                for item in account_result.preliminary_race_results
            )
        )
        self.assertEqual(
            result.terminal.evidence_sha256["race"],
            account_result.race_result.evidence_sha256,
        )

    def test_coordinate_limit_is_applied_per_signature(self) -> None:
        rows_by_signature = []
        for signature_index in range(2):
            proposals = []
            for proposal_index in range(300):
                identity = signature_index * 300 + proposal_index + 1
                proposals.append(
                    SimpleNamespace(
                        changed_wearer_count=1,
                        surrogate_score=str(10_000 - proposal_index),
                        proposal_sha256=f"{identity:064x}",
                        diversity_labels=(
                            f"coordinate_fixed_slot:{signature_index + 1}",
                        ),
                        compiled_candidate=SimpleNamespace(
                            compiled_config_sha256=f"{identity + 1000:064x}",
                        ),
                    )
                )
            rows_by_signature.append(
                ((str(signature_index),) * 4, tuple(proposals))
            )

        retained = _retain_signature_coordinate_frontiers(
            rows_by_signature,
            limit=256,
        )

        self.assertEqual(len(retained), 512)
        for signature_index in range(2):
            lower = signature_index * 300 + 1
            upper = lower + 300
            self.assertEqual(
                sum(
                    lower <= int(item.proposal_sha256, 16) < upper
                    for item in retained
                ),
                256,
            )

    def test_source_anchor_survives_neutral_set_impact_false_negative(
        self,
    ) -> None:
        result = run_gcsim_optimizer_all_database_sets(
            self.environment.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(),
            set_impact_discovery=_SourceNegativeSetImpactDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
        )
        anchor = derive_gcsim_optimizer_source_package_anchor(
            self.environment.run_input,
            set_refs=result.derived_set_refs,
        )
        signature = build_gcsim_optimizer_account_package_signature(anchor)
        race_results = (
            *result.account_result.preliminary_race_results,
            result.account_result.race_result,
        )
        screened_signatures = {
            build_gcsim_optimizer_account_package_signature(
                item.proposal.compiled_candidate.targets
            )
            for race in race_results
            for item in race.trace_evaluations
            if item.tier_id == "screen_8"
        }

        self.assertIn(signature, screened_signatures)
        self.assertTrue(
            all(
                next(
                    item
                    for item in result.package_decisions
                    if item.target == target
                ).status
                in {"exact_screened", "refined", "validated"}
                for target in anchor
            )
        )

    def test_injected_exact_account_winner_survives_every_race_tier(
        self,
    ) -> None:
        source = self._run(self.environment)
        source_evaluations = (
            source.account_result.race_result.confirmed_evaluations[:2]
        )
        self.assertEqual(len(source_evaluations), 2)
        source_configs = {
            item.proposal.compiled_candidate.compiled_config_sha256
            for item in source_evaluations
        }

        result = run_gcsim_optimizer_all_database_sets(
            self.environment.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(),
            set_impact_discovery=_PositiveSetImpactDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
            required_account_anchors=tuple(
                item.proposal for item in source_evaluations
            ),
        )

        self.assertEqual(
            len(result.account_result.preliminary_race_results),
            2 + 2 * self.plan.account_plan.coordinate_refinement_rounds,
        )
        race_results = (
            *result.account_result.preliminary_race_results,
            result.account_result.race_result,
        )
        for race in race_results:
            for tier_id in (
                "screen_8",
                "refine_32",
                "validate_200",
                "rerace_1000",
            ):
                tier_configs = {
                    item.proposal.compiled_candidate.compiled_config_sha256
                    for item in race.trace_evaluations
                    if item.tier_id == tier_id
                }
                self.assertTrue(source_configs.issubset(tier_configs))
        rebound_configs = {
            item.proposal.compiled_candidate.compiled_config_sha256
            for item in result.account_result.race_result.trace_evaluations
            if item.tier_id == "rerace_1000"
            and "required_external_anchor"
            in item.proposal.diversity_labels
        }
        self.assertTrue(source_configs.issubset(rebound_configs))
        self.assertEqual(
            result.terminal.coverage.counters[
                "all_set_injected_account_anchor_count"
            ],
            2,
        )

    def test_soft_neutral_ranking_preserves_hp_support_main_layout(
        self,
    ) -> None:
        environment = _all_set_environment(self.plan)
        set_uid = environment.set_refs[0].set_uid
        artifacts = tuple(
            replace(
                item,
                main_property_type=3,
                main_property_name="HP%",
                main_property_value="46.6%",
                main_numeric_value=46.6,
            )
            if item.set_uid == set_uid and item.position in {3, 4, 5}
            else item
            for item in environment.database.artifacts
        )
        database = replace(environment.database, artifacts=artifacts)
        built = build_gcsim_optimizer_run_input(
            request=environment.request,
            config_shell=environment.shell,
            artifact_database=database,
            engine_context=environment.engine,
        )
        self.assertTrue(built.ready)
        run_input = built.run_input
        catalog = build_gcsim_optimizer_dense_artifact_catalog(run_input)
        wearer = environment.wearers[0]
        weights = tuple(
            1.0 if axis == "atk%" else 0.0
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        neutral = GcsimOptimizerAnytimeStatProfile(
            wearer=wearer,
            profile_id="neutral_atk_only",
            stat_weights=weights,
            main_scores=(
                ("sands", "atk%", 1.0),
                ("goblet", "atk%", 1.0),
                ("circlet", "cr", 1.0),
            ),
            evidence_sha256="d" * 64,
        )
        profiles = build_gcsim_optimizer_soft_main_coverage_profiles(
            (neutral,)
        )
        target = next(
            item
            for item in derive_gcsim_optimizer_source_package_anchor(
                run_input,
                set_refs=derive_gcsim_optimizer_all_database_set_refs(
                    run_input
                ),
            )
            if item.wearer == wearer
        )
        pool = generate_gcsim_optimizer_anytime_wearer_pool(
            run_input,
            catalog=catalog,
            wearer=wearer,
            targets=(target,),
            profiles=profiles,
            hard_main_pruning=False,
            plan=GcsimOptimizerAnytimeCandidatePlan(
                max_frontier_per_group=8,
                shadow_per_group=2,
                per_profile_slot_count=4,
                max_slot_pool=32,
                wearer_beam_width=64,
                max_builds_per_target=32,
                max_builds_per_wearer=32,
                joint_beam_width=32,
                max_joint_proposals=8,
                local_search_seed_count=2,
                max_seconds=10.0,
            ),
        )

        self.assertTrue(
            any(
                "profile:main_anchor_hp_pct" in item.feature_labels
                and "main_shape:hp%/hp%/hp%" in item.feature_labels
                for item in pool.candidates
            )
        )

    def test_marginal_coverage_bypasses_small_joint_proposal_cap(self) -> None:
        small_account_plan = replace(
            self.plan.account_plan,
            candidates=replace(
                self.plan.account_plan.candidates,
                max_joint_proposals=1,
            ),
            top_n=1,
        )
        plan = GcsimOptimizerAllSetPlan(
            account_plan=small_account_plan,
        )
        environment = _all_set_environment(plan)

        result = self._run(environment, plan=plan)

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertIsNotNone(result.account_result)
        coverage = result.account_result.joint_coverage
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage.marginal_required_target_count, 16)
        self.assertEqual(len(coverage.marginal_covered_targets), 16)
        self.assertEqual(coverage.marginal_uncovered_targets, ())
        self.assertGreater(coverage.compiled_proposal_count, 1)
        expected = {
            (
                target.wearer.team_slot,
                target.package.identity_sha256,
            )
            for _slot, targets in result.account_result.targets_by_wearer
            for target in targets
        }
        race_results = (
            *result.account_result.preliminary_race_results,
            result.account_result.race_result,
        )
        screened = {
            _coverage_key(label)
            for race in race_results
            for evaluation in race.trace_evaluations
            if evaluation.tier_id == "screen_8"
            for label in evaluation.proposal.diversity_labels
            if label.startswith("marginal_package_coverage:")
        }
        self.assertTrue(expected.issubset(screened))
        coverage_proposals = {
            _coverage_key(label): proposal
            for proposal in (
                evaluation.proposal
                for race in race_results
                for evaluation in race.trace_evaluations
                if evaluation.tier_id == "screen_8"
            )
            for label in proposal.diversity_labels
            if label.startswith("marginal_package_coverage:")
        }
        candidate_scopes = tuple(
            build_gcsim_optimizer_account_candidate_keys(
                proposal,
                engine_context=environment.engine,
            )[0]
            for proposal in coverage_proposals.values()
        )
        self.assertEqual(
            len(set(candidate_scopes)),
            len(candidate_scopes),
        )
        pools_by_slot = {
            pool.wearer.team_slot: pool
            for pool in result.account_result.wearer_pools
        }
        for key, proposal in coverage_proposals.items():
            fixed = next(
                candidate
                for candidate in proposal.wearer_candidates
                if (
                    candidate.target.wearer.team_slot,
                    candidate.target.package.identity_sha256,
                )
                == key
            )
            strongest = next(
                candidate
                for candidate in pools_by_slot[key[0]].candidates
                if (
                    candidate.target.package.identity_sha256 == key[1]
                )
            )
            self.assertEqual(
                fixed.candidate_sha256,
                strongest.candidate_sha256,
            )
        self.assertEqual(
            result.terminal.coverage.counters[
                "all_set_package_exact_screened_count"
            ],
            16,
        )
        self.assertEqual(
            result.terminal.coverage.counters[
                "joint_marginal_uncovered_target_count"
            ],
            0,
        )

    def test_include_2p2p_adds_every_canonical_pair_decision(self) -> None:
        environment = _all_set_environment(self.plan, include_2p2p=True)

        result = self._run(environment)

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertEqual(len(result.package_decisions), 40)
        pairs = tuple(
            item
            for item in result.package_decisions
            if isinstance(item.target.package, GcsimTwoPlusTwoTargetPackage)
        )
        self.assertEqual(len(pairs), 24)

    def test_cancel_before_run_returns_typed_cancelled_result(self) -> None:
        session = gcsim_api.GcsimOptimizerAllSetSession(
            self.environment.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(),
            set_impact_discovery=_PositiveSetImpactDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
        )
        session.cancel()

        result = session.run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.CANCELLED,
        )

    def _run(self, environment, *, plan=None):
        return run_gcsim_optimizer_all_database_sets(
            environment.run_input,
            engine_context=environment.engine,
            prepared_config_text=environment.source_config_text,
            plan=self.plan if plan is None else plan,
            response_discovery=_ResponseDiscovery(),
            set_impact_discovery=_PositiveSetImpactDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
        )


class _PositiveSetImpactDiscovery:
    def __call__(self, *, targets, plan, response, **_kwargs):
        zero = GcsimStatResponseEstimate(
            count=plan.iterations,
            mean=0.0,
            sample_sd=0.0,
            standard_error=0.0,
        )
        rows = tuple(
            GcsimOptimizerSetImpactRow(
                target=target,
                classification=(
                    GcsimOptimizerSetImpactClassification
                    .PERSONAL_AND_TEAM_POSITIVE
                ),
                team_delta=replace(zero, mean=100.0),
                personal_delta=replace(zero, mean=50.0),
                character_deltas=(zero, zero, zero, zero),
                surrogate_dps=100.0,
                evidence_sha256="c" * 64,
            )
            for target in targets
        )
        return GcsimOptimizerSetImpactResult(
            rows=rows,
            plan=plan,
            response_evidence_sha256=response.evidence_sha256,
            elapsed_seconds=0.0,
            batch_count=1,
        )


class _SourceNegativeSetImpactDiscovery(_PositiveSetImpactDiscovery):
    def __call__(self, **kwargs):
        result = super().__call__(**kwargs)
        rows = tuple(
            replace(
                item,
                classification=GcsimOptimizerSetImpactClassification.NEGLIGIBLE,
                surrogate_dps=0.0,
            )
            if (
                item.target.package.set_ref.gcsim_set_key
                == "oracleset" + item.target.wearer.gcsim_character_key
            )
            else item
            for item in result.rows
        )
        return replace(result, rows=rows)


def _coverage_key(label: str) -> tuple[int, str]:
    _prefix, slot, package_sha256 = label.split(":", 2)
    return int(slot), package_sha256


def _all_set_environment(plan, *, include_2p2p=False):
    environment = build_oracle_account_environment()
    capabilities = tuple(
        replace(item, max_rarity=5)
        for item in environment.engine.catalog.sets
    )
    catalog = GcsimArtifactSetCatalog(
        source_root=environment.engine.catalog.source_root,
        source_fingerprint=environment.engine.catalog.source_fingerprint,
        sets=capabilities,
        warnings=environment.engine.catalog.warnings,
    )
    engine = replace(environment.engine, catalog=catalog)
    artifacts = tuple(
        replace(
            item,
            rarity=5,
            level=20,
            default_eligible=item.calculation_valid,
        )
        if item.rarity == 4
        else item
        for item in environment.database.artifacts
    )
    database = replace(environment.database, artifacts=artifacts)
    request = replace(
        environment.request,
        account_scope=GcsimOptimizerAccountScope.ALL_DATABASE_SETS,
        selected_set_pools=(),
        include_2p2p=include_2p2p,
        four_star_overrides=tuple(
            replace(item, allowed_set_uids=())
            for item in environment.request.four_star_overrides
        ),
        work_plan=GcsimOptimizerWorkPlan(
            operation=environment.request.operation,
            plan_id=GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
            plan_version=GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
            parameters=plan.to_dict(),
        ),
    )
    built = build_gcsim_optimizer_run_input(
        request=request,
        config_shell=environment.shell,
        artifact_database=database,
        engine_context=engine,
    )
    assert built.ready and built.run_input is not None
    return replace(
        environment,
        engine=engine,
        request=request,
        database=database,
        run_input=built.run_input,
    )


if __name__ == "__main__":
    unittest.main()
