from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from localization import tr, tr_for_language

from .models import AbyssTimerState, calculate_abyss_chamber_result
from .abyss.factual_dps import (
    REASON_MISSING_HP,
    REASON_ZERO_OR_NEGATIVE_TIME,
    calculate_factual_dps,
)
from .abyss.source_data import (
    HP_SOURCE_NANOKA_RESOLVED,
    HP_SOURCE_UNAVAILABLE,
    AbyssChamberSideSourceData,
    AbyssFloorSourceData,
)
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
from hoyolab_export.character_trait_catalog import (
    get_hexerei_tooltip_sections,
    hexerei_tooltip_reference,
)
from .perf import log_perf, perf_ms, perf_now


RIGHT_PANEL_PROTOTYPE_SCHEMA_VERSION = 7

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
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEAM_BONUS_ICON_DIR = PROJECT_ROOT / "assets" / "team_bonus"
ARTIFACT_DB_PATH = PROJECT_ROOT / "data" / "artifacts.db"
MOONSIGN_SOURCE_URL = "https://wiki.hoyolab.com/pc/genshin/entry/8782"
HEXEREI_SOURCE_URL = "https://wiki.hoyolab.com/pc/genshin/entry/9347"
TRAIT_MOONSIGN = "moonsign"
TRAIT_HEXEREI = "hexerei"
ELEMENT_RESONANCE_ICONS = {
    "anemo": "anemo_resonance.png",
    "cryo": "cryo_resonance.png",
    "dendro": "dendro_resonance.png",
    "electro": "electro_resonance.png",
    "geo": "geo_resonance.png",
    "hydro": "hydro_resonance.png",
    "pyro": "pyro_resonance.png",
}
ELEMENT_TO_DMG_STAT_KEY = {
    "pyro": "PYRO_DMG_BONUS",
    "hydro": "HYDRO_DMG_BONUS",
    "cryo": "CRYO_DMG_BONUS",
    "electro": "ELECTRO_DMG_BONUS",
    "anemo": "ANEMO_DMG_BONUS",
    "geo": "GEO_DMG_BONUS",
    "dendro": "DENDRO_DMG_BONUS",
}


@dataclass(frozen=True, slots=True)
class _TeamBonusMember:
    slot_index: int
    name: str
    element: str
    traits: tuple[str, ...]
    icon_path: str
    details: dict[str, Any]
    hoyowiki_entry_id: str = ""
    constellation: int | None = None


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
class RightPanelBonusSourceDisplayItem:
    source_kind: str
    source_id: str
    label: str
    icon_path: str = ""
    short_effects: tuple[str, ...] = ()
    tooltip_effects: tuple[str, ...] = ()
    tooltip_title: str = ""
    tooltip_body: str = ""
    applied: bool = True
    not_applied_reason: str = ""
    character_icons: tuple[str, ...] = ()
    character_tooltips: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "label": self.label,
            "icon_path": self.icon_path,
            "short_effects": list(self.short_effects),
            "tooltip_effects": list(self.tooltip_effects),
            "tooltip_title": self.tooltip_title,
            "tooltip_body": self.tooltip_body,
            "applied": self.applied,
            "not_applied_reason": self.not_applied_reason,
            "character_icons": list(self.character_icons),
            "character_tooltips": list(self.character_tooltips),
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
    weapon_tooltip: str
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
            "weapon_tooltip": self.weapon_tooltip,
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
    weapon_icon_path: str = ""
    crit_value: float | None = None
    active_sets: tuple[str, ...] = ()
    stat_rows: tuple[RightPanelDetailRowViewModel, ...] = ()
    bonus_sources: tuple[RightPanelBonusSourceDisplayItem, ...] = ()
    external_bonuses_enabled: bool = True
    weapon_tooltip: str = ""

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
            "weapon_icon_path": self.weapon_icon_path,
            "crit_value": self.crit_value,
            "active_sets": list(self.active_sets),
            "stat_rows": [row.to_dict() for row in self.stat_rows],
            "bonus_sources": [item.to_dict() for item in self.bonus_sources],
            "external_bonuses_enabled": self.external_bonuses_enabled,
            "weapon_tooltip": self.weapon_tooltip,
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
    timer_editable: bool = False
    factual_team1_tooltip: "FactDpsTooltipViewModel | None" = None
    factual_team2_tooltip: "FactDpsTooltipViewModel | None" = None

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
            "timer_editable": self.timer_editable,
            "factual_team1_tooltip": None
            if self.factual_team1_tooltip is None
            else self.factual_team1_tooltip.to_dict(),
            "factual_team2_tooltip": None
            if self.factual_team2_tooltip is None
            else self.factual_team2_tooltip.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FactDpsEnemyTooltipViewModel:
    wave: int
    primary_display_name: str
    enemy_count: int
    display_level: int | None
    matched_nanoka_display_name: str | None
    hp_used: int | None
    hp_source: str
    match_method: str
    match_confidence: str
    cached_icon_path: str | None = None
    selected_for_solo: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "wave": self.wave,
            "primary_display_name": self.primary_display_name,
            "enemy_count": self.enemy_count,
            "display_level": self.display_level,
            "matched_nanoka_display_name": self.matched_nanoka_display_name,
            "hp_used": self.hp_used,
            "hp_source": self.hp_source,
            "match_method": self.match_method,
            "match_confidence": self.match_confidence,
            "cached_icon_path": self.cached_icon_path,
            "selected_for_solo": self.selected_for_solo,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class FactDpsTooltipViewModel:
    title: str
    formula: str
    total_solo_hp: int | None
    elapsed_seconds: int
    calculated_dps: int | None
    hp_source_label: str
    unavailable_reason: str = ""
    warnings: tuple[str, ...] = ()
    enemies: tuple[FactDpsEnemyTooltipViewModel, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.calculated_dps is not None and not self.unavailable_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "formula": self.formula,
            "total_solo_hp": self.total_solo_hp,
            "elapsed_seconds": self.elapsed_seconds,
            "calculated_dps": self.calculated_dps,
            "hp_source_label": self.hp_source_label,
            "unavailable_reason": self.unavailable_reason,
            "warnings": list(self.warnings),
            "enemies": [enemy.to_dict() for enemy in self.enemies],
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
    external_bonuses_enabled: bool = True
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
            "external_bonuses_enabled": self.external_bonuses_enabled,
            "action_labels": list(self.action_labels),
        }


