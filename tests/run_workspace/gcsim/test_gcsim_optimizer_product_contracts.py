from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import run_workspace.gcsim as gcsim_api
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
    GcsimOptimizerCandidateResult,
    GcsimOptimizerContractError,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerProgressEvent,
    GcsimOptimizerProgressStage,
    GcsimOptimizerSearchBudget,
    GcsimOptimizerSearchDepth,
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerUncertaintyLabel,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
    adapt_gcsim_optimized_four_piece_result,
    build_gcsim_optimizer_top_n,
    canonical_gcsim_optimizer_json,
    get_gcsim_optimizer_operation_contract,
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
    def test_public_facade_exports_milestone_zero_contracts(self) -> None:
        expected = {
            "GcsimOptimizerOperation",
            "GcsimOptimizerOperationRequest",
            "GcsimOptimizerSearchDepth",
            "GcsimFourPieceTargetPackage",
            "GcsimTwoPlusTwoTargetPackage",
            "GcsimOptimizerTerminalStatus",
            "GcsimOptimizerProgressEvent",
            "GcsimOptimizerTopN",
            "adapt_gcsim_optimized_four_piece_result",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))

    def test_operations_have_distinct_versioned_namespaces(self) -> None:
        contracts = tuple(
            get_gcsim_optimizer_operation_contract(operation)
            for operation in GcsimOptimizerOperation
        )

        self.assertEqual(
            tuple(item.value for item in GcsimOptimizerOperation),
            ("theoretical_4p", "theoretical_2p2p", "account_artifacts"),
        )
        self.assertEqual(
            tuple(item.value for item in GcsimOptimizerSearchDepth),
            ("quick", "balanced", "deep"),
        )
        self.assertEqual(
            tuple(item.value for item in GcsimOptimizerTerminalStatus),
            (
                "best_found",
                "cancelled",
                "deadline",
                "not_ready",
                "no_success",
                "failed",
            ),
        )
        self.assertEqual(
            {item.schema_version for item in contracts},
            {GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION},
        )
        self.assertEqual(
            len({item.cache_namespace for item in contracts}),
            len(contracts),
        )
        self.assertEqual(
            len({item.provenance_namespace for item in contracts}),
            len(contracts),
        )
        self.assertEqual(
            tuple(item.requires_account_depth for item in contracts),
            (False, False, True),
        )

    def test_target_packages_serialize_canonically(self) -> None:
        four_left = GcsimFourPieceTargetPackage(
            set_key="gladiatorsfinale",
            set_parameters={"stacks": 4, "enabled": True},
        )
        four_right = GcsimFourPieceTargetPackage(
            set_key="gladiatorsfinale",
            set_parameters={"enabled": True, "stacks": 4},
        )
        pair_left = GcsimTwoPlusTwoTargetPackage(
            set_a="wandererstroupe",
            set_b="gladiatorsfinale",
            set_a_parameters={"variant": "a"},
            set_b_parameters={"variant": "b"},
        )
        pair_right = GcsimTwoPlusTwoTargetPackage(
            set_a="gladiatorsfinale",
            set_b="wandererstroupe",
            set_a_parameters={"variant": "b"},
            set_b_parameters={"variant": "a"},
        )

        self.assertEqual(four_left, four_right)
        self.assertEqual(four_left.identity_sha256, four_right.identity_sha256)
        self.assertEqual(pair_left, pair_right)
        self.assertEqual(pair_left.identity_sha256, pair_right.identity_sha256)
        self.assertEqual(pair_left.set_a, "gladiatorsfinale")
        self.assertEqual(pair_left.set_b, "wandererstroupe")
        self.assertEqual(
            canonical_gcsim_optimizer_json(pair_left),
            canonical_gcsim_optimizer_json(pair_right),
        )

    def test_invalid_or_excluded_package_shapes_are_unrepresentable(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "two different set keys",
        ):
            GcsimTwoPlusTwoTargetPackage(
                set_a="gladiatorsfinale",
                set_b="gladiatorsfinale",
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "canonical lowercase",
        ):
            GcsimFourPieceTargetPackage(set_key="Rainbow")
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "FourPiece or TwoPlusTwo",
        ):
            GcsimOptimizerWearerTarget(
                wearer_id="alpha",
                package="2p+1+1+1",  # type: ignore[arg-type]
            )

    def test_depth_is_required_only_for_account_budgets(self) -> None:
        theoretical = GcsimOptimizerSearchBudget(
            operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            budget_id="theoretical_v1",
            budget_version=1,
            parameters={"finalists": 10},
        )
        account = GcsimOptimizerSearchBudget(
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            budget_id="account_quick",
            budget_version=1,
            depth=GcsimOptimizerSearchDepth.QUICK,
            parameters={"candidate_limit": 10},
        )

        self.assertIsNone(theoretical.depth)
        self.assertIs(account.depth, GcsimOptimizerSearchDepth.QUICK)
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "must not carry account search depth",
        ):
            replace(theoretical, depth=GcsimOptimizerSearchDepth.DEEP)
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "requires Quick, Balanced, or Deep",
        ):
            replace(account, depth=None)

    def test_account_request_requires_four_targets_and_inventory(self) -> None:
        source = _source()
        budget = _account_budget(GcsimOptimizerSearchDepth.BALANCED)
        targets = _mixed_targets()
        request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            source_simulation=source,
            search_budget=budget,
            target_packages=targets,
            inventory_snapshot_sha256="9" * 64,
        )

        self.assertEqual(request.depth, GcsimOptimizerSearchDepth.BALANCED)
        self.assertIn("account_artifacts.v1", request.cache_namespace)
        self.assertEqual(
            request.request_sha256,
            replace(request).request_sha256,
        )
        self.assertEqual(
            canonical_gcsim_optimizer_json(request),
            canonical_gcsim_optimizer_json(replace(request)),
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "one target package for every source wearer",
        ):
            replace(request, target_packages=targets[:3])
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "inventory_snapshot_sha256",
        ):
            replace(request, inventory_snapshot_sha256="")

    def test_mixed_operation_request_fails_before_execution(self) -> None:
        source = _source()
        theoretical_budget = GcsimOptimizerSearchBudget(
            operation=GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
            budget_id="theoretical_pairs",
            budget_version=1,
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "another optimizer operation",
        ):
            GcsimOptimizerOperationRequest(
                operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
                source_simulation=source,
                search_budget=theoretical_budget,
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "must not carry selected account targets",
        ):
            GcsimOptimizerOperationRequest(
                operation=GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
                source_simulation=source,
                search_budget=theoretical_budget,
                target_packages=_mixed_targets(),
            )

    def test_progress_event_has_typed_mode_and_budget_semantics(self) -> None:
        event = GcsimOptimizerProgressEvent(
            request_sha256="a" * 64,
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            depth=GcsimOptimizerSearchDepth.DEEP,
            stage=GcsimOptimizerProgressStage.JOINT_SEARCH,
            sequence=4,
            completed_work=8,
            planned_work=20,
            elapsed_seconds=2.5,
            remaining_seconds=7.5,
            cache_hits=3,
        )

        self.assertEqual(event.to_dict()["depth"], "deep")
        self.assertEqual(event.event_sha256, replace(event).event_sha256)
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "must not carry account search depth",
        ):
            replace(
                event,
                operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "cannot exceed",
        ):
            replace(event, completed_work=21)

    def test_top_n_uses_common_percent_delta_and_uncertainty_semantics(self) -> None:
        targets = _four_piece_targets()
        candidates = (
            _candidate("1", 99.0, 1.0, targets),
            _candidate("0", 100.0, 1.0, targets),
            _candidate("2", 90.0, 1.0, targets),
            _candidate("3", 80.0, None, targets),
        )

        top_n = build_gcsim_optimizer_top_n(
            candidates,
            baseline_dps=85.0,
        )

        self.assertEqual(
            tuple(item.estimate.dps_mean for item in top_n.entries),
            (100.0, 99.0, 90.0, 80.0),
        )
        self.assertEqual(
            tuple(item.uncertainty.label for item in top_n.entries),
            (
                GcsimOptimizerUncertaintyLabel.REFERENCE,
                GcsimOptimizerUncertaintyLabel.WITHIN_NOISE,
                GcsimOptimizerUncertaintyLabel.SEPARATED,
                GcsimOptimizerUncertaintyLabel.UNKNOWN,
            ),
        )
        self.assertEqual(top_n.entries[1].percent_of_best, 99.0)
        self.assertEqual(top_n.entries[1].dps_delta_to_best, -1.0)
        self.assertEqual(top_n.entries[0].baseline_delta, 15.0)
        self.assertIsNone(
            top_n.entries[-1].uncertainty.combined_standard_error
        )

    def test_terminal_status_and_operation_specific_result_shapes_are_checked(
        self,
    ) -> None:
        source = _source()
        request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            source_simulation=source,
            search_budget=GcsimOptimizerSearchBudget(
                operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
                budget_id="theoretical_v1",
                budget_version=1,
            ),
        )
        top_n = build_gcsim_optimizer_top_n(
            (_candidate("0", 100.0, 1.0, _four_piece_targets()),)
        )
        result = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="completed",
            elapsed_seconds=1.0,
            top_n=top_n,
        )

        self.assertIsNotNone(result.best_found)
        self.assertEqual(result.result_sha256, replace(result).result_sha256)
        cancelled = replace(
            result,
            status=GcsimOptimizerTerminalStatus.CANCELLED,
            stop_reason="cancelled",
        )
        self.assertIsNotNone(cancelled.best_found)
        failed_with_evidence = replace(
            result,
            status=GcsimOptimizerTerminalStatus.FAILED,
            stop_reason="orchestration_failed",
            error="late failure after a completed candidate",
        )
        self.assertIsNotNone(failed_with_evidence.best_found)
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "require no top-N evidence",
        ):
            replace(
                result,
                status=GcsimOptimizerTerminalStatus.NO_SUCCESS,
                stop_reason="no_success",
            )
        wrong_shape = build_gcsim_optimizer_top_n(
            (_candidate("1", 100.0, 1.0, _two_plus_two_targets()),)
        )
        with self.assertRaisesRegex(
            GcsimOptimizerContractError,
            "only FourPiece",
        ):
            replace(result, top_n=wrong_shape)
        pair_request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
            source_simulation=source,
            search_budget=GcsimOptimizerSearchBudget(
                operation=GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
                budget_id="theoretical_pairs",
                budget_version=1,
            ),
        )
        pair_result = replace(
            result,
            request=pair_request,
            top_n=wrong_shape,
        )
        self.assertIsInstance(
            pair_result.best_found.target_packages[0].package,
            GcsimTwoPlusTwoTargetPackage,
        )
        account_targets = _mixed_targets()
        account_request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            source_simulation=source,
            search_budget=_account_budget(GcsimOptimizerSearchDepth.QUICK),
            target_packages=account_targets,
            inventory_snapshot_sha256="9" * 64,
        )
        account_result = replace(
            result,
            request=account_request,
            top_n=build_gcsim_optimizer_top_n(
                (_candidate("2", 100.0, 1.0, account_targets),)
            ),
        )
        self.assertEqual(
            account_result.best_found.target_packages,
            account_request.target_packages,
        )

    def test_non_success_terminal_states_have_coherent_evidence_rules(self) -> None:
        request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            source_simulation=_source(),
            search_budget=GcsimOptimizerSearchBudget(
                operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
                budget_id="theoretical_v1",
                budget_version=1,
            ),
        )

        not_ready = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.NOT_READY,
            stop_reason="source_not_ready",
            elapsed_seconds=0.0,
            issues=("missing_engine_entity",),
        )
        failed = GcsimOptimizerTerminalResult(
            request=request,
            status=GcsimOptimizerTerminalStatus.FAILED,
            stop_reason="orchestration_failed",
            elapsed_seconds=0.5,
            error="typed failure",
        )

        self.assertIsNone(not_ready.best_found)
        self.assertEqual(not_ready.issues, ("missing_engine_entity",))
        self.assertEqual(failed.error, "typed failure")

    def test_existing_theoretical_four_piece_result_adapts_without_evidence_loss(
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
            adapted.contract.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
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


def _source() -> GcsimOptimizerSourceSimulationIdentity:
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id="engine",
        engine_version="v1",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_sha256="1" * 64,
        engine_tree_sha256="2" * 64,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        source_config_sha256="5" * 64,
        wearer_ids=("alpha", "beta", "gamma", "delta"),
    )


