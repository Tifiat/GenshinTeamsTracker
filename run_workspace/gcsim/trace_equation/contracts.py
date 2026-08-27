"""Immutable contracts for the trace-equation engine/Python boundary.

This is the first, deliberately narrow trace-era schema described by
``docs/handoff/GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md``.  It models the
audited terminal enemy-damage seam and the topology information needed to
decide whether a candidate may be replayed.  It is not a scorer, candidate
generator, optimizer, or compatibility facade for the removed M/S pipelines.

Schema v1 intentionally treats non-zero ``flat_dmg`` and direct-lunar damage
as exact-simulation cases.  Later engine provenance may make those formulae
replayable, but that requires an explicit schema/version change rather than a
silent relaxation of this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import TypeAlias


TRACE_DOCUMENT_SCHEMA_VERSION = 1
TRACE_EXTRACTION_REQUEST_SCHEMA_VERSION = 1
TRACE_EXTRACTION_RECEIPT_SCHEMA_VERSION = 1
TRACE_TOPOLOGY_SCHEMA_VERSION = 1
TRACE_REPLAY_ASSESSMENT_SCHEMA_VERSION = 1

TRACE_DOCUMENT_KIND = "gtt.trace_equation.trace"
TRACE_EXTRACTION_REQUEST_KIND = "gtt.trace_equation.extraction_request"
TRACE_EXTRACTION_RECEIPT_KIND = "gtt.trace_equation.extraction_receipt"
TRACE_TOPOLOGY_KIND = "gtt.trace_equation.guard_topology"
TRACE_REPLAY_ASSESSMENT_KIND = "gtt.trace_equation.replay_assessment"
TOPOLOGY_COVERAGE_SENTINEL_KIND = "coverage_complete"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEED_MAX = 2**63 - 1
_FORMULA_REL_TOLERANCE = 1e-9
_FORMULA_ABS_TOLERANCE = 1e-7


class TraceContractError(ValueError):
    """Raised when a trace object violates the frozen schema contract."""


class TraceObjective(str, Enum):
    CLEAR_TIME = "clear_time"
    CAPPED_DAMAGE = "capped_damage"
    UNCAPPED_DAMAGE = "uncapped_damage"
    TEAM_DPS = "team_dps"


class ReplayStatus(str, Enum):
    EXACT_IN_CELL = "EXACT_IN_CELL"
    NEEDS_EXACT = "NEEDS_EXACT"
    UNSUPPORTED = "UNSUPPORTED"


class DamageFormulaKind(str, Enum):
    NORMAL = "standard"
    DIRECT_LUNAR = "direct_lunar"


class ScalingKind(str, Enum):
    ATTACK = "atk"
    HP = "hp"
    DEFENSE = "def"
    ELEMENTAL_MASTERY = "em"


class TraceDamageMode(str, Enum):
    DAMAGE = "damage"
    DURATION = "duration"


class ReactionOperator(str, Enum):
    NONE = "none"
    MULTIPLY_PARENT_HIT = "multiply_parent_hit"
    ADD_FLAT_TO_PARENT_HIT_BEFORE_BONUSES = (
        "add_flat_to_parent_hit_before_bonuses"
    )
    SPAWN_DAMAGE_ATTACK = "spawn_damage_attack"
    PERSISTENT_OWNER_TICK = "persistent_owner_tick"
    GADGET_LIFECYCLE = "gadget_lifecycle"
    TEAM_CONTRIBUTION_REDUCE = "team_contribution_reduce"
    OPAQUE_CUSTOM = "opaque_custom"


class ProvenanceSourceKind(str, Enum):
    ENGINE_FORMULA = "engine_formula"
    CHARACTER = "character"
    WEAPON = "weapon"
    ARTIFACT = "artifact"
    ARTIFACT_SET = "artifact_set"
    TALENT = "talent"
    CONSTELLATION = "constellation"
    REACTION = "reaction"
    GADGET = "gadget"
    SCENARIO = "scenario"
    TARGET = "target"
    OPAQUE_CUSTOM = "opaque_custom"


class CallbackPhase(str, Enum):
    SNAPSHOT = "snapshot"
    ON_ENEMY_HIT = "on_enemy_hit"
    REACTION_RESOLUTION = "reaction_resolution"
    DAMAGE_RESOLUTION = "damage_resolution"
    ON_ENEMY_DAMAGE = "on_enemy_damage"
    END_OF_FRAME = "end_of_frame"
    UNKNOWN = "unknown"


class ValueReadMode(str, Enum):
    SNAPSHOT = "snapshot"
    LIVE = "live"
    CONSTANT = "constant"


class TopologyChannel(str, Enum):
    ACTIONS = "actions"
    EVENTS = "events"
    REACTIONS = "reactions"
    GADGETS = "gadgets"
    TARGETS = "targets"
    RNG = "rng"
    DEATH_AND_WAVES = "death_and_waves"


class GuardKind(str, Enum):
    ACTION_FEASIBILITY = "action_feasibility"
    ENERGY = "energy"
    COOLDOWN = "cooldown"
    ATTACK_SPEED = "attack_speed"
    HITLAG = "hitlag"
    EVENT_ORDER = "event_order"
    RNG_BRANCH = "rng_branch"
    CRIT_CONTROL_FLOW = "crit_control_flow"
    HP = "hp"
    HEALING = "healing"
    COUNTER = "counter"
    SHIELD = "shield"
    THRESHOLD = "threshold"
    DEATH = "death"
    STACK = "stack"
    ICD = "icd"
    STATUS = "status"
    GLOBAL_STATE = "global_state"
    AURA = "aura"
    REACTION_TYPE = "reaction_type"
    REACTION_OWNER = "reaction_owner"
    SPAWN_COUNT = "spawn_count"
    GADGET = "gadget"
    TARGET_GEOMETRY = "target_geometry"
    DAMAGE_CAP = "damage_cap"
    WAVE_TRANSITION = "wave_transition"
    CLEAR_TIME = "clear_time"
    OPAQUE_CUSTOM = "opaque_custom"


class GuardOperator(str, Enum):
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    CLOSED_INTERVAL = "closed_interval"
    HASH_EQUAL = "hash_equal"


GuardScalar: TypeAlias = bool | int | float | str


def canonical_json(value: object) -> str:
    """Return the canonical JSON representation used by Python-side hashes."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TraceContractError(f"value is not canonical-JSON encodable: {exc}") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FormulaProvenance:
    provenance_id: str
    source_kind: ProvenanceSourceKind
    source_key: str
    owner_key: str | None
    provider_event_id: str | None
    modifier_key: str | None
    modifier_channel: str | None
    read_phase: CallbackPhase
    read_mode: ValueReadMode

    def __post_init__(self) -> None:
        _require_trimmed(self.provenance_id, "provenance_id")
        _require_enum(self.source_kind, ProvenanceSourceKind, "source_kind")
        _require_trimmed(self.source_key, "source_key")
        _require_optional_trimmed(self.owner_key, "owner_key")
        _require_optional_trimmed(self.provider_event_id, "provider_event_id")
        _require_optional_trimmed(self.modifier_key, "modifier_key")
        _require_optional_trimmed(self.modifier_channel, "modifier_channel")
        _require_enum(self.read_phase, CallbackPhase, "read_phase")
        _require_enum(self.read_mode, ValueReadMode, "read_mode")

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance_id": self.provenance_id,
            "source_kind": self.source_kind.value,
            "source_key": self.source_key,
            "owner_key": self.owner_key,
            "provider_event_id": self.provider_event_id,
            "modifier_key": self.modifier_key,
            "modifier_channel": self.modifier_channel,
            "read_phase": self.read_phase.value,
            "read_mode": self.read_mode.value,
        }


