from __future__ import annotations

import asyncio
import io
import unittest
from unittest.mock import patch

from PIL import Image

from run_workspace.abyss.browser_image_fetcher import (
    BrowserImageFetchError,
    fetch_public_fandom_images,
    fetch_public_fandom_images_in_context,
)


PERIOD = "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors"
IMAGE_A = "https://static.wikia.nocookie.net/gensin-impact/images/a/a1/One.png"
IMAGE_B = "https://static.wikia.nocookie.net/gensin-impact/images/b/b2/Two.png"


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (2, 2)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, *, status=200, headers=None, body=None, body_delay=0, final_url=None):
        self.status = status
        self.headers = headers or {}
        self.payload = body if body is not None else png_bytes()
        self.body_delay = body_delay
        self.url = final_url

    async def all_headers(self):
        return self.headers

    async def body(self):
        await asyncio.sleep(self.body_delay)
        return self.payload


class FakePage:
    def __init__(self, owner):
        self.owner = owner
        self.closed = False

    async def goto(self, url, **_kwargs):
        self.owner.visits.append(url)
        self.owner.active += 1
        self.owner.peak = max(self.owner.peak, self.owner.active)
        try:
            await asyncio.sleep(self.owner.delay)
            response = self.owner.responses[url]
            if response.url is None:
                response.url = url
            return response
        finally:
            self.owner.active -= 1

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, owner):
        self.owner = owner
        self.pages = []
        self.closed = False

    async def new_page(self):
        page = FakePage(self.owner)
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, owner):
        self.owner = owner
        self.context = FakeContext(owner)
        self.closed = False

    async def new_context(self):
        return self.context

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, owner):
        self.owner = owner
        self.launches = []

    async def launch(self, **kwargs):
        self.launches.append(kwargs)
        if self.owner.launch_error:
            raise RuntimeError("launch failed")
        return self.owner.browser


class FakePlaywright:
    def __init__(self, responses, *, delay=0, launch_error=False):
        self.responses = responses
        self.delay = delay
        self.launch_error = launch_error
        self.visits = []
        self.active = 0
        self.peak = 0
        self.browser = FakeBrowser(self)
        self.chromium = FakeChromium(self)
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
        return self.playwright


