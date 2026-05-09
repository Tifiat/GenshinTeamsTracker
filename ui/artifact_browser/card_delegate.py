from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from .list_model import ArtifactRoles
from .models import ArtifactItem
from .stat_types import is_crit_type, stat_badge


CARD_SIZE = QSize(248, 138)
GRID_SIZE = QSize(260, 150)
ICON_SIZE = QSize(56, 56)

CV_COLORS = [
    (0.0, 14.9, "#9b9b9b"),      # gray
    (15.0, 24.9, "#3f8cff"),     # blue
    (25.0, 34.9, "#b27cff"),     # purple
    (35.0, 44.9, "#ff9c47"),     # orange
    (45.0, 49.9, "#ffe066"),     # yellow
    (50.0, 9999.0, "#62d0ff"),   # cyan
]

_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def cached_scaled_pixmap(icon_path: Path, size: QSize) -> QPixmap | None:
    key = (str(icon_path.resolve()), size.width(), size.height())

    cached = _PIXMAP_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached

    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        return None

    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _PIXMAP_CACHE[key] = scaled
    return scaled


def cv_color(artifact: ArtifactItem) -> QColor:
    effective_cv = artifact.cv

    if artifact.pos == 5 and is_crit_type(artifact.main_property_type):
        effective_cv = artifact.cv * 2

    for lower, upper, color in CV_COLORS:
        if lower <= effective_cv <= upper:
            return QColor(color)

    return QColor("#9b9b9b")


def roll_text(times: int | None) -> str:
    value = int(times or 0)
    return f"×{value}" if value > 0 else ""


class ArtifactCardDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.custom_edit_artifact_ids: set[int] = set()

    def set_custom_edit_artifact_ids(self, artifact_ids: set[int]) -> None:
        self.custom_edit_artifact_ids = set(artifact_ids)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QSize:
        return GRID_SIZE

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        artifact = index.data(ArtifactRoles.ArtifactRole)
        if artifact is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        card_rect = self._card_rect(option)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        custom_edit_selected = artifact.id in self.custom_edit_artifact_ids

        if custom_edit_selected:
            background = QColor("#2d2b1f") if not hovered else QColor("#383526")
            border = QColor("#d6b15d")
        else:
            background = QColor("#252a33") if hovered else QColor("#20232a")
            border = QColor("#7da7ff") if selected else QColor("#6f86b8" if hovered else "#3a3f4b")

        painter.setPen(QPen(border, 2 if selected or custom_edit_selected else 1))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(card_rect), 10, 10)

        self._draw_main_stat(painter, option, card_rect, artifact)
        self._draw_icon_block(painter, option, card_rect, artifact)
        self._draw_substats(painter, option, card_rect, artifact)

        painter.restore()

    @staticmethod
    def _card_rect(option: QStyleOptionViewItem) -> QRect:
        x = option.rect.x() + (option.rect.width() - CARD_SIZE.width()) // 2
        y = option.rect.y() + (option.rect.height() - CARD_SIZE.height()) // 2
        return QRect(x, y, CARD_SIZE.width(), CARD_SIZE.height())

    def _draw_main_stat(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        card_rect: QRect,
        artifact: ArtifactItem,
    ) -> None:
        font = QFont(option.font)
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f0d58a"))

        text = f"{artifact.main_property_name}: {artifact.main_property_value}"
        text_rect = QRect(
            card_rect.x() + 8,
            card_rect.y() + 7,
            card_rect.width() - 16,
            18,
        )
        metrics = QFontMetrics(font)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )

    def _draw_icon_block(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        card_rect: QRect,
        artifact: ArtifactItem,
    ) -> None:
        icon_rect = QRect(
            card_rect.x() + 8,
            card_rect.y() + 34,
            ICON_SIZE.width(),
            ICON_SIZE.height(),
        )

        if artifact.icon_path:
            pixmap = cached_scaled_pixmap(artifact.icon_path, ICON_SIZE)
        else:
            pixmap = None

        if pixmap is not None:
            target = QRect(
                icon_rect.x() + (icon_rect.width() - pixmap.width()) // 2,
                icon_rect.y() + (icon_rect.height() - pixmap.height()) // 2,
                pixmap.width(),
                pixmap.height(),
            )
            painter.drawPixmap(target, pixmap)
        else:
            painter.setPen(QPen(QColor("#4a5060"), 1))
            painter.setBrush(QColor("#262b34"))
            painter.drawRoundedRect(QRectF(icon_rect), 7, 7)

            font = QFont(option.font)
            font.setPointSize(18)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#d8c36a"))
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "★")

        cv_rect = QRect(
            card_rect.x() + 6,
            icon_rect.bottom() + 5,
            ICON_SIZE.width() + 4,
            18,
        )
        font = QFont(option.font)
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(cv_color(artifact))
        cv_text = "CV —" if artifact.cv <= 0 else f"CV {artifact.cv:.1f}"
        painter.drawText(cv_rect, Qt.AlignmentFlag.AlignCenter, cv_text)

        level_rect = QRect(
            card_rect.x() + 6,
            cv_rect.bottom() + 1,
            ICON_SIZE.width() + 4,
            18,
        )
        font = QFont(option.font)
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f0d58a"))
        painter.drawText(level_rect, Qt.AlignmentFlag.AlignCenter, f"+{artifact.level}")

    def _draw_substats(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        card_rect: QRect,
        artifact: ArtifactItem,
    ) -> None:
        x = card_rect.x() + 72
        y = card_rect.y() + 33
        width = card_rect.width() - 80
        row_height = 23

        for index, substat in enumerate(artifact.substats[:4]):
            row_rect = QRect(x, y + index * row_height, width, 19)
            self._draw_substat_row(painter, option, row_rect, substat)

    def _draw_substat_row(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        row_rect: QRect,
        substat,
    ) -> None:
        badge_rect = QRect(row_rect.x(), row_rect.y(), 48, 18)

        painter.setPen(QPen(QColor("#475066"), 1))
        painter.setBrush(QColor("#2d3340"))
        painter.drawRoundedRect(QRectF(badge_rect), 6, 6)

        badge_font = QFont(option.font)
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QColor("#d9e2ff"))
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            stat_badge(substat.property_type),
        )

        roll = roll_text(substat.times)
        roll_width = 24 if roll else 0

        value_rect = QRect(
            badge_rect.right() + 6,
            row_rect.y(),
            max(10, row_rect.width() - badge_rect.width() - roll_width - 12),
            18,
        )

        value_font = QFont(option.font)
        value_font.setPointSize(9)
        painter.setFont(value_font)
        painter.setPen(QColor("#aab0bd"))

        metrics = QFontMetrics(value_font)
        value = metrics.elidedText(
            str(substat.value),
            Qt.TextElideMode.ElideRight,
            value_rect.width(),
        )
        painter.drawText(
            value_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            value,
        )

        if roll:
            roll_rect = QRect(
                row_rect.right() - roll_width,
                row_rect.y(),
                roll_width,
                18,
            )
            painter.setPen(QColor("#9aa4b5"))
            painter.drawText(
                roll_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                roll,
            )
