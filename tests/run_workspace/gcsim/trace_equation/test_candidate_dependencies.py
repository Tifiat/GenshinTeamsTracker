from __future__ import annotations

import unittest

from run_workspace.gcsim.trace_equation import (
    BoundaryReachability,
    CandidateStatCoordinate,
    build_unknown_mechanic_report,
    build_candidate_dependency_slice,
    canonical_json,
    decode_engine_trace,
)
from run_workspace.gcsim.trace_equation.candidate_dependencies import (
    CandidateDependencyIndex,
)

from test_state_evidence_v6 import _v6_fixture


class CandidateDependencySliceTests(unittest.TestCase):
    def _trace(self):
        request, raw, binding, _ = _v6_fixture()
        return decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

    def test_hp_coordinate_reaches_explicit_feedback_chain(self) -> None:
        trace = self._trace()
        result = build_candidate_dependency_slice(
            trace,
            (CandidateStatCoordinate("furina", "hp%"),),
        )

        self.assertEqual(result.engine_call_count, 0)
        self.assertFalse(result.hard_prune_allowed)
        self.assertIn("event/state-event:5", result.seed_node_ids)
        self.assertIn("event/state-event:20", result.reached_node_ids)
        self.assertTrue(result.affected_hit_event_ids)
        self.assertTrue(result.reachable_boundary_keys)
        self.assertTrue(
            any(
                row.reason_code == "numeric_marker_replay_not_recomputed"
                for row in result.reachable_boundary_keys
            )
        )

    def test_crit_coordinate_reaches_terminal_formula_without_fake_state_edge(self) -> None:
        trace = self._trace()
        result = build_candidate_dependency_slice(
            trace,
            (CandidateStatCoordinate("furina", "cr"),),
        )

        self.assertTrue(result.affected_hit_event_ids)
        self.assertFalse(
            any(node == "event/state-event:5" for node in result.seed_node_ids)
        )
        self.assertEqual(result.engine_call_count, 0)

    def test_state_event_inside_terminal_occurrence_flows_to_that_hit(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        occurrence = raw["source_occurrences"][2]
        for state_event in raw["state_events"][2:7]:
            state_event["frame"] = occurrence["frame"]
        event = raw["state_events"][2]
        event["source_occurrence_id"] = occurrence["occurrence_id"]
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

        index = CandidateDependencyIndex(trace)

        self.assertIn("hit/hit:1", index.graph["event/state-event:2"])

    def test_unconsumed_defense_stays_unresolved_instead_of_fake_independence(self) -> None:
        trace = self._trace()
        result = build_candidate_dependency_slice(
            trace,
            (CandidateStatCoordinate("furina", "def%"),),
        )

        self.assertFalse(result.affected_hit_event_ids)
        self.assertFalse(result.reachable_boundary_keys)
        self.assertFalse(result.proven_independent_boundary_keys)
        self.assertTrue(result.unresolved_boundary_keys)
        self.assertFalse(result.dependency_proof_complete)
        self.assertIn(
            "opaque_or_incomplete_boundary_inputs_not_enumerated",
            result.coverage_gap_codes,
        )

    def test_slice_is_deterministic_and_coordinate_order_independent(self) -> None:
        trace = self._trace()
        left = build_candidate_dependency_slice(
            trace,
            (
                CandidateStatCoordinate("furina", "hp%"),
                CandidateStatCoordinate("furina", "cr"),
            ),
        )
        right = build_candidate_dependency_slice(
            trace,
            (
                CandidateStatCoordinate("furina", "cr"),
                CandidateStatCoordinate("furina", "hp%"),
            ),
        )

        self.assertEqual(left.slice_sha256, right.slice_sha256)
        self.assertEqual(left.to_dict(), right.to_dict())

    def test_boundary_key_routing_consumes_candidate_slice(self) -> None:
        trace = self._trace()
        dependency_slice = build_candidate_dependency_slice(
            trace,
            (CandidateStatCoordinate("furina", "hp%"),),
        )
        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=128,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=(
                dependency_slice.candidate_reachable_source_ids
            ),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source=(
                dependency_slice.affected_dimensions_by_source
            ),
            max_boundaries=128,
            max_events_per_boundary=8,
            candidate_independent_boundary_keys=frozenset(
                dependency_slice.proven_independent_boundary_keys
            ),
            candidate_reachable_boundary_keys=frozenset(
                dependency_slice.reachable_boundary_keys
            ),
        )

        self.assertTrue(
            any(
                any(
                    key.reason_code == row.reason_code
                    and key.source_id == row.source_id
                    for key in dependency_slice.reachable_boundary_keys
                )
                and row.reachability is BoundaryReachability.PROVEN_REACHABLE
                for row in report.boundaries
            )
        )


if __name__ == "__main__":
    unittest.main()
