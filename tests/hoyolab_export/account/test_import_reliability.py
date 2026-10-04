"""Isolated import fault fixtures; network/layers are simulated, SQLite writes are real.

These pin the existing account/equipment contracts, not a full HoYoLAB simulator.
"""
import asyncio
from copy import deepcopy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing, nullcontext, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hoyolab_export import import_pipeline as pipeline
from hoyolab_export import run_import
from hoyolab_export import import_store
from hoyolab_export.account_equipment import equip_artifact, equip_weapon
from hoyolab_export.account_storage import sync_account_storage_from_sources
from hoyolab_export.artifact_db import connect_db, init_db, create_build_preset
from hoyolab_export.artifact_importer import import_character_details_payload
from hoyolab_export.artifact_set_catalog import UnmappedArtifactSetError
from hoyolab_export.character_detail import browser_fetch_json, fetch_character_details_batch
from hoyolab_export.collect_account_inventory import wait_for_character_list_response
from hoyolab_export.hoyolab_exporter import close_export_context, HoyolabExporter
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_weapon, fake_account_details,
)


class ImportWarningCliTest(unittest.TestCase):
    def test_partial_import_exits_success_and_emits_structured_warning(self):
        warning = {"code": "artifact_sets_unmapped", "count": 1,
                   "sets": [{"hoyolab_set_id": 2150451, "name": "Celestial Gift"}]}
        output = io.StringIO()
        with patch.object(run_import.sys, "argv", ["run_import"]), \
                patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", new=AsyncMock(return_value={"warnings": [warning]})), \
                redirect_stdout(output):
            self.assertEqual(run_import.main(), 0)
        lines = [line for line in output.getvalue().splitlines() if line.startswith("[IMPORT_WARNING] ")]
        self.assertEqual([json.loads(line[len("[IMPORT_WARNING] "):]) for line in lines], [warning])

    def test_primary_failure_still_exits_failure(self):
        with patch.object(run_import.sys, "argv", ["run_import"]), \
                patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", new=AsyncMock(side_effect=pipeline.HoYoLABImportError("invalid source"))), \
                redirect_stderr(io.StringIO()):
            self.assertEqual(run_import.main(), 2)


class ImportPreservationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        paths = {
            "PROJECT_ROOT": self.root,
            "ACCOUNT_ROOT": self.root,
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
            self.stack.enter_context(patch.object(pipeline, name, value, create=True))
        for name in ("HOYOLAB_DATA_DIR", "HOYOLAB_CHARACTER_ASSETS_DIR", "HOYOLAB_WEAPON_ASSETS_DIR", "HOYOLAB_DEBUG_DIR"):
            paths[name].mkdir(parents=True)
        self.db = paths["ARTIFACT_DB_PATH"]
        self.details = fake_account_details()
        self.details["detectedLanguage"] = "en-us"
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
        import_store.prepare_import_store(self.db)
        import_store.adopt_legacy_account_binding(self.db, account_uid="123", server="os_euro", verified=True)
        self.stack.enter_context(patch.object(import_store, "build_account_sync_context", return_value={
            "character_stats_catalog": None, "weapon_stats_catalog": None,
            "character_region_entries": [], "character_trait_entries": [], "gcsim_key_resolver": None,
        }))
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
        self.page.goto = AsyncMock(side_effect=self.navigate)
        self.page.locator.return_value.first.wait_for = AsyncMock()
        self.exporter = MagicMock()
        self.exporter._create_context = AsyncMock(return_value=MagicMock())
        self.exporter._wait_until_ready_or_login = AsyncMock()
        self.exporter._click_with_popup_retry = AsyncMock()
        self.patch("HoyolabExporter", return_value=self.exporter)
        self.patch("get_export_page", new=AsyncMock(return_value=self.page))
        self.direct_list = self.patch("fetch_character_list_direct", new=AsyncMock(return_value=None))
        self.patch("get_auth_status", return_value=pipeline.AuthStatus.LOGGED_IN)
        self.patch("ensure_hoyolab_dirs")
        self.patch("fetch_character_details_batch", new=AsyncMock(return_value=self.details))
        self.patch("build_inventory", return_value=([fake_account_character()], [fake_account_weapon()]))
        self.patch("resolve_abyss_period_with_fallbacks", new=AsyncMock(side_effect=RuntimeError("offline fixture")))
        self.patch("sync_static_reference_catalogs_for_import", return_value=({}, None))
        self.patch("ensure_artifact_set_names", return_value={})
        self.patch("ensure_artifact_set_bonus_descriptions", return_value={})
        self.mapping = self.patch("ensure_hoyolab_set_mapping", new=AsyncMock(return_value={}))
        self.patch("rebuild_artifact_set_display_stat_effects", return_value=0)
        self.patch("rebuild_weapon_display_stat_effects", return_value=0)
        self.patch("sync_account_storage_for_import", side_effect=self.sync_account)
        self.patch("refresh_import_side_icons", new=AsyncMock(return_value={"pending": False}))
        self.patch("build_import_log", return_value={})
        self.layers = self.patch("prepare_layered_assets", new=AsyncMock(side_effect=self.stage_assets))
        self.patch("cleanup_unused_v2_assets", return_value=[])
        self.close = self.patch("close_export_context", new=AsyncMock())

