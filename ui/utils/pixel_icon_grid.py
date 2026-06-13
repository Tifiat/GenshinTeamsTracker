from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from PySide6.QtCore import QEvent, QMargins, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ui.utils.hidpi_pixmap import (
    dpr_cache_key,
    load_hidpi_pixmap,
    logical_pixmap_size,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import (
    UI_SELECTION_BADGE_FILL_ALPHA,
    UI_SELECTION_NEUTRAL_FILL_ALPHA,
    UI_SELECTION_OUTLINE_ALPHA,
    UI_TEXT_ON_ACCENT,
)


@dataclass(frozen=True)
class PixelIconGridMetrics:
    item_width: int
    item_height: int | None = None
    gap_x: int = 0
    gap_y: int | None = None
    margin_top: int = 0
    margin_bottom: int = 0

    @property
    def resolved_item_height(self) -> int:
        return self.item_width if self.item_height is None else self.item_height

    @property
    def resolved_gap_y(self) -> int:
        return self.gap_x if self.gap_y is None else self.gap_y


@dataclass(frozen=True)
class PixelIconGridOutline:
    color: str
    width: int = 2
    radius: int = 4
    overhang: int = 0
    alpha: int = UI_SELECTION_OUTLINE_ALPHA
    fill_color: str = ""
    fill_alpha: int = 0
    badge_text: str = ""
    badge_width: int = 24
    badge_height: int = 20
    badge_margin: int = 4
    badge_fill_alpha: int = UI_SELECTION_BADGE_FILL_ALPHA
    badge_text_color: str = UI_TEXT_ON_ACCENT
    font_size: int = 10


@dataclass(frozen=True)
class PixelIconGridFill:
    color: str
    alpha: int = UI_SELECTION_NEUTRAL_FILL_ALPHA


@dataclass(frozen=True)
class PixelIconGridOverlayIcon:
    icon_path: str
    size_ratio: float = 1.0
    right_overhang_ratio: float = 0.0
    top_overhang_ratio: float = 0.0
    background_enabled: bool = False
    background_size_ratio: float = 43 / 70
    background_offset_x_ratio: float = 1 / 70
    background_offset_y_ratio: float = 16 / 70
    background_fill_color: str = "#6f7684"
    background_fill_alpha: int = 150
    background_border_color: str = "#ffffff"
    background_border_alpha: int = 210
    background_border_width: float = 2.0


@dataclass(frozen=True)
class PixelIconGridItem:
    item_id: str
    icon_path: str
    label: str = ""
    tooltip: str = ""
    enabled: bool = True
    outline: PixelIconGridOutline | None = None
    overlay_fill: PixelIconGridFill | None = None
    overlay_icons: tuple[PixelIconGridOverlayIcon, ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)
    pixmap_cache_key_parts: tuple[object, ...] = ()


@dataclass(frozen=True)
class PixelIconPhysicalLayout:
    columns: int
    rows: int
    rects: tuple[QRect, ...]
    item_width: int
    item_height: int
    gap_x: int
    gap_y: int
    margin_left: int
    margin_right: int
    margin_top: int
    margin_bottom: int
    content_width: int
    content_height: int
    dpr: float


def build_pixel_icon_grid_layout(
    item_count: int,
    viewport_width: int,
    metrics: PixelIconGridMetrics,
    *,
    dpr: float | int | None = 1.0,
) -> PixelIconPhysicalLayout:
    raw_dpr = max(0.001, float(dpr or 1.0))
    count = max(0, int(item_count))
    available_width = max(1, int(round(max(1, int(viewport_width)) * raw_dpr)))
    item_width = max(1, int(round(max(1, int(metrics.item_width)) * raw_dpr)))
    item_height = max(
        1,
        int(round(max(1, int(metrics.resolved_item_height)) * raw_dpr)),
    )
    gap_x = max(0, int(round(max(0, int(metrics.gap_x)) * raw_dpr)))
    gap_y = max(0, int(round(max(0, int(metrics.resolved_gap_y)) * raw_dpr)))
    margin_top = max(0, int(round(max(0, int(metrics.margin_top)) * raw_dpr)))
    margin_bottom = max(0, int(round(max(0, int(metrics.margin_bottom)) * raw_dpr)))

    if count <= 0:
        return PixelIconPhysicalLayout(
            columns=0,
            rows=0,
            rects=(),
            item_width=item_width,
            item_height=item_height,
            gap_x=gap_x,
            gap_y=gap_y,
            margin_left=0,
            margin_right=0,
            margin_top=0,
            margin_bottom=0,
            content_width=available_width,
            content_height=0,
            dpr=raw_dpr,
        )

    pitch_x = item_width + gap_x
    columns = max(1, (available_width + gap_x) // max(1, pitch_x))
    columns = min(columns, count)
    rows = int(math.ceil(count / columns))
    grid_width = columns * item_width + max(0, columns - 1) * gap_x
    margin_left = max(0, (available_width - grid_width) // 2)
    margin_right = max(0, available_width - grid_width - margin_left)

    rects = tuple(
        QRect(
            margin_left + (index % columns) * pitch_x,
            margin_top + (index // columns) * (item_height + gap_y),
            item_width,
            item_height,
        )
        for index in range(count)
    )
    content_height = (
        margin_top
        + rows * item_height
        + max(0, rows - 1) * gap_y
        + margin_bottom
    )
    return PixelIconPhysicalLayout(
        columns=columns,
        rows=rows,
        rects=rects,
        item_width=item_width,
        item_height=item_height,
        gap_x=gap_x,
        gap_y=gap_y,
        margin_left=margin_left,
        margin_right=margin_right,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        content_width=available_width,
        content_height=content_height,
        dpr=raw_dpr,
    )


class PixelIconGrid(QWidget):
    item_clicked = Signal(str)
    item_hovered = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        metrics: PixelIconGridMetrics | None = None,
        surface: str = "pixel_icon_grid",
    ) -> None:
        super().__init__(parent)
        self._metrics = metrics or PixelIconGridMetrics(item_width=48)
        self._surface = surface
        self._items: tuple[PixelIconGridItem, ...] = ()
        self._items_by_id: dict[str, PixelIconGridItem] = {}
        self._layout = build_pixel_icon_grid_layout(0, 1, self._metrics)
        self._prepared_pixmaps: dict[str, QPixmap] = {}
        self._prepared_overlay_pixmaps: dict[tuple[str, int], QPixmap] = {}
        self._prepared_backgrounds: dict[tuple[str, int, int], QPixmap] = {}
        self._pixmap_cache: dict[tuple[object, ...], QPixmap | None] = {}
        self._hovered_item_id = ""
        self._tooltip_anchor = QWidget(self)
        self._tooltip_anchor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._tooltip_anchor.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._tooltip_anchor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._tooltip_anchor.setGeometry(QRect())
        self._tooltip_anchor.show()
        self._tooltip_controller = install_custom_tooltip(self._tooltip_anchor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_metrics(self, metrics: PixelIconGridMetrics) -> None:
        if metrics == self._metrics:
            return
        self._metrics = metrics
        self._refresh_layout()
        self._refresh_prepared_pixmaps()
        self.update()

    def set_items(self, items: list[PixelIconGridItem] | tuple[PixelIconGridItem, ...]) -> None:
        self._items = tuple(items)
        self._items_by_id = {item.item_id: item for item in self._items if item.item_id}
        self._hovered_item_id = ""
        self._tooltip_controller.hide()
        self._refresh_layout()
        self._refresh_prepared_pixmaps()
        self.update()

    def update_item(self, item_id: str, **changes: Any) -> bool:
        if item_id not in self._items_by_id:
            return False
        updated: list[PixelIconGridItem] = []
        changed = False
        for item in self._items:
            if item.item_id == item_id:
                item = replace(item, **changes)
                changed = True
            updated.append(item)
        if not changed:
            return False
        self._items = tuple(updated)
        self._items_by_id = {item.item_id: item for item in self._items if item.item_id}
        self._refresh_prepared_pixmaps()
        self.update()
        return True

    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self._items)

    def item_count(self) -> int:
        return len(self._items)

    def item(self, item_id: str) -> PixelIconGridItem | None:
        return self._items_by_id.get(item_id)

    def item_property(self, item_id: str, name: str, default: Any = None) -> Any:
        item = self._items_by_id.get(item_id)
        if item is None:
            return default
        return item.properties.get(name, default)

    def item_logical_rect(self, item_id: str) -> QRectF:
        for index, item in enumerate(self._items):
            if item.item_id == item_id and index < len(self._layout.rects):
                return _logical_rect(self._layout.rects[index], self._layout.dpr)
        return QRectF()

    def item_physical_rect(self, item_id: str) -> QRect:
        for index, item in enumerate(self._items):
            if item.item_id == item_id and index < len(self._layout.rects):
                return QRect(self._layout.rects[index])
        return QRect()

    def item_at(self, point: QPoint) -> str:
        return self._item_id_at_logical(point)

    def click_item_for_test(self, item_id: str) -> bool:
        item = self._items_by_id.get(item_id)
        if item is None or not item.enabled:
            return False
        self.item_clicked.emit(item_id)
        return True

    def horizontalSpacing(self) -> int:  # noqa: N802 - Qt-style compatibility
        return self._metrics.gap_x

    def verticalSpacing(self) -> int:  # noqa: N802 - Qt-style compatibility
        return self._metrics.resolved_gap_y

    def count(self) -> int:
        return len(self._items)

    def sizeHint(self) -> QSize:
        height = _logical_extent(self._layout.content_height, self._layout.dpr)
        return QSize(max(1, self.width()), max(1, height))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._refresh_layout()

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.Show,
        ):
            self._refresh_layout()
            self._refresh_prepared_pixmaps()
        return super().event(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        item_id = self._item_id_at_logical(event.position().toPoint())
        self._set_hovered_item(item_id)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._set_hovered_item("")
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            item_id = self._item_id_at_logical(event.position().toPoint())
            item = self._items_by_id.get(item_id)
            if item is not None and item.enabled:
                self._tooltip_controller.hide()
                self.item_clicked.emit(item_id)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if not self._items:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            visible = _physical_rect_for_logical(self.rect(), self._layout.dpr)
            for index, item in enumerate(self._items):
                if index >= len(self._layout.rects):
                    break
                rect = self._layout.rects[index]
                if not rect.intersects(visible):
                    continue
                icon_rect = self._icon_physical_rect(item, rect)
                self._draw_icon(painter, item, icon_rect)
                if item.overlay_fill is not None:
                    self._draw_fill(painter, item.overlay_fill, rect)
                if item.outline is not None:
                    self._draw_outline(painter, item.outline, icon_rect)
            for index, item in enumerate(self._items):
                if index >= len(self._layout.rects):
                    break
                rect = self._layout.rects[index]
                if not rect.intersects(visible):
                    continue
                icon_rect = self._icon_physical_rect(item, rect)
                for overlay_index, overlay in enumerate(item.overlay_icons):
                    self._draw_overlay_icon(painter, item, overlay, overlay_index, icon_rect)
        finally:
            painter.end()

    def _refresh_layout(self) -> None:
        viewport_width = max(1, self.width())
        self._layout = build_pixel_icon_grid_layout(
            len(self._items),
            viewport_width,
            self._metrics,
            dpr=self.devicePixelRatioF(),
        )
        margins = QMargins(
            _logical_floor(self._layout.margin_left, self._layout.dpr),
            max(0, int(self._metrics.margin_top)) if self._items else 0,
            _logical_floor(self._layout.margin_right, self._layout.dpr),
            max(0, int(self._metrics.margin_bottom)) if self._items else 0,
        )
        self.setContentsMargins(margins)
        self.setMinimumHeight(max(1, _logical_extent(self._layout.content_height, self._layout.dpr)))
        self.updateGeometry()

    def _refresh_prepared_pixmaps(self) -> None:
        dpr = self.devicePixelRatioF()
        self._prepared_pixmaps = {}
        self._prepared_overlay_pixmaps = {}
        self._prepared_backgrounds = {}
        for item in self._items:
            if item.icon_path:
                result = load_hidpi_pixmap(
                    item.icon_path,
                    QSize(self._metrics.item_width, self._metrics.resolved_item_height),
                    dpr=dpr,
                    aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                    transform_mode=Qt.TransformationMode.SmoothTransformation,
                    cache=self._pixmap_cache,
                    cache_key_parts=item.pixmap_cache_key_parts,
                    surface=self._surface,
                )
                self._prepared_pixmaps[item.item_id] = result.pixmap
            for overlay_index, overlay in enumerate(item.overlay_icons):
                logical_size = self._overlay_logical_size(overlay)
                result = load_hidpi_pixmap(
                    overlay.icon_path,
                    logical_size,
                    dpr=dpr,
                    aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                    transform_mode=Qt.TransformationMode.SmoothTransformation,
                    cache=self._pixmap_cache,
                    cache_key_parts=("overlay", overlay_index),
                    surface=f"{self._surface}_overlay",
                )
                self._prepared_overlay_pixmaps[(item.item_id, overlay_index)] = result.pixmap

    def _overlay_logical_size(self, overlay: PixelIconGridOverlayIcon) -> QSize:
        return QSize(
            max(1, int(round(self._metrics.item_width * overlay.size_ratio))),
            max(1, int(round(self._metrics.resolved_item_height * overlay.size_ratio))),
        )

    def _icon_physical_rect(self, item: PixelIconGridItem, item_rect: QRect) -> QRect:
        pixmap = self._prepared_pixmaps.get(item.item_id)
        if pixmap is None or pixmap.isNull():
            return QRect(item_rect)
        source_width = max(1, int(pixmap.width()))
        source_height = max(1, int(pixmap.height()))
        scale = min(item_rect.width() / source_width, item_rect.height() / source_height)
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        return QRect(
            item_rect.x() + (item_rect.width() - width) // 2,
            item_rect.y() + (item_rect.height() - height) // 2,
            width,
            height,
        )

    def _draw_icon(self, painter: QPainter, item: PixelIconGridItem, icon_rect: QRect) -> None:
        pixmap = self._prepared_pixmaps.get(item.item_id)
        if pixmap is None or pixmap.isNull():
            return
        target = _logical_rect(icon_rect, self._layout.dpr)
        source = QRectF(0, 0, pixmap.width(), pixmap.height())
        painter.drawPixmap(target, pixmap, source)

    def _draw_fill(self, painter: QPainter, fill: PixelIconGridFill, rect: QRect) -> None:
        color = QColor(fill.color)
        color.setAlpha(max(0, min(255, int(fill.alpha))))
        painter.fillRect(_logical_rect(rect, self._layout.dpr), color)

    def _draw_outline(
        self,
        painter: QPainter,
        outline: PixelIconGridOutline,
        icon_rect: QRect,
    ) -> None:
        frame = QRect(icon_rect).adjusted(
            -int(round(outline.overhang * self._layout.dpr)),
            -int(round(outline.overhang * self._layout.dpr)),
            int(round(outline.overhang * self._layout.dpr)),
            int(round(outline.overhang * self._layout.dpr)),
        )
        pen_color = QColor(outline.color)
        pen_color.setAlpha(max(0, min(255, int(outline.alpha))))
        painter.setPen(
            QPen(
                pen_color,
                max(1.0, outline.width / self._layout.dpr),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        if outline.fill_color and outline.fill_alpha > 0:
            fill = QColor(outline.fill_color)
            fill.setAlpha(max(0, min(255, int(outline.fill_alpha))))
            painter.setBrush(fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            _logical_rect(frame, self._layout.dpr),
            outline.radius,
            outline.radius,
        )
        if outline.badge_text:
            self._draw_badge(painter, outline, frame)

    def _draw_badge(
        self,
        painter: QPainter,
        outline: PixelIconGridOutline,
        frame: QRect,
    ) -> None:
        badge = QRect(
            frame.left() + int(round(outline.badge_margin * self._layout.dpr)),
            frame.bottom()
            - int(round((outline.badge_height + outline.badge_margin) * self._layout.dpr))
            + 1,
            max(1, int(round(outline.badge_width * self._layout.dpr))),
            max(1, int(round(outline.badge_height * self._layout.dpr))),
        )
        fill = QColor(outline.color)
        fill.setAlpha(max(0, min(255, int(outline.badge_fill_alpha))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(_logical_rect(badge, self._layout.dpr), 5, 5)
        painter.setPen(QColor(outline.badge_text_color))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(outline.font_size)
        painter.setFont(font)
        painter.drawText(
            _logical_rect(badge, self._layout.dpr),
            Qt.AlignmentFlag.AlignCenter,
            outline.badge_text,
        )

    def _draw_overlay_icon(
        self,
        painter: QPainter,
        item: PixelIconGridItem,
        overlay: PixelIconGridOverlayIcon,
        overlay_index: int,
        icon_rect: QRect,
    ) -> None:
        pixmap = self._prepared_overlay_pixmaps.get((item.item_id, overlay_index))
        if pixmap is None or pixmap.isNull():
            return
        overlay_size = QSize(
            max(1, int(round(icon_rect.width() * overlay.size_ratio))),
            max(1, int(round(icon_rect.height() * overlay.size_ratio))),
        )
        right_overhang = int(round(overlay_size.width() * overlay.right_overhang_ratio))
        top_overhang = int(round(overlay_size.height() * overlay.top_overhang_ratio))
        target = QRect(
            icon_rect.right() - overlay_size.width() + 1 + right_overhang,
            icon_rect.top() - top_overhang,
            overlay_size.width(),
            overlay_size.height(),
        )
        if overlay.background_enabled:
            background_size = QSize(
                max(1, int(round(target.width() * overlay.background_size_ratio))),
                max(1, int(round(target.height() * overlay.background_size_ratio))),
            )
            background = self._background_pixmap(overlay, background_size)
            background_rect = QRect(
                target.center().x()
                - background_size.width() // 2
                + int(round(target.width() * overlay.background_offset_x_ratio)),
                target.center().y()
                - background_size.height() // 2
                + int(round(target.height() * overlay.background_offset_y_ratio)),
                background_size.width(),
                background_size.height(),
            )
            painter.drawPixmap(_logical_rect(background_rect, self._layout.dpr), background, QRectF(0, 0, background.width(), background.height()))
        painter.drawPixmap(_logical_rect(target, self._layout.dpr), pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))

    def _background_pixmap(
        self,
        overlay: PixelIconGridOverlayIcon,
        size: QSize,
    ) -> QPixmap:
        key = (
            overlay.icon_path,
            size.width(),
            size.height(),
            dpr_cache_key(self.devicePixelRatioF()),
        )
        cached = self._prepared_backgrounds.get(key)
        if cached is not None:
            return cached
        pixmap = QPixmap(size)
        pixmap.setDevicePixelRatio(1.0)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            diameter = min(size.width(), size.height())
            rect = QRectF(1, 1, max(1, diameter - 2), max(1, diameter - 2))
            fill = QColor(overlay.background_fill_color)
            fill.setAlpha(max(0, min(255, int(overlay.background_fill_alpha))))
            border = QColor(overlay.background_border_color)
            border.setAlpha(max(0, min(255, int(overlay.background_border_alpha))))
            painter.setBrush(fill)
            painter.setPen(QPen(border, overlay.background_border_width))
            painter.drawEllipse(rect)
        finally:
            painter.end()
        self._prepared_backgrounds[key] = pixmap
        return pixmap

    def _item_id_at_logical(self, point: QPoint) -> str:
        physical = QPoint(
            int(round(point.x() * self._layout.dpr)),
            int(round(point.y() * self._layout.dpr)),
        )
        for index, rect in enumerate(self._layout.rects):
            if rect.contains(physical) and index < len(self._items):
                return self._items[index].item_id
        return ""

    def _set_hovered_item(self, item_id: str) -> None:
        if item_id == self._hovered_item_id:
            return
        self._hovered_item_id = item_id
        self.item_hovered.emit(item_id)
        item = self._items_by_id.get(item_id)
        if item is None or not item.tooltip:
            self._tooltip_controller.hide()
            self._tooltip_controller.set_text("")
            self._tooltip_anchor.setGeometry(QRect())
            return
        item_rect = self.item_logical_rect(item_id).toAlignedRect()
        self._tooltip_anchor.setGeometry(item_rect)
        self._tooltip_controller.set_text(item.tooltip)
        self._tooltip_controller.show_later()


def _logical_rect(rect: QRect, dpr: float) -> QRectF:
    scale = max(0.001, float(dpr or 1.0))
    return QRectF(
        rect.x() / scale,
        rect.y() / scale,
        rect.width() / scale,
        rect.height() / scale,
    )


def _physical_rect_for_logical(rect: QRect, dpr: float) -> QRect:
    scale = max(0.001, float(dpr or 1.0))
    return QRect(
        int(math.floor(rect.x() * scale)),
        int(math.floor(rect.y() * scale)),
        int(math.ceil(rect.width() * scale)),
        int(math.ceil(rect.height() * scale)),
    )


def _logical_floor(value: int, dpr: float) -> int:
    return int(math.floor(value / max(0.001, float(dpr or 1.0))))


def _logical_extent(value: int, dpr: float) -> int:
    return int(math.ceil(value / max(0.001, float(dpr or 1.0))))
