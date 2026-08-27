from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
import unittest

from run_workspace.gcsim.trace_equation import (
    ENGINE_TRACE_V4_CAPABILITY,
    ENGINE_TRACE_V5_CAPABILITY,
    ENGINE_TRACE_V5_SCHEMA_VERSION,
    HealthEvidenceTrace,
    SourceDependencyEvidenceTrace,
    SourceManifestBinding,
    TraceContractError,
    canonical_json,
    decode_engine_trace,
    decode_engine_trace_v4,
    decode_engine_trace_v5,
    decode_health_operations,
)

from test_source_dependencies_v4 import _fixture, _provider


class HealthEvidenceV5Tests(unittest.TestCase):
    def test_v5_is_additive_and_preserves_v4_evidence_collections(self) -> None:
        request, raw_v5, binding_v5, raw_v4, binding_v4, _ = _v5_fixture()

        self.assertEqual(set(raw_v5), set(raw_v4) | {"health_operations"})
        v4 = decode_engine_trace_v4(
            canonical_json(raw_v4),
            request=request,
            source_manifest_binding=binding_v4,
        )
        v5 = decode_engine_trace_v5(
            canonical_json(raw_v5),
            request=request,
            source_manifest_binding=binding_v5,
        )
        dispatched = decode_engine_trace(
            canonical_json(raw_v5),
            request=request,
            source_manifest_binding=binding_v5,
        )

        self.assertIsInstance(v5, HealthEvidenceTrace)
        self.assertEqual(v5, dispatched)
        self.assertEqual(v5.reaction_evidence, v4.reaction_evidence)
        self.assertEqual(v5.occurrences, v4.occurrences)
        self.assertEqual(v5.value_bindings, v4.value_bindings)
        self.assertNotEqual(
            v5.source_manifest_binding.manifest_body_sha256,
            v4.source_manifest_binding.manifest_body_sha256,
        )
        self.assertFalse(v5.exact_replay_eligible)
        self.assertFalse(v5.hard_prune_allowed)
        self.assertFalse(v5.publishable)
        self.assertEqual(len(v5.health_operations), 2)

        # A drain receipt can legitimately have an event amount different from
        # the observed HP delta, and absolute HP direction is not authoritative
        # across mid-operation MaxHP/state callbacks.
        drain = v5.health_operations[1]
        self.assertEqual(drain.event_effective_amount, 750.0)
        self.assertEqual(drain.hp_delta_magnitude, 500.0)
        self.assertGreater(drain.hp_after, drain.hp_before)

    def test_v4_and_v5_manifest_pairs_remain_strictly_separate(self) -> None:
        request, raw_v5, binding_v5, raw_v4, binding_v4, _ = _v5_fixture()

        with self.assertRaisesRegex(TraceContractError, "4/v4"):
            decode_engine_trace_v4(
                canonical_json(raw_v4),
                request=request,
                source_manifest_binding=binding_v5,
            )
        with self.assertRaisesRegex(TraceContractError, "5/v5"):
            decode_engine_trace_v5(
                canonical_json(raw_v5),
                request=request,
                source_manifest_binding=binding_v4,
            )

        v4 = decode_engine_trace_v4(
            canonical_json(raw_v4),
            request=request,
            source_manifest_binding=binding_v4,
        )
        v5 = decode_engine_trace_v5(
            canonical_json(raw_v5),
            request=request,
            source_manifest_binding=binding_v5,
        )
        self.assertIsInstance(v4, SourceDependencyEvidenceTrace)
        with self.assertRaisesRegex(TraceContractError, "4/v4"):
            replace(v4, source_manifest_binding=binding_v5)
        with self.assertRaisesRegex(TraceContractError, "5/v5"):
            replace(v5, source_manifest_binding=binding_v4)

        with self.assertRaisesRegex(TraceContractError, "trace_capability"):
            replace(
                binding_v4.manifest_body,
                trace_schema_version=5,
                trace_capability=ENGINE_TRACE_V4_CAPABILITY,
            )
        with self.assertRaisesRegex(TraceContractError, "trace_capability"):
            replace(
                binding_v4.manifest_body,
                trace_schema_version=4,
                trace_capability=ENGINE_TRACE_V5_CAPABILITY,
            )

    def test_health_wire_shape_and_kind_nullability_are_fail_closed(self) -> None:
        request, raw, binding, _, _, _ = _v5_fixture()

        mutations = (
            (
                "missing row key",
                lambda changed: changed["health_operations"][0].pop(
                    "hp_delta_magnitude"
                ),
                "missing",
            ),
            (
                "unknown old effective key",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "effective_amount", 1000.0
                ),
                "unknown",
            ),
            (
                "heal external",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "external", False
                ),
                "requires heal_type and null external",
            ),
            (
                "heal type null",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "heal_type", None
                ),
                "requires heal_type",
            ),
            (
                "heal type numeric",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "heal_type", 1
                ),
                "must be a string",
            ),
            (
                "drain external null",
                lambda changed: changed["health_operations"][1].__setitem__(
                    "external", None
                ),
                "boolean external",
            ),
            (
                "drain heal type",
                lambda changed: changed["health_operations"][1].__setitem__(
                    "heal_type", "absolute"
                ),
                "null heal_type",
            ),
            (
                "drain heal-only value",
                lambda changed: changed["health_operations"][1].__setitem__(
                    "overheal", 0.0
                ),
                "null heal-only",
            ),
        )
        for label, mutate, expected in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(label=label):
                with self.assertRaisesRegex(TraceContractError, expected):
                    _decode(request, changed, binding)

    def test_health_arithmetic_and_base_formulas_are_explicit(self) -> None:
        request, raw, binding, _, _, _ = _v5_fixture()

        percent = deepcopy(raw)
        heal = percent["health_operations"][0]
        heal["heal_type"] = "percent"
        heal["input_value"] = 0.1
        heal["adjusted_input_value"] = 0.1
        self.assertIsInstance(_decode(request, percent, binding), HealthEvidenceTrace)

        mutations = (
            (
                "heal event effective",
                0,
                "event_effective_amount",
                999.0,
                r"max\(event-overheal",
            ),
            (
                "drain event effective",
                1,
                "event_effective_amount",
                749.0,
                "equal event_amount",
            ),
            (
                "hp delta",
                1,
                "hp_delta_magnitude",
                750.0,
                "observed HP delta",
            ),
            (
                "heal bonus sum",
                0,
                "heal_bonus_total",
                0.3,
                "contribution sum",
            ),
            (
                "raw heal amount",
                0,
                "raw_amount",
                1299.0,
                "base and bonus",
            ),
            (
                "absolute base",
                0,
                "base_amount",
                999.0,
                "heal_type input formula",
            ),
            (
                "ratio",
                0,
                "hp_ratio_after",
                0.7,
                "HP/MaxHP",
            ),
            (
                "nonnegative debt",
                0,
                "hp_debt_after",
                -1.0,
                "non-negative",
            ),
            (
                "positive max hp",
                0,
                "max_hp_after",
                0.0,
                "positive",
            ),
        )
        for label, index, key, value, expected in mutations:
            changed = deepcopy(raw)
            changed["health_operations"][index][key] = value
            with self.subTest(label=label):
                with self.assertRaisesRegex(TraceContractError, expected):
                    _decode(request, changed, binding)

        bad_percent = deepcopy(percent)
        bad_percent["health_operations"][0]["base_amount"] = 999.0
        with self.assertRaisesRegex(TraceContractError, "heal_type input formula"):
            _decode(request, bad_percent, binding)

        nonfinite = deepcopy(raw["health_operations"])
        nonfinite[0]["raw_amount"] = math.nan
        with self.assertRaisesRegex(TraceContractError, "finite"):
            decode_health_operations(nonfinite, "$.health_operations")

    def test_health_relations_time_and_completeness_are_fail_closed(self) -> None:
        request, raw, binding, _, _, ids = _v5_fixture()

        source_occurrence_optional = deepcopy(raw)
        source_occurrence_optional["health_operations"][0][
            "modifier_contributions"
        ][0]["source_occurrence_id"] = None
        self.assertIsInstance(
            _decode(request, source_occurrence_optional, binding),
            HealthEvidenceTrace,
        )

        # Heal HP direction is also not an invariant across nested callbacks.
        heal_direction = deepcopy(raw)
        heal_direction["health_operations"][0].update(
            hp_after=4000.0,
            hp_ratio_after=0.4,
            hp_delta_magnitude=1000.0,
        )
        self.assertIsInstance(
            _decode(request, heal_direction, binding), HealthEvidenceTrace
        )

        mutations = (
            (
                "operation id",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "operation_id", "health-operation:9"
                ),
                "operation_id",
            ),
            (
                "contribution id",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__(
                    "contribution_id", "health-operation:0:modifier:1"
                ),
                "contiguous and relational",
            ),
            (
                "unknown parent",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "parent_occurrence_id", "source-occurrence:99"
                ),
                "unknown V4 occurrence",
            ),
            (
                "unknown contribution occurrence",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__(
                    "source_occurrence_id", "source-occurrence:99"
                ),
                "unknown V4 occurrence",
            ),
            (
                "source id mismatch",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__("source_id", ids["hp"]),
                "source occurrence/source_id mismatch",
            ),
            (
                "provider mismatch",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__("provider", _provider("character", "wrong", 0)),
                "owner binding mismatch",
            ),
            (
                "expired contribution",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__("expiry_frame", 120),
                "expiry",
            ),
            (
                "frame order",
                lambda changed: changed["health_operations"][1].__setitem__(
                    "frame", 119
                ),
                "nondecreasing",
            ),
            (
                "later parent",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "parent_occurrence_id", "source-occurrence:3"
                ),
                "parent occurrence cannot be later",
            ),
            (
                "later modifier source",
                _make_modifier_source_later,
                "source occurrence cannot be later",
            ),
            (
                "complete with uncertainty",
                lambda changed: changed["health_operations"][0].__setitem__(
                    "uncertainty_codes", ["unexpected_state"]
                ),
                "complete health dependency",
            ),
            (
                "complete with incomplete contribution",
                lambda changed: changed["health_operations"][0][
                    "modifier_contributions"
                ][0].__setitem__("candidate_dependency_complete", False),
                "complete health dependency",
            ),
            (
                "incomplete without uncertainty",
                lambda changed: changed["health_operations"][1].__setitem__(
                    "uncertainty_codes", []
                ),
                "requires an uncertainty code",
            ),
        )
        for label, mutate, expected in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(label=label):
                with self.assertRaisesRegex(TraceContractError, expected):
                    _decode(request, changed, binding)

    def test_top_level_v5_contract_is_exact_and_externally_bound(self) -> None:
        request, raw, binding, _, _, _ = _v5_fixture()

        missing = deepcopy(raw)
        del missing["health_operations"]
        with self.assertRaisesRegex(TraceContractError, "missing"):
            _decode(request, missing, binding)

        unknown = deepcopy(raw)
        unknown["health_operation_count"] = 2
        with self.assertRaisesRegex(TraceContractError, "unknown"):
            _decode(request, unknown, binding)

        wrong_hash = deepcopy(raw)
        wrong_hash["source_manifest_body_sha256"] = "0" * 64
        with self.assertRaisesRegex(TraceContractError, "does not match"):
            _decode(request, wrong_hash, binding)

        with self.assertRaisesRegex(TraceContractError, "external source manifest"):
            decode_engine_trace(canonical_json(raw), request=request)


