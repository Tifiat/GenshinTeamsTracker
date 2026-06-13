from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from localization import tr
from ui.character_browser.icon_grid_adapter import build_asset_grid_items
from run_workspace.pvp.deck_preset import (
    DEFAULT_PVP_DECK_PRESET_DIR,
    DeckPresetError,
    PvpDeckPreset,
    character_id_from_asset,
    create_deck_preset_from_account_assets,
    deck_preset_to_draft_deck,
    delete_deck_preset,
    load_deck_presets,
    rename_deck_preset,
    resolve_deck_preset_dir,
    save_deck_preset,
    update_deck_preset_selection,
    weapon_ref_from_asset,
)
from run_workspace.pvp.validation import validate_draft_deck
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    CHARACTER_STANDARD_FILTER,
    CHARACTER_TRAIT_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    STANDARD_FILTER_ALL,
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    WEAPON_RARITY_FILTERS,
    WEAPON_TYPE_FILTERS,
    character_matches_filters,
    character_sort_key,
    load_account_character_asset_items,
    load_account_weapon_stack_asset_items,
    metadata_int,
    standard_character_filter_icon,
)
from ui.utils.filter_button_style import (
    FILTER_BUTTON_ICON_SIZE,
    FILTER_BUTTON_SIZE,
    filter_button_style,
)
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.icon_utils import auto_contrast_svg_icon
from ui.utils.marquee_label import MarqueeButton
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.pixel_icon_grid import (
    PixelIconGrid,
    PixelIconGridFill,
    PixelIconGridMetrics,
    PixelIconGridOutline,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import (
    UI_BG_APP,
    UI_BG_BUTTON,
    UI_BG_PANEL,
    UI_BG_PANEL_RAISED,
    UI_BORDER_DEFAULT,
    UI_BORDER_PANEL,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)


WEAPON_PICKER_ICON_SIZE = 48
WEAPON_PICKER_SAFE_MARGIN = 6
WEAPON_PICKER_VIEWPORT_TOP_EXTENSION = 6
CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN = 4
PVP_DECK_ROW_ACTION_SIZE = 24
PVP_DECK_UI_ICON_SIZE = 24
PVP_DECK_UI_ICON_BACKGROUND = UI_BG_PANEL_RAISED
FILTER_BUTTON_STYLE = filter_button_style("app_shell_filter_button")
_PVP_DECK_ICON_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}

WEAPON_TYPE_FILTER_BY_ID = {
    1: "sword",
    10: "catalyst",
    11: "claymore",
    12: "bow",
    13: "polearm",
}
WEAPON_TYPE_FILTER_ALIASES = {
    "sword": "sword",
    "one_handed_sword": "sword",
    "catalyst": "catalyst",
    "claymore": "claymore",
    "bow": "bow",
    "polearm": "polearm",
}


