from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.engine_update import (
    make_patch_backend,
    prepare_official_gcsim_engine_update,
)
from run_workspace.gcsim.patch_backends import GitApplyPatchBackend
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

    def test_git_patch_backend_and_runtime_probe_pass_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            patch_stack = _make_git_patch_stack(root / "patch-stack")
            go_runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _completed(stdout="gcsim version test\n"),
            )
            git_runner = FakeGitRunner(_completed(), _write_gtt_marker_source)

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                patch_stack_dir=patch_stack,
                patch_backend=GitApplyPatchBackend(runner=git_runner),
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                probe_runtime=True,
                runtime_probe_runner=go_runner,
                go_work_dir=root / ".go-test",
            )

            self.assertTrue(report.success)
            self.assertTrue(report.activated)
            self.assertTrue(report.runtime_ready)
            self.assertEqual(report.patch_backend, "git")
            self.assertEqual(report.patch_count, 1)
            self.assertEqual(report.patch_files, ("001-marker.patch",))
            self.assertEqual(report.patch_check_status, "passed")
            self.assertEqual(report.patch_apply_status, "passed")
            self.assertEqual(report.patch_git_status, "available")
            self.assertEqual(report.runtime_check_status, "runtime_probe_passed")
            self.assertEqual(len(git_runner.calls), 2)
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.manifest.patch_metadata["patch_apply_status"], "passed")

    def test_patch_backend_factory_selects_git_backend(self) -> None:
        self.assertIsInstance(make_patch_backend("git"), GitApplyPatchBackend)

    def test_successful_fake_build_artifact_activates_runtime_ready_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _write_fake_artifact,
                _completed(stdout="gcsim version built\n"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                build_artifact=True,
                artifact_build_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertTrue(report.success)
            self.assertTrue(report.activated)
            self.assertTrue(report.runtime_ready)
            self.assertTrue(report.artifact_ready)
            self.assertEqual(report.runtime_check_status, "artifact_runtime_passed")
            self.assertEqual(report.artifact_build_status, "artifact_build_passed")
            self.assertEqual(report.artifact_filename, "gtt-gcsim.exe")
            self.assertEqual(report.artifact_relative_path, "build/gtt-gcsim.exe")
            self.assertEqual(report.artifact_sha256, hashlib.sha256(b"fake artifact").hexdigest())
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertTrue((active.path / "build" / "gtt-gcsim.exe").exists())
            self.assertEqual(report.artifact_path, str(active.path / "build" / "gtt-gcsim.exe"))
            self.assertEqual(active.manifest.metadata["runtime_ready"], "true")
            self.assertEqual(active.manifest.metadata["artifact_ready"], "true")
            self.assertEqual(active.manifest.metadata["artifact_relative_path"], "build/gtt-gcsim.exe")
            self.assertEqual(active.manifest.metadata["artifact_path"], "build/gtt-gcsim.exe")
            self.assertEqual(
                active.manifest.metadata["artifact_sha256"],
                hashlib.sha256(b"fake artifact").hexdigest(),
            )

    def test_build_artifact_go_missing_keeps_old_active_engine(self) -> None:
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
                build_artifact=True,
                artifact_build_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertFalse(report.runtime_ready)
            self.assertEqual(report.runtime_check_status, "go_missing")
            self.assertEqual(report.active_engine_id, old)

    def test_build_artifact_wrong_go_arch_keeps_old_active_engine(self) -> None:
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
                build_artifact=True,
                artifact_build_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "go_wrong_arch")
            self.assertEqual(report.go_os, "windows")
            self.assertEqual(report.go_arch, "386")
            self.assertEqual(report.active_engine_id, old)

    def test_build_artifact_nonzero_build_keeps_old_active_engine(self) -> None:
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
                build_artifact=True,
                artifact_build_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "artifact_build_failed")
            self.assertIn("build failed", report.artifact_build_stderr)
            self.assertEqual(report.active_engine_id, old)

    def test_built_artifact_version_failure_keeps_old_active_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _write_fake_artifact,
                _completed(returncode=1, stderr="version failed"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                build_artifact=True,
                artifact_build_runner=runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "artifact_version_failed")
            self.assertEqual(report.artifact_sha256, hashlib.sha256(b"fake artifact").hexdigest())
            self.assertIn("version failed", report.artifact_version_stderr)
            self.assertEqual(report.active_engine_id, old)

    def test_gtt_marker_success_records_capabilities_and_activates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            patch_stack = _make_git_patch_stack(root / "patch-stack")
            git_runner = FakeGitRunner(_completed(), _write_gtt_marker_source)
            go_runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _write_fake_artifact,
                _completed(stdout="gcsim version built\n"),
                _completed(stdout=_gtt_info_stdout()),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                patch_stack_dir=patch_stack,
                patch_backend=GitApplyPatchBackend(runner=git_runner),
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                build_artifact=True,
                artifact_build_runner=go_runner,
                go_work_dir=root / ".go-test",
            )

            self.assertTrue(report.success)
            self.assertTrue(report.activated)
            self.assertTrue(report.runtime_ready)
            self.assertEqual(report.runtime_check_status, "gtt_info_passed")
            self.assertEqual(report.artifact_runtime_check_status, "artifact_runtime_passed")
            self.assertTrue(report.gtt_marker_required)
            self.assertTrue(report.gtt_marker_ready)
            self.assertEqual(report.gtt_patch_version, "gtt-wave-scenario-v1")
            self.assertEqual(
                report.gtt_capabilities,
                (
                    "gtt_engine_marker",
                    "gtt_wave_scheduler_prototype",
                    "gtt_wave_scenario_payload",
                ),
            )
            self.assertEqual(report.gtt_sequential_waves, "true")
            self.assertIn("-gtt-info", report.gtt_info_command)
            active = GcsimEngineStore(store_dir).get_active_engine()
            self.assertIsNotNone(active)
            assert active is not None
            self.assertIn("gtt_engine_marker", active.manifest.capabilities)
            self.assertEqual(active.manifest.metadata["gtt_marker_ready"], "true")
            self.assertEqual(active.manifest.metadata["gtt_patch_version"], "gtt-wave-scenario-v1")

    def test_gtt_marker_nonzero_keeps_old_active_engine_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            patch_stack = _make_git_patch_stack(root / "patch-stack")
            git_runner = FakeGitRunner(_completed(), _write_gtt_marker_source)
            go_runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _write_fake_artifact,
                _completed(stdout="gcsim version built\n"),
                _completed(returncode=2, stderr="flag provided but not defined: -gtt-info"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                patch_stack_dir=patch_stack,
                patch_backend=GitApplyPatchBackend(runner=git_runner),
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                build_artifact=True,
                artifact_build_runner=go_runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "gtt_info_failed")
            self.assertTrue(report.gtt_marker_required)
            self.assertFalse(report.gtt_marker_ready)
            self.assertIn("flag provided", report.gtt_info_stderr)
            self.assertEqual(report.active_engine_id, old)

    def test_gtt_marker_invalid_json_keeps_old_active_engine_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_dir = root / "store"
            old = _install_old_active_engine(GcsimEngineStore(store_dir), root)
            archive = _write_fake_gcsim_archive(root / "gcsim.zip")
            patch_stack = _make_git_patch_stack(root / "patch-stack")
            git_runner = FakeGitRunner(_completed(), _write_gtt_marker_source)
            go_runner = FakeGoRunner(
                _completed(stdout="go version go1.22.0 windows/amd64\n"),
                _write_fake_artifact,
                _completed(stdout="gcsim version built\n"),
                _completed(stdout="not json\n"),
            )

            report = prepare_official_gcsim_engine_update(
                release="v-test",
                store_dir=store_dir,
                source_cache_dir=root / "sources",
                patch_stack_dir=patch_stack,
                patch_backend=GitApplyPatchBackend(runner=git_runner),
                source_acquirer=_archive_acquirer(archive, tag="v-test"),
                build_artifact=True,
                artifact_build_runner=go_runner,
                go_work_dir=root / ".go-test",
            )

            self.assertFalse(report.success)
            self.assertFalse(report.activated)
            self.assertEqual(report.runtime_check_status, "gtt_info_invalid")
            self.assertFalse(report.gtt_marker_ready)
            self.assertIn("invalid GTT marker JSON", report.error)
            self.assertEqual(report.active_engine_id, old)

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


