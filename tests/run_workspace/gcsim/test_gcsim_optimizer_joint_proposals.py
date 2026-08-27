from __future__ import annotations

from decimal import Decimal
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.optimizer_account_oracle import (
    run_gcsim_optimizer_account_four_piece_oracle,
)
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_joint_proposals import (
    GcsimOptimizerJointCandidatePool,
    GcsimOptimizerJointEnrichmentPolicy,
    GcsimOptimizerJointProposalBudget,
    GcsimOptimizerJointProposalStopReason,
    GcsimOptimizerJointScoreAdjustment,
    solve_gcsim_optimizer_joint_proposals,
    solve_gcsim_optimizer_joint_proposals_from_generators,
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
from run_workspace.gcsim.optimizer_oracle import GcsimOptimizerOracleScore

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerJointProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        self.execution_sha256 = "e" * 64

    def test_public_facade_exports_milestone_six_boundary(self) -> None:
        expected = {
            "GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION",
            "GcsimOptimizerJointProposal",
            "GcsimOptimizerJointProposalResult",
            "GcsimOptimizerJointProposalStopReason",
            "solve_gcsim_optimizer_joint_proposals",
            "solve_gcsim_optimizer_joint_proposals_from_generators",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_exact_bounded_solution_matches_reduced_account_oracle(self) -> None:
        coefficients = (Decimal(1), Decimal(4), Decimal(2), Decimal(3))
        pools = self._complete_pools(
            tuple(
                (("cr", Decimal(1000)), ("em", coefficient))
                for coefficient in coefficients
            )
        )
        result = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=1),
        )

        oracle = run_gcsim_optimizer_account_four_piece_oracle(
            self.environment.run_input,
            targets=self.environment.targets,
            execution_identity_sha256=self.execution_sha256,
            evaluator=lambda candidate: _oracle_score(
                candidate,
                coefficients,
            ),
        )

        self.assertEqual(
            result.status,
            GcsimOptimizerJointProposalStopReason.COMPLETED,
        )
        self.assertIsNotNone(result.best_proposal)
        self.assertEqual(
            Decimal(result.best_proposal.surrogate_score),
            Decimal(str(oracle.winner.score.objective_value)),
        )
        assignments = {
            item.target.wearer.team_slot: item.assignment
            for item in result.best_proposal.wearer_candidates
        }
        self.assertIn(
            self.environment.shared_goblet_id,
            assignments[2].artifact_ids,
        )
        all_ids = tuple(
            artifact_id
            for assignment in assignments.values()
            for artifact_id in assignment.artifact_ids
        )
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_wearer_and_pool_input_order_do_not_change_result(self) -> None:
        pools = self._complete_pools(
            ((("cr", Decimal(1)),),) * 4
        )
        forward = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=4),
        )
        reversed_result = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=tuple(reversed(self.environment.targets)),
            candidate_pools=tuple(reversed(pools)),
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=4),
        )

        self.assertEqual(
            tuple(item.proposal_sha256 for item in forward.proposals),
            tuple(
                item.proposal_sha256
                for item in reversed_result.proposals
            ),
        )

    def test_feedback_adjustment_assigns_contested_piece_to_best_wearer(
        self,
    ) -> None:
        pools = self._complete_pools(
            ((("cr", Decimal(1)),),) * 4
        )
        baseline = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=1),
        )
        beta_shared = next(
            item
            for item in pools[1].candidates
            if self.environment.shared_goblet_id
            in item.assignment.artifact_ids
        )
        adjusted = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=1),
            score_adjustments=(
                GcsimOptimizerJointScoreAdjustment(
                    wearer=self.environment.wearers[1],
                    candidate_sha256=beta_shared.candidate_sha256,
                    score_delta="100",
                    evidence_sha256="f" * 64,
                    reason="synthetic_gcsim_feedback",
                ),
            ),
        )

        self.assertNotIn(
            self.environment.shared_goblet_id,
            baseline.best_proposal.wearer_candidates[1].assignment.artifact_ids,
        )
        self.assertIn(
            self.environment.shared_goblet_id,
            adjusted.best_proposal.wearer_candidates[1].assignment.artifact_ids,
        )

    def test_lazy_conflict_repair_finds_three_wearer_change(self) -> None:
        generators = tuple(
            self._generator(
                index,
                (("em", Decimal(1)),),
            )
            for index in range(4)
        )

        result = solve_gcsim_optimizer_joint_proposals_from_generators(
            self.environment.run_input,
            targets=self.environment.targets,
            generators=generators,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=1),
            enrichment=GcsimOptimizerJointEnrichmentPolicy(
                initial_candidates_per_generator=1,
                candidates_per_round=1,
                max_rounds=4,
            ),
        )

        self.assertEqual(
            result.status,
            GcsimOptimizerJointProposalStopReason.COMPLETED,
        )
        self.assertEqual(result.best_proposal.changed_wearer_count, 3)
        self.assertGreater(result.coverage.lazy_request_count, 4)
        self.assertGreater(result.coverage.enrichment_round_count, 0)
        self.assertGreater(
            dict(result.coverage.coordinated_change_counts)[3],
            0,
        )

    def test_stop_reasons_and_cancelled_best_so_far_are_distinct(self) -> None:
        pools = self._complete_pools(
            ((("cr", Decimal(1)),),) * 4
        )
        cancelled_calls = 0

        def cancel_after_one_state() -> bool:
            nonlocal cancelled_calls
            cancelled_calls += 1
            return cancelled_calls > 2

        cancelled = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(max_proposals=100),
            is_cancelled=cancel_after_one_state,
        )
        cancelled_empty = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            is_cancelled=lambda: True,
        )
        bounded = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(
                model_score_floor="999999",
            ),
        )
        clock = _SequenceClock((0.0, 0.0, 0.0, 2.0, 2.0))
        deadline = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=pools,
            execution_identity_sha256=self.execution_sha256,
            budget=GcsimOptimizerJointProposalBudget(
                max_proposals=100,
                max_seconds=1.0,
            ),
            clock=clock,
        )
        shared_only = tuple(
            GcsimOptimizerJointCandidatePool(
                wearer=pool.wearer,
                candidates=(
                    next(
                        item
                        for item in pool.candidates
                        if self.environment.shared_goblet_id
                        in item.assignment.artifact_ids
                    ),
                ),
                source_exhausted=True,
            )
            for pool in pools
        )
        exhausted = solve_gcsim_optimizer_joint_proposals(
            self.environment.run_input,
            targets=self.environment.targets,
            candidate_pools=shared_only,
            execution_identity_sha256=self.execution_sha256,
        )

        self.assertEqual(
            cancelled.status,
            GcsimOptimizerJointProposalStopReason.CANCELLED,
        )
        self.assertIsNotNone(cancelled.best_proposal)
        self.assertIsNone(cancelled_empty.best_proposal)
        self.assertEqual(
            bounded.status,
            GcsimOptimizerJointProposalStopReason.MODEL_BOUND_PRUNED,
        )
        self.assertEqual(
            deadline.status,
            GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED,
        )
        self.assertIsNotNone(deadline.best_proposal)
        self.assertEqual(
            exhausted.status,
            GcsimOptimizerJointProposalStopReason.POOL_EXHAUSTED,
        )
        self.assertIsNone(exhausted.best_proposal)

    def _complete_pools(self, wearer_weights):
        pools = []
        for index, weights in enumerate(wearer_weights):
            batch = self._generator(index, weights).take(100)
            pools.append(
                GcsimOptimizerJointCandidatePool(
                    wearer=self.environment.wearers[index],
                    candidates=batch.candidates,
                    source_exhausted=batch.exhausted,
                )
            )
        return tuple(pools)

    def _generator(self, index, weights):
        target = self.environment.targets[index]
        branch = GcsimOptimizerResponseBranch(
            wearer=target.wearer,
            package=target.package,
            layout=GcsimFiveStarMainStatLayout(
                sands="atk%",
                goblet="pyro%",
                circlet="cr",
            ),
            kind=GcsimOptimizerResponseBranchKind.DAMAGE,
            focus_axes=tuple(axis for axis, _weight in weights),
            reasons=("synthetic_joint_fixture",),
            evidence_probe_sha256s=(f"{index + 1:x}" * 64,),
        )
        response_model = GcsimOptimizerCandidateResponseModel(
            response_branch=branch,
            stat_weights=tuple(
                GcsimOptimizerCandidateStatWeight(
                    axis_key=axis,
                    weight=str(weight),
                )
                for axis, weight in weights
            ),
        )
        return build_gcsim_optimizer_lazy_wearer_candidate_generator(
            self.environment.run_input,
            target=target,
            response_model=response_model,
        )


class _SequenceClock:
    def __init__(self, values):
        self._values = iter(values)
        self._last = 0.0

    def __call__(self):
        try:
            self._last = next(self._values)
        except StopIteration:
            pass
        return self._last


def _oracle_score(candidate, coefficients):
    score = Decimal(0)
    for build, coefficient in zip(
        candidate.builds,
        coefficients,
        strict=True,
    ):
        stats = {
            key: Decimal(value) for key, value in build.normalized_stats
        }
        score += stats.get("cr", Decimal(0)) * Decimal(1000)
        score += stats.get("em", Decimal(0)) * coefficient
    return GcsimOptimizerOracleScore(
        objective_name="synthetic_joint_value",
        objective_value=float(score),
        evidence_sha256=candidate.compiled_config_sha256,
    )


if __name__ == "__main__":
    unittest.main()
