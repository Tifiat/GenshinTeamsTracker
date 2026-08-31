from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
RECEIPT = (
    ROOT
    / "tests"
    / "fixtures"
    / "gcsim_optimizer_go_v1"
    / "gob2_frozen_seed_receipt_v1.json"
)


class GoCompactAdapterReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_frozen_seed_formula_parity_is_within_rounding_noise(self) -> None:
        parity = self.receipt["parity"]
        self.assertLess(
            abs(parity["go_baseline_damage"] - parity["python_baseline_damage"]),
            1e-6,
        )
        self.assertLess(
            abs(parity["go_candidate_damage"] - parity["python_candidate_damage"]),
            1e-6,
        )
        self.assertLess(
            abs(parity["go_delta_damage"] - parity["python_delta_damage"]),
            1e-6,
        )

    def test_engine_adapter_reduces_the_frozen_payload_materially(self) -> None:
        raw_bytes = self.receipt["raw_trace"]["bytes"]
        compact_bytes = self.receipt["compact_member"]["bytes"]
        self.assertGreater(raw_bytes / compact_bytes, 15.0)
        self.assertEqual(
            self.receipt["raw_trace"]["hit_count"],
            self.receipt["compact_member"]["channel_count"],
        )

    def test_receipt_does_not_claim_later_gates(self) -> None:
        self.assertEqual(self.receipt["engine_executions"]["total"], 2)
        self.assertTrue(all(value is False for value in self.receipt["limits"].values()))

    def test_receipt_is_bound_to_the_committed_adapter_patch(self) -> None:
        patch = ROOT / self.receipt["engine_patch"]["path"]
        self.assertEqual(
            hashlib.sha256(patch.read_bytes()).hexdigest(),
            self.receipt["engine_patch"]["sha256"],
        )


if __name__ == "__main__":
    unittest.main()