@dataclass(frozen=True, slots=True)
class FormulaValue:
    """One observed scalar plus attribution IDs; this is not a symbolic node."""

    value: float
    provenance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_finite(self.value, "value")
        _require_sorted_unique_strings(self.provenance_ids, "provenance_ids")

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "provenance_ids": list(self.provenance_ids),
        }


@dataclass(frozen=True, slots=True)
class SnapshotStat:
    stat_key: str
    value: float
    provenance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_trimmed(self.stat_key, "stat_key")
        _require_finite(self.value, "value")
        _require_sorted_unique_strings(self.provenance_ids, "provenance_ids")

    def to_dict(self) -> dict[str, object]:
        return {
            "stat_key": self.stat_key,
            "value": self.value,
            "provenance_ids": list(self.provenance_ids),
        }


@dataclass(frozen=True, slots=True)
class DamageFormulaInputs:
    """Exact inputs observed at the audited terminal enemy-damage seam."""

    formula_kind: str
    formula_sha256: str
    character_level: int
    target_level: int
    scaling_kind: ScalingKind
    scaling_value: FormulaValue
    snapshot_stats: tuple[SnapshotStat, ...]
    mult: FormulaValue
    base_dmg_bonus: FormulaValue
    flat_dmg: FormulaValue
    base_damage: FormulaValue
    dmg_bonus: FormulaValue
    raw_crit_rate: FormulaValue
    crit_rate: FormulaValue
    crit_damage: FormulaValue
    crit_roll: FormulaValue | None
    hit_weak_point: bool
    defense_multiplier: FormulaValue
    defense_adjustment: FormulaValue
    ignore_defense_percent: FormulaValue
    resistance_multiplier: FormulaValue
    resistance: FormulaValue
    amplifying: bool
    amp_multiplier: FormulaValue
    elemental_mastery: FormulaValue
    em_bonus: FormulaValue
    reaction_bonus: FormulaValue
    amp_reaction_bonus: FormulaValue
    group_multiplier: FormulaValue
    elevation: FormulaValue
    elevation_multiplier: FormulaValue

    def __post_init__(self) -> None:
        _require_trimmed(self.formula_kind, "formula_kind")
        _require_sha256(self.formula_sha256, "formula_sha256")
        _require_nonnegative_int(self.character_level, "character_level")
        _require_nonnegative_int(self.target_level, "target_level")
        _require_enum(self.scaling_kind, ScalingKind, "scaling_kind")
        for field_name in (
            "scaling_value",
            "mult",
            "base_dmg_bonus",
            "flat_dmg",
            "base_damage",
            "dmg_bonus",
            "raw_crit_rate",
            "crit_rate",
            "crit_damage",
            "defense_multiplier",
            "defense_adjustment",
            "ignore_defense_percent",
            "resistance_multiplier",
            "resistance",
            "amp_multiplier",
            "elemental_mastery",
            "em_bonus",
            "reaction_bonus",
            "amp_reaction_bonus",
            "group_multiplier",
            "elevation",
            "elevation_multiplier",
        ):
            if not isinstance(getattr(self, field_name), FormulaValue):
                raise TraceContractError(f"{field_name} must be FormulaValue")
        if self.crit_roll is not None and not isinstance(self.crit_roll, FormulaValue):
            raise TraceContractError("crit_roll must be FormulaValue or null")
        _require_bool(self.hit_weak_point, "hit_weak_point")
        _require_bool(self.amplifying, "amplifying")
        _require_tuple(self.snapshot_stats, "snapshot_stats")
        stat_keys = tuple(stat.stat_key for stat in self.snapshot_stats)
        if stat_keys != tuple(sorted(stat_keys)) or len(stat_keys) != len(set(stat_keys)):
            raise TraceContractError(
                "snapshot_stats must be sorted by unique stat_key"
            )
        snapshot = {stat.stat_key: stat.value for stat in self.snapshot_stats}
        for required_key in ("cr", "cd", "em"):
            if required_key not in snapshot:
                raise TraceContractError(
                    f"full snapshot_stats is missing required key {required_key!r}"
                )
        _require_close(
            self.raw_crit_rate.value,
            snapshot["cr"],
            "raw_crit_rate does not match snapshot CR",
        )
        _require_close(
            self.crit_damage.value,
            snapshot["cd"],
            "crit_damage does not match snapshot CD",
        )
        _require_close(
            self.elemental_mastery.value,
            snapshot["em"],
            "elemental_mastery does not match snapshot EM",
        )
        if not 0.0 <= self.crit_rate.value <= 1.0:
            raise TraceContractError("crit_rate must contain the engine-clamped [0, 1] value")
        _require_close(
            self.crit_rate.value,
            max(0.0, min(1.0, self.raw_crit_rate.value)),
            "crit_rate must be the exact clamp of raw_crit_rate",
        )
        if self.crit_roll is not None and not 0.0 <= self.crit_roll.value < 1.0:
            raise TraceContractError("crit_roll must be in [0, 1)")
        if self.hit_weak_point and self.crit_roll is not None:
            raise TraceContractError("weak-point hits must not consume an RNG crit roll")

        _require_close(
            self.amp_reaction_bonus.value,
            self.em_bonus.value + self.reaction_bonus.value,
            "amp_reaction_bonus must equal em_bonus + reaction_bonus",
        )
        _require_close(
            self.resistance_multiplier.value,
            _engine_resistance_multiplier(self.resistance.value),
            "resistance_multiplier does not match the bound engine branch",
        )
        _require_close(
            self.elevation_multiplier.value,
            1.0 + self.elevation.value,
            "elevation_multiplier must equal 1 + elevation",
        )

        if self.known_formula_kind is DamageFormulaKind.NORMAL:
            if self.amplifying:
                if self.elemental_mastery.value <= -1400.0:
                    raise TraceContractError("amplifying EM formula is outside its domain")
                _require_close(
                    self.em_bonus.value,
                    (2.78 * self.elemental_mastery.value)
                    / (1400.0 + self.elemental_mastery.value),
                    "em_bonus does not match the bound amplifying formula",
                )
            else:
                for field_name in ("em_bonus", "reaction_bonus", "amp_reaction_bonus"):
                    _require_close(
                        getattr(self, field_name).value,
                        0.0,
                        f"non-amplifying {field_name} must be zero",
                    )
            scaling_from_snapshot = _snapshot_scaling_value(
                self.scaling_kind,
                snapshot,
            )
            _require_close(
                self.scaling_value.value,
                scaling_from_snapshot,
                "scaling_value does not match snapshot stats",
            )
            expected_base = (
                self.mult.value
                * self.scaling_value.value
                * (1.0 + self.base_dmg_bonus.value)
                + self.flat_dmg.value
            )
            _require_close(
                self.base_damage.value,
                expected_base,
                "base_damage does not match the normal damage formula",
            )

    @property
    def known_formula_kind(self) -> DamageFormulaKind | None:
        """Map known formula IDs while retaining unknown IDs for fail-open bailout."""

        try:
            return DamageFormulaKind(self.formula_kind)
        except ValueError:
            return None

    def iter_formula_values(self) -> tuple[FormulaValue, ...]:
        values = (
            self.scaling_value,
            self.mult,
            self.base_dmg_bonus,
            self.flat_dmg,
            self.base_damage,
            self.dmg_bonus,
            self.raw_crit_rate,
            self.crit_rate,
            self.crit_damage,
            self.defense_multiplier,
            self.defense_adjustment,
            self.ignore_defense_percent,
            self.resistance_multiplier,
            self.resistance,
            self.amp_multiplier,
            self.elemental_mastery,
            self.em_bonus,
            self.reaction_bonus,
            self.amp_reaction_bonus,
            self.group_multiplier,
            self.elevation,
            self.elevation_multiplier,
        )
        if self.crit_roll is None:
            return values
        return (*values, self.crit_roll)

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_kind": self.formula_kind,
            "formula_sha256": self.formula_sha256,
            "character_level": self.character_level,
            "target_level": self.target_level,
            "scaling_kind": self.scaling_kind.value,
            "scaling_value": self.scaling_value.to_dict(),
            "snapshot_stats": [stat.to_dict() for stat in self.snapshot_stats],
            "mult": self.mult.to_dict(),
            "base_dmg_bonus": self.base_dmg_bonus.to_dict(),
            "flat_dmg": self.flat_dmg.to_dict(),
            "base_damage": self.base_damage.to_dict(),
            "dmg_bonus": self.dmg_bonus.to_dict(),
            "raw_crit_rate": self.raw_crit_rate.to_dict(),
            "crit_rate": self.crit_rate.to_dict(),
            "crit_damage": self.crit_damage.to_dict(),
            "crit_roll": None if self.crit_roll is None else self.crit_roll.to_dict(),
            "hit_weak_point": self.hit_weak_point,
            "defense_multiplier": self.defense_multiplier.to_dict(),
            "defense_adjustment": self.defense_adjustment.to_dict(),
            "ignore_defense_percent": self.ignore_defense_percent.to_dict(),
            "resistance_multiplier": self.resistance_multiplier.to_dict(),
            "resistance": self.resistance.to_dict(),
            "amplifying": self.amplifying,
            "amp_multiplier": self.amp_multiplier.to_dict(),
            "elemental_mastery": self.elemental_mastery.to_dict(),
            "em_bonus": self.em_bonus.to_dict(),
            "reaction_bonus": self.reaction_bonus.to_dict(),
            "amp_reaction_bonus": self.amp_reaction_bonus.to_dict(),
            "group_multiplier": self.group_multiplier.to_dict(),
            "elevation": self.elevation.to_dict(),
            "elevation_multiplier": self.elevation_multiplier.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TraceLineage:
    parent_event_id: str | None
    source_event_id: str | None
    damage_source_key: str
    gadget_id: str | None
    reaction_type: str | None
    reaction_operator_id: str
    reaction_operator_sha256: str
    opaque_reaction_payload_json: str | None
    opaque_reaction_payload_sha256: str | None
    reaction_owner_key: str | None
    aura_source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_optional_trimmed(self.parent_event_id, "parent_event_id")
        _require_optional_trimmed(self.source_event_id, "source_event_id")
        _require_trimmed(self.damage_source_key, "damage_source_key")
        _require_optional_trimmed(self.gadget_id, "gadget_id")
        _require_optional_trimmed(self.reaction_type, "reaction_type")
        _require_trimmed(self.reaction_operator_id, "reaction_operator_id")
        _require_sha256(self.reaction_operator_sha256, "reaction_operator_sha256")
        _require_optional_canonical_json(
            self.opaque_reaction_payload_json,
            "opaque_reaction_payload_json",
        )
        _require_optional_sha256(
            self.opaque_reaction_payload_sha256,
            "opaque_reaction_payload_sha256",
        )
        if (self.opaque_reaction_payload_json is None) is not (
            self.opaque_reaction_payload_sha256 is None
        ):
            raise TraceContractError(
                "opaque reaction payload JSON and SHA-256 must appear together"
            )
        if self.opaque_reaction_payload_json is not None:
            payload_hash = hashlib.sha256(
                self.opaque_reaction_payload_json.encode("utf-8")
            ).hexdigest()
            if payload_hash != self.opaque_reaction_payload_sha256:
                raise TraceContractError("opaque reaction payload SHA-256 mismatch")
        _require_optional_trimmed(self.reaction_owner_key, "reaction_owner_key")
        _require_sorted_unique_strings(self.aura_source_keys, "aura_source_keys")
        operator = self.known_reaction_operator
        if operator is ReactionOperator.NONE:
            if self.reaction_type is not None or self.reaction_owner_key is not None:
                raise TraceContractError(
                    "reaction_type/reaction_owner_key require a non-none reaction operator"
                )
        elif (
            operator is not None
            and operator is not ReactionOperator.OPAQUE_CUSTOM
            and self.reaction_type is None
        ):
            raise TraceContractError("a non-none reaction operator requires reaction_type")
        if operator in {None, ReactionOperator.OPAQUE_CUSTOM}:
            if self.opaque_reaction_payload_json is None:
                raise TraceContractError(
                    "unknown/opaque reaction operator requires preserved canonical payload"
                )

    @property
    def known_reaction_operator(self) -> ReactionOperator | None:
        """Return a known operator, preserving unknown raw IDs as opaque data."""

        try:
            return ReactionOperator(self.reaction_operator_id)
        except ValueError:
            return None

    def to_dict(self) -> dict[str, object]:
        return {
            "parent_event_id": self.parent_event_id,
            "source_event_id": self.source_event_id,
            "damage_source_key": self.damage_source_key,
            "gadget_id": self.gadget_id,
            "reaction_type": self.reaction_type,
            "reaction_operator_id": self.reaction_operator_id,
            "reaction_operator_sha256": self.reaction_operator_sha256,
            "opaque_reaction_payload_json": self.opaque_reaction_payload_json,
            "opaque_reaction_payload_sha256": self.opaque_reaction_payload_sha256,
            "reaction_owner_key": self.reaction_owner_key,
            "aura_source_keys": list(self.aura_source_keys),
        }


