from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from localization import tr
from ui.right_panel.common.metrics import _set_custom_tooltip_text
from ui.right_panel.common.slot_parts import (
    RightPanelArtifactMiniZoneState,
    RightPanelArtifactMiniZoneWidget,
    RightPanelPortraitMiniBox,
    RightPanelWeaponMiniBox,
    slot_portrait_fallback,
)
from ui.right_panel.pvp._shared import (
    _refresh_qss,
)


class PvpPostDraftTargetSlotWidget(QFrame):
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
        self._clickable = False
        self._clear_tooltip_controller = None
        self.setObjectName("pvp-team-slot")
        self.setFixedSize(92, 82)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        root.addLayout(top)

        self.portrait_label = RightPanelPortraitMiniBox(
            box_size=QSize(46, 46),
            object_name="pvp-target-slot-portrait",
        )
        top.addWidget(self.portrait_label)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(3)
        top.addLayout(side)

        self.weapon_label = RightPanelWeaponMiniBox(
            box_size=QSize(28, 28),
            pixmap_size=QSize(24, 24),
            object_name="pvp-target-slot-weapon",
        )
        side.addWidget(self.weapon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.artifact_label = RightPanelArtifactMiniZoneWidget(
            box_size=QSize(28, 12),
            icon_size=QSize(12, 12),
            object_name="pvp-target-slot-artifact",
            missing_object_name="pvp-target-slot-artifact",
        )
        self.artifact_label.setVisible(False)
        side.addWidget(self.artifact_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.clear_button = QPushButton("x")
        self.clear_button.setObjectName("row_cancel_button")
        self.clear_button.clicked.connect(self.clear_assignment_requested.emit)
        side.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.name_label = QLabel("")
        self.name_label.setObjectName("pvp-target-slot-name")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedHeight(16)
        root.addWidget(self.name_label)

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
        self._clickable = bool(clickable)
        has_character = bool(character_id)
        has_weapon = bool(weapon_stack_key)
        self.setProperty("seat", seat)
        self.setProperty("teamIndex", team_index)
        self.setProperty("slotIndex", slot_index)
        self.setProperty("characterId", character_id)
        self.setProperty("stackKey", weapon_stack_key)
        self.setProperty("hasCharacter", has_character)
        self.setProperty("selectedAssignment", selected_assignment)
        self.setProperty("selectedWeaponCharacter", selected_weapon_character)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._clickable
            else Qt.CursorShape.ArrowCursor
        )

        portrait_loaded = self.portrait_label.set_portrait(
            image_path=portrait_path,
            fallback_text=slot_portrait_fallback(character_name, slot_index),
            empty=not has_character,
            surface="pvp_postdraft_target_portrait",
        )
        self.setProperty("hasPortraitPixmap", portrait_loaded)

        weapon_loaded = self.weapon_label.set_weapon(
            image_path=weapon_image_path,
            fallback_text="W" if has_weapon else "-",
            tooltip=weapon_tooltip or weapon_name,
            assigned=has_weapon,
            surface="pvp_postdraft_target_weapon",
        )
        self.setProperty("hasWeaponPixmap", weapon_loaded)
        self.artifact_label.set_state(RightPanelArtifactMiniZoneState())

        self.clear_button.setVisible(clear_mode in {"assignment", "weapon"})
        self.clear_button.setEnabled(
            (clear_mode == "assignment" and has_character)
            or (clear_mode == "weapon" and has_weapon)
        )
        try:
            self.clear_button.clicked.disconnect()
        except RuntimeError:
            pass
        if clear_mode == "weapon":
            self.clear_button.clicked.connect(self.clear_weapon_requested.emit)
            clear_text = tr("app_shell.pvp.post.clear_weapon")
        else:
            self.clear_button.clicked.connect(self.clear_assignment_requested.emit)
            clear_text = ""
        self._clear_tooltip_controller = _set_custom_tooltip_text(
            self.clear_button,
            self._clear_tooltip_controller,
            clear_text,
        )

        self.name_label.setText(character_name if has_character else empty_label)
        _refresh_qss(self)
        _refresh_qss(self.portrait_label)
        _refresh_qss(self.weapon_label)

    def click(self) -> None:
        if self._clickable:
            self.clicked.emit()

    def refresh_hidpi_pixmaps(self) -> None:
        self.portrait_label.refresh_hidpi_pixmap()
        self.weapon_label.refresh_hidpi_pixmap()
        self.artifact_label.refresh_hidpi_pixmap()

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.Show,
        ):
            self.refresh_hidpi_pixmaps()
        return super().event(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._clickable:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


__all__ = ["PvpPostDraftTargetSlotWidget"]
