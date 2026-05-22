from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .display_stats import build_character_display_stats
from .team_builder import (
    TeamBuilderSlotState,
    TeamBuilderState,
    create_empty_team_builder_state,
)
from .team_card_view_model import (
    EMPTY_SLOT_TITLE,
    TeamCardArtifactSummaryViewModel,
    TeamCardSlotViewModel,
    build_team_card_slot_view_model,
)


RIGHT_PANEL_PROTOTYPE_SCHEMA_VERSION = 6

MODE_ABYSS = "abyss"
MODE_DPS_DUMMY = "dps_dummy"
MODE_TABS = ("Abyss", "DPS Dummy")
ARTIFACT_STAT_BADGES = {
    2: "HP",
    3: "HP%",
    5: "ATK",
    6: "ATK%",
    8: "DEF",
    9: "DEF%",
    20: "CR",
    22: "CD",
    23: "ER",
    26: "HEAL",
    28: "EM",
    30: "PHYS",
    40: "PYRO",
    41: "ELECTRO",
    42: "HYDRO",
    43: "DENDRO",
    44: "ANEMO",
    45: "GEO",
    46: "CRYO",
}
ARTIFACT_STAT_PRIORITY = {
    20: 0,
    22: 1,
    23: 2,
    28: 3,
    3: 4,
    6: 5,
    2: 6,
    5: 7,
    8: 8,
    9: 9,
}
ARTIFACT_PERCENT_TYPES = {
    3,
    6,
    9,
    20,
    22,
    23,
    26,
    30,
    40,
    41,
    42,
    43,
    44,
    45,
    46,
}
CHAMBER_TABLE_HEADERS = (
    "Ch.",
    "T1",
    "T2",
    "Fact T1 DPS",
    "Fact T2 DPS",
    "Sim T1 DPS",
    "Sim T2 DPS",
)
ARTIFACT_SANDS_POSITION = 3
ARTIFACT_GOBLET_POSITION = 4


@dataclass(frozen=True, slots=True)
class RightPanelDetailRowViewModel:
    label: str
    value: str
    icon_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "icon_label": self.icon_label,
        }


@dataclass(frozen=True, slots=True)
class RightPanelBuildMiniSetViewModel:
    set_uid: str
    set_name: str
    piece_count: int
    owned_count: int
    icon_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "piece_count": self.piece_count,
            "owned_count": self.owned_count,
            "icon_path": self.icon_path,
        }


@dataclass(frozen=True, slots=True)
class RightPanelSlotPrototypeViewModel:
    team_index: int
    slot_index: int
    is_empty: bool
    is_selected: bool
    character_title: str
    character_meta: str
    portrait_label: str
    portrait_path: str
    weapon_label: str
    weapon_square_label: str
    weapon_image_path: str
    build_label: str
    artifact_square_label: str
    artifact_image_path: str
    build_mini_sets: tuple[RightPanelBuildMiniSetViewModel, ...]
    stat_badge: str
    warning_count: int
    warning_tooltip: str
    artifact_summary: TeamCardArtifactSummaryViewModel | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_index": self.team_index,
            "slot_index": self.slot_index,
            "is_empty": self.is_empty,
            "is_selected": self.is_selected,
            "character_title": self.character_title,
            "character_meta": self.character_meta,
            "portrait_label": self.portrait_label,
            "portrait_path": self.portrait_path,
            "weapon_label": self.weapon_label,
            "weapon_square_label": self.weapon_square_label,
            "weapon_image_path": self.weapon_image_path,
            "build_label": self.build_label,
            "artifact_square_label": self.artifact_square_label,
            "artifact_image_path": self.artifact_image_path,
            "build_mini_sets": [item.to_dict() for item in self.build_mini_sets],
            "stat_badge": self.stat_badge,
            "warning_count": self.warning_count,
            "warning_tooltip": self.warning_tooltip,
            "artifact_summary": _artifact_summary_to_dict(self.artifact_summary),
        }


@dataclass(frozen=True, slots=True)
class RightPanelTeamPrototypeViewModel:
    team_index: int
    slots: tuple[RightPanelSlotPrototypeViewModel, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_index": self.team_index,
            "slots": [slot.to_dict() for slot in self.slots],
        }


@dataclass(frozen=True, slots=True)
class RightPanelSelectedDetailsViewModel:
    has_selection: bool
    team_index: int | None = None
    slot_index: int | None = None
    character_name: str = ""
    character_level: int | None = None
    constellation: int | None = None
    element: str = ""
    weapon_name: str = ""
    weapon_level: int | None = None
    weapon_refinement: int | None = None
    weapon_base_atk: str = ""
    weapon_secondary_label: str = ""
    weapon_secondary_value: str = ""
    crit_value: float | None = None
    active_sets: tuple[str, ...] = ()
    stat_rows: tuple[RightPanelDetailRowViewModel, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_selection": self.has_selection,
            "team_index": self.team_index,
            "slot_index": self.slot_index,
            "character_name": self.character_name,
            "character_level": self.character_level,
            "constellation": self.constellation,
            "element": self.element,
            "weapon_name": self.weapon_name,
            "weapon_level": self.weapon_level,
            "weapon_refinement": self.weapon_refinement,
            "weapon_base_atk": self.weapon_base_atk,
            "weapon_secondary_label": self.weapon_secondary_label,
            "weapon_secondary_value": self.weapon_secondary_value,
            "crit_value": self.crit_value,
            "active_sets": list(self.active_sets),
            "stat_rows": [row.to_dict() for row in self.stat_rows],
        }


