from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.abyss.source_data_runtime import read_cached_hoyolab_abyss_period
from tests.run_workspace.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)
from tools.future.abyss_period_switch import (
    _safe_monthly_period_end,
    list_cached_periods,
    restore_period_backup,
    switch_current_period_to_cached_source_data,
)


def _source_data(period_start: str, tower_id: str):
    return load_abyss_floor12_source_data(
        period_start,
        tower_id,
        composition_report=composition_report(
            period_start,
            [
                fandom_row(
                    "Debug Enemy",
                    chamber=1,
                    side=1,
                    wave=1,
                    count=1,
                    level=100,
                ),
            ],
        ),
        nanoka_report=nanoka_report(
            tower_id,
            [
                nanoka_row(
                    "Debug Enemy",
                    chamber=1,
                    side=1,
                    hp=1_000_000,
                    monster_id=tower_id,
                    level=100,
                ),
            ],
        ),
    )


class FutureAbyssPeriodSwitchToolTest(unittest.TestCase):
    def test_short_cache_period_end_is_not_used_as_official_period_end(self) -> None:
        self.assertIsNone(
            _safe_monthly_period_end("2026-05-16", "2026-05-17 03:59:59")
        )
        self.assertEqual(
            _safe_monthly_period_end("2026-05-16", "2026-06-16 03:59:59"),
            "2026-06-16",
        )

    def test_lists_cached_periods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            save_abyss_floor_source_data(
                _source_data("2026-02-16", "116"),
                cache_dir=cache_dir,
            )

            periods = list_cached_periods(floor=12, cache_dir=cache_dir)

        self.assertEqual([item["periodStart"] for item in periods], ["2026-02-16"])
        self.assertEqual(periods[0]["enemyRows"], 1)
        self.assertEqual(periods[0]["matched"], 1)

    def test_switch_writes_period_ref_and_preserves_existing_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            period_path = root / "spiral_abyss_period.json"
            backup_path = root / "spiral_abyss_period.backup.json"
            save_abyss_floor_source_data(
                _source_data("2026-02-16", "116"),
                cache_dir=cache_dir,
            )
            save_abyss_floor_source_data(
                _source_data("2026-05-16", "119"),
                cache_dir=cache_dir,
            )
            period_path.write_text(
                json.dumps({"startDate": "2026-05-16", "endDate": "2026-06-16"}),
                encoding="utf-8",
            )

            first = switch_current_period_to_cached_source_data(
                "2026-02-16",
                cache_dir=cache_dir,
                period_path=period_path,
                backup_path=backup_path,
            )
            second = switch_current_period_to_cached_source_data(
                "2026-05-16",
                cache_dir=cache_dir,
                period_path=period_path,
                backup_path=backup_path,
            )
            current = read_cached_hoyolab_abyss_period(period_path)
            backup = read_cached_hoyolab_abyss_period(backup_path)

        self.assertEqual(first.status, "switched")
        self.assertEqual(first.backup_status, "created")
        self.assertEqual(second.backup_status, "preserved_existing")
        self.assertIsNotNone(current)
        self.assertIsNotNone(backup)
        assert current is not None
        assert backup is not None
        self.assertEqual(current.start_date, "2026-05-16")
        self.assertEqual(backup.start_date, "2026-05-16")

    def test_restore_backup_copies_backup_to_period_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            period_path = root / "spiral_abyss_period.json"
            backup_path = root / "spiral_abyss_period.backup.json"
            period_path.write_text(
                json.dumps({"startDate": "2026-02-16", "endDate": "2026-03-16"}),
                encoding="utf-8",
            )
            backup_path.write_text(
                json.dumps({"startDate": "2026-05-16", "endDate": "2026-06-16"}),
                encoding="utf-8",
            )

            result = restore_period_backup(
                period_path=period_path,
                backup_path=backup_path,
            )
            current = read_cached_hoyolab_abyss_period(period_path)

        self.assertEqual(result.status, "restored_backup")
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.start_date, "2026-05-16")

    def test_missing_cache_does_not_write_period_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            period_path = root / "spiral_abyss_period.json"

            with self.assertRaises(SystemExit):
                switch_current_period_to_cached_source_data(
                    "2026-02-16",
                    cache_dir=root / "cache",
                    period_path=period_path,
                )

            self.assertFalse(period_path.exists())


if __name__ == "__main__":
    unittest.main()
