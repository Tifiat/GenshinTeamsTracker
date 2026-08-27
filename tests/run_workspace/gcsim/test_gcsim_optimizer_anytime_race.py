from __future__ import annotations

import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationStatus,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeStatProfile,
    build_gcsim_optimizer_anytime_joint_proposals,
    build_gcsim_optimizer_dense_artifact_catalog,
    generate_gcsim_optimizer_anytime_wearer_pool,
)
from run_workspace.gcsim.optimizer_account_evaluator import (
    build_gcsim_optimizer_account_candidate_keys,
)

from run_workspace.gcsim.optimizer_anytime_race import (
    GcsimOptimizerAnytimeRacePlan,
    GcsimOptimizerAnytimeRaceSession,
    GcsimOptimizerAnytimeRaceStatus,
    GcsimOptimizerAnytimeRaceTier,
    _allocate_tier_resources,
    _close_leaders,
    _retain_evaluation_diversity,
    _retain_proposal_diversity,
    _select_survivors,
    build_gcsim_optimizer_account_package_signature,
)
from run_workspace.gcsim.optimizer_anytime_selected_service import (
    _retain_best_account_package_candidates,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerAnytimeRaceDiversityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package_a = _targets(("alpha", "beta", "gamma", "delta"))
        self.package_b = _targets(("alpha", "beta", "gamma", "epsilon"))
        self.a_leader = _proposal(
            self.package_a,
            score=100.0,
            digest_character="a",
        )
        self.a_physical_variant = _proposal(
            self.package_a,
            score=99.0,
            digest_character="b",
        )
        self.b_leader = _proposal(
            self.package_b,
            score=98.0,
            digest_character="c",
        )

    def test_signature_is_ordered_by_canonical_wearer(self) -> None:
        signature_a = build_gcsim_optimizer_account_package_signature(
            self.package_a
        )
        signature_b = build_gcsim_optimizer_account_package_signature(
            self.package_b
        )

        self.assertEqual(len(signature_a), 4)
        self.assertNotEqual(signature_a, signature_b)
        with self.assertRaisesRegex(
            RuntimeError,
            "canonical wearer slots",
        ):
            build_gcsim_optimizer_account_package_signature(
                tuple(reversed(self.package_a))
            )

    def test_proposal_budget_prefers_new_package_over_physical_duplicate(
        self,
    ) -> None:
        retained = _retain_proposal_diversity(
            (
                self.a_leader,
                self.a_physical_variant,
                self.b_leader,
            ),
            limit=2,
        )

        self.assertEqual(
            tuple(item.proposal_sha256 for item in retained),
            (
                self.a_leader.proposal_sha256,
                self.b_leader.proposal_sha256,
            ),
        )

    def test_evaluation_retention_does_not_prefill_with_one_package(
        self,
    ) -> None:
        rows = (
            _evaluation(self.a_leader, 100.0),
            _evaluation(self.a_physical_variant, 99.0),
            _evaluation(self.b_leader, 98.0),
        )

        retained = _retain_evaluation_diversity(
            rows[:2],
            rows,
            limit=2,
        )

        self.assertEqual(
            tuple(item.proposal.proposal_sha256 for item in retained),
            (
                self.a_leader.proposal_sha256,
                self.b_leader.proposal_sha256,
            ),
        )

    def test_close_rerace_uses_distinct_package_signatures(self) -> None:
        rows = (
            _evaluation(self.a_leader, 100.0),
            _evaluation(self.a_physical_variant, 99.9),
            _evaluation(self.b_leader, 99.8),
        )

        retained = _close_leaders(
            rows,
            limit=2,
            confidence_sigma=2.0,
            relative_margin=0.01,
        )

        self.assertEqual(
            tuple(item.proposal.proposal_sha256 for item in retained),
            (
                self.a_leader.proposal_sha256,
                self.b_leader.proposal_sha256,
            ),
        )

    def test_noisy_third_candidate_survives_the_early_screen(self) -> None:
        third = _proposal(
            self.package_a,
            score=97.0,
            digest_character="d",
        )
        clearly_lost = _proposal(
            self.package_a,
            score=96.0,
            digest_character="e",
        )
        rows = (
            _evaluation(self.a_leader, 100.0, dps_se=0.2),
            _evaluation(self.a_physical_variant, 99.4, dps_se=0.2),
            _evaluation(third, 98.5, dps_se=1.0),
            _evaluation(clearly_lost, 96.0, dps_se=0.1),
        )

        retained = _select_survivors(
            rows,
            limit=3,
            minimum=1,
            confidence_sigma=2.0,
            relative_margin=0.0,
        )

        retained_ids = {
            item.proposal.proposal_sha256 for item in retained
        }
        self.assertIn(third.proposal_sha256, retained_ids)
        self.assertNotIn(clearly_lost.proposal_sha256, retained_ids)

    def test_top_n_keeps_best_confirmed_build_per_package_signature(
        self,
    ) -> None:
        retained = _retain_best_account_package_candidates(
            (
                _candidate(self.a_physical_variant, 129_000.0),
                _candidate(self.b_leader, 128_000.0),
                _candidate(self.a_leader, 130_000.0),
            )
        )

        self.assertEqual(
            tuple(item.candidate_identity_sha256 for item in retained),
            (
                self.a_leader.proposal_sha256,
                self.b_leader.proposal_sha256,
            ),
        )

    def test_tier_resources_fill_small_final_races_without_oversubscription(
        self,
    ) -> None:
        plan = GcsimOptimizerAnytimeRacePlan(
            worker_count=1,
            max_parallel_candidates=15,
            total_cpu_budget=15,
        )

        self.assertEqual(
            _allocate_tier_resources(plan, proposal_count=3),
            (5, 3),
        )
        self.assertEqual(
            _allocate_tier_resources(plan, proposal_count=8),
            (1, 8),
        )
        workers, parallel = _allocate_tier_resources(
            plan,
            proposal_count=64,
        )
        self.assertLessEqual(workers * parallel, 15)
        self.assertEqual((workers, parallel), (1, 15))

        with self.assertRaisesRegex(
            RuntimeError,
            "proposal_count must be a positive integer",
        ):
            _allocate_tier_resources(plan, proposal_count=0)


class GcsimOptimizerAnytimeRaceTerminalBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.environment = build_oracle_account_environment()
        cls.proposals = _typed_race_proposals(cls.environment)

    def test_deadline_skipped_required_preserves_successful_validated_top(
        self,
    ) -> None:
        required = self.proposals[1]
        scheduler_factory = _TerminalBatchSchedulerFactory(
            terminal_iterations=200,
            terminal_status=GcsimFarmingBatchStatus.DEADLINE_REACHED,
            skipped_status=(
                GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE
            ),
            required_candidate_keys=(
                build_gcsim_optimizer_account_candidate_keys(
                    required,
                    engine_context=self.environment.engine,
                )[0]
            ),
        )

        with patch(
            "run_workspace.gcsim.optimizer_anytime_race."
            "GcsimFarmingEvaluationScheduler",
            scheduler_factory,
        ):
            result = GcsimOptimizerAnytimeRaceSession(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=self.proposals,
                required_proposal_sha256s=(required.proposal_sha256,),
                plan=_terminal_batch_plan(),
                enable_cache=False,
            ).run()

        self.assertIs(result.status, GcsimOptimizerAnytimeRaceStatus.DEADLINE)
        self.assertIsNotNone(result.best_confirmed)
        assert result.best_confirmed is not None
        self.assertEqual(result.best_confirmed.iterations, 200)
        self.assertNotEqual(
            result.best_confirmed.proposal.proposal_sha256,
            required.proposal_sha256,
        )
        validate_rows = tuple(
            item
            for item in result.trace_evaluations
            if item.iterations == 200
        )
        self.assertEqual(len(validate_rows), 2)
        self.assertTrue(any(item.success for item in validate_rows))
        self.assertEqual(
            next(
                item.result.status
                for item in validate_rows
                if item.proposal.proposal_sha256 == required.proposal_sha256
            ),
            GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
        )

    def test_cancelled_rerace_keeps_prior_required_and_successful_replacement(
        self,
    ) -> None:
        required = self.proposals[1]
        scheduler_factory = _TerminalBatchSchedulerFactory(
            terminal_iterations=1000,
            terminal_status=GcsimFarmingBatchStatus.CANCELLED,
            skipped_status=(
                GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED
            ),
            required_candidate_keys=(
                build_gcsim_optimizer_account_candidate_keys(
                    required,
                    engine_context=self.environment.engine,
                )[0]
            ),
        )

        with patch(
            "run_workspace.gcsim.optimizer_anytime_race."
            "GcsimFarmingEvaluationScheduler",
            scheduler_factory,
        ):
            result = GcsimOptimizerAnytimeRaceSession(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=self.proposals,
                required_proposal_sha256s=(required.proposal_sha256,),
                plan=_terminal_batch_plan(),
                enable_cache=False,
            ).run()

        self.assertIs(result.status, GcsimOptimizerAnytimeRaceStatus.CANCELLED)
        confirmed_by_id = {
            item.proposal.proposal_sha256: item
            for item in result.confirmed_evaluations
        }
        self.assertEqual(len(confirmed_by_id), 2)
        self.assertEqual(
            confirmed_by_id[required.proposal_sha256].iterations,
            200,
        )
        self.assertIsNotNone(result.best_confirmed)
        assert result.best_confirmed is not None
        self.assertEqual(result.best_confirmed.iterations, 1000)
        rerace_rows = tuple(
            item
            for item in result.trace_evaluations
            if item.iterations == 1000
        )
        self.assertEqual(len(rerace_rows), 2)
        self.assertTrue(any(item.success for item in rerace_rows))
        self.assertEqual(
            next(
                item.result.status
                for item in rerace_rows
                if item.proposal.proposal_sha256 == required.proposal_sha256
            ),
            GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
        )


def _targets(
    set_keys: tuple[str, str, str, str],
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer=GcsimOptimizerWearerIdentity(
                team_slot=slot,
                account_character_id=10_000 + slot,
                gcsim_character_key=f"character{slot}",
            ),
            package=GcsimFourPieceTargetPackage(
                GcsimOptimizerSetReference(
                    set_uid=f"{set_key}-uid",
                    gcsim_set_key=set_key,
                    engine_binding_sha256="1" * 64,
                    catalog_fingerprint="2" * 64,
                )
            ),
        )
        for slot, set_key in enumerate(set_keys, start=1)
    )


