from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.abyss_source_refresh import (
    AbyssSourceDataRefreshResult,
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    HoYoLABAbyssPeriodError,
    HoYoLABAbyssPeriod,
    fetch_hoyolab_spiral_abyss_period,
    extract_hoyolab_abyss_period,
    parse_hoyolab_abyss_period,
    resolve_abyss_period_with_fallbacks,
    refresh_cached_abyss_source_data_for_hoyolab_period,
    update_cached_abyss_source_data_for_hoyolab_period,
    write_hoyolab_abyss_period,
)
from hoyolab_export.import_pipeline import refresh_abyss_source_data_for_import
from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import (
    cache_abyss_floor_monster_icons,
    save_abyss_floor_source_data,
)
from run_workspace.abyss.source_data_runtime import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH as RUNTIME_HOYOLAB_ABYSS_PERIOD_PATH,
)
from run_workspace.abyss.source_data_fetchers import ResolvedAbyssPeriodSource
from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


class _FakeAPIResponse:
    def __init__(self, url: str, payload: dict[str, object], *, status: int = 200) -> None:
        self.url = url
        self.status = status
        self.status_text = "OK" if status == 200 else "Error"
        self._payload = payload

    async def text(self) -> str:
        return json.dumps(self._payload)


class _FakeRequest:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    async def get(self, url: str, *, headers: dict[str, str] | None = None):
        self.calls.append({"method": "GET", "url": url, "headers": headers or {}})
        payload = self._payloads.pop(0)
        return _FakeAPIResponse(url, payload)

    async def post(self, url: str, *, headers: dict[str, str] | None = None, data: str = ""):
        self.calls.append(
            {"method": "POST", "url": url, "headers": headers or {}, "data": data}
        )
        payload = self._payloads.pop(0)
        return _FakeAPIResponse(url, payload)


class _FakeContext:
    def __init__(self, request: _FakeRequest) -> None:
        self.request = request

    async def cookies(self):
        return [{"name": "mi18nLang", "value": "ru-ru"}]


class _FakePage:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.request = _FakeRequest(payloads)
        self.context = _FakeContext(self.request)
        self.evaluate_calls = 0

    async def evaluate(self, *_args, **_kwargs):
        self.evaluate_calls += 1
        raise AssertionError("page.evaluate should not be used for Abyss period fetch")


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

    def test_extracts_period_from_hoyolab_epoch_fields(self) -> None:
        period = extract_hoyolab_abyss_period(
            {
                "retcode": 0,
                "data": {
                    "start_time": "1778900400",
                    "end_time": "1781578799",
                },
            }
        )

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")
        self.assertEqual(period.source_path, "$.data")


