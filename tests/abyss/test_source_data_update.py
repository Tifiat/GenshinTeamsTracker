from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from run_workspace.abyss.source_data_cache import load_cached_abyss_floor_source_data
from run_workspace.abyss.source_data_fetchers import AbyssSourceFetchError
from run_workspace.abyss.source_data_update import build_update_report

from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


def current_style_reports() -> tuple[dict, dict]:
    names = [
        ("Super-Heavy Landrover: Mechanized Fortress", "Super-Heavy Landrover: Mechanized Fortress"),
        ("Lord of the Hidden Depths: Whisperer of Nightmares", "Lord of the Hidden Depths: Whisperer of Nightmares"),
        ("Ruin Drake: Earthguard", "Ruin Drake: Earthguard"),
        ("Primo Geovishap (Cryo)", "Primo Geovishap"),
        ("Battle-Hardened Grounded Geoshroom", "Battle-Hardened Grounded Geoshroom"),
        ("Hexadecatonic Battle-Hardened Mandragora", "Hexadecatonic Battle-Hardened Mandragora"),
        ("Battle-Scarred Rock Crab", "Battle-Scarred Rock Crab"),
        ("Hydro Hilichurl Rogue", "Hydro Hilichurl Rogue"),
        ("Fatui Electro Cicin Mage", "Fatui Electro Cicin Mage"),
        ("Abyss Lector: Fathomless Flames", "Abyss Lector: Fathomless Flames"),
    ]
    fandom_rows = [
        fandom_row(
            fandom_name,
            chamber=(index // 4) + 1,
            side=(index % 2) + 1,
            wave=(index % 3) + 1,
            level=100,
        )
        for index, (fandom_name, _nanoka_name) in enumerate(names)
    ]
    nanoka_rows = [
        nanoka_row(
            nanoka_name,
            chamber=(index // 4) + 1,
            side=(index % 2) + 1,
            hp=1_000_000 + index,
            monster_id=f"m{index}",
            level=100,
        )
        for index, (_fandom_name, nanoka_name) in enumerate(names)
    ]
    return (
        composition_report("2026-05-16", fandom_rows),
        nanoka_report("119", nanoka_rows),
    )


class AbyssSourceDataUpdateTest(unittest.TestCase):
    def test_update_entrypoint_builds_current_style_data_from_period_lookup(self) -> None:
        fandom_report, tower_report = current_style_reports()
        with patch(
            "run_workspace.abyss.source_data_update.fetch_fandom_composition_report",
            return_value=fandom_report,
        ) as fandom_fetch, patch(
            "run_workspace.abyss.source_data_update.fetch_nanoka_tower_report_for_period",
            return_value=tower_report,
        ) as nanoka_fetch:
            report = build_update_report(
                period_start="2026-05-16",
                floor=12,
            )

        self.assertEqual(report["summary"]["enemy_rows"], 10)
        self.assertEqual(report["summary"]["matched"], 10)
        self.assertEqual(report["summary"]["unmatched"], 0)
        self.assertEqual(report["summary"]["ambiguous"], 0)
        self.assertEqual(
            report["probe"]["normal_path_contract"]["fandom_enemy_page_requests"],
            0,
        )
        fandom_fetch.assert_called_once()
        nanoka_fetch.assert_called_once()
        self.assertEqual(report["inputs"]["tower_id"], None)
        self.assertEqual(report["inputs"]["tower_id_input_mode"], "period_lookup")
        self.assertEqual(report["nanoka"]["resolved_tower_id"], "119")

        rows = report["source_data"]["enemy_rows"]
        primo = next(row for row in rows if row["primary_display_name"] == "Primo Geovishap (Cryo)")
        self.assertEqual(primo["matched_nanoka_display_name"], "Primo Geovishap")
        self.assertEqual(primo["match_method"], "variant_strip")

    def test_explicit_tower_id_still_works_without_period_resolver(self) -> None:
        fandom_report, tower_report = current_style_reports()
        with patch(
            "run_workspace.abyss.source_data_update.fetch_fandom_composition_report",
            return_value=fandom_report,
        ), patch(
            "run_workspace.abyss.source_data_update.fetch_nanoka_tower_report",
            return_value=tower_report,
        ) as explicit_fetch, patch(
            "run_workspace.abyss.source_data_update.fetch_nanoka_tower_report_for_period",
            side_effect=AssertionError("period resolver should not run"),
        ):
            report = build_update_report(
                period_start="2026-05-16",
                tower_id="119",
                floor=12,
            )

        explicit_fetch.assert_called_once()
        self.assertEqual(report["summary"]["matched"], 10)
        self.assertEqual(report["inputs"]["tower_id"], "119")
        self.assertEqual(report["inputs"]["tower_id_input_mode"], "explicit_debug_override")

    def test_update_entrypoint_handles_missing_nanoka_without_crash(self) -> None:
        fandom_report = composition_report(
            "2026-05-16",
            [fandom_row("Unmatched Enemy", chamber=1, side=1, wave=1)],
        )
        with patch(
            "run_workspace.abyss.source_data_update.fetch_fandom_composition_report",
            return_value=fandom_report,
        ), patch(
            "run_workspace.abyss.source_data_update.fetch_nanoka_tower_report_for_period",
            side_effect=AbyssSourceFetchError("boom"),
        ):
            report = build_update_report(
                period_start="2026-05-16",
                floor=12,
            )

        self.assertEqual(report["summary"]["enemy_rows"], 1)
        self.assertEqual(report["summary"]["matched"], 0)
        self.assertEqual(report["summary"]["unmatched"], 1)
        self.assertIn("nanoka_report_unavailable", report["summary"]["warnings"])
        self.assertTrue(
            any(
                warning.startswith("nanoka_fetch_failed:")
                for warning in report["summary"]["warnings"]
            )
        )

    def test_update_entrypoint_can_save_cache_when_requested(self) -> None:
        fandom_report, tower_report = current_style_reports()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_workspace.abyss.source_data_update.fetch_fandom_composition_report",
            return_value=fandom_report,
        ), patch(
            "run_workspace.abyss.source_data_update.fetch_nanoka_tower_report_for_period",
            return_value=tower_report,
        ):
            report = build_update_report(
                period_start="2026-05-16",
                floor=12,
                save_cache=True,
                cache_dir=tmp,
            )
            loaded = load_cached_abyss_floor_source_data(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )

        self.assertTrue(report["cache"]["saved"])
        self.assertIn("2026-05-16", report["cache"]["path"])
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(len(loaded.enemy_rows), 10)
        self.assertEqual(loaded.matched_count, 10)


if __name__ == "__main__":
    unittest.main()
