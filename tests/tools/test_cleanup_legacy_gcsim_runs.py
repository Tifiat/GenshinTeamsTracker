"""Windows cleanup safety controls; recycling is always mocked in temp roots."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "tools/cleanup_legacy_gcsim_runs.ps1"
POWERSHELL = shutil.which("powershell.exe")
PROFILE = "a" * 32


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell required")
class LegacyRunsCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gtt-cleanup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / "tools" / SCRIPT.name
        self.script.parent.mkdir()
        shutil.copyfile(SCRIPT, self.script)
        self.put("CODEX.md", b"test root")
        self.put("run_workspace/profile_legacy.py", b"# test marker")
        self.put("data/profiles/registry.json", json.dumps({
            "schema_version": 1, "active_profile_id": PROFILE,
            "profiles": [{"id": PROFILE}],
        }).encode())
        self.db = self.put(f"data/profiles/{PROFILE}/data/artifacts.db", b"profile sentinel")
        self.runs = self.root / "data/gcsim/runs"
        self.put("data/gcsim/runs/old/rotation.txt", b"active chasca;")
        self.protected = [self.db]
        for relative in (
            f"data/profiles/{PROFILE}/data/gcsim/runs/keep.txt",
            "data/gcsim/optimizer-go-runs/keep.txt",
            "data/gcsim/engines/keep.exe",
            "state.json", "source.py",
        ):
            self.protected.append(self.put(relative, b"keep"))

    def put(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def run_script(self, *, apply=False, whatif=False, fail_recycle=False):
        # EncodedCommand avoids quoting special characters in temporary paths.
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        command = f". {quote(self.script)}\n"
        if fail_recycle:
            command += "function Move-LegacyRunsToRecycleBin { param($Target) throw 'mock recycle failure' }\n"
        else:
            destination = self.root / "mock-recycled-runs"
            command += ("function Move-LegacyRunsToRecycleBin { param($Target) "
                        f"Move-Item -LiteralPath $Target -Destination {quote(destination)} }}\n")
        command += f"Invoke-LegacyRunsCleanup -ProjectRoot {quote(self.root)}"
        if apply:
            command += " -Apply"
        if whatif:
            command += " -WhatIf"
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=20,
        )

    def assert_refused(self, expected):
        before = self.snapshot()
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_preview_and_whatif_make_no_writes(self):
        before = self.snapshot()
        for kwargs in ({}, {"apply": True, "whatif": True}):
            result = self.run_script(**kwargs)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 file(s), 14 byte(s)", result.stdout)
            self.assertEqual(self.snapshot(), before)

    def test_mocked_apply_is_narrow_and_idempotent(self):
        result = self.run_script(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.runs.exists())
        self.assertEqual((self.root / "mock-recycled-runs/old/rotation.txt").read_bytes(), b"active chasca;")
        for path in self.protected:
            self.assertTrue(path.is_file(), path)
        self.assertEqual(self.db.read_bytes(), b"profile sentinel")
        before = self.snapshot()
        second = self.run_script(apply=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Nothing to clean", second.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_journal_blocks_registered_and_unregistered_profile(self):
        for profile in (PROFILE, "b" * 32):
            journal = self.put(f"data/profiles/{profile}/.legacy-migration.json", b"{}")
            self.assert_refused("Unfinished legacy migration")
            journal.unlink()

    def test_legacy_database_and_sidecars_block_cleanup(self):
        for name in ("artifacts.db", "artifacts.db-wal", "artifacts.db-shm"):
            source = self.put(f"data/{name}", b"legacy sentinel")
            self.assert_refused("Legacy account database/sidecar")
            source.unlink()

    def test_missing_profile_database_blocks_cleanup(self):
        self.db.unlink()
        self.assert_refused("Selected profile has no account database")

    def test_invalid_active_profile_blocks_cleanup(self):
        self.put("data/profiles/registry.json", json.dumps({
            "schema_version": 1, "active_profile_id": "../outside", "profiles": [],
        }).encode())
        self.assert_refused("valid selected account profile")

    def test_busy_product_locks_block_and_release(self):
        import msvcrt
        for name in ("profile-supervisor.lock", "profile-operations.lock", "account_profiles.lock"):
            lock = self.put(f"data/{name}", b"0")
            before = self.runs.joinpath("old/rotation.txt").read_bytes()
            with lock.open("r+b") as handle:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    result = self.run_script(apply=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("lock cannot be acquired", result.stderr)
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.assertEqual(self.runs.joinpath("old/rotation.txt").read_bytes(), before)
        result = self.run_script(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_recycle_failure_preserves_files_and_releases_locks(self):
        result = self.run_script(apply=True, fail_recycle=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mock recycle failure", result.stderr)
        self.assertTrue(self.runs.joinpath("old/rotation.txt").exists())
        retry = self.run_script(apply=True)
        self.assertEqual(retry.returncode, 0, retry.stderr)

    def junction(self, link, destination):
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(destination)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            self.skipTest("Host cannot create temporary directory junctions")
        # Unlink the junction itself, not its contents, before temp teardown.
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)

    def test_nested_junction_refused_without_following(self):
        external = self.root / "outside"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_bytes(b"outside sentinel")
        self.junction(self.runs / "redirect", external)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Link/junction", result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"outside sentinel")
        self.assertTrue(self.runs.joinpath("old/rotation.txt").exists())

    def test_target_junction_refused_without_following(self):
        destination = self.root / "moved-old-runs"
        self.runs.rename(destination)
        self.junction(self.runs, destination)
        result = self.run_script(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Link/junction", result.stderr)
        self.assertTrue(destination.joinpath("old/rotation.txt").exists())


if __name__ == "__main__":
    unittest.main()
