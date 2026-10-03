"""Bounded evidence retention and early unmanaged refusal; no engine runs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.experiments.gcsim.parametric_effects.recheck_saved_all_sets import main, save_receipt


class SavedAllSetsRecheckTests(unittest.TestCase):
    def test_refuses_unmanaged_before_inputs(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(RuntimeError):
            main()

    def test_fixed_receipt_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'receipt.json'
            save_receipt(path, {'result': 'failed'})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_receipt(path, {'result': 'pass'})
            self.assertEqual(path.read_bytes(), original)

    def test_oversize_is_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'receipt.json'
            with patch('tools.experiments.gcsim.parametric_effects.recheck_saved_all_sets.MAX_BYTES', 10), self.assertRaises(ValueError):
                save_receipt(path, {'result': 'oversized payload'})
            self.assertFalse(path.exists())
