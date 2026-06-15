from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from localization import tr
from ui.right_panel.pvp._shared import (
    _refresh_qss,
    _set_custom_tooltip_text,
    _set_label_hidpi_pixmap,
    _slot_portrait_fallback,
)


class PvpPostDraftTargetSlotWidget(QFrame):
    clicked = Signal()
    clear_assignment_requested = Signal()
    clear_weapon_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clickable = False
        self._portrait_path = ""
        self._weapon_path = ""
        self._weapon_tooltip_controller = None
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

        self.portrait_label = QLabel("")
        self.portrait_label.setObjectName("pvp-target-slot-portrait")
        self.portrait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait_label.setFixedSize(46, 46)
        top.addWidget(self.portrait_label)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(3)
        top.addLayout(side)

        self.weapon_label = QLabel("")
        self.weapon_label.setObjectName("pvp-target-slot-weapon")
        self.weapon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weapon_label.setFixedSize(28, 28)
        side.addWidget(self.weapon_label, alignment=Qt.AlignmentFlag.AlignLeft)

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
        self._portrait_path = portrait_path
        self._weapon_path = weapon_image_path
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

        portrait_loaded = _set_label_hidpi_pixmap(
            self.portrait_label,
            portrait_path,
            QSize(46, 46),
            surface="pvp_postdraft_target_portrait",
        )
        self.setProperty("hasPortraitPixmap", portrait_loaded)
        self.portrait_label.setProperty("hasPixmap", portrait_loaded)
        if not portrait_loaded:
            self.portrait_label.setText(_slot_portrait_fallback(character_name, slot_index))

        weapon_loaded = _set_label_hidpi_pixmap(
            self.weapon_label,
            weapon_image_path,
            QSize(24, 24),
            surface="pvp_postdraft_target_weapon",
        )
        self.setProperty("hasWeaponPixmap", weapon_loaded)
        self.weapon_label.setProperty("hasPixmap", weapon_loaded)
        self.weapon_label.setProperty("assigned", has_weapon)
        if not weapon_loaded:
            self.weapon_label.setText("W" if has_weapon else "-")
        self._weapon_tooltip_controller = _set_custom_tooltip_text(
            self.weapon_label,
            self._weapon_tooltip_controller,
            weapon_tooltip or weapon_name,
        )

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
        _set_label_hidpi_pixmap(
            self.portrait_label,
            self._portrait_path,
            QSize(46, 46),
            surface="pvp_postdraft_target_portrait",
        )
        _set_label_hidpi_pixmap(
            self.weapon_label,
            self._weapon_path,
            QSize(24, 24),
            surface="pvp_postdraft_target_weapon",
        )

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
