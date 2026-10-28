from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


TEAM_BUILDER_SCHEMA_VERSION = 1
DEFAULT_TEAM_SLOT_COUNT = 4

TEAM_BUILDER_STATUS_READY = "ready"
TEAM_BUILDER_STATUS_EMPTY = "empty"
TEAM_BUILDER_STATUS_WARNING = "warning"

WARNING_DUPLICATE_SELECTED_CHARACTER = "duplicate_selected_character"
WARNING_WEAPON_ALLOCATION_DEFERRED = "weapon_allocation_deferred"


@dataclass(frozen=True, slots=True)
class SelectedCharacterRef:
    id: str = ""
    name: str = ""
    level: int | None = None
    element: str = ""
    rarity: int | None = None
    constellation: int | None = None
    source: str = "account"

    @property
    def is_selected(self) -> bool:
        return bool(self.id or self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "element": self.element,
            "rarity": self.rarity,
            "constellation": self.constellation,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class SelectedWeaponRef:
    id: str = ""
    name: str = ""
    level: int | None = None
    promote_level: int | None = None
    rarity: int | None = None
    refinement: int | None = None
    weapon_type: str = ""
    variant_key: str = ""
    source: str = "account"
    warnings: tuple[str, ...] = (WARNING_WEAPON_ALLOCATION_DEFERRED,)

    @property
    def is_selected(self) -> bool:
        return bool(self.id or self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "rarity": self.rarity,
            "refinement": self.refinement,
            "weapon_type": self.weapon_type,
            "variant_key": self.variant_key,
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SelectedArtifactBuildRef:
    build_id: int | None = None
    build_name: str = ""
    source: str = "artifact_browser"
    provenance_note: str = (
        "Build id/name are selection provenance only; saved runs must snapshot "
        "actual artifact/build contents."
    )

    @property
    def is_selected(self) -> bool:
        return self.build_id is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "build_name": self.build_name,
            "source": self.source,
            "provenance_note": self.provenance_note,
        }


@dataclass(frozen=True, slots=True)
class TeamBuilderSlotState:
    slot_index: int
    character: SelectedCharacterRef | None = None
    weapon: SelectedWeaponRef | None = None
    artifact_build: SelectedArtifactBuildRef | None = None
    character_details_data: Any | None = None
    warnings: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            self.character is None
            and self.weapon is None
            and self.artifact_build is None
            and self.character_details_data is None
        )

    def with_character(
        self,
        character: SelectedCharacterRef | Mapping[str, Any] | None,
        *,
        clear_details: bool = True,
    ) -> "TeamBuilderSlotState":
        return replace(
            self,
            character=selected_character_ref(character),
            character_details_data=None if clear_details else self.character_details_data,
        )

    def with_weapon(
        self,
        weapon: SelectedWeaponRef | Mapping[str, Any] | None,
        *,
        clear_details: bool = True,
    ) -> "TeamBuilderSlotState":
        return replace(
            self,
            weapon=selected_weapon_ref(weapon),
            character_details_data=None if clear_details else self.character_details_data,
        )

    def with_artifact_build(
        self,
        build: SelectedArtifactBuildRef | Mapping[str, Any] | int | None,
        *,
        clear_details: bool = True,
    ) -> "TeamBuilderSlotState":
        return replace(
            self,
            artifact_build=selected_artifact_build_ref(build),
            character_details_data=None if clear_details else self.character_details_data,
        )

    def with_character_details_data(
        self,
        character_details_data: Any | None,
    ) -> "TeamBuilderSlotState":
        return replace(self, character_details_data=character_details_data)

    def clear_character_details_data(self) -> "TeamBuilderSlotState":
        return replace(self, character_details_data=None)

    def clear_weapon(self) -> "TeamBuilderSlotState":
        return replace(self, weapon=None, character_details_data=None)

    def clear_artifact_build(self) -> "TeamBuilderSlotState":
        return replace(self, artifact_build=None, character_details_data=None)

    def clear(self) -> "TeamBuilderSlotState":
        return TeamBuilderSlotState(slot_index=self.slot_index)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "character": self.character.to_dict() if self.character else None,
            "weapon": self.weapon.to_dict() if self.weapon else None,
            "artifact_build": (
                self.artifact_build.to_dict()
                if self.artifact_build is not None
                else None
            ),
            "character_details_data": _details_data_to_dict(self.character_details_data),
            "warnings": list(self.warnings),
            "is_empty": self.is_empty,
        }


