from __future__ import annotations

import json
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
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
    EquipmentError,
    equip_weapon,
    get_equipped_weapon_for_character,
    list_equipped_artifacts_for_character,
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
from ui.right_panel_prototype import (
    RIGHT_PANEL_PROTOTYPE_MIN_WIDTH,
    RightPanelPrototypeWidget,
)
from run_workspace.perf import log_perf, perf_ms, perf_now
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip


RIGHT_OPERATIONS_DOCK_WIDTH = RIGHT_PANEL_PROTOTYPE_MIN_WIDTH
RIGHT_PANEL_REFRESH_DEBOUNCE_MS = 30
RIGHT_PANEL_FAST_REFRESH_MS = 1
WEAPON_FILTER_SYNC_DEBOUNCE_MS = 80
PERSISTENT_EQUIPMENT_HYDRATION_DELAY_MS = 40
MODE_TEAM_COUNTS = {
    MODE_ABYSS: 2,
    MODE_DPS_DUMMY: 1,
}
TEAM_MARKER_COLORS = ("#3ed47b", "#4e91ff")
_SCALED_ICON_PIXMAP_CACHE: dict[tuple[str, int, int, int, int], QPixmap] = {}
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

FILTER_BUTTON_STYLE = """
QPushButton#app_shell_filter_button {
    border: 2px solid transparent;
    border-radius: 15px;
    background-color: #202228;
    padding: 1px;
}
QPushButton#app_shell_filter_button:hover {
    background-color: #292c34;
}
QPushButton#app_shell_filter_button:checked {
    border-color: #4e91ff;
    background-color: #252936;
}
QPushButton#app_shell_filter_button[standardOnly="true"] {
    border-color: #4e91ff;
    background-color: #252936;
}
"""


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
                equip_weapon(conn, character_id, weapon_fingerprint)
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

        self.invalidate_persistent_equipment_cache({character_id})
        weapon = persisted_weapon or weapon
        self.state = self.state.set_weapon(
            self.selected_team_index,
            self.selected_slot_index,
            weapon,
        )
        details["account_character"] = dict(character)
        details["account_weapon"] = dict(weapon)
        details["weapon_image_path"] = _text(weapon.get("icon_path"))
        details.update(_weapon_bonus_context(weapon, db_path=self.equipment_db_path))
        self.state = self.state.attach_character_details_data(
            self.selected_team_index,
            self.selected_slot_index,
            details,
        )
        self.last_equipment_error = ""
        self._store_current_mode_state()
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
        self.resize(1408, 820)

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self.left_host = LeftWorkspaceHost(
            artifact_db_path=self.controller.equipment_db_path,
            artifact_equipment_changed=self._on_artifact_browser_equipment_changed,
        )
        root.addWidget(self.left_host, 1)

        self.right_panel = RightPanelPrototypeWidget(self.controller.right_panel_model())
        self.right_dock = RightOperationsDock(self.right_panel)
        root.addWidget(self.right_dock, 0)

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

        self.right_panel.mode_requested.connect(self._on_mode_requested)
        self.right_panel.slot_selected.connect(self._on_slot_selected)
        self.right_panel.external_bonuses_toggled.connect(
            self._on_external_bonuses_toggled
        )
        self.left_host.character_weapon_workspace.character_clicked.connect(
            self._on_character_clicked
        )
        self.left_host.character_weapon_workspace.weapon_clicked.connect(
            self._on_weapon_clicked
        )
        self._refresh_character_selection_markers()
        self._sync_artifact_browser_operation_target()

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
        self.controller.set_mode(mode)
        marker_timings = self._refresh_character_selection_markers(
            affected_character_ids=None
        )
        self._sync_artifact_browser_operation_target()
        self.schedule_weapon_filter_sync()
        self.schedule_right_panel_refresh()
        log_perf("mode_switch", mode=mode, **marker_timings)

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

        self.character_weapon_workspace = CharacterWeaponWorkspace()
        self.add_workspace(
            tr("app_shell.workspace.characters_weapons"),
            self.character_weapon_workspace,
        )
        self.artifact_browser_workspace = None
        self._pending_artifact_right_panel_target: dict[str, Any] | None = None
        self.artifact_browser_placeholder = self._make_artifact_browser_placeholder()
        self.artifact_browser_index = self.stack.addWidget(
            self.artifact_browser_placeholder
        )
        self.artifact_browser_button = QPushButton(tr("app_shell.workspace.artifacts"))
        self.artifact_browser_button.setCheckable(True)
        self.artifact_browser_button.clicked.connect(
            lambda _checked=False: self.show_artifact_browser_workspace()
        )
        self.nav_group.addButton(self.artifact_browser_button)
        self.nav_layout.addWidget(self.artifact_browser_button)

    def _make_artifact_browser_placeholder(self) -> QWidget:
        placeholder = QFrame()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(tr("artifact.browser.title"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label, 1)
        return placeholder

    def add_workspace(self, label: str, widget: QWidget) -> QPushButton:
        index = self.stack.addWidget(widget)
        button = QPushButton(label)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, page=index: self.stack.setCurrentIndex(page))
        self.nav_group.addButton(button)
        self.nav_layout.addWidget(button)
        if index == 0:
            button.setChecked(True)
            self.stack.setCurrentIndex(0)
        return button

    def show_artifact_browser_workspace(self) -> None:
        self.ensure_artifact_browser_workspace()
        self.stack.setCurrentIndex(self.artifact_browser_index)
        self.artifact_browser_button.setChecked(True)

    def ensure_artifact_browser_workspace(self):
        if self.artifact_browser_workspace is not None:
            return self.artifact_browser_workspace

        from ui.artifact_browser.window import ArtifactBrowserWindow

        create_start = perf_now()
        browser = ArtifactBrowserWindow(
            parent=self.stack,
            embedded=True,
            db_path=self.artifact_db_path,
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


class RightOperationsDock(QFrame):
    def __init__(self, operation_widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightOperationsDock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(operation_widget)

        operation_widget.setMinimumWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setFixedWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)


class CharacterWeaponWorkspace(QWidget):
    character_clicked = Signal(dict)
    weapon_clicked = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        self._weapon_type_buttons: dict[str, QPushButton] = {}
        self._auto_weapon_type_filter: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        root.addWidget(QLabel(tr("asset_panel.weapons")))
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

        root.addWidget(QLabel(tr("asset_panel.characters")))
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
        self.char_area, self.char_widget, self.char_grid = self._make_grid_area()
        root.addWidget(self.char_area, 3)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_grid_built:
            self._initial_grid_built = True
            QTimer.singleShot(0, self.update_grids)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
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

    def _character_asset_items(self) -> tuple[list[dict], float, str]:
        load_start = perf_now()
        source = "cache"
        if self._all_character_items is None:
            source = "sqlite"
            self._all_character_items = list(load_account_character_asset_items())
        return list(self._all_character_items), perf_ms(load_start), source

    def _weapon_asset_items(self) -> tuple[list[dict], float, str]:
        load_start = perf_now()
        source = "cache"
        if self._all_weapon_items is None:
            source = "sqlite"
            self._all_weapon_items = list(load_account_weapon_stack_asset_items())
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
        )
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
            icon_size=48,
            spacing=6,
            clicked=self.weapon_clicked.emit,
            grid_name="weapons",
        )
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
        button.setFixedSize(30, 30)
        button.setIconSize(QSize(24, 24))
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
        button.setFixedSize(30, 30)
        button.setIconSize(QSize(24, 24))
        button.setStyleSheet(FILTER_BUTTON_STYLE)
        button.setIcon(standard_character_filter_icon(STANDARD_FILTER_ALL, size=24))
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
                standard_character_filter_icon(self._character_standard_filter, size=24)
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
        grid.setContentsMargins(left_margin, 0, right_margin, 0)
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
                    character_id = _asset_character_id(asset)
                    if character_id:
                        card_registry[character_id] = icon
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
    path = Path(image_path)
    target_px = max(1, int(size * dpr))
    dpr_key = int(round(dpr * 1000))
    try:
        stat = path.stat()
        mtime_ns = stat.st_mtime_ns
        file_size = stat.st_size
    except OSError:
        mtime_ns = 0
        file_size = 0
    key = (str(path), target_px, dpr_key, mtime_ns, file_size)
    cached = _SCALED_ICON_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached, True

    source = QPixmap(str(path))
    if source.isNull():
        _SCALED_ICON_PIXMAP_CACHE[key] = source
        return source, False

    pixmap = source.scaled(
        target_px,
        target_px,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    pixmap.setDevicePixelRatio(dpr)
    _SCALED_ICON_PIXMAP_CACHE[key] = pixmap
    return pixmap, False


class AssetIconLabel(QLabel):
    clicked = Signal(dict)

    def __init__(
        self,
        image_path: str,
        size: int,
        *,
        asset: dict[str, Any] | None = None,
        selection_marker: RosterSelectionMarker | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.asset = asset or {}
        self.base_size = int(size)
        self.selection_marker = selection_marker
        self._last_pixmap_cache_hit = False
        self._tooltip_controller = install_custom_tooltip(self)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_pixmap()
        QTimer.singleShot(0, self._update_pixmap)

    def set_selection_marker(self, marker: RosterSelectionMarker | None) -> None:
        self.selection_marker = marker
        self.update()

    def setToolTip(self, text: str) -> None:
        self._tooltip_controller.set_text(text or "")
        super().setToolTip("")

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
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
        if marker is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(marker.color)
        border = QColor(color)
        border.setAlpha(230)
        painter.setPen(QPen(border, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 7, 7)

        badge_rect = QRect(4, max(4, self.height() - 24), 24, 20)
        badge_fill = QColor(color)
        badge_fill.setAlpha(235)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(badge_fill)
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(8, min(11, self.base_size // 7)))
        painter.setFont(font)
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            str(marker.slot_number),
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(dict(self.asset))
            event.accept()
            return
        super().mousePressEvent(event)


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
    "LeftWorkspaceHost",
    "RosterSelectionMarker",
    "RightOperationsDock",
    "launch_app_shell",
]
