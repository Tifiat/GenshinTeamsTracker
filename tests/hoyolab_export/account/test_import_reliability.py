"""Isolated import fault fixtures; network/crops are simulated, SQLite writes are real.

These pin the existing account/equipment contracts, not a full HoYoLAB simulator.
"""
import asyncio
from copy import deepcopy
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hoyolab_export import import_pipeline as pipeline
from hoyolab_export.account_equipment import equip_artifact, equip_weapon
from hoyolab_export.account_storage import sync_account_storage_from_sources
from hoyolab_export.artifact_db import connect_db, init_db, create_build_preset
from hoyolab_export.artifact_importer import import_character_details_payload
from hoyolab_export.character_detail import browser_fetch_json, fetch_character_details_batch
from hoyolab_export.collect_account_inventory import wait_for_character_list_response
from hoyolab_export.hoyolab_exporter import close_export_context, HoyolabExporter
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_weapon, fake_account_details,
)


class ImportPreservationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        paths = {
            "PROJECT_ROOT": self.root,
            "HOYOLAB_DATA_DIR": self.root / "data/hoyolab",
            "HOYOLAB_ASSETS_DIR": self.root / "assets/hoyolab",
            "HOYOLAB_CHARACTER_ASSETS_DIR": self.root / "assets/hoyolab/characters",
            "HOYOLAB_WEAPON_ASSETS_DIR": self.root / "assets/hoyolab/weapons",
            "HOYOLAB_DEBUG_DIR": self.root / "debug/hoyolab",
            "HOYOLAB_PROFILE_DIR": self.root / "profile",
            "ARTIFACT_DB_PATH": self.root / "data/artifacts.db",
            "DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH": self.root / "data/hoyolab/spiral_abyss_period.json",
        }
        for name, value in paths.items():
            self.stack.enter_context(patch.object(pipeline, name, value))
        for name in ("HOYOLAB_DATA_DIR", "HOYOLAB_CHARACTER_ASSETS_DIR", "HOYOLAB_WEAPON_ASSETS_DIR", "HOYOLAB_DEBUG_DIR"):
            paths[name].mkdir(parents=True)
        self.db = paths["ARTIFACT_DB_PATH"]
        self.details = fake_account_details()
        self.details["json"]["retcode"] = 0
        self.details["json"]["data"]["list"][0]["relics"] = [{
            "id": 1, "name": "Fixture flower", "pos": 1, "rarity": 5, "level": 20,
            "set": {"id": 1, "name": "Fixture set"},
            "main_property": {"property_type": 2000, "value": "4780"},
            "sub_property_list": [],
        }]
        self.stack.enter_context(patch("hoyolab_export.artifact_importer.ensure_artifact_set_catalog", return_value={}))
        self.stack.enter_context(patch("hoyolab_export.artifact_importer.resolve_hoyolab_set_uid", return_value=None))
        with closing(connect_db(self.db)) as conn:
            init_db(conn)
        import_character_details_payload(self.details, db_path=self.db)
        with closing(connect_db(self.db)) as conn:
            sync_account_storage_from_sources(
                conn, account_characters=[fake_account_character()],
                account_weapons=[fake_account_weapon()], account_character_details=self.details,
            )
            artifact_id = conn.execute("SELECT id FROM artifacts").fetchone()[0]
            fingerprint = conn.execute("SELECT weapon_fingerprint FROM account_weapon_observed_stacks").fetchone()[0]
            equip_artifact(conn, 1001, artifact_id)
            equip_weapon(conn, 1001, fingerprint)
            create_build_preset(conn, name="Saved fixture", slots={1: artifact_id}, targets=[
                {"target_type": "character", "character_id": 1001}
            ])
            conn.commit()
        for name, value in (
            ("account_characters.json", [fake_account_character()]),
            ("account_weapons.json", [fake_account_weapon()]),
            ("account_character_details.json", self.details),
            ("crop_manifest.json", {"source": {}, "characterAssets": [], "weaponAssets": []}),
            ("account_language.json", {"contentLanguage": "en-us"}),
        ):
            pipeline.write_json(paths["HOYOLAB_DATA_DIR"] / name, value)
        (paths["HOYOLAB_CHARACTER_ASSETS_DIR"] / "old.png").write_bytes(b"old-image")
        self.before_files = self.account_files()
        self.before_db = self.db_dump()
        self.page = MagicMock()
        self.page.goto = AsyncMock()
        self.page.wait_for_timeout = AsyncMock()
        self.page.screenshot = AsyncMock()
        self.exporter = MagicMock()
        self.exporter.fixed_container_width = 500
        self.exporter._create_context = AsyncMock(return_value=MagicMock())
        self.exporter._prepare_export_page = AsyncMock()
        self.exporter._run_export_flow = AsyncMock(side_effect=self.export_flow)
        self.download = MagicMock()
        self.download.save_as = AsyncMock()
        self.patch("HoyolabExporter", return_value=self.exporter)
        self.patch("get_export_page", new=AsyncMock(return_value=self.page))
        self.patch("get_auth_status", return_value=pipeline.AuthStatus.LOGGED_IN)
        self.patch("ensure_hoyolab_dirs")
        self.patch("image_width", return_value=2000)
        self.patch("collect_layout", new=AsyncMock(return_value={"rootDiscovery": {"imageLike": [{}]}}))
        self.patch("fetch_character_details_batch", new=AsyncMock(return_value=self.details))
        self.patch("build_inventory", return_value=([fake_account_character()], [fake_account_weapon()]))
        self.patch("resolve_abyss_period_with_fallbacks", new=AsyncMock(side_effect=RuntimeError("offline fixture")))
        self.patch("sync_static_reference_catalogs_for_import", return_value=({}, None))
        self.patch("ensure_artifact_set_names", return_value={})
        self.patch("ensure_artifact_set_bonus_descriptions", return_value={})
        self.patch("ensure_hoyolab_set_mapping", new=AsyncMock(return_value={}))
        self.patch("rebuild_artifact_set_display_stat_effects", return_value=0)
        self.patch("rebuild_weapon_display_stat_effects", return_value=0)
        self.patch("sync_account_storage_for_import", side_effect=self.sync_account)
        self.patch("build_import_log", return_value={})
        self.crop = self.patch("build_crop_manifest", side_effect=self.crop_assets)
        self.close = self.patch("close_export_context", new=AsyncMock())

    def patch(self, name, **kwargs):
        return self.stack.enter_context(patch.object(pipeline, name, **kwargs))

    async def export_flow(self, page, after_character_list_open, **kwargs):
        callback = self.page.on.call_args.args[1]
        response = MagicMock(url="https://fixture.test/event/game_record/genshin/api/character/list", ok=True)
        response.json = AsyncMock(return_value={"retcode": 0, "data": {"list": [{"id": 1001}]}})
        await callback(response)
        await after_character_list_open()
        return self.download

    def crop_assets(self, **kwargs):
        (kwargs["character_output_dir"] / "old.png").write_bytes(b"new-image")
        return {"source": {}, "cardsCount": 1, "characterAssets": [], "weaponAssets": []}

    def sync_account(self, **kwargs):
        with closing(connect_db(self.db)) as conn:
            summary = sync_account_storage_from_sources(
                conn, account_characters=[fake_account_character()],
                account_weapons=[fake_account_weapon()], account_character_details=self.details,
            )
        return summary.to_dict(), None

    def account_files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for folder in ("data/hoyolab", "assets/hoyolab")
                for p in (self.root / folder).rglob("*") if p.is_file()}

    def db_dump(self):
        with closing(sqlite3.connect(self.db)) as conn:
            return list(conn.iterdump())

    async def test_early_failure_preserves_account_and_releases_listener(self):
        self.exporter._run_export_flow.side_effect = RuntimeError("early failure")
        with self.assertRaisesRegex(RuntimeError, "early failure"):
            await pipeline.run_hoyolab_import()
        await asyncio.sleep(0)
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)
        self.close.assert_awaited_once()
        self.page.remove_listener.assert_called_once()

    async def test_enabled_import_applies_fresh_equipment_and_off_does_not(self):
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM account_character_equipped_artifacts")
            conn.execute("DELETE FROM account_character_equipped_weapons")
            conn.commit()
        await pipeline.run_hoyolab_import()
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM account_character_equipped_artifacts").fetchone()[0], 0)
        await pipeline.run_hoyolab_import(change_equipment=True)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM account_character_equipped_artifacts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM account_character_equipped_weapons").fetchone()[0], 1)

    async def test_enabled_import_storage_failure_keeps_current_equipment(self):
        with closing(connect_db(self.db)) as conn:
            before = [tuple(r) for r in conn.execute("SELECT * FROM account_character_equipped_artifacts")]
        with patch.object(pipeline, "sync_account_storage_for_import", return_value=({}, "fixture")):
            with self.assertRaisesRegex(pipeline.HoYoLABImportError, "Equipment was not applied"):
                await pipeline.run_hoyolab_import(change_equipment=True)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(before, [tuple(r) for r in conn.execute("SELECT * FROM account_character_equipped_artifacts")])

    async def test_identical_artifacts_only_split_for_simultaneously_visible_characters(self):
        payload = deepcopy(self.details)
        first = payload["json"]["data"]["list"][0]
        second = deepcopy(first)
        second["base"]["id"] = 1002
        payload["json"]["data"]["list"] = [first, second]
        result = import_character_details_payload(payload, db_path=self.db)
        self.assertEqual(result["artifacts_inserted"], 1)
        with closing(connect_db(self.db)) as conn:
            assignments = [tuple(r) for r in conn.execute("SELECT character_id, artifact_id FROM artifact_equipment ORDER BY character_id")]
            self.assertNotEqual(assignments[0][1], assignments[1][1])
            preset_id = conn.execute("SELECT artifact_id FROM artifact_build_slots").fetchone()[0]
        payload["json"]["data"]["list"].reverse()
        self.assertEqual(import_character_details_payload(payload, db_path=self.db)["artifacts_inserted"], 0)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(assignments, [tuple(r) for r in conn.execute("SELECT character_id, artifact_id FROM artifact_equipment ORDER BY character_id")])
            self.assertEqual(conn.execute("SELECT artifact_id FROM artifact_build_slots").fetchone()[0], preset_id)
        payload["json"]["data"]["list"] = [second]
        self.assertEqual(import_character_details_payload(payload, db_path=self.db)["artifacts_inserted"], 0)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM artifacts").fetchone()[0], 2)

    async def test_duplicate_character_rows_are_not_evidence_of_two_artifact_copies(self):
        payload = deepcopy(self.details)
        payload["json"]["data"]["list"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate character"):
            import_character_details_payload(payload, db_path=self.db)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_partial_crop_failure_preserves_old_files_and_database(self):
        def fail(**kwargs):
            self.crop_assets(**kwargs)
            raise RuntimeError("partial crop failure")
        self.crop.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "partial crop failure"):
            await pipeline.run_hoyolab_import()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)
        self.close.assert_awaited_once()
        self.assertFalse(list((self.root / "debug/hoyolab").glob("import-assets-*")))

    async def test_failure_diagnostics_capture_closure_before_cleanup_without_secrets(self):
        async def fail(*args, **kwargs):
            callbacks = dict(call.args for call in self.page.on.call_args_list)
            self.page.is_closed.return_value = True
            callbacks["close"]()
            raise RuntimeError("secret-token-must-not-be-recorded")
        self.exporter._run_export_flow.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "secret-token"):
            await pipeline.run_hoyolab_import()
        diagnostic = (self.root / "debug/hoyolab/import_failure.json").read_text()
        data = json.loads(diagnostic)
        self.assertTrue(data["pageClosed"])
        self.assertEqual(data["stage"], "exporting_image")
        self.assertEqual(data["browserEvents"][0]["event"], "page_closed")
        self.assertNotIn("secret-token", diagnostic)
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_failure_diagnostics_cannot_mask_original_error(self):
        self.exporter._run_export_flow.side_effect = RuntimeError("original failure")
        self.page.is_closed.side_effect = RuntimeError("diagnostics unavailable")
        with self.assertRaisesRegex(RuntimeError, "original failure"):
            await pipeline.run_hoyolab_import()
        self.close.assert_awaited_once()

    async def test_empty_layout_is_not_reported_as_success(self):
        with patch.object(pipeline, "collect_layout", new=AsyncMock(return_value={"rootDiscovery": {"imageLike": []}})):
            with self.assertRaisesRegex(pipeline.HoYoLABImportError, "layout is empty"):
                await pipeline.run_hoyolab_import()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_empty_crop_result_preserves_old_files_and_database(self):
        self.crop.return_value = {"cardsCount": 0}
        self.crop.side_effect = None
        with self.assertRaisesRegex(pipeline.HoYoLABImportError, "no cards"):
            await pipeline.run_hoyolab_import()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_artifact_write_failure_rolls_back_and_preserves_source_files(self):
        with patch("hoyolab_export.artifact_importer.replace_current_equipment", side_effect=RuntimeError("write failure")):
            with self.assertRaisesRegex(RuntimeError, "write failure"):
                await pipeline.run_hoyolab_import()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_restart_and_repeated_import_preserve_ids_presets_and_equipment(self):
        self.exporter._run_export_flow.side_effect = RuntimeError("first attempt")
        with self.assertRaises(RuntimeError):
            await pipeline.run_hoyolab_import()
        self.exporter._run_export_flow.side_effect = self.export_flow
        tables = ("artifact_builds", "artifact_build_slots", "artifact_build_targets",
                  "account_character_equipped_artifacts", "account_character_equipped_weapons")
        with closing(sqlite3.connect(self.db)) as conn:
            before = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
            ids = conn.execute("SELECT id, fingerprint, content_fingerprint FROM artifacts").fetchall()
        for _ in range(2):
            result = await pipeline.run_hoyolab_import()
            self.assertEqual(result["artifactSummary"]["artifacts_inserted"], 0)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual({t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}, before)
            self.assertEqual(conn.execute("SELECT id, fingerprint, content_fingerprint FROM artifacts").fetchall(), ids)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.close.await_count, 3)


class ImportResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_bad_inventory_response_is_rejected_and_listener_removed(self):
        for payload in ({"retcode": -1}, {"retcode": 0, "data": {"list": []}}, {"retcode": 0}):
            page = MagicMock()
            future = await wait_for_character_list_response(page)
            response = MagicMock(url="/event/game_record/genshin/api/character/list", ok=True)
            response.json = AsyncMock(return_value=payload)
            await page.on.call_args.args[1](response)
            with self.assertRaises(RuntimeError):
                await future
            await asyncio.sleep(0)
            page.remove_listener.assert_called_once()

    async def test_browser_fetch_has_finite_timeout(self):
        page = MagicMock()
        async def hang(*args):
            await asyncio.Future()
        page.evaluate = AsyncMock(side_effect=hang)
        with self.assertRaises(TimeoutError):
            await browser_fetch_json(page, "https://fixture.test", timeout_sec=0.01)

    async def test_incomplete_detail_batch_is_rejected(self):
        roles = {"ok": True, "json": {"retcode": 0, "data": {"list": [
            {"game_biz": "hk4e_global", "game_uid": "1", "region": "fixture"}
        ]}}}
        detail = {"ok": True, "json": {"retcode": 0, "data": {"list": [{"base": {"id": 1001}}]}}}
        with patch("hoyolab_export.character_detail.browser_fetch_json", new=AsyncMock(side_effect=[roles, detail])):
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                await fetch_character_details_batch(MagicMock(), [1001, 1002])

    async def test_browser_cleanup_failure_still_stops_playwright(self):
        context = MagicMock()
        context._attached_debug_port = None
        context._keep_browser_open = False
        context._browser_process.poll.return_value = None
        context._browser_process.terminate.side_effect = OSError("fixture terminate error")
        context._browser_process.kill.side_effect = OSError("fixture kill error")
        context._playwright_instance.stop = AsyncMock()
        await close_export_context(context)
        context._playwright_instance.stop.assert_awaited_once()

    async def test_failed_browser_acquisition_cleans_up(self):
        with tempfile.TemporaryDirectory() as folder:
            exporter = HoyolabExporter(folder, folder)
            playwright = MagicMock()
            with patch("hoyolab_export.hoyolab_exporter.async_playwright") as factory, patch(
                "hoyolab_export.hoyolab_exporter.close_export_context", new=AsyncMock()
            ) as close:
                factory.return_value.start = AsyncMock(return_value=playwright)
                exporter._connect_export_context = AsyncMock(side_effect=RuntimeError("CDP failure"))
                with self.assertRaisesRegex(RuntimeError, "CDP failure"):
                    await exporter._create_context()
                close.assert_awaited_once()

    def test_json_serialization_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "account.json"
            target.write_text("old", encoding="utf-8")
            with self.assertRaises(TypeError):
                pipeline.write_json(target, {"invalid": object()})
            self.assertEqual(target.read_text(), "old")
            self.assertEqual(len(list(Path(folder).iterdir())), 1)
