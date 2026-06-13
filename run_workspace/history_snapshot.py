"""Immutable History Snapshot Bundle v1 data contract and local file service.

This module defines the autonomous saved-run bundle shape only. It deliberately
does not build bundles from live AppShell/session state and does not wire Save,
History rows, export rendering, asset copying, account DB access, or cache reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping


HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION = 1
HISTORY_SNAPSHOT_BUNDLE_KIND = "gtt.history_snapshot_bundle"
HISTORY_SNAPSHOT_FILENAME = "snapshot.json"

HISTORY_RUN_TYPE_ABYSS = "abyss"
HISTORY_RUN_TYPE_DPS_DUMMY = "dps_dummy"
HISTORY_RUN_TYPES = (HISTORY_RUN_TYPE_ABYSS, HISTORY_RUN_TYPE_DPS_DUMMY)
HISTORY_SNAPSHOT_GROUP_ABYSS = "abyss"
HISTORY_SNAPSHOT_GROUP_DPS_DUMMY = "dps_dummy"
HISTORY_UNKNOWN_ABYSS_PERIOD = "unknown_period"


class HistorySnapshotBundleError(ValueError):
    """Raised when a History Snapshot Bundle cannot satisfy the v1 contract."""


class UnsupportedHistorySnapshotSchemaVersionError(HistorySnapshotBundleError):
    """Raised for bundle schema versions this code cannot read."""


class MalformedHistorySnapshotBundleError(HistorySnapshotBundleError):
    """Raised for malformed v1 bundle payloads."""


@dataclass(frozen=True, slots=True)
class HistorySnapshotBundleRecord:
    bundle: "HistorySnapshotBundle"
    path: Path
    relative_dir: Path


@dataclass(frozen=True, slots=True)
class HistorySnapshotBundleReadError:
    path: Path
    error_text: str


@dataclass(frozen=True, slots=True)
class HistorySnapshotBundleListing:
    records: tuple[HistorySnapshotBundleRecord, ...] = ()
    errors: tuple[HistorySnapshotBundleReadError, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryAssetRefSnapshot:
    path: str
    role: str = ""
    label: str = ""
    asset_id: str = ""
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    sha256: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "role": self.role,
            "label": self.label,
            "asset_id": self.asset_id,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAssetRefSnapshot":
        data = _mapping(payload)
        return cls(
            path=_text(data.get("path")),
            role=_text(data.get("role")),
            label=_text(data.get("label")),
            asset_id=_text(data.get("asset_id")),
            mime_type=_text(data.get("mime_type")),
            width=_optional_int(data.get("width")),
            height=_optional_int(data.get("height")),
            sha256=_text(data.get("sha256")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryPreviewRefSnapshot:
    path: str
    preview_type: str = ""
    label: str = ""
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    sha256: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "preview_type": self.preview_type,
            "label": self.label,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryPreviewRefSnapshot":
        data = _mapping(payload)
        return cls(
            path=_text(data.get("path")),
            preview_type=_text(data.get("preview_type")),
            label=_text(data.get("label")),
            mime_type=_text(data.get("mime_type")),
            width=_optional_int(data.get("width")),
            height=_optional_int(data.get("height")),
            sha256=_text(data.get("sha256")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryStatRowSnapshot:
    label: str
    value: str
    key: str = ""
    icon_label: str = ""
    unit: str = ""
    source: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "key": self.key,
            "icon_label": self.icon_label,
            "unit": self.unit,
            "source": self.source,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryStatRowSnapshot":
        data = _mapping(payload)
        return cls(
            label=_text(data.get("label")),
            value=_text(data.get("value")),
            key=_text(data.get("key")),
            icon_label=_text(data.get("icon_label")),
            unit=_text(data.get("unit")),
            source=_text(data.get("source")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistorySetBonusSnapshot:
    set_uid: str = ""
    set_name: str = ""
    piece_count: int = 0
    icon_ref: str = ""
    effects: tuple[str, ...] = ()
    source: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "piece_count": self.piece_count,
            "icon_ref": self.icon_ref,
            "effects": list(self.effects),
            "source": self.source,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistorySetBonusSnapshot":
        data = _mapping(payload)
        return cls(
            set_uid=_text(data.get("set_uid")),
            set_name=_text(data.get("set_name")),
            piece_count=_optional_int(data.get("piece_count")) or 0,
            icon_ref=_text(data.get("icon_ref")),
            effects=_text_tuple(data.get("effects")),
            source=_text(data.get("source")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryBonusSourceSnapshot:
    source_kind: str
    label: str
    source_id: str = ""
    icon_ref: str = ""
    effects: tuple[str, ...] = ()
    applied: bool = True
    not_applied_reason: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "label": self.label,
            "icon_ref": self.icon_ref,
            "effects": list(self.effects),
            "applied": self.applied,
            "not_applied_reason": self.not_applied_reason,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryBonusSourceSnapshot":
        data = _mapping(payload)
        return cls(
            source_kind=_text(data.get("source_kind")),
            source_id=_text(data.get("source_id")),
            label=_text(data.get("label")),
            icon_ref=_text(data.get("icon_ref")),
            effects=_text_tuple(data.get("effects")),
            applied=bool(data.get("applied", True)),
            not_applied_reason=_text(data.get("not_applied_reason")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryCharacterSnapshot:
    name: str
    character_id: str = ""
    level: int | None = None
    element: str = ""
    rarity: int | None = None
    constellation: int | None = None
    portrait_ref: str = ""
    side_icon_ref: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "level": self.level,
            "element": self.element,
            "rarity": self.rarity,
            "constellation": self.constellation,
            "portrait_ref": self.portrait_ref,
            "side_icon_ref": self.side_icon_ref,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryCharacterSnapshot":
        data = _mapping(payload)
        return cls(
            character_id=_text(data.get("character_id")),
            name=_text(data.get("name")),
            level=_optional_int(data.get("level")),
            element=_text(data.get("element")),
            rarity=_optional_int(data.get("rarity")),
            constellation=_optional_int(data.get("constellation")),
            portrait_ref=_text(data.get("portrait_ref")),
            side_icon_ref=_text(data.get("side_icon_ref")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryWeaponSnapshot:
    name: str
    weapon_id: str = ""
    level: int | None = None
    promote_level: int | None = None
    rarity: int | None = None
    refinement: int | None = None
    weapon_type: str = ""
    weapon_fingerprint: str = ""
    icon_ref: str = ""
    passive_name: str = ""
    passive_effects: tuple[str, ...] = ()
    stat_rows: tuple[HistoryStatRowSnapshot, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "rarity": self.rarity,
            "refinement": self.refinement,
            "weapon_type": self.weapon_type,
            "weapon_fingerprint": self.weapon_fingerprint,
            "icon_ref": self.icon_ref,
            "passive_name": self.passive_name,
            "passive_effects": list(self.passive_effects),
            "stat_rows": [row.to_dict() for row in self.stat_rows],
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryWeaponSnapshot":
        data = _mapping(payload)
        return cls(
            weapon_id=_text(data.get("weapon_id")),
            name=_text(data.get("name")),
            level=_optional_int(data.get("level")),
            promote_level=_optional_int(data.get("promote_level")),
            rarity=_optional_int(data.get("rarity")),
            refinement=_optional_int(data.get("refinement")),
            weapon_type=_text(data.get("weapon_type")),
            weapon_fingerprint=_text(data.get("weapon_fingerprint")),
            icon_ref=_text(data.get("icon_ref")),
            passive_name=_text(data.get("passive_name")),
            passive_effects=_text_tuple(data.get("passive_effects")),
            stat_rows=_stat_rows(data.get("stat_rows")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryArtifactSlotSnapshot:
    position: int
    artifact_id: str = ""
    set_uid: str = ""
    set_name: str = ""
    piece_name: str = ""
    rarity: int | None = None
    level: int | None = None
    main_stat: HistoryStatRowSnapshot | None = None
    substats: tuple[HistoryStatRowSnapshot, ...] = ()
    icon_ref: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "artifact_id": self.artifact_id,
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "piece_name": self.piece_name,
            "rarity": self.rarity,
            "level": self.level,
            "main_stat": None if self.main_stat is None else self.main_stat.to_dict(),
            "substats": [row.to_dict() for row in self.substats],
            "icon_ref": self.icon_ref,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryArtifactSlotSnapshot":
        data = _mapping(payload)
        main_stat = data.get("main_stat")
        return cls(
            position=_optional_int(data.get("position")) or 0,
            artifact_id=_text(data.get("artifact_id")),
            set_uid=_text(data.get("set_uid")),
            set_name=_text(data.get("set_name")),
            piece_name=_text(data.get("piece_name")),
            rarity=_optional_int(data.get("rarity")),
            level=_optional_int(data.get("level")),
            main_stat=(
                HistoryStatRowSnapshot.from_dict(main_stat)
                if isinstance(main_stat, Mapping)
                else None
            ),
            substats=_stat_rows(data.get("substats")),
            icon_ref=_text(data.get("icon_ref")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryArtifactBuildSnapshot:
    source: str = ""
    build_name: str = ""
    build_id: str = ""
    artifact_slots: tuple[HistoryArtifactSlotSnapshot, ...] = ()
    active_set_bonuses: tuple[HistorySetBonusSnapshot, ...] = ()
    stat_rows: tuple[HistoryStatRowSnapshot, ...] = ()
    crit_value: float | None = None
    proc_count: int | None = None
    missing_positions: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "build_id": self.build_id,
            "build_name": self.build_name,
            "artifact_slots": [slot.to_dict() for slot in self.artifact_slots],
            "active_set_bonuses": [
                bonus.to_dict() for bonus in self.active_set_bonuses
            ],
            "stat_rows": [row.to_dict() for row in self.stat_rows],
            "crit_value": self.crit_value,
            "proc_count": self.proc_count,
            "missing_positions": list(self.missing_positions),
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryArtifactBuildSnapshot":
        data = _mapping(payload)
        return cls(
            source=_text(data.get("source")),
            build_id=_text(data.get("build_id")),
            build_name=_text(data.get("build_name")),
            artifact_slots=tuple(
                HistoryArtifactSlotSnapshot.from_dict(item)
                for item in _mapping_list(data.get("artifact_slots"))
            ),
            active_set_bonuses=tuple(
                HistorySetBonusSnapshot.from_dict(item)
                for item in _mapping_list(data.get("active_set_bonuses"))
            ),
            stat_rows=_stat_rows(data.get("stat_rows")),
            crit_value=_optional_float(data.get("crit_value")),
            proc_count=_optional_int(data.get("proc_count")),
            missing_positions=_int_tuple(data.get("missing_positions")),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryTeamSlotSnapshot:
    slot_index: int
    character: HistoryCharacterSnapshot | None = None
    weapon: HistoryWeaponSnapshot | None = None
    artifact_build: HistoryArtifactBuildSnapshot | None = None
    stat_rows: tuple[HistoryStatRowSnapshot, ...] = ()
    bonus_sources: tuple[HistoryBonusSourceSnapshot, ...] = ()
    asset_refs: tuple[HistoryAssetRefSnapshot, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "character": None if self.character is None else self.character.to_dict(),
            "weapon": None if self.weapon is None else self.weapon.to_dict(),
            "artifact_build": (
                None
                if self.artifact_build is None
                else self.artifact_build.to_dict()
            ),
            "stat_rows": [row.to_dict() for row in self.stat_rows],
            "bonus_sources": [item.to_dict() for item in self.bonus_sources],
            "asset_refs": [item.to_dict() for item in self.asset_refs],
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryTeamSlotSnapshot":
        data = _mapping(payload)
        character = data.get("character")
        weapon = data.get("weapon")
        artifact_build = data.get("artifact_build")
        return cls(
            slot_index=_optional_int(data.get("slot_index")) or 0,
            character=(
                HistoryCharacterSnapshot.from_dict(character)
                if isinstance(character, Mapping)
                else None
            ),
            weapon=(
                HistoryWeaponSnapshot.from_dict(weapon)
                if isinstance(weapon, Mapping)
                else None
            ),
            artifact_build=(
                HistoryArtifactBuildSnapshot.from_dict(artifact_build)
                if isinstance(artifact_build, Mapping)
                else None
            ),
            stat_rows=_stat_rows(data.get("stat_rows")),
            bonus_sources=tuple(
                HistoryBonusSourceSnapshot.from_dict(item)
                for item in _mapping_list(data.get("bonus_sources"))
            ),
            asset_refs=_asset_refs(data.get("asset_refs")),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryTeamSnapshot:
    team_index: int
    slots: tuple[HistoryTeamSlotSnapshot, ...]
    label: str = ""
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_index": self.team_index,
            "label": self.label,
            "slots": [slot.to_dict() for slot in self.slots],
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryTeamSnapshot":
        data = _mapping(payload)
        return cls(
            team_index=_optional_int(data.get("team_index")) or 0,
            label=_text(data.get("label")),
            slots=tuple(
                HistoryTeamSlotSnapshot.from_dict(item)
                for item in _mapping_list(data.get("slots"))
            ),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryAbyssTimerSnapshot:
    team1_left_seconds: int
    team2_left_seconds: int
    start_seconds: int = 600
    normalized_team1_left_seconds: int | None = None
    normalized_team2_left_seconds: int | None = None
    team1_elapsed_seconds: int | None = None
    team2_elapsed_seconds: int | None = None
    total_elapsed_seconds: int | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "team1_left_seconds": self.team1_left_seconds,
            "team2_left_seconds": self.team2_left_seconds,
            "start_seconds": self.start_seconds,
            "normalized_team1_left_seconds": self.normalized_team1_left_seconds,
            "normalized_team2_left_seconds": self.normalized_team2_left_seconds,
            "team1_elapsed_seconds": self.team1_elapsed_seconds,
            "team2_elapsed_seconds": self.team2_elapsed_seconds,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAbyssTimerSnapshot":
        data = _mapping(payload)
        return cls(
            team1_left_seconds=_optional_int(data.get("team1_left_seconds")) or 0,
            team2_left_seconds=_optional_int(data.get("team2_left_seconds")) or 0,
            start_seconds=_optional_int(data.get("start_seconds")) or 0,
            normalized_team1_left_seconds=_optional_int(
                data.get("normalized_team1_left_seconds")
            ),
            normalized_team2_left_seconds=_optional_int(
                data.get("normalized_team2_left_seconds")
            ),
            team1_elapsed_seconds=_optional_int(data.get("team1_elapsed_seconds")),
            team2_elapsed_seconds=_optional_int(data.get("team2_elapsed_seconds")),
            total_elapsed_seconds=_optional_int(data.get("total_elapsed_seconds")),
            warnings=_text_tuple(data.get("warnings")),
        )


@dataclass(frozen=True, slots=True)
class HistoryAbyssSideResultSnapshot:
    side: int
    team_index: int
    elapsed_seconds: int | None = None
    total_hp: int | None = None
    factual_dps: int | None = None
    hp_source: str = ""
    target_mode: str = ""
    sim_result_ref: str = ""
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "team_index": self.team_index,
            "elapsed_seconds": self.elapsed_seconds,
            "total_hp": self.total_hp,
            "factual_dps": self.factual_dps,
            "hp_source": self.hp_source,
            "target_mode": self.target_mode,
            "sim_result_ref": self.sim_result_ref,
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAbyssSideResultSnapshot":
        data = _mapping(payload)
        return cls(
            side=_optional_int(data.get("side")) or 0,
            team_index=_optional_int(data.get("team_index")) or 0,
            elapsed_seconds=_optional_int(data.get("elapsed_seconds")),
            total_hp=_optional_int(data.get("total_hp")),
            factual_dps=_optional_int(data.get("factual_dps")),
            hp_source=_text(data.get("hp_source")),
            target_mode=_text(data.get("target_mode")),
            sim_result_ref=_text(data.get("sim_result_ref")),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryAbyssChamberSnapshot:
    chamber_index: int
    chamber_label: str = ""
    timer: HistoryAbyssTimerSnapshot | None = None
    side_results: tuple[HistoryAbyssSideResultSnapshot, ...] = ()
    enemies: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chamber_index": self.chamber_index,
            "chamber_label": self.chamber_label,
            "timer": None if self.timer is None else self.timer.to_dict(),
            "side_results": [item.to_dict() for item in self.side_results],
            "enemies": [dict(sorted(item.items())) for item in self.enemies],
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAbyssChamberSnapshot":
        data = _mapping(payload)
        timer = data.get("timer")
        return cls(
            chamber_index=_optional_int(data.get("chamber_index")) or 0,
            chamber_label=_text(data.get("chamber_label")),
            timer=(
                HistoryAbyssTimerSnapshot.from_dict(timer)
                if isinstance(timer, Mapping)
                else None
            ),
            side_results=tuple(
                HistoryAbyssSideResultSnapshot.from_dict(item)
                for item in _mapping_list(data.get("side_results"))
            ),
            enemies=tuple(dict(item) for item in _mapping_list(data.get("enemies"))),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryAbyssScenarioSnapshot:
    chambers: tuple[HistoryAbyssChamberSnapshot, ...] = ()
    season_label: str = ""
    period_start: str = ""
    period_end: str = ""
    floor: int | None = None
    target_mode: str = ""
    total_elapsed_seconds: int | None = None
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "season_label": self.season_label,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "floor": self.floor,
            "target_mode": self.target_mode,
            "chambers": [chamber.to_dict() for chamber in self.chambers],
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAbyssScenarioSnapshot":
        data = _mapping(payload)
        return cls(
            season_label=_text(data.get("season_label")),
            period_start=_text(data.get("period_start")),
            period_end=_text(data.get("period_end")),
            floor=_optional_int(data.get("floor")),
            target_mode=_text(data.get("target_mode")),
            chambers=tuple(
                HistoryAbyssChamberSnapshot.from_dict(item)
                for item in _mapping_list(data.get("chambers"))
            ),
            total_elapsed_seconds=_optional_int(data.get("total_elapsed_seconds")),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryDpsDummyScenarioSnapshot:
    target_label: str = ""
    target_id: str = ""
    target_hp: int | None = None
    target_level: int | None = None
    resistances: Mapping[str, Any] = field(default_factory=dict)
    duration_seconds: float | None = None
    factual_damage: float | None = None
    factual_dps: float | None = None
    result_status: str = ""
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_label": self.target_label,
            "target_hp": self.target_hp,
            "target_level": self.target_level,
            "resistances": dict(sorted(self.resistances.items())),
            "duration_seconds": self.duration_seconds,
            "factual_damage": self.factual_damage,
            "factual_dps": self.factual_dps,
            "result_status": self.result_status,
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryDpsDummyScenarioSnapshot":
        data = _mapping(payload)
        return cls(
            target_id=_text(data.get("target_id")),
            target_label=_text(data.get("target_label")),
            target_hp=_optional_int(data.get("target_hp")),
            target_level=_optional_int(data.get("target_level")),
            resistances=dict(_mapping(data.get("resistances"))),
            duration_seconds=_optional_float(data.get("duration_seconds")),
            factual_damage=_optional_float(data.get("factual_damage")),
            factual_dps=_optional_float(data.get("factual_dps")),
            result_status=_text(data.get("result_status")),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryScenarioSnapshot:
    run_type: str
    abyss: HistoryAbyssScenarioSnapshot | None = None
    dps_dummy: HistoryDpsDummyScenarioSnapshot | None = None
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalize_history_run_type(self.run_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_type": self.run_type,
            "abyss": None if self.abyss is None else self.abyss.to_dict(),
            "dps_dummy": None if self.dps_dummy is None else self.dps_dummy.to_dict(),
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryScenarioSnapshot":
        data = _mapping(payload)
        abyss = data.get("abyss")
        dps_dummy = data.get("dps_dummy")
        return cls(
            run_type=normalize_history_run_type(data.get("run_type")),
            abyss=(
                HistoryAbyssScenarioSnapshot.from_dict(abyss)
                if isinstance(abyss, Mapping)
                else None
            ),
            dps_dummy=(
                HistoryDpsDummyScenarioSnapshot.from_dict(dps_dummy)
                if isinstance(dps_dummy, Mapping)
                else None
            ),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryResultSummarySnapshot:
    result_type: str
    label: str = ""
    team_index: int | None = None
    slot_index: int | None = None
    chamber_index: int | None = None
    side: int | None = None
    dps: float | None = None
    damage: float | None = None
    elapsed_seconds: float | None = None
    source: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_type": self.result_type,
            "label": self.label,
            "team_index": self.team_index,
            "slot_index": self.slot_index,
            "chamber_index": self.chamber_index,
            "side": self.side,
            "dps": self.dps,
            "damage": self.damage,
            "elapsed_seconds": self.elapsed_seconds,
            "source": self.source,
            "payload": dict(sorted(self.payload.items())),
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryResultSummarySnapshot":
        data = _mapping(payload)
        return cls(
            result_type=_text(data.get("result_type")),
            label=_text(data.get("label")),
            team_index=_optional_int(data.get("team_index")),
            slot_index=_optional_int(data.get("slot_index")),
            chamber_index=_optional_int(data.get("chamber_index")),
            side=_optional_int(data.get("side")),
            dps=_optional_float(data.get("dps")),
            damage=_optional_float(data.get("damage")),
            elapsed_seconds=_optional_float(data.get("elapsed_seconds")),
            source=_text(data.get("source")),
            payload=dict(_mapping(data.get("payload"))),
            warnings=_text_tuple(data.get("warnings")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistoryAccountProfileSnapshot:
    account_uid: str = ""
    nickname: str = ""
    server: str = ""
    profile_name: str = ""
    source: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_uid": self.account_uid,
            "nickname": self.nickname,
            "server": self.server,
            "profile_name": self.profile_name,
            "source": self.source,
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryAccountProfileSnapshot":
        data = _mapping(payload)
        return cls(
            account_uid=_text(data.get("account_uid")),
            nickname=_text(data.get("nickname")),
            server=_text(data.get("server")),
            profile_name=_text(data.get("profile_name")),
            source=_text(data.get("source")),
            provenance=dict(_mapping(data.get("provenance"))),
        )


@dataclass(frozen=True, slots=True)
class HistorySnapshotBundle:
    bundle_id: str
    created_at: str
    run_type: str
    source: str
    content_language: str
    teams: tuple[HistoryTeamSnapshot, ...] = ()
    scenario: HistoryScenarioSnapshot | None = None
    result_summaries: tuple[HistoryResultSummarySnapshot, ...] = ()
    account: HistoryAccountProfileSnapshot | None = None
    asset_refs: tuple[HistoryAssetRefSnapshot, ...] = ()
    preview_refs: tuple[HistoryPreviewRefSnapshot, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION
    kind: str = HISTORY_SNAPSHOT_BUNDLE_KIND

    def __post_init__(self) -> None:
        require_supported_history_snapshot_schema_version(self.schema_version)
        normalize_history_run_type(self.run_type)
        if not self.bundle_id:
            raise MalformedHistorySnapshotBundleError(
                "Malformed history snapshot bundle: bundle_id is required."
            )
        if self.kind != HISTORY_SNAPSHOT_BUNDLE_KIND:
            raise MalformedHistorySnapshotBundleError(
                f"Malformed history snapshot kind {self.kind!r}; "
                f"expected {HISTORY_SNAPSHOT_BUNDLE_KIND!r}."
            )
        if self.scenario is not None and self.scenario.run_type != self.run_type:
            raise MalformedHistorySnapshotBundleError(
                "Malformed history snapshot bundle: scenario.run_type must match run_type."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "run_type": self.run_type,
            "source": self.source,
            "content_language": self.content_language,
            "account": None if self.account is None else self.account.to_dict(),
            "teams": [team.to_dict() for team in self.teams],
            "scenario": None if self.scenario is None else self.scenario.to_dict(),
            "result_summaries": [
                summary.to_dict() for summary in self.result_summaries
            ],
            "asset_refs": [item.to_dict() for item in self.asset_refs],
            "preview_refs": [item.to_dict() for item in self.preview_refs],
            "warnings": list(self.warnings),
            "provenance": dict(sorted(self.provenance.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistorySnapshotBundle":
        if not isinstance(payload, Mapping):
            raise MalformedHistorySnapshotBundleError(
                "Malformed history snapshot bundle: root must be an object."
            )
        require_supported_history_snapshot_schema_version(payload.get("schema_version"))
        run_type = normalize_history_run_type(payload.get("run_type"))
        kind = _text(payload.get("kind") or HISTORY_SNAPSHOT_BUNDLE_KIND)
        account = payload.get("account")
        scenario = payload.get("scenario")
        return cls(
            schema_version=HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION,
            kind=kind,
            bundle_id=_required_text(payload.get("bundle_id"), "bundle_id"),
            created_at=_required_text(payload.get("created_at"), "created_at"),
            run_type=run_type,
            source=_required_text(payload.get("source"), "source"),
            content_language=_required_text(
                payload.get("content_language"),
                "content_language",
            ),
            account=(
                HistoryAccountProfileSnapshot.from_dict(account)
                if isinstance(account, Mapping)
                else None
            ),
            teams=tuple(
                HistoryTeamSnapshot.from_dict(item)
                for item in _mapping_list(payload.get("teams"))
            ),
            scenario=(
                HistoryScenarioSnapshot.from_dict(scenario)
                if isinstance(scenario, Mapping)
                else None
            ),
            result_summaries=tuple(
                HistoryResultSummarySnapshot.from_dict(item)
                for item in _mapping_list(payload.get("result_summaries"))
            ),
            asset_refs=_asset_refs(payload.get("asset_refs")),
            preview_refs=tuple(
                HistoryPreviewRefSnapshot.from_dict(item)
                for item in _mapping_list(payload.get("preview_refs"))
            ),
            warnings=_text_tuple(payload.get("warnings")),
            provenance=dict(_mapping(payload.get("provenance"))),
        )


class HistorySnapshotBundleStore:
    """Read/write History Snapshot Bundles under a caller-provided root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def bundle_dir(self, bundle_id: str) -> Path:
        return self.root / _safe_bundle_id(bundle_id)

    def snapshot_path(self, bundle_id: str) -> Path:
        return self.bundle_dir(bundle_id) / HISTORY_SNAPSHOT_FILENAME

    def bundle_relative_dir_for(self, bundle: HistorySnapshotBundle) -> Path:
        bundle_id = _safe_bundle_id(bundle.bundle_id)
        if normalize_history_run_type(bundle.run_type) == HISTORY_RUN_TYPE_ABYSS:
            return (
                Path(HISTORY_SNAPSHOT_GROUP_ABYSS)
                / _abyss_period_path_segment(bundle)
                / bundle_id
            )
        return Path(HISTORY_SNAPSHOT_GROUP_DPS_DUMMY) / bundle_id

    def grouped_bundle_dir(self, bundle: HistorySnapshotBundle) -> Path:
        return self.root / self.bundle_relative_dir_for(bundle)

    def grouped_snapshot_path(self, bundle: HistorySnapshotBundle) -> Path:
        return self.grouped_bundle_dir(bundle) / HISTORY_SNAPSHOT_FILENAME

    def write_bundle(self, bundle: HistorySnapshotBundle) -> Path:
        bundle_id = _safe_bundle_id(bundle.bundle_id)
        bundle_dir = self.bundle_dir(bundle_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        path = bundle_dir / HISTORY_SNAPSHOT_FILENAME
        _write_json_atomic(path, bundle.to_dict())
        return path

    def write_bundle_grouped(self, bundle: HistorySnapshotBundle) -> Path:
        bundle_dir = self.grouped_bundle_dir(bundle)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        path = bundle_dir / HISTORY_SNAPSHOT_FILENAME
        _write_json_atomic(path, bundle.to_dict())
        return path

    def read_bundle(self, bundle_id: str) -> HistorySnapshotBundle:
        safe_bundle_id = _safe_bundle_id(bundle_id)
        path = self.snapshot_path(safe_bundle_id)
        if not path.exists():
            path = self._find_snapshot_path_by_bundle_id(safe_bundle_id)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HistorySnapshotBundleError(
                f"History snapshot bundle not found or unreadable: {path}"
            ) from exc
        return history_snapshot_bundle_from_json_text(text)

    def iter_bundle_paths(self) -> tuple[Path, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(
                path
                for path in self.root.rglob(HISTORY_SNAPSHOT_FILENAME)
                if path.is_file()
            )
        )

    def list_bundle_records(self) -> HistorySnapshotBundleListing:
        records: list[HistorySnapshotBundleRecord] = []
        errors: list[HistorySnapshotBundleReadError] = []
        for path in self.iter_bundle_paths():
            try:
                bundle = history_snapshot_bundle_from_json_text(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, HistorySnapshotBundleError) as exc:
                errors.append(
                    HistorySnapshotBundleReadError(
                        path=path,
                        error_text=str(exc) or exc.__class__.__name__,
                    )
                )
                continue
            records.append(
                HistorySnapshotBundleRecord(
                    bundle=bundle,
                    path=path,
                    relative_dir=_relative_parent(path, self.root),
                )
            )
        return HistorySnapshotBundleListing(
            records=tuple(records),
            errors=tuple(errors),
        )

    def list_bundles(self) -> HistorySnapshotBundleListing:
        return self.list_bundle_records()

    def _find_snapshot_path_by_bundle_id(self, bundle_id: str) -> Path:
        for path in self.iter_bundle_paths():
            if path.parent.name == bundle_id:
                return path
        return self.snapshot_path(bundle_id)


def normalize_history_run_type(value: Any) -> str:
    run_type = _text(value)
    if run_type not in HISTORY_RUN_TYPES:
        expected = ", ".join(HISTORY_RUN_TYPES)
        raise MalformedHistorySnapshotBundleError(
            f"Malformed history snapshot run type {run_type!r}; expected one of: {expected}."
        )
    return run_type


def require_supported_history_snapshot_schema_version(value: Any) -> None:
    schema_version = _optional_int(value)
    if schema_version != HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION:
        raise UnsupportedHistorySnapshotSchemaVersionError(
            "Unsupported history snapshot schema version: "
            f"{schema_version!r}; expected {HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION}."
        )


def history_snapshot_bundle_from_json_text(text: str) -> HistorySnapshotBundle:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedHistorySnapshotBundleError(
            f"Invalid history snapshot JSON: {exc.msg}."
        ) from exc
    return HistorySnapshotBundle.from_dict(payload)


def history_snapshot_bundle_to_json_text(
    bundle: HistorySnapshotBundle,
    *,
    indent: int = 2,
) -> str:
    return json.dumps(
        bundle.to_dict(),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    ) + "\n"


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _abyss_period_path_segment(bundle: HistorySnapshotBundle) -> str:
    scenario = bundle.scenario
    abyss = None if scenario is None else scenario.abyss
    period_start = "" if abyss is None else abyss.period_start
    iso_segment = _iso_date_segment(period_start)
    if iso_segment:
        return iso_segment
    return _safe_history_path_segment(
        period_start,
        fallback=HISTORY_UNKNOWN_ABYSS_PERIOD,
    )


def _iso_date_segment(value: Any) -> str:
    text = _text(value)
    if len(text) < 10:
        return ""
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return ""


def _safe_history_path_segment(value: Any, *, fallback: str) -> str:
    text = _text(value)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    chars: list[str] = []
    previous_was_separator = False
    for char in text:
        if char in allowed:
            chars.append(char)
            previous_was_separator = False
        elif not previous_was_separator:
            chars.append("_")
            previous_was_separator = True
    segment = "".join(chars).strip("._-")
    if not segment or segment in {".", ".."}:
        return fallback
    return segment


def _relative_parent(path: Path, root: Path) -> Path:
    try:
        return path.parent.relative_to(root)
    except ValueError:
        return path.parent


def _safe_bundle_id(bundle_id: Any) -> str:
    text = _text(bundle_id)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if (
        not text
        or text in {".", ".."}
        or any(char not in allowed for char in text)
    ):
        raise MalformedHistorySnapshotBundleError(
            f"Malformed history snapshot bundle_id {text!r}; "
            "expected one safe path segment."
        )
    return text


def _required_text(value: Any, path: str) -> str:
    text = _text(value)
    if not text:
        raise MalformedHistorySnapshotBundleError(
            f"Malformed history snapshot bundle: {path} is required."
        )
    return text


def _asset_refs(value: Any) -> tuple[HistoryAssetRefSnapshot, ...]:
    return tuple(
        HistoryAssetRefSnapshot.from_dict(item)
        for item in _mapping_list(value)
    )


def _stat_rows(value: Any) -> tuple[HistoryStatRowSnapshot, ...]:
    return tuple(
        HistoryStatRowSnapshot.from_dict(item)
        for item in _mapping_list(value)
    )


def _mapping_list(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_text(item) for item in value if _text(item))


def _int_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    result: list[int] = []
    for item in value:
        number = _optional_int(item)
        if number is not None:
            result.append(number)
    return tuple(result)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "HISTORY_RUN_TYPE_ABYSS",
    "HISTORY_RUN_TYPE_DPS_DUMMY",
    "HISTORY_RUN_TYPES",
    "HISTORY_SNAPSHOT_GROUP_ABYSS",
    "HISTORY_SNAPSHOT_GROUP_DPS_DUMMY",
    "HISTORY_SNAPSHOT_BUNDLE_KIND",
    "HISTORY_SNAPSHOT_BUNDLE_SCHEMA_VERSION",
    "HISTORY_SNAPSHOT_FILENAME",
    "HISTORY_UNKNOWN_ABYSS_PERIOD",
    "HistoryAbyssChamberSnapshot",
    "HistoryAbyssScenarioSnapshot",
    "HistoryAbyssSideResultSnapshot",
    "HistoryAbyssTimerSnapshot",
    "HistoryAccountProfileSnapshot",
    "HistoryArtifactBuildSnapshot",
    "HistoryArtifactSlotSnapshot",
    "HistoryAssetRefSnapshot",
    "HistoryBonusSourceSnapshot",
    "HistoryCharacterSnapshot",
    "HistoryDpsDummyScenarioSnapshot",
    "HistoryPreviewRefSnapshot",
    "HistoryResultSummarySnapshot",
    "HistoryScenarioSnapshot",
    "HistorySetBonusSnapshot",
    "HistorySnapshotBundle",
    "HistorySnapshotBundleError",
    "HistorySnapshotBundleListing",
    "HistorySnapshotBundleReadError",
    "HistorySnapshotBundleRecord",
    "HistorySnapshotBundleStore",
    "HistoryStatRowSnapshot",
    "HistoryTeamSlotSnapshot",
    "HistoryTeamSnapshot",
    "HistoryWeaponSnapshot",
    "MalformedHistorySnapshotBundleError",
    "UnsupportedHistorySnapshotSchemaVersionError",
    "history_snapshot_bundle_from_json_text",
    "history_snapshot_bundle_to_json_text",
    "normalize_history_run_type",
    "require_supported_history_snapshot_schema_version",
]
