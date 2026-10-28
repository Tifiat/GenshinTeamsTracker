from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .team_builder import (
    WARNING_DUPLICATE_SELECTED_CHARACTER,
    TeamBuilderSlotState,
    TeamBuilderState,
    TeamBuilderTeamState,
)


TEAM_CARD_VIEW_MODEL_SCHEMA_VERSION = 1

EMPTY_SLOT_TITLE = "Empty slot"


@dataclass(frozen=True, slots=True)
class TeamCardArtifactSummaryViewModel:
    active_sets: tuple[str, ...] = ()
    crit_value: float | None = None
    proc_count: int | None = None
    missing_positions: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_sets": list(self.active_sets),
            "crit_value": self.crit_value,
            "proc_count": self.proc_count,
            "missing_positions": list(self.missing_positions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class TeamCardSlotViewModel:
    slot_index: int
    is_empty: bool
    status: str
    character_title: str
    character_meta: str = ""
    weapon_label: str = ""
    build_label: str = ""
    artifact_summary: TeamCardArtifactSummaryViewModel | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "is_empty": self.is_empty,
            "status": self.status,
            "character_title": self.character_title,
            "character_meta": self.character_meta,
            "weapon_label": self.weapon_label,
            "build_label": self.build_label,
            "artifact_summary": (
                self.artifact_summary.to_dict()
                if self.artifact_summary is not None
                else None
            ),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class TeamCardViewModel:
    title: str
    slots: tuple[TeamCardSlotViewModel, ...]
    warnings: tuple[str, ...] = ()
    schema_version: int = TEAM_CARD_VIEW_MODEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "warnings": list(self.warnings),
            "slots": [slot.to_dict() for slot in self.slots],
        }


def build_team_card_view_model_from_state(
    state: TeamBuilderState,
    *,
    team_index: int = 0,
    title: str | None = None,
) -> TeamCardViewModel:
    team = state.team(team_index)
    return build_team_card_view_model(
        team,
        title=title or f"Team {int(team_index) + 1}",
        duplicate_character_ids=state.duplicate_character_ids(),
        warnings=state.validation_warnings(),
    )


def build_team_card_view_model(
    team: TeamBuilderTeamState,
    *,
    title: str = "Team",
    duplicate_character_ids: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> TeamCardViewModel:
    return TeamCardViewModel(
        title=title,
        slots=tuple(
            build_team_card_slot_view_model(
                slot,
                duplicate_character_ids=duplicate_character_ids,
            )
            for slot in team.slots
        ),
        warnings=tuple(_dedupe(warnings)),
    )


def build_team_card_slot_view_model(
    slot: TeamBuilderSlotState,
    *,
    duplicate_character_ids: tuple[str, ...] = (),
) -> TeamCardSlotViewModel:
    details = _details_dict(slot.character_details_data)
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact_summary = _artifact_summary_from_details(details)
    warnings: list[str] = []
    warnings.extend(str(item) for item in slot.warnings)
    warnings.extend(str(item) for item in details.get("warnings") or [])
    if artifact_summary is not None:
        warnings.extend(artifact_summary.warnings)
    if _slot_character_id(slot, details) in set(duplicate_character_ids):
        warnings.append(WARNING_DUPLICATE_SELECTED_CHARACTER)

    is_empty = slot.is_empty and not details
    return TeamCardSlotViewModel(
        slot_index=slot.slot_index,
        is_empty=is_empty,
        status=_text(details.get("status")) or ("empty" if is_empty else "ready"),
        character_title=_character_title(slot, details),
        character_meta=_character_meta(slot, details),
        weapon_label=_weapon_label(slot, details),
        build_label=_build_label(slot, details),
        artifact_summary=artifact_summary,
        warnings=tuple(_dedupe(warnings)),
    )


def _artifact_summary_from_details(
    details: Mapping[str, Any],
) -> TeamCardArtifactSummaryViewModel | None:
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact = _mapping(stat_snapshot.get("artifact"))
    summary = _mapping(artifact.get("summary"))
    if not summary:
        return None

    return TeamCardArtifactSummaryViewModel(
        active_sets=tuple(_active_set_labels(summary.get("active_set_bonuses"))),
        crit_value=_optional_float(summary.get("crit_value")),
        proc_count=_optional_int(summary.get("proc_count")),
        missing_positions=tuple(
            int(item)
            for item in (_optional_int(value) for value in summary.get("missing_positions") or [])
            if item is not None
        ),
        warnings=tuple(str(item) for item in artifact.get("warnings") or []),
    )


def _character_title(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> str:
    account_character = _mapping(details.get("account_character"))
    if account_character:
        return _text(account_character.get("name")) or _text(account_character.get("id"))
    if slot.character is not None:
        return slot.character.name or slot.character.id or EMPTY_SLOT_TITLE
    return EMPTY_SLOT_TITLE


def _character_meta(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> str:
    account_character = _mapping(details.get("account_character"))
    if not account_character and slot.character is not None:
        account_character = slot.character.to_dict()

    parts: list[str] = []
    level = _optional_int(account_character.get("level"))
    if level is not None:
        parts.append(f"Lv.{level}")
    constellation = _optional_int(account_character.get("constellation"))
    if constellation is not None:
        parts.append(f"C{constellation}")
    element = _text(account_character.get("element"))
    if element:
        parts.append(element)
    character_id = _text(account_character.get("id"))
    if character_id:
        parts.append(f"id {character_id}")
    return " | ".join(parts)


def _weapon_label(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> str:
    account_weapon = _mapping(details.get("account_weapon"))
    if not account_weapon and slot.weapon is not None:
        account_weapon = slot.weapon.to_dict()
    if not account_weapon:
        return ""

    parts: list[str] = []
    name = _text(account_weapon.get("name")) or _text(account_weapon.get("id"))
    if name:
        parts.append(name)
    level = _optional_int(account_weapon.get("level"))
    if level is not None:
        parts.append(f"Lv.{level}")
    refinement = _optional_int(account_weapon.get("refinement"))
    if refinement is not None:
        parts.append(f"R{refinement}")
    return " ".join(parts)


def _build_label(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> str:
    selected_build = _mapping(details.get("selected_build"))
    if not selected_build and slot.artifact_build is not None:
        selected_build = slot.artifact_build.to_dict()
    build_id = _optional_int(selected_build.get("build_id"))
    build_name = _text(selected_build.get("build_name"))
    if build_id is None and not build_name:
        return ""
    if build_id is None:
        return build_name
    if build_name:
        return f"Build #{build_id}: {build_name}"
    return f"Build #{build_id}"


def _active_set_labels(value: Any) -> list[str]:
    labels: list[str] = []
    if not isinstance(value, list):
        return labels
    for item in value:
        if not isinstance(item, Mapping):
            continue
        piece_count = _optional_int(item.get("piece_count"))
        set_name = _text(item.get("set_name")) or _text(item.get("set_uid"))
        if not set_name:
            continue
        if piece_count:
            labels.append(f"{piece_count}p {set_name}")
        else:
            labels.append(set_name)
    return labels


def _slot_character_id(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> str:
    account_character = _mapping(details.get("account_character"))
    if account_character:
        return _text(account_character.get("id"))
    if slot.character is not None:
        return slot.character.id
    return ""


def _details_dict(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        return data if isinstance(data, dict) else {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