def _account_budget(
    depth: GcsimOptimizerSearchDepth,
) -> GcsimOptimizerSearchBudget:
    return GcsimOptimizerSearchBudget(
        operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
        budget_id=f"account_{depth.value}",
        budget_version=1,
        depth=depth,
        parameters={"candidate_limit": 10},
    )


def _mixed_targets() -> tuple[GcsimOptimizerWearerTarget, ...]:
    return (
        GcsimOptimizerWearerTarget(
            "alpha",
            GcsimFourPieceTargetPackage("gladiatorsfinale"),
        ),
        GcsimOptimizerWearerTarget(
            "beta",
            GcsimTwoPlusTwoTargetPackage(
                "gladiatorsfinale",
                "wandererstroupe",
            ),
        ),
        GcsimOptimizerWearerTarget(
            "gamma",
            GcsimFourPieceTargetPackage("noblesseoblige"),
        ),
        GcsimOptimizerWearerTarget(
            "delta",
            GcsimFourPieceTargetPackage("viridescentvenerer"),
        ),
    )


def _four_piece_targets() -> tuple[GcsimOptimizerWearerTarget, ...]:
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer_id,
            GcsimFourPieceTargetPackage(set_key),
        )
        for wearer_id, set_key in zip(
            ("alpha", "beta", "gamma", "delta"),
            (
                "gladiatorsfinale",
                "wandererstroupe",
                "noblesseoblige",
                "viridescentvenerer",
            ),
            strict=True,
        )
    )


def _two_plus_two_targets() -> tuple[GcsimOptimizerWearerTarget, ...]:
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer_id,
            GcsimTwoPlusTwoTargetPackage(
                "gladiatorsfinale",
                second_set,
            ),
        )
        for wearer_id, second_set in zip(
            ("alpha", "beta", "gamma", "delta"),
            (
                "wandererstroupe",
                "noblesseoblige",
                "viridescentvenerer",
                "shimenawasreminiscence",
            ),
            strict=True,
        )
    )


def _candidate(
    digest_character: str,
    dps_mean: float,
    dps_se: float | None,
    targets: tuple[GcsimOptimizerWearerTarget, ...],
) -> GcsimOptimizerCandidateResult:
    return GcsimOptimizerCandidateResult(
        candidate_identity_sha256=digest_character * 64,
        estimate=GcsimOptimizerDpsEstimate(
            dps_mean=dps_mean,
            dps_se=dps_se,
            iterations=100,
        ),
        target_packages=targets,
        evidence_sha256={"result": digest_character * 64},
    )


if __name__ == "__main__":
    unittest.main()
