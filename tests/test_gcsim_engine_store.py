from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.engine_store import (
    GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION,
    GcsimEngineStore,
    GcsimPatchResult,
    MANIFEST_FILE_NAME,
    OverlayPatchBackend,
)


class FailingPatchBackend:
    name = "failing-test-backend"

    def apply(self, *, engine_dir: Path, patch_stack_dir: Path | None) -> GcsimPatchResult:
        return GcsimPatchResult.failure(
            backend=self.name,
            error="simulated patch conflict",
        )


class GcsimEngineStoreTest(unittest.TestCase):
    def test_successful_prepare_activates_new_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _make_source_tree(root / "source", version="official-v1")
            patch = _make_patch_stack(root / "patch", version="gtt-v1")
            store = GcsimEngineStore(root / "store")

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch,
                source_label="official-v1",
                engine_id="engine-v1",
                capabilities=("gtt_patch_stack",),
                metadata={"source_commit": "abc123"},
            )

            self.assertTrue(result.success)
            self.assertTrue(result.activated)
            active = store.get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.engine_id, "engine-v1")
            self.assertEqual((active.path / "engine.txt").read_text(encoding="utf-8"), "gtt-v1")
            self.assertTrue((active.path / MANIFEST_FILE_NAME).exists())

    def test_patch_failure_does_not_replace_previous_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_v1 = _make_source_tree(root / "source-v1", version="official-v1")
            patch_v1 = _make_patch_stack(root / "patch-v1", version="gtt-v1")
            source_v2 = _make_source_tree(root / "source-v2", version="official-v2")
            patch_v2 = _make_patch_stack(root / "patch-v2", version="gtt-v2")
            store = GcsimEngineStore(root / "store")
            first = store.prepare_engine_update(
                source_dir=source_v1,
                patch_stack_dir=patch_v1,
                source_label="official-v1",
                engine_id="engine-v1",
            )
            self.assertTrue(first.success)

            failed = store.prepare_engine_update(
                source_dir=source_v2,
                patch_stack_dir=patch_v2,
                source_label="official-v2",
                engine_id="engine-v2",
                patch_backend=FailingPatchBackend(),
            )

            self.assertFalse(failed.success)
            self.assertFalse(failed.activated)
            self.assertEqual(failed.previous_active_engine_id, "engine-v1")
            self.assertEqual(failed.error, "simulated patch conflict")
            active = store.get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.engine_id, "engine-v1")
            self.assertEqual((active.path / "engine.txt").read_text(encoding="utf-8"), "gtt-v1")
            self.assertFalse((store.engines_dir / "engine-v2").exists())
            self.assertTrue((store.failed_dir / "engine-v2").exists())

    def test_manifest_contains_update_metadata_for_future_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _make_source_tree(root / "source", version="official-v1")
            patch = _make_patch_stack(root / "patch", version="gtt-v1")
            store = GcsimEngineStore(root / "store")

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch,
                source_label="official-v1",
                engine_id="engine-v1",
                capabilities=("engine_info", "gtt_patch_stack"),
                metadata={"source_commit": "abc123", "patch_stack_version": "test"},
            )

            manifest = result.manifest
            self.assertIsNotNone(manifest)
            assert manifest is not None
            self.assertEqual(manifest.schema_version, GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(manifest.engine_id, "engine-v1")
            self.assertEqual(manifest.source_label, "official-v1")
            self.assertEqual(manifest.patch_backend, OverlayPatchBackend.name)
            self.assertEqual(manifest.patch_count, 1)
            self.assertIn("engine_info", manifest.capabilities)
            self.assertIn("gtt_patch_stack", manifest.capabilities)
            self.assertEqual(manifest.metadata["source_commit"], "abc123")
            self.assertEqual(len(manifest.source_tree_hash), 64)
            self.assertEqual(len(manifest.engine_tree_hash), 64)
            self.assertNotEqual(manifest.source_tree_hash, manifest.engine_tree_hash)

    def test_old_active_engine_remains_available_after_failed_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_v1 = _make_source_tree(root / "source-v1", version="official-v1")
            patch_v1 = _make_patch_stack(root / "patch-v1", version="gtt-v1")
            source_v2 = _make_source_tree(root / "source-v2", version="official-v2")
            store = GcsimEngineStore(root / "store")
            store.prepare_engine_update(
                source_dir=source_v1,
                patch_stack_dir=patch_v1,
                source_label="official-v1",
                engine_id="engine-v1",
            )

            failed = store.prepare_engine_update(
                source_dir=source_v2,
                patch_stack_dir=None,
                source_label="official-v2",
                engine_id="engine-v2",
                smoke_check=lambda _path: "simulated smoke failure",
            )

            self.assertFalse(failed.success)
            active = store.get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.engine_id, "engine-v1")
            self.assertTrue(active.path.exists())
            self.assertEqual((active.path / "engine.txt").read_text(encoding="utf-8"), "gtt-v1")


def _make_source_tree(path: Path, *, version: str) -> Path:
    path.mkdir(parents=True)
    (path / "engine.txt").write_text(version, encoding="utf-8")
    (path / "cmd").mkdir()
    (path / "cmd" / "gcsim.txt").write_text("source-like entrypoint", encoding="utf-8")
    return path


def _make_patch_stack(path: Path, *, version: str) -> Path:
    path.mkdir(parents=True)
    (path / "engine.txt").write_text(version, encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
