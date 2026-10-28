"""Typed reaction-construction evidence layered over the frozen v1/v2 trace.

The terminal :class:`TraceDocument` remains unchanged.  This module carries the
construction receipt that the engine previously collapsed into ``FlatDmg``.
It is sufficient for same-topology expected-value ranking, but deliberately
does not claim that a candidate preserves reaction count, owner, aura, target,
or timing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .contracts import (
    ReactionOperator,
    TraceContractError,
    ValueReadMode,
    canonical_sha256,
)
from .provider_evidence import (
    ProviderEvidenceTrace,
    ProviderReactionBonusContribution,
)


REACTION_EVIDENCE_SCHEMA_VERSION = 3
REACTION_EVIDENCE_KIND = "gtt.trace_equation.reaction_evidence"
TRANSFORMATIVE_REACTION_FORMULA_ID = "gtt_transformative_reaction_v1"
TRANSFORMATIVE_REACTION_FORMULA_SHA256 = hashlib.sha256(
    TRANSFORMATIVE_REACTION_FORMULA_ID.encode("utf-8")
).hexdigest()

_REL_TOL = 1e-9
_ABS_TOL = 1e-7


@dataclass(frozen=True, slots=True)
class TransformativeReactionFormula:
    formula_id: str
    formula_sha256: str
    reaction_type: str
    operator: ReactionOperator
    owner_index: int
    owner_key: str
    read_frame: int
    read_mode: ValueReadMode
    read_phase: str
    level: int
    level_base: float
    elemental_mastery: float
    em_curve_numerator: float
    em_curve_denominator_offset: float
    reaction_bonus: float
    reaction_bonus_contributions: tuple[
        ProviderReactionBonusContribution, ...
    ]
    core_damage: float
    coefficient: float
    constructed_flat_damage: float
    parent_attack_id: int
    parent_target_key: int
    parent_occurrence_resolved: bool
    aura_source_indices: tuple[int, ...]
    aura_source_keys: tuple[str, ...]
    child_role: str
    child_ordinal: int
    persistent_state_id: str | None
    persistent_revision: int | None
    gadget_id: str | None
    gadget_creator_index: int | None
    gadget_creator_key: str | None
    gadget_converter_index: int | None
    gadget_converter_key: str | None
    gadget_resolution_reason: str | None

    def __post_init__(self) -> None:
        _trimmed(self.formula_id, "formula_id")
        _sha256(self.formula_sha256, "formula_sha256")
        _trimmed(self.reaction_type, "reaction_type")
        if not isinstance(self.operator, ReactionOperator):
            raise TraceContractError("operator must be ReactionOperator")
        if self.operator not in {
            ReactionOperator.SPAWN_DAMAGE_ATTACK,
            ReactionOperator.OPAQUE_CUSTOM,
        }:
            raise TraceContractError(
                "transformative v1 requires spawn_damage_attack or opaque fallback"
            )
        _nonnegative_int(self.owner_index, "owner_index")
        _trimmed(self.owner_key, "owner_key")
        _nonnegative_int(self.read_frame, "read_frame")
        if not isinstance(self.read_mode, ValueReadMode):
            raise TraceContractError("read_mode must be ValueReadMode")
        if self.read_mode not in {ValueReadMode.LIVE, ValueReadMode.SNAPSHOT}:
            raise TraceContractError("reaction read_mode must be live or snapshot")
        _trimmed(self.read_phase, "read_phase")
        _positive_int(self.level, "level")
        for name in (
            "level_base",
            "elemental_mastery",
            "em_curve_numerator",
            "em_curve_denominator_offset",
            "reaction_bonus",
            "core_damage",
            "coefficient",
            "constructed_flat_damage",
        ):
            _finite(getattr(self, name), name)
        if self.level_base <= 0.0:
            raise TraceContractError("level_base must be positive")
        if self.em_curve_numerator <= 0.0:
            raise TraceContractError("em_curve_numerator must be positive")
        if self.em_curve_denominator_offset <= 0.0:
            raise TraceContractError(
                "em_curve_denominator_offset must be positive"
            )
        if self.coefficient < 0.0 or self.constructed_flat_damage < 0.0:
            raise TraceContractError(
                "reaction coefficient and constructed damage must be non-negative"
            )
        if not isinstance(self.reaction_bonus_contributions, tuple):
            raise TraceContractError(
                "reaction_bonus_contributions must be an immutable tuple"
            )
        if any(
            not isinstance(row, ProviderReactionBonusContribution)
            for row in self.reaction_bonus_contributions
        ):
            raise TraceContractError("invalid reaction bonus contribution")
        expected_sequence = tuple(range(len(self.reaction_bonus_contributions)))
        actual_sequence = tuple(
            row.sequence_index for row in self.reaction_bonus_contributions
        )
        if actual_sequence != expected_sequence:
            raise TraceContractError(
                "reaction bonus contribution sequence must be contiguous"
            )
        _positive_int(self.parent_attack_id, "parent_attack_id")
        _nonnegative_int(self.parent_target_key, "parent_target_key")
        if not isinstance(self.parent_occurrence_resolved, bool):
            raise TraceContractError("parent_occurrence_resolved must be boolean")
        _sorted_unique_nonnegative(
            self.aura_source_indices, "aura_source_indices"
        )
        if len(self.aura_source_indices) != len(self.aura_source_keys):
            raise TraceContractError("aura source indices/keys length mismatch")
        if any(not isinstance(value, str) or not value for value in self.aura_source_keys):
            raise TraceContractError("aura_source_keys must contain non-empty strings")
        _trimmed(self.child_role, "child_role")
        _nonnegative_int(self.child_ordinal, "child_ordinal")
        persistent_present = self.persistent_state_id is not None
        if persistent_present != (self.persistent_revision is not None):
            raise TraceContractError(
                "persistent state id and persistent revision must appear together"
            )
        if self.persistent_state_id is not None:
            _trimmed(self.persistent_state_id, "persistent_state_id")
            _positive_int(self.persistent_revision, "persistent_revision")
        gadget_related = (
            self.gadget_creator_index,
            self.gadget_creator_key,
            self.gadget_converter_index,
            self.gadget_converter_key,
            self.gadget_resolution_reason,
        )
        if self.gadget_id is None:
            if any(value is not None for value in gadget_related):
                raise TraceContractError(
                    "gadget lineage fields require gadget_id"
                )
        else:
            _trimmed(self.gadget_id, "gadget_id")
            if self.gadget_creator_index is None or self.gadget_creator_key is None:
                raise TraceContractError("gadget lineage requires creator")
            _nonnegative_int(self.gadget_creator_index, "gadget_creator_index")
            _trimmed(self.gadget_creator_key, "gadget_creator_key")
            if (self.gadget_converter_index is None) is not (
                self.gadget_converter_key is None
            ):
                raise TraceContractError(
                    "gadget converter index/key must appear together"
                )
            if self.gadget_converter_index is not None:
                _nonnegative_int(
                    self.gadget_converter_index, "gadget_converter_index"
                )
                _trimmed(self.gadget_converter_key, "gadget_converter_key")
            if self.gadget_resolution_reason is None:
                raise TraceContractError("gadget lineage requires resolution reason")
            _trimmed(
                self.gadget_resolution_reason, "gadget_resolution_reason"
            )

    @property
    def formula_known(self) -> bool:
        return (
            self.formula_id == TRANSFORMATIVE_REACTION_FORMULA_ID
            and self.formula_sha256
            == TRANSFORMATIVE_REACTION_FORMULA_SHA256
        )

    @property
    def construction_consistent(self) -> bool:
        denominator = self.em_curve_denominator_offset + self.elemental_mastery
        if denominator <= 0.0:
            return False
        expected_core = self.level_base * (
            1.0
            + self.em_curve_numerator * self.elemental_mastery / denominator
            + self.reaction_bonus
        )
        expected_flat = self.coefficient * expected_core
        return _close(self.core_damage, expected_core) and _close(
            self.constructed_flat_damage, expected_flat
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_id": self.formula_id,
            "formula_sha256": self.formula_sha256,
            "reaction_type": self.reaction_type,
            "operator": self.operator.value,
            "owner_index": self.owner_index,
            "owner_key": self.owner_key,
            "read_frame": self.read_frame,
            "read_mode": self.read_mode.value,
            "read_phase": self.read_phase,
            "level": self.level,
            "level_base": self.level_base,
            "elemental_mastery": self.elemental_mastery,
            "em_curve_numerator": self.em_curve_numerator,
            "em_curve_denominator_offset": self.em_curve_denominator_offset,
            "reaction_bonus": self.reaction_bonus,
            "reaction_bonus_contributions": [
                row.to_dict() for row in self.reaction_bonus_contributions
            ],
            "core_damage": self.core_damage,
            "coefficient": self.coefficient,
            "constructed_flat_damage": self.constructed_flat_damage,
            "parent_attack_id": self.parent_attack_id,
            "parent_target_key": self.parent_target_key,
            "parent_occurrence_resolved": self.parent_occurrence_resolved,
            "aura_source_indices": list(self.aura_source_indices),
            "aura_source_keys": list(self.aura_source_keys),
            "child_role": self.child_role,
            "child_ordinal": self.child_ordinal,
            "persistent_state_id": self.persistent_state_id,
            "persistent_revision": self.persistent_revision,
            "gadget_id": self.gadget_id,
            "gadget_creator_index": self.gadget_creator_index,
            "gadget_creator_key": self.gadget_creator_key,
            "gadget_converter_index": self.gadget_converter_index,
            "gadget_converter_key": self.gadget_converter_key,
            "gadget_resolution_reason": self.gadget_resolution_reason,
        }


@dataclass(frozen=True, slots=True)
class ReactionHitEvidence:
    event_id: str
    formula: TransformativeReactionFormula

    def __post_init__(self) -> None:
        _trimmed(self.event_id, "reaction event_id")
        if not isinstance(self.formula, TransformativeReactionFormula):
            raise TraceContractError(
                "reaction hit formula must be TransformativeReactionFormula"
            )

    def to_dict(self) -> dict[str, object]:
        return {"event_id": self.event_id, "formula": self.formula.to_dict()}


@dataclass(frozen=True, slots=True)
class ReactionEvidenceTrace:
    provider_evidence: ProviderEvidenceTrace
    raw_payload_sha256: str
    reaction_hits: tuple[ReactionHitEvidence, ...]
    schema_version: int = REACTION_EVIDENCE_SCHEMA_VERSION
    kind: str = REACTION_EVIDENCE_KIND

    def __post_init__(self) -> None:
        if not isinstance(self.provider_evidence, ProviderEvidenceTrace):
            raise TraceContractError(
                "provider_evidence must be ProviderEvidenceTrace"
            )
        _sha256(self.raw_payload_sha256, "raw_payload_sha256")
        if not isinstance(self.reaction_hits, tuple):
            raise TraceContractError("reaction_hits must be an immutable tuple")
        if any(not isinstance(row, ReactionHitEvidence) for row in self.reaction_hits):
            raise TraceContractError("invalid reaction hit evidence")
        event_ids = tuple(row.event_id for row in self.reaction_hits)
        if len(event_ids) != len(set(event_ids)):
            raise TraceContractError("reaction hit event IDs must be unique")
        terminal_ids = tuple(
            hit.event_id for hit in self.provider_evidence.terminal_trace.hits
        )
        terminal_set = set(terminal_ids)
        if not set(event_ids).issubset(terminal_set):
            raise TraceContractError(
                "reaction evidence references an unknown terminal hit"
            )
        order = {event_id: index for index, event_id in enumerate(terminal_ids)}
        if tuple(order[event_id] for event_id in event_ids) != tuple(
            sorted(order[event_id] for event_id in event_ids)
        ):
            raise TraceContractError("reaction hits must follow terminal hit order")
        character_keys = self.provider_evidence.terminal_trace.request.character_keys
        for row in self.reaction_hits:
            formula = row.formula
            _bound_character_key(
                formula.owner_index,
                formula.owner_key,
                character_keys,
                "reaction owner",
            )
            for index, key in zip(
                formula.aura_source_indices,
                formula.aura_source_keys,
                strict=True,
            ):
                _bound_character_key(
                    index, key, character_keys, "reaction aura source"
                )
            if formula.gadget_creator_index is not None:
                _bound_character_key(
                    formula.gadget_creator_index,
                    formula.gadget_creator_key,
                    character_keys,
                    "gadget creator",
                )
            if formula.gadget_converter_index is not None:
                _bound_character_key(
                    formula.gadget_converter_index,
                    formula.gadget_converter_key,
                    character_keys,
                    "gadget converter",
                )
        if self.schema_version != REACTION_EVIDENCE_SCHEMA_VERSION:
            raise TraceContractError("unsupported reaction evidence schema")
        if self.kind != REACTION_EVIDENCE_KIND:
            raise TraceContractError("unsupported reaction evidence kind")

    @property
    def terminal_trace(self):
        return self.provider_evidence.terminal_trace

    @property
    def exact_replay_eligible(self) -> bool:
        return False

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema_version": self.schema_version,
                "kind": self.kind,
                "provider_evidence_sha256": self.provider_evidence.evidence_sha256,
                "raw_payload_sha256": self.raw_payload_sha256,
                "reaction_hits": [row.to_dict() for row in self.reaction_hits],
            }
        )


def _trimmed(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{field} must be a non-empty trimmed string")


def _sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TraceContractError(f"{field} must be a lowercase SHA-256 digest")


def _finite(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{field} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{field} must be finite")


def _nonnegative_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceContractError(f"{field} must be a non-negative integer")


def _positive_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TraceContractError(f"{field} must be a positive integer")


def _sorted_unique_nonnegative(value: object, field: str) -> None:
    if not isinstance(value, tuple):
        raise TraceContractError(f"{field} must be an immutable tuple")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value):
        raise TraceContractError(f"{field} must contain non-negative integers")
    if value != tuple(sorted(set(value))):
        raise TraceContractError(f"{field} must be sorted and unique")


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _bound_character_key(
    index: int,
    key: str | None,
    character_keys: tuple[str, ...],
    field: str,
) -> None:
    if index >= len(character_keys) or key != character_keys[index]:
        raise TraceContractError(f"{field} index/key binding mismatch")


__all__ = [
    "REACTION_EVIDENCE_KIND",
    "REACTION_EVIDENCE_SCHEMA_VERSION",
    "ReactionEvidenceTrace",
    "ReactionHitEvidence",
    "TRANSFORMATIVE_REACTION_FORMULA_ID",
    "TRANSFORMATIVE_REACTION_FORMULA_SHA256",
    "TransformativeReactionFormula",
]