@dataclass(frozen=True, slots=True)
class RightPanelChamberRowViewModel:
    chamber_label: str
    team1_time: str
    team1_seconds: int
    team2_time: str
    team2_seconds: int
    factual_team1: str
    factual_team2: str
    sim_team1: str
    sim_team2: str
    total_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chamber_label": self.chamber_label,
            "team1_time": self.team1_time,
            "team1_seconds": self.team1_seconds,
            "team2_time": self.team2_time,
            "team2_seconds": self.team2_seconds,
            "factual_team1": self.factual_team1,
            "factual_team2": self.factual_team2,
            "sim_team1": self.sim_team1,
            "sim_team2": self.sim_team2,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True, slots=True)
class RightPanelGcsimStatusViewModel:
    status: str
    button_label: str = "GCSIM"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "button_label": self.button_label,
        }


@dataclass(frozen=True, slots=True)
class RightPanelPrototypeViewModel:
    mode: str
    mode_tabs: tuple[str, ...]
    teams: tuple[RightPanelTeamPrototypeViewModel, ...]
    selected_details: RightPanelSelectedDetailsViewModel
    chamber_headers: tuple[str, ...]
    chamber_rows: tuple[RightPanelChamberRowViewModel, ...]
    total_seconds: int
    gcsim_status: RightPanelGcsimStatusViewModel
    action_labels: tuple[str, ...] = ("Reset", "Save Run", "History")
    schema_version: int = RIGHT_PANEL_PROTOTYPE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "mode_tabs": list(self.mode_tabs),
            "teams": [team.to_dict() for team in self.teams],
            "selected_details": self.selected_details.to_dict(),
            "chamber_headers": list(self.chamber_headers),
            "chamber_rows": [row.to_dict() for row in self.chamber_rows],
            "total_seconds": self.total_seconds,
            "gcsim_status": self.gcsim_status.to_dict(),
            "action_labels": list(self.action_labels),
        }


def build_right_panel_prototype_view_model(
    state: TeamBuilderState,
    *,
    mode: str = MODE_ABYSS,
    selected_team_index: int = 0,
    selected_slot_index: int = 0,
) -> RightPanelPrototypeViewModel:
    normalized_mode = _normalize_mode(mode)
    visible_team_count = 2 if normalized_mode == MODE_ABYSS else 1
    duplicate_ids = state.duplicate_character_ids()
    teams = tuple(
        _build_team(
            state,
            team_index=index,
            duplicate_character_ids=duplicate_ids,
            selected_team_index=selected_team_index,
            selected_slot_index=selected_slot_index,
        )
        for index in range(min(visible_team_count, len(state.teams)))
    )
    selected_details = _build_selected_details(
        state,
        selected_team_index=selected_team_index,
        selected_slot_index=selected_slot_index,
        duplicate_character_ids=duplicate_ids,
    )
    chamber_rows = _chamber_rows_for_mode(normalized_mode)
    total_seconds = sum(row.total_seconds for row in chamber_rows)
    return RightPanelPrototypeViewModel(
        mode=normalized_mode,
        mode_tabs=MODE_TABS,
        teams=teams,
        selected_details=selected_details,
        chamber_headers=CHAMBER_TABLE_HEADERS,
        chamber_rows=chamber_rows,
        total_seconds=total_seconds,
        gcsim_status=_gcsim_status_for_mode(normalized_mode),
    )


