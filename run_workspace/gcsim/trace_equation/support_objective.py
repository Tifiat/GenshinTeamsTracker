"""Isolated formula control that includes replayed support-state dependencies.

This is deliberately a STANDARD-granularity development control.  It proves
that an artifact delta on one actor can travel through the observed support
state and change the formula inputs of another actor's exact hit rows.  It is
not the product FAST implementation and never grants pruning authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .artifact_variable_objective import (
    ArtifactStatVector,
    artifact_replacements_between,
)
from .contracts import TraceContractError, canonical_sha256
from .rotation_objective import (
    CompactRotationObjective,
    CompactTermKind,
    compile_rotation_objective,
)
from .state_evidence import StateEvidenceTrace
from .support_replay import (
    SupportReplayPlan,
    compile_support_replay_plan,
    evaluate_support_plan_sliced,
    project_support_evaluation_plan_to_hits,
    project_support_replay_plan_to_hits,
    replay_support_plan,
)


SUPPORT_AWARE_CONTROL_OBJECTIVE_KIND = (
    "gtt.trace_equation.support_aware_artifact_control"
)
SUPPORT_AWARE_CONTROL_OBJECTIVE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SupportAwareControlObjective:
    objective_sha256: str
    trace: StateEvidenceTrace
    replay_plan: SupportReplayPlan
    standard: CompactRotationObjective
    incumbent_artifact_vector: ArtifactStatVector
    character_keys: tuple[str, ...]
    duration_frames: int | None
    baseline_damage: float
    schema_version: int = SUPPORT_AWARE_CONTROL_OBJECTIVE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class SupportAwareControlScore:
    objective_sha256: str
    artifact_vector_sha256: str
    baseline_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    support_changed_hit_count: int
    support_replayed_event_count: int
    fallback_group_count: int
    fallback_hit_count: int
    uncertainty_codes: tuple[str, ...]
    engine_call_count: int = 0
    authoritative: bool = False
    hard_prune_allowed: bool = False


def compile_support_aware_control_objective(
    trace: StateEvidenceTrace,
    incumbent_artifact_vector: ArtifactStatVector,
) -> SupportAwareControlObjective:
    if not isinstance(trace, StateEvidenceTrace):
        raise TraceContractError("support-aware control requires StateEvidenceTrace")
    if not isinstance(incumbent_artifact_vector, ArtifactStatVector):
        raise TraceContractError("incumbent artifact vector is invalid")
    _validate_vector_actors(trace.terminal_trace.request.character_keys, incumbent_artifact_vector)
    standard = compile_rotation_objective(trace)
    replay_plan = compile_support_replay_plan(
        trace,
        evidence_sha256=standard.evidence_sha256,
    )
    identity = canonical_sha256(
        {
            "kind": SUPPORT_AWARE_CONTROL_OBJECTIVE_KIND,
            "schema_version": SUPPORT_AWARE_CONTROL_OBJECTIVE_SCHEMA_VERSION,
            "evidence_sha256": trace.evidence_sha256,
            "standard_objective_sha256": standard.objective_sha256,
            "incumbent_artifact_vector_sha256": (
                incumbent_artifact_vector.vector_sha256
            ),
        }
    )
    return SupportAwareControlObjective(
        objective_sha256=identity,
        trace=trace,
        replay_plan=replay_plan,
        standard=standard,
        incumbent_artifact_vector=incumbent_artifact_vector,
        character_keys=standard.character_keys,
        duration_frames=standard.duration_frames,
        baseline_damage=standard.baseline_damage,
    )


def evaluate_support_aware_control_objective(
    objective: SupportAwareControlObjective,
    candidate_artifact_vector: ArtifactStatVector,
) -> SupportAwareControlScore:
    """Evaluate through the full ledger correctness oracle."""

    return _evaluate_support_aware_control_objective(
        objective,
        candidate_artifact_vector,
        sliced=False,
    )


def evaluate_support_aware_sliced_control_objective(
    objective: SupportAwareControlObjective,
    candidate_artifact_vector: ArtifactStatVector,
) -> SupportAwareControlScore:
    """Evaluate the stat-reachable ledger slice for full-control parity tests."""

    return _evaluate_support_aware_control_objective(
        objective,
        candidate_artifact_vector,
        sliced=True,
    )


def _evaluate_support_aware_control_objective(
    objective: SupportAwareControlObjective,
    candidate_artifact_vector: ArtifactStatVector,
    *,
    sliced: bool,
) -> SupportAwareControlScore:
    if not isinstance(objective, SupportAwareControlObjective):
        raise TraceContractError("objective must be SupportAwareControlObjective")
    if not isinstance(candidate_artifact_vector, ArtifactStatVector):
        raise TraceContractError("candidate artifact vector is invalid")
    _validate_vector_actors(objective.character_keys, candidate_artifact_vector)

    replacements = artifact_replacements_between(
        objective.incumbent_artifact_vector,
        candidate_artifact_vector,
    )
    direct_deltas = {
        (row.actor_key, row.stat_key): row.delta
        for row in replacements
        if not math.isclose(row.delta, 0.0, rel_tol=1e-12, abs_tol=1e-12)
    }
    if sliced:
        evaluation = evaluate_support_plan_sliced(
            objective.replay_plan,
            direct_deltas,
        )
        projected = project_support_evaluation_plan_to_hits(
            objective.replay_plan,
            evaluation,
        )
        replayed_event_count = evaluation.replayed_event_count
    else:
        replay = replay_support_plan(objective.replay_plan, direct_deltas)
        projected = project_support_replay_plan_to_hits(
            objective.replay_plan,
            replay,
        )
        replayed_event_count = replay.replayed_event_count
    projection_by_event = {
        row.event_id: row for row in projected.projections
    }

    by_actor = {actor: 0.0 for actor in objective.character_keys}
    uncertainties = set(projected.uncertainty_codes)
    fallback_groups = 0
    fallback_hits = 0
    changed_hits = sum(bool(row.stat_deltas) for row in projected.projections)
    total = 0.0
    for group in objective.standard.groups:
        if group.kind is CompactTermKind.FROZEN or group.expression is None:
            contribution = group.baseline_damage
            total += contribution
            by_actor[group.actor_key] += contribution
            fallback_groups += 1
            fallback_hits += group.multiplicity
            for event_id in group.event_ids:
                if projection_by_event[event_id].stat_deltas:
                    uncertainties.add(f"frozen_support_affected_hit:{event_id}")
            continue

        group_total = 0.0
        group_fallback = False
        for event_id in group.event_ids:
            projection = projection_by_event[event_id]
            dynamic_deltas = {
                (projection.actor_key, stat_key): value
                for stat_key, value in projection.stat_deltas
            }
            value, fallback = group.expression.evaluate(
                direct_deltas,
                dynamic_deltas,
            )
            group_total += value
            group_fallback = group_fallback or fallback
            if fallback:
                fallback_hits += 1
                uncertainties.add(f"support_formula_fallback:{event_id}")
        if group_fallback:
            fallback_groups += 1
        total += group_total
        by_actor[group.actor_key] += group_total

    baseline_dps = None
    candidate_dps = None
    if objective.duration_frames is not None:
        baseline_dps = objective.baseline_damage * 60.0 / objective.duration_frames
        candidate_dps = total * 60.0 / objective.duration_frames
    return SupportAwareControlScore(
        objective_sha256=objective.objective_sha256,
        artifact_vector_sha256=candidate_artifact_vector.vector_sha256,
        baseline_damage=objective.baseline_damage,
        candidate_damage=total,
        expected_delta=total - objective.baseline_damage,
        baseline_dps=baseline_dps,
        candidate_dps=candidate_dps,
        candidate_damage_by_actor=tuple(sorted(by_actor.items())),
        support_changed_hit_count=changed_hits,
        support_replayed_event_count=replayed_event_count,
        fallback_group_count=fallback_groups,
        fallback_hit_count=fallback_hits,
        uncertainty_codes=tuple(sorted(uncertainties)),
    )


def _validate_vector_actors(
    character_keys: tuple[str, ...],
    vector: ArtifactStatVector,
) -> None:
    unknown = {
        row.actor_key for row in vector.values
    } - set(character_keys)
    if unknown:
        raise TraceContractError(
            f"unknown artifact-vector actors: {sorted(unknown)!r}"
        )


__all__ = [
    "SUPPORT_AWARE_CONTROL_OBJECTIVE_KIND",
    "SUPPORT_AWARE_CONTROL_OBJECTIVE_SCHEMA_VERSION",
    "SupportAwareControlObjective",
    "SupportAwareControlScore",
    "compile_support_aware_control_objective",
    "evaluate_support_aware_control_objective",
    "evaluate_support_aware_sliced_control_objective",
]
