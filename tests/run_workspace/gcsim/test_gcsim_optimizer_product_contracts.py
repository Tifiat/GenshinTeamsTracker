from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.farming_auto_advisor import (
    GcsimAutomaticAdvisorSession,
)
from run_workspace.gcsim.farming_finalist_optimizer import (
    GcsimFinalistOptimizerSession,
)
from run_workspace.gcsim.farming_optimized_advisor import (
    GcsimOptimizedAdvisorSession,
    GcsimOptimizedAdvisorStatus,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerAccountScope,
    GcsimOptimizerCandidateResult,
    GcsimOptimizerContractError,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerEvaluationIdentity,
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerLeaderSnapshot,
    GcsimOptimizerMinimumStatConstraint,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerProgressEvent,
    GcsimOptimizerProgressLeaderQuality,
    GcsimOptimizerProgressLeaderScope,
    GcsimOptimizerProgressStage,
    GcsimOptimizerSetReference,
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerTheoreticalAllocationWitness,
    GcsimOptimizerTheoreticalStatRoll,
    GcsimOptimizerTheoreticalWearerAllocation,
    GcsimOptimizerUncertaintyLabel,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerTarget,
    GcsimOptimizerWorkPlan,
    GcsimTwoPlusTwoTargetPackage,
    adapt_gcsim_optimized_four_piece_result,
    build_gcsim_optimizer_top_n,
    canonical_gcsim_optimizer_json,
    get_gcsim_optimizer_operation_contract,
    parse_gcsim_optimizer_operation_request,
    parse_gcsim_optimizer_progress_event,
    parse_gcsim_optimizer_terminal_result,
)

from tests.run_workspace.gcsim.test_gcsim_farming_finalist_optimizer import (
    EvidenceSessionFactory,
)
from tests.run_workspace.gcsim.test_gcsim_farming_layout_scan import (
    LayoutSchedulerFactory,
)
from tests.run_workspace.gcsim.test_gcsim_farming_optimized_advisor import (
    _request as _legacy_request,
)