    def patch(self, name, **kwargs):
        return self.stack.enter_context(patch.object(pipeline, name, **kwargs))

    async def navigate(self, *args, **kwargs):
        callback = self.page.on.call_args.args[1]
        response = MagicMock(url="https://fixture.test/event/game_record/genshin/api/character/list", ok=True)
        response.request.post_data_json = {"role_id": "123", "server": "os_euro"}
        response.json = AsyncMock(return_value={"retcode": 0, "data": {"list": [{"id": 1001}]}})
        await callback(response)

    async def stage_assets(self, **kwargs):
        path = kwargs["staging_root"] / "assets/hoyolab/characters/char_v2_fixture.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"new-image")
        return {"version": 2, "source": {}, "cardsCount": 1, "characterAssets": [], "weaponAssets": []}

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
        self.exporter._click_with_popup_retry.side_effect = RuntimeError("early failure")
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

    async def test_direct_list_skips_browser_cards_and_uses_context_for_details(self):
        self.direct_list.return_value = ([{"id": 1001}], {"role_id": "123", "server": "os_euro"})
        await pipeline.run_hoyolab_import()
        self.exporter._click_with_popup_retry.assert_not_awaited()
        self.assertIs(pipeline.fetch_character_details_batch.call_args.kwargs["json_fetcher"], pipeline.fast_context_request_fetch_json)

    async def test_direct_detail_failure_retries_existing_page_request(self):
        self.direct_list.return_value = ([{"id": 1001}], {"role_id": "123", "server": "os_euro"})
        pipeline.fetch_character_details_batch.side_effect = [TimeoutError("slow API"), self.details]
        await pipeline.run_hoyolab_import()
        self.assertEqual(pipeline.fetch_character_details_batch.await_count, 2)
        self.assertNotIn("json_fetcher", pipeline.fetch_character_details_batch.await_args_list[1].kwargs)

    async def test_unknown_artifact_set_refreshes_recent_list_once_before_retry(self):
        self.mapping.side_effect = [
            {"unmapped": [{"hoyolab_set_id": 2150451, "display_name": "Celestial Gift"}]},
            {"mapped": 1, "unmapped": []},
        ]
        first = MagicMock(sources={"en-us": "fresh_cache"}, cleanup_failures=[])
        fresh = MagicMock(sources={"en-us": "network"}, cleanup_failures=[])
        with patch.object(pipeline, "ImportArtifactSetLists", side_effect=[first, fresh]) as lists, patch.object(
            pipeline, "ensure_artifact_set_catalog", return_value={},
        ) as catalog:
            await pipeline.run_hoyolab_import()
        self.assertEqual(self.mapping.await_count, 2)
        self.assertTrue(lists.call_args.kwargs["force_network"])
        catalog.assert_called_once()