def build_fake_right_panel_prototype_state() -> TeamBuilderState:
    state = create_empty_team_builder_state(team_count=2)
    state = _fill_slot(
        state,
        team_index=0,
        slot_index=0,
        character={
            "id": "10000050",
            "name": "Thoma",
            "level": 70,
            "element": "Pyro",
            "rarity": 4,
            "constellation": 6,
        },
        weapon={
            "id": "13407",
            "name": "Favonius Lance",
            "level": 70,
            "refinement": 5,
            "type_name": "Polearm",
        },
        build={"build_id": 20, "build_name": "test111"},
        details=_fake_details(
            character_name="Thoma",
            character_id="10000050",
            level=70,
            constellation=6,
            element="Pyro",
            weapon_name="Favonius Lance",
            weapon_level=70,
            refinement=5,
            build_id=20,
            build_name="test111",
            active_sets=("2p Silken Moon", "2p Emblem"),
            crit_value=95.6,
            proc_count=12,
            missing_positions=(5,),
            key_stats=("HP 21440", "ER 212%", "EM 137", "Pyro 46.6%", "DEF 0"),
            warnings=(
                "artifact_build_incomplete",
                "final_totals_not_computed",
                "gcsim_config_generation_not_implemented",
            ),
        ),
    )
    state = _fill_slot(
        state,
        team_index=0,
        slot_index=1,
        character={
            "id": "10000089",
            "name": "Furina",
            "level": 90,
            "element": "Hydro",
            "rarity": 5,
            "constellation": 2,
        },
        weapon={
            "id": "11501",
            "name": "Splendor of Tranquil Waters",
            "level": 90,
            "refinement": 1,
            "type_name": "Sword",
        },
        build={"build_id": 31, "build_name": "Salon DPS"},
        details=_fake_details(
            character_name="Furina",
            character_id="10000089",
            level=90,
            constellation=2,
            element="Hydro",
            weapon_name="Splendor of Tranquil Waters",
            weapon_level=90,
            refinement=1,
            build_id=31,
            build_name="Salon DPS",
            active_sets=("4p Golden Troupe",),
            crit_value=212.4,
            proc_count=24,
            missing_positions=(),
            key_stats=("HP 39210", "CR 78%", "CD 212%", "Hydro 46.6%"),
            warnings=("final_totals_not_computed",),
        ),
    )
    state = state.set_character(
        0,
        2,
        {
            "id": "10000047",
            "name": "Kaedehara Kazuha",
            "level": 90,
            "element": "Anemo",
            "rarity": 5,
            "constellation": 0,
        },
    )
    state = state.set_weapon(
        0,
        2,
        {
            "id": "11403",
            "name": "Favonius Sword",
            "level": 90,
            "refinement": 4,
            "type_name": "Sword",
        },
    )
    state = _fill_slot(
        state,
        team_index=0,
        slot_index=3,
        character={
            "id": "10000032",
            "name": "Bennett",
            "level": 90,
            "element": "Pyro",
            "rarity": 4,
            "constellation": 6,
        },
        weapon={
            "id": "11510",
            "name": "Sapwood Blade",
            "level": 90,
            "refinement": 5,
            "type_name": "Sword",
        },
        build={"build_id": 44, "build_name": "NO support"},
        details=_fake_details(
            character_name="Bennett",
            character_id="10000032",
            level=90,
            constellation=6,
            element="Pyro",
            weapon_name="Sapwood Blade",
            weapon_level=90,
            refinement=5,
            build_id=44,
            build_name="NO support",
            active_sets=("4p Noblesse Oblige",),
            crit_value=42.0,
            proc_count=9,
            missing_positions=(),
            key_stats=("ER 245%", "HP 27100", "Heal 35%"),
            warnings=("weapon_passive_not_included", "final_totals_not_computed"),
        ),
    )
    state = _fill_slot(
        state,
        team_index=1,
        slot_index=0,
        character={
            "id": "10000052",
            "name": "Raiden Shogun",
            "level": 90,
            "element": "Electro",
            "rarity": 5,
            "constellation": 2,
        },
        weapon={
            "id": "13509",
            "name": "Engulfing Lightning",
            "level": 90,
            "refinement": 1,
            "type_name": "Polearm",
        },
        build={"build_id": 52, "build_name": "Emblem carry"},
        details=_fake_details(
            character_name="Raiden Shogun",
            character_id="10000052",
            level=90,
            constellation=2,
            element="Electro",
            weapon_name="Engulfing Lightning",
            weapon_level=90,
            refinement=1,
            build_id=52,
            build_name="Emblem carry",
            active_sets=("4p Emblem",),
            crit_value=201.8,
            proc_count=22,
            missing_positions=(),
            key_stats=("ER 270%", "CR 72%", "CD 186%", "Electro 46.6%"),
            warnings=("final_totals_not_computed",),
        ),
    )
    state = _fill_slot(
        state,
        team_index=1,
        slot_index=1,
        character={
            "id": "10000023",
            "name": "Xingqiu",
            "level": 90,
            "element": "Hydro",
            "rarity": 4,
            "constellation": 6,
        },
        weapon={
            "id": "11407",
            "name": "Sacrificial Sword",
            "level": 90,
            "refinement": 5,
            "type_name": "Sword",
        },
        build={"build_id": 61, "build_name": "2p2p hydro"},
        details=_fake_details(
            character_name="Xingqiu",
            character_id="10000023",
            level=90,
            constellation=6,
            element="Hydro",
            weapon_name="Sacrificial Sword",
            weapon_level=90,
            refinement=5,
            build_id=61,
            build_name="2p2p hydro",
            active_sets=("2p Heart of Depth", "2p Noblesse"),
            crit_value=176.2,
            proc_count=20,
            missing_positions=(),
            key_stats=("ER 215%", "CR 66%", "CD 154%", "Hydro 46.6%"),
            warnings=("final_totals_not_computed",),
        ),
    )
    return state


def _build_team(
    state: TeamBuilderState,
    *,
    team_index: int,
    duplicate_character_ids: tuple[str, ...],
    selected_team_index: int,
    selected_slot_index: int,
) -> RightPanelTeamPrototypeViewModel:
    team = state.team(team_index)
    return RightPanelTeamPrototypeViewModel(
        team_index=team_index,
        slots=tuple(
            _build_slot(
                raw_slot,
                team_index=team_index,
                duplicate_character_ids=duplicate_character_ids,
                is_selected=(
                    team_index == int(selected_team_index)
                    and raw_slot.slot_index == int(selected_slot_index)
                ),
            )
            for raw_slot in team.slots
        ),
    )