class GcsimOptimizerProductContractsTest(unittest.TestCase):
    def test_operations_have_distinct_v4_namespaces(self) -> None:
        contracts = tuple(
            get_gcsim_optimizer_operation_contract(operation)
            for operation in GcsimOptimizerOperation
        )

        self.assertEqual(GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION, 4)
        self.assertEqual(
            tuple(item.value for item in GcsimOptimizerOperation),
            ("theoretical_4p", "theoretical_2p2p", "account_artifacts"),
        )
        self.assertEqual(
            tuple(item.requires_artifact_database for item in contracts),
            (False, False, True),
        )
        self.assertEqual(
            len({item.cache_namespace for item in contracts}),
            len(contracts),
        )
        self.assertTrue(
            all(".v4" in item.cache_namespace for item in contracts)
        )

    def test_engine_bound_packages_serialize_canonically(self) -> None:
        gladiator = _set_ref(
            "GladiatorsFinale",
            "gladiatorsfinale",
            parameters={"stacks": 4, "enabled": True},
        )
        reordered_parameters = _set_ref(
            "GladiatorsFinale",
            "gladiatorsfinale",
            parameters={"enabled": True, "stacks": 4},
        )
        wanderer = _set_ref("WanderersTroupe", "wandererstroupe")

        self.assertEqual(gladiator, reordered_parameters)
        self.assertEqual(
            GcsimFourPieceTargetPackage(gladiator).identity_sha256,
            GcsimFourPieceTargetPackage(reordered_parameters).identity_sha256,
        )
        pair_left = GcsimTwoPlusTwoTargetPackage(gladiator, wanderer)
        pair_right = GcsimTwoPlusTwoTargetPackage(wanderer, gladiator)
        self.assertEqual(pair_left, pair_right)
        self.assertEqual(
            canonical_gcsim_optimizer_json(pair_left),
            canonical_gcsim_optimizer_json(pair_right),
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "different concrete set_uid",
        ):
            GcsimTwoPlusTwoTargetPackage(gladiator, reordered_parameters)

    def test_selected_scope_supports_one_or_many_sets_without_speed_depth(
        self,
    ) -> None:
        one_set = _account_request(pool_width=1)
        many_sets = _account_request(pool_width=2)

        self.assertIs(
            one_set.account_scope,
            GcsimOptimizerAccountScope.SELECTED_SET_POOLS,
        )
        self.assertTrue(
            all(len(item.allowed_sets) == 1 for item in one_set.selected_set_pools)
        )
        self.assertTrue(
            all(len(item.allowed_sets) == 2 for item in many_sets.selected_set_pools)
        )
        serialized = many_sets.to_dict()
        serialized_text = canonical_gcsim_optimizer_json(many_sets)
        self.assertNotIn("depth", serialized)
        self.assertNotIn('"quick"', serialized_text.lower())
        self.assertNotIn('"balanced"', serialized_text.lower())
        self.assertNotIn('"deep"', serialized_text.lower())
        self.assertNotIn("inventory_snapshot_sha256", serialized)

        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "account_character_id must be a positive integer",
        ):
            replace(
                many_sets.source_simulation.wearers[0],
                account_character_id="10001",  # type: ignore[arg-type]
            )
        mismatched_ref = replace(
            many_sets.selected_set_pools[0].allowed_sets[0],
            engine_binding_sha256="f" * 64,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "active engine/catalog binding",
        ):
            replace(
                many_sets,
                selected_set_pools=(
                    replace(
                        many_sets.selected_set_pools[0],
                        allowed_sets=(
                            mismatched_ref,
                            many_sets.selected_set_pools[0].allowed_sets[1],
                        ),
                    ),
                )
                + many_sets.selected_set_pools[1:],
            )

    def test_account_minimum_stat_constraints_are_typed_and_round_trip(self) -> None:
        request = _account_request()
        wearer = request.source_simulation.wearers[0]
        constrained = replace(
            request,
            minimum_stat_constraints=(
                GcsimOptimizerMinimumStatConstraint(
                    wearer=wearer,
                    axis_key="er",
                    minimum="0.3000",
                ),
                GcsimOptimizerMinimumStatConstraint(
                    wearer=wearer,
                    axis_key="cr",
                    minimum="0.2",
                ),
            ),
        )

        self.assertEqual(
            tuple(
                (item.axis_key, item.minimum)
                for item in constrained.minimum_stat_constraints
            ),
            (("cr", "0.2"), ("er", "0.3")),
        )
        self.assertEqual(
            parse_gcsim_optimizer_operation_request(
                canonical_gcsim_optimizer_json(constrained)
            ),
            constrained,
        )
        self.assertTrue(
            all(
                item["stat_space"] == "static_build_contribution"
                for item in constrained.to_dict()[
                    "minimum_stat_constraints"
                ]
            )
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "supported normalized artifact-build",
        ):
            GcsimOptimizerMinimumStatConstraint(
                wearer=wearer,
                axis_key="banana",
                minimum="1",
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "wearer/axis pairs must be unique",
        ):
            replace(
                request,
                minimum_stat_constraints=(
                    GcsimOptimizerMinimumStatConstraint(
                        wearer=wearer,
                        axis_key="er",
                        minimum="0.2",
                    ),
                    GcsimOptimizerMinimumStatConstraint(
                        wearer=wearer,
                        axis_key="er",
                        minimum="0.3",
                    ),
                ),
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "theoretical operation must not carry",
        ):
            replace(
                _theoretical_request(
                    GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
                ),
                minimum_stat_constraints=(
                    GcsimOptimizerMinimumStatConstraint(
                        wearer=wearer,
                        axis_key="er",
                        minimum="0.3",
                    ),
                ),
            )

    def test_all_database_scope_rejects_selected_only_fields(self) -> None:
        request = _account_request(
            scope=GcsimOptimizerAccountScope.ALL_DATABASE_SETS,
        )
        self.assertFalse(request.selected_set_pools)
        self.assertTrue(request.include_2p2p)

        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "cannot carry selected_set_pools",
        ):
            replace(
                request,
                selected_set_pools=_selected_pools(request.source_simulation, 1),
            )

    def test_four_star_overrides_are_explicit_and_scope_checked(self) -> None:
        request = _account_request(pool_width=2)
        wearer = request.source_simulation.wearers[0]
        selected_uid = request.selected_set_pools[0].allowed_sets[0].set_uid
        allowed = GcsimOptimizerFourStarEligibilityOverride(
            wearer=wearer,
            allowed_set_uids=(selected_uid,),
            allowed_artifact_ids=(42,),
        )
        request_with_override = replace(request, four_star_overrides=(allowed,))
        self.assertEqual(
            request_with_override.four_star_overrides[0].allowed_artifact_ids,
            (42,),
        )

        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "belong to that wearer's selected pool",
        ):
            replace(
                request,
                four_star_overrides=(
                    replace(allowed, allowed_set_uids=("NotSelected",)),
                ),
            )
        all_sets = _account_request(
            scope=GcsimOptimizerAccountScope.ALL_DATABASE_SETS,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "only by explicit artifact ID",
        ):
            replace(
                all_sets,
                four_star_overrides=(
                    GcsimOptimizerFourStarEligibilityOverride(
                        wearer=all_sets.source_simulation.wearers[0],
                        allowed_set_uids=("AnySet",),
                    ),
                ),
            )

    def test_account_assignment_requires_exact_4x5_and_global_uniqueness(
        self,
    ) -> None:
        request = _account_request()
        witness = _witness(request)

        self.assertEqual(len(witness.wearer_assignments), 4)
        self.assertEqual(
            len(
                {
                    artifact_id
                    for row in witness.wearer_assignments
                    for artifact_id in row.artifact_ids
                }
            ),
            20,
        )
        duplicate_rows = list(witness.wearer_assignments)
        duplicate_rows[-1] = replace(
            duplicate_rows[-1],
            artifact_ids_by_slot={
                **duplicate_rows[-1].artifact_ids_by_slot,
                "circlet": 1,
            },
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "twenty globally distinct",
        ):
            replace(witness, wearer_assignments=tuple(duplicate_rows))

    def test_candidate_request_and_evaluation_bind_before_result_construction(
        self,
    ) -> None:
        request = _account_request()
        candidate = _candidate(request, "a", 100.0, 1.0)

        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "candidate and evaluation request identities differ",
        ):
            replace(
                candidate,
                evaluation=replace(
                    candidate.evaluation,
                    request_sha256="f" * 64,
                ),
            )
        top_n = build_gcsim_optimizer_top_n(
            (candidate,),
            operation=request.operation,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "complete 4x5 assignment witness",
        ):
            GcsimOptimizerTerminalResult(
                request=request,
                status=GcsimOptimizerTerminalStatus.BEST_FOUND,
                stop_reason="completed",
                elapsed_seconds=1.0,
                top_n=replace(
                    top_n,
                    entries=(
                        replace(top_n.entries[0], account_assignment=None),
                    ),
                ),
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "evaluation does not match",
        ):
            GcsimOptimizerTerminalResult(
                request=request,
                status=GcsimOptimizerTerminalStatus.BEST_FOUND,
                stop_reason="completed",
                elapsed_seconds=1.0,
                top_n=replace(
                    top_n,
                    entries=(
                        replace(
                            top_n.entries[0],
                            evaluation=replace(
                                top_n.entries[0].evaluation,
                                compiled_config_sha256="b" * 64,
                                work_plan_sha256="f" * 64,
                            ),
                        ),
                    ),
                ),
            )

    def test_account_result_has_absolute_dps_without_baseline_or_percent(
        self,
    ) -> None:
        request = _account_request()
        candidate = replace(
            _candidate(request, "a", 100.0, 1.0),
            replacement_witnesses=(_witness(request, first_id=101),),
            equivalent_assignment_count=7,
            has_many_replacements=True,
        )
        top_n = build_gcsim_optimizer_top_n(
            (candidate,),
            operation=request.operation,
        )
        result = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="completed",
            elapsed_seconds=1.0,
            top_n=top_n,
        )

        self.assertEqual(result.best_found.estimate.dps_mean, 100.0)
        self.assertIsNone(result.best_found.percent_of_best)
        self.assertEqual(result.best_found.equivalent_assignment_count, 7)
        self.assertTrue(result.best_found.has_many_replacements)
        serialized = result.to_dict()
        serialized_text = canonical_gcsim_optimizer_json(result)
        self.assertNotIn("baseline", serialized_text)
        self.assertEqual(
            serialized["top_n"]["entries"][0]["percent_of_best"],
            None,
        )

    def test_include_2p2p_controls_account_pair_results(self) -> None:
        request = _account_request(pool_width=2, include_2p2p=False)
        pair_candidate = _candidate(
            request,
            "a",
            100.0,
            1.0,
            targets=_pair_targets(request),
        )
        top_n = build_gcsim_optimizer_top_n(
            (pair_candidate,),
            operation=request.operation,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "requires include_2p2p",
        ):
            GcsimOptimizerTerminalResult(
                request=request,
                status=GcsimOptimizerTerminalStatus.BEST_FOUND,
                stop_reason="completed",
                elapsed_seconds=1.0,
                top_n=top_n,
            )

        accepted = replace(request, include_2p2p=True)
        accepted_candidate = _candidate(
            accepted,
            "b",
            101.0,
            1.0,
            targets=_pair_targets(accepted),
        )
        result = GcsimOptimizerTerminalResult(
            request=accepted,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="completed",
            elapsed_seconds=1.0,
            top_n=build_gcsim_optimizer_top_n(
                (accepted_candidate,),
                operation=accepted.operation,
            ),
        )
        self.assertIsInstance(
            result.best_found.target_packages[0].package,
            GcsimTwoPlusTwoTargetPackage,
        )

    def test_theoretical_result_uses_percent_to_best_only(self) -> None:
        request = _theoretical_request(
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
        )
        candidates = (
            _candidate(request, "b", 97.0, 1.0),
            _candidate(request, "a", 100.0, 1.0),
        )
        top_n = build_gcsim_optimizer_top_n(
            candidates,
            operation=request.operation,
        )

        self.assertEqual(
            tuple(item.percent_of_best for item in top_n.entries),
            (100.0, 97.0),
        )
        self.assertEqual(
            tuple(item.uncertainty.label for item in top_n.entries),
            (
                GcsimOptimizerUncertaintyLabel.REFERENCE,
                GcsimOptimizerUncertaintyLabel.SEPARATED,
            ),
        )
        self.assertNotIn(
            "baseline",
            canonical_gcsim_optimizer_json(top_n),
        )

    def test_theoretical_result_round_trips_readable_equal_investment(self) -> None:
        request = _theoretical_request(
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
        )
        terminal = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="completed",
            elapsed_seconds=1.0,
            top_n=build_gcsim_optimizer_top_n(
                (_candidate(request, "a", 100.0, 1.0),),
                operation=request.operation,
            ),
        )

        parsed = parse_gcsim_optimizer_terminal_result(
            canonical_gcsim_optimizer_json(terminal)
        )
        witness = parsed.best_found.theoretical_allocation
        self.assertIsNotNone(witness)
        self.assertEqual(
            dict(witness.wearer_allocations[0].main_stats_by_slot),
            {"sands": "atk%", "goblet": "atk%", "circlet": "cr"},
        )
        self.assertEqual(witness.wearer_allocations[0].total_liquid_rolls, 20)
        self.assertEqual(
            witness.wearer_allocations[0].roll_by_axis["cd"].total_rolls,
            12,
        )

    def test_request_progress_and_result_round_trip_deterministically(self) -> None:
        request = _account_request(pool_width=2)
        result = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="completed",
            elapsed_seconds=1.5,
            top_n=build_gcsim_optimizer_top_n(
                (_candidate(request, "a", 100.0, 1.0),),
                operation=request.operation,
            ),
        )
        progress = GcsimOptimizerProgressEvent(
            request_sha256=request.request_sha256,
            operation=request.operation,
            work_plan_sha256=request.work_plan.identity_sha256,
            stage=GcsimOptimizerProgressStage.FINAL_VALIDATION,
            sequence=4,
            completed_work=8,
            planned_work=None,
            elapsed_seconds=2.5,
            remaining_seconds=None,
            cache_hits=3,
            current_iterations=200,
            current_best=GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256="c" * 64,
                estimate=GcsimOptimizerDpsEstimate(100.0, 1.0, 200),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=GcsimOptimizerProgressLeaderQuality.VERIFIED,
            ),
        )

        parsed_request = parse_gcsim_optimizer_operation_request(
            canonical_gcsim_optimizer_json(request)
        )
        parsed_progress = parse_gcsim_optimizer_progress_event(
            canonical_gcsim_optimizer_json(progress)
        )
        parsed_result = parse_gcsim_optimizer_terminal_result(
            canonical_gcsim_optimizer_json(result)
        )
        self.assertEqual(parsed_request, request)
        self.assertEqual(parsed_progress, progress)
        self.assertEqual(parsed_result, result)
        self.assertEqual(
            canonical_gcsim_optimizer_json(parsed_result),
            canonical_gcsim_optimizer_json(result),
        )

    def test_progress_v3_rejects_stale_and_incoherent_leader_metadata(self) -> None:
        request = _account_request(pool_width=2)
        progress = GcsimOptimizerProgressEvent(
            request_sha256=request.request_sha256,
            operation=request.operation,
            work_plan_sha256=request.work_plan.identity_sha256,
            stage=GcsimOptimizerProgressStage.SCREENING,
            sequence=0,
            completed_work=0,
            planned_work=64,
            elapsed_seconds=0.0,
            remaining_seconds=None,
            current_iterations=8,
        )
        stale_payload = progress.to_dict()
        stale_payload["schema_version"] = 2
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "expected version 3",
        ):
            parse_gcsim_optimizer_progress_event(stale_payload)

        missing_fidelity_payload = progress.to_dict()
        missing_fidelity_payload.pop("current_iterations")
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "missing=.*current_iterations",
        ):
            parse_gcsim_optimizer_progress_event(missing_fidelity_payload)

        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "must match current_iterations",
        ):
            GcsimOptimizerProgressEvent(
                request_sha256=request.request_sha256,
                operation=request.operation,
                work_plan_sha256=request.work_plan.identity_sha256,
                stage=GcsimOptimizerProgressStage.REFINEMENT,
                sequence=1,
                completed_work=1,
                planned_work=16,
                elapsed_seconds=1.0,
                remaining_seconds=None,
                current_iterations=32,
                current_best=GcsimOptimizerLeaderSnapshot(
                    candidate_identity_sha256="d" * 64,
                    estimate=GcsimOptimizerDpsEstimate(100.0, 1.0, 8),
                    scope=GcsimOptimizerProgressLeaderScope.STAGE,
                    quality=(
                        GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                    ),
                ),
            )

    def test_pre_v4_and_speed_depth_payloads_fail_closed(self) -> None:
        payload = _account_request().to_dict()
        payload["schema_version"] = 2
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "expected version 4",
        ):
            parse_gcsim_optimizer_operation_request(payload)

        payload = _account_request().to_dict()
        payload["depth"] = "quick"
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "unknown=.*depth",
        ):
            parse_gcsim_optimizer_operation_request(payload)

    def test_non_success_terminal_states_keep_typed_contracts(self) -> None:
        request = _theoretical_request(
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
        )
        not_ready = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.NOT_READY,
            stop_reason="source_not_ready",
            elapsed_seconds=0.0,
        )
        failed = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.FAILED,
            stop_reason="orchestration_failed",
            elapsed_seconds=0.5,
            error="typed failure",
        )

        self.assertIsNone(not_ready.best_found)
        self.assertEqual(failed.error, "typed failure")

    def test_existing_theoretical_four_piece_result_keeps_source_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_request = _legacy_request(root)
            source_result = GcsimOptimizedAdvisorSession(
                source_request,
                automatic_session_factory=lambda value: (
                    GcsimAutomaticAdvisorSession(
                        value,
                        enable_cache=False,
                        scheduler_factory=LayoutSchedulerFactory(),
                    )
                ),
                finalist_session_factory=lambda value: (
                    GcsimFinalistOptimizerSession(
                        value,
                        session_factory=EvidenceSessionFactory(
                            root / "optimizer-runs"
                        ),
                    )
                ),
            ).run()

            adapted = adapt_gcsim_optimized_four_piece_result(source_result)

        self.assertEqual(
            source_result.status,
            GcsimOptimizedAdvisorStatus.BEST_FOUND,
        )
        self.assertIs(adapted.source_evidence, source_result)
        self.assertEqual(
            adapted.contract.request.operation,
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        )
        self.assertEqual(
            adapted.contract.request.schema_version,
            GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION,
        )
        self.assertEqual(
            len(adapted.contract.top_n.entries),
            len(source_result.finalist.outcomes),
        )
        self.assertEqual(
            adapted.contract.best_found.estimate.dps_mean,
            source_result.best_found.dps_mean,
        )
        self.assertEqual(
            adapted.contract.best_found.evidence_sha256["result_json"],
            source_result.best_found.result_json_sha256,
        )
        self.assertEqual(
            adapted.contract.best_found.theoretical_allocation
            .source_allocation_sha256,
            source_result.best_found.allocation_sha256,
        )


