from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import unittest

from run_workspace.gcsim.trace_equation import (
    SourceLocator,
    SourceManifestBinding,
    SourceManifestEntry,
    SourceSeam,
    SourceSliceStatus,
    SourceSliceTemplate,
    canonical_json,
    decode_engine_trace,
)
from run_workspace.gcsim.trace_equation.unknown_mechanics import (
    BoundaryFallback,
    BoundaryReachability,
    build_unknown_mechanic_report,
    diagnostic_json,
    validate_secret_free_diagnostic,
)

from test_state_evidence_v6 import _v6_fixture


class UnknownMechanicReportTests(unittest.TestCase):
    def test_report_is_deterministic_bounded_and_fail_open(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        source_id = raw["state_events"][12]["source_id"]
        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset({source_id}),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={source_id: ("hp%", "hp%")},
            max_boundaries=64,
            max_events_per_boundary=8,
        )
        second = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset({source_id}),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={source_id: ("hp%",)},
            max_boundaries=64,
            max_events_per_boundary=8,
        )
        self.assertEqual(diagnostic_json(report), diagnostic_json(second))
        self.assertTrue(report.boundaries)
        self.assertTrue(
            all(
                row.fallback is BoundaryFallback.KEEP_FOR_EXACT
                for row in report.boundaries
            )
        )
        self.assertFalse(report.exact_boundary_overflow)
        self.assertTrue(report.routing_complete)
        self.assertEqual(
            report.exact_boundary_admitted,
            report.exact_boundary_required,
        )
        self.assertTrue(
            any(
                row.source_id == source_id
                and row.reachability is BoundaryReachability.PROVEN_REACHABLE
                for row in report.boundaries
            )
        )
        self.assertTrue(
            any(row.affected_candidate_dimensions == ("hp%",) for row in report.boundaries)
        )
        bounded = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset({source_id}),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={source_id: ("hp%",)},
            max_boundaries=1,
            max_events_per_boundary=1,
        )
        self.assertEqual(len(bounded.boundaries), 1)
        self.assertTrue(bounded.truncated)
        self.assertLessEqual(len(bounded.boundaries[0].event_ids), 1)
        self.assertEqual(
            bounded.exact_boundary_required,
            report.exact_boundary_required,
        )

    def test_independent_boundary_freezes_and_no_budget_stops(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        source_id = raw["state_events"][12]["source_id"]
        frozen = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=0,
            candidate_independent_source_ids=frozenset({source_id}),
            candidate_reachable_source_ids=frozenset(),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={},
            max_boundaries=64,
            max_events_per_boundary=8,
        )
        self.assertTrue(
            any(
                row.source_id == source_id
                and row.fallback is BoundaryFallback.BASELINE_FROZEN
                for row in frozen.boundaries
            )
        )
        self.assertTrue(frozen.exact_boundary_overflow)
        self.assertFalse(frozen.routing_complete)
        self.assertEqual(frozen.exact_boundary_admitted, 0)
        self.assertTrue(
            any(
                row.source_id != source_id
                and row.fallback is BoundaryFallback.UNSUPPORTED_STOP
                for row in frozen.boundaries
            )
        )

    def test_secret_fields_are_rejected(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset(),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={},
            max_boundaries=64,
            max_events_per_boundary=8,
        )
        malicious = copy.deepcopy(report.to_dict())
        malicious["session_cookie"] = "do-not-export"
        with self.assertRaises(Exception):
            validate_secret_free_diagnostic(malicious)

    def test_fully_supported_executed_formula_creates_no_boundary(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        supported_source_id = raw["source_occurrences"][1]["source_id"]

        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset(),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={},
            max_boundaries=64,
            max_events_per_boundary=8,
        )

        self.assertFalse(
            any(row.source_id == supported_source_id for row in report.boundaries)
        )

    def test_partial_supported_formula_retains_known_value_and_routes_exact(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        changed = copy.deepcopy(raw)
        parameter = changed["source_value_bindings"][1]["parameters"][0]
        parameter.update(
            kind="frozen_runtime_state",
            read_mode="live",
            candidate_dependency_complete=False,
        )
        trace = decode_engine_trace(
            canonical_json(changed),
            request=request,
            source_manifest_binding=binding,
        )
        source_id = changed["source_occurrences"][1]["source_id"]

        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset({source_id}),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={source_id: ("furina:hp%",)},
            max_boundaries=64,
            max_events_per_boundary=8,
        )

        row = next(
            item
            for item in report.boundaries
            if item.source_id == source_id
            and item.reason_code.startswith(
                "frozen_runtime_state_dependency_unresolved:"
            )
        )
        self.assertEqual(row.fallback, BoundaryFallback.KEEP_FOR_EXACT)
        self.assertEqual(
            row.routing_reason,
            "candidate_reachable_exact_required",
        )
        self.assertGreater(row.direct_baseline_damage or 0.0, 0.0)
        self.assertGreater(row.direct_baseline_damage_share or 0.0, 0.0)

    def test_schedule_changing_boundary_requires_exact_lane(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )
        source_id = raw["state_events"][12]["source_id"]

        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset({source_id}),
            topology_changing_source_ids=frozenset({source_id}),
            affected_dimensions_by_source={source_id: ("furina:hp%",)},
            max_boundaries=64,
            max_events_per_boundary=8,
        )

        self.assertTrue(
            any(
                row.source_id == source_id
                and row.topology_may_change
                and row.fallback is BoundaryFallback.KEEP_FOR_EXACT
                and row.routing_reason == "schedule_change_exact_required"
                for row in report.boundaries
            )
        )

    def test_unexecuted_manifest_opaque_entries_are_not_reported(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        locator = SourceLocator(
            "internal/unseen/mechanic.go",
            "unseenMechanic",
            SourceSeam.TASK_CALLBACK,
            0,
        )
        unseen = SourceManifestEntry(
            source_id=locator.source_id,
            locator=locator,
            source_node_sha256=hashlib.sha256(b"unseen-mechanic").hexdigest(),
            template=SourceSliceTemplate.build(
                status=SourceSliceStatus.OPAQUE_FROZEN,
                nodes=(),
                root_node_id=None,
                parameter_keys=(),
                dependencies_complete=False,
                stop_reason_code="unseen_test_boundary",
            ),
        )
        body = replace(
            binding.manifest_body,
            entries=tuple(
                sorted(
                    (*binding.manifest_body.entries, unseen),
                    key=lambda row: row.source_id,
                )
            ),
        )
        expanded_binding = SourceManifestBinding.build(
            manifest_body=body,
            source_tree_sha256=binding.source_tree_sha256,
            engine_tree_sha256=binding.engine_tree_sha256,
            engine_artifact_sha256=binding.engine_artifact_sha256,
            engine_binding_sha256=binding.engine_binding_sha256,
        )
        changed = copy.deepcopy(raw)
        changed["source_manifest_body_sha256"] = body.body_sha256
        trace = decode_engine_trace(
            canonical_json(changed),
            request=request,
            source_manifest_binding=expanded_binding,
        )

        report = build_unknown_mechanic_report(
            trace,
            exact_boundary_budget=64,
            candidate_independent_source_ids=frozenset(),
            candidate_reachable_source_ids=frozenset(),
            topology_changing_source_ids=frozenset(),
            affected_dimensions_by_source={},
            max_boundaries=64,
            max_events_per_boundary=8,
        )

        self.assertFalse(
            any(row.source_id == unseen.source_id for row in report.boundaries)
        )


if __name__ == "__main__":
    unittest.main()
