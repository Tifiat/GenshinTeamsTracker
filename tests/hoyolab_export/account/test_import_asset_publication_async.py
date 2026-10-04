"""Asset publication keeps staging alive until its worker drains on cancellation."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hoyolab_export import import_pipeline


class ImportAssetPublicationAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_publication_does_not_block_loop_or_delete_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "debug"
            debug_dir.mkdir()
            started = threading.Event()
            release = threading.Event()
            finished = threading.Event()
            staging_root: Path | None = None
            worker_thread_id: int | None = None
            loop_thread_id = threading.get_ident()

            async def prepare(**kwargs):
                nonlocal staging_root
                staging_root = kwargs["staging_root"]
                (staging_root / "fixture.marker").write_text("staged", encoding="utf-8")
                return {"cardsCount": 1}

            def publish(manifest, staging, attempt_id):
                nonlocal worker_thread_id
                worker_thread_id = threading.get_ident()
                self.assertEqual(attempt_id, "fixture-attempt")
                self.assertEqual(manifest["cardsCount"], 1)
                self.assertTrue((staging / "fixture.marker").is_file())
                started.set()
                try:
                    if not release.wait(timeout=5):
                        raise AssertionError("publication worker was never released")
                    self.assertTrue(staging.exists())
                    return {"manifest": manifest, "pending": False}
                finally:
                    finished.set()

            with patch.object(import_pipeline, "HOYOLAB_DEBUG_DIR", debug_dir), \
                 patch.object(import_pipeline, "prepare_layered_assets", side_effect=prepare), \
                 patch.object(import_pipeline, "_publish_import_assets", side_effect=publish):
                task = asyncio.create_task(import_pipeline.refresh_import_assets(
                    [], [], attempt_id="fixture-attempt",
                ))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    self.assertNotEqual(worker_thread_id, loop_thread_id)
                    # A timer on the same event loop must still fire while the
                    # publication thread is blocked on the release event.
                    await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.5)
                    self.assertFalse(task.done())
                    self.assertIsNotNone(staging_root)
                    assert staging_root is not None

                    task.cancel()
                    await asyncio.sleep(0.02)
                    self.assertFalse(task.done())
                    self.assertTrue((staging_root / "fixture.marker").is_file())

                    task.cancel()
                    await asyncio.sleep(0.02)
                    self.assertFalse(task.done())
                    self.assertTrue((staging_root / "fixture.marker").is_file())
                    self.assertFalse(finished.is_set())
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, timeout=3)

            self.assertTrue(finished.is_set())
            assert staging_root is not None
            self.assertFalse(staging_root.exists())


if __name__ == "__main__":
    unittest.main()
