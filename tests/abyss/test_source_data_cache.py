from __future__ import annotations

import tempfile
import unittest

from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import (
    AbyssSourceDataCacheError,
    cached_abyss_floor_source_data_path,
    has_cached_abyss_floor_source_data,
    load_cached_abyss_floor_source_data,
    save_abyss_floor_source_data,
)

from tests.abyss.test_source_data_update import current_style_reports


def _current_style_source_data():
    fandom_report, tower_report = current_style_reports()
    return load_abyss_floor12_source_data(
        "2026-05-16",
        "119",
        composition_report=fandom_report,
        nanoka_report=tower_report,
    )


class AbyssSourceDataCacheTest(unittest.TestCase):
    def test_save_load_roundtrip_preserves_source_data_shape(self) -> None:
        data = _current_style_source_data()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_abyss_floor_source_data(data, cache_dir=tmp)
            loaded = load_cached_abyss_floor_source_data(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )

        self.assertEqual(path.name, "floor_12.json")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.period.start_date, "2026-05-16")
        self.assertEqual(loaded.period.end_date, "2026-06-16 04:00:00")
        self.assertEqual(loaded.floor, 12)
        self.assertEqual(len(loaded.enemy_rows), 10)
        self.assertEqual(loaded.matched_count, 10)
        self.assertEqual(loaded.unmatched_count, 0)
        self.assertEqual(loaded.ambiguous_count, 0)
        self.assertEqual(len(loaded.side_summaries), len(data.side_summaries))
        self.assertEqual(
            loaded.side_summary(1, 1).solo_target_hp,
            data.side_summary(1, 1).solo_target_hp,
        )
        self.assertEqual(
            loaded.side_summary(1, 1).multi_target_hp,
            data.side_summary(1, 1).multi_target_hp,
        )
        self.assertEqual(
            loaded.source_urls["fandom_period_url"],
            data.source_urls["fandom_period_url"],
        )
        self.assertEqual(
            loaded.source_urls["nanoka_page_url"],
            "https://gi.nanoka.cc/tower/119/",
        )

    def test_missing_cache_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                load_cached_abyss_floor_source_data(
                    "2026-05-16",
                    floor=12,
                    cache_dir=tmp,
                )
            )
            self.assertFalse(
                has_cached_abyss_floor_source_data(
                    "2026-05-16",
                    floor=12,
                    cache_dir=tmp,
                )
            )

    def test_malformed_cache_raises_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = cached_abyss_floor_source_data_path(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not json", encoding="utf-8")

            with self.assertRaises(AbyssSourceDataCacheError):
                load_cached_abyss_floor_source_data(
                    "2026-05-16",
                    floor=12,
                    cache_dir=tmp,
                )

    def test_cache_key_includes_period_and_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = cached_abyss_floor_source_data_path(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )
            other_period = cached_abyss_floor_source_data_path(
                "2026-02-16",
                floor=12,
                cache_dir=tmp,
            )
            other_floor = cached_abyss_floor_source_data_path(
                "2026-05-16",
                floor=11,
                cache_dir=tmp,
            )

        self.assertIn("2026-05-16", str(first))
        self.assertIn("floor_12", first.name)
        self.assertNotEqual(first, other_period)
        self.assertNotEqual(first, other_floor)


if __name__ == "__main__":
    unittest.main()
