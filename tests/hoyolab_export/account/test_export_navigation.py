"""Regression fixtures for navigation during HoYoLAB export startup."""
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from playwright.async_api import Error as PlaywrightError

from hoyolab_export.hoyolab_exporter import HoyolabExporter, LoginRequiredError


def navigation_error():
    return PlaywrightError(
        "Page.evaluate: Execution context was destroyed, most likely because of a navigation"
    )


class ExportNavigationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.exporter = HoyolabExporter(self.folder.name, self.folder.name)
        self.page = MagicMock()
        self.page.wait_for_load_state = AsyncMock()
        self.page.wait_for_timeout = AsyncMock()
        self.page.is_closed.return_value = False
        self.page.locator.return_value.first.is_visible = AsyncMock(return_value=True)
        self.page.locator.return_value.count = AsyncMock(return_value=1)
        self.exporter._is_login_open = AsyncMock(return_value=False)
        self.exporter._dismiss_known_popups = AsyncMock()

    async def test_startup_navigation_rechecks_readiness_before_click(self):
        self.exporter._dismiss_known_popups.side_effect = [navigation_error(), False]
        await self.exporter._wait_until_ready_or_login(self.page)
        self.assertEqual(self.exporter._dismiss_known_popups.await_count, 2)
        self.assertGreaterEqual(self.exporter._is_login_open.await_count, 2)

    async def test_navigation_retries_are_bounded(self):
        self.exporter._dismiss_known_popups.side_effect = navigation_error()
        with self.assertRaises(PlaywrightError):
            await self.exporter._wait_until_ready_or_login(self.page)
        self.assertEqual(self.exporter._dismiss_known_popups.await_count, 3)

    async def test_other_errors_are_not_retried(self):
        self.exporter._dismiss_known_popups.side_effect = PlaywrightError("page closed")
        with self.assertRaisesRegex(PlaywrightError, "page closed"):
            await self.exporter._wait_until_ready_or_login(self.page)
        self.assertEqual(self.exporter._dismiss_known_popups.await_count, 1)

    async def test_login_is_reported_before_popup_dismissal(self):
        self.exporter._is_login_open.return_value = True
        with self.assertRaises(LoginRequiredError):
            await self.exporter._wait_until_ready_or_login(self.page)
        self.exporter._dismiss_known_popups.assert_not_awaited()

    async def test_cleanup_does_not_mask_original_export_error(self):
        self.exporter._wait_until_ready_or_login = AsyncMock()
        self.exporter._click_with_popup_retry = AsyncMock(side_effect=RuntimeError("original click failure"))
        self.page.evaluate = AsyncMock(side_effect=[None, navigation_error()])
        with self.assertRaisesRegex(RuntimeError, "original click failure"):
            await self.exporter._run_export_flow(self.page)

    async def test_trusted_click_has_no_javascript_cleanup_after_navigation(self):
        locator = self.page.locator.return_value.first
        locator.wait_for = AsyncMock()
        locator.click = AsyncMock(side_effect=RuntimeError("original click failure"))
        self.page.evaluate = AsyncMock(side_effect=[None, navigation_error()])
        with self.assertRaisesRegex(RuntimeError, "original click failure"):
            await self.exporter._trusted_click(self.page, ".block-title-right")

    async def test_popup_cleanup_keeps_original_click_failure(self):
        self.exporter._dismiss_known_popups.side_effect = [False, navigation_error()]
        self.exporter._trusted_click = AsyncMock(side_effect=RuntimeError("original click failure"))
        with self.assertRaisesRegex(RuntimeError, "original click failure"):
            await self.exporter._click_with_popup_retry(self.page, ".block-title-right")

    async def test_observed_current_and_legacy_export_calls_capture_the_correct_root(self):
        for call, root in (("p()(e,r)", "e"), ("f()(t,r)", "t")):
            with self.subTest(call=call):
                route = MagicMock()
                route.fulfill = AsyncMock()
                self.exporter._fetch_route_js_body = AsyncMock(
                    return_value="r={useCORS:!0,backgroundColor:null,scale:2};" + call
                )
                await self.exporter._patch_js_route(route, MagicMock(url="https://fixture.test/r_m_ys_all_hash.js"))
                body = route.fulfill.call_args.kwargs["body"]
                self.assertIn(f"__gtt_capture_html2canvas_root__({root},r,", body)
                self.assertIn(call + ".then(function(c)", body)
                self.assertIn("scale:4", body)
                self.assertIn("width:376", body)

    async def test_current_character_list_bundle_is_intercepted(self):
        self.page.route = AsyncMock()
        await self.exporter._prepare_export_page(self.page)
        self.page.route.assert_any_await("**/r_m_ys_all_*.js", self.exporter._patch_js_route)
