"""Diagnostic offline scoring over effective per-hit snapshots.

One accepted trace supplies the fixed hit/reaction schedule and each hit's
effective stat vector. Candidate artifacts are represented as replacement
contributions; only candidate-minus-baseline deltas are added to each hit's own
snapshot. The result is a shortlist diagnostic, never prune or publication
authority, and this module contains no engine runner or candidate enumeration.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .contracts import TraceContractError, TraceDocument, TraceHitEvent, canonical_sha256
from .ranking import (
    ExpectedHitEstimate,
    ExpectedRankingEstimate,
    RankingStatDelta,
    RankingSupport,
    estimate_candidate_expected_damage_deltas,
)
from .reaction_evidence import ReactionEvidenceTrace, TransformativeReactionFormula
from .state_evidence import StateEvidenceTrace


ObservedRankingDocument = TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace


@dataclass(frozen=True, slots=True)
class ArtifactStatReplacement:
    """One baseline artifact contribution replaced by a candidate contribution."""

    actor_key: str
    stat_key: str
    baseline_artifact_value: float
    candidate_artifact_value: float

    def __post_init__(self) -> None:
        _trimmed(self.actor_key, "actor_key")
        _trimmed(self.stat_key, "stat_key")
        _finite(self.baseline_artifact_value, "baseline_artifact_value")
        _finite(self.candidate_artifact_value, "candidate_artifact_value")
        # Reuse the ranking delta contract as the canonical stat allowlist.
        RankingStatDelta(self.actor_key, self.stat_key, self.delta)

    @property
    def delta(self) -> float:
        return float(self.candidate_artifact_value) - float(
            self.baseline_artifact_value
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "baseline_artifact_value": float(self.baseline_artifact_value),
            "candidate_artifact_value": float(self.candidate_artifact_value),
            "delta": self.delta,
        }


@dataclass(frozen=True, slots=True)
class ObservedFormulaGroup:
    group_sha256: str
    actor_key: str
    element: str
    event_ids: tuple[str, ...]
    multiplicity: int
    baseline_score: float
    candidate_score: float
    support: RankingSupport
    uncertainty_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _sha256(self.group_sha256, "group_sha256")
        _trimmed(self.actor_key, "actor_key")
        _trimmed(self.element, "element")
        if not self.event_ids or len(self.event_ids) != self.multiplicity:
            raise TraceContractError(
                "observed formula group multiplicity must match non-empty event_ids"
            )
        if len(self.event_ids) != len(set(self.event_ids)):
            raise TraceContractError("observed formula group event_ids must be unique")
        _finite(self.baseline_score, "group baseline_score")
        _finite(self.candidate_score, "group candidate_score")
        if not isinstance(self.support, RankingSupport):
            raise TraceContractError("observed formula group support is invalid")
        if tuple(sorted(set(self.uncertainty_codes))) != self.uncertainty_codes:
            raise TraceContractError(
                "observed formula group uncertainty_codes must be sorted and unique"
            )


@dataclass(frozen=True, slots=True)
class ObservedSnapshotScore:
    evidence_sha256: str
    candidate_sha256: str
    ranking: ExpectedRankingEstimate
    groups: tuple[ObservedFormulaGroup, ...]
    grouped_baseline_score: float | None
    grouped_candidate_score: float | None
    grouping_preserves_scores: bool
    duration_frames: int | None
    baseline_expected_dps: float | None
    candidate_expected_dps: float | None
    modeled_baseline_share: float
    frozen_baseline_share: float
    engine_call_count: int = 0
    authoritative: bool = False

    def __post_init__(self) -> None:
        _sha256(self.evidence_sha256, "evidence_sha256")
        _sha256(self.candidate_sha256, "candidate_sha256")
        if self.candidate_sha256 != self.ranking.candidate_sha256:
            raise TraceContractError(
                "observed score candidate identity must match ranking identity"
            )
        if self.engine_call_count != 0:
            raise TraceContractError("observed snapshot scoring must use zero engine calls")
        if self.authoritative:
            raise TraceContractError(
                "observed snapshot score cannot grant authoritative result"
            )
        for value, name in (
            (self.modeled_baseline_share, "modeled_baseline_share"),
            (self.frozen_baseline_share, "frozen_baseline_share"),
        ):
            _finite(value, name)
            if value < 0.0 or value > 1.0:
                raise TraceContractError(f"{name} must be in [0, 1]")
        if not math.isclose(
            self.modeled_baseline_share + self.frozen_baseline_share,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise TraceContractError("modeled and frozen baseline shares must sum to 1")
        if not self.grouping_preserves_scores:
            raise TraceContractError("observed formula grouping changed score totals")
        if self.duration_frames is None:
            if (
                self.baseline_expected_dps is not None
                or self.candidate_expected_dps is not None
            ):
                raise TraceContractError("DPS requires an observed rotation duration")
        else:
            if (
                isinstance(self.duration_frames, bool)
                or not isinstance(self.duration_frames, int)
                or self.duration_frames <= 0
            ):
                raise TraceContractError("duration_frames must be a positive integer")
            if self.ranking.baseline_score is None or self.ranking.candidate_score is None:
                raise TraceContractError("DPS requires finite ranking totals")
            _finite(self.baseline_expected_dps, "baseline_expected_dps")
            _finite(self.candidate_expected_dps, "candidate_expected_dps")
            if not math.isclose(
                self.baseline_expected_dps,
                self.ranking.baseline_score * 60.0 / self.duration_frames,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ) or not math.isclose(
                self.candidate_expected_dps,
                self.ranking.candidate_score * 60.0 / self.duration_frames,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise TraceContractError("observed DPS does not match damage/duration")

    @property
    def publishable(self) -> bool:
        return False


def score_observed_artifact_replacement(
    document: ObservedRankingDocument,
    replacements: tuple[ArtifactStatReplacement, ...],
) -> ObservedSnapshotScore:
    """Score artifact replacement deltas and audit lossless formula grouping."""

    if not isinstance(replacements, tuple):
        raise TraceContractError("artifact replacements must be an immutable tuple")
    if any(not isinstance(row, ArtifactStatReplacement) for row in replacements):
        raise TraceContractError(
            "every artifact replacement must be ArtifactStatReplacement"
        )
    keys = tuple((row.actor_key, row.stat_key) for row in replacements)
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise TraceContractError(
            "artifact replacements must be sorted by unique actor_key/stat_key"
        )

    trace_document, reaction_by_event, evidence_sha256, duration_frames = _unwrap(
        document
    )
    candidate_sha256 = canonical_sha256(
        {
            "kind": "gtt.observed_snapshot_artifact_replacement.v1",
            "evidence_sha256": evidence_sha256,
            "replacements": [row.to_dict() for row in replacements],
        }
    )
    deltas = tuple(
        RankingStatDelta(row.actor_key, row.stat_key, row.delta)
        for row in replacements
    )
    ranking = estimate_candidate_expected_damage_deltas(
        document,
        deltas,
        candidate_sha256=candidate_sha256,
    )
    groups = _group_hits(
        trace_document,
        ranking.hits,
        reaction_by_event,
    )
    grouped_baseline = (
        sum(group.baseline_score for group in groups)
        if ranking.baseline_score is not None
        else None
    )
    grouped_candidate = (
        sum(group.candidate_score for group in groups)
        if ranking.candidate_score is not None
        else None
    )
    grouping_preserves = _optional_close(
        grouped_baseline, ranking.baseline_score
    ) and _optional_close(grouped_candidate, ranking.candidate_score)
    baseline_mass = (
        ranking.modeled_baseline_damage + ranking.fixed_placeholder_damage
    )
    if baseline_mass > 0.0:
        modeled_share = ranking.modeled_baseline_damage / baseline_mass
        frozen_share = ranking.fixed_placeholder_damage / baseline_mass
    else:
        modeled_share = 0.0
        frozen_share = 1.0
    baseline_dps = (
        None
        if duration_frames is None or ranking.baseline_score is None
        else ranking.baseline_score * 60.0 / duration_frames
    )
    candidate_dps = (
        None
        if duration_frames is None or ranking.candidate_score is None
        else ranking.candidate_score * 60.0 / duration_frames
    )
    return ObservedSnapshotScore(
        evidence_sha256=evidence_sha256,
        candidate_sha256=candidate_sha256,
        ranking=ranking,
        groups=groups,
        grouped_baseline_score=grouped_baseline,
        grouped_candidate_score=grouped_candidate,
        grouping_preserves_scores=grouping_preserves,
        duration_frames=duration_frames,
        baseline_expected_dps=baseline_dps,
        candidate_expected_dps=candidate_dps,
        modeled_baseline_share=modeled_share,
        frozen_baseline_share=frozen_share,
    )


def _unwrap(
    document: ObservedRankingDocument,
) -> tuple[
    TraceDocument,
    dict[str, TransformativeReactionFormula],
    str,
    int | None,
]:
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


def _group_hits(
    document: TraceDocument,
    estimates: tuple[ExpectedHitEstimate, ...],
    reaction_by_event: dict[str, TransformativeReactionFormula],
) -> tuple[ObservedFormulaGroup, ...]:
    if len(document.hits) != len(estimates):
        raise TraceContractError("ranking hit count does not match trace hit count")
    grouped: dict[str, list[tuple[TraceHitEvent, ExpectedHitEstimate]]] = {}
    for hit, estimate in zip(document.hits, estimates, strict=True):
        signature = _formula_group_sha256(
            hit,
            estimate,
            reaction_by_event.get(hit.event_id),
        )
        grouped.setdefault(signature, []).append((hit, estimate))

    result: list[ObservedFormulaGroup] = []
    for signature, rows in grouped.items():
        first_hit, first_estimate = rows[0]
        if any(
            estimate.actor_key != first_estimate.actor_key
            or estimate.support is not first_estimate.support
            or estimate.uncertainty_codes != first_estimate.uncertainty_codes
            for _, estimate in rows[1:]
        ):
            raise TraceContractError("formula grouping merged incompatible estimates")
        result.append(
            ObservedFormulaGroup(
                group_sha256=signature,
                actor_key=first_estimate.actor_key,
                element=first_hit.element,
                event_ids=tuple(hit.event_id for hit, _ in rows),
                multiplicity=len(rows),
                baseline_score=sum(row.baseline_score for _, row in rows),
                candidate_score=sum(row.candidate_score for _, row in rows),
                support=first_estimate.support,
                uncertainty_codes=first_estimate.uncertainty_codes,
            )
        )
    return tuple(sorted(result, key=lambda row: row.group_sha256))


def _formula_group_sha256(
    hit: TraceHitEvent,
    estimate: ExpectedHitEstimate,
    reaction_formula: TransformativeReactionFormula | None,
) -> str:
    inputs = hit.formula_inputs
    return canonical_sha256(
        {
            "kind": "gtt.observed_formula_group.v1",
            "actor_key": hit.actor_key,
            "target_key": hit.target_key,
            "target_index": hit.target_index,
            "element": hit.element,
            "damage_mode": hit.damage_mode.value,
            "hp_cap_active": hit.hp_cap_active,
            "formula_kind": inputs.formula_kind,
            "formula_sha256": inputs.formula_sha256,
            "scaling_kind": inputs.scaling_kind.value,
            "snapshot_stats": {
                row.stat_key: row.value for row in inputs.snapshot_stats
            },
            "mult": inputs.mult.value,
            "base_dmg_bonus": inputs.base_dmg_bonus.value,
            "flat_dmg": inputs.flat_dmg.value,
            "dmg_bonus": inputs.dmg_bonus.value,
            "raw_crit_rate": inputs.raw_crit_rate.value,
            "crit_damage": inputs.crit_damage.value,
            "hit_weak_point": inputs.hit_weak_point,
            "defense_multiplier": inputs.defense_multiplier.value,
            "resistance_multiplier": inputs.resistance_multiplier.value,
            "amplifying": inputs.amplifying,
            "amp_multiplier": inputs.amp_multiplier.value,
            "reaction_bonus": inputs.reaction_bonus.value,
            "group_multiplier": inputs.group_multiplier.value,
            "elevation_multiplier": inputs.elevation_multiplier.value,
            "reaction_operator": hit.lineage.reaction_operator_id,
            "reaction_type": hit.lineage.reaction_type,
            "transformative_formula": (
                None if reaction_formula is None else reaction_formula.to_dict()
            ),
            "formula_replay_status": hit.formula_replay_status.value,
            "formula_replay_reasons": list(hit.formula_replay_reason_codes),
            "unsupported": list(hit.unsupported_feature_codes),
            "ranking_support": estimate.support.value,
            "ranking_uncertainty": list(estimate.uncertainty_codes),
            "baseline_score": estimate.baseline_score,
            "candidate_score": estimate.candidate_score,
        }
    )


def _optional_close(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-7)


def _trimmed(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{field_name} must be a non-empty trimmed string")


def _finite(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{field_name} must be finite")


def _sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise TraceContractError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "ArtifactStatReplacement",
    "ObservedFormulaGroup",
    "ObservedSnapshotScore",
    "score_observed_artifact_replacement",
]
