"""Fixture-only lifecycle checks for account switching and destructive actions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from run_workspace.account_profiles import (
    active_profile, create_profile, list_profiles, profile_root, update_profile_metadata,
)
from run_workspace import profile_context, profile_control


class ProfileControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_global_leases_reject_a_second_owner_and_release(self) -> None:
        with profile_control.profile_supervisor_lock(project_root=self.root):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with profile_control.profile_supervisor_lock(project_root=self.root):
                    pass
        with profile_control.profile_supervisor_lock(project_root=self.root):
            pass
        with profile_control.profile_operation_lock(project_root=self.root):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with profile_control.profile_operation_lock(project_root=self.root):
                    pass
        with profile_control.profile_operation_lock(project_root=self.root):
            pass

    def test_delete_refuses_import_and_browser_owners(self) -> None:
        profile = create_profile(project_root=self.root)
        root = profile_root(profile["id"], project_root=self.root)
        lock = root / "debug" / "hoyolab_import.lock"
        with profile_control._file_lock(lock, label="fixture import", create=True):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                profile_control.apply_profile_operation(
                    "delete", profile["id"], project_root=self.root,
                )
        self.assertTrue(root.exists())
        browser = root / "hoyolab_export" / "profile"
        browser.mkdir(parents=True)
        (browser / "SingletonLock").write_text("fixture", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "login browser"):
            profile_control.apply_profile_operation(
                "delete", profile["id"], project_root=self.root,
            )
        self.assertTrue(root.exists())
        self.assertEqual(active_profile(project_root=self.root)["id"], profile["id"])

    def test_reset_checks_legacy_before_data_or_settings_change(self) -> None:
        profile = create_profile(project_root=self.root)
        settings = self.root / "settings.json"
        settings.write_text('{"dont_show_again": true}', encoding="utf-8")
        legacy = self.root / "state.json"
        legacy.write_text("fixture", encoding="utf-8")
        with patch("run_workspace.profile_legacy._preflight", side_effect=RuntimeError("unsafe legacy")):
            with self.assertRaisesRegex(RuntimeError, "unsafe legacy"):
                profile_control.apply_profile_operation("reset", project_root=self.root)
        self.assertTrue(profile_root(profile["id"], project_root=self.root).exists())
        self.assertTrue(legacy.exists())
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"dont_show_again": True})

        profile_control.apply_profile_operation("reset", project_root=self.root)
        self.assertEqual(list_profiles(project_root=self.root), [])
        self.assertFalse(legacy.exists())
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {})

    def test_request_is_ephemeral_and_rejects_invalid_payloads(self) -> None:
        action_dir = self.root / "data" / ".profile-actions"
        action_dir.mkdir(parents=True)
        destination = action_dir / ("a" * 32 + ".json")
        with patch.object(profile_control, "PROJECT_ROOT", self.root), \
             patch.dict(os.environ, {profile_control.ACTION_ENV: str(destination)}):
            with self.assertRaises(ValueError):
                profile_control.request_profile_operation("delete", "../outside")
            with self.assertRaises(ValueError):
                profile_control.request_profile_operation("unknown")
            profile_control.request_profile_operation("new")
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")),
                             {"operation": "new", "profile_id": ""})
            with self.assertRaisesRegex(RuntimeError, "already been requested"):
                profile_control.request_profile_operation("new")
        self.assertEqual(len(list(action_dir.glob("*.tmp"))), 0)

    def test_supervisor_applies_request_only_after_child_exits_and_cleans_file(self) -> None:
        calls: list[str] = []

        def child(*_args, **kwargs):
            calls.append("child exited")
            self.assertNotIn("GTT_ACCOUNT_PROFILE", kwargs["env"])
            if len(calls) == 1:
                Path(kwargs["env"][profile_control.ACTION_ENV]).write_text(
                    json.dumps({"operation": "new", "profile_id": ""}), encoding="utf-8",
                )
            return type("Result", (), {"returncode": 0})()

        def apply(*_args, **_kwargs):
            calls.append("applied")

        with patch.object(profile_control, "PROJECT_ROOT", self.root), \
             patch.object(profile_control.subprocess, "run", side_effect=child), \
             patch.object(profile_control, "apply_profile_operation", side_effect=apply), \
             patch.dict(os.environ, {"GTT_ACCOUNT_PROFILE": "a" * 32}):
            self.assertEqual(profile_control.supervise_app([]), 0)
        self.assertEqual(calls, ["child exited", "applied", "child exited"])
        self.assertEqual(list((self.root / "data" / ".profile-actions").glob("*.json")), [])

    def test_supervisor_clears_only_recognized_stale_request_files(self) -> None:
        action_dir = self.root / "data" / ".profile-actions"
        action_dir.mkdir(parents=True)
        stale_action = action_dir / ("a" * 32 + ".json")
        stale_temp = action_dir / ".request-abc123.tmp"
        unrelated = action_dir / "keep.txt"
        for path in (stale_action, stale_temp, unrelated):
            path.write_text("fixture", encoding="utf-8")

        def child(*_args, **_kwargs):
            self.assertFalse(stale_action.exists())
            self.assertFalse(stale_temp.exists())
            self.assertTrue(unrelated.exists())
            return type("Result", (), {"returncode": 0})()

        with patch.object(profile_control, "PROJECT_ROOT", self.root), \
             patch.object(profile_control.subprocess, "run", side_effect=child):
            self.assertEqual(profile_control.supervise_app([]), 0)
        self.assertEqual([item.name for item in action_dir.iterdir()], ["keep.txt"])

    def test_invalid_request_never_reaches_operation(self) -> None:
        calls = 0

        def child(*_args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                Path(kwargs["env"][profile_control.ACTION_ENV]).write_text(
                    json.dumps({"operation": "delete", "profile_id": "../outside"}),
                    encoding="utf-8",
                )
            else:
                self.assertIn("valid profile ID", kwargs["env"]["GTT_PROFILE_ACTION_ERROR"])
            return type("Result", (), {"returncode": 0})()

        with patch.object(profile_control, "PROJECT_ROOT", self.root), \
             patch.object(profile_control.subprocess, "run", side_effect=child), \
             patch.object(profile_control, "apply_profile_operation") as apply:
            self.assertEqual(profile_control.supervise_app([]), 0)
            apply.assert_not_called()


class ProfileBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.previous_id = profile_context.PROFILE_ID
        self.previous_root = profile_context.ACCOUNT_ROOT
        self.previous_env = os.environ.get(profile_context.PROFILE_ENV)
        self.addCleanup(self._restore_context)

    def _restore_context(self) -> None:
        profile_context.PROFILE_ID = self.previous_id
        profile_context.ACCOUNT_ROOT = self.previous_root
        if self.previous_env is None:
            os.environ.pop(profile_context.PROFILE_ENV, None)
        else:
            os.environ[profile_context.PROFILE_ENV] = self.previous_env

    def _binding_db(self, path: Path, uid: str = "600000001") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE hoyolab_account_binding (singleton INTEGER PRIMARY KEY, "
                         "account_uid TEXT, server TEXT)")
            conn.execute("INSERT INTO hoyolab_account_binding VALUES (1, ?, 'os_euro')", (uid,))
            conn.commit()

    def test_bootstrap_moves_legacy_and_marks_verified_binding_imported(self) -> None:
        profile = create_profile(project_root=self.root)
        self._binding_db(self.root / "data" / "artifacts.db")
        with patch.object(profile_context, "PROJECT_ROOT", self.root), \
             patch.dict(os.environ, {}, clear=True):
            result = profile_context.bootstrap_profile()
        self.assertEqual(result, profile_root(profile["id"], project_root=self.root))
        self.assertFalse((self.root / "data" / "artifacts.db").exists())
        self.assertTrue((result / "data" / "artifacts.db").exists())
        entry = active_profile(project_root=self.root)
        self.assertTrue(entry["imported"])
        self.assertEqual(entry["metadata"]["uid"], "600000001")

    def test_bootstrap_resumes_journal_even_when_no_legacy_source_remains(self) -> None:
        profile = create_profile(project_root=self.root)
        target = profile_root(profile["id"], project_root=self.root)
        self._binding_db(target / "data" / "artifacts.db")
        (target / ".legacy-migration.json").write_text(json.dumps({
            "schema_version": 1, "profile_id": profile["id"],
            "paths": ["data/artifacts.db"], "started_at": "2026-01-01T00:00:00+00:00",
        }), encoding="utf-8")
        with patch.object(profile_context, "PROJECT_ROOT", self.root), \
             patch.dict(os.environ, {}, clear=True):
            profile_context.bootstrap_profile()
        self.assertFalse((target / ".legacy-migration.json").exists())
        self.assertTrue(active_profile(project_root=self.root)["imported"])

    def test_bootstrap_refuses_to_merge_legacy_into_imported_profile(self) -> None:
        profile = create_profile(project_root=self.root)
        update_profile_metadata(profile["id"], {"uid": "600000002", "server": "os_euro"},
                                imported=True, project_root=self.root)
        legacy = self.root / "state.json"
        legacy.write_text("legacy", encoding="utf-8")
        with patch.object(profile_context, "PROJECT_ROOT", self.root), \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "cannot be merged"):
                profile_context.bootstrap_profile()
        self.assertTrue(legacy.exists())
        self.assertEqual(active_profile(project_root=self.root)["id"], profile["id"])

    def test_asset_paths_never_reach_another_profile(self) -> None:
        current = "a" * 32
        foreign = "b" * 32
        account_root = self.root / "data" / "profiles" / current
        with patch.object(profile_context, "PROJECT_ROOT", self.root), \
             patch.object(profile_context, "ACCOUNT_ROOT", account_root), \
             patch.object(profile_context, "PROFILE_ID", current):
            legacy = self.root / "assets" / "hoyolab" / "avatar.png"
            self.assertEqual(profile_context.account_asset_path(legacy),
                             account_root / "assets" / "hoyolab" / "avatar.png")
            other = self.root / "data" / "profiles" / foreign / "assets" / "hoyolab" / "avatar.png"
            self.assertEqual(profile_context.account_asset_path(other),
                             account_root / ".unavailable-account-asset")


if __name__ == "__main__":
    unittest.main()