def _proposal(targets, *, score: float, digest_character: str):
    return SimpleNamespace(
        compiled_candidate=SimpleNamespace(targets=targets),
        surrogate_score=str(score),
        proposal_sha256=digest_character * 64,
        diversity_labels=("balanced",),
    )


def _evaluation(proposal, dps_mean: float, *, dps_se: float = 0.1):
    return SimpleNamespace(
        proposal=proposal,
        dps_mean=dps_mean,
        dps_se=dps_se,
    )


def _candidate(proposal, dps_mean: float):
    return SimpleNamespace(
        target_packages=proposal.compiled_candidate.targets,
        estimate=SimpleNamespace(dps_mean=dps_mean),
        candidate_identity_sha256=proposal.proposal_sha256,
    )


def _typed_race_proposals(environment):
    plan = GcsimOptimizerAnytimeCandidatePlan(
        max_frontier_per_group=8,
        shadow_per_group=2,
        per_profile_slot_count=4,
        max_slot_pool=16,
        wearer_beam_width=32,
        max_builds_per_target=8,
        max_builds_per_wearer=8,
        joint_beam_width=32,
        max_joint_proposals=6,
        local_search_seed_count=2,
        max_seconds=10.0,
    )
    catalog = build_gcsim_optimizer_dense_artifact_catalog(
        environment.run_input
    )
    pools = []
    for wearer, target in zip(
        environment.wearers,
        environment.targets,
        strict=True,
    ):
        profile = GcsimOptimizerAnytimeStatProfile(
            wearer=wearer,
            profile_id="terminal_batch_regression",
            stat_weights=tuple(
                1.0
                if axis == "cr"
                else 0.1
                if axis == "em"
                else 0.0
                for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
            ),
            main_scores=(),
            evidence_sha256="f" * 64,
        )
        pools.append(
            generate_gcsim_optimizer_anytime_wearer_pool(
                environment.run_input,
                catalog=catalog,
                wearer=wearer,
                targets=(target,),
                profiles=(profile,),
                plan=plan,
                hard_main_pruning=False,
            )
        )
    proposals, _coverage = build_gcsim_optimizer_anytime_joint_proposals(
        environment.run_input,
        catalog=catalog,
        wearer_pools=tuple(pools),
        plan=plan,
        execution_identity_sha256="e" * 64,
    )
    if len(proposals) < 2:
        raise AssertionError("terminal batch fixture requires two proposals")
    return tuple(proposals[:2])


