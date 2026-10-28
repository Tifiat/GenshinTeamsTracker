"""Controlled download/closure event fixtures for the production export path."""
import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from hoyolab_export.hoyolab_exporter import HoyolabExporter


class ExportDownloadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.exporter = HoyolabExporter(folder.name, folder.name)
        self.page = MagicMock()
        self.page.is_closed.return_value = False
        self.page.wait_for_timeout = AsyncMock()
        self.handlers = {}
        self.page.on.side_effect = lambda event, handler: self.handlers.update({event: handler})
        for method in ("_ensure_share_popover_open", "_clear_captured_canvas_state", "_debug_visible_blockers"):
            setattr(self.exporter, method, AsyncMock())
        self.exporter._html2canvas_call_count = AsyncMock(return_value=0)
        self.exporter._captured_canvas_download = AsyncMock(side_effect=RuntimeError("no canvas"))
        self.exporter._dom_root_screenshot_download = AsyncMock(side_effect=RuntimeError("no root"))

    async def immediate_wait(self, futures, **kwargs):
        # Explicit deterministic timeout fixture; no real elapsed-time promises.
        return {f for f in futures if f.done()}, {f for f in futures if not f.done()}

    async def immediate_wait_for(self, future, **kwargs):
        if future.done():
            return future.result()
        future.cancel()
        raise asyncio.TimeoutError

    async def test_missing_first_download_really_clicks_again(self):
        download = object()
        async def click(*args, **kwargs):
            if self.exporter._click_with_popup_retry.await_count == 2:
                self.handlers["download"](download)
        self.exporter._click_with_popup_retry = AsyncMock(side_effect=click)
        with patch("asyncio.wait", side_effect=self.immediate_wait), patch("asyncio.wait_for", side_effect=self.immediate_wait_for):
            result = await self.exporter._download_export_image_from_popover(self.page, ".fixture")
        self.assertIs(result, download)
        self.assertEqual(self.exporter._click_with_popup_retry.await_count, 2)
        self.exporter._dom_root_screenshot_download.assert_not_awaited()

    async def test_closed_page_does_not_wait_or_retry(self):
        async def click(*args, **kwargs):
            self.page.is_closed.return_value = True
            self.handlers["close"]()
        self.exporter._click_with_popup_retry = AsyncMock(side_effect=click)
        with self.assertRaisesRegex(RuntimeError, "closed.*download"):
            await self.exporter._download_export_image_from_popover(self.page, ".fixture")
        self.assertEqual(self.exporter._click_with_popup_retry.await_count, 1)
        self.exporter._captured_canvas_download.assert_not_awaited()
        self.page.wait_for_timeout.assert_not_awaited()
        removed = [call.args[0] for call in self.page.remove_listener.call_args_list]
        self.assertIn("download", removed)
        self.assertIn("close", removed)

    async def test_retries_stop_at_three_clicks(self):
        self.exporter._click_with_popup_retry = AsyncMock()
        with patch("asyncio.wait", side_effect=self.immediate_wait), patch("asyncio.wait_for", side_effect=self.immediate_wait_for):
            with self.assertRaises(RuntimeError):
                await self.exporter._download_export_image_from_popover(self.page, ".fixture")
        self.assertEqual(self.exporter._click_with_popup_retry.await_count, 3)

    async def test_crash_interrupts_pending_download_wait(self):
        async def click(*args, **kwargs):
            asyncio.get_running_loop().call_soon(self.handlers["crash"])
        self.exporter._click_with_popup_retry = AsyncMock(side_effect=click)
        # Real asyncio wait: the crash must wake it, not consume the 8s timeout.
        with self.assertRaisesRegex(RuntimeError, "crashed.*download"):
            await asyncio.wait_for(
                self.exporter._download_export_image_from_popover(self.page, ".fixture"),
                timeout=1,
            )
        self.assertEqual(self.exporter._click_with_popup_retry.await_count, 1)
        self.exporter._captured_canvas_download.assert_not_awaited()
