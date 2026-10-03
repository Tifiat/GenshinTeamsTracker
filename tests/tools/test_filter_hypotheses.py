"""Finite receipt ownership; heavy pilot output is removed by the managed runner."""
from pathlib import Path
import sys
import tempfile
import unittest

# Import the research runner without creating another persistent cache tree.
prior_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from tools.experiments.gcsim.filter_hypotheses.run import (
        MAX_RECEIPTS, MAX_RECEIPT_BYTES, receipt_target,
    )
finally:
    sys.dont_write_bytecode = prior_bytecode


class ReceiptOwnershipTests(unittest.TestCase):
    def test_normalizes_path_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = Path(tmp) / "evidence"
            owner.mkdir()
            target = owner / "result.json"
            self.assertEqual(receipt_target(target, owner=owner), target.resolve())
            with self.assertRaises(ValueError):
                receipt_target(owner / ".." / "outside.json", owner=owner)
            with self.assertRaises(ValueError):
                receipt_target(owner / "nested" / "result.json", owner=owner)
            with self.assertRaises(ValueError):
                receipt_target(owner / "result.txt", owner=owner)

    def test_preserves_existing_evidence_and_enforces_finite_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = Path(tmp)
            first = owner / "failed.json"
            first.write_bytes(b'{"exit_code":1}')
            with self.assertRaises(FileExistsError):
                receipt_target(first, owner=owner)
            for number in range(MAX_RECEIPTS - 1):
                (owner / f"result-{number}.json").write_bytes(b"{}")
            with self.assertRaises(ValueError):
                receipt_target(owner / "extra.json", owner=owner)
            self.assertEqual(first.read_bytes(), b'{"exit_code":1}')

    def test_oversize_prior_receipt_blocks_new_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = Path(tmp)
            previous = owner / "previous.json"
            previous.write_bytes(b" " * (MAX_RECEIPT_BYTES + 1))
            with self.assertRaises(ValueError):
                receipt_target(owner / "new.json", owner=owner)
            self.assertTrue(previous.exists())


if __name__ == "__main__":
    unittest.main()