def _build_slot(
    slot: TeamBuilderSlotState,
    *,
    team_index: int,
    duplicate_character_ids: tuple[str, ...],
    is_selected: bool,
) -> RightPanelSlotPrototypeViewModel:
    card_slot = build_team_card_slot_view_model(
        slot,
        duplicate_character_ids=duplicate_character_ids,
    )
    details = _details_dict(slot.character_details_data)
    artifact = card_slot.artifact_summary
    warnings = _visible_slot_warnings(tuple(card_slot.warnings))
    warning_count = len(warnings)
    return RightPanelSlotPrototypeViewModel(
        team_index=team_index,
        slot_index=slot.slot_index,
        is_empty=card_slot.is_empty,
        is_selected=is_selected,
        character_title=card_slot.character_title,
        character_meta=card_slot.character_meta,
        portrait_label=_portrait_label(card_slot),
        portrait_path=_portrait_path(details),
        weapon_label=card_slot.weapon_label,
        weapon_square_label=_square_label(card_slot.weapon_label, fallback="WPN"),
        weapon_image_path=_image_path(details, "weapon_image_path", "weapon_path"),
        build_label=card_slot.build_label,
        artifact_square_label=_artifact_square_label(card_slot),
        artifact_image_path=_image_path(details, "artifact_image_path", "build_image_path"),
        build_mini_sets=tuple(_build_mini_sets(details)),
        stat_badge=_stat_badge(card_slot, details),
        warning_count=warning_count,
        warning_tooltip=_warning_tooltip(warnings),
        artifact_summary=artifact,
    )


def _build_selected_details(
    state: TeamBuilderState,
    *,
    selected_team_index: int,
    selected_slot_index: int,
    duplicate_character_ids: tuple[str, ...],
) -> RightPanelSelectedDetailsViewModel:
    try:
        slot = state.team(selected_team_index).slot(selected_slot_index)
    except IndexError:
        return RightPanelSelectedDetailsViewModel(has_selection=False)

    card_slot = build_team_card_slot_view_model(
        slot,
        duplicate_character_ids=duplicate_character_ids,
    )
    if card_slot.is_empty:
        return RightPanelSelectedDetailsViewModel(has_selection=False)

    details = _details_dict(slot.character_details_data)
    artifact = card_slot.artifact_summary
    account_character = _account_character_for_slot(slot, details)
    account_weapon = _account_weapon_for_slot(slot, details)
    weapon_secondary_label, weapon_secondary_value = _weapon_secondary_meta(details)
    return RightPanelSelectedDetailsViewModel(
        has_selection=True,
        team_index=int(selected_team_index),
        slot_index=int(selected_slot_index),
        character_name=card_slot.character_title,
        character_level=_optional_int(account_character.get("level")),
        constellation=_optional_int(account_character.get("constellation")),
        element=_text(account_character.get("element")),
        weapon_name=_text(account_weapon.get("name")) or "No weapon selected",
        weapon_level=_optional_int(account_weapon.get("level")),
        weapon_refinement=_optional_int(account_weapon.get("refinement")),
        weapon_base_atk=_weapon_base_atk_meta(details),
        weapon_secondary_label=weapon_secondary_label,
        weapon_secondary_value=weapon_secondary_value,
        crit_value=artifact.crit_value if artifact is not None else None,
        active_sets=artifact.active_sets if artifact is not None else (),
        stat_rows=tuple(_stat_rows(details)),
    )


def _chamber_rows_for_mode(mode: str) -> tuple[RightPanelChamberRowViewModel, ...]:
    if mode == MODE_DPS_DUMMY:
        return (
            RightPanelChamberRowViewModel(
                chamber_label="Dummy",
                team1_time="01:30",
                team1_seconds=90,
                team2_time="-",
                team2_seconds=0,
                factual_team1="128k",
                factual_team2="-",
                sim_team1="not run",
                sim_team2="-",
                total_seconds=90,
            ),
        )
    return (
        RightPanelChamberRowViewModel(
            "C1",
            "09:47",
            13,
            "09:25",
            22,
            "-",
            "-",
            "not run",
            "not run",
            35,
        ),
        RightPanelChamberRowViewModel(
            "C2",
            "10:00",
            0,
            "05:00",
            300,
            "-",
            "-",
            "not run",
            "not run",
            300,
        ),
        RightPanelChamberRowViewModel(
            "C3",
            "05:00",
            300,
            "06:00",
            0,
            "-",
            "-",
            "not run",
            "not run",
            300,
        ),
    )


def _gcsim_status_for_mode(mode: str) -> RightPanelGcsimStatusViewModel:
    if mode == MODE_DPS_DUMMY:
        return RightPanelGcsimStatusViewModel(status="GCSIM: not configured")
    return RightPanelGcsimStatusViewModel(status="GCSIM: not run")


def _fill_slot(
    state: TeamBuilderState,
    *,
    team_index: int,
    slot_index: int,
    character: Mapping[str, Any],
    weapon: Mapping[str, Any],
    build: Mapping[str, Any],
    details: Mapping[str, Any],
) -> TeamBuilderState:
    state = state.set_character(team_index, slot_index, character)
    state = state.set_weapon(team_index, slot_index, weapon)
    state = state.set_artifact_build(team_index, slot_index, build)
    return state.attach_character_details_data(team_index, slot_index, dict(details))


