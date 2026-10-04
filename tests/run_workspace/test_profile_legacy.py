"""Fixture-only checks for bounded legacy account moves and cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.account_profiles import create_profile, profile_root
from run_workspace.profile_legacy import (
    ACCOUNT_RELATIVE_PATHS,
    LegacyProfileDataError,
    clear_legacy_account_data,
    has_legacy_account_data,
    migrate_legacy_account_data,
)


class LegacyProfileDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = create_profile(project_root=self.root)
        self.target = profile_root(self.profile["id"], project_root=self.root)

    def _legacy_file(self, relative: str, content: str = "account") -> Path:
        path = self.root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_migration_moves_only_account_allowlist_and_is_idempotent(self) -> None:
        self.assertIn("data/gcsim/runs", ACCOUNT_RELATIVE_PATHS)
        self.assertNotIn("debug/hoyolab_import.lock", ACCOUNT_RELATIVE_PATHS)
        account_files = (
            "data/artifacts.db", "data/artifacts.db-wal",
            "data/hoyolab/account_characters.json", "assets/hoyolab/characters/a.png",
            "hoyolab_export/profile/cookies.json", "debug/hoyolab/import_log.json",
            "state.json", "runs_history.json", "data/history/abyss/one/snapshot.json",
            "data/pvp/decks/deck.json", "data/gcsim/runs/gcsim-browser-prepare/config.txt",
            "data/gcsim/farming-runs/run.txt", "data/gcsim/optimizer-runs/run.txt",
            "data/gcsim/optimizer-go-runs/run.txt", "data/cache/gcsim_optimizer/cache.json",
        )
        for relative in account_files:
            self._legacy_file(relative)
        shared = (
            "settings.json", "debug/hoyolab_import.lock",
            "data/gcsim/engines/engine.bin", "data/gcsim/sources/source.zip",
            "data/cache/abyss/source_data/period.json",
        )
        for relative in shared:
            self._legacy_file(relative, "shared")

        self.assertTrue(has_legacy_account_data(project_root=self.root))
        result = migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        self.assertIn("data/artifacts.db", result["moved"])
        self.assertIn("data/gcsim/runs", result["moved"])
        for relative in account_files:
            self.assertFalse(self.root.joinpath(*relative.split("/")).exists())
            self.assertEqual(self.target.joinpath(*relative.split("/")).read_text(encoding="utf-8"), "account")
        for relative in shared:
            self.assertEqual(self.root.joinpath(*relative.split("/")).read_text(encoding="utf-8"), "shared")
        self.assertFalse((self.target / ".legacy-migration.json").exists())
        self.assertFalse(has_legacy_account_data(project_root=self.root))
        self.assertEqual(migrate_legacy_account_data(
            self.profile["id"], project_root=self.root,
        )["moved"], [])

    def test_interrupted_move_resumes_without_copying_or_overwriting(self) -> None:
        first = self._legacy_file("data/artifacts.db", "database")
        second = self._legacy_file("data/hoyolab/account_characters.json", "snapshot")
        from run_workspace import profile_legacy
        real_replace = profile_legacy._replace_owned_path
        calls = 0

        def interrupt(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated interruption")
            real_replace(source, destination)

        with patch.object(profile_legacy, "_replace_owned_path", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue((self.target / ".legacy-migration.json").exists())

        result = migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        self.assertEqual(result["already_moved"], ["data/artifacts.db"])
        self.assertEqual(result["moved"], ["data/hoyolab"])
        self.assertEqual((self.target / "data/artifacts.db").read_text(encoding="utf-8"), "database")
        self.assertEqual((self.target / "data/hoyolab/account_characters.json").read_text(encoding="utf-8"), "snapshot")
        self.assertFalse((self.target / ".legacy-migration.json").exists())

    def test_existing_destination_fails_before_any_legacy_move(self) -> None:
        source = self._legacy_file("data/artifacts.db", "legacy")
        destination = self.target / "data/hoyolab"
        destination.mkdir(parents=True)
        (destination / "keep.json").write_text("profile", encoding="utf-8")
        with self.assertRaises(LegacyProfileDataError):
            migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        self.assertTrue(source.exists())
        self.assertEqual((destination / "keep.json").read_text(encoding="utf-8"), "profile")

    def test_empty_legacy_folders_do_not_claim_an_existing_account(self) -> None:
        (self.root / "data" / "hoyolab").mkdir(parents=True)
        (self.root / "assets" / "hoyolab" / "characters").mkdir(parents=True)
        (self.root / "debug" / "hoyolab").mkdir(parents=True)
        self.assertFalse(has_legacy_account_data(project_root=self.root))
        result = migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        self.assertEqual(result["moved"], [])
        self.assertFalse((self.target / ".legacy-migration.json").exists())

    def test_linked_descendant_blocks_move_and_clear_before_changes(self) -> None:
        source = self._legacy_file("data/artifacts.db", "legacy")
        folder = self.root / "data" / "hoyolab"
        folder.mkdir(parents=True)
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            os.symlink(outside, folder / "linked")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises(LegacyProfileDataError):
            migrate_legacy_account_data(self.profile["id"], project_root=self.root)
        with self.assertRaises(LegacyProfileDataError):
            clear_legacy_account_data(project_root=self.root)
        self.assertTrue(source.exists())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
        self.assertFalse((self.target / ".legacy-migration.json").exists())

    def test_detected_reparse_point_blocks_all_changes_without_host_symlink_support(self) -> None:
        source = self._legacy_file("data/artifacts.db", "legacy")
        linked = self._legacy_file("data/hoyolab/linked", "fixture")
        from run_workspace import profile_legacy
        real_check = profile_legacy._is_link_or_reparse
        with patch.object(profile_legacy, "_is_link_or_reparse",
                          side_effect=lambda path: path == linked or real_check(path)):
            with self.assertRaises(LegacyProfileDataError):
                migrate_legacy_account_data(self.profile["id"], project_root=self.root)
            with self.assertRaises(LegacyProfileDataError):
                clear_legacy_account_data(project_root=self.root)
        self.assertTrue(source.exists())
        self.assertTrue(linked.exists())

    def test_clear_removes_exact_legacy_paths_and_preserves_global_state(self) -> None:
        account = self._legacy_file("data/hoyolab/account_weapons.json")
        db = self._legacy_file("data/artifacts.db-shm")
        shared = self._legacy_file("data/gcsim/engines/engine.bin", "shared")
        settings = self._legacy_file("settings.json", "shared")
        lock = self._legacy_file("debug/hoyolab_import.lock", "shared")
        result = clear_legacy_account_data(project_root=self.root)
        self.assertIn("data/hoyolab", result["removed"])
        self.assertFalse(account.exists())
        self.assertFalse(db.exists())
        self.assertTrue(shared.exists())
        self.assertTrue(settings.exists())
        self.assertTrue(lock.exists())
        self.assertTrue(self.target.exists())


if __name__ == "__main__":
    unittest.main()
