"""Strict JSON codec for trace-equation contracts.

Known schema versions reject missing/unknown keys, duplicate object keys,
non-finite numbers, trailing JSON and closed-enum drift.  Formula kinds and
reaction operator IDs are deliberately raw strings: their contracts require
identity-preserving exact fallback rather than a decode failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import math
from typing import TypeVar

from .contracts import (
    CallbackPhase,
    DamageFormulaInputs,
    FormulaProvenance,
    FormulaValue,
    GuardKind,
    GuardObservation,
    GuardOperator,
    GuardPredicate,
    GuardTopologyReport,
    ProvenanceSourceKind,
    ReplayAssessment,
    ReplayStatus,
    ScalingKind,
    SnapshotStat,
    TopologyChannel,
    TopologyChannelDigest,
    TopologyEvidenceEvent,
    TraceContractError,
    TraceDamageMode,
    TraceDocument,
    TraceExtractionReceipt,
    TraceExtractionRequest,
    TraceHitCompleteness,
    TraceHitEvent,
    TraceLineage,
    TraceObjective,
    ValueReadMode,
    canonical_json,
)


_EnumT = TypeVar("_EnumT")


def encode_trace_document(document: TraceDocument) -> str:
    if not isinstance(document, TraceDocument):
        raise TraceContractError("document must be TraceDocument")
    return canonical_json(document.to_dict())


def decode_trace_document(payload: str | bytes | bytearray) -> TraceDocument:
    root = _decode_json(payload)
    row = _object(
        root,
        "$",
        {"schema_version", "kind", "request", "receipt", "hits", "topology"},
    )
    return TraceDocument(
        schema_version=_integer(row["schema_version"], "$.schema_version"),
        kind=_string(row["kind"], "$.kind"),
        request=_request(row["request"], "$.request"),
        receipt=_receipt(row["receipt"], "$.receipt"),
        hits=tuple(
            _hit(item, f"$.hits[{index}]")
            for index, item in enumerate(_array(row["hits"], "$.hits"))
        ),
        topology=_topology(row["topology"], "$.topology"),
    )


def encode_replay_assessment(assessment: ReplayAssessment) -> str:
    if not isinstance(assessment, ReplayAssessment):
        raise TraceContractError("assessment must be ReplayAssessment")
    return canonical_json(assessment.to_dict())


def decode_replay_assessment(payload: str | bytes | bytearray) -> ReplayAssessment:
    root = _decode_json(payload)
    row = _object(
        root,
        "$",
        {
            "schema_version",
            "kind",
            "trace_receipt_sha256",
            "candidate_sha256",
            "status",
            "triggered_guard_ids",
            "reason_codes",
            "replayed_hit_count",
        },
    )
    return ReplayAssessment(
        schema_version=_integer(row["schema_version"], "$.schema_version"),
        kind=_string(row["kind"], "$.kind"),
        trace_receipt_sha256=_string(
            row["trace_receipt_sha256"], "$.trace_receipt_sha256"
        ),
        candidate_sha256=_string(row["candidate_sha256"], "$.candidate_sha256"),
        status=_enum(ReplayStatus, row["status"], "$.status"),
        triggered_guard_ids=_string_tuple(
            row["triggered_guard_ids"], "$.triggered_guard_ids"
        ),
        reason_codes=_string_tuple(row["reason_codes"], "$.reason_codes"),
        replayed_hit_count=_integer(
            row["replayed_hit_count"], "$.replayed_hit_count"
        ),
    )


def _request(value: object, path: str) -> TraceExtractionRequest:
    row = _object(
        value,
        path,
        {
            "schema_version",
            "kind",
            "context_sha256",
            "source_config_sha256",
            "compiled_action_sha256",
            "target_sha256",
            "engine_artifact_sha256",
            "engine_binding_sha256",
            "formula_version",
            "formula_sha256",
            "seed",
            "objective",
            "character_keys",
            "required_capabilities",
        },
    )
    return TraceExtractionRequest(
        schema_version=_integer(row["schema_version"], f"{path}.schema_version"),
        kind=_string(row["kind"], f"{path}.kind"),
        context_sha256=_string(row["context_sha256"], f"{path}.context_sha256"),
        source_config_sha256=_string(
            row["source_config_sha256"], f"{path}.source_config_sha256"
        ),
        compiled_action_sha256=_string(
            row["compiled_action_sha256"], f"{path}.compiled_action_sha256"
        ),
        target_sha256=_string(row["target_sha256"], f"{path}.target_sha256"),
        engine_artifact_sha256=_string(
            row["engine_artifact_sha256"], f"{path}.engine_artifact_sha256"
        ),
        engine_binding_sha256=_string(
            row["engine_binding_sha256"], f"{path}.engine_binding_sha256"
        ),
        formula_version=_string(row["formula_version"], f"{path}.formula_version"),
        formula_sha256=_string(row["formula_sha256"], f"{path}.formula_sha256"),
        seed=_integer(row["seed"], f"{path}.seed"),
        objective=_enum(TraceObjective, row["objective"], f"{path}.objective"),
        character_keys=_string_tuple(row["character_keys"], f"{path}.character_keys"),
        required_capabilities=_string_tuple(
            row["required_capabilities"], f"{path}.required_capabilities"
        ),
    )


def _receipt(value: object, path: str) -> TraceExtractionReceipt:
    row = _object(
        value,
        path,
        {
            "schema_version",
            "kind",
            "request_sha256",
            "trace_body_sha256",
            "topology_sha256",
            "engine_artifact_sha256",
            "engine_binding_sha256",
            "formula_version",
            "formula_sha256",
            "seed",
            "hit_count",
        },
    )
    return TraceExtractionReceipt(
        schema_version=_integer(row["schema_version"], f"{path}.schema_version"),
        kind=_string(row["kind"], f"{path}.kind"),
        request_sha256=_string(row["request_sha256"], f"{path}.request_sha256"),
        trace_body_sha256=_string(
            row["trace_body_sha256"], f"{path}.trace_body_sha256"
        ),
        topology_sha256=_string(
            row["topology_sha256"], f"{path}.topology_sha256"
        ),
        engine_artifact_sha256=_string(
            row["engine_artifact_sha256"], f"{path}.engine_artifact_sha256"
        ),
        engine_binding_sha256=_string(
            row["engine_binding_sha256"], f"{path}.engine_binding_sha256"
        ),
        formula_version=_string(row["formula_version"], f"{path}.formula_version"),
        formula_sha256=_string(row["formula_sha256"], f"{path}.formula_sha256"),
        seed=_integer(row["seed"], f"{path}.seed"),
        hit_count=_integer(row["hit_count"], f"{path}.hit_count"),
    )


def _hit(value: object, path: str) -> TraceHitEvent:
    row = _object(
        value,
        path,
        {
            "event_id",
            "frame",
            "source_frame",
            "snapshot_frame",
            "actor_index",
            "actor_key",
            "ability",
            "attack_tag",
            "element",
            "target_key",
            "target_index",
            "damage_mode",
            "hp_cap_active",
            "lineage",
            "provenance",
            "formula_inputs",
            "uncapped_rolled_damage",
            "hp_damage_applied",
            "reported_damage",
            "target_hp_before",
            "target_hp_after",
            "target_killed",
            "crit",
            "completeness",
            "unsupported_feature_codes",
            "formula_replay_status",
            "formula_replay_reason_codes",
        },
    )
    return TraceHitEvent(
        event_id=_string(row["event_id"], f"{path}.event_id"),
        frame=_integer(row["frame"], f"{path}.frame"),
        source_frame=_integer(row["source_frame"], f"{path}.source_frame"),
        snapshot_frame=_integer(row["snapshot_frame"], f"{path}.snapshot_frame"),
        actor_index=_integer(row["actor_index"], f"{path}.actor_index"),
        actor_key=_string(row["actor_key"], f"{path}.actor_key"),
        ability=_string(row["ability"], f"{path}.ability"),
        attack_tag=_integer(row["attack_tag"], f"{path}.attack_tag"),
        element=_string(row["element"], f"{path}.element"),
        target_key=_string(row["target_key"], f"{path}.target_key"),
        target_index=_integer(row["target_index"], f"{path}.target_index"),
        damage_mode=_enum(
            TraceDamageMode, row["damage_mode"], f"{path}.damage_mode"
        ),
        hp_cap_active=_boolean(row["hp_cap_active"], f"{path}.hp_cap_active"),
        lineage=_lineage(row["lineage"], f"{path}.lineage"),
        provenance=tuple(
            _provenance(item, f"{path}.provenance[{index}]")
            for index, item in enumerate(
                _array(row["provenance"], f"{path}.provenance")
            )
        ),
        formula_inputs=_formula_inputs(
            row["formula_inputs"], f"{path}.formula_inputs"
        ),
        uncapped_rolled_damage=_number(
            row["uncapped_rolled_damage"], f"{path}.uncapped_rolled_damage"
        ),
        hp_damage_applied=_number(
            row["hp_damage_applied"], f"{path}.hp_damage_applied"
        ),
        reported_damage=_number(row["reported_damage"], f"{path}.reported_damage"),
        target_hp_before=_number(
            row["target_hp_before"], f"{path}.target_hp_before"
        ),
        target_hp_after=_number(row["target_hp_after"], f"{path}.target_hp_after"),
        target_killed=_boolean(row["target_killed"], f"{path}.target_killed"),
        crit=_boolean(row["crit"], f"{path}.crit"),
        completeness=_completeness(row["completeness"], f"{path}.completeness"),
        unsupported_feature_codes=_string_tuple(
            row["unsupported_feature_codes"], f"{path}.unsupported_feature_codes"
        ),
        formula_replay_status=_enum(
            ReplayStatus,
            row["formula_replay_status"],
            f"{path}.formula_replay_status",
        ),
        formula_replay_reason_codes=_string_tuple(
            row["formula_replay_reason_codes"],
            f"{path}.formula_replay_reason_codes",
        ),
    )


def _lineage(value: object, path: str) -> TraceLineage:
    row = _object(
        value,
        path,
        {
            "parent_event_id",
            "source_event_id",
            "damage_source_key",
            "gadget_id",
            "reaction_type",
            "reaction_operator_id",
            "reaction_operator_sha256",
            "opaque_reaction_payload_json",
            "opaque_reaction_payload_sha256",
            "reaction_owner_key",
            "aura_source_keys",
        },
    )
    return TraceLineage(
        parent_event_id=_optional_string(row["parent_event_id"], f"{path}.parent_event_id"),
        source_event_id=_optional_string(row["source_event_id"], f"{path}.source_event_id"),
        damage_source_key=_string(row["damage_source_key"], f"{path}.damage_source_key"),
        gadget_id=_optional_string(row["gadget_id"], f"{path}.gadget_id"),
        reaction_type=_optional_string(row["reaction_type"], f"{path}.reaction_type"),
        reaction_operator_id=_string(
            row["reaction_operator_id"], f"{path}.reaction_operator_id"
        ),
        reaction_operator_sha256=_string(
            row["reaction_operator_sha256"], f"{path}.reaction_operator_sha256"
        ),
        opaque_reaction_payload_json=_optional_string(
            row["opaque_reaction_payload_json"],
            f"{path}.opaque_reaction_payload_json",
        ),
        opaque_reaction_payload_sha256=_optional_string(
            row["opaque_reaction_payload_sha256"],
            f"{path}.opaque_reaction_payload_sha256",
        ),
        reaction_owner_key=_optional_string(
            row["reaction_owner_key"], f"{path}.reaction_owner_key"
        ),
        aura_source_keys=_string_tuple(
            row["aura_source_keys"], f"{path}.aura_source_keys"
        ),
    )


def _provenance(value: object, path: str) -> FormulaProvenance:
    row = _object(
        value,
        path,
        {
            "provenance_id",
            "source_kind",
            "source_key",
            "owner_key",
            "provider_event_id",
            "modifier_key",
            "modifier_channel",
            "read_phase",
            "read_mode",
        },
    )
    return FormulaProvenance(
        provenance_id=_string(row["provenance_id"], f"{path}.provenance_id"),
        source_kind=_enum(
            ProvenanceSourceKind, row["source_kind"], f"{path}.source_kind"
        ),
        source_key=_string(row["source_key"], f"{path}.source_key"),
        owner_key=_optional_string(row["owner_key"], f"{path}.owner_key"),
        provider_event_id=_optional_string(
            row["provider_event_id"], f"{path}.provider_event_id"
        ),
        modifier_key=_optional_string(row["modifier_key"], f"{path}.modifier_key"),
        modifier_channel=_optional_string(
            row["modifier_channel"], f"{path}.modifier_channel"
        ),
        read_phase=_enum(CallbackPhase, row["read_phase"], f"{path}.read_phase"),
        read_mode=_enum(ValueReadMode, row["read_mode"], f"{path}.read_mode"),
    )


def _formula_inputs(value: object, path: str) -> DamageFormulaInputs:
    keys = {
        "formula_kind",
        "formula_sha256",
        "character_level",
        "target_level",
        "scaling_kind",
        "scaling_value",
        "snapshot_stats",
        "mult",
        "base_dmg_bonus",
        "flat_dmg",
        "base_damage",
        "dmg_bonus",
        "raw_crit_rate",
        "crit_rate",
        "crit_damage",
        "crit_roll",
        "hit_weak_point",
        "defense_multiplier",
        "defense_adjustment",
        "ignore_defense_percent",
        "resistance_multiplier",
        "resistance",
        "amplifying",
        "amp_multiplier",
        "elemental_mastery",
        "em_bonus",
        "reaction_bonus",
        "amp_reaction_bonus",
        "group_multiplier",
        "elevation",
        "elevation_multiplier",
    }
    row = _object(value, path, keys)

    def fv(name: str) -> FormulaValue:
        return _formula_value(row[name], f"{path}.{name}")

    crit_roll = row["crit_roll"]
    return DamageFormulaInputs(
        formula_kind=_string(row["formula_kind"], f"{path}.formula_kind"),
        formula_sha256=_string(row["formula_sha256"], f"{path}.formula_sha256"),
        character_level=_integer(row["character_level"], f"{path}.character_level"),
        target_level=_integer(row["target_level"], f"{path}.target_level"),
        scaling_kind=_enum(ScalingKind, row["scaling_kind"], f"{path}.scaling_kind"),
        scaling_value=fv("scaling_value"),
        snapshot_stats=tuple(
            _snapshot_stat(item, f"{path}.snapshot_stats[{index}]")
            for index, item in enumerate(
                _array(row["snapshot_stats"], f"{path}.snapshot_stats")
            )
        ),
        mult=fv("mult"),
        base_dmg_bonus=fv("base_dmg_bonus"),
        flat_dmg=fv("flat_dmg"),
        base_damage=fv("base_damage"),
        dmg_bonus=fv("dmg_bonus"),
        raw_crit_rate=fv("raw_crit_rate"),
        crit_rate=fv("crit_rate"),
        crit_damage=fv("crit_damage"),
        crit_roll=None if crit_roll is None else _formula_value(crit_roll, f"{path}.crit_roll"),
        hit_weak_point=_boolean(row["hit_weak_point"], f"{path}.hit_weak_point"),
        defense_multiplier=fv("defense_multiplier"),
        defense_adjustment=fv("defense_adjustment"),
        ignore_defense_percent=fv("ignore_defense_percent"),
        resistance_multiplier=fv("resistance_multiplier"),
        resistance=fv("resistance"),
        amplifying=_boolean(row["amplifying"], f"{path}.amplifying"),
        amp_multiplier=fv("amp_multiplier"),
        elemental_mastery=fv("elemental_mastery"),
        em_bonus=fv("em_bonus"),
        reaction_bonus=fv("reaction_bonus"),
        amp_reaction_bonus=fv("amp_reaction_bonus"),
        group_multiplier=fv("group_multiplier"),
        elevation=fv("elevation"),
        elevation_multiplier=fv("elevation_multiplier"),
    )


def _formula_value(value: object, path: str) -> FormulaValue:
    row = _object(value, path, {"value", "provenance_ids"})
    return FormulaValue(
        value=_number(row["value"], f"{path}.value"),
        provenance_ids=_string_tuple(row["provenance_ids"], f"{path}.provenance_ids"),
    )


def _snapshot_stat(value: object, path: str) -> SnapshotStat:
    row = _object(value, path, {"stat_key", "value", "provenance_ids"})
    return SnapshotStat(
        stat_key=_string(row["stat_key"], f"{path}.stat_key"),
        value=_number(row["value"], f"{path}.value"),
        provenance_ids=_string_tuple(row["provenance_ids"], f"{path}.provenance_ids"),
    )


def _completeness(value: object, path: str) -> TraceHitCompleteness:
    keys = {
        "formula_complete",
        "flat_dmg_provenance_complete",
        "attack_mod_provenance_complete",
        "reaction_topology_complete",
        "provider_identity_complete",
    }
    row = _object(value, path, keys)
    return TraceHitCompleteness(
        formula_complete=_boolean(row["formula_complete"], f"{path}.formula_complete"),
        flat_dmg_provenance_complete=_boolean(
            row["flat_dmg_provenance_complete"],
            f"{path}.flat_dmg_provenance_complete",
        ),
        attack_mod_provenance_complete=_boolean(
            row["attack_mod_provenance_complete"],
            f"{path}.attack_mod_provenance_complete",
        ),
        reaction_topology_complete=_boolean(
            row["reaction_topology_complete"],
            f"{path}.reaction_topology_complete",
        ),
        provider_identity_complete=_boolean(
            row["provider_identity_complete"],
            f"{path}.provider_identity_complete",
        ),
    )


def _topology(value: object, path: str) -> GuardTopologyReport:
    row = _object(
        value,
        path,
        {
            "schema_version",
            "kind",
            "channels",
            "evidence_events",
            "guards",
            "unsupported_feature_codes",
            "complete",
        },
    )
    return GuardTopologyReport(
        schema_version=_integer(row["schema_version"], f"{path}.schema_version"),
        kind=_string(row["kind"], f"{path}.kind"),
        channels=tuple(
            _topology_channel(item, f"{path}.channels[{index}]")
            for index, item in enumerate(_array(row["channels"], f"{path}.channels"))
        ),
        evidence_events=tuple(
            _topology_event(item, f"{path}.evidence_events[{index}]")
            for index, item in enumerate(
                _array(row["evidence_events"], f"{path}.evidence_events")
            )
        ),
        guards=tuple(
            _guard(item, f"{path}.guards[{index}]")
            for index, item in enumerate(_array(row["guards"], f"{path}.guards"))
        ),
        unsupported_feature_codes=_string_tuple(
            row["unsupported_feature_codes"], f"{path}.unsupported_feature_codes"
        ),
        complete=_boolean(row["complete"], f"{path}.complete"),
    )


def _topology_channel(value: object, path: str) -> TopologyChannelDigest:
    row = _object(value, path, {"channel", "sha256", "item_count", "complete"})
    return TopologyChannelDigest(
        channel=_enum(TopologyChannel, row["channel"], f"{path}.channel"),
        sha256=_string(row["sha256"], f"{path}.sha256"),
        item_count=_integer(row["item_count"], f"{path}.item_count"),
        complete=_boolean(row["complete"], f"{path}.complete"),
    )


def _topology_event(value: object, path: str) -> TopologyEvidenceEvent:
    row = _object(
        value,
        path,
        {"event_id", "channel", "frame", "phase", "kind_id", "subject_key", "state_sha256"},
    )
    return TopologyEvidenceEvent(
        event_id=_string(row["event_id"], f"{path}.event_id"),
        channel=_enum(TopologyChannel, row["channel"], f"{path}.channel"),
        frame=_integer(row["frame"], f"{path}.frame"),
        phase=_enum(CallbackPhase, row["phase"], f"{path}.phase"),
        kind_id=_string(row["kind_id"], f"{path}.kind_id"),
        subject_key=_string(row["subject_key"], f"{path}.subject_key"),
        state_sha256=_string(row["state_sha256"], f"{path}.state_sha256"),
    )


def _guard(value: object, path: str) -> GuardObservation:
    row = _object(
        value,
        path,
        {
            "guard_id",
            "guard_kind",
            "frame",
            "subject_key",
            "phase",
            "baseline_value",
            "predicate",
            "dependency_keys",
            "evidence_event_ids",
        },
    )
    return GuardObservation(
        guard_id=_string(row["guard_id"], f"{path}.guard_id"),
        guard_kind=_enum(GuardKind, row["guard_kind"], f"{path}.guard_kind"),
        frame=_integer(row["frame"], f"{path}.frame"),
        subject_key=_string(row["subject_key"], f"{path}.subject_key"),
        phase=_enum(CallbackPhase, row["phase"], f"{path}.phase"),
        baseline_value=_guard_scalar(row["baseline_value"], f"{path}.baseline_value"),
        predicate=_guard_predicate(row["predicate"], f"{path}.predicate"),
        dependency_keys=_string_tuple(
            row["dependency_keys"], f"{path}.dependency_keys"
        ),
        evidence_event_ids=_string_tuple(
            row["evidence_event_ids"], f"{path}.evidence_event_ids"
        ),
    )


def _guard_predicate(value: object, path: str) -> GuardPredicate:
    row = _object(
        value,
        path,
        {
            "operator",
            "expected_value",
            "lower_bound",
            "upper_bound",
            "lower_inclusive",
            "upper_inclusive",
        },
    )
    expected = row["expected_value"]
    lower = row["lower_bound"]
    upper = row["upper_bound"]
    return GuardPredicate(
        operator=_enum(GuardOperator, row["operator"], f"{path}.operator"),
        expected_value=None if expected is None else _guard_scalar(expected, f"{path}.expected_value"),
        lower_bound=None if lower is None else _number(lower, f"{path}.lower_bound"),
        upper_bound=None if upper is None else _number(upper, f"{path}.upper_bound"),
        lower_inclusive=_boolean(row["lower_inclusive"], f"{path}.lower_inclusive"),
        upper_inclusive=_boolean(row["upper_inclusive"], f"{path}.upper_inclusive"),
    )


def _decode_json(payload: str | bytes | bytearray) -> object:
    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TraceContractError("trace payload is not UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise TraceContractError("trace payload must be str or UTF-8 bytes")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise TraceContractError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise TraceContractError(f"non-finite JSON number {value!r} is forbidden")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except TraceContractError:
        raise
    except (TypeError, ValueError) as exc:
        raise TraceContractError(f"invalid trace JSON: {exc}") from exc


def _object(value: object, path: str, exact_keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TraceContractError(f"{path} must be an object")
    actual = set(value)
    if actual != exact_keys:
        missing = sorted(exact_keys - actual)
        unknown = sorted(actual - exact_keys)
        raise TraceContractError(
            f"{path} object keys mismatch; missing={missing!r}, unknown={unknown!r}"
        )
    return value


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise TraceContractError(f"{path} must be an array")
    return value


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise TraceContractError(f"{path} must be a string")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{path} must be an integer")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise TraceContractError(f"{path} must be finite")
    return result


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise TraceContractError(f"{path} must be a boolean")
    return value


def _guard_scalar(value: object, path: str) -> bool | int | float | str:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TraceContractError(f"{path} must be finite")
        return value
    if isinstance(value, str):
        return value
    raise TraceContractError(f"{path} must be a JSON scalar")


def _enum(enum_type: Callable[[str], _EnumT], value: object, path: str) -> _EnumT:
    raw = _string(value, path)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise TraceContractError(f"{path} has unsupported enum value {raw!r}") from exc


__all__ = [
    "decode_replay_assessment",
    "decode_trace_document",
    "encode_replay_assessment",
    "encode_trace_document",
]