def _wearers(*, account: bool) -> tuple[GcsimOptimizerWearerIdentity, ...]:
    keys = ("alpha", "beta", "gamma", "delta")
    return tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=(10_000 + index if account else None),
            gcsim_character_key=key,
        )
        for index, key in enumerate(keys, start=1)
    )


def _source(*, account: bool) -> GcsimOptimizerSourceSimulationIdentity:
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id="engine",
        engine_version="v1",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_sha256="1" * 64,
        engine_tree_sha256="2" * 64,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        prepared_config_sha256="5" * 64,
        rotation_sha256="6" * 64,
        target_sha256="7" * 64,
        simulation_options_sha256="8" * 64,
        wearers=_wearers(account=account),
    )


def _set_ref(
    set_uid: str,
    set_key: str,
    *,
    parameters: dict[str, str | int | float | bool] | None = None,
) -> GcsimOptimizerSetReference:
    return GcsimOptimizerSetReference(
        set_uid=set_uid,
        gcsim_set_key=set_key,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        set_parameters={} if parameters is None else parameters,
    )


def _pool_sets(index: int) -> tuple[GcsimOptimizerSetReference, ...]:
    primary = (
        ("GladiatorsFinale", "gladiatorsfinale"),
        ("WanderersTroupe", "wandererstroupe"),
        ("NoblesseOblige", "noblesseoblige"),
        ("ViridescentVenerer", "viridescentvenerer"),
    )[index]
    secondary = (
        ("ShimenawasReminiscence", "shimenawasreminiscence"),
        ("EmblemOfSeveredFate", "emblemofseveredfate"),
        ("DeepwoodMemories", "deepwoodmemories"),
        ("GoldenTroupe", "goldentroupe"),
    )[index]
    return (_set_ref(*primary), _set_ref(*secondary))


