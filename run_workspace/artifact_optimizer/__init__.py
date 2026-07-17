"""Real-account artifact candidate search, isolated from AppShell/UI state."""

from .models import (
    ARTIFACT_POSITIONS,
    OPTIMIZER_REPORT_SCHEMA_VERSION,
    ArtifactBuildCandidate,
    ArtifactOptimizationDiagnostics,
    ArtifactOptimizationReport,
    ArtifactOptimizationRequest,
    ArtifactSetCount,
    ArtifactSetRequirement,
    OptimizerArtifact,
)
from .repository import (
    build_candidate_snapshot,
    connect_artifact_db_readonly,
    load_optimizer_artifacts,
    optimize_artifacts_from_db,
)
from .solver import FinalBuildEvaluator, optimize_artifacts

__all__ = [
    "ARTIFACT_POSITIONS",
    "OPTIMIZER_REPORT_SCHEMA_VERSION",
    "ArtifactBuildCandidate",
    "ArtifactOptimizationDiagnostics",
    "ArtifactOptimizationReport",
    "ArtifactOptimizationRequest",
    "ArtifactSetCount",
    "ArtifactSetRequirement",
    "FinalBuildEvaluator",
    "OptimizerArtifact",
    "build_candidate_snapshot",
    "connect_artifact_db_readonly",
    "load_optimizer_artifacts",
    "optimize_artifacts",
    "optimize_artifacts_from_db",
]
