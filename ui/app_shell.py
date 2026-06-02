from __future__ import annotations

import json
import os
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import QEvent, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.account_equipment import (
    EquipmentChangeResult,
    EquipmentError,
    equip_weapon,
    get_equipped_weapon_for_character,
    list_equipped_artifacts_for_character,
    unequip_weapon,
)
from hoyolab_export.account_storage import get_account_weapon_observed_stack
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db
from hoyolab_export.display_stat_effects import (
    get_weapon_passive_tooltip,
    list_artifact_set_display_stat_effects_for_active_sets,
    list_weapon_display_stat_effects,
)
from hoyolab_export.paths import PROJECT_ROOT
from hoyolab_export.team_card_data import (
    BUILD_IDENTITY_SOURCE_CURRENT_EQUIPMENT,
    build_current_equipment_artifact_snapshot,
)
from localization import tr
from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    build_right_panel_prototype_view_model,
)
from run_workspace.team_builder import TeamBuilderState, create_empty_team_builder_state
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    CHARACTER_STANDARD_FILTER,
    CHARACTER_TRAIT_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    STANDARD_FILTER_ALL,
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    WEAPON_RARITY_FILTERS,
    WEAPON_TYPE_FILTERS,
    character_matches_filters,
    character_sort_key,
    load_account_character_asset_items,
    load_account_weapon_stack_asset_items,
    metadata_int,
    standard_character_filter_icon,
)
from ui.account_data_page import AccountDataPage
from ui.right_panel_prototype import (
    RIGHT_PANEL_PROTOTYPE_MIN_WIDTH,
    RunModeTabsWidget,
    RightPanelPrototypeWidget,
    make_mode_tab_button,
    right_panel_stylesheet,
)
from run_workspace.perf import log_perf, perf_ms, perf_now
from ui.utils.filter_button_style import (
    FILTER_BUTTON_ICON_SIZE,
    FILTER_BUTTON_SIZE,
    filter_button_style,
)
from ui.utils.hidpi_pixmap import (
    effective_pixmap_dpr,
    load_hidpi_pixmap,
    logical_pixmap_size,
)
from ui.utils.icon_utils import tinted_svg_pixmap
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.owner_icon_badge import (
    make_owner_icon_badge_background,
    owner_badge_rect_for_icon_rect,
    owner_badge_size_for_icon,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import (
    UI_ACCENT_TEAM_1,
    UI_ACCENT_TEAM_2,
    UI_EQUIPPED_WEAPON_ACCENT,
    UI_SELECTION_BADGE_FILL_ALPHA,
    UI_SELECTION_NEUTRAL_FILL,
    UI_SELECTION_NEUTRAL_FILL_ALPHA,
    UI_SELECTION_OUTLINE_ALPHA,
    UI_BG_APP,
    UI_TEXT_SECONDARY,
    UI_TEXT_ON_ACCENT,
)


RIGHT_OPERATIONS_DOCK_WIDTH = RIGHT_PANEL_PROTOTYPE_MIN_WIDTH
RIGHT_DOCK_PAGE_RUN = "run"
RIGHT_DOCK_PAGE_ACCOUNT = "account"
RIGHT_DOCK_ACCOUNT_ICON_SIZE = 18
LEFT_WORKSPACE_CHARACTERS_WEAPONS = "characters_weapons"
LEFT_WORKSPACE_ARTIFACTS = "artifacts"

# Calibrated global shell minimum for the embedded Artifact Browser footprint.
# This is intentionally a top-level contract, not a dynamic maximum of current
# QStackedWidget/minimumSizeHint states. It should fit the Artifact Browser with
# one artifact grid cell, Assignment, preset/current-equipment panel, at least
# one fully visible preset row / readable no-target hint, and the full build
# preview block without vertical squeezing.
APP_SHELL_MIN_WIDTH = 1408
APP_SHELL_MIN_HEIGHT = 640
APP_SHELL_INITIAL_SIZE = QSize(APP_SHELL_MIN_WIDTH, APP_SHELL_MIN_HEIGHT)
RIGHT_PANEL_REFRESH_DEBOUNCE_MS = 30
RIGHT_PANEL_FAST_REFRESH_MS = 1
WEAPON_FILTER_SYNC_DEBOUNCE_MS = 80
PERSISTENT_EQUIPMENT_HYDRATION_DELAY_MS = 40
MODE_TEAM_COUNTS = {
    MODE_ABYSS: 2,
    MODE_DPS_DUMMY: 1,
}
TEAM_MARKER_COLORS = (UI_ACCENT_TEAM_1, UI_ACCENT_TEAM_2)
_SCALED_ICON_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}
_OWNER_BADGE_ICON_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}
_OWNER_BADGE_BACKGROUND_CACHE: dict[tuple[int, int, int], QPixmap] = {}
OWNER_BADGE_TRACE = os.environ.get("GTT_OWNER_BADGE_TRACE", "").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
WEAPON_OWNER_OVERLAY_TRACE = os.environ.get(
    "GTT_WEAPON_OWNER_OVERLAY_TRACE",
    "",
).strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
# Calibrated after fixing the previous double-downscale bug: the accepted visual
# placed a 45px side-icon at x=17/y=-22 relative to a 48px weapon card.
WEAPON_PICKER_OWNER_SIDE_ICON_RATIO = 45 / 48
WEAPON_PICKER_OWNER_RIGHT_OVERHANG_RATIO = 14 / 45
WEAPON_PICKER_OWNER_TOP_OVERHANG_RATIO = 22 / 45
WEAPON_PICKER_ICON_SIZE = 48
WEAPON_PICKER_SAFE_MARGIN = 6
WEAPON_PICKER_VIEWPORT_TOP_EXTENSION = 6
WEAPON_PICKER_OCCUPIED_OUTLINE_COLOR = UI_EQUIPPED_WEAPON_ACCENT
GRID_SELECTION_OUTLINE_ALPHA = UI_SELECTION_OUTLINE_ALPHA
GRID_SELECTION_BADGE_FILL_ALPHA = UI_SELECTION_BADGE_FILL_ALPHA
GRID_SELECTION_OUTLINE_WIDTH = 4
GRID_SELECTION_OUTLINE_OVERHANG = 1
GRID_SELECTION_OUTLINE_RADIUS = 3
CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN = 4
GRID_SELECTION_BADGE_WIDTH = 24
GRID_SELECTION_BADGE_HEIGHT = 20
GRID_SELECTION_BADGE_MARGIN = 4
WEAPON_PICKER_OCCUPIED_FILL_COLOR = UI_SELECTION_NEUTRAL_FILL
WEAPON_PICKER_OCCUPIED_FILL_ALPHA = UI_SELECTION_NEUTRAL_FILL_ALPHA
WEAPON_TYPE_FILTER_BY_ID = {
    1: "sword",
    10: "catalyst",
    11: "claymore",
    12: "bow",
    13: "polearm",
}
WEAPON_TYPE_FILTER_ALIASES = {
    "sword": "sword",
    "one_handed_sword": "sword",
    "catalyst": "catalyst",
    "claymore": "claymore",
    "bow": "bow",
    "polearm": "polearm",
}

FILTER_BUTTON_STYLE = filter_button_style("app_shell_filter_button")


@dataclass(frozen=True)
class RosterSelectionMarker:
    team_index: int
    slot_index: int
    slot_number: int
    color: str


@dataclass(frozen=True)
class CharacterPlacementResult:
    changed: bool = False
    added: bool = False
    removed: bool = False
    character_id: str = ""
    team_index: int = -1
    slot_index: int = -1


