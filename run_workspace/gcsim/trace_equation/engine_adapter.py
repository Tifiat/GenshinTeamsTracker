"""Strict adapters for raw trace-equation engine envelopes.

The Go trace is a terminal numeric observation, not unrestricted symbolic Go.
V1 materializes the frozen terminal contract, v2 adds immutable attribution,
v3 adds reaction construction, v4 adds version-bound source-slice evidence,
v5 adds typed health-operation receipts, and v6 adds one ordered state ledger.
Every additive wrapper keeps pruning/publication authority disabled.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib

from .codec import (
    _array,
    _boolean,
    _decode_json,
    _integer,
    _number,
    _object,
    _optional_string,
    _string,
)
from .contracts import (
    CallbackPhase,
    DamageFormulaInputs,
    DamageFormulaKind,
    FormulaProvenance,
    FormulaValue,
    GuardTopologyReport,
    ProvenanceSourceKind,
    ReactionOperator,
    ReplayStatus,
    ScalingKind,
    SnapshotStat,
    TopologyChannel,
    TopologyChannelDigest,
    TopologyEvidenceEvent,
    TraceContractError,
    TraceDamageMode,
    TraceDocument,
    TraceExtractionRequest,
    TraceHitCompleteness,
    TraceHitEvent,
    TraceLineage,
    ValueReadMode,
    canonical_json,
    canonical_sha256,
)
from .provider_evidence import (
    HitProviderEvidence,
    ProviderAttackModEvidence,
    ProviderCallbackAttempt,
    ProviderEvidenceTrace,
    ProviderIdentity,
    ProviderReactionBonusContribution,
    ProviderStatContribution,
    ProviderStatDelta,
    ProviderTargetModContribution,
    ProviderTransition,
)
from .health_evidence import (
    HealthEvidenceTrace,
    decode_health_operations,
)
from .state_evidence import (
    StateEvidenceTrace,
    decode_state_events,
    decode_state_slots,
)
from .reaction_evidence import (
    ReactionEvidenceTrace,
    ReactionHitEvidence,
    TransformativeReactionFormula,
)
from .source_dependencies import (
    SourceDependencyEvidenceTrace,
    SourceManifestBinding,
    decode_source_occurrences,
    decode_source_value_bindings,
)


ENGINE_TRACE_SCHEMA_VERSION = 1
ENGINE_TRACE_CAPABILITY = "gtt_trace_equation_v1"
ENGINE_TRACE_V2_SCHEMA_VERSION = 2
ENGINE_TRACE_V2_CAPABILITY = "gtt_trace_equation_v2"
ENGINE_TRACE_V3_SCHEMA_VERSION = 3
ENGINE_TRACE_V3_CAPABILITY = "gtt_trace_equation_v3"
ENGINE_TRACE_V4_SCHEMA_VERSION = 4
ENGINE_TRACE_V4_CAPABILITY = "gtt_trace_equation_v4"
ENGINE_TRACE_V5_SCHEMA_VERSION = 5
ENGINE_TRACE_V5_CAPABILITY = "gtt_trace_equation_v5"
ENGINE_TRACE_V6_SCHEMA_VERSION = 6
ENGINE_TRACE_V6_CAPABILITY = "gtt_trace_equation_v6"
_UINT64_MAX = 2**64 - 1

_TOP_LEVEL_KEYS = {
    "schema_version",
    "capability",
    "engine_version",
    "patch_version",
    "formula_version",
    "formula_sha256",
    "context_sha256",
    "request_sha256",
    "source_config_sha256",
    "compiled_action_sha256",
    "target_sha256",
    "seed",
    "duration_frames",
    "character_keys",
    "hits",
    "topology_events",
    "unsupported",
    "guard_summary",
}

_HIT_KEYS = {
    "attack_id",
    "hit_id",
    "parent_attack_id",
    "parent_hit_id",
    "frame",
    "source_frame",
    "snapshot_frame",
    "actor_index",
    "damage_src",
    "ability",
    "attack_tag",
    "element",
    "target_key",
    "target_type",
    "formula_kind",
    "formula_sha256",
    "reaction_operator_id",
    "mult",
    "flat_dmg",
    "use_def",
    "use_hp",
    "use_em",
    "base_dmg_bonus",
    "elevation",
    "ignore_def_percent",
    "amped",
    "amp_mult",
    "amp_type",
    "catalyzed",
    "icd_tag",
    "icd_group",
    "durability_initial",
    "durability_post_icd",
    "damage_group_multiplier",
    "snapshot_stats",
    "char_level",
    "target_level",
    "scaling_stat_kind",
    "scaling_stat_value",
    "base_damage",
    "damage_bonus",
    "raw_crit_rate",
    "crit_rate_clamped",
    "crit_damage",
    "crit_roll",
    "hit_weak_point",
    "is_crit",
    "resistance",
    "res_mod",
    "def_adj",
    "def_mod",
    "em",
    "em_bonus",
    "reaction_bonus",
    "amp_total",
    "pre_amp_damage",
    "elevation_multiplier",
    "uncapped_damage",
    "hp_before",
    "actual_damage",
    "reported_damage",
    "hp_after",
    "killed",
    "damage_mode",
    "hp_cap_active",
    "attack_mods",
    "aura_before",
    "aura_after_reaction",
    "aura_after_attachment",
    "completeness",
    "unsupported",
}

_TOP_LEVEL_V2_KEYS = _TOP_LEVEL_KEYS | {"provider_transitions"}
_HIT_V2_KEYS = _HIT_KEYS | {
    "provider",
    "stat_contributions",
    "callback_attempts",
    "target_mod_contributions",
    "reaction_bonus_contributions",
}
_HIT_V3_KEYS = _HIT_V2_KEYS | {"reaction_formula", "parent_target_key"}
_TOP_LEVEL_V4_KEYS = _TOP_LEVEL_V2_KEYS | {
    "source_manifest_body_sha256",
    "source_occurrences",
    "source_value_bindings",
}
_TOP_LEVEL_V5_KEYS = _TOP_LEVEL_V4_KEYS | {"health_operations"}
_TOP_LEVEL_V6_KEYS = _TOP_LEVEL_V5_KEYS | {"state_slots", "state_events"}
_REACTION_FORMULA_V3_KEYS = {
    "formula_id",
    "formula_sha256",
    "reaction_type",
    "operator_id",
    "owner_index",
    "read_frame",
    "read_mode",
    "read_phase",
    "level",
    "level_base",
    "elemental_mastery",
    "em_curve_numerator",
    "em_curve_denominator_offset",
    "reaction_bonus",
    "reaction_bonus_contributions",
    "core_damage",
    "coefficient",
    "constructed_flat_damage",
    "parent_attack_id",
    "parent_target_key",
    "aura_source_indices",
    "child_role",
    "child_ordinal",
    "persistent_state_id",
    "persistent_revision",
    "gadget_id",
    "gadget_creator_index",
    "gadget_converter_index",
    "gadget_resolution_reason",
}
_ATTACK_MOD_V1_KEYS = {
    "modifier_key",
    "source_key",
    "owner_index",
    "accepted",
    "before_damage",
    "after_damage",
    "delta",
}
_ATTACK_MOD_V2_KEYS = _ATTACK_MOD_V1_KEYS | {"provider"}
_ATTACK_MOD_V2_BOUND_KEYS = _ATTACK_MOD_V2_KEYS | {"modifier_eval_event_id"}

_COMPLETENESS_KEYS = {
    "formula_complete",
    "flat_dmg_provenance_complete",
    "attack_mod_provenance_complete",
    "reaction_topology_complete",
    "provider_identity_complete",
}

_GUARD_SUMMARY_KEYS = {
    "hit_count",
    "topology_event_count",
    "unsupported_hit_count",
    "unsupported_count",
    "formula_kind_counts",
    "reaction_operator_counts",
    "formula_complete",
    "flat_dmg_provenance_complete",
    "attack_mod_provenance_complete",
    "reaction_topology_complete",
    "provider_identity_complete",
    "exact_replay_eligible",
}


@dataclass(frozen=True, slots=True)
class OpaqueEngineTraceEnvelope:
    """Identity-preserving exact-fallback result for a future raw schema."""

    schema_version: int
    capability: str | None
    canonical_payload_json: str
    payload_sha256: str
    reason_code: str = "unsupported_engine_trace_schema"

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise TraceContractError("opaque schema_version must be an integer")
        if self.capability is not None:
            _require_trimmed(self.capability, "opaque capability")
        if canonical_json(_decode_json(self.canonical_payload_json)) != self.canonical_payload_json:
            raise TraceContractError("opaque payload must be canonical JSON")
        expected = hashlib.sha256(self.canonical_payload_json.encode("utf-8")).hexdigest()
        if self.payload_sha256 != expected:
            raise TraceContractError("opaque payload SHA-256 mismatch")
        _require_trimmed(self.reason_code, "opaque reason_code")


def decode_engine_trace_v1(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
) -> TraceDocument | OpaqueEngineTraceEnvelope:
    """Decode one raw engine envelope without invoking a process or optimizer.

    Known schema v1 is strict: unknown or missing fields are rejected.  A
    future schema is retained as an opaque canonical envelope so the caller can
    route it to exact simulation without losing content identity.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    root = _decode_json(payload)
    if not isinstance(root, Mapping):
        raise TraceContractError("engine trace root must be an object")
    if "schema_version" not in root:
        raise TraceContractError("engine trace is missing schema_version")
    schema_version = _integer(root["schema_version"], "$.schema_version")
    if schema_version != ENGINE_TRACE_SCHEMA_VERSION:
        canonical_payload = canonical_json(root)
        raw_capability = root.get("capability")
        capability = raw_capability if isinstance(raw_capability, str) else None
        return OpaqueEngineTraceEnvelope(
            schema_version=schema_version,
            capability=capability,
            canonical_payload_json=canonical_payload,
            payload_sha256=hashlib.sha256(
                canonical_payload.encode("utf-8")
            ).hexdigest(),
        )

    row = _object(root, "$", _TOP_LEVEL_KEYS)
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_CAPABILITY:
        raise TraceContractError("unsupported engine trace capability")
    _require_trimmed(_string(row["engine_version"], "$.engine_version"), "engine_version")
    _require_trimmed(_string(row["patch_version"], "$.patch_version"), "patch_version")
    formula_version = _string(row["formula_version"], "$.formula_version")
    if formula_version != request.formula_version:
        raise TraceContractError("engine formula_version does not match extraction request")
    formula_sha256 = _sha256(row["formula_sha256"], "$.formula_sha256")
    if formula_sha256 != request.formula_sha256:
        raise TraceContractError("engine formula_sha256 does not match extraction request")
    for key, expected in (
        ("context_sha256", request.context_sha256),
        ("source_config_sha256", request.source_config_sha256),
        ("compiled_action_sha256", request.compiled_action_sha256),
        ("target_sha256", request.target_sha256),
    ):
        actual = _sha256(row[key], f"$.{key}")
        if actual != expected:
            raise TraceContractError(f"engine {key} does not match extraction request")
    _sha256(row["request_sha256"], "$.request_sha256")
    seed_text = _string(row["seed"], "$.seed")
    if not seed_text.isascii() or not seed_text.isdigit() or str(int(seed_text)) != seed_text:
        raise TraceContractError("$.seed must be a canonical positive int64 string")
    seed = int(seed_text)
    if seed != request.seed or seed <= 0 or seed > 2**63 - 1:
        raise TraceContractError("engine seed does not match extraction request")
    duration_frames = _integer(row["duration_frames"], "$.duration_frames")
    if duration_frames < 0:
        raise TraceContractError("duration_frames must be non-negative")
    character_keys = tuple(
        _string(item, f"$.character_keys[{index}]")
        for index, item in enumerate(_array(row["character_keys"], "$.character_keys"))
    )
    if character_keys != request.character_keys:
        raise TraceContractError("engine character_keys do not match extraction request")

    raw_hits = _array(row["hits"], "$.hits")
    top_unsupported = _string_list(row["unsupported"], "$.unsupported")
    topology_events = _parse_topology_events(row["topology_events"])
    _validate_guard_summary(
        row["guard_summary"],
        raw_hits=raw_hits,
        topology_event_count=len(topology_events),
        top_unsupported=top_unsupported,
    )

    engine_version = _string(row["engine_version"], "$.engine_version")
    patch_version = _string(row["patch_version"], "$.patch_version")
    engine_request_sha256 = _sha256(row["request_sha256"], "$.request_sha256")
    hits = tuple(
        _parse_hit(
            raw,
            path=f"$.hits[{index}]",
            request=request,
            engine_version=engine_version,
            patch_version=patch_version,
            engine_request_sha256=engine_request_sha256,
            top_unsupported=top_unsupported,
        )
        for index, raw in enumerate(raw_hits)
    )
    topology = _build_incomplete_topology(topology_events, top_unsupported)
    return TraceDocument.build(request=request, hits=hits, topology=topology)


