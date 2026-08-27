from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationStatus,
)
from run_workspace.gcsim.optimizer_cache import GcsimOptimizerCacheStore
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_feedback_loop import (
    GcsimOptimizerFeedbackEnrichmentResponse,
    GcsimOptimizerFeedbackFidelity,
    GcsimOptimizerFeedbackPlan,
    GcsimOptimizerFeedbackStage,
    GcsimOptimizerFeedbackStopReason,
    build_gcsim_optimizer_feedback_candidate_keys,
    run_gcsim_optimizer_feedback_loop,
)
from run_workspace.gcsim.optimizer_joint_proposals import (
    GcsimOptimizerJointCandidatePool,
    GcsimOptimizerJointProposalBudget,
    solve_gcsim_optimizer_joint_proposals,
)
from run_workspace.gcsim.optimizer_lazy_candidates import (
    GcsimOptimizerCandidateResponseModel,
    GcsimOptimizerCandidateStatWeight,
    build_gcsim_optimizer_lazy_wearer_candidate_generator,
)
from run_workspace.gcsim.optimizer_main_response import (
    GcsimOptimizerResponseBranch,
    GcsimOptimizerResponseBranchKind,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerMinimumStatConstraint,
    GcsimOptimizerUncertaintyLabel,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerFeedbackLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        self.damage_proposals = self._proposals("cr", max_proposals=8)

    def test_public_facade_exports_milestone_seven_boundary(self) -> None:
        expected = {
            "GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION",
            "GcsimOptimizerFeedbackPlan",
            "GcsimOptimizerFeedbackResult",
            "GcsimOptimizerFeedbackSession",
            "build_gcsim_optimizer_feedback_candidate_keys",
            "run_gcsim_optimizer_feedback_loop",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_enrichment_recovers_absent_winner_and_rechecks_em(self) -> None:
        initial = self.damage_proposals[0]
        recovered = self.damage_proposals[1]
        em_proposal = self._proposals("em", max_proposals=1)[0]
        scores = {}
        for proposal, dps in (
            (initial, 100.0),
            (em_proposal, 80.0),
            (recovered, 120.0),
        ):
            keys = build_gcsim_optimizer_feedback_candidate_keys(proposal)
            scores[(keys, 10)] = (dps, 1.0)
            scores[(keys, 20)] = (dps, 1.0)
            scores[(keys, 40)] = (dps, 1.0)
        enrichment_calls = 0

        def enricher(request):
            nonlocal enrichment_calls
            enrichment_calls += 1
            self.assertIn("em_response", request.required_branch_labels)
            return GcsimOptimizerFeedbackEnrichmentResponse(
                proposals=(recovered,) if enrichment_calls == 1 else (),
                trace_notes=("synthetic winner enrichment",),
            )

        result = run_gcsim_optimizer_feedback_loop(
            self.environment.run_input,
            engine_context=self.environment.engine,
            proposals=(initial, em_proposal),
            plan=_plan(max_finalists=3),
            enricher=enricher,
            enable_cache=False,
            session_factory=_ScoreSessionFactory(scores),
        )

        self.assertEqual(
            result.status,
            GcsimOptimizerFeedbackStopReason.COMPLETED,
        )
        self.assertEqual(
            result.finalists[0].proposal.proposal_sha256,
            recovered.proposal_sha256,
        )
        self.assertEqual(result.coverage.enriched_proposal_count, 1)
        self.assertGreater(result.coverage.em_safeguard_finalist_count, 0)
        em_finalist = next(
            item
            for item in result.finalists
            if "em_response" in item.feature_labels
        )
        self.assertGreaterEqual(em_finalist.final_evaluation.iterations, 20)
        self.assertIn(
            "synthetic winner enrichment",
            result.enrichment_trace_notes,
        )

    def test_enrichment_below_request_floor_never_starts_simulation(
        self,
    ) -> None:
        request = replace(
            self.environment.request,
            minimum_stat_constraints=(
                GcsimOptimizerMinimumStatConstraint(
                    wearer=self.environment.wearers[0],
                    axis_key="em",
                    minimum="100",
                ),
            ),
        )
        run_input_result = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=self.environment.shell,
            artifact_database=self.environment.database,
            engine_context=self.environment.engine,
        )
        self.assertTrue(run_input_result.ready)
        run_input = run_input_result.run_input
        assert run_input is not None

        pools = self._complete_pools("cr")
        valid_alpha = next(
            item
            for item in pools[0].candidates
            if Decimal(dict(item.materialized_build.normalized_stats).get(
                "em",
                "0",
            ))
            >= Decimal("100")
        )
        below_floor_alpha = next(
            item
            for item in pools[0].candidates
            if Decimal(dict(item.materialized_build.normalized_stats).get(
                "em",
                "0",
            ))
            < Decimal("100")
        )
        fixed_other_candidates = tuple(
            next(
                item
                for item in pool.candidates
                if self.environment.shared_goblet_id
                not in item.assignment.artifact_ids
            )
            for pool in pools[1:]
        )

        def proposal_with_alpha(alpha_candidate, proposal_run_input):
            candidate_pools = (
                GcsimOptimizerJointCandidatePool(
                    wearer=self.environment.wearers[0],
                    candidates=(alpha_candidate,),
                    source_exhausted=True,
                ),
                *(
                    GcsimOptimizerJointCandidatePool(
                        wearer=wearer,
                        candidates=(candidate,),
                        source_exhausted=True,
                    )
                    for wearer, candidate in zip(
                        self.environment.wearers[1:],
                        fixed_other_candidates,
                        strict=True,
                    )
                ),
            )
            joint = solve_gcsim_optimizer_joint_proposals(
                proposal_run_input,
                targets=self.environment.targets,
                candidate_pools=candidate_pools,
                execution_identity_sha256="e" * 64,
                budget=GcsimOptimizerJointProposalBudget(max_proposals=1),
            )
            self.assertEqual(len(joint.proposals), 1)
            return joint.proposals[0]

        valid = proposal_with_alpha(valid_alpha, run_input)
        unconstrained_below_floor = proposal_with_alpha(
            below_floor_alpha,
            self.environment.run_input,
        )
        # Model a typed proposal supplied by an enrichment implementation that
        # compiled an exact-five build without applying this request's floor.
        witness = replace(
            unconstrained_below_floor.compiled_candidate.assignment_witness,
            request_sha256=request.request_sha256,
        )

        def canonical_sha256(payload):
            return hashlib.sha256(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest()

        target_identity = canonical_sha256(
            [
                item.to_dict()
                for item in unconstrained_below_floor.compiled_candidate.targets
            ]
        )
        candidate_identity = canonical_sha256(
            {
                "physical_assignment_sha256": witness.identity_sha256,
                "target_identity_sha256": target_identity,
            }
        )
        compiled = replace(
            unconstrained_below_floor.compiled_candidate,
            assignment_witness=witness,
            physical_assignment_sha256=witness.identity_sha256,
            candidate_identity_sha256=candidate_identity,
        )
        below_floor = replace(
            unconstrained_below_floor,
            compiled_candidate=compiled,
            proposal_sha256=canonical_sha256(
                {
                    "schema_version": (
                        unconstrained_below_floor.schema_version
                    ),
                    "run_input_sha256": run_input.run_input_sha256,
                    "candidate_identity_sha256": candidate_identity,
                    "wearer_candidate_sha256s": [
                        item.candidate_sha256
                        for item in (
                            unconstrained_below_floor.wearer_candidates
                        )
                    ],
                    "surrogate_score": (
                        unconstrained_below_floor.surrogate_score
                    ),
                }
            ),
        )
        self.assertTrue(
            all(
                len(item.assignment.artifact_ids) == 5
                for item in below_floor.wearer_candidates
            )
        )
        valid_keys = build_gcsim_optimizer_feedback_candidate_keys(valid)
        factory = _ScoreSessionFactory(
            {
                (valid_keys, 10): (100.0, 1.0),
                (valid_keys, 20): (101.0, 1.0),
            }
        )
        enrichment_calls = 0

        def enricher(_request):
            nonlocal enrichment_calls
            enrichment_calls += 1
            return GcsimOptimizerFeedbackEnrichmentResponse(
                proposals=(below_floor,) if enrichment_calls == 1 else (),
            )

        result = run_gcsim_optimizer_feedback_loop(
            run_input,
            engine_context=self.environment.engine,
            proposals=(valid,),
            plan=_plan(max_finalists=2),
            enricher=enricher,
            enable_cache=False,
            session_factory=factory,
        )

        self.assertEqual(factory.calls, 2)
        self.assertEqual(result.coverage.enriched_proposal_count, 0)
        self.assertEqual(
            {item.proposal.proposal_sha256 for item in result.finalists},
            {valid.proposal_sha256},
        )
        self.assertNotIn(
            below_floor.proposal_sha256,
            {
                item.proposal.proposal_sha256
                for item in result.trace_evaluations
            },
        )

    def test_close_leaders_are_reraced_with_honest_uncertainty(self) -> None:
        first = self.damage_proposals[0]
        second = next(
            proposal
            for proposal in self.damage_proposals[1:]
            if proposal.compiled_candidate.compiled_config_sha256
            != first.compiled_candidate.compiled_config_sha256
        )
        first_keys = build_gcsim_optimizer_feedback_candidate_keys(first)
        second_keys = build_gcsim_optimizer_feedback_candidate_keys(second)
        scores = {
            (first_keys, 10): (100.0, 10.0),
            (second_keys, 10): (99.5, 10.0),
            (first_keys, 20): (100.0, 10.0),
            (second_keys, 20): (99.5, 10.0),
            (first_keys, 40): (101.0, 20.0),
            (second_keys, 40): (100.8, 20.0),
        }

        result = run_gcsim_optimizer_feedback_loop(
            self.environment.run_input,
            engine_context=self.environment.engine,
            proposals=(first, second),
            plan=_plan(max_finalists=2),
            enable_cache=False,
            session_factory=_ScoreSessionFactory(scores),
        )

        self.assertEqual(result.coverage.reraced_finalist_count, 2)
        self.assertTrue(
            all(
                item.evidence_stage
                is GcsimOptimizerFeedbackStage.RERACE
                and item.final_evaluation.iterations == 40
                for item in result.finalists
            )
        )
        self.assertEqual(
            result.finalists[0].uncertainty.label,
            GcsimOptimizerUncertaintyLabel.REFERENCE,
        )
        self.assertEqual(
            result.finalists[1].uncertainty.label,
            GcsimOptimizerUncertaintyLabel.WITHIN_NOISE,
        )
        payload = result.finalists[0].to_dict()
        self.assertIn("absolute_dps", payload)
        self.assertNotIn("percent_of_best", payload)
        self.assertNotIn("baseline", payload)

    def test_exact_dps_ties_use_one_deterministic_proposal_tiebreak(self) -> None:
        first = self.damage_proposals[0]
        second = next(
            proposal
            for proposal in self.damage_proposals[1:]
            if proposal.compiled_candidate.compiled_config_sha256
            != first.compiled_candidate.compiled_config_sha256
        )
        scores = {}
        for proposal in (first, second):
            keys = build_gcsim_optimizer_feedback_candidate_keys(proposal)
            scores[(keys, 10)] = (100.0, 1.0)
            scores[(keys, 20)] = (100.0, 1.0)
            scores[(keys, 40)] = (100.0, 1.0)

        result = run_gcsim_optimizer_feedback_loop(
            self.environment.run_input,
            engine_context=self.environment.engine,
            proposals=(first, second),
            plan=_plan(max_finalists=2),
            enable_cache=False,
            session_factory=_ScoreSessionFactory(scores),
        )

        self.assertEqual(
            tuple(
                item.proposal.proposal_sha256
                for item in result.finalists
            ),
            tuple(
                sorted(
                    (
                        first.proposal_sha256,
                        second.proposal_sha256,
                    )
                )
            ),
        )

    def test_cached_and_uncached_semantics_match(self) -> None:
        proposal = self.damage_proposals[0]
        keys = build_gcsim_optimizer_feedback_candidate_keys(proposal)
        scores = {
            (keys, 10): (100.0, 2.0),
            (keys, 20): (101.0, 2.0),
        }
        factory = _ScoreSessionFactory(scores)
        with tempfile.TemporaryDirectory(prefix="gtt-m7-cache-") as tmp:
            cache = GcsimOptimizerCacheStore(Path(tmp))
            first = run_gcsim_optimizer_feedback_loop(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=(proposal,),
                plan=_plan(max_finalists=2),
                cache_store=cache,
                session_factory=factory,
            )
            calls_after_first = factory.calls
            second = run_gcsim_optimizer_feedback_loop(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=(proposal,),
                plan=_plan(max_finalists=2),
                cache_store=cache,
                session_factory=_UnexpectedSessionFactory(),
            )

        self.assertEqual(calls_after_first, 2)
        self.assertEqual(first.semantic_signature, second.semantic_signature)
        self.assertEqual(
            sum(dict(second.coverage.cache_hits_by_stage).values()),
            2,
        )

    def test_cancelled_results_are_not_cached_as_success(self) -> None:
        proposal = self.damage_proposals[0]
        keys = build_gcsim_optimizer_feedback_candidate_keys(proposal)
        with tempfile.TemporaryDirectory(prefix="gtt-m7-failed-cache-") as tmp:
            cache = GcsimOptimizerCacheStore(Path(tmp))
            failed_factory = _FailedSessionFactory(
                GcsimFarmingEvaluationStatus.CANCELLED
            )
            failed = run_gcsim_optimizer_feedback_loop(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=(proposal,),
                plan=_plan(max_finalists=2),
                cache_store=cache,
                session_factory=failed_factory,
            )
            passing_factory = _ScoreSessionFactory(
                {
                    (keys, 10): (100.0, 2.0),
                    (keys, 20): (101.0, 2.0),
                }
            )
            recovered = run_gcsim_optimizer_feedback_loop(
                self.environment.run_input,
                engine_context=self.environment.engine,
                proposals=(proposal,),
                plan=_plan(max_finalists=2),
                cache_store=cache,
                session_factory=passing_factory,
            )

        self.assertEqual(
            failed.status,
            GcsimOptimizerFeedbackStopReason.NO_SUCCESS,
        )
        self.assertGreater(passing_factory.calls, 0)
        self.assertTrue(recovered.finalists)

    def test_identical_configs_share_runs_but_keep_physical_witnesses(
        self,
    ) -> None:
        pools = list(self._complete_pools("cr"))
        alpha_candidates = tuple(
            item
            for item in pools[0].candidates
            if item.assignment.artifact_ids_by_slot["circlet"] in {10, 11}
        )
        fixed_pools = (
            GcsimOptimizerJointCandidatePool(
                wearer=pools[0].wearer,
                candidates=alpha_candidates,
                source_exhausted=True,
            ),
            *(
                GcsimOptimizerJointCandidatePool(
                    wearer=pool.wearer,
                    candidates=(
                        next(
                            item
                            for item in pool.candidates
                            if self.environment.shared_goblet_id
                            not in item.assignment.artifact_ids
                        ),
                    ),
                    source_exhausted=True,
                )
                for pool in pools[1:]
            ),
        )
        joint = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=fixed_pools,
            execution_identity_sha256="e" * 64,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=10),
        )
        self.assertEqual(len(joint.proposals), 2)
        self.assertEqual(
            len(
                {
                    item.compiled_candidate.compiled_config_sha256
                    for item in joint.proposals
                }
            ),
            1,
        )
        keys = build_gcsim_optimizer_feedback_candidate_keys(
            joint.proposals[0]
        )
        factory = _ScoreSessionFactory(
            {
                (keys, 10): (100.0, 1.0),
                (keys, 20): (101.0, 1.0),
            }
        )

        result = run_gcsim_optimizer_feedback_loop(
            self.environment.run_input,
            engine_context=self.environment.engine,
            proposals=joint.proposals,
            plan=_plan(max_finalists=2),
            enable_cache=False,
            session_factory=factory,
        )

        self.assertEqual(factory.calls, 2)
        self.assertEqual(
            result.finalists[0].equivalent_assignment_count,
            2,
        )
        self.assertEqual(
            len(result.finalists[0].replacement_proposal_sha256s),
            1,
        )

    def _proposals(self, axis, *, max_proposals):
        pools = self._complete_pools(axis)
        result = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256="e" * 64,
            budget=GcsimOptimizerJointProposalBudget(
                max_proposals=max_proposals,
            ),
        )
        return result.proposals

    def _complete_pools(self, axis):
        pools = []
        for index, target in enumerate(self.environment.targets):
            branch = GcsimOptimizerResponseBranch(
                wearer=target.wearer,
                package=target.package,
                layout=GcsimFiveStarMainStatLayout(
                    "atk%",
                    "pyro%",
                    "cr",
                ),
                kind=GcsimOptimizerResponseBranchKind.DAMAGE,
                focus_axes=(axis,),
                reasons=("synthetic_feedback_fixture",),
                evidence_probe_sha256s=(f"{index + 1:x}" * 64,),
            )
            model = GcsimOptimizerCandidateResponseModel(
                response_branch=branch,
                stat_weights=(
                    GcsimOptimizerCandidateStatWeight(axis, "1"),
                ),
            )
            batch = build_gcsim_optimizer_lazy_wearer_candidate_generator(
                self.environment.run_input,
                target=target,
                response_model=model,
            ).take(100)
            pools.append(
                GcsimOptimizerJointCandidatePool(
                    wearer=target.wearer,
                    candidates=batch.candidates,
                    source_exhausted=batch.exhausted,
                )
            )
        return tuple(pools)