def _selected_pools(
    source: GcsimOptimizerSourceSimulationIdentity,
    width: int,
) -> tuple[GcsimOptimizerWearerSetPool, ...]:
    return tuple(
        GcsimOptimizerWearerSetPool(
            wearer=wearer,
            allowed_sets=_pool_sets(index)[:width],
        )
        for index, wearer in enumerate(source.wearers)
    )


def _work_plan(operation: GcsimOptimizerOperation) -> GcsimOptimizerWorkPlan:
    return GcsimOptimizerWorkPlan(
        operation=operation,
        plan_id="quality_first",
        plan_version=3,
        parameters={"candidate_limit": 10},
    )


def _account_request(
    *,
    scope: GcsimOptimizerAccountScope = (
        GcsimOptimizerAccountScope.SELECTED_SET_POOLS
    ),
    pool_width: int = 1,
    include_2p2p: bool = True,
) -> GcsimOptimizerOperationRequest:
    source = _source(account=True)
    return GcsimOptimizerOperationRequest(
        operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
        source_simulation=source,
        work_plan=_work_plan(GcsimOptimizerOperation.ACCOUNT_ARTIFACTS),
        account_scope=scope,
        selected_set_pools=(
            _selected_pools(source, pool_width)
            if scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS
            else ()
        ),
        include_2p2p=include_2p2p,
        artifact_database_input_sha256="9" * 64,
    )


