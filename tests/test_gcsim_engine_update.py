from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.engine_update import (
    prepare_official_gcsim_engine_update,
)
from run_workspace.gcsim.source_acquisition import (
    GCSIM_UPSTREAM_REPO,
    GcsimSourceAcquisitionError,
    OfficialGcsimSourceAcquisition,
    OfficialGcsimSourceRef,
    acquire_official_gcsim_source_from_archive,
)


class GcsimEngineUpdateTest(unittest.TestCase):
    def test_fake_official_source_acquisition_activates_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            patch_stack = _make_patch_stack(root / "patch-stack")

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                patch_stack_dir=patch_stack,
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
            )

            self.assertTrue(report.success)
            self.assertTrue(report.activated)
            self.assertFalse(report.runtime_ready)
            self.assertEqual(report.runtime_check_status, "not_requested")
            self.assertEqual(report.upstream_ref, "v-test")
            self.assertEqual(report.patch_count, 1)
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertTrue((active.path / "GTT_PATCH.txt").exists())

    def test_go_missing_probe_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(FileNotFoundError("go"))

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertFalse(report.runtime_ready)
            self.assertEqual(report.runtime_check_status, "go_missing")
            self.assertEqual(report.active_engine_id, old)
            self.assertIn("Go executable not found", report.error)

    def test_wrong_go_arch_probe_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(_completed(stdout="go version go1.22.0 windows/386\n"))

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "go_wrong_arch")
            self.assertEqual(report.go_os, "windows")
            self.assertEqual(report.go_arch, "386")
            self.assertEqual(report.active_engine_id, old)

    def test_go_probe_nonzero_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _completed(returncode=1, stderr="build failed"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "runtime_probe_failed")
            self.assertIn("build failed", report.runtime_probe_stderr)
            self.assertEqual(report.active_engine_id, old)

    def test_go_probe_timeout_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                subprocess.TimeoutExpired(cmd=["go", "run"], timeout=1),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=runner,
                runtime_probe_timeout_seconds=1,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "runtime_probe_timeout")
            self.assertEqual(report.active_engine_id, old)

    def test_successful_fake_go_probe_activates_runtime_ready_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            go_work = root / ".go-test"
            runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _completed(stdout="gcsim version test\n"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=runner,
                go_work_dir=go_work,
            )

            self.assertTrue(report.success)
            self.assertTrue(report.activated)
            self.assertTrue(report.runtime_ready)
            self.assertEqual(report.runtime_check_status, "runtime_probe_passed")
            self.assertEqual(report.go_version, "go1.22.0")
            self.assertEqual(report.go_os, "windows")
            self.assertEqual(report.go_arch, "amd64")
            self.assertIn("go run ./cmd/gcsim -version", report.runtime_probe_command)
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            metadata = active.manifest.metadata
            self.assertEqual(metadata["runtime_ready"], "true")
            self.assertEqual(metadata["runtime_check_status"], "runtime_probe_passed")
            self.assertEqual(metadata["go_version"], "go1.22.0")
            self.assertIn(str(go_work), metadata["go_env_root"])
            self.assertIn("GOMODCACHE", runner.calls[0]["env"])
            self.assertIn(str(go_work), runner.calls[0]["env"]["GOMODCACHE"])

    def test_download_failure_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            store = GcsimEngineStore(store_dir)
            old = _install_old_active_engine(store, root)

            report = prepare_official_gcsim_engine_update(
                release="latest",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_failing_acquirer("simulated download failure"),
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.active_engine_id, old)
            self.assertIn("simulated download failure", report.error)
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.engine_id, old)

    def test_corrupt_archive_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            corrupt = root / "corrupt.zip"
            corrupt.write_bytes(b"not a zip")

            report = prepare_official_gcsim_engine_update(
                release="v-bad",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(corrupt, tag="v-bad"),
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.active_engine_id, old)
            self.assertIn("valid zip", report.error)

    def test_source_layout_failure_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(
                root / "missing-layout.zip",
                include_main=False,
            )

            report = prepare_official_gcsim_engine_update(
                release="v-layout-bad",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-layout-bad"),
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.active_engine_id, old)
            self.assertIn("cmd/gcsim/main.go", report.error)
            self.assertTrue((GcsimEngineStore(store_dir).failed_dir / report.engine_id).exists())

    def test_manifest_includes_upstream_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            report = prepare_official_gcsim_engine_update(
                release="latest",
                store_dir=root / "store",
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
            )

            self.assertTrue(report.success)
            active = GcsimEngineStore(root / "store").get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            metadata = active.manifest.metadata
            self.assertEqual(metadata["upstream_repo"], GCSIM_UPSTREAM_REPO)
            self.assertEqual(metadata["upstream_release_request"], "latest")
            self.assertEqual(metadata["upstream_ref"], "v-test")
            self.assertEqual(metadata["source_acquisition_status"], "ok")
            self.assertEqual(metadata["check_status"], "source_layout_passed")
            self.assertEqual(metadata["runtime_ready"], "false")
            self.assertEqual(metadata["runtime_check_status"], "not_requested")

    def test_old_active_remains_available_after_failed_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)

            prepare_official_gcsim_engine_update(
                release="latest",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_failing_acquirer("no network today"),
            )

            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.engine_id, old)
            self.assertEqual((active.path / "engine.txt").read_text(encoding="utf-8"), "old")