@dataclass(frozen=True, slots=True)
class TeamBuilderTeamState:
    slots: tuple[TeamBuilderSlotState, ...] = field(
        default_factory=lambda: create_empty_team().slots
    )

    @classmethod
    def empty(cls, *, slot_count: int = DEFAULT_TEAM_SLOT_COUNT) -> "TeamBuilderTeamState":
        return cls(
            slots=tuple(
                TeamBuilderSlotState(slot_index=index)
                for index in range(max(0, int(slot_count)))
            )
        )

    def set_character(
        self,
        slot_index: int,
        character: SelectedCharacterRef | Mapping[str, Any] | None,
    ) -> "TeamBuilderTeamState":
        return self._replace_slot(
            slot_index,
            self.slot(slot_index).with_character(character),
        )

    def set_weapon(
        self,
        slot_index: int,
        weapon: SelectedWeaponRef | Mapping[str, Any] | None,
    ) -> "TeamBuilderTeamState":
        return self._replace_slot(slot_index, self.slot(slot_index).with_weapon(weapon))

    def set_artifact_build(
        self,
        slot_index: int,
        build: SelectedArtifactBuildRef | Mapping[str, Any] | int | None,
    ) -> "TeamBuilderTeamState":
        return self._replace_slot(
            slot_index,
            self.slot(slot_index).with_artifact_build(build),
        )

    def attach_character_details_data(
        self,
        slot_index: int,
        character_details_data: Any | None,
    ) -> "TeamBuilderTeamState":
        return self._replace_slot(
            slot_index,
            self.slot(slot_index).with_character_details_data(character_details_data),
        )

    def clear_slot(self, slot_index: int) -> "TeamBuilderTeamState":
        return self._replace_slot(slot_index, self.slot(slot_index).clear())

    def clear_weapon(self, slot_index: int) -> "TeamBuilderTeamState":
        return self._replace_slot(slot_index, self.slot(slot_index).clear_weapon())

    def clear_artifact_build(self, slot_index: int) -> "TeamBuilderTeamState":
        return self._replace_slot(slot_index, self.slot(slot_index).clear_artifact_build())

    def swap_slots(
        self,
        first_slot_index: int,
        second_slot_index: int,
    ) -> "TeamBuilderTeamState":
        first = self.slot(first_slot_index)
        second = self.slot(second_slot_index)
        slots = list(self.slots)
        slots[first_slot_index] = replace(second, slot_index=first_slot_index)
        slots[second_slot_index] = replace(first, slot_index=second_slot_index)
        return replace(self, slots=tuple(slots))

    def move_slot(
        self,
        source_slot_index: int,
        target_slot_index: int,
    ) -> "TeamBuilderTeamState":
        source = self.slot(source_slot_index)
        slots = list(self.slots)
        slots[target_slot_index] = replace(source, slot_index=target_slot_index)
        slots[source_slot_index] = TeamBuilderSlotState(slot_index=source_slot_index)
        return replace(self, slots=tuple(slots))

    def duplicate_character_ids(self) -> tuple[str, ...]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for slot in self.slots:
            character_id = _selected_character_id(slot)
            if not character_id:
                continue
            if character_id in seen and character_id not in duplicates:
                duplicates.append(character_id)
            seen.add(character_id)
        return tuple(duplicates)

    def validation_warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if self.duplicate_character_ids():
            warnings.append(WARNING_DUPLICATE_SELECTED_CHARACTER)
        for slot in self.slots:
            warnings.extend(slot.warnings)
        return tuple(_dedupe(warnings))

    def slot(self, slot_index: int) -> TeamBuilderSlotState:
        index = int(slot_index)
        if index < 0 or index >= len(self.slots):
            raise IndexError(f"Team builder slot index out of range: {slot_index}")
        return self.slots[index]

    def to_dict(self) -> dict[str, Any]:
        warnings = self.validation_warnings()
        return {
            "slot_count": len(self.slots),
            "status": _status_for_slots(self.slots, warnings),
            "duplicate_character_ids": list(self.duplicate_character_ids()),
            "warnings": list(warnings),
            "slots": [slot.to_dict() for slot in self.slots],
        }

    def _replace_slot(
        self,
        slot_index: int,
        slot: TeamBuilderSlotState,
    ) -> "TeamBuilderTeamState":
        self.slot(slot_index)
        slots = list(self.slots)
        slots[int(slot_index)] = replace(slot, slot_index=int(slot_index))
        return replace(self, slots=tuple(slots))


