from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    FinalistReason,
    TraceContractError,
    UncertaintyShortlistPolicy,
    build_uncertainty_shortlist_plan,
    score_with_frozen_boundaries,
)

from test_contracts import _document
from test_ranking import _with_amplifying_reaction, _with_unresolved_flat_damage


_FIDELITY = "f" * 64
_SEEDS = "e" * 64


class UncertaintyShortlistTests(unittest.TestCase):
    def test_numeric_leaders_and_lower_uncertainty_representatives_are_retained(
        self,
    ) -> None:
        numeric_best = _score(0.90)
        numeric_second = _score(0.80)
        reachable = _with_reachable_input(_score(0.30), boundary_count=40)
        unresolved = _with_unresolved(_score(0.20), boundary_count=90)

        plan = _plan(
            (unresolved, numeric_second, reachable, numeric_best),
            finalist_limit=4,
            numeric_limit=2,
            reachable_limit=1,
            unresolved_limit=1,
        )

        self.assertEqual(plan.selected_candidate_count, 4)
        self.assertEqual(plan.engine_call_count, 0)
        self.assertFalse(plan.execution_authorized)
        self.assertFalse(plan.hard_prune_allowed)
        self.assertEqual(
            [row.candidate_sha256 for row in plan.requests[:2]],
            [numeric_best.candidate_sha256, numeric_second.candidate_sha256],
        )
        reasons = {row.candidate_sha256: set(row.reasons) for row in plan.requests}
        self.assertIn(
            FinalistReason.REACHABLE_UNCERTAINTY_REPRESENTATIVE,
            reasons[reachable.candidate_sha256],
        )
        self.assertIn(
            FinalistReason.UNRESOLVED_UNCERTAINTY_REPRESENTATIVE,
            reasons[unresolved.candidate_sha256],
        )

    def test_input_order_does_not_change_plan_identity(self) -> None:
        rows = (
            _score(0.40),
            _with_reachable_input(_score(0.30), boundary_count=3),
            _with_unresolved(_score(0.20), boundary_count=5),
        )

        left = _plan(
            rows,
            finalist_limit=3,
            numeric_limit=1,
            reachable_limit=1,
            unresolved_limit=1,
        )
        right = _plan(
            tuple(reversed(rows)),
            finalist_limit=3,
            numeric_limit=1,
            reachable_limit=1,
            unresolved_limit=1,
        )

        self.assertEqual(left.plan_sha256, right.plan_sha256)
        self.assertEqual(left.to_dict(), right.to_dict())

    def test_duplicate_candidate_is_one_request(self) -> None:
        score = _with_reachable_input(_score(0.40), boundary_count=12)

        plan = _plan(
            (score, score),
            finalist_limit=2,
            numeric_limit=1,
            reachable_limit=1,
            unresolved_limit=0,
        )

        self.assertEqual(plan.input_candidate_count, 2)
        self.assertEqual(plan.duplicate_candidate_count, 1)
        self.assertEqual(plan.numeric_candidate_count, 1)
        self.assertEqual(plan.selected_candidate_count, 1)
        self.assertEqual(
            set(plan.requests[0].reasons),
            {
                FinalistReason.NUMERIC_LEADER,
                FinalistReason.REACHABLE_UNCERTAINTY_REPRESENTATIVE,
            },
        )

    def test_many_boundaries_never_create_many_requests(self) -> None:
        numeric = _score(0.60)
        uncertain = _with_reachable_input(_score(0.10), boundary_count=100_000)

        plan = _plan(
            (numeric, uncertain),
            finalist_limit=2,
            numeric_limit=1,
            reachable_limit=1,
            unresolved_limit=0,
        )

        self.assertEqual(plan.selected_candidate_count, 2)
        uncertain_request = next(
            row
            for row in plan.requests
            if row.candidate_sha256 == uncertain.candidate_sha256
        )
        self.assertEqual(uncertain_request.candidate_reachable_boundary_count, 100_000)

    def test_representative_order_prefers_distinct_uncertainty_shapes(self) -> None:
        input_high = _with_reachable_input(_score(0.70), boundary_count=5)
        input_low = _with_reachable_input(_score(0.60), boundary_count=6)
        topology = _with_reachable_topology(_score(0.20), boundary_count=2)

        plan = _plan(
            (input_low, topology, input_high),
            finalist_limit=3,
            numeric_limit=1,
            reachable_limit=2,
            unresolved_limit=0,
        )

        selected = {row.candidate_sha256 for row in plan.requests}
        self.assertIn(input_high.candidate_sha256, selected)
        self.assertIn(topology.candidate_sha256, selected)
        self.assertNotIn(input_low.candidate_sha256, selected)

    def test_policy_requires_one_shared_limit_for_all_lanes(self) -> None:
        with self.assertRaises(TraceContractError):
            UncertaintyShortlistPolicy(
                finalist_limit=3,
                numeric_leader_limit=2,
                reachable_representative_limit=1,
                unresolved_representative_limit=1,
            )


def _source_document():
    return _with_amplifying_reaction(
        _with_unresolved_flat_damage(_document(), 100.0)
    )


def _score(candidate_cr: float):
    return score_with_frozen_boundaries(
        _source_document(),
        (
            ArtifactStatReplacement(
                actor_key="hero",
                stat_key="cr",
                baseline_artifact_value=0.50,
                candidate_artifact_value=candidate_cr,
            ),
        ),
    )


def _with_reachable_input(score, *, boundary_count: int):
    coverage = replace(
        score.coverage,
        candidate_reachable_frozen_input_damage=(
            score.coverage.frozen_input_exposed_damage
        ),
        candidate_affected_hit_count=1,
        candidate_reachable_boundary_count=boundary_count,
        candidate_dependency_slice_sha256="a" * 64,
    )
    return replace(score, coverage=coverage)


def _with_reachable_topology(score, *, boundary_count: int):
    coverage = replace(
        score.coverage,
        candidate_reachable_topology_damage=score.coverage.topology_exposed_damage,
        candidate_affected_hit_count=1,
        candidate_reachable_boundary_count=boundary_count,
        candidate_dependency_slice_sha256="b" * 64,
    )
    return replace(score, coverage=coverage)


def _with_unresolved(score, *, boundary_count: int):
    coverage = replace(
        score.coverage,
        candidate_unresolved_boundary_count=boundary_count,
        candidate_dependency_slice_sha256="c" * 64,
        candidate_dependency_gap_codes=(
            "opaque_or_incomplete_boundary_inputs_not_enumerated",
        ),
    )
    return replace(score, coverage=coverage)


def _plan(
    scores,
    *,
    finalist_limit: int,
    numeric_limit: int,
    reachable_limit: int,
    unresolved_limit: int,
):
    return build_uncertainty_shortlist_plan(
        tuple(scores),
        policy=UncertaintyShortlistPolicy(
            finalist_limit=finalist_limit,
            numeric_leader_limit=numeric_limit,
            reachable_representative_limit=reachable_limit,
            unresolved_representative_limit=unresolved_limit,
        ),
        fidelity_sha256=_FIDELITY,
        seed_panel_sha256=_SEEDS,
    )


if __name__ == "__main__":
    unittest.main()
