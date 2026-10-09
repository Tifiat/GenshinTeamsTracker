"""No real bootstrap, launcher, profile or project-root mutation in this suite."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import warnings

from run_workspace import profile_context, profile_legacy
from run_workspace.account_profiles import create_profile, profile_root, update_profile_metadata


class DerivedLegacyStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gtt-startup-legacy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = create_profile(project_root=self.root)
        self.target = profile_root(self.profile["id"], project_root=self.root)

    def _file(self, root, relative, data=b"fixture"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _database(self):
        database = self.target / "data/artifacts.db"
        database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("CREATE TABLE artifacts(id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO artifacts VALUES (1)")
            conn.commit()
        return database

    def _bootstrap(self):
        with patch.object(profile_context, "PROJECT_ROOT", self.root), \
                patch.object(profile_context, "PROFILE_ID", None), \
                patch.object(profile_context, "ACCOUNT_ROOT", self.root), \
                patch.dict(os.environ, {}, clear=True):
            return profile_context.bootstrap_profile()

    def test_recreated_runs_do_not_block_existing_draft_or_move_data(self):
        database = self._database()
        legacy = self._file(self.root, "data/gcsim/runs/new-run/config.txt", b"legacy-run")
        existing = self._file(self.target, "data/gcsim/runs/saved-run/config.txt", b"profile-run")
        before = database.read_bytes()
        for _ in range(2):
            with self.assertLogs(profile_legacy.__name__, level="WARNING"):
                self.assertEqual(self._bootstrap(), self.target)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(legacy.read_bytes(), b"legacy-run")
        self.assertEqual(existing.read_bytes(), b"profile-run")
        self.assertFalse((self.target / ".legacy-migration.json").exists())
        self.assertTrue(profile_legacy.has_legacy_account_data(project_root=self.root))

    def test_imported_profile_also_preserves_orphan_cache(self):
        self._database()
        update_profile_metadata(self.profile["id"], {"uid": "600000002", "server": "os_euro"},
                                imported=True, project_root=self.root)
        orphan = self._file(self.root, "data/cache/gcsim_optimizer/cache.json")
        with self.assertLogs(profile_legacy.__name__, level="WARNING"):
            self.assertEqual(self._bootstrap(), self.target)
        self.assertTrue(orphan.is_file())

    def _empty_legacy_database(self):
        path = self.root / "data/artifacts.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE artifacts(id INTEGER PRIMARY KEY)")
            conn.commit()
        return path

    def test_recreated_empty_database_and_sidecars_do_not_block_repeat_launch(self):
        target = self._database()
        source = self._empty_legacy_database()
        wal = self._file(self.root, "data/artifacts.db-wal", b"")
        shm = self._file(self.root, "data/artifacts.db-shm", bytes(32768))
        paths = (target, source, wal, shm)
        before = [p.read_bytes() for p in paths]
        for _ in range(2):
            with self.assertLogs(profile_legacy.__name__, level="WARNING"):
                self.assertEqual(self._bootstrap(), self.target)
        self.assertEqual([p.read_bytes() for p in paths], before)
        self.assertFalse((self.target / ".legacy-migration.json").exists())
        self.assertTrue(profile_legacy.has_legacy_account_data(project_root=self.root))

    def test_empty_database_does_not_block_imported_profile(self):
        self._database()
        source = self._empty_legacy_database()
        update_profile_metadata(self.profile["id"], {"uid": "600000002", "server": "os_euro"},
                                imported=True, project_root=self.root)
        before = source.read_bytes()
        with self.assertLogs(profile_legacy.__name__, level="WARNING"):
            self.assertEqual(self._bootstrap(), self.target)
        self.assertEqual(source.read_bytes(), before)

    def test_nonempty_wal_cannot_hide_account_data_behind_empty_database(self):
        self._database()
        self._empty_legacy_database()
        wal = self._file(self.root, "data/artifacts.db-wal", b"uncheckpointed rows")
        with self.assertRaises(profile_legacy.LegacyProfileDataError):
            self._bootstrap()
        self.assertEqual(wal.read_bytes(), b"uncheckpointed rows")

    def test_any_legacy_database_row_retains_collision_error(self):
        self._database()
        source = self._empty_legacy_database()
        with closing(sqlite3.connect(source)) as conn:
            conn.execute("CREATE TABLE unknown_account_data(value TEXT)")
            conn.execute("INSERT INTO unknown_account_data VALUES ('keep')")
            conn.commit()
        before = source.read_bytes()
        with self.assertRaisesRegex(profile_legacy.LegacyProfileDataError, "already contains"):
            self._bootstrap()
        self.assertEqual(source.read_bytes(), before)

    def test_rollback_journal_prevents_empty_database_exception(self):
        self._database()
        self._empty_legacy_database()
        journal = self._file(self.root, "data/artifacts.db-journal", b"pending transaction")
        self.assertTrue(profile_legacy.startup_legacy_migration_needed(
            self.profile["id"], project_root=self.root))
        with self.assertRaisesRegex(RuntimeError, "Cannot inspect the legacy account binding"):
            self._bootstrap()
        self.assertEqual(journal.read_bytes(), b"pending transaction")

    def test_corrupt_legacy_database_retains_collision_error(self):
        self._database()
        source = self._file(self.root, "data/artifacts.db", b"not a database")
        with self.assertRaisesRegex(RuntimeError, "Cannot inspect the legacy account binding"):
            self._bootstrap()
        self.assertEqual(source.read_bytes(), b"not a database")

    def test_empty_database_with_primary_state_retains_collision_error(self):
        self._database()
        self._empty_legacy_database()
        self._file(self.root, "state.json")
        with self.assertRaisesRegex(profile_legacy.LegacyProfileDataError, "already contains"):
            self._bootstrap()

    def test_empty_database_first_upgrade_still_migrates(self):
        source = self._empty_legacy_database()
        before = source.read_bytes()
        self.assertEqual(self._bootstrap(), self.target)
        self.assertFalse(source.exists())
        self.assertEqual((self.target / "data/artifacts.db").read_bytes(), before)

    def test_all_derived_output_kinds_remain_separate_on_repeat_launch(self):
        self._database()
        outputs = ("data/gcsim/runs", "data/gcsim/farming-runs", "data/gcsim/optimizer-runs",
                   "data/gcsim/optimizer-go-runs", "data/cache/gcsim_optimizer")
        files = [self._file(self.root, relative + "/kept.txt") for relative in outputs]
        for _ in range(2):
            with self.assertLogs(profile_legacy.__name__, level="WARNING"):
                self.assertEqual(self._bootstrap(), self.target)
        for relative, source in zip(outputs, files, strict=True):
            self.assertEqual(source.read_bytes(), b"fixture")
            self.assertFalse((self.target / relative).exists())

    def test_diagnostic_cannot_turn_into_a_fatal_python_warning(self):
        self._database()
        orphan = self._file(self.root, "data/gcsim/runs/one/config.txt")
        with warnings.catch_warnings(), self.assertLogs(profile_legacy.__name__, level="WARNING"):
            warnings.simplefilter("error")
            self.assertEqual(self._bootstrap(), self.target)
        self.assertTrue(orphan.exists())

    def test_real_legacy_state_still_fails_closed_without_any_move(self):
        database = self._database()
        before = database.read_bytes()
        legacy = self._file(self.root, "state.json")
        self._file(self.root, "data/gcsim/runs/one/config.txt")
        with self.assertRaisesRegex(profile_legacy.LegacyProfileDataError, "already contains"):
            self._bootstrap()
        self.assertEqual(database.read_bytes(), before)
        self.assertTrue(legacy.exists())
        self.assertFalse((self.target / ".legacy-migration.json").exists())

    def test_legacy_database_sidecar_is_not_treated_as_disposable_output(self):
        self._database()
        source = self._file(self.root, "data/artifacts.db-wal")
        with self.assertRaises(profile_legacy.LegacyProfileDataError):
            self._bootstrap()
        self.assertTrue(source.exists())

    def test_journal_resumes_even_with_populated_target_and_only_runs_left(self):
        database = self._database()
        before = database.read_bytes()
        legacy = self._file(self.root, "data/gcsim/runs/one/config.txt", b"resumable")
        journal = self.target / ".legacy-migration.json"
        journal.write_text(json.dumps({"schema_version": 1, "profile_id": self.profile["id"],
            "paths": ["data/artifacts.db", "data/gcsim/runs"], "started_at": "fixture"}), encoding="utf-8")
        self.assertEqual(self._bootstrap(), self.target)
        self.assertFalse(legacy.exists())
        self.assertFalse(journal.exists())
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual((self.target / "data/gcsim/runs/one/config.txt").read_bytes(), b"resumable")

    def test_empty_first_upgrade_still_migrates_derived_outputs(self):
        legacy = self._file(self.root, "data/gcsim/runs/one/config.txt", b"first-upgrade")
        self.assertEqual(self._bootstrap(), self.target)
        self.assertFalse(legacy.exists())
        self.assertEqual((self.target / "data/gcsim/runs/one/config.txt").read_bytes(), b"first-upgrade")

    def test_malformed_journal_is_not_hidden_by_derived_output_exception(self):
        self._database()
        legacy = self._file(self.root, "data/gcsim/runs/one/config.txt")
        self._file(self.target, ".legacy-migration.json", b"invalid json")
        with self.assertRaisesRegex(profile_legacy.LegacyProfileDataError, "cannot be read"):
            self._bootstrap()
        self.assertTrue(legacy.exists())

    def test_linked_derived_source_cannot_bypass_safety_checks(self):
        self._database()
        legacy = self._file(self.root, "data/gcsim/runs/one/config.txt")
        real_check = profile_legacy._is_link_or_reparse
        with patch.object(profile_legacy, "_is_link_or_reparse", side_effect=lambda p: p == legacy or real_check(p)):
            with self.assertRaisesRegex(profile_legacy.LegacyProfileDataError, "link or junction"):
                self._bootstrap()
        self.assertTrue(legacy.exists())


if __name__ == "__main__":
    unittest.main()