@dataclass(frozen=True, slots=True)
class TeamBuilderState:
    teams: tuple[TeamBuilderTeamState, ...]
    schema_version: int = TEAM_BUILDER_SCHEMA_VERSION

    @classmethod
    def empty(
        cls,
        *,
        team_count: int = 1,
        slot_count: int = DEFAULT_TEAM_SLOT_COUNT,
    ) -> "TeamBuilderState":
        return cls(
            teams=tuple(
                TeamBuilderTeamState.empty(slot_count=slot_count)
                for _ in range(max(0, int(team_count)))
            )
        )

    def set_character(
        self,
        team_index: int,
        slot_index: int,
        character: SelectedCharacterRef | Mapping[str, Any] | None,
    ) -> "TeamBuilderState":
        team = self.team(team_index).set_character(slot_index, character)
        return self._replace_team(team_index, team)

    def set_weapon(
        self,
        team_index: int,
        slot_index: int,
        weapon: SelectedWeaponRef | Mapping[str, Any] | None,
    ) -> "TeamBuilderState":
        team = self.team(team_index).set_weapon(slot_index, weapon)
        return self._replace_team(team_index, team)

    def set_artifact_build(
        self,
        team_index: int,
        slot_index: int,
        build: SelectedArtifactBuildRef | Mapping[str, Any] | int | None,
    ) -> "TeamBuilderState":
        team = self.team(team_index).set_artifact_build(slot_index, build)
        return self._replace_team(team_index, team)

    def attach_character_details_data(
        self,
        team_index: int,
        slot_index: int,
        character_details_data: Any | None,
    ) -> "TeamBuilderState":
        team = self.team(team_index).attach_character_details_data(
            slot_index,
            character_details_data,
        )
        return self._replace_team(team_index, team)

    def clear_slot(self, team_index: int, slot_index: int) -> "TeamBuilderState":
        return self._replace_team(
            team_index,
            self.team(team_index).clear_slot(slot_index),
        )

    def clear_weapon(self, team_index: int, slot_index: int) -> "TeamBuilderState":
        return self._replace_team(
            team_index,
            self.team(team_index).clear_weapon(slot_index),
        )

    def clear_artifact_build(self, team_index: int, slot_index: int) -> "TeamBuilderState":
        return self._replace_team(
            team_index,
            self.team(team_index).clear_artifact_build(slot_index),
        )

    def swap_slots(
        self,
        first_team_index: int,
        first_slot_index: int,
        second_team_index: int,
        second_slot_index: int,
    ) -> "TeamBuilderState":
        if int(first_team_index) == int(second_team_index):
            team = self.team(first_team_index).swap_slots(
                first_slot_index,
                second_slot_index,
            )
            return self._replace_team(first_team_index, team)

        first_team = self.team(first_team_index)
        second_team = self.team(second_team_index)
        first_slot = first_team.slot(first_slot_index)
        second_slot = second_team.slot(second_slot_index)
        first_team = first_team._replace_slot(
            first_slot_index,
            replace(second_slot, slot_index=int(first_slot_index)),
        )
        second_team = second_team._replace_slot(
            second_slot_index,
            replace(first_slot, slot_index=int(second_slot_index)),
        )
        return self._replace_team(first_team_index, first_team)._replace_team(
            second_team_index,
            second_team,
        )

    def move_slot(
        self,
        source_team_index: int,
        source_slot_index: int,
        target_team_index: int,
        target_slot_index: int,
    ) -> "TeamBuilderState":
        if int(source_team_index) == int(target_team_index):
            team = self.team(source_team_index).move_slot(
                source_slot_index,
                target_slot_index,
            )
            return self._replace_team(source_team_index, team)

        source_team = self.team(source_team_index)
        target_team = self.team(target_team_index)
        source_slot = source_team.slot(source_slot_index)
        source_team = source_team.clear_slot(source_slot_index)
        target_team = target_team._replace_slot(
            target_slot_index,
            replace(source_slot, slot_index=int(target_slot_index)),
        )
        return self._replace_team(source_team_index, source_team)._replace_team(
            target_team_index,
            target_team,
        )

    def duplicate_character_ids(self) -> tuple[str, ...]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for team in self.teams:
            for slot in team.slots:
                character_id = _selected_character_id(slot)
                if not character_id:
                    continue
                if character_id in seen and character_id not in duplicates:
                    duplicates.append(character_id)
                seen.add(character_id)
        return tuple(duplicates)

    def validation_warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if self.duplicate_character_ids():
            warnings.append(WARNING_DUPLICATE_SELECTED_CHARACTER)
        for team in self.teams:
            warnings.extend(team.validation_warnings())
        return tuple(_dedupe(warnings))

    def team(self, team_index: int) -> TeamBuilderTeamState:
        index = int(team_index)
        if index < 0 or index >= len(self.teams):
            raise IndexError(f"Team builder team index out of range: {team_index}")
        return self.teams[index]

    def to_dict(self) -> dict[str, Any]:
        warnings = self.validation_warnings()
        return {
            "schema_version": self.schema_version,
            "team_count": len(self.teams),
            "status": _status_for_state(self.teams, warnings),
            "duplicate_character_ids": list(self.duplicate_character_ids()),
            "warnings": list(warnings),
            "teams": [team.to_dict() for team in self.teams],
        }

    def _replace_team(
        self,
        team_index: int,
        team: TeamBuilderTeamState,
    ) -> "TeamBuilderState":
        self.team(team_index)
        teams = list(self.teams)
        teams[int(team_index)] = team
        return replace(self, teams=tuple(teams))


