"""Resolve a future shipped GTT-GCSIM executable artifact.

This backend-only helper defines the reporting contract for a release-bundled
`gtt-gcsim.exe` without adding a binary to the repository. Tests use temporary
files to pin the path/status behavior until the release process provides and
validates a real shipped artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .engine_store import PROJECT_ROOT


DEFAULT_SHIPPED_GCSIM_ARTIFACT_RELATIVE_PATH = (
    Path("run_workspace") / "gcsim" / "shipped" / "gtt-gcsim.exe"
)

STATUS_DISABLED = "disabled"
STATUS_CANDIDATE_MISSING = "candidate_missing"
STATUS_CANDIDATE_READY = "candidate_ready"
STATUS_CANDIDATE_NOT_FILE = "candidate_not_file"
STATUS_CANDIDATE_INVALID_PATH = "candidate_invalid_path"

WARNING_SHIPPED_ARTIFACT_NOT_BUNDLED = "shipped_artifact_not_bundled"
WARNING_SHIPPED_ARTIFACT_NOT_VALIDATED = "shipped_artifact_not_validated"
WARNING_SHIPPED_ARTIFACT_PATH_INVALID = "shipped_artifact_path_invalid"


@dataclass(frozen=True, slots=True)
class GcsimShippedArtifactResolution:
    enabled: bool
    candidate_path: str = ""
    status: str = STATUS_DISABLED
    artifact_path: str = ""
    warnings: tuple[str, ...] = ()
    error: str = ""

    @property
    def ready(self) -> bool:
        return self.status == STATUS_CANDIDATE_READY and bool(self.artifact_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "candidate_path": self.candidate_path,
            "status": self.status,
            "artifact_path": self.artifact_path,
            "warnings": list(self.warnings),
            "error": self.error,
        }


def resolve_shipped_gcsim_artifact(
    *,
    enabled: bool = False,
    candidate_path: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
) -> GcsimShippedArtifactResolution:
    path_result = _resolve_candidate_path(candidate_path, project_root=project_root)
    if isinstance(path_result, str):
        return GcsimShippedArtifactResolution(
            enabled=bool(enabled),
            status=STATUS_CANDIDATE_INVALID_PATH,
            warnings=(WARNING_SHIPPED_ARTIFACT_PATH_INVALID,),
            error=path_result,
        )

    if not enabled:
        return GcsimShippedArtifactResolution(
            enabled=False,
            candidate_path=str(path_result),
            status=STATUS_DISABLED,
        )

    if not path_result.exists():
        return GcsimShippedArtifactResolution(
            enabled=True,
            candidate_path=str(path_result),
            status=STATUS_CANDIDATE_MISSING,
            warnings=(WARNING_SHIPPED_ARTIFACT_NOT_BUNDLED,),
            error=f"Shipped GCSIM artifact candidate is missing: {path_result}",
        )
    if not path_result.is_file():
        return GcsimShippedArtifactResolution(
            enabled=True,
            candidate_path=str(path_result),
            status=STATUS_CANDIDATE_NOT_FILE,
            error=f"Shipped GCSIM artifact candidate is not a file: {path_result}",
        )

    return GcsimShippedArtifactResolution(
        enabled=True,
        candidate_path=str(path_result),
        status=STATUS_CANDIDATE_READY,
        artifact_path=str(path_result),
        warnings=(WARNING_SHIPPED_ARTIFACT_NOT_VALIDATED,),
    )


def _resolve_candidate_path(
    candidate_path: str | Path | None,
    *,
    project_root: str | Path,
) -> Path | str:
    if candidate_path is None:
        raw = DEFAULT_SHIPPED_GCSIM_ARTIFACT_RELATIVE_PATH
    else:
        if str(candidate_path).strip() == "":
            return "Shipped GCSIM artifact candidate path is empty."
        raw = Path(candidate_path)
    path = Path(raw)
    if not path.is_absolute() and ".." in path.parts:
        return f"Shipped GCSIM artifact candidate must not contain '..': {path}"
    if path.is_absolute():
        return path.resolve()
    return (Path(project_root) / path).resolve()
