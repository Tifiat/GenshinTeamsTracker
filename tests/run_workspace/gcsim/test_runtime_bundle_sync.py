from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from run_workspace.gcsim import runtime_bundle_sync as sync
from run_workspace.gcsim.engine_compatibility import REQUIRED_BUNDLE_CAPABILITIES
from run_workspace.gcsim.engine_store import GcsimEngineManifest, GcsimEngineStore
from run_workspace.gcsim.tree_identity import directory_sha256


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RuntimeBundleSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.reference = base / "reference"
        self.target = base / "target"
        self.reference.mkdir()
        self.target.mkdir()
        self.active_bytes = b"accepted active mini engine"
        self.rollback_bytes = b"accepted rollback mini engine"
        self.consumer_bytes = b"accepted optimizer mini consumer"
        self.active_sha = _sha(self.active_bytes)
        self.rollback_sha = _sha(self.rollback_bytes)
        self.consumer_sha = _sha(self.consumer_bytes)
        store = GcsimEngineStore(self.reference / sync.STORE_RELATIVE)
        for engine_id, payload in ((sync.ROLLBACK_ID, self.rollback_bytes),
                                   (sync.ACTIVE_ID, self.active_bytes)):
            engine = store.engines_dir / engine_id
            (engine / "build").mkdir(parents=True)
            (engine / "build" / "gtt-gcsim.exe").write_bytes(payload)
            (engine / "build" / "gtt-source-manifest-body.json").write_text("{}")
            metadata = {
                "artifact_relative_path": "build/gtt-gcsim.exe",
                "artifact_sha256": _sha(payload),
                "artifact_version_stdout": "v-test",
                "gtt_info_stdout": json.dumps({"gtt_engine": True}),
                "source_manifest_required": "true",
                "source_manifest_ready": "true",
                "source_manifest_body_relative_path": "build/gtt-source-manifest-body.json",
                "source_manifest_body_sha256": "0" * 64,
                "gtt_capabilities": json.dumps(sorted(REQUIRED_BUNDLE_CAPABILITIES)),
                "gtt_sequential_waves": "true",
            }
            manifest = GcsimEngineManifest(
                engine_id=engine_id, source_label="gcsim-test",
                source_path="historical build source", source_tree_hash="a" * 64,
                engine_tree_hash=directory_sha256(engine),
                prepared_at_utc="2026-09-26T00:00:00+00:00",
                patch_backend="git", patch_count=9, capabilities=("local_build_artifact",),
                metadata=metadata,
            )
            (engine / "gtt_engine_manifest.json").write_text(json.dumps(manifest.to_dict()))
        store.activate_engine(sync.ROLLBACK_ID)
        store.activate_engine(sync.ACTIVE_ID)
        consumer = self.reference / sync.CONSUMER_RELATIVE
        consumer.parent.mkdir(parents=True)
        consumer.write_bytes(self.consumer_bytes)
        self.root_patch = mock.patch.object(sync, "PROJECT_ROOT", self.target)
        self.body_patch = mock.patch.object(sync, "_source_body_digest", return_value=None)
        self.check_patch = mock.patch.object(sync, "_compatibility", return_value=None)
        self.root_patch.start()
        self.body_patch.start()
        self.check = self.check_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.body_patch.stop)
        self.addCleanup(self.check_patch.stop)

    def run_sync(self, **kwargs):
        return sync.sync_runtime_bundle(
            self.reference, expected_active_sha256=self.active_sha,
            expected_rollback_sha256=self.rollback_sha,
            expected_consumer_sha256=self.consumer_sha, **kwargs,
        )

    def test_preview_is_read_only_and_reports_exact_scope(self) -> None:
        before = sorted(path.relative_to(self.target).as_posix() for path in self.target.rglob("*"))
        result = self.run_sync()
        after = sorted(path.relative_to(self.target).as_posix() for path in self.target.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(result["engine_install_count"], 2)
        self.assertTrue(result["consumer_to_install"])
        self.assertTrue(result["pointer_to_set"])
        self.check.assert_not_called()

    def test_expected_hash_mismatch_refuses_before_target_mutation(self) -> None:
        with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "artifact hash mismatch"):
            sync.sync_runtime_bundle(
                self.reference, expected_active_sha256="f" * 64,
                expected_rollback_sha256=self.rollback_sha,
                expected_consumer_sha256=self.consumer_sha, apply=True,
            )
        self.assertEqual(list(self.target.iterdir()), [])

    def test_install_uses_store_preserves_provenance_and_becomes_noop(self) -> None:
        result = self.run_sync(apply=True)
        self.assertEqual(result["status"], "installed")
        self.assertEqual(self.check.call_count, 2)
        store = GcsimEngineStore(self.target / sync.STORE_RELATIVE)
        self.assertEqual(store.active_engine_id(), sync.ACTIVE_ID)
        self.assertEqual(store.rollback_engine_id(), sync.ROLLBACK_ID)
        self.assertEqual((self.target / sync.CONSUMER_RELATIVE).read_bytes(), self.consumer_bytes)
        for engine_id in (sync.ACTIVE_ID, sync.ROLLBACK_ID):
            source = self.reference / sync.STORE_RELATIVE / "engines" / engine_id
            installed = store.engines_dir / engine_id
            self.assertEqual((installed / "gtt_engine_manifest.json").read_bytes(),
                             (source / "gtt_engine_manifest.json").read_bytes())
            self.assertEqual(directory_sha256(installed,
                excluded_relative_paths=("gtt_engine_manifest.json",)),
                directory_sha256(source, excluded_relative_paths=("gtt_engine_manifest.json",)))
        self.check.reset_mock()
        again = self.run_sync(apply=True)
        self.assertEqual(again["status"], "already_installed")
        self.check.assert_not_called()

    def test_compatibility_failure_keeps_consumer_and_pointer(self) -> None:
        old = self.target / sync.CONSUMER_RELATIVE
        old.parent.mkdir(parents=True)
        old.write_bytes(b"old worker consumer")
        store = GcsimEngineStore(self.target / sync.STORE_RELATIVE)
        source = self.reference / sync.STORE_RELATIVE / "engines" / sync.ROLLBACK_ID
        destination = store.engines_dir / sync.ROLLBACK_ID
        destination.parent.mkdir(parents=True)
        import shutil
        shutil.copytree(source, destination)
        store.activate_engine(sync.ROLLBACK_ID)
        pointer_before = store.active_state_path.read_bytes()
        with mock.patch.object(sync, "_compatibility", side_effect=sync.RuntimeBundleSyncError("fixture rejected")):
            with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "fixture rejected"):
                self.run_sync(apply=True)
        self.assertEqual(store.active_state_path.read_bytes(), pointer_before)
        self.assertEqual(old.read_bytes(), b"old worker consumer")
        self.assertFalse(sync._backup_paths(old)[0].exists())
        self.assertTrue(destination.is_dir())

    def test_old_consumer_is_retained_and_can_be_swapped_back(self) -> None:
        consumer = self.target / sync.CONSUMER_RELATIVE
        consumer.parent.mkdir(parents=True)
        consumer.write_bytes(b"old worker consumer")
        self.run_sync(apply=True)
        backup, receipt = sync._backup_paths(consumer)
        self.assertEqual(backup.read_bytes(), b"old worker consumer")
        self.assertEqual(json.loads(receipt.read_text())["current_sha256"], self.consumer_sha)
        result = self.run_sync(apply=True, rollback_consumer=True)
        self.assertEqual(result["status"], "consumer_rolled_back")
        self.assertEqual(consumer.read_bytes(), b"old worker consumer")
        self.assertEqual(backup.read_bytes(), self.consumer_bytes)
        self.assertEqual(json.loads(receipt.read_text())["backup_sha256"], self.consumer_sha)
        self.run_sync(apply=True, rollback_consumer=True)
        self.assertEqual(consumer.read_bytes(), self.consumer_bytes)
        accepted = self.run_sync(apply=True, accept_consumer=True)
        self.assertEqual(accepted["status"], "consumer_accepted")
        self.assertFalse(backup.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual(consumer.read_bytes(), self.consumer_bytes)

    def test_activation_failure_restores_old_pointer_and_consumer(self) -> None:
        consumer = self.target / sync.CONSUMER_RELATIVE
        consumer.parent.mkdir(parents=True)
        consumer.write_bytes(b"old worker consumer")
        original_activate = GcsimEngineStore.activate_engine

        def fail_on_final_activation(store, engine_id):
            if store.root_dir == self.target / sync.STORE_RELATIVE and engine_id == sync.ACTIVE_ID:
                raise OSError("fixture pointer failure")
            return original_activate(store, engine_id)

        with mock.patch.object(GcsimEngineStore, "activate_engine", fail_on_final_activation):
            with self.assertRaisesRegex(OSError, "fixture pointer failure"):
                self.run_sync(apply=True)
        store = GcsimEngineStore(self.target / sync.STORE_RELATIVE)
        self.assertFalse(store.active_state_path.exists())
        self.assertEqual(consumer.read_bytes(), b"old worker consumer")
        self.assertFalse(sync._backup_paths(consumer)[0].exists())
        self.assertFalse(sync._backup_paths(consumer)[1].exists())

    def test_conflicting_engine_and_unknown_rollback_slot_refuse(self) -> None:
        engine = self.target / sync.STORE_RELATIVE / "engines" / sync.ACTIVE_ID
        engine.mkdir(parents=True)
        (engine / "foreign.txt").write_text("draft")
        with self.assertRaises(sync.RuntimeBundleSyncError):
            self.run_sync(apply=True)
        self.assertEqual((engine / "foreign.txt").read_text(), "draft")
        import shutil
        shutil.rmtree(engine)
        consumer = self.target / sync.CONSUMER_RELATIVE
        consumer.parent.mkdir(parents=True)
        consumer.write_bytes(b"old")
        sync._backup_paths(consumer)[0].write_bytes(b"unknown slot")
        with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "rollback slot"):
            self.run_sync(apply=True)
        self.assertEqual(consumer.read_bytes(), b"old")

    def test_same_tree_with_changed_manifest_provenance_refuses(self) -> None:
        import shutil
        source = self.reference / sync.STORE_RELATIVE / "engines" / sync.ACTIVE_ID
        target = self.target / sync.STORE_RELATIVE / "engines" / sync.ACTIVE_ID
        target.parent.mkdir(parents=True)
        shutil.copytree(source, target)
        manifest_path = target / "gtt_engine_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source_tree_hash"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "conflicting manifest provenance"):
            self.run_sync()

    def test_unsafe_metadata_and_symlink_are_rejected(self) -> None:
        with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "unsafe"):
            sync._contained_file(self.reference, "../outside")
        source = self.reference / sync.STORE_RELATIVE / "engines" / sync.ACTIVE_ID
        link = source / "linked.txt"
        try:
            os.symlink(source / "build" / "gtt-gcsim.exe", link)
        except (OSError, NotImplementedError):
            link.write_bytes(b"simulated reparse")
            original = sync._is_reparse
            with mock.patch.object(sync, "_is_reparse",
                                   side_effect=lambda path: path == link or original(path)):
                with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "Link or reparse"):
                    self.run_sync()
        else:
            with self.assertRaisesRegex(sync.RuntimeBundleSyncError, "Link or reparse"):
                self.run_sync()


if __name__ == "__main__":
    unittest.main()
