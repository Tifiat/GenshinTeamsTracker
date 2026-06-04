"""Optional Go runtime probe for a prepared GCSIM source tree.

This probe is deliberately separate from source acquisition and the engine
store. It checks the local Go toolchain, keeps Go caches inside the project
when invoked through this module, and runs a minimal GCSIM command from the
patched source tree. Unit tests use a fake subprocess runner, so no test
requires real Go.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping, Sequence

from .engine_store import PROJECT_ROOT


DEFAULT_GO_WORK_DIR = PROJECT_ROOT / ".go"
DEFAULT_GO_PROBE_TIMEOUT_SECONDS = 300
EXPECTED_GO_OS = "windows"
EXPECTED_GO_ARCH = "amd64"
MAX_PROBE_TEXT_CHARS = 1200

GoRunner = Callable[
    [Sequence[str], Path | None, Mapping[str, str], int],
    subprocess.CompletedProcess[str],
]


@dataclass(frozen=True, slots=True)
class GcsimRuntimeProbeResult:
    status: str
    runtime_ready: bool
    go_available: bool
    go_version: str = ""
    go_os: str = ""
    go_arch: str = ""
    go_env_root: str = ""
    command: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
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
            "runtime_probe_command": " ".join(self.command),
            "runtime_probe_stdout": self.stdout,
            "runtime_probe_stderr": self.stderr,
            "runtime_probe_error": self.error,
        }


def run_gcsim_runtime_probe(
    engine_dir: str | Path,
    *,
    go_executable: str = "go",
    go_work_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    runner: GoRunner | None = None,
    expected_go_os: str = EXPECTED_GO_OS,
    expected_go_arch: str = EXPECTED_GO_ARCH,
) -> GcsimRuntimeProbeResult:
    engine_dir = Path(engine_dir)
    go_root = Path(go_work_dir) if go_work_dir is not None else DEFAULT_GO_WORK_DIR
    env = _go_sandbox_env(go_root)
    command_runner = runner or _subprocess_runner

    version_command = (go_executable, "version")
    try:
        version_result = command_runner(
            version_command,
            None,
            env,
            int(timeout_seconds),
        )
    except FileNotFoundError as exc:
        return _probe_result(
            status="go_missing",
            runtime_ready=False,
            go_available=False,
            go_env_root=go_root,
            command=version_command,
            error=f"Go executable not found: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        return _probe_result(
            status="go_version_timeout",
            runtime_ready=False,
            go_available=False,
            go_env_root=go_root,
            command=version_command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="go version timed out",
        )
    except OSError as exc:
        return _probe_result(
            status="go_version_failed",
            runtime_ready=False,
            go_available=False,
            go_env_root=go_root,
            command=version_command,
            error=str(exc),
        )

    parsed = _parse_go_version(version_result.stdout.strip())
    if version_result.returncode != 0 or parsed is None:
        return _probe_result(
            status="go_version_failed",
            runtime_ready=False,
            go_available=False,
            go_env_root=go_root,
            command=version_command,
            stdout=version_result.stdout,
            stderr=version_result.stderr,
            error=(
                f"go version exited with {version_result.returncode}"
                if version_result.returncode != 0
                else "Could not parse go version output."
            ),
        )
    go_version, go_os, go_arch = parsed
    if go_os != expected_go_os or go_arch != expected_go_arch:
        return _probe_result(
            status="go_wrong_arch",
            runtime_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            command=version_command,
            stdout=version_result.stdout,
            stderr=version_result.stderr,
            error=f"Expected Go target {expected_go_os}/{expected_go_arch}, got {go_os}/{go_arch}.",
        )

    probe_command = (go_executable, "run", "./cmd/gcsim", "-version")
    try:
        probe_result = command_runner(
            probe_command,
            engine_dir,
            env,
            int(timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        return _probe_result(
            status="runtime_probe_timeout",
            runtime_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            command=probe_command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            error="GCSIM runtime probe timed out.",
        )
    except OSError as exc:
        return _probe_result(
            status="runtime_probe_failed",
            runtime_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            command=probe_command,
            error=str(exc),
        )
    if probe_result.returncode != 0:
        return _probe_result(
            status="runtime_probe_failed",
            runtime_ready=False,
            go_available=True,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
            go_env_root=go_root,
            command=probe_command,
            stdout=probe_result.stdout,
            stderr=probe_result.stderr,
            error=f"GCSIM runtime probe exited with {probe_result.returncode}.",
        )
    return _probe_result(
        status="runtime_probe_passed",
        runtime_ready=True,
        go_available=True,
        go_version=go_version,
        go_os=go_os,
        go_arch=go_arch,
        go_env_root=go_root,
        command=probe_command,
        stdout=probe_result.stdout,
        stderr=probe_result.stderr,
    )


def _subprocess_runner(
    command: Sequence[str],
    cwd: Path | None,
    env: Mapping[str, str],
    timeout_seconds: int,
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


def _go_sandbox_env(go_root: Path) -> dict[str, str]:
    go_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["GOMODCACHE"] = str(go_root / "pkg" / "mod")
    env["GOCACHE"] = str(go_root / "build-cache")
    env["GOBIN"] = str(go_root / "bin")
    for key in ("GOMODCACHE", "GOCACHE", "GOBIN"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def _parse_go_version(text: str) -> tuple[str, str, str] | None:
    match = re.search(r"go version\s+(\S+)\s+([^/\s]+)/([^\s]+)", text)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def _probe_result(
    *,
    status: str,
    runtime_ready: bool,
    go_available: bool,
    go_env_root: Path,
    command: Sequence[str],
    go_version: str = "",
    go_os: str = "",
    go_arch: str = "",
    stdout: str = "",
    stderr: str = "",
    error: str = "",
) -> GcsimRuntimeProbeResult:
    return GcsimRuntimeProbeResult(
        status=status,
        runtime_ready=runtime_ready,
        go_available=go_available,
        go_version=go_version,
        go_os=go_os,
        go_arch=go_arch,
        go_env_root=str(go_env_root),
        command=tuple(str(part) for part in command),
        stdout=_trim_probe_text(stdout),
        stderr=_trim_probe_text(stderr),
        error=_trim_probe_text(error),
    )


def _trim_probe_text(text: str) -> str:
    clean = str(text or "").strip()
    if len(clean) <= MAX_PROBE_TEXT_CHARS:
        return clean
    return clean[:MAX_PROBE_TEXT_CHARS] + "...[truncated]"
