"""Support-aware continuous target and its separable physical-build guide.

This is an isolated extension of ``continuous_target_v1``.  It keeps the same
game-derived roll budget and marginal-allocation idea, but evaluates every
trial through the accepted support-aware FAST boundary.  The target and guide
are diagnostic heuristics only: neither may prune a physical assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from ..artifact_investment_rules import (
    ARTIFACT_INVESTMENT_RULES_SHA256,
    ARTIFACT_MAIN_STAT_SLOTS,
    FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER,
    FIVE_STAR_SUBSTAT_ROLL_RULES,
    five_star_substat_coordinate_cap,
)
from ..trace_equation.artifact_variable_objective import (
    ArtifactStatValue,
    ArtifactStatVector,
)
from ..trace_equation.contracts import TraceContractError, canonical_sha256
from ..trace_equation.rotation_objective import StatCoordinate, StatDeltas
from ..trace_equation.support_fast_objective import (
    SupportAwareFastObjective,
    SupportAwareFastScore,
    SupportProjectionCache,
    build_support_projection_cache,
    evaluate_support_aware_fast_objective,
)
from .continuous_target import (
    ContinuousAllocationValue,
    ContinuousMainStatLane,
    ContinuousTargetConfig,
    ContinuousTargetPoint,
)


SUPPORT_CONTINUOUS_TARGET_KIND = (
    "gtt.optimizer_trace_search.support_continuous_target_v1"
)
SUPPORT_CONTINUOUS_GUIDE_KIND = (
    "gtt.optimizer_trace_search.support_continuous_guide_v1"
)
SUPPORT_CONTINUOUS_SCHEMA_VERSION = 1
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class SupportAwareContinuousTargetResult:
    target_sha256: str
    objective_sha256: str
    lane_id: str
    lane_sha256: str
    artifact_rules_sha256: str
    requested_roll_units_per_wearer: float
    requested_roll_units: float
    spent_roll_units: float
    unspent_roll_units: float
    relevant_coordinates: tuple[StatCoordinate, ...]
    coordinate_caps: tuple[tuple[str, str, float], ...]
    allocations: tuple[ContinuousAllocationValue, ...]
    target_artifact_vector: ArtifactStatVector
    target_score: SupportAwareFastScore
    curve: tuple[ContinuousTargetPoint, ...]
    evaluation_count: int
    exchange_iterations: int
    stop_reason: str
    support_cache_hits: int
    support_cache_misses: int
    engine_call_count: int = 0
    authoritative: bool = False
    prune_authority: bool = False
    schema_version: int = SUPPORT_CONTINUOUS_SCHEMA_VERSION
    kind: str = SUPPORT_CONTINUOUS_TARGET_KIND


@dataclass(frozen=True, slots=True)
class ContinuousGuideCandidate:
    candidate_id: str
    lane_sha256: str
    artifact_vector: ArtifactStatVector

    def __post_init__(self) -> None:
        _trimmed(self.candidate_id, "candidate_id")
        _sha256(self.lane_sha256, "lane_sha256")
        if not isinstance(self.artifact_vector, ArtifactStatVector):
            raise TraceContractError("guide candidate artifact vector is invalid")


@dataclass(frozen=True, slots=True)
class ContinuousGuidePrediction:
    candidate_id: str
    lane_sha256: str
    predicted_damage: float
    coordinate_response_sum: float


@dataclass(frozen=True, slots=True)
class SupportAwareContinuousGuideResult:
    guide_sha256: str
    objective_sha256: str
    predictions: tuple[ContinuousGuidePrediction, ...]
    target_count: int
    candidate_count: int
    response_evaluation_count: int
    support_cache_hits: int
    support_cache_misses: int
    engine_call_count: int = 0
    authoritative: bool = False
    prune_authority: bool = False
    schema_version: int = SUPPORT_CONTINUOUS_SCHEMA_VERSION
    kind: str = SUPPORT_CONTINUOUS_GUIDE_KIND


def solve_support_aware_continuous_target(
    objective: SupportAwareFastObjective,
    lane: ContinuousMainStatLane,
    config: ContinuousTargetConfig | None = None,
    *,
    cache: SupportProjectionCache | None = None,
) -> SupportAwareContinuousTargetResult:
    """Solve one main-stat lane through support-aware FAST with zero engine calls."""

    if not isinstance(objective, SupportAwareFastObjective):
        raise TraceContractError("support FAST objective is invalid")
    if not isinstance(lane, ContinuousMainStatLane):
        raise TraceContractError("continuous main-stat lane is invalid")
    config = config or ContinuousTargetConfig()
    if not isinstance(config, ContinuousTargetConfig):
        raise TraceContractError("continuous target config is invalid")
    cache = cache or build_support_projection_cache(objective, max_entries=32_768)
    _validate_cache(objective, cache)

    character_keys = objective.direct_fast.character_keys
    _validate_complete_lane(character_keys, lane)
    wearer_budget = float(config.roll_units_per_wearer)
    requested_budget = float(len(character_keys) * wearer_budget)
    main_values = _values(lane.main_stat_vector)
    main_stats_by_actor = _main_stats_by_actor(character_keys, lane)
    coordinates = tuple(
        coordinate
        for coordinate in sorted(
            set(objective.direct_fast.relevant_coordinates)
            | set(objective.support_coordinates)
        )
        if coordinate[1] in FIVE_STAR_SUBSTAT_ROLL_RULES
    )
    caps = {
        coordinate: five_star_substat_coordinate_cap(
            coordinate[1],
            main_stats_by_actor[coordinate[0]],
        )
        for coordinate in coordinates
    }
    coordinates = tuple(row for row in coordinates if caps[row] > 0.0)
    allocations = {coordinate: 0.0 for coordinate in coordinates}
    actor_used = {actor: 0.0 for actor in character_keys}
    curve: list[ContinuousTargetPoint] = []
    evaluation_count = 0

    def damage(rows: dict[StatCoordinate, float]) -> float:
        nonlocal evaluation_count
        evaluation_count += 1
        vector = _vector_from_values(_candidate_values(main_values, rows))
        return evaluate_support_aware_fast_objective(
            objective,
            vector,
            cache=cache,
        ).candidate_damage

    current_damage = damage(allocations)
    if config.record_curve:
        curve.append(_point("base", allocations, current_damage))

    spent = 0.0
    stop_reason = "budget_exhausted"
    while spent + _EPSILON < requested_budget:
        remaining = requested_budget - spent
        best_coordinate: StatCoordinate | None = None
        best_amount = 0.0
        best_damage = current_damage
        best_gain_per_roll = -math.inf
        for coordinate in coordinates:
            actor_key, _ = coordinate
            amount = min(
                float(config.allocation_step),
                remaining,
                caps[coordinate] - allocations[coordinate],
                wearer_budget - actor_used[actor_key],
            )
            if amount <= _EPSILON:
                continue
            trial = dict(allocations)
            trial[coordinate] += amount
            trial_damage = damage(trial)
            gain_per_roll = (trial_damage - current_damage) / amount
            if _better_marginal(
                gain_per_roll,
                coordinate,
                best_gain_per_roll,
                best_coordinate,
            ):
                best_coordinate = coordinate
                best_amount = amount
                best_damage = trial_damage
                best_gain_per_roll = gain_per_roll
        if (
            best_coordinate is None
            or best_gain_per_roll <= config.minimum_gain_per_roll
        ):
            stop_reason = "no_positive_marginal"
            break
        allocations[best_coordinate] += best_amount
        actor_used[best_coordinate[0]] += best_amount
        spent += best_amount
        current_damage = best_damage
        if config.record_curve:
            curve.append(_point("greedy", allocations, current_damage))

    exchange_iterations = 0
    exchange_converged = False
    for _ in range(config.max_exchange_iterations):
        best_move: tuple[StatCoordinate, StatCoordinate, float] | None = None
        best_damage = current_damage
        for source in coordinates:
            if allocations[source] <= _EPSILON:
                continue
            for destination in coordinates:
                if source == destination:
                    continue
                amount = min(
                    float(config.exchange_step),
                    allocations[source],
                    caps[destination] - allocations[destination],
                )
                if source[0] != destination[0]:
                    amount = min(
                        amount,
                        wearer_budget - actor_used[destination[0]],
                    )
                if amount <= _EPSILON:
                    continue
                trial = dict(allocations)
                trial[source] -= amount
                trial[destination] += amount
                trial_damage = damage(trial)
                if _better_exchange(
                    trial_damage,
                    (source, destination, amount),
                    best_damage,
                    best_move,
                ):
                    best_damage = trial_damage
                    best_move = (source, destination, amount)
        if best_move is None or best_damage <= current_damage + 1e-10:
            exchange_converged = True
            break
        source, destination, amount = best_move
        allocations[source] -= amount
        allocations[destination] += amount
        if source[0] != destination[0]:
            actor_used[source[0]] -= amount
            actor_used[destination[0]] += amount
        current_damage = best_damage
        exchange_iterations += 1
        if config.record_curve:
            curve.append(_point("exchange", allocations, current_damage))
    if config.max_exchange_iterations == 0:
        exchange_converged = True
    if not exchange_converged:
        stop_reason = "exchange_iteration_limit"

    target_vector = _vector_from_values(_candidate_values(main_values, allocations))
    target_score = evaluate_support_aware_fast_objective(
        objective,
        target_vector,
        cache=cache,
    )
    evaluation_count += 1
    if not math.isclose(
        target_score.candidate_damage,
        current_damage,
        rel_tol=1e-10,
        abs_tol=1e-7,
    ):
        raise TraceContractError("support continuous target diverged from FAST")
    allocation_rows = _allocation_rows(allocations)
    identity = canonical_sha256(
        {
            "kind": SUPPORT_CONTINUOUS_TARGET_KIND,
            "schema_version": SUPPORT_CONTINUOUS_SCHEMA_VERSION,
            "objective_sha256": objective.objective_sha256,
            "lane_sha256": lane.lane_sha256,
            "artifact_rules_sha256": ARTIFACT_INVESTMENT_RULES_SHA256,
            "config": config.to_dict(),
            "target_vector_sha256": target_vector.vector_sha256,
            "allocations": [
                {
                    "actor_key": row.actor_key,
                    "stat_key": row.stat_key,
                    "roll_units": row.roll_units,
                    "stat_value": row.stat_value,
                }
                for row in allocation_rows
            ],
        }
    )
    return SupportAwareContinuousTargetResult(
        target_sha256=identity,
        objective_sha256=objective.objective_sha256,
        lane_id=lane.lane_id,
        lane_sha256=lane.lane_sha256,
        artifact_rules_sha256=ARTIFACT_INVESTMENT_RULES_SHA256,
        requested_roll_units_per_wearer=wearer_budget,
        requested_roll_units=requested_budget,
        spent_roll_units=spent,
        unspent_roll_units=max(0.0, requested_budget - spent),
        relevant_coordinates=coordinates,
        coordinate_caps=tuple(
            (actor, stat, caps[(actor, stat)]) for actor, stat in coordinates
        ),
        allocations=allocation_rows,
        target_artifact_vector=target_vector,
        target_score=target_score,
        curve=tuple(curve),
        evaluation_count=evaluation_count,
        exchange_iterations=exchange_iterations,
        stop_reason=stop_reason,
        support_cache_hits=cache.hit_count,
        support_cache_misses=cache.miss_count,
    )


def rank_candidates_by_support_continuous_target(
    objective: SupportAwareFastObjective,
    targets: tuple[SupportAwareContinuousTargetResult, ...],
    candidates: tuple[ContinuousGuideCandidate, ...],
    *,
    cache: SupportProjectionCache | None = None,
) -> SupportAwareContinuousGuideResult:
    """Rank physical vectors by an additive one-coordinate response surface.

    For every lane and every coordinate value present in its candidates, the
    guide measures one exact support-aware FAST perturbation around that lane's
    continuous optimum.  Candidate ranking then sums those precomputed response
    deltas.  This is intentionally cheaper than complete support replay per
    candidate and remains heuristic because cross-coordinate interactions are
    approximated as separable.
    """

    if not isinstance(objective, SupportAwareFastObjective):
        raise TraceContractError("support FAST objective is invalid")
    if not targets or any(
        not isinstance(row, SupportAwareContinuousTargetResult) for row in targets
    ):
        raise TraceContractError("support continuous targets are invalid")
    if not candidates or any(
        not isinstance(row, ContinuousGuideCandidate) for row in candidates
    ):
        raise TraceContractError("continuous guide candidates are invalid")
    target_by_lane = {row.lane_sha256: row for row in targets}
    if len(target_by_lane) != len(targets):
        raise TraceContractError("continuous guide targets contain duplicate lanes")
    if any(row.objective_sha256 != objective.objective_sha256 for row in targets):
        raise TraceContractError("continuous guide target objective mismatch")
    if any(row.lane_sha256 not in target_by_lane for row in candidates):
        raise TraceContractError("continuous guide candidate lane has no target")
    ids = tuple(row.candidate_id for row in candidates)
    if len(ids) != len(set(ids)):
        raise TraceContractError("continuous guide candidate IDs are duplicated")
    cache = cache or build_support_projection_cache(objective, max_entries=32_768)
    _validate_cache(objective, cache)

    response_evaluations = 0
    response_by_lane_coordinate_value: dict[
        tuple[str, str, str, float], float
    ] = {}
    candidates_by_lane: dict[str, list[ContinuousGuideCandidate]] = {}
    for candidate in candidates:
        candidates_by_lane.setdefault(candidate.lane_sha256, []).append(candidate)

    for lane_sha256, lane_candidates in sorted(candidates_by_lane.items()):
        target = target_by_lane[lane_sha256]
        target_values = _values(target.target_artifact_vector)
        response_coordinates = tuple(
            sorted(
                set(objective.direct_fast.relevant_coordinates)
                | set(objective.support_coordinates)
            )
        )
        for actor, stat in response_coordinates:
            coordinate = (actor, stat)
            values = sorted(
                {
                    _values(row.artifact_vector).get(coordinate, 0.0)
                    for row in lane_candidates
                }
            )
            target_value = target_values.get(coordinate, 0.0)
            for value in values:
                key = (lane_sha256, actor, stat, float(value))
                if math.isclose(value, target_value, rel_tol=0.0, abs_tol=1e-12):
                    response_by_lane_coordinate_value[key] = 0.0
                    continue
                trial = dict(target_values)
                if value > _EPSILON:
                    trial[coordinate] = float(value)
                else:
                    trial.pop(coordinate, None)
                score = evaluate_support_aware_fast_objective(
                    objective,
                    _vector_from_values(trial),
                    cache=cache,
                )
                response_evaluations += 1
                response_by_lane_coordinate_value[key] = (
                    score.candidate_damage - target.target_score.candidate_damage
                )

    predictions = []
    for candidate in candidates:
        target = target_by_lane[candidate.lane_sha256]
        values = _values(candidate.artifact_vector)
        response_coordinates = tuple(
            sorted(
                set(objective.direct_fast.relevant_coordinates)
                | set(objective.support_coordinates)
            )
        )
        response_sum = sum(
            response_by_lane_coordinate_value[
                (
                    candidate.lane_sha256,
                    actor,
                    stat,
                    float(values.get((actor, stat), 0.0)),
                )
            ]
            for actor, stat in response_coordinates
        )
        predictions.append(
            ContinuousGuidePrediction(
                candidate_id=candidate.candidate_id,
                lane_sha256=candidate.lane_sha256,
                predicted_damage=target.target_score.candidate_damage + response_sum,
                coordinate_response_sum=response_sum,
            )
        )
    ordered = tuple(
        sorted(predictions, key=lambda row: (-row.predicted_damage, row.candidate_id))
    )
    identity = canonical_sha256(
        {
            "kind": SUPPORT_CONTINUOUS_GUIDE_KIND,
            "schema_version": SUPPORT_CONTINUOUS_SCHEMA_VERSION,
            "objective_sha256": objective.objective_sha256,
            "target_sha256s": sorted(row.target_sha256 for row in targets),
            "predictions": [
                {
                    "candidate_id": row.candidate_id,
                    "lane_sha256": row.lane_sha256,
                    "predicted_damage": row.predicted_damage,
                }
                for row in ordered
            ],
        }
    )
    return SupportAwareContinuousGuideResult(
        guide_sha256=identity,
        objective_sha256=objective.objective_sha256,
        predictions=ordered,
        target_count=len(targets),
        candidate_count=len(candidates),
        response_evaluation_count=response_evaluations,
        support_cache_hits=cache.hit_count,
        support_cache_misses=cache.miss_count,
    )


def _validate_complete_lane(
    character_keys: tuple[str, ...],
    lane: ContinuousMainStatLane,
) -> None:
    expected = {
        (actor, slot)
        for actor in character_keys
        for slot in ARTIFACT_MAIN_STAT_SLOTS
    }
    actual = {(row.actor_key, row.slot_key) for row in lane.selections}
    if actual != expected:
        raise TraceContractError("main-stat lane must cover the full team")


def _main_stats_by_actor(
    character_keys: tuple[str, ...],
    lane: ContinuousMainStatLane,
) -> dict[str, tuple[str, ...]]:
    rows = {actor: [] for actor in character_keys}
    for selection in lane.selections:
        rows[selection.actor_key].append((selection.slot_key, selection.stat_key))
    return {
        actor: tuple(stat for _, stat in sorted(values))
        for actor, values in rows.items()
    }


def _candidate_values(
    main_values: StatDeltas,
    allocations: dict[StatCoordinate, float],
) -> StatDeltas:
    result = dict(main_values)
    for coordinate, roll_units in allocations.items():
        if roll_units <= _EPSILON:
            continue
        rule = FIVE_STAR_SUBSTAT_ROLL_RULES[coordinate[1]]
        result[coordinate] = result.get(coordinate, 0.0) + (
            rule.value_for_max_roll_units(roll_units)
        )
    return result


def _allocation_rows(
    allocations: dict[StatCoordinate, float],
) -> tuple[ContinuousAllocationValue, ...]:
    return tuple(
        ContinuousAllocationValue(
            actor_key=actor,
            stat_key=stat,
            roll_units=float(roll_units),
            stat_value=FIVE_STAR_SUBSTAT_ROLL_RULES[
                stat
            ].value_for_max_roll_units(roll_units),
        )
        for (actor, stat), roll_units in sorted(allocations.items())
        if roll_units > _EPSILON
    )


def _point(
    stage: str,
    allocations: dict[StatCoordinate, float],
    damage: float,
) -> ContinuousTargetPoint:
    return ContinuousTargetPoint(
        stage=stage,
        spent_roll_units=sum(allocations.values()),
        candidate_damage=damage,
        allocations=_allocation_rows(allocations),
    )


def _values(vector: ArtifactStatVector) -> StatDeltas:
    return {
        (row.actor_key, row.stat_key): float(row.value) for row in vector.values
    }


def _vector_from_values(values: StatDeltas) -> ArtifactStatVector:
    return ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, value)
            for (actor, stat), value in values.items()
            if value > _EPSILON
        )
    )


def _better_marginal(
    gain: float,
    coordinate: StatCoordinate,
    best_gain: float,
    best_coordinate: StatCoordinate | None,
) -> bool:
    if gain > best_gain + 1e-12:
        return True
    return math.isclose(gain, best_gain, rel_tol=0.0, abs_tol=1e-12) and (
        best_coordinate is None or coordinate < best_coordinate
    )


def _better_exchange(
    damage: float,
    move: tuple[StatCoordinate, StatCoordinate, float],
    best_damage: float,
    best_move: tuple[StatCoordinate, StatCoordinate, float] | None,
) -> bool:
    if damage > best_damage + 1e-10:
        return True
    return math.isclose(damage, best_damage, rel_tol=0.0, abs_tol=1e-10) and (
        best_move is None or move < best_move
    )


def _validate_cache(
    objective: SupportAwareFastObjective,
    cache: SupportProjectionCache,
) -> None:
    if not isinstance(cache, SupportProjectionCache):
        raise TraceContractError("support projection cache is invalid")
    if cache.objective_sha256 != objective.objective_sha256:
        raise TraceContractError("support projection cache objective mismatch")


def _trimmed(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TraceContractError(f"{field_name} must be a non-empty trimmed string")


def _sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TraceContractError(f"{field_name} must be a lowercase SHA-256")


__all__ = [
    "SUPPORT_CONTINUOUS_GUIDE_KIND",
    "SUPPORT_CONTINUOUS_SCHEMA_VERSION",
    "SUPPORT_CONTINUOUS_TARGET_KIND",
    "ContinuousGuideCandidate",
    "ContinuousGuidePrediction",
    "SupportAwareContinuousGuideResult",
    "SupportAwareContinuousTargetResult",
    "rank_candidates_by_support_continuous_target",
    "solve_support_aware_continuous_target",
]
