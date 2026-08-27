from __future__ import annotations

from copy import deepcopy
import unittest

from run_workspace.gcsim.trace_equation import (
    StateEvidenceTrace,
    canonical_json,
    compile_support_replay_plan,
    decode_engine_trace_v6,
    project_support_replay_plan_to_hits,
    project_support_replay_to_hits,
    replay_support_plan,
    replay_support_plan_sliced,
    replay_support_state,
)

from test_state_evidence_v6 import _event_ref, _v6_fixture


class SupportReplayTests(unittest.TestCase):
    def test_empty_delta_is_exact_observed_receipt(self) -> None:
        trace = _trace_with_replayable_write()

        replay = replay_support_state(trace, {})

        self.assertEqual(replay.engine_call_count, 0)
        self.assertFalse(replay.authoritative)
        self.assertFalse(replay.hard_prune_allowed)
        self.assertEqual(replay.changed_event_ids, ())
        self.assertEqual(replay.changed_health_operation_ids, ())
        self.assertEqual(replay.uncertainty_codes, ())
        self.assertEqual(replay.event_value("state-event:6"), 600.0)
        self.assertEqual(replay.state_slot_value("state-slot:0"), 105.0)

    def test_max_hp_delta_replays_health_and_preserves_normalized_feedback(self) -> None:
        trace = _trace_with_replayable_write()

        replay = replay_support_state(trace, {("furina", "hp%"): 0.10})

        self.assertAlmostEqual(replay.event_output("state-event:5")["max_hp"], 13000.0)
        self.assertAlmostEqual(replay.event_value("state-event:6"), 650.0)
        operation = replay.health_operation("health-operation:1")
        self.assertAlmostEqual(operation["event_amount"], 650.0)
        self.assertAlmostEqual(replay.event_value("state-event:13"), 0.05)
        self.assertAlmostEqual(replay.event_value("state-event:14"), 5.0)
        self.assertAlmostEqual(replay.state_slot_value("state-slot:0"), 105.0)
        self.assertIn("state-event:6", replay.changed_event_ids)
        self.assertIn("health-operation:1", replay.changed_health_operation_ids)
        self.assertEqual(replay.uncertainty_codes, ())

    def test_opaque_numeric_boundary_freezes_and_reports(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        raw["state_events"][19].update(
            operation="source_expression",
            inputs=[_event_ref(6)],
            value=105.0,
            candidate_dependency_complete=False,
            uncertainty_codes=["numeric_marker_replay_not_recomputed"],
        )
        raw["state_events"][20]["inputs"] = [_event_ref(19)]
        trace = decode_engine_trace_v6(
            canonical_json(raw), request=request, source_manifest_binding=binding
        )

        replay = replay_support_state(trace, {("furina", "hp%"): 0.10})

        self.assertEqual(replay.event_value("state-event:19"), 105.0)
        self.assertEqual(replay.state_slot_value("state-slot:0"), 105.0)
        self.assertIn(
            "frozen_numeric_source_expression:state-event:19",
            replay.uncertainty_codes,
        )

    def test_stat_reachable_slice_matches_full_replay(self) -> None:
        trace = _trace_with_bound_replayable_modifier()
        plan = compile_support_replay_plan(trace)
        deltas = {("furina", "hp%"): 0.10}

        full = replay_support_plan(plan, deltas)
        sliced = replay_support_plan_sliced(plan, deltas)
        full_projection = project_support_replay_plan_to_hits(plan, full)
        sliced_projection = project_support_replay_plan_to_hits(plan, sliced)

        self.assertEqual(sliced_projection.projections, full_projection.projections)
        self.assertLess(sliced.replayed_event_count, full.replayed_event_count)
        self.assertTrue(
            set(sliced.uncertainty_codes).issubset(full.uncertainty_codes)
        )

    def test_exact_hit_binding_projects_changed_modifier_output(self) -> None:
        request, raw, binding, _ = _v6_fixture()
        raw = deepcopy(raw)
        hit = raw["hits"][0]
        hit["frame"] = 123
        hit["snapshot_frame"] = 122
        stat = hit["stat_contributions"][0]
        stat.update(
            modifier_key="synthetic_empty_stat",
            accepted=False,
            values={},
            provider=raw["state_events"][4]["provider"],
            modifier_eval_event_id="state-event:22",
        )
        attack = hit["attack_mods"][0]
        attack.update(
            modifier_key="synthetic_support_damage",
            accepted=True,
            delta={"dmg%": 600.0},
            modifier_eval_event_id="state-event:23",
        )
        raw["state_events"].append(
            {
                **raw["state_events"][4],
                "sequence_index": 22,
                "event_id": "state-event:22",
                "frame": 122,
                "key": "synthetic_empty_stat",
                "inputs": [],
                "accepted": False,
                "output": {},
            }
        )
        raw["state_events"].append(
            {
                **raw["state_events"][4],
                "sequence_index": 23,
                "event_id": "state-event:23",
                "frame": 123,
                "channel": "attack",
                "key": "synthetic_support_damage",
                "inputs": [_event_ref(6)],
                "output": {"dmg%": 600.0},
            }
        )
        trace = decode_engine_trace_v6(
            canonical_json(raw), request=request, source_manifest_binding=binding
        )

        replay = replay_support_state(trace, {("furina", "hp%"): 0.10})
        projected = project_support_replay_to_hits(trace, replay)
        hit_projection = projected.projection("hit:1")

        self.assertAlmostEqual(hit_projection.stat_delta_map["dmg%"], 50.0)
        self.assertIn("state-event:23", hit_projection.bound_modifier_event_ids)
        self.assertEqual(hit_projection.uncertainty_codes, ())
        self.assertIn("state-event:22", hit_projection.bound_modifier_event_ids)
        self.assertEqual(projected.engine_call_count, 0)


def _trace_with_replayable_write() -> StateEvidenceTrace:
    request, raw, binding, _ = _v6_fixture()
    raw = deepcopy(raw)
    raw["state_events"][20]["inputs"] = [_event_ref(19)]
    return decode_engine_trace_v6(
        canonical_json(raw), request=request, source_manifest_binding=binding
    )


def _trace_with_bound_replayable_modifier() -> StateEvidenceTrace:
    request, raw, binding, _ = _v6_fixture()
    raw = deepcopy(raw)
    hit = raw["hits"][0]
    hit["frame"] = 123
    hit["snapshot_frame"] = 122
    stat = hit["stat_contributions"][0]
    stat.update(
        modifier_key="synthetic_empty_stat",
        accepted=False,
        values={},
        provider=raw["state_events"][4]["provider"],
        modifier_eval_event_id="state-event:22",
    )
    attack = hit["attack_mods"][0]
    attack.update(
        modifier_key="synthetic_support_damage",
        accepted=True,
        delta={"dmg%": 600.0},
        modifier_eval_event_id="state-event:23",
    )
    raw["state_events"].append(
        {
            **raw["state_events"][4],
            "sequence_index": 22,
            "event_id": "state-event:22",
            "frame": 122,
            "key": "synthetic_empty_stat",
            "inputs": [],
            "accepted": False,
            "output": {},
        }
    )
    raw["state_events"].append(
        {
            **raw["state_events"][4],
            "sequence_index": 23,
            "event_id": "state-event:23",
            "frame": 123,
            "channel": "attack",
            "key": "synthetic_support_damage",
            "inputs": [_event_ref(6)],
            "output": {"dmg%": 600.0},
        }
    )
    return decode_engine_trace_v6(
        canonical_json(raw), request=request, source_manifest_binding=binding
    )


if __name__ == "__main__":
    unittest.main()
