from __future__ import annotations

import html
import re
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from run_workspace.right_panel_prototype_view_model import (
    RightPanelBuildMiniSetViewModel,
    RightPanelSlotPrototypeViewModel,
)
from ui.artifact_browser.queries import list_set_bonus_description_map
from ui.right_panel.common.metrics import (
    _BUILD_MINI_SET_ICON_PIXMAP_CACHE,
    SLOT_BUILD_BONUS_FEATHER,
    SLOT_EQUIP_BOX_SIZE,
    SLOT_EQUIP_ICON_SIZE,
    _fit_pixmap,
    _resolve_pixmap_path,
    _scale_trimmed_icon_for_chip,
    _set_custom_tooltip_text,
    _set_object_name,
)
from ui.utils.hidpi_pixmap import effective_pixmap_dpr
from ui.utils.pixmap_utils import draw_count_badge, make_diagonal_split_pixmap


@dataclass(frozen=True, slots=True)
class RightPanelArtifactMiniZoneState:
    label: str = ""
    image_path: str = ""
    mini_sets: tuple[RightPanelBuildMiniSetViewModel, ...] = ()


class RightPanelPixmapMiniBoxLabel(QLabel):
    """Shared HiDPI-aware mini image box used by compact right-panel slots."""

    def __init__(
        self,
        *,
        box_size: QSize,
        pixmap_size: QSize | None = None,
        object_name: str = "",
        empty_object_name: str = "",
        has_pixmap_property: str = "hasPixmap",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("", parent)
        self._box_size = QSize(box_size)
        self._pixmap_size = QSize(pixmap_size or box_size)
        self._object_name = object_name
        self._empty_object_name = empty_object_name
        self._has_pixmap_property = has_pixmap_property
        self._image_path = ""
        self._fallback_text = ""
        self._empty = False
        self._tooltip_text = ""
        self._tooltip_controller = None
        self._surface = "right_panel_mini_box"
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self._box_size)
        if object_name:
            self.setObjectName(object_name)

    def set_visual(
        self,
        *,
        image_path: str,
        fallback_text: str = "",
        empty: bool = False,
        tooltip: str = "",
        surface: str = "right_panel_mini_box",
    ) -> bool:
        self._image_path = image_path or ""
        self._fallback_text = fallback_text or ""
        self._empty = bool(empty)
        self._tooltip_text = tooltip or ""
        self._surface = surface
        return self._render()

    def refresh_hidpi_pixmap(self) -> bool:
        return self._render()

    def _render(self) -> bool:
        object_name = (
            self._empty_object_name
            if self._empty and self._empty_object_name
            else self._object_name
        )
        if object_name:
            _set_object_name(self, object_name)
        self.clear()
        self.setText(self._fallback_text)
        pixmap = _fit_pixmap(
            self._image_path,
            self._pixmap_size,
            dpr=self.devicePixelRatioF(),
        )
        loaded = pixmap is not None
        self.setProperty(self._has_pixmap_property, loaded)
        if loaded:
            self.setPixmap(pixmap)
        self._tooltip_controller = _set_custom_tooltip_text(
            self,
            self._tooltip_controller,
            self._tooltip_text,
        )
        return loaded


class RightPanelPortraitMiniBox(RightPanelPixmapMiniBoxLabel):
    def set_portrait(
        self,
        *,
        image_path: str,
        fallback_text: str,
        empty: bool = False,
        surface: str = "right_panel_portrait_mini_box",
    ) -> bool:
        return self.set_visual(
            image_path=image_path,
            fallback_text=fallback_text,
            empty=empty,
            surface=surface,
        )


class RightPanelWeaponMiniBox(RightPanelPixmapMiniBoxLabel):
    def set_weapon(
        self,
        *,
        image_path: str,
        fallback_text: str,
        tooltip: str = "",
        assigned: bool | None = None,
        surface: str = "right_panel_weapon_mini_box",
    ) -> bool:
        loaded = self.set_visual(
            image_path=image_path,
            fallback_text=fallback_text,
            tooltip=tooltip,
            surface=surface,
        )
        if assigned is not None:
            self.setProperty("assigned", bool(assigned))
        return loaded