def build_right_panel_prototype_view_model(
    state: TeamBuilderState,
    *,
    mode: str = MODE_ABYSS,
    selected_team_index: int = 0,
    selected_slot_index: int = 0,
    external_bonuses_enabled: bool = True,
    chamber_rows: tuple[RightPanelChamberRowViewModel, ...] | None = None,
) -> RightPanelPrototypeViewModel:
    total_start = perf_now()
    normalized_mode = _normalize_mode(mode)
    visible_team_count = 2 if normalized_mode == MODE_ABYSS else 1
    duplicate_start = perf_now()
    duplicate_ids = state.duplicate_character_ids()
    duplicate_ms = perf_ms(duplicate_start)
    teams_start = perf_now()
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
    teams_ms = perf_ms(teams_start)
    selected_start = perf_now()
    selected_details = _build_selected_details(
        state,
        selected_team_index=selected_team_index,
        selected_slot_index=selected_slot_index,
        duplicate_character_ids=duplicate_ids,
        external_bonuses_enabled=external_bonuses_enabled,
    )
    selected_ms = perf_ms(selected_start)
    chamber_start = perf_now()
    chamber_rows = chamber_rows or _chamber_rows_for_mode(normalized_mode)
    total_seconds = sum(row.total_seconds for row in chamber_rows)
    chamber_ms = perf_ms(chamber_start)
    model = RightPanelPrototypeViewModel(
        mode=normalized_mode,
        mode_tabs=MODE_TABS,
        teams=teams,
        selected_details=selected_details,
        chamber_headers=CHAMBER_TABLE_HEADERS,
        chamber_rows=chamber_rows,
        total_seconds=total_seconds,
        gcsim_status=_gcsim_status_for_mode(normalized_mode),
        external_bonuses_enabled=bool(external_bonuses_enabled),
    )
    log_perf(
        "right_panel_vm",
        total=perf_ms(total_start),
        duplicate=duplicate_ms,
        teams=teams_ms,
        selected_details=selected_ms,
        chamber=chamber_ms,
    )
    return model


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
    account_weapon = _account_weapon_for_slot(slot, details)
    has_weapon = _has_weapon_reference(account_weapon)
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
        weapon_image_path=(
            _image_path(details, "weapon_image_path", "weapon_path") if has_weapon else ""
        ),
        weapon_tooltip=_weapon_tooltip(details) if has_weapon and details else "",
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
    external_bonuses_enabled: bool,
) -> RightPanelSelectedDetailsViewModel:
    total_start = perf_now()
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
    has_weapon = _has_weapon_reference(account_weapon)
    if has_weapon:
        weapon_secondary_label, weapon_secondary_value = _weapon_secondary_meta(details)
        weapon_base_atk = _weapon_base_atk_meta(details)
        weapon_icon_path = _image_path(details, "weapon_image_path", "weapon_path")
        weapon_tooltip = _weapon_tooltip(details)
    else:
        weapon_secondary_label, weapon_secondary_value = "", ""
        weapon_base_atk = ""
        weapon_icon_path = ""
        weapon_tooltip = ""
    team_bonus_start = perf_now()
    team_members = _team_bonus_members(state.team(selected_team_index))
    selected_member = _selected_team_bonus_member(
        team_members,
        selected_slot_index=selected_slot_index,
    )
    team_bonus_effects = _elemental_resonance_effect_rows(
        team_members,
        selected_member=selected_member,
    )
    team_bonus_ms = perf_ms(team_bonus_start)
    stat_details = dict(details)
    if team_bonus_effects:
        stat_details["team_bonus_display_stat_effects"] = team_bonus_effects
    bonus_sources_start = perf_now()
    team_bonus_sources = _team_bonus_source_items(
        team_members,
        selected_member=selected_member,
        elemental_effects=team_bonus_effects,
        external_bonuses_enabled=external_bonuses_enabled,
    )
    bonus_sources = tuple(
        _bonus_source_items(
            details,
            artifact=artifact,
            external_bonuses_enabled=external_bonuses_enabled,
            leading_items=team_bonus_sources,
        )
    )
    bonus_sources_ms = perf_ms(bonus_sources_start)
    stat_rows_start = perf_now()
    stat_rows = tuple(
        _stat_rows(
            stat_details,
            external_bonuses_enabled=external_bonuses_enabled,
        )
    )
    stat_rows_ms = perf_ms(stat_rows_start)
    model = RightPanelSelectedDetailsViewModel(
        has_selection=True,
        team_index=int(selected_team_index),
        slot_index=int(selected_slot_index),
        character_name=card_slot.character_title,
        character_level=_optional_int(account_character.get("level")),
        constellation=_optional_int(account_character.get("constellation")),
        element=_text(account_character.get("element")),
        weapon_name=_text(account_weapon.get("name")) if has_weapon else "",
        weapon_level=_optional_int(account_weapon.get("level")) if has_weapon else None,
        weapon_refinement=(
            _optional_int(account_weapon.get("refinement")) if has_weapon else None
        ),
        weapon_base_atk=weapon_base_atk,
        weapon_secondary_label=weapon_secondary_label,
        weapon_secondary_value=weapon_secondary_value,
        weapon_icon_path=weapon_icon_path,
        crit_value=artifact.crit_value if artifact is not None else None,
        active_sets=artifact.active_sets if artifact is not None else (),
        stat_rows=stat_rows,
        bonus_sources=bonus_sources,
        external_bonuses_enabled=bool(external_bonuses_enabled),
        weapon_tooltip=weapon_tooltip,
    )
    log_perf(
        "selected_details_vm",
        total=perf_ms(total_start),
        team_bonus=team_bonus_ms,
        bonus_sources=bonus_sources_ms,
        stat_rows=stat_rows_ms,
    )
    return model


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
    summary = _artifact_summary_mapping(details)
    icon_paths_by_set_uid = _set_icon_paths_from_summary_slots(summary)

    explicit = details.get("build_mini_sets")
    if isinstance(explicit, list):
        rows: list[RightPanelBuildMiniSetViewModel] = []
        for item in explicit:
            row = _build_mini_set_from_mapping(item)
            if row is not None:
                row = _with_mini_set_icon_path(row, icon_paths_by_set_uid)
                rows.append(row)
        return rows

    icon_paths_by_set_uid = _set_icon_paths_from_summary_slots(summary)
    active_sets = summary.get("active_set_bonuses")
    if not isinstance(active_sets, list):
        return []

    rows: list[RightPanelBuildMiniSetViewModel] = []
    for item in active_sets:
        row = _build_mini_set_from_mapping(item)
        if row is not None:
            row = _with_mini_set_icon_path(row, icon_paths_by_set_uid)
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
    icon_path = _text(item.get("icon_path")) or _artifact_set_icon_path(set_uid)
    if piece_count <= 0 or not (set_name or set_uid):
        return None
    return RightPanelBuildMiniSetViewModel(
        set_uid=set_uid,
        set_name=set_name or set_uid,
        piece_count=piece_count,
        owned_count=owned_count,
        icon_path=icon_path,
    )


