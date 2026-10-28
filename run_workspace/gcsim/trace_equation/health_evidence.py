"""Strict additive health-operation evidence for raw engine trace schema V5.

V5 keeps reaction/source collections structurally unchanged and adds typed
health-operation receipts.  These receipts are diagnostic causal evidence;
they never grant replay, publication, or pruning authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re

from .codec import (
    _array,
    _boolean,
    _integer,
    _number,
    _object,
    _optional_string,
    _string,
)
from .contracts import TraceContractError, canonical_sha256
from .provider_evidence import ProviderIdentity
from .reaction_evidence import ReactionEvidenceTrace
from .source_dependencies import (
    SOURCE_HEALTH_EVIDENCE_CAPABILITY,
    SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION,
    SourceManifestBinding,
    SourceOccurrence,
    SourceSliceStatus,
    SourceValueBinding,
    validate_source_evidence_components,
)


HEALTH_EVIDENCE_SCHEMA_VERSION = SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION
HEALTH_EVIDENCE_KIND = "gtt.trace_equation.health_evidence"
HEALTH_OPERATION_ID_PREFIX = "health-operation:"
HEALTH_CONTRIBUTION_ID_PREFIX = "health-operation:"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTRIBUTION_ID_RE = re.compile(
    r"^health-operation:(0|[1-9][0-9]*):modifier:(0|[1-9][0-9]*)$"
)
_REL_TOLERANCE = 1e-9
_ABS_TOLERANCE = 1e-7

_HEALTH_OPERATION_KEYS = {
    "sequence_index",
    "operation_id",
    "kind",
    "frame",
    "parent_occurrence_id",
    "provider",
    "caller_index",
    "target_index",
    "heal_type",
    "external",
    "input_value",
    "adjusted_input_value",
    "base_amount",
    "source_bonus",
    "heal_bonus_total",
    "raw_amount",
    "event_amount",
    "event_effective_amount",
    "hp_delta_magnitude",
    "overheal",
    "hp_debt_before",
    "hp_debt_after",
    "max_hp_before",
    "max_hp_after",
    "hp_before",
    "hp_after",
    "hp_ratio_before",
    "hp_ratio_after",
    "modifier_contributions",
    "candidate_dependency_complete",
    "uncertainty_codes",
}

_HEALTH_MODIFIER_CONTRIBUTION_KEYS = {
    "contribution_id",
    "modifier_key",
    "source_id",
    "source_occurrence_id",
    "provider",
    "value",
    "expiry_frame",
    "candidate_dependency_complete",
}


class HealthOperationKind(str, Enum):
    HEAL = "heal"
    DRAIN = "drain"


@dataclass(frozen=True, slots=True)
class HealthModifierContribution:
    contribution_id: str
    modifier_key: str
    source_id: str
    source_occurrence_id: str | None
    provider: ProviderIdentity
    value: float
    expiry_frame: int
    candidate_dependency_complete: bool

    def __post_init__(self) -> None:
        _trimmed(self.contribution_id, "health contribution_id")
        if _CONTRIBUTION_ID_RE.fullmatch(self.contribution_id) is None:
            raise TraceContractError(
                "health contribution_id must use the relational "
                "health-operation:<operation>:modifier:<ordinal> form"
            )
        _trimmed(self.modifier_key, "health modifier_key")
        _sha256(self.source_id, "health modifier source_id")
        _optional_trimmed(
            self.source_occurrence_id,
            "health modifier source_occurrence_id",
        )
        if not isinstance(self.provider, ProviderIdentity):
            raise TraceContractError("health modifier provider is invalid")
        _finite(self.value, "health modifier value")
        _int(self.expiry_frame, "health modifier expiry_frame")
        _bool(
            self.candidate_dependency_complete,
            "health modifier candidate_dependency_complete",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contribution_id": self.contribution_id,
            "modifier_key": self.modifier_key,
            "source_id": self.source_id,
            "source_occurrence_id": self.source_occurrence_id,
            "provider": self.provider.to_dict(),
            "value": self.value,
            "expiry_frame": self.expiry_frame,
            "candidate_dependency_complete": self.candidate_dependency_complete,
        }


@dataclass(frozen=True, slots=True)
class HealthOperation:
    sequence_index: int
    operation_id: str
    kind: HealthOperationKind
    frame: int
    parent_occurrence_id: str | None
    provider: ProviderIdentity
    caller_index: int | None
    target_index: int
    heal_type: str | None
    external: bool | None
    input_value: float
    adjusted_input_value: float
    base_amount: float | None
    source_bonus: float | None
    heal_bonus_total: float | None
    raw_amount: float
    event_amount: float
    event_effective_amount: float
    hp_delta_magnitude: float
    overheal: float | None
    hp_debt_before: float
    hp_debt_after: float
    max_hp_before: float
    max_hp_after: float
    hp_before: float
    hp_after: float
    hp_ratio_before: float
    hp_ratio_after: float
    modifier_contributions: tuple[HealthModifierContribution, ...]
    candidate_dependency_complete: bool
    uncertainty_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonnegative_int(self.sequence_index, "health sequence_index")
        expected_id = f"{HEALTH_OPERATION_ID_PREFIX}{self.sequence_index}"
        if self.operation_id != expected_id:
            raise TraceContractError(
                f"health operation_id must be {expected_id!r}"
            )
        if not isinstance(self.kind, HealthOperationKind):
            raise TraceContractError("health kind is invalid")
        _nonnegative_int(self.frame, "health frame")
        _optional_trimmed(self.parent_occurrence_id, "health parent_occurrence_id")
        if not isinstance(self.provider, ProviderIdentity):
            raise TraceContractError("health provider is invalid")
        _optional_nonnegative_int(self.caller_index, "health caller_index")
        _nonnegative_int(self.target_index, "health target_index")
        _optional_trimmed(self.heal_type, "health heal_type")
        if self.heal_type not in {None, "absolute", "percent"}:
            raise TraceContractError(
                "health heal_type must be 'absolute', 'percent', or null"
            )
        _optional_bool(self.external, "health external")

        for name in (
            "input_value",
            "adjusted_input_value",
            "raw_amount",
            "event_amount",
            "event_effective_amount",
            "hp_delta_magnitude",
            "hp_debt_before",
            "hp_debt_after",
            "max_hp_before",
            "max_hp_after",
            "hp_before",
            "hp_after",
            "hp_ratio_before",
            "hp_ratio_after",
        ):
            _finite(getattr(self, name), f"health {name}")
        for name in (
            "base_amount",
            "source_bonus",
            "heal_bonus_total",
            "overheal",
        ):
            _optional_finite(getattr(self, name), f"health {name}")

        for name in (
            "input_value",
            "adjusted_input_value",
            "raw_amount",
            "event_amount",
            "event_effective_amount",
            "hp_delta_magnitude",
            "hp_debt_before",
            "hp_debt_after",
            "hp_before",
            "hp_after",
        ):
            _nonnegative(getattr(self, name), f"health {name}")
        if self.base_amount is not None:
            _nonnegative(self.base_amount, "health base_amount")
        if self.overheal is not None:
            _nonnegative(self.overheal, "health overheal")
        if self.max_hp_before <= 0 or self.max_hp_after <= 0:
            raise TraceContractError("health max_hp values must be positive")
        for name in ("hp_ratio_before", "hp_ratio_after"):
            value = getattr(self, name)
            if value < 0 or value > 1:
                raise TraceContractError(f"health {name} must be in [0, 1]")
        if self.hp_before > self.max_hp_before + _ABS_TOLERANCE:
            raise TraceContractError("health hp_before exceeds max_hp_before")
        if self.hp_after > self.max_hp_after + _ABS_TOLERANCE:
            raise TraceContractError("health hp_after exceeds max_hp_after")
        if not _close(self.hp_ratio_before, self.hp_before / self.max_hp_before):
            raise TraceContractError("health hp_ratio_before does not match HP/MaxHP")
        if not _close(self.hp_ratio_after, self.hp_after / self.max_hp_after):
            raise TraceContractError("health hp_ratio_after does not match HP/MaxHP")

        if not isinstance(self.modifier_contributions, tuple):
            raise TraceContractError("health modifier_contributions must be a tuple")
        if any(
            not isinstance(row, HealthModifierContribution)
            for row in self.modifier_contributions
        ):
            raise TraceContractError("health modifier_contributions contain invalid rows")
        _bool(
            self.candidate_dependency_complete,
            "health candidate_dependency_complete",
        )
        if not isinstance(self.uncertainty_codes, tuple):
            raise TraceContractError("health uncertainty_codes must be a tuple")
        if any(
            not isinstance(code, str) or not code or code != code.strip()
            for code in self.uncertainty_codes
        ):
            raise TraceContractError(
                "health uncertainty_codes must contain trimmed strings"
            )
        if self.uncertainty_codes != tuple(sorted(set(self.uncertainty_codes))):
            raise TraceContractError(
                "health uncertainty_codes must be sorted and unique"
            )
        if self.candidate_dependency_complete and (
            self.uncertainty_codes
            or any(
                not row.candidate_dependency_complete
                for row in self.modifier_contributions
            )
        ):
            raise TraceContractError(
                "complete health dependency cannot retain uncertainty or an "
                "incomplete modifier contribution"
            )
        if (
            not self.candidate_dependency_complete
            and not self.uncertainty_codes
        ):
            raise TraceContractError(
                "incomplete health dependency requires an uncertainty code"
            )

        hp_delta = abs(self.hp_after - self.hp_before)
        if not _close(self.hp_delta_magnitude, hp_delta):
            raise TraceContractError(
                "health hp_delta_magnitude does not match the observed HP delta"
            )
        if self.kind is HealthOperationKind.HEAL:
            if self.heal_type is None or self.external is not None:
                raise TraceContractError(
                    "heal operation requires heal_type and null external"
                )
            if any(
                value is None
                for value in (
                    self.base_amount,
                    self.source_bonus,
                    self.heal_bonus_total,
                    self.overheal,
                )
            ):
                raise TraceContractError(
                    "heal operation requires base/source/heal-bonus/overheal values"
                )
            assert self.overheal is not None
            expected_effective = max(self.event_amount - self.overheal, 0.0)
            if not _close(self.event_effective_amount, expected_effective):
                raise TraceContractError(
                    "heal event_effective_amount must equal max(event-overheal, 0)"
                )
            assert self.heal_bonus_total is not None
            contribution_total = sum(
                row.value for row in self.modifier_contributions
            )
            if not _close(self.heal_bonus_total, contribution_total):
                raise TraceContractError(
                    "heal_bonus_total must equal modifier contribution sum"
                )
            assert self.base_amount is not None and self.source_bonus is not None
            expected_base = (
                self.adjusted_input_value
                if self.heal_type == "absolute"
                else self.max_hp_before * self.adjusted_input_value
            )
            if not _close(self.base_amount, expected_base):
                raise TraceContractError(
                    "heal base_amount does not match heal_type input formula"
                )
            expected_raw = self.base_amount * (
                1.0 + self.source_bonus + self.heal_bonus_total
            )
            if not _close(self.raw_amount, expected_raw):
                raise TraceContractError(
                    "heal raw_amount does not match base and bonus contributions"
                )
        else:
            if self.heal_type is not None or self.external is None:
                raise TraceContractError(
                    "drain operation requires null heal_type and boolean external"
                )
            if any(
                value is not None
                for value in (
                    self.base_amount,
                    self.source_bonus,
                    self.heal_bonus_total,
                    self.overheal,
                )
            ):
                raise TraceContractError(
                    "drain operation requires null heal-only values"
                )
            if self.modifier_contributions:
                raise TraceContractError(
                    "drain operation cannot contain heal modifier contributions"
                )
            if not _close(self.event_effective_amount, self.event_amount):
                raise TraceContractError(
                    "drain event_effective_amount must equal event_amount"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "operation_id": self.operation_id,
            "kind": self.kind.value,
            "frame": self.frame,
            "parent_occurrence_id": self.parent_occurrence_id,
            "provider": self.provider.to_dict(),
            "caller_index": self.caller_index,
            "target_index": self.target_index,
            "heal_type": self.heal_type,
            "external": self.external,
            "input_value": self.input_value,
            "adjusted_input_value": self.adjusted_input_value,
            "base_amount": self.base_amount,
            "source_bonus": self.source_bonus,
            "heal_bonus_total": self.heal_bonus_total,
            "raw_amount": self.raw_amount,
            "event_amount": self.event_amount,
            "event_effective_amount": self.event_effective_amount,
            "hp_delta_magnitude": self.hp_delta_magnitude,
            "overheal": self.overheal,
            "hp_debt_before": self.hp_debt_before,
            "hp_debt_after": self.hp_debt_after,
            "max_hp_before": self.max_hp_before,
            "max_hp_after": self.max_hp_after,
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "hp_ratio_before": self.hp_ratio_before,
            "hp_ratio_after": self.hp_ratio_after,
            "modifier_contributions": [
                row.to_dict() for row in self.modifier_contributions
            ],
            "candidate_dependency_complete": self.candidate_dependency_complete,
            "uncertainty_codes": list(self.uncertainty_codes),
        }


@dataclass(frozen=True, slots=True)
class HealthEvidenceTrace:
    reaction_evidence: ReactionEvidenceTrace
    source_manifest_binding: SourceManifestBinding
    raw_payload_sha256: str
    occurrences: tuple[SourceOccurrence, ...]
    value_bindings: tuple[SourceValueBinding, ...]
    health_operations: tuple[HealthOperation, ...]
    schema_version: int = HEALTH_EVIDENCE_SCHEMA_VERSION
    kind: str = HEALTH_EVIDENCE_KIND

    def __post_init__(self) -> None:
        if self.schema_version != HEALTH_EVIDENCE_SCHEMA_VERSION:
            raise TraceContractError("health evidence schema must be 5")
        if self.kind != HEALTH_EVIDENCE_KIND:
            raise TraceContractError("health evidence kind mismatch")
        if not isinstance(self.source_manifest_binding, SourceManifestBinding):
            raise TraceContractError(
                "source_manifest_binding must be SourceManifestBinding"
            )
        manifest = self.source_manifest_binding.manifest_body
        if (
            manifest.trace_schema_version,
            manifest.trace_capability,
        ) != (
            HEALTH_EVIDENCE_SCHEMA_VERSION,
            SOURCE_HEALTH_EVIDENCE_CAPABILITY,
        ):
            raise TraceContractError(
                "health evidence v5 requires a 5/v5 source manifest"
            )
        validate_health_evidence_components(
            reaction_evidence=self.reaction_evidence,
            source_manifest_binding=self.source_manifest_binding,
            raw_payload_sha256=self.raw_payload_sha256,
            occurrences=self.occurrences,
            value_bindings=self.value_bindings,
            health_operations=self.health_operations,
        )

    @property
    def terminal_trace(self):
        return self.reaction_evidence.terminal_trace

    @property
    def exact_replay_eligible(self) -> bool:
        return False

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def publishable(self) -> bool:
        return False

    @property
    def uncertainty_codes(self) -> tuple[str, ...]:
        codes: set[str] = set()
        bound_occurrences = {row.occurrence_id for row in self.value_bindings}
        manifest = self.source_manifest_binding.manifest_body
        for occurrence in self.occurrences:
            entry = manifest.entry_by_id(occurrence.source_id)
            assert entry is not None
            if occurrence.occurrence_id not in bound_occurrences:
                codes.add(f"source_occurrence_unbound:{occurrence.occurrence_id}")
            if entry.template.status is SourceSliceStatus.OPAQUE_FROZEN:
                codes.add(
                    "source_dependency_opaque_frozen:"
                    f"{occurrence.occurrence_id}:{entry.template.stop_reason_code}"
                )
        for operation in self.health_operations:
            codes.update(
                f"health_operation:{operation.operation_id}:{code}"
                for code in operation.uncertainty_codes
            )
            if not operation.candidate_dependency_complete:
                codes.add(
                    "health_candidate_dependency_incomplete:"
                    f"{operation.operation_id}"
                )
        return tuple(sorted(codes))

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema_version": self.schema_version,
                "kind": self.kind,
                "reaction_evidence_sha256": self.reaction_evidence.evidence_sha256,
                "source_manifest_binding_sha256": (
                    self.source_manifest_binding.binding_sha256
                ),
                "raw_payload_sha256": self.raw_payload_sha256,
                "occurrences": [row.to_dict() for row in self.occurrences],
                "value_bindings": [row.to_dict() for row in self.value_bindings],
                "health_operations": [
                    row.to_dict() for row in self.health_operations
                ],
                "uncertainty_codes": list(self.uncertainty_codes),
                "exact_replay_eligible": False,
                "hard_prune_allowed": False,
                "publishable": False,
            }
        )


def validate_health_evidence_components(
    *,
    reaction_evidence: ReactionEvidenceTrace,
    source_manifest_binding: SourceManifestBinding,
    raw_payload_sha256: str,
    occurrences: tuple[SourceOccurrence, ...],
    value_bindings: tuple[SourceValueBinding, ...],
    health_operations: tuple[HealthOperation, ...],
) -> None:
    """Validate the unchanged V5 ledger for a strict additive wrapper.

    ``HealthEvidenceTrace`` itself still accepts only 5/v5.  V6 reuses this
    component validator so inherited health rows keep exactly their V5 meaning
    without relabeling a 6/v6 executable as an accepted V5 executable.
    """

    validate_source_evidence_components(
        reaction_evidence=reaction_evidence,
        source_manifest_binding=source_manifest_binding,
        raw_payload_sha256=raw_payload_sha256,
        occurrences=occurrences,
        value_bindings=value_bindings,
    )
    if not isinstance(health_operations, tuple):
        raise TraceContractError("health_operations must be a tuple")
    if any(not isinstance(row, HealthOperation) for row in health_operations):
        raise TraceContractError("health_operations contain invalid rows")
    if tuple(row.sequence_index for row in health_operations) != tuple(
        range(len(health_operations))
    ):
        raise TraceContractError("health operation sequence must be contiguous")
    if tuple(row.frame for row in health_operations) != tuple(
        sorted(row.frame for row in health_operations)
    ):
        raise TraceContractError("health operation frames must be nondecreasing")

    request = reaction_evidence.terminal_trace.request
    character_keys = request.character_keys
    occurrence_map = {row.occurrence_id: row for row in occurrences}
    contribution_ids: set[str] = set()
    manifest_body = source_manifest_binding.manifest_body
    for operation in health_operations:
        _validate_character_index(
            operation.target_index,
            character_keys,
            "health target_index",
        )
        if operation.caller_index is not None:
            _validate_character_index(
                operation.caller_index,
                character_keys,
                "health caller_index",
            )
        _validate_provider_owner(operation.provider, character_keys)
        if operation.parent_occurrence_id is not None:
            parent_occurrence = occurrence_map.get(operation.parent_occurrence_id)
            if parent_occurrence is None:
                raise TraceContractError(
                    "health parent_occurrence_id references an unknown V4 occurrence"
                )
            if parent_occurrence.frame > operation.frame:
                raise TraceContractError(
                    "health parent occurrence cannot be later than operation"
                )
        for ordinal, contribution in enumerate(operation.modifier_contributions):
            expected_contribution_id = f"{operation.operation_id}:modifier:{ordinal}"
            if contribution.contribution_id != expected_contribution_id:
                raise TraceContractError(
                    "health modifier contribution IDs must be contiguous and "
                    "relational to their operation"
                )
            if contribution.contribution_id in contribution_ids:
                raise TraceContractError(
                    "health contribution IDs must be globally unique"
                )
            contribution_ids.add(contribution.contribution_id)
            _validate_provider_owner(contribution.provider, character_keys)
            if manifest_body.entry_by_id(contribution.source_id) is None:
                raise TraceContractError(
                    "health modifier contribution references unknown source_id"
                )
            if (
                contribution.expiry_frame != -1
                and contribution.expiry_frame <= operation.frame
            ):
                raise TraceContractError(
                    "active health modifier expiry must be -1 or later than "
                    "operation frame"
                )
            if contribution.source_occurrence_id is None:
                continue
            source_occurrence = occurrence_map.get(contribution.source_occurrence_id)
            if source_occurrence is None:
                raise TraceContractError(
                    "health modifier source_occurrence_id references an unknown "
                    "V4 occurrence"
                )
            if source_occurrence.source_id != contribution.source_id:
                raise TraceContractError(
                    "health modifier source occurrence/source_id mismatch"
                )
            if source_occurrence.provider != contribution.provider:
                raise TraceContractError(
                    "health modifier source occurrence/provider mismatch"
                )
            if source_occurrence.frame > operation.frame:
                raise TraceContractError(
                    "health modifier source occurrence cannot be later than operation"
                )


def decode_health_operations(value: object, path: str) -> tuple[HealthOperation, ...]:
    return tuple(
        _decode_health_operation(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _decode_health_operation(value: object, path: str) -> HealthOperation:
    row = _object(value, path, _HEALTH_OPERATION_KEYS)
    raw_kind = _string(row["kind"], f"{path}.kind")
    try:
        kind = HealthOperationKind(raw_kind)
    except ValueError as exc:
        raise TraceContractError(
            f"{path}.kind has unsupported value {raw_kind!r}"
        ) from exc
    return HealthOperation(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        operation_id=_string(row["operation_id"], f"{path}.operation_id"),
        kind=kind,
        frame=_integer(row["frame"], f"{path}.frame"),
        parent_occurrence_id=_optional_string(
            row["parent_occurrence_id"], f"{path}.parent_occurrence_id"
        ),
        provider=_decode_provider(row["provider"], f"{path}.provider"),
        caller_index=_optional_integer(row["caller_index"], f"{path}.caller_index"),
        target_index=_integer(row["target_index"], f"{path}.target_index"),
        heal_type=_optional_string(row["heal_type"], f"{path}.heal_type"),
        external=_optional_boolean(row["external"], f"{path}.external"),
        input_value=_number(row["input_value"], f"{path}.input_value"),
        adjusted_input_value=_number(
            row["adjusted_input_value"], f"{path}.adjusted_input_value"
        ),
        base_amount=_optional_number(row["base_amount"], f"{path}.base_amount"),
        source_bonus=_optional_number(row["source_bonus"], f"{path}.source_bonus"),
        heal_bonus_total=_optional_number(
            row["heal_bonus_total"], f"{path}.heal_bonus_total"
        ),
        raw_amount=_number(row["raw_amount"], f"{path}.raw_amount"),
        event_amount=_number(row["event_amount"], f"{path}.event_amount"),
        event_effective_amount=_number(
            row["event_effective_amount"], f"{path}.event_effective_amount"
        ),
        hp_delta_magnitude=_number(
            row["hp_delta_magnitude"], f"{path}.hp_delta_magnitude"
        ),
        overheal=_optional_number(row["overheal"], f"{path}.overheal"),
        hp_debt_before=_number(row["hp_debt_before"], f"{path}.hp_debt_before"),
        hp_debt_after=_number(row["hp_debt_after"], f"{path}.hp_debt_after"),
        max_hp_before=_number(row["max_hp_before"], f"{path}.max_hp_before"),
        max_hp_after=_number(row["max_hp_after"], f"{path}.max_hp_after"),
        hp_before=_number(row["hp_before"], f"{path}.hp_before"),
        hp_after=_number(row["hp_after"], f"{path}.hp_after"),
        hp_ratio_before=_number(
            row["hp_ratio_before"], f"{path}.hp_ratio_before"
        ),
        hp_ratio_after=_number(row["hp_ratio_after"], f"{path}.hp_ratio_after"),
        modifier_contributions=tuple(
            _decode_health_modifier_contribution(
                item,
                f"{path}.modifier_contributions[{index}]",
            )
            for index, item in enumerate(
                _array(
                    row["modifier_contributions"],
                    f"{path}.modifier_contributions",
                )
            )
        ),
        candidate_dependency_complete=_boolean(
            row["candidate_dependency_complete"],
            f"{path}.candidate_dependency_complete",
        ),
        uncertainty_codes=tuple(
            _string(item, f"{path}.uncertainty_codes[{index}]")
            for index, item in enumerate(
                _array(row["uncertainty_codes"], f"{path}.uncertainty_codes")
            )
        ),
    )


def _decode_health_modifier_contribution(
    value: object,
    path: str,
) -> HealthModifierContribution:
    row = _object(value, path, _HEALTH_MODIFIER_CONTRIBUTION_KEYS)
    return HealthModifierContribution(
        contribution_id=_string(
            row["contribution_id"], f"{path}.contribution_id"
        ),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        source_id=_string(row["source_id"], f"{path}.source_id"),
        source_occurrence_id=_optional_string(
            row["source_occurrence_id"], f"{path}.source_occurrence_id"
        ),
        provider=_decode_provider(row["provider"], f"{path}.provider"),
        value=_number(row["value"], f"{path}.value"),
        expiry_frame=_integer(row["expiry_frame"], f"{path}.expiry_frame"),
        candidate_dependency_complete=_boolean(
            row["candidate_dependency_complete"],
            f"{path}.candidate_dependency_complete",
        ),
    )


def _decode_provider(value: object, path: str) -> ProviderIdentity:
    row = _object(value, path, {"known", "kind", "key", "owner_index", "piece_count"})
    return ProviderIdentity(
        known=_boolean(row["known"], f"{path}.known"),
        kind=_string(row["kind"], f"{path}.kind"),
        key=_string(row["key"], f"{path}.key"),
        owner_index=_integer(row["owner_index"], f"{path}.owner_index"),
        piece_count=_integer(row["piece_count"], f"{path}.piece_count"),
    )


def _validate_provider_owner(
    provider: ProviderIdentity,
    character_keys: tuple[str, ...],
) -> None:
    if provider.known and provider.owner_index >= len(character_keys):
        raise TraceContractError("health provider owner_index exceeds character catalog")
    if (
        provider.known
        and provider.kind.casefold() == "character"
        and character_keys[provider.owner_index] != provider.key
    ):
        raise TraceContractError("health character provider owner binding mismatch")


def _validate_character_index(
    value: int,
    character_keys: tuple[str, ...],
    label: str,
) -> None:
    if value >= len(character_keys):
        raise TraceContractError(f"{label} exceeds character catalog")


def _optional_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _integer(value, path)


def _optional_boolean(value: object, path: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, path)


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _optional_trimmed(value: object, label: str) -> None:
    if value is not None:
        _trimmed(value, label)


def _sha256(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TraceContractError(f"{label} must be a lowercase SHA-256")


def _int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{label} must be an integer")


def _nonnegative_int(value: object, label: str) -> None:
    _int(value, label)
    if value < 0:
        raise TraceContractError(f"{label} must be non-negative")


def _optional_nonnegative_int(value: object, label: str) -> None:
    if value is not None:
        _nonnegative_int(value, label)


def _bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TraceContractError(f"{label} must be boolean")


def _optional_bool(value: object, label: str) -> None:
    if value is not None:
        _bool(value, label)


def _finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be a number")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{label} must be finite")


def _optional_finite(value: object, label: str) -> None:
    if value is not None:
        _finite(value, label)


def _nonnegative(value: float, label: str) -> None:
    if value < 0:
        raise TraceContractError(f"{label} must be non-negative")


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(
        _ABS_TOLERANCE,
        _REL_TOLERANCE * max(abs(left), abs(right)),
    )


__all__ = [
    "HEALTH_CONTRIBUTION_ID_PREFIX",
    "HEALTH_EVIDENCE_KIND",
    "HEALTH_EVIDENCE_SCHEMA_VERSION",
    "HEALTH_OPERATION_ID_PREFIX",
    "HealthEvidenceTrace",
    "HealthModifierContribution",
    "HealthOperation",
    "HealthOperationKind",
    "decode_health_operations",
    "validate_health_evidence_components",
]
