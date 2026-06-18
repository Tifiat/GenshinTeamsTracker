from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from run_workspace.right_panel_prototype_view_model import RightPanelSlotPrototypeViewModel
from ui.right_panel.common.metrics import (
    SLOT_BADGE_HEIGHT,
    SLOT_CARD_FIXED_HEIGHT,
    SLOT_CARD_MARGIN,
    SLOT_CARD_WIDTH,
    SLOT_CLUSTER_WIDTH,
    SLOT_DRAG_MIME_TYPE,
    SLOT_EQUIP_BOX_SIZE,
    SLOT_EQUIP_ICON_SIZE,
    SLOT_NAME_HEIGHT,
    SLOT_PORTRAIT_SIZE,
    SLOT_TOP_SPACING,
    SLOT_WARNING_BADGE_WIDTH,
    SLOT_WEAPON_ICON_SIZE,
    _set_custom_tooltip_text,
    _set_object_name,
)
from ui.right_panel.common.slot_parts import (
    BuildMiniSetStackWidget,
    RightPanelPortraitMiniBox,
    RightPanelWeaponMiniBox,
    _clean_set_bonus_description,
    _build_mini_set_stack_pixmap as _build_common_mini_set_stack_pixmap,
)


class RightPanelSlotCardWidget(QFrame):
    clicked = Signal(int, int)
    dropped = Signal(int, int, int, int)

    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
        *,
        allow_mutation: bool = True,
    ):
        super().__init__(parent)
        self._model = model
        self._allow_mutation = bool(allow_mutation)
        self._model_key: tuple[object, ...] | None = None
        self._warning_tooltip_controller = None
        self._press_pos = None
        self._drag_started = False
        self.setObjectName("SlotCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(SLOT_CARD_WIDTH)
        self.setFixedHeight(SLOT_CARD_FIXED_HEIGHT)
        self.setAcceptDrops(self._allow_mutation)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
        )
        outer.setSpacing(3)

        image_cluster = QWidget()
        image_cluster.setFixedWidth(SLOT_CLUSTER_WIDTH)
        cluster_layout = QVBoxLayout(image_cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(4)
        outer.addWidget(image_cluster, alignment=Qt.AlignmentFlag.AlignLeft)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SLOT_TOP_SPACING)
        cluster_layout.addLayout(top)

        portrait_size = QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE)
        self._portrait = RightPanelPortraitMiniBox(
            box_size=portrait_size,
            object_name="PortraitBox",
            empty_object_name="PortraitBoxEmpty",
        )
        top.addWidget(self._portrait, alignment=Qt.AlignmentFlag.AlignLeft)

        side = QVBoxLayout()
        side.setSpacing(4)
        side.setContentsMargins(0, 0, 0, 0)
        top.addLayout(side)

        self._weapon = RightPanelWeaponMiniBox(
            box_size=QSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE),
            pixmap_size=QSize(SLOT_WEAPON_ICON_SIZE, SLOT_WEAPON_ICON_SIZE),
            object_name="MiniEquipBox",
        )
        side.addWidget(self._weapon, alignment=Qt.AlignmentFlag.AlignLeft)

        self._artifact = BuildMiniSetStackWidget(model)
        side.addWidget(self._artifact, alignment=Qt.AlignmentFlag.AlignLeft)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)
        cluster_layout.addLayout(footer)

        self._stat_badge = QLabel("")
        self._stat_badge.setObjectName("StatBadge")
        self._stat_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stat_badge.setFixedSize(SLOT_PORTRAIT_SIZE, SLOT_BADGE_HEIGHT)
        footer.addWidget(self._stat_badge)
        footer.addSpacing(SLOT_TOP_SPACING)

        self._warning = QLabel("")
        self._warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._warning.setFixedSize(SLOT_WARNING_BADGE_WIDTH, SLOT_BADGE_HEIGHT)
        footer.addWidget(self._warning)

        self._name = QLabel("")
        self._name.setObjectName("SlotName")
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(False)
        self._name.setFixedHeight(SLOT_NAME_HEIGHT)
        outer.addWidget(self._name)
        self.set_model(model)

    def slot_position(self) -> tuple[int, int]:
        return self._model.team_index, self._model.slot_index

    def set_model(self, model: RightPanelSlotPrototypeViewModel) -> None:
        self._model = model
        _set_object_name(self, "SlotCardSelected" if model.is_selected else "SlotCard")

        model_key = (
            model.team_index,
            model.slot_index,
            model.is_empty,
            model.character_title,
            model.portrait_label,
            model.portrait_path,
            model.weapon_square_label,
            model.weapon_image_path,
            model.weapon_tooltip,
            model.artifact_square_label,
            model.artifact_image_path,
            tuple(model.build_mini_sets),
            model.stat_badge,
            model.warning_count,
            model.warning_tooltip,
        )
        if model_key == self._model_key:
            return

        self._model_key = model_key

        self._portrait.set_portrait(
            image_path=model.portrait_path,
            fallback_text=model.portrait_label,
            empty=model.is_empty,
        )

        self._weapon.set_weapon(
            image_path=model.weapon_image_path,
            fallback_text=model.weapon_square_label,
            tooltip=model.weapon_tooltip,
        )

        self._artifact.set_model(model)
        self._stat_badge.setText(model.stat_badge)

        if model.warning_count:
            _set_object_name(self._warning, "WarningBadge")
            self._warning.setText(f"!{model.warning_count}")
            self._warning_tooltip_controller = _set_custom_tooltip_text(
                self._warning,
                self._warning_tooltip_controller,
                model.warning_tooltip,
            )
        else:
            _set_object_name(self._warning, "")
            self._warning.setText("")
            self._warning_tooltip_controller = _set_custom_tooltip_text(
                self._warning,
                self._warning_tooltip_controller,
                "",
            )

        self._name.setText(model.character_title)

    def refresh_hidpi_pixmaps(self) -> None:
        self._model_key = None
        self.set_model(self._model)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if (
            not self._allow_mutation
            or self._press_pos is None
            or self._drag_started
            or self._model.is_empty
            or not (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            super().mouseMoveEvent(event)
            return

        distance = (event.position().toPoint() - self._press_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        self._drag_started = True
        payload = f"{self._model.team_index}:{self._model.slot_index}"
        mime = QMimeData()
        mime.setData(SLOT_DRAG_MIME_TYPE, QByteArray(payload.encode("ascii")))

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._press_pos = None
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            if self._press_pos is not None and not self._drag_started:
                self.clicked.emit(self._model.team_index, self._model.slot_index)
            self._press_pos = None
            self._drag_started = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._allow_mutation:
            event.ignore()
            return
        source = self._drag_source_from_event(event)
        if source is None or source == (self._model.team_index, self._model.slot_index):
            event.ignore()
            return
        self._set_drag_hover(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._allow_mutation:
            event.ignore()
            return
        source = self._drag_source_from_event(event)
        if source is None or source == (self._model.team_index, self._model.slot_index):
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._set_drag_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._allow_mutation:
            event.ignore()
            return
        source = self._drag_source_from_event(event)
        self._set_drag_hover(False)
        if source is None:
            event.ignore()
            return
        source_team_index, source_slot_index = source
        target = (self._model.team_index, self._model.slot_index)
        if source == target:
            event.ignore()
            return
        self.dropped.emit(
            source_team_index,
            source_slot_index,
            self._model.team_index,
            self._model.slot_index,
        )
        event.acceptProposedAction()

    def _drag_source_from_event(self, event) -> tuple[int, int] | None:
        mime = event.mimeData()
        if mime is None or not mime.hasFormat(SLOT_DRAG_MIME_TYPE):
            return None
        try:
            payload = bytes(mime.data(SLOT_DRAG_MIME_TYPE)).decode("ascii")
            team_text, slot_text = payload.split(":", 1)
            return int(team_text), int(slot_text)
        except (TypeError, ValueError):
            return None

    def _set_drag_hover(self, enabled: bool) -> None:
        if self.property("dragHover") == bool(enabled):
            return
        self.setProperty("dragHover", bool(enabled))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


def _build_mini_set_stack_pixmap(active_sets, *, dpr: float = 1.0):
    """Deprecated compatibility wrapper; implementation lives in slot_parts."""

    return _build_common_mini_set_stack_pixmap(
        tuple(active_sets),
        icon_size=QSize(SLOT_EQUIP_ICON_SIZE, SLOT_EQUIP_ICON_SIZE),
        dpr=dpr,
    )


# Deprecated compatibility name for old imports/tests.
RightPanelSlotPrototypeWidget = RightPanelSlotCardWidget

__all__ = [name for name in globals() if not name.startswith("__")]