class RightPanelArtifactMiniZoneWidget(QLabel):
    def __init__(
        self,
        *,
        box_size: QSize | None = None,
        icon_size: QSize | None = None,
        object_name: str = "MiniEquipBox",
        missing_object_name: str = "MiniEquipBoxMissing",
        parent: QWidget | None = None,
    ):
        super().__init__("", parent)
        self._tooltip_controller = None
        self._model_key: tuple[object, ...] | None = None
        self._state = RightPanelArtifactMiniZoneState()
        self._box_size = QSize(box_size or QSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE))
        self._icon_size = QSize(icon_size or QSize(SLOT_EQUIP_ICON_SIZE, SLOT_EQUIP_ICON_SIZE))
        self._object_name = object_name
        self._missing_object_name = missing_object_name
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self._box_size)
        if object_name:
            self.setObjectName(object_name)

    def set_state(self, state: RightPanelArtifactMiniZoneState) -> None:
        self._state = state
        model_key = (
            state.label,
            state.image_path,
            tuple(state.mini_sets),
            self._icon_size.width(),
            self._icon_size.height(),
            int(round(effective_pixmap_dpr(self.devicePixelRatioF()) * 1000)),
        )
        if model_key == self._model_key:
            return

        self._model_key = model_key
        is_missing = state.label in {"Equip", "Fix", "ART"}
        object_name = self._missing_object_name if is_missing else self._object_name
        if object_name:
            _set_object_name(self, object_name)
        self.clear()
        self.setText(state.label)

        pixmap = _build_mini_set_stack_pixmap(
            state.mini_sets,
            icon_size=self._icon_size,
            dpr=self.devicePixelRatioF(),
        )
        if pixmap is None and state.image_path:
            pixmap = _fit_pixmap(
                state.image_path,
                self._icon_size,
                dpr=self.devicePixelRatioF(),
            )
        if pixmap is not None:
            self.setText("")
            self.setPixmap(pixmap)
        elif state.mini_sets:
            self.setText(_build_mini_set_fallback_text(state.mini_sets))

        tooltip = _build_mini_set_tooltip_html(state.mini_sets)
        self._tooltip_controller = _set_custom_tooltip_text(
            self,
            self._tooltip_controller,
            tooltip,
        )

    def refresh_hidpi_pixmap(self) -> None:
        self._model_key = None
        self.set_state(self._state)


class BuildMiniSetStackWidget(RightPanelArtifactMiniZoneWidget):
    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._model = model
        self.set_model(model)

    def set_model(self, model: RightPanelSlotPrototypeViewModel) -> None:
        self._model = model
        self.set_state(
            RightPanelArtifactMiniZoneState(
                label=model.artifact_square_label,
                image_path=model.artifact_image_path,
                mini_sets=tuple(model.build_mini_sets),
            )
        )

    def refresh_hidpi_pixmap(self) -> None:
        self._model_key = None
        self.set_model(self._model)


def slot_portrait_fallback(character_name: str, slot_index: int) -> str:
    name = str(character_name or "").strip()
    if not name:
        return str(slot_index + 1)
    for character in name:
        if character.strip():
            return character.upper()
    return str(slot_index + 1)


def _build_mini_set_stack_pixmap(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
    *,
    icon_size: QSize,
    dpr: float = 1.0,
) -> QPixmap | None:
    active_sets = tuple(active_sets[:2])
    if not active_sets:
        return None

    icons: list[QPixmap] = []
    for item in active_sets:
        if not item.icon_path:
            continue
        icon = _build_mini_set_icon_pixmap(item.icon_path, icon_size=icon_size, dpr=dpr)
        if icon is not None and not icon.isNull():
            icons.append(icon)

    if len(active_sets) == 2 and len(icons) == 2:
        composite = make_diagonal_split_pixmap(
            icons[0],
            icons[1],
            width=icon_size.width(),
            height=icon_size.height(),
            feather=SLOT_BUILD_BONUS_FEATHER,
        )
        return draw_count_badge(composite, "2")

    if len(active_sets) == 1 and len(icons) == 1:
        count = active_sets[0].piece_count
        badge = str(count) if count in (2, 4) else ""
        return draw_count_badge(icons[0], badge) if badge else icons[0]

    return None


def _build_mini_set_icon_pixmap(
    path: str,
    *,
    icon_size: QSize,
    dpr: float = 1.0,
) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            icon_size.width(),
            icon_size.height(),
            int(round(effective_pixmap_dpr(dpr) * 1000)),
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (
            str(path),
            icon_size.width(),
            icon_size.height(),
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
        icon_size.width(),
        icon_size.height(),
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


__all__ = [name for name in globals() if not name.startswith("__")]
