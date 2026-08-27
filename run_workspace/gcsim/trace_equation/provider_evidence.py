"""Immutable provider evidence carried by raw engine trace schema v2.

The provider extension deliberately wraps the frozen terminal ``TraceDocument``
instead of changing its v1 JSON shape or receipt identity.  The evidence is
useful for attribution and future ranking work, but it is not a causal removal
certificate, an exact-replay certificate, or hard-prune authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from .codec import (
    _array,
    _boolean,
    _decode_json,
    _integer,
    _number,
    _object,
    _optional_string,
    _string,
    decode_trace_document,
)
from .contracts import (
    ReplayStatus,
    TraceContractError,
    TraceDocument,
    canonical_json,
    canonical_sha256,
)


PROVIDER_EVIDENCE_SCHEMA_VERSION = 2
PROVIDER_EVIDENCE_KIND = "gtt.trace_equation.provider_evidence"
_SET_PROVIDER_KINDS = frozenset({"artifact_set", "artifact-set", "set"})
_OWNER_REQUIRED_PROVIDER_KINDS = frozenset(
    {"character", "weapon", "artifact_set", "artifact-set", "set"}
)


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """Raw provider coordinates plus an explicit known/unknown bit.

    Go's zero value uses empty kind/key, owner index ``0`` and piece count ``0``.
    Honest unknown fallbacks may retain paired kind/key hints.  The explicit
    ``known`` field prevents either representation from being mistaken for a
    verified identity.  Even a known-looking identity remains untrusted by the
    wrapper because current instrumentation does not prove provider origin.
    """

    known: bool
    kind: str
    key: str
    owner_index: int
    piece_count: int

    def __post_init__(self) -> None:
        _require_bool(self.known, "provider.known")
        _require_trimmed_or_empty(self.kind, "provider.kind")
        _require_trimmed_or_empty(self.key, "provider.key")
        _require_int(self.owner_index, "provider.owner_index")
        _require_nonnegative_int(self.piece_count, "provider.piece_count")
        if bool(self.kind) is not bool(self.key):
            raise TraceContractError(
                "provider kind/key must either both be present or both be empty"
            )
        if not self.known:
            if self.owner_index not in {-1, 0} or self.piece_count != 0:
                raise TraceContractError(
                    "unknown provider must use the raw zero/-1 owner sentinel "
                    "and zero piece_count"
                )
        if self.known:
            if not self.kind or not self.key:
                raise TraceContractError("known provider requires kind and key")
            normalized_kind = self.kind.casefold()
            if (
                normalized_kind in _OWNER_REQUIRED_PROVIDER_KINDS
                and self.owner_index < 0
            ):
                raise TraceContractError(
                    "character/weapon/set provider requires a wearer owner_index"
                )
            if self.owner_index < -1:
                raise TraceContractError("known provider owner_index must be >= -1")
            if (
                normalized_kind in _SET_PROVIDER_KINDS
                and self.piece_count <= 0
            ):
                raise TraceContractError(
                    "known artifact-set provider requires positive piece_count"
                )

    @classmethod
    def from_raw(
        cls,
        *,
        known: bool,
        kind: str,
        key: str,
        owner_index: int,
        piece_count: int,
    ) -> "ProviderIdentity":
        return cls(
            known=known,
            kind=kind,
            key=key,
            owner_index=owner_index,
            piece_count=piece_count,
        )

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "known": self.known,
            "kind": self.kind,
            "key": self.key,
            "owner_index": self.owner_index,
            "piece_count": self.piece_count,
        }


@dataclass(frozen=True, slots=True)
class ProviderStatDelta:
    stat_key: str
    value: float

    def __post_init__(self) -> None:
        _require_trimmed(self.stat_key, "stat_delta.stat_key")
        _require_finite(self.value, "stat_delta.value")

    def to_dict(self) -> dict[str, object]:
        return {"stat_key": self.stat_key, "value": self.value}


@dataclass(frozen=True, slots=True)
class ProviderStatContribution:
    sequence_index: int
    modifier_key: str
    recipient_index: int
    accepted: bool
    values: tuple[ProviderStatDelta, ...]
    provider: ProviderIdentity
    modifier_eval_event_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.sequence_index, "stat contribution sequence")
        _require_trimmed(self.modifier_key, "stat contribution modifier_key")
        _require_nonnegative_int(self.recipient_index, "stat contribution recipient")
        _require_bool(self.accepted, "stat contribution accepted")
        _require_tuple(self.values, "stat contribution values")
        keys = tuple(row.stat_key for row in self.values)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise TraceContractError(
                "stat contribution values must be sorted by unique stat_key"
            )
        if any(
            math.isclose(row.value, 0.0, rel_tol=0.0, abs_tol=1e-12)
            for row in self.values
        ):
            raise TraceContractError(
                "stat contribution values must contain only non-zero deltas"
            )
        _require_provider(self.provider, "stat contribution provider")
        _require_optional_state_event_id(
            self.modifier_eval_event_id,
            "stat contribution modifier_eval_event_id",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "modifier_key": self.modifier_key,
            "recipient_index": self.recipient_index,
            "accepted": self.accepted,
            "values": [row.to_dict() for row in self.values],
            "provider": self.provider.to_dict(),
            "modifier_eval_event_id": self.modifier_eval_event_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderCallbackAttempt:
    sequence_index: int
    event: int
    hook_key: str
    provider: ProviderIdentity
    changed: bool
    topology_changed: bool
    state_effects_unobserved: bool
    snapshot_delta: tuple[ProviderStatDelta, ...]
    mult_delta: float
    flat_dmg_delta: float
    base_dmg_bonus_delta: float
    elevation_delta: float
    ignore_def_delta: float
    amp_multiplier_delta: float

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.sequence_index, "callback sequence")
        _require_nonnegative_int(self.event, "callback event")
        _require_trimmed_or_empty(self.hook_key, "callback hook_key")
        _require_provider(self.provider, "callback provider")
        _require_bool(self.changed, "callback changed")
        _require_bool(self.topology_changed, "callback topology_changed")
        _require_bool(
            self.state_effects_unobserved,
            "callback state_effects_unobserved",
        )
        _require_tuple(self.snapshot_delta, "callback snapshot_delta")
        keys = tuple(row.stat_key for row in self.snapshot_delta)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise TraceContractError(
                "callback snapshot_delta must be sorted by unique stat_key"
            )
        numeric = (
            self.mult_delta,
            self.flat_dmg_delta,
            self.base_dmg_bonus_delta,
            self.elevation_delta,
            self.ignore_def_delta,
            self.amp_multiplier_delta,
        )
        for name, value in zip(
            (
                "mult_delta",
                "flat_dmg_delta",
                "base_dmg_bonus_delta",
                "elevation_delta",
                "ignore_def_delta",
                "amp_multiplier_delta",
            ),
            numeric,
            strict=True,
        ):
            _require_finite(value, f"callback {name}")
        has_numeric_delta = any(
            not math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-12)
            for value in numeric
        ) or any(
            not math.isclose(row.value, 0.0, rel_tol=0.0, abs_tol=1e-12)
            for row in self.snapshot_delta
        )
        if has_numeric_delta and not self.changed:
            raise TraceContractError(
                "callback with a numeric delta must set changed=true"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "event": self.event,
            "hook_key": self.hook_key,
            "provider": self.provider.to_dict(),
            "changed": self.changed,
            "topology_changed": self.topology_changed,
            "state_effects_unobserved": self.state_effects_unobserved,
            "snapshot_delta": [row.to_dict() for row in self.snapshot_delta],
            "mult_delta": self.mult_delta,
            "flat_dmg_delta": self.flat_dmg_delta,
            "base_dmg_bonus_delta": self.base_dmg_bonus_delta,
            "elevation_delta": self.elevation_delta,
            "ignore_def_delta": self.ignore_def_delta,
            "amp_multiplier_delta": self.amp_multiplier_delta,
        }


@dataclass(frozen=True, slots=True)
class ProviderTargetModContribution:
    sequence_index: int
    channel: str
    modifier_key: str
    value: float
    provider: ProviderIdentity

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.sequence_index, "target mod sequence")
        _require_trimmed(self.channel, "target mod channel")
        _require_trimmed_or_empty(self.modifier_key, "target mod modifier_key")
        _require_finite(self.value, "target mod value")
        _require_provider(self.provider, "target mod provider")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "channel": self.channel,
            "modifier_key": self.modifier_key,
            "value": self.value,
            "provider": self.provider.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ProviderReactionBonusContribution:
    sequence_index: int
    modifier_key: str
    value: float
    provider: ProviderIdentity

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.sequence_index, "reaction bonus sequence")
        _require_trimmed_or_empty(self.modifier_key, "reaction bonus modifier_key")
        _require_finite(self.value, "reaction bonus value")
        _require_provider(self.provider, "reaction bonus provider")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "modifier_key": self.modifier_key,
            "value": self.value,
            "provider": self.provider.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ProviderAttackModEvidence:
    sequence_index: int
    modifier_key: str
    legacy_source_key: str
    legacy_owner_index: int
    accepted: bool
    before_damage: float | None
    after_damage: float | None
    delta: tuple[ProviderStatDelta, ...]
    provider: ProviderIdentity
    modifier_eval_event_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.sequence_index, "attack mod sequence")
        _require_trimmed(self.modifier_key, "attack mod modifier_key")
        _require_trimmed_or_empty(self.legacy_source_key, "attack mod source_key")
        _require_int(self.legacy_owner_index, "attack mod legacy_owner_index")
        _require_bool(self.accepted, "attack mod accepted")
        _require_optional_finite(self.before_damage, "attack mod before_damage")
        _require_optional_finite(self.after_damage, "attack mod after_damage")
        _require_tuple(self.delta, "attack mod delta")
        keys = tuple(row.stat_key for row in self.delta)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise TraceContractError(
                "attack mod delta must be sorted by unique stat_key"
            )
        _require_provider(self.provider, "attack mod provider")
        _require_optional_state_event_id(
            self.modifier_eval_event_id,
            "attack mod modifier_eval_event_id",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "modifier_key": self.modifier_key,
            "legacy_source_key": self.legacy_source_key,
            "legacy_owner_index": self.legacy_owner_index,
            "accepted": self.accepted,
            "before_damage": self.before_damage,
            "after_damage": self.after_damage,
            "delta": [row.to_dict() for row in self.delta],
            "provider": self.provider.to_dict(),
            "modifier_eval_event_id": self.modifier_eval_event_id,
        }


@dataclass(frozen=True, slots=True)
class HitProviderEvidence:
    event_id: str
    provider: ProviderIdentity
    stat_contributions: tuple[ProviderStatContribution, ...]
    callback_attempts: tuple[ProviderCallbackAttempt, ...]
    attack_mods: tuple[ProviderAttackModEvidence, ...]
    target_mod_contributions: tuple[ProviderTargetModContribution, ...]
    reaction_bonus_contributions: tuple[ProviderReactionBonusContribution, ...]

    def __post_init__(self) -> None:
        _require_trimmed(self.event_id, "hit provider evidence event_id")
        _require_provider(self.provider, "hit provider")
        for label, rows in (
            ("stat_contributions", self.stat_contributions),
            ("callback_attempts", self.callback_attempts),
            ("attack_mods", self.attack_mods),
            ("target_mod_contributions", self.target_mod_contributions),
            ("reaction_bonus_contributions", self.reaction_bonus_contributions),
        ):
            _require_contiguous_sequence(rows, label)

    def iter_providers(self) -> tuple[ProviderIdentity, ...]:
        return (
            self.provider,
            *(row.provider for row in self.stat_contributions),
            *(row.provider for row in self.callback_attempts),
            *(row.provider for row in self.attack_mods),
            *(row.provider for row in self.target_mod_contributions),
            *(row.provider for row in self.reaction_bonus_contributions),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "provider": self.provider.to_dict(),
            "stat_contributions": [row.to_dict() for row in self.stat_contributions],
            "callback_attempts": [row.to_dict() for row in self.callback_attempts],
            "attack_mods": [row.to_dict() for row in self.attack_mods],
            "target_mod_contributions": [
                row.to_dict() for row in self.target_mod_contributions
            ],
            "reaction_bonus_contributions": [
                row.to_dict() for row in self.reaction_bonus_contributions
            ],
        }


@dataclass(frozen=True, slots=True)
class ProviderTransition:
    """One row in the engine's deterministic transition catalog.

    ``catalog_index`` preserves wire-array identity.  It is deliberately not
    called an execution sequence: the current engine sorts this catalog after
    collection and does not expose a causal ordinal for same-frame callbacks.
    """

    catalog_index: int
    frame: int
    channel: str
    recipient_index: int
    modifier_key: str
    transition: str
    provider: ProviderIdentity
    displaced_provider: ProviderIdentity | None

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.catalog_index, "provider transition catalog index")
        _require_sentinel_or_nonnegative_int(self.frame, "provider transition frame")
        _require_trimmed(self.channel, "provider transition channel")
        _require_sentinel_or_nonnegative_int(
            self.recipient_index,
            "provider transition recipient",
        )
        _require_trimmed_or_empty(self.modifier_key, "provider transition modifier_key")
        _require_trimmed(self.transition, "provider transition kind")
        _require_provider(self.provider, "provider transition provider")
        if self.displaced_provider is not None:
            _require_provider(
                self.displaced_provider,
                "provider transition displaced_provider",
            )

    def iter_providers(self) -> tuple[ProviderIdentity, ...]:
        if self.displaced_provider is None:
            return (self.provider,)
        return (self.provider, self.displaced_provider)

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_index": self.catalog_index,
            "frame": self.frame,
            "channel": self.channel,
            "recipient_index": self.recipient_index,
            "modifier_key": self.modifier_key,
            "transition": self.transition,
            "provider": self.provider.to_dict(),
            "displaced_provider": (
                None
                if self.displaced_provider is None
                else self.displaced_provider.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class ProviderEvidenceTrace:
    terminal_trace: TraceDocument
    engine_request_sha256: str
    raw_payload_sha256: str
    hit_evidence: tuple[HitProviderEvidence, ...]
    provider_transitions: tuple[ProviderTransition, ...]
    authority_reason_codes: tuple[str, ...]
    evidence_sha256: str
    exact_replay_eligible: bool = False
    hard_prune_allowed: bool = False
    kind: str = PROVIDER_EVIDENCE_KIND
    schema_version: int = PROVIDER_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_EVIDENCE_SCHEMA_VERSION:
            raise TraceContractError("unsupported provider evidence schema")
        if self.kind != PROVIDER_EVIDENCE_KIND:
            raise TraceContractError("unsupported provider evidence kind")
        if not isinstance(self.terminal_trace, TraceDocument):
            raise TraceContractError("terminal_trace must be TraceDocument")
        _require_sha256(self.engine_request_sha256, "engine_request_sha256")
        _require_sha256(self.raw_payload_sha256, "raw_payload_sha256")
        _require_tuple(self.hit_evidence, "hit_evidence")
        _require_contiguous_catalog(self.provider_transitions, "provider_transitions")
        _require_sorted_unique_strings(
            self.authority_reason_codes,
            "authority_reason_codes",
        )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        _require_bool(self.exact_replay_eligible, "exact_replay_eligible")
        _require_bool(self.hard_prune_allowed, "hard_prune_allowed")
        if self.exact_replay_eligible or self.hard_prune_allowed:
            raise TraceContractError(
                "provider evidence v2 cannot authorize exact replay or hard prune"
            )
        if self.terminal_trace.topology.complete or any(
            hit.formula_replay_status is ReplayStatus.EXACT_IN_CELL
            for hit in self.terminal_trace.hits
        ):
            raise TraceContractError(
                "provider evidence v2 terminal trace must remain NEEDS_EXACT/unsupported"
            )
        hit_ids = tuple(hit.event_id for hit in self.terminal_trace.hits)
        evidence_ids = tuple(row.event_id for row in self.hit_evidence)
        if hit_ids != evidence_ids:
            raise TraceContractError(
                "hit_evidence must match terminal trace hits in engine order"
            )
        frames = tuple(row.frame for row in self.provider_transitions)
        if frames != tuple(sorted(frames)):
            raise TraceContractError(
                "provider_transitions must preserve non-decreasing frame order"
            )
        character_count = len(self.terminal_trace.request.character_keys)
        for hit in self.hit_evidence:
            for contribution in hit.stat_contributions:
                _require_index_in_range(
                    contribution.recipient_index,
                    character_count,
                    "stat contribution recipient",
                )
            for provider in hit.iter_providers():
                _validate_provider_owner(provider, character_count)
        for transition in self.provider_transitions:
            if transition.recipient_index >= 0:
                _require_index_in_range(
                    transition.recipient_index,
                    character_count,
                    "provider transition recipient",
                )
            for provider in transition.iter_providers():
                _validate_provider_owner(provider, character_count)
        expected_reasons = _authority_reason_codes(
            self.terminal_trace,
            self.hit_evidence,
            self.provider_transitions,
        )
        if self.authority_reason_codes != expected_reasons:
            raise TraceContractError(
                "authority_reason_codes do not match provider evidence"
            )
        expected_hash = provider_evidence_body_sha256(
            terminal_trace=self.terminal_trace,
            engine_request_sha256=self.engine_request_sha256,
            raw_payload_sha256=self.raw_payload_sha256,
            hit_evidence=self.hit_evidence,
            provider_transitions=self.provider_transitions,
            authority_reason_codes=self.authority_reason_codes,
        )
        if self.evidence_sha256 != expected_hash:
            raise TraceContractError("provider evidence SHA-256 mismatch")

    @classmethod
    def build(
        cls,
        *,
        terminal_trace: TraceDocument,
        engine_request_sha256: str,
        raw_payload_sha256: str,
        hit_evidence: tuple[HitProviderEvidence, ...],
        provider_transitions: tuple[ProviderTransition, ...],
    ) -> "ProviderEvidenceTrace":
        reasons = _authority_reason_codes(
            terminal_trace,
            hit_evidence,
            provider_transitions,
        )
        evidence_sha256 = provider_evidence_body_sha256(
            terminal_trace=terminal_trace,
            engine_request_sha256=engine_request_sha256,
            raw_payload_sha256=raw_payload_sha256,
            hit_evidence=hit_evidence,
            provider_transitions=provider_transitions,
            authority_reason_codes=reasons,
        )
        return cls(
            terminal_trace=terminal_trace,
            engine_request_sha256=engine_request_sha256,
            raw_payload_sha256=raw_payload_sha256,
            hit_evidence=hit_evidence,
            provider_transitions=provider_transitions,
            authority_reason_codes=reasons,
            evidence_sha256=evidence_sha256,
        )

    @property
    def all_provider_identities_known(self) -> bool:
        return all(
            provider.known
            for provider in _iter_all_providers(
                self.hit_evidence,
                self.provider_transitions,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "terminal_trace": self.terminal_trace.to_dict(),
            "engine_request_sha256": self.engine_request_sha256,
            "raw_payload_sha256": self.raw_payload_sha256,
            "hit_evidence": [row.to_dict() for row in self.hit_evidence],
            "provider_transitions": [
                row.to_dict() for row in self.provider_transitions
            ],
            "authority_reason_codes": list(self.authority_reason_codes),
            "evidence_sha256": self.evidence_sha256,
            "exact_replay_eligible": self.exact_replay_eligible,
            "hard_prune_allowed": self.hard_prune_allowed,
        }


def provider_evidence_body_sha256(
    *,
    terminal_trace: TraceDocument,
    engine_request_sha256: str,
    raw_payload_sha256: str,
    hit_evidence: tuple[HitProviderEvidence, ...],
    provider_transitions: tuple[ProviderTransition, ...],
    authority_reason_codes: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "schema_version": PROVIDER_EVIDENCE_SCHEMA_VERSION,
            "terminal_trace_receipt_sha256": terminal_trace.receipt.receipt_sha256,
            "engine_request_sha256": engine_request_sha256,
            "raw_payload_sha256": raw_payload_sha256,
            "hit_evidence": [row.to_dict() for row in hit_evidence],
            "provider_transitions": [row.to_dict() for row in provider_transitions],
            "authority_reason_codes": list(authority_reason_codes),
            "exact_replay_eligible": False,
            "hard_prune_allowed": False,
        }
    )


def encode_provider_evidence_trace(document: ProviderEvidenceTrace) -> str:
    if not isinstance(document, ProviderEvidenceTrace):
        raise TraceContractError("document must be ProviderEvidenceTrace")
    return canonical_json(document.to_dict())


def decode_provider_evidence_trace(
    payload: str | bytes | bytearray,
) -> ProviderEvidenceTrace:
    root = _decode_json(payload)
    row = _object(
        root,
        "$",
        {
            "schema_version",
            "kind",
            "terminal_trace",
            "engine_request_sha256",
            "raw_payload_sha256",
            "hit_evidence",
            "provider_transitions",
            "authority_reason_codes",
            "evidence_sha256",
            "exact_replay_eligible",
            "hard_prune_allowed",
        },
    )
    terminal_trace = decode_trace_document(canonical_json(row["terminal_trace"]))
    return ProviderEvidenceTrace(
        schema_version=_integer(row["schema_version"], "$.schema_version"),
        kind=_string(row["kind"], "$.kind"),
        terminal_trace=terminal_trace,
        engine_request_sha256=_string(
            row["engine_request_sha256"], "$.engine_request_sha256"
        ),
        raw_payload_sha256=_string(
            row["raw_payload_sha256"], "$.raw_payload_sha256"
        ),
        hit_evidence=tuple(
            _hit_provider_evidence(item, f"$.hit_evidence[{index}]")
            for index, item in enumerate(
                _array(row["hit_evidence"], "$.hit_evidence")
            )
        ),
        provider_transitions=tuple(
            _provider_transition(item, f"$.provider_transitions[{index}]")
            for index, item in enumerate(
                _array(row["provider_transitions"], "$.provider_transitions")
            )
        ),
        authority_reason_codes=_string_tuple(
            row["authority_reason_codes"], "$.authority_reason_codes"
        ),
        evidence_sha256=_string(row["evidence_sha256"], "$.evidence_sha256"),
        exact_replay_eligible=_boolean(
            row["exact_replay_eligible"], "$.exact_replay_eligible"
        ),
        hard_prune_allowed=_boolean(
            row["hard_prune_allowed"], "$.hard_prune_allowed"
        ),
    )


def _hit_provider_evidence(value: object, path: str) -> HitProviderEvidence:
    row = _object(
        value,
        path,
        {
            "event_id",
            "provider",
            "stat_contributions",
            "callback_attempts",
            "attack_mods",
            "target_mod_contributions",
            "reaction_bonus_contributions",
        },
    )
    return HitProviderEvidence(
        event_id=_string(row["event_id"], f"{path}.event_id"),
        provider=_provider(row["provider"], f"{path}.provider"),
        stat_contributions=tuple(
            _stat_contribution(item, f"{path}.stat_contributions[{index}]")
            for index, item in enumerate(
                _array(row["stat_contributions"], f"{path}.stat_contributions")
            )
        ),
        callback_attempts=tuple(
            _callback_attempt(item, f"{path}.callback_attempts[{index}]")
            for index, item in enumerate(
                _array(row["callback_attempts"], f"{path}.callback_attempts")
            )
        ),
        attack_mods=tuple(
            _attack_mod(item, f"{path}.attack_mods[{index}]")
            for index, item in enumerate(
                _array(row["attack_mods"], f"{path}.attack_mods")
            )
        ),
        target_mod_contributions=tuple(
            _target_mod(item, f"{path}.target_mod_contributions[{index}]")
            for index, item in enumerate(
                _array(
                    row["target_mod_contributions"],
                    f"{path}.target_mod_contributions",
                )
            )
        ),
        reaction_bonus_contributions=tuple(
            _reaction_bonus(
                item,
                f"{path}.reaction_bonus_contributions[{index}]",
            )
            for index, item in enumerate(
                _array(
                    row["reaction_bonus_contributions"],
                    f"{path}.reaction_bonus_contributions",
                )
            )
        ),
    )


def _provider(value: object, path: str) -> ProviderIdentity:
    row = _object(value, path, {"known", "kind", "key", "owner_index", "piece_count"})
    return ProviderIdentity(
        known=_boolean(row["known"], f"{path}.known"),
        kind=_string(row["kind"], f"{path}.kind"),
        key=_string(row["key"], f"{path}.key"),
        owner_index=_integer(row["owner_index"], f"{path}.owner_index"),
        piece_count=_integer(row["piece_count"], f"{path}.piece_count"),
    )


def decode_provider_identity(value: object, path: str) -> ProviderIdentity:
    """Decode the exact provider wire shape shared by additive trace schemas."""

    return _provider(value, path)


def _stat_delta(value: object, path: str) -> ProviderStatDelta:
    row = _object(value, path, {"stat_key", "value"})
    return ProviderStatDelta(
        stat_key=_string(row["stat_key"], f"{path}.stat_key"),
        value=_number(row["value"], f"{path}.value"),
    )


def _stat_contribution(value: object, path: str) -> ProviderStatContribution:
    has_binding = (
        isinstance(value, Mapping) and "modifier_eval_event_id" in value
    )
    row = _object(
        value,
        path,
        {
            "sequence_index",
            "modifier_key",
            "recipient_index",
            "accepted",
            "values",
            "provider",
            *({"modifier_eval_event_id"} if has_binding else set()),
        },
    )
    return ProviderStatContribution(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        recipient_index=_integer(row["recipient_index"], f"{path}.recipient_index"),
        accepted=_boolean(row["accepted"], f"{path}.accepted"),
        values=tuple(
            _stat_delta(item, f"{path}.values[{index}]")
            for index, item in enumerate(_array(row["values"], f"{path}.values"))
        ),
        provider=_provider(row["provider"], f"{path}.provider"),
        modifier_eval_event_id=(
            _optional_string(
                row["modifier_eval_event_id"],
                f"{path}.modifier_eval_event_id",
            )
            if has_binding
            else None
        ),
    )


def _callback_attempt(value: object, path: str) -> ProviderCallbackAttempt:
    row = _object(
        value,
        path,
        {
            "sequence_index",
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
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        event=_integer(row["event"], f"{path}.event"),
        hook_key=_string(row["hook_key"], f"{path}.hook_key"),
        provider=_provider(row["provider"], f"{path}.provider"),
        changed=_boolean(row["changed"], f"{path}.changed"),
        topology_changed=_boolean(
            row["topology_changed"], f"{path}.topology_changed"
        ),
        state_effects_unobserved=_boolean(
            row["state_effects_unobserved"],
            f"{path}.state_effects_unobserved",
        ),
        snapshot_delta=tuple(
            _stat_delta(item, f"{path}.snapshot_delta[{index}]")
            for index, item in enumerate(
                _array(row["snapshot_delta"], f"{path}.snapshot_delta")
            )
        ),
        mult_delta=_number(row["mult_delta"], f"{path}.mult_delta"),
        flat_dmg_delta=_number(row["flat_dmg_delta"], f"{path}.flat_dmg_delta"),
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


def _attack_mod(value: object, path: str) -> ProviderAttackModEvidence:
    has_binding = (
        isinstance(value, Mapping) and "modifier_eval_event_id" in value
    )
    row = _object(
        value,
        path,
        {
            "sequence_index",
            "modifier_key",
            "legacy_source_key",
            "legacy_owner_index",
            "accepted",
            "before_damage",
            "after_damage",
            "delta",
            "provider",
            *({"modifier_eval_event_id"} if has_binding else set()),
        },
    )
    return ProviderAttackModEvidence(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        legacy_source_key=_string(
            row["legacy_source_key"], f"{path}.legacy_source_key"
        ),
        legacy_owner_index=_integer(
            row["legacy_owner_index"], f"{path}.legacy_owner_index"
        ),
        accepted=_boolean(row["accepted"], f"{path}.accepted"),
        before_damage=_optional_number(
            row["before_damage"], f"{path}.before_damage"
        ),
        after_damage=_optional_number(
            row["after_damage"], f"{path}.after_damage"
        ),
        delta=tuple(
            _stat_delta(item, f"{path}.delta[{index}]")
            for index, item in enumerate(_array(row["delta"], f"{path}.delta"))
        ),
        provider=_provider(row["provider"], f"{path}.provider"),
        modifier_eval_event_id=(
            _optional_string(
                row["modifier_eval_event_id"],
                f"{path}.modifier_eval_event_id",
            )
            if has_binding
            else None
        ),
    )


def _target_mod(value: object, path: str) -> ProviderTargetModContribution:
    row = _object(
        value,
        path,
        {"sequence_index", "channel", "modifier_key", "value", "provider"},
    )
    return ProviderTargetModContribution(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        channel=_string(row["channel"], f"{path}.channel"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        value=_number(row["value"], f"{path}.value"),
        provider=_provider(row["provider"], f"{path}.provider"),
    )


def _reaction_bonus(value: object, path: str) -> ProviderReactionBonusContribution:
    row = _object(
        value,
        path,
        {"sequence_index", "modifier_key", "value", "provider"},
    )
    return ProviderReactionBonusContribution(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        value=_number(row["value"], f"{path}.value"),
        provider=_provider(row["provider"], f"{path}.provider"),
    )


def _provider_transition(value: object, path: str) -> ProviderTransition:
    row = _object(
        value,
        path,
        {
            "catalog_index",
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
        catalog_index=_integer(row["catalog_index"], f"{path}.catalog_index"),
        frame=_integer(row["frame"], f"{path}.frame"),
        channel=_string(row["channel"], f"{path}.channel"),
        recipient_index=_integer(row["recipient_index"], f"{path}.recipient_index"),
        modifier_key=_string(row["modifier_key"], f"{path}.modifier_key"),
        transition=_string(row["transition"], f"{path}.transition"),
        provider=_provider(row["provider"], f"{path}.provider"),
        displaced_provider=(
            None if displaced is None else _provider(displaced, f"{path}.displaced_provider")
        ),
    )


def _authority_reason_codes(
    terminal_trace: TraceDocument,
    hit_evidence: tuple[HitProviderEvidence, ...],
    provider_transitions: tuple[ProviderTransition, ...],
) -> tuple[str, ...]:
    reasons = {
        "provider_evidence_not_causal_certificate",
        "provider_origin_trust_not_proven",
        "terminal_topology_incomplete",
    }
    providers = tuple(_iter_all_providers(hit_evidence, provider_transitions))
    if any(not provider.known for provider in providers):
        reasons.add("provider_identity_unknown")
    if any(
        callback.topology_changed
        for hit in hit_evidence
        for callback in hit.callback_attempts
    ):
        reasons.add("callback_topology_change_unmodeled")
    if any(
        callback.state_effects_unobserved
        for hit in hit_evidence
        for callback in hit.callback_attempts
    ):
        reasons.add("callback_state_effects_unobserved")
    if any(
        not row.modifier_key
        for hit in hit_evidence
        for rows in (
            hit.stat_contributions,
            hit.attack_mods,
            hit.target_mod_contributions,
            hit.reaction_bonus_contributions,
        )
        for row in rows
    ) or any(
        not callback.hook_key
        for hit in hit_evidence
        for callback in hit.callback_attempts
    ):
        reasons.add("provider_evidence_key_missing")
    return tuple(sorted(reasons))


def _iter_all_providers(
    hit_evidence: tuple[HitProviderEvidence, ...],
    provider_transitions: tuple[ProviderTransition, ...],
):
    for hit in hit_evidence:
        yield from hit.iter_providers()
    for transition in provider_transitions:
        yield from transition.iter_providers()


def _validate_provider_owner(provider: ProviderIdentity, character_count: int) -> None:
    if not provider.known:
        return
    if provider.kind.casefold() in _OWNER_REQUIRED_PROVIDER_KINDS:
        _require_index_in_range(
            provider.owner_index,
            character_count,
            "known provider owner",
        )
    elif provider.owner_index != -1:
        _require_index_in_range(
            provider.owner_index,
            character_count,
            "known provider owner",
        )


def _require_contiguous_sequence(rows: object, label: str) -> None:
    _require_tuple(rows, label)
    assert isinstance(rows, tuple)
    actual = tuple(row.sequence_index for row in rows)
    expected = tuple(range(len(rows)))
    if actual != expected:
        raise TraceContractError(f"{label} sequence_index must be contiguous and ordered")


def _require_contiguous_catalog(rows: object, label: str) -> None:
    _require_tuple(rows, label)
    assert isinstance(rows, tuple)
    actual = tuple(row.catalog_index for row in rows)
    expected = tuple(range(len(rows)))
    if actual != expected:
        raise TraceContractError(
            f"{label} catalog_index must be contiguous and preserve wire order"
        )


def _require_index_in_range(value: int, size: int, label: str) -> None:
    if value < 0 or value >= size:
        raise TraceContractError(f"{label} is outside character_keys")


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _require_provider(value: object, label: str) -> None:
    if not isinstance(value, ProviderIdentity):
        raise TraceContractError(f"{label} must be ProviderIdentity")


def _require_trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _require_trimmed_or_empty(value: object, label: str) -> None:
    if not isinstance(value, str) or value != value.strip():
        raise TraceContractError(f"{label} must be a trimmed string")


def _require_optional_state_event_id(value: object, label: str) -> None:
    if value is None:
        return
    _require_trimmed(value, label)
    assert isinstance(value, str)
    prefix = "state-event:"
    suffix = value.removeprefix(prefix)
    if not value.startswith(prefix) or not suffix.isdigit():
        raise TraceContractError(f"{label} must reference a state event")


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TraceContractError(f"{label} must be a lowercase SHA-256 digest")


def _require_tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise TraceContractError(f"{label} must be an immutable tuple")


def _require_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TraceContractError(f"{label} must be a boolean")


def _require_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{label} must be an integer")


def _require_nonnegative_int(value: object, label: str) -> None:
    _require_int(value, label)
    assert isinstance(value, int)
    if value < 0:
        raise TraceContractError(f"{label} must be non-negative")


def _require_sentinel_or_nonnegative_int(value: object, label: str) -> None:
    _require_int(value, label)
    assert isinstance(value, int)
    if value < -1:
        raise TraceContractError(
            f"{label} must be -1 sentinel or non-negative"
        )


def _require_finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{label} must be finite")


def _require_optional_finite(value: object, label: str) -> None:
    if value is not None:
        _require_finite(value, label)


def _require_sorted_unique_strings(values: object, label: str) -> None:
    _require_tuple(values, label)
    assert isinstance(values, tuple)
    for value in values:
        _require_trimmed(value, f"{label} item")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise TraceContractError(f"{label} must be sorted and unique")


__all__ = [
    "HitProviderEvidence",
    "PROVIDER_EVIDENCE_KIND",
    "PROVIDER_EVIDENCE_SCHEMA_VERSION",
    "ProviderAttackModEvidence",
    "ProviderCallbackAttempt",
    "ProviderEvidenceTrace",
    "ProviderIdentity",
    "ProviderReactionBonusContribution",
    "ProviderStatContribution",
    "ProviderStatDelta",
    "ProviderTargetModContribution",
    "ProviderTransition",
    "decode_provider_identity",
    "decode_provider_evidence_trace",
    "encode_provider_evidence_trace",
    "provider_evidence_body_sha256",
]
