from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from localization import tr
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.ui_palette import (
    UI_ACCENT_TEAM_1,
    UI_ACCENT_TEAM_2,
    UI_BG_INSET,
    UI_BG_PANEL_RAISED,
    UI_BORDER_DEFAULT,
    UI_SELECTION_NEUTRAL_FILL,
    UI_STATE_DANGER,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
)


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
        self.setMinimumHeight(112)

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

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1, 112)

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
            columns = (len(self._positions) + 1) // 2
            gap = 4
            margin = 2
            cell_width = max(28, min(62, (self.width() - margin * 2 - gap * (columns - 1)) // columns))
            cell_height = max(46, (self.height() - margin * 2 - gap) // 2)
            content_width = columns * cell_width + max(0, columns - 1) * gap
            start_x = max(margin, (self.width() - content_width) // 2)
            for index, row in enumerate(self._positions):
                rect = QRect(
                    start_x + (index % columns) * (cell_width + gap),
                    margin + (index // columns) * (cell_height + gap),
                    cell_width,
                    cell_height,
                )
                self._draw_position(painter, index, row, rect)
        finally:
            painter.end()

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
        seat_color = UI_ACCENT_TEAM_1 if row["seat"] == "player_1" else UI_ACCENT_TEAM_2
        status = str(row["status"])
        action_type = str(row["action_type"])
        border_color = seat_color if status in {"active", "complete"} else UI_BORDER_DEFAULT
        fill_color = UI_BG_PANEL_RAISED if status == "complete" else UI_BG_INSET
        if status == "active":
            fill_color = seat_color
        fill = QColor(fill_color)
        fill.setAlpha(52 if status == "active" else 255)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(border_color), 3 if status == "active" else 1))
        painter.drawRoundedRect(QRectF(rect), 5, 5)

        pixmap = self._prepared.get(index)
        if pixmap is not None:
            source = QRectF(0, 0, pixmap.width(), pixmap.height())
            painter.drawPixmap(QRectF(rect.adjusted(2, 2, -2, -2)), pixmap, source)
            shade = QColor(UI_SELECTION_NEUTRAL_FILL)
            shade.setAlpha(28)
            painter.fillRect(QRectF(rect), shade)

        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(UI_TEXT_PRIMARY if status != "pending" else UI_TEXT_MUTED))
        painter.drawText(rect.adjusted(5, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, str(row["number"]))

        action_label = (
            tr("app_shell.pvp.draft.ban")
            if action_type == "ban_character"
            else tr("app_shell.pvp.draft.pick")
        )
        painter.setPen(QColor(UI_STATE_DANGER if action_type == "ban_character" else seat_color))
        painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, action_label[:1].upper())


__all__ = ["PvpDraftOrderStrip"]