@dataclass(frozen=True, slots=True)
class TraceHitCompleteness:
    formula_complete: bool
    flat_dmg_provenance_complete: bool
    attack_mod_provenance_complete: bool
    reaction_topology_complete: bool
    provider_identity_complete: bool

    def __post_init__(self) -> None:
        for field_name in (
            "formula_complete",
            "flat_dmg_provenance_complete",
            "attack_mod_provenance_complete",
            "reaction_topology_complete",
            "provider_identity_complete",
        ):
            _require_bool(getattr(self, field_name), field_name)

    @property
    def replay_complete(self) -> bool:
        return all(
            (
                self.formula_complete,
                self.flat_dmg_provenance_complete,
                self.attack_mod_provenance_complete,
                self.reaction_topology_complete,
                self.provider_identity_complete,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_complete": self.formula_complete,
            "flat_dmg_provenance_complete": self.flat_dmg_provenance_complete,
            "attack_mod_provenance_complete": self.attack_mod_provenance_complete,
            "reaction_topology_complete": self.reaction_topology_complete,
            "provider_identity_complete": self.provider_identity_complete,
        }


@dataclass(frozen=True, slots=True)
class TraceHitEvent:
    event_id: str
    frame: int
    source_frame: int
    snapshot_frame: int
    actor_index: int
    actor_key: str
    ability: str
    attack_tag: int
    element: str
    target_key: str
    target_index: int
    damage_mode: TraceDamageMode
    hp_cap_active: bool
    lineage: TraceLineage
    provenance: tuple[FormulaProvenance, ...]
    formula_inputs: DamageFormulaInputs
    uncapped_rolled_damage: float
    hp_damage_applied: float
    reported_damage: float
    target_hp_before: float
    target_hp_after: float
    target_killed: bool
    crit: bool
    completeness: TraceHitCompleteness
    unsupported_feature_codes: tuple[str, ...]
    formula_replay_status: ReplayStatus
    formula_replay_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_trimmed(self.event_id, "event_id")
        _require_nonnegative_int(self.frame, "frame")
        _require_nonnegative_int(self.source_frame, "source_frame")
        _require_nonnegative_int(self.snapshot_frame, "snapshot_frame")
        _require_nonnegative_int(self.actor_index, "actor_index")
        _require_trimmed(self.actor_key, "actor_key")
        _require_trimmed(self.ability, "ability")
        _require_int(self.attack_tag, "attack_tag")
        _require_trimmed(self.element, "element")
        _require_trimmed(self.target_key, "target_key")
        _require_nonnegative_int(self.target_index, "target_index")
        _require_enum(self.damage_mode, TraceDamageMode, "damage_mode")
        _require_bool(self.hp_cap_active, "hp_cap_active")
        if not isinstance(self.lineage, TraceLineage):
            raise TraceContractError("lineage must be TraceLineage")
        _require_tuple(self.provenance, "provenance")
        if not isinstance(self.formula_inputs, DamageFormulaInputs):
            raise TraceContractError("formula_inputs must be DamageFormulaInputs")
        _require_finite(self.uncapped_rolled_damage, "uncapped_rolled_damage")
        _require_finite(self.hp_damage_applied, "hp_damage_applied")
        _require_finite(self.reported_damage, "reported_damage")
        _require_finite(self.target_hp_before, "target_hp_before")
        _require_finite(self.target_hp_after, "target_hp_after")
        if self.target_hp_before < 0.0 or self.target_hp_after < 0.0:
            raise TraceContractError("target HP values must be non-negative")
        _require_bool(self.target_killed, "target_killed")
        _require_bool(self.crit, "crit")
        if not isinstance(self.completeness, TraceHitCompleteness):
            raise TraceContractError("completeness must be TraceHitCompleteness")
        _require_sorted_unique_strings(
            self.unsupported_feature_codes,
            "unsupported_feature_codes",
        )
        _require_enum(self.formula_replay_status, ReplayStatus, "formula_replay_status")
        _require_sorted_unique_strings(
            self.formula_replay_reason_codes,
            "formula_replay_reason_codes",
        )

        provenance_ids = tuple(item.provenance_id for item in self.provenance)
        if len(provenance_ids) != len(set(provenance_ids)):
            raise TraceContractError("provenance_id values must be unique per event")
        known_ids = set(provenance_ids)
        for value in self.formula_inputs.iter_formula_values():
            unknown = set(value.provenance_ids) - known_ids
            if unknown:
                raise TraceContractError(
                    f"formula input references unknown provenance ids: {sorted(unknown)!r}"
                )
        for stat in self.formula_inputs.snapshot_stats:
            unknown = set(stat.provenance_ids) - known_ids
            if unknown:
                raise TraceContractError(
                    f"snapshot stat references unknown provenance ids: {sorted(unknown)!r}"
                )

        known_formula_kind = self.formula_inputs.known_formula_kind
        known_reaction_operator = self.lineage.known_reaction_operator

        if self.formula_replay_status is ReplayStatus.EXACT_IN_CELL:
            if self.formula_replay_reason_codes:
                raise TraceContractError("EXACT_IN_CELL hit must not carry reason codes")
            if self.unsupported_feature_codes:
                raise TraceContractError("EXACT_IN_CELL hit cannot carry unsupported features")
            if not self.completeness.replay_complete:
                raise TraceContractError("EXACT_IN_CELL hit requires complete provenance")
            if not self.provenance:
                raise TraceContractError("EXACT_IN_CELL hit requires provenance rows")
            if any(
                not value.provenance_ids
                for value in self.formula_inputs.iter_formula_values()
            ):
                raise TraceContractError(
                    "EXACT_IN_CELL requires attribution for every formula input"
                )
            if any(
                not stat.provenance_ids
                for stat in self.formula_inputs.snapshot_stats
            ):
                raise TraceContractError(
                    "EXACT_IN_CELL requires attribution for every snapshot stat"
                )
            if known_formula_kind is not DamageFormulaKind.NORMAL:
                raise TraceContractError("direct-lunar formula is NEEDS_EXACT in schema v1")
            if not math.isclose(
                self.formula_inputs.flat_dmg.value,
                0.0,
                rel_tol=0.0,
                abs_tol=_FORMULA_ABS_TOLERANCE,
            ):
                raise TraceContractError("non-zero flat_dmg is NEEDS_EXACT in schema v1")
            if not self.formula_inputs.hit_weak_point and self.formula_inputs.crit_roll is None:
                raise TraceContractError(
                    "EXACT_IN_CELL random-crit hit requires the captured crit_roll"
                )
        elif not self.formula_replay_reason_codes:
            raise TraceContractError("non-exact hit must carry at least one reason code")

        if known_formula_kind is None:
            if self.formula_replay_status is not ReplayStatus.UNSUPPORTED:
                raise TraceContractError("unknown formula kinds must be UNSUPPORTED")
        elif known_formula_kind is DamageFormulaKind.DIRECT_LUNAR:
            if self.formula_replay_status is ReplayStatus.EXACT_IN_CELL:
                raise TraceContractError("direct-lunar formula is not exact in schema v1")
        if not math.isclose(
            self.formula_inputs.flat_dmg.value,
            0.0,
            rel_tol=0.0,
            abs_tol=_FORMULA_ABS_TOLERANCE,
        ) and self.formula_replay_status is ReplayStatus.EXACT_IN_CELL:
            raise TraceContractError("non-zero flat_dmg is not exact in schema v1")
        if known_reaction_operator in {None, ReactionOperator.OPAQUE_CUSTOM}:
            if self.formula_replay_status is not ReplayStatus.UNSUPPORTED:
                raise TraceContractError("opaque reaction operators must be UNSUPPORTED")

        if self.formula_inputs.hit_weak_point:
            if not self.crit:
                raise TraceContractError("weak-point hit must be recorded as a crit")
        elif self.formula_inputs.crit_roll is not None:
            expected_crit = (
                self.formula_inputs.crit_roll.value
                <= self.formula_inputs.crit_rate.value
            )
            if self.crit is not expected_crit:
                raise TraceContractError("crit result disagrees with captured CR/crit_roll")

        if known_formula_kind is DamageFormulaKind.NORMAL:
            expected_uncapped = _normal_uncapped_damage(self.formula_inputs, self.crit)
            _require_close(
                self.uncapped_rolled_damage,
                expected_uncapped,
                "uncapped_rolled_damage does not match formula inputs",
            )
        if (
            self.uncapped_rolled_damage >= 0.0
            and self.hp_damage_applied
            > self.uncapped_rolled_damage + _FORMULA_ABS_TOLERANCE
        ):
            raise TraceContractError(
                "hp_damage_applied cannot exceed uncapped_rolled_damage"
            )
        if self.hp_cap_active is not (self.damage_mode is TraceDamageMode.DAMAGE):
            raise TraceContractError("hp_cap_active must equal the engine DamageMode flag")
        _require_close(
            self.hp_damage_applied,
            min(self.uncapped_rolled_damage, self.target_hp_before),
            "hp_damage_applied does not match internal HP subtraction",
        )
        _require_close(
            self.target_hp_after,
            max(0.0, self.target_hp_before - self.hp_damage_applied),
            "target_hp_after does not match hp_damage_applied",
        )
        if self.damage_mode is TraceDamageMode.DAMAGE:
            if self.target_killed is not math.isclose(
                self.target_hp_after,
                0.0,
                rel_tol=0.0,
                abs_tol=_FORMULA_ABS_TOLERANCE,
            ):
                raise TraceContractError("target_killed disagrees with target_hp_after")
        elif self.target_killed:
            raise TraceContractError(
                "duration mode must not claim the damage-mode target-death event"
            )
        expected_reported = (
            self.hp_damage_applied
            if self.damage_mode is TraceDamageMode.DAMAGE and self.target_killed
            else self.uncapped_rolled_damage
        )
        _require_close(
            self.reported_damage,
            expected_reported,
            "reported_damage does not match applyDamage/OnEnemyDamage semantics",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "frame": self.frame,
            "source_frame": self.source_frame,
            "snapshot_frame": self.snapshot_frame,
            "actor_index": self.actor_index,
            "actor_key": self.actor_key,
            "ability": self.ability,
            "attack_tag": self.attack_tag,
            "element": self.element,
            "target_key": self.target_key,
            "target_index": self.target_index,
            "damage_mode": self.damage_mode.value,
            "hp_cap_active": self.hp_cap_active,
            "lineage": self.lineage.to_dict(),
            "provenance": [item.to_dict() for item in self.provenance],
            "formula_inputs": self.formula_inputs.to_dict(),
            "uncapped_rolled_damage": self.uncapped_rolled_damage,
            "hp_damage_applied": self.hp_damage_applied,
            "reported_damage": self.reported_damage,
            "target_hp_before": self.target_hp_before,
            "target_hp_after": self.target_hp_after,
            "target_killed": self.target_killed,
            "crit": self.crit,
            "completeness": self.completeness.to_dict(),
            "unsupported_feature_codes": list(self.unsupported_feature_codes),
            "formula_replay_status": self.formula_replay_status.value,
            "formula_replay_reason_codes": list(self.formula_replay_reason_codes),
        }


@dataclass(frozen=True, slots=True)
class TopologyChannelDigest:
    channel: TopologyChannel
    sha256: str
    item_count: int
    complete: bool

    def __post_init__(self) -> None:
        _require_enum(self.channel, TopologyChannel, "channel")
        _require_sha256(self.sha256, "sha256")
        _require_nonnegative_int(self.item_count, "item_count")
        _require_bool(self.complete, "complete")

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel.value,
            "sha256": self.sha256,
            "item_count": self.item_count,
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class TopologyEvidenceEvent:
    event_id: str
    channel: TopologyChannel
    frame: int
    phase: CallbackPhase
    kind_id: str
    subject_key: str
    state_sha256: str

    def __post_init__(self) -> None:
        _require_trimmed(self.event_id, "event_id")
        _require_enum(self.channel, TopologyChannel, "channel")
        _require_nonnegative_int(self.frame, "frame")
        _require_enum(self.phase, CallbackPhase, "phase")
        _require_trimmed(self.kind_id, "kind_id")
        _require_trimmed(self.subject_key, "subject_key")
        _require_sha256(self.state_sha256, "state_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "channel": self.channel.value,
            "frame": self.frame,
            "phase": self.phase.value,
            "kind_id": self.kind_id,
            "subject_key": self.subject_key,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class GuardPredicate:
    operator: GuardOperator
    expected_value: GuardScalar | None
    lower_bound: float | None
    upper_bound: float | None
    lower_inclusive: bool
    upper_inclusive: bool

    def __post_init__(self) -> None:
        _require_enum(self.operator, GuardOperator, "operator")
        if self.expected_value is not None:
            _require_guard_scalar(self.expected_value, "expected_value")
        if self.lower_bound is not None:
            _require_finite(self.lower_bound, "lower_bound")
        if self.upper_bound is not None:
            _require_finite(self.upper_bound, "upper_bound")
        _require_bool(self.lower_inclusive, "lower_inclusive")
        _require_bool(self.upper_inclusive, "upper_inclusive")

        if self.operator is GuardOperator.CLOSED_INTERVAL:
            if self.expected_value is not None:
                raise TraceContractError(
                    "closed_interval predicate must not have expected_value"
                )
            if self.lower_bound is None or self.upper_bound is None:
                raise TraceContractError(
                    "closed_interval predicate requires both bounds"
                )
            if self.lower_bound > self.upper_bound:
                raise TraceContractError("closed_interval lower_bound exceeds upper_bound")
        else:
            if self.expected_value is None:
                raise TraceContractError(
                    f"{self.operator.value} predicate requires expected_value"
                )
            if self.lower_bound is not None or self.upper_bound is not None:
                raise TraceContractError(
                    f"{self.operator.value} predicate must not have interval bounds"
                )
            if self.operator in {
                GuardOperator.LESS_THAN,
                GuardOperator.LESS_THAN_OR_EQUAL,
                GuardOperator.GREATER_THAN,
                GuardOperator.GREATER_THAN_OR_EQUAL,
            }:
                _require_numeric_guard_scalar(self.expected_value, "expected_value")
            if self.operator is GuardOperator.HASH_EQUAL:
                _require_sha256(self.expected_value, "expected_value")

    def holds(self, value: GuardScalar) -> bool:
        _require_guard_scalar(value, "guard value")
        if self.operator is GuardOperator.EQUAL:
            return _guard_equal(value, self.expected_value)
        if self.operator is GuardOperator.NOT_EQUAL:
            return not _guard_equal(value, self.expected_value)
        if self.operator is GuardOperator.HASH_EQUAL:
            return value == self.expected_value
        if self.operator is GuardOperator.CLOSED_INTERVAL:
            numeric = _numeric_guard_value(value)
            assert self.lower_bound is not None and self.upper_bound is not None
            lower_ok = (
                numeric >= self.lower_bound
                if self.lower_inclusive
                else numeric > self.lower_bound
            )
            upper_ok = (
                numeric <= self.upper_bound
                if self.upper_inclusive
                else numeric < self.upper_bound
            )
            return lower_ok and upper_ok
        numeric = _numeric_guard_value(value)
        expected = _numeric_guard_value(self.expected_value)
        if self.operator is GuardOperator.LESS_THAN:
            return numeric < expected
        if self.operator is GuardOperator.LESS_THAN_OR_EQUAL:
            return numeric <= expected
        if self.operator is GuardOperator.GREATER_THAN:
            return numeric > expected
        if self.operator is GuardOperator.GREATER_THAN_OR_EQUAL:
            return numeric >= expected
        raise TraceContractError(f"unhandled guard operator {self.operator.value}")

    def to_dict(self) -> dict[str, object]:
        return {
            "operator": self.operator.value,
            "expected_value": self.expected_value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "lower_inclusive": self.lower_inclusive,
            "upper_inclusive": self.upper_inclusive,
        }


@dataclass(frozen=True, slots=True)
class GuardObservation:
    guard_id: str
    guard_kind: GuardKind
    frame: int
    subject_key: str
    phase: CallbackPhase
    baseline_value: GuardScalar
    predicate: GuardPredicate
    dependency_keys: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_trimmed(self.guard_id, "guard_id")
        _require_enum(self.guard_kind, GuardKind, "guard_kind")
        _require_nonnegative_int(self.frame, "frame")
        _require_trimmed(self.subject_key, "subject_key")
        _require_enum(self.phase, CallbackPhase, "phase")
        _require_guard_scalar(self.baseline_value, "baseline_value")
        if not isinstance(self.predicate, GuardPredicate):
            raise TraceContractError("predicate must be GuardPredicate")
        _require_sorted_unique_strings(self.dependency_keys, "dependency_keys")
        _require_sorted_unique_strings(self.evidence_event_ids, "evidence_event_ids")
        if not self.predicate.holds(self.baseline_value):
            raise TraceContractError("baseline_value does not satisfy its guard predicate")

    def to_dict(self) -> dict[str, object]:
        return {
            "guard_id": self.guard_id,
            "guard_kind": self.guard_kind.value,
            "frame": self.frame,
            "subject_key": self.subject_key,
            "phase": self.phase.value,
            "baseline_value": self.baseline_value,
            "predicate": self.predicate.to_dict(),
            "dependency_keys": list(self.dependency_keys),
            "evidence_event_ids": list(self.evidence_event_ids),
        }


@dataclass(frozen=True, slots=True)
class GuardTopologyReport:
    channels: tuple[TopologyChannelDigest, ...]
    evidence_events: tuple[TopologyEvidenceEvent, ...]
    guards: tuple[GuardObservation, ...]
    unsupported_feature_codes: tuple[str, ...]
    complete: bool
    kind: str = TRACE_TOPOLOGY_KIND
    schema_version: int = TRACE_TOPOLOGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_exact(self.schema_version, TRACE_TOPOLOGY_SCHEMA_VERSION, "topology schema")
        _require_exact(self.kind, TRACE_TOPOLOGY_KIND, "topology kind")
        _require_tuple(self.channels, "channels")
        _require_tuple(self.evidence_events, "evidence_events")
        _require_tuple(self.guards, "guards")
        _require_sorted_unique_strings(
            self.unsupported_feature_codes,
            "unsupported_feature_codes",
        )
        _require_bool(self.complete, "complete")
        channel_values = tuple(item.channel for item in self.channels)
        expected_channels = tuple(TopologyChannel)
        if channel_values != expected_channels:
            raise TraceContractError(
                "channels must contain every TopologyChannel exactly once in schema order"
            )
        evidence_ids = tuple(event.event_id for event in self.evidence_events)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise TraceContractError("topology evidence event ids must be unique")
        if tuple(event.frame for event in self.evidence_events) != tuple(
            sorted(event.frame for event in self.evidence_events)
        ):
            raise TraceContractError(
                "topology evidence events must preserve non-decreasing frame order"
            )
        for digest in self.channels:
            rows = [
                event.to_dict()
                for event in self.evidence_events
                if event.channel is digest.channel
            ]
            if digest.item_count != len(rows):
                raise TraceContractError(
                    f"{digest.channel.value} item_count does not match evidence rows"
                )
            if digest.sha256 != canonical_sha256(rows):
                raise TraceContractError(
                    f"{digest.channel.value} SHA-256 does not match evidence rows"
                )
            if digest.complete and not any(
                row["kind_id"] == TOPOLOGY_COVERAGE_SENTINEL_KIND
                for row in rows
            ):
                raise TraceContractError(
                    f"complete {digest.channel.value} channel requires an explicit "
                    "coverage sentinel"
                )
        guard_ids = tuple(guard.guard_id for guard in self.guards)
        if len(guard_ids) != len(set(guard_ids)):
            raise TraceContractError("guard_id values must be unique")
        evidence_id_set = set(evidence_ids)
        for guard in self.guards:
            unknown = set(guard.evidence_event_ids) - evidence_id_set
            if unknown:
                raise TraceContractError(
                    f"guard references unknown topology evidence: {sorted(unknown)!r}"
                )
        computed_complete = (
            all(channel.complete for channel in self.channels)
            and not self.unsupported_feature_codes
        )
        if self.complete is not computed_complete:
            raise TraceContractError(
                "complete must equal all channel completeness with no unsupported features"
            )

    @property
    def topology_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "channels": [channel.to_dict() for channel in self.channels],
            "evidence_events": [event.to_dict() for event in self.evidence_events],
            "guards": [guard.to_dict() for guard in self.guards],
            "unsupported_feature_codes": list(self.unsupported_feature_codes),
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class TraceExtractionRequest:
    context_sha256: str
    source_config_sha256: str
    compiled_action_sha256: str
    target_sha256: str
    engine_artifact_sha256: str
    engine_binding_sha256: str
    formula_version: str
    formula_sha256: str
    seed: int
    objective: TraceObjective
    character_keys: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    kind: str = TRACE_EXTRACTION_REQUEST_KIND
    schema_version: int = TRACE_EXTRACTION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_exact(
            self.schema_version,
            TRACE_EXTRACTION_REQUEST_SCHEMA_VERSION,
            "extraction request schema",
        )
        _require_exact(self.kind, TRACE_EXTRACTION_REQUEST_KIND, "extraction request kind")
        for field_name in (
            "context_sha256",
            "source_config_sha256",
            "compiled_action_sha256",
            "target_sha256",
            "engine_artifact_sha256",
            "engine_binding_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_trimmed(self.formula_version, "formula_version")
        _require_sha256(self.formula_sha256, "formula_sha256")
        _require_int(self.seed, "seed")
        if self.seed <= 0 or self.seed > _SEED_MAX:
            raise TraceContractError(f"seed must be in [1, {_SEED_MAX}]")
        _require_enum(self.objective, TraceObjective, "objective")
        _require_unique_strings(self.character_keys, "character_keys")
        if not self.character_keys:
            raise TraceContractError("character_keys must not be empty")
        _require_sorted_unique_strings(
            self.required_capabilities,
            "required_capabilities",
        )
        if not self.required_capabilities:
            raise TraceContractError("required_capabilities must not be empty")

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "context_sha256": self.context_sha256,
            "source_config_sha256": self.source_config_sha256,
            "compiled_action_sha256": self.compiled_action_sha256,
            "target_sha256": self.target_sha256,
            "engine_artifact_sha256": self.engine_artifact_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "formula_version": self.formula_version,
            "formula_sha256": self.formula_sha256,
            "seed": self.seed,
            "objective": self.objective.value,
            "character_keys": list(self.character_keys),
            "required_capabilities": list(self.required_capabilities),
        }


@dataclass(frozen=True, slots=True)
class TraceExtractionReceipt:
    request_sha256: str
    trace_body_sha256: str
    topology_sha256: str
    engine_artifact_sha256: str
    engine_binding_sha256: str
    formula_version: str
    formula_sha256: str
    seed: int
    hit_count: int
    kind: str = TRACE_EXTRACTION_RECEIPT_KIND
    schema_version: int = TRACE_EXTRACTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_exact(
            self.schema_version,
            TRACE_EXTRACTION_RECEIPT_SCHEMA_VERSION,
            "extraction receipt schema",
        )
        _require_exact(self.kind, TRACE_EXTRACTION_RECEIPT_KIND, "extraction receipt kind")
        for field_name in (
            "request_sha256",
            "trace_body_sha256",
            "topology_sha256",
            "engine_artifact_sha256",
            "engine_binding_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_trimmed(self.formula_version, "formula_version")
        _require_sha256(self.formula_sha256, "formula_sha256")
        _require_int(self.seed, "seed")
        if self.seed <= 0 or self.seed > _SEED_MAX:
            raise TraceContractError(f"seed must be in [1, {_SEED_MAX}]")
        _require_nonnegative_int(self.hit_count, "hit_count")

    @property
    def receipt_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_sha256": self.request_sha256,
            "trace_body_sha256": self.trace_body_sha256,
            "topology_sha256": self.topology_sha256,
            "engine_artifact_sha256": self.engine_artifact_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "formula_version": self.formula_version,
            "formula_sha256": self.formula_sha256,
            "seed": self.seed,
            "hit_count": self.hit_count,
        }


@dataclass(frozen=True, slots=True)
class TraceDocument:
    request: TraceExtractionRequest
    receipt: TraceExtractionReceipt
    hits: tuple[TraceHitEvent, ...]
    topology: GuardTopologyReport
    kind: str = TRACE_DOCUMENT_KIND
    schema_version: int = TRACE_DOCUMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_exact(self.schema_version, TRACE_DOCUMENT_SCHEMA_VERSION, "trace schema")
        _require_exact(self.kind, TRACE_DOCUMENT_KIND, "trace kind")
        if not isinstance(self.request, TraceExtractionRequest):
            raise TraceContractError("request must be TraceExtractionRequest")
        if not isinstance(self.receipt, TraceExtractionReceipt):
            raise TraceContractError("receipt must be TraceExtractionReceipt")
        _require_tuple(self.hits, "hits")
        if not isinstance(self.topology, GuardTopologyReport):
            raise TraceContractError("topology must be GuardTopologyReport")
        event_ids = tuple(hit.event_id for hit in self.hits)
        if len(event_ids) != len(set(event_ids)):
            raise TraceContractError("event_id values must be unique")
        if tuple(hit.frame for hit in self.hits) != tuple(
            sorted(hit.frame for hit in self.hits)
        ):
            raise TraceContractError("hits must preserve non-decreasing engine frame order")
        for hit in self.hits:
            if hit.actor_index >= len(self.request.character_keys):
                raise TraceContractError("hit actor_index exceeds request character_keys")
            if self.request.character_keys[hit.actor_index] != hit.actor_key:
                raise TraceContractError(
                    "hit actor_key does not match request character index mapping"
                )
            if (
                hit.formula_inputs.formula_sha256 != self.request.formula_sha256
                and hit.formula_replay_status is not ReplayStatus.UNSUPPORTED
            ):
                raise TraceContractError(
                    "formula hash drift must be preserved as an UNSUPPORTED hit"
                )

        if self.topology.complete:
            known_event_ids = set(event_ids) | {
                event.event_id for event in self.topology.evidence_events
            }
            for hit in self.hits:
                for label, referenced_id in (
                    ("lineage.parent_event_id", hit.lineage.parent_event_id),
                    ("lineage.source_event_id", hit.lineage.source_event_id),
                ):
                    if referenced_id is not None and referenced_id not in known_event_ids:
                        raise TraceContractError(
                            f"{label} references unknown event {referenced_id!r}"
                        )
                for provenance in hit.provenance:
                    if (
                        provenance.provider_event_id is not None
                        and provenance.provider_event_id not in known_event_ids
                    ):
                        raise TraceContractError(
                            "provenance provider_event_id references unknown event "
                            f"{provenance.provider_event_id!r}"
                        )

        if self.receipt.request_sha256 != self.request.request_sha256:
            raise TraceContractError("receipt request_sha256 does not match request")
        if self.receipt.trace_body_sha256 != trace_body_sha256(self.hits, self.topology):
            raise TraceContractError("receipt trace_body_sha256 does not match trace body")
        if self.receipt.topology_sha256 != self.topology.topology_sha256:
            raise TraceContractError("receipt topology_sha256 does not match topology")
        if self.receipt.engine_artifact_sha256 != self.request.engine_artifact_sha256:
            raise TraceContractError("receipt engine_artifact_sha256 does not match request")
        if self.receipt.engine_binding_sha256 != self.request.engine_binding_sha256:
            raise TraceContractError("receipt engine_binding_sha256 does not match request")
        if self.receipt.formula_version != self.request.formula_version:
            raise TraceContractError("receipt formula_version does not match request")
        if self.receipt.formula_sha256 != self.request.formula_sha256:
            raise TraceContractError("receipt formula_sha256 does not match request")
        if self.receipt.seed != self.request.seed:
            raise TraceContractError("receipt seed does not match request")
        if self.receipt.hit_count != len(self.hits):
            raise TraceContractError("receipt hit_count does not match hits")

    @classmethod
    def build(
        cls,
        *,
        request: TraceExtractionRequest,
        hits: tuple[TraceHitEvent, ...],
        topology: GuardTopologyReport,
    ) -> "TraceDocument":
        _require_tuple(hits, "hits")
        receipt = TraceExtractionReceipt(
            request_sha256=request.request_sha256,
            trace_body_sha256=trace_body_sha256(hits, topology),
            topology_sha256=topology.topology_sha256,
            engine_artifact_sha256=request.engine_artifact_sha256,
            engine_binding_sha256=request.engine_binding_sha256,
            formula_version=request.formula_version,
            formula_sha256=request.formula_sha256,
            seed=request.seed,
            hit_count=len(hits),
        )
        return cls(request=request, receipt=receipt, hits=hits, topology=topology)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request": self.request.to_dict(),
            "receipt": self.receipt.to_dict(),
            "hits": [hit.to_dict() for hit in self.hits],
            "topology": self.topology.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReplayAssessment:
    trace_receipt_sha256: str
    candidate_sha256: str
    status: ReplayStatus
    triggered_guard_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    replayed_hit_count: int
    kind: str = TRACE_REPLAY_ASSESSMENT_KIND
    schema_version: int = TRACE_REPLAY_ASSESSMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_exact(
            self.schema_version,
            TRACE_REPLAY_ASSESSMENT_SCHEMA_VERSION,
            "replay assessment schema",
        )
        _require_exact(self.kind, TRACE_REPLAY_ASSESSMENT_KIND, "replay assessment kind")
        _require_sha256(self.trace_receipt_sha256, "trace_receipt_sha256")
        _require_sha256(self.candidate_sha256, "candidate_sha256")
        _require_enum(self.status, ReplayStatus, "status")
        _require_sorted_unique_strings(self.triggered_guard_ids, "triggered_guard_ids")
        _require_sorted_unique_strings(self.reason_codes, "reason_codes")
        _require_nonnegative_int(self.replayed_hit_count, "replayed_hit_count")
        if self.status is ReplayStatus.EXACT_IN_CELL:
            if self.triggered_guard_ids or self.reason_codes:
                raise TraceContractError(
                    "EXACT_IN_CELL assessment cannot carry guards or reasons"
                )
        elif not self.reason_codes:
            raise TraceContractError("non-exact assessment requires reason_codes")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "trace_receipt_sha256": self.trace_receipt_sha256,
            "candidate_sha256": self.candidate_sha256,
            "status": self.status.value,
            "triggered_guard_ids": list(self.triggered_guard_ids),
            "reason_codes": list(self.reason_codes),
            "replayed_hit_count": self.replayed_hit_count,
        }


def trace_body_sha256(
    hits: tuple[TraceHitEvent, ...],
    topology: GuardTopologyReport,
) -> str:
    _require_tuple(hits, "hits")
    if not isinstance(topology, GuardTopologyReport):
        raise TraceContractError("topology must be GuardTopologyReport")
    return canonical_sha256(
        {
            "hits": [hit.to_dict() for hit in hits],
            "topology": topology.to_dict(),
        }
    )


def validate_replay_assessment(
    document: TraceDocument,
    assessment: ReplayAssessment,
) -> None:
    """Validate a replay decision against its exact trace document identity."""

    if not isinstance(document, TraceDocument):
        raise TraceContractError("document must be TraceDocument")
    if not isinstance(assessment, ReplayAssessment):
        raise TraceContractError("assessment must be ReplayAssessment")
    if assessment.trace_receipt_sha256 != document.receipt.receipt_sha256:
        raise TraceContractError("assessment is bound to a different trace receipt")
    guard_ids = {guard.guard_id for guard in document.topology.guards}
    unknown_guards = set(assessment.triggered_guard_ids) - guard_ids
    if unknown_guards:
        raise TraceContractError(
            f"assessment references unknown guard ids: {sorted(unknown_guards)!r}"
        )
    if assessment.replayed_hit_count > len(document.hits):
        raise TraceContractError("replayed_hit_count exceeds trace hit count")
    if assessment.status is ReplayStatus.EXACT_IN_CELL:
        if not document.topology.complete:
            raise TraceContractError("incomplete topology cannot yield EXACT_IN_CELL")
        if assessment.replayed_hit_count != len(document.hits):
            raise TraceContractError("EXACT_IN_CELL must replay every trace hit")
        non_exact = tuple(
            hit.event_id
            for hit in document.hits
            if hit.formula_replay_status is not ReplayStatus.EXACT_IN_CELL
        )
        if non_exact:
            raise TraceContractError(
                f"non-replayable hits prevent EXACT_IN_CELL: {non_exact!r}"
            )


def _normal_uncapped_damage(inputs: DamageFormulaInputs, crit: bool) -> float:
    damage = inputs.base_damage.value * (1.0 + inputs.dmg_bonus.value)
    damage *= inputs.defense_multiplier.value
    damage *= inputs.resistance_multiplier.value
    if crit:
        damage *= 1.0 + inputs.crit_damage.value
    if inputs.amplifying:
        damage *= inputs.amp_multiplier.value * (
            1.0 + inputs.amp_reaction_bonus.value
        )
    damage *= inputs.group_multiplier.value
    damage *= inputs.elevation_multiplier.value
    return damage


def _engine_resistance_multiplier(resistance: float) -> float:
    """Mirror the audited engine's exact piecewise branch, including r == .75."""

    result = 1.0 - resistance / 2.0
    if 0.0 <= resistance < 0.75:
        result = 1.0 - resistance
    elif resistance > 0.75:
        result = 1.0 / (4.0 * resistance + 1.0)
    return result


def _snapshot_scaling_value(
    scaling_kind: ScalingKind,
    snapshot: dict[str, float],
) -> float:
    if scaling_kind is ScalingKind.ELEMENTAL_MASTERY:
        return snapshot["em"]
    prefix = {
        ScalingKind.ATTACK: "atk",
        ScalingKind.HP: "hp",
        ScalingKind.DEFENSE: "def",
    }[scaling_kind]
    required = (f"base_{prefix}", prefix, f"{prefix}%")
    missing = tuple(key for key in required if key not in snapshot)
    if missing:
        raise TraceContractError(
            f"full snapshot_stats is missing scaling keys {missing!r}"
        )
    return snapshot[required[0]] * (1.0 + snapshot[required[2]]) + snapshot[required[1]]


def _require_close(actual: float, expected: float, message: str) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_FORMULA_REL_TOLERANCE,
        abs_tol=_FORMULA_ABS_TOLERANCE,
    ):
        raise TraceContractError(f"{message}: {actual!r} != {expected!r}")


