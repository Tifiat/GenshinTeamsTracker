from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from localization import tr
from ui.right_panel.common.compact_slot import RightPanelCompactSlotWidget
from ui.right_panel.common.slot_parts import (
    RightPanelArtifactMiniZoneState,
    slot_portrait_fallback,
)
from ui.right_panel.pvp._shared import (
    _refresh_qss,
)


class PvpPostDraftTargetSlotWidget(RightPanelCompactSlotWidget):
    """Compact PvP v0 target slot backed by shared right-panel visual parts.

    Artifact equipment is intentionally not implemented here yet; the hidden
    artifact mini-zone is a stable extension point for the later scoped PvP
    artifact session.
    """

    clicked = Signal()
    clear_assignment_requested = Signal()
    clear_weapon_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pvp-team-slot")
        self.portrait_label.setObjectName("pvp-target-slot-portrait")
        self.weapon_label.setObjectName("pvp-target-slot-weapon")
        self.artifact_label.setObjectName("pvp-target-slot-artifact")
        self.clear_button.setObjectName("pvp-target-slot-clear")
        self.name_label.setObjectName("pvp-target-slot-name")
        self.clear_requested.connect(self._emit_clear_for_mode)
        self._clear_mode = ""

    def configure(
        self,
        *,
        seat: str,
        team_index: int,
        slot_index: int,
        character_id: str,
        character_name: str,
        empty_label: str,
        portrait_path: str,
        weapon_stack_key: str,
        weapon_name: str,
        weapon_image_path: str,
        weapon_tooltip: str,
        selected_assignment: bool,
        selected_weapon_character: bool,
        clear_mode: str,
        clickable: bool,
    ) -> None:
        has_character = bool(character_id)
        has_weapon = bool(weapon_stack_key)
        self._clear_mode = clear_mode
        self.setProperty("seat", seat)
        self.setProperty("teamIndex", team_index)
        self.setProperty("slotIndex", slot_index)
        self.setProperty("characterId", character_id)
        self.setProperty("stackKey", weapon_stack_key)
        self.setProperty("hasCharacter", has_character)
        self.setProperty("selectedAssignment", selected_assignment)
        self.setProperty("selectedWeaponCharacter", selected_weapon_character)
        clear_enabled = (
            (clear_mode == "assignment" and has_character)
            or (clear_mode == "weapon" and has_weapon)
        )
        clear_tooltip = (
            tr("app_shell.pvp.post.clear_weapon")
            if clear_mode == "weapon"
            else ""
        )
        portrait_loaded, weapon_loaded = self.set_slot_visual(
            character_name=character_name,
            empty_label=empty_label,
            portrait_path=portrait_path,
            portrait_fallback=slot_portrait_fallback(character_name, slot_index),
            weapon_path=weapon_image_path,
            weapon_fallback="W" if has_character else "-",
            weapon_tooltip=weapon_tooltip or weapon_name,
            artifact_state=RightPanelArtifactMiniZoneState(),
            artifact_visible=False,
            has_character=has_character,
            has_weapon=has_weapon,
            selected=selected_assignment,
            secondary_selected=selected_weapon_character,
            clear_visible=clear_mode in {"assignment", "weapon"} and (has_character or has_weapon),
            clear_enabled=clear_enabled,
            clear_tooltip=clear_tooltip,
            clickable=clickable,
        )
        self.setProperty("hasPortraitPixmap", portrait_loaded)
        self.setProperty("hasWeaponPixmap", weapon_loaded)
        _refresh_qss(self)
        _refresh_qss(self.portrait_label)
        _refresh_qss(self.weapon_label)

    def click(self) -> None:
        if self._clickable:
            self.clicked.emit()

    def _emit_clear_for_mode(self) -> None:
        if self._clear_mode == "weapon":
            self.clear_weapon_requested.emit()
        else:
            self.clear_assignment_requested.emit()


__all__ = ["PvpPostDraftTargetSlotWidget"]