def decode_engine_trace(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
    source_manifest_binding: SourceManifestBinding | None = None,
) -> (
    TraceDocument
    | ProviderEvidenceTrace
    | ReactionEvidenceTrace
    | SourceDependencyEvidenceTrace
    | HealthEvidenceTrace
    | StateEvidenceTrace
    | OpaqueEngineTraceEnvelope
):
    """Dispatch a raw engine envelope without weakening either known schema.

    V1 continues to materialize the frozen terminal ``TraceDocument``.  V2
    wraps that same terminal document with attribution evidence that is useful
    for diagnostics but cannot authorize exact replay or candidate removal.
    Unknown versions are identity-preserved for exact fallback.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    root = _decode_json(payload)
    if not isinstance(root, Mapping):
        raise TraceContractError("engine trace root must be an object")
    if "schema_version" not in root:
        raise TraceContractError("engine trace is missing schema_version")
    schema_version = _integer(root["schema_version"], "$.schema_version")
    canonical_payload = canonical_json(root)
    if schema_version == ENGINE_TRACE_SCHEMA_VERSION:
        return decode_engine_trace_v1(canonical_payload, request=request)
    if schema_version == ENGINE_TRACE_V2_SCHEMA_VERSION:
        return decode_engine_trace_v2(canonical_payload, request=request)
    if schema_version == ENGINE_TRACE_V3_SCHEMA_VERSION:
        return decode_engine_trace_v3(canonical_payload, request=request)
    if schema_version == ENGINE_TRACE_V4_SCHEMA_VERSION:
        if source_manifest_binding is None:
            raise TraceContractError(
                "engine trace v4 requires an external source manifest binding"
            )
        return decode_engine_trace_v4(
            canonical_payload,
            request=request,
            source_manifest_binding=source_manifest_binding,
        )
    if schema_version == ENGINE_TRACE_V5_SCHEMA_VERSION:
        if source_manifest_binding is None:
            raise TraceContractError(
                "engine trace v5 requires an external source manifest binding"
            )
        return decode_engine_trace_v5(
            canonical_payload,
            request=request,
            source_manifest_binding=source_manifest_binding,
        )
    if schema_version == ENGINE_TRACE_V6_SCHEMA_VERSION:
        if source_manifest_binding is None:
            raise TraceContractError(
                "engine trace v6 requires an external source manifest binding"
            )
        return decode_engine_trace_v6(
            canonical_payload,
            request=request,
            source_manifest_binding=source_manifest_binding,
        )
    raw_capability = root.get("capability")
    capability = raw_capability if isinstance(raw_capability, str) else None
    return OpaqueEngineTraceEnvelope(
        schema_version=schema_version,
        capability=capability,
        canonical_payload_json=canonical_payload,
        payload_sha256=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
    )


def decode_engine_trace_v2(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
) -> ProviderEvidenceTrace:
    """Strictly decode raw provider trace schema v2.

    Provider presence is attribution evidence only.  The returned wrapper is
    deliberately fail-open for search decisions: its terminal trace keeps the
    v1 incomplete topology and every candidate still requires exact execution.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    root = _decode_json(payload)
    row = _object(root, "$", _TOP_LEVEL_V2_KEYS)
    if _integer(row["schema_version"], "$.schema_version") != ENGINE_TRACE_V2_SCHEMA_VERSION:
        raise TraceContractError("unsupported engine trace v2 schema_version")
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_V2_CAPABILITY:
        raise TraceContractError("unsupported engine trace v2 capability")

    raw_hits = _array(row["hits"], "$.hits")
    hit_rows = tuple(
        _object(item, f"$.hits[{index}]", _HIT_V2_KEYS)
        for index, item in enumerate(raw_hits)
    )
    hit_evidence = tuple(
        _parse_hit_provider_evidence_v2(hit, path=f"$.hits[{index}]")
        for index, hit in enumerate(hit_rows)
    )
    provider_transitions = tuple(
        _parse_provider_transition_v2(
            item,
            path=f"$.provider_transitions[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(row["provider_transitions"], "$.provider_transitions")
        )
    )

    # Reuse the already-audited terminal v1 arithmetic by removing only the
    # additive provider evidence.  This is intentionally not a conversion of
    # provider rows into FormulaValue provenance or a symbolic expression.
    legacy_root = {key: row[key] for key in _TOP_LEVEL_KEYS}
    legacy_root["schema_version"] = ENGINE_TRACE_SCHEMA_VERSION
    legacy_root["capability"] = ENGINE_TRACE_CAPABILITY
    legacy_hits: list[dict[str, object]] = []
    for index, hit in enumerate(hit_rows):
        legacy_hit = {key: hit[key] for key in _HIT_KEYS}
        legacy_attack_mods: list[dict[str, object]] = []
        for mod_index, item in enumerate(
            _array(hit["attack_mods"], f"$.hits[{index}].attack_mods")
        ):
            mod_path = f"$.hits[{index}].attack_mods[{mod_index}]"
            mod = _object(
                item,
                mod_path,
                (
                    _ATTACK_MOD_V2_BOUND_KEYS
                    if isinstance(item, Mapping)
                    and "modifier_eval_event_id" in item
                    else _ATTACK_MOD_V2_KEYS
                ),
            )
            legacy_attack_mods.append(
                {key: mod[key] for key in _ATTACK_MOD_V1_KEYS}
            )
        legacy_hit["attack_mods"] = legacy_attack_mods
        legacy_hits.append(legacy_hit)
    legacy_root["hits"] = legacy_hits
    terminal = decode_engine_trace_v1(canonical_json(legacy_root), request=request)
    if not isinstance(terminal, TraceDocument):
        raise TraceContractError("internal v2 terminal materialization failed")

    return ProviderEvidenceTrace.build(
        terminal_trace=terminal,
        engine_request_sha256=_sha256(row["request_sha256"], "$.request_sha256"),
        raw_payload_sha256=canonical_sha256(root),
        hit_evidence=hit_evidence,
        provider_transitions=provider_transitions,
    )