def _terminal_batch_plan() -> GcsimOptimizerAnytimeRacePlan:
    return GcsimOptimizerAnytimeRacePlan(
        tiers=(
            GcsimOptimizerAnytimeRaceTier("screen_8", 8, 2, 1, 2.0),
            GcsimOptimizerAnytimeRaceTier("refine_32", 32, 2, 1, 2.0),
            GcsimOptimizerAnytimeRaceTier(
                "validate_200", 200, 2, 1, 2.0
            ),
            GcsimOptimizerAnytimeRaceTier(
                "rerace_1000", 1000, 2, 1, 2.0
            ),
        ),
        worker_count=1,
        max_parallel_candidates=1,
        total_cpu_budget=1,
        overall_deadline_seconds=30.0,
    )


class _TerminalBatchSchedulerFactory:
    def __init__(
        self,
        *,
        terminal_iterations,
        terminal_status,
        skipped_status,
        required_candidate_keys,
    ) -> None:
        self.terminal_iterations = terminal_iterations
        self.terminal_status = terminal_status
        self.skipped_status = skipped_status
        self.required_candidate_keys = required_candidate_keys

    def __call__(self, requests, budget, **kwargs):
        return _TerminalBatchScheduler(
            requests=tuple(requests),
            budget=budget,
            completion_callback=kwargs.get("completion_callback"),
            terminal_iterations=self.terminal_iterations,
            terminal_status=self.terminal_status,
            skipped_status=self.skipped_status,
            required_candidate_keys=self.required_candidate_keys,
        )


