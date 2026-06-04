from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.patch_backends import GitApplyPatchBackend


class GcsimGitPatchBackendTest(unittest.TestCase):
    def test_successful_patch_backend_applies_ordered_patches_and_activates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _make_source_tree(root / "source", text="official")
            patch_stack = _make_patch_stack(root / "patches", "002-second.patch", "001-first.patch")
            runner = FakeGitPatchRunner(
                _completed(),
                lambda command, cwd: _write_patch_order(command, cwd),
            )
            store = GcsimEngineStore(root / "store")

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch_stack,
                source_label="official",
                engine_id="engine-v1",
                patch_backend=GitApplyPatchBackend(runner=runner),
            )

            self.assertTrue(result.success)
            self.assertTrue(result.activated)
            self.assertEqual(result.patch_result.patch_count, 2)
            self.assertEqual(result.patch_result.metadata["patch_check_status"], "passed")
            self.assertEqual(result.patch_result.metadata["patch_apply_status"], "passed")
            self.assertEqual(result.patch_result.metadata["patch_git_status"], "available")
            self.assertEqual(
                json.loads(result.patch_result.metadata["patch_files"]),
                ["001-first.patch", "002-second.patch"],
            )
            active = store.get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.manifest.patch_backend, "git")
            self.assertEqual(active.manifest.patch_count, 2)
            self.assertEqual(active.manifest.patch_metadata["patch_apply_status"], "passed")
            self.assertEqual(
                (active.path / "patch_order.txt").read_text(encoding="utf-8"),
                "001-first.patch\n002-second.patch",
            )

    def test_missing_git_is_controlled_failure_and_preserves_old_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimEngineStore(root / "store")
            _install_old_active_engine(store, root)
            source = _make_source_tree(root / "source", text="official-v2")
            patch_stack = _make_patch_stack(root / "patches", "001.patch")
            runner = FakeGitPatchRunner(FileNotFoundError("git"))

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch_stack,
                source_label="official-v2",
                engine_id="engine-v2",
                patch_backend=GitApplyPatchBackend(runner=runner),
            )

            self.assertFalse(result.success)
            self.assertFalse(result.activated)
            self.assertIn("git_missing", result.error)
            self.assertEqual(result.patch_result.patch_count, 1)
            self.assertEqual(result.patch_result.metadata["patch_git_status"], "missing")
            self.assertEqual(store.active_engine_id(), "old-engine")
            self.assertFalse((store.engines_dir / "engine-v2").exists())
            self.assertTrue((store.failed_dir / "engine-v2").exists())

    def test_patch_check_failure_preserves_old_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimEngineStore(root / "store")
            _install_old_active_engine(store, root)
            source = _make_source_tree(root / "source", text="official-v2")
            patch_stack = _make_patch_stack(root / "patches", "001.patch")
            runner = FakeGitPatchRunner(_completed(returncode=1, stderr="check failed"))

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch_stack,
                source_label="official-v2",
                engine_id="engine-v2",
                patch_backend=GitApplyPatchBackend(runner=runner),
            )

            self.assertFalse(result.success)
            self.assertIn("patch_check_failed", result.error)
            self.assertEqual(result.patch_result.metadata["patch_check_status"], "failed")
            self.assertEqual(result.patch_result.metadata["patch_apply_status"], "not_started")
            self.assertEqual(store.active_engine_id(), "old-engine")
            self.assertEqual(len(runner.calls), 1)

    def test_patch_apply_failure_preserves_old_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimEngineStore(root / "store")
            _install_old_active_engine(store, root)
            source = _make_source_tree(root / "source", text="official-v2")
            patch_stack = _make_patch_stack(root / "patches", "001.patch")
            runner = FakeGitPatchRunner(
                _completed(),
                _completed(returncode=1, stderr="apply failed"),
            )

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch_stack,
                source_label="official-v2",
                engine_id="engine-v2",
                patch_backend=GitApplyPatchBackend(runner=runner),
            )

            self.assertFalse(result.success)
            self.assertIn("patch_apply_failed", result.error)
            self.assertEqual(result.patch_result.metadata["patch_check_status"], "passed")
            self.assertEqual(result.patch_result.metadata["patch_apply_status"], "failed")
            self.assertEqual(store.active_engine_id(), "old-engine")
            self.assertEqual(len(runner.calls), 2)

    def test_empty_patch_stack_is_controlled_success_without_git_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _make_source_tree(root / "source", text="official")
            patch_stack = root / "patches"
            patch_stack.mkdir()
            runner = FakeGitPatchRunner()
            store = GcsimEngineStore(root / "store")

            result = store.prepare_engine_update(
                source_dir=source,
                patch_stack_dir=patch_stack,
                source_label="official",
                engine_id="engine-v1",
                patch_backend=GitApplyPatchBackend(runner=runner),
            )

            self.assertTrue(result.success)
            self.assertEqual(result.patch_result.patch_count, 0)
            self.assertEqual(result.patch_result.metadata["patch_check_status"], "no_patches")
            self.assertEqual(result.patch_result.metadata["patch_apply_status"], "no_patches")
            self.assertEqual(runner.calls, [])


class FakeGitPatchRunner:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command, cwd):
        self.calls.append(tuple(str(part) for part in command))
        if not self.results:
            raise AssertionError(f"Unexpected git command: {command}")
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return result(command, cwd)
        return result


def _write_patch_order(command, cwd: Path):
    patch_names = [Path(part).name for part in command[2:]]
    (cwd / "patch_order.txt").write_text("\n".join(patch_names), encoding="utf-8")
    return _completed()


def _completed(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_source_tree(path: Path, *, text: str) -> Path:
    path.mkdir(parents=True)
    (path / "engine.txt").write_text(text, encoding="utf-8")
    return path


def _make_patch_stack(path: Path, *names: str) -> Path:
    path.mkdir(parents=True)
    for name in names:
        (path / name).write_text("dummy patch", encoding="utf-8")
    return path


def _install_old_active_engine(store: GcsimEngineStore, root: Path) -> None:
    source = _make_source_tree(root / "old-source", text="old")
    result = store.prepare_engine_update(
        source_dir=source,
        source_label="old",
        engine_id="old-engine",
    )
    assert result.success


if __name__ == "__main__":
    unittest.main()