def decode_engine_trace_v3(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
) -> ReactionEvidenceTrace:
    """Strictly decode additive reaction-construction trace schema v3.

    The v2 provider wrapper and frozen v1 terminal trace are reconstructed
    byte-for-byte in meaning.  Reaction rows are an outer expected-value layer;
    they do not grant exact replay or hard-prune authority.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    root = _decode_json(payload)
    row = _object(root, "$", _TOP_LEVEL_V2_KEYS)
    if _integer(row["schema_version"], "$.schema_version") != ENGINE_TRACE_V3_SCHEMA_VERSION:
        raise TraceContractError("unsupported engine trace v3 schema_version")
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_V3_CAPABILITY:
        raise TraceContractError("unsupported engine trace v3 capability")

    raw_hits = _array(row["hits"], "$.hits")
    hit_rows = tuple(
        _object(item, f"$.hits[{index}]", _HIT_V3_KEYS)
        for index, item in enumerate(raw_hits)
    )
    preceding_refs: set[tuple[int, int]] = set()
    reaction_hits: list[ReactionHitEvidence] = []
    for index, hit in enumerate(hit_rows):
        current_attack_id = _uint64(
            hit["attack_id"], f"$.hits[{index}].attack_id"
        )
        raw_formula = hit["reaction_formula"]
        current_ref = (
            current_attack_id,
            _nonnegative_int(hit["target_key"], f"$.hits[{index}].target_key"),
        )
        if raw_formula is None:
            preceding_refs.add(current_ref)
            continue
        formula = _parse_reaction_formula_v3(
            raw_formula,
            path=f"$.hits[{index}].reaction_formula",
            character_keys=request.character_keys,
            known_parent_refs={
                ref for ref in preceding_refs if ref[0] < current_attack_id
            },
        )
        terminal_parent = _optional_uint64(
            hit["parent_attack_id"], f"$.hits[{index}].parent_attack_id"
        )
        if terminal_parent != formula.parent_attack_id:
            raise TraceContractError(
                f"$.hits[{index}] reaction parent attack binding mismatch"
            )
        terminal_parent_target = _optional_nonnegative_int(
            hit["parent_target_key"], f"$.hits[{index}].parent_target_key"
        )
        if terminal_parent_target != formula.parent_target_key:
            raise TraceContractError(
                f"$.hits[{index}] reaction parent target binding mismatch"
            )
        terminal_actor = _character_index(
            hit["actor_index"], f"$.hits[{index}].actor_index", request.character_keys
        )
        if terminal_actor != formula.owner_index:
            raise TraceContractError(
                f"$.hits[{index}] reaction owner binding mismatch"
            )
        if _positive_int(hit["char_level"], f"$.hits[{index}].char_level") != formula.level:
            raise TraceContractError(
                f"$.hits[{index}] reaction level binding mismatch"
            )
        if _nonnegative_int(
            hit["snapshot_frame"], f"$.hits[{index}].snapshot_frame"
        ) != formula.read_frame:
            raise TraceContractError(
                f"$.hits[{index}] reaction read-frame binding mismatch"
            )
        snapshot_stats = _number_map(
            hit["snapshot_stats"], f"$.hits[{index}].snapshot_stats"
        )
        if "em" not in snapshot_stats or not _close(
            snapshot_stats["em"], formula.elemental_mastery
        ):
            raise TraceContractError(
                f"$.hits[{index}] reaction EM binding mismatch"
            )
        reaction_hits.append(
            ReactionHitEvidence(
                event_id=f"hit:{_uint64(hit['hit_id'], f'$.hits[{index}].hit_id')}",
                formula=formula,
            )
        )
        preceding_refs.add(current_ref)

    legacy_root = {key: row[key] for key in _TOP_LEVEL_V2_KEYS}
    legacy_root["schema_version"] = ENGINE_TRACE_V2_SCHEMA_VERSION
    legacy_root["capability"] = ENGINE_TRACE_V2_CAPABILITY
    legacy_root["hits"] = [
        {key: hit[key] for key in _HIT_V2_KEYS} for hit in hit_rows
    ]
    provider = decode_engine_trace_v2(canonical_json(legacy_root), request=request)
    return ReactionEvidenceTrace(
        provider_evidence=provider,
        raw_payload_sha256=canonical_sha256(root),
        reaction_hits=tuple(reaction_hits),
    )


def decode_engine_trace_v4(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
    source_manifest_binding: SourceManifestBinding,
) -> SourceDependencyEvidenceTrace:
    """Strictly decode source/dependency trace schema v4.

    The external semantic manifest is mandatory.  A missing or mismatched
    manifest is a controlled contract failure; v4 must never silently discard
    its source evidence and downgrade to v3.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    if not isinstance(source_manifest_binding, SourceManifestBinding):
        raise TraceContractError(
            "source_manifest_binding must be SourceManifestBinding"
        )
    manifest_body = source_manifest_binding.manifest_body
    if (
        manifest_body.trace_schema_version,
        manifest_body.trace_capability,
    ) != (ENGINE_TRACE_V4_SCHEMA_VERSION, ENGINE_TRACE_V4_CAPABILITY):
        raise TraceContractError(
            "engine trace v4 requires a 4/v4 source manifest binding"
        )
    root = _decode_json(payload)
    row = _object(root, "$", _TOP_LEVEL_V4_KEYS)
    if _integer(row["schema_version"], "$.schema_version") != ENGINE_TRACE_V4_SCHEMA_VERSION:
        raise TraceContractError("unsupported engine trace v4 schema_version")
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_V4_CAPABILITY:
        raise TraceContractError("unsupported engine trace v4 capability")
    manifest_sha256 = _sha256(
        row["source_manifest_body_sha256"],
        "$.source_manifest_body_sha256",
    )
    if manifest_sha256 != source_manifest_binding.manifest_body.body_sha256:
        raise TraceContractError(
            "engine trace source manifest does not match external binding"
        )
    if source_manifest_binding.engine_artifact_sha256 != request.engine_artifact_sha256:
        raise TraceContractError(
            "external source manifest executable does not match request"
        )
    if source_manifest_binding.engine_binding_sha256 != request.engine_binding_sha256:
        raise TraceContractError(
            "external source manifest engine binding does not match request"
        )

    occurrences = decode_source_occurrences(
        row["source_occurrences"],
        "$.source_occurrences",
    )
    value_bindings = decode_source_value_bindings(
        row["source_value_bindings"],
        "$.source_value_bindings",
    )

    # Strip only additive v4 fields and reuse the already-audited v3 decoder.
    # This preserves every nested v1-v3 field and interpretation unchanged.
    legacy_root = {key: row[key] for key in _TOP_LEVEL_V2_KEYS}
    legacy_root["schema_version"] = ENGINE_TRACE_V3_SCHEMA_VERSION
    legacy_root["capability"] = ENGINE_TRACE_V3_CAPABILITY
    reaction = decode_engine_trace_v3(canonical_json(legacy_root), request=request)
    return SourceDependencyEvidenceTrace(
        reaction_evidence=reaction,
        source_manifest_binding=source_manifest_binding,
        raw_payload_sha256=canonical_sha256(root),
        occurrences=occurrences,
        value_bindings=value_bindings,
    )