def _plan(*, max_finalists):
    return GcsimOptimizerFeedbackPlan(
        screening=GcsimOptimizerFeedbackFidelity(10, 1, 2.0),
        finalist=GcsimOptimizerFeedbackFidelity(20, 1, 2.0),
        rerace=GcsimOptimizerFeedbackFidelity(40, 1, 2.0),
        max_feedback_rounds=3,
        max_screening_per_round=8,
        max_finalists=max_finalists,
        max_trace_evaluations=64,
        max_parallel_candidates=1,
        total_cpu_budget=1,
        overall_deadline_seconds=20.0,
    )


class _ScoreSessionFactory:
    def __init__(self, scores):
        self.scores = dict(scores)
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        dps, sd = self.scores[
            (request.candidate_keys, request.expected_iterations)
        ]
        return _ImmediateSession(request, dps=dps, sd=sd)


class _UnexpectedSessionFactory:
    def __call__(self, _request):
        raise AssertionError("cache hit must not start a session")


class _FailedSessionFactory:
    def __init__(self, status):
        self.status = status

    def __call__(self, request):
        return _FailedSession(request, self.status)


class _ImmediateSession:
    def __init__(self, request, *, dps, sd):
        self.request = request
        self.dps = dps
        self.sd = sd

    def cancel(self):
        pass

    def run(self):
        return _passed_result(self.request, self.dps, self.sd)


class _FailedSession:
    def __init__(self, request, status):
        self.request = request
        self.status = status

    def cancel(self):
        pass

    def run(self):
        return _failed_result(self.request, self.status)


def _passed_result(request, dps, sd):
    iterations = request.expected_iterations
    summary = GcsimResultSummary(
        schema_version="1",
        sim_version="fixture",
        iterations=iterations,
        dps_mean=dps,
        dps_sd=sd,
        dps_se=sd / math.sqrt(iterations),
    )
    return GcsimFarmingEvaluationResult(
        status=GcsimFarmingEvaluationStatus.PASSED,
        success=True,
        request_identity_sha256=request.identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        summary=summary,
        engine_binding_sha256=request.engine_binding_sha256,
        artifact_sha256=request.artifact_sha256,
        source_config_sha256=request.identity.source_config_sha256,
    )


def _failed_result(request, status):
    return GcsimFarmingEvaluationResult(
        status=status,
        success=False,
        request_identity_sha256=request.identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        engine_binding_sha256=request.engine_binding_sha256,
        artifact_sha256=request.artifact_sha256,
        source_config_sha256=request.identity.source_config_sha256,
        error="synthetic failure",
    )


if __name__ == "__main__":
    unittest.main()
