from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import stdev
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "tests"
    / "fixtures"
    / "gcsim_optimizer_go_v1"
    / "gob3a_stochastic_contract_v1.json"
)
CAPTURE_RECEIPT = (
    ROOT
    / "tests"
    / "fixtures"
    / "gcsim_optimizer_go_v1"
    / "gob3d_two_seed_capture_receipt_v1.json"
)


class GoStochasticContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_panel_is_the_frozen_sorted_equal_weight_pair(self) -> None:
        panel = self.contract["real_parity_panel"]
        self.assertEqual(panel["seeds"], [742031889, 742031890])
        self.assertEqual(panel["weights"], ["0.5", "0.5"])
        self.assertEqual(
            self.contract["seed_source"],
            "sorted_unique_request_field_never_hardcoded",
        )
        self.assertEqual(self.contract["mode"], "equal_weight_fixed_panel_v1")

    def test_python_parity_landmarks_follow_the_frozen_math(self) -> None:
        parity = self.contract["python_parity"]
        values = [float(value) for value in parity["member_dps"]]
        self.assertAlmostEqual(
            math.fsum(values) / len(values),
            float(parity["equal_weight_dps"]),
            places=9,
        )
        sample_sd = stdev(values)
        self.assertAlmostEqual(sample_sd, float(parity["sample_sd_dps"]), places=9)
        self.assertAlmostEqual(
            sample_sd / math.sqrt(len(values)),
            float(parity["standard_error_dps"]),
            places=9,
        )

    def test_contract_grants_no_search_or_product_authority(self) -> None:
        authority = self.contract["authority"]
        self.assertEqual(authority["engine_calls"], 0)
        self.assertFalse(authority["product_panel_size_accepted"])
        self.assertFalse(authority["convergence_rule_accepted"])
        self.assertFalse(authority["artifact_search_authority"])
        self.assertFalse(
            self.contract["uncertainty"]["opaque_exposure_values_are_additive_damage"]
        )

    def test_gob3d_receipt_is_the_same_unaggregated_real_panel(self) -> None:
        receipt = json.loads(CAPTURE_RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(
            [member["seed"] for member in receipt["members"]],
            self.contract["real_parity_panel"]["seeds"],
        )
        self.assertEqual(
            [member["duration_ms"] for member in receipt["members"]],
            [self.contract["duration_ms"], self.contract["duration_ms"]],
        )
        self.assertNotEqual(
            receipt["members"][0]["topology_sha256"],
            receipt["members"][1]["topology_sha256"],
        )
        self.assertTrue(
            all(member["strict_go_contract_validated"] for member in receipt["members"])
        )
        self.assertTrue(
            all(member["zero_delta_baseline_validated"] for member in receipt["members"])
        )
        self.assertEqual(receipt["engine_executions"], 2)
        self.assertEqual(receipt["search_executions"], 0)
        self.assertEqual(receipt["n1000_executions"], 0)
        self.assertFalse(receipt["real_panel_aggregation_performed"])


if __name__ == "__main__":
    unittest.main()
