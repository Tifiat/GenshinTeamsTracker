"""Backend foundation for future GTT-managed GCSIM engine lifecycle."""

from .artifact_build import GcsimBuildArtifactResult, build_gcsim_artifact
from .artifact_runner import (
    GcsimArtifactRunResult,
    GcsimResultSummary,
    parse_gcsim_result_payload,
    run_active_gcsim_artifact,
)
from .engine_store import (
    GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION,
    GcsimEngineInstallation,
    GcsimEngineManifest,
    GcsimEngineStore,
    GcsimEngineUpdateResult,
    GcsimPatchResult,
    OverlayPatchBackend,
    PatchBackend,
)
from .runtime_probe import GcsimRuntimeProbeResult, run_gcsim_runtime_probe
from .patch_backends import GitApplyPatchBackend

__all__ = [
    "GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION",
    "GcsimArtifactRunResult",
    "GcsimBuildArtifactResult",
    "GcsimEngineInstallation",
    "GcsimEngineManifest",
    "GcsimEngineStore",
    "GcsimEngineUpdateResult",
    "GcsimPatchResult",
    "GcsimResultSummary",
    "OverlayPatchBackend",
    "PatchBackend",
    "GitApplyPatchBackend",
    "GcsimRuntimeProbeResult",
    "parse_gcsim_result_payload",
    "run_active_gcsim_artifact",
    "run_gcsim_runtime_probe",
    "build_gcsim_artifact",
]