def _set_icon_paths_from_summary_slots(
    summary: Mapping[str, Any],
) -> dict[str, str]:
    slots = summary.get("slots")
    if not isinstance(slots, list):
        return {}

    result: dict[str, str] = {}
    for value in slots:
        item = _mapping(value)
        if not item:
            continue
        set_uid = _text(item.get("set_uid"))
        icon_path = _text(item.get("set_icon_path"))
        if set_uid and icon_path and set_uid not in result:
            result[set_uid] = icon_path
    return result


def _with_mini_set_icon_path(
    row: RightPanelBuildMiniSetViewModel,
    icon_paths_by_set_uid: Mapping[str, str],
) -> RightPanelBuildMiniSetViewModel:
    icon_path = _text(icon_paths_by_set_uid.get(row.set_uid)) or row.icon_path
    if not icon_path:
        return row
    if icon_path != row.icon_path:
        return RightPanelBuildMiniSetViewModel(
        set_uid=row.set_uid,
        set_name=row.set_name,
        piece_count=row.piece_count,
        owned_count=row.owned_count,
        icon_path=icon_path,
    )
    return row


def _artifact_set_icon_path(set_uid: str) -> str:
    set_uid = _text(set_uid)
    if not set_uid:
        return ""
    path = Path("assets") / "artifact_sets" / f"{set_uid}_1.png"
    if (PROJECT_ROOT / path).is_file():
        return path.as_posix()
    return ""


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


def _bonus_source_items(
    details: Mapping[str, Any],
    *,
    artifact: TeamCardArtifactSummaryViewModel | None,
    external_bonuses_enabled: bool,
    leading_items: tuple[RightPanelBonusSourceDisplayItem, ...] = (),
) -> list[RightPanelBonusSourceDisplayItem]:
    items: list[RightPanelBonusSourceDisplayItem] = list(leading_items)
    active_sets = _active_set_context(details, artifact=artifact)
    grouped_artifact_effects: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for effect in details.get("artifact_set_display_stat_effects") or []:
        if not isinstance(effect, Mapping):
            continue
        set_uid = _text(effect.get("set_uid"))
        pieces_required = _optional_int(effect.get("pieces_required"))
        if not set_uid or pieces_required is None:
            continue
        grouped_artifact_effects.setdefault((set_uid, int(pieces_required)), []).append(effect)

    for (set_uid, pieces_required), effects in grouped_artifact_effects.items():
        context = active_sets.get(set_uid, {})
        set_name = _text(context.get("set_name")) or set_uid
        effect_labels = tuple(_static_effect_short_label(effect) for effect in effects)
        effect_labels = tuple(label for label in effect_labels if label)
        tooltip_effect_labels = tuple(
            _localized_static_effect_label(effect) for effect in effects
        )
        tooltip_effect_labels = tuple(label for label in tooltip_effect_labels if label)
        if not effect_labels:
            continue
        description = _text(effects[0].get("description"))
        items.append(
            RightPanelBonusSourceDisplayItem(
                source_kind="artifact_set_static",
                source_id=f"{set_uid}:{pieces_required}",
                label=f"{pieces_required}p",
                icon_path=_text(context.get("icon_path")),
                short_effects=effect_labels,
                tooltip_effects=tooltip_effect_labels,
                tooltip_title=f"{set_name} {pieces_required}p",
                tooltip_body=description,
                applied=bool(external_bonuses_enabled),
                not_applied_reason=(
                    "" if external_bonuses_enabled else _external_bonuses_disabled_text()
                ),
            )
        )

    weapon_effects = [
        effect
        for effect in details.get("weapon_display_stat_effects") or []
        if isinstance(effect, Mapping)
    ]
    if weapon_effects:
        account_weapon = _account_weapon_for_details(details)
        weapon_name = _text(account_weapon.get("name")) or "Weapon passive"
        effect_labels = tuple(_static_effect_short_label(effect) for effect in weapon_effects)
        effect_labels = tuple(label for label in effect_labels if label)
        tooltip_effect_labels = tuple(
            _localized_static_effect_label(effect) for effect in weapon_effects
        )
        tooltip_effect_labels = tuple(label for label in tooltip_effect_labels if label)
        if effect_labels:
            refinement = _optional_int(account_weapon.get("refinement"))
            tooltip_title, tooltip_body = _weapon_tooltip_title_body(details)
            items.append(
                RightPanelBonusSourceDisplayItem(
                    source_kind="weapon_passive_static",
                    source_id=_text(account_weapon.get("id"))
                    or _text(account_weapon.get("weapon_id"))
                    or weapon_name,
                    label=f"R{refinement}" if refinement is not None else "WPN",
                    icon_path=_text(account_weapon.get("icon_path")),
                    short_effects=effect_labels,
                    tooltip_effects=tooltip_effect_labels,
                    tooltip_title=tooltip_title,
                    tooltip_body=tooltip_body,
                    applied=bool(external_bonuses_enabled),
                    not_applied_reason=(
                        "" if external_bonuses_enabled else _external_bonuses_disabled_text()
                    ),
                )
            )
    return items