class BrowserImageFetcherTest(unittest.TestCase):
    def _fetch(self, playwright, urls, **kwargs):
        with patch("run_workspace.abyss.browser_image_fetcher.find_browser_exe", return_value=__file__), patch(
            "run_workspace.abyss.browser_image_fetcher.async_playwright",
            return_value=FakePlaywrightStarter(playwright),
        ):
            return fetch_public_fandom_images(urls, **kwargs)

    def test_one_isolated_browser_visits_period_once_and_limits_image_pages(self):
        playwright = FakePlaywright({PERIOD: FakeResponse(), IMAGE_A: FakeResponse(), IMAGE_B: FakeResponse()}, delay=0.01)
        result = self._fetch(playwright, [IMAGE_A, IMAGE_B, IMAGE_A], period_url=PERIOD)
        self.assertEqual(set(result.images), {IMAGE_A, IMAGE_B})
        self.assertEqual(result.errors, {})
        self.assertEqual(playwright.visits.count(PERIOD), 1)
        self.assertEqual(playwright.visits.count(IMAGE_A), 1)
        self.assertLessEqual(playwright.peak, 2)
        self.assertEqual(len(playwright.chromium.launches), 1)
        self.assertFalse(playwright.chromium.launches[0]["headless"])
        self.assertTrue(playwright.browser.context.closed)
        self.assertTrue(playwright.browser.closed)
        self.assertTrue(playwright.stopped)
        self.assertTrue(all(page.closed for page in playwright.browser.context.pages))

    def test_challenge_is_per_url_and_invalid_payload_is_rejected(self):
        playwright = FakePlaywright({
            IMAGE_A: FakeResponse(status=403, headers={"cf-mitigated": "challenge"}),
            IMAGE_B: FakeResponse(body=b"<html>challenge</html>"),
        })
        result = self._fetch(playwright, [IMAGE_A, IMAGE_B])
        self.assertEqual(result.images, {})
        self.assertEqual(result.errors[IMAGE_A], "browser_verification_required")
        self.assertEqual(result.errors[IMAGE_B], "invalid_image")
        self.assertEqual(playwright.visits.count(IMAGE_A), 1)

    def test_borrowed_context_keeps_caller_browser_and_context_open(self):
        playwright = FakePlaywright({IMAGE_A: FakeResponse()})
        result = asyncio.run(fetch_public_fandom_images_in_context(
            playwright.browser.context, [IMAGE_A],
        ))
        self.assertIn(IMAGE_A, result.images)
        self.assertFalse(playwright.browser.context.closed)
        self.assertFalse(playwright.browser.closed)
        self.assertFalse(playwright.stopped)
        self.assertTrue(all(page.closed for page in playwright.browser.context.pages))

    def test_borrowed_context_remains_open_after_timeout(self):
        playwright = FakePlaywright({IMAGE_A: FakeResponse()}, delay=0.2)
        result = asyncio.run(fetch_public_fandom_images_in_context(
            playwright.browser.context, [IMAGE_A], total_timeout_s=0.02,
        ))
        self.assertEqual(result.errors[IMAGE_A], "batch_timeout")
        self.assertFalse(playwright.browser.context.closed)
        self.assertFalse(playwright.browser.closed)
        self.assertTrue(all(page.closed for page in playwright.browser.context.pages))

    def test_period_challenge_is_recorded_but_exact_images_remain_independent(self):
        playwright = FakePlaywright({
            PERIOD: FakeResponse(status=403, headers={"cf-mitigated": "challenge"}),
            IMAGE_A: FakeResponse(),
        })
        result = self._fetch(playwright, [IMAGE_A], period_url=PERIOD)
        self.assertEqual(result.period_error, "period_browser_verification_required")
        self.assertIn(IMAGE_A, result.images)
        self.assertEqual(playwright.visits, [PERIOD, IMAGE_A])

    def test_period_redirect_outside_fandom_route_is_reported(self):
        playwright = FakePlaywright({
            PERIOD: FakeResponse(final_url="https://example.test/other"),
            IMAGE_A: FakeResponse(),
        })
        result = self._fetch(playwright, [IMAGE_A], period_url=PERIOD)
        self.assertEqual(result.period_error, "period_redirected_to_unsupported_url")
        self.assertIn(IMAGE_A, result.images)

    def test_total_timeout_reports_pending_and_closes_browser(self):
        playwright = FakePlaywright({IMAGE_A: FakeResponse()}, delay=0.2)
        result = self._fetch(playwright, [IMAGE_A], total_timeout_s=0.02)
        self.assertEqual(result.errors[IMAGE_A], "batch_timeout")
        self.assertTrue(playwright.browser.context.closed)
        self.assertTrue(playwright.browser.closed)
        self.assertTrue(playwright.stopped)

    def test_individual_timeout_bounds_response_body(self):
        playwright = FakePlaywright({IMAGE_A: FakeResponse(body_delay=0.2)})
        result = self._fetch(
            playwright, [IMAGE_A], individual_timeout_s=0.02, total_timeout_s=1,
        )
        self.assertEqual(result.errors[IMAGE_A], "navigation_timeout")
        self.assertTrue(playwright.browser.context.closed)

    def test_launch_and_url_validation_are_explicit(self):
        playwright = FakePlaywright({IMAGE_A: FakeResponse()}, launch_error=True)
        with self.assertRaisesRegex(BrowserImageFetchError, "launch failed"):
            self._fetch(playwright, [IMAGE_A])
        self.assertTrue(playwright.stopped)
        with patch(
            "run_workspace.abyss.browser_image_fetcher.find_browser_exe",
            side_effect=FileNotFoundError("no supported browser"),
        ):
            with self.assertRaisesRegex(BrowserImageFetchError, "executable was not found"):
                fetch_public_fandom_images([IMAGE_A])
        valid = FakePlaywright({IMAGE_A: FakeResponse()})
        result = self._fetch(valid, ["http://static.wikia.nocookie.net/icon.png", IMAGE_A])
        self.assertEqual(result.errors["http://static.wikia.nocookie.net/icon.png"], "unsupported_image_url")
        self.assertIn(IMAGE_A, result.images)

    def test_credential_port_path_and_redirect_are_rejected(self):
        invalid_urls = [
            "https://user:pass@static.wikia.nocookie.net/gensin-impact/images/a.png",
            "https://static.wikia.nocookie.net:443/gensin-impact/images/a.png",
            "https://static.wikia.nocookie.net/other/images/a.png",
            "https://static.wikia.nocookie.net/gensin-impact/images/../other.png",
            "https://static.wikia.nocookie.net/gensin-impact/images/%2e%2e/other.png",
        ]
        playwright = FakePlaywright({IMAGE_A: FakeResponse(final_url="https://example.test/stolen.png")})
        result = self._fetch(playwright, [*invalid_urls, IMAGE_A])
        self.assertEqual({url: result.errors[url] for url in invalid_urls},
                         {url: "unsupported_image_url" for url in invalid_urls})
        self.assertEqual(result.errors[IMAGE_A], "redirected_to_unsupported_url")
        self.assertEqual(playwright.visits, [IMAGE_A])
        with self.assertRaisesRegex(ValueError, "period_url"):
            self._fetch(FakePlaywright({IMAGE_A: FakeResponse()}), [IMAGE_A],
                        period_url="https://user@genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors")


if __name__ == "__main__":
    unittest.main()
