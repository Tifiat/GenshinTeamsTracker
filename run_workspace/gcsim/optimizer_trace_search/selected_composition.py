"""Isolated complete-assignment boundary for support-aware FAST scoring.

This module deliberately does not generate or prune artifact combinations.  A
replaceable strategy supplies complete physical assignments; this boundary
validates Selected fixed-4p legality, materializes absolute artifact stats and
scores them with the cached support-aware FAST objective.  It owns no UI,
engine execution, account mutation, finalist policy or product authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import islice
from typing import Iterable

from ..optimizer_artifact_database import GcsimOptimizerArtifactDatabaseInput
from ..optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from ..optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerArtifactAssignment,
)
from ..optimizer_trace_selected_candidates import SelectedEquippedTeamSnapshot
from ..trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    SupportAwareFastObjective,
    SupportAwareFastScore,
    SupportProjectionCache,
    TraceContractError,
    build_support_projection_cache,
    canonical_sha256,
    evaluate_support_aware_fast_objective,
)


SELECTED_COMPOSITION_KIND = "gtt.optimizer_trace_search.selected_composition_v1"
SELECTED_COMPOSITION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SelectedCompleteAssignment:
    snapshot_sha256: str
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...]
    physical_assignment_sha256: str
    is_incumbent: bool
    engine_call_count: int = 0
    schema_version: int = SELECTED_COMPOSITION_SCHEMA_VERSION
    kind: str = SELECTED_COMPOSITION_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_COMPOSITION_SCHEMA_VERSION:
            raise TraceContractError("selected composition schema mismatch")
        if self.kind != SELECTED_COMPOSITION_KIND:
            raise TraceContractError("selected composition kind mismatch")
        _sha256(self.snapshot_sha256, "snapshot_sha256")
        _sha256(self.physical_assignment_sha256, "physical_assignment_sha256")
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != 4
            or any(
                not isinstance(row, GcsimOptimizerWearerArtifactAssignment)
                for row in self.assignments
            )
        ):
            raise TraceContractError(
                "selected composition requires four typed assignments"
            )
        if not isinstance(self.is_incumbent, bool):
            raise TraceContractError("selected composition incumbent flag is invalid")
        if self.engine_call_count != 0:
            raise TraceContractError("selected composition cannot call the engine")

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(
            artifact_id
            for assignment in self.assignments
            for artifact_id in assignment.artifact_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "snapshot_sha256": self.snapshot_sha256,
            "assignments": [row.to_dict() for row in self.assignments],
            "physical_assignment_sha256": self.physical_assignment_sha256,
            "is_incumbent": self.is_incumbent,
            "engine_call_count": 0,
        }


@dataclass(frozen=True, slots=True)
class SelectedCompleteAssignmentScore:
    candidate: SelectedCompleteAssignment
    artifact_vector_sha256: str
    score: SupportAwareFastScore

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, SelectedCompleteAssignment):
            raise TraceContractError("selected composition candidate is invalid")
        _sha256(self.artifact_vector_sha256, "artifact_vector_sha256")
        if not isinstance(self.score, SupportAwareFastScore):
            raise TraceContractError("selected composition score is invalid")
        if self.score.artifact_vector_sha256 != self.artifact_vector_sha256:
            raise TraceContractError("selected composition vector identity mismatch")
        if self.score.engine_call_count != 0:
            raise TraceContractError("selected composition score called the engine")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.to_dict(),
            "artifact_vector_sha256": self.artifact_vector_sha256,
            "candidate_damage": self.score.candidate_damage,
            "candidate_dps": self.score.candidate_dps,
            "expected_delta": self.score.expected_delta,
            "support_correction_damage": self.score.support_correction_damage,
            "support_changed_hit_count": self.score.support_changed_hit_count,
            "support_cache_hit": self.score.support_cache_hit,
            "uncertainty_codes": list(self.score.uncertainty_codes),
            "frozen_baseline_damage": self.score.frozen_baseline_damage,
            "frozen_baseline_share": self.score.frozen_baseline_share,
            "engine_call_count": 0,
            "authoritative": False,
            "prune_authority": False,
        }


@dataclass(frozen=True, slots=True)
class SelectedCompositionScoreBatch:
    objective_sha256: str
    snapshot_sha256: str
    scores: tuple[SelectedCompleteAssignmentScore, ...]
    incumbent_physical_assignment_sha256: str
    support_cache_entries: int
    support_cache_hits: int
    support_cache_misses: int
    engine_call_count: int = 0
    authoritative: bool = False
    prune_authority: bool = False

    def __post_init__(self) -> None:
        _sha256(self.objective_sha256, "objective_sha256")
        _sha256(self.snapshot_sha256, "snapshot_sha256")
        _sha256(
            self.incumbent_physical_assignment_sha256,
            "incumbent_physical_assignment_sha256",
        )
        if not self.scores:
            raise TraceContractError("selected composition score batch is empty")
        if any(
            not isinstance(row, SelectedCompleteAssignmentScore)
            for row in self.scores
        ):
            raise TraceContractError("selected composition score rows are invalid")
        identities = tuple(
            row.candidate.physical_assignment_sha256 for row in self.scores
        )
        if len(identities) != len(set(identities)):
            raise TraceContractError("selected composition score rows are duplicated")
        if self.incumbent_physical_assignment_sha256 not in identities:
            raise TraceContractError("selected composition batch lost the incumbent")
        if any(value < 0 for value in (
            self.support_cache_entries,
            self.support_cache_hits,
            self.support_cache_misses,
        )):
            raise TraceContractError("selected composition cache counters are invalid")
        if self.engine_call_count != 0 or self.authoritative or self.prune_authority:
            raise TraceContractError("selected composition batch gained product authority")

    @property
    def leader(self) -> SelectedCompleteAssignmentScore:
        return self.scores[0]


@dataclass(slots=True)
class SelectedCompositionScoringSession:
    artifact_database: GcsimOptimizerArtifactDatabaseInput
    snapshot: SelectedEquippedTeamSnapshot
    objective: SupportAwareFastObjective
    support_cache: SupportProjectionCache
    artifact_stat_cache: dict[
        tuple[str, int], tuple[tuple[str, Decimal], ...]
    ] = field(default_factory=dict)
    assignment_vector_cache: dict[tuple[int, ...], ArtifactStatVector] = field(
        default_factory=dict
    )
    assignment_vector_cache_limit: int = 4096
    assignment_vector_cache_evictions: int = 0


def build_selected_complete_assignment(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    *,
    snapshot: SelectedEquippedTeamSnapshot,
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...],
) -> SelectedCompleteAssignment:
    """Validate one complete physical Selected assignment fail-closed."""

    _validate_context(artifact_database, snapshot)
    _validate_assignments(artifact_database, snapshot, assignments)
    identity = _physical_assignment_sha256(snapshot, assignments)
    incumbent = tuple(row.assignment for row in snapshot.wearers)
    return SelectedCompleteAssignment(
        snapshot_sha256=snapshot.snapshot_sha256,
        assignments=assignments,
        physical_assignment_sha256=identity,
        is_incumbent=assignments == incumbent,
    )


def compile_selected_composition_scoring_session(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    *,
    snapshot: SelectedEquippedTeamSnapshot,
    objective: SupportAwareFastObjective,
    cache_entry_limit: int = 4096,
) -> SelectedCompositionScoringSession:
    """Bind one attempt-local database/snapshot/objective/cache identity."""

    _validate_context(artifact_database, snapshot)
    if not isinstance(objective, SupportAwareFastObjective):
        raise TraceContractError("selected composition objective is invalid")
    if objective.control.standard.character_keys != snapshot.character_keys:
        raise TraceContractError("selected composition objective/team mismatch")
    if (
        isinstance(cache_entry_limit, bool)
        or not isinstance(cache_entry_limit, int)
        or cache_entry_limit <= 0
    ):
        raise TraceContractError("selected composition cache limit is invalid")
    return SelectedCompositionScoringSession(
        artifact_database=artifact_database,
        snapshot=snapshot,
        objective=objective,
        support_cache=build_support_projection_cache(
            objective,
            max_entries=cache_entry_limit,
        ),
        assignment_vector_cache_limit=cache_entry_limit,
    )


def score_selected_complete_assignment(
    session: SelectedCompositionScoringSession,
    candidate: SelectedCompleteAssignment,
) -> SelectedCompleteAssignmentScore:
    if not isinstance(session, SelectedCompositionScoringSession):
        raise TraceContractError("selected composition session is invalid")
    if not isinstance(candidate, SelectedCompleteAssignment):
        raise TraceContractError("selected composition candidate is invalid")
    if candidate.snapshot_sha256 != session.snapshot.snapshot_sha256:
        raise TraceContractError("selected composition candidate snapshot mismatch")
    _validate_assignments(
        session.artifact_database,
        session.snapshot,
        candidate.assignments,
    )
    expected_identity = _physical_assignment_sha256(
        session.snapshot,
        candidate.assignments,
    )
    if candidate.physical_assignment_sha256 != expected_identity:
        raise TraceContractError("selected composition physical identity mismatch")
    incumbent_assignments = tuple(
        row.assignment for row in session.snapshot.wearers
    )
    if candidate.is_incumbent != (candidate.assignments == incumbent_assignments):
        raise TraceContractError("selected composition incumbent identity mismatch")
    vector = _artifact_vector(session, candidate.assignments)
    score = evaluate_support_aware_fast_objective(
        session.objective,
        vector,
        cache=session.support_cache,
    )
    return SelectedCompleteAssignmentScore(
        candidate=candidate,
        artifact_vector_sha256=vector.vector_sha256,
        score=score,
    )


def score_selected_complete_assignments(
    session: SelectedCompositionScoringSession,
    candidates: Iterable[SelectedCompleteAssignment],
    *,
    candidate_limit: int,
) -> SelectedCompositionScoreBatch:
    """Score a bounded supplied complete-assignment corpus, preserving incumbent."""

    if (
        isinstance(candidate_limit, bool)
        or not isinstance(candidate_limit, int)
        or candidate_limit <= 0
    ):
        raise TraceContractError("selected composition candidate_limit is invalid")
    try:
        rows = tuple(islice(iter(candidates), candidate_limit + 1))
    except TypeError as error:
        raise TraceContractError(
            "selected composition candidates are not iterable"
        ) from error
    if not rows:
        raise TraceContractError("selected composition candidates are empty")
    if len(rows) > candidate_limit:
        raise TraceContractError("selected composition candidate limit exceeded")
    identities = tuple(row.physical_assignment_sha256 for row in rows)
    if len(identities) != len(set(identities)):
        raise TraceContractError("selected composition candidates are duplicated")
    incumbents = tuple(row for row in rows if row.is_incumbent)
    if len(incumbents) != 1:
        raise TraceContractError(
            "selected composition batch requires exactly one incumbent"
        )
    scored = tuple(score_selected_complete_assignment(session, row) for row in rows)
    ordered = tuple(
        sorted(
            scored,
            key=lambda row: (
                -row.score.candidate_damage,
                row.candidate.physical_assignment_sha256,
            ),
        )
    )
    return SelectedCompositionScoreBatch(
        objective_sha256=session.objective.objective_sha256,
        snapshot_sha256=session.snapshot.snapshot_sha256,
        scores=ordered,
        incumbent_physical_assignment_sha256=(
            incumbents[0].physical_assignment_sha256
        ),
        support_cache_entries=len(session.support_cache.entries),
        support_cache_hits=session.support_cache.hit_count,
        support_cache_misses=session.support_cache.miss_count,
    )


def _artifact_vector(
    session: SelectedCompositionScoringSession,
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...],
) -> ArtifactStatVector:
    cache_key = tuple(
        artifact_id
        for assignment in assignments
        for artifact_id in assignment.artifact_ids
    )
    cached = session.assignment_vector_cache.get(cache_key)
    if cached is not None:
        return cached
    totals: dict[tuple[str, str], Decimal] = {}
    for assignment in assignments:
        actor = assignment.wearer.gcsim_character_key
        for artifact_id in assignment.artifact_ids:
            artifact_key = (actor, artifact_id)
            stats = session.artifact_stat_cache.get(artifact_key)
            if stats is None:
                artifact = session.artifact_database.artifact_by_id(artifact_id)
                if artifact is None:
                    raise TraceContractError(
                        f"selected composition artifact {artifact_id} is missing"
                    )
                materialized = materialize_gcsim_optimizer_artifact_stat_vector(
                    artifact,
                    wearer=assignment.wearer,
                )
                if not materialized.ready or materialized.stat_vector is None:
                    raise TraceContractError(
                        f"selected composition artifact {artifact_id} did not materialize"
                    )
                stats = tuple(
                    (stat_key, Decimal(value))
                    for stat_key, value in materialized.stat_vector.normalized_stats
                )
                session.artifact_stat_cache[artifact_key] = stats
            for stat_key, value in stats:
                coordinate = (actor, stat_key)
                totals[coordinate] = totals.get(coordinate, Decimal(0)) + value
    vector = ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, float(value))
            for (actor, stat), value in totals.items()
            if value > 0
        )
    )
    if len(session.assignment_vector_cache) >= session.assignment_vector_cache_limit:
        oldest_key = next(iter(session.assignment_vector_cache))
        del session.assignment_vector_cache[oldest_key]
        session.assignment_vector_cache_evictions += 1
    session.assignment_vector_cache[cache_key] = vector
    return vector


def _validate_context(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    snapshot: SelectedEquippedTeamSnapshot,
) -> None:
    if not isinstance(artifact_database, GcsimOptimizerArtifactDatabaseInput):
        raise TraceContractError("selected composition database is invalid")
    if not isinstance(snapshot, SelectedEquippedTeamSnapshot):
        raise TraceContractError("selected composition snapshot is invalid")
    if snapshot.artifact_database_input_sha256 != (
        artifact_database.artifact_database_input_sha256
    ):
        raise TraceContractError("selected composition database identity mismatch")


def _validate_assignments(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    snapshot: SelectedEquippedTeamSnapshot,
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...],
) -> None:
    if (
        not isinstance(assignments, tuple)
        or len(assignments) != 4
        or any(
            not isinstance(row, GcsimOptimizerWearerArtifactAssignment)
            for row in assignments
        )
    ):
        raise TraceContractError(
            "selected composition requires four complete assignments"
        )
    expected_wearers = tuple(row.wearer for row in snapshot.wearers)
    if tuple(row.wearer for row in assignments) != expected_wearers:
        raise TraceContractError("selected composition wearer order mismatch")
    artifact_ids = tuple(
        artifact_id
        for assignment in assignments
        for artifact_id in assignment.artifact_ids
    )
    if len(artifact_ids) != 20 or len(set(artifact_ids)) != 20:
        raise TraceContractError(
            "selected composition requires twenty globally unique artifacts"
        )
    for selected, assignment in zip(snapshot.wearers, assignments, strict=True):
        counts: Counter[str] = Counter()
        for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            artifact_id = assignment.artifact_ids_by_slot[slot]
            artifact = artifact_database.artifact_by_id(artifact_id)
            if artifact is None:
                raise TraceContractError(
                    f"selected composition artifact {artifact_id} is missing"
                )
            if not artifact.default_eligible:
                raise TraceContractError(
                    f"selected composition artifact {artifact_id} is ineligible"
                )
            if artifact.position_key != slot:
                raise TraceContractError(
                    f"selected composition artifact {artifact_id} slot mismatch"
                )
            counts[artifact.set_uid] += 1
        if counts[selected.target_set_uid] < 4:
            raise TraceContractError(
                "selected composition does not preserve the selected 4p set"
            )


def _sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TraceContractError(f"{field_name} must be lowercase SHA-256")


def _physical_assignment_sha256(
    snapshot: SelectedEquippedTeamSnapshot,
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...],
) -> str:
    return canonical_sha256(
        {
            "kind": SELECTED_COMPOSITION_KIND,
            "schema_version": SELECTED_COMPOSITION_SCHEMA_VERSION,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "assignments": [row.to_dict() for row in assignments],
        }
    )


__all__ = [
    "SELECTED_COMPOSITION_KIND",
    "SELECTED_COMPOSITION_SCHEMA_VERSION",
    "SelectedCompleteAssignment",
    "SelectedCompleteAssignmentScore",
    "SelectedCompositionScoreBatch",
    "SelectedCompositionScoringSession",
    "build_selected_complete_assignment",
    "compile_selected_composition_scoring_session",
    "score_selected_complete_assignment",
    "score_selected_complete_assignments",
]
