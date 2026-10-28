from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
import unittest

from run_workspace.gcsim.trace_equation import (
    ENGINE_TRACE_V3_CAPABILITY,
    ENGINE_TRACE_V3_SCHEMA_VERSION,
    ReactionEvidenceTrace,
    RankingStatValue,
    RankingSupport,
    TraceContractError,
    canonical_json,
    decode_engine_trace,
    decode_engine_trace_v3,
    estimate_candidate_expected_damage,
)

from .test_contracts import _document
from .test_provider_evidence_v2 import _raw_engine_trace_v2


_REACTION_FORMULA_ID = "gtt_transformative_reaction_v1"
_REACTION_FORMULA_SHA256 = (
    "c5e843111092ced9e2979cc228715acaafb4701b462923bb21b2c59091d43139"
)


class ReactionEvidenceV3Tests(unittest.TestCase):
    def test_dispatcher_materializes_additive_v3_without_changing_v2(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v3(request)

        direct = decode_engine_trace_v3(canonical_json(raw), request=request)
        dispatched = decode_engine_trace(canonical_json(raw), request=request)

        self.assertIsInstance(direct, ReactionEvidenceTrace)
        self.assertEqual(dispatched, direct)
        self.assertEqual(direct.schema_version, 3)
        self.assertFalse(direct.exact_replay_eligible)
        self.assertFalse(direct.hard_prune_allowed)
        self.assertEqual(direct.reaction_hits[0].event_id, "hit:1")
        self.assertEqual(direct.reaction_hits[0].formula.owner_key, "hero")

    def test_transformative_formula_replays_absolute_owner_em(self) -> None:
        request = _document().request
        decoded = decode_engine_trace_v3(
            canonical_json(_raw_engine_trace_v3(request)), request=request
        )

        baseline = estimate_candidate_expected_damage(decoded, ())
        em_1000 = estimate_candidate_expected_damage(
            decoded,
            (RankingStatValue("hero", "em", 1000.0),),
        )

        expected_base = _reaction_damage(em=300.0)
        expected_1000 = _reaction_damage(em=1000.0)
        self.assertEqual(baseline.modeled_hit_count, 1)
        self.assertEqual(baseline.support, RankingSupport.HEURISTIC)
        self.assertTrue(math.isclose(baseline.candidate_score or 0.0, expected_base))
        self.assertTrue(math.isclose(em_1000.candidate_score or 0.0, expected_1000))
        self.assertGreater(em_1000.expected_delta or 0.0, 0.0)
        self.assertIn("reaction_schedule_assumed_fixed", em_1000.uncertainty_codes)

    def test_parent_occurrence_is_resolved_only_from_preceding_attack(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v3(request)
        raw["hits"][0]["attack_id"] = 8
        parent = deepcopy(_raw_engine_trace_v2(request)["hits"][0])
        parent.update(
            {
                "attack_id": 7,
                "hit_id": 99,
                "parent_target_key": None,
                "reaction_formula": None,
            }
        )
        raw["hits"].insert(0, parent)
        raw["guard_summary"]["hit_count"] = 2
        raw["guard_summary"]["formula_kind_counts"] = {"standard": 2}
        raw["guard_summary"]["reaction_operator_counts"] = {
            "none": 1,
            "spawn_damage_attack": 1,
        }
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)

        self.assertTrue(
            decoded.reaction_hits[0].formula.parent_occurrence_resolved
        )

    def test_future_matching_hit_does_not_resolve_parent_occurrence(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v3(request)
        parent = deepcopy(_raw_engine_trace_v2(request)["hits"][0])
        parent.update(
            {
                "attack_id": 7,
                "hit_id": 99,
                "parent_target_key": None,
                "reaction_formula": None,
            }
        )
        raw["hits"].append(parent)
        raw["guard_summary"]["hit_count"] = 2
        raw["guard_summary"]["formula_kind_counts"] = {"standard": 2}
        raw["guard_summary"]["reaction_operator_counts"] = {
            "none": 1,
            "spawn_damage_attack": 1,
        }
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)
        estimate = estimate_candidate_expected_damage(decoded, ())

        self.assertFalse(
            decoded.reaction_hits[0].formula.parent_occurrence_resolved
        )
        self.assertIn(
            "reaction_parent_occurrence_unresolved",
            estimate.uncertainty_codes,
        )

    def test_child_cannot_resolve_itself_as_its_parent(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v3(request)
        raw["hits"][0]["parent_attack_id"] = 1
        raw["hits"][0]["reaction_formula"]["parent_attack_id"] = 1
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)
        estimate = estimate_candidate_expected_damage(decoded, ())

        self.assertFalse(
            decoded.reaction_hits[0].formula.parent_occurrence_resolved
        )
        self.assertIn(
            "reaction_parent_occurrence_unresolved",
            estimate.uncertainty_codes,
        )

    def test_formula_uses_explicit_owner_not_terminal_actor_or_aura_owner(self) -> None:
        request = replace(
            _document().request, character_keys=("hero", "owner", "aura")
        )
        raw = _raw_engine_trace_v3(request)
        raw["hits"][0]["actor_index"] = 1
        raw["hits"][0]["reaction_formula"]["owner_index"] = 1
        raw["hits"][0]["reaction_formula"]["aura_source_indices"] = [2]
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)

        changed = estimate_candidate_expected_damage(
            decoded,
            (
                RankingStatValue("aura", "em", 1200.0),
                RankingStatValue("owner", "em", 1000.0),
            ),
        )
        self.assertTrue(
            math.isclose(changed.candidate_score or 0.0, _reaction_damage(em=1000.0))
        )

    def test_persistent_revision_and_gadget_ownership_round_trip(self) -> None:
        request = replace(
            _document().request, character_keys=("creator", "converter")
        )
        raw = _raw_engine_trace_v3(request)
        raw["hits"][0]["actor_index"] = 1
        formula = raw["hits"][0]["reaction_formula"]
        formula.update(
            {
                "owner_index": 1,
                "persistent_state_id": "ec:target-0:120",
                "persistent_revision": 2,
                "gadget_id": "dendro-core:7",
                "gadget_creator_index": 0,
                "gadget_converter_index": 1,
                "gadget_resolution_reason": "converted",
            }
        )
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)
        row = decoded.reaction_hits[0].formula

        self.assertEqual(row.owner_key, "converter")
        self.assertEqual(row.persistent_revision, 2)
        self.assertEqual(row.gadget_creator_key, "creator")
        self.assertEqual(row.gadget_converter_key, "converter")

    def test_bloom_family_keeps_creator_and_selects_damage_owner(self) -> None:
        request = replace(
            _document().request, character_keys=("creator", "converter")
        )
        cases = (
            ("Bloom", 0, None, "expired", "creator"),
            ("Hyperbloom", 1, 1, "converted", "converter"),
            ("Burgeon", 1, 1, "converted", "converter"),
        )
        for reaction_type, owner, converter, reason, expected_owner in cases:
            raw = _raw_engine_trace_v3(request)
            raw["hits"][0]["actor_index"] = owner
            formula = raw["hits"][0]["reaction_formula"]
            formula.update(
                {
                    "reaction_type": reaction_type,
                    "owner_index": owner,
                    "gadget_id": "gadget:7",
                    "gadget_creator_index": 0,
                    "gadget_converter_index": converter,
                    "gadget_resolution_reason": reason,
                }
            )
            with self.subTest(reaction_type=reaction_type):
                decoded = decode_engine_trace_v3(
                    canonical_json(raw), request=request
                )
                row = decoded.reaction_hits[0].formula
                self.assertEqual(row.owner_key, expected_owner)
                self.assertEqual(row.gadget_creator_key, "creator")

    def test_unknown_formula_and_post_construction_change_freeze_safely(self) -> None:
        request = _document().request
        unknown = _raw_engine_trace_v3(request)
        unknown["hits"][0]["reaction_formula"]["formula_sha256"] = "0" * 64
        changed = _raw_engine_trace_v3(request)
        changed["hits"][0]["reaction_formula"]["constructed_flat_damage"] += 1.0

        for raw in (unknown, changed):
            with self.subTest(raw=raw["hits"][0]["reaction_formula"]):
                decoded = decode_engine_trace_v3(canonical_json(raw), request=request)
                estimate = estimate_candidate_expected_damage(
                    decoded,
                    (RankingStatValue("hero", "em", 1000.0),),
                )
                self.assertEqual(estimate.modeled_hit_count, 0)
                self.assertEqual(estimate.support, RankingSupport.BASELINE_FROZEN)

    def test_same_topology_icd_suppressed_child_remains_zero(self) -> None:
        request = _document().request
        raw = _raw_engine_trace_v3(request)
        raw["hits"][0]["damage_group_multiplier"] = 0.0
        raw["hits"][0]["pre_amp_damage"] = 0.0
        raw["hits"][0]["uncapped_damage"] = 0.0
        raw["hits"][0]["actual_damage"] = 0.0
        raw["hits"][0]["reported_damage"] = 0.0
        raw["hits"][0]["hp_after"] = raw["hits"][0]["hp_before"]
        decoded = decode_engine_trace_v3(canonical_json(raw), request=request)

        estimate = estimate_candidate_expected_damage(
            decoded,
            (RankingStatValue("hero", "em", 1000.0),),
        )
        self.assertEqual(estimate.modeled_hit_count, 1)
        self.assertEqual(estimate.candidate_score, 0.0)

    def test_v3_rejects_missing_coordinates_and_invalid_persistent_group(self) -> None:
        request = _document().request
        missing = _raw_engine_trace_v3(request)
        del missing["hits"][0]["reaction_formula"]["owner_index"]
        with self.assertRaisesRegex(TraceContractError, "missing"):
            decode_engine_trace_v3(canonical_json(missing), request=request)

        partial = _raw_engine_trace_v3(request)
        partial["hits"][0]["reaction_formula"]["persistent_revision"] = 1
        with self.assertRaisesRegex(TraceContractError, "persistent"):
            decode_engine_trace_v3(canonical_json(partial), request=request)

    def test_v3_rejects_terminal_owner_level_em_and_parent_binding_drift(self) -> None:
        request = replace(_document().request, character_keys=("hero", "other"))
        mutations = (
            ("parent target", lambda raw: raw["hits"][0].__setitem__("parent_target_key", 9)),
            ("owner", lambda raw: raw["hits"][0]["reaction_formula"].__setitem__("owner_index", 1)),
            ("level", lambda raw: raw["hits"][0]["reaction_formula"].__setitem__("level", 89)),
            ("EM", lambda raw: raw["hits"][0]["reaction_formula"].__setitem__("elemental_mastery", 0.0)),
            ("read-frame", lambda raw: raw["hits"][0]["reaction_formula"].__setitem__("read_frame", 999)),
        )
        for reason, mutate in mutations:
            raw = _raw_engine_trace_v3(request)
            mutate(raw)
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(TraceContractError, "binding mismatch"):
                    decode_engine_trace_v3(canonical_json(raw), request=request)


