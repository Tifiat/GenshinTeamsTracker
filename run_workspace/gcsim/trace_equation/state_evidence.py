"""Strict additive ordered-state evidence for raw engine trace schema V6.

V6 does not grant replay or pruning authority.  It preserves the V1--V5
terminal, provider, reaction, source, and health rows and adds a single global
timeline that can explain mutable-state feedback without entity-name rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Mapping

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
from .health_evidence import (
    HealthOperation,
    validate_health_evidence_components,
)
from .provider_evidence import ProviderIdentity, decode_provider_identity
from .reaction_evidence import ReactionEvidenceTrace
from .source_dependencies import (
    SOURCE_STATE_EVIDENCE_CAPABILITY,
    SOURCE_STATE_EVIDENCE_SCHEMA_VERSION,
    SourceManifestBinding,
    SourceOccurrence,
    SourceParameterBinding,
    SourceValueBinding,
    decode_source_parameter_bindings,
)


STATE_EVIDENCE_SCHEMA_VERSION = SOURCE_STATE_EVIDENCE_SCHEMA_VERSION
STATE_EVIDENCE_CAPABILITY = SOURCE_STATE_EVIDENCE_CAPABILITY
STATE_EVIDENCE_KIND = "gtt.trace_equation.state_evidence"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATE_SLOT_RE = re.compile(r"^state-slot:(0|[1-9][0-9]*)$")
_STATE_EVENT_RE = re.compile(r"^state-event:(0|[1-9][0-9]*)$")
_TASK_ID_RE = re.compile(r"^task:(0|[1-9][0-9]*)$")
_QUEUE_ID_RE = re.compile(r"^task-queue:(0|[1-9][0-9]*)$")
_REL_TOL = 1e-9
_ABS_TOL = 1e-7

_STATE_SLOT_KEYS = {
    "sequence_index",
    "slot_id",
    "scope",
    "provider",
    "slot_key",
    "initial_value",
    "registration_event_id",
    "candidate_dependency_complete",
    "uncertainty_codes",
    "authoritative",
}

_NUMERIC_REF_KEYS = {
    "kind",
    "event_id",
    "health_operation_id",
    "field_key",
    "literal_value",
}

_NUMERIC_PAYLOAD_KEYS = {"key", "value", "reference"}

_STATE_EVENT_KEYS = {
    "sequence_index",
    "event_id",
    "frame",
    "kind",
    "source_id",
    "source_occurrence_id",
    "provider",
    "parent_event_id",
    "health_operation_id",
    "task_id",
    "call_id",
    "slot_id",
    "channel",
    "key",
    "operation",
    "inputs",
    "modifier_eval_ids",
    "template_sha256",
    "parameters",
    "before",
    "value",
    "after",
    "result",
    "accepted",
    "numeric_payload",
    "enqueue_frame",
    "delay_frames",
    "execute_by_frame",
    "queue_id",
    "queue_sequence",
    "expiry_frame",
    "owner_index",
    "target_index",
    "output",
    "bound_event_id",
    "candidate_dependency_complete",
    "uncertainty_codes",
    "authoritative",
}

_NUMERIC_OPERATIONS = {
    "literal",
    "identity",
    "add",
    "subtract",
    "multiply",
    "divide",
    "min",
    "max",
    "negate",
    "source_expression",
    "health_input",
    "task_payload",
    "state_transition",
}
_GUARD_OPERATIONS = {
    "eq",
    "ne",
    "lt",
    "lte",
    "gt",
    "gte",
    "and",
    "or",
    "not",
    "observed",
}

_HEALTH_NUMERIC_FIELDS = {
    "input_value",
    "adjusted_input_value",
    "raw_amount",
    "event_amount",
    "event_effective_amount",
    "hp_delta_magnitude",
    "max_hp_before",
    "max_hp_after",
    "hp_before",
    "hp_after",
    "hp_ratio_before",
    "hp_ratio_after",
}


class NumericReferenceKind(str, Enum):
    EVENT = "event"
    LITERAL = "literal"
    HEALTH_FIELD = "health_field"


class StateEventKind(str, Enum):
    HEALTH_CONTEXT_ENTER = "health_context_enter"
    HEALTH_CONTEXT_EXIT = "health_context_exit"
    EVENT_CALLBACK_ENTER = "event_callback_enter"
    EVENT_CALLBACK_EXIT = "event_callback_exit"
    TASK_ENQUEUE = "task_enqueue"
    TASK_EXECUTE_ENTER = "task_execute_enter"
    TASK_EXECUTE_EXIT = "task_execute_exit"
    STATUS_READ = "status_read"
    STATUS_ADD = "status_add"
    STATUS_DELETE = "status_delete"
    STATE_SLOT_REGISTER = "state_slot_register"
    STATE_READ = "state_read"
    STATE_WRITE = "state_write"
    STATE_RESYNC = "state_resync"
    NUMERIC_EVAL = "numeric_eval"
    GUARD_EVAL = "guard_eval"
    MODIFIER_EVAL = "modifier_eval"
    MAX_HP_READ = "max_hp_read"
    HEALTH_FIELD_BINDING = "health_field_binding"


@dataclass(frozen=True, slots=True)
class NumericReference:
    kind: NumericReferenceKind
    event_id: str | None
    health_operation_id: str | None
    field_key: str | None
    literal_value: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NumericReferenceKind):
            raise TraceContractError("numeric reference kind is invalid")
        _optional_trimmed(self.event_id, "numeric reference event_id")
        _optional_trimmed(
            self.health_operation_id,
            "numeric reference health_operation_id",
        )
        _optional_trimmed(self.field_key, "numeric reference field_key")
        _optional_finite(self.literal_value, "numeric reference literal_value")
        if self.kind is NumericReferenceKind.EVENT:
            _required(self.event_id, "event numeric reference event_id")
            if any(
                value is not None
                for value in (
                    self.health_operation_id,
                    self.literal_value,
                )
            ):
                raise TraceContractError(
                    "event numeric reference has non-event coordinates"
                )
        elif self.kind is NumericReferenceKind.LITERAL:
            if self.literal_value is None:
                raise TraceContractError(
                    "literal numeric reference requires literal_value"
                )
            if any(
                value is not None
                for value in (
                    self.event_id,
                    self.health_operation_id,
                    self.field_key,
                )
            ):
                raise TraceContractError(
                    "literal numeric reference has relational coordinates"
                )
        else:
            _required(
                self.health_operation_id,
                "health-field reference health_operation_id",
            )
            _required(self.field_key, "health-field reference field_key")
            if self.event_id is not None or self.literal_value is not None:
                raise TraceContractError(
                    "health-field reference has event/literal coordinates"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "event_id": self.event_id,
            "health_operation_id": self.health_operation_id,
            "field_key": self.field_key,
            "literal_value": self.literal_value,
        }


@dataclass(frozen=True, slots=True)
class NumericPayload:
    key: str
    value: float
    reference: NumericReference

    def __post_init__(self) -> None:
        _trimmed(self.key, "numeric payload key")
        _finite(self.value, "numeric payload value")
        if not isinstance(self.reference, NumericReference):
            raise TraceContractError("numeric payload reference is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "value": self.value,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StateSlot:
    sequence_index: int
    slot_id: str
    scope: str
    provider: ProviderIdentity
    slot_key: str
    initial_value: float
    registration_event_id: str
    candidate_dependency_complete: bool
    uncertainty_codes: tuple[str, ...]
    authoritative: bool

    def __post_init__(self) -> None:
        _nonnegative_int(self.sequence_index, "state slot sequence_index")
        if self.slot_id != f"state-slot:{self.sequence_index}":
            raise TraceContractError("state slot_id must match its sequence index")
        _trimmed(self.scope, "state slot scope")
        if not isinstance(self.provider, ProviderIdentity):
            raise TraceContractError("state slot provider is invalid")
        _trimmed(self.slot_key, "state slot slot_key")
        _finite(self.initial_value, "state slot initial_value")
        if _STATE_EVENT_RE.fullmatch(self.registration_event_id) is None:
            raise TraceContractError(
                "state slot registration_event_id has invalid format"
            )
        _validate_dependency_evidence(
            self.candidate_dependency_complete,
            self.uncertainty_codes,
            "state slot",
        )
        if self.authoritative:
            raise TraceContractError("V6 state slots must not be authoritative")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "slot_id": self.slot_id,
            "scope": self.scope,
            "provider": self.provider.to_dict(),
            "slot_key": self.slot_key,
            "initial_value": self.initial_value,
            "registration_event_id": self.registration_event_id,
            "candidate_dependency_complete": self.candidate_dependency_complete,
            "uncertainty_codes": list(self.uncertainty_codes),
            "authoritative": False,
        }


@dataclass(frozen=True, slots=True)
class StateEvent:
    sequence_index: int
    event_id: str
    frame: int
    kind: StateEventKind
    source_id: str | None
    source_occurrence_id: str | None
    provider: ProviderIdentity
    parent_event_id: str | None
    health_operation_id: str | None
    task_id: str | None
    call_id: str | None
    slot_id: str | None
    channel: str | None
    key: str | None
    operation: str | None
    inputs: tuple[NumericReference, ...]
    modifier_eval_ids: tuple[str, ...]
    template_sha256: str | None
    parameters: tuple[SourceParameterBinding, ...]
    before: float | None
    value: float | None
    after: float | None
    result: bool | None
    accepted: bool | None
    numeric_payload: tuple[NumericPayload, ...]
    enqueue_frame: int | None
    delay_frames: int | None
    execute_by_frame: int | None
    queue_id: str | None
    queue_sequence: int | None
    expiry_frame: int | None
    owner_index: int | None
    target_index: int | None
    output: tuple[tuple[str, float], ...]
    bound_event_id: str | None
    candidate_dependency_complete: bool
    uncertainty_codes: tuple[str, ...]
    authoritative: bool

    def __post_init__(self) -> None:
        _nonnegative_int(self.sequence_index, "state event sequence_index")
        if self.event_id != f"state-event:{self.sequence_index}":
            raise TraceContractError("state event_id must match its sequence index")
        _nonnegative_int(self.frame, "state event frame")
        if not isinstance(self.kind, StateEventKind):
            raise TraceContractError("state event kind is invalid")
        _optional_sha256(self.source_id, "state event source_id")
        for name in (
            "source_occurrence_id",
            "parent_event_id",
            "health_operation_id",
            "task_id",
            "call_id",
            "slot_id",
            "channel",
            "key",
            "operation",
            "bound_event_id",
        ):
            _optional_trimmed(getattr(self, name), f"state event {name}")
        _optional_sha256(self.template_sha256, "state event template_sha256")
        if not isinstance(self.provider, ProviderIdentity):
            raise TraceContractError("state event provider is invalid")
        if not isinstance(self.inputs, tuple) or any(
            not isinstance(row, NumericReference) for row in self.inputs
        ):
            raise TraceContractError("state event inputs are invalid")
        if not isinstance(self.modifier_eval_ids, tuple):
            raise TraceContractError("state event modifier_eval_ids must be a tuple")
        _sorted_unique_strings(
            self.modifier_eval_ids,
            "state event modifier_eval_ids",
            preserve_order=True,
        )
        if not isinstance(self.parameters, tuple) or any(
            not isinstance(row, SourceParameterBinding) for row in self.parameters
        ):
            raise TraceContractError("state event parameters are invalid")
        parameter_keys = tuple(row.parameter_key for row in self.parameters)
        if parameter_keys != tuple(sorted(set(parameter_keys))):
            raise TraceContractError(
                "state event parameters must be sorted by unique parameter_key"
            )
        for name in ("before", "value", "after"):
            _optional_finite(getattr(self, name), f"state event {name}")
        for name in ("result", "accepted"):
            _optional_bool(getattr(self, name), f"state event {name}")
        if not isinstance(self.numeric_payload, tuple) or any(
            not isinstance(row, NumericPayload) for row in self.numeric_payload
        ):
            raise TraceContractError("state event numeric_payload is invalid")
        payload_keys = tuple(row.key for row in self.numeric_payload)
        if payload_keys != tuple(sorted(set(payload_keys))):
            raise TraceContractError(
                "numeric_payload must be sorted by unique key"
            )
        for name in (
            "enqueue_frame",
            "delay_frames",
            "execute_by_frame",
            "queue_sequence",
            "owner_index",
            "target_index",
        ):
            _optional_nonnegative_int(getattr(self, name), f"state event {name}")
        if self.expiry_frame is not None:
            _integer_value(self.expiry_frame, "state event expiry_frame")
        if self.queue_id is not None and _QUEUE_ID_RE.fullmatch(self.queue_id) is None:
            raise TraceContractError("state event queue_id has invalid format")
        if self.task_id is not None and _TASK_ID_RE.fullmatch(self.task_id) is None:
            raise TraceContractError("state event task_id has invalid format")
        if self.slot_id is not None and _STATE_SLOT_RE.fullmatch(self.slot_id) is None:
            raise TraceContractError("state event slot_id has invalid format")
        if not isinstance(self.output, tuple):
            raise TraceContractError("state event output must be immutable")
        output_keys = tuple(key for key, _ in self.output)
        if output_keys != tuple(sorted(set(output_keys))):
            raise TraceContractError("state event output keys must be sorted and unique")
        for key, output_value in self.output:
            _trimmed(key, "state event output key")
            _finite(output_value, f"state event output[{key!r}]")
        _validate_dependency_evidence(
            self.candidate_dependency_complete,
            self.uncertainty_codes,
            f"state event {self.event_id}",
        )
        if self.authoritative:
            raise TraceContractError("V6 state events must not be authoritative")
        _validate_event_local_shape(self)

    @property
    def output_map(self) -> dict[str, float]:
        return dict(self.output)

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "event_id": self.event_id,
            "frame": self.frame,
            "kind": self.kind.value,
            "source_id": self.source_id,
            "source_occurrence_id": self.source_occurrence_id,
            "provider": self.provider.to_dict(),
            "parent_event_id": self.parent_event_id,
            "health_operation_id": self.health_operation_id,
            "task_id": self.task_id,
            "call_id": self.call_id,
            "slot_id": self.slot_id,
            "channel": self.channel,
            "key": self.key,
            "operation": self.operation,
            "inputs": [row.to_dict() for row in self.inputs],
            "modifier_eval_ids": list(self.modifier_eval_ids),
            "template_sha256": self.template_sha256,
            "parameters": [row.to_dict() for row in self.parameters],
            "before": self.before,
            "value": self.value,
            "after": self.after,
            "result": self.result,
            "accepted": self.accepted,
            "numeric_payload": [row.to_dict() for row in self.numeric_payload],
            "enqueue_frame": self.enqueue_frame,
            "delay_frames": self.delay_frames,
            "execute_by_frame": self.execute_by_frame,
            "queue_id": self.queue_id,
            "queue_sequence": self.queue_sequence,
            "expiry_frame": self.expiry_frame,
            "owner_index": self.owner_index,
            "target_index": self.target_index,
            "output": dict(self.output),
            "bound_event_id": self.bound_event_id,
            "candidate_dependency_complete": self.candidate_dependency_complete,
            "uncertainty_codes": list(self.uncertainty_codes),
            "authoritative": False,
        }


@dataclass(frozen=True, slots=True)
class StateEvidenceTrace:
    reaction_evidence: ReactionEvidenceTrace
    source_manifest_binding: SourceManifestBinding
    raw_payload_sha256: str
    occurrences: tuple[SourceOccurrence, ...]
    value_bindings: tuple[SourceValueBinding, ...]
    health_operations: tuple[HealthOperation, ...]
    state_slots: tuple[StateSlot, ...]
    state_events: tuple[StateEvent, ...]
    duration_frames: int
    schema_version: int = STATE_EVIDENCE_SCHEMA_VERSION
    kind: str = STATE_EVIDENCE_KIND

    def __post_init__(self) -> None:
        if self.schema_version != STATE_EVIDENCE_SCHEMA_VERSION:
            raise TraceContractError("state evidence schema must be 6")
        if self.kind != STATE_EVIDENCE_KIND:
            raise TraceContractError("state evidence kind mismatch")
        if not isinstance(self.source_manifest_binding, SourceManifestBinding):
            raise TraceContractError(
                "source_manifest_binding must be SourceManifestBinding"
            )
        manifest = self.source_manifest_binding.manifest_body
        if (
            manifest.trace_schema_version,
            manifest.trace_capability,
        ) != (STATE_EVIDENCE_SCHEMA_VERSION, STATE_EVIDENCE_CAPABILITY):
            raise TraceContractError(
                "state evidence v6 requires a strict 6/v6 source manifest"
            )
        validate_health_evidence_components(
            reaction_evidence=self.reaction_evidence,
            source_manifest_binding=self.source_manifest_binding,
            raw_payload_sha256=self.raw_payload_sha256,
            occurrences=self.occurrences,
            value_bindings=self.value_bindings,
            health_operations=self.health_operations,
        )
        _nonnegative_int(self.duration_frames, "state evidence duration_frames")
        _validate_state_timeline(self)

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
        for slot in self.state_slots:
            codes.update(
                f"state_slot:{slot.slot_id}:{code}"
                for code in slot.uncertainty_codes
            )
        for event in self.state_events:
            codes.update(
                f"state_event:{event.event_id}:{code}"
                for code in event.uncertainty_codes
            )
        for operation in self.health_operations:
            codes.update(
                f"health_operation:{operation.operation_id}:{code}"
                for code in operation.uncertainty_codes
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
                "state_slots": [row.to_dict() for row in self.state_slots],
                "state_events": [row.to_dict() for row in self.state_events],
                "duration_frames": self.duration_frames,
                "uncertainty_codes": list(self.uncertainty_codes),
                "exact_replay_eligible": False,
                "hard_prune_allowed": False,
                "publishable": False,
            }
        )


def decode_state_slots(value: object, path: str) -> tuple[StateSlot, ...]:
    result: list[StateSlot] = []
    for index, item in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        row = _object(item, item_path, _STATE_SLOT_KEYS)
        result.append(
            StateSlot(
                sequence_index=_integer(
                    row["sequence_index"], f"{item_path}.sequence_index"
                ),
                slot_id=_string(row["slot_id"], f"{item_path}.slot_id"),
                scope=_string(row["scope"], f"{item_path}.scope"),
                provider=decode_provider_identity(
                    row["provider"], f"{item_path}.provider"
                ),
                slot_key=_string(row["slot_key"], f"{item_path}.slot_key"),
                initial_value=_number(
                    row["initial_value"], f"{item_path}.initial_value"
                ),
                registration_event_id=_string(
                    row["registration_event_id"],
                    f"{item_path}.registration_event_id",
                ),
                candidate_dependency_complete=_boolean(
                    row["candidate_dependency_complete"],
                    f"{item_path}.candidate_dependency_complete",
                ),
                uncertainty_codes=_decode_uncertainty_codes(
                    row["uncertainty_codes"], f"{item_path}.uncertainty_codes"
                ),
                authoritative=_boolean(
                    row["authoritative"], f"{item_path}.authoritative"
                ),
            )
        )
    return tuple(result)


def decode_state_events(value: object, path: str) -> tuple[StateEvent, ...]:
    return tuple(
        _decode_state_event(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _decode_state_event(value: object, path: str) -> StateEvent:
    row = _object(value, path, _STATE_EVENT_KEYS)
    try:
        kind = StateEventKind(_string(row["kind"], f"{path}.kind"))
    except ValueError as exc:
        raise TraceContractError(f"{path}.kind is unsupported") from exc
    output_raw = row["output"]
    if not isinstance(output_raw, Mapping):
        raise TraceContractError(f"{path}.output must be an object")
    output = tuple(
        sorted(
            (
                _trimmed_key(key, f"{path}.output key"),
                _number(item, f"{path}.output.{key}"),
            )
            for key, item in output_raw.items()
        )
    )
    return StateEvent(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        event_id=_string(row["event_id"], f"{path}.event_id"),
        frame=_integer(row["frame"], f"{path}.frame"),
        kind=kind,
        source_id=_optional_string(row["source_id"], f"{path}.source_id"),
        source_occurrence_id=_optional_string(
            row["source_occurrence_id"], f"{path}.source_occurrence_id"
        ),
        provider=decode_provider_identity(row["provider"], f"{path}.provider"),
        parent_event_id=_optional_string(
            row["parent_event_id"], f"{path}.parent_event_id"
        ),
        health_operation_id=_optional_string(
            row["health_operation_id"], f"{path}.health_operation_id"
        ),
        task_id=_optional_string(row["task_id"], f"{path}.task_id"),
        call_id=_optional_string(row["call_id"], f"{path}.call_id"),
        slot_id=_optional_string(row["slot_id"], f"{path}.slot_id"),
        channel=_optional_string(row["channel"], f"{path}.channel"),
        key=_optional_string(row["key"], f"{path}.key"),
        operation=_optional_string(row["operation"], f"{path}.operation"),
        inputs=tuple(
            _decode_numeric_reference(item, f"{path}.inputs[{index}]")
            for index, item in enumerate(_array(row["inputs"], f"{path}.inputs"))
        ),
        modifier_eval_ids=tuple(
            _string(item, f"{path}.modifier_eval_ids[{index}]")
            for index, item in enumerate(
                _array(row["modifier_eval_ids"], f"{path}.modifier_eval_ids")
            )
        ),
        template_sha256=_optional_string(
            row["template_sha256"], f"{path}.template_sha256"
        ),
        parameters=decode_source_parameter_bindings(
            row["parameters"], f"{path}.parameters"
        ),
        before=_optional_number(row["before"], f"{path}.before"),
        value=_optional_number(row["value"], f"{path}.value"),
        after=_optional_number(row["after"], f"{path}.after"),
        result=_optional_boolean(row["result"], f"{path}.result"),
        accepted=_optional_boolean(row["accepted"], f"{path}.accepted"),
        numeric_payload=tuple(
            _decode_numeric_payload(item, f"{path}.numeric_payload[{index}]")
            for index, item in enumerate(
                _array(row["numeric_payload"], f"{path}.numeric_payload")
            )
        ),
        enqueue_frame=_optional_integer(
            row["enqueue_frame"], f"{path}.enqueue_frame"
        ),
        delay_frames=_optional_integer(row["delay_frames"], f"{path}.delay_frames"),
        execute_by_frame=_optional_integer(
            row["execute_by_frame"], f"{path}.execute_by_frame"
        ),
        queue_id=_optional_string(row["queue_id"], f"{path}.queue_id"),
        queue_sequence=_optional_integer(
            row["queue_sequence"], f"{path}.queue_sequence"
        ),
        expiry_frame=_optional_integer(row["expiry_frame"], f"{path}.expiry_frame"),
        owner_index=_optional_integer(row["owner_index"], f"{path}.owner_index"),
        target_index=_optional_integer(row["target_index"], f"{path}.target_index"),
        output=output,
        bound_event_id=_optional_string(
            row["bound_event_id"], f"{path}.bound_event_id"
        ),
        candidate_dependency_complete=_boolean(
            row["candidate_dependency_complete"],
            f"{path}.candidate_dependency_complete",
        ),
        uncertainty_codes=_decode_uncertainty_codes(
            row["uncertainty_codes"], f"{path}.uncertainty_codes"
        ),
        authoritative=_boolean(row["authoritative"], f"{path}.authoritative"),
    )


def _decode_numeric_reference(value: object, path: str) -> NumericReference:
    row = _object(value, path, _NUMERIC_REF_KEYS)
    try:
        kind = NumericReferenceKind(_string(row["kind"], f"{path}.kind"))
    except ValueError as exc:
        raise TraceContractError(f"{path}.kind is unsupported") from exc
    return NumericReference(
        kind=kind,
        event_id=_optional_string(row["event_id"], f"{path}.event_id"),
        health_operation_id=_optional_string(
            row["health_operation_id"], f"{path}.health_operation_id"
        ),
        field_key=_optional_string(row["field_key"], f"{path}.field_key"),
        literal_value=_optional_number(
            row["literal_value"], f"{path}.literal_value"
        ),
    )


def _decode_numeric_payload(value: object, path: str) -> NumericPayload:
    row = _object(value, path, _NUMERIC_PAYLOAD_KEYS)
    return NumericPayload(
        key=_string(row["key"], f"{path}.key"),
        value=_number(row["value"], f"{path}.value"),
        reference=_decode_numeric_reference(
            row["reference"], f"{path}.reference"
        ),
    )


def _validate_event_local_shape(event: StateEvent) -> None:
    kind = event.kind
    if kind in {StateEventKind.HEALTH_CONTEXT_ENTER, StateEventKind.HEALTH_CONTEXT_EXIT}:
        _required(event.health_operation_id, f"{kind.value} health_operation_id")
        _required(event.call_id, f"{kind.value} call_id")
        if kind is StateEventKind.HEALTH_CONTEXT_EXIT:
            _required(event.parent_event_id, "health_context_exit parent_event_id")
    elif kind in {StateEventKind.EVENT_CALLBACK_ENTER, StateEventKind.EVENT_CALLBACK_EXIT}:
        _required(event.call_id, f"{kind.value} call_id")
        _required(event.channel, f"{kind.value} channel")
        _required(event.key, f"{kind.value} key")
        if kind is StateEventKind.EVENT_CALLBACK_EXIT:
            _required(event.parent_event_id, "event_callback_exit parent_event_id")
    elif kind in {
        StateEventKind.TASK_ENQUEUE,
        StateEventKind.TASK_EXECUTE_ENTER,
        StateEventKind.TASK_EXECUTE_EXIT,
    }:
        for field in (
            "task_id",
            "queue_id",
            "queue_sequence",
            "enqueue_frame",
            "delay_frames",
            "execute_by_frame",
        ):
            _required(getattr(event, field), f"{kind.value} {field}")
        assert event.enqueue_frame is not None
        assert event.delay_frames is not None
        assert event.execute_by_frame is not None
        if event.execute_by_frame != event.enqueue_frame + event.delay_frames:
            raise TraceContractError("task execute_by_frame arithmetic mismatch")
        if kind is not StateEventKind.TASK_ENQUEUE:
            _required(event.call_id, f"{kind.value} call_id")
            _required(event.value, f"{kind.value} execution frame")
            assert event.value is not None
            if event.value < event.execute_by_frame or not event.value.is_integer():
                raise TraceContractError("task executed before due queue frame")
        elif event.value is not None:
            raise TraceContractError("task_enqueue cannot carry execution frame")
        if kind is StateEventKind.TASK_EXECUTE_EXIT:
            _required(event.parent_event_id, "task_execute_exit parent_event_id")
    elif kind is StateEventKind.STATUS_READ:
        for field in ("owner_index", "key", "operation", "expiry_frame", "value"):
            _required(getattr(event, field), f"status_read {field}")
        assert event.operation is not None
        assert event.expiry_frame is not None and event.value is not None
        if event.operation == "active":
            expected = event.expiry_frame == -1 or event.expiry_frame >= event.frame
            if event.expiry_frame == 0:
                expected = False
            if event.result is None or event.value not in {0.0, 1.0}:
                raise TraceContractError("invalid active status value")
            if event.result is not expected or (event.value == 1.0) is not event.result:
                raise TraceContractError("status active expiry mismatch")
        elif event.operation == "duration":
            expected = max(event.expiry_frame - event.frame, 0)
            if event.result is not None or not _close(event.value, float(expected)):
                raise TraceContractError("status duration mismatch")
        elif event.operation == "expiry":
            if event.result is not None or not _close(event.value, float(event.expiry_frame)):
                raise TraceContractError("status expiry mismatch")
        else:
            raise TraceContractError("status_read operation is unsupported")
    elif kind is StateEventKind.STATUS_ADD:
        for field in ("owner_index", "key", "before", "after", "expiry_frame", "result"):
            _required(getattr(event, field), f"status_add {field}")
        assert event.after is not None and event.expiry_frame is not None
        if int(event.after) != event.expiry_frame:
            raise TraceContractError("status_add expiry mismatch")
    elif kind is StateEventKind.STATUS_DELETE:
        for field in ("owner_index", "key", "before", "result", "accepted"):
            _required(getattr(event, field), f"status_delete {field}")
    elif kind is StateEventKind.STATE_SLOT_REGISTER:
        for field in ("slot_id", "key", "value"):
            _required(getattr(event, field), f"state_slot_register {field}")
    elif kind is StateEventKind.STATE_READ:
        _required(event.slot_id, "state_read slot_id")
        _required(event.value, "state_read value")
    elif kind is StateEventKind.STATE_WRITE:
        _required(event.slot_id, "state_write slot_id")
        _required(event.before, "state_write before")
        _required(event.after, "state_write after")
    elif kind is StateEventKind.STATE_RESYNC:
        _required(event.slot_id, "state_resync slot_id")
        _required(event.before, "state_resync before")
        _required(event.after, "state_resync after")
        if event.candidate_dependency_complete or (
            "state_slot_unobserved_mutation" not in event.uncertainty_codes
        ):
            raise TraceContractError(
                "state_resync must remain incomplete with its uncertainty code"
            )
    elif kind is StateEventKind.NUMERIC_EVAL:
        _required(event.operation, "numeric_eval operation")
        _required(event.value, "numeric_eval value")
        if event.operation not in _NUMERIC_OPERATIONS:
            raise TraceContractError("numeric_eval operation is unsupported")
    elif kind is StateEventKind.GUARD_EVAL:
        _required(event.operation, "guard_eval operation")
        _required(event.result, "guard_eval result")
        if event.operation not in _GUARD_OPERATIONS:
            raise TraceContractError("guard_eval operation is unsupported")
        if event.operation == "observed" and (
            event.inputs
            or event.candidate_dependency_complete
            or "guard_operand_dependency_incomplete" not in event.uncertainty_codes
        ):
            raise TraceContractError("observed guard must remain an opaque boundary")
    elif kind is StateEventKind.MODIFIER_EVAL:
        for field in ("channel", "key", "expiry_frame", "owner_index", "accepted"):
            _required(getattr(event, field), f"modifier_eval {field}")
        if event.accepted is False and event.output:
            raise TraceContractError("rejected modifier_eval cannot carry output")
    elif kind is StateEventKind.MAX_HP_READ:
        _required(event.owner_index, "max_hp_read owner_index")
        if set(event.output_map) != {"base_hp", "hp%", "hp", "max_hp"}:
            raise TraceContractError("max_hp_read output has wrong exact keys")
        output = event.output_map
        expected = output["base_hp"] * (1.0 + output["hp%"]) + output["hp"]
        if not _close(output["max_hp"], expected):
            raise TraceContractError("max_hp_read does not recompute")
    elif kind is StateEventKind.HEALTH_FIELD_BINDING:
        for field in ("health_operation_id", "key", "value", "bound_event_id"):
            _required(getattr(event, field), f"health_field_binding {field}")
        if event.key not in _HEALTH_NUMERIC_FIELDS:
            raise TraceContractError("health_field_binding key is unsupported")


def _validate_state_timeline(trace: StateEvidenceTrace) -> None:
    if not isinstance(trace.state_slots, tuple) or any(
        not isinstance(row, StateSlot) for row in trace.state_slots
    ):
        raise TraceContractError("state_slots contain invalid rows")
    if not isinstance(trace.state_events, tuple) or any(
        not isinstance(row, StateEvent) for row in trace.state_events
    ):
        raise TraceContractError("state_events contain invalid rows")
    if tuple(row.sequence_index for row in trace.state_slots) != tuple(
        range(len(trace.state_slots))
    ):
        raise TraceContractError("state slot sequence must be contiguous")
    if tuple(row.sequence_index for row in trace.state_events) != tuple(
        range(len(trace.state_events))
    ):
        raise TraceContractError("state event sequence must be contiguous")
    frames = tuple(row.frame for row in trace.state_events)
    if frames != tuple(sorted(frames)):
        raise TraceContractError("state event frames must be nondecreasing")

    request = trace.reaction_evidence.terminal_trace.request
    character_keys = request.character_keys
    event_map = {row.event_id: row for row in trace.state_events}
    slot_map = {row.slot_id: row for row in trace.state_slots}
    operation_map = {row.operation_id: row for row in trace.health_operations}
    occurrence_map = {row.occurrence_id: row for row in trace.occurrences}
    manifest = trace.source_manifest_binding.manifest_body

    slot_coordinates: set[tuple[str, str, str, int, int]] = set()
    for slot in trace.state_slots:
        _validate_provider_owner(slot.provider, character_keys)
        coordinate = (
            slot.scope,
            slot.provider.kind,
            slot.provider.key,
            slot.provider.owner_index,
            slot.provider.piece_count,
        )
        coordinate += (slot.slot_key,)
        if coordinate in slot_coordinates:
            raise TraceContractError("state slot coordinate is duplicated")
        slot_coordinates.add(coordinate)
        registration = event_map.get(slot.registration_event_id)
        if registration is None or registration.kind is not StateEventKind.STATE_SLOT_REGISTER:
            raise TraceContractError("state slot registration event is missing")
        if registration.slot_id != slot.slot_id:
            raise TraceContractError("state slot registration slot mismatch")
        if registration.key != slot.slot_key or registration.provider != slot.provider:
            raise TraceContractError("state slot registration identity mismatch")
        if registration.value is None or not _close(
            registration.value, slot.initial_value
        ):
            raise TraceContractError("state slot registration value mismatch")
        if (
            registration.candidate_dependency_complete
            != slot.candidate_dependency_complete
            or registration.uncertainty_codes != slot.uncertainty_codes
        ):
            raise TraceContractError("state slot registration evidence mismatch")

    current_slot_values = {
        row.slot_id: row.initial_value for row in trace.state_slots
    }
    task_enqueues: dict[str, StateEvent] = {}
    task_enters: dict[str, StateEvent] = {}
    task_exits: dict[str, StateEvent] = {}
    call_enters: dict[str, StateEvent] = {}
    call_exits: set[str] = set()
    executed_queue_order: dict[str, tuple[int, int]] = {}
    prior_map: dict[str, StateEvent] = {}

    for event in trace.state_events:
        _validate_provider_owner(event.provider, character_keys)
        for index_name in ("owner_index", "target_index"):
            index = getattr(event, index_name)
            if index is not None and index >= len(character_keys):
                raise TraceContractError(f"state event {index_name} is out of range")
        _validate_event_source(event, occurrence_map, manifest)
        if event.parent_event_id is not None:
            parent = prior_map.get(event.parent_event_id)
            if parent is None:
                raise TraceContractError("state parent_event_id must be backward")
            if parent.frame > event.frame:
                raise TraceContractError("state parent event is later than child")
        if event.health_operation_id is not None:
            operation = operation_map.get(event.health_operation_id)
            if operation is None:
                raise TraceContractError("state event references unknown health operation")
            if operation.frame > event.frame:
                raise TraceContractError("health operation is later than state event")
        _validate_parameters(event, character_keys, manifest)
        resolved_inputs = tuple(
            _resolve_numeric_reference(
                reference,
                event=event,
                prior_events=prior_map,
                operations=operation_map,
            )
            for reference in event.inputs
        )
        _validate_event_computation(event, resolved_inputs, manifest)
        for payload in event.numeric_payload:
            resolved = _resolve_numeric_reference(
                payload.reference,
                event=event,
                prior_events=prior_map,
                operations=operation_map,
            )
            if isinstance(resolved, bool) or not _close(payload.value, resolved):
                raise TraceContractError("task numeric payload reference mismatch")
            if event.candidate_dependency_complete and not _reference_complete(
                payload.reference, prior_map, operation_map
            ):
                raise TraceContractError(
                    "complete task payload depends on incomplete evidence"
                )
        if event.candidate_dependency_complete:
            if any(
                not _reference_complete(reference, prior_map, operation_map)
                for reference in event.inputs
            ):
                raise TraceContractError(
                    "complete state event depends on incomplete evidence"
                )
            if any(
                not prior_map[modifier_id].candidate_dependency_complete
                for modifier_id in event.modifier_eval_ids
            ):
                raise TraceContractError(
                    "complete state event depends on incomplete modifier"
                )
            if event.slot_id is not None and not slot_map[
                event.slot_id
            ].candidate_dependency_complete:
                raise TraceContractError(
                    "complete state event depends on incomplete slot"
                )

        if event.kind is StateEventKind.STATE_SLOT_REGISTER:
            assert event.slot_id is not None
            if event.slot_id not in slot_map:
                raise TraceContractError("registration references unknown state slot")
        elif event.kind is StateEventKind.STATE_READ:
            assert event.slot_id is not None and event.value is not None
            if event.slot_id not in current_slot_values:
                raise TraceContractError("state read references unknown slot")
            if not _close(event.value, current_slot_values[event.slot_id]):
                raise TraceContractError("state read does not match slot ledger")
        elif event.kind is StateEventKind.STATE_WRITE:
            assert event.slot_id is not None
            assert event.before is not None and event.after is not None
            if event.slot_id not in current_slot_values:
                raise TraceContractError("state write references unknown slot")
            if not _close(event.before, current_slot_values[event.slot_id]):
                raise TraceContractError("state write before does not match ledger")
            current_slot_values[event.slot_id] = event.after
        elif event.kind is StateEventKind.STATE_RESYNC:
            assert event.slot_id is not None
            assert event.before is not None and event.after is not None
            if event.slot_id not in current_slot_values:
                raise TraceContractError("state resync references unknown slot")
            if not _close(event.before, current_slot_values[event.slot_id]):
                raise TraceContractError("state resync before does not match ledger")
            current_slot_values[event.slot_id] = event.after
        elif event.kind in {
            StateEventKind.HEALTH_CONTEXT_ENTER,
            StateEventKind.EVENT_CALLBACK_ENTER,
            StateEventKind.TASK_EXECUTE_ENTER,
        }:
            assert event.call_id is not None
            if event.call_id != event.event_id or event.call_id in call_enters:
                raise TraceContractError("call enter identity is not unique/self-bound")
            call_enters[event.call_id] = event
        elif event.kind in {
            StateEventKind.HEALTH_CONTEXT_EXIT,
            StateEventKind.EVENT_CALLBACK_EXIT,
            StateEventKind.TASK_EXECUTE_EXIT,
        }:
            assert event.call_id is not None
            enter = call_enters.get(event.call_id)
            if enter is None or enter.event_id != event.parent_event_id:
                raise TraceContractError("call exit does not pair with its enter")
            if event.call_id in call_exits:
                raise TraceContractError("call exits more than once")
            expected_exit = {
                StateEventKind.HEALTH_CONTEXT_ENTER: StateEventKind.HEALTH_CONTEXT_EXIT,
                StateEventKind.EVENT_CALLBACK_ENTER: StateEventKind.EVENT_CALLBACK_EXIT,
                StateEventKind.TASK_EXECUTE_ENTER: StateEventKind.TASK_EXECUTE_EXIT,
            }[enter.kind]
            if event.kind is not expected_exit:
                raise TraceContractError("call enter/exit kinds do not match")
            if enter.health_operation_id != event.health_operation_id:
                raise TraceContractError("call enter/exit health context mismatch")
            call_exits.add(event.call_id)

        if event.kind is StateEventKind.TASK_ENQUEUE:
            assert event.task_id is not None
            if event.task_id in task_enqueues:
                raise TraceContractError("task enqueue ID is duplicated")
            task_enqueues[event.task_id] = event
        elif event.kind is StateEventKind.TASK_EXECUTE_ENTER:
            assert event.task_id is not None and event.queue_id is not None
            enqueue = task_enqueues.get(event.task_id)
            if enqueue is None:
                raise TraceContractError("task execution has no prior enqueue")
            if event.task_id in task_enters:
                raise TraceContractError("task executes more than once")
            _validate_task_metadata(enqueue, event)
            assert event.execute_by_frame is not None
            assert event.queue_sequence is not None
            if event.frame < event.execute_by_frame:
                raise TraceContractError("task executed before its due frame")
            order = (event.execute_by_frame, event.queue_sequence)
            previous = executed_queue_order.get(event.queue_id)
            if previous is not None and (
                order[0] < previous[0]
                or (order[0] == previous[0] and order[1] <= previous[1])
            ):
                raise TraceContractError("task queue execution order regressed")
            executed_queue_order[event.queue_id] = order
            task_enters[event.task_id] = event
        elif event.kind is StateEventKind.TASK_EXECUTE_EXIT:
            assert event.task_id is not None
            enter = task_enters.get(event.task_id)
            if enter is None:
                raise TraceContractError("task exit has no execution enter")
            if event.task_id in task_exits:
                raise TraceContractError("task execution exits more than once")
            _validate_task_metadata(enter, event)
            task_exits[event.task_id] = event

        if event.kind is StateEventKind.MAX_HP_READ:
            for modifier_id in event.modifier_eval_ids:
                modifier = prior_map.get(modifier_id)
                if modifier is None or modifier.kind is not StateEventKind.MODIFIER_EVAL:
                    raise TraceContractError(
                        "max_hp_read modifier_eval_ids must be backward modifier rows"
                    )
                if modifier.owner_index != event.owner_index:
                    raise TraceContractError("max_hp modifier recipient mismatch")
                if modifier.channel != "stat":
                    raise TraceContractError("max_hp modifier channel must be 'stat'")
        elif event.kind is StateEventKind.HEALTH_FIELD_BINDING:
            _validate_health_field_binding(event, prior_map, operation_map)

        prior_map[event.event_id] = event

    for call_id, enter in call_enters.items():
        if call_id not in call_exits and enter.candidate_dependency_complete:
            raise TraceContractError("complete call enter has no matching exit")
    duration_frames = trace.duration_frames
    for task_id, enqueue in task_enqueues.items():
        if (
            task_id not in task_enters
            and enqueue.candidate_dependency_complete
            and enqueue.execute_by_frame is not None
            and enqueue.execute_by_frame <= duration_frames
        ):
            raise TraceContractError("complete task enqueue has no execution")
    for task_id, enter in task_enters.items():
        if task_id not in task_exits and enter.candidate_dependency_complete:
            raise TraceContractError("complete task execution has no exit")


def _validate_event_source(
    event: StateEvent,
    occurrences: Mapping[str, SourceOccurrence],
    manifest,
) -> None:
    if event.source_id is not None and manifest.entry_by_id(event.source_id) is None:
        raise TraceContractError("state event source_id is absent from manifest")
    if event.source_occurrence_id is None:
        return
    if event.source_id is None:
        raise TraceContractError("source occurrence requires state event source_id")
    occurrence = occurrences.get(event.source_occurrence_id)
    if occurrence is None:
        raise TraceContractError("state event source occurrence is unknown")
    if occurrence.source_id != event.source_id:
        raise TraceContractError("state event source/occurrence mismatch")
    if occurrence.provider != event.provider:
        raise TraceContractError("state event occurrence/provider mismatch")
    if occurrence.frame > event.frame:
        raise TraceContractError("state event occurrence is later than event")


def _validate_parameters(
    event: StateEvent,
    character_keys: tuple[str, ...],
    manifest,
) -> None:
    for parameter in event.parameters:
        if parameter.actor_index is not None:
            if parameter.actor_index >= len(character_keys):
                raise TraceContractError("state parameter actor index is out of range")
            if parameter.actor_key != character_keys[parameter.actor_index]:
                raise TraceContractError("state parameter actor identity mismatch")
    if event.template_sha256 is None:
        if event.parameters:
            raise TraceContractError("state parameters require template_sha256")
        return
    if event.source_id is None:
        raise TraceContractError("state template requires source_id")
    entry = manifest.entry_by_id(event.source_id)
    if entry is None or entry.template.template_sha256 != event.template_sha256:
        raise TraceContractError("state event template/source identity mismatch")
    actual_keys = tuple(row.parameter_key for row in event.parameters)
    expected_keys = entry.template.parameter_keys
    if event.candidate_dependency_complete:
        if actual_keys != expected_keys:
            raise TraceContractError(
                "complete state event parameters do not match source template"
            )
        return
    if not set(actual_keys).issubset(expected_keys):
        raise TraceContractError(
            "incomplete state event parameters exceed source template"
        )


def _resolve_numeric_reference(
    reference: NumericReference,
    *,
    event: StateEvent,
    prior_events: Mapping[str, StateEvent],
    operations: Mapping[str, HealthOperation],
) -> float | bool:
    if reference.kind is NumericReferenceKind.LITERAL:
        assert reference.literal_value is not None
        return reference.literal_value
    if reference.kind is NumericReferenceKind.HEALTH_FIELD:
        assert reference.health_operation_id is not None
        assert reference.field_key is not None
        operation = operations.get(reference.health_operation_id)
        if operation is None:
            raise TraceContractError("numeric reference health operation is unknown")
        return _health_field_value(operation, reference.field_key)
    assert reference.event_id is not None
    source = prior_events.get(reference.event_id)
    if source is None:
        raise TraceContractError("numeric event reference must be backward")
    if source.frame > event.frame:
        raise TraceContractError("numeric event reference is later than consumer")
    if reference.field_key is not None:
        output = source.output_map
        if reference.field_key not in output:
            raise TraceContractError(
                "numeric event output reference points to an unknown field"
            )
        return output[reference.field_key]
    if source.value is None:
        raise TraceContractError("numeric event reference has no scalar output")
    return source.value


def _reference_complete(
    reference: NumericReference,
    events: Mapping[str, StateEvent],
    operations: Mapping[str, HealthOperation],
) -> bool:
    if reference.kind is NumericReferenceKind.LITERAL:
        return True
    if reference.kind is NumericReferenceKind.EVENT:
        assert reference.event_id is not None
        return events[reference.event_id].candidate_dependency_complete
    assert reference.health_operation_id is not None
    return operations[reference.health_operation_id].candidate_dependency_complete


def _validate_event_computation(
    event: StateEvent,
    inputs: tuple[float | bool, ...],
    manifest,
) -> None:
    if event.kind is StateEventKind.NUMERIC_EVAL:
        assert event.operation is not None and event.value is not None
        if event.operation in {
            "source_expression",
            "health_input",
            "task_payload",
            "state_transition",
        }:
            if event.candidate_dependency_complete or (
                "numeric_marker_replay_not_recomputed"
                not in event.uncertainty_codes
            ):
                raise TraceContractError(
                    "unrecomputed numeric marker must be incomplete with its "
                    "frozen uncertainty code"
                )
            return
        if event.operation == "literal":
            if inputs:
                raise TraceContractError("literal requires zero inputs")
            return
        numeric = _numeric_inputs(inputs, event.operation)
        expected = _evaluate_numeric_operation(event.operation, numeric)
        if not _close(event.value, expected):
            raise TraceContractError("numeric_eval result does not recompute")
    elif event.kind is StateEventKind.GUARD_EVAL:
        assert event.operation is not None and event.result is not None
        if event.operation == "observed":
            return
        expected = _evaluate_guard_operation(event.operation, inputs)
        if event.result is not expected:
            raise TraceContractError("guard_eval result does not recompute")


def _evaluate_numeric_operation(operation: str, values: tuple[float, ...]) -> float:
    if operation in {"identity", "health_input", "task_payload"}:
        if len(values) != 1:
            raise TraceContractError(f"{operation} requires one input")
        return values[0]
    if operation == "negate":
        if len(values) != 1:
            raise TraceContractError("negate requires one input")
        return -values[0]
    if operation in {"add", "multiply", "min", "max"} and not values:
        raise TraceContractError(f"{operation} requires at least one input")
    if operation == "add":
        return sum(values)
    if operation == "multiply":
        result = 1.0
        for value in values:
            result *= value
        return _finite_result(result, "multiply")
    if operation == "min":
        return min(values)
    if operation == "max":
        return max(values)
    if len(values) != 2:
        raise TraceContractError(f"{operation} requires two inputs")
    if operation == "subtract":
        return values[0] - values[1]
    if values[1] == 0:
        raise TraceContractError("divide denominator must be non-zero")
    return _finite_result(values[0] / values[1], "divide")


def _evaluate_guard_operation(
    operation: str,
    values: tuple[float | bool, ...],
) -> bool:
    if operation == "not":
        if len(values) != 1 or values[0] not in {0.0, 1.0}:
            raise TraceContractError("not requires one 0/1 input")
        return values[0] == 0.0
    if operation in {"and", "or"}:
        if len(values) < 2 or any(value not in {0.0, 1.0} for value in values):
            raise TraceContractError(f"{operation} requires 0/1 inputs")
        return all(value == 1.0 for value in values) if operation == "and" else any(value == 1.0 for value in values)
    if len(values) != 2:
        raise TraceContractError(f"{operation} requires two numeric inputs")
    left, right = values
    if operation == "eq":
        return left == right
    if operation == "ne":
        return left != right
    if operation == "lt":
        return left < right
    if operation == "lte":
        return left <= right
    if operation == "gt":
        return left > right
    return left >= right


def _validate_task_metadata(left: StateEvent, right: StateEvent) -> None:
    for field in (
        "task_id",
        "queue_id",
        "queue_sequence",
        "enqueue_frame",
        "delay_frames",
        "execute_by_frame",
        "numeric_payload",
    ):
        if getattr(left, field) != getattr(right, field):
            raise TraceContractError(f"task {field} changed between receipts")


def _validate_health_field_binding(
    event: StateEvent,
    events: Mapping[str, StateEvent],
    operations: Mapping[str, HealthOperation],
) -> None:
    assert event.health_operation_id is not None
    assert event.key is not None
    assert event.value is not None
    assert event.bound_event_id is not None
    operation = operations[event.health_operation_id]
    observed = _health_field_value(operation, event.key)
    if not _close(event.value, observed):
        raise TraceContractError("health field binding does not match V5 field")
    bound = events.get(event.bound_event_id)
    if bound is None:
        raise TraceContractError("health field binding must reference earlier event")
    if event.key in {"max_hp_before", "max_hp_after"}:
        if bound.kind is not StateEventKind.MAX_HP_READ:
            raise TraceContractError("MaxHP health field must bind max_hp_read")
        bound_value = bound.output_map["max_hp"]
    else:
        if bound.value is None:
            raise TraceContractError("health field bound event has no scalar value")
        bound_value = bound.value
    if not _close(event.value, bound_value):
        raise TraceContractError("health field/bound event value mismatch")
    if event.candidate_dependency_complete and not bound.candidate_dependency_complete:
        raise TraceContractError("complete health binding points to incomplete event")
    if event.key == "adjusted_input_value" and not operation.candidate_dependency_complete:
        if event.candidate_dependency_complete:
            raise TraceContractError(
                "adjusted_input_value cannot be exact for incomplete health operation"
            )


def _health_field_value(operation: HealthOperation, field_key: str) -> float:
    if field_key not in _HEALTH_NUMERIC_FIELDS:
        raise TraceContractError("health numeric reference field is unsupported")
    value = getattr(operation, field_key)
    if value is None:
        raise TraceContractError("health numeric reference points to null field")
    return float(value)


def _validate_provider_owner(
    provider: ProviderIdentity,
    character_keys: tuple[str, ...],
) -> None:
    if provider.known and provider.owner_index >= len(character_keys):
        raise TraceContractError("state provider owner_index exceeds character catalog")
    if (
        provider.known
        and provider.kind.casefold() == "character"
        and character_keys[provider.owner_index] != provider.key
    ):
        raise TraceContractError("state character provider owner binding mismatch")


def _decode_uncertainty_codes(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _validate_dependency_evidence(
    complete: object,
    uncertainty_codes: object,
    label: str,
) -> None:
    if not isinstance(complete, bool):
        raise TraceContractError(f"{label} completeness must be boolean")
    if not isinstance(uncertainty_codes, tuple):
        raise TraceContractError(f"{label} uncertainty_codes must be a tuple")
    _sorted_unique_strings(uncertainty_codes, f"{label} uncertainty_codes")
    if complete and uncertainty_codes:
        raise TraceContractError(f"complete {label} cannot retain uncertainty")
    if not complete and not uncertainty_codes:
        raise TraceContractError(f"incomplete {label} requires uncertainty")


def _sorted_unique_strings(
    values: tuple[str, ...],
    label: str,
    *,
    preserve_order: bool = False,
) -> None:
    for value in values:
        _trimmed(value, f"{label} item")
    if len(values) != len(set(values)):
        raise TraceContractError(f"{label} must be unique")
    if not preserve_order and values != tuple(sorted(values)):
        raise TraceContractError(f"{label} must be sorted")


def _numeric_inputs(
    values: tuple[float | bool, ...],
    operation: str,
) -> tuple[float, ...]:
    if any(isinstance(value, bool) for value in values):
        raise TraceContractError(f"{operation} requires numeric inputs")
    return tuple(float(value) for value in values)


def _finite_result(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise TraceContractError(f"{label} produced non-finite result")
    return value


def _integer_value(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{label} must be an integer")


def _nonnegative_int(value: object, label: str) -> None:
    _integer_value(value, label)
    if value < 0:
        raise TraceContractError(f"{label} must be non-negative")


def _optional_nonnegative_int(value: object, label: str) -> None:
    if value is not None:
        _nonnegative_int(value, label)


def _trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _trimmed_key(value: object, label: str) -> str:
    _trimmed(value, label)
    assert isinstance(value, str)
    return value


def _optional_trimmed(value: object, label: str) -> None:
    if value is not None:
        _trimmed(value, label)


def _required(value: object, label: str) -> None:
    if value is None:
        raise TraceContractError(f"{label} is required")


def _finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{label} must be finite")


def _optional_finite(value: object, label: str) -> None:
    if value is not None:
        _finite(value, label)


def _optional_bool(value: object, label: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise TraceContractError(f"{label} must be boolean or null")


def _optional_sha256(value: object, label: str) -> None:
    if value is not None and (
        not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
    ):
        raise TraceContractError(f"{label} must be a lowercase SHA-256 or null")


def _optional_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _integer(value, path)


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _optional_boolean(value: object, path: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, path)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


__all__ = [
    "NumericPayload",
    "NumericReference",
    "NumericReferenceKind",
    "STATE_EVIDENCE_CAPABILITY",
    "STATE_EVIDENCE_KIND",
    "STATE_EVIDENCE_SCHEMA_VERSION",
    "StateEvent",
    "StateEventKind",
    "StateEvidenceTrace",
    "StateSlot",
    "decode_state_events",
    "decode_state_slots",
]