def _require_exact(actual: object, expected: object, label: str) -> None:
    if actual != expected or type(actual) is not type(expected):
        raise TraceContractError(f"unsupported {label}: {actual!r}; expected {expected!r}")


def _require_enum(value: object, enum_type: type[Enum], label: str) -> None:
    if not isinstance(value, enum_type):
        raise TraceContractError(f"{label} must be {enum_type.__name__}")


def _require_tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise TraceContractError(f"{label} must be an immutable tuple")


def _require_trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _require_optional_trimmed(value: object, label: str) -> None:
    if value is not None:
        _require_trimmed(value, label)


def _require_sha256(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TraceContractError(f"{label} must be a lowercase SHA-256 digest")


def _require_optional_sha256(value: object, label: str) -> None:
    if value is not None:
        _require_sha256(value, label)


def _require_optional_canonical_json(value: object, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise TraceContractError(f"{label} must be canonical JSON text or null")
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise TraceContractError(f"{label} is invalid JSON") from exc
    if canonical_json(decoded) != value:
        raise TraceContractError(f"{label} must use canonical JSON encoding")


def _require_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{label} must be an integer")


def _require_nonnegative_int(value: object, label: str) -> None:
    _require_int(value, label)
    assert isinstance(value, int)
    if value < 0:
        raise TraceContractError(f"{label} must be non-negative")


def _require_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TraceContractError(f"{label} must be a boolean")


def _require_finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be a number")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{label} must be finite")


def _require_sorted_unique_strings(values: object, label: str) -> None:
    _require_tuple(values, label)
    assert isinstance(values, tuple)
    for value in values:
        _require_trimmed(value, f"{label} item")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise TraceContractError(f"{label} must be sorted and unique")


def _require_unique_strings(values: object, label: str) -> None:
    _require_tuple(values, label)
    assert isinstance(values, tuple)
    for value in values:
        _require_trimmed(value, f"{label} item")
    if len(values) != len(set(values)):
        raise TraceContractError(f"{label} must be unique")


def _require_guard_scalar(value: object, label: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TraceContractError(f"{label} must be finite")
        return
    if isinstance(value, str):
        _require_trimmed(value, label)
        return
    raise TraceContractError(f"{label} must be bool, int, finite float, or string")


def _require_numeric_guard_scalar(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be a numeric guard scalar")
    _require_finite(value, label)


def _numeric_guard_value(value: object) -> float:
    _require_numeric_guard_scalar(value, "guard value")
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


def _guard_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    return left == right


__all__ = [
    "CallbackPhase",
    "DamageFormulaInputs",
    "DamageFormulaKind",
    "FormulaProvenance",
    "FormulaValue",
    "GuardKind",
    "GuardObservation",
    "GuardOperator",
    "GuardPredicate",
    "GuardTopologyReport",
    "ProvenanceSourceKind",
    "ReactionOperator",
    "ReplayAssessment",
    "ReplayStatus",
    "ScalingKind",
    "SnapshotStat",
    "TopologyChannel",
    "TopologyChannelDigest",
    "TopologyEvidenceEvent",
    "TOPOLOGY_COVERAGE_SENTINEL_KIND",
    "TraceContractError",
    "TraceDocument",
    "TraceDamageMode",
    "TraceExtractionReceipt",
    "TraceExtractionRequest",
    "TraceHitEvent",
    "TraceHitCompleteness",
    "TraceLineage",
    "TraceObjective",
    "ValueReadMode",
    "canonical_json",
    "canonical_sha256",
    "trace_body_sha256",
    "validate_replay_assessment",
]
