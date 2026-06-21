from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from localization import tr
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.ui_palette import (
    UI_BORDER_DEFAULT,
    UI_BG_INSET,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
)
from ui.right_panel.pvp._shared import (
    PVP_DRAFT_BAN_ACCENT,
    PVP_DRAFT_IMMUNE_ACCENT,
)
from ui.utils.pvp_colors import pvp_player_color


class PvpDraftOrderStrip(QWidget):
    """Painted 22-action Draft order; portraits fill accepted positions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pvp_draft_order_strip")
        self._positions: tuple[dict[str, Any], ...] = ()
        self._portrait_paths: dict[str, str] = {}
        self._pixmap_cache: dict[tuple[object, ...], QPixmap | None] = {}
        self._prepared: dict[int, QPixmap] = {}
        self._prepared_signature: tuple[object, ...] | None = None
        self.setMinimumHeight(132)

    def set_board(
        self,
        board: Mapping[str, Any],
        *,
        portrait_paths: Mapping[str, str],
    ) -> None:
        timeline = board.get("timeline")
        action_log = board.get("action_log")
        steps = timeline if isinstance(timeline, list) else []
        actions = action_log if isinstance(action_log, list) else []
        positions: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            required = step.get("required_actions")
            if not isinstance(required, list):
                continue
            for action_type in required:
                index = len(positions)
                accepted = actions[index] if index < len(actions) else None
                accepted_row = accepted if isinstance(accepted, Mapping) else {}
                positions.append(
                    {
                        "number": index + 1,
                        "seat": str(step.get("seat") or ""),
                        "action_type": str(action_type or ""),
                        "status": (
                            "complete"
                            if accepted_row
                            else "active"
                            if index == len(actions) and board.get("current_requirement") is not None
                            else "pending"
                        ),
                        "character_id": str(accepted_row.get("target_id") or ""),
                    }
                )
        self._positions = tuple(positions)
        self._portrait_paths = dict(portrait_paths)
        self._prepared_signature = None
        self.update()

    def position_count(self) -> int:
        return len(self._positions)

    def active_position(self) -> int:
        for row in self._positions:
            if row["status"] == "active":
                return int(row["number"])
        return 0

    def active_action_type(self) -> str:
        for row in self._positions:
            if row["status"] == "active":
                return str(row["action_type"])
        return ""

    def current_action_visual(self) -> dict[str, str]:
        return _current_action_visual(self._positions)

    def position_visual(self, number: int) -> dict[str, Any]:
        if not (1 <= int(number) <= len(self._positions)):
            return {}
        return _position_visual(self._positions[int(number) - 1])

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1, 132)

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
        ):
            self._prepared_signature = None
        return super().event(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if not self._positions:
            return
        self._prepare_pixmaps()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        try:
            self._draw_grouped_positions(painter)
        finally:
            painter.end()

    def _draw_grouped_positions(self, painter: QPainter) -> None:
        gap = 5
        margin = 2
        center_width = min(255, max(155, self.width() // 5))
        side_width = max(110, (self.width() - center_width - margin * 2 - 28) // 2)
        available_height = max(60, self.height() - margin * 2 - gap)
        left_rows = [
            (index, row)
            for index, row in enumerate(self._positions)
            if row["seat"] == "player_1"
        ]
        right_rows = [
            (index, row)
            for index, row in enumerate(self._positions)
            if row["seat"] == "player_2"
        ]
        columns = max(1, max((len(left_rows) + 1) // 2, (len(right_rows) + 1) // 2))
        cell_size = max(28, min(58, available_height // 2, side_width // columns))
        content_width = columns * cell_size + max(0, columns - 1) * gap
        content_height = cell_size * 2 + gap
        start_y = max(margin, (self.height() - content_height) // 2)
        center_rect = QRect(
            max(margin + content_width + 8, (self.width() - center_width) // 2),
            start_y,
            center_width,
            content_height,
        )
        left_x = max(margin, center_rect.left() - 10 - content_width)
        right_x = min(
            self.width() - margin - content_width,
            center_rect.right() + 10,
        )
        self._draw_position_group(
            painter,
            left_rows,
            QRect(left_x, start_y, content_width, content_height),
            cell_size,
            gap,
        )
        self._draw_current_action_card(painter, center_rect)
        self._draw_position_group(
            painter,
            right_rows,
            QRect(right_x, start_y, content_width, content_height),
            cell_size,
            gap,
        )

    def _draw_position_group(
        self,
        painter: QPainter,
        rows: list[tuple[int, Mapping[str, Any]]],
        bounds: QRect,
        cell_size: int,
        gap: int,
    ) -> None:
        columns = max(1, (len(rows) + 1) // 2)
        for local_index, (index, row) in enumerate(rows):
            rect = QRect(
                bounds.left() + (local_index % columns) * (cell_size + gap),
                bounds.top() + (local_index // columns) * (cell_size + gap),
                cell_size,
                cell_size,
            )
            self._draw_position(painter, index, row, rect)

    def _draw_current_action_card(self, painter: QPainter, rect: QRect) -> None:
        visual = _current_action_visual(self._positions)
        title = visual["title"]
        detail = visual["detail"]
        accent = visual["accent"]
        painter.setPen(QPen(QColor(accent), 2))
        fill = QColor(UI_BG_INSET)
        fill.setAlpha(178)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(rect), 8, 8)

        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(max(10, min(16, rect.width() // 14)))
        painter.setFont(title_font)
        painter.setPen(QColor(UI_TEXT_MUTED))
        painter.drawText(
            rect.adjusted(8, 8, -8, -rect.height() // 2),
            Qt.AlignmentFlag.AlignCenter,
            title,
        )

        detail_font = painter.font()
        detail_font.setBold(True)
        detail_font.setPointSize(max(15, min(24, rect.width() // 8)))
        painter.setFont(detail_font)
        painter.setPen(QColor(accent))
        painter.drawText(
            rect.adjusted(8, rect.height() // 2 - 5, -8, -8),
            Qt.AlignmentFlag.AlignCenter,
            detail,
        )

    def _prepare_pixmaps(self) -> None:
        signature = (
            round(self.devicePixelRatioF(), 3),
            tuple(
                (index, row["character_id"], self._portrait_paths.get(row["character_id"], ""))
                for index, row in enumerate(self._positions)
                if row["character_id"]
            ),
        )
        if signature == self._prepared_signature:
            return
        self._prepared = {}
        for index, row in enumerate(self._positions):
            path = self._portrait_paths.get(row["character_id"], "")
            if not path:
                continue
            result = load_hidpi_pixmap(
                path,
                QSize(62, 52),
                dpr=self.devicePixelRatioF(),
                aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                transform_mode=Qt.TransformationMode.SmoothTransformation,
                cache=self._pixmap_cache,
                cache_key_parts=("pvp_draft_order", row["character_id"]),
                surface="pvp_draft_order",
            )
            if result.pixmap is not None and not result.pixmap.isNull():
                self._prepared[index] = result.pixmap
        self._prepared_signature = signature

    def _draw_position(
        self,
        painter: QPainter,
        index: int,
        row: Mapping[str, Any],
        rect: QRect,
    ) -> None:
        visual = _position_visual(row)
        status = str(row["status"])
        action_type = str(row["action_type"])
        action_color = str(visual["overlay_color"])
        border_color = str(visual["border_color"])
        fill = QColor(action_color)
        fill.setAlpha(int(visual["overlay_alpha"]))
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(border_color), 3 if status == "active" else 2 if status == "complete" else 1))
        painter.drawRoundedRect(QRectF(rect), 5, 5)

        pixmap = self._prepared.get(index)
        if pixmap is not None:
            source = QRectF(0, 0, pixmap.width(), pixmap.height())
            target = _aspect_fit_rect(source, QRectF(rect.adjusted(2, 2, -2, -2)))
            painter.drawPixmap(target, pixmap, source)
            shade = QColor(action_color)
            shade.setAlpha(34 if status != "active" else 48)
            painter.fillRect(QRectF(rect), shade)
        else:
            font = painter.font()
            font.setBold(True)
            font.setPointSize(18)
            painter.setFont(font)
            painter.setPen(QColor(UI_TEXT_PRIMARY if status == "active" else UI_TEXT_MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(row["number"]))
            font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(QColor(action_color))
            painter.drawText(
                rect.adjusted(3, 2, -3, -3),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                _draft_action_short_label(action_type),
            )


def _aspect_fit_rect(source: QRectF, bounds: QRectF) -> QRectF:
    if source.width() <= 0 or source.height() <= 0:
        return bounds
    scale = min(bounds.width() / source.width(), bounds.height() / source.height())
    width = source.width() * scale
    height = source.height() * scale
    return QRectF(
        bounds.x() + (bounds.width() - width) / 2,
        bounds.y() + (bounds.height() - height) / 2,
        width,
        height,
    )


def _draft_action_color(action_type: str, *, seat_color: str) -> str:
    value = str(action_type or "").casefold()
    if "ban" in value:
        return PVP_DRAFT_BAN_ACCENT
    if "immune" in value or "immun" in value:
        return PVP_DRAFT_IMMUNE_ACCENT
    return seat_color


def _position_visual(row: Mapping[str, Any]) -> dict[str, Any]:
    seat_color = pvp_player_color(str(row["seat"]))
    status = str(row["status"])
    action_color = _draft_action_color(
        str(row["action_type"]),
        seat_color=seat_color,
    )
    return {
        "overlay_color": action_color,
        "overlay_alpha": 76 if status == "active" else 34,
        "border_color": (
            action_color if status in {"active", "complete"} else UI_BORDER_DEFAULT
        ),
    }


def _current_action_visual(rows: tuple[dict[str, Any], ...]) -> dict[str, str]:
    active = next((row for row in rows if row["status"] == "active"), None)
    complete = bool(rows) and active is None and all(
        row["status"] == "complete" for row in rows
    )
    if active is None:
        return {
            "title": tr("app_shell.pvp.draft.turn_complete"),
            "detail": tr("app_shell.pvp.draft.completed"),
            "accent": UI_STATE_SUCCESS if complete else UI_TEXT_MUTED,
            "seat": "",
            "action_type": "",
        }
    action_type = str(active["action_type"])
    seat = str(active["seat"])
    return {
        "title": tr("app_shell.pvp.draft.turn_title").format(
            player=_draft_seat_display(seat),
        ),
        "detail": _draft_action_turn_label(action_type),
        "accent": _draft_action_color(
            action_type,
            seat_color=pvp_player_color(seat),
        ),
        "seat": seat,
        "action_type": action_type,
    }


def _draft_action_short_label(action_type: str) -> str:
    value = str(action_type or "").casefold()
    if "ban" in value:
        return tr("app_shell.pvp.draft.ban").upper()
    if "immune" in value or "immun" in value:
        return tr("app_shell.pvp.draft.immune").upper()
    return tr("app_shell.pvp.draft.pick").upper()


def _draft_action_turn_label(action_type: str) -> str:
    value = str(action_type or "").casefold()
    if "ban" in value:
        return tr("app_shell.pvp.draft.turn_ban").upper()
    if "immune" in value or "immun" in value:
        return tr("app_shell.pvp.draft.turn_immune").upper()
    return tr("app_shell.pvp.draft.turn_pick").upper()


def _draft_seat_display(seat: str) -> str:
    if seat == "player_2":
        return tr("app_shell.pvp.draft.player_2")
    return tr("app_shell.pvp.draft.player_1")


__all__ = ["PvpDraftOrderStrip"]
