from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import (
    AbyssSourceDataCacheError,
    DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR,
    cache_abyss_floor_monster_icons,
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
    def test_default_cache_path_is_project_root_anchored(self) -> None:
        path = cached_abyss_floor_source_data_path("2026-05-16", floor=12)

        self.assertTrue(DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR.is_absolute())
        self.assertTrue(path.is_absolute())
        self.assertEqual(
            path,
            DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR / "2026-05-16" / "floor_12.json",
        )

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

    def test_cache_monster_icons_prefers_nanoka_icon_urls(self) -> None:
        data = _current_style_source_data()
        fetched_urls: list[str] = []

        def fetcher(url: str) -> bytes:
            fetched_urls.append(url)
            return f"bytes:{url}".encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            result = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=fetcher,
            )
            first_row = result.data.enemy_rows[0]

        self.assertEqual(result.attempted, 10)
        self.assertEqual(result.saved, 10)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.downloaded, 10)
        self.assertTrue(all("static.nanoka.cc" in url for url in fetched_urls))
        self.assertIsNotNone(first_row.cached_icon_path)
        assert first_row.cached_icon_path is not None
        self.assertTrue(first_row.cached_icon_path.endswith(".png"))

    def test_cache_monster_icons_falls_back_to_fandom_icon_url(self) -> None:
        data = _current_style_source_data()

        def fetcher(url: str) -> bytes:
            if "static.nanoka.cc" in url:
                raise OSError("nanoka unavailable")
            return b"fandom-icon"

        with tempfile.TemporaryDirectory() as tmp:
            result = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=fetcher,
            )
            first_row = result.data.enemy_rows[0]
            cached_path = first_row.cached_icon_path
            assert cached_path is not None
            cached_bytes = Path(cached_path).read_bytes()

        self.assertEqual(result.saved, 10)
        self.assertEqual(result.failed, 0)
        self.assertEqual(cached_bytes, b"fandom-icon")
        self.assertIn("nanoka_icon_cache_failed_used_fandom_icon", first_row.warnings)

    def test_failed_icon_cache_keeps_source_data_save_usable(self) -> None:
        data = _current_style_source_data()

        def fetcher(_url: str) -> bytes:
            raise OSError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            result = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=fetcher,
            )
            path = save_abyss_floor_source_data(result.data, cache_dir=tmp)
            loaded = load_cached_abyss_floor_source_data(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )
            self.assertTrue(path.is_file())

        self.assertEqual(result.saved, 0)
        self.assertEqual(result.failed, 10)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIsNone(loaded.enemy_rows[0].cached_icon_path)
        self.assertTrue(
            any(
                warning.startswith("monster_icon_cache_failed")
                for warning in loaded.enemy_rows[0].warnings
            )
        )

    def test_saved_source_data_preserves_local_cached_icon_paths(self) -> None:
        data = _current_style_source_data()

        with tempfile.TemporaryDirectory() as tmp:
            result = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=lambda _url: b"icon",
            )
            save_abyss_floor_source_data(result.data, cache_dir=tmp)
            loaded = load_cached_abyss_floor_source_data(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )

            self.assertIsNotNone(loaded)
            assert loaded is not None
            cached_path = loaded.enemy_rows[0].cached_icon_path
            self.assertIsNotNone(cached_path)
            assert cached_path is not None
            self.assertTrue(Path(cached_path).is_file())

    def test_missing_cached_icon_file_is_cleared_on_load(self) -> None:
        data = _current_style_source_data()

        with tempfile.TemporaryDirectory() as tmp:
            result = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=lambda _url: b"icon",
            )
            save_abyss_floor_source_data(result.data, cache_dir=tmp)
            cached_path = result.data.enemy_rows[0].cached_icon_path
            assert cached_path is not None
            Path(cached_path).unlink()

            loaded = load_cached_abyss_floor_source_data(
                "2026-05-16",
                floor=12,
                cache_dir=tmp,
            )

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIsNone(loaded.enemy_rows[0].cached_icon_path)
        self.assertIn("cached_icon_file_missing", loaded.enemy_rows[0].warnings)

    def test_cache_monster_icons_is_idempotent_for_existing_files(self) -> None:
        data = _current_style_source_data()
        fetch_count = 0

        def fetcher(_url: str) -> bytes:
            nonlocal fetch_count
            fetch_count += 1
            return b"icon"

        with tempfile.TemporaryDirectory() as tmp:
            first = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=fetcher,
            )
            second = cache_abyss_floor_monster_icons(
                data,
                cache_dir=tmp,
                icon_fetcher=fetcher,
            )
            icon_files = list(
                cached_abyss_floor_source_data_path(
                    "2026-05-16",
                    floor=12,
                    cache_dir=tmp,
                )
                .with_name("floor_12_assets")
                .joinpath("monster_icons")
                .iterdir()
            )

        self.assertEqual(first.downloaded, 10)
        self.assertEqual(second.downloaded, 0)
        self.assertEqual(second.cache_hits, 10)
        self.assertEqual(fetch_count, 10)
        self.assertEqual(len(icon_files), 10)


if __name__ == "__main__":
    unittest.main()