class _TerminalBatchScheduler:
    def __init__(
        self,
        *,
        requests,
        budget,
        completion_callback,
        terminal_iterations,
        terminal_status,
        skipped_status,
        required_candidate_keys,
    ) -> None:
        self.requests = requests
        self.budget = budget
        self.completion_callback = completion_callback
        self.terminal_iterations = terminal_iterations
        self.terminal_status = terminal_status
        self.skipped_status = skipped_status
        self.required_candidate_keys = required_candidate_keys

    def cancel(self) -> None:
        pass

    def run(self) -> GcsimFarmingBatchResult:
        is_terminal_tier = (
            self.requests[0].expected_iterations
            == self.terminal_iterations
        )
        results = []
        for index, request in enumerate(self.requests):
            is_required = request.candidate_keys == self.required_candidate_keys
            status = (
                self.skipped_status
                if is_terminal_tier and is_required
                else GcsimFarmingEvaluationStatus.PASSED
            )
            result = _scheduler_evaluation_result(
                request,
                status=status,
                dps_mean=100.0 if is_required else 200.0,
            )
            results.append(result)
            if self.completion_callback is not None:
                self.completion_callback(
                    index + 1,
                    len(self.requests),
                    index,
                    result,
                )
        successful = tuple(item for item in results if item.success)
        best = (
            None
            if not successful
            else min(
                successful,
                key=lambda item: (
                    -float(item.summary.dps_mean),
                    item.candidate_keys,
                ),
            )
        )
        return GcsimFarmingBatchResult(
            status=(
                self.terminal_status
                if is_terminal_tier
                else GcsimFarmingBatchStatus.COMPLETED
            ),
            comparison_context_sha256=(
                self.requests[0].comparison_context_sha256
            ),
            results=tuple(results),
            best_result=best,
            best_evaluation=None,
            requested_count=len(results),
            successful_count=len(successful),
            cache_hit_count=0,
            failed_count=0,
            skipped_count=sum(
                item.status
                in {
                    GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
                    GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
                }
                for item in results
            ),
            max_parallel_candidates=(
                self.budget.max_parallel_candidates
            ),
            total_cpu_budget=self.budget.total_cpu_budget,
            deadline_seconds=self.budget.overall_deadline_seconds,
            elapsed_seconds=0.01,
        )


def _scheduler_evaluation_result(request, *, status, dps_mean):
    success = status is GcsimFarmingEvaluationStatus.PASSED
    iterations = request.expected_iterations
    standard_deviation = 1.0
    return GcsimFarmingEvaluationResult(
        status=status,
        success=success,
        request_identity_sha256=request.identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=iterations,
        summary=(
            GcsimResultSummary(
                schema_version="1",
                sim_version="terminal-batch-fixture",
                iterations=iterations,
                dps_mean=dps_mean,
                dps_sd=standard_deviation,
                dps_se=standard_deviation / math.sqrt(iterations),
            )
            if success
            else GcsimResultSummary()
        ),
        engine_binding_sha256=request.engine_binding_sha256,
        artifact_sha256=request.artifact_sha256,
        source_config_sha256=request.identity.source_config_sha256,
        error="" if success else status.value,
    )


if __name__ == "__main__":
    unittest.main()
