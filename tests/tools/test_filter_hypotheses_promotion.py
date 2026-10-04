"""Bounded H4 promotion checks; no engine, account, app or native process."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

prior_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from tools.experiments.gcsim.filter_hypotheses import promotion as gate
finally:
    sys.dont_write_bytecode = prior_bytecode


class FilterPromotionTests(unittest.TestCase):
    def pair(self):
        return {"status": "complete_search_pair_pass", "exact_rows": True,
                "same_ordered_score_trace": True, "same_scored_count": True,
                "same_work_stop": True, "protected_inputs_unchanged": True,
                "runs": [{"name": "baseline", "search_seconds": 100},
                         {"name": "gate", "search_seconds": 90}],
                "reference_rows": [{"group": "a", "dps": "100.1", "ids": [["a", "flower", 1]]}]}

    def test_requires_two_passes_and_both_run_orders_faster(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = self.pair(), self.pair()
            for name, data in (("pair1.json", first), ("pair2-reverse.json", second)):
                (root / name).write_text(json.dumps(data), encoding="utf-8")
            with patch.object(gate, "EVIDENCE", root):
                self.assertEqual(gate.accepted_pairs()["reference_rows"], first["reference_rows"])
                for altered in (dict(second, same_ordered_score_trace=False),
                                dict(second, reference_rows=[]),
                                dict(second, runs=[{"name": "baseline", "search_seconds": 100},
                                                   {"name": "gate", "search_seconds": 101}])):
                    (root / "pair2-reverse.json").write_text(json.dumps(altered), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        gate.accepted_pairs()

    def test_default_adapters_use_installed_path_without_account_reads(self):
        raw = {"stochastic": {"seeds": [742031889, 742031890]},
               "result_options": {"set_group_limit": 5, "builds_per_group": 7, "fast_mode": True}}
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ("selected", "all_sets"):
                session = gate.make_session(Path(temporary), mode, copy.deepcopy(raw))
                self.assertEqual(Path(session.request.optimizer_binary_path).resolve(),
                                 Path(gate.DEFAULT_OPTIMIZER_BINARY).resolve())
                self.assertEqual(session.request.builds_per_group, 7)
                self.assertTrue(session.request.fast_mode)
                self.assertEqual(session.request.product_timeout_ms, 0)
                self.assertFalse(Path(session.request.db_path).exists())

    def test_promoted_domain_kernel_matches_tested_research_implementation(self):
        research = (gate.ROOT / "tools/experiments/gcsim/filter_hypotheses/neighborhood_gate.go").read_text(encoding="utf-8")
        expected = research.replace("HypothesisNeighborhoodGatePlan", "NeighborhoodPlan").replace(
            "PrepareHypothesisNeighborhoodGate", "PrepareNeighborhood").replace(
            "hypothesisNeighborhood", "neighborhood").replace(
            "a research-only physical-legality lookup", "a physical-legality lookup").replace(
            "so a research caller can fall back", "so the caller can fall back")
        actual = (gate.NATIVE / "internal/domain/neighborhood.go").read_text(encoding="utf-8")
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