def _theoretical_request(
    operation: GcsimOptimizerOperation,
) -> GcsimOptimizerOperationRequest:
    return GcsimOptimizerOperationRequest(
        operation=operation,
        source_simulation=_source(account=False),
        work_plan=_work_plan(operation),
    )


def _four_piece_targets(
    request: GcsimOptimizerOperationRequest,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    if request.selected_set_pools:
        refs = tuple(item.allowed_sets[0] for item in request.selected_set_pools)
    else:
        refs = tuple(_pool_sets(index)[0] for index in range(4))
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer=wearer,
            package=GcsimFourPieceTargetPackage(set_ref),
        )
        for wearer, set_ref in zip(
            request.source_simulation.wearers,
            refs,
            strict=True,
        )
    )


def _pair_targets(
    request: GcsimOptimizerOperationRequest,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer=pool.wearer,
            package=GcsimTwoPlusTwoTargetPackage(
                pool.allowed_sets[0],
                pool.allowed_sets[1],
            ),
        )
        for pool in request.selected_set_pools
    )


def _witness(
    request: GcsimOptimizerOperationRequest,
    *,
    first_id: int = 1,
) -> GcsimOptimizerAccountAssignmentWitness:
    next_id = first_id
    rows: list[GcsimOptimizerWearerArtifactAssignment] = []
    for wearer in request.source_simulation.wearers:
        rows.append(
            GcsimOptimizerWearerArtifactAssignment(
                wearer=wearer,
                artifact_ids_by_slot={
                    slot: next_id + offset
                    for offset, slot in enumerate(
                        ("flower", "plume", "sands", "goblet", "circlet")
                    )
                },
            )
        )
        next_id += 5
    return GcsimOptimizerAccountAssignmentWitness(
        request_sha256=request.request_sha256,
        artifact_database_input_sha256=(
            request.artifact_database_input_sha256
        ),
        wearer_assignments=tuple(rows),
    )


