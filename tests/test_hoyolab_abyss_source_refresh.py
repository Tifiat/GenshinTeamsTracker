from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.abyss_source_refresh import (
    AbyssSourceDataRefreshResult,
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    HoYoLABAbyssPeriod,
    extract_hoyolab_abyss_period,
    parse_hoyolab_abyss_period,
    refresh_cached_abyss_source_data_for_hoyolab_period,
    update_cached_abyss_source_data_for_hoyolab_period,
    write_hoyolab_abyss_period,
)
from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import (
    cache_abyss_floor_monster_icons,
    save_abyss_floor_source_data,
)
from run_workspace.abyss.source_data_runtime import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH as RUNTIME_HOYOLAB_ABYSS_PERIOD_PATH,
)
from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


class HoYoLABAbyssPeriodParsingTest(unittest.TestCase):
    def test_parse_hoyolab_period_string(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")
        self.assertEqual(period.raw_period, "2026/05/16-2026/06/16")

    def test_extracts_period_from_payload_string(self) -> None:
        period = extract_hoyolab_abyss_period(
            {
                "retcode": 0,
                "data": {
                    "schedule": {
                        "period": "2026/05/16-2026/06/16",
                    }
                },
            }
        )

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")
        self.assertEqual(period.source_path, "$.data.schedule.period")

    def test_extracts_period_from_start_end_fields(self) -> None:
        period = extract_hoyolab_abyss_period(
            {
                "retcode": 0,
                "data": {
                    "schedule": {
                        "start_time": "2026/05/16 04:00:00",
                        "end_time": "2026/06/16 03:59:59",
                    }
                },
            }
        )

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")
        self.assertEqual(period.source_path, "$.data.schedule")


class HoYoLABAbyssSourceRefreshTest(unittest.TestCase):
    def test_period_writer_uses_runtime_period_path_contract(self) -> None:
        self.assertEqual(
            DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
            RUNTIME_HOYOLAB_ABYSS_PERIOD_PATH,
        )
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_hoyolab_abyss_period(
                period,
                period_path=Path(tmp) / "spiral_abyss_period.json",
            )

            self.assertTrue(path.is_file())
            self.assertIn("2026-05-16", path.read_text(encoding="utf-8"))

    def test_update_helper_calls_source_data_cache_update_for_floor_12(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def fake_report(**kwargs: object) -> dict[str, object]:
            self.assertEqual(kwargs["period_start"], "2026-05-16")
            self.assertEqual(kwargs["period_end"], "2026-06-16")
            self.assertEqual(kwargs["floor"], 12)
            self.assertTrue(kwargs["save_cache"])
            self.assertTrue(kwargs["cache_assets"])
            return {
                "summary": {
                    "enemy_rows": 10,
                    "matched": 10,
                    "unmatched": 0,
                    "ambiguous": 0,
                    "warnings": [],
                },
                "cache": {"saved": True, "path": "cache/floor_12.json"},
                "assets": {"enabled": True, "saved": 10, "failed": 0, "warnings": []},
            }

        result = update_cached_abyss_source_data_for_hoyolab_period(
            period,
            floor=12,
            force=True,
            update_report_builder=fake_report,
        )

        self.assertTrue(result.cache_saved)
        self.assertEqual(result.cache_path, "cache/floor_12.json")
        self.assertEqual(result.enemy_rows, 10)
        self.assertEqual(result.matched, 10)

    def test_best_effort_refresh_calls_updater_once(self) -> None:
        calls: list[dict[str, object]] = []
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def fake_updater(
            update_period: HoYoLABAbyssPeriod | str,
            *,
            floor: int = 12,
            cache_dir: str | None = None,
            cache_assets: bool = True,
            force: bool = False,
        ) -> AbyssSourceDataRefreshResult:
            calls.append(
                {
                    "period": update_period,
                    "floor": floor,
                    "cache_dir": cache_dir,
                    "cache_assets": cache_assets,
                    "force": force,
                }
            )
            assert isinstance(update_period, HoYoLABAbyssPeriod)
            return AbyssSourceDataRefreshResult(
                period=update_period,
                floor=floor,
                cache_saved=True,
                cache_path="cache/floor_12.json",
                matched=10,
                unmatched=0,
                ambiguous=0,
                enemy_rows=10,
                assets={"enabled": True},
            )

        summary, error = refresh_cached_abyss_source_data_for_hoyolab_period(
            period,
            floor=12,
            updater=fake_updater,
        )

        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertTrue(summary["cacheSaved"])
        self.assertEqual(summary["enemyRows"], 10)

    def test_best_effort_refresh_failure_is_nonfatal(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def failing_updater(*args: object, **kwargs: object) -> AbyssSourceDataRefreshResult:
            raise RuntimeError("network offline")

        summary, error = refresh_cached_abyss_source_data_for_hoyolab_period(
            period,
            updater=failing_updater,
        )

        self.assertIsNone(summary)
        self.assertEqual(error, "network offline")

    def test_failure_does_not_delete_existing_cache_file(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def failing_updater(*args: object, **kwargs: object) -> AbyssSourceDataRefreshResult:
            raise RuntimeError("nanoka down")

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "floor_12.json"
            cache_path.write_text("sentinel", encoding="utf-8")
            summary, error = refresh_cached_abyss_source_data_for_hoyolab_period(
                period,
                cache_dir=tmp,
                updater=failing_updater,
            )

            self.assertIsNone(summary)
            self.assertEqual(error, "nanoka down")
            self.assertEqual(cache_path.read_text(encoding="utf-8"), "sentinel")

    def test_update_helper_uses_build_update_report_by_default(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")
        with patch(
            "hoyolab_export.abyss_source_refresh.build_update_report",
            return_value={
                "summary": {
                    "enemy_rows": 10,
                    "matched": 10,
                    "unmatched": 0,
                    "ambiguous": 0,
                },
                "cache": {"saved": True, "path": "cache/floor_12.json"},
                "assets": {"enabled": True, "saved": 10},
            },
        ) as report_builder:
            result = update_cached_abyss_source_data_for_hoyolab_period(
                period,
                force=True,
            )

        report_builder.assert_called_once_with(
            period_start="2026-05-16",
            period_end="2026-06-16",
            floor=12,
            save_cache=True,
            cache_dir=None,
            cache_assets=True,
        )
        self.assertTrue(result.cache_saved)

    def test_update_helper_skips_when_same_period_cache_and_assets_are_ready(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=100)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Enemy",
                        chamber=1,
                        side=1,
                        hp=1_000_000,
                        monster_id="enemy",
                        level=100,
                    )
                ],
            ),
        )
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")
        with tempfile.TemporaryDirectory() as tmp:
            icon_result = cache_abyss_floor_monster_icons(
                source_data,
                cache_dir=tmp,
                icon_fetcher=lambda _url: b"icon",
            )
            save_abyss_floor_source_data(icon_result.data, cache_dir=tmp)

            result = update_cached_abyss_source_data_for_hoyolab_period(
                period,
                cache_dir=tmp,
                update_report_builder=lambda **_kwargs: self.fail(
                    "source update should be skipped"
                ),
            )

        self.assertTrue(result.skipped)
        self.assertFalse(result.cache_saved)
        self.assertEqual(result.skip_reason, "same_period_cache_and_assets_ready")
        self.assertEqual(result.enemy_rows, 1)
        self.assertEqual(result.matched, 1)

    def test_update_helper_force_refreshes_even_when_cache_is_ready(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=100)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Enemy",
                        chamber=1,
                        side=1,
                        hp=1_000_000,
                        monster_id="enemy",
                        level=100,
                    )
                ],
            ),
        )
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")
        with tempfile.TemporaryDirectory() as tmp:
            icon_result = cache_abyss_floor_monster_icons(
                source_data,
                cache_dir=tmp,
                icon_fetcher=lambda _url: b"icon",
            )
            save_abyss_floor_source_data(icon_result.data, cache_dir=tmp)

            result = update_cached_abyss_source_data_for_hoyolab_period(
                period,
                cache_dir=tmp,
                force=True,
                update_report_builder=lambda **_kwargs: {
                    "summary": {
                        "enemy_rows": 1,
                        "matched": 1,
                        "unmatched": 0,
                        "ambiguous": 0,
                    },
                    "cache": {"saved": True, "path": "cache/floor_12.json"},
                    "assets": {"enabled": True, "saved": 1},
                },
            )

        self.assertFalse(result.skipped)
        self.assertTrue(result.cache_saved)


if __name__ == "__main__":
    unittest.main()