def create_empty_team(*, slot_count: int = DEFAULT_TEAM_SLOT_COUNT) -> TeamBuilderTeamState:
    return TeamBuilderTeamState.empty(slot_count=slot_count)


def create_empty_team_builder_state(
    *,
    team_count: int = 1,
    slot_count: int = DEFAULT_TEAM_SLOT_COUNT,
) -> TeamBuilderState:
    return TeamBuilderState.empty(team_count=team_count, slot_count=slot_count)


def selected_character_ref(
    value: SelectedCharacterRef | Mapping[str, Any] | None,
) -> SelectedCharacterRef | None:
    if value is None:
        return None
    if isinstance(value, SelectedCharacterRef):
        return value
    return SelectedCharacterRef(
        id=_text(value.get("id")),
        name=_text(value.get("name")),
        level=_optional_int(value.get("level")),
        element=_text(value.get("element")),
        rarity=_optional_int(value.get("rarity")),
        constellation=_optional_int(
            _first_present(value, "constellation", "actived_constellation_num")
        ),
    )


def selected_weapon_ref(
    value: SelectedWeaponRef | Mapping[str, Any] | None,
) -> SelectedWeaponRef | None:
    if value is None:
        return None
    if isinstance(value, SelectedWeaponRef):
        return value
    name = _text(value.get("name"))
    level = _optional_int(value.get("level"))
    refinement = _optional_int(_first_present(value, "refinement", "affix_level"))
    weapon_type = _text(_first_present(value, "type_name", "weapon_type_name", "type"))
    return SelectedWeaponRef(
        id=_text(value.get("id")),
        name=name,
        level=level,
        promote_level=_optional_int(
            _first_present(value, "promote_level", "ascension", "ascension_phase")
        ),
        rarity=_optional_int(value.get("rarity")),
        refinement=refinement,
        weapon_type=weapon_type,
        variant_key=_weapon_variant_key(
            name=name,
            level=level,
            refinement=refinement,
            weapon_type=weapon_type,
        ),
    )


def selected_artifact_build_ref(
    value: SelectedArtifactBuildRef | Mapping[str, Any] | int | None,
) -> SelectedArtifactBuildRef | None:
    if value is None:
        return None
    if isinstance(value, SelectedArtifactBuildRef):
        return value
    if isinstance(value, int):
        return SelectedArtifactBuildRef(build_id=value)
    build_id = _optional_int(_first_present(value, "build_id", "id"))
    return SelectedArtifactBuildRef(
        build_id=build_id,
        build_name=_text(_first_present(value, "build_name", "name")),
    )


def _selected_character_id(slot: TeamBuilderSlotState) -> str:
    if slot.character is None:
        return ""
    return slot.character.id


def _details_data_to_dict(value: Any | None) -> dict[str, Any] | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": str(value)}


def _status_for_slots(
    slots: tuple[TeamBuilderSlotState, ...],
    warnings: tuple[str, ...],
) -> str:
    if warnings:
        return TEAM_BUILDER_STATUS_WARNING
    if all(slot.is_empty for slot in slots):
        return TEAM_BUILDER_STATUS_EMPTY
    return TEAM_BUILDER_STATUS_READY


def _status_for_state(
    teams: tuple[TeamBuilderTeamState, ...],
    warnings: tuple[str, ...],
) -> str:
    if warnings:
        return TEAM_BUILDER_STATUS_WARNING
    if all(slot.is_empty for team in teams for slot in team.slots):
        return TEAM_BUILDER_STATUS_EMPTY
    return TEAM_BUILDER_STATUS_READY


def _weapon_variant_key(
    *,
    name: str,
    level: int | None,
    refinement: int | None,
    weapon_type: str,
) -> str:
    parts = [
        name.casefold().strip(),
        str(level or ""),
        str(refinement or ""),
        weapon_type.casefold().strip(),
    ]
    return "|".join(parts)


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
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


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