def _raw_engine_trace_v3(request) -> dict[str, object]:
    raw = deepcopy(_raw_engine_trace_v2(request))
    raw["schema_version"] = ENGINE_TRACE_V3_SCHEMA_VERSION
    raw["capability"] = ENGINE_TRACE_V3_CAPABILITY
    hit = raw["hits"][0]
    level_base = 1446.8535
    em = 300.0
    reaction_bonus = 0.15
    coefficient = 2.0
    core_damage = level_base * (1.0 + 16.0 * em / (2000.0 + em) + reaction_bonus)
    constructed = coefficient * core_damage
    terminal = constructed * 0.9
    hit.update(
        {
            "parent_attack_id": 7,
            "parent_target_key": 0,
            "snapshot_frame": 120,
            "ability": "Electro-Charged",
            "attack_tag": 13,
            "element": "electro",
            "reaction_operator_id": "spawn_damage_attack",
            "mult": 0.0,
            "flat_dmg": constructed,
            "ignore_def_percent": 1.0,
            "damage_group_multiplier": 1.0,
            "snapshot_stats": {
                **hit["snapshot_stats"],
                "em": em,
                "cr": 0.0,
                "cd": 0.0,
            },
            "char_level": 90,
            "base_damage": constructed,
            "damage_bonus": 0.0,
            "raw_crit_rate": 0.0,
            "crit_rate_clamped": 0.0,
            "crit_damage": 0.0,
            "crit_roll": 0.8,
            "resistance": 0.1,
            "res_mod": 0.9,
            "def_adj": 0.0,
            "def_mod": 1.0,
            "em": em,
            "pre_amp_damage": terminal,
            "uncapped_damage": terminal,
            "actual_damage": terminal,
            "reported_damage": terminal,
            "hp_after": 10000.0 - terminal,
            "reaction_formula": {
                "formula_id": _REACTION_FORMULA_ID,
                "formula_sha256": _REACTION_FORMULA_SHA256,
                "reaction_type": "Electro-Charged",
                "operator_id": "spawn_damage_attack",
                "owner_index": 0,
                "read_frame": 120,
                "read_mode": "live",
                "read_phase": "persistent_update",
                "level": 90,
                "level_base": level_base,
                "elemental_mastery": em,
                "em_curve_numerator": 16.0,
                "em_curve_denominator_offset": 2000.0,
                "reaction_bonus": reaction_bonus,
                "reaction_bonus_contributions": [],
                "core_damage": core_damage,
                "coefficient": coefficient,
                "constructed_flat_damage": constructed,
                "parent_attack_id": 7,
                "parent_target_key": 0,
                "aura_source_indices": [],
                "child_role": "damage",
                "child_ordinal": 0,
                "persistent_state_id": None,
                "persistent_revision": None,
                "gadget_id": None,
                "gadget_creator_index": None,
                "gadget_converter_index": None,
                "gadget_resolution_reason": None,
            },
        }
    )
    hit["completeness"]["flat_dmg_provenance_complete"] = True
    raw["guard_summary"]["reaction_operator_counts"] = {
        "spawn_damage_attack": 1
    }
    return raw


def _reaction_damage(*, em: float) -> float:
    level_base = 1446.8535
    reaction_bonus = 0.15
    coefficient = 2.0
    return (
        coefficient
        * level_base
        * (1.0 + 16.0 * em / (2000.0 + em) + reaction_bonus)
        * 0.9
    )


if __name__ == "__main__":
    unittest.main()
