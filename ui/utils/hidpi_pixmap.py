from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget


_TRACE_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEFAULT_CACHE: dict[tuple[object, ...], QPixmap | None] = {}


@dataclass(frozen=True)
class HidpiPixmapResult:
    pixmap: QPixmap
    cache_hit: bool
    effective_dpr: float


def effective_pixmap_dpr(widget_or_dpr: QWidget | float | int | None) -> float:
    """Return the pixmap DPR used for raster UI assets.

    Startup UI downscale can make widget DPR smaller than 1.0. Raster images
    should not be rendered below their logical design size in that case.
    """
    if isinstance(widget_or_dpr, QWidget):
        raw_dpr = widget_or_dpr.devicePixelRatioF()
    else:
        raw_dpr = float(widget_or_dpr or 1.0)
    return max(1.0, raw_dpr)


def dpr_cache_key(dpr: float) -> int:
    return int(round(effective_pixmap_dpr(dpr) * 1000))


def physical_size_for_logical(
    logical_size: QSize | int,
    dpr: float | int | None,
) -> QSize:
    if isinstance(logical_size, int):
        logical_size = QSize(int(logical_size), int(logical_size))
    effective_dpr = effective_pixmap_dpr(dpr)
    return QSize(
        max(1, int(round(logical_size.width() * effective_dpr))),
        max(1, int(round(logical_size.height() * effective_dpr))),
    )


def logical_pixmap_size(pixmap: QPixmap) -> QSize:
    dpr = pixmap.devicePixelRatio() or 1.0
    return QSize(
        max(1, int(round(pixmap.width() / dpr))),
        max(1, int(round(pixmap.height() / dpr))),
    )


def make_hidpi_canvas(
    logical_size: QSize | int,
    dpr: float | int | None,
    *,
    fill: Qt.GlobalColor | None = Qt.GlobalColor.transparent,
) -> QPixmap:
    effective_dpr = effective_pixmap_dpr(dpr)
    physical_size = physical_size_for_logical(logical_size, effective_dpr)
    canvas = QPixmap(physical_size)
    canvas.setDevicePixelRatio(effective_dpr)
    if fill is not None:
        canvas.fill(fill)
    return canvas


def scale_pixmap_for_logical_size(
    source: QPixmap,
    logical_size: QSize | int,
    *,
    dpr: float | int | None,
    aspect_mode: Qt.AspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio,
    transform_mode: Qt.TransformationMode = Qt.TransformationMode.SmoothTransformation,
) -> QPixmap:
    effective_dpr = effective_pixmap_dpr(dpr)
    physical_size = physical_size_for_logical(logical_size, effective_dpr)
    scaled = source.scaled(physical_size, aspect_mode, transform_mode)
    scaled.setDevicePixelRatio(effective_dpr)
    return scaled


def load_hidpi_pixmap(
    path: str | Path,
    logical_size: QSize | int,
    *,
    dpr: float | int | None,
    aspect_mode: Qt.AspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio,
    transform_mode: Qt.TransformationMode = Qt.TransformationMode.SmoothTransformation,
    cache: MutableMapping[tuple[object, ...], QPixmap | None] | None = None,
    cache_key_parts: tuple[object, ...] = (),
    surface: str = "",
) -> HidpiPixmapResult:
    cache = _DEFAULT_CACHE if cache is None else cache
    path = Path(path)
    effective_dpr = effective_pixmap_dpr(dpr)
    logical_qsize = QSize(logical_size, logical_size) if isinstance(logical_size, int) else logical_size
    physical_size = physical_size_for_logical(logical_qsize, effective_dpr)
    try:
        stat = path.stat()
        mtime_ns = stat.st_mtime_ns
        file_size = stat.st_size
    except OSError:
        mtime_ns = 0
        file_size = 0

    key = (
        str(path),
        int(logical_qsize.width()),
        int(logical_qsize.height()),
        int(physical_size.width()),
        int(physical_size.height()),
        dpr_cache_key(effective_dpr),
        int(aspect_mode.value),
        int(transform_mode.value),
        int(mtime_ns),
        int(file_size),
        *cache_key_parts,
    )
    if key in cache:
        cached = cache[key]
        pixmap = QPixmap() if cached is None else cached
        _trace(surface, path, logical_qsize, effective_dpr, physical_size, True)
        return HidpiPixmapResult(pixmap, True, effective_dpr)

    source = QPixmap(str(path))
    if source.isNull():
        cache[key] = None
        _trace(surface, path, logical_qsize, effective_dpr, physical_size, False)
        return HidpiPixmapResult(source, False, effective_dpr)

    pixmap = source.scaled(physical_size, aspect_mode, transform_mode)
    pixmap.setDevicePixelRatio(effective_dpr)
    cache[key] = pixmap
    _trace(surface, path, logical_qsize, effective_dpr, physical_size, False)
    return HidpiPixmapResult(pixmap, False, effective_dpr)


def _trace(
    surface: str,
    path: Path,
    logical_size: QSize,
    effective_dpr: float,
    physical_size: QSize,
    cache_hit: bool,
) -> None:
    if os.environ.get("GTT_HIDPI_PIXMAP_TRACE", "").strip().casefold() not in _TRACE_TRUE_VALUES:
        return
    print(
        "[HIDPI_PIXMAP_TRACE] "
        f"surface={surface or '-'} "
        f"path={str(path)!r} "
        f"logical={logical_size.width()}x{logical_size.height()} "
        f"dpr={effective_dpr:.3f} "
        f"physical={physical_size.width()}x{physical_size.height()} "
        f"cache_hit={int(cache_hit)}",
        flush=True,
    )
