"""Build and verify a local executable artifact for a prepared GCSIM tree.

This backend-only helper is the first step from "source can run through Go" to
"the engine folder contains a ready executable". It intentionally does not
install dependencies or integrate with UI; tests inject fake runners so no test
requires real Go.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess

from .runtime_probe import (
    DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    DEFAULT_GO_WORK_DIR,
    EXPECTED_GO_ARCH,
    EXPECTED_GO_OS,
    GoRunner,
    _go_sandbox_env,
    _parse_go_version,
    _trim_probe_text,
)


DEFAULT_GCSIM_ARTIFACT_RELATIVE_PATH = Path("build") / "gtt-gcsim.exe"
GTT_INFO_CAPABILITY = "gtt_engine_marker"
GTT_INFO_COMMAND_FLAG = "-gtt-info"
GTT_INFO_SOURCE_FLAG_NAME = "gtt-info"


@dataclass(frozen=True, slots=True)
class GcsimBuildArtifactResult:
    status: str
    runtime_ready: bool
    artifact_ready: bool
    go_available: bool
    go_version: str = ""
    go_os: str = ""
    go_arch: str = ""
    go_env_root: str = ""
    artifact_path: str = ""
    artifact_relative_path: str = ""
    artifact_filename: str = ""
    artifact_sha256: str = ""
    artifact_runtime_check_status: str = ""
    build_command: tuple[str, ...] = ()
    build_stdout: str = ""
    build_stderr: str = ""
    artifact_version_command: tuple[str, ...] = ()
    artifact_version_stdout: str = ""
    artifact_version_stderr: str = ""
    gtt_marker_required: bool = False
    gtt_marker_ready: bool = False
    gtt_patch_version: str = ""
    gtt_capabilities: tuple[str, ...] = ()
    gtt_sequential_waves: str = ""
    gtt_upstream_version: str = ""
    gtt_info_command: tuple[str, ...] = ()
    gtt_info_stdout: str = ""
    gtt_info_stderr: str = ""
    error: str = ""

    def metadata(self) -> dict[str, str]:
        return {
            "runtime_ready": "true" if self.runtime_ready else "false",
            "runtime_check_status": self.status,
            "go_available": "true" if self.go_available else "false",
            "go_version": self.go_version,
            "go_os": self.go_os,
            "go_arch": self.go_arch,
            "go_env_root": self.go_env_root,
            "artifact_build_requested": "true",
            "artifact_ready": "true" if self.artifact_ready else "false",
            "artifact_kind": "local_build",
            "artifact_path": self.artifact_relative_path or self.artifact_path,
            "artifact_relative_path": self.artifact_relative_path,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_build_status": self._artifact_build_status(),
            "artifact_runtime_check_status": self.artifact_runtime_check_status or self.status,
            "artifact_build_command": " ".join(self.build_command),
            "artifact_build_stdout": self.build_stdout,
            "artifact_build_stderr": self.build_stderr,
            "artifact_version_command": " ".join(self.artifact_version_command),
            "artifact_version_stdout": self.artifact_version_stdout,
            "artifact_version_stderr": self.artifact_version_stderr,
            "gtt_marker_required": "true" if self.gtt_marker_required else "false",
            "gtt_marker_ready": "true" if self.gtt_marker_ready else "false",
            "gtt_info_status": self._gtt_info_status(),
            "gtt_patch_version": self.gtt_patch_version,
            "gtt_capabilities": json.dumps(list(self.gtt_capabilities), ensure_ascii=True),
            "gtt_sequential_waves": self.gtt_sequential_waves,
            "gtt_upstream_version": self.gtt_upstream_version,
            "gtt_info_command": " ".join(self.gtt_info_command),
            "gtt_info_stdout": self.gtt_info_stdout,
            "gtt_info_stderr": self.gtt_info_stderr,
            "artifact_error": self.error,
            "shipped_fallback_status": "planned_not_implemented",
        }

    def _artifact_build_status(self) -> str:
        if self.artifact_ready:
            return "artifact_build_passed"
        if self.status in {
            "artifact_build_failed",
            "artifact_build_timeout",
            "artifact_missing",
        }:
            return self.status
        if self.build_command:
            return "artifact_build_incomplete"
        return "not_started"

    def _gtt_info_status(self) -> str:
        if self.gtt_marker_ready:
            return "gtt_info_passed"
        if self.gtt_marker_required:
            return self.status if self.status.startswith("gtt_info_") else "gtt_info_not_run"
        return "not_required"


def build_gcsim_artifact(
    engine_dir: str | Path,
    *,
    artifact_relative_path: str | Path = DEFAULT_GCSIM_ARTIFACT_RELATIVE_PATH,
    go_executable: str = "go",
    go_work_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    runner: GoRunner | None = None,
    expected_go_os: str = EXPECTED_GO_OS,
    expected_go_arch: str = EXPECTED_GO_ARCH,
    require_gtt_marker: bool = False,
    expected_gtt_capability: str = GTT_INFO_CAPABILITY,
) -> GcsimBuildArtifactResult:
    engine_dir = Path(engine_dir)
    artifact_relative_path = Path(artifact_relative_path)
    if artifact_relative_path.is_absolute() or ".." in artifact_relative_path.parts:
        return _result(
            status="artifact_path_invalid",
            runtime_ready=False,
            artifact_ready=False,
            go_available=False,
            go_env_root=Path(go_work_dir) if go_work_dir is not None else DEFAULT_GO_WORK_DIR,
            artifact_path=Path(),
            error=f"Artifact path must stay relative to the engine folder: {artifact_relative_path}",
        )
    artifact_path = engine_dir / artifact_relative_path
    go_root = Path(go_work_dir) if go_work_dir is not None else DEFAULT_GO_WORK_DIR
    env = _go_sandbox_env(go_root)
    command_runner = runner or _subprocess_runner

    go_check = _check_go_toolchain(
        go_executable=go_executable,
        go_root=go_root,
        env=env,
        timeout_seconds=int(timeout_seconds),
        runner=command_runner,
        expected_go_os=expected_go_os,
        expected_go_arch=expected_go_arch,
    )
    if isinstance(go_check, GcsimBuildArtifactResult):
        return go_check
    go_version, go_os, go_arch = go_check
    if require_gtt_marker and not _source_has_gtt_marker(engine_dir):
        return _result(
            status="gtt_info_missing",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=Path(),
            gtt_marker_required=True,
            error=(
                "Prepared GCSIM source tree does not contain the required "
                "GTT marker command before build."
            ),
        )

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    build_command = (
        go_executable,
        "build",
        "-o",
        str(artifact_path),
        "./cmd/gcsim",
    )
    try:
        build_result = command_runner(
            build_command,
            engine_dir,
            env,
            int(timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        return _result(
            status="artifact_build_timeout",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            build_command=build_command,
            build_stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            build_stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="GCSIM artifact build timed out.",
        )
    except OSError as exc:
        return _result(
            status="artifact_build_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            build_command=build_command,
            error=str(exc),
        )
    if build_result.returncode != 0:
        return _result(
            status="artifact_build_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            error=f"GCSIM artifact build exited with {build_result.returncode}.",
        )
    if not artifact_path.exists():
        return _result(
            status="artifact_missing",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            error="GCSIM artifact build did not create the expected executable.",
        )

    artifact_version_command = (str(artifact_path), "-version")
    try:
        artifact_version_result = command_runner(
            artifact_version_command,
            engine_dir,
            env,
            int(timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        return _result(
            status="artifact_version_timeout",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            artifact_sha256=_file_sha256(artifact_path),
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            artifact_version_command=artifact_version_command,
            artifact_version_stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            artifact_version_stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="Built GCSIM artifact version check timed out.",
        )
    except OSError as exc:
        return _result(
            status="artifact_version_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            artifact_sha256=_file_sha256(artifact_path),
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            artifact_version_command=artifact_version_command,
            error=str(exc),
        )
    if artifact_version_result.returncode != 0:
        return _result(
            status="artifact_version_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=artifact_path,
            artifact_relative_path=artifact_relative_path.as_posix(),
            artifact_sha256=_file_sha256(artifact_path),
            artifact_runtime_check_status="artifact_version_failed",
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            artifact_version_command=artifact_version_command,
            artifact_version_stdout=artifact_version_result.stdout,
            artifact_version_stderr=artifact_version_result.stderr,
            error=f"Built GCSIM artifact version check exited with {artifact_version_result.returncode}.",
        )

    artifact_sha256 = _file_sha256(artifact_path)
    common_success = {
        "artifact_ready": True,
        "go_available": True,
        "go_version": go_version,
        "go_os": go_os,
        "go_arch": go_arch,
        "go_env_root": go_root,
        "artifact_path": artifact_path,
        "artifact_relative_path": artifact_relative_path.as_posix(),
        "artifact_sha256": artifact_sha256,
        "artifact_runtime_check_status": "artifact_runtime_passed",
        "build_command": build_command,
        "build_stdout": build_result.stdout,
        "build_stderr": build_result.stderr,
        "artifact_version_command": artifact_version_command,
        "artifact_version_stdout": artifact_version_result.stdout,
        "artifact_version_stderr": artifact_version_result.stderr,
        "gtt_marker_required": require_gtt_marker,
    }
    if not require_gtt_marker:
        return _result(
            status="artifact_runtime_passed",
            runtime_ready=True,
            **common_success,
        )

    gtt_info_command = (str(artifact_path), GTT_INFO_COMMAND_FLAG)
    try:
        gtt_info_result = command_runner(
            gtt_info_command,
            engine_dir,
            env,
            int(timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        return _result(
            status="gtt_info_timeout",
            runtime_ready=False,
            gtt_info_command=gtt_info_command,
            gtt_info_stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            gtt_info_stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="Built GCSIM artifact GTT marker check timed out.",
            **common_success,
        )
    except OSError as exc:
        return _result(
            status="gtt_info_failed",
            runtime_ready=False,
            gtt_info_command=gtt_info_command,
            error=str(exc),
            **common_success,
        )
    if gtt_info_result.returncode != 0:
        return _result(
            status="gtt_info_failed",
            runtime_ready=False,
            gtt_info_command=gtt_info_command,
            gtt_info_stdout=gtt_info_result.stdout,
            gtt_info_stderr=gtt_info_result.stderr,
            error=f"Built GCSIM artifact GTT marker check exited with {gtt_info_result.returncode}.",
            **common_success,
        )

    parsed = _parse_gtt_info(
        gtt_info_result.stdout,
        expected_capability=expected_gtt_capability,
    )
    if isinstance(parsed, str):
        return _result(
            status=parsed,
            runtime_ready=False,
            gtt_info_command=gtt_info_command,
            gtt_info_stdout=gtt_info_result.stdout,
            gtt_info_stderr=gtt_info_result.stderr,
            error=_gtt_info_error(parsed, expected_gtt_capability),
            **common_success,
        )
    return _result(
        status="gtt_info_passed",
        runtime_ready=True,
        gtt_marker_ready=True,
        gtt_patch_version=parsed["patch_version"],
        gtt_capabilities=tuple(parsed["capabilities"]),
        gtt_sequential_waves=parsed["sequential_waves"],
        gtt_upstream_version=parsed["upstream_version"],
        gtt_info_command=gtt_info_command,
        gtt_info_stdout=gtt_info_result.stdout,
        gtt_info_stderr=gtt_info_result.stderr,
        **common_success,
    )


def _subprocess_runner(
    command,
    cwd,
    env,
    timeout_seconds,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=None if cwd is None else str(cwd),
        env=dict(env),
        timeout=int(timeout_seconds),
        check=False,
        capture_output=True,
        text=True,
    )


def _check_go_toolchain(
    *,
    go_executable: str,
    go_root: Path,
    env: dict[str, str],
    timeout_seconds: int,
    runner: GoRunner,
    expected_go_os: str,
    expected_go_arch: str,
) -> GcsimBuildArtifactResult | tuple[str, str, str]:
    version_command = (go_executable, "version")
    try:
        version_result = runner(version_command, None, env, timeout_seconds)
    except FileNotFoundError as exc:
        return _result(
            status="go_missing",
            runtime_ready=False,
            artifact_ready=False,
            go_available=False,
            go_env_root=go_root,
            artifact_path=Path(),
            error=f"Go executable not found: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        return _result(
            status="go_version_timeout",
            runtime_ready=False,
            artifact_ready=False,
            go_available=False,
            go_env_root=go_root,
            artifact_path=Path(),
            artifact_version_command=version_command,
            artifact_version_stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            artifact_version_stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="go version timed out",
        )
    except OSError as exc:
        return _result(
            status="go_version_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=False,
            go_env_root=go_root,
            artifact_path=Path(),
            artifact_version_command=version_command,
            error=str(exc),
        )

    parsed = _parse_go_version(version_result.stdout.strip())
    if version_result.returncode != 0 or parsed is None:
        return _result(
            status="go_version_failed",
            runtime_ready=False,
            artifact_ready=False,
            go_available=False,
            go_env_root=go_root,
            artifact_path=Path(),
            artifact_version_command=version_command,
            artifact_version_stdout=version_result.stdout,
            artifact_version_stderr=version_result.stderr,
            error=(
                f"go version exited with {version_result.returncode}"
                if version_result.returncode != 0
                else "Could not parse go version output."
            ),
        )
    go_version, go_os, go_arch = parsed
    if go_os != expected_go_os or go_arch != expected_go_arch:
        return _result(
            status="go_wrong_arch",
            runtime_ready=False,
            artifact_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            artifact_path=Path(),
            artifact_version_command=version_command,
            artifact_version_stdout=version_result.stdout,
            artifact_version_stderr=version_result.stderr,
            error=f"Expected Go target {expected_go_os}/{expected_go_arch}, got {go_os}/{go_arch}.",
        )
    return go_version, go_os, go_arch


def _result(
    *,
    status: str,
    runtime_ready: bool,
    artifact_ready: bool,
    go_available: bool,
    go_env_root: Path,
    artifact_path: Path,
    artifact_relative_path: str = "",
    go_version: str = "",
    go_os: str = "",
    go_arch: str = "",
    artifact_sha256: str = "",
    artifact_runtime_check_status: str = "",
    build_command=(),
    build_stdout: str = "",
    build_stderr: str = "",
    artifact_version_command=(),
    artifact_version_stdout: str = "",
    artifact_version_stderr: str = "",
    gtt_marker_required: bool = False,
    gtt_marker_ready: bool = False,
    gtt_patch_version: str = "",
    gtt_capabilities=(),
    gtt_sequential_waves: str = "",
    gtt_upstream_version: str = "",
    gtt_info_command=(),
    gtt_info_stdout: str = "",
    gtt_info_stderr: str = "",
    error: str = "",
) -> GcsimBuildArtifactResult:
    return GcsimBuildArtifactResult(
        status=status,
        runtime_ready=runtime_ready,
        artifact_ready=artifact_ready,
        go_available=go_available,
        go_version=go_version,
        go_os=go_os,
        go_arch=go_arch,
        go_env_root=str(go_env_root) if str(go_env_root) != "." else "",
        artifact_path="" if not str(artifact_path) else str(artifact_path),
        artifact_relative_path=artifact_relative_path,
        artifact_filename="" if not str(artifact_path) else artifact_path.name,
        artifact_sha256=artifact_sha256,
        artifact_runtime_check_status=artifact_runtime_check_status,
        build_command=tuple(str(part) for part in build_command),
        build_stdout=_trim_probe_text(build_stdout),
        build_stderr=_trim_probe_text(build_stderr),
        artifact_version_command=tuple(str(part) for part in artifact_version_command),
        artifact_version_stdout=_trim_probe_text(artifact_version_stdout),
        artifact_version_stderr=_trim_probe_text(artifact_version_stderr),
        gtt_marker_required=gtt_marker_required,
        gtt_marker_ready=gtt_marker_ready,
        gtt_patch_version=_trim_probe_text(gtt_patch_version),
        gtt_capabilities=tuple(str(item) for item in gtt_capabilities),
        gtt_sequential_waves=_trim_probe_text(gtt_sequential_waves),
        gtt_upstream_version=_trim_probe_text(gtt_upstream_version),
        gtt_info_command=tuple(str(part) for part in gtt_info_command),
        gtt_info_stdout=_trim_probe_text(gtt_info_stdout),
        gtt_info_stderr=_trim_probe_text(gtt_info_stderr),
        error=_trim_probe_text(error),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _parse_gtt_info(
    text: str,
    *,
    expected_capability: str,
) -> dict[str, object] | str:
    try:
        data = json.loads(str(text or "").strip())
    except json.JSONDecodeError:
        return "gtt_info_invalid"
    if not isinstance(data, dict):
        return "gtt_info_invalid"
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        return "gtt_info_invalid"
    capability_values = [str(item) for item in capabilities]
    if data.get("gtt_engine") is not True or expected_capability not in capability_values:
        return "gtt_info_missing"
    patch_version = str(data.get("gtt_patch_version") or "").strip()
    if not patch_version:
        return "gtt_info_missing"
    sequential_waves = data.get("sequential_waves")
    return {
        "patch_version": patch_version,
        "capabilities": capability_values,
        "sequential_waves": "true" if sequential_waves is True else "false",
        "upstream_version": str(data.get("upstream_version") or "").strip(),
    }


def _gtt_info_error(status: str, expected_capability: str) -> str:
    if status == "gtt_info_missing":
        return (
            "Built GCSIM artifact did not report the required GTT marker "
            f"capability: {expected_capability}."
        )
    if status == "gtt_info_invalid":
        return "Built GCSIM artifact returned invalid GTT marker JSON."
    return status


def _source_has_gtt_marker(engine_dir: Path) -> bool:
    main_path = engine_dir / "cmd" / "gcsim" / "main.go"
    info_path = engine_dir / "pkg" / "gtt" / "info.go"
    try:
        main_text = main_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return info_path.exists() and GTT_INFO_SOURCE_FLAG_NAME in main_text

