from __future__ import annotations

import unittest
import asyncio
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from hoyolab_export import import_pipeline as pipeline
from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_variant_id

from hoyolab_export.import_pipeline import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    sync_account_storage_for_import,
    sync_static_reference_catalogs_for_import,
    _sync_image_paths_only,
)
from hoyolab_export.account_storage import init_account_storage
from hoyolab_export.artifact_db import connect_db, init_db
from run_workspace.abyss.source_data_runtime import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH as RUNTIME_HOYOLAB_ABYSS_PERIOD_PATH,
)


class ImportSharedAssetsTest(unittest.TestCase):
    def test_publication_replaces_downloaded_shared_layers_with_package_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "old_element.png"
            Image.new("RGBA", (8, 8), "red").save(old)
            previous = {"sharedAssets": {"elements": {"pyro": str(old)}, "custom": {"unsafe": str(old)}}}
            with patch.object(pipeline, "ACCOUNT_ROOT", root):
                merged = pipeline._merge_asset_manifests(previous, {})
            shared = merged["sharedAssets"]
            self.assertEqual(set(shared["elements"]), {"anemo", "geo", "electro", "dendro", "hydro", "pyro", "cryo"})
            self.assertEqual(set(shared["characterBackgrounds"]), {"4", "5"})
            self.assertEqual(set(shared["weaponBackgrounds"]), {"3", "4", "5"})
            self.assertNotIn("custom", shared)
            self.assertEqual(shared["elements"]["pyro"], "assets/filters/element_pyro.png")
            self.assertNotIn(str(old), str(shared))

    def test_only_allowlisted_package_paths_can_escape_account_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            account = Path(temporary) / "account"
            account.mkdir()
            with (
                patch.object(pipeline, "ACCOUNT_ROOT", account),
                patch.object(pipeline, "account_asset_path", side_effect=lambda value: account / value),
            ):
                expected = pipeline.PROJECT_ROOT / "assets/filters/element_geo.png"
                self.assertEqual(pipeline._asset_local_path("assets/filters/element_geo.png"), expected)
                self.assertIsNone(pipeline._asset_local_path(str(expected)))
                self.assertIsNone(pipeline._asset_local_path("../outside.png"))
                self.assertEqual(pipeline._asset_local_path("assets/hoyolab/portrait.png"), account / "assets/hoyolab/portrait.png")

    def test_unique_image_recovery_survives_without_shared_cache_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "empty-package"
            package.mkdir()
            raw = root / "portrait.png"
            Image.new("RGBA", (8, 8), "blue").save(raw)
            previous = {"characterAssets": [{"character": {"id": 1001}, "portrait": str(raw)}],
                        "sharedAssets": {"elements": {"pyro": str(raw)}}}
            fresh = {"characterAssets": [{"character": {"id": 1001}, "portrait": str(root / "missing.png")}]}
            with patch.object(pipeline, "ACCOUNT_ROOT", root), patch.object(pipeline, "PROJECT_ROOT", package):
                merged = pipeline._merge_asset_manifests(previous, fresh)
            self.assertEqual(merged["characterAssets"][0]["portrait"], str(raw))
            self.assertEqual(merged["sharedAssets"], {"elements": {}, "characterBackgrounds": {}, "weaponBackgrounds": {}})

    def test_traveler_side_icons_use_one_download_and_the_existing_anchor_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = root / "account.db"
            with closing(connect_db(db)) as conn, conn:
                init_db(conn)
                init_account_storage(conn)
                for element in TRAVELER_ELEMENTS:
                    character_id = 10000007 if element == "Cryo" else traveler_variant_id(10000007, element)
                    conn.execute(
                        "INSERT INTO account_characters (character_id, name, element, side_icon_url) VALUES (?, 'Traveler', ?, ?)",
                        (character_id, element, "https://example.invalid/unique_traveler.png"),
                    )
            progress = []
            def download(_url: str, destination: Path) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (8, 8), "green").save(destination)
            with (
                patch.object(pipeline, "ARTIFACT_DB_PATH", db),
                patch.object(pipeline, "HOYOLAB_ASSETS_DIR", root / "assets"),
                patch.object(pipeline, "_download_url_to_file", side_effect=download) as downloader,
            ):
                first = asyncio.run(pipeline.refresh_import_side_icons(progress_callback=lambda *event: progress.append(event)))
                second = asyncio.run(pipeline.refresh_import_side_icons())
            self.assertEqual(downloader.call_count, 1)
            self.assertEqual(first["downloaded"], 1)
            self.assertEqual(second["downloaded"], 0)
            self.assertEqual(progress, [("download", 0, 1), ("download", 1, 1)])
            with closing(connect_db(db)) as conn:
                paths = [row[0] for row in conn.execute("SELECT side_icon_path FROM account_characters")]
            self.assertEqual(len(paths), 7)
            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(Path(paths[0]).name, "char_10000007.png")


