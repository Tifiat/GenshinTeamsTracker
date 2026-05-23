from __future__ import annotations

import unittest
from pathlib import Path

from ui.artifact_browser.json_import_actions import (
    affected_preset_ids,
    clear_summary_values,
    run_artiscan_imports,
)


class ArtiscanJsonImportActionsTest(unittest.TestCase):
    def test_run_artiscan_imports_aggregates_successes_and_errors(self) -> None:
        def fake_import(paths: list[str | Path]) -> list[dict]:
            path = Path(paths[0])
            if path.name == "bad.json":
                raise RuntimeError("broken file")
            if path.name == "empty.json":
                return []
            return [
                {
                    "inserted": 2,
                    "skipped_duplicates": 3,
                    "skipped_invalid": 1,
                }
            ]

        result = run_artiscan_imports(
            ["ok.json", "bad.json", "empty.json"],
            import_files=fake_import,
        )

        self.assertTrue(result.has_imports)
        self.assertEqual(
            result.totals,
            {
                "files": 3,
                "inserted": 2,
                "duplicates": 3,
                "invalid": 1,
            },
        )
        self.assertEqual(result.errors, ["bad.json: broken file"])

    def test_run_artiscan_imports_reports_no_successful_imports(self) -> None:
        def fake_import(paths: list[str | Path]) -> list[dict]:
            raise RuntimeError("nope")

        result = run_artiscan_imports(
            ["one.json", "two.json"],
            import_files=fake_import,
        )

        self.assertFalse(result.has_imports)
        self.assertEqual(result.totals["files"], 2)
        self.assertEqual(result.totals["inserted"], 0)
        self.assertEqual(
            result.error_text(),
            "one.json: nope\ntwo.json: nope",
        )

    def test_affected_preset_ids_normalizes_ids(self) -> None:
        summary = {
            "affected_presets": [
                {"id": "12", "name": "A"},
                {"id": 34, "name": "B"},
            ],
        }

        self.assertEqual(affected_preset_ids(summary), [12, 34])

    def test_clear_summary_values_defaults_missing_counts(self) -> None:
        self.assertEqual(
            clear_summary_values(
                {
                    "deleted_artifacts": "5",
                    "cleared_slots": None,
                },
                deleted_presets=2,
            ),
            {
                "deleted": 5,
                "slots": 0,
                "presets": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