class PvpDeckAssetIconLabel(QLabel):
    clicked = Signal(dict)

    def __init__(
        self,
        image_path: str,
        size: int,
        *,
        asset: dict[str, Any] | None = None,
        deck_selected: bool = False,
        deck_inactive: bool = False,
        deck_editing: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.asset = asset or {}
        self.base_size = int(size)
        self.deck_selected = bool(deck_selected)
        self.deck_inactive = bool(deck_inactive)
        self.deck_editing = bool(deck_editing)
        self._last_pixmap_cache_hit = False
        self._tooltip_controller = install_custom_tooltip(self)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_deck_state(
            selected=deck_selected,
            inactive=deck_inactive,
            editing=deck_editing,
        )
        self._update_pixmap()

    def set_deck_state(
        self,
        *,
        selected: bool,
        inactive: bool,
        editing: bool,
    ) -> None:
        self.deck_selected = bool(selected)
        self.deck_inactive = bool(inactive)
        self.deck_editing = bool(editing)
        self.setProperty("deckSelected", self.deck_selected)
        self.setProperty("deckInactive", self.deck_inactive)
        self.setProperty("deckEditing", self.deck_editing)
        self.setProperty("deckEditSelected", self.deck_editing and self.deck_selected)
        self.update()

    def setToolTip(self, text: str) -> None:
        self._tooltip_controller.set_text(text or "")
        super().setToolTip("")

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._update_pixmap()
        return super().event(event)

    def _update_pixmap(self) -> None:
        result = load_hidpi_pixmap(
            self.image_path,
            self.base_size,
            dpr=self.devicePixelRatioF(),
            aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
            transform_mode=Qt.TransformationMode.SmoothTransformation,
            cache=_PVP_DECK_ICON_PIXMAP_CACHE,
            surface="pvp_deck_icon",
        )
        self._last_pixmap_cache_hit = result.cache_hit
        if result.pixmap.isNull():
            self.clear()
            return
        self.setPixmap(result.pixmap)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            if self.deck_inactive:
                fill = QColor("#0f172a")
                fill.setAlpha(132)
                painter.fillRect(self.rect(), fill)
            if self.deck_editing and self.deck_selected:
                painter.setPen(QPen(QColor("#d6b15d"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 4, 4)
        finally:
            painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(dict(self.asset))
            event.accept()
            return
        super().mousePressEvent(event)


class PvpDeckGridItemHandle(QObject):
    clicked = Signal(dict)

    def __init__(
        self,
        grid: PixelIconGrid,
        item_id: str,
        asset: dict[str, Any],
        clicked,
    ) -> None:
        super().__init__(grid)
        self._grid = grid
        self.item_id = item_id
        self.asset = dict(asset)
        self.clicked.connect(lambda asset: clicked(dict(asset)))

    def property(self, name: str) -> Any:
        return self._grid.item_property(self.item_id, name)


PVP_DECKS_WORKSPACE_STYLE = """
QFrame#pvp_deck_editor_frame {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}
QScrollArea#pvp_deck_grid_area {
    background: transparent;
    border: none;
}
QScrollArea#pvp_deck_grid_area[deckEditMode="true"] {
    background: #203861;
    border: 1px solid #4f8ee8;
    border-radius: 8px;
}
QWidget#pvp_deck_grid_viewport,
QWidget#pvp_deck_grid_container {
    background: transparent;
}
QWidget#pvp_deck_grid_viewport[deckEditMode="true"],
QWidget#pvp_deck_grid_container[deckEditMode="true"] {
    background: #203861;
}
"""


class PvpDecksWorkspace(QWidget):
    state_changed = Signal()
    save_edit_requested = Signal()
    cancel_edit_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        db_path: str | Path = ARTIFACT_DB_PATH,
        deck_dir: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
        character_assets_provider: Callable[[], Iterable[dict[str, Any]]] | None = None,
        weapon_assets_provider: Callable[[], Iterable[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PvpDecksWorkspace")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(PVP_DECKS_WORKSPACE_STYLE)
        self.setProperty("pvpDeckEditMode", False)
        self.db_path = db_path
        self.deck_dir = resolve_deck_preset_dir(deck_dir)
        self._character_assets_provider = character_assets_provider
        self._weapon_assets_provider = weapon_assets_provider
        self._resize_timer: QTimer | None = None
        self._last_refresh_viewport_widths: tuple[int, int] | None = None
        self.character_assets: list[dict[str, Any]] = []
        self.weapon_assets: list[dict[str, Any]] = []
        self.presets: list[PvpDeckPreset] = []
        self.selected_deck_id = ""
        self._editing_preset: PvpDeckPreset | None = None
        self._editing_is_new_deck = False
        self._selected_deck_id_before_new_edit = ""
        self._last_status = ""
        self.character_cards_by_id: dict[str, Any] = {}
        self.weapon_cards_by_key: dict[str, Any] = {}
        self._character_grid_assets_by_id: dict[str, dict[str, Any]] = {}
        self._weapon_grid_assets_by_id: dict[str, dict[str, Any]] = {}
        self._character_element_filters: set[str] = set()
        self._character_weapon_filters: set[str] = set()
        self._character_rarity_filters: set[int] = set()
        self._character_trait_filters: set[str] = set()
        self._character_standard_filter = STANDARD_FILTER_ALL
        self._weapon_type_filters: set[str] = set()
        self._weapon_rarity_filters: set[int] = set()
        self._weapon_type_buttons: dict[str, QPushButton] = {}
        self._edit_shortcuts: list[QShortcut] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("small_muted")
        root.addWidget(self.empty_label)

        self.deck_editor_frame = QFrame()
        self.deck_editor_frame.setObjectName("pvp_deck_editor_frame")
        root.addWidget(self.deck_editor_frame, 1)
        editor = QVBoxLayout(self.deck_editor_frame)
        editor.setContentsMargins(4, 4, 4, 4)
        editor.setSpacing(0)

        self.weapon_title_label = QLabel()
        editor.addWidget(self.weapon_title_label)
        editor.addSpacing(6)
        editor.addLayout(
            self._build_filter_row(
                (
                    (WEAPON_TYPE_FILTERS, self._weapon_type_filters, self.refresh_view),
                    (WEAPON_RARITY_FILTERS, self._weapon_rarity_filters, self.refresh_view),
                )
            )
        )
        self.weapon_area, self.weapon_widget, self.weapon_grid = self._make_grid_area()
        self.weapon_grid.item_clicked.connect(
            lambda item_id: self._emit_grid_asset_click(
                self._weapon_grid_assets_by_id,
                self._on_weapon_card_clicked,
                item_id,
            )
        )
        editor.addWidget(self.weapon_area, 1)

        editor.addSpacing(6)
        self.character_title_label = QLabel()
        editor.addWidget(self.character_title_label)
        editor.addSpacing(6)
        editor.addLayout(
            self._build_filter_row(
                (
                    (ELEMENT_FILTERS, self._character_element_filters, self.refresh_view),
                    (WEAPON_TYPE_FILTERS, self._character_weapon_filters, self.refresh_view),
                    (
                        CHARACTER_RARITY_FILTERS,
                        self._character_rarity_filters,
                        self.refresh_view,
                    ),
                    (
                        CHARACTER_TRAIT_FILTERS,
                        self._character_trait_filters,
                        self.refresh_view,
                    ),
                ),
                trailing_widgets=(self._make_standard_filter_button(),),
            )
        )
        editor.addSpacing(6)
        self.character_area, self.character_widget, self.character_grid = (
            self._make_grid_area()
        )
        self.character_grid.item_clicked.connect(
            lambda item_id: self._emit_grid_asset_click(
                self._character_grid_assets_by_id,
                self._on_character_card_clicked,
                item_id,
            )
        )
        editor.addWidget(self.character_area, 3)

        self._init_edit_shortcuts()
        self.refresh_account_data(reload_presets=True, emit_signal=False)
        self.retranslate_ui()

    @property
    def is_editing(self) -> bool:
        return self._editing_preset is not None

    @property
    def is_new_deck_edit(self) -> bool:
        return self.is_editing and self._editing_is_new_deck

    def selected_preset(self) -> PvpDeckPreset | None:
        for preset in self.presets:
            if preset.deck_id == self.selected_deck_id:
                return preset
        return None

    def active_preset(self) -> PvpDeckPreset | None:
        return self._editing_preset or self.selected_preset()

    def refresh_account_data(
        self,
        *,
        reload_presets: bool = False,
        emit_signal: bool = True,
    ) -> None:
        self.character_assets = self._load_character_assets()
        self.weapon_assets = self._load_weapon_assets()
        if reload_presets:
            self.reload_presets(emit_signal=False)
        self.refresh_view()
        if emit_signal:
            self.state_changed.emit()

    def reload_presets(self, *, emit_signal: bool = True) -> None:
        self.presets = load_deck_presets(self.deck_dir)
        if self.selected_deck_id and not any(
            preset.deck_id == self.selected_deck_id for preset in self.presets
        ):
            self.selected_deck_id = ""
        if not self.selected_deck_id and self.presets:
            self.selected_deck_id = self.presets[0].deck_id
        if emit_signal:
            self.state_changed.emit()

    def create_deck(self, name: str = "") -> bool:
        if self.is_editing:
            return False
        self.refresh_account_data(reload_presets=False, emit_signal=False)
        try:
            preset = create_deck_preset_from_account_assets(
                self.character_assets,
                self.weapon_assets,
                name=name or self._default_new_deck_name(),
            )
        except DeckPresetError as exc:
            self._last_status = str(exc)
            self.refresh_view()
            self.state_changed.emit()
            return False
        self._last_status = ""
        self._selected_deck_id_before_new_edit = self.selected_deck_id
        self._editing_preset = preset
        self._editing_is_new_deck = True
        self.selected_deck_id = preset.deck_id
        self.refresh_view()
        self.state_changed.emit()
        return True

    def select_deck(self, deck_id: str) -> None:
        if self.is_editing:
            return
        if any(preset.deck_id == deck_id for preset in self.presets):
            self.selected_deck_id = deck_id
            self.refresh_view()
            self.state_changed.emit()

    def begin_edit(self) -> bool:
        if self.is_editing:
            return False
        preset = self.selected_preset()
        if preset is None:
            return False
        self._editing_preset = preset
        self._editing_is_new_deck = False
        self._selected_deck_id_before_new_edit = ""
        self.refresh_view()
        self.state_changed.emit()
        return True

    def save_edit(self, *, name: str = "") -> bool:
        preset = self._editing_preset
        if preset is None:
            return False
        if name:
            preset = rename_deck_preset(preset, name)
        try:
            save_deck_preset(preset, self.deck_dir)
        except DeckPresetError as exc:
            self._last_status = str(exc)
            self.state_changed.emit()
            return False
        self.selected_deck_id = preset.deck_id
        self._editing_preset = None
        self._editing_is_new_deck = False
        self._selected_deck_id_before_new_edit = ""
        self.reload_presets(emit_signal=False)
        self.selected_deck_id = preset.deck_id
        self.refresh_view()
        self.state_changed.emit()
        return True

    def cancel_edit(self) -> None:
        if self._editing_preset is None:
            return
        was_new = self._editing_is_new_deck
        previous_deck_id = self._selected_deck_id_before_new_edit
        self._editing_preset = None
        self._editing_is_new_deck = False
        self._selected_deck_id_before_new_edit = ""
        if was_new:
            if previous_deck_id and any(
                preset.deck_id == previous_deck_id for preset in self.presets
            ):
                self.selected_deck_id = previous_deck_id
            elif self.presets:
                self.selected_deck_id = self.presets[0].deck_id
            else:
                self.selected_deck_id = ""
        self.refresh_view()
        self.state_changed.emit()

    def delete_selected(self) -> bool:
        preset = self.selected_preset()
        if preset is None or self.is_editing:
            return False
        return self.delete_deck(preset.deck_id)

    def delete_deck(self, deck_id: str) -> bool:
        if self.is_editing:
            return False
        deleted = delete_deck_preset(deck_id, self.deck_dir)
        if self.selected_deck_id == deck_id:
            self.selected_deck_id = ""
        self.reload_presets(emit_signal=False)
        self.refresh_view()
        self.state_changed.emit()
        return deleted

    def validation_report(self):
        preset = self.active_preset()
        if preset is None:
            return None
        draft_deck = deck_preset_to_draft_deck(
            preset,
            self.character_assets,
            self.weapon_assets,
        )
        return validate_draft_deck(draft_deck)

    def selected_counts(self) -> tuple[int, int]:
        preset = self.active_preset()
        if preset is None:
            return (0, 0)
        return (len(preset.character_ids), len(preset.weapon_refs))

    def refresh_view(self) -> None:
        preset = self.active_preset()
        editing = self.is_editing
        character_ids = set(preset.character_ids) if preset is not None else set()
        weapon_keys = {ref.key for ref in preset.weapon_refs} if preset is not None else set()
        character_assets = self._visible_character_assets(character_ids, editing)
        weapon_assets = self._visible_weapon_assets(weapon_keys, editing)

        self._reload_deck_grid(
            weapon_assets,
            self.weapon_grid,
            self.weapon_widget,
            self.weapon_area,
            icon_size=WEAPON_PICKER_ICON_SIZE,
            spacing=6,
            selected_keys=weapon_keys,
            key_for_asset=self._weapon_key_for_asset,
            clicked=self._on_weapon_card_clicked,
            registry=self.weapon_cards_by_key,
            vertical_safe_margin=WEAPON_PICKER_SAFE_MARGIN,
            vertical_safe_top_margin=(
                WEAPON_PICKER_SAFE_MARGIN + WEAPON_PICKER_VIEWPORT_TOP_EXTENSION
            ),
        )
        self._reload_deck_grid(
            character_assets,
            self.character_grid,
            self.character_widget,
            self.character_area,
            icon_size=72,
            spacing=3,
            selected_keys=character_ids,
            key_for_asset=character_id_from_asset,
            clicked=self._on_character_card_clicked,
            registry=self.character_cards_by_id,
            vertical_safe_top_margin=CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN,
        )
        self._sync_empty_state()
        self._sync_edit_state()
        self._last_refresh_viewport_widths = self._current_viewport_widths()

    def retranslate_ui(self) -> None:
        self.character_title_label.setText(tr("app_shell.pvp.decks.characters"))
        self.weapon_title_label.setText(tr("app_shell.pvp.decks.weapons"))
        self._sync_empty_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_view_if_viewport_widths_changed()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(
                self._refresh_view_if_viewport_widths_changed
            )
        if self._current_viewport_widths() == self._last_refresh_viewport_widths:
            return
        self._resize_timer.start(75)

    def _load_character_assets(self) -> list[dict[str, Any]]:
        try:
            if self._character_assets_provider is not None:
                return list(self._character_assets_provider())
            return list(load_account_character_asset_items(db_path=self.db_path))
        except Exception as exc:
            self._last_status = str(exc)
            return []

    def _load_weapon_assets(self) -> list[dict[str, Any]]:
        try:
            if self._weapon_assets_provider is not None:
                return list(self._weapon_assets_provider())
            return list(load_account_weapon_stack_asset_items(db_path=self.db_path))
        except Exception as exc:
            self._last_status = str(exc)
            return []

    def _emit_grid_asset_click(
        self,
        assets_by_id: dict[str, dict[str, Any]],
        clicked,
        item_id: str,
    ) -> None:
        asset = assets_by_id.get(_text(item_id))
        if asset is None:
            return
        clicked(dict(asset))

    def _visible_character_assets(
        self,
        selected_ids: set[str],
        editing: bool,
    ) -> list[dict[str, Any]]:
        assets = [
            asset
            for asset in self.character_assets
            if character_matches_filters(
                asset,
                self._character_element_filters,
                self._character_weapon_filters,
                self._character_rarity_filters,
                trait_filters=self._character_trait_filters,
                standard_filter=self._character_standard_filter,
            )
        ]
        assets.sort(key=character_sort_key)
        if editing:
            return assets
        return [asset for asset in assets if character_id_from_asset(asset) in selected_ids]

    def _visible_weapon_assets(
        self,
        selected_keys: set[str],
        editing: bool,
    ) -> list[dict[str, Any]]:
        assets = [asset for asset in self.weapon_assets if self._weapon_matches_filters(asset)]
        assets.sort(key=_pvp_weapon_sort_key)
        if editing:
            return assets
        return [asset for asset in assets if self._weapon_key_for_asset(asset) in selected_keys]

    def _reload_deck_grid(
        self,
        assets: list[dict[str, Any]],
        grid: PixelIconGrid,
        container: PixelIconGrid,
        area: QScrollArea,
        *,
        icon_size: int,
        spacing: int,
        selected_keys: set[str],
        key_for_asset,
        clicked,
        registry: dict[str, Any],
        vertical_safe_margin: int = 0,
        vertical_safe_top_margin: int | None = None,
    ) -> None:
        registry.clear()
        safe_margin = max(0, int(vertical_safe_margin))
        safe_top_margin = (
            safe_margin
            if vertical_safe_top_margin is None
            else max(0, int(vertical_safe_top_margin))
        )
        grid.set_metrics(
            PixelIconGridMetrics(
                item_width=icon_size,
                gap_x=spacing,
                margin_top=safe_top_margin,
                margin_bottom=safe_margin,
            )
        )
        result = build_asset_grid_items(
            assets,
            key_for_asset=key_for_asset,
            outline_for_asset=lambda asset, key: _pvp_deck_outline(
                editing=self.is_editing,
                selected=bool(key and key in selected_keys),
            ),
            overlay_fill_for_asset=lambda asset, key: _pvp_deck_inactive_fill(
                editing=self.is_editing,
                selected=bool(key and key in selected_keys),
            ),
            properties_for_asset=lambda asset, key: _pvp_deck_item_properties(
                editing=self.is_editing,
                selected=bool(key and key in selected_keys),
            ),
        )
        grid.set_items(result.items)
        if grid is self.character_grid:
            self._character_grid_assets_by_id = result.assets_by_id
        else:
            self._weapon_grid_assets_by_id = result.assets_by_id
        for item in result.items:
            asset = result.assets_by_id.get(item.item_id, {})
            registry[item.item_id] = PvpDeckGridItemHandle(
                grid,
                item.item_id,
                asset,
                clicked,
            )

        container.updateGeometry()
        area.horizontalScrollBar().setValue(0)
        area.viewport().update()

    def _on_character_card_clicked(self, asset: dict[str, Any]) -> None:
        if self._editing_preset is None:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        character_id = character_id_from_asset(asset)
        if not character_id:
            return
        character_ids = list(self._editing_preset.character_ids)
        if character_id in character_ids:
            character_ids.remove(character_id)
        else:
            character_ids.append(character_id)
        self._editing_preset = update_deck_preset_selection(
            self._editing_preset,
            character_ids=character_ids,
            weapon_refs=self._editing_preset.weapon_refs,
        )
        self.refresh_view()
        self.state_changed.emit()

    def _on_weapon_card_clicked(self, asset: dict[str, Any]) -> None:
        if self._editing_preset is None:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        ref = weapon_ref_from_asset(asset)
        if ref is None or not ref.key:
            return
        refs = list(self._editing_preset.weapon_refs)
        existing_index = next(
            (index for index, item in enumerate(refs) if item.key == ref.key),
            None,
        )
        if existing_index is None:
            refs.append(ref)
        else:
            refs.pop(existing_index)
        self._editing_preset = update_deck_preset_selection(
            self._editing_preset,
            character_ids=self._editing_preset.character_ids,
            weapon_refs=refs,
        )
        self.refresh_view()
        self.state_changed.emit()

    def _sync_empty_state(self) -> None:
        preset = self.active_preset()
        if not self.character_assets and not self.weapon_assets:
            text = self._last_status or tr("app_shell.pvp.decks.empty_account")
        elif preset is None:
            text = tr("app_shell.pvp.decks.no_deck_selected")
        else:
            text = ""
        self.empty_label.setText(text)
        self.empty_label.setVisible(bool(text))

    def _current_viewport_widths(self) -> tuple[int, int]:
        return (
            self.weapon_area.viewport().width() or self.weapon_area.width(),
            self.character_area.viewport().width() or self.character_area.width(),
        )

    def _refresh_view_if_viewport_widths_changed(self) -> None:
        if self._current_viewport_widths() == self._last_refresh_viewport_widths:
            return
        self.refresh_view()

    def _init_edit_shortcuts(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._emit_save_edit_requested)
            shortcut.setEnabled(False)
            self._edit_shortcuts.append(shortcut)

        cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        cancel_shortcut.activated.connect(self._emit_cancel_edit_requested)
        cancel_shortcut.setEnabled(False)
        self._edit_shortcuts.append(cancel_shortcut)

    def _sync_edit_state(self) -> None:
        editing = self.is_editing
        if self.property("pvpDeckEditMode") != editing:
            self.setProperty("pvpDeckEditMode", editing)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        self._sync_grid_edit_state(self.weapon_area, self.weapon_widget, editing)
        self._sync_grid_edit_state(self.character_area, self.character_widget, editing)
        for shortcut in self._edit_shortcuts:
            shortcut.setEnabled(editing)

    def _sync_grid_edit_state(
        self,
        area: QScrollArea,
        container: QWidget,
        editing: bool,
    ) -> None:
        viewport = area.viewport()
        changed = False
        for widget in (area, viewport, container):
            if widget.property("deckEditMode") == editing:
                continue
            widget.setProperty("deckEditMode", editing)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
            changed = True
        if changed:
            area.update()

    def _emit_save_edit_requested(self) -> None:
        if self.is_editing:
            self.save_edit_requested.emit()

    def _emit_cancel_edit_requested(self) -> None:
        if self.is_editing:
            self.cancel_edit_requested.emit()

    def _default_new_deck_name(self) -> str:
        return f"{tr('app_shell.pvp.decks.default_name')} {len(self.presets) + 1}"

    def _make_grid_area(self) -> tuple[QScrollArea, PixelIconGrid, PixelIconGrid]:
        area = OverlayVerticalScrollArea(auto_hide_ms=850)
        area.setObjectName("pvp_deck_grid_area")
        area.setProperty("deckEditMode", False)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.viewport().setObjectName("pvp_deck_grid_viewport")
        area.viewport().setProperty("deckEditMode", False)
        container = PixelIconGrid(surface="pvp_deck_icon_grid")
        container.setObjectName("pvp_deck_grid_container")
        container.setProperty("deckEditMode", False)
        area.setWidget(container)
        return area, container, container

    @staticmethod
    def _weapon_key_for_asset(asset: dict[str, Any]) -> str:
        ref = weapon_ref_from_asset(asset)
        return ref.key if ref is not None else ""

    def _make_filter_button(
        self,
        value: Any,
        icon_name: str,
        active_set: set,
        update_callback,
    ) -> QPushButton:
        button = QPushButton("")
        button.setObjectName("app_shell_filter_button")
        button.setCheckable(True)
        button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
        button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
        button.setStyleSheet(FILTER_BUTTON_STYLE)

        icon_path = FILTER_ASSETS_DIR / icon_name
        if icon_path.exists():
            button.setIcon(QIcon(str(icon_path)))
        else:
            button.setText(str(value))

        def toggle_filter(checked: bool, *, filter_value=value, filters=active_set) -> None:
            if checked:
                filters.add(filter_value)
            else:
                filters.discard(filter_value)
            update_callback()

        button.clicked.connect(toggle_filter)
        return button

    def _build_filter_row(self, filter_groups, *, trailing_widgets=None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        for filters, active_set, update_callback in filter_groups:
            for value, icon_name, _tooltip_key in filters:
                button = self._make_filter_button(
                    value,
                    icon_name,
                    active_set,
                    update_callback,
                )
                if active_set is self._weapon_type_filters:
                    self._weapon_type_buttons[_text(value)] = button
                row.addWidget(button)
        for widget in trailing_widgets or ():
            row.addWidget(widget)
        row.addStretch()
        return row

    def _make_standard_filter_button(self) -> QPushButton:
        _value, _icon_name, _tooltip_key = CHARACTER_STANDARD_FILTER
        button = QPushButton("")
        button.setObjectName("app_shell_filter_button")
        button.setCheckable(False)
        button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
        button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
        button.setStyleSheet(FILTER_BUTTON_STYLE)
        button.setIcon(standard_character_filter_icon(STANDARD_FILTER_ALL, size=FILTER_BUTTON_ICON_SIZE))
        button.setProperty("standardOnly", False)

        def cycle_standard_filter() -> None:
            if self._character_standard_filter == STANDARD_FILTER_ALL:
                self._character_standard_filter = STANDARD_FILTER_ONLY
            elif self._character_standard_filter == STANDARD_FILTER_ONLY:
                self._character_standard_filter = STANDARD_FILTER_EXCLUDE
            else:
                self._character_standard_filter = STANDARD_FILTER_ALL
            button.setProperty(
                "standardOnly",
                self._character_standard_filter == STANDARD_FILTER_ONLY,
            )
            button.style().unpolish(button)
            button.style().polish(button)
            button.setIcon(
                standard_character_filter_icon(
                    self._character_standard_filter,
                    size=FILTER_BUTTON_ICON_SIZE,
                )
            )
            button.repaint()
            self.refresh_view()

        button.clicked.connect(cycle_standard_filter)
        return button

    def _weapon_matches_filters(self, asset: dict[str, Any]) -> bool:
        metadata = asset.get("metadata") or {}
        weapon = metadata.get("weapon") or {}
        weapon_type_keys = _weapon_type_filter_keys(weapon)
        rarity = metadata_int(weapon.get("rarity"))
        if self._weapon_type_filters and not (
            weapon_type_keys & self._weapon_type_filters
        ):
            return False
        if self._weapon_rarity_filters and rarity not in self._weapon_rarity_filters:
            return False
        return True


PVP_DECKS_RIGHT_PANEL_STYLE = f"""
QLineEdit {{
    min-height: 28px;
    padding: 4px 8px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_APP};
    color: {UI_TEXT_PRIMARY};
}}
QFrame#build_slot_row {{
    border: 1px solid #343b49;
    border-radius: 7px;
    background: {UI_BG_PANEL_RAISED};
}}
QFrame#build_slot_row[selectedDeck="true"] {{
    border-color: #d6b35f;
    background: #3a3224;
}}
QFrame#pvp_deck_expanded_info {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 6px;
    background: {UI_BG_PANEL};
}}
QLabel#small_muted {{
    color: {UI_TEXT_MUTED};
    font-size: 12px;
}}
QLabel#pvp_deck_info_line {{
    color: {UI_TEXT_SECONDARY};
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#icon_button,
QPushButton#row_save_button,
QPushButton#row_cancel_button {{
    min-width: {PVP_DECK_ROW_ACTION_SIZE}px;
    max-width: {PVP_DECK_ROW_ACTION_SIZE}px;
    min-height: {PVP_DECK_ROW_ACTION_SIZE}px;
    max-height: {PVP_DECK_ROW_ACTION_SIZE}px;
    padding: 2px;
}}
QPushButton#row_save_button {{
    border-color: {UI_STATE_SUCCESS};
    background: #24452d;
}}
QPushButton#row_save_button:hover {{
    background: #2d5938;
}}
QPushButton#row_cancel_button {{
    border-color: {UI_STATE_DANGER};
    background: #4a2529;
}}
QPushButton#row_cancel_button:hover {{
    background: #5c2d32;
}}
QPushButton#pvp_ruleset_chip {{
    min-height: 24px;
    padding: 2px 7px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_SECONDARY};
    font-weight: 700;
}}
QPushButton#pvp_ruleset_chip:disabled {{
    color: #798291;
    background: {UI_BG_BUTTON};
    border-color: #343b49;
}}
"""


class PvpDecksRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpDecksWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.pending_delete_deck_id = ""
        self.deck_row_frames: dict[str, QFrame] = {}
        self.selected_info_labels: dict[str, QLabel] = {}
        self.edit_name_edit: QLineEdit | None = None
        self.ruleset_button: QPushButton | None = None
        self._edit_shortcuts: list[QShortcut] = []
        self._preserved_edit_deck_id = ""
        self._preserved_edit_name = ""
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.create_row_widget = QWidget()
        create_layout = QHBoxLayout(self.create_row_widget)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.setSpacing(6)
        self.create_name_edit = QLineEdit()
        self.create_name_edit.installEventFilter(self)
        create_layout.addWidget(self.create_name_edit, 1)

        self.create_button = QPushButton()
        self.create_button.setObjectName("icon_button")
        self.create_button.setIcon(self._ui_icon("plus"))
        self.create_button.clicked.connect(self._on_create_clicked)
        create_layout.addWidget(self.create_button)

        self.cancel_new_deck_button = QPushButton()
        self.cancel_new_deck_button.setObjectName("row_cancel_button")
        self.cancel_new_deck_button.setIcon(self._ui_icon("x"))
        self.cancel_new_deck_button.clicked.connect(self._on_cancel_new_clicked)
        create_layout.addWidget(self.cancel_new_deck_button)
        root.addWidget(self.create_row_widget)

        self.deck_list_scroll = OverlayVerticalScrollArea()
        self.deck_list_scroll.setWidgetResizable(True)
        self.deck_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        list_content = QWidget()
        self.deck_list_layout = QVBoxLayout(list_content)
        self.deck_list_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_list_layout.setSpacing(5)
        self.deck_list_scroll.setWidget(list_content)
        root.addWidget(self.deck_list_scroll, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self._init_edit_shortcuts()
        self.create_name_edit.returnPressed.connect(self._on_create_clicked)
        self.workspace.state_changed.connect(self.refresh)
        self.workspace.save_edit_requested.connect(self._save_active_edit)
        self.workspace.cancel_edit_requested.connect(self._cancel_active_edit)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        self._capture_existing_edit_name()
        self._clear_stale_pending_delete()
        self._refresh_create_controls()
        self._rebuild_deck_list()
        status = self.workspace._last_status
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        self._sync_edit_shortcuts()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.decks.title"))
        self.create_name_edit.setPlaceholderText(
            tr("app_shell.pvp.decks.create_placeholder")
        )
        self._install_button_tooltip(self.create_button, tr("artifact.build.new"))
        self._install_button_tooltip(
            self.cancel_new_deck_button,
            tr("artifact.build.cancel"),
        )
        self.refresh()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.create_name_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.workspace.is_editing:
                    self._save_active_edit()
                else:
                    self._on_create_clicked()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape:
                if self.workspace.is_new_deck_edit:
                    self._on_cancel_new_clicked()
                else:
                    self.create_name_edit.clear()
                event.accept()
                return True
        if (
            watched is self.edit_name_edit
            and event.type() == QEvent.Type.KeyPress
        ):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._save_existing_from(watched)
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_active_edit()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self.workspace.is_editing and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self._save_active_edit()
            event.accept()
            return
        if self.workspace.is_editing and event.key() == Qt.Key.Key_Escape:
            self._cancel_active_edit()
            event.accept()
            return
        if self.pending_delete_deck_id:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._confirm_delete_deck(self.pending_delete_deck_id)
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_delete_deck()
                event.accept()
                return
        super().keyPressEvent(event)

    def _init_edit_shortcuts(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._save_active_edit)
            shortcut.setEnabled(False)
            self._edit_shortcuts.append(shortcut)

        cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        cancel_shortcut.activated.connect(self._cancel_active_edit)
        cancel_shortcut.setEnabled(False)
        self._edit_shortcuts.append(cancel_shortcut)

    def _sync_edit_shortcuts(self) -> None:
        editing = self.workspace.is_editing
        for shortcut in self._edit_shortcuts:
            shortcut.setEnabled(editing)

    def _capture_existing_edit_name(self) -> None:
        self._preserved_edit_deck_id = ""
        self._preserved_edit_name = ""
        if not self.workspace.is_editing or self.workspace.is_new_deck_edit:
            return
        active_preset = self.workspace.active_preset()
        if active_preset is None or self.edit_name_edit is None:
            return
        self._preserved_edit_deck_id = active_preset.deck_id
        self._preserved_edit_name = self.edit_name_edit.text()

    def _refresh_create_controls(self) -> None:
        new_edit = self.workspace.is_new_deck_edit
        existing_edit = self.workspace.is_editing and not new_edit
        if new_edit:
            preset = self.workspace.active_preset()
            if preset is not None and not self.create_name_edit.text().strip():
                self.create_name_edit.setText(preset.name)
        elif not self.workspace.is_editing:
            if self.create_button.objectName() == "row_save_button":
                self.create_name_edit.clear()

        self.create_name_edit.setEnabled(not existing_edit)
        self.create_button.setEnabled(not existing_edit)
        self.create_button.setObjectName("row_save_button" if new_edit else "icon_button")
        self.create_button.setIcon(self._ui_icon("save" if new_edit else "plus"))
        self._install_button_tooltip(
            self.create_button,
            tr("artifact.build.save") if new_edit else tr("artifact.build.new"),
        )
        self.cancel_new_deck_button.setVisible(new_edit)
        for button in (self.create_button, self.cancel_new_deck_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.ensurePolished()
            button.sizeHint()

    def _rebuild_deck_list(self) -> None:
        _clear_layout(self.deck_list_layout)
        self.deck_row_frames.clear()
        self.selected_info_labels.clear()
        self.edit_name_edit = None
        self.ruleset_button = None

        if not self.workspace.presets:
            if not self.workspace.is_new_deck_edit:
                label = QLabel(tr("app_shell.pvp.decks.list_empty"))
                label.setObjectName("small_muted")
                label.setWordWrap(True)
                self.deck_list_layout.addWidget(label)
            self.deck_list_layout.addStretch(1)
            return

        for preset in self.workspace.presets:
            row = self._make_deck_row(preset)
            self.deck_list_layout.addWidget(row)
            self.deck_row_frames[preset.deck_id] = row
        self.deck_list_layout.addStretch(1)

    def _make_deck_row(self, preset: PvpDeckPreset) -> QFrame:
        selected = preset.deck_id == self.workspace.selected_deck_id
        pending = self.pending_delete_deck_id == preset.deck_id
        editing_this_row = (
            self.workspace.is_editing
            and not self.workspace.is_new_deck_edit
            and self.workspace.active_preset() is not None
            and self.workspace.active_preset().deck_id == preset.deck_id
        )

        row = QFrame()
        row.setObjectName("build_slot_row")
        row.setProperty("selectedDeck", selected or editing_this_row)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)
        outer.addLayout(top)

        if editing_this_row:
            name_input = QLineEdit()
            active_preset = self.workspace.active_preset()
            name_text = active_preset.name if active_preset is not None else ""
            if (
                active_preset is not None
                and self._preserved_edit_deck_id == active_preset.deck_id
            ):
                name_text = self._preserved_edit_name
            name_input.setText(name_text)
            name_input.setPlaceholderText(tr("app_shell.pvp.decks.create_placeholder"))
            name_input.installEventFilter(self)
            name_input.returnPressed.connect(lambda: self._save_existing_from(name_input))
            top.addWidget(name_input, 1)
            self.edit_name_edit = name_input
        else:
            select_button = MarqueeButton(preset.name)
            select_button.setCheckable(True)
            select_button.setChecked(selected)
            select_button.setEnabled(not self.workspace.is_editing)
            select_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self.workspace.select_deck(deck_id)
            )
            top.addWidget(select_button, 1)

        if pending:
            confirm_label = QLabel(tr("artifact.build.delete_confirm_short"))
            confirm_label.setObjectName("small_muted")
            top.addWidget(confirm_label)

            confirm_button = self._row_icon_button("check", tr("artifact.build.delete"))
            confirm_button.setObjectName("row_save_button")
            confirm_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self._confirm_delete_deck(deck_id)
            )
            self._prepare_row_action_button(confirm_button)
            top.addWidget(confirm_button)

            cancel_button = self._row_icon_button("x", tr("common.cancel"))
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.clicked.connect(self._cancel_delete_deck)
            self._prepare_row_action_button(cancel_button)
            top.addWidget(cancel_button)
            return row

        if editing_this_row:
            save_button = self._row_icon_button("save", tr("artifact.build.save"))
            save_button.setObjectName("row_save_button")
            save_button.clicked.connect(lambda _checked=False: self._save_existing_from(name_input))
            self._prepare_row_action_button(save_button)
            top.addWidget(save_button)

            cancel_button = self._row_icon_button("x", tr("artifact.build.cancel"))
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.clicked.connect(self._cancel_active_edit)
            self._prepare_row_action_button(cancel_button)
            top.addWidget(cancel_button)
        else:
            count_label = QLabel(f"({len(preset.character_ids) + len(preset.weapon_refs)})")
            count_label.setObjectName("small_muted")
            top.addWidget(count_label)

            edit_button = self._row_icon_button("edit", tr("artifact.build.edit"))
            edit_button.clicked.connect(self.workspace.begin_edit)
            top.addWidget(edit_button)

            delete_button = self._row_icon_button("delete", tr("artifact.build.delete"))
            delete_button.clicked.connect(
                lambda _checked=False, deck_id=preset.deck_id: self._request_delete_deck(deck_id)
            )
            top.addWidget(delete_button)

        if selected or editing_this_row:
            self._add_expanded_deck_info(outer, preset if not editing_this_row else self.workspace.active_preset())

        return row

    def _add_expanded_deck_info(
        self,
        outer: QVBoxLayout,
        preset: PvpDeckPreset | None,
    ) -> None:
        if preset is None:
            return
        info = QFrame()
        info.setObjectName("pvp_deck_expanded_info")
        layout = QVBoxLayout(info)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.ruleset_button = QPushButton(tr("app_shell.pvp.decks.ruleset_free"))
        self.ruleset_button.setObjectName("pvp_ruleset_chip")
        self.ruleset_button.setEnabled(False)
        layout.addWidget(self.ruleset_button)

        counts_label = self._info_label(
            tr("app_shell.pvp.decks.counts").format(
                characters=len(preset.character_ids),
                weapons=len(preset.weapon_refs),
            )
        )
        layout.addWidget(counts_label)
        self.selected_info_labels["counts"] = counts_label

        validation_label = self._info_label(self._validation_text())
        validation_label.setWordWrap(True)
        layout.addWidget(validation_label)
        self.selected_info_labels["validation"] = validation_label

        outer.addWidget(info)

    def _info_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pvp_deck_info_line")
        return label

    def _validation_text(self) -> str:
        preset = self.workspace.active_preset()
        if preset is None:
            return tr("app_shell.pvp.decks.validation_none")
        try:
            report = self.workspace.validation_report()
        except Exception as exc:
            return tr("app_shell.pvp.decks.validation_error").format(error=str(exc))
        if report is None:
            return tr("app_shell.pvp.decks.validation_none")
        codes = list(report.issue_codes())
        code_text = ", ".join(codes[:4])
        if len(codes) > 4:
            code_text += ", ..."
        if report.ready:
            return tr("app_shell.pvp.decks.validation_ready").format(
                issues=len(codes),
            )
        return tr("app_shell.pvp.decks.validation_invalid").format(
            issues=len(codes),
            codes=f": {code_text}" if code_text else "",
        )

    def _on_create_clicked(self) -> None:
        if self.workspace.is_new_deck_edit:
            if self.workspace.save_edit(name=self.create_name_edit.text()):
                self.create_name_edit.clear()
            return
        if self.workspace.is_editing:
            return
        if self.workspace.create_deck(self.create_name_edit.text()):
            preset = self.workspace.active_preset()
            if preset is not None:
                self.create_name_edit.setText(preset.name)

    def _on_cancel_new_clicked(self) -> None:
        if self.workspace.is_new_deck_edit:
            self.workspace.cancel_edit()
        self.create_name_edit.clear()

    def _save_existing_from(self, name_input: QLineEdit) -> None:
        self.workspace.save_edit(name=name_input.text())

    def _save_active_edit(self) -> None:
        if self.workspace.is_new_deck_edit:
            if self.workspace.save_edit(name=self.create_name_edit.text()):
                self.create_name_edit.clear()
        elif self.edit_name_edit is not None:
            self.workspace.save_edit(name=self.edit_name_edit.text())

    def _cancel_active_edit(self) -> None:
        if self.workspace.is_new_deck_edit:
            self._on_cancel_new_clicked()
        else:
            self.workspace.cancel_edit()

    def _request_delete_deck(self, deck_id: str) -> None:
        if self.workspace.is_editing:
            return
        self.pending_delete_deck_id = deck_id
        self.refresh()

    def _cancel_delete_deck(self) -> None:
        self.pending_delete_deck_id = ""
        self.refresh()

    def _confirm_delete_deck(self, deck_id: str) -> None:
        if self.pending_delete_deck_id != deck_id:
            return
        self.pending_delete_deck_id = ""
        self.workspace.delete_deck(deck_id)

    def _clear_stale_pending_delete(self) -> None:
        if not self.pending_delete_deck_id:
            return
        if any(preset.deck_id == self.pending_delete_deck_id for preset in self.workspace.presets):
            return
        self.pending_delete_deck_id = ""

    def _row_icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("icon_button")
        button.setIcon(self._ui_icon(icon_name))
        self._install_button_tooltip(button, tooltip)
        self._prepare_row_action_button(button)
        return button

    def _ui_icon(self, name: str) -> QIcon:
        return auto_contrast_svg_icon(
            name,
            PVP_DECK_UI_ICON_SIZE,
            PVP_DECK_UI_ICON_BACKGROUND,
        )

    def _install_button_tooltip(self, button: QPushButton, text: str) -> None:
        controller = button.property("_custom_tooltip_controller")
        if controller is None:
            controller = install_custom_tooltip(button)
            button.setProperty("_custom_tooltip_controller", controller)
        controller.set_text(text)
        button.setToolTip("")

    def _prepare_row_action_button(self, button: QPushButton) -> None:
        button.ensurePolished()
        button.sizeHint()
        button.minimumSizeHint()




def _clear_grid(grid: QGridLayout) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()
        if child_layout is not None:
            _clear_layout(child_layout)
        if widget is not None:
            widget.deleteLater()


def _reset_grid_columns(grid: QGridLayout) -> None:
    for column in range(grid.columnCount()):
        grid.setColumnMinimumWidth(column, 0)
        grid.setColumnStretch(column, 0)


def _pvp_deck_outline(
    *,
    editing: bool,
    selected: bool,
) -> PixelIconGridOutline | None:
    if not editing or not selected:
        return None
    return PixelIconGridOutline(
        color="#d6b15d",
        width=2,
        radius=4,
        alpha=255,
    )


def _pvp_deck_inactive_fill(
    *,
    editing: bool,
    selected: bool,
) -> PixelIconGridFill | None:
    if not editing or selected:
        return None
    return PixelIconGridFill(color="#0f172a", alpha=132)


def _pvp_deck_item_properties(
    *,
    editing: bool,
    selected: bool,
) -> dict[str, bool]:
    return {
        "deckSelected": bool(selected),
        "deckInactive": bool(editing and not selected),
        "deckEditing": bool(editing),
        "deckEditSelected": bool(editing and selected),
    }


def _weapon_type_filter_keys(weapon: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for numeric_key in ("weapon_type", "type"):
        weapon_type_id = _optional_int(weapon.get(numeric_key))
        if weapon_type_id is not None:
            filter_key = WEAPON_TYPE_FILTER_BY_ID.get(weapon_type_id)
            if filter_key:
                keys.add(filter_key)
    for text_key in ("weapon_type_name", "type_name", "type"):
        token = _filter_token(weapon.get(text_key))
        if not token:
            continue
        filter_key = WEAPON_TYPE_FILTER_ALIASES.get(token)
        if filter_key:
            keys.add(filter_key)
    return keys


def _filter_token(value: Any) -> str:
    return (
        _text(value)
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("__", "_")
    )


def _pvp_weapon_sort_key(asset: dict[str, Any]):
    metadata = asset.get("metadata") or {}
    weapon = metadata.get("weapon") or {}
    rarity = metadata_int(weapon.get("rarity"))
    level = metadata_int(weapon.get("level"))
    name = _text(weapon.get("name") or metadata.get("name") or asset.get("filename"))
    key = _text(weapon.get("source_key") or weapon.get("weapon_fingerprint"))
    return (-rarity, -level, name.casefold(), key)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "PvpDeckAssetIconLabel",
    "PvpDecksRightPanel",
    "PvpDecksWorkspace",
]
