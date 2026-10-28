"""Finite POC receipt/fixture checks, not a rerun or account-scale acceptance.

The dated archetype audit owns this temporary research contract. These checks
pin real-vector preservation, physically legal restricted domains and explicit
proof limitations; managed-runner tests separately own deletion/failure safety.
"""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from tools.experiments.gcsim.inventory_bound_poc.run import choose_pool, stat_vector, write_compact_receipt

ROOT = Path(__file__).resolve().parents[2]


class InventoryBoundPocTest(unittest.TestCase):
    def test_compact_export_limit_and_existing_evidence_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            with self.assertRaises(ValueError):
                write_compact_receipt(path, {"unbounded": "x" * 65536})
            self.assertFalse(path.exists())
            write_compact_receipt(path, {"keep": 1})
            with self.assertRaises(FileExistsError):
                write_compact_receipt(path, {"replace": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"keep": 1})

    def test_balanced_witness_is_preserved_as_one_joint_vector(self):
        def artifact(identity, cr, cd):
            return {"artifact_id": identity, "main_stat": {"key": "hp", "value": "4780"},
                    "substats": [{"key": "crit_rate", "value": str(cr)},
                                 {"key": "crit_damage", "value": str(cd)}]}
        items = [artifact(1, 0, .23), artifact(2, .117, 0), artifact(3, .10, .22)]
        pool = choose_pool(items, preferred=3)
        self.assertEqual({a["artifact_id"] for a in pool}, {1, 2, 3})
        self.assertEqual(stat_vector(pool[0]), {"hp": 4780, "crit_rate": .10, "crit_damage": .22})
        with self.assertRaises(ValueError):
            choose_pool([])

    def test_receipt_has_legal_restricted_domains_and_full_oracle_agreement(self):
        receipt = json.loads((ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["engine_capture_calls"], 6)
        self.assertEqual(receipt["ordinary_simulator_calls"], 0)
        self.assertIn("no proof of schedule invariance", receipt["proof_scope"])
        self.assertEqual(len(receipt["real_cases"]), 3)
        for case, result in zip(receipt["inputs"], receipt["real_cases"]):
            with self.subTest(case=case["name"]):
                self.assertEqual(case["name"], result["name"])
                reserved = {a for w, slots in case["reference_ids"].items() if w != case["actor"] for a in slots.values()}
                self.assertEqual(len(reserved), 15)
                slots = ("flower", "plume", "sands", "goblet", "circlet")
                seen = set()
                combinations = 1
                constant_families = []
                for slot, pool in zip(slots, case["pools"]):
                    combinations *= len(pool)
                    self.assertTrue(pool)
                    families = {a["set_uid"] for a in pool}
                    if len(families) == 1:
                        constant_families.append(next(iter(families)))
                    for artifact in pool:
                        self.assertEqual(artifact["slot"], slot)
                        self.assertNotIn(artifact["id"], reserved | seen)
                        seen.add(artifact["id"])
                    self.assertEqual(pool[0]["id"], case["reference_ids"][case["actor"]][slot])
                if case["name"] == "zero_bonus":
                    self.assertEqual(len(set(constant_families)), 5)
                else:
                    self.assertGreaterEqual(Counter(constant_families)[case["set_uid"]], 4)
                self.assertEqual(combinations, result["combinations"])
                self.assertEqual(result["search_best"], result["oracle_best"])
                self.assertEqual(result["best_ids"], result["oracle_ids"])
                self.assertEqual(result["worst_upper_bound_violation"], 0)
                self.assertLess(result["reduced_point_max_error"], 1e-6)
                self.assertLess(result["exact_scored_unique"], combinations)
                self.assertLessEqual(result["search_best"], result["root_upper"])
                self.assertTrue(result["opaque_boundary_counts"])
                self.assertEqual(len(result["topology_sha256"]), 2)
        for case in receipt["synthetic"]:
            self.assertEqual(case["search_best"], case["oracle_best"])
            self.assertEqual(case["worst_upper_bound_violation"], 0)


if __name__ == "__main__":
    unittest.main()
