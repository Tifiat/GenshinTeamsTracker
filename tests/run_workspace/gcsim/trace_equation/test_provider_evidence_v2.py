from __future__ import annotations

from copy import deepcopy
import json
import unittest

from run_workspace.gcsim.trace_equation import (
    ENGINE_TRACE_V2_CAPABILITY,
    ENGINE_TRACE_V2_SCHEMA_VERSION,
    OpaqueEngineTraceEnvelope,
    ProviderEvidenceTrace,
    PruneSafety,
    RankingStatValue,
    ReplayStatus,
    TraceContractError,
    TraceDocument,
    canonical_json,
    decode_engine_trace,
    decode_engine_trace_v1,
    decode_engine_trace_v2,
    decode_provider_evidence_trace,
    encode_provider_evidence_trace,
    estimate_candidate_expected_damage,
)

from test_contracts import _document, _raw_engine_trace


class ProviderEvidenceV2Tests(unittest.TestCase):
    def test_dispatcher_preserves_v1_and_strictly_materializes_v2(self) -> None:
        request = _document().request
        v1_raw = _raw_engine_trace(request)
        direct_v1 = decode_engine_trace_v1(canonical_json(v1_raw), request=request)
        dispatched_v1 = decode_engine_trace(canonical_json(v1_raw), request=request)

        self.assertIsInstance(direct_v1, TraceDocument)
        self.assertEqual(dispatched_v1, direct_v1)

        v2_raw = _raw_engine_trace_v2(request)
        direct_v1_view = decode_engine_trace_v1(
            canonical_json(v2_raw), request=request
        )
        self.assertIsInstance(direct_v1_view, OpaqueEngineTraceEnvelope)

        decoded = decode_engine_trace(canonical_json(v2_raw), request=request)
        strict = decode_engine_trace_v2(canonical_json(v2_raw), request=request)
        self.assertIsInstance(decoded, ProviderEvidenceTrace)
        self.assertEqual(decoded, strict)
        self.assertEqual(decoded.schema_version, 2)
        self.assertFalse(decoded.exact_replay_eligible)
        self.assertFalse(decoded.hard_prune_allowed)
        self.assertTrue(
            all(
                hit.formula_replay_status is not ReplayStatus.EXACT_IN_CELL
                for hit in decoded.terminal_trace.hits
            )
        )
        self.assertFalse(decoded.terminal_trace.topology.complete)

        estimate = estimate_candidate_expected_damage(
            decoded.terminal_trace,
            (RankingStatValue("hero", "atk%", 0.55),),
        )
        self.assertEqual(estimate.prune_safety, PruneSafety.KEEP)
        self.assertFalse(estimate.publishable)

    def test_wrapper_round_trip_is_immutable_and_hash_bound(self) -> None:
        request = _document().request
        decoded = decode_engine_trace_v2(
            canonical_json(_raw_engine_trace_v2(request)), request=request
        )
        payload = encode_provider_evidence_trace(decoded)
        round_trip = decode_provider_evidence_trace(payload)

        self.assertEqual(round_trip, decoded)
        self.assertEqual(round_trip.evidence_sha256, decoded.evidence_sha256)
        self.assertEqual(
            round_trip.terminal_trace.receipt.receipt_sha256,
            decoded.terminal_trace.receipt.receipt_sha256,
        )
        with self.assertRaises((AttributeError, TypeError)):
            round_trip.hard_prune_allowed = True  # type: ignore[misc]

        tampered = json.loads(payload)
        tampered["evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(TraceContractError, "SHA-256 mismatch"):
            decode_provider_evidence_trace(canonical_json(tampered))

    def test_ordered_transitions_and_raw_evidence_change_identity(self) -> None:
        request = _document().request
        baseline_raw = _raw_engine_trace_v2(request)
        baseline = decode_engine_trace_v2(
            canonical_json(baseline_raw), request=request
        )

        reversed_raw = deepcopy(baseline_raw)
        reversed_raw["provider_transitions"] = list(
            reversed(reversed_raw["provider_transitions"])
        )
        reversed_trace = decode_engine_trace_v2(
            canonical_json(reversed_raw), request=request
        )

        self.assertNotEqual(
            baseline.raw_payload_sha256, reversed_trace.raw_payload_sha256
        )
        self.assertNotEqual(baseline.evidence_sha256, reversed_trace.evidence_sha256)
        self.assertEqual(
            [row.catalog_index for row in reversed_trace.provider_transitions],
            [0, 1],
        )
        self.assertNotEqual(
            baseline.provider_transitions[0].modifier_key,
            reversed_trace.provider_transitions[0].modifier_key,
        )

    def test_explicit_unknown_and_global_provider_never_gain_authority(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v2(request)
        hit = raw["hits"][0]
        hit["provider"] = {
            "known": False,
            "kind": "unattributed_attack",
            "key": "skill",
            "owner_index": -1,
            "piece_count": 0,
        }
        hit["callback_attempts"][0]["provider"] = _provider(
            kind="global_rule",
            key="rotation-rule",
            owner_index=-1,
        )
        decoded = decode_engine_trace_v2(canonical_json(raw), request=request)

        self.assertFalse(decoded.hit_evidence[0].provider.known)
        self.assertEqual(
            decoded.hit_evidence[0].provider.kind,
            "unattributed_attack",
        )
        self.assertEqual(
            decoded.hit_evidence[0].callback_attempts[0].provider.owner_index,
            -1,
        )
        self.assertIn("provider_identity_unknown", decoded.authority_reason_codes)
        self.assertIn(
            "callback_state_effects_unobserved",
            decoded.authority_reason_codes,
        )
        self.assertFalse(decoded.exact_replay_eligible)
        self.assertFalse(decoded.hard_prune_allowed)

    def test_v2_rejects_schema_drift_and_invalid_provider_evidence(self) -> None:
        request = _document().request

        missing = _raw_engine_trace_v2(request)
        del missing["hits"][0]["callback_attempts"]
        with self.assertRaisesRegex(TraceContractError, "missing"):
            decode_engine_trace_v2(canonical_json(missing), request=request)

        unknown = _raw_engine_trace_v2(request)
        unknown["hits"][0]["provider"]["surprise"] = True
        with self.assertRaisesRegex(TraceContractError, "unknown"):
            decode_engine_trace_v2(canonical_json(unknown), request=request)

        null_array = _raw_engine_trace_v2(request)
        null_array["hits"][0]["stat_contributions"] = None
        with self.assertRaisesRegex(TraceContractError, "array"):
            decode_engine_trace_v2(canonical_json(null_array), request=request)

        zero_coordinate = _raw_engine_trace_v2(request)
        zero_coordinate["hits"][0]["stat_contributions"][0]["values"] = {
            "atk%": 0.0
        }
        with self.assertRaisesRegex(TraceContractError, "non-zero"):
            decode_engine_trace_v2(
                canonical_json(zero_coordinate), request=request
            )

        bad_set = _raw_engine_trace_v2(request)
        bad_set["hits"][0]["stat_contributions"][0]["provider"][
            "piece_count"
        ] = 0
        with self.assertRaisesRegex(TraceContractError, "piece_count"):
            decode_engine_trace_v2(canonical_json(bad_set), request=request)

    def test_empty_values_records_a_zero_or_rejected_statmod_attempt(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v2(request)
        row = raw["hits"][0]["stat_contributions"][0]
        row["accepted"] = False
        row["values"] = {}

        decoded = decode_engine_trace_v2(canonical_json(raw), request=request)
        contribution = decoded.hit_evidence[0].stat_contributions[0]
        self.assertFalse(contribution.accepted)
        self.assertEqual(contribution.values, ())
        self.assertFalse(decoded.hard_prune_allowed)

    def test_modifier_eval_bindings_are_optional_but_strict_when_present(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v2(request)
        raw["hits"][0]["stat_contributions"][0][
            "modifier_eval_event_id"
        ] = "state-event:17"
        raw["hits"][0]["attack_mods"][0][
            "modifier_eval_event_id"
        ] = "state-event:23"

        decoded = decode_engine_trace_v2(canonical_json(raw), request=request)

        self.assertEqual(
            decoded.hit_evidence[0].stat_contributions[0].modifier_eval_event_id,
            "state-event:17",
        )
        self.assertEqual(
            decoded.hit_evidence[0].attack_mods[0].modifier_eval_event_id,
            "state-event:23",
        )
        self.assertEqual(
            decode_provider_evidence_trace(
                encode_provider_evidence_trace(decoded)
            ),
            decoded,
        )

        invalid = _raw_engine_trace_v2(request)
        invalid["hits"][0]["stat_contributions"][0][
            "modifier_eval_event_id"
        ] = "modifier:17"
        with self.assertRaisesRegex(TraceContractError, "state event"):
            decode_engine_trace_v2(canonical_json(invalid), request=request)

    def test_transition_accepts_only_minus_one_sentinels(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v2(request)
        transition = raw["provider_transitions"][0]
        transition["frame"] = -1
        transition["recipient_index"] = -1

        decoded = decode_engine_trace_v2(canonical_json(raw), request=request)
        self.assertEqual(decoded.provider_transitions[0].frame, -1)
        self.assertEqual(decoded.provider_transitions[0].recipient_index, -1)

        for field in ("frame", "recipient_index"):
            invalid = _raw_engine_trace_v2(request)
            invalid["provider_transitions"][0][field] = -2
            with self.subTest(field=field):
                with self.assertRaisesRegex(TraceContractError, "-1 sentinel"):
                    decode_engine_trace_v2(canonical_json(invalid), request=request)


def _provider(
    *,
    kind: str = "character",
    key: str = "hero",
    owner_index: int = 0,
    piece_count: int = 0,
    known: bool = True,
) -> dict[str, object]:
    if not known:
        kind = ""
        key = ""
        piece_count = 0
    return {
        "known": known,
        "kind": kind,
        "key": key,
        "owner_index": owner_index,
        "piece_count": piece_count,
    }


def _raw_engine_trace_v2(request) -> dict[str, object]:
    raw = deepcopy(_raw_engine_trace(request))
    raw["schema_version"] = ENGINE_TRACE_V2_SCHEMA_VERSION
    raw["capability"] = ENGINE_TRACE_V2_CAPABILITY

    character = _provider()
    artifact_set = _provider(
        kind="artifact_set",
        key="test-support-set",
        piece_count=4,
    )
    global_rule = _provider(
        kind="global_rule",
        key="reaction-table",
        owner_index=-1,
    )
    hit = raw["hits"][0]
    hit["provider"] = character
    hit["stat_contributions"] = [
        {
            "modifier_key": "statmod:test-support-set",
            "recipient_index": 0,
            "accepted": True,
            "values": {"atk%": 0.2},
            "provider": artifact_set,
        }
    ]
    hit["callback_attempts"] = [
        {
            "event": 17,
            "hook_key": "callback:team-state",
            "provider": global_rule,
            "changed": False,
            "topology_changed": False,
            "state_effects_unobserved": True,
            "snapshot_delta": {},
            "mult_delta": 0.0,
            "flat_dmg_delta": 0.0,
            "base_dmg_bonus_delta": 0.0,
            "elevation_delta": 0.0,
            "ignore_def_delta": 0.0,
            "amp_multiplier_delta": 0.0,
        }
    ]
    hit["attack_mods"] = [
        {
            "modifier_key": "attackmod:test",
            "source_key": "legacy:test",
            "owner_index": 0,
            "accepted": False,
            "before_damage": None,
            "after_damage": None,
            "delta": {},
            "provider": artifact_set,
        }
    ]
    hit["target_mod_contributions"] = [
        {
            "channel": "resistance",
            "modifier_key": "targetmod:test",
            "value": -0.1,
            "provider": artifact_set,
        }
    ]
    hit["reaction_bonus_contributions"] = [
        {
            "modifier_key": "reaction:test",
            "value": 0.15,
            "provider": global_rule,
        }
    ]
    # Both rows deliberately share a frame.  Array order is evidence and is
    # preserved by the wrapper even when all other transition keys are valid.
    raw["provider_transitions"] = [
        {
            "frame": 100,
            "channel": "team_stat",
            "recipient_index": 0,
            "modifier_key": "transition:a",
            "transition": "added",
            "provider": artifact_set,
            "displaced_provider": None,
        },
        {
            "frame": 100,
            "channel": "team_stat",
            "recipient_index": 0,
            "modifier_key": "transition:b",
            "transition": "replaced",
            "provider": global_rule,
            "displaced_provider": artifact_set,
        },
    ]
    return raw


if __name__ == "__main__":
    unittest.main()