def _fake_details(
    *,
    character_name: str,
    character_id: str,
    level: int,
    constellation: int,
    element: str,
    weapon_name: str,
    weapon_level: int,
    refinement: int,
    build_id: int,
    build_name: str,
    active_sets: tuple[str, ...],
    crit_value: float,
    proc_count: int,
    missing_positions: tuple[int, ...],
    key_stats: tuple[str, ...],
    warnings: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "status": "partial" if warnings else "ready",
        "account_character": {
            "id": character_id,
            "name": character_name,
            "level": level,
            "element": element,
            "constellation": constellation,
        },
        "account_weapon": {
            "name": weapon_name,
            "level": weapon_level,
            "refinement": refinement,
        },
        "selected_build": {
            "build_id": build_id,
            "build_name": build_name,
        },
        "display_stats": list(key_stats),
        "stat_snapshot": {
            "character_base": {
                "base_hp": {"selected": key_stats[0].split(" ", 1)[-1]},
                "base_atk": {"selected": "not computed"},
                "base_def": {"selected": "not computed"},
            },
            "artifact": {
                "summary": {
                    "slots": _fake_artifact_slots(
                        element=element,
                        key_stats=key_stats,
                        missing_positions=missing_positions,
                    ),
                    "active_set_bonuses": [
                        {"piece_count": _piece_count(label), "set_name": label[3:]}
                        for label in active_sets
                    ],
                    "crit_value": crit_value,
                    "proc_count": proc_count,
                    "missing_positions": list(missing_positions),
                },
                "warnings": [
                    warning
                    for warning in warnings
                    if warning.startswith("artifact_")
                    or warning.startswith("set_bonus_")
                ],
            },
        },
        "warnings": list(warnings),
        "gcsim_readiness": {
            "config_generation_ready": False,
            "reasons": [
                "gcsim_config_generation_not_implemented",
                "gcsim_key_mapping_not_implemented",
            ],
        },
    }


def _piece_count(label: str) -> int:
    if label.startswith("4p "):
        return 4
    if label.startswith("2p "):
        return 2
    return 0


def _fake_artifact_slots(
    *,
    element: str,
    key_stats: tuple[str, ...],
    missing_positions: tuple[int, ...],
) -> list[dict[str, Any]]:
    missing = set(missing_positions)
    slots: list[dict[str, Any]] = []
    if ARTIFACT_SANDS_POSITION not in missing:
        sands_type = _fake_sands_property_type(key_stats)
        slots.append(
            {
                "pos": ARTIFACT_SANDS_POSITION,
                "main_property_type": sands_type,
                "main_property_name": ARTIFACT_STAT_BADGES.get(sands_type, ""),
            }
        )
    if ARTIFACT_GOBLET_POSITION not in missing:
        goblet_type = _fake_goblet_property_type(element, key_stats)
        slots.append(
            {
                "pos": ARTIFACT_GOBLET_POSITION,
                "main_property_type": goblet_type,
                "main_property_name": ARTIFACT_STAT_BADGES.get(goblet_type, ""),
            }
        )
    return slots


def _fake_sands_property_type(key_stats: tuple[str, ...]) -> int:
    text = " ".join(key_stats).casefold()
    if "er " in text or "er%" in text:
        return 23
    if "em " in text:
        return 28
    if "hp " in text:
        return 3
    if "def " in text:
        return 9
    return 6


def _fake_goblet_property_type(element: str, key_stats: tuple[str, ...]) -> int:
    text = " ".join(key_stats).casefold()
    for name, property_type in (
        ("pyro", 40),
        ("electro", 41),
        ("hydro", 42),
        ("dendro", 43),
        ("anemo", 44),
        ("geo", 45),
        ("cryo", 46),
    ):
        if name in text:
            return property_type
    normalized_element = str(element or "").strip().casefold()
    if normalized_element in {
        "pyro",
        "electro",
        "hydro",
        "dendro",
        "anemo",
        "geo",
        "cryo",
    }:
        return {
            "pyro": 40,
            "electro": 41,
            "hydro": 42,
            "dendro": 43,
            "anemo": 44,
            "geo": 45,
            "cryo": 46,
        }[normalized_element]
    return 3


def _normalize_mode(mode: str) -> str:
    text = str(mode or "").strip().casefold()
    if text in {"dps", "dps_dummy", "dummy"}:
        return MODE_DPS_DUMMY
    return MODE_ABYSS


