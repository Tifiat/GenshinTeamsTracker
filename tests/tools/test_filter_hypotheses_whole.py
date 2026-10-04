"""Output-parity evidence validation; no app, account or engine access."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

prior_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from tools.experiments.gcsim.filter_hypotheses.whole_search import (
        fingerprint, make_overlay, rows_of,
    )
finally:
    sys.dont_write_bytecode = prior_bytecode


class WholeSearchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.request = {"wearers": [{"wearer_key": f"actor{i}"} for i in range(4)], "artifacts": []}
        assignment = []
        for actor in range(4):
            for slot in ("flower", "plume", "sands", "goblet", "circlet"):
                item = len(assignment) + 1
                self.request["artifacts"].append({"artifact_id": item, "slot": slot, "set_uid": f"solo{actor}_{slot}"})
                assignment.append({"wearer_key": f"actor{actor}", "slot": slot, "artifact_id": item})
        self.request["artifacts"] += [
            {"artifact_id": 21, "slot": "plume", "set_uid": "other_plume"},
            {"artifact_id": 22, "slot": "goblet", "set_uid": "other_goblet"},
        ]
        group = json.dumps([{"wearer_key": f"actor{i}", "bonuses": []} for i in range(4)])
        leader = {"artifacts": assignment, "alternative_rank": 1, "formula_dps": "100.25", "set_group_key": group}
        swap = copy.deepcopy(leader)
        swap["alternative_rank"], swap["formula_dps"] = 2, "99.5"
        swap["artifacts"][1]["artifact_id"] = 21
        self.output = {"product_result": {"candidates": [leader, swap]}}

    def test_valid_physical_output_and_exact_fingerprint(self):
        rows = rows_of(self.output, self.request)
        self.assertEqual(len(rows), 2)
        self.assertEqual(fingerprint(rows), fingerprint(rows_of(copy.deepcopy(self.output), self.request)))
        altered = copy.deepcopy(rows)
        altered[0]["dps"] = "100.2500000001"
        self.assertNotEqual(fingerprint(rows), fingerprint(altered))

    def test_rejects_reused_item_and_mismatched_bonus(self):
        invalid = copy.deepcopy(self.output)
        invalid["product_result"]["candidates"][0]["artifacts"][0]["artifact_id"] = 6
        with self.assertRaisesRegex(ValueError, "Illegal"):
            rows_of(invalid, self.request)
        invalid = copy.deepcopy(self.output)
        wrong = json.loads(invalid["product_result"]["candidates"][0]["set_group_key"])
        wrong[0]["bonuses"] = [{"set_uid": "other", "pieces": 4}]
        invalid["product_result"]["candidates"][0]["set_group_key"] = json.dumps(wrong)
        with self.assertRaisesRegex(ValueError, "piece counts"):
            rows_of(invalid, self.request)

    def test_rejects_double_swap(self):
        invalid = copy.deepcopy(self.output)
        invalid["product_result"]["candidates"][1]["artifacts"][3]["artifact_id"] = 22
        with self.assertRaisesRegex(ValueError, "exactly one"):
            rows_of(invalid, self.request)

    def test_current_source_overlay_is_generated_only_in_temporary_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay = make_overlay(Path(tmp))
            replacements = json.loads(overlay.read_text(encoding="utf-8"))["Replace"]
            self.assertGreaterEqual(len(replacements), 6)
            code = (Path(tmp) / "internal/search/candidates.go").read_text(encoding="utf-8")
            self.assertIn("gate.Pairs[a][b][position]", code)
            self.assertIn("hypothesisRecord(r.anchor, r.actor, ids, v)", code)
            self.assertNotIn("hypothesisRecord(r.anchor, r.actor, ids, v)",
                             Path(next(k for k in replacements if k.endswith("candidates.go"))).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
