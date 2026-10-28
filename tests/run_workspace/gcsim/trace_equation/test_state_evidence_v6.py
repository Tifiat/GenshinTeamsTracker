from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    ENGINE_TRACE_V6_CAPABILITY,
    ENGINE_TRACE_V6_SCHEMA_VERSION,
    SOURCE_STATE_COMPILER_VERSION,
    SOURCE_STATE_IR_FORMULA_ID,
    SOURCE_STATE_IR_FORMULA_SHA256,
    SourceManifestBinding,
    StateEvidenceTrace,
    TraceContractError,
    canonical_json,
    decode_engine_trace,
    decode_engine_trace_v6,
    score_observed_artifact_replacement,
)

from .test_health_evidence_v5 import _v5_fixture
from .test_source_dependencies_v4 import _provider


class StateEvidenceV6Tests(unittest.TestCase):
    def test_synthetic_feedback_loop_decodes_and_keeps_all_authority_false(self) -> None:
        request, raw, binding, _ = _v6_fixture()

        trace = _decode(request, raw, binding)
        dispatched = decode_engine_trace(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

        self.assertIsInstance(trace, StateEvidenceTrace)
        self.assertEqual(trace, dispatched)
        self.assertEqual(len(trace.state_slots), 1)
        self.assertEqual(len(trace.state_events), 22)
        self.assertFalse(trace.exact_replay_eligible)
        self.assertFalse(trace.hard_prune_allowed)
        self.assertFalse(trace.publishable)
        self.assertEqual(trace.state_events[5].output_map["max_hp"], 12000.0)
        self.assertEqual(trace.state_events[6].value, 600.0)
        self.assertEqual(trace.state_events[-2].after, 105.0)

    def test_v6_trace_feeds_zero_engine_observed_snapshot_score(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = _decode(request, raw, binding)
        actor_key = trace.terminal_trace.request.character_keys[0]

        score = score_observed_artifact_replacement(
            trace,
            (
                ArtifactStatReplacement(
                    actor_key,
                    "cr",
                    baseline_artifact_value=0.20,
                    candidate_artifact_value=0.25,
                ),
            ),
        )

        self.assertEqual(score.evidence_sha256, trace.evidence_sha256)
        self.assertEqual(score.engine_call_count, 0)
        self.assertFalse(score.authoritative)
        self.assertEqual(score.duration_frames, trace.duration_frames)
        self.assertIsNotNone(score.baseline_expected_dps)
        self.assertIsNotNone(score.candidate_expected_dps)
        self.assertTrue(score.grouping_preserves_scores)
        self.assertEqual(len(score.ranking.hits), len(trace.terminal_trace.hits))

    def test_v6_ranking_replays_supported_source_flat_damage(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        trace = _decode(request, raw, binding)

        score = score_observed_artifact_replacement(
            trace,
            (
                ArtifactStatReplacement(
                    "furina",
                    "hp%",
                    baseline_artifact_value=0.0,
                    candidate_artifact_value=0.0496,
                ),
            ),
        )

        hit = score.ranking.hits[0]
        self.assertGreater(hit.candidate_score, hit.baseline_score)
        self.assertNotIn(
            "flat_damage_dependency_unresolved",
            hit.uncertainty_codes,
        )

    def test_v6_top_level_and_external_manifest_pair_are_exact(self) -> None:
        request, raw, binding, binding_v5 = _v6_fixture()
        self.assertEqual(
            set(raw),
            _v5_top_level_keys(raw) | {"state_slots", "state_events"},
        )

        missing = deepcopy(raw)
        missing.pop("state_events")
        with self.assertRaisesRegex(TraceContractError, "missing"):
            _decode(request, missing, binding)

        unknown = deepcopy(raw)
        unknown["state_event_count"] = 22
        with self.assertRaisesRegex(TraceContractError, "unknown"):
            _decode(request, unknown, binding)

        with self.assertRaisesRegex(TraceContractError, "6/v6"):
            _decode(request, raw, binding_v5)
        with self.assertRaisesRegex(TraceContractError, "external source manifest"):
            decode_engine_trace(canonical_json(raw), request=request)

    def test_exact_union_shapes_and_reference_kinds_fail_closed(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        mutations = (
            lambda changed: changed["state_events"][3].pop("inputs"),
            lambda changed: changed["state_events"][3].__setitem__(
                "input_event_ids", []
            ),
            lambda changed: changed["state_events"][3]["inputs"][0].__setitem__(
                "literal_value", 100.0
            ),
            lambda changed: changed["state_events"][6]["inputs"][0].__setitem__(
                "field_key", "missing"
            ),
            lambda changed: changed["state_events"][18]["numeric_payload"][0].pop(
                "reference"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate):
                with self.assertRaises(TraceContractError):
                    _decode(request, changed, binding)

    def test_contiguous_ids_backward_refs_and_slot_ledger_are_strict(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        mutations = (
            lambda changed: changed["state_events"][2].__setitem__(
                "event_id", "state-event:99"
            ),
            lambda changed: changed["state_events"][3]["inputs"][0].__setitem__(
                "event_id", "state-event:20"
            ),
            lambda changed: changed["state_events"][20].__setitem__("before", 99.0),
            lambda changed: changed["state_slots"][0].__setitem__(
                "registration_event_id", "state-event:1"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate):
                with self.assertRaises(TraceContractError):
                    _decode(request, changed, binding)

    def test_arithmetic_max_hp_and_health_bindings_recompute(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        mutations = (
            lambda changed: changed["state_events"][3].__setitem__("value", 0.3),
            lambda changed: changed["state_events"][5]["output"].__setitem__(
                "max_hp", 11999.0
            ),
            lambda changed: changed["state_events"][7].__setitem__("value", 601.0),
            lambda changed: changed["state_events"][7].__setitem__(
                "bound_event_id", "state-event:5"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate):
                with self.assertRaises(TraceContractError):
                    _decode(request, changed, binding)

    def test_task_pairing_payload_and_queue_order_are_strict(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        mutations = (
            lambda changed: changed["state_events"][18].__setitem__(
                "queue_sequence", 1
            ),
            lambda changed: changed["state_events"][18]["numeric_payload"][0].__setitem__(
                "value", 6.0
            ),
            lambda changed: changed["state_events"][21].__setitem__(
                "parent_event_id", "state-event:17"
            ),
            lambda changed: changed["state_events"][21].__setitem__(
                "task_id", "task:2"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate):
                with self.assertRaises(TraceContractError):
                    _decode(request, changed, binding)

    def test_completeness_uncertainty_provider_and_source_are_strict(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        mutations = (
            lambda changed: changed["state_events"][3].__setitem__(
                "uncertainty_codes", ["z", "a"]
            ),
            lambda changed: changed["state_events"][3].__setitem__(
                "candidate_dependency_complete", False
            ),
            lambda changed: changed["state_events"][3].__setitem__(
                "authoritative", True
            ),
            lambda changed: changed["state_events"][3].__setitem__(
                "source_id", "0" * 64
            ),
            lambda changed: changed["state_events"][3]["provider"].__setitem__(
                "key", "not-furina"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate):
                with self.assertRaises(TraceContractError):
                    _decode(request, changed, binding)

    def test_numeric_operator_property_table_recomputes(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        cases = (
            ("add", [2.0, 3.0, 4.0], 9.0),
            ("subtract", [7.0, 2.0], 5.0),
            ("multiply", [2.0, 3.0, 4.0], 24.0),
            ("divide", [9.0, 3.0], 3.0),
            ("min", [5.0, -2.0, 7.0], -2.0),
            ("max", [5.0, -2.0, 7.0], 7.0),
            ("negate", [5.0], -5.0),
            ("identity", [5.0], 5.0),
        )
        for operation, values, expected in cases:
            changed = deepcopy(raw)
            event = changed["state_events"][3]
            event["operation"] = operation
            event["inputs"] = [_literal(value) for value in values]
            event["value"] = expected
            with self.subTest(operation=operation):
                self.assertIsInstance(_decode(request, changed, binding), StateEvidenceTrace)
                event["value"] = expected + 0.5
                with self.assertRaisesRegex(TraceContractError, "recompute"):
                    _decode(request, changed, binding)

    def test_state_transition_is_an_incomplete_frozen_marker(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        event = raw["state_events"][19]
        event["operation"] = "state_transition"
        event["value"] = 999.0
        event["candidate_dependency_complete"] = False
        event["uncertainty_codes"] = ["numeric_marker_replay_not_recomputed"]

        self.assertIsInstance(_decode(request, raw, binding), StateEvidenceTrace)

        event["candidate_dependency_complete"] = True
        event["uncertainty_codes"] = []
        with self.assertRaisesRegex(TraceContractError, "marker"):
            _decode(request, raw, binding)

    def test_incomplete_source_event_may_omit_unbound_template_parameters(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        entry = next(
            row
            for row in binding.manifest_body.entries
            if row.template.parameter_keys
        )
        event = raw["state_events"][19]
        event.update(
            source_id=entry.source_id,
            template_sha256=entry.template.template_sha256,
            parameters=[],
            operation="state_transition",
            candidate_dependency_complete=False,
            uncertainty_codes=[
                "numeric_marker_replay_not_recomputed",
                "source_parameter_binding_incomplete",
            ],
        )

        self.assertIsInstance(_decode(request, raw, binding), StateEvidenceTrace)

        event["candidate_dependency_complete"] = True
        event["uncertainty_codes"] = []
        with self.assertRaisesRegex(TraceContractError, "parameters do not match"):
            _decode(request, raw, binding)

    def test_observed_guard_is_an_incomplete_frozen_boundary(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        event = raw["state_events"][19]
        event.update(
            kind="guard_eval",
            operation="observed",
            inputs=[],
            value=None,
            result=True,
            before=None,
            after=None,
            candidate_dependency_complete=False,
            uncertainty_codes=["guard_operand_dependency_incomplete"],
        )

        self.assertIsInstance(_decode(request, raw, binding), StateEvidenceTrace)

        event["candidate_dependency_complete"] = True
        event["uncertainty_codes"] = []
        with self.assertRaisesRegex(TraceContractError, "opaque boundary"):
            _decode(request, raw, binding)

    def test_state_resync_is_explicit_and_incomplete(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        event = raw["state_events"][19]
        event.update(
            kind="state_resync",
            slot_id="state-slot:0",
            operation=None,
            inputs=[],
            value=None,
            before=100.0,
            after=105.0,
            candidate_dependency_complete=False,
            uncertainty_codes=["state_slot_unobserved_mutation"],
        )
        raw["state_events"][20]["before"] = 105.0

        self.assertIsInstance(_decode(request, raw, binding), StateEvidenceTrace)

        event["before"] = 99.0
        with self.assertRaisesRegex(TraceContractError, "resync"):
            _decode(request, raw, binding)


def _decode(request, raw, binding):
    return decode_engine_trace_v6(
        canonical_json(raw),
        request=request,
        source_manifest_binding=binding,
    )


def _v5_top_level_keys(raw):
    return set(raw) - {"state_slots", "state_events"}


def _v6_fixture():
    request, raw_v5, binding_v5, _, _, ids = _v5_fixture()
    body_v5 = binding_v5.manifest_body
    formulas = tuple(
        replace(
            row,
            id=SOURCE_STATE_IR_FORMULA_ID,
            sha256=SOURCE_STATE_IR_FORMULA_SHA256,
        )
        if row.id == "gtt_source_ir_v1"
        else row
        for row in body_v5.formula_identities
    )
    body_v6 = replace(
        body_v5,
        compiler_version=SOURCE_STATE_COMPILER_VERSION,
        trace_schema_version=ENGINE_TRACE_V6_SCHEMA_VERSION,
        trace_capability=ENGINE_TRACE_V6_CAPABILITY,
        formula_identities=formulas,
    )
    binding_v6 = SourceManifestBinding.build(
        manifest_body=body_v6,
        source_tree_sha256=body_v6.pristine_source_tree_sha256,
        engine_tree_sha256=binding_v5.engine_tree_sha256,
        engine_artifact_sha256=request.engine_artifact_sha256,
        engine_binding_sha256=request.engine_binding_sha256,
    )
    raw = deepcopy(raw_v5)
    raw["schema_version"] = ENGINE_TRACE_V6_SCHEMA_VERSION
    raw["capability"] = ENGINE_TRACE_V6_CAPABILITY
    raw["source_manifest_body_sha256"] = binding_v6.manifest_body_sha256

    drain = raw["health_operations"][1]
    drain.update(
        {
            "input_value": 600.0,
            "adjusted_input_value": 600.0,
            "raw_amount": 600.0,
            "event_amount": 600.0,
            "event_effective_amount": 600.0,
            "hp_delta_magnitude": 600.0,
            "max_hp_before": 12000.0,
            "max_hp_after": 12000.0,
            "hp_before": 6000.0,
            "hp_after": 5400.0,
            "hp_ratio_before": 0.5,
            "hp_ratio_after": 0.45,
            "candidate_dependency_complete": True,
            "uncertainty_codes": [],
        }
    )

    character = _provider("character", "furina", 0)
    raw["state_slots"] = [
        {
            "sequence_index": 0,
            "slot_id": "state-slot:0",
            "scope": "character_state",
            "provider": character,
            "slot_key": "synthetic_meter",
            "initial_value": 0.0,
            "registration_event_id": "state-event:0",
            "candidate_dependency_complete": True,
            "uncertainty_codes": [],
            "authoritative": False,
        }
    ]
    source_id = ids["furina"]
    events = [
        _event(0, 100, "state_slot_register", character, slot_id="state-slot:0", key="synthetic_meter", value=0.0),
        _event(1, 100, "state_write", character, source_id=source_id, slot_id="state-slot:0", before=0.0, after=100.0),
        _event(2, 101, "state_read", character, source_id=source_id, slot_id="state-slot:0", value=100.0),
        _event(3, 101, "numeric_eval", character, source_id=source_id, operation="multiply", inputs=[_event_ref(2), _literal(0.002)], value=0.2),
        _event(4, 101, "modifier_eval", character, source_id=source_id, channel="stat", key="synthetic_hp_feedback", inputs=[_event_ref(3)], expiry_frame=-1, owner_index=0, accepted=True, output={"hp%": 0.2}),
        _event(5, 101, "max_hp_read", character, modifier_eval_ids=["state-event:4"], owner_index=0, output={"base_hp": 10000.0, "hp%": 0.2, "hp": 0.0, "max_hp": 12000.0}),
        _event(6, 120, "numeric_eval", character, source_id=source_id, operation="multiply", inputs=[_event_output_ref(5, "max_hp"), _literal(0.05)], value=600.0),
        _event(7, 121, "health_field_binding", character, health_operation_id="health-operation:1", key="input_value", value=600.0, bound_event_id="state-event:6"),
        _event(8, 121, "health_field_binding", character, health_operation_id="health-operation:1", key="max_hp_before", value=12000.0, bound_event_id="state-event:5"),
        _event(9, 121, "health_field_binding", character, health_operation_id="health-operation:1", key="max_hp_after", value=12000.0, bound_event_id="state-event:5"),
        _event(10, 121, "health_context_enter", character, health_operation_id="health-operation:1", call_id="state-event:10"),
        _event(11, 121, "event_callback_enter", character, source_id=source_id, parent_event_id="state-event:10", health_operation_id="health-operation:1", call_id="state-event:11", channel="OnPlayerHPDrain", key="synthetic_hook"),
        _event(12, 121, "numeric_eval", character, source_id=source_id, parent_event_id="state-event:11", health_operation_id="health-operation:1", operation="health_input", inputs=[_health_ref(1, "event_amount")], value=600.0, candidate_dependency_complete=False, uncertainty_codes=["numeric_marker_replay_not_recomputed"]),
        _event(13, 121, "numeric_eval", character, source_id=source_id, parent_event_id="state-event:11", health_operation_id="health-operation:1", operation="divide", inputs=[_event_ref(12), _event_output_ref(5, "max_hp")], value=0.05, candidate_dependency_complete=False, uncertainty_codes=["numeric_input_dependency_incomplete"]),
        _event(14, 121, "numeric_eval", character, source_id=source_id, parent_event_id="state-event:11", health_operation_id="health-operation:1", operation="multiply", inputs=[_event_ref(13), _literal(100.0)], value=5.0, candidate_dependency_complete=False, uncertainty_codes=["numeric_input_dependency_incomplete"]),
        _event(15, 121, "task_enqueue", character, source_id=source_id, parent_event_id="state-event:11", health_operation_id="health-operation:1", task_id="task:1", queue_id="task-queue:1", queue_sequence=0, enqueue_frame=121, delay_frames=1, execute_by_frame=122, numeric_payload=[_payload("amount", 5.0, _event_ref(14))], candidate_dependency_complete=False, uncertainty_codes=["task_payload_dependency_incomplete"]),
        _event(16, 121, "event_callback_exit", character, source_id=source_id, parent_event_id="state-event:11", health_operation_id="health-operation:1", call_id="state-event:11", channel="OnPlayerHPDrain", key="synthetic_hook"),
        _event(17, 121, "health_context_exit", character, parent_event_id="state-event:10", health_operation_id="health-operation:1", call_id="state-event:10"),
        _event(18, 122, "task_execute_enter", character, source_id=source_id, task_id="task:1", call_id="state-event:18", queue_id="task-queue:1", queue_sequence=0, enqueue_frame=121, delay_frames=1, execute_by_frame=122, value=122.0, numeric_payload=[_payload("amount", 5.0, _event_ref(14))], candidate_dependency_complete=False, uncertainty_codes=["task_payload_dependency_incomplete"]),
        _event(19, 122, "numeric_eval", character, source_id=source_id, parent_event_id="state-event:18", operation="add", inputs=[_event_ref(2), _event_ref(14)], value=105.0, candidate_dependency_complete=False, uncertainty_codes=["numeric_input_dependency_incomplete"]),
        _event(20, 122, "state_write", character, source_id=source_id, parent_event_id="state-event:18", slot_id="state-slot:0", before=100.0, after=105.0, candidate_dependency_complete=False, uncertainty_codes=["state_write_dependency_incomplete"]),
        _event(21, 122, "task_execute_exit", character, source_id=source_id, parent_event_id="state-event:18", task_id="task:1", call_id="state-event:18", queue_id="task-queue:1", queue_sequence=0, enqueue_frame=121, delay_frames=1, execute_by_frame=122, value=122.0, numeric_payload=[_payload("amount", 5.0, _event_ref(14))], candidate_dependency_complete=False, uncertainty_codes=["task_payload_dependency_incomplete"]),
    ]
    raw["state_events"] = events
    return request, raw, binding_v6, binding_v5


def _event(index, frame, kind, provider, **updates):
    row = {
        "sequence_index": index,
        "event_id": f"state-event:{index}",
        "frame": frame,
        "kind": kind,
        "source_id": None,
        "source_occurrence_id": None,
        "provider": provider,
        "parent_event_id": None,
        "health_operation_id": None,
        "task_id": None,
        "call_id": None,
        "slot_id": None,
        "channel": None,
        "key": None,
        "operation": None,
        "inputs": [],
        "modifier_eval_ids": [],
        "template_sha256": None,
        "parameters": [],
        "before": None,
        "value": None,
        "after": None,
        "result": None,
        "accepted": None,
        "numeric_payload": [],
        "enqueue_frame": None,
        "delay_frames": None,
        "execute_by_frame": None,
        "queue_id": None,
        "queue_sequence": None,
        "expiry_frame": None,
        "owner_index": None,
        "target_index": None,
        "output": {},
        "bound_event_id": None,
        "candidate_dependency_complete": True,
        "uncertainty_codes": [],
        "authoritative": False,
    }
    row.update(updates)
    return row


def _event_ref(index):
    return {
        "kind": "event",
        "event_id": f"state-event:{index}",
        "health_operation_id": None,
        "field_key": None,
        "literal_value": None,
    }


def _event_output_ref(index, key):
    row = _event_ref(index)
    row["field_key"] = key
    return row


def _literal(value):
    return {
        "kind": "literal",
        "event_id": None,
        "health_operation_id": None,
        "field_key": None,
        "literal_value": value,
    }


def _health_ref(index, field):
    return {
        "kind": "health_field",
        "event_id": None,
        "health_operation_id": f"health-operation:{index}",
        "field_key": field,
        "literal_value": None,
    }


def _payload(key, value, reference):
    return {"key": key, "value": value, "reference": reference}


if __name__ == "__main__":
    unittest.main()