def _make_git_patch_stack(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "001-marker.patch").write_text("dummy patch", encoding="utf-8")
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
        if callable(result):
            return result(command, cwd, env, timeout)
        return result


class FakeGitRunner:
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


def _completed(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["go"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _write_fake_artifact(command, cwd, _env, _timeout):
    output_index = list(command).index("-o") + 1
    artifact_path = Path(command[output_index])
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"fake artifact")
    return _completed(stdout="built fake artifact\n")


def _write_gtt_marker_source(_command, cwd: Path):
    main_path = cwd / "cmd" / "gcsim" / "main.go"
    main_text = main_path.read_text(encoding="utf-8")
    if "gtt-info" not in main_text:
        main_path.write_text(main_text + '\n// fake test patch adds -gtt-info\n', encoding="utf-8")
    info_path = cwd / "pkg" / "gtt" / "info.go"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text("package gtt\n", encoding="utf-8")
    return _completed()


def _gtt_info_stdout() -> str:
    return json.dumps(
        {
            "gtt_engine": True,
            "gtt_patch_version": "gtt-wave-scenario-v1",
            "capabilities": [
                "gtt_engine_marker",
                "gtt_wave_scheduler_prototype",
                "gtt_wave_scenario_payload",
            ],
            "sequential_waves": True,
            "wave_scheduler_stage": "scenario_payload_prototype",
            "upstream_version": "gcsim version built",
        }
    )


if __name__ == "__main__":
    unittest.main()