def _evaluation(
    request: GcsimOptimizerOperationRequest,
    digest_character: str,
) -> GcsimOptimizerEvaluationIdentity:
    return GcsimOptimizerEvaluationIdentity(
        request_sha256=request.request_sha256,
        source_simulation_sha256=request.source_simulation.identity_sha256,
        work_plan_sha256=request.work_plan.identity_sha256,
        engine_binding_sha256=request.source_simulation.engine_binding_sha256,
        compiled_config_sha256=digest_character * 64,
        execution_identity_sha256="e" * 64,
    )


def _candidate(
    request: GcsimOptimizerOperationRequest,
    digest_character: str,
    dps_mean: float,
    dps_se: float | None,
    *,
    targets: tuple[GcsimOptimizerWearerTarget, ...] | None = None,
) -> GcsimOptimizerCandidateResult:
    resolved_targets = (
        _four_piece_targets(request) if targets is None else targets
    )
    theoretical = (
        request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
    )
    return GcsimOptimizerCandidateResult(
        request_sha256=request.request_sha256,
        candidate_identity_sha256=digest_character * 64,
        evaluation=_evaluation(request, digest_character),
        estimate=GcsimOptimizerDpsEstimate(
            dps_mean=dps_mean,
            dps_se=dps_se,
            iterations=100,
        ),
        target_packages=resolved_targets,
        evidence_sha256=(
            {
                "allocation": digest_character * 64,
                "result": digest_character * 64,
            }
            if theoretical
            else {"result": digest_character * 64}
        ),
        theoretical_allocation=(
            _theoretical_witness(
                request,
                resolved_targets,
                digest_character,
            )
            if theoretical
            else None
        ),
        account_assignment=(
            _witness(request)
            if request.operation is GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
            else None
        ),
    )


