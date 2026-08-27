"""Absolute artifact-variable view of the incumbent-anchored FAST objective.

The accepted FAST evaluator stores effective channel snapshots observed with
one incumbent artifact assignment and evaluates replacements as
``candidate - incumbent`` deltas.  This module performs the algebraic rebase
once so callers can evaluate sparse *absolute raw artifact stat vectors*.

It owns no artifact enumeration, set search, engine runner, product callback or
UI.  The original delta evaluator remains the bounded parity oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .coarse_rotation_objective import (
    CoarseActorFormula,
    CoarseNormalChannel,
    CoarseReactionChannel,
    CoarseRotationObjective,
)
from .contracts import ScalingKind, TraceContractError, canonical_sha256
from .observed_snapshot import ArtifactStatReplacement
from .ranking import RANKING_STAT_KEYS
from .rotation_objective import StatCoordinate, StatDeltas


ARTIFACT_STAT_VECTOR_KIND = "gtt.trace_equation.raw_artifact_stat_vector"
ARTIFACT_STAT_VECTOR_SCHEMA_VERSION = 1
ARTIFACT_VARIABLE_OBJECTIVE_KIND = (
    "gtt.trace_equation.artifact_variable_rotation_objective"
)
ARTIFACT_VARIABLE_OBJECTIVE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ArtifactStatValue:
    """One non-zero absolute raw main/sub-stat contribution from artifacts."""

    actor_key: str
    stat_key: str
    value: float

    def __post_init__(self) -> None:
        _trimmed(self.actor_key, "actor_key")
        _trimmed(self.stat_key, "stat_key")
        if self.stat_key not in RANKING_STAT_KEYS:
            raise TraceContractError(
                f"artifact stat {self.stat_key!r} is unsupported"
            )
        _finite(self.value, "artifact stat value")
        if self.value < 0.0:
            raise TraceContractError("raw artifact stat value cannot be negative")
        if math.isclose(self.value, 0.0, rel_tol=0.0, abs_tol=1e-15):
            raise TraceContractError(
                "zero artifact stat rows are non-canonical; omit the row"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "value": float(self.value),
        }


@dataclass(frozen=True, slots=True)
class ArtifactStatVector:
    """Canonical sparse absolute artifact-only stat vector for a full team."""

    values: tuple[ArtifactStatValue, ...]
    schema_version: int = ARTIFACT_STAT_VECTOR_SCHEMA_VERSION
    kind: str = ARTIFACT_STAT_VECTOR_KIND

    def __post_init__(self) -> None:
        if self.schema_version != ARTIFACT_STAT_VECTOR_SCHEMA_VERSION:
            raise TraceContractError("artifact stat-vector schema mismatch")
        if self.kind != ARTIFACT_STAT_VECTOR_KIND:
            raise TraceContractError("artifact stat-vector kind mismatch")
        if not isinstance(self.values, tuple) or any(
            not isinstance(row, ArtifactStatValue) for row in self.values
        ):
            raise TraceContractError("artifact stat-vector values must be immutable")
        keys = tuple((row.actor_key, row.stat_key) for row in self.values)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise TraceContractError(
                "artifact stat-vector values must be sorted and unique"
            )

    @classmethod
    def build(
        cls,
        values: tuple[ArtifactStatValue, ...],
    ) -> ArtifactStatVector:
        if not isinstance(values, tuple):
            raise TraceContractError("artifact stat-vector values must be a tuple")
        filtered = tuple(
            row
            for row in values
            if not math.isclose(row.value, 0.0, rel_tol=0.0, abs_tol=1e-15)
        )
        return cls(tuple(sorted(filtered, key=lambda row: (row.actor_key, row.stat_key))))

    @property
    def vector_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "schema_version": self.schema_version,
            "values": [row.to_dict() for row in self.values],
        }


@dataclass(frozen=True, slots=True)
class ArtifactVariableObjective:
    """FAST formula rebased onto absolute artifact-controlled coordinates."""

    objective_sha256: str
    fast_objective_sha256: str
    evidence_sha256: str
    character_keys: tuple[str, ...]
    duration_frames: int | None
    fixed_actor_formulas: tuple[CoarseActorFormula, ...]
    incumbent_artifact_vector: ArtifactStatVector
    baseline_damage: float
    fixed_context_damage: float
    relevant_coordinates: tuple[StatCoordinate, ...]
    schema_version: int = ARTIFACT_VARIABLE_OBJECTIVE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ArtifactVariableScore:
    objective_sha256: str
    artifact_vector_sha256: str
    baseline_damage: float
    fixed_context_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    engine_call_count: int = 0
    authoritative: bool = False


def compile_artifact_variable_objective(
    fast: CoarseRotationObjective,
    incumbent_artifact_vector: ArtifactStatVector,
) -> ArtifactVariableObjective:
    """Remove the incumbent raw artifact vector from FAST channel constants."""

    if not isinstance(fast, CoarseRotationObjective):
        raise TraceContractError("fast must be a CoarseRotationObjective")
    if not isinstance(incumbent_artifact_vector, ArtifactStatVector):
        raise TraceContractError(
            "incumbent_artifact_vector must be an ArtifactStatVector"
        )
    incumbent = _values(
        fast.character_keys,
        incumbent_artifact_vector,
        field_name="incumbent artifact vector",
    )
    actors = tuple(
        _rebase_actor(actor, incumbent)
        for actor in fast.actor_formulas
    )
    fixed_context_damage = sum(actor.evaluate({}) for actor in actors)
    reconstructed = sum(actor.evaluate(incumbent) for actor in actors)
    if not _close(reconstructed, fast.baseline_damage):
        raise TraceContractError(
            "absolute incumbent artifact vector does not reconstruct FAST baseline"
        )
    identity = canonical_sha256(
        {
            "kind": ARTIFACT_VARIABLE_OBJECTIVE_KIND,
            "schema_version": ARTIFACT_VARIABLE_OBJECTIVE_SCHEMA_VERSION,
            "fast_objective_sha256": fast.objective_sha256,
            "incumbent_artifact_vector_sha256": (
                incumbent_artifact_vector.vector_sha256
            ),
        }
    )
    return ArtifactVariableObjective(
        objective_sha256=identity,
        fast_objective_sha256=fast.objective_sha256,
        evidence_sha256=fast.evidence_sha256,
        character_keys=fast.character_keys,
        duration_frames=fast.duration_frames,
        fixed_actor_formulas=actors,
        incumbent_artifact_vector=incumbent_artifact_vector,
        baseline_damage=fast.baseline_damage,
        fixed_context_damage=fixed_context_damage,
        relevant_coordinates=fast.relevant_coordinates,
    )


def evaluate_artifact_variable_objective(
    objective: ArtifactVariableObjective,
    candidate_artifact_vector: ArtifactStatVector,
) -> ArtifactVariableScore:
    """Evaluate one sparse absolute artifact vector with zero engine calls."""

    if not isinstance(objective, ArtifactVariableObjective):
        raise TraceContractError("objective must be an ArtifactVariableObjective")
    if not isinstance(candidate_artifact_vector, ArtifactStatVector):
        raise TraceContractError(
            "candidate_artifact_vector must be an ArtifactStatVector"
        )
    candidate_values = _values(
        objective.character_keys,
        candidate_artifact_vector,
        field_name="candidate artifact vector",
    )
    by_actor = tuple(
        (actor.actor_key, actor.evaluate(candidate_values))
        for actor in objective.fixed_actor_formulas
    )
    candidate = sum(value for _, value in by_actor)
    baseline_dps = None
    candidate_dps = None
    if objective.duration_frames is not None:
        baseline_dps = objective.baseline_damage * 60.0 / objective.duration_frames
        candidate_dps = candidate * 60.0 / objective.duration_frames
    return ArtifactVariableScore(
        objective_sha256=objective.objective_sha256,
        artifact_vector_sha256=candidate_artifact_vector.vector_sha256,
        baseline_damage=objective.baseline_damage,
        fixed_context_damage=objective.fixed_context_damage,
        candidate_damage=candidate,
        expected_delta=candidate - objective.baseline_damage,
        baseline_dps=baseline_dps,
        candidate_dps=candidate_dps,
        candidate_damage_by_actor=by_actor,
    )


def artifact_replacements_between(
    baseline: ArtifactStatVector,
    candidate: ArtifactStatVector,
) -> tuple[ArtifactStatReplacement, ...]:
    """Build the old parity-oracle delta from two absolute artifact vectors."""

    if not isinstance(baseline, ArtifactStatVector) or not isinstance(
        candidate, ArtifactStatVector
    ):
        raise TraceContractError("artifact replacement endpoints must be vectors")
    left = _unchecked_values(baseline)
    right = _unchecked_values(candidate)
    rows = []
    for actor_key, stat_key in sorted(set(left) | set(right)):
        baseline_value = left.get((actor_key, stat_key), 0.0)
        candidate_value = right.get((actor_key, stat_key), 0.0)
        if math.isclose(
            baseline_value,
            candidate_value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            continue
        rows.append(
            ArtifactStatReplacement(
                actor_key=actor_key,
                stat_key=stat_key,
                baseline_artifact_value=baseline_value,
                candidate_artifact_value=candidate_value,
            )
        )
    return tuple(rows)


def _rebase_actor(
    actor: CoarseActorFormula,
    incumbent: StatDeltas,
) -> CoarseActorFormula:
    normal = tuple(
        _rebase_normal_channel(channel, incumbent)
        for channel in actor.normal_channels
    )
    reaction = (
        None
        if actor.reaction_channel is None
        else _rebase_reaction_channel(actor.reaction_channel, incumbent)
    )
    return replace(
        actor,
        normal_channels=normal,
        reaction_channel=reaction,
    )


def _rebase_normal_channel(
    channel: CoarseNormalChannel,
    incumbent: StatDeltas,
) -> CoarseNormalChannel:
    own = lambda stat_key: incumbent.get((channel.actor_key, stat_key), 0.0)
    scaling = channel.average_scaling_value
    if channel.scaling_kind is ScalingKind.ATTACK:
        scaling -= channel.average_scaling_base * own("atk%")
        scaling -= own("atk")
    elif channel.scaling_kind is ScalingKind.HP:
        scaling -= channel.average_scaling_base * own("hp%")
        scaling -= own("hp")
    elif channel.scaling_kind is ScalingKind.DEFENSE:
        scaling -= channel.average_scaling_base * own("def%")
        scaling -= own("def")
    else:
        scaling -= own("em")

    flat = channel.average_flat_damage - sum(
        slope * incumbent.get((actor_key, stat_key), 0.0)
        for actor_key, stat_key, slope in channel.flat_response_slopes
    )
    bonus = channel.average_damage_bonus - own("dmg%")
    bonus -= sum(
        weight * own(stat_key)
        for stat_key, weight in channel.element_bonus_weights
    )
    return replace(
        channel,
        average_scaling_value=scaling,
        average_flat_damage=flat,
        average_damage_bonus=bonus,
        average_raw_crit_rate=channel.average_raw_crit_rate - own("cr"),
        average_crit_damage=channel.average_crit_damage - own("cd"),
        average_elemental_mastery=(
            channel.average_elemental_mastery - own("em")
        ),
    )


def _rebase_reaction_channel(
    channel: CoarseReactionChannel,
    incumbent: StatDeltas,
) -> CoarseReactionChannel:
    return replace(
        channel,
        average_elemental_mastery=(
            channel.average_elemental_mastery
            - incumbent.get((channel.actor_key, "em"), 0.0)
        ),
    )


def _values(
    character_keys: tuple[str, ...],
    vector: ArtifactStatVector,
    *,
    field_name: str,
) -> StatDeltas:
    values = _unchecked_values(vector)
    unknown = {actor for actor, _ in values} - set(character_keys)
    if unknown:
        raise TraceContractError(
            f"unknown actors in {field_name}: {sorted(unknown)!r}"
        )
    return values


def _unchecked_values(vector: ArtifactStatVector) -> StatDeltas:
    return {
        (row.actor_key, row.stat_key): float(row.value)
        for row in vector.values
    }


def _trimmed(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TraceContractError(f"{field_name} must be a non-empty trimmed string")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{field_name} must be finite")


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-7)


__all__ = [
    "ARTIFACT_STAT_VECTOR_KIND",
    "ARTIFACT_STAT_VECTOR_SCHEMA_VERSION",
    "ARTIFACT_VARIABLE_OBJECTIVE_KIND",
    "ARTIFACT_VARIABLE_OBJECTIVE_SCHEMA_VERSION",
    "ArtifactStatValue",
    "ArtifactStatVector",
    "ArtifactVariableObjective",
    "ArtifactVariableScore",
    "artifact_replacements_between",
    "compile_artifact_variable_objective",
    "evaluate_artifact_variable_objective",
]
