"""Expected-value ranking for artifact stat vectors under a frozen rotation.

This is deliberately separate from seeded replay.  Replay asks whether one
concrete engine path is reproduced exactly.  Ranking asks which absolute stat
vector is more promising.  It uses analytic crit expectation, keeps unknown
components at their observed baseline contribution, and reports uncertainty
without silently converting it into either zero value or hard pruning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import (
    DamageFormulaKind,
    ReactionOperator,
    ScalingKind,
    TraceContractError,
    TraceDocument,
    TraceHitEvent,
    canonical_sha256,
)
from .reaction_evidence import (
    ReactionEvidenceTrace,
    TransformativeReactionFormula,
)
from .source_dependencies import (
    SourceManifestEntry,
    SourceOutputKind,
    SourceParameterKind,
    SourceSliceStatus,
    SourceValueBinding,
    evaluate_source_template,
)
from .state_evidence import StateEvidenceTrace


RANKING_STAT_KEYS = frozenset(
    {
        "atk",
        "atk%",
        "hp",
        "hp%",
        "def",
        "def%",
        "em",
        "cr",
        "cd",
        "er",
        "heal",
        "dmg%",
        "anemo%",
        "cryo%",
        "dendro%",
        "electro%",
        "geo%",
        "hydro%",
        "phys%",
        "pyro%",
    }
)

_DIRECT_SCALING_KEYS = {
    ScalingKind.ATTACK: frozenset({"base_atk", "atk", "atk%"}),
    ScalingKind.HP: frozenset({"base_hp", "hp", "hp%"}),
    ScalingKind.DEFENSE: frozenset({"base_def", "def", "def%"}),
    ScalingKind.ELEMENTAL_MASTERY: frozenset({"em"}),
}


class RankingSupport(str, Enum):
    MODELED_EXPECTATION = "MODELED_EXPECTATION"
    BASELINE_FROZEN = "BASELINE_FROZEN"
    HEURISTIC = "HEURISTIC"
    UNSCORED = "UNSCORED"


class PruneSafety(str, Enum):
    """Hard-prune authority is pairwise and independent from numeric rank."""

    PROVEN_DOMINATED = "PROVEN_DOMINATED"
    KEEP = "KEEP"


@dataclass(frozen=True, slots=True)
class RankingStatValue:
    """One absolute candidate stat value, not a delta from the baseline."""

    actor_key: str
    stat_key: str
    value: float

    def __post_init__(self) -> None:
        _require_trimmed(self.actor_key, "actor_key")
        _require_trimmed(self.stat_key, "stat_key")
        if self.stat_key not in RANKING_STAT_KEYS:
            raise TraceContractError(
                f"ranking stat {self.stat_key!r} is unsupported by schema v1"
            )
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TraceContractError("ranking stat value must be numeric")
        if not math.isfinite(float(self.value)):
            raise TraceContractError("ranking stat value must be finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "value": float(self.value),
        }


@dataclass(frozen=True, slots=True)
class RankingStatDelta:
    """One candidate-minus-baseline artifact delta applied to every hit snapshot."""

    actor_key: str
    stat_key: str
    amount: float

    def __post_init__(self) -> None:
        _require_trimmed(self.actor_key, "actor_key")
        _require_trimmed(self.stat_key, "stat_key")
        if self.stat_key not in RANKING_STAT_KEYS:
            raise TraceContractError(
                f"ranking stat {self.stat_key!r} is unsupported by schema v1"
            )
        if isinstance(self.amount, bool) or not isinstance(
            self.amount, (int, float)
        ):
            raise TraceContractError("ranking stat delta must be numeric")
        if not math.isfinite(float(self.amount)):
            raise TraceContractError("ranking stat delta must be finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "amount": float(self.amount),
        }


@dataclass(frozen=True, slots=True)
class ExpectedHitEstimate:
    event_id: str
    actor_key: str
    baseline_score: float
    candidate_score: float
    support: RankingSupport
    uncertainty_codes: tuple[str, ...]

    @property
    def expected_delta(self) -> float:
        return self.candidate_score - self.baseline_score


@dataclass(frozen=True, slots=True)
class ExpectedRankingEstimate:
    """Shortlist signal only; never a publishable optimizer winner."""

    candidate_sha256: str
    baseline_score: float | None
    candidate_score: float | None
    expected_delta: float | None
    modeled_baseline_damage: float
    fixed_placeholder_damage: float
    modeled_hit_count: int
    total_hit_count: int
    support: RankingSupport
    prune_safety: PruneSafety
    uncertainty_codes: tuple[str, ...]
    hits: tuple[ExpectedHitEstimate, ...]

    @property
    def orderable(self) -> bool:
        return (
            self.candidate_score is not None
            and self.support
            in {RankingSupport.MODELED_EXPECTATION, RankingSupport.HEURISTIC}
        )

    @property
    def publishable(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class _SourceFlatDamageBinding:
    binding: SourceValueBinding
    entry: SourceManifestEntry


@dataclass(frozen=True, slots=True)
class _SourceFlatDamageEstimate:
    candidate_value: float
    consumed_by_actor: dict[str, frozenset[str]]
    uncertainty_codes: tuple[str, ...]


def estimate_candidate_expected_damage(
    document: TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace,
    values: tuple[RankingStatValue, ...],
    *,
    candidate_sha256: str | None = None,
) -> ExpectedRankingEstimate:
    """Score one absolute stat vector without invoking GCSIM.

    A partial finite score may order a shortlist.  This v1 function never emits
    ``PROVEN_DOMINATED``: formal pairwise Pareto/formula dominance is a later,
    separate certificate rather than a side effect of a heuristic score.
    """

    return _estimate_candidate_expected_damage(
        document,
        values,
        apply_deltas=False,
        candidate_sha256=candidate_sha256,
    )


def estimate_candidate_expected_damage_deltas(
    document: TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace,
    deltas: tuple[RankingStatDelta, ...],
    *,
    candidate_sha256: str | None = None,
) -> ExpectedRankingEstimate:
    """Score candidate-minus-baseline artifact deltas on observed hit snapshots.

    Unlike absolute replacement, the same delta is added to each hit's own
    effective snapshot. Time-varying buffs therefore remain distinct instead
    of being overwritten by one global displayed stat value.
    """

    return _estimate_candidate_expected_damage(
        document,
        deltas,
        apply_deltas=True,
        candidate_sha256=candidate_sha256,
    )


def _estimate_candidate_expected_damage(
    document: TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace,
    changes: tuple[RankingStatValue, ...] | tuple[RankingStatDelta, ...],
    *,
    apply_deltas: bool,
    candidate_sha256: str | None,
) -> ExpectedRankingEstimate:
    reaction_by_event: dict[str, TransformativeReactionFormula] = {}
    if isinstance(document, StateEvidenceTrace):
        reaction_by_event = {
            row.event_id: row.formula
            for row in document.reaction_evidence.reaction_hits
        }
        trace_document = document.terminal_trace
        ranking_contract = "expected_damage_observed_snapshot_v6"
        evidence_identity = document.evidence_sha256
    elif isinstance(document, ReactionEvidenceTrace):
        reaction_by_event = {
            row.event_id: row.formula for row in document.reaction_hits
        }
        trace_document = document.terminal_trace
        ranking_contract = "expected_damage_reaction_v3"
        evidence_identity = document.evidence_sha256
    elif isinstance(document, TraceDocument):
        trace_document = document
        ranking_contract = "expected_damage_v1"
        evidence_identity = document.receipt.receipt_sha256
    else:
        raise TraceContractError(
            "document must be TraceDocument, ReactionEvidenceTrace, or "
            "StateEvidenceTrace"
        )
    expected_type = RankingStatDelta if apply_deltas else RankingStatValue
    field_name = "ranking deltas" if apply_deltas else "ranking values"
    if not isinstance(changes, tuple):
        raise TraceContractError(f"{field_name} must be an immutable tuple")
    for row in changes:
        if not isinstance(row, expected_type):
            raise TraceContractError(
                f"every {field_name[:-1]} must be {expected_type.__name__}"
            )
    keys = tuple((row.actor_key, row.stat_key) for row in changes)
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise TraceContractError(
            f"{field_name} must be sorted by unique actor_key/stat_key"
        )
    unknown_actors = {row.actor_key for row in changes} - set(
        trace_document.request.character_keys
    )
    if unknown_actors:
        raise TraceContractError(
            f"unknown actor keys in ranking values: {sorted(unknown_actors)!r}"
        )
    if candidate_sha256 is None:
        candidate_sha256 = canonical_sha256(
            {
                "ranking_contract": ranking_contract,
                "evidence_sha256": evidence_identity,
                (
                    "stat_deltas"
                    if apply_deltas
                    else "absolute_stat_values"
                ): [row.to_dict() for row in changes],
            }
        )
    _require_sha256(candidate_sha256, "candidate_sha256")

    values_by_actor = {
        actor: {
            row.stat_key: float(row.amount if apply_deltas else row.value)
            for row in changes
            if row.actor_key == actor
        }
        for actor in {row.actor_key for row in changes}
    }
    changed_actors = set(values_by_actor)
    actors_with_hits = {hit.actor_key for hit in trace_document.hits} | {
        formula.owner_key for formula in reaction_by_event.values()
    }
    uncertainty: set[str] = set()
    uncertainty.update(
        f"actor_without_damage_hit:{actor}"
        for actor in sorted(changed_actors - actors_with_hits)
    )
    if len(actors_with_hits) > 1 and changed_actors:
        uncertainty.add("cross_actor_dependency_unresolved")
    if not trace_document.topology.complete:
        uncertainty.add("fixed_rotation_topology_assumed")
    source_flat_by_event = _source_flat_damage_bindings(document)

    estimates: list[ExpectedHitEstimate] = []
    modeled_baseline = 0.0
    fixed_placeholder = 0.0
    for hit in trace_document.hits:
        estimate = _estimate_hit(
            hit,
            values_by_actor,
            reaction_by_event.get(hit.event_id),
            apply_deltas=apply_deltas,
            source_flat_binding=source_flat_by_event.get(hit.event_id),
        )
        estimates.append(estimate)
        uncertainty.update(estimate.uncertainty_codes)
        if estimate.support is RankingSupport.MODELED_EXPECTATION:
            modeled_baseline += estimate.baseline_score
        else:
            fixed_placeholder += estimate.baseline_score

    baseline_score = sum(row.baseline_score for row in estimates)
    candidate_score = sum(row.candidate_score for row in estimates)
    finite = math.isfinite(baseline_score) and math.isfinite(candidate_score)
    modeled_count = sum(
        row.support is RankingSupport.MODELED_EXPECTATION for row in estimates
    )
    if not finite or not estimates:
        support = RankingSupport.UNSCORED
        baseline_result: float | None = None
        candidate_result: float | None = None
        delta_result: float | None = None
    else:
        baseline_result = baseline_score
        candidate_result = candidate_score
        delta_result = candidate_score - baseline_score
        if modeled_count == len(estimates) and not uncertainty:
            support = RankingSupport.MODELED_EXPECTATION
        elif modeled_count > 0:
            support = RankingSupport.HEURISTIC
        else:
            support = RankingSupport.BASELINE_FROZEN
    return ExpectedRankingEstimate(
        candidate_sha256=candidate_sha256,
        baseline_score=baseline_result,
        candidate_score=candidate_result,
        expected_delta=delta_result,
        modeled_baseline_damage=modeled_baseline,
        fixed_placeholder_damage=fixed_placeholder,
        modeled_hit_count=modeled_count,
        total_hit_count=len(estimates),
        support=support,
        prune_safety=PruneSafety.KEEP,
        uncertainty_codes=tuple(sorted(uncertainty)),
        hits=tuple(estimates),
    )


def _estimate_hit(
    hit: TraceHitEvent,
    candidate_values_by_actor: dict[str, dict[str, float]],
    reaction_formula: TransformativeReactionFormula | None = None,
    *,
    apply_deltas: bool = False,
    source_flat_binding: _SourceFlatDamageBinding | None = None,
) -> ExpectedHitEstimate:
    if reaction_formula is not None:
        return _estimate_transformative_hit(
            hit,
            candidate_values_by_actor,
            reaction_formula,
            apply_deltas=apply_deltas,
        )
    candidate_values = candidate_values_by_actor.get(hit.actor_key, {})
    uncertainties: set[str] = set()
    inputs = hit.formula_inputs
    operator = hit.lineage.known_reaction_operator
    if inputs.known_formula_kind is not DamageFormulaKind.NORMAL:
        uncertainties.add("formula_unmodeled")
    if operator not in {
        ReactionOperator.NONE,
        ReactionOperator.MULTIPLY_PARENT_HIT,
    }:
        uncertainties.add("reaction_operator_unmodeled")
    if operator is ReactionOperator.MULTIPLY_PARENT_HIT:
        uncertainties.add("reaction_schedule_assumed_fixed")
    if inputs.amplifying != (operator is ReactionOperator.MULTIPLY_PARENT_HIT):
        uncertainties.add("amplifying_operator_binding_inconsistent")

    modelable = (
        inputs.known_formula_kind is DamageFormulaKind.NORMAL
        and operator
        in {ReactionOperator.NONE, ReactionOperator.MULTIPLY_PARENT_HIT}
        and "amplifying_operator_binding_inconsistent" not in uncertainties
    )
    if not modelable:
        placeholder = float(hit.uncapped_rolled_damage)
        return ExpectedHitEstimate(
            event_id=hit.event_id,
            actor_key=hit.actor_key,
            baseline_score=placeholder,
            candidate_score=placeholder,
            support=RankingSupport.BASELINE_FROZEN,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )

    baseline_stats = {row.stat_key: row.value for row in inputs.snapshot_stats}
    candidate_stats = dict(baseline_stats)
    changed_keys: set[str] = set()
    for stat_key, value in candidate_values.items():
        if stat_key not in candidate_stats:
            uncertainties.add(f"stat_missing_from_snapshot:{stat_key}")
            continue
        candidate_value = candidate_stats[stat_key] + value if apply_deltas else value
        if not math.isclose(
            candidate_stats[stat_key],
            candidate_value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            changed_keys.add(stat_key)
        candidate_stats[stat_key] = candidate_value

    source_flat = _evaluate_source_flat_damage(
        source_flat_binding,
        hit,
        candidate_values_by_actor,
        apply_deltas=apply_deltas,
    )
    if source_flat is not None:
        uncertainties.update(source_flat.uncertainty_codes)

    consumed = set(_DIRECT_SCALING_KEYS[inputs.scaling_kind]) | {"cr", "cd", "dmg%"}
    element_bonus_key = _element_bonus_key(hit.element)
    if element_bonus_key is not None:
        consumed.add(element_bonus_key)
    if inputs.amplifying:
        consumed.add("em")
    if source_flat is not None:
        consumed.update(source_flat.consumed_by_actor.get(hit.actor_key, ()))
    uncertainty_stat_keys = changed_keys - consumed
    uncertainties.update(
        f"stat_not_consumed_by_direct_formula:{key}"
        for key in sorted(uncertainty_stat_keys)
    )
    if source_flat is None and inputs.flat_dmg.value != 0.0 and (
        changed_keys or not hit.completeness.flat_dmg_provenance_complete
    ):
        uncertainties.add("flat_damage_dependency_unresolved")
    multiplier_only_keys = {"cr", "cd", "dmg%"}
    if element_bonus_key is not None:
        multiplier_only_keys.add(element_bonus_key)
    unresolved_flat_reachable = (
        inputs.flat_dmg.value != 0.0
        and source_flat is None
        and not hit.completeness.flat_dmg_provenance_complete
        and bool(changed_keys - multiplier_only_keys)
    )
    if not hit.completeness.provider_identity_complete:
        uncertainties.add("provider_identity_incomplete")
    if any(
        code
        in {
            "multiplier_source_expression_not_instrumented",
            "attack_mod_closure_expression_collapsed",
            "flat_dmg_expression_collapsed",
        }
        for code in hit.unsupported_feature_codes
    ):
        uncertainties.add("coefficient_or_modifier_dependency_unresolved")

    baseline_or_reason = _expected_normal_damage(
        hit,
        baseline_stats,
        damage_bonus=inputs.dmg_bonus.value,
    )
    if unresolved_flat_reachable:
        placeholder = (
            float(hit.uncapped_rolled_damage)
            if isinstance(baseline_or_reason, str)
            else baseline_or_reason
        )
        return ExpectedHitEstimate(
            event_id=hit.event_id,
            actor_key=hit.actor_key,
            baseline_score=placeholder,
            candidate_score=placeholder,
            support=RankingSupport.BASELINE_FROZEN,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )
    candidate_damage_bonus = inputs.dmg_bonus.value
    if "dmg%" in changed_keys:
        candidate_damage_bonus += (
            candidate_stats["dmg%"] - baseline_stats["dmg%"]
        )
    if element_bonus_key is not None and element_bonus_key in changed_keys:
        candidate_damage_bonus += (
            candidate_stats[element_bonus_key]
            - baseline_stats[element_bonus_key]
        )
    candidate_or_reason = _expected_normal_damage(
        hit,
        candidate_stats,
        damage_bonus=candidate_damage_bonus,
        flat_damage=(
            None if source_flat is None else source_flat.candidate_value
        ),
    )
    if isinstance(baseline_or_reason, str) or isinstance(candidate_or_reason, str):
        uncertainties.add(
            baseline_or_reason
            if isinstance(baseline_or_reason, str)
            else candidate_or_reason
        )
        placeholder = float(hit.uncapped_rolled_damage)
        return ExpectedHitEstimate(
            event_id=hit.event_id,
            actor_key=hit.actor_key,
            baseline_score=placeholder,
            candidate_score=placeholder,
            support=RankingSupport.BASELINE_FROZEN,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )
    return ExpectedHitEstimate(
        event_id=hit.event_id,
        actor_key=hit.actor_key,
        baseline_score=baseline_or_reason,
        candidate_score=candidate_or_reason,
        support=RankingSupport.MODELED_EXPECTATION,
        uncertainty_codes=tuple(sorted(uncertainties)),
    )


def _estimate_transformative_hit(
    hit: TraceHitEvent,
    candidate_values_by_actor: dict[str, dict[str, float]],
    formula: TransformativeReactionFormula,
    *,
    apply_deltas: bool = False,
) -> ExpectedHitEstimate:
    """Evaluate one already-observed transformative child attack.

    Only the explicit construction owner supplies candidate EM.  The observed
    occurrence, target, reaction bonus, terminal callback state and schedule
    remain frozen and are reported as uncertainty rather than prune authority.
    """

    uncertainties: set[str] = {"reaction_schedule_assumed_fixed"}
    if not formula.parent_occurrence_resolved:
        uncertainties.add("reaction_parent_occurrence_unresolved")
    if (
        not math.isclose(formula.reaction_bonus, 0.0, abs_tol=1e-12)
        or formula.reaction_bonus_contributions
    ):
        uncertainties.add("reaction_bonus_dependency_frozen")
    if any(
        not row.provider.known
        for row in formula.reaction_bonus_contributions
    ):
        uncertainties.add("reaction_bonus_provider_unknown")
    operator = hit.lineage.known_reaction_operator
    if operator is not ReactionOperator.SPAWN_DAMAGE_ATTACK:
        uncertainties.add("reaction_operator_binding_inconsistent")
    if formula.operator is not ReactionOperator.SPAWN_DAMAGE_ATTACK:
        uncertainties.add("reaction_formula_operator_unknown")
    if not formula.formula_known:
        uncertainties.add("reaction_formula_identity_unknown")
    if not formula.construction_consistent:
        uncertainties.add("reaction_construction_receipt_mismatch")
    if not math.isclose(
        hit.formula_inputs.flat_dmg.value,
        formula.constructed_flat_damage,
        rel_tol=1e-9,
        abs_tol=1e-7,
    ):
        uncertainties.add("reaction_flat_damage_modified_after_construction")
    if hit.formula_inputs.known_formula_kind is not DamageFormulaKind.NORMAL:
        uncertainties.add("reaction_terminal_formula_unmodeled")
    if not hit.completeness.provider_identity_complete:
        uncertainties.add("provider_identity_incomplete")

    blocking = {
        "reaction_operator_binding_inconsistent",
        "reaction_formula_operator_unknown",
        "reaction_formula_identity_unknown",
        "reaction_construction_receipt_mismatch",
        "reaction_flat_damage_modified_after_construction",
        "reaction_terminal_formula_unmodeled",
    }
    if uncertainties & blocking:
        placeholder = float(hit.uncapped_rolled_damage)
        return ExpectedHitEstimate(
            event_id=hit.event_id,
            actor_key=formula.owner_key,
            baseline_score=placeholder,
            candidate_score=placeholder,
            support=RankingSupport.BASELINE_FROZEN,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )

    candidate_em = formula.elemental_mastery
    owner_values = candidate_values_by_actor.get(formula.owner_key, {})
    if "em" in owner_values:
        candidate_em = (
            candidate_em + owner_values["em"]
            if apply_deltas
            else owner_values["em"]
        )
    baseline_or_reason = _expected_transformative_damage(
        hit,
        formula,
        elemental_mastery=formula.elemental_mastery,
    )
    candidate_or_reason = _expected_transformative_damage(
        hit,
        formula,
        elemental_mastery=candidate_em,
    )
    if isinstance(baseline_or_reason, str) or isinstance(candidate_or_reason, str):
        uncertainties.add(
            baseline_or_reason
            if isinstance(baseline_or_reason, str)
            else candidate_or_reason
        )
        placeholder = float(hit.uncapped_rolled_damage)
        return ExpectedHitEstimate(
            event_id=hit.event_id,
            actor_key=formula.owner_key,
            baseline_score=placeholder,
            candidate_score=placeholder,
            support=RankingSupport.BASELINE_FROZEN,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )
    return ExpectedHitEstimate(
        event_id=hit.event_id,
        actor_key=formula.owner_key,
        baseline_score=baseline_or_reason,
        candidate_score=candidate_or_reason,
        support=RankingSupport.MODELED_EXPECTATION,
        uncertainty_codes=tuple(sorted(uncertainties)),
    )


def _expected_transformative_damage(
    hit: TraceHitEvent,
    formula: TransformativeReactionFormula,
    *,
    elemental_mastery: float,
) -> float | str:
    denominator = formula.em_curve_denominator_offset + elemental_mastery
    if denominator <= 0.0:
        return "em_formula_domain_crossed"
    core_damage = formula.level_base * (
        1.0
        + formula.em_curve_numerator * elemental_mastery / denominator
        + formula.reaction_bonus
    )
    damage = formula.coefficient * core_damage
    inputs = hit.formula_inputs
    damage *= 1.0 + inputs.dmg_bonus.value
    damage *= inputs.defense_multiplier.value
    damage *= inputs.resistance_multiplier.value
    raw_cr = inputs.raw_crit_rate.value
    crit_damage = inputs.crit_damage.value
    useful_cr = max(0.0, min(1.0, raw_cr))
    expected_crit = (
        1.0 + crit_damage
        if inputs.hit_weak_point
        else 1.0 + useful_cr * crit_damage
    )
    damage *= expected_crit
    damage *= inputs.group_multiplier.value
    damage *= inputs.elevation_multiplier.value
    if not math.isfinite(damage):
        return "nonfinite_expected_damage"
    return damage


def _expected_normal_damage(
    hit: TraceHitEvent,
    stats: dict[str, float],
    *,
    damage_bonus: float,
    flat_damage: float | None = None,
) -> float | str:
    inputs = hit.formula_inputs
    scaling = _scaling_value(inputs.scaling_kind, stats)
    if isinstance(scaling, str):
        return scaling
    raw_cr = _stat(stats, "cr")
    cd = _stat(stats, "cd")
    if isinstance(raw_cr, str):
        return raw_cr
    if isinstance(cd, str):
        return cd
    useful_cr = max(0.0, min(1.0, raw_cr))
    expected_crit = 1.0 + cd if inputs.hit_weak_point else 1.0 + useful_cr * cd
    base_damage = (
        inputs.mult.value
        * scaling
        * (1.0 + inputs.base_dmg_bonus.value)
        + (inputs.flat_dmg.value if flat_damage is None else flat_damage)
    )
    damage = base_damage * (1.0 + damage_bonus)
    damage *= inputs.defense_multiplier.value
    damage *= inputs.resistance_multiplier.value
    damage *= expected_crit
    if inputs.amplifying:
        em = _stat(stats, "em")
        if isinstance(em, str):
            return em
        if em <= -1400.0:
            return "em_formula_domain_crossed"
        em_bonus = (2.78 * em) / (1400.0 + em)
        damage *= inputs.amp_multiplier.value * (
            1.0 + em_bonus + inputs.reaction_bonus.value
        )
    damage *= inputs.group_multiplier.value
    damage *= inputs.elevation_multiplier.value
    if not math.isfinite(damage):
        return "nonfinite_expected_damage"
    return damage


def _source_flat_damage_bindings(
    document: TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace,
) -> dict[str, _SourceFlatDamageBinding]:
    if not isinstance(document, StateEvidenceTrace):
        return {}
    occurrence_by_id = {row.occurrence_id: row for row in document.occurrences}
    result: dict[str, _SourceFlatDamageBinding] = {}
    for binding in document.value_bindings:
        if (
            binding.output_kind is not SourceOutputKind.TERMINAL_FLAT_DMG
            or binding.terminal_event_id is None
        ):
            continue
        occurrence = occurrence_by_id[binding.occurrence_id]
        entry = document.source_manifest_binding.manifest_body.entry_by_id(
            occurrence.source_id
        )
        assert entry is not None
        result[binding.terminal_event_id] = _SourceFlatDamageBinding(binding, entry)
    return result


def _evaluate_source_flat_damage(
    source: _SourceFlatDamageBinding | None,
    hit: TraceHitEvent,
    candidate_values_by_actor: dict[str, dict[str, float]],
    *,
    apply_deltas: bool,
) -> _SourceFlatDamageEstimate | None:
    if source is None or source.entry.template.status is SourceSliceStatus.OPAQUE_FROZEN:
        return None
    snapshot = {row.stat_key: row.value for row in hit.formula_inputs.snapshot_stats}
    values: dict[str, float] = {}
    consumed: dict[str, set[str]] = {}
    uncertainties: set[str] = set()
    any_change = any(candidate_values_by_actor.values())
    for parameter in source.binding.parameters:
        value = parameter.observed_value
        if parameter.kind is SourceParameterKind.CANDIDATE_STAT:
            assert parameter.actor_key is not None and parameter.stat_key is not None
            actor_values = candidate_values_by_actor.get(parameter.actor_key, {})
            value, used = _source_parameter_candidate_value(
                parameter.observed_value,
                parameter.stat_key,
                actor_values,
                snapshot if parameter.actor_key == hit.actor_key else None,
                apply_deltas=apply_deltas,
            )
            if used:
                consumed.setdefault(parameter.actor_key, set()).update(used)
        elif (
            parameter.kind is SourceParameterKind.FROZEN_RUNTIME_STATE
            and not parameter.candidate_dependency_complete
            and any_change
        ):
            uncertainties.add(
                f"frozen_runtime_state_dependency_unresolved:{parameter.parameter_key}"
            )
        values[parameter.parameter_key] = value
    candidate = evaluate_source_template(source.entry.template, values)
    return _SourceFlatDamageEstimate(
        candidate_value=candidate,
        consumed_by_actor={
            actor: frozenset(keys) for actor, keys in consumed.items()
        },
        uncertainty_codes=tuple(sorted(uncertainties)),
    )


def _source_parameter_candidate_value(
    observed_value: float,
    parameter_stat_key: str,
    actor_values: dict[str, float],
    snapshot: dict[str, float] | None,
    *,
    apply_deltas: bool,
) -> tuple[float, frozenset[str]]:
    if not actor_values:
        return observed_value, frozenset()
    derived = {
        "max_hp": ("base_hp", "hp%", "hp"),
        "total_atk": ("base_atk", "atk%", "atk"),
        "total_def": ("base_def", "def%", "def"),
    }.get(parameter_stat_key)
    if derived is None:
        if parameter_stat_key not in actor_values:
            return observed_value, frozenset()
        candidate = actor_values[parameter_stat_key]
        if apply_deltas:
            candidate += observed_value
        return candidate, frozenset({parameter_stat_key})
    base_key, percent_key, flat_key = derived
    used = frozenset(key for key in (percent_key, flat_key) if key in actor_values)
    if not used:
        return observed_value, frozenset()
    if apply_deltas:
        if snapshot is None:
            return observed_value, frozenset()
        delta = snapshot[base_key] * actor_values.get(percent_key, 0.0)
        delta += actor_values.get(flat_key, 0.0)
        return observed_value + delta, used
    if snapshot is None:
        return observed_value, frozenset()
    percent = actor_values.get(percent_key, snapshot[percent_key])
    flat = actor_values.get(flat_key, snapshot[flat_key])
    return snapshot[base_key] * (1.0 + percent) + flat, used


def _scaling_value(kind: ScalingKind, stats: dict[str, float]) -> float | str:
    if kind is ScalingKind.ELEMENTAL_MASTERY:
        return _stat(stats, "em")
    prefix = {
        ScalingKind.ATTACK: "atk",
        ScalingKind.HP: "hp",
        ScalingKind.DEFENSE: "def",
    }.get(kind)
    if prefix is None:
        return "unknown_scaling_kind"
    base = _stat(stats, f"base_{prefix}")
    flat = _stat(stats, prefix)
    percent = _stat(stats, f"{prefix}%")
    if isinstance(base, str):
        return base
    if isinstance(flat, str):
        return flat
    if isinstance(percent, str):
        return percent
    return base * (1.0 + percent) + flat


def _element_bonus_key(raw: str) -> str | None:
    value = raw.casefold()
    if value.startswith("element:"):
        value = value.split(":", 1)[1]
    value = {"physical": "phys", "phys": "phys"}.get(value, value)
    key = f"{value}%"
    return key if key in RANKING_STAT_KEYS else None


def _stat(stats: dict[str, float], key: str) -> float | str:
    if key not in stats:
        return f"stat_missing_from_hit:{key}"
    value = stats[key]
    if not math.isfinite(value):
        return f"nonfinite_stat:{key}"
    return value


def _require_trimmed(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{field_name} must be a non-empty trimmed string")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise TraceContractError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "ExpectedHitEstimate",
    "ExpectedRankingEstimate",
    "PruneSafety",
    "RANKING_STAT_KEYS",
    "RankingStatDelta",
    "RankingStatValue",
    "RankingSupport",
    "estimate_candidate_expected_damage",
    "estimate_candidate_expected_damage_deltas",
]