@dataclass
class PersistentEquipmentHydration:
    weapon: dict[str, Any] | None = None
    current_artifacts: dict[str, int] = field(default_factory=dict)
    artifact_snapshot: Any | None = None
    artifact_set_effects: list[dict[str, Any]] = field(default_factory=list)
    weapon_bonus_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppShellController:
    """Tiny boundary for the separate AppShell prototype."""

    state: TeamBuilderState
    equipment_db_path: str | Path = ARTIFACT_DB_PATH
    mode: str = MODE_ABYSS
    selected_team_index: int = -1
    selected_slot_index: int = -1
    external_bonuses_enabled: bool = True
    mode_states: dict[str, TeamBuilderState] = field(default_factory=dict)
    last_equipment_error: str = ""
    last_weapon_equipment_change_result: EquipmentChangeResult | None = None
    _persistent_equipment_cache: dict[str, PersistentEquipmentHydration] = field(
        default_factory=dict
    )

    @classmethod
    def empty(
        cls,
        *,
        equipment_db_path: str | Path = ARTIFACT_DB_PATH,
    ) -> "AppShellController":
        abyss_state = _empty_state_for_mode(MODE_ABYSS)
        return cls(
            state=abyss_state,
            equipment_db_path=equipment_db_path,
            mode=MODE_ABYSS,
            mode_states={
                MODE_ABYSS: abyss_state,
                MODE_DPS_DUMMY: _empty_state_for_mode(MODE_DPS_DUMMY),
            },
        )

    def __post_init__(self) -> None:
        self.mode = _normalize_mode(self.mode)
        if not self.mode_states:
            self.mode_states[self.mode] = self.state
        elif self.mode in self.mode_states:
            self.state = self.mode_states[self.mode]
        else:
            self.mode_states[self.mode] = self.state
        for mode in MODE_TEAM_COUNTS:
            self.mode_states.setdefault(mode, _empty_state_for_mode(mode))

    def right_panel_model(self):
        return build_right_panel_prototype_view_model(
            self.state,
            mode=self.mode,
            selected_team_index=self.selected_team_index,
            selected_slot_index=self.selected_slot_index,
            external_bonuses_enabled=self.external_bonuses_enabled,
        )

    def set_mode(self, mode: str) -> None:
        self._store_current_mode_state()
        self.mode = _normalize_mode(mode)
        self.state = self.mode_states.get(self.mode) or _empty_state_for_mode(self.mode)
        self.mode_states[self.mode] = self.state
        self.clear_selection()

    def toggle_slot_selection(self, team_index: int, slot_index: int) -> None:
        if (
            self.selected_team_index == int(team_index)
            and self.selected_slot_index == int(slot_index)
        ):
            self.clear_selection()
            return
        self.selected_team_index = int(team_index)
        self.selected_slot_index = int(slot_index)

    def clear_selection(self) -> None:
        self.selected_team_index = -1
        self.selected_slot_index = -1

    def swap_slots(
        self,
        source_team_index: int,
        source_slot_index: int,
        target_team_index: int,
        target_slot_index: int,
    ) -> bool:
        source_team_index = int(source_team_index)
        source_slot_index = int(source_slot_index)
        target_team_index = int(target_team_index)
        target_slot_index = int(target_slot_index)
        if (
            source_team_index == target_team_index
            and source_slot_index == target_slot_index
        ):
            return False
        try:
            source_slot = self.state.team(source_team_index).slot(source_slot_index)
            self.state.team(target_team_index).slot(target_slot_index)
        except IndexError:
            return False
        if source_slot.is_empty:
            return False
        self.state = self.state.swap_slots(
            source_team_index,
            source_slot_index,
            target_team_index,
            target_slot_index,
        )
        self.selected_team_index = target_team_index
        self.selected_slot_index = target_slot_index
        self._store_current_mode_state()
        return True

    def add_or_replace_character_fast(
        self,
        asset: dict[str, Any],
    ) -> CharacterPlacementResult:
        character = _asset_metadata_mapping(asset, "character")
        character_id = _text(character.get("id"))
        if not character_id:
            return CharacterPlacementResult()

        existing_slot = self._find_character_slot(character_id)
        if existing_slot is not None:
            team_index, slot_index = existing_slot
            self.state = self.state.clear_slot(team_index, slot_index)
            if (
                self.selected_team_index == team_index
                and self.selected_slot_index == slot_index
            ):
                self.clear_selection()
            self._store_current_mode_state()
            return CharacterPlacementResult(
                changed=True,
                removed=True,
                character_id=character_id,
                team_index=team_index,
                slot_index=slot_index,
            )

        target_slot = self._first_empty_slot()
        if target_slot is None:
            return CharacterPlacementResult()
        team_index, slot_index = target_slot

        self._set_character_minimal(
            team_index,
            slot_index,
            character,
            asset_path=_text(asset.get("path")),
        )
        self.selected_team_index = team_index
        self.selected_slot_index = slot_index
        self._store_current_mode_state()
        return CharacterPlacementResult(
            changed=True,
            added=True,
            character_id=character_id,
            team_index=team_index,
            slot_index=slot_index,
        )

    def add_or_replace_character(self, asset: dict[str, Any]) -> bool:
        result = self.add_or_replace_character_fast(asset)
        if result.added:
            self.hydrate_persistent_equipment_for_slot(
                result.team_index,
                result.slot_index,
                result.character_id,
            )
            self._store_current_mode_state()
        return result.changed

    def assign_weapon_to_selected_slot(self, asset: dict[str, Any]) -> bool:
        self.last_weapon_equipment_change_result = None
        if self.selected_team_index < 0 or self.selected_slot_index < 0:
            return False

        try:
            slot = self.state.team(self.selected_team_index).slot(self.selected_slot_index)
        except IndexError:
            return False
        if slot.character is None:
            return False

        weapon = _normalized_weapon_image_paths(
            _asset_metadata_mapping(asset, "weapon"),
            asset_path=_text(asset.get("path")),
        )
        if not weapon:
            return False

        details = dict(slot.character_details_data or {})
        character = _mapping(details.get("account_character")) or slot.character.to_dict()
        if not _weapon_matches_character(character, weapon):
            return False

        weapon_fingerprint = _weapon_equipment_fingerprint(weapon)
        if not weapon_fingerprint:
            self.last_equipment_error = "weapon_fingerprint_missing"
            return False
        character_id = _text(character.get("id")) or _text(slot.character.id)
        if not character_id:
            return False
        try:
            with self._equipment_connection() as conn:
                current_weapon = get_equipped_weapon_for_character(conn, character_id)
                if (
                    current_weapon is not None
                    and current_weapon.weapon_fingerprint == weapon_fingerprint
                ):
                    equipment_result = unequip_weapon(conn, character_id)
                else:
                    equipment_result = equip_weapon(conn, character_id, weapon_fingerprint)
                persisted_weapon = self._persistent_weapon_for_character(
                    conn,
                    character_id,
                    character,
                    preferred_weapon=weapon,
                )
                conn.commit()
        except EquipmentError as exc:
            self.last_equipment_error = str(exc)
            return False
        except Exception as exc:
            self.last_equipment_error = str(exc)
            return False

        self.last_weapon_equipment_change_result = equipment_result
        affected_character_ids = {
            _text(affected_character_id)
            for affected_character_id in equipment_result.affected_character_ids
            if _text(affected_character_id)
        }
        affected_character_ids.add(character_id)
        self.invalidate_persistent_equipment_cache(affected_character_ids)
        details["account_character"] = dict(character)
        if persisted_weapon:
            weapon = persisted_weapon
            self.state = self.state.set_weapon(
                self.selected_team_index,
                self.selected_slot_index,
                weapon,
            )
            details["account_weapon"] = dict(weapon)
            details["weapon_image_path"] = _text(weapon.get("icon_path"))
            details.update(_weapon_bonus_context(weapon, db_path=self.equipment_db_path))
        else:
            self.state = self.state.clear_weapon(
                self.selected_team_index,
                self.selected_slot_index,
            )
            details.pop("account_weapon", None)
            details.pop("weapon_image_path", None)
            details.update(
                {
                    "weapon_passive_reference": {},
                    "weapon_display_stat_effects": [],
                }
            )
        self.state = self.state.attach_character_details_data(
            self.selected_team_index,
            self.selected_slot_index,
            details,
        )
        self.last_equipment_error = ""
        self._store_current_mode_state()
        for affected_character_id in sorted(affected_character_ids - {character_id}):
            self.refresh_persistent_equipment_for_character(affected_character_id)
        return True

    def selected_character_weapon_filter_key(self) -> str:
        if self.selected_team_index < 0 or self.selected_slot_index < 0:
            return ""
        try:
            slot = self.state.team(self.selected_team_index).slot(self.selected_slot_index)
        except IndexError:
            return ""
        if slot.character is None:
            return ""
        details = _mapping(slot.character_details_data)
        character = _mapping(details.get("account_character")) or slot.character.to_dict()
        return _character_weapon_type_filter_key(character)

    def selected_operation_target(self) -> dict[str, Any] | None:
        if self.selected_team_index < 0 or self.selected_slot_index < 0:
            return None
        try:
            slot = self.state.team(self.selected_team_index).slot(self.selected_slot_index)
        except IndexError:
            return None
        if slot.character is None:
            return None
        details = _mapping(slot.character_details_data)
        character = _mapping(details.get("account_character")) or slot.character.to_dict()
        character_id = _text(character.get("id")) or _text(slot.character.id)
        if not character_id:
            return None
        try:
            normalized_character_id: int | str = int(character_id)
        except ValueError:
            normalized_character_id = character_id
        return {
            "character_id": normalized_character_id,
            "character_name": _text(character.get("name")) or _text(slot.character.name),
            "team_index": self.selected_team_index,
            "slot_index": self.selected_slot_index,
        }

    def selected_equipment_hydration_target(
        self,
    ) -> CharacterPlacementResult | None:
        if self.selected_team_index < 0 or self.selected_slot_index < 0:
            return None
        try:
            slot = self.state.team(self.selected_team_index).slot(self.selected_slot_index)
        except IndexError:
            return None
        if slot.character is None:
            return None
        details = _mapping(slot.character_details_data)
        if bool(details.get("persistent_equipment_hydrated")):
            return None
        character_id = _text(slot.character.id)
        if not character_id:
            return None
        return CharacterPlacementResult(
            changed=True,
            added=True,
            character_id=character_id,
            team_index=self.selected_team_index,
            slot_index=self.selected_slot_index,
        )

    def refresh_persistent_equipment_for_character(self, character_id: int | str) -> bool:
        character_id_text = _text(character_id)
        if not character_id_text:
            return False
        slot_location = self._find_character_slot(character_id_text)
        if slot_location is None:
            return False
        team_index, slot_index = slot_location
        slot = self.state.team(team_index).slot(slot_index)
        if slot.character is None:
            return False
        details = _mapping(slot.character_details_data)
        character = _mapping(details.get("account_character")) or slot.character.to_dict()
        asset_path = _text(
            details.get("portrait_path")
            or character.get("local_portrait_path")
            or character.get("portrait_path")
        )
        self.invalidate_persistent_equipment_cache({character_id_text})
        self._set_character_with_persistent_equipment(
            team_index,
            slot_index,
            character,
            asset_path=asset_path,
        )
        self._store_current_mode_state()
        return True

    def roster_selection_markers(self) -> dict[str, RosterSelectionMarker]:
        markers: dict[str, RosterSelectionMarker] = {}
        for team_index, team in enumerate(self.state.teams):
            for slot in team.slots:
                if slot.character is None:
                    continue
                character_id = _text(slot.character.id)
                if not character_id:
                    continue
                markers[character_id] = RosterSelectionMarker(
                    team_index=team_index,
                    slot_index=slot.slot_index,
                    slot_number=slot.slot_index + 1,
                    color=TEAM_MARKER_COLORS[team_index % len(TEAM_MARKER_COLORS)],
                )
        return markers

    def _first_empty_slot(self) -> tuple[int, int] | None:
        for team_index, team in enumerate(self.state.teams):
            for slot in team.slots:
                if slot.is_empty:
                    return team_index, slot.slot_index
        return None

    def _find_character_slot(self, character_id: str) -> tuple[int, int] | None:
        for team_index, team in enumerate(self.state.teams):
            for slot in team.slots:
                if slot.character is not None and _text(slot.character.id) == character_id:
                    return team_index, slot.slot_index
        return None

    def invalidate_persistent_equipment_cache(
        self,
        character_ids: set[str] | set[int] | None = None,
    ) -> None:
        if character_ids is None:
            self._persistent_equipment_cache.clear()
            return
        for character_id in character_ids:
            self._persistent_equipment_cache.pop(_text(character_id), None)

    def _set_character_with_persistent_equipment(
        self,
        team_index: int,
        slot_index: int,
        character: dict[str, Any],
        *,
        asset_path: str = "",
    ) -> None:
        character = self._set_character_minimal(
            team_index,
            slot_index,
            character,
            asset_path=asset_path,
        )
        self.hydrate_persistent_equipment_for_slot(
            team_index,
            slot_index,
            _text(character.get("id")),
        )

    def _set_character_minimal(
        self,
        team_index: int,
        slot_index: int,
        character: dict[str, Any],
        *,
        asset_path: str = "",
    ) -> dict[str, Any]:
        character = _normalized_character_image_paths(character, asset_path=asset_path)
        self.state = self.state.clear_slot(team_index, slot_index)
        self.state = self.state.set_character(team_index, slot_index, character)
        details: dict[str, Any] = {"account_character": dict(character)}
        portrait_path = _text(character.get("local_portrait_path") or character.get("portrait_path"))
        if portrait_path:
            details["portrait_path"] = portrait_path
        self.state = self.state.attach_character_details_data(team_index, slot_index, details)
        return character

    def hydrate_persistent_equipment_for_slot(
        self,
        team_index: int,
        slot_index: int,
        character_id: str,
        *,
        use_cache: bool = True,
    ) -> dict[str, float]:
        total_start = perf_now()
        character_id = _text(character_id)
        if not character_id:
            return {"hydration_total": perf_ms(total_start), "hydration_applied": 0.0}
        try:
            slot = self.state.team(team_index).slot(slot_index)
        except IndexError:
            return {"hydration_total": perf_ms(total_start), "hydration_applied": 0.0}
        if slot.character is None or _text(slot.character.id) != character_id:
            log_perf(
                "persistent_equipment_hydration",
                total=perf_ms(total_start),
                character=character_id,
                applied=False,
                stale=True,
            )
            return {"hydration_total": perf_ms(total_start), "hydration_applied": 0.0}
        details = _mapping(slot.character_details_data)
        character = _mapping(details.get("account_character")) or slot.character.to_dict()
        load_start = perf_now()
        hydration, load_timings = self._load_persistent_equipment(
            character_id,
            character,
            use_cache=use_cache,
        )
        load_ms = perf_ms(load_start)
        try:
            current_slot = self.state.team(team_index).slot(slot_index)
        except IndexError:
            return {"hydration_total": perf_ms(total_start), "hydration_applied": 0.0}
        if current_slot.character is None or _text(current_slot.character.id) != character_id:
            log_perf(
                "persistent_equipment_hydration",
                total=perf_ms(total_start),
                character=character_id,
                applied=False,
                stale=True,
                load=load_ms,
            )
            return {
                "hydration_total": perf_ms(total_start),
                "hydration_load": load_ms,
                "hydration_applied": 0.0,
            }

        attach_start = perf_now()
        details = dict(_mapping(current_slot.character_details_data))
        details["account_character"] = dict(character)
        for key in (
            "current_equipped_artifact_ids_by_slot",
            "selected_build",
            "stat_snapshot",
            "artifact_set_display_stat_effects",
            "warnings",
            "status",
            "weapon_passive_reference",
            "weapon_display_stat_effects",
        ):
            details.pop(key, None)
        source_notes = dict(_mapping(details.get("source_notes")))
        for key in (
            "current_equipped_artifacts_readonly",
            "current_equipment_artifact_snapshot",
            "current_equipment_snapshot_persisted_as_build",
        ):
            source_notes.pop(key, None)
        if source_notes:
            details["source_notes"] = source_notes
        else:
            details.pop("source_notes", None)

        if hydration.current_artifacts:
            details["current_equipped_artifact_ids_by_slot"] = dict(
                hydration.current_artifacts
            )
            details.setdefault("source_notes", {})[
                "current_equipped_artifacts_readonly"
            ] = True
        if hydration.artifact_snapshot is not None:
            _apply_current_artifact_snapshot_to_details(
                details,
                hydration.artifact_snapshot,
                artifact_set_effects=hydration.artifact_set_effects,
            )
        if hydration.weapon:
            self.state = self.state.set_weapon(team_index, slot_index, hydration.weapon)
            details["account_weapon"] = dict(hydration.weapon)
            if _text(hydration.weapon.get("icon_path")):
                details["weapon_image_path"] = _text(hydration.weapon.get("icon_path"))
            details.update(hydration.weapon_bonus_context)
        else:
            self.state = self.state.clear_weapon(team_index, slot_index)
            details.pop("account_weapon", None)
            details.pop("weapon_image_path", None)
            details.update(
                {
                    "weapon_passive_reference": {},
                    "weapon_display_stat_effects": [],
                }
            )
        details["persistent_equipment_hydrated"] = True
        self.state = self.state.attach_character_details_data(
            team_index,
            slot_index,
            details,
        )
        self._store_current_mode_state()
        attach_ms = perf_ms(attach_start)
        total_ms = perf_ms(total_start)
        timings = {
            "hydration_total": total_ms,
            "hydration_load": load_ms,
            "hydration_attach_details": attach_ms,
            "hydration_applied": 1.0,
            **load_timings,
        }
        log_perf(
            "persistent_equipment_hydration",
            total=total_ms,
            character=character_id,
            applied=True,
            **load_timings,
            attach_details=attach_ms,
        )
        return timings

    def _load_persistent_equipment(
        self,
        character_id: str,
        character: dict[str, Any],
        *,
        use_cache: bool = True,
    ) -> tuple[PersistentEquipmentHydration, dict[str, float]]:
        character_id = _text(character_id)
        if use_cache and character_id in self._persistent_equipment_cache:
            return self._persistent_equipment_cache[character_id], {
                "hydration_cache_hit": 1.0
            }

        timings: dict[str, float] = {"hydration_cache_hit": 0.0}
        connect_start = perf_now()
        conn = connect_db(self.equipment_db_path)
        timings["hydration_connect_db"] = perf_ms(connect_start)
        try:
            weapon_start = perf_now()
            session_weapon = self._persistent_weapon_for_character(
                conn,
                character_id,
                character,
            )
            timings["hydration_get_weapon"] = perf_ms(weapon_start)

            artifact_ids_start = perf_now()
            current_artifacts = self._persistent_artifact_ids_for_character(
                conn,
                character_id,
            )
            timings["hydration_get_artifact_ids"] = perf_ms(artifact_ids_start)

            artifact_snapshot = None
            artifact_set_effects: list[dict[str, Any]] = []
            if current_artifacts:
                snapshot_start = perf_now()
                artifact_snapshot = build_current_equipment_artifact_snapshot(
                    conn,
                    character_id,
                    build_name=tr("artifact.build.current_equipment"),
                )
                timings["hydration_build_artifact_snapshot"] = perf_ms(snapshot_start)

                effects_start = perf_now()
                artifact_set_effects = (
                    list_artifact_set_display_stat_effects_for_active_sets(
                        conn,
                        artifact_snapshot.to_dict().get("active_set_bonuses") or [],
                        preferred_lang=_account_content_language(),
                    )
                    if artifact_snapshot is not None
                    else []
                )
                timings["hydration_list_artifact_set_effects"] = perf_ms(effects_start)
            else:
                timings["hydration_build_artifact_snapshot"] = 0.0
                timings["hydration_list_artifact_set_effects"] = 0.0

            weapon_bonus_start = perf_now()
            weapon_bonus_context = (
                _weapon_bonus_context_from_conn(conn, session_weapon)
                if session_weapon
                else {
                    "weapon_passive_reference": {},
                    "weapon_display_stat_effects": [],
                }
            )
            timings["hydration_weapon_bonus_context"] = perf_ms(weapon_bonus_start)
        finally:
            conn.close()

        hydration = PersistentEquipmentHydration(
            weapon=session_weapon,
            current_artifacts=dict(current_artifacts),
            artifact_snapshot=artifact_snapshot,
            artifact_set_effects=[dict(item) for item in artifact_set_effects],
            weapon_bonus_context=dict(weapon_bonus_context),
        )
        if use_cache:
            self._persistent_equipment_cache[character_id] = hydration
        return hydration, timings

    def _equipment_connection(self):
        return closing(connect_db(self.equipment_db_path))

    def _persistent_weapon_for_character(
        self,
        conn,
        character_id: str,
        character: dict[str, Any],
        *,
        preferred_weapon: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not character_id:
            return None
        record = get_equipped_weapon_for_character(conn, character_id)
        if record is None:
            return None
        stack = get_account_weapon_observed_stack(conn, record.weapon_fingerprint)
        if stack is None:
            return None
        weapon = stack.to_team_builder_weapon_ref()
        if preferred_weapon:
            preferred_path = _text(preferred_weapon.get("icon_path"))
            if preferred_path:
                weapon["icon_path"] = preferred_path
                weapon["local_icon_path"] = preferred_path
        weapon = _normalized_weapon_image_paths(weapon)
        if not _weapon_matches_character(character, weapon):
            return None
        return weapon

    def _persistent_artifact_ids_for_character(
        self,
        conn,
        character_id: str,
    ) -> dict[str, int]:
        if not character_id:
            return {}
        try:
            records = list_equipped_artifacts_for_character(conn, character_id)
        except EquipmentError:
            return {}
        return {
            record.slot_key: record.artifact_id
            for record in records
        }

    def _store_current_mode_state(self) -> None:
        self.mode_states[self.mode] = self.state


def _apply_current_artifact_snapshot_to_details(
    details: dict[str, Any],
    artifact_snapshot,
    *,
    artifact_set_effects: list[dict[str, Any]],
) -> None:
    summary = artifact_snapshot.to_dict()
    warnings = [str(item) for item in artifact_snapshot.warnings if str(item)]
    details["selected_build"] = {
        "build_id": None,
        "build_name": artifact_snapshot.build_name,
        "identity_source": BUILD_IDENTITY_SOURCE_CURRENT_EQUIPMENT,
        "provenance_note": (
            "Current equipment is runtime SQLite state, not an artifact_build preset."
        ),
    }
    details["stat_snapshot"] = {
        "artifact": {
            "summary": summary,
            "warnings": warnings,
        }
    }
    details["artifact_set_display_stat_effects"] = [
        dict(item)
        for item in artifact_set_effects
    ]
    details["warnings"] = _dedupe(
        [
            *[str(item) for item in details.get("warnings") or []],
            *warnings,
        ]
    )
    details["status"] = "partial" if warnings else "ready"
    source_notes = details.setdefault("source_notes", {})
    source_notes["current_equipment_artifact_snapshot"] = True
    source_notes["current_equipment_snapshot_persisted_as_build"] = False


class AppShell(QWidget):
    """Prototype entrypoint for the future app shell.

    The legacy `ui.main_window.App` remains the production `main.py` target for
    now. This shell is separately launchable for visual inspection.
    """

    def __init__(
        self,
        controller: AppShellController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller or AppShellController.empty()
        self.setWindowTitle(tr("app_shell.title"))
        self.setMinimumSize(APP_SHELL_MIN_WIDTH, APP_SHELL_MIN_HEIGHT)
        self.resize(APP_SHELL_INITIAL_SIZE)

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self.left_host = LeftWorkspaceHost(
            artifact_db_path=self.controller.equipment_db_path,
            artifact_equipment_changed=self._on_artifact_browser_equipment_changed,
        )
        root.addWidget(self.left_host, 1)

        self.right_panel = RightPanelPrototypeWidget(
            self.controller.right_panel_model(),
            show_mode_tabs=False,
        )
        self.right_dock = RightOperationsDock(
            self.right_panel,
            active_mode=self.controller.mode,
        )
        root.addWidget(self.right_dock, 0)
        self.right_dock.account_page.account_data_changed.connect(
            self._on_account_data_changed
        )
        self.right_dock.account_page.language_changed.connect(self.retranslate_ui)

        self._right_panel_refresh_pending = False
        self._right_panel_refresh_timer = QTimer(self)
        self._right_panel_refresh_timer.setSingleShot(True)
        self._right_panel_refresh_timer.timeout.connect(
            self.flush_pending_right_panel_refresh
        )
        self._weapon_filter_sync_pending = False
        self._weapon_filter_sync_timer = QTimer(self)
        self._weapon_filter_sync_timer.setSingleShot(True)
        self._weapon_filter_sync_timer.timeout.connect(
            self.flush_pending_weapon_filter_sync
        )
        self._equipment_hydration_pending: CharacterPlacementResult | None = None
        self._equipment_hydration_generation = 0
        self._equipment_hydration_timer = QTimer(self)
        self._equipment_hydration_timer.setSingleShot(True)
        self._equipment_hydration_timer.timeout.connect(
            self.flush_pending_equipment_hydration
        )
        self._resize_event_count = 0
        self._resize_settle_timer = QTimer(self)
        self._resize_settle_timer.setSingleShot(True)
        self._resize_settle_timer.timeout.connect(
            lambda: self._log_resize_geometry("settled")
        )

        self.right_dock.mode_requested.connect(self._on_mode_requested)
        self.right_panel.slot_selected.connect(self._on_slot_selected)
        self.right_panel.slot_dropped.connect(self._on_slot_dropped)
        self.right_panel.external_bonuses_toggled.connect(
            self._on_external_bonuses_toggled
        )
        self.left_host.character_weapon_workspace.character_clicked.connect(
            self._on_character_clicked
        )
        self.left_host.character_weapon_workspace.weapon_clicked.connect(
            self._on_weapon_clicked
        )
        self.left_host.workspace_requested.connect(self._on_workspace_requested)
        self.left_host.workspace_activated.connect(self._on_workspace_activated)
        self.active_left_workspace_id = self.left_host.active_workspace_id()
        self._refresh_character_selection_markers()
        self._sync_artifact_browser_operation_target()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("app_shell.title"))
        self.left_host.retranslate_ui()
        self.right_dock.retranslate_ui()
        self._refresh_right_panel()

    def resizeEvent(self, event) -> None:
        if not hasattr(self, "left_host") or not hasattr(self, "_resize_settle_timer"):
            super().resizeEvent(event)
            return
        self._resize_event_count += 1
        self._log_resize_geometry(
            "before",
            old_size=event.oldSize(),
            new_size=event.size(),
        )
        super().resizeEvent(event)
        self._log_resize_geometry(
            "during",
            old_size=event.oldSize(),
            new_size=event.size(),
        )
        self._resize_settle_timer.start(120)

    def _log_resize_geometry(
        self,
        phase: str,
        *,
        old_size: QSize | None = None,
        new_size: QSize | None = None,
    ) -> None:
        current_widget = self.left_host.stack.currentWidget()
        current_name = type(current_widget).__name__ if current_widget is not None else "-"
        current_min_hint = (
            current_widget.minimumSizeHint()
            if current_widget is not None
            else QSize()
        )
        geom = self.geometry()
        frame = self.frameGeometry()
        right_geom = self.right_dock.geometry()
        log_perf(
            "app_shell_resize",
            phase=phase,
            count=self._resize_event_count,
            old=f"{old_size.width()}x{old_size.height()}" if old_size else "-",
            new=f"{new_size.width()}x{new_size.height()}" if new_size else "-",
            geom=f"{geom.x()},{geom.y()} {geom.width()}x{geom.height()}",
            frame=f"{frame.x()},{frame.y()} {frame.width()}x{frame.height()}",
            min=f"{self.minimumSize().width()}x{self.minimumSize().height()}",
            min_hint=f"{self.minimumSizeHint().width()}x{self.minimumSizeHint().height()}",
            left=f"{self.left_host.width()}",
            left_min_hint=f"{self.left_host.minimumSizeHint().width()}",
            stack_min_hint=f"{self.left_host.stack.minimumSizeHint().width()}",
            current=current_name,
            current_min_hint=f"{current_min_hint.width()}x{current_min_hint.height()}",
            right=f"{right_geom.x()} {right_geom.width()}",
        )

    def schedule_right_panel_refresh(
        self,
        delay_ms: int = RIGHT_PANEL_REFRESH_DEBOUNCE_MS,
    ) -> None:
        if self._right_panel_refresh_pending:
            remaining = self._right_panel_refresh_timer.remainingTime()
            if remaining < 0:
                self._right_panel_refresh_timer.start(delay_ms)
                log_perf(
                    "right_panel_refresh_schedule",
                    pending=True,
                    delay=delay_ms,
                    restarted=True,
                )
                return
            if delay_ms >= remaining:
                log_perf(
                    "right_panel_refresh_schedule",
                    pending=True,
                    delay=remaining,
                )
                return
            self._right_panel_refresh_timer.start(delay_ms)
            log_perf(
                "right_panel_refresh_schedule",
                pending=True,
                delay=delay_ms,
                restarted=True,
            )
            return
        self._right_panel_refresh_pending = True
        self._right_panel_refresh_timer.start(delay_ms)
        log_perf(
            "right_panel_refresh_schedule",
            pending=False,
            delay=delay_ms,
        )

    def cancel_pending_right_panel_refresh(self, *, reason: str) -> None:
        if not self._right_panel_refresh_pending:
            return
        self._right_panel_refresh_pending = False
        if self._right_panel_refresh_timer.isActive():
            self._right_panel_refresh_timer.stop()
        log_perf(
            "right_panel_refresh_cancel",
            reason=reason,
        )

    def schedule_weapon_filter_sync(
        self,
        delay_ms: int = WEAPON_FILTER_SYNC_DEBOUNCE_MS,
    ) -> None:
        if self._weapon_filter_sync_pending:
            self._weapon_filter_sync_timer.start(delay_ms)
            log_perf(
                "weapon_filter_sync_schedule",
                pending=True,
                delay=delay_ms,
                restarted=True,
            )
            return
        self._weapon_filter_sync_pending = True
        self._weapon_filter_sync_timer.start(delay_ms)
        log_perf("weapon_filter_sync_schedule", pending=False, delay=delay_ms)

    def schedule_persistent_equipment_hydration(
        self,
        result: CharacterPlacementResult,
    ) -> None:
        if not result.added:
            return
        self._equipment_hydration_generation += 1
        self.cancel_pending_right_panel_refresh(
            reason="pending_equipment_hydration"
        )
        self._equipment_hydration_pending = result
        self._equipment_hydration_timer.start(PERSISTENT_EQUIPMENT_HYDRATION_DELAY_MS)
        log_perf(
            "persistent_equipment_hydration_schedule",
            generation=self._equipment_hydration_generation,
            character=result.character_id,
            delay=PERSISTENT_EQUIPMENT_HYDRATION_DELAY_MS,
        )

    def cancel_pending_equipment_hydration(
        self,
        result: CharacterPlacementResult | None = None,
    ) -> None:
        if result is not None and self._equipment_hydration_pending is not None:
            pending = self._equipment_hydration_pending
            if (
                pending.character_id != result.character_id
                or pending.team_index != result.team_index
                or pending.slot_index != result.slot_index
            ):
                return
        self._equipment_hydration_generation += 1
        self._equipment_hydration_pending = None
        if self._equipment_hydration_timer.isActive():
            self._equipment_hydration_timer.stop()
        log_perf(
            "persistent_equipment_hydration_cancel",
            generation=self._equipment_hydration_generation,
        )

    def flush_pending_weapon_filter_sync(self) -> bool:
        if self._weapon_filter_sync_timer.isActive():
            self._weapon_filter_sync_timer.stop()
        if not self._weapon_filter_sync_pending:
            return False
        self._weapon_filter_sync_pending = False
        total_start = perf_now()
        filter_start = perf_now()
        filter_key = self.controller.selected_character_weapon_filter_key()
        filter_ms = perf_ms(filter_start)
        apply_start = perf_now()
        changed = self.left_host.character_weapon_workspace.set_auto_weapon_type_filter(
            filter_key
        )
        apply_ms = perf_ms(apply_start)
        log_perf(
            "weapon_filter_sync",
            total=perf_ms(total_start),
            selected_filter=filter_ms,
            apply=apply_ms,
            filter=filter_key or "all",
            changed=changed,
        )
        return changed

    def flush_pending_equipment_hydration(self) -> dict[str, float]:
        if self._equipment_hydration_timer.isActive():
            self._equipment_hydration_timer.stop()
        result = self._equipment_hydration_pending
        self._equipment_hydration_pending = None
        if result is None or not result.added:
            return {}
        total_start = perf_now()
        timings = self.controller.hydrate_persistent_equipment_for_slot(
            result.team_index,
            result.slot_index,
            result.character_id,
        )
        total_ms = perf_ms(total_start)
        applied = bool(timings.get("hydration_applied"))
        if applied:
            sync_start = perf_now()
            self._sync_artifact_browser_operation_target()
            sync_ms = perf_ms(sync_start)
            self.schedule_right_panel_refresh(delay_ms=RIGHT_PANEL_FAST_REFRESH_MS)
            timings["operation_target_sync"] = sync_ms
        log_perf(
            "persistent_equipment_hydration_flush",
            total=total_ms,
            character=result.character_id,
            applied=applied,
            **timings,
        )
        return timings

    def flush_pending_right_panel_refresh(self) -> dict[str, float]:
        if self._right_panel_refresh_timer.isActive():
            self._right_panel_refresh_timer.stop()
        if not self._right_panel_refresh_pending:
            return {}
        self._right_panel_refresh_pending = False
        timings = self._refresh_right_panel()
        log_perf("right_panel_refresh_deferred", **timings)
        return timings

    def _sync_artifact_browser_operation_target(self) -> None:
        self.left_host.set_artifact_right_panel_operation_target(
            self.controller.selected_operation_target()
        )

    def _on_artifact_browser_equipment_changed(self, result: object) -> None:
        affected_ids = {
            str(character_id)
            for character_id in getattr(result, "affected_character_ids", ()) or ()
            if str(character_id)
        }
        if not affected_ids:
            target = self.controller.selected_operation_target()
            if target is not None and target.get("character_id") is not None:
                affected_ids.add(str(target["character_id"]))

        refreshed = False
        for character_id in affected_ids:
            refreshed = (
                self.controller.refresh_persistent_equipment_for_character(character_id)
                or refreshed
            )
        if refreshed:
            self.schedule_right_panel_refresh()

    def _on_account_data_changed(self, reset_runtime_state: bool) -> None:
        self.cancel_pending_equipment_hydration()
        self.cancel_pending_right_panel_refresh(reason="account_data_changed")
        if self._weapon_filter_sync_timer.isActive():
            self._weapon_filter_sync_timer.stop()
        self._weapon_filter_sync_pending = False

        if reset_runtime_state:
            previous_mode = self.controller.mode
            external_bonuses_enabled = self.controller.external_bonuses_enabled
            controller = AppShellController.empty(
                equipment_db_path=self.controller.equipment_db_path
            )
            controller.external_bonuses_enabled = external_bonuses_enabled
            if previous_mode != MODE_ABYSS:
                controller.set_mode(previous_mode)
            self.controller = controller
        else:
            self.controller.invalidate_persistent_equipment_cache()

        self.left_host.refresh_account_data()
        self._refresh_character_selection_markers()
        self._sync_artifact_browser_operation_target()
        self.schedule_weapon_filter_sync(delay_ms=0)
        self.schedule_right_panel_refresh(delay_ms=RIGHT_PANEL_FAST_REFRESH_MS)

    def _refresh_right_panel(self) -> dict[str, float]:
        total_start = perf_now()
        vm_start = perf_now()
        model = self.controller.right_panel_model()
        vm_ms = perf_ms(vm_start)
        set_model_start = perf_now()
        self.right_panel.set_model(model)
        set_model_ms = perf_ms(set_model_start)
        total_ms = perf_ms(total_start)
        log_perf(
            "right_panel_refresh",
            total=total_ms,
            vm=vm_ms,
            set_model=set_model_ms,
        )
        return {
            "right_panel_total": total_ms,
            "vm": vm_ms,
            "set_model": set_model_ms,
        }

    def _refresh_character_selection_markers(
        self,
        *,
        affected_character_ids: set[str] | None = None,
        markers: dict[str, RosterSelectionMarker] | None = None,
    ) -> dict[str, float]:
        total_start = perf_now()
        marker_start = perf_now()
        markers = markers if markers is not None else self.controller.roster_selection_markers()
        marker_ms = perf_ms(marker_start)
        workspace_start = perf_now()
        self.left_host.character_weapon_workspace.set_character_selection_markers(
            markers,
            affected_character_ids=affected_character_ids,
        )
        workspace_ms = perf_ms(workspace_start)
        total_ms = perf_ms(total_start)
        log_perf(
            "selected_marker_update",
            total=total_ms,
            marker_state=marker_ms,
            workspace=workspace_ms,
            affected="all" if affected_character_ids is None else len(affected_character_ids),
        )
        return {
            "markers_total": total_ms,
            "marker_state": marker_ms,
            "marker_workspace": workspace_ms,
        }

    def _refresh_shell(
        self,
        *,
        affected_character_ids: set[str] | None = None,
        markers: dict[str, RosterSelectionMarker] | None = None,
    ) -> dict[str, float]:
        timings: dict[str, float] = {}
        timings.update(self._refresh_right_panel())
        timings.update(
            self._refresh_character_selection_markers(
                affected_character_ids=affected_character_ids,
                markers=markers,
            )
        )
        return timings

    def _on_mode_requested(self, mode: str) -> None:
        self.right_dock.show_run_page(mode)
        self.controller.set_mode(mode)
        marker_timings = self._refresh_character_selection_markers(
            affected_character_ids=None
        )
        self._sync_artifact_browser_operation_target()
        self.schedule_weapon_filter_sync()
        self.schedule_right_panel_refresh()
        log_perf("mode_switch", mode=mode, **marker_timings)

    def _on_workspace_requested(self, workspace_id: str) -> None:
        self.left_host.activate_workspace(workspace_id)

    def _on_workspace_activated(self, workspace_id: str) -> None:
        self.active_left_workspace_id = workspace_id
        log_perf(
            "left_workspace_activate",
            workspace=workspace_id,
            right_page=self.right_dock.current_page(),
        )

    def _on_slot_selected(self, team_index: int, slot_index: int) -> None:
        total_start = perf_now()
        self.controller.toggle_slot_selection(team_index, slot_index)
        self._sync_artifact_browser_operation_target()
        hydration_target = self.controller.selected_equipment_hydration_target()
        if hydration_target is not None:
            self.schedule_persistent_equipment_hydration(hydration_target)
        else:
            self.cancel_pending_equipment_hydration()
        self.schedule_weapon_filter_sync()
        self.schedule_right_panel_refresh()
        log_perf("slot_select", total=perf_ms(total_start), scheduled=True)

    def _on_slot_dropped(
        self,
        source_team_index: int,
        source_slot_index: int,
        target_team_index: int,
        target_slot_index: int,
    ) -> None:
        total_start = perf_now()
        self.cancel_pending_equipment_hydration()
        self.cancel_pending_right_panel_refresh(reason="slot_dropped")
        state_start = perf_now()
        changed = self.controller.swap_slots(
            source_team_index,
            source_slot_index,
            target_team_index,
            target_slot_index,
        )
        state_ms = perf_ms(state_start)
        timings: dict[str, float] = {}
        if changed:
            timings.update(self._refresh_character_selection_markers())
            target_start = perf_now()
            self._sync_artifact_browser_operation_target()
            timings["operation_target_sync"] = perf_ms(target_start)
            hydration_target = self.controller.selected_equipment_hydration_target()
            if hydration_target is not None:
                self.schedule_persistent_equipment_hydration(hydration_target)
            self.schedule_weapon_filter_sync()
            self.schedule_right_panel_refresh(delay_ms=RIGHT_PANEL_FAST_REFRESH_MS)
        log_perf(
            "slot_drop",
            total=perf_ms(total_start),
            state=state_ms,
            changed=changed,
            source_team=source_team_index,
            source_slot=source_slot_index,
            target_team=target_team_index,
            target_slot=target_slot_index,
            scheduled=changed,
            **timings,
        )

    def _on_external_bonuses_toggled(self, enabled: bool) -> None:
        total_start = perf_now()
        self.controller.external_bonuses_enabled = bool(enabled)
        self.schedule_right_panel_refresh()
        log_perf("external_bonus_toggle", total=perf_ms(total_start), scheduled=True)

    def _on_character_clicked(self, asset: dict) -> None:
        total_start = perf_now()
        before_markers = self.controller.roster_selection_markers()
        state_start = perf_now()
        result = self.controller.add_or_replace_character_fast(asset)
        changed = result.changed
        state_ms = perf_ms(state_start)
        timings: dict[str, float] = {}
        if changed:
            after_markers = self.controller.roster_selection_markers()
            affected_character_ids = _changed_marker_ids(before_markers, after_markers)
            timings = self._refresh_character_selection_markers(
                affected_character_ids=affected_character_ids,
                markers=after_markers,
            )
            target_start = perf_now()
            self._sync_artifact_browser_operation_target()
            target_ms = perf_ms(target_start)
            timings["operation_target_sync"] = target_ms
            self.schedule_weapon_filter_sync()
            if result.added:
                self.schedule_persistent_equipment_hydration(result)
            elif result.removed:
                self.cancel_pending_equipment_hydration(result)
                self.cancel_pending_right_panel_refresh(
                    reason="character_removed"
                )
                self.schedule_right_panel_refresh(delay_ms=RIGHT_PANEL_FAST_REFRESH_MS)
            else:
                self.schedule_right_panel_refresh(delay_ms=RIGHT_PANEL_FAST_REFRESH_MS)
        log_perf(
            "character_click",
            total=perf_ms(total_start),
            state=state_ms,
            changed=changed,
            scheduled=changed,
            **timings,
        )

    def _on_weapon_clicked(self, asset: dict) -> None:
        total_start = perf_now()
        state_start = perf_now()
        changed = self.controller.assign_weapon_to_selected_slot(asset)
        state_ms = perf_ms(state_start)
        timings: dict[str, float] = {}
        if changed:
            workspace_start = perf_now()
            workspace = self.left_host.character_weapon_workspace
            workspace.refresh_weapon_asset_cache()
            workspace.reload_weapons()
            timings["weapon_workspace_refresh"] = perf_ms(workspace_start)
            self.schedule_right_panel_refresh()
        log_perf(
            "weapon_click",
            total=perf_ms(total_start),
            state=state_ms,
            changed=changed,
            scheduled=changed,
            **timings,
        )


class LeftWorkspaceHost(QWidget):
    workspace_requested = Signal(str)
    workspace_activated = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        artifact_db_path: str | Path = ARTIFACT_DB_PATH,
        artifact_equipment_changed=None,
    ) -> None:
        super().__init__(parent)
        self.artifact_db_path = artifact_db_path
        self.artifact_equipment_changed = artifact_equipment_changed
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_layout = QHBoxLayout()
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(4)
        layout.addLayout(self.nav_layout)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self._workspace_indices_by_id: dict[str, int] = {}
        self._workspace_ids_by_index: dict[int, str] = {}
        self._workspace_buttons_by_id: dict[str, QPushButton] = {}

        self.character_weapon_workspace = CharacterWeaponWorkspace(
            db_path=self.artifact_db_path
        )
        self.character_weapon_button = self.add_workspace(
            LEFT_WORKSPACE_CHARACTERS_WEAPONS,
            tr("app_shell.workspace.characters_weapons"),
            self.character_weapon_workspace,
        )
        self.artifact_browser_workspace = None
        self._pending_artifact_right_panel_target: dict[str, Any] | None = None
        self.artifact_browser_placeholder = self._make_artifact_browser_placeholder()
        self.artifact_browser_index = self.stack.addWidget(
            self.artifact_browser_placeholder
        )
        self._register_workspace_index(
            LEFT_WORKSPACE_ARTIFACTS,
            self.artifact_browser_index,
        )
        self.artifact_browser_button = QPushButton(tr("app_shell.workspace.artifacts"))
        self.artifact_browser_button.setCheckable(True)
        self.artifact_browser_button.clicked.connect(
            lambda _checked=False: self.request_workspace(LEFT_WORKSPACE_ARTIFACTS)
        )
        self.nav_group.addButton(self.artifact_browser_button)
        self.nav_layout.addWidget(self.artifact_browser_button)
        self._workspace_buttons_by_id[
            LEFT_WORKSPACE_ARTIFACTS
        ] = self.artifact_browser_button
        self.stack.currentChanged.connect(self._on_stack_current_changed)

    def _make_artifact_browser_placeholder(self) -> QWidget:
        placeholder = QFrame()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        self.artifact_browser_placeholder_label = QLabel(tr("artifact.browser.title"))
        self.artifact_browser_placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.artifact_browser_placeholder_label, 1)
        return placeholder

    def add_workspace(
        self,
        workspace_id: str,
        label: str,
        widget: QWidget,
    ) -> QPushButton:
        index = self.stack.addWidget(widget)
        self._register_workspace_index(workspace_id, index)
        button = QPushButton(label)
        button.setCheckable(True)
        button.clicked.connect(
            lambda _checked=False, value=workspace_id: self.request_workspace(value)
        )
        self.nav_group.addButton(button)
        self.nav_layout.addWidget(button)
        self._workspace_buttons_by_id[workspace_id] = button
        if index == 0:
            button.setChecked(True)
            self.stack.setCurrentIndex(0)
        return button

    def _register_workspace_index(self, workspace_id: str, index: int) -> None:
        self._workspace_indices_by_id[workspace_id] = int(index)
        self._workspace_ids_by_index[int(index)] = workspace_id

    def request_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspace_indices_by_id:
            return
        self.workspace_requested.emit(workspace_id)

    def activate_workspace(self, workspace_id: str) -> None:
        if workspace_id == LEFT_WORKSPACE_ARTIFACTS:
            self.ensure_artifact_browser_workspace()
        index = self._workspace_indices_by_id.get(workspace_id)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        button = self._workspace_buttons_by_id.get(workspace_id)
        if button is not None:
            button.setChecked(True)

    def active_workspace_id(self) -> str:
        return self._workspace_ids_by_index.get(self.stack.currentIndex(), "")

    def _on_stack_current_changed(self, index: int) -> None:
        workspace_id = self._workspace_ids_by_index.get(int(index))
        if workspace_id:
            self.workspace_activated.emit(workspace_id)

    def show_artifact_browser_workspace(self) -> None:
        self.activate_workspace(LEFT_WORKSPACE_ARTIFACTS)

    def show_character_weapon_workspace(self) -> None:
        self.activate_workspace(LEFT_WORKSPACE_CHARACTERS_WEAPONS)

    def ensure_artifact_browser_workspace(self):
        if self.artifact_browser_workspace is not None:
            return self.artifact_browser_workspace

        from ui.artifact_browser.window import ArtifactBrowserWindow

        create_start = perf_now()
        browser = ArtifactBrowserWindow(
            parent=self.stack,
            embedded=True,
            db_path=self.artifact_db_path,
            character_asset_items=self.character_weapon_workspace.character_asset_items_snapshot(),
        )
        self.stack.removeWidget(self.artifact_browser_placeholder)
        self.artifact_browser_placeholder.deleteLater()
        self.stack.insertWidget(self.artifact_browser_index, browser)
        self.artifact_browser_workspace = browser
        if self.artifact_equipment_changed is not None:
            browser.equipment_changed.connect(self.artifact_equipment_changed)
        browser.set_right_panel_operation_target(
            self._pending_artifact_right_panel_target
        )
        log_perf(
            "artifact_workspace_lazy_create",
            total=perf_ms(create_start),
            artifacts=browser.model.rowCount(),
            adaptive_runs=getattr(browser, "_adaptive_update_count", 0),
            resize_events=getattr(browser, "_resize_event_count", 0),
        )
        return browser

    def set_artifact_right_panel_operation_target(
        self,
        target: dict[str, Any] | None,
    ) -> None:
        self._pending_artifact_right_panel_target = target
        if self.artifact_browser_workspace is not None:
            self.artifact_browser_workspace.set_right_panel_operation_target(target)

    def refresh_account_data(self) -> None:
        workspace = self.character_weapon_workspace
        workspace.refresh_asset_cache()
        if workspace._initial_grid_built:
            workspace.update_grids()
        if self.artifact_browser_workspace is not None:
            self.artifact_browser_workspace.refresh_account_data(
                workspace.character_asset_items_snapshot()
            )

    def retranslate_ui(self) -> None:
        self.character_weapon_button.setText(
            tr("app_shell.workspace.characters_weapons")
        )
        self.artifact_browser_button.setText(tr("app_shell.workspace.artifacts"))
        self.character_weapon_workspace.retranslate_ui()
        if self.artifact_browser_workspace is None:
            self.artifact_browser_placeholder_label.setText(
                tr("artifact.browser.title")
            )
        else:
            self.artifact_browser_workspace.retranslate_ui()