def _theoretical_witness(
    request: GcsimOptimizerOperationRequest,
    targets: tuple[GcsimOptimizerWearerTarget, ...],
    digest_character: str,
) -> GcsimOptimizerTheoreticalAllocationWitness:
    rolls = tuple(
        GcsimOptimizerTheoreticalStatRoll(
            axis_key=axis,
            fixed_rolls=2,
            liquid_rolls=(10 if axis in {"atk%", "cd"} else 0),
        )
        for axis in (
            "atk%",
            "cr",
            "cd",
            "em",
            "er",
            "hp%",
            "def%",
            "atk",
            "def",
            "hp",
        )
    )
    rows = []
    for target in targets:
        package = target.package
        package_key = (
            package.set_ref.gcsim_set_key
            if isinstance(package, GcsimFourPieceTargetPackage)
            else f"pair_{package.identity_sha256}"
        )
        wearer = target.wearer.gcsim_character_key
        rows.append(
            GcsimOptimizerTheoreticalWearerAllocation(
                wearer=target.wearer,
                package_key=package_key,
                main_stat_layout_id="main/atkpct-atkpct-cr",
                main_stats_by_slot={
                    "sands": "atk%",
                    "goblet": "atk%",
                    "circlet": "cr",
                },
                rolls=rolls,
                total_liquid_rolls=20,
                gcsim_add_stats_lines=(
                    f"{wearer} add stats hp=4780 atk=311 atk%=0.466 "
                    "atk%=0.466 cr=0.311;",
                    f"{wearer} add stats atk%=0.0496*12 cr=0.0331*2 "
                    "cd=0.0662*12 em=19.82*2 er=0.0551*2 "
                    "hp%=0.0496*2 def%=0.062*2 atk=16.54*2 "
                    "def=19.68*2 hp=253.94*2;",
                ),
            )
        )
    return GcsimOptimizerTheoreticalAllocationWitness(
        request_sha256=request.request_sha256,
        source_allocation_sha256=digest_character * 64,
        wearer_allocations=tuple(rows),
    )


if __name__ == "__main__":
    unittest.main()
