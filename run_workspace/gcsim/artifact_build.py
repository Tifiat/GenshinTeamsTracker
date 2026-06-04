"""Build and verify a local executable artifact for a prepared GCSIM tree.

This backend-only helper is the first step from "source can run through Go" to
"the engine folder contains a ready executable". It intentionally does not
install dependencies or integrate with UI; tests inject fake runners so no test
requires real Go.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    build_command: tuple[str, ...] = ()
    build_stdout: str = ""
    build_stderr: str = ""
    artifact_version_command: tuple[str, ...] = ()
    artifact_version_stdout: str = ""
    artifact_version_stderr: str = ""
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
            "artifact_runtime_check_status": self.status,
            "artifact_build_command": " ".join(self.build_command),
            "artifact_build_stdout": self.build_stdout,
            "artifact_build_stderr": self.build_stderr,
            "artifact_version_command": " ".join(self.artifact_version_command),
            "artifact_version_stdout": self.artifact_version_stdout,
            "artifact_version_stderr": self.artifact_version_stderr,
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
            build_command=build_command,
            build_stdout=build_result.stdout,
            build_stderr=build_result.stderr,
            artifact_version_command=artifact_version_command,
            artifact_version_stdout=artifact_version_result.stdout,
            artifact_version_stderr=artifact_version_result.stderr,
            error=f"Built GCSIM artifact version check exited with {artifact_version_result.returncode}.",
        )

    return _result(
        status="artifact_runtime_passed",
        runtime_ready=True,
        artifact_ready=True,
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
        artifact_version_stdout=artifact_version_result.stdout,
        artifact_version_stderr=artifact_version_result.stderr,
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
    build_command=(),
    build_stdout: str = "",
    build_stderr: str = "",
    artifact_version_command=(),
    artifact_version_stdout: str = "",
    artifact_version_stderr: str = "",
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
        build_command=tuple(str(part) for part in build_command),
        build_stdout=_trim_probe_text(build_stdout),
        build_stderr=_trim_probe_text(build_stderr),
        artifact_version_command=tuple(str(part) for part in artifact_version_command),
        artifact_version_stdout=_trim_probe_text(artifact_version_stdout),
        artifact_version_stderr=_trim_probe_text(artifact_version_stderr),
        error=_trim_probe_text(error),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()