def _decode(request, raw, binding):
    return decode_engine_trace_v5(
        canonical_json(raw),
        request=request,
        source_manifest_binding=binding,
    )


def _make_modifier_source_later(changed) -> None:
    changed["health_operations"][0]["parent_occurrence_id"] = None
    changed["source_occurrences"][2]["frame"] = 121


def _v5_fixture():
    request, raw_v4, binding_v4, ids = _fixture()
    body_v5 = replace(
        binding_v4.manifest_body,
        trace_schema_version=ENGINE_TRACE_V5_SCHEMA_VERSION,
        trace_capability=ENGINE_TRACE_V5_CAPABILITY,
    )
    binding_v5 = SourceManifestBinding.build(
        manifest_body=body_v5,
        source_tree_sha256=body_v5.pristine_source_tree_sha256,
        engine_tree_sha256=binding_v4.engine_tree_sha256,
        engine_artifact_sha256=request.engine_artifact_sha256,
        engine_binding_sha256=request.engine_binding_sha256,
    )
    raw_v5 = deepcopy(raw_v4)
    raw_v5["schema_version"] = ENGINE_TRACE_V5_SCHEMA_VERSION
    raw_v5["capability"] = ENGINE_TRACE_V5_CAPABILITY
    raw_v5["source_manifest_body_sha256"] = binding_v5.manifest_body_sha256
    character = _provider("character", "furina", 0)
    raw_v5["health_operations"] = [
        {
            "sequence_index": 0,
            "operation_id": "health-operation:0",
            "kind": "heal",
            "frame": 120,
            "parent_occurrence_id": "source-occurrence:2",
            "provider": character,
            "caller_index": 0,
            "target_index": 0,
            "heal_type": "absolute",
            "external": None,
            "input_value": 1000.0,
            "adjusted_input_value": 1000.0,
            "base_amount": 1000.0,
            "source_bonus": 0.1,
            "heal_bonus_total": 0.2,
            "raw_amount": 1300.0,
            "event_amount": 1200.0,
            "event_effective_amount": 1000.0,
            "hp_delta_magnitude": 1000.0,
            "overheal": 200.0,
            "hp_debt_before": 100.0,
            "hp_debt_after": 0.0,
            "max_hp_before": 10000.0,
            "max_hp_after": 10000.0,
            "hp_before": 5000.0,
            "hp_after": 6000.0,
            "hp_ratio_before": 0.5,
            "hp_ratio_after": 0.6,
            "modifier_contributions": [
                {
                    "contribution_id": "health-operation:0:modifier:0",
                    "modifier_key": "healbonus:furina",
                    "source_id": ids["furina"],
                    "source_occurrence_id": "source-occurrence:2",
                    "provider": character,
                    "value": 0.2,
                    "expiry_frame": -1,
                    "candidate_dependency_complete": True,
                }
            ],
            "candidate_dependency_complete": True,
            "uncertainty_codes": [],
        },
        {
            "sequence_index": 1,
            "operation_id": "health-operation:1",
            "kind": "drain",
            "frame": 121,
            "parent_occurrence_id": "source-occurrence:3",
            "provider": character,
            "caller_index": None,
            "target_index": 0,
            "heal_type": None,
            "external": False,
            "input_value": 750.0,
            "adjusted_input_value": 750.0,
            "base_amount": None,
            "source_bonus": None,
            "heal_bonus_total": None,
            "raw_amount": 750.0,
            "event_amount": 750.0,
            "event_effective_amount": 750.0,
            "hp_delta_magnitude": 500.0,
            "overheal": None,
            "hp_debt_before": 0.0,
            "hp_debt_after": 0.0,
            "max_hp_before": 10000.0,
            "max_hp_after": 12000.0,
            "hp_before": 6000.0,
            "hp_after": 6500.0,
            "hp_ratio_before": 0.6,
            "hp_ratio_after": 6500.0 / 12000.0,
            "modifier_contributions": [],
            "candidate_dependency_complete": False,
            "uncertainty_codes": ["health_state_callback_interleaving"],
        },
    ]
    return request, raw_v5, binding_v5, raw_v4, binding_v4, ids


if __name__ == "__main__":
    unittest.main()
