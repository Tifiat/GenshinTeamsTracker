"""Isolated FAST objective with cached exact-hit support corrections.

Direct artifact response stays in the accepted response-equivalent FAST
channels.  The generic support ledger is evaluated only for coordinates that
can reach a consumed hit modifier, cached by that smaller input vector, and
applied as a correction on the exact affected STANDARD hit expressions.  This
module has no product, UI, runner, or pruning authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .artifact_variable_objective import (
    ArtifactStatVector,
    ArtifactVariableObjective,
    artifact_replacements_between,
    compile_artifact_variable_objective,
    evaluate_artifact_variable_objective,
)
from .coarse_rotation_objective import compile_coarse_rotation_objective
from .contracts import TraceContractError, canonical_sha256
from .rotation_objective import CompactTermKind
from .ranking import RANKING_STAT_KEYS
from .state_evidence import StateEvidenceTrace
from .support_objective import (
    SupportAwareControlObjective,
    compile_support_aware_control_objective,
)
from .support_replay import (
    SupportReplayHitProjectionSet,
    evaluate_support_plan_sliced,
    project_support_evaluation_plan_to_hits,
)


SUPPORT_AWARE_FAST_OBJECTIVE_KIND = "gtt.trace_equation.support_aware_fast"
SUPPORT_AWARE_FAST_OBJECTIVE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SupportAwareFastObjective:
    objective_sha256: str
    control: SupportAwareControlObjective
    direct_fast: ArtifactVariableObjective
    support_coordinates: tuple[tuple[str, str], ...]
    schema_version: int = SUPPORT_AWARE_FAST_OBJECTIVE_SCHEMA_VERSION


@dataclass(slots=True)
class SupportProjectionCache:
    objective_sha256: str
    entries: dict[
        tuple[tuple[str, str, float], ...], SupportReplayHitProjectionSet
    ] = field(default_factory=dict)
    max_entries: int = 4096
    hit_count: int = 0
    miss_count: int = 0
    eviction_count: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_entries, bool)
            or not isinstance(self.max_entries, int)
            or self.max_entries <= 0
        ):
            raise TraceContractError("support projection cache limit is invalid")


@dataclass(frozen=True, slots=True)
class SupportAwareFastScore:
    objective_sha256: str
    artifact_vector_sha256: str
    baseline_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    support_correction_damage: float
    support_changed_hit_count: int
    support_cache_hit: bool
    support_cache_entry_count: int
    uncertainty_codes: tuple[str, ...]
    frozen_baseline_damage: float = 0.0
    frozen_baseline_share: float = 0.0
    stochastic_sample_count: int = 1
    stochastic_sample_sd: float = 0.0
    stochastic_standard_error: float = 0.0
    stochastic_mode: str = "single_trace"
    engine_call_count: int = 0
    authoritative: bool = False
    hard_prune_allowed: bool = False


def compile_support_aware_fast_objective(
    trace: StateEvidenceTrace,
    incumbent_artifact_vector: ArtifactStatVector,
) -> SupportAwareFastObjective:
    control = compile_support_aware_control_objective(
        trace,
        incumbent_artifact_vector,
    )
    return compile_support_aware_fast_objective_from_control(control)


def compile_support_aware_fast_objective_from_control(
    control: SupportAwareControlObjective,
) -> SupportAwareFastObjective:
    """Reuse an already-compiled correctness control for FAST compilation."""

    if not isinstance(control, SupportAwareControlObjective):
        raise TraceContractError("support control objective is invalid")
    coarse = compile_coarse_rotation_objective(control.standard)
    direct_fast = compile_artifact_variable_objective(
        coarse,
        control.incumbent_artifact_vector,
    )
    support_coordinates = tuple(
        sorted(
            coordinate
            for coordinate in control.replay_plan.replay_events_by_coordinate
            if coordinate[1] in RANKING_STAT_KEYS
        )
    )
    identity = canonical_sha256(
        {
            "kind": SUPPORT_AWARE_FAST_OBJECTIVE_KIND,
            "schema_version": SUPPORT_AWARE_FAST_OBJECTIVE_SCHEMA_VERSION,
            "control_objective_sha256": control.objective_sha256,
            "direct_fast_objective_sha256": direct_fast.objective_sha256,
            "support_coordinates": [list(row) for row in support_coordinates],
        }
    )
    return SupportAwareFastObjective(
        objective_sha256=identity,
        control=control,
        direct_fast=direct_fast,
        support_coordinates=support_coordinates,
    )


def build_support_projection_cache(
    objective: SupportAwareFastObjective,
    *,
    max_entries: int = 4096,
) -> SupportProjectionCache:
    if not isinstance(objective, SupportAwareFastObjective):
        raise TraceContractError("support FAST objective is invalid")
    return SupportProjectionCache(
        objective_sha256=objective.objective_sha256,
        max_entries=max_entries,
    )


def evaluate_support_aware_fast_objective(
    objective: SupportAwareFastObjective,
    candidate_artifact_vector: ArtifactStatVector,
    *,
    cache: SupportProjectionCache,
) -> SupportAwareFastScore:
    if not isinstance(objective, SupportAwareFastObjective):
        raise TraceContractError("support FAST objective is invalid")
    if not isinstance(candidate_artifact_vector, ArtifactStatVector):
        raise TraceContractError("candidate artifact vector is invalid")
    if not isinstance(cache, SupportProjectionCache):
        raise TraceContractError("support projection cache is invalid")
    if cache.objective_sha256 != objective.objective_sha256:
        raise TraceContractError("support projection cache objective mismatch")

    direct_score = evaluate_artifact_variable_objective(
        objective.direct_fast,
        candidate_artifact_vector,
    )
    replacements = artifact_replacements_between(
        objective.control.incumbent_artifact_vector,
        candidate_artifact_vector,
    )
    direct_deltas = {
        (row.actor_key, row.stat_key): row.delta
        for row in replacements
        if not math.isclose(row.delta, 0.0, rel_tol=1e-12, abs_tol=1e-12)
    }
    support_key = tuple(
        (actor, stat, direct_deltas[(actor, stat)])
        for actor, stat in objective.support_coordinates
        if (actor, stat) in direct_deltas
    )
    projection = cache.entries.get(support_key)
    cache_hit = projection is not None
    if projection is None:
        support_deltas = {
            (actor, stat): value for actor, stat, value in support_key
        }
        evaluation = evaluate_support_plan_sliced(
            objective.control.replay_plan,
            support_deltas,
        )
        projection = project_support_evaluation_plan_to_hits(
            objective.control.replay_plan,
            evaluation,
        )
        if len(cache.entries) >= cache.max_entries:
            oldest_key = next(iter(cache.entries))
            del cache.entries[oldest_key]
            cache.eviction_count += 1
        cache.entries[support_key] = projection
        cache.miss_count += 1
    else:
        cache.hit_count += 1

    projection_by_event = {
        row.event_id: row
        for row in projection.projections
        if row.stat_deltas
    }
    correction = 0.0
    by_actor = dict(direct_score.candidate_damage_by_actor)
    uncertainties = set(projection.uncertainty_codes)
    frozen_baseline_damage = sum(
        actor.frozen_damage
        for actor in objective.direct_fast.fixed_actor_formulas
    )
    frozen_baseline_share = 0.0
    if objective.direct_fast.baseline_damage > 0.0:
        frozen_baseline_share = (
            frozen_baseline_damage / objective.direct_fast.baseline_damage
        )
    if frozen_baseline_damage > 1e-12:
        uncertainties.add("direct_fast_frozen_residual_present")
    if any(
        channel.unresolved_input_event_count > 0
        for actor in objective.direct_fast.fixed_actor_formulas
        for channel in actor.normal_channels
    ):
        uncertainties.add("direct_fast_unresolved_inputs_present")
    changed_hits = 0
    for group in objective.control.standard.groups:
        for event_id in group.event_ids:
            hit_projection = projection_by_event.get(event_id)
            if hit_projection is None:
                continue
            changed_hits += 1
            if group.kind is CompactTermKind.FROZEN or group.expression is None:
                uncertainties.add(f"frozen_support_affected_hit:{event_id}")
                continue
            dynamic_deltas = {
                (hit_projection.actor_key, stat_key): value
                for stat_key, value in hit_projection.stat_deltas
            }
            direct_value, direct_fallback = group.expression.evaluate(direct_deltas)
            support_value, support_fallback = group.expression.evaluate(
                direct_deltas,
                dynamic_deltas,
            )
            if direct_fallback or support_fallback:
                uncertainties.add(f"support_fast_formula_fallback:{event_id}")
                continue
            delta = support_value - direct_value
            correction += delta
            by_actor[group.actor_key] = by_actor.get(group.actor_key, 0.0) + delta

    candidate_damage = direct_score.candidate_damage + correction
    baseline_dps = direct_score.baseline_dps
    candidate_dps = None
    if objective.direct_fast.duration_frames is not None:
        candidate_dps = (
            candidate_damage * 60.0 / objective.direct_fast.duration_frames
        )
    return SupportAwareFastScore(
        objective_sha256=objective.objective_sha256,
        artifact_vector_sha256=candidate_artifact_vector.vector_sha256,
        baseline_damage=direct_score.baseline_damage,
        candidate_damage=candidate_damage,
        expected_delta=candidate_damage - direct_score.baseline_damage,
        baseline_dps=baseline_dps,
        candidate_dps=candidate_dps,
        candidate_damage_by_actor=tuple(sorted(by_actor.items())),
        support_correction_damage=correction,
        support_changed_hit_count=changed_hits,
        support_cache_hit=cache_hit,
        support_cache_entry_count=len(cache.entries),
        uncertainty_codes=tuple(sorted(uncertainties)),
        frozen_baseline_damage=frozen_baseline_damage,
        frozen_baseline_share=frozen_baseline_share,
    )


__all__ = [
    "SUPPORT_AWARE_FAST_OBJECTIVE_KIND",
    "SUPPORT_AWARE_FAST_OBJECTIVE_SCHEMA_VERSION",
    "SupportAwareFastObjective",
    "SupportAwareFastScore",
    "SupportProjectionCache",
    "build_support_projection_cache",
    "compile_support_aware_fast_objective",
    "compile_support_aware_fast_objective_from_control",
    "evaluate_support_aware_fast_objective",
]
