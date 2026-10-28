"""Compiled expected-damage objective for one observed fixed rotation.

Compilation performs provenance and formula-shape work once.  Candidate
evaluation then applies artifact-stat deltas to compact immutable arithmetic
terms; it never walks source manifests, rebuilds hit estimates, or invokes the
engine.  The objective is a shortlist signal only and preserves unsupported
terms at their observed baseline contribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import (
    ScalingKind,
    TraceContractError,
    TraceDocument,
    TraceHitEvent,
    canonical_sha256,
)
from .observed_snapshot import ArtifactStatReplacement
from .ranking import (
    RankingSupport,
    _estimate_hit,
    _source_flat_damage_bindings,
)
from .reaction_evidence import (
    ReactionEvidenceTrace,
    TransformativeReactionFormula,
)
from .source_dependencies import (
    SourceIROperator,
    SourceParameterKind,
    SourceSliceStatus,
)
from .state_evidence import StateEvidenceTrace


ROTATION_OBJECTIVE_SCHEMA_VERSION = 2
ROTATION_OBJECTIVE_KIND = "gtt.trace_equation.rotation_objective"

RotationObjectiveDocument = TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace
StatCoordinate = tuple[str, str]
StatDeltas = dict[StatCoordinate, float]


class CompactTermKind(str, Enum):
    NORMAL = "normal"
    TRANSFORMATIVE = "transformative"
    FROZEN = "frozen"


@dataclass(frozen=True, slots=True)
class _SourceParameter:
    observed_value: float
    actor_key: str | None = None
    stat_key: str | None = None
    derived_percent_key: str | None = None
    derived_flat_key: str | None = None
    derived_base_value: float | None = None

    @property
    def coordinates(self) -> tuple[StatCoordinate, ...]:
        if self.actor_key is None:
            return ()
        if self.derived_percent_key is not None:
            if self.derived_base_value is None:
                return ()
            assert self.derived_flat_key is not None
            return (
                (self.actor_key, self.derived_percent_key),
                (self.actor_key, self.derived_flat_key),
            )
        assert self.stat_key is not None
        return ((self.actor_key, self.stat_key),)

    def evaluate(self, deltas: StatDeltas) -> float:
        if self.actor_key is None:
            return self.observed_value
        if self.derived_percent_key is not None:
            if self.derived_base_value is None:
                return self.observed_value
            assert self.derived_flat_key is not None
            return (
                self.observed_value
                + self.derived_base_value
                * deltas.get((self.actor_key, self.derived_percent_key), 0.0)
                + deltas.get((self.actor_key, self.derived_flat_key), 0.0)
            )
        assert self.stat_key is not None
        return self.observed_value + deltas.get(
            (self.actor_key, self.stat_key), 0.0
        )


@dataclass(frozen=True, slots=True)
class _IRInstruction:
    operator: SourceIROperator
    inputs: tuple[int, ...]
    constant_value: float | None = None
    parameter_index: int | None = None


@dataclass(frozen=True, slots=True)
class _SourceProgram:
    parameters: tuple[_SourceParameter, ...]
    instructions: tuple[_IRInstruction, ...]
    root_node_id: int

    @property
    def coordinates(self) -> tuple[StatCoordinate, ...]:
        return tuple(
            sorted(
                {
                    coordinate
                    for parameter in self.parameters
                    for coordinate in parameter.coordinates
                }
            )
        )

    def evaluate(self, deltas: StatDeltas) -> float | None:
        parameters = tuple(row.evaluate(deltas) for row in self.parameters)
        values: list[float] = []
        try:
            for instruction in self.instructions:
                operator = instruction.operator
                if operator is SourceIROperator.CONST:
                    assert instruction.constant_value is not None
                    value = instruction.constant_value
                elif operator is SourceIROperator.PARAM:
                    assert instruction.parameter_index is not None
                    value = parameters[instruction.parameter_index]
                else:
                    inputs = tuple(values[index] for index in instruction.inputs)
                    value = _evaluate_ir_operator(operator, inputs)
                if not math.isfinite(value):
                    return None
                values.append(value)
        except (ArithmeticError, OverflowError):
            return None
        return values[self.root_node_id]


@dataclass(frozen=True, slots=True)
class _NormalExpression:
    actor_key: str
    attack_tag: int
    damage_type_key: str
    available_stat_keys: tuple[str, ...]
    scaling_kind: ScalingKind
    scaling_baseline: float
    scaling_base: float
    mult: float
    base_dmg_bonus: float
    observed_flat_dmg: float
    source_program: _SourceProgram | None
    unresolved_flat_candidate_sensitive: bool
    damage_bonus: float
    element_bonus_key: str | None
    raw_crit_rate: float
    crit_damage: float
    hit_weak_point: bool
    defense_multiplier: float
    resistance_multiplier: float
    amplifying: bool
    amp_multiplier: float
    elemental_mastery: float
    reaction_bonus: float
    group_multiplier: float
    elevation_multiplier: float
    baseline_score: float
    invalid_candidate_placeholder: float

    @property
    def coordinates(self) -> tuple[StatCoordinate, ...]:
        keys: set[str] = {"cr", "cd", "dmg%"}
        if self.element_bonus_key is not None:
            keys.add(self.element_bonus_key)
        if self.scaling_kind is ScalingKind.ATTACK:
            keys.update(("atk%", "atk"))
        elif self.scaling_kind is ScalingKind.HP:
            keys.update(("hp%", "hp"))
        elif self.scaling_kind is ScalingKind.DEFENSE:
            keys.update(("def%", "def"))
        elif self.scaling_kind is ScalingKind.ELEMENTAL_MASTERY:
            keys.add("em")
        if self.amplifying:
            keys.add("em")
        coordinates = {
            (self.actor_key, key)
            for key in keys
            if key in self.available_stat_keys
        }
        if self.source_program is not None:
            coordinates.update(self.source_program.coordinates)
        return tuple(sorted(coordinates))

    def evaluate(
        self,
        deltas: StatDeltas,
        dynamic_deltas: StatDeltas | None = None,
    ) -> tuple[float, bool]:
        # Artifact coordinates are limited by the observed stat snapshot.  A
        # replayed runtime modifier is a different input domain: for example,
        # generic DMG% is not an artifact stat, but it is still a real damage
        # formula input.  Keep those domains separate and merge only after the
        # artifact-side filter.
        actor_delta = {
            stat_key: amount
            for (actor_key, stat_key), amount in deltas.items()
            if actor_key == self.actor_key
            and stat_key in self.available_stat_keys
            and not math.isclose(amount, 0.0, rel_tol=1e-12, abs_tol=1e-12)
        }
        combined_deltas = dict(deltas)
        if dynamic_deltas:
            for coordinate, amount in dynamic_deltas.items():
                combined_deltas[coordinate] = (
                    combined_deltas.get(coordinate, 0.0) + amount
                )
                if coordinate[0] == self.actor_key:
                    actor_delta[coordinate[1]] = (
                        actor_delta.get(coordinate[1], 0.0) + amount
                    )
        if self.unresolved_flat_candidate_sensitive:
            multiplier_only = {"cr", "cd", "dmg%"}
            if self.element_bonus_key is not None:
                multiplier_only.add(self.element_bonus_key)
            if set(actor_delta) - multiplier_only:
                return self.baseline_score, True

        scaling = self.scaling_baseline
        if self.scaling_kind is ScalingKind.ATTACK:
            scaling += self.scaling_base * actor_delta.get("atk%", 0.0)
            scaling += actor_delta.get("atk", 0.0)
        elif self.scaling_kind is ScalingKind.HP:
            scaling += self.scaling_base * actor_delta.get("hp%", 0.0)
            scaling += actor_delta.get("hp", 0.0)
        elif self.scaling_kind is ScalingKind.DEFENSE:
            scaling += self.scaling_base * actor_delta.get("def%", 0.0)
            scaling += actor_delta.get("def", 0.0)
        elif self.scaling_kind is ScalingKind.ELEMENTAL_MASTERY:
            scaling += actor_delta.get("em", 0.0)

        flat_damage = self.observed_flat_dmg
        if self.source_program is not None:
            evaluated_flat = self.source_program.evaluate(combined_deltas)
            if evaluated_flat is None:
                return self.invalid_candidate_placeholder, True
            flat_damage = evaluated_flat

        bonus = self.damage_bonus + actor_delta.get("dmg%", 0.0)
        if self.element_bonus_key is not None:
            bonus += actor_delta.get(self.element_bonus_key, 0.0)
        raw_cr = self.raw_crit_rate + actor_delta.get("cr", 0.0)
        cd = self.crit_damage + actor_delta.get("cd", 0.0)
        useful_cr = max(0.0, min(1.0, raw_cr))
        crit = 1.0 + cd if self.hit_weak_point else 1.0 + useful_cr * cd

        damage = (
            self.mult * scaling * (1.0 + self.base_dmg_bonus) + flat_damage
        )
        damage *= 1.0 + bonus
        damage *= self.defense_multiplier * self.resistance_multiplier * crit
        if self.amplifying:
            em = self.elemental_mastery + actor_delta.get("em", 0.0)
            if em <= -1400.0:
                return self.invalid_candidate_placeholder, True
            damage *= self.amp_multiplier * (
                1.0 + (2.78 * em) / (1400.0 + em) + self.reaction_bonus
            )
        damage *= self.group_multiplier * self.elevation_multiplier
        if not math.isfinite(damage):
            return self.invalid_candidate_placeholder, True
        return damage, False


@dataclass(frozen=True, slots=True)
class _TransformativeExpression:
    actor_key: str
    elemental_mastery: float
    level_base: float
    em_curve_numerator: float
    em_curve_denominator_offset: float
    reaction_bonus: float
    coefficient: float
    damage_bonus: float
    defense_multiplier: float
    resistance_multiplier: float
    raw_crit_rate: float
    crit_damage: float
    hit_weak_point: bool
    group_multiplier: float
    elevation_multiplier: float
    baseline_score: float
    invalid_candidate_placeholder: float

    @property
    def coordinates(self) -> tuple[StatCoordinate, ...]:
        return ((self.actor_key, "em"),)

    def evaluate(
        self,
        deltas: StatDeltas,
        dynamic_deltas: StatDeltas | None = None,
    ) -> tuple[float, bool]:
        combined = dict(deltas)
        if dynamic_deltas:
            for coordinate, amount in dynamic_deltas.items():
                combined[coordinate] = combined.get(coordinate, 0.0) + amount
        em = self.elemental_mastery + combined.get((self.actor_key, "em"), 0.0)
        denominator = self.em_curve_denominator_offset + em
        if denominator <= 0.0:
            return self.invalid_candidate_placeholder, True
        core = self.level_base * (
            1.0 + self.em_curve_numerator * em / denominator + self.reaction_bonus
        )
        raw_cr = self.raw_crit_rate + combined.get((self.actor_key, "cr"), 0.0)
        crit_damage = self.crit_damage + combined.get(
            (self.actor_key, "cd"), 0.0
        )
        useful_cr = max(0.0, min(1.0, raw_cr))
        crit = (
            1.0 + crit_damage
            if self.hit_weak_point
            else 1.0 + useful_cr * crit_damage
        )
        damage = self.coefficient * core
        damage *= 1.0 + self.damage_bonus + combined.get(
            (self.actor_key, "dmg%"), 0.0
        )
        damage *= self.defense_multiplier * self.resistance_multiplier * crit
        damage *= self.group_multiplier * self.elevation_multiplier
        if not math.isfinite(damage):
            return self.invalid_candidate_placeholder, True
        return damage, False


CompactExpression = _NormalExpression | _TransformativeExpression


@dataclass(frozen=True, slots=True)
class CompactDamageGroup:
    kind: CompactTermKind
    actor_key: str
    event_ids: tuple[str, ...]
    expression: CompactExpression | None
    frozen_damage_per_event: float

    @property
    def multiplicity(self) -> int:
        return len(self.event_ids)

    @property
    def baseline_damage(self) -> float:
        if self.expression is None:
            return self.frozen_damage_per_event * self.multiplicity
        return self.expression.baseline_score * self.multiplicity


@dataclass(frozen=True, slots=True)
class CompactRotationObjective:
    objective_sha256: str
    evidence_sha256: str
    character_keys: tuple[str, ...]
    duration_frames: int | None
    source_hit_count: int
    groups: tuple[CompactDamageGroup, ...]
    relevant_coordinates: tuple[StatCoordinate, ...]
    baseline_damage: float
    detailed_baseline_damage: float
    compilation_preserves_baseline: bool
    schema_version: int = ROTATION_OBJECTIVE_SCHEMA_VERSION

    @property
    def group_count(self) -> int:
        return len(self.groups)

    @property
    def compression_ratio(self) -> float:
        return self.group_count / self.source_hit_count


@dataclass(frozen=True, slots=True)
class CompactObjectiveScore:
    objective_sha256: str
    baseline_damage: float
    candidate_damage: float
    expected_delta: float
    baseline_dps: float | None
    candidate_dps: float | None
    candidate_damage_by_actor: tuple[tuple[str, float], ...]
    fallback_group_count: int
    fallback_hit_count: int
    engine_call_count: int = 0
    authoritative: bool = False


def compile_rotation_objective(
    document: RotationObjectiveDocument,
) -> CompactRotationObjective:
    """Compile one validated trace into reusable candidate arithmetic."""

    trace, reaction_by_event, evidence_sha256, duration_frames = _unwrap(document)
    source_by_event = _source_flat_damage_bindings(document)
    grouped: dict[
        tuple[CompactTermKind, str, CompactExpression | None, float],
        list[str],
    ] = {}
    empty_values: dict[str, dict[str, float]] = {}
    detailed_baseline = 0.0

    for hit in trace.hits:
        reaction = reaction_by_event.get(hit.event_id)
        detailed = _estimate_hit(
            hit,
            empty_values,
            reaction,
            apply_deltas=True,
            source_flat_binding=source_by_event.get(hit.event_id),
        )
        detailed_baseline += detailed.baseline_score
        expression: CompactExpression | None = None
        kind = CompactTermKind.FROZEN
        frozen = detailed.baseline_score
        if detailed.support is RankingSupport.MODELED_EXPECTATION:
            if reaction is not None:
                expression = _compile_transformative(hit, reaction, detailed.baseline_score)
                kind = CompactTermKind.TRANSFORMATIVE
            else:
                expression = _compile_normal(
                    hit,
                    source_by_event.get(hit.event_id),
                    detailed.baseline_score,
                )
                kind = CompactTermKind.NORMAL
            candidate, fallback = expression.evaluate({})
            if fallback or not _close(candidate, detailed.baseline_score):
                raise TraceContractError(
                    f"compact expression baseline mismatch for {hit.event_id!r}"
                )
            frozen = 0.0
        key = (kind, detailed.actor_key, expression, frozen)
        grouped.setdefault(key, []).append(hit.event_id)

    groups = tuple(
        CompactDamageGroup(
            kind=key[0],
            actor_key=key[1],
            event_ids=tuple(event_ids),
            expression=key[2],
            frozen_damage_per_event=key[3],
        )
        for key, event_ids in grouped.items()
    )
    groups = tuple(sorted(groups, key=lambda row: row.event_ids[0]))
    baseline = sum(row.baseline_damage for row in groups)
    preserves = _close(baseline, detailed_baseline)
    if not preserves:
        raise TraceContractError("compact objective changed detailed baseline total")
    relevant = tuple(
        sorted(
            {
                coordinate
                for group in groups
                if group.expression is not None
                for coordinate in group.expression.coordinates
            }
        )
    )
    identity = canonical_sha256(
        {
            "kind": ROTATION_OBJECTIVE_KIND,
            "schema_version": ROTATION_OBJECTIVE_SCHEMA_VERSION,
            "evidence_sha256": evidence_sha256,
            "groups": [
                {
                    "kind": row.kind.value,
                    "actor_key": row.actor_key,
                    "event_ids": list(row.event_ids),
                }
                for row in groups
            ],
        }
    )
    return CompactRotationObjective(
        objective_sha256=identity,
        evidence_sha256=evidence_sha256,
        character_keys=trace.request.character_keys,
        duration_frames=duration_frames,
        source_hit_count=len(trace.hits),
        groups=groups,
        relevant_coordinates=relevant,
        baseline_damage=baseline,
        detailed_baseline_damage=detailed_baseline,
        compilation_preserves_baseline=preserves,
    )


def evaluate_rotation_objective(
    objective: CompactRotationObjective,
    replacements: tuple[ArtifactStatReplacement, ...],
) -> CompactObjectiveScore:
    """Evaluate one artifact replacement vector without trace/provenance work."""

    if not isinstance(objective, CompactRotationObjective):
        raise TraceContractError("objective must be CompactRotationObjective")
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
    unknown_actors = {actor for actor, _ in deltas} - set(objective.character_keys)
    if unknown_actors:
        raise TraceContractError(
            f"unknown actor keys in compact objective: {sorted(unknown_actors)!r}"
        )

    total = 0.0
    by_actor = {actor: 0.0 for actor in objective.character_keys}
    fallback_groups = 0
    fallback_hits = 0
    for group in objective.groups:
        if group.expression is None:
            value = group.frozen_damage_per_event
            fallback = True
        else:
            value, fallback = group.expression.evaluate(deltas)
        contribution = value * group.multiplicity
        total += contribution
        by_actor[group.actor_key] = by_actor.get(group.actor_key, 0.0) + contribution
        if fallback:
            fallback_groups += 1
            fallback_hits += group.multiplicity
    baseline_dps = None
    candidate_dps = None
    if objective.duration_frames is not None:
        baseline_dps = objective.baseline_damage * 60.0 / objective.duration_frames
        candidate_dps = total * 60.0 / objective.duration_frames
    return CompactObjectiveScore(
        objective_sha256=objective.objective_sha256,
        baseline_damage=objective.baseline_damage,
        candidate_damage=total,
        expected_delta=total - objective.baseline_damage,
        baseline_dps=baseline_dps,
        candidate_dps=candidate_dps,
        candidate_damage_by_actor=tuple(sorted(by_actor.items())),
        fallback_group_count=fallback_groups,
        fallback_hit_count=fallback_hits,
    )


def _compile_normal(hit, source, baseline_score: float) -> _NormalExpression:
    inputs = hit.formula_inputs
    stats = {row.stat_key: row.value for row in inputs.snapshot_stats}
    scaling_base = {
        ScalingKind.ATTACK: stats.get("base_atk", 0.0),
        ScalingKind.HP: stats.get("base_hp", 0.0),
        ScalingKind.DEFENSE: stats.get("base_def", 0.0),
        ScalingKind.ELEMENTAL_MASTERY: 0.0,
    }[inputs.scaling_kind]
    source_program = _compile_source_program(source, hit) if source is not None else None
    element_bonus_key = _element_bonus_key(hit.element)
    unresolved = (
        inputs.flat_dmg.value != 0.0
        and source_program is None
        and not hit.completeness.flat_dmg_provenance_complete
    )
    return _NormalExpression(
        actor_key=hit.actor_key,
        attack_tag=hit.attack_tag,
        damage_type_key=hit.element,
        available_stat_keys=tuple(sorted(stats)),
        scaling_kind=inputs.scaling_kind,
        scaling_baseline=inputs.scaling_value.value,
        scaling_base=scaling_base,
        mult=inputs.mult.value,
        base_dmg_bonus=inputs.base_dmg_bonus.value,
        observed_flat_dmg=inputs.flat_dmg.value,
        source_program=source_program,
        unresolved_flat_candidate_sensitive=unresolved,
        damage_bonus=inputs.dmg_bonus.value,
        element_bonus_key=element_bonus_key,
        raw_crit_rate=inputs.raw_crit_rate.value,
        crit_damage=inputs.crit_damage.value,
        hit_weak_point=inputs.hit_weak_point,
        defense_multiplier=inputs.defense_multiplier.value,
        resistance_multiplier=inputs.resistance_multiplier.value,
        amplifying=inputs.amplifying,
        amp_multiplier=inputs.amp_multiplier.value,
        elemental_mastery=inputs.elemental_mastery.value,
        reaction_bonus=inputs.reaction_bonus.value,
        group_multiplier=inputs.group_multiplier.value,
        elevation_multiplier=inputs.elevation_multiplier.value,
        baseline_score=baseline_score,
        invalid_candidate_placeholder=float(hit.uncapped_rolled_damage),
    )


def _compile_transformative(
    hit: TraceHitEvent,
    formula: TransformativeReactionFormula,
    baseline_score: float,
) -> _TransformativeExpression:
    inputs = hit.formula_inputs
    return _TransformativeExpression(
        actor_key=formula.owner_key,
        elemental_mastery=formula.elemental_mastery,
        level_base=formula.level_base,
        em_curve_numerator=formula.em_curve_numerator,
        em_curve_denominator_offset=formula.em_curve_denominator_offset,
        reaction_bonus=formula.reaction_bonus,
        coefficient=formula.coefficient,
        damage_bonus=inputs.dmg_bonus.value,
        defense_multiplier=inputs.defense_multiplier.value,
        resistance_multiplier=inputs.resistance_multiplier.value,
        raw_crit_rate=inputs.raw_crit_rate.value,
        crit_damage=inputs.crit_damage.value,
        hit_weak_point=inputs.hit_weak_point,
        group_multiplier=inputs.group_multiplier.value,
        elevation_multiplier=inputs.elevation_multiplier.value,
        baseline_score=baseline_score,
        invalid_candidate_placeholder=float(hit.uncapped_rolled_damage),
    )


def _compile_source_program(source, hit: TraceHitEvent) -> _SourceProgram | None:
    template = source.entry.template
    if template.status is SourceSliceStatus.OPAQUE_FROZEN:
        return None
    bindings = {row.parameter_key: row for row in source.binding.parameters}
    parameters: list[_SourceParameter] = []
    parameter_index: dict[str, int] = {}
    snapshot = {row.stat_key: row.value for row in hit.formula_inputs.snapshot_stats}
    derived_by_key = {
        "max_hp": ("base_hp", "hp%", "hp"),
        "total_atk": ("base_atk", "atk%", "atk"),
        "total_def": ("base_def", "def%", "def"),
    }
    for key in template.parameter_keys:
        binding = bindings[key]
        parameter_index[key] = len(parameters)
        if binding.kind is not SourceParameterKind.CANDIDATE_STAT:
            parameters.append(_SourceParameter(binding.observed_value))
            continue
        assert binding.actor_key is not None and binding.stat_key is not None
        derived = derived_by_key.get(binding.stat_key)
        if derived is None:
            parameters.append(
                _SourceParameter(
                    binding.observed_value,
                    actor_key=binding.actor_key,
                    stat_key=binding.stat_key,
                )
            )
            continue
        base_key, percent_key, flat_key = derived
        parameters.append(
            _SourceParameter(
                binding.observed_value,
                actor_key=binding.actor_key,
                stat_key=binding.stat_key,
                derived_percent_key=percent_key,
                derived_flat_key=flat_key,
                derived_base_value=(
                    snapshot[base_key] if binding.actor_key == hit.actor_key else None
                ),
            )
        )
    instructions: list[_IRInstruction] = []
    for node in template.nodes:
        instructions.append(
            _IRInstruction(
                operator=node.operator,
                inputs=node.input_node_ids,
                constant_value=node.constant_value,
                parameter_index=(
                    None
                    if node.parameter_key is None
                    else parameter_index[node.parameter_key]
                ),
            )
        )
    assert template.root_node_id is not None
    return _SourceProgram(
        parameters=tuple(parameters),
        instructions=tuple(instructions),
        root_node_id=template.root_node_id,
    )


def _unwrap(document: RotationObjectiveDocument):
    if isinstance(document, StateEvidenceTrace):
        reaction = document.reaction_evidence
        return (
            document.terminal_trace,
            {row.event_id: row.formula for row in reaction.reaction_hits},
            document.evidence_sha256,
            document.duration_frames,
        )
    if isinstance(document, ReactionEvidenceTrace):
        return (
            document.terminal_trace,
            {row.event_id: row.formula for row in document.reaction_hits},
            document.evidence_sha256,
            None,
        )
    if isinstance(document, TraceDocument):
        return document, {}, document.receipt.receipt_sha256, None
    raise TraceContractError(
        "document must be TraceDocument, ReactionEvidenceTrace, or StateEvidenceTrace"
    )


def _element_bonus_key(raw: str) -> str | None:
    value = raw.casefold()
    if value.startswith("element:"):
        value = value.split(":", 1)[1]
    value = {"physical": "phys", "phys": "phys"}.get(value, value)
    key = f"{value}%"
    return key if key in {
        "anemo%", "cryo%", "dendro%", "electro%", "geo%", "hydro%",
        "phys%", "pyro%",
    } else None


def _evaluate_ir_operator(operator: SourceIROperator, inputs: tuple[float, ...]) -> float:
    if operator is SourceIROperator.ADD:
        return inputs[0] + inputs[1]
    if operator is SourceIROperator.SUB:
        return inputs[0] - inputs[1]
    if operator is SourceIROperator.MUL:
        return inputs[0] * inputs[1]
    if operator is SourceIROperator.DIV:
        return inputs[0] / inputs[1]
    if operator is SourceIROperator.MIN:
        return min(inputs)
    if operator is SourceIROperator.MAX:
        return max(inputs)
    if operator is SourceIROperator.ABS:
        return abs(inputs[0])
    if operator is SourceIROperator.AND:
        return float(bool(inputs[0]) and bool(inputs[1]))
    if operator is SourceIROperator.OR:
        return float(bool(inputs[0]) or bool(inputs[1]))
    if operator is SourceIROperator.EQ:
        return float(inputs[0] == inputs[1])
    if operator is SourceIROperator.NE:
        return float(inputs[0] != inputs[1])
    if operator is SourceIROperator.LT:
        return float(inputs[0] < inputs[1])
    if operator is SourceIROperator.LE:
        return float(inputs[0] <= inputs[1])
    if operator is SourceIROperator.GT:
        return float(inputs[0] > inputs[1])
    if operator is SourceIROperator.GE:
        return float(inputs[0] >= inputs[1])
    if operator is SourceIROperator.NOT:
        return float(not bool(inputs[0]))
    if operator is SourceIROperator.SELECT:
        return inputs[1] if bool(inputs[0]) else inputs[2]
    raise TraceContractError(f"unsupported compact IR operator {operator.value!r}")


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-7)


__all__ = [
    "CompactDamageGroup",
    "CompactObjectiveScore",
    "CompactRotationObjective",
    "CompactTermKind",
    "ROTATION_OBJECTIVE_KIND",
    "ROTATION_OBJECTIVE_SCHEMA_VERSION",
    "compile_rotation_objective",
    "evaluate_rotation_objective",
]
