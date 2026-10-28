from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ui.utils.hidpi_pixmap import (
    effective_pixmap_dpr,
    load_hidpi_pixmap,
    logical_pixmap_size,
    make_hidpi_canvas,
)
from ui.utils.pixmap_utils import scale_trimmed_pixmap_to_size
from ui.utils.tooltips import install_custom_tooltip

RIGHT_PANEL_PROTOTYPE_MIN_WIDTH = 660
RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH = 640
SLOT_CARD_MARGIN = 5
SLOT_PORTRAIT_SIZE = 96
SLOT_EQUIP_BOX_SIZE = 46
SLOT_EQUIP_ICON_SIZE = 42
SLOT_WEAPON_ICON_SIZE = 52
SLOT_BUILD_BONUS_FEATHER = 3
SLOT_TOP_SPACING = 2
SLOT_CLUSTER_WIDTH = SLOT_PORTRAIT_SIZE + SLOT_TOP_SPACING + SLOT_EQUIP_BOX_SIZE
SLOT_BADGE_HEIGHT = 22
SLOT_WARNING_BADGE_WIDTH = SLOT_EQUIP_BOX_SIZE
SLOT_CARD_WIDTH = SLOT_CLUSTER_WIDTH + SLOT_CARD_MARGIN * 2
SLOT_CARD_FIXED_HEIGHT = 154
SLOT_NAME_HEIGHT = 18
SLOT_DRAG_MIME_TYPE = "application/x-gtt-right-panel-slot"
ABYSS_CHAMBER_BADGE_WIDTH = 26
ABYSS_CHAMBER_GRID_SPACING = 3
ABYSS_TIMER_SEGMENT_WIDTH = 26
ABYSS_TIMER_SEPARATOR_WIDTH = 5
ABYSS_TIMER_ELAPSED_WIDTH = 30
ABYSS_TIMER_FRAME_WIDTH = (
    ABYSS_TIMER_SEGMENT_WIDTH * 2
    + ABYSS_TIMER_SEPARATOR_WIDTH
    + 4
)
ABYSS_TIMER_CELL_WIDTH = ABYSS_TIMER_FRAME_WIDTH + ABYSS_TIMER_ELAPSED_WIDTH + 2
ABYSS_FACT_DPS_LEFT_BUDGET_MAX = 224
ABYSS_DPS_COLUMN_MIN_WIDTH = 62

_FIT_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}
_BUILD_MINI_SET_ICON_PIXMAP_CACHE: dict[
    tuple[object, ...],
    QPixmap | None,
] = {}
_BONUS_SOURCE_ICON_PIXMAP_CACHE: dict[
    tuple[object, ...],
    QPixmap | None,
] = {}
_BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}
BONUS_MEMBER_ICON_SCALE = 125
BONUS_MEMBER_ICON_BOTTOM_PADDING = 0
BONUS_SOURCE_CHIP_HEIGHT = 26
BONUS_MEMBER_ICON_SIZE = 26
OWNER_BADGE_TRACE = os.environ.get("GTT_OWNER_BADGE_TRACE", "").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _fit_pixmap(path: str, size: QSize, *, dpr: float = 1.0) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    effective_dpr = effective_pixmap_dpr(dpr)
    dpr_key = int(round(effective_dpr * 1000))
    if not resolved.is_file():
        key = (
            "fit_canvas",
            str(path),
            int(size.width()),
            int(size.height()),
            dpr_key,
            0,
            0,
        )
        _FIT_PIXMAP_CACHE[key] = None
        return None
    try:
        stat = resolved.stat()
        mtime_ns = int(stat.st_mtime_ns)
        file_size = int(stat.st_size)
    except OSError:
        mtime_ns = 0
        file_size = 0
    key = (
        "fit_canvas",
        str(resolved),
        int(size.width()),
        int(size.height()),
        dpr_key,
        mtime_ns,
        file_size,
    )
    if key in _FIT_PIXMAP_CACHE:
        cached = _FIT_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    result = load_hidpi_pixmap(
        resolved,
        size,
        dpr=effective_dpr,
        aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
        transform_mode=Qt.TransformationMode.SmoothTransformation,
        cache_key_parts=("fit_source",),
        surface="right_panel_fit",
    )
    if result.pixmap.isNull():
        _FIT_PIXMAP_CACHE[key] = None
        return None

    canvas = make_hidpi_canvas(size, result.effective_dpr)
    painter = QPainter(canvas)
    scaled_size = logical_pixmap_size(result.pixmap)
    x = max(0, (size.width() - scaled_size.width()) // 2)
    y = max(0, (size.height() - scaled_size.height()) // 2)
    painter.drawPixmap(x, y, result.pixmap)
    painter.end()
    _FIT_PIXMAP_CACHE[key] = QPixmap(canvas)
    return canvas


def _resolve_pixmap_path(path: str) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    project_path = _PROJECT_ROOT / resolved
    if project_path.is_file():
        return project_path
    return resolved


def _trace_rect(rect: QRect) -> str:
    return f"{rect.x()},{rect.y()},{rect.width()}x{rect.height()}"


def _set_object_name(widget: QWidget, object_name: str) -> None:
    if widget.objectName() == object_name:
        return
    widget.setObjectName(object_name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _set_custom_tooltip_text(owner: QWidget, controller, text: str):
    text = str(text or "")
    if controller is not None:
        controller.set_text(text)
        return controller
    if text:
        return install_custom_tooltip(owner, text)
    QWidget.setToolTip(owner, "")
    return None


def _scale_trimmed_icon_for_chip(
    source: QPixmap,
    width: int,
    height: int,
    *,
    padding: int,
    alpha_threshold: int,
    dpr: float = 1.0,
) -> QPixmap:
    effective_dpr = effective_pixmap_dpr(dpr)
    prescale_width = max(1, int(round(width * effective_dpr)) * 2)
    prescale_height = max(1, int(round(height * effective_dpr)) * 2)
    prescaled = source.scaled(
        prescale_width,
        prescale_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return scale_trimmed_pixmap_to_size(
        prescaled,
        width,
        height,
        padding=padding,
        alpha_threshold=alpha_threshold,
        dpr=effective_dpr,
    )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


__all__ = [name for name in globals() if not name.startswith("__")]