    async def test_successful_mapping_keeps_partial_forced_catalog_refresh_pending(self):
        self.mapping.side_effect = [{"unmapped": [{"id": 1}]}, {"mapped": 1, "unmapped": []}]
        cached = MagicMock(sources={"en-us": "fresh_cache"})
        fresh = MagicMock(sources={"en-us": "network"})
        with patch.object(pipeline, "ImportArtifactSetLists", side_effect=[cached, fresh]), patch.object(
            pipeline, "ensure_artifact_set_catalog", return_value={"errors": ["fixture timeout"]},
        ), patch.object(pipeline, "ensure_artifact_set_names", side_effect=[{}, {"error": "fixture"}]), patch.object(
            pipeline, "ensure_artifact_set_bonus_descriptions", side_effect=[{}, {"failed": 1}],
        ):
            result = await pipeline.run_hoyolab_import()
        references = result["enrichment"]["references"]
        self.assertEqual(result["status"], "committed")
        self.assertEqual(references["status"], "pending")
        self.assertEqual(references["result"]["mapping"]["unmapped"], [])
        self.assertEqual(references["result"]["mappingRefresh"]["errors"], ["catalog", "names", "bonuses"])

    async def test_storage_failure_rolls_back_core_and_keeps_replayable_source(self):
        before = self.account_files()
        with closing(connect_db(self.db)) as conn:
            gear = list(map(tuple, conn.execute("SELECT * FROM account_character_equipped_artifacts")))
        with patch.object(import_store, "sync_account_storage_from_sources", side_effect=RuntimeError("fixture")):
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                await pipeline.run_hoyolab_import(change_equipment=True, attempt_id="failed-core")
        self.assertEqual(self.account_files(), before)
        pending = import_store.get_import_attempt(self.db, "failed-core")
        self.assertEqual(pending["status"], "pending")
        self.assertIsNone(pending["result"])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(gear, list(map(tuple, conn.execute("SELECT * FROM account_character_equipped_artifacts"))))
        replay = await pipeline.run_hoyolab_import(resume_attempt="failed-core")
        self.assertEqual(replay["status"], "committed")
        self.assertTrue(replay["equipmentApplied"]["applied"])

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

    async def test_partial_layer_failure_preserves_old_images_and_committed_account(self):
        async def fail(**kwargs):
            await self.stage_assets(**kwargs)
            raise RuntimeError("partial layer failure")
        self.layers.side_effect = fail
        result = await pipeline.run_hoyolab_import()
        self.assertEqual(result["status"], "committed")
        self.assertIn("assets", result["pendingJobs"])
        self.assertEqual(result["enrichment"]["assets"]["status"], "failed")
        self.assertEqual((pipeline.HOYOLAB_CHARACTER_ASSETS_DIR / "old.png").read_bytes(), b"old-image")
        self.close.assert_awaited_once()
        self.assertFalse(list((self.root / "debug/hoyolab").glob("import-assets-*")))