def _archive_acquirer(archive: Path, *, tag: str):
    def acquire(*, release: str, cache_dir: str | Path) -> OfficialGcsimSourceAcquisition:
        return acquire_official_gcsim_source_from_archive(
            source_ref=_source_ref(tag=tag, requested_release=release),
            archive_path=archive,
            cache_dir=cache_dir,
        )

    return acquire


def _failing_acquirer(message: str):
    def acquire(*, release: str, cache_dir: str | Path) -> OfficialGcsimSourceAcquisition:
        raise GcsimSourceAcquisitionError(message)

    return acquire


def _source_ref(*, tag: str, requested_release: str = "latest") -> OfficialGcsimSourceRef:
    return OfficialGcsimSourceRef(
        requested_release=requested_release,
        tag=tag,
        archive_url=f"https://api.github.example/repos/genshinsim/gcsim/zipball/{tag}",
        html_url=f"https://github.example/genshinsim/gcsim/releases/tag/{tag}",
        api_url=f"https://api.github.example/repos/genshinsim/gcsim/releases/tags/{tag}",
    )


def _write_fake_gcsim_archive(
    archive_path: Path,
    *,
    include_main: bool = True,
) -> Path:
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("genshinsim-gcsim-test/go.mod", "module github.com/genshinsim/gcsim\n")
        if include_main:
            archive.writestr("genshinsim-gcsim-test/cmd/gcsim/main.go", "package main\n")
        archive.writestr("genshinsim-gcsim-test/pkg/simulator/simulator.go", "package simulator\n")
        archive.writestr("genshinsim-gcsim-test/pkg/model/model.go", "package model\n")
    return archive_path


def _make_patch_stack(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "GTT_PATCH.txt").write_text("patched", encoding="utf-8")
    return path


def _install_old_active_engine(store: GcsimEngineStore, root: Path) -> str:
    source = root / "old-source"
    source.mkdir()
    (source / "engine.txt").write_text("old", encoding="utf-8")
    result = store.prepare_engine_update(
        source_dir=source,
        source_label="old",
        engine_id="old-engine",
    )
    assert result.success
    return "old-engine"


class FakeGoRunner:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[dict] = []

    def __call__(self, command, cwd, env, timeout):
        self.calls.append(
            {
                "command": tuple(command),
                "cwd": cwd,
                "env": dict(env),
                "timeout": timeout,
            }
        )
        if not self.results:
            raise AssertionError(f"Unexpected command: {command}")
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _completed(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["go"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


if __name__ == "__main__":
    unittest.main()
