from __future__ import annotations

from dataclasses import replace
import hashlib
from itertools import combinations
from pathlib import Path
import tempfile
from threading import Event, Thread
from types import SimpleNamespace
import unittest

from run_workspace.gcsim.optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponseResult,
    _profiles_with_surface,
    discover_gcsim_optimizer_theoretical_anytime_response,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimStatResponseObjective,
    GcsimStatResponseTarget,
    build_gcsim_stat_response_probe_request,
    parse_gcsim_stat_response_result,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_stat_response import (
    _complete_result_payload,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_anytime_selected_service import (
    _test_response_profiles,
)
from run_workspace.gcsim.farming_team_search import (
    TEAM_SIM_CANCELLED,
    FullTeamPhysicalState,
    FullTeamSimulationMetrics,
)
from run_workspace.gcsim.farming_search import FourPieceSetState
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerOperation,
    GcsimOptimizerProgressLeaderQuality,
    GcsimOptimizerProgressLeaderScope,
    GcsimOptimizerProgressStage,
    GcsimOptimizerSetReference,
    GcsimOptimizerTargetPackageKind,
    GcsimOptimizerTerminalStatus,
    GcsimTwoPlusTwoTargetPackage,
    GcsimOptimizerWearerIdentity,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_service import (
    GcsimOptimizerTheoreticalAnytimeError,
    GcsimOptimizerTheoreticalAnytimePlan,
    GcsimOptimizerTheoreticalAnytimeSession,
    _coverage,
    _prospective_two_plus_two_targets,
    _targets_for_state,
    _two_piece_component_targets,
    build_gcsim_optimizer_theoretical_anytime_operation_request,
    build_gcsim_optimizer_theoretical_shared_kernel_plan,
)
from run_workspace.gcsim.optimizer_theoretical_packages import (
    gcsim_theoretical_pair_package_key,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_race import (
    GcsimOptimizerTheoreticalAnytimeRaceSession,
    GcsimOptimizerTheoreticalAnytimeRaceStatus,
)
from run_workspace.gcsim.optimizer_set_impact import (
    GcsimOptimizerSetImpactClassification,
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSetImpactRow,
    GcsimOptimizerSingleTwoPieceImpactTarget,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimStatResponseEstimate,
)
from run_workspace.gcsim.optimizer_two_piece_signatures import (
    build_gcsim_optimizer_theoretical_pair_domain,
)

from tests.run_workspace.gcsim.test_gcsim_farming_evaluator import (
    _passed_result,
)
from tests.run_workspace.gcsim.test_gcsim_farming_finalist_optimizer import (
    EvidenceSessionFactory,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_theoretical_anytime_race import (
    _ScriptedSimulatorFactory,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_theoretical_anytime_candidates import (
    _context as _candidate_context,
    _profiles_with_em_focus,
    _set_impact as _candidate_set_impact,
    _wide_pair_packages,
    _wearers as _candidate_wearers,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_candidates import (
    build_gcsim_optimizer_theoretical_anytime_candidate_domain,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_theoretical_anytime_validation import (
    _OptimizerFactory,
    _config,
    _fixture,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_two_piece_signatures import (
    _context as _two_piece_context,
)


_WEARER_KEYS = ("furina", "bennett", "xiangling", "xingqiu")


class GcsimOptimizerTheoreticalAnytimeServiceTests(
    unittest.TestCase
):
    def test_prospective_pair_scan_bounds_a_full_pair_domain_before_candidates(
        self,
    ) -> None:
        set_keys = tuple(f"set{index:02d}" for index in range(20))
        context = _candidate_context(modeled_keys=set_keys)
        wearers = _candidate_wearers()
        refs = {
            set_key: GcsimOptimizerSetReference(
                set_uid=set_key,
                gcsim_set_key=set_key,
                engine_binding_sha256=context.binding_sha256,
                catalog_fingerprint=context.catalog.source_fingerprint,
            )
            for set_key in set_keys
        }
        concrete_packages = tuple(
            GcsimTwoPlusTwoTargetPackage(refs[set_a], refs[set_b])
            for set_a, set_b in combinations(set_keys, 2)
        )
        groups = tuple(
            SimpleNamespace(
                pair_signature_sha256=hashlib.sha256(
                    (
                        package.set_a.gcsim_set_key
                        + "|"
                        + package.set_b.gcsim_set_key
                    ).encode("utf-8")
                ).hexdigest(),
                representative=package,
                concrete_aliases=(package,),
                modifier_key_relation="distinct_static_keys",
            )
            for package in concrete_packages
        )
        pair_domain = SimpleNamespace(
            descriptors=tuple(
                SimpleNamespace(set_key=set_key) for set_key in set_keys
            ),
            groups=groups,
            engine_binding_sha256=context.binding_sha256,
            catalog_fingerprint=context.catalog.source_fingerprint,
        )
        estimate = GcsimStatResponseEstimate(
            count=8,
            mean=1.0,
            sample_sd=0.0,
            standard_error=0.0,
        )
        component_targets = _two_piece_component_targets(
            wearers,
            pair_domain,
        )
        component_impact = GcsimOptimizerSetImpactResult(
            rows=tuple(
                GcsimOptimizerSetImpactRow(
                    target=target,
                    classification=(
                        GcsimOptimizerSetImpactClassification.TEAM_POSITIVE
                    ),
                    team_delta=estimate,
                    personal_delta=estimate,
                    character_deltas=(estimate,) * 4,
                    surrogate_dps=(
                        1000.0
                        - set_keys.index(
                            target.set_ref.gcsim_set_key
                        )
                    ),
                    evidence_sha256=hashlib.sha256(
                        repr(target.to_dict()).encode("utf-8")
                    ).hexdigest(),
                )
                for target in component_targets
            ),
            plan=GcsimOptimizerSetImpactPlan(),
            response_evidence_sha256="e" * 64,
            elapsed_seconds=0.0,
            batch_count=1,
        )

        pair_targets, selected_packages = (
            _prospective_two_plus_two_targets(
                wearers,
                pair_domain,
                component_impact,
                max_core_components_per_wearer=12,
                max_targets_per_wearer=96,
            )
        )
        set_impact = _candidate_set_impact(
            context,
            wearers,
            packages=selected_packages,
        )
        candidate_domain = (
            build_gcsim_optimizer_theoretical_anytime_candidate_domain(
                engine_context=context,
                wearers=wearers,
                response_profiles=_profiles_with_em_focus(wearers),
                set_impact=set_impact,
                two_plus_two_packages=selected_packages,
            )
        )

        self.assertEqual(len(concrete_packages), 190)
        self.assertEqual(len(pair_targets), 4 * 96)
        self.assertEqual(len(selected_packages), 96)
        self.assertEqual(len(candidate_domain.proposals), 512)
        self.assertEqual(
            [
                len(pool.retained_package_keys)
                for pool in candidate_domain.wearer_pools
            ],
            [96, 96, 96, 96],
        )
        self.assertEqual(
            [
                len(pool.anchor_package_keys)
                for pool in candidate_domain.wearer_pools
            ],
            [30, 30, 30, 30],
        )

    def test_wide_pair_shortlist_is_explicit_in_typed_coverage(self) -> None:
        set_keys = tuple(f"set{index:02d}" for index in range(13))
        context = _candidate_context(modeled_keys=set_keys)
        wearers = _candidate_wearers()
        packages = _wide_pair_packages(context, set_keys)
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=context,
            wearers=wearers,
            response_profiles=_profiles_with_em_focus(wearers),
            set_impact=_candidate_set_impact(
                context,
                wearers,
                packages=packages,
            ),
            two_plus_two_packages=packages,
        )

        coverage = _coverage(
            response=None,
            component_set_impact=None,
            set_impact=None,
            domain=domain,
            race=None,
            validation=None,
        ).counters
        self.assertEqual(coverage["retained_package_count"], 312)
        self.assertEqual(coverage["screened_anchor_count"], 120)
        self.assertEqual(coverage["retained_unscreened_count"], 192)
        for slot in range(1, 5):
            self.assertEqual(
                coverage[f"wearer_{slot}_retained_package_count"],
                78,
            )
            self.assertEqual(
                coverage[f"wearer_{slot}_screened_anchor_count"],
                30,
            )
            self.assertEqual(
                coverage[f"wearer_{slot}_retained_unscreened_count"],
                48,
            )

    def test_plan_requires_balanced_and_crit_headroom_set_panels(self) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeError,
            "both balanced and crit-headroom panels",
        ):
            GcsimOptimizerTheoreticalAnytimePlan(
                set_impact=GcsimOptimizerSetImpactPlan(
                    enable_crit_headroom_panel=False,
                )
            )

    def test_four_piece_end_to_end_is_inventory_independent_and_saveable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _fixture(root / "engine", set_count=3)
            harness = _run_service(
                root,
                operation=(
                    GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                ),
                context=source.context,
                config=source.config,
                pair_domain=None,
            )

        result = harness.result
        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertIsNone(result.pair_domain)
        self.assertIsNotNone(result.response_result)
        self.assertIsNotNone(result.candidate_domain)
        self.assertIsNotNone(result.race_result)
        self.assertIsNotNone(result.validation_result)
        self.assertEqual(
            result.candidate_domain.package_kind,
            GcsimOptimizerTargetPackageKind.FOUR_PIECE,
        )
        self.assertEqual(result.best_found.percent_of_best, 100.0)
        self.assertEqual(result.best_found.rank, 1)
        self.assertIsNotNone(result.best_found.theoretical_allocation)
        self.assertEqual(
            tuple(
                item.wearer
                for item in result.best_found.theoretical_allocation
                .wearer_allocations
            ),
            result.terminal.request.source_simulation.wearers,
        )
        self.assertTrue(
            all(
                set(item.main_stats_by_slot)
                == {"sands", "goblet", "circlet"}
                and item.total_liquid_rolls == 20
                for item in result.best_found.theoretical_allocation
                .wearer_allocations
            )
        )
        self.assertTrue(
            all(
                entry.estimate.iterations >= 200
                for entry in result.terminal.top_n.entries
            )
        )
        self.assertIsNone(result.terminal.request.account_scope)
        self.assertEqual(
            result.terminal.request.selected_set_pools,
            (),
        )
        self.assertEqual(
            result.terminal.request.artifact_database_input_sha256,
            "",
        )
        self.assertFalse(
            any(
                key in kwargs
                for kwargs in harness.response.calls
                for key in (
                    "artifact_database",
                    "artifact_database_input",
                    "run_input",
                )
            )
        )
        self._assert_fidelity_progress(result)

    def test_two_plus_two_end_to_end_preserves_explicit_pair_domain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = _two_piece_context(root / "engine")
            pair_domain = build_gcsim_optimizer_theoretical_pair_domain(
                context
            )
            harness = _run_service(
                root,
                operation=(
                    GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
                ),
                context=context,
                config=_config("alpha"),
                pair_domain=pair_domain,
            )

        result = harness.result
        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertIs(result.pair_domain, pair_domain)
        self.assertEqual(
            result.candidate_domain.package_kind,
            GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO,
        )
        self.assertEqual(result.best_found.percent_of_best, 100.0)
        self.assertTrue(
            all(
                item.package_key.startswith("pair_")
                for item in result.best_found.theoretical_allocation
                .wearer_allocations
            )
        )
        self.assertTrue(
            all(
                target.package.kind
                is GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO
                for entry in result.terminal.top_n.entries
                for target in entry.target_packages
            )
        )
        self.assertIsNone(result.terminal.request.account_scope)
        self.assertEqual(
            result.terminal.request.artifact_database_input_sha256,
            "",
        )
        self.assertIsNotNone(result.component_set_impact_result)
        self.assertEqual(
            len(result.component_set_impact_result.rows),
            4 * len(pair_domain.descriptors),
        )
        self.assertTrue(
            all(
                isinstance(
                    row.target,
                    GcsimOptimizerSingleTwoPieceImpactTarget,
                )
                for row in result.component_set_impact_result.rows
            )
        )
        self.assertIsNotNone(result.set_impact_result)
        counters = result.terminal.coverage.counters
        self.assertEqual(
            counters["retained_package_count"],
            counters["screened_anchor_count"]
            + counters["retained_unscreened_count"],
        )
        for slot in range(1, 5):
            self.assertEqual(
                counters[f"wearer_{slot}_retained_package_count"],
                counters[f"wearer_{slot}_screened_anchor_count"]
                + counters[
                    f"wearer_{slot}_retained_unscreened_count"
                ],
            )
        self.assertEqual(
            len(result.set_impact_result.rows),
            4 * len(pair_domain.groups),
        )
        self._assert_fidelity_progress(result)

    def test_two_piece_screen_selects_the_best_concrete_effect_alias(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _two_piece_context(Path(tmp) / "engine")
            pair_domain = build_gcsim_optimizer_theoretical_pair_domain(
                context
            )
            component_targets = _two_piece_component_targets(
                _wearers(),
                pair_domain,
            )
            estimate = GcsimStatResponseEstimate(
                count=8,
                mean=1.0,
                sample_sd=0.0,
                standard_error=0.0,
            )
            component_impact = GcsimOptimizerSetImpactResult(
                rows=tuple(
                    GcsimOptimizerSetImpactRow(
                        target=target,
                        classification=(
                            GcsimOptimizerSetImpactClassification.TEAM_POSITIVE
                        ),
                        team_delta=estimate,
                        personal_delta=estimate,
                        character_deltas=(estimate,) * 4,
                        surrogate_dps=(
                            100.0
                            if target.set_ref.gcsim_set_key == "beta"
                            else 10.0
                        ),
                        evidence_sha256=hashlib.sha256(
                            repr(target.to_dict()).encode("utf-8")
                        ).hexdigest(),
                    )
                    for target in component_targets
                ),
                plan=GcsimOptimizerSetImpactPlan(),
                response_evidence_sha256="e" * 64,
                elapsed_seconds=0.0,
                batch_count=1,
            )

            targets, packages = _prospective_two_plus_two_targets(
                _wearers(),
                pair_domain,
                component_impact,
                max_core_components_per_wearer=4,
                max_targets_per_wearer=96,
            )
            selected_alias = next(
                target.package
                for target in targets
                if target.wearer.team_slot == 1
                and {
                    target.package.set_a.gcsim_set_key,
                    target.package.set_b.gcsim_set_key,
                }
                == {"beta", "gamma"}
            )
            selected_key = gcsim_theoretical_pair_package_key(
                selected_alias
            )
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
                    ),
                    engine_context=context,
                    prepared_config_text=_config("alpha"),
                    wearers=_wearers(),
                    pair_domain=pair_domain,
                )
            )
            state = FullTeamPhysicalState(
                tuple(
                    FourPieceSetState(
                        wearer_id=wearer.gcsim_character_key,
                        set_key=selected_key,
                        main_stat_layout_id="main/test",
                    )
                    for wearer in _wearers()
                )
            )
            packaged = _targets_for_state(
                request,
                state,
                engine_context=context,
                pair_packages=packages,
            )

        first_wearer_pairs = {
            frozenset(
                (
                    target.package.set_a.gcsim_set_key,
                    target.package.set_b.gcsim_set_key,
                )
            )
            for target in targets
            if target.wearer.team_slot == 1
        }
        self.assertIn(frozenset(("beta", "gamma")), first_wearer_pairs)
        self.assertNotIn(frozenset(("alpha", "gamma")), first_wearer_pairs)
        self.assertTrue(
            all(target.package == selected_alias for target in packaged)
        )
        with self.assertRaisesRegex(
            GcsimOptimizerTheoreticalAnytimeError,
            "outside the measured candidate mapping",
        ):
            _targets_for_state(
                request,
                state,
                engine_context=context,
                pair_packages={},
            )

    def test_work_plan_mismatch_fails_before_any_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = GcsimOptimizerTheoreticalAnytimePlan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            request = replace(
                request,
                work_plan=replace(
                    request.work_plan,
                    plan_id="wrong_anytime_plan",
                ),
            )
            unexpected = _UnexpectedCall()

            result = GcsimOptimizerTheoreticalAnytimeSession(
                request,
                engine_context=source.context,
                prepared_config_text=source.config,
                plan=plan,
                response_discovery=unexpected,
                candidate_domain_builder=unexpected,
                race_session_factory=unexpected,
                validation_session_factory=unexpected,
                enable_cache=False,
            ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.NOT_READY,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "theoretical_anytime_work_plan_mismatch",
        )
        self.assertEqual(unexpected.calls, 0)
        self.assertIsNone(result.response_result)
        self.assertIsNone(result.candidate_domain)
        self.assertIsNone(result.race_result)
        self.assertIsNone(result.validation_result)

    def test_source_request_mismatch_fails_before_any_simulation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = GcsimOptimizerTheoreticalAnytimePlan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            unexpected = _UnexpectedCall()

            result = GcsimOptimizerTheoreticalAnytimeSession(
                request,
                engine_context=source.context,
                prepared_config_text=source.config + "# drift\n",
                plan=plan,
                response_discovery=unexpected,
                candidate_domain_builder=unexpected,
                race_session_factory=unexpected,
                validation_session_factory=unexpected,
                enable_cache=False,
            ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.NOT_READY,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "theoretical_anytime_source_config_mismatch",
        )
        self.assertEqual(unexpected.calls, 0)
        self.assertIsNone(result.response_result)
        self.assertIsNone(result.candidate_domain)
        self.assertIsNone(result.race_result)
        self.assertIsNone(result.validation_result)

    def test_cancel_before_start_stops_before_response_or_race(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = GcsimOptimizerTheoreticalAnytimePlan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            unexpected = _UnexpectedCall()
            session = GcsimOptimizerTheoreticalAnytimeSession(
                request,
                engine_context=source.context,
                prepared_config_text=source.config,
                plan=plan,
                response_discovery=unexpected,
                candidate_domain_builder=unexpected,
                race_session_factory=unexpected,
                validation_session_factory=unexpected,
                enable_cache=False,
            )

            session.cancel()
            result = session.run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.CANCELLED,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "theoretical_anytime_cancelled",
        )
        self.assertEqual(unexpected.calls, 0)
        self.assertEqual(
            [event.stage for event in result.progress_events],
            [
                GcsimOptimizerProgressStage.PREFLIGHT,
                GcsimOptimizerProgressStage.PREFLIGHT,
            ],
        )
        self.assertTrue(
            all(event.current_best is None for event in result.progress_events)
        )

    def test_response_discovery_exception_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = GcsimOptimizerTheoreticalAnytimePlan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            unexpected = _UnexpectedCall()

            result = GcsimOptimizerTheoreticalAnytimeSession(
                request,
                engine_context=source.context,
                prepared_config_text=source.config,
                plan=plan,
                response_discovery=_ExplodingResponseDiscovery(),
                candidate_domain_builder=unexpected,
                race_session_factory=unexpected,
                validation_session_factory=unexpected,
                enable_cache=False,
            ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.FAILED,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "theoretical_anytime_orchestration_failed",
        )
        self.assertIn("synthetic response failure", result.terminal.error)
        self.assertIsNone(result.terminal.best_found)
        self.assertFalse(result.terminal.top_n.entries)
        self.assertIsNone(result.response_result)
        self.assertEqual(unexpected.calls, 0)

    def test_local_race_deadline_with_finalists_still_validates_at_200(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _fixture(root / "engine", set_count=3)
            harness = _run_service(
                root,
                operation=(
                    GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                ),
                context=source.context,
                config=source.config,
                pair_domain=None,
                race_session_factory=_DeadlineRaceSessionFactory(),
            )

        result = harness.result
        self.assertEqual(
            result.race_result.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE,
        )
        self.assertTrue(result.race_result.physical_finalists)
        self.assertIsNotNone(result.validation_result)
        self.assertTrue(result.validation_result.evaluations)
        self.assertTrue(
            all(
                item.iterations >= 200
                for item in result.validation_result.evaluations
            )
        )
        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertTrue(result.terminal.top_n.entries)

    def test_cancel_during_paired_response_returns_cancelled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = GcsimOptimizerTheoreticalAnytimePlan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            response_discovery = _BlockingResponseDiscovery()
            unexpected = _UnexpectedCall()
            session = GcsimOptimizerTheoreticalAnytimeSession(
                request,
                engine_context=source.context,
                prepared_config_text=source.config,
                plan=plan,
                response_discovery=response_discovery,
                candidate_domain_builder=unexpected,
                race_session_factory=unexpected,
                validation_session_factory=unexpected,
                enable_cache=False,
            )
            outcomes = []
            failures = []

            def run_session() -> None:
                try:
                    outcomes.append(session.run())
                except BaseException as exc:  # pragma: no cover - assertion aid.
                    failures.append(exc)

            thread = Thread(target=run_session)
            thread.start()
            self.assertTrue(response_discovery.started.wait(2.0))

            session.cancel()
            thread.join(2.0)
            terminated_after_cancel = not thread.is_alive()
            if thread.is_alive():  # Never leak a failed blocking fixture.
                response_discovery.force_release()
                thread.join(2.0)

        self.assertTrue(terminated_after_cancel)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(unexpected.calls, 0)
        self.assertEqual(
            outcomes[0].terminal.status,
            GcsimOptimizerTerminalStatus.CANCELLED,
        )
        self.assertEqual(
            outcomes[0].terminal.stop_reason,
            "theoretical_anytime_cancelled",
        )

    def test_production_response_progress_reports_both_paired_batches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = _fixture(Path(tmp) / "engine", set_count=2)
            plan = build_gcsim_optimizer_theoretical_shared_kernel_plan()
            request = (
                build_gcsim_optimizer_theoretical_anytime_operation_request(
                    operation=(
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                    ),
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    wearers=_wearers(),
                    plan=plan,
                )
            )
            progress = []
            target = GcsimStatResponseTarget(
                objective=GcsimStatResponseObjective.DPS,
                target_sha256=hashlib.sha256(
                    source.config.encode("utf-8")
                ).hexdigest(),
            )

            def stat_runner(**kwargs):
                payload = _complete_result_payload(kwargs["request"], {})
                payload["character_keys"] = [
                    item.gcsim_character_key for item in _wearers()
                ]
                return parse_gcsim_stat_response_result(payload)

            result = (
                discover_gcsim_optimizer_theoretical_anytime_response(
                    request,
                    engine_context=source.context,
                    prepared_config_text=source.config,
                    package_keys=(source.set_keys[0],) * 4,
                    plan=plan.response,
                    progress_callback=lambda completed, planned, hits: (
                        progress.append((completed, planned, hits))
                    ),
                    stat_response_target=target,
                    stat_response_runner=stat_runner,
                )
            )

        planned = result.planned_probe_count
        self.assertEqual(planned, 480)
        self.assertEqual(
            progress,
            [
                (0, planned, 0),
                (108, planned, 0),
                (318, planned, 0),
                (planned, planned, 0),
            ],
        )
        self.assertIsNotNone(result.surface_result)
        assert result.surface_result is not None
        self.assertEqual(len(result.surface_result.curves), 40)
        self.assertTrue(
            any(
                item.crosses_wearers
                for item in result.surface_result.interactions
            )
        )
        self.assertTrue(
            {"crit_pair", "scaling_crit", "scaling_damage_bonus"}.issubset(
                {item.kind for item in result.surface_result.interactions}
            )
        )
        self.assertTrue(
            all(
                len(item.character_residual_means) == 4
                for item in result.surface_result.interactions
            )
        )

    def test_uncertain_surface_slope_isolated_to_exploration_lane(self) -> None:
        wearers = _wearers()
        balanced_profiles = _test_response_profiles(
            wearers,
            evidence_sha256="a" * 64,
        )
        profiles = tuple(
            row
            for balanced in balanced_profiles
            for row in (
                balanced,
                replace(
                    balanced,
                    profile_id="crit_chance",
                    stat_weights=tuple(
                        1.0 if axis == "cr" else 0.0
                        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                    ),
                    stat_classifications=tuple(
                        (
                            axis,
                            "secondary" if axis == "cr" else "negligible",
                        )
                        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                    ),
                ),
            )
        )
        curve_index = {
            (wearer.team_slot, axis): SimpleNamespace(
                local_slope=lambda: (1.0, 1.0)
            )
            for wearer in wearers
            for axis in GCSIM_STAT_RESPONSE_ROLL_VALUES
        }

        result = _profiles_with_surface(
            wearers,
            profiles,
            surface=SimpleNamespace(curve_index=curve_index),
            evidence_sha256="b" * 64,
            confidence_sigma=2.0,
        )

        for wearer in wearers:
            balanced = next(
                item
                for item in result
                if item.wearer == wearer and item.profile_id == "balanced"
            )
            exploration = next(
                item
                for item in result
                if item.wearer == wearer
                and item.profile_id == "uncertain_exploration"
            )
            crit_chance = next(
                item
                for item in result
                if item.wearer == wearer and item.profile_id == "crit_chance"
            )
            balanced_weights = dict(
                zip(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                    balanced.stat_weights,
                    strict=True,
                )
            )
            exploration_weights = dict(
                zip(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                    exploration.stat_weights,
                    strict=True,
                )
            )
            balanced_classes = dict(balanced.stat_classifications)
            exploration_classes = dict(exploration.stat_classifications)
            for axis in GCSIM_STAT_RESPONSE_ROLL_VALUES:
                self.assertEqual(balanced_weights[axis], 0.0)
                self.assertEqual(balanced_classes[axis], "uncertain")
                self.assertGreater(exploration_weights[axis], 0.0)
                self.assertEqual(exploration_classes[axis], "secondary")
            crit_weights = dict(
                zip(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                    crit_chance.stat_weights,
                    strict=True,
                )
            )
            crit_classes = dict(crit_chance.stat_classifications)
            self.assertGreater(crit_weights["cr"], 0.0)
            self.assertEqual(crit_classes["cr"], "secondary")
            self.assertEqual(crit_weights["cd"], 0.0)
            self.assertEqual(crit_classes["cd"], "uncertain")

    def _assert_fidelity_progress(self, result) -> None:
        quick = tuple(
            event.current_best
            for event in result.progress_events
            if event.stage is GcsimOptimizerProgressStage.SCREENING
            and event.current_best is not None
        )
        balanced = tuple(
            event.current_best
            for event in result.progress_events
            if event.stage is GcsimOptimizerProgressStage.REFINEMENT
            and event.current_best is not None
        )
        self.assertTrue(quick)
        self.assertTrue(balanced)
        self.assertEqual(
            {leader.estimate.iterations for leader in quick},
            {8},
        )
        self.assertEqual(
            {leader.estimate.iterations for leader in balanced},
            {32},
        )
        self.assertTrue(
            all(
                leader.scope is GcsimOptimizerProgressLeaderScope.STAGE
                and leader.quality
                is GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                for leader in (*quick, *balanced)
            )
        )
        for stage, iterations in (
            (GcsimOptimizerProgressStage.SCREENING, 8),
            (GcsimOptimizerProgressStage.REFINEMENT, 32),
            (GcsimOptimizerProgressStage.FINAL_VALIDATION, 200),
            (GcsimOptimizerProgressStage.RERACE, 1000),
        ):
            stage_events = tuple(
                event
                for event in result.progress_events
                if event.stage is stage
            )
            self.assertTrue(stage_events)
            self.assertEqual(
                {event.current_iterations for event in stage_events},
                {iterations},
            )
        saveable_stages = {
            GcsimOptimizerProgressStage.FINAL_VALIDATION,
            GcsimOptimizerProgressStage.RERACE,
            GcsimOptimizerProgressStage.COMPLETED,
        }
        self.assertTrue(
            any(
                event.current_best is not None
                and event.stage
                is GcsimOptimizerProgressStage.FINAL_VALIDATION
                for event in result.progress_events
            )
        )
        self.assertTrue(
            all(
                event.current_best is None
                or event.current_best.estimate.iterations >= 200
                for event in result.progress_events
                if event.stage in saveable_stages
            )
        )
        completed = tuple(
            event
            for event in result.progress_events
            if event.stage is GcsimOptimizerProgressStage.COMPLETED
        )
        self.assertEqual(len(completed), 1)
        self.assertIsNotNone(completed[0].current_best)
        assert completed[0].current_best is not None
        self.assertIs(
            completed[0].current_best.scope,
            GcsimOptimizerProgressLeaderScope.RUN,
        )
        self.assertIs(
            completed[0].current_best.quality,
            GcsimOptimizerProgressLeaderQuality.FINAL,
        )


class _Harness:
    def __init__(
        self,
        *,
        result,
        response,
        race,
        optimizer,
        evaluation,
    ) -> None:
        self.result = result
        self.response = response
        self.race = race
        self.optimizer = optimizer
        self.evaluation = evaluation


class _ResponseDiscovery:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, request, **kwargs):
        self.calls.append(kwargs)
        progress = kwargs.get("progress_callback")
        if progress is not None:
            progress(0, 1, 0)
            progress(1, 1, 0)
        evidence = hashlib.sha256(
            (
                "service-response:"
                f"{request.request_sha256}:"
                f"{request.operation.value}"
            ).encode("utf-8")
        ).hexdigest()
        return GcsimOptimizerAnytimeResponseResult(
            profiles=(
                _test_response_profiles(
                    request.source_simulation.wearers,
                    evidence_sha256=evidence,
                )
            ),
            synthetic_baseline_changes=(
                build_gcsim_stat_response_probe_request(
                    context_sha256="c" * 64,
                    objective=GcsimStatResponseObjective.DPS,
                ).baseline_changes
            ),
            synthetic_master_seed=123,
            planned_probe_count=1,
            successful_probe_count=1,
            failed_probe_count=0,
            cache_hit_count=0,
            evidence_sha256=evidence,
            elapsed_seconds=0.0,
        )


class _SetImpactDiscovery:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, *, targets, response, plan, **_kwargs):
        self.calls.append(tuple(targets))
        estimate = GcsimStatResponseEstimate(
            count=8,
            mean=100.0,
            sample_sd=0.0,
            standard_error=0.0,
        )
        rows = tuple(
            GcsimOptimizerSetImpactRow(
                target=target,
                classification=(
                    GcsimOptimizerSetImpactClassification.TEAM_POSITIVE
                ),
                team_delta=estimate,
                personal_delta=estimate,
                character_deltas=(estimate,) * 4,
                surrogate_dps=100.0,
                evidence_sha256=hashlib.sha256(
                    repr(target.to_dict()).encode("utf-8")
                ).hexdigest(),
            )
            for target in targets
        )
        return GcsimOptimizerSetImpactResult(
            rows=rows,
            plan=(
                plan
                if isinstance(plan, GcsimOptimizerSetImpactPlan)
                else GcsimOptimizerSetImpactPlan()
            ),
            response_evidence_sha256=response.evidence_sha256,
            elapsed_seconds=0.0,
            batch_count=1,
        )


class _ExplodingResponseDiscovery:
    def __call__(self, *_args, **_kwargs):
        raise RuntimeError("synthetic response failure")


class _OrdinaryEvaluationFactory:
    def __init__(self) -> None:
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return _OrdinaryEvaluationSession(
            request,
            dps=1_100.0 - len(self.requests),
        )


class _OrdinaryEvaluationSession:
    def __init__(self, request, *, dps: float) -> None:
        self.request = request
        self.dps = dps
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        if self.cancelled:
            raise AssertionError("ordinary evaluation unexpectedly cancelled")
        return _passed_result(self.request, self.dps, sd=20.0)


class _BlockingResponseDiscovery:
    def __init__(self) -> None:
        self.started = Event()
        self.released = Event()

    def __call__(self, _request, **kwargs):
        is_cancelled = kwargs["is_cancelled"]
        self.started.set()
        while not is_cancelled():
            if self.released.wait(0.01):
                break
        if is_cancelled():
            raise RuntimeError("cancelled response fixture")
        raise AssertionError("blocking response fixture was force-released")

    def force_release(self) -> None:
        self.released.set()


class _DeadlineRaceSessionFactory:
    def __call__(self, prepared_config_text, **kwargs):
        kwargs["simulator_factory"] = _ScriptedSimulatorFactory()
        return _DeadlineRaceSession(
            GcsimOptimizerTheoreticalAnytimeRaceSession(
                prepared_config_text,
                **kwargs,
            )
        )


class _DeadlineRaceSession:
    def __init__(self, inner) -> None:
        self.inner = inner

    def cancel(self) -> None:
        self.inner.cancel()

    def run(self):
        completed = self.inner.run()
        return replace(
            completed,
            status=GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE,
            evidence_sha256=hashlib.sha256(
                (
                    completed.evidence_sha256
                    + ":synthetic-local-deadline"
                ).encode("utf-8")
            ).hexdigest(),
        )


class _UnexpectedCall:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("simulation path must not be entered")


def _run_service(
    root: Path,
    *,
    operation: GcsimOptimizerOperation,
    context,
    config: str,
    pair_domain,
    race_simulator_factory=None,
    race_session_factory=None,
) -> _Harness:
    plan = GcsimOptimizerTheoreticalAnytimePlan()
    request = build_gcsim_optimizer_theoretical_anytime_operation_request(
        operation=operation,
        engine_context=context,
        prepared_config_text=config,
        wearers=_wearers(),
        plan=plan,
        pair_domain=pair_domain,
    )
    response = _ResponseDiscovery()
    set_impact = _SetImpactDiscovery()
    race = race_simulator_factory or _ScriptedSimulatorFactory()
    runner = EvidenceSessionFactory(root / "optimizer-runs")
    optimizer = _OptimizerFactory(runner)
    evaluation = _OrdinaryEvaluationFactory()
    result = GcsimOptimizerTheoreticalAnytimeSession(
        request,
        engine_context=context,
        prepared_config_text=config,
        plan=plan,
        pair_domain=pair_domain,
        enable_cache=False,
        evaluation_session_factory=evaluation,
        race_simulator_factory=race,
        race_session_factory=race_session_factory,
        finalist_session_factory=optimizer,
        response_discovery=response,
        set_impact_discovery=set_impact,
    ).run()
    return _Harness(
        result=result,
        response=response,
        race=race,
        optimizer=optimizer,
        evaluation=evaluation,
    )


def _wearers() -> tuple[GcsimOptimizerWearerIdentity, ...]:
    return tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=None,
            gcsim_character_key=key,
        )
        for index, key in enumerate(_WEARER_KEYS, start=1)
    )


if __name__ == "__main__":
    unittest.main()
