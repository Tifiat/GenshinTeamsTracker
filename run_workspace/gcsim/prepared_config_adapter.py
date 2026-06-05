"""Adapter boundary for explicit prepared GCSIM character config inputs.

There is not yet a single production owner for selected team + current weapon +
current artifact build + production GCSIM mappings. This module therefore
accepts explicit backend/dev dictionaries or JSON fixtures and converts them
into `GcsimCharacterConfigInput` without reading widgets, SQLite, network, or
right-panel final stat totals. Future account/team adapters should replace the
fixture shape once that source owner is confirmed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hoyolab_export.artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    ArtifactStatTotalSnapshot,
    build_artifact_build_snapshot,
)
from run_workspace.gcsim.config_blocks import (
    GcsimArtifactConfigInput,
    GcsimArtifactSetConfigInput,
    GcsimCharacterConfigBlock,
    GcsimCharacterConfigInput,
    GcsimConfigBlockIssue,
    GcsimWeaponConfigInput,
    build_gcsim_character_config_block,
)
from run_workspace.gcsim.config_readiness import (
    GcsimMappingRef,
    GcsimTalentInput,
)


PREPARED_CONFIG_READY = "ready"
PREPARED_CONFIG_NOT_READY = "not_ready"
PREPARED_CONFIG_INVALID_INPUT = "invalid_input"

WARNING_PREPARED_FIXTURE_BOUNDARY = "prepared_fixture_adapter_boundary"
WARNING_NO_UI_OR_STORAGE_ACCESS = "no_ui_or_storage_access"
WARNING_FINAL_STATS_IGNORED = "final_or_right_panel_stats_ignored"

_FINAL_STATS_KEYS = {
    "account_stat_sheet",
    "account_stat_totals",
    "character_stats",
    "display_stats",
    "final_stats",
    "right_panel_stats",
    "right_panel_total",
    "stat_sheet",
}


@dataclass(frozen=True, slots=True)
class PreparedGcsimCharacterConfigResult:
    status: str
    ready: bool
    character_input: GcsimCharacterConfigInput | None = None
    block: GcsimCharacterConfigBlock | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigBlockIssue, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "character_input": (
                self.character_input.to_dict()
                if self.character_input is not None
                else None
            ),
            "block": self.block.to_dict() if self.block is not None else None,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


@dataclass(frozen=True, slots=True)
class PreparedGcsimTeamConfigResult:
    status: str
    ready: bool
    characters: tuple[PreparedGcsimCharacterConfigResult, ...] = ()
    warnings: tuple[str, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    @property
    def ready_blocks(self) -> tuple[GcsimCharacterConfigBlock, ...]:
        return tuple(
            result.block
            for result in self.characters
            if result.ready and result.block is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "characters": [item.to_dict() for item in self.characters],
            "warnings": list(self.warnings),
            "source_notes": dict(self.source_notes),
        }


def adapt_prepared_character_config_input(
    payload: Mapping[str, Any],
) -> PreparedGcsimCharacterConfigResult:
    if not isinstance(payload, Mapping):
        return PreparedGcsimCharacterConfigResult(
            status=PREPARED_CONFIG_INVALID_INPUT,
            ready=False,
            warnings=_default_warnings(),
            source_notes=_source_notes(),
        )

    warnings = list(_default_warnings())
    if any(key in payload for key in _FINAL_STATS_KEYS):
        warnings.append(WARNING_FINAL_STATS_IGNORED)

    character_input = GcsimCharacterConfigInput(
        project_character_id=_text(
            _first_present(payload, "project_character_id", "character_id", "id")
        ),
        display_name=_text(_first_present(payload, "display_name", "name")),
        level=_first_present(payload, "level", "current_level"),
        promote_level=_first_present(payload, "promote_level", "promote"),
        level_resolution=payload.get("level_resolution"),
        constellation=_first_present(payload, "constellation", "cons"),
        mapping=_mapping_ref(
            payload.get("mapping")
            or payload.get("gcsim_mapping")
            or _inline_mapping(payload)
        ),
        weapon=_weapon_input(payload.get("weapon") or payload.get("equipped_weapon")),
        artifacts=_artifact_input(
            payload.get("artifacts")
            or payload.get("artifact_build")
            or payload.get("artifact_build_snapshot")
        ),
        talents=_talent_input(payload.get("talents")),
        is_traveler=bool(payload.get("is_traveler")),
    )
    block = build_gcsim_character_config_block(character_input)
    warnings.extend(block.warnings)
    return PreparedGcsimCharacterConfigResult(
        status=PREPARED_CONFIG_READY if block.ready else PREPARED_CONFIG_NOT_READY,
        ready=block.ready,
        character_input=character_input,
        block=block,
        warnings=_dedupe_tuple(warnings),
        issues=block.issues,
        source_notes=_source_notes(),
    )


def adapt_prepared_team_config_inputs(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> PreparedGcsimTeamConfigResult:
    if isinstance(payload, Mapping):
        raw_characters = payload.get("characters")
        if raw_characters is None:
            raw_characters = payload.get("team")
    else:
        raw_characters = payload

    characters = tuple(
        adapt_prepared_character_config_input(item)
        for item in (raw_characters or ())
        if isinstance(item, Mapping)
    )
    warnings = _dedupe_tuple(
        warning
        for item in characters
        for warning in item.warnings
    )
    ready = bool(characters) and all(item.ready for item in characters)
    return PreparedGcsimTeamConfigResult(
        status=PREPARED_CONFIG_READY if ready else PREPARED_CONFIG_NOT_READY,
        ready=ready,
        characters=characters,
        warnings=warnings,
        source_notes=_source_notes(),
    )


def load_prepared_team_config_inputs_json(
    path: str | Path,
) -> PreparedGcsimTeamConfigResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return adapt_prepared_team_config_inputs(payload)
    if isinstance(payload, list):
        return adapt_prepared_team_config_inputs(payload)
    return PreparedGcsimTeamConfigResult(
        status=PREPARED_CONFIG_INVALID_INPUT,
        ready=False,
        warnings=_default_warnings(),
        source_notes=_source_notes(),
    )


def _weapon_input(value: Any) -> GcsimWeaponConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimWeaponConfigInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimWeaponConfigInput(
        project_weapon_id=_text(_first_present(value, "project_weapon_id", "weapon_id", "id")),
        display_name=_text(_first_present(value, "display_name", "name")),
        level=_first_present(value, "level", "current_level"),
        promote_level=_first_present(value, "promote_level", "promote"),
        level_resolution=value.get("level_resolution"),
        refinement=_first_present(value, "refinement", "refine", "affix_level"),
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _artifact_input(value: Any) -> GcsimArtifactConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimArtifactConfigInput):
        return value
    if isinstance(value, ArtifactBuildSnapshot):
        return _artifact_snapshot_input(value)
    if not isinstance(value, Mapping):
        return None

    snapshot = None
    if value.get("schema_version") and (
        value.get("set_counts") is not None
        or value.get("stat_totals") is not None
        or value.get("artifact_ids_by_pos") is not None
    ):
        snapshot = build_artifact_build_snapshot(value)
    set_counts_raw = (
        value.get("set_counts")
        or value.get("active_sets")
        or value.get("active_set_bonuses")
        or ()
    )
    stat_totals_raw = value.get("stat_totals") or value.get("total_stats") or ()
    if snapshot is not None and not set_counts_raw:
        set_counts_raw = [item.to_dict() for item in snapshot.set_counts]
    if snapshot is not None and not stat_totals_raw:
        stat_totals_raw = [item.to_dict() for item in snapshot.stat_totals]
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            _artifact_set_input(item)
            for item in set_counts_raw
            if isinstance(item, Mapping)
        ),
        stat_totals=tuple(
            item
            for item in stat_totals_raw
            if isinstance(item, (ArtifactStatTotalSnapshot, Mapping))
        ),
    )


def _artifact_snapshot_input(snapshot: ArtifactBuildSnapshot) -> GcsimArtifactConfigInput:
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            GcsimArtifactSetConfigInput(
                set_uid=item.set_uid,
                display_name=item.set_name,
                count=item.count,
            )
            for item in snapshot.set_counts
        ),
        stat_totals=snapshot.stat_totals,
    )


def _artifact_set_input(value: Mapping[str, Any]) -> GcsimArtifactSetConfigInput:
    return GcsimArtifactSetConfigInput(
        set_uid=_text(_first_present(value, "set_uid", "project_id", "id")),
        display_name=_text(_first_present(value, "display_name", "set_name", "name")),
        count=_optional_int(_first_present(value, "count", "piece_count", "owned_count")) or 0,
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _talent_input(value: Any) -> GcsimTalentInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimTalentInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimTalentInput(
        normal=_optional_int(value.get("normal")),
        skill=_optional_int(value.get("skill")),
        burst=_optional_int(value.get("burst")),
        source_order_confirmed=bool(value.get("source_order_confirmed")),
    )


def _mapping_ref(value: GcsimMappingRef | Mapping[str, Any] | None) -> GcsimMappingRef:
    if isinstance(value, GcsimMappingRef):
        return value
    if not isinstance(value, Mapping):
        return GcsimMappingRef()
    return GcsimMappingRef(
        gcsim_key=_text(value.get("gcsim_key") or value.get("key")),
        source=_text(value.get("source") or value.get("source_kind")),
        ambiguous=bool(value.get("ambiguous")),
    )


def _inline_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if "gcsim_key" not in value and "key" not in value:
        return {}
    return {
        "gcsim_key": value.get("gcsim_key") or value.get("key"),
        "source": value.get("source") or value.get("source_kind"),
        "ambiguous": value.get("ambiguous"),
    }


def _default_warnings() -> tuple[str, ...]:
    return (
        WARNING_PREPARED_FIXTURE_BOUNDARY,
        WARNING_NO_UI_OR_STORAGE_ACCESS,
    )


def _source_notes() -> dict[str, Any]:
    return {
        "adapter": "explicit_prepared_backend_input",
        "ui_access": False,
        "storage_query": False,
        "network_fetch": False,
        "final_stats_as_add_stats": False,
    }


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)
