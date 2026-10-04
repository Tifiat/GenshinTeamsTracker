"""Offline export fixtures: never touch or export a user's live profile."""
from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from hoyolab_export import offline_profile as profile
from hoyolab_export.import_store import prepare_import_store, stage_import_attempt, commit_import_snapshot
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_weapon, fake_account_details,
)


class ProfileImportProjectionTest(unittest.TestCase):
    def test_export_uses_one_database_snapshot_despite_stale_source_files(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            db = root / "data/artifacts.db"
            data_dir = root / "data/hoyolab"
            data_dir.mkdir(parents=True)
            prepare_import_store(db)
            details = fake_account_details()
            details["json"]["retcode"] = 0
            details["json"]["data"]["list"][0]["relics"] = []
            character = fake_account_character()
            character["name"] = "Current source"
            attempt = stage_import_attempt(
                db, account_uid="123", server="os_euro", account_characters=[character],
                account_weapons=[fake_account_weapon()], account_character_details=details,
            )
            commit_import_snapshot(db, attempt_id=attempt, account_sync_context={
                "character_stats_catalog": None, "weapon_stats_catalog": None,
                "character_region_entries": [], "character_trait_entries": [], "gcsim_key_resolver": None,
            }, side_icon_cache_dir=root / "icons")
            stale = data_dir / "account_characters.json"
            stale.write_text('[{"name":"Stale projection"}]', encoding="utf-8")
            data_files = tuple(data_dir / name for name in (
                "account_characters.json", "account_weapons.json", "account_character_details.json",
                "account_language.json", "crop_manifest.json",
            ))
            for name, value in {
                "PROJECT_ROOT": root, "ACCOUNT_ROOT": root,
                "ARTIFACT_DB_PATH": db, "HOYOLAB_DATA_DIR": data_dir,
                "PROFILE_DATA_FILES": data_files, "PROFILE_ASSET_DIRS": (),
                "PROFILE_EXPORT_STATE_FILE": data_dir / "offline_export_state.json",
            }.items():
                stack.enter_context(patch.object(profile, name, value))
            stack.enter_context(patch.object(profile, "ensure_hoyolab_dirs"))
            target = root / "fixture.zip"
            result = profile.export_offline_profile(target)
            with zipfile.ZipFile(target) as archive:
                exported = json.loads(archive.read("data/hoyolab/account_characters.json"))
                self.assertEqual(exported, [character])
                language = json.loads(archive.read("data/hoyolab/account_language.json"))
                self.assertEqual(language["attemptId"], attempt)
                self.assertNotIn("profile-projections", " ".join(archive.namelist()))
            self.assertEqual(json.loads(stale.read_text())[0]["name"], "Stale projection")
            self.assertEqual(profile.current_profile_signature()["hash"], result["signature"]["hash"])
            self.assertTrue(profile.is_current_profile_exported())

    def test_corrupt_database_is_not_silently_copied_into_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder) / "bad.db", Path(folder) / "snapshot.db"
            source.write_bytes(b"not a database")
            with self.assertRaisesRegex(RuntimeError, "consistent account snapshot"):
                profile._backup_sqlite_db(source, destination)

    def test_snapshot_projection_files_live_only_in_temporary_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "legacy.db"
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("CREATE TABLE legacy (id INTEGER)")
            self.assertEqual(profile._snapshot_projection_files(db), {})
            self.assertFalse((db.parent / "profile-projections").exists())
