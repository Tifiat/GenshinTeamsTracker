"""Synthetic, offline coverage for linked-worktree runtime seeding."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools import bootstrap_optimizer_worker as seed
from run_workspace.gcsim.tree_identity import directory_sha256


class BootstrapWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source, self.target, self.job = base / "source", base / "target", base / "job"
        for path in (self.source, self.target, self.job):
            path.mkdir()
        self.common = base / "common.git"
        self.common.mkdir()
        self.patches = [
            patch.object(seed, "owned_job", return_value=self.job),
            patch.object(seed, "_git_value", side_effect=self.git_value),
        ]
        for context in self.patches:
            context.start()
            self.addCleanup(context.stop)
        self.put("native/gcsim_optimizer/gtt-optimizer.exe", b"native")
        self.put("data/hoyolab/account_language.json", b'{"language":"en"}')
        self.put("settings.json", b"{}")
        self.put("state.json", b"{}")
        self.put("data/hoyolab/auth.json", b"secret")
        self.put("data/hoyolab/debug/private.json", b"secret")
        self.put("data/cache/hoyowiki/character_stats_catalog.json", b'{"public":true}')
        self.put("data/cache/hoyowiki/private_session.json", b"secret")
        self.put("assets/hoyolab/characters/portrait.png", b"picture")
        self.put("assets/hoyolab/browser/profile.txt", b"secret")
        self.put("data/gcsim/engines/failed/trash/file", b"old")
        self.put("data/gcsim/engines/engines/old-unused/file", b"old")
        self.put("data/artifacts.db", b"")
        (self.source / "data/artifacts.db").unlink()
        with closing(sqlite3.connect(self.source / "data/artifacts.db")) as db:
            db.execute("CREATE TABLE records (value TEXT)")
            db.execute("INSERT INTO records VALUES ('base')")
            db.commit()
        self.engine("active")
        self.engine("rollback")
        self.pointer("active", "rollback")

    def git_value(self, root: Path, option: str) -> Path:
        if option == "--show-toplevel":
            return root
        if option == "--git-common-dir":
            return self.common
        raise AssertionError(option)

    def put(self, relative: str, data: bytes) -> Path:
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def pointer(self, active: str, rollback: str | None) -> None:
        self.put(seed.POINTER.as_posix(), json.dumps({
            "schema_version": 1, "active_engine_id": active,
            "rollback_engine_id": rollback,
        }).encode())

    def engine(self, engine_id: str) -> None:
        root = self.source / "data/gcsim/engines/engines" / engine_id
        artifact = root / "bin" / "gtt-gcsim.exe"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes((engine_id + " binary").encode())
        (root / "pkg").mkdir()
        (root / "pkg" / "source.go").write_bytes(b"source")
        manifest = {"schema_version": 1, "engine_id": engine_id,
                    "engine_tree_hash": directory_sha256(root, excluded_relative_paths=(seed.MANIFEST,)),
                    "metadata": {"artifact_relative_path": "bin/gtt-gcsim.exe",
                                 "artifact_sha256": seed._sha(artifact)}}
        (root / seed.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")

    def test_success_copies_exact_runtime_and_receipt(self) -> None:
        # Keep a writer connected with a committed record in WAL, absent from
        # the main DB file until checkpoint, to exercise SQLite backup.
        writer = sqlite3.connect(self.source / "data/artifacts.db")
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO records VALUES ('wal')")
        writer.commit()
        self.assertTrue(Path(str(self.source / "data/artifacts.db") + "-wal").exists())
        receipt = seed.bootstrap(self.source, self.target)
        self.assertEqual(receipt["active_engine_id"], "active")
        self.assertEqual(receipt["rollback_engine_id"], "rollback")
        self.assertEqual(len(receipt["engines"]), 2)
        self.assertEqual((self.target / seed.POINTER).read_bytes(),
                         (self.source / seed.POINTER).read_bytes())
        self.assertEqual(seed._sha(self.target / "native/gcsim_optimizer/gtt-optimizer.exe"),
                         receipt["consumer_sha256"])
        with closing(sqlite3.connect(self.target / "data/artifacts.db")) as db:
            self.assertEqual(db.execute("SELECT value FROM records ORDER BY value").fetchall(),
                             [("base",), ("wal",)])
        self.assertFalse((self.target / "data/artifacts.db-wal").exists())
        self.assertFalse((self.target / "data/hoyolab/auth.json").exists())
        self.assertFalse((self.target / "data/hoyolab/debug").exists())
        self.assertEqual((self.target / "data/cache/hoyowiki/character_stats_catalog.json").read_bytes(),
                         b'{"public":true}')
        self.assertFalse((self.target / "data/cache/hoyowiki/private_session.json").exists())
        self.assertFalse((self.target / "assets/hoyolab/browser").exists())
        self.assertFalse((self.target / "data/gcsim/engines/failed").exists())
        self.assertFalse((self.target / "data/gcsim/engines/engines/old-unused").exists())
        saved = self.target / seed.RECEIPT
        self.assertLessEqual(saved.stat().st_size, 16 * 1024)
        self.assertEqual(json.loads(saved.read_text(encoding="utf-8")), receipt)

    def test_engine_hash_matches_existing_manifest_contract(self) -> None:
        receipt = seed.bootstrap(self.source, self.target)
        for details in receipt["engines"]:
            source_engine = self.source / "data/gcsim/engines/engines" / details["id"]
            target_engine = self.target / "data/gcsim/engines/engines" / details["id"]
            expected = directory_sha256(source_engine, excluded_relative_paths=(seed.MANIFEST,))
            self.assertEqual(details["engine_tree_sha256"], expected)
            self.assertEqual(directory_sha256(target_engine, excluded_relative_paths=(seed.MANIFEST,)), expected)
        manifest_path = self.source / "data/gcsim/engines/engines/active" / seed.MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["engine_tree_hash"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fresh_target = Path(self.temp.name) / "another-target"
        fresh_target.mkdir()
        with self.assertRaisesRegex(ValueError, "Engine tree hash mismatch"):
            seed.bootstrap(self.source, fresh_target)

    def test_duplicate_same_and_nested_roots(self) -> None:
        with self.assertRaisesRegex(ValueError, "distinct"):
            seed.bootstrap(self.source, self.source)
        (self.source / "nested").mkdir()
        with self.assertRaisesRegex(ValueError, "distinct"):
            seed.bootstrap(self.source, self.source / "nested")
        existing = self.target / "data/gcsim/engines/active_engine.json"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"user")
        with self.assertRaises(FileExistsError):
            seed.bootstrap(self.source, self.target)
        self.assertEqual(existing.read_bytes(), b"user")
        self.assertFalse((self.target / "native/gcsim_optimizer/gtt-optimizer.exe").exists())

    def test_nonlinked_worktrees_rejected(self) -> None:
        with patch.object(seed, "_git_value", side_effect=lambda root, option:
                          root if option == "--show-toplevel" else root / ".git"):
            with self.assertRaisesRegex(ValueError, "linked worktrees"):
                seed.bootstrap(self.source, self.target)

    def test_invalid_active_or_manifest_id_rejected(self) -> None:
        self.pointer("../outside", None)
        with self.assertRaisesRegex(ValueError, "Invalid engine ID"):
            seed.bootstrap(self.source, self.target)
        self.pointer("active", None)
        manifest_path = self.source / "data/gcsim/engines/engines/active" / seed.MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["engine_id"] = "wrong"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest identity"):
            seed.bootstrap(self.source, self.target)

    def test_links_in_selected_content_rejected(self) -> None:
        link = self.source / "assets/hoyolab/characters/link.png"
        try:
            link.symlink_to(self.source / "assets/hoyolab/characters/portrait.png")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "Linked path"):
            seed.bootstrap(self.source, self.target)

    def test_copy_failure_has_no_publication(self) -> None:
        original = seed.shutil.copytree
        def fail_copy(src: Path, dst: Path, *args, **kwargs):
            if str(src).endswith("rollback"):
                raise OSError("induced copy failure")
            return original(src, dst, *args, **kwargs)
        with patch.object(seed.shutil, "copytree", side_effect=fail_copy):
            with self.assertRaisesRegex(OSError, "induced copy"):
                seed.bootstrap(self.source, self.target)
        self.assertFalse((self.target / seed.POINTER).exists())
        self.assertFalse((self.target / "data/gcsim/engines/engines/active").exists())

    def test_publication_failure_removes_only_new_paths(self) -> None:
        unrelated = self.target / "keep.txt"
        unrelated.write_bytes(b"user")
        original = Path.rename
        def fail_receipt(path: Path, destination: Path):
            if destination == self.target / seed.RECEIPT:
                raise OSError("induced publication failure")
            return original(path, destination)
        with patch.object(Path, "rename", fail_receipt):
            with self.assertRaisesRegex(OSError, "induced publication"):
                seed.bootstrap(self.source, self.target)
        self.assertEqual(unrelated.read_bytes(), b"user")
        self.assertFalse((self.target / seed.POINTER).exists())
        self.assertFalse((self.target / seed.RECEIPT).exists())
        self.assertFalse((self.target / "data/gcsim/engines/engines/active").exists())


if __name__ == "__main__":
    unittest.main()
