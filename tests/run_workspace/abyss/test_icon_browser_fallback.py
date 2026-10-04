from __future__ import annotations

import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from PIL import Image

from run_workspace.abyss.browser_image_fetcher import BrowserImageFetchResult
from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from run_workspace.abyss.source_data_cache import (
    AbyssIconBrowserRequired,
    cache_abyss_floor_monster_icons,
)
from tests.run_workspace.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


NAMES = ("Nanoka Success", "Browser One", "Browser Two", "Fandom HTTP")
FANDOM_URLS = tuple(
    f"https://static.wikia.nocookie.net/gensin-impact/images/a/a{i}/{i}.png"
    for i in range(len(NAMES))
)


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGBA", (2, 2)).save(stream, format="PNG")
    return stream.getvalue()


def _data():
    data = load_abyss_floor12_source_data(
        "2026-05-16", "119",
        composition_report=composition_report("2026-05-16", [
            fandom_row(name, chamber=1, side=1, wave=index + 1, count=index + 2)
            for index, name in enumerate(NAMES)
        ]),
        nanoka_report=nanoka_report("119", [
            nanoka_row(name, chamber=1, side=1, hp=1000 + index, monster_id=f"m{index}")
            for index, name in enumerate(NAMES)
        ]),
    )
    return replace(data, enemy_rows=tuple(
        replace(row, fandom_icon_url=FANDOM_URLS[index],
                nanoka_icon_url=row.nanoka_icon_url if index == 0 else None)
        for index, row in enumerate(data.enemy_rows)
    ))


class IconBrowserFallbackTest(unittest.TestCase):
    def test_one_batch_only_for_challenges_preserves_sources_and_cache_reuse(self):
        original = _data()
        payload = _png()
        http_calls = []
        browser_calls = []
        events = []

        def http_fetch(url):
            http_calls.append(url)
            if url in FANDOM_URLS[1:3]:
                raise AbyssIconBrowserRequired("browser verification required")
            return payload

        def browser_fetch(urls, *, max_concurrency):
            browser_calls.append((urls, max_concurrency))
            events.append(("browser", 0, 0))
            return BrowserImageFetchResult(images={url: payload for url in urls})

        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_workspace.abyss.source_data_cache._fetch_url_bytes", side_effect=http_fetch,
        ):
            result = cache_abyss_floor_monster_icons(
                original, cache_dir=tmp, catalog_fetcher=lambda _manifest: {},
                browser_fetcher=browser_fetch, max_workers=2,
                progress_callback=lambda _phase, done, total: events.append(("progress", done, total)),
            )
            first_http_calls = list(http_calls)
            second = cache_abyss_floor_monster_icons(
                result.data, cache_dir=tmp, catalog_fetcher=lambda _manifest: {},
                browser_fetcher=browser_fetch, max_workers=2,
            )
            for row in result.data.enemy_rows:
                with Image.open(row.cached_icon_path) as image:
                    image.verify()

        self.assertEqual(browser_calls, [((FANDOM_URLS[1], FANDOM_URLS[2]), 1)])
        self.assertEqual(http_calls, first_http_calls)
        self.assertEqual(http_calls.count(FANDOM_URLS[1]), 1)
        self.assertEqual(http_calls.count(FANDOM_URLS[2]), 1)
        self.assertEqual(result.downloaded, 4)
        self.assertEqual(result.failed, 0)
        self.assertEqual(second.cache_hits, 4)
        self.assertEqual([row.primary_display_name for row in result.data.enemy_rows], list(NAMES))
        for before, after in zip(original.enemy_rows, result.data.enemy_rows):
            for field in ("nanoka_hp", "nanoka_monster_id", "enemy_count", "wave", "chamber", "side"):
                self.assertEqual(getattr(after, field), getattr(before, field))
        browser_event = next(i for i, event in enumerate(events) if event[0] == "browser")
        self.assertTrue(all(done < total for kind, done, total in events[:browser_event]
                            if kind == "progress" and total))
        self.assertEqual(events[-1][1], events[-1][2])

    def test_partial_challenge_and_launch_error_stay_optional_without_http_retry(self):
        payload = _png()
        for launch_error in (False, True):
            with self.subTest(launch_error=launch_error), tempfile.TemporaryDirectory() as tmp:
                calls = []

                def http_fetch(url):
                    calls.append(url)
                    if url in FANDOM_URLS[1:3]:
                        raise AbyssIconBrowserRequired("browser verification required")
                    return payload

                def browser_fetch(urls, *, max_concurrency):
                    self.assertEqual(urls, FANDOM_URLS[1:3])
                    if launch_error:
                        raise RuntimeError("launch failed")
                    return BrowserImageFetchResult(
                        images={FANDOM_URLS[1]: payload},
                        errors={FANDOM_URLS[2]: "browser_verification_required"},
                    )

                original = _data()
                with patch("run_workspace.abyss.source_data_cache._fetch_url_bytes", side_effect=http_fetch):
                    result = cache_abyss_floor_monster_icons(
                        original, cache_dir=tmp, catalog_fetcher=lambda _manifest: {},
                        browser_fetcher=browser_fetch,
                    )
                self.assertEqual(calls.count(FANDOM_URLS[1]), 1)
                self.assertEqual(calls.count(FANDOM_URLS[2]), 1)
                self.assertEqual(result.failed, 2 if launch_error else 1)
                self.assertEqual(result.data.enemy_rows[0].nanoka_hp, original.enemy_rows[0].nanoka_hp)
                self.assertEqual(result.data.enemy_rows[2].enemy_count, original.enemy_rows[2].enemy_count)
                self.assertIsNone(result.data.enemy_rows[2].cached_icon_path)
                expected = "browser_unavailable:RuntimeError" if launch_error else "browser_verification_required"
                self.assertIn(expected, result.entries[2].warning)

    def test_injected_http_fetcher_stays_offline_without_browser_provider(self):
        calls = []

        def injected_fetch(url):
            calls.append(url)
            raise AbyssIconBrowserRequired("browser verification required")

        with tempfile.TemporaryDirectory() as tmp, patch(
            "run_workspace.abyss.browser_image_fetcher.fetch_public_fandom_images",
            side_effect=AssertionError("must stay offline"),
        ) as browser:
            result = cache_abyss_floor_monster_icons(
                _data(), cache_dir=tmp, catalog_fetcher=lambda _manifest: {},
                icon_fetcher=injected_fetch,
            )
        browser.assert_not_called()
        self.assertEqual(result.failed, 4)
        self.assertTrue(calls)

    def test_shared_executor_limits_browser_to_one_request_at_a_time(self):
        payload = _png()
        browser_calls = []

        def http_fetch(url):
            if url in FANDOM_URLS[1:3]:
                raise AbyssIconBrowserRequired("browser verification required")
            return payload

        def browser_fetch(urls, *, max_concurrency):
            browser_calls.append((urls, max_concurrency))
            return BrowserImageFetchResult(images={url: payload for url in urls})

        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=2) as executor, patch(
            "run_workspace.abyss.source_data_cache._fetch_url_bytes", side_effect=http_fetch,
        ):
            result = cache_abyss_floor_monster_icons(
                _data(), cache_dir=tmp, catalog_fetcher=lambda _manifest: {},
                browser_fetcher=browser_fetch, executor=executor,
            )
        self.assertEqual(browser_calls, [((FANDOM_URLS[1], FANDOM_URLS[2]), 1)])
        self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
