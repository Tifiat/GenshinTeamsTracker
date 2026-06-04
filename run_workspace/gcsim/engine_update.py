"""Dev command for official GCSIM source update through the engine store.

This command is intentionally backend-only. It downloads official source,
prepares it through `GcsimEngineStore`, records metadata, and can optionally
build a local executable artifact. It does not integrate GCSIM into UI.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .artifact_build import (
    DEFAULT_GCSIM_ARTIFACT_RELATIVE_PATH,
    GcsimBuildArtifactResult,
    build_gcsim_artifact,
)
from .engine_store import (
    GcsimEngineStore,
    GcsimEngineUpdateResult,
    OverlayPatchBackend,
    PatchBackend,
)
from .patch_backends import GitApplyPatchBackend
from .source_acquisition import (
    DEFAULT_GCSIM_SOURCE_CACHE_DIR,
    GCSIM_UPSTREAM_REPO,
    OfficialGcsimSourceAcquisition,
    acquire_official_gcsim_source,
)
from .runtime_probe import (
    DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    GcsimRuntimeProbeResult,
    GoRunner,
    run_gcsim_runtime_probe,
)


DEFAULT_GCSIM_PATCH_STACK_DIR = Path(__file__).resolve().parent / "patch_stack"
GCSIM_REQUIRED_SOURCE_PATHS = (
    "go.mod",
    "cmd/gcsim/main.go",
    "pkg/simulator",
    "pkg/model",
)


@dataclass(frozen=True, slots=True)
class GcsimOfficialEngineUpdateReport:
    success: bool
    activated: bool
    release: str
    engine_id: str | None
    previous_active_engine_id: str | None
    active_engine_id: str | None
    engine_path: str
    source_dir: str
    source_archive_path: str
    source_archive_url: str
    upstream_ref: str
    upstream_repo: str
    patch_backend: str
    patch_count: int
    patch_stack_path: str
    patch_stack_status: str
    patch_files: tuple[str, ...]
    patch_check_status: str
    patch_apply_status: str
    patch_git_status: str
    patch_git_executable: str
    check_status: str
    layout_check_status: str
    runtime_check_status: str
    runtime_ready: bool
    go_available: bool
    go_version: str
    go_os: str
    go_arch: str
    go_env_root: str
    runtime_probe_command: str
    runtime_probe_stdout: str
    runtime_probe_stderr: str
    artifact_build_requested: bool
    artifact_ready: bool
    artifact_kind: str
    artifact_path: str
    artifact_relative_path: str
    artifact_filename: str
    artifact_sha256: str
    artifact_build_status: str
    artifact_runtime_check_status: str
    artifact_build_command: str
    artifact_build_stdout: str
    artifact_build_stderr: str
    artifact_version_command: str
    artifact_version_stdout: str
    artifact_version_stderr: str
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "activated": self.activated,
            "release": self.release,
            "engine_id": self.engine_id,
            "previous_active_engine_id": self.previous_active_engine_id,
            "active_engine_id": self.active_engine_id,
            "engine_path": self.engine_path,
            "source_dir": self.source_dir,
            "source_archive_path": self.source_archive_path,
            "source_archive_url": self.source_archive_url,
            "upstream_ref": self.upstream_ref,
            "upstream_repo": self.upstream_repo,
            "patch_backend": self.patch_backend,
            "patch_count": self.patch_count,
            "patch_stack_path": self.patch_stack_path,
            "patch_stack_status": self.patch_stack_status,
            "patch_files": list(self.patch_files),
            "patch_check_status": self.patch_check_status,
            "patch_apply_status": self.patch_apply_status,
            "patch_git_status": self.patch_git_status,
            "patch_git_executable": self.patch_git_executable,
            "check_status": self.check_status,
            "layout_check_status": self.layout_check_status,
            "runtime_check_status": self.runtime_check_status,
            "runtime_ready": self.runtime_ready,
            "go_available": self.go_available,
            "go_version": self.go_version,
            "go_os": self.go_os,
            "go_arch": self.go_arch,
            "go_env_root": self.go_env_root,
            "runtime_probe_command": self.runtime_probe_command,
            "runtime_probe_stdout": self.runtime_probe_stdout,
            "runtime_probe_stderr": self.runtime_probe_stderr,
            "artifact_build_requested": self.artifact_build_requested,
            "artifact_ready": self.artifact_ready,
            "artifact_kind": self.artifact_kind,
            "artifact_path": self.artifact_path,
            "artifact_relative_path": self.artifact_relative_path,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_build_status": self.artifact_build_status,
            "artifact_runtime_check_status": self.artifact_runtime_check_status,
            "artifact_build_command": self.artifact_build_command,
            "artifact_build_stdout": self.artifact_build_stdout,
            "artifact_build_stderr": self.artifact_build_stderr,
            "artifact_version_command": self.artifact_version_command,
            "artifact_version_stdout": self.artifact_version_stdout,
            "artifact_version_stderr": self.artifact_version_stderr,
            "error": self.error,
        }


def prepare_official_gcsim_engine_update(
    *,
    release: str = "latest",
    store_dir: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    patch_stack_dir: str | Path | None = None,
    engine_id: str | None = None,
    patch_backend: PatchBackend | None = None,
    source_acquirer: Callable[..., OfficialGcsimSourceAcquisition] | None = None,
    probe_runtime: bool = False,
    runtime_probe_runner: GoRunner | None = None,
    build_artifact: bool = False,
    artifact_build_runner: GoRunner | None = None,
    artifact_relative_path: str | Path = DEFAULT_GCSIM_ARTIFACT_RELATIVE_PATH,
    go_executable: str = "go",
    go_work_dir: str | Path | None = None,
    runtime_probe_timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
) -> GcsimOfficialEngineUpdateReport:
    store = GcsimEngineStore(store_dir)
    previous_active = store.active_engine_id()
    acquirer = source_acquirer or acquire_official_gcsim_source
    try:
        acquisition = acquirer(
            release=release,
            cache_dir=source_cache_dir or DEFAULT_GCSIM_SOURCE_CACHE_DIR,
        )
    except Exception as exc:  # noqa: BLE001 - command/report boundary.
        return GcsimOfficialEngineUpdateReport(
            success=False,
            activated=False,
            release=str(release),
            engine_id=None,
            previous_active_engine_id=previous_active,
            active_engine_id=previous_active,
            engine_path="",
            source_dir="",
            source_archive_path="",
            source_archive_url="",
            upstream_ref="",
            upstream_repo=GCSIM_UPSTREAM_REPO,
            patch_backend=(patch_backend or OverlayPatchBackend()).name,
            patch_count=0,
            patch_stack_path="",
            patch_stack_status="not_started",
            patch_files=(),
            patch_check_status="not_started",
            patch_apply_status="not_started",
            patch_git_status="not_started",
            patch_git_executable="",
            check_status="source_acquisition_failed",
            layout_check_status="not_started",
            runtime_check_status="not_started",
            runtime_ready=False,
            go_available=False,
            go_version="",
            go_os="",
            go_arch="",
            go_env_root="",
            runtime_probe_command="",
            runtime_probe_stdout="",
            runtime_probe_stderr="",
            artifact_build_requested=build_artifact,
            artifact_ready=False,
            artifact_kind="local_build" if build_artifact else "",
            artifact_path="",
            artifact_relative_path="",
            artifact_filename=Path(artifact_relative_path).name if build_artifact else "",
            artifact_sha256="",
            artifact_build_status="not_started",
            artifact_runtime_check_status="not_started",
            artifact_build_command="",
            artifact_build_stdout="",
            artifact_build_stderr="",
            artifact_version_command="",
            artifact_version_stdout="",
            artifact_version_stderr="",
            error=str(exc),
        )

    patch_stack = _resolve_patch_stack_dir(patch_stack_dir)
    patch_stack_status = "present" if patch_stack is not None else "absent_no_patches"
    backend = patch_backend or OverlayPatchBackend()
    metadata = _engine_manifest_metadata(
        acquisition=acquisition,
        requested_release=release,
        patch_stack=patch_stack,
        patch_stack_status=patch_stack_status,
        probe_runtime=probe_runtime,
        build_artifact=build_artifact,
        artifact_relative_path=artifact_relative_path,
    )
    runtime_probe_state: dict[str, GcsimRuntimeProbeResult | None] = {"result": None}
    artifact_build_state: dict[str, GcsimBuildArtifactResult | None] = {"result": None}
    update_result = store.prepare_engine_update(
        source_dir=acquisition.source_dir,
        patch_stack_dir=patch_stack,
        source_label=f"gcsim-{acquisition.source_ref.tag}",
        engine_id=engine_id,
        patch_backend=backend,
        capabilities=_engine_capabilities(
            probe_runtime=probe_runtime,
            build_artifact=build_artifact,
        ),
        metadata=metadata,
        smoke_check=_make_engine_update_smoke_check(
            probe_runtime=probe_runtime,
            build_artifact=build_artifact,
            metadata=metadata,
            runtime_probe_state=runtime_probe_state,
            artifact_build_state=artifact_build_state,
            go_executable=go_executable,
            go_work_dir=go_work_dir,
            runtime_probe_runner=runtime_probe_runner,
            artifact_build_runner=artifact_build_runner,
            runtime_probe_timeout_seconds=runtime_probe_timeout_seconds,
            artifact_relative_path=artifact_relative_path,
        ),
    )
    return _report_from_update_result(
        release=release,
        store=store,
        acquisition=acquisition,
        patch_stack=patch_stack,
        patch_stack_status=patch_stack_status,
        update_result=update_result,
        probe_runtime=probe_runtime,
        runtime_probe_result=runtime_probe_state["result"],
        build_artifact=build_artifact,
        artifact_build_result=artifact_build_state["result"],
    )


def gcsim_source_layout_smoke_check(engine_dir: Path) -> str:
    missing = [
        relative
        for relative in GCSIM_REQUIRED_SOURCE_PATHS
        if not (engine_dir / relative).exists()
    ]
    if missing:
        return "GCSIM source layout check failed; missing: " + ", ".join(missing)
    return ""


def _make_engine_update_smoke_check(
    *,
    probe_runtime: bool,
    build_artifact: bool,
    metadata: dict[str, str],
    runtime_probe_state: dict[str, GcsimRuntimeProbeResult | None],
    artifact_build_state: dict[str, GcsimBuildArtifactResult | None],
    go_executable: str,
    go_work_dir: str | Path | None,
    runtime_probe_runner: GoRunner | None,
    artifact_build_runner: GoRunner | None,
    runtime_probe_timeout_seconds: int,
    artifact_relative_path: str | Path,
):
    def smoke_check(engine_dir: Path) -> str:
        layout_error = gcsim_source_layout_smoke_check(engine_dir)
        if layout_error:
            metadata["layout_check_status"] = "source_layout_failed"
            metadata["check_status"] = "source_layout_failed"
            return layout_error
        metadata["layout_check_status"] = "source_layout_passed"
        metadata["check_status"] = "source_layout_passed"
        if build_artifact:
            result = build_gcsim_artifact(
                engine_dir,
                artifact_relative_path=artifact_relative_path,
                go_executable=go_executable,
                go_work_dir=go_work_dir,
                timeout_seconds=runtime_probe_timeout_seconds,
                runner=artifact_build_runner or runtime_probe_runner,
            )
            artifact_build_state["result"] = result
            metadata.update(result.metadata())
            if result.runtime_ready:
                metadata["check_status"] = "artifact_runtime_passed"
                return ""
            metadata["check_status"] = result.status
            return result.error or result.status
        if not probe_runtime:
            metadata["runtime_check_status"] = "not_requested"
            metadata["runtime_ready"] = "false"
            return ""

        result = run_gcsim_runtime_probe(
            engine_dir,
            go_executable=go_executable,
            go_work_dir=go_work_dir,
            timeout_seconds=runtime_probe_timeout_seconds,
            runner=runtime_probe_runner,
        )
        runtime_probe_state["result"] = result
        metadata.update(result.metadata())
        if result.runtime_ready:
            metadata["check_status"] = "runtime_probe_passed"
            return ""
        metadata["check_status"] = result.status
        return result.error or result.status

    return smoke_check


def _engine_capabilities(*, probe_runtime: bool, build_artifact: bool) -> tuple[str, ...]:
    capabilities = ["official_source_layout", "gtt_patch_stack_boundary"]
    if build_artifact:
        capabilities.extend(["local_build_artifact", "built_artifact_runtime_probe"])
    if probe_runtime and not build_artifact:
        capabilities.append("go_runtime_probe")
    return tuple(capabilities)


def _engine_manifest_metadata(
    *,
    acquisition: OfficialGcsimSourceAcquisition,
    requested_release: str,
    patch_stack: Path | None,
    patch_stack_status: str,
    probe_runtime: bool,
    build_artifact: bool,
    artifact_relative_path: str | Path,
) -> dict[str, str]:
    runtime_pending = probe_runtime or build_artifact
    return {
        "upstream_repo": acquisition.source_ref.upstream_repo,
        "upstream_release_request": str(requested_release),
        "upstream_ref": acquisition.source_ref.tag,
        "upstream_source_archive_url": acquisition.source_ref.archive_url,
        "upstream_html_url": acquisition.source_ref.html_url,
        "upstream_api_url": acquisition.source_ref.api_url,
        "source_acquisition_status": "ok",
        "source_archive_path": str(acquisition.archive_path),
        "source_cache_dir": str(acquisition.cache_dir),
        "patch_stack_path": "" if patch_stack is None else str(patch_stack),
        "patch_stack_status": patch_stack_status,
        "check_status": "source_layout_passed",
        "layout_check_status": "source_layout_passed",
        "runtime_ready": "false",
        "runtime_check_status": "pending" if runtime_pending else "not_requested",
        "go_available": "false",
        "go_version": "",
        "go_os": "",
        "go_arch": "",
        "go_env_root": "",
        "runtime_probe_command": "",
        "runtime_probe_stdout": "",
        "runtime_probe_stderr": "",
        "artifact_build_requested": "true" if build_artifact else "false",
        "artifact_ready": "false",
        "artifact_kind": "local_build" if build_artifact else "",
        "artifact_path": "",
        "artifact_filename": Path(artifact_relative_path).name if build_artifact else "",
        "artifact_sha256": "",
        "artifact_build_status": "pending" if build_artifact else "not_requested",
        "artifact_runtime_check_status": "pending" if build_artifact else "not_requested",
        "artifact_build_command": "",
        "artifact_build_stdout": "",
        "artifact_build_stderr": "",
        "artifact_version_command": "",
        "artifact_version_stdout": "",
        "artifact_version_stderr": "",
        "shipped_fallback_status": "planned_not_implemented",
    }


def _runtime_status_for_report(
    *,
    probe_runtime: bool,
    runtime_probe_result: GcsimRuntimeProbeResult | None,
    build_artifact: bool,
    artifact_build_result: GcsimBuildArtifactResult | None,
    update_result: GcsimEngineUpdateResult,
) -> str:
    if artifact_build_result is not None:
        return artifact_build_result.status
    if build_artifact:
        return "not_run" if not update_result.success else "artifact_runtime_passed"
    if runtime_probe_result is not None:
        return runtime_probe_result.status
    if not probe_runtime:
        return "not_requested"
    if update_result.success:
        return "runtime_probe_passed"
    return "not_run"


def _report_from_update_result(
    *,
    release: str,
    store: GcsimEngineStore,
    acquisition: OfficialGcsimSourceAcquisition,
    patch_stack: Path | None,
    patch_stack_status: str,
    update_result: GcsimEngineUpdateResult,
    probe_runtime: bool,
    runtime_probe_result: GcsimRuntimeProbeResult | None,
    build_artifact: bool,
    artifact_build_result: GcsimBuildArtifactResult | None,
) -> GcsimOfficialEngineUpdateReport:
    active_engine_id = store.active_engine_id()
    patch_metadata = dict(update_result.patch_result.metadata)
    report_metadata = dict(update_result.manifest.metadata) if update_result.manifest else {}
    if artifact_build_result is not None:
        report_metadata.update(artifact_build_result.metadata())
    if runtime_probe_result is not None:
        report_metadata.update(runtime_probe_result.metadata())
    layout_status = (
        "source_layout_passed"
        if update_result.success or runtime_probe_result is not None or artifact_build_result is not None
        else (update_result.error or "engine_update_failed")
    )
    runtime_status = _runtime_status_for_report(
        probe_runtime=probe_runtime,
        runtime_probe_result=runtime_probe_result,
        build_artifact=build_artifact,
        artifact_build_result=artifact_build_result,
        update_result=update_result,
    )
    runtime_ready = (
        bool(artifact_build_result and artifact_build_result.runtime_ready)
        if build_artifact
        else bool(runtime_probe_result and runtime_probe_result.runtime_ready)
    )
    check_status = (
        runtime_status if (probe_runtime or build_artifact) else layout_status
        if update_result.success
        else (update_result.error or "engine_update_failed")
    )
    return GcsimOfficialEngineUpdateReport(
        success=update_result.success,
        activated=update_result.activated,
        release=str(release),
        engine_id=update_result.engine_id,
        previous_active_engine_id=update_result.previous_active_engine_id,
        active_engine_id=active_engine_id,
        engine_path="" if update_result.engine_path is None else str(update_result.engine_path),
        source_dir=str(acquisition.source_dir),
        source_archive_path=str(acquisition.archive_path),
        source_archive_url=acquisition.source_ref.archive_url,
        upstream_ref=acquisition.source_ref.tag,
        upstream_repo=acquisition.source_ref.upstream_repo,
        patch_backend=update_result.patch_result.backend,
        patch_count=update_result.patch_result.patch_count,
        patch_stack_path="" if patch_stack is None else str(patch_stack),
        patch_stack_status=patch_stack_status,
        patch_files=_patch_files_for_report(patch_metadata),
        patch_check_status=patch_metadata.get("patch_check_status", ""),
        patch_apply_status=patch_metadata.get("patch_apply_status", ""),
        patch_git_status=patch_metadata.get("patch_git_status", ""),
        patch_git_executable=patch_metadata.get("git_executable", ""),
        check_status=check_status,
        layout_check_status=layout_status,
        runtime_check_status=runtime_status,
        runtime_ready=runtime_ready,
        go_available=report_metadata.get("go_available", "false") == "true",
        go_version=report_metadata.get("go_version", ""),
        go_os=report_metadata.get("go_os", ""),
        go_arch=report_metadata.get("go_arch", ""),
        go_env_root=report_metadata.get("go_env_root", ""),
        runtime_probe_command=""
        if runtime_probe_result is None
        else " ".join(runtime_probe_result.command),
        runtime_probe_stdout="" if runtime_probe_result is None else runtime_probe_result.stdout,
        runtime_probe_stderr="" if runtime_probe_result is None else runtime_probe_result.stderr,
        artifact_build_requested=report_metadata.get("artifact_build_requested", "false") == "true",
        artifact_ready=report_metadata.get("artifact_ready", "false") == "true",
        artifact_kind=report_metadata.get("artifact_kind", ""),
        artifact_path=_artifact_path_for_report(
            engine_path=update_result.engine_path,
            metadata=report_metadata,
            artifact_build_result=artifact_build_result,
        ),
        artifact_relative_path=report_metadata.get("artifact_relative_path", ""),
        artifact_filename=report_metadata.get("artifact_filename", ""),
        artifact_sha256=report_metadata.get("artifact_sha256", ""),
        artifact_build_status=report_metadata.get("artifact_build_status", "not_requested"),
        artifact_runtime_check_status=report_metadata.get(
            "artifact_runtime_check_status",
            "not_requested",
        ),
        artifact_build_command=report_metadata.get("artifact_build_command", ""),
        artifact_build_stdout=report_metadata.get("artifact_build_stdout", ""),
        artifact_build_stderr=report_metadata.get("artifact_build_stderr", ""),
        artifact_version_command=report_metadata.get("artifact_version_command", ""),
        artifact_version_stdout=report_metadata.get("artifact_version_stdout", ""),
        artifact_version_stderr=report_metadata.get("artifact_version_stderr", ""),
        error=update_result.error,
    )


def _artifact_path_for_report(
    *,
    engine_path: Path | None,
    metadata: dict[str, str],
    artifact_build_result: GcsimBuildArtifactResult | None,
) -> str:
    relative = metadata.get("artifact_relative_path", "")
    if engine_path is not None and relative:
        return str(engine_path / Path(relative))
    if artifact_build_result is not None and artifact_build_result.artifact_path:
        return artifact_build_result.artifact_path
    return metadata.get("artifact_path", "")


def _go_target_text(report: GcsimOfficialEngineUpdateReport) -> str:
    if not report.go_os and not report.go_arch:
        return ""
    if report.go_os and report.go_arch:
        return f"{report.go_os}/{report.go_arch}"
    return report.go_os or report.go_arch


def make_patch_backend(name: str) -> PatchBackend:
    normalized = str(name).strip().lower()
    if normalized == "overlay":
        return OverlayPatchBackend()
    if normalized == "git":
        return GitApplyPatchBackend()
    raise ValueError(f"Unsupported GCSIM patch backend: {name!r}")


def _patch_files_for_report(metadata: dict[str, str]) -> tuple[str, ...]:
    raw = metadata.get("patch_files", "")
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data)


def _resolve_patch_stack_dir(path: str | Path | None) -> Path | None:
    if path is not None:
        return Path(path)
    if DEFAULT_GCSIM_PATCH_STACK_DIR.exists():
        return DEFAULT_GCSIM_PATCH_STACK_DIR
    return None


def _format_report_text(report: GcsimOfficialEngineUpdateReport) -> str:
    lines = [
        "GCSIM engine source update",
        f"success={report.success} activated={report.activated}",
        f"release={report.release} upstream_ref={report.upstream_ref}",
        f"engine_id={report.engine_id or ''}",
        f"active_engine_id={report.active_engine_id or ''}",
        f"previous_active_engine_id={report.previous_active_engine_id or ''}",
        f"source_dir={report.source_dir}",
        f"archive={report.source_archive_path}",
        f"engine_path={report.engine_path}",
        (
            "patch="
            f"backend={report.patch_backend} count={report.patch_count} "
            f"stack_status={report.patch_stack_status} "
            f"check={report.patch_check_status or ''} "
            f"apply={report.patch_apply_status or ''} "
            f"git={report.patch_git_status or ''}"
        ),
        (
            "checks="
            f"layout={report.layout_check_status} "
            f"runtime={report.runtime_check_status} "
            f"runtime_ready={str(report.runtime_ready).lower()}"
        ),
        (
            "artifact="
            f"requested={str(report.artifact_build_requested).lower()} "
            f"ready={str(report.artifact_ready).lower()} "
            f"status={report.artifact_build_status} "
            f"path={report.artifact_path or ''} "
            f"sha256={report.artifact_sha256 or ''}"
        ),
        (
            "go="
            f"available={str(report.go_available).lower()} "
            f"version={report.go_version or ''} "
            f"target={_go_target_text(report)} "
            f"cache={report.go_env_root or ''}"
        ),
    ]
    if report.runtime_probe_stdout:
        lines.append(f"probe_stdout={report.runtime_probe_stdout}")
    if report.runtime_probe_stderr:
        lines.append(f"probe_stderr={report.runtime_probe_stderr}")
    if report.artifact_build_stdout:
        lines.append(f"artifact_build_stdout={report.artifact_build_stdout}")
    if report.artifact_build_stderr:
        lines.append(f"artifact_build_stderr={report.artifact_build_stderr}")
    if report.artifact_version_stdout:
        lines.append(f"artifact_version_stdout={report.artifact_version_stdout}")
    if report.artifact_version_stderr:
        lines.append(f"artifact_version_stderr={report.artifact_version_stderr}")
    if report.patch_files:
        lines.append("patch_files=" + ", ".join(report.patch_files))
    if report.error:
        lines.append(f"error={report.error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch official genshinsim/gcsim source and prepare a local "
            "transactional GTT engine folder."
        )
    )
    parser.add_argument("--release", default="latest", help="GitHub release tag or 'latest'.")
    parser.add_argument("--store-dir", default=None, help="Optional engine store root.")
    parser.add_argument("--source-cache-dir", default=None, help="Optional source cache root.")
    parser.add_argument(
        "--patch-stack",
        default=None,
        help=(
            "Optional patch-stack directory. If omitted, the command uses "
            "run_workspace/gcsim/patch_stack only when it exists."
        ),
    )
    parser.add_argument(
        "--patch-backend",
        choices=("overlay", "git"),
        default="overlay",
        help=(
            "Patch backend to use. 'overlay' copies fixture files and remains the "
            "conservative default; 'git' applies ordered .patch files with git apply."
        ),
    )
    parser.add_argument("--engine-id", default=None, help="Optional explicit engine id.")
    parser.add_argument(
        "--probe-runtime",
        action="store_true",
        help=(
            "Run an optional Go runtime probe. The new engine activates only if "
            "source layout and `go run ./cmd/gcsim -version` pass."
        ),
    )
    parser.add_argument(
        "--build-artifact",
        action="store_true",
        help=(
            "Build build/gtt-gcsim.exe with `go build` and verify that executable "
            "with `-version`. The new engine activates only if build and artifact "
            "runtime check pass."
        ),
    )
    parser.add_argument("--go-executable", default="go", help="Go executable name/path.")
    parser.add_argument(
        "--go-work-dir",
        default=None,
        help="Project-local Go cache root. Defaults to .go under the project root.",
    )
    parser.add_argument(
        "--runtime-probe-timeout",
        type=int,
        default=DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
        help="Timeout in seconds for each Go probe command.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = prepare_official_gcsim_engine_update(
        release=args.release,
        store_dir=args.store_dir,
        source_cache_dir=args.source_cache_dir,
        patch_stack_dir=args.patch_stack,
        engine_id=args.engine_id,
        patch_backend=make_patch_backend(args.patch_backend),
        probe_runtime=args.probe_runtime,
        build_artifact=args.build_artifact,
        go_executable=args.go_executable,
        go_work_dir=args.go_work_dir,
        runtime_probe_timeout_seconds=args.runtime_probe_timeout,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_report_text(report))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