    async def test_failure_diagnostics_capture_closure_before_cleanup_without_secrets(self):
        async def fail(*args, **kwargs):
            callbacks = dict(call.args for call in self.page.on.call_args_list)
            self.page.is_closed.return_value = True
            callbacks["close"]()
            raise RuntimeError("secret-token-must-not-be-recorded")
        self.exporter._click_with_popup_retry.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "secret-token"):
            await pipeline.run_hoyolab_import()
        diagnostic = (self.root / "debug/hoyolab/import_failure.json").read_text()
        data = json.loads(diagnostic)
        self.assertTrue(data["pageClosed"])
        self.assertEqual(data["stage"], "opening_character_list")
        self.assertEqual(data["browserEvents"][0]["event"], "page_closed")
        self.assertNotIn("secret-token", diagnostic)
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(self.db_dump(), self.before_db)

    async def test_failure_diagnostics_cannot_mask_original_error(self):
        self.exporter._click_with_popup_retry.side_effect = RuntimeError("original failure")
        self.page.is_closed.side_effect = RuntimeError("diagnostics unavailable")
        with self.assertRaisesRegex(RuntimeError, "original failure"):
            await pipeline.run_hoyolab_import()
        self.close.assert_awaited_once()

    async def test_asset_refresh_can_resume_without_auth_or_reapplying_equipment(self):
        self.layers.side_effect = RuntimeError("layer URLs missing")
        first = await pipeline.run_hoyolab_import(change_equipment=True)
        self.assertEqual(first["enrichment"]["assets"]["status"], "failed")
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM account_character_equipped_artifacts")
            conn.commit()
        self.layers.side_effect = self.stage_assets
        self.exporter._create_context.reset_mock()
        with patch.object(pipeline, "get_auth_status", return_value=None):
            resumed = await pipeline.run_hoyolab_import(resume_attempt=first["attemptId"])
        self.assertEqual(resumed["enrichment"]["assets"]["status"], "complete")
        self.exporter._create_context.assert_not_awaited()
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_character_equipped_artifacts").fetchone()[0], 0)

    async def test_empty_layer_result_does_not_discard_account_snapshot(self):
        self.layers.return_value = {"cardsCount": 0}
        self.layers.side_effect = None
        result = await pipeline.run_hoyolab_import()
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["enrichment"]["assets"]["status"], "failed")
        self.assertEqual(result["artifactSummary"]["relics_seen"], 1)

    async def test_artifact_write_failure_rolls_back_core_and_keeps_source_for_retry(self):
        tables = ("artifacts", "artifact_substats", "artifact_equipment", "artifact_build_slots",
                  "account_characters", "account_character_equipped_artifacts", "account_character_equipped_weapons")
        with closing(connect_db(self.db)) as conn:
            before = {t: list(map(tuple, conn.execute(f"SELECT * FROM {t}"))) for t in tables}
        with patch("hoyolab_export.artifact_importer.replace_current_equipment", side_effect=RuntimeError("write failure")):
            with self.assertRaisesRegex(RuntimeError, "write failure"):
                await pipeline.run_hoyolab_import(change_equipment=True, attempt_id="retry-artifacts")
        self.layers.assert_not_awaited()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(import_store.get_import_attempt(self.db, "retry-artifacts")["status"], "pending")
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(before, {t: list(map(tuple, conn.execute(f"SELECT * FROM {t}"))) for t in tables})

    async def test_unknown_set_is_stored_and_can_apply_fresh_equipment_without_warning(self):
        new = deepcopy(self.details["json"]["data"]["list"][0]["relics"][0])
        new.update(id=2, pos=2, name="Known new plume")
        unknown = deepcopy(new)
        unknown.update(id=3, pos=3, name="Unknown sands", set={"id": 2150451, "name": "Celestial Gift"})
        self.details["json"]["data"]["list"][0]["relics"] += [new, unknown]
        def resolve(conn, *, hoyolab_set_id, display_name):
            if hoyolab_set_id == 2150451:
                raise UnmappedArtifactSetError(hoyolab_set_id=hoyolab_set_id, display_name=display_name)
            return None
        with patch("hoyolab_export.artifact_importer.resolve_hoyolab_set_uid", side_effect=resolve):
            with self.assertRaises(UnmappedArtifactSetError):
                import_character_details_payload(self.details, db_path=self.db)
            self.assertEqual(self.db_dump(), self.before_db)
            result = await pipeline.run_hoyolab_import(change_equipment=True)
        summary = result["artifactSummary"]
        self.assertEqual(summary["relics_seen"], 3)
        self.assertEqual(summary["artifacts_inserted"], 2)
        self.assertEqual(summary["relics_unresolved_set"], 1)
        self.assertTrue(summary["equipment_updated"])
        self.assertTrue(result["equipmentApplied"]["applied"])
        self.assertEqual(result["warnings"], [])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM artifacts").fetchone()[0], 3)
            row = conn.execute("SELECT id, set_uid FROM artifacts WHERE set_id=2150451").fetchone()
            self.assertIsNone(row["set_uid"])
            self.assertEqual(conn.execute("SELECT artifact_id FROM account_character_equipped_artifacts WHERE slot_key='sands'").fetchone()[0], row["id"])
            self.assertEqual(conn.execute("SELECT count(*) FROM artifact_build_slots").fetchone()[0], 1)
        self.assertEqual(json.loads(result["characterDetailsPath"].read_text()), self.details)

    async def test_reference_and_mapping_failures_do_not_abort_account_import(self):
        with patch.object(pipeline, "sync_static_reference_catalogs_for_import", return_value=({}, "catalog unavailable")), \
                patch.object(pipeline, "ensure_artifact_set_names", side_effect=RuntimeError("names unavailable")), \
                patch.object(pipeline, "ensure_artifact_set_bonus_descriptions", side_effect=RuntimeError("bonus unavailable")):
            self.mapping.side_effect = TimeoutError("mapping unavailable")
            result = await pipeline.run_hoyolab_import()
        self.assertEqual(result["warnings"], [])
        self.assertIn("references", result["pendingJobs"])
        self.assertEqual(result["artifactSummary"]["artifacts_existing"], 1)
        self.assertTrue((pipeline.HOYOLAB_CHARACTER_ASSETS_DIR / "char_v2_fixture.png").is_file())
        self.assertEqual(json.loads(result["characterDetailsPath"].read_text()), self.details)

    async def test_unknown_mapping_refresh_failure_keeps_complete_source_result(self):
        self.mapping.return_value = {"unmapped": [{"hoyolab_set_id": 2150451}]}
        lists = MagicMock(sources={"en-us": "fresh_cache"}, cleanup_failures=[])
        with patch.object(pipeline, "ImportArtifactSetLists", return_value=lists), \
                patch.object(pipeline, "ensure_artifact_set_catalog", side_effect=TimeoutError("refresh unavailable")):
            result = await pipeline.run_hoyolab_import()
        self.assertEqual(self.mapping.await_count, 1)
        self.assertEqual(result["warnings"], [])
        self.assertIn("references", result["pendingJobs"])
        self.assertEqual(result["status"], "committed")

    async def test_equipment_write_failure_rolls_back_whole_core(self):
        with closing(connect_db(self.db)) as conn:
            before = list(map(tuple, conn.execute("SELECT * FROM account_character_equipped_artifacts")))
        def fail(conn, **kwargs):
            conn.execute("DELETE FROM account_character_equipped_artifacts")
            raise RuntimeError("equipment write failed")
        with patch.object(import_store, "apply_hoyolab_equipment_snapshot", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "equipment write failed"):
                await pipeline.run_hoyolab_import(change_equipment=True, attempt_id="equipment-fault")
        self.assertIsNone(import_store.get_import_result(self.db, "equipment-fault"))
        self.assertEqual(self.account_files(), self.before_files)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(before, list(map(tuple, conn.execute("SELECT * FROM account_character_equipped_artifacts"))))

    async def test_restart_and_repeated_import_preserve_ids_presets_and_equipment(self):
        self.exporter._click_with_popup_retry.side_effect = RuntimeError("first attempt")
        with self.assertRaises(RuntimeError):
            await pipeline.run_hoyolab_import()
        self.exporter._click_with_popup_retry.side_effect = None
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


    async def test_cold_import_stores_every_relic_before_optional_services(self):
        self.db.unlink()
        unknown = self.details["json"]["data"]["list"][0]["relics"][0]
        unknown["set"] = {"id": 2150451, "name": "Celestial Gift"}
        with patch("hoyolab_export.artifact_importer.resolve_hoyolab_set_uid",
                   side_effect=UnmappedArtifactSetError(hoyolab_set_id=2150451, display_name="Celestial Gift")):
            self.layers.side_effect = RuntimeError("network offline")
            self.mapping.side_effect = RuntimeError("wiki offline")
            result = await pipeline.run_hoyolab_import(attempt_id="cold-account")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["artifactSummary"]["artifacts_inserted"], 1)
        self.assertEqual(result["warnings"], [])
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT set_id FROM artifacts").fetchone()[0], 2150451)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_characters").fetchone()[0], 1)
        self.assertEqual(import_store.get_active_account_binding(self.db)["account_uid"], "123")

    async def test_core_receipt_is_available_while_independent_jobs_are_running(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow_assets(**kwargs):
            entered.set()
            await release.wait()
            return await self.stage_assets(**kwargs)
        self.layers.side_effect = slow_assets
        task = asyncio.create_task(pipeline.run_hoyolab_import(attempt_id="visible-core"))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            self.assertFalse(task.done())
            self.assertEqual(import_store.get_import_result(self.db, "visible-core")["status"], "committed")
        finally:
            release.set()
            result = await task
        self.assertEqual(result["status"], "committed")

    async def test_independent_enrichment_jobs_start_together(self):
        entered, release = set(), asyncio.Event()
        async def arrive(name, value):
            entered.add(name)
            if len(entered) == 3:
                release.set()
            await asyncio.wait_for(release.wait(), 3)
            return value
        with patch.object(pipeline, "refresh_import_assets", new=AsyncMock(
                side_effect=lambda *args, **kwargs: None)) as assets, \
                patch.object(pipeline, "refresh_import_catalogs", new=AsyncMock()) as references, \
                patch.object(pipeline, "refresh_import_side_icons", new=AsyncMock()) as sides:
            async def asset_job(*args, **kwargs):
                return await arrive("assets", {"manifest": {"cardsCount": 1}})
            async def reference_job(*args, **kwargs):
                return await arrive("references", {})
            async def side_job(*args, **kwargs):
                return await arrive("side_icons", {})
            assets.side_effect, references.side_effect, sides.side_effect = asset_job, reference_job, side_job
            result = await pipeline.run_hoyolab_import()
        self.assertEqual(entered, {"assets", "references", "side_icons"})
        for kind in entered:
            self.assertEqual(result["enrichment"][kind]["status"], "complete")

    async def test_partial_catalog_result_remains_recoverable(self):
        with patch.object(pipeline, "sync_static_reference_catalogs_for_import", return_value=({
            "artifactSetCatalog": {"errors": [{"stage": "icon_download"}]},
            "localizedWeaponStatsCatalog": {"failed": 1},
        }, None)):
            first = await pipeline.run_hoyolab_import()
        self.assertEqual(first["enrichment"]["references"]["status"], "pending")
        self.mapping.reset_mock()
        repaired = await pipeline.run_hoyolab_import(resume_attempt=first["attemptId"])
        self.mapping.assert_awaited_once()
        self.assertEqual(repaired["enrichment"]["references"]["status"], "complete")

    async def test_gear_changed_during_acquisition_is_not_overwritten(self):
        async def detail_response(*args, **kwargs):
            with closing(connect_db(self.db)) as conn:
                conn.execute("DELETE FROM account_character_equipped_artifacts")
                conn.commit()
            return self.details
        pipeline.fetch_character_details_batch.side_effect = detail_response
        result = await pipeline.run_hoyolab_import(change_equipment=True)
        self.assertEqual(result["equipmentApplied"]["reason"], "stale_equipment_revision")
        self.assertEqual(result["status"], "committed")
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM account_character_equipped_artifacts").fetchone()[0], 0)

    async def test_known_russian_sets_do_not_refetch_english_character_batch(self):
        self.details["detectedLanguage"] = "ru-ru"
        with closing(connect_db(self.db)) as conn:
            conn.execute("INSERT INTO artifact_sets (set_uid, hoyowiki_entry_id, hoyolab_set_id, fallback_name, updated_at) VALUES ('FixtureSet', 'entry', 1, 'Fixture', 'now')")
            conn.commit()
        await pipeline.run_hoyolab_import()
        pipeline.fetch_character_details_batch.assert_awaited_once()

    async def test_projection_write_failure_repairs_from_receipt_without_network(self):
        writer = pipeline.write_json
        def fail(path, value):
            if path.name == "account_character_details.json":
                raise OSError("disk busy")
            return writer(path, value)
        with patch.object(pipeline, "write_json", side_effect=fail):
            first = await pipeline.run_hoyolab_import()
        self.assertEqual(first["enrichment"]["projections"]["status"], "failed")
        self.layers.reset_mock()
        pipeline.fetch_character_details_batch.reset_mock()
        repaired = await pipeline.run_hoyolab_import(resume_attempt=first["attemptId"])
        self.assertEqual(repaired["enrichment"]["projections"]["status"], "complete")
        self.layers.assert_not_awaited()
        pipeline.fetch_character_details_batch.assert_not_awaited()
        self.assertEqual(json.loads(repaired["characterDetailsPath"].read_text()), self.details)

    async def test_exception_immediately_after_commit_returns_durable_success(self):
        commit = pipeline.commit_import_snapshot
        def commit_then_fail(*args, **kwargs):
            commit(*args, **kwargs)
            raise RuntimeError("process failed after commit")
        with patch.object(pipeline, "commit_import_snapshot", side_effect=commit_then_fail):
            result = await pipeline.run_hoyolab_import(attempt_id="after-commit")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(import_store.get_import_result(self.db, "after-commit")["status"], "committed")
        recovered = await pipeline.run_hoyolab_import(resume_attempt="after-commit")
        self.assertEqual(recovered["enrichment"]["assets"]["status"], "complete")
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM artifacts").fetchone()[0], 1)

    async def test_import_log_failure_never_changes_success(self):
        writer = pipeline.write_json
        def fail(path, value):
            if path.name == "import_log.json":
                raise OSError("log unwritable")
            return writer(path, value)
        with patch.object(pipeline, "write_json", side_effect=fail):
            result = await pipeline.run_hoyolab_import()
        self.assertEqual(result["status"], "committed")
        self.assertEqual(import_store.get_import_result(self.db, result["attemptId"])["status"], "committed")

    async def test_legacy_binding_requires_confirmation_and_reuses_saved_source(self):
        with closing(connect_db(self.db)) as conn:
            conn.execute("DELETE FROM hoyolab_account_binding")
            conn.commit()
        with self.assertRaises(import_store.LegacyAccountBindingRequired):
            await pipeline.run_hoyolab_import(attempt_id="legacy")
        self.layers.assert_not_awaited()
        pipeline.fetch_character_details_batch.reset_mock()
        result = await pipeline.run_hoyolab_import(resume_attempt="legacy", adopt_legacy=True)
        self.assertEqual(result["status"], "committed")
        pipeline.fetch_character_details_batch.assert_not_awaited()

    async def test_other_account_is_rejected_without_replacing_current_inventory(self):
        self.direct_list.return_value = ([{"id": 1001}], {"role_id": "999", "server": "os_usa"})
        with self.assertRaises(import_store.AccountBindingMismatch):
            await pipeline.run_hoyolab_import(attempt_id="other-account")
        self.layers.assert_not_awaited()
        pipeline.fetch_character_details_batch.assert_not_awaited()
        self.assertEqual(self.account_files(), self.before_files)
        self.assertEqual(import_store.get_active_account_binding(self.db)["account_uid"], "123")

    async def test_staging_cleanup_removes_only_expired_owned_directories(self):
        import os
        root = pipeline.HOYOLAB_DEBUG_DIR
        expired, recent, unrelated = [root / name for name in ("import-assets-old", "import-assets-new", "keep-me")]
        for folder in (expired, recent, unrelated):
            folder.mkdir()
            (folder / "fixture.png").write_bytes(b"test")
        os.utime(expired, (10, 10))
        os.utime(unrelated, (10, 10))
        self.assertEqual(pipeline.cleanup_import_staging(now=90000), [])
        self.assertFalse(expired.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(unrelated.exists())


class ImportResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_list_accepts_one_role_and_reuses_its_context(self):
        roles = {"ok": True, "json": {"retcode": 0, "data": {"list": [
            {"game_biz": "hk4e_global", "game_uid": "123", "region": "os_euro"},
        ]}}}
        listing = {"ok": True, "json": {"retcode": 0, "data": {"list": [{"id": 1001}]}}}
        with patch.object(pipeline, "context_request_fetch_json", new=AsyncMock(side_effect=[roles, listing])) as fetch:
            result = await pipeline.fetch_character_list_direct(MagicMock())
        self.assertEqual(result, ([{"id": 1001}], {"role_id": "123", "server": "os_euro"}))
        self.assertEqual(fetch.await_count, 2)
        self.assertEqual(fetch.call_args.kwargs["body"], {"server": "os_euro", "role_id": "123"})
        self.assertEqual(fetch.call_args.kwargs["timeout_ms"], pipeline.FAST_REQUEST_TIMEOUT_MS)

    async def test_direct_list_defers_multirole_and_api_failure_to_browser(self):
        roles = {"ok": True, "json": {"retcode": 0, "data": {"list": [
            {"game_biz": "hk4e_global", "game_uid": "123", "region": "os_euro"},
            {"game_biz": "hk4e_global", "game_uid": "456", "region": "os_usa"},
        ]}}}
        with patch.object(pipeline, "context_request_fetch_json", new=AsyncMock(return_value=roles)) as fetch:
            self.assertIsNone(await pipeline.fetch_character_list_direct(MagicMock()))
        fetch.assert_awaited_once()
        with patch.object(pipeline, "context_request_fetch_json", new=AsyncMock(side_effect=RuntimeError("offline"))):
            self.assertIsNone(await pipeline.fetch_character_list_direct(MagicMock()))

    async def test_fast_context_request_has_total_deadline(self):
        async def never_finish(*_args, **_kwargs):
            await asyncio.Future()
        with patch.object(pipeline, "FAST_REQUEST_TIMEOUT_MS", 1), patch.object(
            pipeline, "context_request_fetch_json", new=AsyncMock(side_effect=never_finish),
        ):
            with self.assertRaises(TimeoutError):
                await pipeline.fast_context_request_fetch_json(MagicMock(), "https://fixture.test")

    async def test_character_list_captures_account_context_for_followup_calls(self):
        page = MagicMock()
        account = {}
        future = await wait_for_character_list_response(page, request_context=account)
        response = MagicMock(url="/event/game_record/genshin/api/character/list", ok=True)
        response.request.post_data_json = {"role_id": "123", "server": "os_euro"}
        response.json = AsyncMock(return_value={"retcode": 0, "data": {"list": [{"id": 1001}]}})
        await page.on.call_args.args[1](response)
        self.assertEqual(await future, [{"id": 1001}])
        self.assertEqual(account, {"role_id": "123", "server": "os_euro"})

    async def test_character_list_still_accepts_inventory_if_request_body_is_unavailable(self):
        page = MagicMock()
        account = {}
        future = await wait_for_character_list_response(page, request_context=account)
        response = MagicMock(url="/event/game_record/genshin/api/character/list", ok=True)
        response.request = object()
        response.json = AsyncMock(return_value={"retcode": 0, "data": {"list": [{"id": 1001}]}})
        await page.on.call_args.args[1](response)
        self.assertEqual(await future, [{"id": 1001}])
        self.assertEqual(account, {})

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

    async def test_detail_reuses_character_list_account_context(self):
        detail = {"ok": True, "json": {"retcode": 0, "data": {"list": [{"base": {"id": 1001}}]}}}
        with patch("hoyolab_export.character_detail.browser_fetch_json", new=AsyncMock(return_value=detail)) as fetch:
            await fetch_character_details_batch(MagicMock(), [1001], role_id="123", server="os_euro")
        fetch.assert_awaited_once()
        self.assertEqual(fetch.call_args.kwargs["body"]["role_id"], "123")

    async def test_detail_can_use_context_request_fetcher(self):
        detail = {"ok": True, "json": {"retcode": 0, "data": {"list": [{"base": {"id": 1001}}]}}}
        fetch = AsyncMock(return_value=detail)
        with patch("hoyolab_export.character_detail.browser_fetch_json", new=AsyncMock(side_effect=AssertionError("browser fetch used"))):
            result = await fetch_character_details_batch(
                MagicMock(), [1001], role_id="123", server="os_euro", json_fetcher=fetch,
            )
        self.assertEqual(result["charactersReturned"], 1)
        fetch.assert_awaited_once()

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
