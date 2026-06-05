from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.snap_monster_titles import (
    SNAP_TITLE_STATUS_AMBIGUOUS,
    SNAP_TITLE_STATUS_MISSING,
    SNAP_TITLE_STATUS_RESOLVED,
    load_snap_monster_title_index,
)


class GcsimSnapMonsterTitlesTest(unittest.TestCase):
    def test_loads_name_title_records_from_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Assault Specialist Mek - Pneuma",
                            "Title": "Assault Specialist Mek",
                            "HpBase": 123,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(lookup.candidates[0].title, "Assault Specialist Mek")

    def test_loads_simple_wrapper_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "Name": "Tenebrous Mimesis - Anemo Hilichurl Rogue",
                                "Title": "Tenebrous Mimiflora",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Tenebrous Mimesis - Anemo Hilichurl Rogue")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(lookup.candidates[0].title, "Tenebrous Mimiflora")

    def test_duplicate_name_with_same_title_is_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(len(lookup.candidates), 1)

    def test_duplicate_name_with_different_titles_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Clockwork Mek"},
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_AMBIGUOUS)
        self.assertIn(
            "snap_title_ambiguous_for_name:assaultspecialistmekpneuma",
            lookup.warnings,
        )

    def test_missing_name_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}]),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Missing Enemy")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_MISSING)
        self.assertIn("snap_title_missing_for_name:missingenemy", lookup.warnings)


if __name__ == "__main__":
    unittest.main()