class HoYoLABAbyssSourceRefreshTest(unittest.TestCase):
    def test_period_resolver_hoyolab_success_wins_without_fallback_calls(self) -> None:
        calls: list[str] = []

        async def fake_hoyolab_fetcher(_page: object, *, language: str | None = None):
            calls.append(f"hoyolab:{language}")
            return parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def fallback_should_not_run():
            raise AssertionError("fallback resolver should not run")

        period = asyncio.run(
            resolve_abyss_period_with_fallbacks(
                object(),
                language="ru-ru",
                hoyolab_fetcher=fake_hoyolab_fetcher,
                nanoka_live_resolver=fallback_should_not_run,
                fandom_latest_resolver=fallback_should_not_run,
            )
        )

        self.assertEqual(period.source, "hoyolab_spiral_abyss_overview")
        self.assertFalse(period.fallback)
        self.assertEqual(period.warnings, ())
        self.assertEqual(calls, ["hoyolab:ru-ru"])

    def test_period_resolver_falls_back_to_fandom_latest_first(self) -> None:
        async def failing_hoyolab_fetcher(_page: object, *, language: str | None = None):
            raise RuntimeError("hoyolab navigation failed")

        period = asyncio.run(
            resolve_abyss_period_with_fallbacks(
                object(),
                hoyolab_fetcher=failing_hoyolab_fetcher,
                nanoka_live_resolver=lambda: self.fail("nanoka should not run"),
                fandom_latest_resolver=lambda: ResolvedAbyssPeriodSource(
                    raw_period="2026-05-16/2026-06-16",
                    start_date="2026-05-16",
                    end_date="2026-06-16",
                    source="fandom_latest_fallback",
                    source_path="fandom_index#latest",
                    warnings=("fandom_latest_used_as_period_fallback",),
                ),
            )
        )

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.source, "fandom_latest_fallback")
        self.assertTrue(period.fallback)
        self.assertIn("fandom_latest_used_as_period_fallback", period.warnings)
        self.assertTrue(
            any(
                warning.startswith("hoyolab_spiral_abyss_overview_failed:")
                for warning in period.warnings
            )
        )

    def test_period_resolver_falls_back_to_nanoka_live_after_fandom_failure(self) -> None:
        async def failing_hoyolab_fetcher(_page: object, *, language: str | None = None):
            raise RuntimeError("hoyolab down")

        def failing_fandom():
            raise RuntimeError("fandom down")

        period = asyncio.run(
            resolve_abyss_period_with_fallbacks(
                object(),
                hoyolab_fetcher=failing_hoyolab_fetcher,
                nanoka_live_resolver=lambda: ResolvedAbyssPeriodSource(
                    raw_period="2026-05-16/2026-06-16",
                    start_date="2026-05-16",
                    end_date="2026-06-16",
                    source="nanoka_live_fallback",
                    source_path="nanoka_manifest#tower[119]",
                    metadata={"tower_id": "119"},
                ),
                fandom_latest_resolver=failing_fandom,
            )
        )

        self.assertEqual(period.source, "nanoka_live_fallback")
        self.assertTrue(period.fallback)
        self.assertIn("tower_id", period.source_metadata)
        self.assertTrue(
            any(warning.startswith("fandom_latest_fallback_failed:") for warning in period.warnings)
        )

    def test_period_resolver_all_sources_fail_controlled(self) -> None:
        async def failing_hoyolab_fetcher(_page: object, *, language: str | None = None):
            raise RuntimeError("hoyolab down")

        with self.assertRaises(HoYoLABAbyssPeriodError) as cm:
            asyncio.run(
                resolve_abyss_period_with_fallbacks(
                    object(),
                    hoyolab_fetcher=failing_hoyolab_fetcher,
                    nanoka_live_resolver=lambda: (_ for _ in ()).throw(RuntimeError("nanoka down")),
                    fandom_latest_resolver=lambda: (_ for _ in ()).throw(RuntimeError("fandom down")),
                )
            )

        message = str(cm.exception)
        self.assertIn("Could not resolve Spiral Abyss period", message)
        self.assertIn("hoyolab_spiral_abyss_overview_failed", message)
        self.assertIn("nanoka_live_fallback_failed", message)
        self.assertIn("fandom_latest_fallback_failed", message)

    def test_fallback_period_writer_records_source_and_warnings(self) -> None:
        period = HoYoLABAbyssPeriod(
            raw_period="2026-05-16/2026-06-16",
            start_date="2026-05-16",
            end_date="2026-06-16",
            source_path="nanoka_manifest#tower[119]",
            source="nanoka_live_fallback",
            warnings=("hoyolab_spiral_abyss_overview_failed:offline",),
            fallback=True,
            source_metadata={"tower_id": "119"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_hoyolab_abyss_period(
                period,
                period_path=Path(tmp) / "spiral_abyss_period.json",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["source"], "nanoka_live_fallback")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["sourceMetadata"]["tower_id"], "119")
        self.assertEqual(
            payload["warnings"],
            ["hoyolab_spiral_abyss_overview_failed:offline"],
        )

    def test_abyss_period_fetch_uses_context_request_instead_of_page_evaluate(self) -> None:
        page = _FakePage(
            [
                {
                    "retcode": 0,
                    "data": {
                        "list": [
                            {
                                "game_biz": "hk4e_global",
                                "game_uid": "700000001",
                                "region": "os_euro",
                            }
                        ]
                    },
                },
                {
                    "retcode": 0,
                    "data": {
                        "schedule": {
                            "period": "2026/05/16-2026/06/16",
                        }
                    },
                },
            ]
        )

        period = asyncio.run(fetch_hoyolab_spiral_abyss_period(page))

        self.assertEqual(period.start_date, "2026-05-16")
        self.assertEqual(period.end_date, "2026-06-16")
        self.assertEqual(page.evaluate_calls, 0)
        self.assertEqual(len(page.request.calls), 2)
        self.assertIn("getUserGameRolesByCookie", str(page.request.calls[0]["url"]))
        self.assertIn("spiralAbyss", str(page.request.calls[1]["url"]))
        self.assertEqual(
            page.request.calls[0]["headers"]["x-rpc-language"],
            "ru-ru",
        )

    def test_abyss_period_fetch_reports_hoyolab_api_failure_readably(self) -> None:
        page = _FakePage(
            [
                {
                    "retcode": -100,
                    "message": "Please login",
                },
            ]
        )

        with self.assertRaises(HoYoLABAbyssPeriodError) as cm:
            asyncio.run(fetch_hoyolab_spiral_abyss_period(page))

        self.assertIn("HoYoLAB roles failed", str(cm.exception))
        self.assertIn("retcode=-100", str(cm.exception))

    def test_fetched_abyss_period_can_be_written_for_runtime(self) -> None:
        page = _FakePage(
            [
                {
                    "retcode": 0,
                    "data": {
                        "list": [
                            {
                                "game_biz": "hk4e_global",
                                "game_uid": "700000001",
                                "region": "os_euro",
                            }
                        ]
                    },
                },
                {
                    "retcode": 0,
                    "data": {
                        "schedule": {
                            "period": "2026/05/16-2026/06/16",
                        }
                    },
                },
            ]
        )

        period = asyncio.run(fetch_hoyolab_spiral_abyss_period(page))
        with tempfile.TemporaryDirectory() as tmp:
            path = write_hoyolab_abyss_period(
                period,
                period_path=Path(tmp) / "spiral_abyss_period.json",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["startDate"], "2026-05-16")
        self.assertEqual(payload["endDate"], "2026-06-16")

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
                "probe": {
                    "timings_ms": {
                        "fandom_composition_fetch_parse": 5.0,
                        "nanoka_source_fetch_parse": 7.0,
                        "join_build_source_data": 1.0,
                        "icon_asset_cache": 2.0,
                        "json_cache_save": 0.5,
                        "total": 15.5,
                    }
                },
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
        self.assertEqual(result.timings_ms["icon_asset_cache"], 2.0)
        self.assertEqual(result.to_dict()["timingsMs"]["total"], 15.5)

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
            hp_source_mode: str = "auto",
            hp_multiplier: float = 3.75,
            fandom_hp_workers: int = 5,
        ) -> AbyssSourceDataRefreshResult:
            calls.append(
                {
                    "period": update_period,
                    "floor": floor,
                    "cache_dir": cache_dir,
                    "cache_assets": cache_assets,
                    "force": force,
                    "hp_source_mode": hp_source_mode,
                    "hp_multiplier": hp_multiplier,
                    "fandom_hp_workers": fandom_hp_workers,
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

    def test_import_refresh_helper_calls_abyss_refresh_once_and_reports_status(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")
        calls: list[HoYoLABAbyssPeriod] = []
        statuses: list[str] = []

        def fake_refresher(update_period: HoYoLABAbyssPeriod, *, floor: int = 12):
            calls.append(update_period)
            return (
                {
                    "enemyRows": 10,
                    "matched": 10,
                    "skipped": False,
                    "assets": {"enabled": True},
                },
                None,
            )

        summary, error = refresh_abyss_source_data_for_import(
            period,
            status_callback=statuses.append,
            refresher=fake_refresher,
        )

        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(summary)
        self.assertEqual(statuses[0], "updating_abyss_source_data")
        self.assertIn("caching_abyss_monster_icons", statuses)

    def test_import_refresh_helper_keeps_abyss_refresh_failure_nonfatal(self) -> None:
        period = parse_hoyolab_abyss_period("2026/05/16-2026/06/16")

        def fake_refresher(update_period: HoYoLABAbyssPeriod, *, floor: int = 12):
            return None, "nanoka down"

        summary, error = refresh_abyss_source_data_for_import(
            period,
            status_callback=None,
            refresher=fake_refresher,
        )

        self.assertIsNone(summary)
        self.assertEqual(error, "nanoka down")

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
            hp_source_mode="auto",
            hp_multiplier=3.75,
            fandom_hp_workers=5,
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
        self.assertIn("cache_ready_lookup", result.timings_ms)
        self.assertIn("total", result.timings_ms)

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
