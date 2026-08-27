"""Bounded continuous artifact-stat target over the explicit FAST objective.

V1 uses the confirmed five-star roll budget. It greedily follows the greatest
team-damage marginal per max-roll-equivalent unit, then performs deterministic
bounded roll exchanges until no tested exchange improves the result. The
result is guidance only: it cannot delete a physical artifact or assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from ..artifact_investment_rules import (
    ARTIFACT_INVESTMENT_RULES_SHA256,
    ARTIFACT_MAIN_STAT_SLOTS,
    FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER,
    FIVE_STAR_SUBSTAT_ROLL_RULES,
    five_star_main_stat_value,
    five_star_substat_coordinate_cap,
)
from ..trace_equation.artifact_variable_objective import (
    ArtifactStatValue,
    ArtifactStatVector,
    ArtifactVariableObjective,
    ArtifactVariableScore,
    evaluate_artifact_variable_objective,
)
from ..trace_equation.contracts import TraceContractError, canonical_sha256
from ..trace_equation.rotation_objective import StatCoordinate, StatDeltas


CONTINUOUS_TARGET_KIND = "gtt.optimizer_trace_search.continuous_target_v1"
CONTINUOUS_TARGET_SCHEMA_VERSION = 1
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class MainStatSelection:
    actor_key: str
    slot_key: str
    stat_key: str

    def __post_init__(self) -> None:
        _trimmed(self.actor_key, "actor_key")
        _trimmed(self.slot_key, "slot_key")
        _trimmed(self.stat_key, "stat_key")
        five_star_main_stat_value(self.slot_key, self.stat_key)

    @property
    def value(self) -> float:
        return five_star_main_stat_value(self.slot_key, self.stat_key)

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "slot_key": self.slot_key,
            "stat_key": self.stat_key,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ContinuousMainStatLane:
    lane_id: str
    selections: tuple[MainStatSelection, ...]
    main_stat_vector: ArtifactStatVector
    lane_sha256: str

    @classmethod
    def build(
        cls,
        lane_id: str,
        selections: tuple[MainStatSelection, ...],
    ) -> ContinuousMainStatLane:
        _trimmed(lane_id, "lane_id")
        if not isinstance(selections, tuple) or any(
            not isinstance(row, MainStatSelection) for row in selections
        ):
            raise TraceContractError("main-stat selections must be immutable")
        ordered = tuple(
            sorted(selections, key=lambda row: (row.actor_key, row.slot_key))
        )
        keys = tuple((row.actor_key, row.slot_key) for row in ordered)
        if len(keys) != len(set(keys)):
            raise TraceContractError("main-stat lane has duplicate actor/slot rows")

        totals: dict[StatCoordinate, float] = {}
        for row in ordered:
            coordinate = (row.actor_key, row.stat_key)
            totals[coordinate] = totals.get(coordinate, 0.0) + row.value
        vector = _vector_from_values(totals)
        identity = canonical_sha256(
            {
                "kind": "gtt.optimizer_trace_search.main_stat_lane_v1",
                "lane_id": lane_id,
                "selections": [row.to_dict() for row in ordered],
                "main_stat_vector_sha256": vector.vector_sha256,
                "artifact_rules_sha256": ARTIFACT_INVESTMENT_RULES_SHA256,
            }
        )
        return cls(lane_id, ordered, vector, identity)


@dataclass(frozen=True, slots=True)
class ContinuousTargetConfig:
    roll_units_per_wearer: float = FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER
    allocation_step: float = 1.0
    exchange_step: float = 0.25
    max_exchange_iterations: int = 96
    minimum_gain_per_roll: float = 1e-9
    record_curve: bool = True

    def __post_init__(self) -> None:
        _finite_non_negative(
            self.roll_units_per_wearer,
            "roll_units_per_wearer",
        )
        if (
            self.roll_units_per_wearer
            > FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER + _EPSILON
        ):
            raise TraceContractError(
                "roll_units_per_wearer exceeds the five-star 45-unit ceiling"
            )
        _finite_positive(self.allocation_step, "allocation_step")
        _finite_positive(self.exchange_step, "exchange_step")
        _finite_non_negative(self.minimum_gain_per_roll, "minimum_gain_per_roll")
        if (
            isinstance(self.max_exchange_iterations, bool)
            or not isinstance(self.max_exchange_iterations, int)
            or self.max_exchange_iterations < 0
        ):
            raise TraceContractError(
                "max_exchange_iterations must be a non-negative integer"
            )
        if not isinstance(self.record_curve, bool):
            raise TraceContractError("record_curve must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "roll_units_per_wearer": self.roll_units_per_wearer,
            "allocation_step": self.allocation_step,
            "exchange_step": self.exchange_step,
            "max_exchange_iterations": self.max_exchange_iterations,
            "minimum_gain_per_roll": self.minimum_gain_per_roll,
            "record_curve": self.record_curve,
        }


@dataclass(frozen=True, slots=True)
class ContinuousAllocationValue:
    actor_key: str
    stat_key: str
    roll_units: float
    stat_value: float


@dataclass(frozen=True, slots=True)
class ContinuousTargetPoint:
    stage: str
    spent_roll_units: float
    candidate_damage: float
    allocations: tuple[ContinuousAllocationValue, ...]


@dataclass(frozen=True, slots=True)
class ContinuousTargetResult:
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
    target_score: ArtifactVariableScore
    curve: tuple[ContinuousTargetPoint, ...]
    evaluation_count: int
    exchange_iterations: int
    stop_reason: str
    engine_call_count: int = 0
    authoritative: bool = False
    prune_authority: bool = False


def solve_continuous_target(
    objective: ArtifactVariableObjective,
    lane: ContinuousMainStatLane,
    config: ContinuousTargetConfig | None = None,
) -> ContinuousTargetResult:
    """Solve one complete main-stat lane with zero engine calls."""

    if not isinstance(objective, ArtifactVariableObjective):
        raise TraceContractError("objective must be an ArtifactVariableObjective")
    if not isinstance(lane, ContinuousMainStatLane):
        raise TraceContractError("lane must be a ContinuousMainStatLane")
    config = config or ContinuousTargetConfig()
    if not isinstance(config, ContinuousTargetConfig):
        raise TraceContractError("config must be a ContinuousTargetConfig")
    _validate_complete_lane(objective, lane)

    wearer_budget = float(config.roll_units_per_wearer)
    requested_budget = float(
        len(objective.character_keys) * wearer_budget
    )

    main_values = _values(lane.main_stat_vector)
    main_stats_by_actor = _main_stats_by_actor(objective, lane)
    coordinates = tuple(
        coordinate
        for coordinate in objective.relevant_coordinates
        if coordinate[1] in FIVE_STAR_SUBSTAT_ROLL_RULES
    )
    caps = {
        coordinate: five_star_substat_coordinate_cap(
            coordinate[1],
            main_stats_by_actor[coordinate[0]],
        )
        for coordinate in coordinates
    }
    coordinates = tuple(coordinate for coordinate in coordinates if caps[coordinate] > 0)

    allocations: dict[StatCoordinate, float] = {
        coordinate: 0.0 for coordinate in coordinates
    }
    actor_used = {actor: 0.0 for actor in objective.character_keys}
    curve: list[ContinuousTargetPoint] = []
    evaluation_count = 0

    def damage(rows: dict[StatCoordinate, float]) -> float:
        nonlocal evaluation_count
        evaluation_count += 1
        values = _candidate_values(main_values, rows)
        return sum(actor.evaluate(values) for actor in objective.fixed_actor_formulas)

    current_damage = damage(allocations)
    if config.record_curve:
        curve.append(
            _point("base", allocations, current_damage)
        )

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
    target_score = evaluate_artifact_variable_objective(objective, target_vector)
    evaluation_count += 1
    if not math.isclose(
        target_score.candidate_damage,
        current_damage,
        rel_tol=1e-10,
        abs_tol=1e-7,
    ):
        raise TraceContractError("continuous target score diverged from FAST")

    allocation_rows = _allocation_rows(allocations)
    identity = canonical_sha256(
        {
            "kind": CONTINUOUS_TARGET_KIND,
            "schema_version": CONTINUOUS_TARGET_SCHEMA_VERSION,
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
    return ContinuousTargetResult(
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
    )


def solve_continuous_main_stat_lanes(
    objective: ArtifactVariableObjective,
    lanes: tuple[ContinuousMainStatLane, ...],
    config: ContinuousTargetConfig | None = None,
) -> tuple[ContinuousTargetResult, ...]:
    """Solve and rank a bounded caller-supplied set of discrete main-stat lanes."""

    if not isinstance(lanes, tuple) or any(
        not isinstance(lane, ContinuousMainStatLane) for lane in lanes
    ):
        raise TraceContractError("main-stat lanes must be immutable")
    if not lanes:
        raise TraceContractError("at least one main-stat lane is required")
    ids = tuple(lane.lane_id for lane in lanes)
    if len(ids) != len(set(ids)):
        raise TraceContractError("main-stat lane IDs must be unique")
    results = tuple(solve_continuous_target(objective, lane, config) for lane in lanes)
    return tuple(
        sorted(
            results,
            key=lambda row: (-row.target_score.candidate_damage, row.lane_id),
        )
    )


def _validate_complete_lane(
    objective: ArtifactVariableObjective,
    lane: ContinuousMainStatLane,
) -> None:
    expected = {
        (actor, slot)
        for actor in objective.character_keys
        for slot in ARTIFACT_MAIN_STAT_SLOTS
    }
    actual = {(row.actor_key, row.slot_key) for row in lane.selections}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise TraceContractError(
            f"main-stat lane must cover the full team; missing={missing!r}, extra={extra!r}"
        )


def _main_stats_by_actor(
    objective: ArtifactVariableObjective,
    lane: ContinuousMainStatLane,
) -> dict[str, tuple[str, ...]]:
    result = {actor: [] for actor in objective.character_keys}
    for row in lane.selections:
        result[row.actor_key].append((row.slot_key, row.stat_key))
    return {
        actor: tuple(
            stat for _, stat in sorted(rows, key=lambda value: value[0])
        )
        for actor, rows in result.items()
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


def _allocation_rows(
    allocations: dict[StatCoordinate, float],
) -> tuple[ContinuousAllocationValue, ...]:
    return tuple(
        ContinuousAllocationValue(
            actor_key=actor,
            stat_key=stat,
            roll_units=float(roll_units),
            stat_value=(
                FIVE_STAR_SUBSTAT_ROLL_RULES[stat]
                .value_for_max_roll_units(roll_units)
            ),
        )
        for (actor, stat), roll_units in sorted(allocations.items())
        if roll_units > _EPSILON
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


def _trimmed(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TraceContractError(f"{field_name} must be a non-empty trimmed string")


def _finite_positive(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise TraceContractError(f"{field_name} must be finite and positive")


def _finite_non_negative(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise TraceContractError(f"{field_name} must be finite and non-negative")


__all__ = [
    "CONTINUOUS_TARGET_KIND",
    "CONTINUOUS_TARGET_SCHEMA_VERSION",
    "ContinuousAllocationValue",
    "ContinuousMainStatLane",
    "ContinuousTargetConfig",
    "ContinuousTargetPoint",
    "ContinuousTargetResult",
    "MainStatSelection",
    "solve_continuous_main_stat_lanes",
    "solve_continuous_target",
]
