"""Character-browser-only presentation of the account's Traveler variants."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import math
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_element, traveler_source_id
from localization import tr
from ui.utils.icon_utils import contrast_icon_color, tinted_svg_icon
from ui.utils.pixel_icon_grid import PixelIconGrid, PixelIconGridItem, PixelIconGridMetrics, PixelIconGridOutline
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_BG_PANEL, UI_BORDER_DEFAULT, UI_TEXT_PRIMARY


@dataclass(frozen=True)
class TravelerBrowserPresentation:
    assets: tuple[dict[str, Any], ...]
    groups: dict[str, tuple[dict[str, Any], ...]]


def collapse_traveler_assets(
    assets: Sequence[dict[str, Any]], selected_ids: Mapping[int, str],
) -> TravelerBrowserPresentation:
    """Group an already-filtered roster without changing stored identities."""
    by_source: dict[int, list[dict[str, Any]]] = {}
    for asset in assets:
        character = (asset.get("metadata") or {}).get("character") or {}
        source = traveler_source_id(character.get("id"))
        if source is not None and traveler_element(character.get("id"), character.get("element")):
            by_source.setdefault(source, []).append(asset)

    chosen: dict[int, dict[str, Any]] = {}
    groups: dict[str, tuple[dict[str, Any], ...]] = {}
    grouped_ids: set[str] = set()
    for source, variants in by_source.items():
        variants.sort(key=lambda asset: TRAVELER_ELEMENTS.index(
            traveler_element(
                (asset["metadata"]["character"]).get("id"),
                (asset["metadata"]["character"]).get("element"),
            )
        ))
        by_id = {str(asset["metadata"]["character"]["id"]): asset for asset in variants}
        grouped_ids.update(by_id)
        preferred = selected_ids.get(source, str(source))
        shown = by_id.get(preferred) or by_id.get(str(source)) or variants[0]
        chosen[source] = shown
        groups[str(shown["metadata"]["character"]["id"])] = tuple(variants)

    visible: list[dict[str, Any]] = []
    seen: set[int] = set()
    for asset in assets:
        character = (asset.get("metadata") or {}).get("character") or {}
        source = traveler_source_id(character.get("id"))
        if source not in chosen or str(character.get("id")) not in grouped_ids:
            visible.append(asset)
        elif source not in seen:
            visible.append(chosen[source])
            seen.add(source)
    return TravelerBrowserPresentation(tuple(visible), groups)


class TravelerVariantPopup(QFrame):
    variant_selected = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("traveler_variant_popup")
        self.setStyleSheet(
            f"QFrame#traveler_variant_popup {{ background: {UI_BG_PANEL}; "
            f"border: 1px solid {UI_BORDER_DEFAULT}; border-radius: 6px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.grid = PixelIconGrid(self, surface="traveler_variant_popup")
        layout.addWidget(self.grid)
        self.grid.item_clicked.connect(self._choose)

    def show_variants(self, items: tuple[PixelIconGridItem, ...], anchor: QRect) -> None:
        if not items:
            self.hide()
            return
        size, gap = 64, 4
        self.grid.set_metrics(PixelIconGridMetrics(item_width=size, gap_x=gap, margin_top=2, margin_bottom=2))
        dpr = max(0.001, self.grid.devicePixelRatioF())
        width = len(items) * round(size * dpr) + (len(items) - 1) * round(gap * dpr)
        height = round(size * dpr) + 2 * round(2 * dpr)
        self.grid.setFixedSize(math.ceil(width / dpr), math.ceil(height / dpr))
        self.grid.set_items(items)
        self.adjustSize()
        screen = self.parentWidget().screen()
        available = screen.availableGeometry()
        x = min(max(anchor.left(), available.left()), max(available.left(), available.right() - self.width() + 1))
        y = anchor.bottom() + 3
        if y + self.height() > available.bottom() + 1:
            y = anchor.top() - self.height() - 3
        y = max(available.top(), y)
        self.move(QPoint(x, y))
        self.show()

    def _choose(self, item_id: str) -> None:
        self.hide()
        self.variant_selected.emit(item_id)


class TravelerVariantGrid(PixelIconGrid):
    variant_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, surface: str) -> None:
        super().__init__(parent, surface=surface)
        self._variant_groups: dict[str, tuple[PixelIconGridItem, ...]] = {}
        self._variant_buttons: dict[str, QToolButton] = {}
        self._variant_popup = TravelerVariantPopup(self)
        self._variant_popup.variant_selected.connect(self.variant_selected.emit)

    def set_items(self, items: list[PixelIconGridItem] | tuple[PixelIconGridItem, ...]) -> None:
        super().set_items(tuple(
            replace(item, outline=self._main_card_outline(item.item_id, item.outline))
            for item in items
        ))

    def update_item(self, item_id: str, **changes: Any) -> bool:
        if "outline" in changes:
            changes["outline"] = self._main_card_outline(item_id, changes["outline"])
        return super().update_item(item_id, **changes)

    @staticmethod
    def _main_card_outline(item_id: str, outline: PixelIconGridOutline | None) -> PixelIconGridOutline | None:
        if outline is not None and traveler_source_id(item_id) is not None:
            # The lower-left corner is reserved for the element selector.
            return replace(outline, badge_position="bottom_right")
        return outline

    def set_variant_groups(self, groups: dict[str, tuple[PixelIconGridItem, ...]]) -> None:
        self._variant_popup.hide()
        self._variant_groups = groups
        wanted = {item_id for item_id, variants in groups.items() if len(variants) > 1}
        for item_id in self._variant_buttons.keys() - wanted:
            button = self._variant_buttons.pop(item_id)
            button.hide()
            button.deleteLater()
        for item_id in wanted - self._variant_buttons.keys():
            button = QToolButton(self)
            button.setObjectName("traveler_variant_button")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(tinted_svg_icon("chevron-down", 16, contrast_icon_color(UI_BG_PANEL)))
            button.setStyleSheet(
                f"QToolButton {{ background: {UI_BG_PANEL}; color: {UI_TEXT_PRIMARY}; "
                "border: none; border-radius: 4px; padding: 0; }"
            )
            install_custom_tooltip(button, tr("asset_panel.traveler_elements"))
            button.setAccessibleName(tr("asset_panel.traveler_elements"))
            button.clicked.connect(lambda _checked=False, current=item_id: self.open_variants(current))
            self._variant_buttons[item_id] = button
        self._position_variant_buttons()

    def open_variants(self, item_id: str) -> bool:
        variants = tuple(item for item in self._variant_groups.get(item_id, ()) if item.item_id != item_id)
        rect = self.item_logical_rect(item_id).toAlignedRect()
        if not variants or rect.isEmpty():
            return False
        self._tooltip_controller.hide()
        anchor = QRect(self.mapToGlobal(rect.topLeft()), rect.size())
        self._variant_popup.show_variants(variants, anchor)
        return True

    def retranslate_ui(self) -> None:
        for button in self._variant_buttons.values():
            install_custom_tooltip(button, tr("asset_panel.traveler_elements"))
            button.setAccessibleName(tr("asset_panel.traveler_elements"))

    def close_variants(self) -> None:
        self._variant_popup.hide()

    def update_variant_outline(self, item_id: str, outline: PixelIconGridOutline | None) -> None:
        for main_id, variants in self._variant_groups.items():
            self._variant_groups[main_id] = tuple(
                replace(item, outline=outline) if item.item_id == item_id else item
                for item in variants
            )
        self._variant_popup.grid.update_item(item_id, outline=outline)

    def _refresh_layout(self) -> None:
        super()._refresh_layout()
        if hasattr(self, "_variant_buttons"):
            self._variant_popup.hide()
            self._position_variant_buttons()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._variant_popup.hide()
        super().hideEvent(event)

    def _position_variant_buttons(self) -> None:
        for item_id, button in self._variant_buttons.items():
            rect = self.item_logical_rect(item_id).toAlignedRect()
            button.setGeometry(rect.left() + 2, rect.bottom() - 19, 22, 18)
            button.setVisible(not rect.isEmpty())
            button.raise_()
