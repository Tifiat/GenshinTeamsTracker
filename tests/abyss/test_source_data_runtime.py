from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.abyss.source_data_runtime import (
    load_current_cached_abyss_floor_source_data,
    read_cached_hoyolab_abyss_period,
)

from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)
from run_workspace.abyss.source_data import load_abyss_floor12_source_data


def runtime_source_data():
    return load_abyss_floor12_source_data(
        "2026-05-16",
        "119",
        composition_report=composition_report(
            "2026-05-16",
            [
                fandom_row(
                    "Solo Enemy",
                    chamber=1,
                    side=1,
                    wave=1,
                    count=3,
                    level=100,
                ),
            ],
        ),
        nanoka_report=nanoka_report(
            "119",
            [
                nanoka_row(
                    "Solo Enemy",
                    chamber=1,
                    side=1,
                    hp=1_200_000,
                    monster_id="solo",
                    level=100,
                ),
            ],
        ),
    )


class AbyssSourceDataRuntimeTest(unittest.TestCase):
    def test_reads_cached_hoyolab_period_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            period_path = Path(tmp) / "spiral_abyss_period.json"
            period_path.write_text(
                json.dumps(
                    {
                        "rawPeriod": "2026/05/16-2026/06/16",
                        "startDate": "2026-05-16",
                        "endDate": "2026-06-16",
                    }
                ),
                encoding="utf-8",
            )

            period = read_cached_hoyolab_abyss_period(period_path)

        self.assertIsNotNone(period)
        assert period is not None
        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")

    def test_loads_current_cached_source_data_by_period_and_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            period_path = root / "spiral_abyss_period.json"
            period_path.write_text(
                json.dumps({"startDate": "2026-05-16", "endDate": "2026-06-16"}),
                encoding="utf-8",
            )
            save_abyss_floor_source_data(runtime_source_data(), cache_dir=root / "cache")

            loaded = load_current_cached_abyss_floor_source_data(
                period_path=period_path,
                cache_dir=root / "cache",
                floor=12,
            )

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.period.start_date, "2026-05-16")
        self.assertEqual(loaded.side_summary(1, 1).solo_target_hp, 1_200_000)
        self.assertEqual(loaded.side_summary(1, 1).multi_target_hp, 3_600_000)

    def test_missing_period_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_current_cached_abyss_floor_source_data(
                period_path=Path(tmp) / "missing.json",
                cache_dir=Path(tmp) / "cache",
            )

        self.assertIsNone(loaded)

    def test_missing_cache_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            period_path = root / "spiral_abyss_period.json"
            period_path.write_text(
                json.dumps({"startDate": "2026-05-16", "endDate": "2026-06-16"}),
                encoding="utf-8",
            )

            loaded = load_current_cached_abyss_floor_source_data(
                period_path=period_path,
                cache_dir=root / "cache",
            )

        self.assertIsNone(loaded)


if __name__ == "__main__":
    unittest.main()
