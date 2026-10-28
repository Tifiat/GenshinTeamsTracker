from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    artifact_replacements_between,
    canonical_json,
    compile_support_aware_control_objective,
    decode_engine_trace_v6,
    evaluate_rotation_objective,
    evaluate_support_aware_control_objective,
    evaluate_support_aware_sliced_control_objective,
)

try:
    from .test_state_evidence_v6 import _event_ref, _v6_fixture
except ImportError:  # unittest discovery adds this directory directly.
    from test_state_evidence_v6 import _event_ref, _v6_fixture


class SupportAwareControlObjectiveTests(unittest.TestCase):
    def test_incumbent_reconstructs_standard_without_engine(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        objective = compile_support_aware_control_objective(trace, incumbent)

        score = evaluate_support_aware_control_objective(objective, incumbent)

        self.assertAlmostEqual(score.candidate_damage, objective.baseline_damage)
        self.assertAlmostEqual(score.expected_delta, 0.0)
        self.assertEqual(score.support_changed_hit_count, 0)
        self.assertEqual(score.engine_call_count, 0)
        self.assertFalse(score.authoritative)
        self.assertFalse(score.hard_prune_allowed)

    def test_replayed_support_output_reaches_exact_hit_formula(self) -> None:
        trace = _trace_with_hit_binding()
        incumbent = ArtifactStatVector(())
        candidate = ArtifactStatVector.build(
            (ArtifactStatValue("furina", "hp%", 0.10),)
        )
        objective = compile_support_aware_control_objective(trace, incumbent)

        direct_only = evaluate_rotation_objective(
            objective.standard,
            artifact_replacements_between(incumbent, candidate),
        )
        support_aware = evaluate_support_aware_control_objective(
            objective,
            candidate,
        )
        sliced = evaluate_support_aware_sliced_control_objective(
            objective,
            candidate,
        )

        self.assertEqual(support_aware.support_changed_hit_count, 1)
        self.assertGreater(
            support_aware.candidate_damage,
            direct_only.candidate_damage,
        )
        self.assertEqual(support_aware.engine_call_count, 0)
        self.assertFalse(support_aware.authoritative)
        self.assertFalse(support_aware.hard_prune_allowed)
        self.assertAlmostEqual(
            sliced.candidate_damage,
            support_aware.candidate_damage,
        )
        self.assertEqual(
            sliced.candidate_damage_by_actor,
            support_aware.candidate_damage_by_actor,
        )
        self.assertEqual(
            sliced.support_changed_hit_count,
            support_aware.support_changed_hit_count,
        )


def _trace_with_hit_binding(
    *,
    seed: int | None = None,
    modifier_input_event_id: str = "state-event:6",
    opaque_modifier_input: bool = False,
    multiple_providers: bool = False,
    healing_source: bool = False,
):
    request, raw, binding, _ = _v6_fixture()
    raw = deepcopy(raw)
    if seed is not None:
        request = replace(request, seed=seed)
        raw["seed"] = str(seed)
        raw["request_sha256"] = request.request_sha256
    if healing_source:
        heal = raw["health_operations"][1]
        heal.update(
            kind="heal",
            caller_index=0,
            heal_type="absolute",
            external=None,
            input_value=600.0,
            adjusted_input_value=600.0,
            base_amount=600.0,
            source_bonus=0.0,
            heal_bonus_total=0.0,
            raw_amount=600.0,
            event_amount=600.0,
            event_effective_amount=600.0,
            hp_delta_magnitude=600.0,
            overheal=0.0,
            hp_debt_before=0.0,
            hp_debt_after=0.0,
            max_hp_before=12000.0,
            max_hp_after=12000.0,
            hp_before=5400.0,
            hp_after=6000.0,
            hp_ratio_before=0.45,
            hp_ratio_after=0.5,
            modifier_contributions=[],
            candidate_dependency_complete=True,
            uncertainty_codes=[],
        )
    if multiple_providers:
        request = replace(request, character_keys=("furina", "bennett"))
        raw["character_keys"] = ["furina", "bennett"]
        raw["request_sha256"] = request.request_sha256
    hit = raw["hits"][0]
    hit["frame"] = 124 if multiple_providers else 123
    hit["snapshot_frame"] = 123 if multiple_providers else 122
    stat = hit["stat_contributions"][0]
    attack = hit["attack_mods"][0]
    if multiple_providers:
        bennett_provider = {
            **raw["state_events"][5]["provider"],
            "key": "bennett",
            "owner_index": 1,
        }
        raw["state_events"].extend(
            (
                {
                    **raw["state_events"][5],
                    "sequence_index": 22,
                    "event_id": "state-event:22",
                    "frame": 122,
                    "provider": bennett_provider,
                    "owner_index": 1,
                    "modifier_eval_ids": [],
                    "output": {
                        "base_hp": 10000.0,
                        "hp%": 0.0,
                        "hp": 0.0,
                        "max_hp": 10000.0,
                    },
                },
                {
                    **raw["state_events"][6],
                    "sequence_index": 23,
                    "event_id": "state-event:23",
                    "frame": 122,
                    "provider": bennett_provider,
                    "inputs": [
                        {
                            **_event_ref(22),
                            "field_key": "max_hp",
                        },
                        {
                            "kind": "literal",
                            "event_id": None,
                            "health_operation_id": None,
                            "field_key": None,
                            "literal_value": 0.01,
                        },
                    ],
                    "value": 100.0,
                },
                {
                    **raw["state_events"][19],
                    "sequence_index": 24,
                    "event_id": "state-event:24",
                    "frame": 122,
                    "parent_event_id": None,
                    "provider": raw["state_events"][6]["provider"],
                    "operation": "add",
                    "inputs": [_event_ref(6), _event_ref(23)],
                    "value": 700.0,
                    "candidate_dependency_complete": True,
                    "uncertainty_codes": [],
                },
                {
                    **raw["state_events"][4],
                    "sequence_index": 25,
                    "event_id": "state-event:25",
                    "frame": 123,
                    "provider": raw["state_events"][4]["provider"],
                    "key": "synthetic_empty_stat",
                    "inputs": [],
                    "accepted": False,
                    "output": {},
                },
                {
                    **raw["state_events"][4],
                    "sequence_index": 26,
                    "event_id": "state-event:26",
                    "frame": 124,
                    "provider": bennett_provider,
                    "channel": "attack",
                    "key": "synthetic_support_damage",
                    "inputs": [_event_ref(24)],
                    "output": {"dmg%": 700.0},
                },
            )
        )
        stat.update(
            modifier_key="synthetic_empty_stat",
            accepted=False,
            values={},
            provider=raw["state_events"][4]["provider"],
            modifier_eval_event_id="state-event:25",
        )
        attack.update(
            modifier_key="synthetic_support_damage",
            accepted=True,
            delta={"dmg%": 700.0},
            provider=bennett_provider,
            modifier_eval_event_id="state-event:26",
        )
    else:
        stat.update(
            modifier_key="synthetic_empty_stat",
            accepted=False,
            values={},
            provider=raw["state_events"][4]["provider"],
            modifier_eval_event_id="state-event:22",
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
        if opaque_modifier_input:
            raw["state_events"][19].update(
                operation="source_expression",
                inputs=[_event_ref(6)],
                candidate_dependency_complete=False,
                uncertainty_codes=["numeric_marker_replay_not_recomputed"],
            )
        input_event = next(
            row
            for row in raw["state_events"]
            if row["event_id"] == modifier_input_event_id
        )
        modifier_value = float(input_event["value"])
        input_complete = bool(input_event["candidate_dependency_complete"])
        raw["state_events"].append(
            {
                **raw["state_events"][4],
                "sequence_index": 23,
                "event_id": "state-event:23",
                "frame": 123,
                "channel": "attack",
                "key": "synthetic_support_damage",
                "inputs": [
                    _event_ref(int(modifier_input_event_id.split(":")[1]))
                ],
                "output": {"dmg%": modifier_value},
                "candidate_dependency_complete": (
                    input_complete and not opaque_modifier_input
                ),
                "uncertainty_codes": (
                    ["modifier_input_dependency_incomplete"]
                    if opaque_modifier_input or not input_complete
                    else []
                ),
            }
        )
        attack.update(
            modifier_key="synthetic_support_damage",
            accepted=True,
            delta={"dmg%": modifier_value},
            modifier_eval_event_id="state-event:23",
        )
    return decode_engine_trace_v6(
        canonical_json(raw),
        request=request,
        source_manifest_binding=binding,
    )


if __name__ == "__main__":
    unittest.main()