def decode_engine_trace_v5(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
    source_manifest_binding: SourceManifestBinding,
) -> HealthEvidenceTrace:
    """Strictly decode additive typed health-operation trace schema V5.

    V5 retains reaction evidence, source occurrences, and source value bindings
    unchanged, then adds ``health_operations``.  Its source manifest remains a
    distinct 5/v5 engine identity; it is never normalized into an accepted V4
    manifest or used to weaken the public V4 decoder.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    if not isinstance(source_manifest_binding, SourceManifestBinding):
        raise TraceContractError(
            "source_manifest_binding must be SourceManifestBinding"
        )
    manifest_body = source_manifest_binding.manifest_body
    if (
        manifest_body.trace_schema_version,
        manifest_body.trace_capability,
    ) != (ENGINE_TRACE_V5_SCHEMA_VERSION, ENGINE_TRACE_V5_CAPABILITY):
        raise TraceContractError(
            "engine trace v5 requires a 5/v5 source manifest binding"
        )

    root = _decode_json(payload)
    row = _object(root, "$", _TOP_LEVEL_V5_KEYS)
    if _integer(row["schema_version"], "$.schema_version") != ENGINE_TRACE_V5_SCHEMA_VERSION:
        raise TraceContractError("unsupported engine trace v5 schema_version")
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_V5_CAPABILITY:
        raise TraceContractError("unsupported engine trace v5 capability")
    manifest_sha256 = _sha256(
        row["source_manifest_body_sha256"],
        "$.source_manifest_body_sha256",
    )
    if manifest_sha256 != source_manifest_binding.manifest_body.body_sha256:
        raise TraceContractError(
            "engine trace source manifest does not match external binding"
        )
    if source_manifest_binding.engine_artifact_sha256 != request.engine_artifact_sha256:
        raise TraceContractError(
            "external source manifest executable does not match request"
        )
    if source_manifest_binding.engine_binding_sha256 != request.engine_binding_sha256:
        raise TraceContractError(
            "external source manifest engine binding does not match request"
        )

    occurrences = decode_source_occurrences(
        row["source_occurrences"],
        "$.source_occurrences",
    )
    value_bindings = decode_source_value_bindings(
        row["source_value_bindings"],
        "$.source_value_bindings",
    )
    health_operations = decode_health_operations(
        row["health_operations"],
        "$.health_operations",
    )

    # Remove only additive V4/V5 collections before reusing the unchanged V3
    # materializer.  No nested V1-V3 field is rewritten or reinterpreted.
    legacy_root = {key: row[key] for key in _TOP_LEVEL_V2_KEYS}
    legacy_root["schema_version"] = ENGINE_TRACE_V3_SCHEMA_VERSION
    legacy_root["capability"] = ENGINE_TRACE_V3_CAPABILITY
    reaction = decode_engine_trace_v3(canonical_json(legacy_root), request=request)
    return HealthEvidenceTrace(
        reaction_evidence=reaction,
        source_manifest_binding=source_manifest_binding,
        raw_payload_sha256=canonical_sha256(root),
        occurrences=occurrences,
        value_bindings=value_bindings,
        health_operations=health_operations,
    )


def decode_engine_trace_v6(
    payload: str | bytes | bytearray,
    *,
    request: TraceExtractionRequest,
    source_manifest_binding: SourceManifestBinding,
) -> StateEvidenceTrace:
    """Strictly decode additive ordered-state trace schema V6.

    Only the two V6 collections are new.  Every inherited V1--V5 collection is
    parsed by the same audited decoders and validated by the same component
    contracts; the 6/v6 source manifest identity remains distinct.
    """

    if not isinstance(request, TraceExtractionRequest):
        raise TraceContractError("request must be TraceExtractionRequest")
    if not isinstance(source_manifest_binding, SourceManifestBinding):
        raise TraceContractError(
            "source_manifest_binding must be SourceManifestBinding"
        )
    manifest_body = source_manifest_binding.manifest_body
    if (
        manifest_body.trace_schema_version,
        manifest_body.trace_capability,
    ) != (ENGINE_TRACE_V6_SCHEMA_VERSION, ENGINE_TRACE_V6_CAPABILITY):
        raise TraceContractError(
            "engine trace v6 requires a strict 6/v6 source manifest binding"
        )

    root = _decode_json(payload)
    row = _object(root, "$", _TOP_LEVEL_V6_KEYS)
    if _integer(row["schema_version"], "$.schema_version") != ENGINE_TRACE_V6_SCHEMA_VERSION:
        raise TraceContractError("unsupported engine trace v6 schema_version")
    if _string(row["capability"], "$.capability") != ENGINE_TRACE_V6_CAPABILITY:
        raise TraceContractError("unsupported engine trace v6 capability")
    manifest_sha256 = _sha256(
        row["source_manifest_body_sha256"],
        "$.source_manifest_body_sha256",
    )
    if manifest_sha256 != source_manifest_binding.manifest_body.body_sha256:
        raise TraceContractError(
            "engine trace source manifest does not match external binding"
        )
    if source_manifest_binding.engine_artifact_sha256 != request.engine_artifact_sha256:
        raise TraceContractError(
            "external source manifest executable does not match request"
        )
    if source_manifest_binding.engine_binding_sha256 != request.engine_binding_sha256:
        raise TraceContractError(
            "external source manifest engine binding does not match request"
        )

    occurrences = decode_source_occurrences(
        row["source_occurrences"],
        "$.source_occurrences",
    )
    value_bindings = decode_source_value_bindings(
        row["source_value_bindings"],
        "$.source_value_bindings",
    )
    health_operations = decode_health_operations(
        row["health_operations"],
        "$.health_operations",
    )
    state_slots = decode_state_slots(row["state_slots"], "$.state_slots")
    state_events = decode_state_events(row["state_events"], "$.state_events")

    legacy_root = {key: row[key] for key in _TOP_LEVEL_V2_KEYS}
    legacy_root["schema_version"] = ENGINE_TRACE_V3_SCHEMA_VERSION
    legacy_root["capability"] = ENGINE_TRACE_V3_CAPABILITY
    reaction = decode_engine_trace_v3(canonical_json(legacy_root), request=request)
    return StateEvidenceTrace(
        reaction_evidence=reaction,
        source_manifest_binding=source_manifest_binding,
        raw_payload_sha256=canonical_sha256(root),
        occurrences=occurrences,
        value_bindings=value_bindings,
        health_operations=health_operations,
        state_slots=state_slots,
        state_events=state_events,
        duration_frames=_nonnegative_int(
            row["duration_frames"], "$.duration_frames"
        ),
    )


def _parse_reaction_formula_v3(
    value: object,
    *,
    path: str,
    character_keys: tuple[str, ...],
    known_parent_refs: set[tuple[int, int]],
) -> TransformativeReactionFormula:
    row = _object(value, path, _REACTION_FORMULA_V3_KEYS)
    raw_operator = _string(row["operator_id"], f"{path}.operator_id")
    known_operator = _known_reaction_operator(raw_operator)
    operator = (
        known_operator
        if known_operator is not None
        else ReactionOperator.OPAQUE_CUSTOM
    )
    owner_index = _character_index(
        row["owner_index"], f"{path}.owner_index", character_keys
    )
    aura_source_indices = tuple(
        _character_index(item, f"{path}.aura_source_indices[{index}]", character_keys)
        for index, item in enumerate(
            _array(row["aura_source_indices"], f"{path}.aura_source_indices")
        )
    )
    if aura_source_indices != tuple(sorted(set(aura_source_indices))):
        raise TraceContractError(
            f"{path}.aura_source_indices must be sorted and unique"
        )
    read_mode_raw = _string(row["read_mode"], f"{path}.read_mode")
    try:
        read_mode = ValueReadMode(read_mode_raw)
    except ValueError as exc:
        raise TraceContractError(f"{path}.read_mode is unsupported") from exc

    gadget_creator_index = _optional_character_index(
        row["gadget_creator_index"],
        f"{path}.gadget_creator_index",
        character_keys,
    )
    gadget_converter_index = _optional_character_index(
        row["gadget_converter_index"],
        f"{path}.gadget_converter_index",
        character_keys,
    )
    contributions = tuple(
        _parse_reaction_bonus_v2(
            item,
            path=f"{path}.reaction_bonus_contributions[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(
                row["reaction_bonus_contributions"],
                f"{path}.reaction_bonus_contributions",
            )
        )
    )
    return TransformativeReactionFormula(
        formula_id=_string(row["formula_id"], f"{path}.formula_id"),
        formula_sha256=_sha256(
            row["formula_sha256"], f"{path}.formula_sha256"
        ),
        reaction_type=_string(row["reaction_type"], f"{path}.reaction_type"),
        operator=operator,
        owner_index=owner_index,
        owner_key=character_keys[owner_index],
        read_frame=_nonnegative_int(row["read_frame"], f"{path}.read_frame"),
        read_mode=read_mode,
        read_phase=_string(row["read_phase"], f"{path}.read_phase"),
        level=_positive_int(row["level"], f"{path}.level"),
        level_base=_number(row["level_base"], f"{path}.level_base"),
        elemental_mastery=_number(
            row["elemental_mastery"], f"{path}.elemental_mastery"
        ),
        em_curve_numerator=_number(
            row["em_curve_numerator"], f"{path}.em_curve_numerator"
        ),
        em_curve_denominator_offset=_number(
            row["em_curve_denominator_offset"],
            f"{path}.em_curve_denominator_offset",
        ),
        reaction_bonus=_number(
            row["reaction_bonus"], f"{path}.reaction_bonus"
        ),
        reaction_bonus_contributions=contributions,
        core_damage=_number(row["core_damage"], f"{path}.core_damage"),
        coefficient=_number(row["coefficient"], f"{path}.coefficient"),
        constructed_flat_damage=_number(
            row["constructed_flat_damage"],
            f"{path}.constructed_flat_damage",
        ),
        parent_attack_id=_uint64(
            row["parent_attack_id"], f"{path}.parent_attack_id"
        ),
        parent_target_key=_nonnegative_int(
            row["parent_target_key"], f"{path}.parent_target_key"
        ),
        parent_occurrence_resolved=(
            (
                _uint64(row["parent_attack_id"], f"{path}.parent_attack_id"),
                _nonnegative_int(
                    row["parent_target_key"], f"{path}.parent_target_key"
                ),
            )
            in known_parent_refs
        ),
        aura_source_indices=aura_source_indices,
        aura_source_keys=tuple(
            character_keys[index] for index in aura_source_indices
        ),
        child_role=_string(row["child_role"], f"{path}.child_role"),
        child_ordinal=_nonnegative_int(
            row["child_ordinal"], f"{path}.child_ordinal"
        ),
        persistent_state_id=_optional_string(
            row["persistent_state_id"], f"{path}.persistent_state_id"
        ),
        persistent_revision=_optional_nonnegative_int(
            row["persistent_revision"], f"{path}.persistent_revision"
        ),
        gadget_id=_optional_string(row["gadget_id"], f"{path}.gadget_id"),
        gadget_creator_index=gadget_creator_index,
        gadget_creator_key=(
            None
            if gadget_creator_index is None
            else character_keys[gadget_creator_index]
        ),
        gadget_converter_index=gadget_converter_index,
        gadget_converter_key=(
            None
            if gadget_converter_index is None
            else character_keys[gadget_converter_index]
        ),
        gadget_resolution_reason=_optional_string(
            row["gadget_resolution_reason"],
            f"{path}.gadget_resolution_reason",
        ),
    )


def _parse_hit_provider_evidence_v2(
    row: Mapping[str, object],
    *,
    path: str,
) -> HitProviderEvidence:
    stat_contributions = tuple(
        _parse_stat_contribution_v2(
            item,
            path=f"{path}.stat_contributions[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(row["stat_contributions"], f"{path}.stat_contributions")
        )
    )
    callback_attempts = tuple(
        _parse_callback_attempt_v2(
            item,
            path=f"{path}.callback_attempts[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(row["callback_attempts"], f"{path}.callback_attempts")
        )
    )
    attack_mods = tuple(
        _parse_attack_mod_evidence_v2(
            item,
            path=f"{path}.attack_mods[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(row["attack_mods"], f"{path}.attack_mods")
        )
    )
    target_mods = tuple(
        _parse_target_mod_v2(
            item,
            path=f"{path}.target_mod_contributions[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(
                row["target_mod_contributions"],
                f"{path}.target_mod_contributions",
            )
        )
    )
    reaction_bonuses = tuple(
        _parse_reaction_bonus_v2(
            item,
            path=f"{path}.reaction_bonus_contributions[{index}]",
            sequence_index=index,
        )
        for index, item in enumerate(
            _array(
                row["reaction_bonus_contributions"],
                f"{path}.reaction_bonus_contributions",
            )
        )
    )
    return HitProviderEvidence(
        event_id=f"hit:{_uint64(row['hit_id'], f'{path}.hit_id')}",
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
        stat_contributions=stat_contributions,
        callback_attempts=callback_attempts,
        attack_mods=attack_mods,
        target_mod_contributions=target_mods,
        reaction_bonus_contributions=reaction_bonuses,
    )


def _parse_provider_v2(value: object, path: str) -> ProviderIdentity:
    row = _object(
        value,
        path,
        {"known", "kind", "key", "owner_index", "piece_count"},
    )
    return ProviderIdentity.from_raw(
        known=_boolean(row["known"], f"{path}.known"),
        kind=_string(row["kind"], f"{path}.kind"),
        key=_string(row["key"], f"{path}.key"),
        owner_index=_integer(row["owner_index"], f"{path}.owner_index"),
        piece_count=_integer(row["piece_count"], f"{path}.piece_count"),
    )


def _provider_stat_deltas(value: object, path: str) -> tuple[ProviderStatDelta, ...]:
    values = _number_map(value, path)
    return tuple(
        ProviderStatDelta(stat_key=key, value=number)
        for key, number in sorted(values.items())
    )


def _parse_stat_contribution_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderStatContribution:
    has_binding = (
        isinstance(value, Mapping) and "modifier_eval_event_id" in value
    )
    row = _object(
        value,
        path,
        {
            "modifier_key",
            "recipient_index",
            "accepted",
            "values",
            "provider",
            *({"modifier_eval_event_id"} if has_binding else set()),
        },
    )
    return ProviderStatContribution(
        sequence_index=sequence_index,
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        recipient_index=_integer(
            row["recipient_index"], f"{path}.recipient_index"
        ),
        accepted=_boolean(row["accepted"], f"{path}.accepted"),
        values=_provider_stat_deltas(row["values"], f"{path}.values"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
        modifier_eval_event_id=(
            _string(
                row["modifier_eval_event_id"],
                f"{path}.modifier_eval_event_id",
            )
            if has_binding
            else None
        ),
    )


def _parse_callback_attempt_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderCallbackAttempt:
    row = _object(
        value,
        path,
        {
            "event",
            "hook_key",
            "provider",
            "changed",
            "topology_changed",
            "state_effects_unobserved",
            "snapshot_delta",
            "mult_delta",
            "flat_dmg_delta",
            "base_dmg_bonus_delta",
            "elevation_delta",
            "ignore_def_delta",
            "amp_multiplier_delta",
        },
    )
    return ProviderCallbackAttempt(
        sequence_index=sequence_index,
        event=_integer(row["event"], f"{path}.event"),
        hook_key=_string(row["hook_key"], f"{path}.hook_key"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
        changed=_boolean(row["changed"], f"{path}.changed"),
        topology_changed=_boolean(
            row["topology_changed"], f"{path}.topology_changed"
        ),
        state_effects_unobserved=_boolean(
            row["state_effects_unobserved"],
            f"{path}.state_effects_unobserved",
        ),
        snapshot_delta=_provider_stat_deltas(
            row["snapshot_delta"], f"{path}.snapshot_delta"
        ),
        mult_delta=_number(row["mult_delta"], f"{path}.mult_delta"),
        flat_dmg_delta=_number(
            row["flat_dmg_delta"], f"{path}.flat_dmg_delta"
        ),
        base_dmg_bonus_delta=_number(
            row["base_dmg_bonus_delta"], f"{path}.base_dmg_bonus_delta"
        ),
        elevation_delta=_number(
            row["elevation_delta"], f"{path}.elevation_delta"
        ),
        ignore_def_delta=_number(
            row["ignore_def_delta"], f"{path}.ignore_def_delta"
        ),
        amp_multiplier_delta=_number(
            row["amp_multiplier_delta"], f"{path}.amp_multiplier_delta"
        ),
    )


def _parse_attack_mod_evidence_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderAttackModEvidence:
    has_binding = (
        isinstance(value, Mapping) and "modifier_eval_event_id" in value
    )
    row = _object(
        value,
        path,
        _ATTACK_MOD_V2_BOUND_KEYS if has_binding else _ATTACK_MOD_V2_KEYS,
    )
    return ProviderAttackModEvidence(
        sequence_index=sequence_index,
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        legacy_source_key=_string(row["source_key"], f"{path}.source_key"),
        legacy_owner_index=_integer(row["owner_index"], f"{path}.owner_index"),
        accepted=_boolean(row["accepted"], f"{path}.accepted"),
        before_damage=_optional_number(
            row["before_damage"], f"{path}.before_damage"
        ),
        after_damage=_optional_number(
            row["after_damage"], f"{path}.after_damage"
        ),
        delta=_provider_stat_deltas(row["delta"], f"{path}.delta"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
        modifier_eval_event_id=(
            _string(
                row["modifier_eval_event_id"],
                f"{path}.modifier_eval_event_id",
            )
            if has_binding
            else None
        ),
    )


def _parse_target_mod_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderTargetModContribution:
    row = _object(
        value,
        path,
        {"channel", "modifier_key", "value", "provider"},
    )
    return ProviderTargetModContribution(
        sequence_index=sequence_index,
        channel=_string(row["channel"], f"{path}.channel"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        value=_number(row["value"], f"{path}.value"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
    )


def _parse_reaction_bonus_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderReactionBonusContribution:
    row = _object(value, path, {"modifier_key", "value", "provider"})
    return ProviderReactionBonusContribution(
        sequence_index=sequence_index,
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        value=_number(row["value"], f"{path}.value"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
    )


def _parse_provider_transition_v2(
    value: object,
    *,
    path: str,
    sequence_index: int,
) -> ProviderTransition:
    row = _object(
        value,
        path,
        {
            "frame",
            "channel",
            "recipient_index",
            "modifier_key",
            "transition",
            "provider",
            "displaced_provider",
        },
    )
    displaced = row["displaced_provider"]
    return ProviderTransition(
        catalog_index=sequence_index,
        frame=_integer(row["frame"], f"{path}.frame"),
        channel=_string(row["channel"], f"{path}.channel"),
        recipient_index=_integer(
            row["recipient_index"], f"{path}.recipient_index"
        ),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        transition=_string(row["transition"], f"{path}.transition"),
        provider=_parse_provider_v2(row["provider"], f"{path}.provider"),
        displaced_provider=(
            None
            if displaced is None
            else _parse_provider_v2(displaced, f"{path}.displaced_provider")
        ),
    )


def _parse_hit(
    value: object,
    *,
    path: str,
    request: TraceExtractionRequest,
    engine_version: str,
    patch_version: str,
    engine_request_sha256: str,
    top_unsupported: tuple[str, ...],
) -> TraceHitEvent:
    row = _object(value, path, _HIT_KEYS)
    hit_id = _uint64(row["hit_id"], f"{path}.hit_id")
    attack_id = _uint64(row["attack_id"], f"{path}.attack_id")
    parent_hit_id = _optional_uint64(row["parent_hit_id"], f"{path}.parent_hit_id")
    _optional_uint64(row["parent_attack_id"], f"{path}.parent_attack_id")
    actor_index = _integer(row["actor_index"], f"{path}.actor_index")
    if actor_index < 0 or actor_index >= len(request.character_keys):
        raise TraceContractError(f"{path}.actor_index is outside character_keys")
    actor_key = request.character_keys[actor_index]
    formula_kind = _string(row["formula_kind"], f"{path}.formula_kind")
    formula_sha256 = _sha256(row["formula_sha256"], f"{path}.formula_sha256")
    reaction_operator_id = _string(
        row["reaction_operator_id"], f"{path}.reaction_operator_id"
    )
    raw_unsupported = _string_list(row["unsupported"], f"{path}.unsupported")
    completeness = _parse_completeness(row["completeness"], f"{path}.completeness")

    snapshot = _number_map(row["snapshot_stats"], f"{path}.snapshot_stats")
    snapshot_provenance_id = "snapshot"
    engine_provenance_id = "engine-formula"
    provenance: list[FormulaProvenance] = [
        FormulaProvenance(
            provenance_id=engine_provenance_id,
            source_kind=ProvenanceSourceKind.ENGINE_FORMULA,
            source_key=(
                f"{engine_version}/{patch_version}/{engine_request_sha256}"
            ),
            owner_key=None,
            provider_event_id=None,
            modifier_key=None,
            modifier_channel=None,
            read_phase=CallbackPhase.DAMAGE_RESOLUTION,
            read_mode=ValueReadMode.CONSTANT,
        ),
        FormulaProvenance(
            provenance_id=snapshot_provenance_id,
            source_kind=ProvenanceSourceKind.CHARACTER,
            source_key=actor_key,
            owner_key=actor_key,
            provider_event_id=None,
            modifier_key=None,
            modifier_channel=None,
            read_phase=CallbackPhase.SNAPSHOT,
            read_mode=ValueReadMode.SNAPSHOT,
        ),
    ]
    attack_mod_rows = _array(row["attack_mods"], f"{path}.attack_mods")
    for index, item in enumerate(attack_mod_rows):
        mod_path = f"{path}.attack_mods[{index}]"
        mod = _object(
            item,
            mod_path,
            _ATTACK_MOD_V1_KEYS,
        )
        modifier_key = _string(mod["modifier_key"], f"{mod_path}.modifier_key")
        _require_trimmed(modifier_key, f"{mod_path}.modifier_key")
        source_key = _string(mod["source_key"], f"{mod_path}.source_key")
        owner_index = _integer(mod["owner_index"], f"{mod_path}.owner_index")
        _boolean(mod["accepted"], f"{mod_path}.accepted")
        _optional_number(mod["before_damage"], f"{mod_path}.before_damage")
        _optional_number(mod["after_damage"], f"{mod_path}.after_damage")
        _number_map(mod["delta"], f"{mod_path}.delta")
        provenance.append(
            FormulaProvenance(
                provenance_id=f"attack-mod:{index:04d}",
                source_kind=ProvenanceSourceKind.OPAQUE_CUSTOM,
                source_key=source_key or f"unresolved:{modifier_key}",
                owner_key=(
                    request.character_keys[owner_index]
                    if 0 <= owner_index < len(request.character_keys)
                    else None
                ),
                provider_event_id=None,
                modifier_key=modifier_key,
                modifier_channel="attack_mod",
                read_phase=CallbackPhase.DAMAGE_RESOLUTION,
                read_mode=ValueReadMode.SNAPSHOT,
            )
        )

    engine_ids = tuple(sorted(item.provenance_id for item in provenance))
    snapshot_ids = (snapshot_provenance_id,)

    def engine_value(key: str) -> FormulaValue:
        return FormulaValue(_number(row[key], f"{path}.{key}"), engine_ids)

    def snapshot_value(key: str) -> FormulaValue:
        return FormulaValue(_number(row[key], f"{path}.{key}"), snapshot_ids)

    scaling_kind = _scaling_kind(row, path)
    formula_inputs = DamageFormulaInputs(
        formula_kind=formula_kind,
        formula_sha256=formula_sha256,
        character_level=_nonnegative_int(row["char_level"], f"{path}.char_level"),
        target_level=_nonnegative_int(row["target_level"], f"{path}.target_level"),
        scaling_kind=scaling_kind,
        scaling_value=snapshot_value("scaling_stat_value"),
        snapshot_stats=tuple(
            SnapshotStat(key, number, snapshot_ids)
            for key, number in sorted(snapshot.items())
        ),
        mult=engine_value("mult"),
        base_dmg_bonus=engine_value("base_dmg_bonus"),
        flat_dmg=engine_value("flat_dmg"),
        base_damage=engine_value("base_damage"),
        dmg_bonus=engine_value("damage_bonus"),
        raw_crit_rate=snapshot_value("raw_crit_rate"),
        crit_rate=snapshot_value("crit_rate_clamped"),
        crit_damage=snapshot_value("crit_damage"),
        crit_roll=(
            None
            if row["crit_roll"] is None
            else FormulaValue(_number(row["crit_roll"], f"{path}.crit_roll"), engine_ids)
        ),
        hit_weak_point=_boolean(row["hit_weak_point"], f"{path}.hit_weak_point"),
        defense_multiplier=engine_value("def_mod"),
        defense_adjustment=engine_value("def_adj"),
        ignore_defense_percent=engine_value("ignore_def_percent"),
        resistance_multiplier=engine_value("res_mod"),
        resistance=engine_value("resistance"),
        amplifying=_boolean(row["amped"], f"{path}.amped"),
        amp_multiplier=engine_value("amp_mult"),
        elemental_mastery=snapshot_value("em"),
        em_bonus=engine_value("em_bonus"),
        reaction_bonus=engine_value("reaction_bonus"),
        amp_reaction_bonus=FormulaValue(
            _number(row["em_bonus"], f"{path}.em_bonus")
            + _number(row["reaction_bonus"], f"{path}.reaction_bonus"),
            engine_ids,
        ),
        group_multiplier=engine_value("damage_group_multiplier"),
        elevation=engine_value("elevation"),
        elevation_multiplier=engine_value("elevation_multiplier"),
    )
    expected_amp_total = formula_inputs.amp_multiplier.value * (
        1.0 + formula_inputs.amp_reaction_bonus.value
    )
    if formula_inputs.amplifying and not _close(
        _number(row["amp_total"], f"{path}.amp_total"), expected_amp_total
    ):
        raise TraceContractError(f"{path}.amp_total disagrees with amp inputs")
    _number(row["pre_amp_damage"], f"{path}.pre_amp_damage")

    aura_payload = {
        "reaction_operator_id": reaction_operator_id,
        "amp_type": _string(row["amp_type"], f"{path}.amp_type"),
        "catalyzed": _boolean(row["catalyzed"], f"{path}.catalyzed"),
        "icd_tag": _integer(row["icd_tag"], f"{path}.icd_tag"),
        "icd_group": _integer(row["icd_group"], f"{path}.icd_group"),
        "durability_initial": _number(
            row["durability_initial"], f"{path}.durability_initial"
        ),
        "durability_post_icd": _number(
            row["durability_post_icd"], f"{path}.durability_post_icd"
        ),
        "aura_before": _parse_auras(row["aura_before"], f"{path}.aura_before"),
        "aura_after_reaction": _parse_auras(
            row["aura_after_reaction"], f"{path}.aura_after_reaction"
        ),
        "aura_after_attachment": _parse_auras(
            row["aura_after_attachment"], f"{path}.aura_after_attachment"
        ),
    }
    known_operator = _known_reaction_operator(reaction_operator_id)
    opaque_json = None
    opaque_sha256 = None
    if known_operator is None or known_operator is ReactionOperator.OPAQUE_CUSTOM:
        opaque_json = canonical_json(aura_payload)
        opaque_sha256 = hashlib.sha256(opaque_json.encode("utf-8")).hexdigest()
    lineage = TraceLineage(
        parent_event_id=None if parent_hit_id is None else f"hit:{parent_hit_id}",
        source_event_id=f"attack:{attack_id}",
        damage_source_key=f"damage-src:{_integer(row['damage_src'], f'{path}.damage_src')}",
        gadget_id=None,
        reaction_type=None if known_operator is ReactionOperator.NONE else reaction_operator_id,
        reaction_operator_id=reaction_operator_id,
        reaction_operator_sha256=canonical_sha256(
            {
                "raw_reaction_operator_id": reaction_operator_id,
                "formula_sha256": formula_sha256,
            }
        ),
        opaque_reaction_payload_json=opaque_json,
        opaque_reaction_payload_sha256=opaque_sha256,
        reaction_owner_key=None,
        aura_source_keys=(),
    )

    reasons: set[str] = {"engine_v1_not_authoritative"}
    unsupported: set[str] = set(raw_unsupported) | set(top_unsupported)
    for field_name in _COMPLETENESS_KEYS:
        if not getattr(completeness, field_name):
            reasons.add(f"{field_name}_incomplete")
    known_formula = formula_inputs.known_formula_kind
    status = ReplayStatus.NEEDS_EXACT
    if formula_sha256 != request.formula_sha256:
        status = ReplayStatus.UNSUPPORTED
        reasons.add("formula_sha256_mismatch")
    if known_formula is None:
        status = ReplayStatus.UNSUPPORTED
        reasons.add("unknown_formula_kind")
    elif known_formula is DamageFormulaKind.DIRECT_LUNAR:
        reasons.add("direct_lunar_requires_exact_v1")
    elif known_formula is DamageFormulaKind.DIRECT_REACTION:
        reasons.add("direct_reaction_requires_exact_v1")
    if known_operator is None or known_operator is ReactionOperator.OPAQUE_CUSTOM:
        status = ReplayStatus.UNSUPPORTED
        reasons.add("opaque_reaction_operator")
    if raw_unsupported:
        # In v1 these codes describe missing provenance/topology authority.
        # They force exact simulation for ranking, but a known terminal formula
        # remains useful for explicitly non-authoritative arithmetic checks.
        reasons.add("engine_reported_incomplete_feature")
    if formula_inputs.flat_dmg.value != 0.0:
        reasons.add("flat_dmg_requires_exact_v1")
    if attack_mod_rows:
        unsupported.add("attack_mod_provider_identity_unavailable")

    damage_mode = (
        TraceDamageMode.DAMAGE
        if _boolean(row["damage_mode"], f"{path}.damage_mode")
        else TraceDamageMode.DURATION
    )
    return TraceHitEvent(
        event_id=f"hit:{hit_id}",
        frame=_nonnegative_int(row["frame"], f"{path}.frame"),
        source_frame=_nonnegative_int(row["source_frame"], f"{path}.source_frame"),
        snapshot_frame=_nonnegative_int(
            row["snapshot_frame"], f"{path}.snapshot_frame"
        ),
        actor_index=actor_index,
        actor_key=actor_key,
        ability=_nonempty_string(row["ability"], f"{path}.ability"),
        attack_tag=_integer(row["attack_tag"], f"{path}.attack_tag"),
        element=f"element:{_nonempty_string(row['element'], f'{path}.element')}",
        target_key=(
            f"target-type:{_integer(row['target_type'], f'{path}.target_type')}"
            f":{_integer(row['target_key'], f'{path}.target_key')}"
        ),
        target_index=_nonnegative_int(row["target_key"], f"{path}.target_key"),
        damage_mode=damage_mode,
        hp_cap_active=_boolean(row["hp_cap_active"], f"{path}.hp_cap_active"),
        lineage=lineage,
        provenance=tuple(provenance),
        formula_inputs=formula_inputs,
        uncapped_rolled_damage=_number(
            row["uncapped_damage"], f"{path}.uncapped_damage"
        ),
        hp_damage_applied=_number(row["actual_damage"], f"{path}.actual_damage"),
        reported_damage=_number(row["reported_damage"], f"{path}.reported_damage"),
        target_hp_before=_number(row["hp_before"], f"{path}.hp_before"),
        target_hp_after=_number(row["hp_after"], f"{path}.hp_after"),
        target_killed=_boolean(row["killed"], f"{path}.killed"),
        crit=_boolean(row["is_crit"], f"{path}.is_crit"),
        completeness=completeness,
        unsupported_feature_codes=tuple(sorted(unsupported)),
        formula_replay_status=status,
        formula_replay_reason_codes=tuple(sorted(reasons)),
    )


def _parse_completeness(value: object, path: str) -> TraceHitCompleteness:
    row = _object(value, path, _COMPLETENESS_KEYS)
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


def _parse_topology_events(value: object) -> tuple[TopologyEvidenceEvent, ...]:
    result: list[TopologyEvidenceEvent] = []
    for index, item in enumerate(_array(value, "$.topology_events")):
        path = f"$.topology_events[{index}]"
        row = _object(
            item,
            path,
            {"event_id", "frame", "phase", "kind", "subject_key", "state_sha256"},
        )
        kind = _string(row["kind"], f"{path}.kind")
        phase = _string(row["phase"], f"{path}.phase")
        if kind == "aura_state_changed" and phase in {"reaction", "attachment"}:
            channel = TopologyChannel.REACTIONS
            callback_phase = CallbackPhase.REACTION_RESOLUTION
        elif kind == "target_death" and phase == "damage":
            channel = TopologyChannel.DEATH_AND_WAVES
            callback_phase = CallbackPhase.DAMAGE_RESOLUTION
        else:
            raise TraceContractError(
                f"{path} has unsupported topology kind/phase {kind!r}/{phase!r}"
            )
        result.append(
            TopologyEvidenceEvent(
                event_id=f"engine-topology:{_uint64(row['event_id'], f'{path}.event_id')}",
                channel=channel,
                frame=_nonnegative_int(row["frame"], f"{path}.frame"),
                phase=callback_phase,
                kind_id=kind,
                subject_key=f"subject:{_integer(row['subject_key'], f'{path}.subject_key')}",
                state_sha256=_sha256(row["state_sha256"], f"{path}.state_sha256"),
            )
        )
    return tuple(result)


def _build_incomplete_topology(
    events: tuple[TopologyEvidenceEvent, ...],
    top_unsupported: tuple[str, ...],
) -> GuardTopologyReport:
    unsupported = tuple(
        sorted({"engine_v1_topology_coverage_incomplete", *top_unsupported})
    )
    return GuardTopologyReport(
        channels=tuple(
            TopologyChannelDigest(
                channel=channel,
                sha256=canonical_sha256(
                    [event.to_dict() for event in events if event.channel is channel]
                ),
                item_count=sum(event.channel is channel for event in events),
                complete=False,
            )
            for channel in TopologyChannel
        ),
        evidence_events=events,
        guards=(),
        unsupported_feature_codes=unsupported,
        complete=False,
    )


def _validate_guard_summary(
    value: object,
    *,
    raw_hits: list[object],
    topology_event_count: int,
    top_unsupported: tuple[str, ...],
) -> None:
    row = _object(value, "$.guard_summary", _GUARD_SUMMARY_KEYS)
    if _nonnegative_int(row["hit_count"], "$.guard_summary.hit_count") != len(raw_hits):
        raise TraceContractError("guard_summary hit_count mismatch")
    if (
        _nonnegative_int(
            row["topology_event_count"], "$.guard_summary.topology_event_count"
        )
        != topology_event_count
    ):
        raise TraceContractError("guard_summary topology_event_count mismatch")
    for key in ("unsupported_hit_count", "unsupported_count"):
        _nonnegative_int(row[key], f"$.guard_summary.{key}")
    _count_map(row["formula_kind_counts"], "$.guard_summary.formula_kind_counts")
    _count_map(
        row["reaction_operator_counts"],
        "$.guard_summary.reaction_operator_counts",
    )
    for key in _COMPLETENESS_KEYS | {"exact_replay_eligible"}:
        _boolean(row[key], f"$.guard_summary.{key}")
    if _boolean(row["exact_replay_eligible"], "$.guard_summary.exact_replay_eligible"):
        raise TraceContractError("raw engine trace v1 must not self-authorize exact replay")
    if (
        _nonnegative_int(row["unsupported_count"], "$.guard_summary.unsupported_count")
        < len(top_unsupported)
    ):
        raise TraceContractError("guard_summary unsupported_count is inconsistent")


def _scaling_kind(row: Mapping[str, object], path: str) -> ScalingKind:
    raw = _string(row["scaling_stat_kind"], f"{path}.scaling_stat_kind")
    try:
        result = ScalingKind(raw)
    except ValueError as exc:
        raise TraceContractError(f"{path}.scaling_stat_kind is unsupported") from exc
    expected = (
        ScalingKind.ELEMENTAL_MASTERY
        if _boolean(row["use_em"], f"{path}.use_em")
        else ScalingKind.DEFENSE
        if _boolean(row["use_def"], f"{path}.use_def")
        else ScalingKind.HP
        if _boolean(row["use_hp"], f"{path}.use_hp")
        else ScalingKind.ATTACK
    )
    if result is not expected:
        raise TraceContractError(f"{path}.scaling_stat_kind disagrees with use_* flags")
    return result


def _known_reaction_operator(raw: str) -> ReactionOperator | None:
    try:
        return ReactionOperator(raw)
    except ValueError:
        return None


def _parse_auras(value: object, path: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, item in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        row = _object(item, item_path, {"element", "durability"})
        rows.append(
            {
                "element": _string(row["element"], f"{item_path}.element"),
                "durability": _number(
                    row["durability"], f"{item_path}.durability"
                ),
            }
        )
    return rows


def _number_map(value: object, path: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise TraceContractError(f"{path} must be an object")
    result: dict[str, float] = {}
    for key, raw in value.items():
        _require_trimmed(key, f"{path} key")
        result[key] = _number(raw, f"{path}.{key}")
    return result


def _count_map(value: object, path: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise TraceContractError(f"{path} must be an object")
    result: dict[str, int] = {}
    for key, raw in value.items():
        _require_trimmed(key, f"{path} key")
        result[key] = _nonnegative_int(raw, f"{path}.{key}")
    return result


def _string_list(value: object, path: str) -> tuple[str, ...]:
    result = tuple(
        _nonempty_string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )
    if len(result) != len(set(result)):
        raise TraceContractError(f"{path} must contain unique strings")
    return result


def _sha256(value: object, path: str) -> str:
    raw = _string(value, path)
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw):
        raise TraceContractError(f"{path} must be a lowercase SHA-256 digest")
    return raw


def _uint64(value: object, path: str) -> int:
    result = _integer(value, path)
    if result < 0 or result > _UINT64_MAX:
        raise TraceContractError(f"{path} must be uint64")
    return result


def _optional_uint64(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _uint64(value, path)


def _nonnegative_int(value: object, path: str) -> int:
    result = _integer(value, path)
    if result < 0:
        raise TraceContractError(f"{path} must be non-negative")
    return result


def _positive_int(value: object, path: str) -> int:
    result = _integer(value, path)
    if result <= 0:
        raise TraceContractError(f"{path} must be positive")
    return result


def _optional_nonnegative_int(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, path)


def _character_index(
    value: object,
    path: str,
    character_keys: tuple[str, ...],
) -> int:
    result = _nonnegative_int(value, path)
    if result >= len(character_keys):
        raise TraceContractError(f"{path} is outside character_keys")
    return result


def _optional_character_index(
    value: object,
    path: str,
    character_keys: tuple[str, ...],
) -> int | None:
    if value is None:
        return None
    return _character_index(value, path, character_keys)


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _nonempty_string(value: object, path: str) -> str:
    result = _string(value, path)
    _require_trimmed(result, path)
    return result


def _require_trimmed(value: object, path: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{path} must be a non-empty trimmed string")


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-7, 1e-9 * max(abs(left), abs(right)))


__all__ = [
    "ENGINE_TRACE_CAPABILITY",
    "ENGINE_TRACE_SCHEMA_VERSION",
    "ENGINE_TRACE_V2_CAPABILITY",
    "ENGINE_TRACE_V2_SCHEMA_VERSION",
    "ENGINE_TRACE_V3_CAPABILITY",
    "ENGINE_TRACE_V3_SCHEMA_VERSION",
    "ENGINE_TRACE_V4_CAPABILITY",
    "ENGINE_TRACE_V4_SCHEMA_VERSION",
    "ENGINE_TRACE_V5_CAPABILITY",
    "ENGINE_TRACE_V5_SCHEMA_VERSION",
    "ENGINE_TRACE_V6_CAPABILITY",
    "ENGINE_TRACE_V6_SCHEMA_VERSION",
    "OpaqueEngineTraceEnvelope",
    "decode_engine_trace",
    "decode_engine_trace_v1",
    "decode_engine_trace_v2",
    "decode_engine_trace_v3",
    "decode_engine_trace_v4",
    "decode_engine_trace_v5",
    "decode_engine_trace_v6",
]
