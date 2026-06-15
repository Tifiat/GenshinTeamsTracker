from __future__ import annotations

import html
import re
from functools import lru_cache

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from run_workspace.right_panel_prototype_view_model import (
    RightPanelBuildMiniSetViewModel,
    RightPanelSlotPrototypeViewModel,
)
from ui.artifact_browser.queries import list_set_bonus_description_map
from ui.utils.hidpi_pixmap import effective_pixmap_dpr
from ui.utils.pixmap_utils import draw_count_badge, make_diagonal_split_pixmap
from ui.right_panel.common.metrics import *

class RightPanelSlotCardWidget(QFrame):
    clicked = Signal(int, int)
    dropped = Signal(int, int, int, int)

    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._model = model
        self._model_key: tuple[object, ...] | None = None
        self._weapon_tooltip_controller = None
        self._warning_tooltip_controller = None
        self._press_pos = None
        self._drag_started = False
        self.setObjectName("SlotCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(SLOT_CARD_WIDTH)
        self.setFixedHeight(SLOT_CARD_FIXED_HEIGHT)
        self.setAcceptDrops(True)

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

        self._portrait = QLabel("")
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait_size = QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE)
        self._portrait.setFixedSize(portrait_size)
        top.addWidget(self._portrait, alignment=Qt.AlignmentFlag.AlignLeft)

        side = QVBoxLayout()
        side.setSpacing(4)
        side.setContentsMargins(0, 0, 0, 0)
        top.addLayout(side)

        self._weapon = QLabel("")
        self._weapon.setObjectName("MiniEquipBox")
        self._weapon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weapon.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)
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

        _set_object_name(
            self._portrait,
            "PortraitBoxEmpty" if model.is_empty else "PortraitBox",
        )
        self._portrait.clear()
        portrait_pixmap = _fit_pixmap(
            model.portrait_path,
            QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE),
            dpr=self._portrait.devicePixelRatioF(),
        )
        if portrait_pixmap is not None:
            self._portrait.setPixmap(portrait_pixmap)
        else:
            self._portrait.setText(model.portrait_label)

        self._weapon.clear()
        self._weapon.setText(model.weapon_square_label)
        weapon_pixmap = _fit_pixmap(
            model.weapon_image_path,
            QSize(SLOT_WEAPON_ICON_SIZE, SLOT_WEAPON_ICON_SIZE),
            dpr=self._weapon.devicePixelRatioF(),
        )
        if weapon_pixmap is not None:
            self._weapon.setPixmap(weapon_pixmap)
        self._weapon_tooltip_controller = _set_custom_tooltip_text(
            self._weapon,
            self._weapon_tooltip_controller,
            model.weapon_tooltip,
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
            self._press_pos is None
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
        source = self._drag_source_from_event(event)
        if source is None or source == (self._model.team_index, self._model.slot_index):
            event.ignore()
            return
        self._set_drag_hover(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        source = self._drag_source_from_event(event)
        if source is None or source == (self._model.team_index, self._model.slot_index):
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._set_drag_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
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


class BuildMiniSetStackWidget(QLabel):
    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__("", parent)
        self._tooltip_controller = None
        self._model_key: tuple[object, ...] | None = None
        self._model = model
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)
        self.set_model(model)

    def set_model(self, model: RightPanelSlotPrototypeViewModel) -> None:
        self._model = model
        model_key = (
            model.artifact_square_label,
            model.artifact_image_path,
            tuple(model.build_mini_sets),
            int(round(effective_pixmap_dpr(self.devicePixelRatioF()) * 1000)),
        )
        if model_key == self._model_key:
            return

        self._model_key = model_key
        is_missing = model.artifact_square_label in {"Equip", "Fix", "ART"}
        _set_object_name(self, "MiniEquipBoxMissing" if is_missing else "MiniEquipBox")
        self.clear()
        self.setText(model.artifact_square_label)

        pixmap = _build_mini_set_stack_pixmap(
            model.build_mini_sets,
            dpr=self.devicePixelRatioF(),
        )
        if pixmap is None and model.artifact_image_path:
            pixmap = _fit_pixmap(
                model.artifact_image_path,
                QSize(SLOT_EQUIP_ICON_SIZE, SLOT_EQUIP_ICON_SIZE),
                dpr=self.devicePixelRatioF(),
            )
        if pixmap is not None:
            self.setText("")
            self.setPixmap(pixmap)
        elif model.build_mini_sets:
            self.setText(_build_mini_set_fallback_text(model.build_mini_sets))

        tooltip = _build_mini_set_tooltip_html(model.build_mini_sets)
        self._tooltip_controller = _set_custom_tooltip_text(
            self,
            self._tooltip_controller,
            tooltip,
        )

    def refresh_hidpi_pixmap(self) -> None:
        self._model_key = None
        self.set_model(self._model)


def _build_mini_set_stack_pixmap(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
    *,
    dpr: float = 1.0,
) -> QPixmap | None:
    active_sets = tuple(active_sets[:2])
    if not active_sets:
        return None

    icons: list[QPixmap] = []
    for item in active_sets:
        if not item.icon_path:
            continue
        icon = _build_mini_set_icon_pixmap(item.icon_path, dpr=dpr)
        if icon is not None and not icon.isNull():
            icons.append(icon)

    if len(active_sets) == 2 and len(icons) == 2:
        composite = make_diagonal_split_pixmap(
            icons[0],
            icons[1],
            width=SLOT_EQUIP_ICON_SIZE,
            height=SLOT_EQUIP_ICON_SIZE,
            feather=SLOT_BUILD_BONUS_FEATHER,
        )
        return draw_count_badge(composite, "2")

    if len(active_sets) == 1 and len(icons) == 1:
        count = active_sets[0].piece_count
        badge = str(count) if count in (2, 4) else ""
        return draw_count_badge(icons[0], badge) if badge else icons[0]

    return None


def _build_mini_set_icon_pixmap(path: str, *, dpr: float = 1.0) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            SLOT_EQUIP_ICON_SIZE,
            SLOT_EQUIP_ICON_SIZE,
            int(round(effective_pixmap_dpr(dpr) * 1000)),
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (
            str(path),
            SLOT_EQUIP_ICON_SIZE,
            SLOT_EQUIP_ICON_SIZE,
            int(round(effective_pixmap_dpr(dpr) * 1000)),
            0,
            0,
        )

    if key in _BUILD_MINI_SET_ICON_PIXMAP_CACHE:
        cached = _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    if not resolved.is_file():
        _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = None
        return None

    pixmap = QPixmap(str(resolved))
    if pixmap.isNull():
        _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = None
        return None
    result = _scale_trimmed_icon_for_chip(
        pixmap,
        SLOT_EQUIP_ICON_SIZE,
        SLOT_EQUIP_ICON_SIZE,
        padding=1,
        alpha_threshold=16,
        dpr=dpr,
    )
    _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = QPixmap(result)
    return result


def _build_mini_set_fallback_text(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    if len(active_sets) >= 2:
        return "+".join(str(item.piece_count) for item in active_sets[:2])
    if active_sets:
        return f"{active_sets[0].piece_count}p"
    return "Build"


def _build_mini_set_tooltip(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    rows = [
        f"{item.piece_count}p {item.set_name}"
        for item in active_sets[:2]
        if item.set_name
    ]
    return " / ".join(rows)


def _build_mini_set_tooltip_html(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    rows = _build_mini_set_tooltip_rows(active_sets)
    rendered_rows: list[str] = []
    for piece_count, description in rows:
        description_html = html.escape(description).replace("\n", "<br>")
        rendered_rows.append(
            "<tr>"
            "<td valign='top' style='padding: 1px 8px 5px 0;'>"
            "<span style='"
            "background-color: #4a3b22; "
            "color: #f0d58a; "
            "border: 1px solid #8f7440; "
            "border-radius: 5px; "
            "font-weight: 800; "
            "padding: 1px 6px;"
            f"'>{int(piece_count)}</span>"
            "</td>"
            "<td valign='top' style='padding: 1px 0 5px 0;'>"
            f"{description_html}"
            "</td>"
            "</tr>"
        )
    if not rendered_rows:
        return _build_mini_set_tooltip(active_sets)
    return (
        "<table cellspacing='0' cellpadding='0' "
        "style='color: #f4ead8; font-size: 12px; font-weight: 600;'>"
        f"{''.join(rendered_rows)}"
        "</table>"
    )


def _build_mini_set_tooltip_rows(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> list[tuple[int, str]]:
    descriptions = _set_bonus_descriptions()
    rows: list[tuple[int, str]] = []
    for item in active_sets[:2]:
        if not item.set_uid:
            continue
        piece_counts = (2, 4) if item.piece_count >= 4 else (2,) if item.piece_count >= 2 else ()
        for piece_count in piece_counts:
            description = _clean_set_bonus_description(
                descriptions.get((item.set_uid, piece_count), "")
            )
            if description:
                rows.append((piece_count, description))
    return rows


@lru_cache(maxsize=1)
def _set_bonus_descriptions() -> dict[tuple[str, int], str]:
    try:
        return list_set_bonus_description_map()
    except Exception:
        return {}


def _clean_set_bonus_description(description: str) -> str:
    text = str(description or "").strip()
    if not text:
        return ""
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


# Deprecated compatibility name for old imports/tests.
RightPanelSlotPrototypeWidget = RightPanelSlotCardWidget

__all__ = [name for name in globals() if not name.startswith("__")]
