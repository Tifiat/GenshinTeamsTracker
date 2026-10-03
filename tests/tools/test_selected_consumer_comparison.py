import unittest
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing

from tools.experiments.gcsim.parametric_effects.compare_selected_consumer import (
    _initial_measurement,
    _ordinary_work,
    _validate_all_wrapper,
    _copy_account_database,
    _matrix_equipment_fixture,
)


class SelectedConsumerComparisonTests(unittest.TestCase):
    def test_snapshot_copy_keeps_live_database_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, copy = root / "live.db", root / "copy.db"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE control (value INTEGER)")
                connection.execute("INSERT INTO control VALUES (7)")
                connection.commit()
            _copy_account_database(source, copy)
            with closing(sqlite3.connect(copy)) as connection:
                connection.execute("UPDATE control SET value=9")
                connection.commit()
            with closing(sqlite3.connect(source)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM control").fetchone(), (7,))

    def test_matrix_equipment_cannot_target_live_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            job.mkdir()
            source = root / "live.db"
            with closing(sqlite3.connect(source)):
                pass
            before = source.read_bytes()
            with self.assertRaises(ValueError):
                _matrix_equipment_fixture(source, job, "flins_jahoda_selected_infinite")
            self.assertEqual(source.read_bytes(), before)

    def test_verify_fgbs_wrapper_uses_all_mode(self):
        _validate_all_wrapper(
            {"mode": "all", "product_result": {"request_sha256": "same"}},
            "same",
            "candidate",
        )
        with self.assertRaisesRegex(RuntimeError, "verify-fgbs all"):
            _validate_all_wrapper(
                {"mode": "selected", "product_result": {"request_sha256": "same"}},
                "same",
                "candidate",
            )

    def test_adaptive_iterations_include_both_base_and_extension_calls(self):
        wrapper = {
            "screening": {"candidates": [{"iterations": 128}, {"iterations": 128}]},
            "verification": {
                "candidates": [
                    {"iterations": 1000}, {"iterations": 1000},
                    {"iterations": 500}, {"iterations": 500}, {"iterations": 500},
                    {"iterations": 500}, {"iterations": 500},
                ],
                "adaptive": {
                    "base_iterations": 500,
                    "extension_iterations": 1000,
                    "extended_assignment_sha256": ["a" * 64, "b" * 64],
                },
            },
        }

        self.assertEqual(_ordinary_work(wrapper), {"calls": 11, "iterations": 5756})

    def test_initial_measurement_prefers_final_verification(self):
        wrapper = {
            "screening": {"candidates": [{
                "assignment": [[1, 2], [3]],
                "measured_dps": 100,
                "standard_error": 8,
                "iterations": 128,
            }]},
            "verification": {"candidates": [{
                "assignment": [[1, 2], [3]],
                "measured_dps": 110,
                "standard_error": 3,
                "iterations": 500,
            }]},
        }

        self.assertEqual(
            _initial_measurement(wrapper, [1, 2, 3]),
            {"dps": 110.0, "standard_error": 3.0, "iterations": 500},
        )


if __name__ == "__main__":
    unittest.main()