def _active_set_context(
    details: Mapping[str, Any],
    *,
    artifact: TeamCardArtifactSummaryViewModel | None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _build_mini_sets(details):
        result[item.set_uid] = {
            "set_name": item.set_name,
            "piece_count": item.piece_count,
            "icon_path": item.icon_path,
        }
    if artifact is not None:
        for label in artifact.active_sets:
            piece_count = _piece_count(label)
            name = label[3:].strip() if label[:2] in {"2p", "4p"} else label
            for context in result.values():
                if not context.get("set_name") and name:
                    context["set_name"] = name
    return result


def _static_effect_short_label(effect: Mapping[str, Any]) -> str:
    stat_key = _text(effect.get("stat_key")).upper()
    value = _optional_float(effect.get("value"))
    value_type = _text(effect.get("value_type"))
    if not stat_key or value is None:
        return ""
    label = _STATIC_EFFECT_LABELS.get(stat_key, _short_stat_label(stat_key))
    suffix = "%" if value_type == "percent_points" else ""
    return f"{label} +{value:g}{suffix}"


def _localized_static_effect_label(effect: Mapping[str, Any]) -> str:
    stat_key = _text(effect.get("stat_key")).upper()
    value = _optional_float(effect.get("value"))
    value_type = _text(effect.get("value_type"))
    if not stat_key or value is None:
        return ""
    locale_key = _STATIC_EFFECT_LOCALE_KEYS.get(stat_key)
    label = tr(locale_key) if locale_key else _STATIC_EFFECT_LABELS.get(
        stat_key,
        _short_stat_label(stat_key),
    )
    suffix = "%" if value_type == "percent_points" else ""
    return f"{label} +{value:g}{suffix}"


def build_abyss_chamber_rows(
    timer_states: tuple[AbyssTimerState, ...],
    *,
    abyss_source_data: AbyssFloorSourceData | None = None,
) -> tuple[RightPanelChamberRowViewModel, ...]:
    return tuple(
        _abyss_chamber_row(
            timer_state,
            chamber_index=index,
            abyss_source_data=abyss_source_data,
        )
        for index, timer_state in enumerate(timer_states, start=1)
    )


def _abyss_chamber_row(
    timer_state: AbyssTimerState,
    *,
    chamber_index: int,
    abyss_source_data: AbyssFloorSourceData | None = None,
) -> RightPanelChamberRowViewModel:
    result = calculate_abyss_chamber_result(
        timer_state,
        chamber_index=chamber_index,
    )
    normalized = result.normalized_timer_state
    team1_summary = _cached_side_summary(abyss_source_data, chamber_index, 1)
    team2_summary = _cached_side_summary(abyss_source_data, chamber_index, 2)
    team1_dps = calculate_factual_dps(
        total_hp=None if team1_summary is None else team1_summary.solo_target_hp,
        elapsed_seconds=result.team1_elapsed_seconds,
    )
    team2_dps = calculate_factual_dps(
        total_hp=None if team2_summary is None else team2_summary.solo_target_hp,
        elapsed_seconds=result.team2_elapsed_seconds,
    )
    return RightPanelChamberRowViewModel(
        chamber_label=f"C{chamber_index}",
        team1_time=_format_remaining_time(normalized.team1_left_seconds),
        team1_seconds=result.team1_elapsed_seconds,
        team2_time=_format_remaining_time(normalized.team2_left_seconds),
        team2_seconds=result.team2_elapsed_seconds,
        factual_team1=_format_factual_dps_cell(team1_dps),
        factual_team2=_format_factual_dps_cell(team2_dps),
        factual_team1_tooltip=_build_fact_dps_tooltip(
            source_data=abyss_source_data,
            side_summary=team1_summary,
            chamber_index=chamber_index,
            team_number=1,
            elapsed_seconds=result.team1_elapsed_seconds,
            dps_result=team1_dps,
        ),
        factual_team2_tooltip=_build_fact_dps_tooltip(
            source_data=abyss_source_data,
            side_summary=team2_summary,
            chamber_index=chamber_index,
            team_number=2,
            elapsed_seconds=result.team2_elapsed_seconds,
            dps_result=team2_dps,
        ),
        sim_team1="not run",
        sim_team2="not run",
        total_seconds=result.total_elapsed_seconds,
        timer_editable=True,
    )


def _cached_side_summary(
    abyss_source_data: AbyssFloorSourceData | None,
    chamber_index: int,
    side: int,
) -> AbyssChamberSideSourceData | None:
    if abyss_source_data is None:
        return None
    try:
        return abyss_source_data.side_summary(chamber_index, side)
    except ValueError:
        return None


def _build_fact_dps_tooltip(
    *,
    source_data: AbyssFloorSourceData | None,
    side_summary: AbyssChamberSideSourceData | None,
    chamber_index: int,
    team_number: int,
    elapsed_seconds: int,
    dps_result,
) -> FactDpsTooltipViewModel:
    total_hp = None if side_summary is None else side_summary.solo_target_hp
    warnings = _fact_dps_tooltip_warnings(source_data, side_summary)
    return FactDpsTooltipViewModel(
        title=f"Floor 12 / C{chamber_index} / Team {team_number}",
        formula="Fact DPS = solo target HP / elapsed time",
        total_solo_hp=total_hp,
        elapsed_seconds=int(elapsed_seconds),
        calculated_dps=dps_result.rounded_dps,
        hp_source_label=_fact_dps_hp_source_label(side_summary),
        unavailable_reason=_fact_dps_unavailable_reason(
            source_data=source_data,
            side_summary=side_summary,
            dps_unavailable_reason=dps_result.unavailable_reason,
        ),
        warnings=warnings,
        enemies=_fact_dps_enemy_tooltip_rows(side_summary),
    )


def _fact_dps_unavailable_reason(
    *,
    source_data: AbyssFloorSourceData | None,
    side_summary: AbyssChamberSideSourceData | None,
    dps_unavailable_reason: str,
) -> str:
    if source_data is None:
        return "Abyss source-data cache is unavailable."
    if side_summary is None:
        return "Abyss source-data has no cached data for this chamber side."
    if dps_unavailable_reason == REASON_ZERO_OR_NEGATIVE_TIME:
        return "Elapsed time is zero."
    if dps_unavailable_reason == REASON_MISSING_HP:
        return "Solo target HP is unavailable."
    return ""


def _fact_dps_hp_source_label(
    side_summary: AbyssChamberSideSourceData | None,
) -> str:
    if side_summary is None:
        return "Unavailable"
    sources = {
        row.hp_source
        for wave in side_summary.waves
        for row in wave.enemies
        if row.hp_source
    }
    if HP_SOURCE_NANOKA_RESOLVED in sources:
        return "Nanoka resolved HP"
    if HP_SOURCE_UNAVAILABLE in sources or not sources:
        return "Unavailable"
    return ", ".join(sorted(sources))


def _fact_dps_tooltip_warnings(
    source_data: AbyssFloorSourceData | None,
    side_summary: AbyssChamberSideSourceData | None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if source_data is not None:
        warnings.extend(source_data.global_warnings)
    if side_summary is not None:
        warnings.extend(side_summary.warnings)
        for wave in side_summary.waves:
            warnings.extend(wave.warnings)
            for row in wave.enemies:
                warnings.extend(row.warnings)
                if row.match_confidence and row.match_confidence != "high":
                    warnings.append(
                        f"match_{row.match_method}_{row.match_confidence}"
                    )
    return tuple(dict.fromkeys(warnings))


def _fact_dps_enemy_tooltip_rows(
    side_summary: AbyssChamberSideSourceData | None,
) -> tuple[FactDpsEnemyTooltipViewModel, ...]:
    if side_summary is None:
        return ()
    rows: list[FactDpsEnemyTooltipViewModel] = []
    for wave in side_summary.waves:
        for row in wave.enemies:
            rows.append(
                FactDpsEnemyTooltipViewModel(
                    wave=wave.wave,
                    primary_display_name=row.primary_display_name,
                    enemy_count=row.enemy_count,
                    display_level=row.display_level,
                    matched_nanoka_display_name=row.matched_nanoka_display_name,
                    hp_used=row.nanoka_hp,
                    hp_source=row.hp_source,
                    match_method=row.match_method,
                    match_confidence=row.match_confidence,
                    cached_icon_path=row.cached_icon_path,
                    selected_for_solo=(
                        row.nanoka_hp is not None
                        and row.primary_display_name == wave.selected_solo_enemy_name
                    ),
                    warnings=row.warnings,
                )
            )
    return tuple(rows)


def _format_factual_dps_cell(result) -> str:
    if not result.is_available or result.rounded_dps is None:
        return "-"
    return f"{result.rounded_dps:,}"


def _format_remaining_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _external_bonuses_disabled_text() -> str:
    return tr("right_panel.bonus_tooltip.external_bonuses_disabled")


def _team_bonus_members(team: Any) -> tuple[_TeamBonusMember, ...]:
    members: list[_TeamBonusMember] = []
    for slot in getattr(team, "slots", ()):
        if getattr(slot, "character", None) is None:
            continue
        details = _details_dict(getattr(slot, "character_details_data", None))
        account_character = _account_character_for_slot(slot, details)
        traits = tuple(
            _normalize_token(item)
            for item in (account_character.get("traits") or [])
            if _normalize_token(item)
        )
        members.append(
            _TeamBonusMember(
                slot_index=int(getattr(slot, "slot_index", 0)),
                name=_text(account_character.get("name")) or "Character",
                element=_normalize_token(account_character.get("element")),
                traits=traits,
                icon_path=_text(
                    account_character.get("side_icon_path")
                    or account_character.get("portrait_path")
                ),
                details=details,
                hoyowiki_entry_id=_text(account_character.get("hoyowiki_entry_id")),
                constellation=_optional_int(account_character.get("constellation")),
            )
        )
    return tuple(members)


def _selected_team_bonus_member(
    members: tuple[_TeamBonusMember, ...],
    *,
    selected_slot_index: int,
) -> _TeamBonusMember | None:
    return next(
        (member for member in members if member.slot_index == int(selected_slot_index)),
        None,
    )


def _elemental_resonance_effect_rows(
    members: tuple[_TeamBonusMember, ...],
    *,
    selected_member: _TeamBonusMember | None,
) -> tuple[dict[str, Any], ...]:
    counts = Counter(member.element for member in members if member.element)
    effects: list[dict[str, Any]] = []
    for element, count in counts.items():
        if count < 2:
            continue
        if element == "pyro":
            effects.append(_team_bonus_effect("pyro", "ATK_PERCENT", 25, "ATK +25%"))
        elif element == "hydro":
            effects.append(_team_bonus_effect("hydro", "HP_PERCENT", 25, "HP +25%"))
        elif element == "cryo":
            effects.append(_team_bonus_effect("cryo", "CRIT_RATE", 15, "CR +15%"))
        elif element == "geo" and selected_member is not None:
            stat_key = ELEMENT_TO_DMG_STAT_KEY.get(selected_member.element)
            if stat_key:
                label = _STATIC_EFFECT_LABELS.get(stat_key, selected_member.element.title())
                effects.append(_team_bonus_effect("geo", stat_key, 15, f"{label} +15%"))
        elif element == "dendro":
            value = _dendro_resonance_em_value(counts)
            effects.append(_team_bonus_effect("dendro", "ELEMENTAL_MASTERY", value, f"EM +{value:g}"))
    return tuple(effects)


def _team_bonus_effect(
    element: str,
    stat_key: str,
    value: float,
    short_label: str,
) -> dict[str, Any]:
    return {
        "source_kind": "elemental_resonance",
        "source_id": f"{element}_resonance",
        "element": element,
        "stat_key": stat_key,
        "value": value,
        "value_type": "percent_points" if stat_key != "ELEMENTAL_MASTERY" else "flat",
        "short_label": short_label,
    }


def _dendro_resonance_em_value(counts: Counter[str]) -> float:
    value = 50.0
    has_pyro = counts.get("pyro", 0) > 0
    has_hydro = counts.get("hydro", 0) > 0
    has_electro = counts.get("electro", 0) > 0
    if has_pyro or has_hydro or has_electro:
        value += 30.0
    if has_electro or (has_hydro and has_pyro):
        value += 20.0
    return value


def _team_bonus_source_items(
    members: tuple[_TeamBonusMember, ...],
    *,
    selected_member: _TeamBonusMember | None,
    elemental_effects: tuple[dict[str, Any], ...],
    external_bonuses_enabled: bool,
) -> tuple[RightPanelBonusSourceDisplayItem, ...]:
    total_start = perf_now()
    items: list[RightPanelBonusSourceDisplayItem] = []
    resonance_start = perf_now()
    for effect in elemental_effects:
        element = _text(effect.get("element"))
        short_label = _text(effect.get("short_label"))
        items.append(
            RightPanelBonusSourceDisplayItem(
                source_kind="elemental_resonance",
                source_id=_text(effect.get("source_id")),
                label="Res",
                icon_path=_team_bonus_icon(ELEMENT_RESONANCE_ICONS.get(element, "")),
                short_effects=(short_label,) if short_label else (),
                tooltip_title=f"{element.title()} Resonance",
                tooltip_body=_elemental_resonance_tooltip(effect, selected_member),
                applied=bool(external_bonuses_enabled),
                not_applied_reason=(
                    "" if external_bonuses_enabled else _external_bonuses_disabled_text()
                ),
            )
        )
    resonance_ms = perf_ms(resonance_start)

    moonsign_start = perf_now()
    moonsign_item = _moonsign_bonus_item(
        members,
        external_bonuses_enabled=external_bonuses_enabled,
    )
    if moonsign_item is not None:
        items.append(moonsign_item)
    moonsign_ms = perf_ms(moonsign_start)

    hexerei_start = perf_now()
    hexerei_item = _hexerei_bonus_item(members)
    if hexerei_item is not None:
        items.append(hexerei_item)
    hexerei_ms = perf_ms(hexerei_start)
    log_perf(
        "team_bonus_sources",
        total=perf_ms(total_start),
        resonance=resonance_ms,
        moonsign=moonsign_ms,
        hexerei=hexerei_ms,
        count=len(items),
    )
    return tuple(items)


def _elemental_resonance_tooltip(
    effect: Mapping[str, Any],
    selected_member: _TeamBonusMember | None,
) -> str:
    element = _text(effect.get("element")).title()
    label = _text(effect.get("short_label"))
    if _text(effect.get("element")) == "dendro":
        return (
            "Simplified rule: 2 Dendro gives EM +50; Pyro/Hydro/Electro adds "
            "+30; Electro or Hydro+Pyro adds another +20."
        )
    if _text(effect.get("element")) == "geo":
        target = selected_member.element.title() if selected_member else "selected"
        return f"Applies to the selected character's {target} DMG Bonus."
    return "Direct display-stat elemental resonance bonus."


def _moonsign_bonus_item(
    members: tuple[_TeamBonusMember, ...],
    *,
    external_bonuses_enabled: bool,
) -> RightPanelBonusSourceDisplayItem | None:
    moonsign_members = [
        member for member in members if TRAIT_MOONSIGN in set(member.traits)
    ]
    if len(moonsign_members) < 2:
        return None
    has_non_moonsign = any(TRAIT_MOONSIGN not in set(member.traits) for member in members)
    value, total_before_cap, contribution_lines = (
        _moonsign_lunar_bonus(
            members,
            external_bonuses_enabled=external_bonuses_enabled,
        )
        if has_non_moonsign
        else (0.0, 0.0, ())
    )
    applied = bool(external_bonuses_enabled)
    reason = ""
    if not external_bonuses_enabled:
        reason = _external_bonuses_disabled_text()
    body_lines = [
        (
            "Считается после прямых внешних бонусов."
            if external_bonuses_enabled
            else "Считается без внешних бонусов, потому что они отключены."
        ),
        "Нужны минимум 2 Moonsign персонажа.",
        "Для ненулевого бонуса нужен хотя бы один персонаж без Moonsign.",
        f"До лимита: {_format_bonus_percent(total_before_cap)}; лимит: 36%.",
        "Это индикатор Lunar Reaction DMG, не строка обычного elemental DMG.",
    ]
    if contribution_lines:
        body_lines.append("Вклад:")
        body_lines.extend(contribution_lines)
    return RightPanelBonusSourceDisplayItem(
        source_kind="moonsign",
        source_id="moonsign_lunar_reaction_bonus",
        label="Lunar",
        icon_path=_team_bonus_icon("Moonsign.png"),
        short_effects=(f"Lunar +{_format_bonus_percent(value)}",),
        tooltip_title="Moonsign",
        tooltip_body="\n".join(body_lines),
        applied=applied,
        not_applied_reason=reason,
        character_icons=tuple(member.icon_path for member in moonsign_members if member.icon_path),
    )


def _moonsign_lunar_bonus(
    members: tuple[_TeamBonusMember, ...],
    *,
    external_bonuses_enabled: bool,
) -> tuple[float, float, tuple[str, ...]]:
    total = 0.0
    lines: list[str] = []
    for member in members:
        stats = _member_display_stats_for_lunar(
            member,
            members=members,
            external_bonuses_enabled=external_bonuses_enabled,
        )
        contribution = 0.0
        stat_label = ""
        stat_key = ""
        stat_value = 0.0
        if member.element in {"pyro", "electro", "cryo"}:
            stat_key = "atk"
            stat_label = "ATK"
            stat_value = stats.get("atk", 0.0)
            contribution = stat_value / 100.0 * 0.9
        elif member.element == "hydro":
            stat_key = "hp"
            stat_label = "HP"
            stat_value = stats.get("hp", 0.0)
            contribution = stat_value / 1000.0 * 0.6
        elif member.element == "geo":
            stat_key = "def"
            stat_label = "DEF"
            stat_value = stats.get("def", 0.0)
            contribution = stat_value / 100.0
        elif member.element in {"anemo", "dendro"}:
            stat_key = "em"
            stat_label = "EM"
            stat_value = stats.get("em", 0.0)
            contribution = stat_value / 100.0 * 2.25
        if stat_key:
            lines.append(
                f"{member.name}: {member.element.title()} {stat_label} "
                f"{_format_numeric(stat_value)} -> +{_format_bonus_percent(contribution)}"
            )
        total += contribution
    return min(36.0, total), total, tuple(lines)


def _member_display_stats_for_lunar(
    member: _TeamBonusMember,
    *,
    members: tuple[_TeamBonusMember, ...],
    external_bonuses_enabled: bool,
) -> dict[str, float]:
    data = dict(member.details)
    data["external_bonuses_enabled"] = bool(external_bonuses_enabled)
    data["team_bonus_display_stat_effects"] = (
        _elemental_resonance_effect_rows(members, selected_member=member)
        if external_bonuses_enabled
        else []
    )
    result = build_character_display_stats(data)
    return {
        row.key: _numeric_display_value(row.value)
        for row in result.rows
        if row.key in {"hp", "atk", "def", "em"}
    }


def _hexerei_bonus_item(
    members: tuple[_TeamBonusMember, ...],
) -> RightPanelBonusSourceDisplayItem | None:
    hexerei_members = [member for member in members if TRAIT_HEXEREI in set(member.traits)]
    if len(hexerei_members) < 2:
        return None
    names = ", ".join(member.name for member in hexerei_members)
    reference = hexerei_tooltip_reference()
    reference_body = reference.body.strip()
    source_url = reference.source_url or HEXEREI_SOURCE_URL
    missing_text = "Localized Hexerei bonus text is not cached yet."
    member_tooltips = _hexerei_member_tooltips(
        hexerei_members,
        fallback_reference=reference,
        fallback_body=reference_body,
        source_url=source_url,
        missing_text=missing_text,
    )
    tooltip_title, tooltip_body = _hexerei_source_tooltip_text(names)
    return RightPanelBonusSourceDisplayItem(
        source_kind="hexerei",
        source_id="hexerei_membership",
        label="Hexerei",
        icon_path=_team_bonus_icon("Hexerei.png"),
        short_effects=(),
        tooltip_title=tooltip_title,
        tooltip_body=tooltip_body,
        applied=True,
        character_icons=tuple(member.icon_path for member in hexerei_members if member.icon_path),
        character_tooltips=member_tooltips,
    )


def _hexerei_source_tooltip_text(
    names: str,
    *,
    language: str | None = None,
) -> tuple[str, str]:
    resolved_language = _hexerei_tooltip_locale(language or _account_content_language())
    return (
        tr_for_language(resolved_language, "right_panel.hexerei.tooltip_title"),
        tr_for_language(resolved_language, "right_panel.hexerei.source_tooltip_body"),
    )


def _hexerei_tooltip_locale(language: str | None) -> str:
    value = _text(language).replace("_", "-").casefold()
    if value.startswith("ru"):
        return "ru"
    if value in {"pt", "pt-br", "br"} or value.startswith("pt-"):
        return "pt-br"
    if value.startswith("en"):
        return "en"
    return "en"


def _hexerei_member_tooltips(
    members: list[_TeamBonusMember],
    *,
    fallback_reference: Any,
    fallback_body: str,
    source_url: str,
    missing_text: str,
) -> tuple[str, ...]:
    total_start = perf_now()
    result: list[str] = []
    language = _account_content_language()
    conn: sqlite3.Connection | None = None
    try:
        if ARTIFACT_DB_PATH.exists():
            conn = sqlite3.connect(ARTIFACT_DB_PATH)
            conn.row_factory = sqlite3.Row
        for member in members:
            if not member.icon_path:
                continue
            sections: tuple[dict[str, Any], ...] = ()
            if conn is not None and member.hoyowiki_entry_id:
                sections = get_hexerei_tooltip_sections(
                    conn,
                    character_entry_page_id=member.hoyowiki_entry_id,
                    account_constellation=member.constellation,
                    preferred_language=language,
                )
            text = _format_hexerei_sections_for_tooltip(sections)
            if not text:
                text = (
                    fallback_reference.text_for_member(name=member.name)
                    or fallback_body
                    or ""
                )
            result.append(
                _hexerei_member_tooltip(
                    member.name,
                    text,
                    source_url=source_url,
                    missing_text=missing_text,
                    constellation=member.constellation,
                )
            )
    except sqlite3.Error:
        result = [
            _hexerei_member_tooltip(
                member.name,
                fallback_reference.text_for_member(name=member.name)
                or fallback_body
                or "",
                source_url=source_url,
                missing_text=missing_text,
                constellation=member.constellation,
            )
            for member in members
            if member.icon_path
        ]
    finally:
        if conn is not None:
            conn.close()
    log_perf(
        "hexerei_tooltips",
        total=perf_ms(total_start),
        members=len(members),
    )
    return tuple(result)


def _format_hexerei_sections_for_tooltip(
    sections: tuple[dict[str, Any], ...],
) -> str:
    blocks: list[str] = []
    sorted_sections = sorted(
        sections,
        key=lambda section: (
            _optional_int(section.get("required_constellation")) or 0,
            _optional_int(section.get("section_index")) or 0,
        ),
    )
    for section in sorted_sections:
        body = _text(section.get("body"))
        if not body:
            continue
        constellation = _optional_int(section.get("required_constellation")) or 0
        paragraphs = [line.strip() for line in body.splitlines() if line.strip()]
        if not paragraphs:
            continue
        first, *rest = paragraphs
        block_lines = [f"C{constellation}: {first}"]
        block_lines.extend(rest)
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks)


def _hexerei_member_tooltip(
    name: str,
    text: str,
    *,
    source_url: str,
    missing_text: str,
    constellation: int | None = None,
) -> str:
    lines = [name]
    lines.append("")
    lines.append(text.strip() or missing_text)
    return "\n".join(lines)


def _team_bonus_icon(filename: str) -> str:
    return str(TEAM_BONUS_ICON_DIR / filename) if filename else ""


def _account_content_language() -> str:
    path = PROJECT_ROOT / "data" / "hoyolab" / "account_language.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "en-us"
    return _text(data.get("contentLanguage") or data.get("language") or "en-us") or "en-us"


def _format_bonus_percent(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def _format_numeric(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _numeric_display_value(value: str) -> float:
    try:
        return float(str(value or "").replace("%", "").replace(",", "").strip())
    except ValueError:
        return 0.0


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")


def _weapon_tooltip(details: Mapping[str, Any]) -> str:
    title, body = _weapon_tooltip_title_body(details)
    return "\n".join(line for line in (title, body) if line)


def _weapon_tooltip_title_body(details: Mapping[str, Any]) -> tuple[str, str]:
    account_weapon = _account_weapon_for_details(details)
    if not _has_weapon_reference(account_weapon):
        return "", ""
    weapon_name = _text(account_weapon.get("name"))
    refinement = _optional_int(account_weapon.get("refinement"))
    title = weapon_name
    if refinement is not None:
        title = f"{weapon_name} R{refinement}"
    lines: list[str] = []
    level = _optional_int(account_weapon.get("level"))
    meta: list[str] = []
    if level is not None:
        meta.append(f"Lv.{level}")
    base_atk = _weapon_base_atk_meta(details)
    if base_atk:
        meta.append(f"ATK {base_atk}")
    secondary_label, secondary_value = _weapon_secondary_meta(details)
    if secondary_label and secondary_value:
        meta.append(f"{secondary_label} {secondary_value}")
    if meta:
        lines.append(" · ".join(meta))
    passive_reference = _mapping(details.get("weapon_passive_reference"))
    passive_name = _text(passive_reference.get("passive_name"))
    passive_text = _text(passive_reference.get("passive_text"))
    if passive_name:
        lines.append(passive_name)
    if passive_text:
        lines.append(passive_text)
    return title, "\n".join(line for line in lines if line)


def _account_weapon_for_details(details: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(details.get("account_weapon")) or _mapping(
        _mapping(details.get("stat_snapshot")).get("weapon")
    )


def _has_weapon_reference(account_weapon: Mapping[str, Any]) -> bool:
    return bool(
        _text(account_weapon.get("id"))
        or _text(account_weapon.get("weapon_id"))
        or _text(account_weapon.get("name"))
    )


_STATIC_EFFECT_LABELS = {
    "HP_FLAT": "HP",
    "HP_PERCENT": "HP",
    "ATK_FLAT": "ATK",
    "ATK_PERCENT": "ATK",
    "DEF_FLAT": "DEF",
    "DEF_PERCENT": "DEF",
    "ELEMENTAL_MASTERY": "EM",
    "ENERGY_RECHARGE": "ER",
    "CRIT_RATE": "CR",
    "CRIT_DMG": "CD",
    "PYRO_DMG_BONUS": "Pyro",
    "HYDRO_DMG_BONUS": "Hydro",
    "ELECTRO_DMG_BONUS": "Electro",
    "CRYO_DMG_BONUS": "Cryo",
    "ANEMO_DMG_BONUS": "Anemo",
    "GEO_DMG_BONUS": "Geo",
    "DENDRO_DMG_BONUS": "Dendro",
    "PHYSICAL_DMG_BONUS": "Physical",
    "ALL_ELEMENTAL_DMG_BONUS": "All Elem",
    "HEALING_BONUS": "Healing",
}

_STATIC_EFFECT_LOCALE_KEYS = {
    "HP_FLAT": "artifact.stat.hp_flat",
    "HP_PERCENT": "artifact.stat.hp_percent",
    "ATK_FLAT": "artifact.stat.atk_flat",
    "ATK_PERCENT": "artifact.stat.atk_percent",
    "DEF_FLAT": "artifact.stat.def_flat",
    "DEF_PERCENT": "artifact.stat.def_percent",
    "ELEMENTAL_MASTERY": "artifact.stat.elemental_mastery",
    "ENERGY_RECHARGE": "artifact.stat.energy_recharge",
    "CRIT_RATE": "artifact.stat.crit_rate",
    "CRIT_DMG": "artifact.stat.crit_damage",
    "PYRO_DMG_BONUS": "artifact.stat.pyro_damage",
    "HYDRO_DMG_BONUS": "artifact.stat.hydro_damage",
    "ELECTRO_DMG_BONUS": "artifact.stat.electro_damage",
    "CRYO_DMG_BONUS": "artifact.stat.cryo_damage",
    "ANEMO_DMG_BONUS": "artifact.stat.anemo_damage",
    "GEO_DMG_BONUS": "artifact.stat.geo_damage",
    "DENDRO_DMG_BONUS": "artifact.stat.dendro_damage",
    "PHYSICAL_DMG_BONUS": "artifact.stat.physical_damage",
    "ALL_ELEMENTAL_DMG_BONUS": "artifact.stat.all_elemental_damage",
    "HEALING_BONUS": "artifact.stat.healing_bonus",
}


def _stat_rows(
    details: Mapping[str, Any],
    *,
    external_bonuses_enabled: bool,
) -> list[RightPanelDetailRowViewModel]:
    if not details:
        return []

    explicit_rows = _explicit_display_stat_rows(details)
    if explicit_rows:
        return explicit_rows

    stats_input = dict(details)
    stats_input["external_bonuses_enabled"] = bool(external_bonuses_enabled)
    display_start = perf_now()
    display_stats = build_character_display_stats(stats_input)
    display_ms = perf_ms(display_start)
    log_perf(
        "display_stats_calc",
        total=display_ms,
        rows=len(display_stats.rows),
    )
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
    account_weapon = _mapping(details.get("account_weapon"))
    account_base_atk = _text(account_weapon.get("base_atk_raw") or account_weapon.get("base_atk"))
    if account_base_atk:
        return account_base_atk

    snapshot_weapon = _snapshot_weapon(details)
    snapshot_base_atk = _selected_value(snapshot_weapon.get("base_atk"))
    if snapshot_base_atk:
        return snapshot_base_atk

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
        "artifact_build_incomplete": (
            "В выбранном билде нет одного или нескольких слотов артефактов; "
            "имеющиеся артефакты всё равно считаются."
        ),
        "duplicate_selected_character": "Персонаж выбран больше одного раза.",
    }
    return labels.get(str(warning or ""), str(warning or ""))


def _visible_slot_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    hidden = {
        "account_weapon_identity_no_source_instance_id",
        "account_weapon_observed_stack_not_full_inventory",
        "character_stats_unavailable",
        "conditional_set_bonuses_not_included",
        "final_totals_not_computed",
        "gcsim_config_generation_not_implemented",
        "set_bonus_formulas_not_included",
        "weapon_stats_unavailable",
    }
    return tuple(
        warning
        for warning in warnings
        if warning not in hidden
    )


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
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
