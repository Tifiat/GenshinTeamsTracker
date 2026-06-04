"""Backend foundation for future GTT-managed GCSIM engine lifecycle."""

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
    "GcsimEngineInstallation",
    "GcsimEngineManifest",
    "GcsimEngineStore",
    "GcsimEngineUpdateResult",
    "GcsimPatchResult",
    "OverlayPatchBackend",
    "PatchBackend",
    "GitApplyPatchBackend",
    "GcsimRuntimeProbeResult",
    "run_gcsim_runtime_probe",
]