def _portrait_label(slot: TeamCardSlotViewModel) -> str:
    if slot.is_empty or slot.character_title == EMPTY_SLOT_TITLE:
        return "+"
    parts = [part for part in slot.character_title.replace("-", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(part[0] for part in parts[:2]).upper()


def _portrait_path(details: Mapping[str, Any]) -> str:
    direct = _text(details.get("portrait_path"))
    if direct:
        return direct
    account_character = _mapping(details.get("account_character"))
    return _text(
        account_character.get("portrait_path")
        or account_character.get("crop")
        or account_character.get("local_portrait_path")
    )


def _image_path(details: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        direct = _text(details.get(key))
        if direct:
            return direct
    account_weapon = _mapping(details.get("account_weapon"))
    if any(key in {"weapon_image_path", "weapon_path"} for key in keys):
        return _text(account_weapon.get("icon_path"))
    return ""


def _build_mini_sets(details: Mapping[str, Any]) -> list[RightPanelBuildMiniSetViewModel]:
    explicit = details.get("build_mini_sets")
    if isinstance(explicit, list):
        rows = [_build_mini_set_from_mapping(item) for item in explicit]
        return [row for row in rows if row is not None]

    summary = _artifact_summary_mapping(details)
    active_sets = summary.get("active_set_bonuses")
    if not isinstance(active_sets, list):
        return []

    rows: list[RightPanelBuildMiniSetViewModel] = []
    for item in active_sets:
        row = _build_mini_set_from_mapping(item)
        if row is not None:
            rows.append(row)
    return rows


def _build_mini_set_from_mapping(
    value: Any,
) -> RightPanelBuildMiniSetViewModel | None:
    item = _mapping(value)
    if not item:
        return None
    piece_count = _optional_int(_first_present(item, "piece_count", "count")) or 0
    owned_count = _optional_int(item.get("owned_count")) or piece_count
    set_name = _text(item.get("set_name"))
    set_uid = _text(item.get("set_uid"))
    icon_path = _text(item.get("icon_path"))
    if piece_count <= 0 or not (set_name or set_uid):
        return None
    return RightPanelBuildMiniSetViewModel(
        set_uid=set_uid,
        set_name=set_name or set_uid,
        piece_count=piece_count,
        owned_count=owned_count,
        icon_path=icon_path,
    )


def _artifact_summary_mapping(details: Mapping[str, Any]) -> dict[str, Any]:
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact = _mapping(stat_snapshot.get("artifact"))
    return _mapping(artifact.get("summary"))


def _square_label(text: str, *, fallback: str) -> str:
    words = [
        word
        for word in str(text or "").replace("#", " ").split()
        if word and not _is_equipment_suffix(word)
    ]
    if not words:
        return fallback
    if words[0].isdigit():
        return f"#{words[0]}"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(word[0] for word in words[:3]).upper()


def _is_equipment_suffix(word: str) -> bool:
    normalized = word.rstrip(",;")
    if normalized.casefold().startswith("lv."):
        return True
    return len(normalized) > 1 and normalized[0].upper() == "R" and normalized[1:].isdigit()


def _artifact_square_label(slot: TeamCardSlotViewModel) -> str:
    if slot.is_empty:
        return "ART"
    if not slot.build_label:
        return "Equip"
    if slot.artifact_summary is None:
        return "Build"
    if slot.artifact_summary.missing_positions:
        return "Fix"
    return _square_label(slot.build_label, fallback="Build")


def _stat_badge(
    slot: TeamCardSlotViewModel,
    details: Mapping[str, Any],
) -> str:
    if slot.is_empty:
        return "EMPTY"
    if not slot.build_label:
        return "NO BUILD"
    return _artifact_main_stat_badge(_artifact_summary_mapping(details))


def _artifact_main_stat_badge(summary: Mapping[str, Any]) -> str:
    sands = _artifact_main_stat_token(summary, ARTIFACT_SANDS_POSITION)
    goblet = _artifact_main_stat_token(summary, ARTIFACT_GOBLET_POSITION)
    if sands or goblet:
        return f"{sands or '-'}/{goblet or '-'}"
    return "NO MAIN"


def _artifact_main_stat_token(
    summary: Mapping[str, Any],
    position: int,
) -> str:
    slots = summary.get("slots")
    if not isinstance(slots, list):
        return ""
    for slot in slots:
        if not isinstance(slot, Mapping):
            continue
        if _optional_int(slot.get("pos")) != position:
            continue
        property_type = _optional_int(slot.get("main_property_type"))
        if property_type in ARTIFACT_STAT_BADGES:
            return ARTIFACT_STAT_BADGES[int(property_type)]
        return _short_stat_label(
            slot.get("main_property_name") or slot.get("stat_key")
        )
    return ""


def _stat_rows(details: Mapping[str, Any]) -> list[RightPanelDetailRowViewModel]:
    if not details:
        return []

    explicit_rows = _explicit_display_stat_rows(details)
    if explicit_rows:
        return explicit_rows

    display_stats = build_character_display_stats(details)
    return [
        RightPanelDetailRowViewModel(
            label=row.label,
            value=row.value,
            icon_label=row.icon_label,
        )
        for row in display_stats.rows
    ]


def _explicit_display_stat_rows(details: Mapping[str, Any]) -> list[RightPanelDetailRowViewModel]:
    explicit = details.get("display_stats")
    if not isinstance(explicit, list):
        return []

    rows: list[RightPanelDetailRowViewModel] = []
    for stat_text in explicit:
        label, value = _split_stat_text(stat_text)
        if not label or _is_empty_stat_value(value):
            continue
        if _is_raw_partial_stat_label(label):
            continue
        rows.append(
            RightPanelDetailRowViewModel(
                label=label,
                value=value,
                icon_label=_stat_token(label),
            )
        )
    return rows[:10]


def _is_raw_partial_stat_label(label: str) -> bool:
    normalized = str(label or "").strip().casefold()
    return normalized.startswith(("base ", "weapon ", "asc ", "art "))


def _split_stat_text(value: str) -> tuple[str, str]:
    parts = str(value or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) >= 3 and parts[0].casefold() in {"base", "weapon", "asc", "art"}:
        return " ".join(parts[:2]), " ".join(parts[2:])
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _is_empty_stat_value(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if text.casefold() in {"-", "none", "null", "not computed", "n/a"}:
        return True
    numeric = text.replace("%", "").replace(",", "")
    try:
        return float(numeric) == 0
    except ValueError:
        return False


def _stat_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "STAT"
    normalized = text.casefold().replace("_", " ")
    aliases = {
        "weapon atk": "WATK",
        "base hp": "HP",
        "base atk": "ATK",
        "base def": "DEF",
        "asc atk": "ASC",
        "asc hp": "ASC",
        "asc def": "ASC",
        "art hp": "AHP",
        "art hp%": "AHP",
        "art atk": "AATK",
        "art atk%": "AATK",
        "art def": "ADEF",
        "art def%": "ADEF",
        "art er": "AER",
        "art em": "AEM",
        "art cr": "ACR",
        "art cd": "ACD",
        "crit rate": "CR",
        "critical rate": "CR",
        "crit dmg": "CD",
        "critical damage": "CD",
        "energy recharge": "ER",
        "elemental mastery": "EM",
        "pyro": "PYRO",
        "hydro": "HYDRO",
        "electro": "ELECTRO",
        "cryo": "CRYO",
        "anemo": "ANEMO",
        "geo": "GEO",
        "dendro": "DENDRO",
    }
    if normalized in aliases:
        return aliases[normalized]
    return "".join(part[0] for part in text.split()).upper() if " " in text else text.upper()


def _element_from_meta_or_details(meta: str, details: Mapping[str, Any]) -> str:
    account_character = _mapping(details.get("account_character"))
    element = str(account_character.get("element") or "").strip()
    if element:
        return element
    for token in ("Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo", "Dendro"):
        if token in meta:
            return token
    return ""


def _legacy_key_stats(details: Mapping[str, Any]) -> list[str]:
    explicit = details.get("display_stats")
    if isinstance(explicit, list):
        return [str(item) for item in explicit if str(item or "").strip()]

    stats: list[str] = []
    snapshot = _mapping(details.get("stat_snapshot"))
    character_base = _mapping(snapshot.get("character_base"))
    for label, key in (
        ("Base HP", "base_hp"),
        ("Base ATK", "base_atk"),
        ("Base DEF", "base_def"),
    ):
        value = _selected_value(character_base.get(key))
        if value:
            stats.append(f"{label} {value}")
    ascension_bonus_type = str(character_base.get("ascension_bonus_stat_type") or "").strip()
    ascension_bonus = _selected_value(character_base.get("ascension_bonus"))
    if ascension_bonus_type and ascension_bonus:
        stats.append(f"Asc {ascension_bonus_type} {ascension_bonus}")

    weapon = _mapping(snapshot.get("weapon"))
    weapon_atk = _selected_value(weapon.get("base_atk"))
    if weapon_atk:
        stats.append(f"Weapon ATK {weapon_atk}")
    secondary_type = str(weapon.get("secondary_stat_type") or "").strip()
    secondary_value = str(weapon.get("secondary_stat_value") or "").strip()
    if secondary_type and secondary_value:
        stats.append(f"{_short_stat_label(secondary_type)} {secondary_value}")

    artifact = _mapping(snapshot.get("artifact"))
    summary = _mapping(artifact.get("summary"))
    stat_totals = [
        stat
        for stat in summary.get("stat_totals") or []
        if isinstance(stat, Mapping)
    ]
    for stat in sorted(stat_totals, key=_artifact_stat_sort_key):
        if not isinstance(stat, Mapping):
            continue
        label = _artifact_stat_label(stat)
        value = _artifact_stat_value(stat)
        if label and value:
            stats.append(f"Art {label} {value}")
    return stats[:10]


def _artifact_stat_sort_key(stat: Mapping[str, Any]) -> tuple[int, int]:
    property_type = _optional_int(stat.get("property_type"))
    if property_type is None:
        return (999, 999)
    return (ARTIFACT_STAT_PRIORITY.get(property_type, 500), property_type)


def _artifact_stat_label(stat: Mapping[str, Any]) -> str:
    property_type = _optional_int(stat.get("property_type"))
    if property_type in ARTIFACT_STAT_BADGES:
        return ARTIFACT_STAT_BADGES[int(property_type)]
    return _short_stat_label(stat.get("property_name") or stat.get("stat_key"))


def _short_stat_label(value: Any) -> str:
    text = str(value or "").strip()
    normalized = text.casefold().replace("_", " ")
    aliases = {
        "hp": "HP",
        "hp%": "HP%",
        "atk": "ATK",
        "atk%": "ATK%",
        "def": "DEF",
        "def%": "DEF%",
        "energy recharge": "ER",
        "elemental mastery": "EM",
        "crit rate": "CR",
        "critical rate": "CR",
        "crit dmg": "CD",
        "crit damage": "CD",
        "pyro dmg bonus": "PYRO",
        "hydro dmg bonus": "HYDRO",
        "electro dmg bonus": "ELECTRO",
        "cryo dmg bonus": "CRYO",
        "anemo dmg bonus": "ANEMO",
        "geo dmg bonus": "GEO",
        "dendro dmg bonus": "DENDRO",
        "healing bonus": "HEAL",
    }
    return aliases.get(normalized, text)


def _artifact_stat_value(stat: Mapping[str, Any]) -> str:
    value = stat.get("value")
    if value not in (None, ""):
        return str(value).strip()
    raw_value = stat.get("raw_value")
    if raw_value in (None, ""):
        return ""
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return str(raw_value)
    text = str(int(number)) if number.is_integer() else f"{number:g}"
    property_type = _optional_int(stat.get("property_type"))
    return f"{text}%" if property_type in ARTIFACT_PERCENT_TYPES else text


def _selected_value(value: Any) -> str:
    data = _mapping(value)
    return str(data.get("selected") or "").strip()


def _account_character_for_slot(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    account_character = _mapping(details.get("account_character"))
    if account_character:
        return account_character
    if slot.character is not None:
        return slot.character.to_dict()
    return {}


def _account_weapon_for_slot(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    account_weapon = _mapping(details.get("account_weapon"))
    if account_weapon:
        return account_weapon
    if slot.weapon is not None:
        return slot.weapon.to_dict()
    return {}


def _weapon_base_atk_meta(details: Mapping[str, Any]) -> str:
    snapshot_weapon = _snapshot_weapon(details)
    snapshot_base_atk = _selected_value(snapshot_weapon.get("base_atk"))
    if snapshot_base_atk:
        return snapshot_base_atk

    account_weapon = _mapping(details.get("account_weapon"))
    account_base_atk = _text(account_weapon.get("base_atk_raw") or account_weapon.get("base_atk"))
    if account_base_atk:
        return account_base_atk

    weapon_sheet = _account_stat_sheet_weapon(details)
    main_property = _mapping(weapon_sheet.get("main_property"))
    if not main_property:
        return ""
    return _text(main_property.get("final") or main_property.get("base"))


def _weapon_secondary_meta(details: Mapping[str, Any]) -> tuple[str, str]:
    snapshot_weapon = _snapshot_weapon(details)
    secondary_type = _text(snapshot_weapon.get("secondary_stat_type"))
    secondary_value = _text(snapshot_weapon.get("secondary_stat_value"))
    if secondary_type and secondary_value:
        return _short_stat_label(secondary_type), secondary_value

    account_weapon = _mapping(details.get("account_weapon"))
    account_property_type = _optional_int(account_weapon.get("secondary_property_type"))
    account_value = _text(
        account_weapon.get("secondary_stat_value_raw")
        or account_weapon.get("secondary_stat_value")
    )
    if account_property_type is not None and account_value:
        return _property_type_short_label(account_property_type), account_value

    weapon_sheet = _account_stat_sheet_weapon(details)
    sub_property = _mapping(weapon_sheet.get("sub_property"))
    if not sub_property:
        return "", ""
    property_type = _optional_int(sub_property.get("property_type"))
    value = _text(sub_property.get("final") or sub_property.get("base"))
    if property_type is None or not value:
        return "", ""
    return _property_type_short_label(property_type), value


def _snapshot_weapon(details: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _mapping(details.get("stat_snapshot"))
    return _mapping(snapshot.get("weapon"))


def _account_stat_sheet_weapon(details: Mapping[str, Any]) -> dict[str, Any]:
    stat_sheet = _mapping(details.get("account_stat_sheet"))
    return _mapping(stat_sheet.get("weapon"))


def _property_type_short_label(property_type: int) -> str:
    if int(property_type) == 4:
        return "ATK"
    return ARTIFACT_STAT_BADGES.get(int(property_type), f"P{int(property_type)}")


def _artifact_summary_to_dict(
    artifact: TeamCardArtifactSummaryViewModel | None,
) -> dict[str, Any] | None:
    if artifact is None:
        return None
    return {
        "active_sets": list(artifact.active_sets),
        "crit_value": artifact.crit_value,
        "proc_count": artifact.proc_count,
        "missing_positions": list(artifact.missing_positions),
    }


def _warning_tooltip(warnings: tuple[str, ...]) -> str:
    if not warnings:
        return ""
    rows = [_warning_label(warning) for warning in warnings]
    return "\n".join(row for row in rows if row)


def _warning_label(warning: str) -> str:
    labels = {
        "final_totals_not_computed": "Display totals are provisional.",
        "character_stats_unavailable": "Static character catalog row was not attached.",
        "weapon_stats_unavailable": "Static weapon catalog row was not attached.",
        "artifact_build_incomplete": "Selected build is missing one or more artifact slots.",
        "set_bonus_formulas_not_included": "Artifact set bonus formulas are not applied.",
        "conditional_set_bonuses_not_included": "Conditional set bonuses are not applied.",
        "duplicate_selected_character": "Character is selected more than once.",
    }
    return labels.get(str(warning or ""), str(warning or ""))


def _visible_slot_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    if "set_bonus_formulas_not_included" not in warnings:
        return warnings
    return tuple(
        warning
        for warning in warnings
        if warning != "conditional_set_bonuses_not_included"
    )


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


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
