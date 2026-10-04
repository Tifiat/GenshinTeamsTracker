"""Fixture-only coverage for isolated account profile registry and deletion."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.account_profiles import (
    AccountProfileError,
    DuplicateAccountProfile,
    InvalidAccountProfileRegistry,
    UnknownAccountProfile,
    activate_profile,
    active_profile,
    clear_all_profiles,
    create_profile,
    delete_profile,
    ensure_active_profile,
    list_profiles,
    profile_root,
    update_profile_metadata,
)


class AccountProfilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_first_launch_creates_one_draft_and_switches_registered_profiles(self) -> None:
        self.assertEqual(list_profiles(project_root=self.root), [])
        self.assertIsNone(active_profile(project_root=self.root))
        self.assertFalse((self.root / "data").exists())

        first = ensure_active_profile(project_root=self.root)
        self.assertFalse(first["imported"])
        self.assertEqual(ensure_active_profile(project_root=self.root)["id"], first["id"])
        self.assertEqual(
            profile_root(first["id"], project_root=self.root),
            self.root / "data" / "profiles" / first["id"],
        )
        second = create_profile(project_root=self.root)
        self.assertEqual(active_profile(project_root=self.root)["id"], second["id"])
        self.assertEqual(activate_profile(first["id"], project_root=self.root)["id"], first["id"])
        self.assertEqual(len(list_profiles(project_root=self.root)), 2)
        with self.assertRaises(UnknownAccountProfile):
            activate_profile("0" * 32, project_root=self.root)

    def test_metadata_is_bounded_and_duplicate_identity_preserves_existing(self) -> None:
        first = create_profile(project_root=self.root)
        second = create_profile(project_root=self.root)
        imported = update_profile_metadata(
            first["id"], {
                "uid": 600000001, "server": "os_euro", "nickname": "Traveler",
                "adventure_rank": 60, "unknown": "ignored",
            }, project_root=self.root, imported=True,
        )
        self.assertTrue(imported["imported"])
        self.assertNotIn("unknown", imported["metadata"])
        self.assertEqual([row["id"] for row in list_profiles(
            project_root=self.root, include_drafts=False,
        )], [first["id"]])

        with self.assertRaises(DuplicateAccountProfile) as duplicate:
            update_profile_metadata(
                second["id"], {"uid": "600000001", "server": "OS_EURO"},
                project_root=self.root,
            )
        self.assertEqual(duplicate.exception.existing_profile_id, first["id"])
        self.assertEqual(list_profiles(project_root=self.root)[1]["metadata"], {})
        with self.assertRaises(ValueError):
            update_profile_metadata(second["id"], {"avatar_path": "../outside"}, project_root=self.root)
        with self.assertRaises(ValueError):
            update_profile_metadata(second["id"], {"nickname": "x" * 81}, project_root=self.root)

    def test_delete_removes_only_registered_root_and_switches_active(self) -> None:
        first = create_profile(project_root=self.root)
        second = create_profile(project_root=self.root)
        first_root = profile_root(first["id"], project_root=self.root)
        second_root = profile_root(second["id"], project_root=self.root)
        (first_root / "data").mkdir()
        (first_root / "data" / "artifacts.db").write_text("fixture", encoding="utf-8")
        (second_root / "keep.txt").write_text("other profile", encoding="utf-8")
        settings = self.root / "settings.json"
        settings.write_text('{"dont_show_again": true}', encoding="utf-8")

        result = delete_profile(second["id"], project_root=self.root)
        self.assertEqual(result["active_profile_id"], first["id"])
        self.assertFalse(second_root.exists())
        self.assertTrue((first_root / "data" / "artifacts.db").exists())
        self.assertTrue(settings.exists())
        with self.assertRaises(UnknownAccountProfile):
            delete_profile(second["id"], project_root=self.root)

    def test_failed_delete_keeps_registry_and_rejects_links(self) -> None:
        profile = create_profile(project_root=self.root)
        root = profile_root(profile["id"], project_root=self.root)
        outside = self.root / "outside.txt"
        outside.write_text("untouched", encoding="utf-8")
        link = root / "linked-file"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            with patch("run_workspace.account_profiles._delete_tree_safely", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    delete_profile(profile["id"], project_root=self.root)
        else:
            with self.assertRaises(AccountProfileError):
                delete_profile(profile["id"], project_root=self.root)
            self.assertTrue(link.is_symlink())
        self.assertTrue(outside.exists())
        self.assertEqual(active_profile(project_root=self.root)["id"], profile["id"])
        self.assertEqual(len(list_profiles(project_root=self.root)), 1)

    def test_clear_all_removes_registered_profiles_but_not_settings(self) -> None:
        ids = [create_profile(project_root=self.root)["id"] for _ in range(3)]
        settings = self.root / "settings.json"
        settings.write_text('{"dont_show_again": true}', encoding="utf-8")
        result = clear_all_profiles(project_root=self.root)
        self.assertEqual(result["deleted_profile_ids"], ids)
        self.assertFalse((self.root / "data" / "profiles" / "registry.json").exists())
        self.assertEqual(list_profiles(project_root=self.root), [])
        self.assertTrue(settings.exists())
        for profile_id in ids:
            self.assertFalse(profile_root(profile_id, project_root=self.root).exists())

    def test_invalid_registry_and_unsafe_ids_fail_closed(self) -> None:
        registry = self.root / "data" / "profiles" / "registry.json"
        registry.parent.mkdir(parents=True)
        registry.write_text('{"profiles": []}', encoding="utf-8")
        with self.assertRaises(InvalidAccountProfileRegistry):
            list_profiles(project_root=self.root)
        with self.assertRaises(InvalidAccountProfileRegistry):
            create_profile(project_root=self.root)
        with self.assertRaises(ValueError):
            profile_root("../outside", project_root=self.root)
        self.assertEqual(json.loads(registry.read_text(encoding="utf-8")), {"profiles": []})

    def test_missing_registry_does_not_hide_existing_profile_directory(self) -> None:
        orphan = self.root / "data" / "profiles" / ("a" * 32)
        orphan.mkdir(parents=True)
        (orphan / "data.txt").write_text("recover me", encoding="utf-8")
        with self.assertRaises(InvalidAccountProfileRegistry):
            ensure_active_profile(project_root=self.root)
        self.assertEqual((orphan / "data.txt").read_text(encoding="utf-8"), "recover me")

    def test_missing_active_directory_fails_closed(self) -> None:
        profile = create_profile(project_root=self.root)
        profile_root(profile["id"], project_root=self.root).rmdir()
        with self.assertRaises(InvalidAccountProfileRegistry):
            active_profile(project_root=self.root)
        with self.assertRaises(InvalidAccountProfileRegistry):
            ensure_active_profile(project_root=self.root)

    def test_concurrent_creates_have_no_lost_registry_updates(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            created = list(pool.map(
                lambda _: create_profile(project_root=self.root, activate=False),
                range(16),
            ))
        self.assertEqual(len({item["id"] for item in created}), 16)
        self.assertEqual(len(list_profiles(project_root=self.root)), 16)
        self.assertIsNone(active_profile(project_root=self.root))
        self.assertIn(ensure_active_profile(project_root=self.root)["id"],
                      {item["id"] for item in created})
        self.assertEqual(len(list_profiles(project_root=self.root)), 16)


if __name__ == "__main__":
    unittest.main()
