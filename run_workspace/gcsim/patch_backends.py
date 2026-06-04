"""Patch backends for GTT-managed GCSIM engine preparation.

`GitApplyPatchBackend` is the first production-oriented patch backend. It is
still backend-only and intentionally small: discover ordered `.patch` files,
then run `git apply --check` and `git apply` for each patch in order. Unit tests
inject a fake runner, so tests do not depend on a real git executable.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
from typing import Callable, Mapping, Sequence

from .engine_store import GcsimPatchResult


MAX_PATCH_COMMAND_TEXT_CHARS = 1200
PatchRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


class GitApplyPatchBackend:
    """Apply an ordered `.patch` stack with `git apply`."""

    name = "git"

    def __init__(
        self,
        *,
        git_executable: str = "git",
        runner: PatchRunner | None = None,
    ) -> None:
        self.git_executable = str(git_executable)
        self._runner = runner or _subprocess_runner

    def apply(self, *, engine_dir: Path, patch_stack_dir: Path | None) -> GcsimPatchResult:
        metadata = _base_metadata(
            git_executable=self.git_executable,
            patch_stack_dir=patch_stack_dir,
        )
        if patch_stack_dir is None:
            metadata.update(
                {
                    "patch_check_status": "no_patch_stack",
                    "patch_apply_status": "no_patch_stack",
                    "patch_git_status": "not_checked",
                }
            )
            return GcsimPatchResult.success(
                backend=self.name,
                patch_count=0,
                metadata=metadata,
            )

        patch_stack_dir = Path(patch_stack_dir)
        if not patch_stack_dir.exists():
            metadata.update(
                {
                    "patch_check_status": "patch_stack_missing",
                    "patch_apply_status": "not_started",
                    "patch_git_status": "not_checked",
                }
            )
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"Patch stack does not exist: {patch_stack_dir}",
                metadata=metadata,
            )
        if not patch_stack_dir.is_dir():
            metadata.update(
                {
                    "patch_check_status": "patch_stack_not_directory",
                    "patch_apply_status": "not_started",
                    "patch_git_status": "not_checked",
                }
            )
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"Patch stack is not a directory: {patch_stack_dir}",
                metadata=metadata,
            )

        patch_files = _discover_patch_files(patch_stack_dir)
        metadata.update(_patch_file_metadata(patch_stack_dir, patch_files))
        if not patch_files:
            metadata.update(
                {
                    "patch_check_status": "no_patches",
                    "patch_apply_status": "no_patches",
                    "patch_git_status": "not_checked",
                }
            )
            return GcsimPatchResult.success(
                backend=self.name,
                patch_count=0,
                metadata=metadata,
            )

        applied_count = 0
        for patch_file in patch_files:
            check_command = (
                self.git_executable,
                "apply",
                "--check",
                str(patch_file),
            )
            check_result = self._run_git_command(
                check_command,
                engine_dir,
                metadata,
                patch_count=len(patch_files),
            )
            if isinstance(check_result, GcsimPatchResult):
                return check_result
            if check_result.returncode != 0:
                metadata.update(
                    _command_result_metadata(
                        check_result,
                        patch_check_status="failed",
                        patch_apply_status=_check_failure_apply_status(applied_count),
                        patch_git_status="available",
                    )
                )
                metadata["patch_failed_file"] = str(patch_file)
                return GcsimPatchResult.failure(
                    backend=self.name,
                    error=_command_error_text("patch_check_failed", check_result),
                    patch_count=len(patch_files),
                    metadata=metadata,
                )
            metadata.update(
                _command_result_metadata(
                    check_result,
                    patch_check_status="passed",
                    patch_apply_status="pending",
                    patch_git_status="available",
                )
            )

            apply_command = (
                self.git_executable,
                "apply",
                str(patch_file),
            )
            apply_result = self._run_git_command(
                apply_command,
                engine_dir,
                metadata,
                patch_count=len(patch_files),
            )
            if isinstance(apply_result, GcsimPatchResult):
                return apply_result
            if apply_result.returncode != 0:
                metadata.update(
                    _command_result_metadata(
                        apply_result,
                        patch_check_status="passed",
                        patch_apply_status="failed",
                        patch_git_status="available",
                    )
                )
                metadata["patch_failed_file"] = str(patch_file)
                return GcsimPatchResult.failure(
                    backend=self.name,
                    error=_command_error_text("patch_apply_failed", apply_result),
                    patch_count=len(patch_files),
                    metadata=metadata,
                )
            applied_count += 1
            metadata.update(
                _command_result_metadata(
                    apply_result,
                    patch_check_status="passed",
                    patch_apply_status="passed",
                    patch_git_status="available",
                )
            )

        return GcsimPatchResult.success(
            backend=self.name,
            patch_count=len(patch_files),
            metadata=metadata,
        )

    def _run_git_command(
        self,
        command: Sequence[str],
        engine_dir: Path,
        base_metadata: Mapping[str, str],
        patch_count: int,
    ) -> subprocess.CompletedProcess[str] | GcsimPatchResult:
        try:
            return self._runner(command, engine_dir)
        except FileNotFoundError as exc:
            metadata = dict(base_metadata)
            metadata.update(
                {
                    "patch_check_status": "git_missing",
                    "patch_apply_status": "not_started",
                    "patch_git_status": "missing",
                    "patch_command": " ".join(str(part) for part in command),
                }
            )
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"git_missing: Git executable not found: {exc}",
                patch_count=patch_count,
                metadata=metadata,
            )
        except OSError as exc:
            metadata = dict(base_metadata)
            metadata.update(
                {
                    "patch_check_status": "git_command_failed",
                    "patch_apply_status": "not_started",
                    "patch_git_status": "error",
                    "patch_command": " ".join(str(part) for part in command),
                }
            )
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"git_command_failed: {exc}",
                patch_count=patch_count,
                metadata=metadata,
            )


def _subprocess_runner(
    command: Sequence[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    env = _git_apply_env(cwd)
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _git_apply_env(cwd: Path) -> dict[str, str]:
    """Keep `git apply` from discovering the parent GTT repository.

    Prepared GCSIM trees live under the project's ignored `data/gcsim/...`
    directory. Without a ceiling, Git discovers this repository's `.git` and can
    treat ignored/generated staged-engine paths as skippable patch targets while
    still exiting successfully.
    """

    env = dict(os.environ)
    ceiling = str(Path(cwd).resolve().parent)
    existing = env.get("GIT_CEILING_DIRECTORIES")
    env["GIT_CEILING_DIRECTORIES"] = (
        ceiling if not existing else ceiling + os.pathsep + existing
    )
    return env


def _discover_patch_files(patch_stack_dir: Path) -> list[Path]:
    return sorted(
        (path for path in patch_stack_dir.rglob("*.patch") if path.is_file()),
        key=lambda path: path.relative_to(patch_stack_dir).as_posix(),
    )


def _base_metadata(
    *,
    git_executable: str,
    patch_stack_dir: Path | None,
) -> dict[str, str]:
    return {
        "git_executable": git_executable,
        "patch_stack_path": "" if patch_stack_dir is None else str(patch_stack_dir),
        "patch_files": "[]",
        "patch_check_status": "not_started",
        "patch_apply_status": "not_started",
        "patch_git_status": "not_started",
    }


def _patch_file_metadata(patch_stack_dir: Path, patch_files: Sequence[Path]) -> dict[str, str]:
    relative_files = [
        path.relative_to(patch_stack_dir).as_posix()
        for path in patch_files
    ]
    return {
        "patch_files": json.dumps(relative_files, ensure_ascii=False),
    }


def _command_result_metadata(
    result: subprocess.CompletedProcess[str],
    *,
    patch_check_status: str,
    patch_apply_status: str,
    patch_git_status: str,
) -> dict[str, str]:
    return {
        "patch_check_status": patch_check_status,
        "patch_apply_status": patch_apply_status,
        "patch_git_status": patch_git_status,
        "patch_command": " ".join(str(part) for part in result.args),
        "patch_stdout": _trim_text(result.stdout),
        "patch_stderr": _trim_text(result.stderr),
        "patch_returncode": str(result.returncode),
    }


def _check_failure_apply_status(applied_count: int) -> str:
    if applied_count == 0:
        return "not_started"
    return "partial_before_check_failure"


def _command_error_text(prefix: str, result: subprocess.CompletedProcess[str]) -> str:
    details = _trim_text(result.stderr) or _trim_text(result.stdout)
    if details:
        return f"{prefix}: {details}"
    return f"{prefix}: git apply exited with {result.returncode}"


def _trim_text(text: str | None) -> str:
    clean = str(text or "").strip()
    if len(clean) <= MAX_PATCH_COMMAND_TEXT_CHARS:
        return clean
    return clean[:MAX_PATCH_COMMAND_TEXT_CHARS] + "...[truncated]"
