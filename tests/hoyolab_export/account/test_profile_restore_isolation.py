"""Managed ZIP restoration uses fixture roots and never opens the live profile."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from hoyolab_export.offline_profile import PROFILE_FORMAT, PROFILE_MANIFEST_NAME, PROFILE_VERSION
from hoyolab_export.profile_restore import restore_saved_profile
from run_workspace.account_profiles import (
    DuplicateAccountProfile, active_profile, create_profile, list_profiles,
    profile_root, update_profile_metadata,
)


class ProfileRestoreIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.active = create_profile(project_root=self.root)
        update_profile_metadata(
            self.active["id"], {"uid": "600000001", "server": "os_euro"},
            imported=True, project_root=self.root,
        )
        active_root = profile_root(self.active["id"], project_root=self.root)
        (active_root / "sentinel.txt").write_text("preserve", encoding="utf-8")

    def _database(self, *, uid: str = "600000002", bound: bool = True) -> bytes:
        path = self.root / "fixture.db"
        path.unlink(missing_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE fixture (value TEXT)")
            conn.execute("INSERT INTO fixture VALUES ('account data')")
            if bound:
                conn.execute(
                    "CREATE TABLE hoyolab_account_binding (singleton INTEGER PRIMARY KEY, "
                    "account_uid TEXT, server TEXT, bound_at TEXT, binding_method TEXT)"
                )
                conn.execute(
                    "INSERT INTO hoyolab_account_binding VALUES (1, ?, 'os_euro', 'now', 'import')",
                    (uid,),
                )
            conn.commit()
        return path.read_bytes()

    def _archive(self, entries: list[tuple[str, bytes]], *, name: str = "account.zip") -> Path:
        path = self.root / name
        manifest = {
            "format": PROFILE_FORMAT,
            "version": PROFILE_VERSION,
            "includedFiles": [member for member, _ in entries],
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for member, payload in entries:
                archive.writestr(member, payload)
            archive.writestr(PROFILE_MANIFEST_NAME, json.dumps(manifest))
        return path

    def _assert_active_unchanged(self) -> None:
        self.assertEqual(active_profile(project_root=self.root)["id"], self.active["id"])
        self.assertEqual(
            (profile_root(self.active["id"], project_root=self.root) / "sentinel.txt")
            .read_text(encoding="utf-8"), "preserve",
        )

    def test_valid_archive_creates_inactive_isolated_profile(self) -> None:
        archive = self._archive([
            ("data/artifacts.db", self._database()),
            ("data/hoyolab/account_summary.json", json.dumps({
                "uid": "600000002", "server": "os_euro", "nickname": "Fixture",
            }).encode()),
        ])
        result = restore_saved_profile(archive, project_root=self.root)
        created = result["profile"]
        self.assertTrue(created["imported"])
        self.assertEqual(created["metadata"]["nickname"], "Fixture")
        self.assertEqual(created["metadata"]["uid"], "600000002")
        self.assertTrue((profile_root(created["id"], project_root=self.root) / "data" / "artifacts.db").is_file())
        self._assert_active_unchanged()

    def test_duplicate_account_removes_draft_and_preserves_active(self) -> None:
        archive = self._archive([("data/artifacts.db", self._database(uid="600000001"))])
        with self.assertRaises(DuplicateAccountProfile):
            restore_saved_profile(archive, project_root=self.root)
        self.assertEqual(len(list_profiles(project_root=self.root)), 1)
        self._assert_active_unchanged()

    def test_corrupt_or_missing_database_does_not_create_profile(self) -> None:
        for entries in ([('data/artifacts.db', b'not a database')],
                        [('data/hoyolab/account_language.json', b'{}')]):
            with self.subTest(entries=entries[0][0]):
                archive = self._archive(entries)
                with self.assertRaisesRegex(RuntimeError, "database"):
                    restore_saved_profile(archive, project_root=self.root)
                self.assertEqual(len(list_profiles(project_root=self.root)), 1)
                self._assert_active_unchanged()

    def test_summary_cannot_mislabel_database_or_unbound_data(self) -> None:
        for bound, summary in (
            (True, {"uid": "600000003", "server": "os_euro"}),
            (False, {"uid": "600000002", "server": "os_euro"}),
        ):
            with self.subTest(bound=bound):
                archive = self._archive([
                    ("data/artifacts.db", self._database(bound=bound)),
                    ("data/hoyolab/account_summary.json", json.dumps(summary).encode()),
                ])
                with self.assertRaisesRegex(RuntimeError, "summary"):
                    restore_saved_profile(archive, project_root=self.root)
                self.assertEqual(len(list_profiles(project_root=self.root)), 1)
                self._assert_active_unchanged()

    def test_unsafe_duplicate_and_crc_failure_leave_existing_profile(self) -> None:
        database = self._database()
        cases = (
            [("data/artifacts.db", database), ("assets/hoyolab/characters//avatar.png", b"x")],
            [("data/artifacts.db", database), ("data/artifacts.db", database)],
            [("data/artifacts.db", database), ("assets/hoyolab/characters/../avatar.png", b"x")],
            [("data/artifacts.db", database), ("assets/hoyolab/characters/CON.png", b"x")],
            [("data/artifacts.db", database), ("assets/hoyolab/characters/avatar.png:alt", b"x")],
        )
        for entries in cases:
            with self.subTest(name=entries[-1][0]):
                archive = self._archive(entries)
                with self.assertRaises(RuntimeError):
                    restore_saved_profile(archive, project_root=self.root)
                self.assertEqual(len(list_profiles(project_root=self.root)), 1)
                self._assert_active_unchanged()

        archive = self._archive([
            ("data/artifacts.db", database),
            ("data/hoyolab/account_language.json", b"CRC_MARKER"),
        ])
        archive.write_bytes(archive.read_bytes().replace(b"CRC_MARKER", b"BAD_MARKER"))
        with self.assertRaises(zipfile.BadZipFile):
            restore_saved_profile(archive, project_root=self.root)
        self.assertEqual(len(list_profiles(project_root=self.root)), 1)
        self._assert_active_unchanged()


if __name__ == "__main__":
    unittest.main()