class ImportPipelineAccountStorageTest(unittest.TestCase):
    def test_image_only_sync_keeps_account_data_and_equipment_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "account.db"
            with closing(connect_db(db)) as conn, conn:
                init_db(conn)
                init_account_storage(conn)
                conn.execute(
                    "INSERT INTO account_characters (character_id, name, level, portrait_path) VALUES (1, 'Hero', 90, 'old.png')"
                )
                conn.execute(
                    "INSERT INTO account_weapon_observed_stacks (weapon_fingerprint, weapon_id, name, level, icon_path) "
                    "VALUES ('weapon-1', 2, 'Blade', 80, 'old-weapon.png')"
                )
            manifest = {
                "characterAssets": [{"character": {"id": 1}, "crop": "new-character.png"}],
                "weaponAssets": [{"weapon": {"id": 2}, "crop": "new-weapon.png"}],
            }
            with patch("hoyolab_export.import_pipeline.ARTIFACT_DB_PATH", db):
                _sync_image_paths_only(manifest)
            with closing(connect_db(db)) as conn:
                character = conn.execute("SELECT name, level, portrait_path FROM account_characters").fetchone()
                weapon = conn.execute("SELECT name, level, icon_path FROM account_weapon_observed_stacks").fetchone()
            self.assertEqual(tuple(character), ("Hero", 90, "new-character.png"))
            self.assertEqual(tuple(weapon), ("Blade", 80, "new-weapon.png"))

    def test_import_pipeline_uses_runtime_abyss_period_path(self) -> None:
        self.assertEqual(
            DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
            RUNTIME_HOYOLAB_ABYSS_PERIOD_PATH,
        )

    def test_account_storage_sync_downloads_side_icons_by_default(self) -> None:
        class FakeSummary:
            def to_dict(self) -> dict[str, object]:
                return {"characters_seen": 1, "weapon_stacks_seen": 1}

        with patch(
            "hoyolab_export.import_pipeline.sync_account_storage_from_local_files",
            return_value=FakeSummary(),
        ) as sync_mock:
            summary, error = sync_account_storage_for_import()

        self.assertIsNone(error)
        self.assertEqual(summary, {"characters_seen": 1, "weapon_stacks_seen": 1})
        sync_mock.assert_called_once_with(download_side_icons=True)

    def test_account_storage_sync_failure_is_nonfatal_result(self) -> None:
        with patch(
            "hoyolab_export.import_pipeline.sync_account_storage_from_local_files",
            side_effect=RuntimeError("db locked"),
        ):
            summary, error = sync_account_storage_for_import()

        self.assertIsNone(summary)
        self.assertEqual(error, "db locked")


class ImportPipelineStaticCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        # Catalog orchestration fixtures must never open the user's runtime DB.
        for name in ("connect_db", "rebuild_character_trait_reference_from_catalog"):
            patcher = patch("hoyolab_export.import_pipeline." + name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_static_catalog_sync_refreshes_artifact_sets_and_traits(self) -> None:
        class FakeTraitEntry:
            traits = ("moonsign",)
            source_character_entry_page_id = "10000001"
            name = "Test Character"
            icon_url = ""
            source_entry_page_id = "source"
            source_language = "en-us"

        class FakeTraitCatalog:
            source = "hoyowiki_team_bonus_entry"
            entries = (FakeTraitEntry(), FakeTraitEntry())
            fetched_at = "now"
            language = "en-us"

        with patch(
            "hoyolab_export.import_pipeline.ensure_artifact_set_catalog",
            return_value={"source": "network", "sets_seen": 1},
        ) as set_mock, patch(
            "hoyolab_export.import_pipeline.load_or_refresh_character_trait_catalog",
            return_value=FakeTraitCatalog(),
        ) as trait_mock:
            summary, error = sync_static_reference_catalogs_for_import()

        self.assertIsNone(error)
        set_mock.assert_called_once()
        self.assertTrue(set_mock.call_args.kwargs["allow_network"])
        self.assertTrue(set_mock.call_args.kwargs["missing_only"])
        trait_mock.assert_called_once_with()
        self.assertEqual(summary["artifactSetCatalog"]["source"], "network")
        self.assertEqual(summary["characterTraitCatalog"]["entries"], 2)

    def test_static_catalog_sync_failure_is_nonfatal_result(self) -> None:
        with patch(
            "hoyolab_export.import_pipeline.ensure_artifact_set_catalog",
            side_effect=RuntimeError("catalog offline"),
        ), patch(
            "hoyolab_export.import_pipeline.load_or_refresh_character_trait_catalog",
            side_effect=RuntimeError("traits offline"),
        ):
            summary, error = sync_static_reference_catalogs_for_import()

        self.assertEqual(summary, {})
        self.assertIn("artifact set catalog: catalog offline", error or "")
        self.assertIn("character trait catalog: traits offline", error or "")


if __name__ == "__main__":
    unittest.main()
