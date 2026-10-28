"""Small raw-DAG diagnostics; never launches GCSIM or optimizer search."""

import hashlib
import json
from pathlib import Path
import unittest

from tools.experiments.gcsim.parametric_effects.capture_equivalence import canonical_capture
from tools.experiments.gcsim.search_hypotheses.capture_repeat import (
    canonical_field_equality, capture_guards, channel_root_diagnostics,
    compare_root_dags, diagnostic_path,
)


def sample(*, offset=0, value="12", owner="actor"):
    member = {"nodes": [
        {"node_id": 1 + offset, "operation": "constant", "value": value, "inputs": []},
        {"node_id": 2 + offset, "operation": "constant", "value": "0", "inputs": []},
        {"node_id": 3 + offset, "operation": "add", "inputs": [
            {"node_id": 1 + offset, "relation": "left"},
            {"node_id": 2 + offset, "relation": "right"}]}],
        "channels": [{"root_node_id": 3 + offset}], "opaque_boundaries": []}
    effects = {"neutral": {"stats": [{"node_id": 1 + offset, "owner": owner,
                                       "stat": "attack"}], "reads": [],
                           "reads_complete": True, "world": {"complete": True},
                           "ledger": {"truncated": False}},
               "effect_inputs": [], "resistance_inputs": []}
    raw = json.dumps(member).encode()
    effects["member_content_sha256"] = hashlib.sha256(raw).hexdigest()
    return member, effects, canonical_capture(raw, json.dumps(effects).encode())


class SearchCaptureRepeatTests(unittest.TestCase):
    def test_attempt_names_keep_first_historical_slot_and_never_alias(self):
        pair = Path("pair.json")
        self.assertEqual(diagnostic_path(pair, 1).name, "pair-capture-diagnostic.json")
        self.assertEqual(diagnostic_path(pair, 2).name, "pair-capture-diagnostic-attempt2.json")
        self.assertEqual(diagnostic_path(pair, 3).name, "pair-capture-diagnostic-attempt3.json")
        with self.assertRaises(ValueError):
            diagnostic_path(pair, 4)

    def test_aligned_node_renumber_is_structurally_exact(self):
        a, ae, ca = sample()
        b, be, cb = sample(offset=10)
        self.assertEqual(ca, cb)
        fields = canonical_field_equality(ca, cb)
        self.assertTrue(all(all(part.values()) for part in fields.values()))
        detail = channel_root_diagnostics(a, ae, b, be, ca, cb)
        self.assertEqual(detail["canonical_root_differences"], 0)
        self.assertEqual(detail["raw_root_id_differences"], 1)
        self.assertTrue(detail["first_differing_roots"][0]["dag"]["structural_equal"])
        self.assertEqual(capture_guards(ae), {"reads_complete": True,
                                              "world_complete": True,
                                              "ledger_not_truncated": True})

    def test_deep_real_constant_and_source_annotation_are_distinguished(self):
        a, ae, _ = sample()
        b, be, _ = sample(offset=10, value="32")
        # More than the 80 preview nodes: traversal must still reach the leaf.
        a["nodes"] = a["nodes"][:1]
        b["nodes"] = b["nodes"][:1]
        for index in range(2, 123):
            a["nodes"].append({"node_id": index, "operation": "identity", "inputs":
                               [{"node_id": index - 1, "relation": "input"}]})
            b["nodes"].append({"node_id": index + 10, "operation": "identity", "inputs":
                               [{"node_id": index + 9, "relation": "input"}]})
        dag = compare_root_dags(a, ae, b, be, 122, 132)
        self.assertGreater(dag["visited_pairs"], 80)
        self.assertEqual(len(dag["first_visited"]), 80)
        arithmetic = [m for m in dag["mismatches"] if m["kind"] == "node_metadata"]
        self.assertEqual(len(arithmetic), 1)
        self.assertEqual((arithmetic[0]["a_node"]["value"], arithmetic[0]["b_node"]["value"]),
                         ("12", "32"))
        self.assertGreater(arithmetic[0]["depth"], 80)
        c, ce, _ = sample()
        d, de, _ = sample(offset=10, owner="different-source")
        annotation = compare_root_dags(c, ce, d, de, 3, 13)
        self.assertEqual([m["kind"] for m in annotation["mismatches"]], ["annotations"])
        self.assertEqual(annotation["mismatches"][0]["a_annotations"][0]["binding"]["owner"], "actor")
        self.assertEqual(annotation["mismatches"][0]["b_annotations"][0]["binding"]["owner"],
                         "different-source")


if __name__ == "__main__":
    unittest.main()
