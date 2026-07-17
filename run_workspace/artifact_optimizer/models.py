from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ARTIFACT_POSITIONS = (1, 2, 3, 4, 5)
OPTIMIZER_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class OptimizerArtifact:
    artifact_id: int
    pos: int
    set_key: str
    set_uid: str = ""
    set_name: str = ""
    name: str = ""
    rarity: int | None = None
    level: int | None = None
    main_property_type: int | None = None
    stats: tuple[tuple[int, float], ...] = ()
    equipped_character_ids: tuple[int, ...] = ()

    def stat_value(self, property_type: int) -> float:
        property_type = int(property_type)
        return next(
            (
                float(value)
                for current_type, value in self.stats
                if current_type == property_type
            ),
            0.0,
        )

    def stats_dict(self) -> dict[int, float]:
        return {
            int(property_type): float(value)
            for property_type, value in self.stats
        }


@dataclass(frozen=True, slots=True)
class ArtifactSetRequirement:
    set_key: str
    minimum_count: int

    def __post_init__(self) -> None:
        if not str(self.set_key).strip():
            raise ValueError("Artifact set requirement needs a non-empty set_key")
        if not 1 <= int(self.minimum_count) <= len(ARTIFACT_POSITIONS):
            raise ValueError("Artifact set minimum_count must be between 1 and 5")


@dataclass(frozen=True, slots=True)
class ArtifactOptimizationRequest:
    weights: Mapping[int, float]
    top_k: int = 10
    minimum_stats: Mapping[int, float] = field(default_factory=dict)
    set_requirements: tuple[ArtifactSetRequirement, ...] = ()
    fixed_artifact_ids_by_pos: Mapping[int, int] = field(default_factory=dict)
    excluded_artifact_ids: frozenset[int] = frozenset()
    allowed_main_stats_by_pos: Mapping[int, frozenset[int]] = field(
        default_factory=dict
    )
    minimum_rarity: int | None = None
    minimum_level: int | None = None
    allow_equipped_artifacts: bool = True
    target_character_id: int | None = None
    per_slot_limit: int | None = 32
    per_set_limit: int | None = 8
    max_combinations: int | None = 2_000_000
    rerank_pool_size: int | None = None

    def __post_init__(self) -> None:
        if int(self.top_k) < 1:
            raise ValueError("top_k must be at least 1")
        for name in ("per_slot_limit", "per_set_limit", "max_combinations"):
            value = getattr(self, name)
            if value is not None and int(value) < 1:
                raise ValueError(f"{name} must be at least 1 or None")
        if self.rerank_pool_size is not None:
            if int(self.rerank_pool_size) < int(self.top_k):
                raise ValueError("rerank_pool_size cannot be smaller than top_k")


@dataclass(frozen=True, slots=True)
class ArtifactSetCount:
    set_key: str
    set_uid: str
    set_name: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_key": self.set_key,
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class ArtifactBuildCandidate:
    artifact_ids_by_pos: tuple[tuple[int, int], ...]
    stat_totals: tuple[tuple[int, float], ...]
    set_counts: tuple[ArtifactSetCount, ...]
    score: float
    proxy_score: float

    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(
            artifact_id
            for _, artifact_id in sorted(self.artifact_ids_by_pos)
        )

    def artifact_id_map(self) -> dict[int, int]:
        return dict(self.artifact_ids_by_pos)

    def stat_total_map(self) -> dict[int, float]:
        return dict(self.stat_totals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_ids_by_pos": {
                str(pos): artifact_id
                for pos, artifact_id in self.artifact_ids_by_pos
            },
            "stat_totals": {
                str(property_type): value
                for property_type, value in self.stat_totals
            },
            "set_counts": [item.to_dict() for item in self.set_counts],
            "score": round(float(self.score), 9),
            "proxy_score": round(float(self.proxy_score), 9),
        }


@dataclass(frozen=True, slots=True)
class ArtifactOptimizationDiagnostics:
    input_artifact_count: int
    filtered_artifact_count: int
    candidate_counts_before_shortlist: tuple[tuple[int, int], ...]
    candidate_counts_after_shortlist: tuple[tuple[int, int], ...]
    estimated_combinations_before_shortlist: int
    estimated_combinations_after_shortlist: int
    complete_builds_considered: int
    feasible_builds_evaluated: int
    reranked_builds: int
    upper_bound_pruned_branches: int
    minimum_stat_pruned_branches: int
    set_requirement_pruned_branches: int
    duplicate_artifact_pruned_branches: int
    candidate_pool_truncated: bool
    stopped_by_combination_limit: bool
    search_complete: bool
    quality: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_artifact_count": self.input_artifact_count,
            "filtered_artifact_count": self.filtered_artifact_count,
            "candidate_counts_before_shortlist": dict(
                self.candidate_counts_before_shortlist
            ),
            "candidate_counts_after_shortlist": dict(
                self.candidate_counts_after_shortlist
            ),
            "estimated_combinations_before_shortlist": (
                self.estimated_combinations_before_shortlist
            ),
            "estimated_combinations_after_shortlist": (
                self.estimated_combinations_after_shortlist
            ),
            "complete_builds_considered": self.complete_builds_considered,
            "feasible_builds_evaluated": self.feasible_builds_evaluated,
            "reranked_builds": self.reranked_builds,
            "upper_bound_pruned_branches": self.upper_bound_pruned_branches,
            "minimum_stat_pruned_branches": self.minimum_stat_pruned_branches,
            "set_requirement_pruned_branches": (
                self.set_requirement_pruned_branches
            ),
            "duplicate_artifact_pruned_branches": (
                self.duplicate_artifact_pruned_branches
            ),
            "candidate_pool_truncated": self.candidate_pool_truncated,
            "stopped_by_combination_limit": self.stopped_by_combination_limit,
            "search_complete": self.search_complete,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class ArtifactOptimizationReport:
    candidates: tuple[ArtifactBuildCandidate, ...]
    diagnostics: ArtifactOptimizationDiagnostics
    schema_version: int = OPTIMIZER_REPORT_SCHEMA_VERSION
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "diagnostics": self.diagnostics.to_dict(),
            "warnings": list(self.warnings),
        }
