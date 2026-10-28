"""Fast product-search formula beside the standard compact control objective.

``STANDARD`` retains every safe compact state as a bounded development control.
``FAST`` intentionally folds those states into response-equivalent channels
with activation rate, weighted coefficients, expected crit, reaction curves and
a frozen residual. FAST is the accepted product search evaluator; its score is
still non-authoritative until retained finalists are verified by real GCSIM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import ScalingKind, TraceContractError, canonical_sha256
from .observed_snapshot import ArtifactStatReplacement
from .rotation_objective import (
    CompactObjectiveScore,
    CompactRotationObjective,
    CompactTermKind,
    RotationObjectiveDocument,
    StatCoordinate,
    StatDeltas,
    _NormalExpression,
    _TransformativeExpression,
    compile_rotation_objective,
    evaluate_rotation_objective,
)


COARSE_ROTATION_OBJECTIVE_SCHEMA_VERSION = 2
COARSE_ROTATION_OBJECTIVE_KIND = "gtt.trace_equation.coarse_rotation_objective"
ROTATION_FORMULA_FILTER_KIND = "gtt.trace_equation.rotation_formula_filters"


class RotationFormulaMode(str, Enum):
    STANDARD = "standard"
    FAST = "fast"


@dataclass(frozen=True, slots=True)
class CoarseNormalChannel:
    actor_key: str
    attack_tag: int
    damage_type_key: str
    response_coordinates: tuple[StatCoordinate, ...]
    scaling_kind: ScalingKind
    amplifying: bool
    event_count: int
    activation_rate_per_second: float | None
    average_scaling_value: float
    average_scaling_base: float
    average_scale_coefficient: float
    average_flat_damage: float
    flat_response_slopes: tuple[tuple[str, str, float], ...]
    average_damage_bonus: float
    element_bonus_weights: tuple[tuple[str, float], ...]
    average_raw_crit_rate: float
    average_crit_damage: float
    weak_point_fraction: float
    average_post_multiplier: float
    average_elemental_mastery: float
    average_amp_multiplier: float
    average_reaction_bonus: float
    baseline_damage: float
    calibration: float
    unresolved_input_event_count: int

    @property
    def relevant_coordinates(self) -> tuple[StatCoordinate, ...]:
        coordinates: set[StatCoordinate] = {
            (self.actor_key, "cr"),
            (self.actor_key, "cd"),
            (self.actor_key, "dmg%"),
        }
        if self.scaling_kind is ScalingKind.ATTACK:
            coordinates.update(
                ((self.actor_key, "atk%"), (self.actor_key, "atk"))
            )
        elif self.scaling_kind is ScalingKind.HP:
            coordinates.update(
                ((self.actor_key, "hp%"), (self.actor_key, "hp"))
            )
        elif self.scaling_kind is ScalingKind.DEFENSE:
            coordinates.update(
                ((self.actor_key, "def%"), (self.actor_key, "def"))
            )
        else:
            coordinates.add((self.actor_key, "em"))
        if self.amplifying:
            coordinates.add((self.actor_key, "em"))
        coordinates.update(
            (self.actor_key, stat_key)
            for stat_key, _ in self.element_bonus_weights
        )
        coordinates.update(
            (actor_key, stat_key)
            for actor_key, stat_key, _ in self.flat_response_slopes
        )
        return tuple(sorted(coordinates))

    def evaluate(self, deltas: StatDeltas) -> float:
        scaling = self.average_scaling_value
        if self.scaling_kind is ScalingKind.ATTACK:
            scaling += self.average_scaling_base * deltas.get(
                (self.actor_key, "atk%"), 0.0
            )
            scaling += deltas.get((self.actor_key, "atk"), 0.0)
        elif self.scaling_kind is ScalingKind.HP:
            scaling += self.average_scaling_base * deltas.get(
                (self.actor_key, "hp%"), 0.0
            )
            scaling += deltas.get((self.actor_key, "hp"), 0.0)
        elif self.scaling_kind is ScalingKind.DEFENSE:
            scaling += self.average_scaling_base * deltas.get(
                (self.actor_key, "def%"), 0.0
            )
            scaling += deltas.get((self.actor_key, "def"), 0.0)
        else:
            scaling += deltas.get((self.actor_key, "em"), 0.0)

        flat = self.average_flat_damage + sum(
            slope * deltas.get((actor_key, stat_key), 0.0)
            for actor_key, stat_key, slope in self.flat_response_slopes
        )
        bonus_delta = deltas.get((self.actor_key, "dmg%"), 0.0)
        bonus_delta += sum(
            weight * deltas.get((self.actor_key, stat_key), 0.0)
            for stat_key, weight in self.element_bonus_weights
        )
        bonus = self.average_damage_bonus + bonus_delta

        raw_cr = self.average_raw_crit_rate + deltas.get(
            (self.actor_key, "cr"), 0.0
        )
        cd = self.average_crit_damage + deltas.get(
            (self.actor_key, "cd"), 0.0
        )
        random_crit = 1.0 + max(0.0, min(1.0, raw_cr)) * cd
        weak_crit = 1.0 + cd
        crit = (
            self.weak_point_fraction * weak_crit
            + (1.0 - self.weak_point_fraction) * random_crit
        )

        damage = self.event_count * (
            self.average_scale_coefficient * scaling + flat
        )
        damage *= 1.0 + bonus
        damage *= crit * self.average_post_multiplier
        if self.amplifying:
            em = self.average_elemental_mastery + deltas.get(
                (self.actor_key, "em"), 0.0
            )
            if em <= -1400.0:
                return self.baseline_damage
            damage *= self.average_amp_multiplier * (
                1.0
                + (2.78 * em) / (1400.0 + em)
                + self.average_reaction_bonus
            )
        result = damage * self.calibration
        return result if math.isfinite(result) else self.baseline_damage


@dataclass(frozen=True, slots=True)
class CoarseReactionChannel:
    actor_key: str
    event_count: int
    activation_rate_per_second: float | None
    average_elemental_mastery: float
    average_level_base: float
    average_em_curve_numerator: float
    average_em_curve_denominator_offset: float
    average_reaction_bonus: float
    average_coefficient: float
    average_post_multiplier: float
    baseline_damage: float
    calibration: float

    @property
    def relevant_coordinates(self) -> tuple[StatCoordinate, ...]:
        return ((self.actor_key, "em"),)

    def evaluate(self, deltas: StatDeltas) -> float:
        em = self.average_elemental_mastery + deltas.get(
            (self.actor_key, "em"), 0.0
        )
        denominator = self.average_em_curve_denominator_offset + em
        if denominator <= 0.0:
            return self.baseline_damage
        reaction = self.average_level_base * (
            1.0
            + self.average_em_curve_numerator * em / denominator
            + self.average_reaction_bonus
        )
        damage = (
            self.event_count
            * self.average_coefficient
            * reaction
            * self.average_post_multiplier
            * self.calibration
        )
        return damage if math.isfinite(damage) else self.baseline_damage


@dataclass(frozen=True, slots=True)
class CoarseActorFormula:
    actor_key: str
    normal_channels: tuple[CoarseNormalChannel, ...]
    reaction_channel: CoarseReactionChannel | None
    frozen_damage: float
    baseline_damage: float

    @property
    def channel_count(self) -> int:
        return len(self.normal_channels) + int(self.reaction_channel is not None)

    @property
    def relevant_coordinates(self) -> tuple[StatCoordinate, ...]:
        coordinates = {
            coordinate
            for channel in self.normal_channels
            for coordinate in channel.relevant_coordinates
        }
        if self.reaction_channel is not None:
            coordinates.update(self.reaction_channel.relevant_coordinates)
        return tuple(sorted(coordinates))

    def evaluate(self, deltas: StatDeltas) -> float:
        damage = self.frozen_damage + sum(
            channel.evaluate(deltas) for channel in self.normal_channels
        )
        if self.reaction_channel is not None:
            damage += self.reaction_channel.evaluate(deltas)
        return damage


@dataclass(frozen=True, slots=True)
class CoarseRotationObjective:
    objective_sha256: str
    standard_objective_sha256: str
    evidence_sha256: str
    character_keys: tuple[str, ...]
    duration_frames: int | None
    actor_formulas: tuple[CoarseActorFormula, ...]
    baseline_damage: float
    standard_group_count: int
    coarse_channel_count: int
    relevant_coordinates: tuple[StatCoordinate, ...]
    schema_version: int = COARSE_ROTATION_OBJECTIVE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CoarseObjectiveScore:
    objective_sha256: str
    baseline_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    engine_call_count: int = 0
    authoritative: bool = False


@dataclass(frozen=True, slots=True)
class RotationFormulaFilters:
    filters_sha256: str
    standard: CompactRotationObjective
    fast: CoarseRotationObjective

    def objective(self, mode: RotationFormulaMode):
        if mode is RotationFormulaMode.STANDARD:
            return self.standard
        if mode is RotationFormulaMode.FAST:
            return self.fast
        raise TraceContractError("unsupported rotation formula mode")


@dataclass(frozen=True, slots=True)
class RotationFormulaScore:
    mode: RotationFormulaMode
    baseline_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    engine_call_count: int = 0
    authoritative: bool = False


def compile_coarse_rotation_objective(
    standard: CompactRotationObjective,
) -> CoarseRotationObjective:
    """Fold STANDARD groups into a few calibrated actor/scaling channels."""

    if not isinstance(standard, CompactRotationObjective):
        raise TraceContractError("standard must be CompactRotationObjective")
    duration = standard.duration_frames
    actor_formulas: list[CoarseActorFormula] = []
    for actor in standard.character_keys:
        normal_rows: dict[
            tuple[
                ScalingKind,
                bool,
                int,
                str,
                tuple[StatCoordinate, ...],
            ],
            list[tuple[_NormalExpression, int]],
        ] = {}
        reaction_rows: list[tuple[_TransformativeExpression, int]] = []
        frozen = 0.0
        for group in standard.groups:
            if group.actor_key != actor:
                continue
            if group.kind is CompactTermKind.NORMAL:
                assert isinstance(group.expression, _NormalExpression)
                normal_rows.setdefault(
                    (
                        group.expression.scaling_kind,
                        group.expression.amplifying,
                        group.expression.attack_tag,
                        group.expression.damage_type_key,
                        group.expression.coordinates,
                    ),
                    [],
                ).append((group.expression, group.multiplicity))
            elif group.kind is CompactTermKind.TRANSFORMATIVE:
                assert isinstance(group.expression, _TransformativeExpression)
                reaction_rows.append((group.expression, group.multiplicity))
            else:
                frozen += group.baseline_damage
        normal_channels = tuple(
            _compile_normal_channel(actor, key, rows, duration)
            for key, rows in sorted(
                normal_rows.items(),
                key=lambda item: (
                    item[0][0].value,
                    item[0][1],
                    item[0][2],
                    item[0][3],
                    item[0][4],
                ),
            )
        )
        reaction_channel = (
            None
            if not reaction_rows
            else _compile_reaction_channel(actor, reaction_rows, duration)
        )
        baseline = frozen + sum(row.baseline_damage for row in normal_channels)
        if reaction_channel is not None:
            baseline += reaction_channel.baseline_damage
        actor_formulas.append(
            CoarseActorFormula(
                actor_key=actor,
                normal_channels=normal_channels,
                reaction_channel=reaction_channel,
                frozen_damage=frozen,
                baseline_damage=baseline,
            )
        )
    baseline = sum(row.baseline_damage for row in actor_formulas)
    if not _close(baseline, standard.baseline_damage):
        raise TraceContractError("coarse actor formulas changed baseline total")
    relevant = tuple(
        sorted(
            {
                coordinate
                for actor in actor_formulas
                for coordinate in actor.relevant_coordinates
            }
        )
    )
    identity = canonical_sha256(
        {
            "kind": COARSE_ROTATION_OBJECTIVE_KIND,
            "schema_version": COARSE_ROTATION_OBJECTIVE_SCHEMA_VERSION,
            "standard_objective_sha256": standard.objective_sha256,
            "actors": [
                {
                    "actor_key": actor.actor_key,
                    "normal_channels": [
                        {
                            "scaling_kind": row.scaling_kind.value,
                            "amplifying": row.amplifying,
                            "attack_tag": row.attack_tag,
                            "damage_type_key": row.damage_type_key,
                            "response_coordinates": [
                                list(coordinate)
                                for coordinate in row.response_coordinates
                            ],
                            "event_count": row.event_count,
                        }
                        for row in actor.normal_channels
                    ],
                    "reaction_event_count": (
                        0
                        if actor.reaction_channel is None
                        else actor.reaction_channel.event_count
                    ),
                }
                for actor in actor_formulas
            ],
        }
    )
    return CoarseRotationObjective(
        objective_sha256=identity,
        standard_objective_sha256=standard.objective_sha256,
        evidence_sha256=standard.evidence_sha256,
        character_keys=standard.character_keys,
        duration_frames=duration,
        actor_formulas=tuple(actor_formulas),
        baseline_damage=baseline,
        standard_group_count=standard.group_count,
        coarse_channel_count=sum(row.channel_count for row in actor_formulas),
        relevant_coordinates=relevant,
    )


def evaluate_coarse_rotation_objective(
    objective: CoarseRotationObjective,
    replacements: tuple[ArtifactStatReplacement, ...],
) -> CoarseObjectiveScore:
    if not isinstance(objective, CoarseRotationObjective):
        raise TraceContractError("objective must be CoarseRotationObjective")
    deltas = _replacement_deltas(objective.character_keys, replacements)
    by_actor = tuple(
        (actor.actor_key, actor.evaluate(deltas))
        for actor in objective.actor_formulas
    )
    candidate = sum(value for _, value in by_actor)
    baseline_dps = None
    candidate_dps = None
    if objective.duration_frames is not None:
        baseline_dps = objective.baseline_damage * 60.0 / objective.duration_frames
        candidate_dps = candidate * 60.0 / objective.duration_frames
    return CoarseObjectiveScore(
        objective_sha256=objective.objective_sha256,
        baseline_damage=objective.baseline_damage,
        candidate_damage=candidate,
        expected_delta=candidate - objective.baseline_damage,
        baseline_dps=baseline_dps,
        candidate_dps=candidate_dps,
        candidate_damage_by_actor=by_actor,
    )


def compile_rotation_formula_filters(
    document: RotationObjectiveDocument,
) -> RotationFormulaFilters:
    standard = compile_rotation_objective(document)
    fast = compile_coarse_rotation_objective(standard)
    identity = canonical_sha256(
        {
            "kind": ROTATION_FORMULA_FILTER_KIND,
            "standard": standard.objective_sha256,
            "fast": fast.objective_sha256,
        }
    )
    return RotationFormulaFilters(identity, standard, fast)


def evaluate_rotation_formula_filter(
    filters: RotationFormulaFilters,
    mode: RotationFormulaMode,
    replacements: tuple[ArtifactStatReplacement, ...],
) -> RotationFormulaScore:
    if not isinstance(filters, RotationFormulaFilters):
        raise TraceContractError("filters must be RotationFormulaFilters")
    if not isinstance(mode, RotationFormulaMode):
        raise TraceContractError("mode must be RotationFormulaMode")
    if mode is RotationFormulaMode.STANDARD:
        score: CompactObjectiveScore | CoarseObjectiveScore = (
            evaluate_rotation_objective(filters.standard, replacements)
        )
    else:
        score = evaluate_coarse_rotation_objective(filters.fast, replacements)
    return RotationFormulaScore(
        mode=mode,
        baseline_damage=score.baseline_damage,
        candidate_damage=score.candidate_damage,
        expected_delta=score.expected_delta,
        baseline_dps=score.baseline_dps,
        candidate_dps=score.candidate_dps,
        candidate_damage_by_actor=score.candidate_damage_by_actor,
    )


def _compile_normal_channel(actor, key, rows, duration):
    (
        scaling_kind,
        amplifying,
        attack_tag,
        damage_type_key,
        response_coordinates,
    ) = key
    count = sum(multiplicity for _, multiplicity in rows)
    weighted = lambda getter: sum(
        getter(expression) * multiplicity for expression, multiplicity in rows
    ) / count
    elements: dict[str, int] = {}
    slopes: dict[StatCoordinate, float] = {}
    unresolved_count = 0
    for expression, multiplicity in rows:
        if expression.element_bonus_key is not None:
            elements[expression.element_bonus_key] = (
                elements.get(expression.element_bonus_key, 0) + multiplicity
            )
        if expression.unresolved_flat_candidate_sensitive:
            unresolved_count += multiplicity
        if expression.source_program is not None:
            for coordinate in expression.source_program.coordinates:
                slope = _source_slope(expression.source_program, coordinate)
                slopes[coordinate] = slopes.get(coordinate, 0.0) + slope * multiplicity
    average_flat = weighted(
        lambda expression: (
            expression.observed_flat_dmg
            if expression.source_program is None
            else expression.source_program.evaluate({})
            or expression.observed_flat_dmg
        )
    )
    channel = CoarseNormalChannel(
        actor_key=actor,
        attack_tag=attack_tag,
        damage_type_key=damage_type_key,
        response_coordinates=response_coordinates,
        scaling_kind=scaling_kind,
        amplifying=amplifying,
        event_count=count,
        activation_rate_per_second=(
            None if duration is None else count * 60.0 / duration
        ),
        average_scaling_value=weighted(lambda row: row.scaling_baseline),
        average_scaling_base=weighted(lambda row: row.scaling_base),
        average_scale_coefficient=weighted(
            lambda row: row.mult * (1.0 + row.base_dmg_bonus)
        ),
        average_flat_damage=average_flat,
        flat_response_slopes=tuple(
            sorted(
                (coordinate[0], coordinate[1], value / count)
                for coordinate, value in slopes.items()
            )
        ),
        average_damage_bonus=weighted(lambda row: row.damage_bonus),
        element_bonus_weights=tuple(
            sorted((stat_key, amount / count) for stat_key, amount in elements.items())
        ),
        average_raw_crit_rate=weighted(lambda row: row.raw_crit_rate),
        average_crit_damage=weighted(lambda row: row.crit_damage),
        weak_point_fraction=sum(
            multiplicity
            for expression, multiplicity in rows
            if expression.hit_weak_point
        ) / count,
        average_post_multiplier=weighted(
            lambda row: (
                row.defense_multiplier
                * row.resistance_multiplier
                * row.group_multiplier
                * row.elevation_multiplier
            )
        ),
        average_elemental_mastery=weighted(lambda row: row.elemental_mastery),
        average_amp_multiplier=weighted(lambda row: row.amp_multiplier),
        average_reaction_bonus=weighted(lambda row: row.reaction_bonus),
        baseline_damage=sum(
            expression.baseline_score * multiplicity
            for expression, multiplicity in rows
        ),
        calibration=1.0,
        unresolved_input_event_count=unresolved_count,
    )
    raw_baseline = channel.evaluate({})
    calibration = (
        1.0
        if math.isclose(raw_baseline, 0.0, abs_tol=1e-12)
        else channel.baseline_damage / raw_baseline
    )
    return _replace_normal_calibration(channel, calibration)


def _replace_normal_calibration(channel, calibration):
    return CoarseNormalChannel(
        **{
            field: getattr(channel, field)
            for field in channel.__dataclass_fields__
            if field != "calibration"
        },
        calibration=calibration,
    )


def _compile_reaction_channel(actor, rows, duration):
    count = sum(multiplicity for _, multiplicity in rows)
    weighted = lambda getter: sum(
        getter(expression) * multiplicity for expression, multiplicity in rows
    ) / count
    channel = CoarseReactionChannel(
        actor_key=actor,
        event_count=count,
        activation_rate_per_second=(
            None if duration is None else count * 60.0 / duration
        ),
        average_elemental_mastery=weighted(lambda row: row.elemental_mastery),
        average_level_base=weighted(lambda row: row.level_base),
        average_em_curve_numerator=weighted(lambda row: row.em_curve_numerator),
        average_em_curve_denominator_offset=weighted(
            lambda row: row.em_curve_denominator_offset
        ),
        average_reaction_bonus=weighted(lambda row: row.reaction_bonus),
        average_coefficient=weighted(lambda row: row.coefficient),
        average_post_multiplier=weighted(
            lambda row: (
                (1.0 + row.damage_bonus)
                * row.defense_multiplier
                * row.resistance_multiplier
                * (
                    1.0 + row.crit_damage
                    if row.hit_weak_point
                    else 1.0
                    + max(0.0, min(1.0, row.raw_crit_rate)) * row.crit_damage
                )
                * row.group_multiplier
                * row.elevation_multiplier
            )
        ),
        baseline_damage=sum(
            expression.baseline_score * multiplicity
            for expression, multiplicity in rows
        ),
        calibration=1.0,
    )
    raw = channel.evaluate({})
    calibration = 1.0 if math.isclose(raw, 0.0, abs_tol=1e-12) else channel.baseline_damage / raw
    return CoarseReactionChannel(
        **{
            field: getattr(channel, field)
            for field in channel.__dataclass_fields__
            if field != "calibration"
        },
        calibration=calibration,
    )


def _source_slope(program, coordinate: StatCoordinate) -> float:
    stat_key = coordinate[1]
    epsilon = 1e-5 if stat_key.endswith("%") or stat_key in {"cr", "cd"} else 1e-3
    plus = program.evaluate({coordinate: epsilon})
    minus = program.evaluate({coordinate: -epsilon})
    if plus is not None and minus is not None:
        return (plus - minus) / (2.0 * epsilon)
    baseline = program.evaluate({})
    if plus is None or baseline is None:
        return 0.0
    return (plus - baseline) / epsilon


def _replacement_deltas(character_keys, replacements):
    if not isinstance(replacements, tuple) or any(
        not isinstance(row, ArtifactStatReplacement) for row in replacements
    ):
        raise TraceContractError("replacements must be ArtifactStatReplacement tuple")
    keys = tuple((row.actor_key, row.stat_key) for row in replacements)
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise TraceContractError(
            "artifact replacements must be sorted by unique actor_key/stat_key"
        )
    deltas = {
        (row.actor_key, row.stat_key): row.delta
        for row in replacements
        if not math.isclose(row.delta, 0.0, rel_tol=1e-12, abs_tol=1e-12)
    }
    unknown = {actor for actor, _ in deltas} - set(character_keys)
    if unknown:
        raise TraceContractError(f"unknown actors in formula filter: {sorted(unknown)!r}")
    return deltas


def _close(left, right):
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-7)


__all__ = [
    "COARSE_ROTATION_OBJECTIVE_KIND",
    "COARSE_ROTATION_OBJECTIVE_SCHEMA_VERSION",
    "CoarseActorFormula",
    "CoarseNormalChannel",
    "CoarseObjectiveScore",
    "CoarseReactionChannel",
    "CoarseRotationObjective",
    "RotationFormulaFilters",
    "RotationFormulaMode",
    "RotationFormulaScore",
    "compile_coarse_rotation_objective",
    "compile_rotation_formula_filters",
    "evaluate_coarse_rotation_objective",
    "evaluate_rotation_formula_filter",
]
