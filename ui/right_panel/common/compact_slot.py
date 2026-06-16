from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.right_panel.common.metrics import _set_custom_tooltip_text
from ui.right_panel.common.slot_parts import (
    RightPanelArtifactMiniZoneState,
    RightPanelArtifactMiniZoneWidget,
    RightPanelPortraitMiniBox,
    RightPanelWeaponMiniBox,
)


class RightPanelCompactSlotWidget(QFrame):
    """Reusable compact right-panel build slot for dense stage panels."""

    clicked = Signal()
    clear_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        slot_size: QSize | None = None,
        portrait_size: QSize | None = None,
        weapon_box_size: QSize | None = None,
        weapon_pixmap_size: QSize | None = None,
        artifact_box_size: QSize | None = None,
        artifact_icon_size: QSize | None = None,
    ) -> None:
        super().__init__(parent)
        self._clickable = False
        self._clear_tooltip_controller = None
        self.setObjectName("CompactSlotCard")
        self.setFixedSize(slot_size or QSize(112, 102))

        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)
        root.addLayout(top)

        self.portrait_label = RightPanelPortraitMiniBox(
            box_size=portrait_size or QSize(62, 62),
            object_name="CompactSlotPortrait",
            empty_object_name="CompactSlotPortraitEmpty",
        )
        top.addWidget(self.portrait_label, alignment=Qt.AlignmentFlag.AlignLeft)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(4)
        top.addLayout(side)

        self.weapon_label = RightPanelWeaponMiniBox(
            box_size=weapon_box_size or QSize(31, 31),
            pixmap_size=weapon_pixmap_size or QSize(28, 28),
            object_name="CompactSlotWeapon",
        )
        side.addWidget(self.weapon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.artifact_label = RightPanelArtifactMiniZoneWidget(
            box_size=artifact_box_size or QSize(31, 16),
            icon_size=artifact_icon_size or QSize(15, 15),
            object_name="CompactSlotArtifact",
            missing_object_name="CompactSlotArtifact",
        )
        self.artifact_label.setVisible(False)
        side.addWidget(self.artifact_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.clear_button = QPushButton("x")
        self.clear_button.setObjectName("CompactSlotClearButton")
        self.clear_button.clicked.connect(self.clear_requested.emit)
        side.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignLeft)

        side.addStretch(1)

        self.name_label = QLabel("")
        self.name_label.setObjectName("CompactSlotName")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedHeight(18)
        root.addWidget(self.name_label)

    def set_slot_visual(
        self,
        *,
        character_name: str,
        empty_label: str,
        portrait_path: str,
        portrait_fallback: str,
        weapon_path: str,
        weapon_fallback: str,
        weapon_tooltip: str = "",
        artifact_state: RightPanelArtifactMiniZoneState | None = None,
        artifact_visible: bool = False,
        has_character: bool = False,
        has_weapon: bool = False,
        selected: bool = False,
        secondary_selected: bool = False,
        clear_visible: bool = False,
        clear_enabled: bool = False,
        clear_tooltip: str = "",
        clickable: bool = False,
    ) -> tuple[bool, bool]:
        self._clickable = bool(clickable)
        self.setProperty("hasCharacter", bool(has_character))
        self.setProperty("selected", bool(selected))
        self.setProperty("secondarySelected", bool(secondary_selected))
        self.setProperty("clearVisible", bool(clear_visible))
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._clickable
            else Qt.CursorShape.ArrowCursor
        )

        portrait_loaded = self.portrait_label.set_portrait(
            image_path=portrait_path,
            fallback_text=portrait_fallback,
            empty=not has_character,
            surface="right_panel_compact_slot_portrait",
        )
        self.setProperty("hasPortraitPixmap", portrait_loaded)

        weapon_loaded = self.weapon_label.set_weapon(
            image_path=weapon_path,
            fallback_text=weapon_fallback,
            tooltip=weapon_tooltip,
            assigned=has_weapon,
            surface="right_panel_compact_slot_weapon",
        )
        self.setProperty("hasWeaponPixmap", weapon_loaded)

        self.artifact_label.set_state(artifact_state or RightPanelArtifactMiniZoneState())
        self.artifact_label.setVisible(bool(artifact_visible))
        self.setProperty("hasArtifact", bool(artifact_visible))

        self.clear_button.setVisible(bool(clear_visible))
        self.clear_button.setEnabled(bool(clear_enabled))
        self._clear_tooltip_controller = _set_custom_tooltip_text(
            self.clear_button,
            self._clear_tooltip_controller,
            clear_tooltip,
        )

        self.name_label.setText(character_name if has_character else empty_label)
        _refresh_qss(self)
        _refresh_qss(self.portrait_label)
        _refresh_qss(self.weapon_label)
        _refresh_qss(self.artifact_label)
        _refresh_qss(self.clear_button)
        return portrait_loaded, weapon_loaded

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


def _refresh_qss(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


__all__ = ["RightPanelCompactSlotWidget"]
