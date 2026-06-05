"""Backend foundation for future GTT-managed GCSIM engine lifecycle."""

from .artifact_build import GcsimBuildArtifactResult, build_gcsim_artifact
from .artifact_runner import (
    GcsimArtifactRunResult,
    GcsimResultSummary,
    parse_gcsim_result_payload,
    run_active_gcsim_artifact,
)
from .abyss_wave_scenario import (
    AbyssEnemyTypeMapping,
    AbyssWaveScenarioAudit,
    AbyssWaveScenarioBuildResult,
    audit_abyss_wave_scenario,
    build_abyss_wave_scenario_payload,
    load_enemy_type_mapping_from_json,
    write_abyss_wave_scenario_payload,
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
    "AbyssEnemyTypeMapping",
    "AbyssWaveScenarioAudit",
    "AbyssWaveScenarioBuildResult",
    "audit_abyss_wave_scenario",
    "build_abyss_wave_scenario_payload",
    "load_enemy_type_mapping_from_json",
    "parse_gcsim_result_payload",
    "run_active_gcsim_artifact",
    "run_gcsim_runtime_probe",
    "write_abyss_wave_scenario_payload",
    "build_gcsim_artifact",
]
