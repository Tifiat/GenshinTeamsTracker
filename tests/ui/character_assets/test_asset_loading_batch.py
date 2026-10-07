"""Batch boundaries must preserve fresh assets, containment and equipment badges."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hoyolab_export import asset_paths
from hoyolab_export.artifact_db import connect_db, init_db
from ui.character_assets import load_account_weapon_stack_asset_items


class AssetLookupBatchTest(unittest.TestCase):
    def test_manifest_is_statted_once_per_batch_and_again_on_next_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text('{"characterAssets": []}', encoding="utf-8")
            original_stat = Path.stat
            calls = []
            def stat(path, *args, **kwargs):
                if path == manifest:
                    calls.append(path)
                return original_stat(path, *args, **kwargs)
            asset_paths._read_manifest.cache_clear()
            with patch.object(asset_paths, "MANIFEST_PATH", manifest), patch.object(Path, "stat", stat):
                with asset_paths.asset_lookup_batch():
                    for _ in range(3):
                        self.assertEqual(asset_paths.current_manifest(), {"characterAssets": []})
                self.assertEqual(len(calls), 1)
                with asset_paths.asset_lookup_batch():
                    asset_paths.current_manifest()
                asset_paths.current_manifest()
                self.assertEqual(len(calls), 3)
            asset_paths._read_manifest.cache_clear()

    def test_nested_batch_reuses_checks_and_exception_releases_them(self):
        with patch.object(asset_paths, "_existing_manifest_asset", return_value=Path("checked")) as check:
            with self.assertRaisesRegex(ValueError, "fixture"):
                with asset_paths.asset_lookup_batch():
                    self.assertEqual(asset_paths.existing_manifest_asset("image"), Path("checked"))
                    with asset_paths.asset_lookup_batch():
                        asset_paths.existing_manifest_asset("image")
                    self.assertEqual(check.call_count, 1)
                    raise ValueError("fixture")
            asset_paths.existing_manifest_asset("image")
            self.assertEqual(check.call_count, 2)

    def test_batch_is_not_shared_with_another_thread(self):
        with patch.object(asset_paths, "_existing_manifest_asset", return_value=None) as check:
            with asset_paths.asset_lookup_batch():
                asset_paths.existing_manifest_asset("missing")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asset_paths.existing_manifest_asset, "missing").result()
                asset_paths.existing_manifest_asset("missing")
            self.assertEqual(check.call_count, 2)

    def test_next_batch_rechecks_manifest_created_deleted_and_foreign_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "account"
            root.mkdir()
            manifest = root / "crop_manifest.json"
            first, second, foreign = root / "first.png", root / "second.png", parent / "foreign.png"
            first.write_bytes(b"fixture")
            foreign.write_bytes(b"foreign")
            manifest.write_text(json.dumps({"sharedAssets": {"elements": {"pyro": str(first)}}}), encoding="utf-8")
            asset_paths._read_manifest.cache_clear()
            with patch.object(asset_paths, "ACCOUNT_ROOT", root), patch.object(asset_paths, "MANIFEST_PATH", manifest):
                with asset_paths.asset_lookup_batch():
                    self.assertEqual(asset_paths.element_icon_path("pyro"), first)
                    self.assertIsNone(asset_paths.existing_manifest_asset(second))
                    self.assertIsNone(asset_paths.existing_manifest_asset(foreign))
                    self.assertIsNone(asset_paths.existing_manifest_asset(root / ".." / foreign.name))
                # A completed import changes the manifest and files before the
                # next UI refresh, which must not reuse either positive/negative hits.
                first.unlink()
                second.write_bytes(b"new fixture")
                manifest.write_text(json.dumps({"sharedAssets": {"elements": {"pyro": str(second)}}}), encoding="utf-8")
                with asset_paths.asset_lookup_batch():
                    self.assertEqual(asset_paths.element_icon_path("pyro"), second)
                    self.assertIsNone(asset_paths.existing_manifest_asset(first))
                    self.assertIsNone(asset_paths.existing_manifest_asset(foreign))
                # Switching to another root (a real switch starts a new process)
                # does not inherit checked paths from the earlier completed read.
                with patch.object(asset_paths, "ACCOUNT_ROOT", parent):
                    with asset_paths.asset_lookup_batch():
                        self.assertEqual(asset_paths.existing_manifest_asset(foreign), foreign)
            asset_paths._read_manifest.cache_clear()


class WeaponInventoryBatchTest(unittest.TestCase):
    def test_bulk_read_keeps_sorted_owners_filters_and_refreshes_after_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "fixture.db"
            icon = root / "icon.png"
            icon.write_bytes(b"fixture")
            with closing(connect_db(database)) as conn:
                init_db(conn)
                conn.executemany("""INSERT INTO account_characters
                    (character_id,name,side_icon_path) VALUES (?,?,?)""",
                    [(3, "Third", str(icon)), (1, "First", str(icon)), (2, "Missing icon", str(root / "missing.png"))])
                conn.executemany("""INSERT INTO account_weapon_observed_stacks
                    (weapon_fingerprint,weapon_id,name,rarity,icon_path,known_count)
                    VALUES (?,?,?, ?,?,3)""", [
                        ("owned", 1, "Owned", 5, str(icon)),
                        ("unowned", 2, "Unowned", 4, str(icon)),
                        ("low", 3, "Low", 1, str(icon)),
                        ("missing", 4, "Missing", 5, str(root / "missing.png")),
                    ])
                conn.executemany("""INSERT INTO account_character_equipped_weapons
                    (character_id,weapon_fingerprint,updated_at) VALUES (?, 'owned', 'fixture')""", [(3,), (1,), (2,)])
                conn.commit()

            statements = []
            def traced_connect(path):
                connection = connect_db(path)
                connection.set_trace_callback(lambda sql: statements.append(" ".join(sql.lower().split())))
                return connection

            with patch("ui.character_assets.connect_db", side_effect=traced_connect), \
                    patch.object(asset_paths, "current_manifest", return_value={}):
                items = load_account_weapon_stack_asset_items(db_path=database)
                by_key = {item["metadata"]["weapon"]["source_key"]: item for item in items}
                self.assertEqual(set(by_key), {"owned", "unowned"})
                self.assertEqual([b["character_id"] for b in by_key["owned"]["metadata"]["owner_badges"]], ["1", "3"])
                self.assertNotIn("owner_badges", by_key["unowned"]["metadata"])
                self.assertEqual(sum(s.startswith("select") and "from account_character_equipped_weapons" in s for s in statements), 1)
                self.assertEqual(sum(s.startswith("create table if not exists account_character_equipped_weapons") for s in statements), 1)

                with closing(connect_db(database)) as conn:
                    conn.execute("UPDATE account_character_equipped_weapons SET weapon_fingerprint='unowned' WHERE character_id=1")
                    conn.commit()
                fresh = {item["metadata"]["weapon"]["source_key"]: item for item in load_account_weapon_stack_asset_items(db_path=database)}
                self.assertEqual([b["character_id"] for b in fresh["owned"]["metadata"]["owner_badges"]], ["3"])
                self.assertEqual([b["character_id"] for b in fresh["unowned"]["metadata"]["owner_badges"]], ["1"])
