"""Offline source binding and full-trace parsing for the fixed Gaming probe."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.theory_verification import trace_case as probe


ACTORS = ["citlali", "gaming", "bennett", "xilonen"]
CONFIG = "options ignore_burst_energy=true;\n"


def sample_trace() -> tuple[dict, dict]:
    request = probe.trace_request(CONFIG, 742031889)
    h = "a" * 64
    document = {
        "schema_version": 6,
        "capability": "gtt_trace_equation_v6",
        "seed": request["seed"],
        "context_sha256": request["context_sha256"],
        "request_sha256": h,
        "source_config_sha256": probe.engine_source_config_sha256(CONFIG),
        "formula_sha256": h,
        "target_sha256": h,
        "character_keys": ACTORS,
        "duration_frames": 1800,
        "hits": [
            {"actor_index": 1, "attack_tag": 3, "amped": True,
             "amp_type": "melt", "reported_damage": 100, "snapshot_stats": {"em": 0}},
            {"actor_index": 1, "attack_tag": 3, "amped": False,
             "amp_type": "", "reported_damage": 25, "snapshot_stats": {"em": 900}},
            {"actor_index": 1, "attack_tag": 4, "amped": True,
             "amp_type": "melt", "reported_damage": 50},
            {"actor_index": 0, "attack_tag": 3, "amped": True,
             "amp_type": "melt", "reported_damage": 60},
        ],
        "topology_events": [{"phase": "reaction"}, {"phase": "damage"}],
        "guard_summary": {
            "hit_count": 4,
            "formula_kind_counts": {"direct": 4},
            "reaction_operator_counts": {"melt": 3},
            "reaction_topology_complete": True,
            "exact_replay_eligible": False,
        },
    }
    return document, request


class TheoryTraceCaseTests(unittest.TestCase):
    def test_actual_receipts_bind_and_request_is_full_trace(self):
        case, entry, candidate, current, point = probe.bind_saved_sources()
        self.assertEqual(entry["id"], "gaming_melt_theory")
        self.assertEqual(candidate["packages"], current["product"]["candidates"][0]["packages"])
        self.assertEqual(candidate["allocations"], current["product"]["candidates"][0]["allocations"])
        self.assertEqual(candidate["formula_dps"], current["product"]["candidates"][0]["formula_dps"])
        self.assertEqual(case["seeds"], point["input"]["seeds"])
        request = probe.trace_request(point["input"]["config_text"], case["seeds"][0])
        self.assertEqual(request, {
            "schema_version": 1,
            "context_sha256": point["input"]["config_sha256"],
            "seed": str(case["seeds"][0]),
            "iterations": 1,
            "workers": 1,
            "ignore_burst_energy": True,
        })
        self.assertNotIn("output_mode", request)
        self.assertNotEqual(probe.engine_source_config_sha256(point["input"]["config_text"]),
                            request["context_sha256"])

    def test_hit_flags_and_actor_order_determine_plunge_melt(self):
        document, request = sample_trace()
        summary = probe.summarize_full_trace(
            document, request, ACTORS, source_config_sha256=probe.engine_source_config_sha256(CONFIG)
        )
        self.assertEqual(summary["duration_seconds"], 30)
        self.assertEqual(summary["gaming_tag3_plunge"], {
            "damage_basis": "reported_damage_actual_hit",
            "total": {"count": 2, "reported_damage": 125},
            "melted": {"count": 1, "reported_damage": 100},
            "nonmelt": {"count": 1, "reported_damage": 25},
        })
        self.assertEqual(summary["amplified_hit_counts_by_actor"][0],
                         {"actor_key": "citlali", "amp_type_counts": {"melt": 1}})
        self.assertEqual(summary["amplified_hit_counts_by_actor"][1],
                         {"actor_key": "gaming", "amp_type_counts": {"melt": 2}})
        self.assertEqual(summary["reaction_aura_topology_event_count"], 1)
        self.assertEqual(summary["reaction_events"], {
            "availability": "not_serialized_in_full_trace_v6", "per_actor": None,
        })

    def test_parser_rejects_broken_binding_and_hit_fields(self):
        document, request = sample_trace()
        variants = []
        for field, value in (("schema_version", 5), ("seed", "742031890"),
                             ("context_sha256", "b" * 64), ("character_keys", list(reversed(ACTORS))),
                             ("source_config_sha256", "b" * 64), ("duration_frames", 0)):
            changed = copy.deepcopy(document)
            changed[field] = value
            variants.append(changed)
        for field, value in (("actor_index", 4), ("attack_tag", "3"),
                             ("amped", 1), ("reported_damage", float("nan"))):
            changed = copy.deepcopy(document)
            changed["hits"][0][field] = value
            variants.append(changed)
        changed = copy.deepcopy(document)
        changed["hits"][0]["amp_type"] = 123
        variants.append(changed)
        changed = copy.deepcopy(document)
        changed["guard_summary"]["hit_count"] = 3
        variants.append(changed)
        changed = copy.deepcopy(document)
        changed["hits"] = changed["hits"][2:]
        changed["guard_summary"]["hit_count"] = 2
        variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    probe.summarize_full_trace(
                        changed, request, ACTORS, source_config_sha256=probe.engine_source_config_sha256(CONFIG)
                    )

    def test_request_rejects_invalid_seed_and_options(self):
        for seed in (0, -1, 1.0, True, 2**63):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                probe.trace_request(CONFIG, seed)
        for config in ("", "options ignore_burst_energy=maybe;\n",
                       "options ignore_burst_energy=true ignore_burst_energy=false;\n"):
            with self.subTest(config=config), self.assertRaises(ValueError):
                probe.trace_request(config, 1)
        for config in ("options ignore_burst_energy=true;\r\n", 'import "other.txt"\n'):
            with self.subTest(config=config), self.assertRaises(ValueError):
                probe.engine_source_config_sha256(config)

    def test_current_vector_and_prior_config_must_stay_bound(self):
        original = probe.base.read_object
        current = original(probe.CURRENT)
        changed = copy.deepcopy(current)
        changed["product"]["candidates"][0]["allocations"][0]["unspent_roll_units"] = 123
        with patch.object(probe.base, "read_object", side_effect=lambda path: changed if path == probe.CURRENT else original(path)):
            with self.assertRaises(ValueError):
                probe.bind_saved_sources()
        point = original(probe.POINT)
        changed = copy.deepcopy(point)
        changed["input"]["config_sha256"] = "0" * 64
        with patch.object(probe.base, "read_object", side_effect=lambda path: changed if path == probe.POINT else original(path)):
            with self.assertRaises(ValueError):
                probe.bind_saved_sources()


if __name__ == "__main__":
    unittest.main()