class RightDockHeader(QWidget):
    mode_requested = Signal(str)
    account_requested = Signal()

    def __init__(
        self,
        active_mode: str = MODE_ABYSS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RightDockHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(6)

        self.run_mode_tabs = RunModeTabsWidget(active_mode)
        self.run_mode_tabs.mode_requested.connect(self.mode_requested.emit)
        layout.addWidget(self.run_mode_tabs, 2)

        self.account_button = make_mode_tab_button(
            tr("app_shell.right_dock.account")
        )
        self.account_button.setIcon(_account_tab_icon())
        self.account_button.setIconSize(
            QSize(RIGHT_DOCK_ACCOUNT_ICON_SIZE, RIGHT_DOCK_ACCOUNT_ICON_SIZE)
        )
        self.account_button.clicked.connect(
            lambda _checked=False: self.account_requested.emit()
        )
        layout.addWidget(self.account_button, 1)

    def show_run_mode(self, mode: str) -> None:
        self.account_button.setChecked(False)
        self.run_mode_tabs.set_active_mode(mode)

    def show_account(self) -> None:
        self.run_mode_tabs.set_active_mode(None)
        self.account_button.setChecked(True)

    def retranslate_ui(self) -> None:
        self.run_mode_tabs.retranslate_ui()
        self.account_button.setText(tr("app_shell.right_dock.account"))


class RightOperationsDock(QFrame):
    mode_requested = Signal(str)

    def __init__(
        self,
        operation_widget: QWidget,
        parent: QWidget | None = None,
        *,
        active_mode: str = MODE_ABYSS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RightOperationsDock")
        self.operation_widget = operation_widget
        self.header = RightDockHeader(active_mode)
        self.account_page = AccountDataPage()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.operation_widget)
        self.content_stack.addWidget(self.account_page)
        layout.addWidget(self.content_stack, 1)

        operation_widget.setMinimumWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setFixedWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(right_panel_stylesheet())

        self.header.mode_requested.connect(self._on_mode_requested)
        self.header.account_requested.connect(self.show_account_page)
        self.show_run_page(active_mode)

    def current_page(self) -> str:
        if self.content_stack.currentWidget() is self.account_page:
            return RIGHT_DOCK_PAGE_ACCOUNT
        return RIGHT_DOCK_PAGE_RUN

    def show_run_page(self, mode: str) -> None:
        self.content_stack.setCurrentWidget(self.operation_widget)
        self.header.show_run_mode(mode)

    def show_account_page(self) -> None:
        self.content_stack.setCurrentWidget(self.account_page)
        self.header.show_account()

    def _on_mode_requested(self, mode: str) -> None:
        self.show_run_page(mode)
        self.mode_requested.emit(mode)

    def retranslate_ui(self) -> None:
        self.header.retranslate_ui()
        self.account_page.retranslate_ui()


def _account_tab_icon() -> QIcon:
    icon = QIcon()
    size = RIGHT_DOCK_ACCOUNT_ICON_SIZE
    icon.addPixmap(
        tinted_svg_pixmap("user-round-cog", size, UI_TEXT_SECONDARY),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    icon.addPixmap(
        tinted_svg_pixmap("user-round-cog", size, UI_BG_APP),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    return icon


class CharacterWeaponWorkspace(QWidget):
    character_clicked = Signal(dict)
    weapon_clicked = Signal(dict)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        db_path: str | Path = ARTIFACT_DB_PATH,
    ) -> None:
        super().__init__(parent)
        self.db_path = db_path
        self._resize_timer: QTimer | None = None
        self._initial_grid_built = False
        self._character_element_filters: set[str] = set()
        self._character_weapon_filters: set[str] = set()
        self._character_rarity_filters: set[int] = set()
        self._character_trait_filters: set[str] = set()
        self._character_standard_filter = STANDARD_FILTER_ALL
        self._weapon_type_filters: set[str] = set()
        self._weapon_rarity_filters: set[int] = set()
        self._character_selection_markers: dict[str, RosterSelectionMarker] = {}
        self._character_cards_by_id: dict[str, AssetIconLabel] = {}
        self._all_character_items: list[dict] | None = None
        self._all_weapon_items: list[dict] | None = None
        self._last_character_grid_keys: tuple[str, ...] = ()
        self._last_weapon_grid_keys: tuple[str, ...] = ()
        self._weapon_cards_by_key: dict[str, AssetIconLabel] = {}
        self._weapon_type_buttons: dict[str, QPushButton] = {}
        self._auto_weapon_type_filter: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.weapon_title_label = QLabel(tr("asset_panel.weapons"))
        root.addWidget(self.weapon_title_label)
        root.addSpacing(6)
        root.addLayout(
            self._build_filter_row(
                (
                    (WEAPON_TYPE_FILTERS, self._weapon_type_filters, self.reload_weapons),
                    (WEAPON_RARITY_FILTERS, self._weapon_rarity_filters, self.reload_weapons),
                )
            )
        )
        self.weapon_area, self.weapon_widget, self.weapon_grid = self._make_grid_area()
        root.addWidget(self.weapon_area, 1)

        root.addSpacing(6)
        self.character_title_label = QLabel(tr("asset_panel.characters"))
        root.addWidget(self.character_title_label)
        root.addSpacing(6)
        root.addLayout(
            self._build_filter_row(
                (
                    (ELEMENT_FILTERS, self._character_element_filters, self.reload_characters),
                    (WEAPON_TYPE_FILTERS, self._character_weapon_filters, self.reload_characters),
                    (
                        CHARACTER_RARITY_FILTERS,
                        self._character_rarity_filters,
                        self.reload_characters,
                    ),
                    (
                        CHARACTER_TRAIT_FILTERS,
                        self._character_trait_filters,
                        self.reload_characters,
                    ),
                ),
                trailing_widgets=(self._make_standard_filter_button(),),
            )
        )
        root.addSpacing(6)
        self.char_area, self.char_widget, self.char_grid = self._make_grid_area()
        root.addWidget(self.char_area, 3)
        self._character_selection_overlay = CharacterSelectionOverlay(
            self,
            self.char_area,
            lambda: self._character_cards_by_id.values(),
        )
        self._weapon_owner_badge_overlay = WeaponOwnerBadgeOverlay(
            self,
            self.weapon_area,
            self.weapon_widget,
            self.weapon_grid,
            lambda: self._weapon_cards_by_key.values(),
        )

    def retranslate_ui(self) -> None:
        self.weapon_title_label.setText(tr("asset_panel.weapons"))
        self.character_title_label.setText(tr("asset_panel.characters"))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._character_selection_overlay.sync_geometry()
        self._character_selection_overlay.update()
        self._weapon_owner_badge_overlay.sync_geometry()
        self._weapon_owner_badge_overlay.update()
        self._weapon_owner_badge_overlay.schedule_settle()
        if not self._initial_grid_built:
            self._initial_grid_built = True
            QTimer.singleShot(0, self.update_grids)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._character_selection_overlay.sync_geometry()
        self._character_selection_overlay.update()
        self._weapon_owner_badge_overlay.sync_geometry()
        self._weapon_owner_badge_overlay.update()
        if self._initial_grid_built:
            self.update_grids_delayed()

    def update_grids_delayed(self) -> None:
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.update_grids)
        self._resize_timer.start(75)

    def update_grids(self) -> None:
        self.reload_characters()
        self.reload_weapons()

    def refresh_asset_cache(self) -> None:
        self._all_character_items = None
        self._all_weapon_items = None
        self._last_character_grid_keys = ()
        self._last_weapon_grid_keys = ()

    def refresh_weapon_asset_cache(self) -> None:
        self._all_weapon_items = None
        self._last_weapon_grid_keys = ()

    def _character_asset_items(self) -> tuple[list[dict], float, str]:
        load_start = perf_now()
        source = "cache"
        if self._all_character_items is None:
            source = "sqlite"
            self._all_character_items = list(
                load_account_character_asset_items(db_path=self.db_path)
            )
        return list(self._all_character_items), perf_ms(load_start), source

    def character_asset_items_snapshot(self) -> list[dict]:
        items, _load_ms, _source = self._character_asset_items()
        return items

    def _weapon_asset_items(self) -> tuple[list[dict], float, str]:
        load_start = perf_now()
        source = "cache"
        if self._all_weapon_items is None:
            source = "sqlite"
            self._all_weapon_items = list(
                load_account_weapon_stack_asset_items(db_path=self.db_path)
            )
        return list(self._all_weapon_items), perf_ms(load_start), source

    def set_character_selection_markers(
        self,
        markers: dict[str, RosterSelectionMarker],
        *,
        affected_character_ids: set[str] | None = None,
    ) -> None:
        if markers == self._character_selection_markers:
            return
        total_start = perf_now()
        previous_markers = self._character_selection_markers
        self._character_selection_markers = dict(markers)
        if not self._initial_grid_built:
            return

        if affected_character_ids is None:
            ids_to_update = set(self._character_cards_by_id)
        else:
            ids_to_update = {
                _text(character_id)
                for character_id in affected_character_ids
                if _text(character_id)
            }
            ids_to_update.update(
                character_id
                for character_id in set(previous_markers) | set(markers)
                if previous_markers.get(character_id) != markers.get(character_id)
            )

        updated_count = 0
        for character_id in ids_to_update:
            card = self._character_cards_by_id.get(character_id)
            if card is None:
                continue
            card.set_selection_marker(markers.get(character_id))
            updated_count += 1
        self._character_selection_overlay.update()
        log_perf(
            "marker_incremental",
            total=perf_ms(total_start),
            affected="all" if affected_character_ids is None else len(affected_character_ids),
            updated=updated_count,
            visible_cards=len(self._character_cards_by_id),
        )

    def reload_characters(self) -> None:
        total_start = perf_now()
        self._character_cards_by_id = {}
        assets, load_ms, load_source = self._character_asset_items()
        predicate_start = perf_now()
        assets = [
            asset
            for asset in assets
            if character_matches_filters(
                asset,
                self._character_element_filters,
                self._character_weapon_filters,
                self._character_rarity_filters,
                trait_filters=self._character_trait_filters,
                standard_filter=self._character_standard_filter,
            )
        ]
        predicate_ms = perf_ms(predicate_start)
        sort_start = perf_now()
        assets.sort(key=character_sort_key)
        sort_ms = perf_ms(sort_start)
        self._last_character_grid_keys = tuple(_asset_character_id(asset) for asset in assets)
        rebuild_ms = self._reload_icon_grid(
            assets,
            self.char_grid,
            self.char_widget,
            self.char_area,
            icon_size=72,
            spacing=3,
            clicked=self.character_clicked.emit,
            selection_markers=self._character_selection_markers,
            grid_name="characters",
            card_registry=self._character_cards_by_id,
            vertical_safe_top_margin=CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN,
        )
        self._character_selection_overlay.sync_geometry()
        self._character_selection_overlay.update()
        log_perf(
            "filter_characters",
            total=perf_ms(total_start),
            load=load_ms,
            load_source=load_source,
            predicate=predicate_ms,
            sort=sort_ms,
            rebuild_cards=rebuild_ms,
            count=len(assets),
            standard=self._character_standard_filter,
        )

    def reload_weapons(self) -> None:
        total_start = perf_now()
        self._weapon_cards_by_key = {}
        assets, load_ms, load_source = self._weapon_asset_items()
        predicate_start = perf_now()
        assets = [asset for asset in assets if self._weapon_matches_filters(asset)]
        predicate_ms = perf_ms(predicate_start)
        sort_start = perf_now()
        assets.sort(key=self._weapon_sort_key)
        sort_ms = perf_ms(sort_start)
        self._last_weapon_grid_keys = tuple(_asset_grid_key(asset) for asset in assets)
        rebuild_ms = self._reload_icon_grid(
            assets,
            self.weapon_grid,
            self.weapon_widget,
            self.weapon_area,
            icon_size=WEAPON_PICKER_ICON_SIZE,
            spacing=6,
            clicked=self.weapon_clicked.emit,
            grid_name="weapons",
            card_registry=self._weapon_cards_by_key,
            vertical_safe_margin=WEAPON_PICKER_SAFE_MARGIN,
            vertical_safe_top_margin=(
                WEAPON_PICKER_SAFE_MARGIN + WEAPON_PICKER_VIEWPORT_TOP_EXTENSION
            ),
        )
        self._weapon_owner_badge_overlay.sync_geometry()
        self._weapon_owner_badge_overlay.update()
        self._weapon_owner_badge_overlay.schedule_settle()
        log_perf(
            "filter_weapons",
            total=perf_ms(total_start),
            load=load_ms,
            load_source=load_source,
            predicate=predicate_ms,
            sort=sort_ms,
            rebuild_cards=rebuild_ms,
            count=len(assets),
        )

    def set_auto_weapon_type_filter(self, weapon_type_key: str | None) -> bool:
        key = _text(weapon_type_key)
        known_keys = {str(value) for value, _icon_name, _tooltip_key in WEAPON_TYPE_FILTERS}
        if key not in known_keys:
            key = ""
        previous_filters = set(self._weapon_type_filters)
        self._auto_weapon_type_filter = key
        self._weapon_type_filters.clear()
        if key:
            self._weapon_type_filters.add(key)
        for value, button in self._weapon_type_buttons.items():
            button.blockSignals(True)
            button.setChecked(bool(key and value == key))
            button.blockSignals(False)
        changed = previous_filters != self._weapon_type_filters
        if changed:
            self.reload_weapons()
        log_perf(
            "weapon_auto_filter",
            filter=key or "all",
            changed=changed,
        )
        return changed

    def _make_grid_area(self) -> tuple[QScrollArea, QWidget, QGridLayout]:
        area = OverlayVerticalScrollArea(auto_hide_ms=850)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        area.setWidget(container)
        return area, container, grid

    def _make_filter_button(
        self,
        value: Any,
        icon_name: str,
        active_set: set,
        update_callback,
    ) -> QPushButton:
        button = QPushButton("")
        button.setObjectName("app_shell_filter_button")
        button.setCheckable(True)
        button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
        button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
        button.setStyleSheet(FILTER_BUTTON_STYLE)

        icon_path = FILTER_ASSETS_DIR / icon_name
        if icon_path.exists():
            button.setIcon(QIcon(str(icon_path)))
        else:
            button.setText(str(value))

        def toggle_filter(checked: bool, *, filter_value=value, filters=active_set) -> None:
            total_start = perf_now()
            if filters is self._weapon_type_filters:
                self._auto_weapon_type_filter = ""
            if checked:
                filters.add(filter_value)
            else:
                filters.discard(filter_value)
            update_callback()
            log_perf(
                "filter_button_toggle",
                total=perf_ms(total_start),
                value=filter_value,
                checked=checked,
            )

        button.clicked.connect(toggle_filter)
        return button

    def _build_filter_row(self, filter_groups, *, trailing_widgets=None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        for filters, active_set, update_callback in filter_groups:
            for value, icon_name, _tooltip_key in filters:
                button = self._make_filter_button(
                    value,
                    icon_name,
                    active_set,
                    update_callback,
                )
                if active_set is self._weapon_type_filters:
                    self._weapon_type_buttons[_text(value)] = button
                row.addWidget(button)
        for widget in trailing_widgets or ():
            row.addWidget(widget)
        row.addStretch()
        return row

    def _make_standard_filter_button(self) -> QPushButton:
        _value, _icon_name, _tooltip_key = CHARACTER_STANDARD_FILTER
        button = QPushButton("")
        button.setObjectName("app_shell_filter_button")
        button.setCheckable(False)
        button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
        button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
        button.setStyleSheet(FILTER_BUTTON_STYLE)
        button.setIcon(standard_character_filter_icon(STANDARD_FILTER_ALL, size=FILTER_BUTTON_ICON_SIZE))
        button.setProperty("standardOnly", False)

        def cycle_standard_filter() -> None:
            total_start = perf_now()
            if self._character_standard_filter == STANDARD_FILTER_ALL:
                self._character_standard_filter = STANDARD_FILTER_ONLY
            elif self._character_standard_filter == STANDARD_FILTER_ONLY:
                self._character_standard_filter = STANDARD_FILTER_EXCLUDE
            else:
                self._character_standard_filter = STANDARD_FILTER_ALL
            button.setProperty(
                "standardOnly",
                self._character_standard_filter == STANDARD_FILTER_ONLY,
            )
            button.style().unpolish(button)
            button.style().polish(button)
            button.setIcon(
                standard_character_filter_icon(
                    self._character_standard_filter,
                    size=FILTER_BUTTON_ICON_SIZE,
                )
            )
            button.repaint()
            QTimer.singleShot(0, self.reload_characters)
            log_perf(
                "filter_standard_toggle",
                total=perf_ms(total_start),
                standard=self._character_standard_filter,
            )

        button.clicked.connect(cycle_standard_filter)
        return button

    def _weapon_matches_filters(self, asset: dict) -> bool:
        metadata = asset.get("metadata")
        if not metadata:
            return True
        weapon = metadata.get("weapon") or {}
        weapon_type_keys = _weapon_type_filter_keys(weapon)
        rarity = metadata_int(weapon.get("rarity"))
        if self._weapon_type_filters and not (
            weapon_type_keys & self._weapon_type_filters
        ):
            return False
        if self._weapon_rarity_filters and rarity not in self._weapon_rarity_filters:
            return False
        return True

    def _weapon_sort_key(self, asset: dict):
        metadata = asset.get("metadata") or {}
        weapon = metadata.get("weapon") or {}
        rarity = metadata_int(weapon.get("rarity"))
        level = metadata_int(weapon.get("level"))
        name = str(weapon.get("name") or metadata.get("name") or asset.get("filename") or "")
        return (-rarity, -level, name.casefold(), str(asset.get("filename") or ""))

    def _reload_icon_grid(
        self,
        assets: list[dict],
        grid: QGridLayout,
        container: QWidget,
        area: QScrollArea,
        *,
        icon_size: int,
        spacing: int,
        clicked,
        selection_markers: dict[str, RosterSelectionMarker] | None = None,
        grid_name: str = "icons",
        card_registry: dict[str, "AssetIconLabel"] | None = None,
        vertical_safe_margin: int = 0,
        vertical_safe_top_margin: int | None = None,
    ) -> float:
        total_start = perf_now()
        _clear_grid(grid)
        _reset_grid_columns(grid)
        if not assets:
            grid.setContentsMargins(0, 0, 0, 0)
            container.adjustSize()
            area.horizontalScrollBar().setValue(0)
            total_ms = perf_ms(total_start)
            log_perf(
                "grid_reload",
                grid=grid_name,
                total=total_ms,
                icon_create=0.0,
                count=0,
                pixmap_hits=0,
                pixmap_misses=0,
            )
            return total_ms

        available_width = area.viewport().width() or area.width() or 300
        cell_width = icon_size + spacing
        cols = max(1, (available_width + spacing) // cell_width)
        total_grid_width = cols * icon_size + max(0, cols - 1) * spacing
        left_margin = max(0, (available_width - total_grid_width) // 2)
        right_margin = max(0, available_width - total_grid_width - left_margin)
        safe_margin = max(0, int(vertical_safe_margin))
        safe_top_margin = (
            safe_margin
            if vertical_safe_top_margin is None
            else max(0, int(vertical_safe_top_margin))
        )
        grid.setContentsMargins(left_margin, safe_top_margin, right_margin, safe_margin)
        grid.setHorizontalSpacing(spacing)
        grid.setVerticalSpacing(spacing)
        for column in range(cols):
            grid.setColumnMinimumWidth(column, icon_size)
            grid.setColumnStretch(column, 0)

        icon_create_ms = 0.0
        pixmap_hits = 0
        pixmap_misses = 0
        for index, asset in enumerate(assets):
            try:
                marker = None
                if selection_markers is not None:
                    marker = selection_markers.get(_asset_character_id(asset))
                icon_start = perf_now()
                icon = AssetIconLabel(
                    str(asset["path"]),
                    icon_size,
                    asset=asset,
                    selection_marker=marker,
                    paint_selection_marker=(grid_name != "characters"),
                )
                if icon._last_pixmap_cache_hit:
                    pixmap_hits += 1
                else:
                    pixmap_misses += 1
                icon_create_ms += perf_ms(icon_start)
                icon.clicked.connect(clicked)
                tooltip = asset.get("tooltip")
                if tooltip:
                    icon.setToolTip(tooltip)
                grid.addWidget(icon, index // cols, index % cols)
                if card_registry is not None:
                    card_key = (
                        _asset_character_id(asset)
                        if grid_name == "characters"
                        else _asset_grid_key(asset)
                    )
                    if card_key:
                        card_registry[card_key] = icon
            except Exception as exc:
                print(f"Failed to load {asset.get('filename')}: {exc}")

        container.adjustSize()
        container.updateGeometry()
        area.horizontalScrollBar().setValue(0)
        area.viewport().update()
        total_ms = perf_ms(total_start)
        log_perf(
            "grid_reload",
            grid=grid_name,
            total=total_ms,
            icon_create=icon_create_ms,
            count=len(assets),
            pixmap_hits=pixmap_hits,
            pixmap_misses=pixmap_misses,
        )
        return total_ms


def _scaled_icon_pixmap(image_path: str, size: int, dpr: float) -> tuple[QPixmap, bool]:
    result = load_hidpi_pixmap(
        image_path,
        size,
        dpr=dpr,
        aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
        transform_mode=Qt.TransformationMode.SmoothTransformation,
        cache=_SCALED_ICON_PIXMAP_CACHE,
        surface="app_shell_asset_icon",
    )
    return result.pixmap, result.cache_hit


def _owner_badge_icon_pixmap(
    image_path: str,
    size: QSize,
    *,
    dpr: float = 1.0,
) -> QPixmap | None:
    result = load_hidpi_pixmap(
        image_path,
        size,
        dpr=dpr,
        aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
        transform_mode=Qt.TransformationMode.SmoothTransformation,
        cache=_OWNER_BADGE_ICON_PIXMAP_CACHE,
        surface="weapon_owner_side_icon",
    )
    return None if result.pixmap.isNull() else result.pixmap


def _owner_badge_background(size: QSize, *, dpr: float = 1.0) -> QPixmap:
    effective_dpr = effective_pixmap_dpr(dpr)
    key = (size.width(), size.height(), int(round(effective_dpr * 1000)))
    cached = _OWNER_BADGE_BACKGROUND_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached

    pixmap = make_owner_icon_badge_background(size, dpr=effective_dpr)
    _OWNER_BADGE_BACKGROUND_CACHE[key] = pixmap
    return pixmap


def _trace_rect(rect: QRect) -> str:
    return f"{rect.x()},{rect.y()},{rect.width()}x{rect.height()}"


def _weapon_owner_side_icon_size(weapon_rect: QRect) -> QSize:
    return QSize(
        max(1, int(round(weapon_rect.width() * WEAPON_PICKER_OWNER_SIDE_ICON_RATIO))),
        max(1, int(round(weapon_rect.height() * WEAPON_PICKER_OWNER_SIDE_ICON_RATIO))),
    )


def _weapon_owner_target_rect(
    weapon_rect: QRect,
    side_icon_size: QSize,
    *,
    right_overhang: int | None = None,
    top_overhang: int | None = None,
) -> QRect:
    if right_overhang is None:
        right_overhang = int(
            round(side_icon_size.width() * WEAPON_PICKER_OWNER_RIGHT_OVERHANG_RATIO)
        )
    if top_overhang is None:
        top_overhang = int(
            round(side_icon_size.height() * WEAPON_PICKER_OWNER_TOP_OVERHANG_RATIO)
        )
    return QRect(
        weapon_rect.right() - side_icon_size.width() + 1 + int(right_overhang),
        weapon_rect.top() - int(top_overhang),
        side_icon_size.width(),
        side_icon_size.height(),
    )


class AssetIconLabel(QLabel):
    clicked = Signal(dict)

    def __init__(
        self,
        image_path: str,
        size: int,
        *,
        asset: dict[str, Any] | None = None,
        selection_marker: RosterSelectionMarker | None = None,
        paint_selection_marker: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.asset = asset or {}
        self.base_size = int(size)
        self.selection_marker = selection_marker
        self.paint_selection_marker = bool(paint_selection_marker)
        self.owner_badges = _asset_owner_badges(self.asset)
        self._last_pixmap_cache_hit = False
        self._tooltip_controller = install_custom_tooltip(self)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_pixmap()

    def set_selection_marker(self, marker: RosterSelectionMarker | None) -> None:
        self.selection_marker = marker
        self.update()

    def setToolTip(self, text: str) -> None:
        self._tooltip_controller.set_text(text or "")
        super().setToolTip("")

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._update_pixmap()
        return super().event(event)

    def _update_pixmap(self) -> None:
        dpr = self.devicePixelRatioF()
        pixmap, cache_hit = _scaled_icon_pixmap(self.image_path, self.base_size, dpr)
        self._last_pixmap_cache_hit = cache_hit
        if pixmap.isNull():
            self.clear()
            return
        self.setPixmap(pixmap)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        marker = self.selection_marker
        if marker is None or not self.paint_selection_marker:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            _draw_selection_frame(
                painter,
                _selection_frame_rect(QRect(0, 0, self.width(), self.height())),
                marker.color,
                badge_text=str(marker.slot_number),
                font_size=max(8, min(11, self.base_size // 7)),
            )
        finally:
            painter.end()

    def _displayed_icon_rect(self) -> QRect:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRect()
        pixmap_size = logical_pixmap_size(pixmap)
        width = pixmap_size.width()
        height = pixmap_size.height()
        return QRect(
            (self.width() - width) // 2,
            (self.height() - height) // 2,
            width,
            height,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(dict(self.asset))
            event.accept()
            return
        super().mousePressEvent(event)


def _selection_frame_rect(card_rect: QRect) -> QRect:
    return card_rect.adjusted(
        -GRID_SELECTION_OUTLINE_OVERHANG,
        -GRID_SELECTION_OUTLINE_OVERHANG,
        GRID_SELECTION_OUTLINE_OVERHANG,
        GRID_SELECTION_OUTLINE_OVERHANG,
    )


def _draw_selection_frame(
    painter: QPainter,
    frame_rect: QRect,
    color: str,
    *,
    badge_text: str = "",
    font_size: int = 10,
    fill_color: str = "",
    fill_alpha: int = 0,
) -> None:
    outline = QColor(color)
    outline.setAlpha(GRID_SELECTION_OUTLINE_ALPHA)
    painter.setPen(
        QPen(
            outline,
            GRID_SELECTION_OUTLINE_WIDTH,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.SquareCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    if fill_color and fill_alpha > 0:
        fill = QColor(fill_color)
        fill.setAlpha(max(0, min(255, int(fill_alpha))))
        painter.setBrush(fill)
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(
        frame_rect,
        GRID_SELECTION_OUTLINE_RADIUS,
        GRID_SELECTION_OUTLINE_RADIUS,
    )

    if not badge_text:
        return
    badge_rect = QRect(
        frame_rect.left() + GRID_SELECTION_BADGE_MARGIN,
        frame_rect.bottom() - GRID_SELECTION_BADGE_HEIGHT - GRID_SELECTION_BADGE_MARGIN + 1,
        GRID_SELECTION_BADGE_WIDTH,
        GRID_SELECTION_BADGE_HEIGHT,
    )
    badge_fill = QColor(color)
    badge_fill.setAlpha(GRID_SELECTION_BADGE_FILL_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(badge_fill)
    painter.drawRoundedRect(badge_rect, 5, 5)
    painter.setPen(QColor(UI_TEXT_ON_ACCENT))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(font_size)
    painter.setFont(font)
    painter.drawText(
        badge_rect,
        Qt.AlignmentFlag.AlignCenter,
        badge_text,
    )


class CharacterSelectionOverlay(QWidget):
    """Paint roster selection frames above the character grid spacing."""

    def __init__(
        self,
        overlay_host: QWidget,
        scroll_area: QScrollArea,
        cards: Callable[[], Iterable[AssetIconLabel]],
    ) -> None:
        super().__init__(overlay_host)
        self._overlay_host = overlay_host
        self._scroll_area = scroll_area
        self._cards = cards
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._scroll_area.verticalScrollBar().valueChanged.connect(self.update)
        self._scroll_area.horizontalScrollBar().valueChanged.connect(self.update)
        self.sync_geometry()
        self.show()

    def sync_geometry(self) -> None:
        self.setGeometry(self._overlay_host.rect())
        self.raise_()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            viewport_rect = self._viewport_rect()
            painter.setClipRect(viewport_rect)
            for card in tuple(self._cards()):
                marker = card.selection_marker
                if marker is None or not card.isVisible():
                    continue
                icon_rect = card._displayed_icon_rect()
                if icon_rect.isNull() or not icon_rect.isValid():
                    continue
                card_rect = QRect(
                    self.mapFromGlobal(card.mapToGlobal(icon_rect.topLeft())),
                    icon_rect.size(),
                )
                if not card_rect.intersects(viewport_rect):
                    continue
                _draw_selection_frame(
                    painter,
                    _selection_frame_rect(card_rect),
                    marker.color,
                    badge_text=str(marker.slot_number),
                    font_size=max(8, min(11, card.base_size // 7)),
                )
        finally:
            painter.end()

    def _viewport_rect(self) -> QRect:
        viewport = self._scroll_area.viewport()
        return QRect(
            self.mapFromGlobal(viewport.mapToGlobal(viewport.rect().topLeft())),
            viewport.size(),
        )


class WeaponOwnerBadgeOverlay(QWidget):
    """Paint weapon owner side-icons above the weapon grid without affecting layout."""

    def __init__(
        self,
        overlay_host: QWidget,
        scroll_area: QScrollArea,
        container: QWidget,
        grid: QGridLayout,
        cards: Callable[[], Iterable[AssetIconLabel]],
    ) -> None:
        super().__init__(overlay_host)
        self._overlay_host = overlay_host
        self._scroll_area = scroll_area
        self._container = container
        self._grid = grid
        self._cards = cards
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._settle_geometry)
        self._scroll_area.verticalScrollBar().valueChanged.connect(self.update)
        self._scroll_area.horizontalScrollBar().valueChanged.connect(self.update)
        self.sync_geometry()
        self.show()

    def sync_geometry(self) -> None:
        self.setGeometry(self._overlay_host.rect())
        self.raise_()

    def schedule_settle(self) -> None:
        self._settle_timer.start(0)

    def _settle_geometry(self) -> None:
        self.sync_geometry()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            cards = tuple(self._cards())
            viewport_rect = self._viewport_rect()
            painter.save()
            painter.setClipRect(viewport_rect)
            for card in cards:
                self._draw_card_occupied_outline(painter, card, viewport_rect)
            painter.restore()
            painter.save()
            painter.setClipRect(viewport_rect)
            for card in cards:
                self._draw_card_owner_badge(painter, card, viewport_rect)
            painter.restore()
        finally:
            painter.end()

    def _viewport_rect(self) -> QRect:
        viewport = self._scroll_area.viewport()
        return QRect(
            self.mapFromGlobal(viewport.mapToGlobal(viewport.rect().topLeft())),
            viewport.size(),
        )

    def _weapon_rect_for_card(
        self,
        card: AssetIconLabel,
        viewport_rect: QRect,
    ) -> QRect:
        if not card.isVisible() or not card.owner_badges:
            return QRect()

        icon_rect = card._displayed_icon_rect()
        if icon_rect.isNull() or not icon_rect.isValid():
            return QRect()

        weapon_rect = QRect(
            self.mapFromGlobal(card.mapToGlobal(icon_rect.topLeft())),
            icon_rect.size(),
        )
        if not weapon_rect.intersects(viewport_rect):
            return QRect()
        return weapon_rect

    def _draw_card_occupied_outline(
        self,
        painter: QPainter,
        card: AssetIconLabel,
        viewport_rect: QRect,
    ) -> None:
        weapon_rect = self._weapon_rect_for_card(card, viewport_rect)
        if weapon_rect.isNull() or not weapon_rect.isValid():
            return

        _draw_selection_frame(
            painter,
            _selection_frame_rect(weapon_rect),
            WEAPON_PICKER_OCCUPIED_OUTLINE_COLOR,
            fill_color=WEAPON_PICKER_OCCUPIED_FILL_COLOR,
            fill_alpha=WEAPON_PICKER_OCCUPIED_FILL_ALPHA,
        )

    def _draw_card_owner_badge(
        self,
        painter: QPainter,
        card: AssetIconLabel,
        viewport_rect: QRect,
    ) -> None:
        weapon_rect = self._weapon_rect_for_card(card, viewport_rect)
        if weapon_rect.isNull() or not weapon_rect.isValid():
            return

        badge = card.owner_badges[0]
        side_icon_path = _text(badge.get("side_icon_path"))
        if not side_icon_path:
            return

        owner_pixmap = _owner_badge_icon_pixmap(
            side_icon_path,
            _weapon_owner_side_icon_size(weapon_rect),
            dpr=self.devicePixelRatioF(),
        )
        if owner_pixmap is None:
            return

        owner_size = logical_pixmap_size(owner_pixmap)
        owner_target = _weapon_owner_target_rect(
            weapon_rect,
            owner_size,
        )
        if not owner_target.intersects(self.rect()):
            return

        badge_size = owner_badge_size_for_icon(owner_target.size())
        badge_rect = owner_badge_rect_for_icon_rect(owner_target, badge_size)
        if badge_rect.isNull() or not badge_rect.isValid():
            return

        if OWNER_BADGE_TRACE or WEAPON_OWNER_OVERLAY_TRACE:
            container_rect = QRect(
                self.mapFromGlobal(self._container.mapToGlobal(self._container.rect().topLeft())),
                self._container.size(),
            )
            margins = self._grid.contentsMargins()
            print(
                "[OWNER_BADGE_TRACE] "
                "surface=weapon_picker_owner_overlay "
                f"overlay={_trace_rect(self.rect())} "
                f"viewport={_trace_rect(viewport_rect)} "
                f"container={_trace_rect(container_rect)} "
                f"grid_margins={margins.left()},{margins.top()},{margins.right()},{margins.bottom()} "
                f"grid_spacing={self._grid.horizontalSpacing()},{self._grid.verticalSpacing()} "
                f"weapon_rect={_trace_rect(weapon_rect)} "
                f"source={side_icon_path!r} "
                f"owner_scaled={owner_pixmap.width()}x{owner_pixmap.height()} "
                f"owner_dpr={owner_pixmap.devicePixelRatio():.3f} "
                f"owner_target={_trace_rect(owner_target)} "
                f"badge_size={badge_size.width()}x{badge_size.height()} "
                f"badge_rect={_trace_rect(badge_rect)} "
                f"owner_crosses_viewport={not viewport_rect.contains(owner_target)} "
                f"badge_crosses_viewport={not viewport_rect.contains(badge_rect)} "
                "computed_from=owner_icon_rect"
            )

        painter.drawPixmap(
            badge_rect,
            _owner_badge_background(badge_size, dpr=self.devicePixelRatioF()),
        )
        painter.drawPixmap(owner_target, owner_pixmap)


def _clear_grid(grid: QGridLayout) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _reset_grid_columns(grid: QGridLayout) -> None:
    for column in range(grid.columnCount()):
        grid.setColumnMinimumWidth(column, 0)
        grid.setColumnStretch(column, 0)


def _asset_metadata_mapping(asset: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = _mapping(asset.get("metadata"))
    return _mapping(metadata.get(key))


def _asset_owner_badges(asset: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _mapping(asset.get("metadata"))
    badges = metadata.get("owner_badges")
    if not isinstance(badges, list):
        return []
    return [dict(badge) for badge in badges if isinstance(badge, dict)]


def _asset_character_id(asset: dict[str, Any]) -> str:
    return _text(_asset_metadata_mapping(asset, "character").get("id"))


def _asset_grid_key(asset: dict[str, Any]) -> str:
    character_id = _asset_character_id(asset)
    if character_id:
        return f"character:{character_id}"
    weapon = _asset_metadata_mapping(asset, "weapon")
    weapon_id = _text(weapon.get("id"))
    variant_key = _text(weapon.get("variant_key"))
    filename = _text(asset.get("filename"))
    return f"weapon:{weapon_id}:{variant_key}:{filename}"


def _existing_project_file_path(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return ""
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _normalized_character_image_paths(
    character: dict[str, Any],
    *,
    asset_path: str = "",
) -> dict[str, Any]:
    normalized = dict(character)
    portrait_path = (
        _existing_project_file_path(asset_path)
        or _existing_project_file_path(normalized.get("local_portrait_path"))
        or _existing_project_file_path(normalized.get("portrait_path"))
        or _existing_project_file_path(normalized.get("crop"))
    )
    side_icon_path = (
        _existing_project_file_path(normalized.get("local_side_icon_path"))
        or _existing_project_file_path(normalized.get("side_icon_path"))
    )
    if portrait_path:
        normalized["portrait_path"] = portrait_path
        normalized["local_portrait_path"] = portrait_path
    if side_icon_path or portrait_path:
        normalized["side_icon_path"] = side_icon_path or portrait_path
        normalized["local_side_icon_path"] = side_icon_path or portrait_path
    return normalized


def _normalized_weapon_image_paths(
    weapon: dict[str, Any],
    *,
    asset_path: str = "",
) -> dict[str, Any]:
    if not weapon:
        return {}
    normalized = dict(weapon)
    icon_path = (
        _existing_project_file_path(asset_path)
        or _existing_project_file_path(normalized.get("local_icon_path"))
        or _existing_project_file_path(normalized.get("icon_path"))
    )
    if icon_path:
        normalized["icon_path"] = icon_path
        normalized["local_icon_path"] = icon_path
    return normalized


def _weapon_bonus_context(
    weapon: dict[str, Any],
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    try:
        with closing(connect_db(db_path)) as conn:
            return _weapon_bonus_context_from_conn(conn, weapon)
    except Exception:
        return {
            "weapon_passive_reference": {},
            "weapon_display_stat_effects": [],
        }


def _weapon_bonus_context_from_conn(conn, weapon: dict[str, Any] | None) -> dict[str, Any]:
    weapon = weapon or {}
    weapon_id = _text(weapon.get("id") or weapon.get("weapon_id"))
    refinement = _optional_int(weapon.get("refinement"))
    result: dict[str, Any] = {
        "weapon_passive_reference": {},
        "weapon_display_stat_effects": [],
    }
    if not weapon_id:
        return result
    try:
        passive_reference = get_weapon_passive_tooltip(
            conn,
            weapon_id=weapon_id,
            language=_account_content_language(),
        )
        weapon_effects = list_weapon_display_stat_effects(
            conn,
            weapon_id=weapon_id,
            refinement=refinement,
        )
    except Exception:
        return result
    if passive_reference:
        result["weapon_passive_reference"] = passive_reference
    if weapon_effects:
        result["weapon_display_stat_effects"] = weapon_effects
    return result


def _weapon_equipment_fingerprint(weapon: dict[str, Any]) -> str:
    return (
        _text(weapon.get("source_key"))
        or _text(weapon.get("weapon_fingerprint"))
        or _text(weapon.get("variant_key"))
    )


def _account_content_language() -> str:
    path = PROJECT_ROOT / "data" / "hoyolab" / "account_language.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return _text(data.get("contentLanguage")) if isinstance(data, dict) else ""


def _changed_marker_ids(
    before: dict[str, RosterSelectionMarker],
    after: dict[str, RosterSelectionMarker],
) -> set[str]:
    return {
        character_id
        for character_id in set(before) | set(after)
        if before.get(character_id) != after.get(character_id)
    }


def _character_weapon_type_filter_key(character: dict[str, Any]) -> str:
    for numeric_key in ("weapon_type", "type"):
        weapon_type_id = _optional_int(character.get(numeric_key))
        if weapon_type_id is not None:
            filter_key = WEAPON_TYPE_FILTER_BY_ID.get(weapon_type_id)
            if filter_key:
                return filter_key
    for text_key in ("weapon_type_name", "type_name", "weapon_type", "type"):
        token = _filter_token(character.get(text_key))
        if not token:
            continue
        filter_key = WEAPON_TYPE_FILTER_ALIASES.get(token)
        if filter_key:
            return filter_key
    return ""


def _empty_state_for_mode(mode: str) -> TeamBuilderState:
    return create_empty_team_builder_state(team_count=MODE_TEAM_COUNTS[_normalize_mode(mode)])


def _normalize_mode(mode: str) -> str:
    return MODE_DPS_DUMMY if mode == MODE_DPS_DUMMY else MODE_ABYSS


def _weapon_type_filter_keys(weapon: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for numeric_key in ("weapon_type", "type"):
        weapon_type_id = _optional_int(weapon.get(numeric_key))
        if weapon_type_id is not None:
            filter_key = WEAPON_TYPE_FILTER_BY_ID.get(weapon_type_id)
            if filter_key:
                keys.add(filter_key)
    for text_key in ("weapon_type_name", "type_name", "type"):
        token = _filter_token(weapon.get(text_key))
        if not token:
            continue
        filter_key = WEAPON_TYPE_FILTER_ALIASES.get(token)
        if filter_key:
            keys.add(filter_key)
    return keys


def _filter_token(value: Any) -> str:
    return (
        _text(value)
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("__", "_")
    )


def _weapon_matches_character(
    character: dict[str, Any],
    weapon: dict[str, Any],
) -> bool:
    character_type = _optional_int(character.get("weapon_type"))
    weapon_type = _optional_int(weapon.get("weapon_type"))
    if character_type is not None and weapon_type is not None:
        return character_type == weapon_type

    character_name = _text(character.get("weapon_type_name")).casefold()
    weapon_name = _text(
        weapon.get("weapon_type_name") or weapon.get("type_name")
    ).casefold()
    if character_name and weapon_name:
        return character_name == weapon_name
    return True


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def launch_app_shell() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = AppShell()
    window.show()
    return app.exec()


__all__ = [
    "AppShell",
    "AppShellController",
    "AssetIconLabel",
    "CharacterWeaponWorkspace",
    "LEFT_WORKSPACE_ARTIFACTS",
    "LEFT_WORKSPACE_CHARACTERS_WEAPONS",
    "LeftWorkspaceHost",
    "RosterSelectionMarker",
    "RightOperationsDock",
    "launch_app_shell",
]
