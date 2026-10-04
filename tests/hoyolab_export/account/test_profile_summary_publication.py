from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from hoyolab_export import import_pipeline as pipeline
from run_workspace.account_profiles import DuplicateAccountProfile


PROFILE_ID = "a" * 32
ATTEMPT_ID = "profile-summary-attempt"
UID = "700000001"
SERVER = "os_usa"
AVATAR_URL = "https://upload-os-bbs.hoyolab.com/avatar/game-head.png"


def _saved_attempt(*, side_icons_status="pending"):
    enrichment = {
        kind: {"status": "complete", "result": {}}
        for kind in ("projections", "assets", "references", "abyss")
    }
    enrichment["side_icons"] = {"status": side_icons_status, "result": {}}
    enrichment["abyss_period"] = {
        "status": "complete",
        "result": {"period": {
            "rawPeriod": "current", "startDate": "2026-10-01", "endDate": "2026-10-15",
            "sourcePath": "", "source": "fixture",
        }},
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "committed",
        "account_uid": UID,
        "server": SERVER,
        "source": {
            "account_characters": [],
            "account_weapons": [],
            "account_character_details": {"detectedLanguage": "en-us"},
        },
        "enrichment": enrichment,
    }


class ProfileSummaryPublicationTest(unittest.IsolatedAsyncioTestCase):
    def test_avatar_cache_validates_candidate_before_replacing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "assets" / "hoyolab" / "account" / "avatar.png"
            destination.parent.mkdir(parents=True)
            image_path = root / "fixture.png"
            Image.new("RGBA", (2, 2), (12, 34, 56, 255)).save(image_path)
            good_bytes = image_path.read_bytes()

            def download(_url, candidate):
                candidate.write_bytes(good_bytes)

            with patch.object(pipeline, "ACCOUNT_ROOT", root), \
                    patch.object(pipeline, "_download_url_to_file", side_effect=download) as downloader:
                relative = pipeline._cache_profile_avatar_sync(AVATAR_URL)
                self.assertEqual(relative, "assets/hoyolab/account/avatar.png")
                self.assertEqual(destination.read_bytes(), good_bytes)
                self.assertEqual(pipeline._cache_profile_avatar_sync(AVATAR_URL), relative)
                downloader.assert_called_once()

                previous_bytes = destination.read_bytes()
                with patch.object(pipeline, "_download_url_to_file",
                                  side_effect=lambda _url, candidate: candidate.write_bytes(b"broken")):
                    with self.assertRaises(ValueError):
                        pipeline._cache_profile_avatar_sync(AVATAR_URL, force=True)
                self.assertEqual(destination.read_bytes(), previous_bytes)
                self.assertEqual([path.name for path in destination.parent.iterdir()], ["avatar.png"])

    async def test_profile_projection_contains_only_allowlisted_fields_and_valid_path(self) -> None:
        profile = {"id": PROFILE_ID, "imported": False, "metadata": {"uid": UID, "server": SERVER}}
        written = {}

        def list_profiles():
            return [profile]

        def update_profile(profile_id, metadata, *, imported=None):
            profile["metadata"].update(metadata)
            if imported is not None:
                profile["imported"] = imported
            return profile

        def write_json(path, payload):
            written[Path(path).name] = payload

        summary = {
            "uid": UID, "server": SERVER, "nickname": "Traveler",
            "world_level": None, "adventure_rank": 60,
            "avatar_url": AVATAR_URL, "community_avatar": "must-not-persist",
        }
        future = asyncio.get_running_loop().create_future()
        future.set_result(summary)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "PROFILE_ID", PROFILE_ID))
            stack.enter_context(patch.object(pipeline, "ACCOUNT_ROOT", Path(tmp)))
            stack.enter_context(patch.object(pipeline, "HOYOLAB_DATA_DIR", Path(tmp) / "data" / "hoyolab"))
            stack.enter_context(patch.object(pipeline, "_image_is_usable", return_value=True))
            stack.enter_context(patch.object(pipeline, "_cache_profile_avatar_sync",
                                             return_value="assets/hoyolab/account/avatar.png"))
            stack.enter_context(patch.object(pipeline, "write_json", side_effect=write_json))
            stack.enter_context(patch("run_workspace.account_profiles.list_profiles", side_effect=list_profiles))
            stack.enter_context(patch("run_workspace.account_profiles.update_profile_metadata",
                                      side_effect=update_profile))
            result = await pipeline._refresh_profile_metadata(
                {"role_id": UID, "server": SERVER}, future,
            )

        self.assertFalse(result["pending"])
        self.assertTrue(profile["imported"])
        self.assertEqual(profile["metadata"]["avatar_path"], "assets/hoyolab/account/avatar.png")
        projection = written["account_summary.json"]
        self.assertEqual(projection["uid"], UID)
        self.assertEqual(projection["nickname"], "Traveler")
        self.assertEqual(projection["adventure_rank"], 60)
        self.assertEqual(projection["avatar_url"], AVATAR_URL)
        self.assertEqual(projection["avatar_path"], "assets/hoyolab/account/avatar.png")
        self.assertNotIn("community_avatar", projection)
        self.assertIsNone(projection["world_level"])

    async def test_failed_summary_is_reported_pending_without_failing_projection(self) -> None:
        future = asyncio.get_running_loop().create_future()
        future.set_exception(TimeoutError("fixture timeout"))
        profile = {"id": PROFILE_ID, "imported": True, "metadata": {"uid": UID, "server": SERVER}}
        writes = []
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "PROFILE_ID", PROFILE_ID))
            stack.enter_context(patch.object(pipeline, "ACCOUNT_ROOT", Path(tmp)))
            stack.enter_context(patch.object(pipeline, "HOYOLAB_DATA_DIR", Path(tmp) / "data"))
            stack.enter_context(patch.object(pipeline, "_profile_registry_entry", return_value=profile))
            stack.enter_context(patch.object(pipeline, "_update_profile_imported_metadata"))
            stack.enter_context(patch.object(pipeline, "_image_is_usable", return_value=False))
            stack.enter_context(patch.object(pipeline, "write_json", side_effect=lambda _path, body: writes.append(body)))

            result = await pipeline._refresh_profile_metadata(
                {"role_id": UID, "server": SERVER}, future,
            )

        self.assertTrue(result["pending"])
        self.assertEqual(result["pendingReason"], "network_profile_summary_unavailable")
        self.assertEqual(result["summaryError"], "TimeoutError")
        self.assertFalse(result["summaryAvailable"])
        self.assertEqual(writes[0]["uid"], UID)

    async def test_browser_context_closes_only_after_profile_summary_settles(self) -> None:
        gate = asyncio.Event()
        context = object()
        closed = []

        async def failing_summary():
            await gate.wait()
            raise TimeoutError("fixture timeout")

        async def record_close(value):
            closed.append(value)

        summary_task = asyncio.create_task(failing_summary())
        with patch.object(pipeline, "close_export_context", side_effect=record_close):
            close_task = asyncio.create_task(
                pipeline._close_context_after_sources(context, summary_task),
            )
            await asyncio.sleep(0)
            self.assertFalse(close_task.done())
            self.assertEqual(closed, [])
            gate.set()
            result = await close_task

        self.assertIsNone(result)
        self.assertEqual(closed, [context])

    async def test_changed_avatar_url_forces_a_fresh_validated_cache(self) -> None:
        profile = {"id": PROFILE_ID, "imported": True, "metadata": {"uid": UID, "server": SERVER}}
        profile_result = asyncio.get_running_loop().create_future()
        profile_result.set_result({"uid": UID, "server": SERVER, "avatar_url": AVATAR_URL})
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "PROFILE_ID", PROFILE_ID))
            stack.enter_context(patch.object(pipeline, "ACCOUNT_ROOT", Path(tmp)))
            stack.enter_context(patch.object(pipeline, "HOYOLAB_DATA_DIR", Path(tmp) / "data"))
            stack.enter_context(patch.object(pipeline, "_profile_registry_entry", return_value=profile))
            stack.enter_context(patch.object(pipeline, "_update_profile_imported_metadata"))
            cache = stack.enter_context(patch.object(
                pipeline, "_run_asset_thread", new_callable=AsyncMock,
                return_value="assets/hoyolab/account/avatar.png",
            ))
            stack.enter_context(patch.object(pipeline, "_image_is_usable", return_value=True))
            stack.enter_context(patch.object(pipeline, "write_json"))

            await pipeline._refresh_profile_metadata(
                {"role_id": UID, "server": SERVER}, profile_result,
                previous_avatar_url="https://upload-os-bbs.hoyolab.com/avatar/old.png",
            )

        self.assertTrue(cache.await_args.kwargs["force"])

    async def test_duplicate_profile_is_reported_before_staging(self) -> None:
        saved = _saved_attempt()
        profile = {"id": PROFILE_ID, "imported": False, "metadata": {}}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(output), ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "PROFILE_ID", PROFILE_ID))
            stack.enter_context(patch.object(pipeline, "ARTIFACT_DB_PATH", Path(tmp) / "account.db"))
            stack.enter_context(patch.object(pipeline, "ensure_hoyolab_dirs"))
            stack.enter_context(patch.object(pipeline, "cleanup_import_staging"))
            stack.enter_context(patch.object(pipeline, "get_import_attempt", return_value=saved))
            stack.enter_context(patch.object(pipeline, "get_import_result", return_value=None))
            stack.enter_context(patch.object(pipeline, "write_json"))
            stack.enter_context(patch("run_workspace.account_profiles.list_profiles", return_value=[profile]))
            update_profile = stack.enter_context(patch(
                "run_workspace.account_profiles.update_profile_metadata",
                side_effect=DuplicateAccountProfile("b" * 32),
            ))
            stage = stack.enter_context(patch.object(pipeline, "stage_import_attempt"))
            commit = stack.enter_context(patch.object(pipeline, "commit_import_snapshot"))
            with self.assertRaises(DuplicateAccountProfile):
                await pipeline.run_hoyolab_import(resume_attempt=ATTEMPT_ID)

        marker = next(line for line in output.getvalue().splitlines()
                      if line.startswith("[PROFILE_DUPLICATE] "))
        self.assertEqual(
            marker,
            '[PROFILE_DUPLICATE] {"existing_profile_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
        )
        update_profile.assert_called_once_with(PROFILE_ID, {"uid": UID, "server": SERVER}, imported=False)
        stage.assert_not_called()
        commit.assert_not_called()

    async def test_postcommit_metadata_and_avatar_failures_remain_recoverable(self) -> None:
        saved = _saved_attempt()
        receipt = {"artifacts": {}, "account_storage": {}, "equipment": {}}
        profile = {
            "id": PROFILE_ID,
            "imported": False,
            "metadata": {"uid": UID, "server": SERVER, "avatar_url": AVATAR_URL},
        }
        update_calls = []

        def update_profile(profile_id, metadata, *, imported=None):
            update_calls.append((profile_id, dict(metadata), imported))
            if len(update_calls) == 2:
                raise OSError("registry temporarily unavailable")
            return {"id": profile_id, "imported": bool(imported), "metadata": dict(profile["metadata"])}

        written = {}

        def write_json(path, payload):
            written[Path(path).name] = payload

        async def side_icons_with_profile(*, progress_callback=None, extra_work=None):
            profile_result = await extra_work() if extra_work else {"pending": False}
            return {"downloaded": 0, "pending": profile_result.get("pending", False),
                    "profileMetadata": profile_result}

        def record_enrichment(_db, *, attempt_id, kind, status, result):
            saved["enrichment"][kind] = {"status": status, "result": result}

        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "PROFILE_ID", PROFILE_ID))
            stack.enter_context(patch.object(pipeline, "ACCOUNT_ROOT", Path(tmp)))
            stack.enter_context(patch.object(pipeline, "HOYOLAB_DATA_DIR", Path(tmp) / "data" / "hoyolab"))
            stack.enter_context(patch.object(pipeline, "HOYOLAB_DEBUG_DIR", Path(tmp) / "debug"))
            stack.enter_context(patch.object(pipeline, "ARTIFACT_DB_PATH", Path(tmp) / "account.db"))
            stack.enter_context(patch.object(pipeline, "ensure_hoyolab_dirs"))
            stack.enter_context(patch.object(pipeline, "cleanup_import_staging"))
            stack.enter_context(patch.object(pipeline, "get_import_attempt", return_value=saved))
            stack.enter_context(patch.object(pipeline, "get_import_result", return_value=None))
            stack.enter_context(patch.object(pipeline, "latest_committed_import", return_value=saved))
            stack.enter_context(patch.object(pipeline, "commit_import_snapshot", return_value=receipt))
            stack.enter_context(patch.object(pipeline, "update_import_enrichment", side_effect=record_enrichment))
            stack.enter_context(patch.object(pipeline, "refresh_import_side_icons", side_effect=side_icons_with_profile))
            stack.enter_context(patch.object(pipeline, "_cache_profile_avatar_sync", side_effect=OSError("offline")))
            stack.enter_context(patch.object(pipeline, "_image_is_usable", return_value=False))
            stack.enter_context(patch.object(pipeline, "write_json", side_effect=write_json))
            stack.enter_context(patch.object(
                pipeline, "fetch_account_summary", side_effect=AssertionError("resume must not fetch"),
            ))
            stack.enter_context(patch("run_workspace.account_profiles.list_profiles", return_value=[profile]))
            stack.enter_context(patch(
                "run_workspace.account_profiles.update_profile_metadata", side_effect=update_profile,
            ))
            result = await pipeline.run_hoyolab_import(resume_attempt=ATTEMPT_ID)

        self.assertEqual(result["status"], "committed")
        self.assertIn("side_icons", result["pendingJobs"])
        self.assertEqual(saved["enrichment"]["side_icons"]["status"], "pending")
        self.assertEqual([call[2] for call in update_calls], [False, True, True])
        self.assertIn("account_summary.json", written)
        summary = written["account_summary.json"]
        self.assertEqual(summary["uid"], UID)
        self.assertEqual(summary["server"], SERVER)
        self.assertEqual(summary["avatar_url"], AVATAR_URL)
        self.assertNotIn("avatar_path", summary)


if __name__ == "__main__":
    unittest.main()
