from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
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
from run_workspace.pvp.account_deck_copy import copy_deck_for_player_2
from run_workspace.pvp.deck import DraftDeck
from run_workspace.pvp.free_draft_controller import (
    FreeDraftController,
    FreeDraftControllerActionRejected,
)
from run_workspace.pvp.validation import DeckValidationReport, validate_draft_deck
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
PVP_PAGE_DECKS = "decks"
PVP_PAGE_PLAY = "play"
PVP_PAGE_DRAFT = "draft"

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


@dataclass(frozen=True, slots=True)
class PvpActiveDraftSession:
    player_1_deck_id: str
    player_1_deck_name: str
    player_2_deck_id: str
    player_2_deck_name: str
    controller: FreeDraftController

    def board_dict(self) -> dict[str, Any]:
        return self.controller.to_board_dict()


@dataclass(frozen=True, slots=True)
class PvpDeckStartStatus:
    preset: PvpDeckPreset | None
    draft_deck: DraftDeck | None
    report: DeckValidationReport | None
    text: str
    ready: bool
    issue_codes: tuple[str, ...] = ()


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
QLabel#small_muted {
    color: #9aa4ad;
    font-size: 12px;
}
QLabel#pvp_deck_info_line {
    color: #c5ced6;
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 12px;
    font-weight: 600;
}
QFrame#pvp_deck_expanded_info {
    border: 1px solid #343b49;
    border-radius: 6px;
    background: #181d23;
}
"""

PVP_DRAFT_WORKSPACE_STYLE = PVP_DECKS_WORKSPACE_STYLE + f"""
QFrame#pvp_draft_banner,
QFrame#pvp_draft_zone,
QFrame#pvp_draft_completed,
QFrame#pvp_draft_empty {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL};
}}
QFrame#pvp_draft_banner[complete="true"] {{
    border-color: {UI_STATE_SUCCESS};
    background: #18291f;
}}
QFrame#pvp_draft_zone[activeSeat="true"] {{
    border-color: #4f8ee8;
    background: #182336;
}}
QScrollArea#pvp_draft_scroll {{
    background: transparent;
    border: none;
}}
QWidget#pvp_draft_scroll_viewport,
QWidget#pvp_draft_scroll_content {{
    background: transparent;
}}
QPushButton#pvp_draft_card {{
    min-width: 116px;
    max-width: 116px;
    min-height: 76px;
    max-height: 76px;
    padding: 5px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 8px;
    background: {UI_BG_PANEL_RAISED};
    color: {UI_TEXT_SECONDARY};
    text-align: left;
    font-size: 11px;
    font-weight: 700;
}}
QPushButton#pvp_draft_card[legalTarget="true"] {{
    border-color: {UI_STATE_SUCCESS};
    background: #203b28;
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#pvp_draft_card[status="picked_by_self"] {{
    border-color: {UI_STATE_SUCCESS};
    background: #24452d;
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#pvp_draft_card[status="globally_banned"] {{
    border-color: {UI_STATE_DANGER};
    background: #432126;
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#pvp_draft_card[status="blocked_by_opponent_pick"] {{
    border-color: #69512d;
    background: #352a1d;
    color: {UI_TEXT_SECONDARY};
}}
QPushButton#pvp_draft_card:disabled {{
    color: {UI_TEXT_MUTED};
}}
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


class PvpPlayWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PvpPlayWorkspace")
        self.setStyleSheet(PVP_DECKS_WORKSPACE_STYLE)
        self._active_session: PvpActiveDraftSession | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.mode_label = QLabel()
        self.mode_label.setObjectName("small_muted")
        self.mode_label.setWordWrap(True)
        root.addWidget(self.mode_label)

        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("pvp_deck_expanded_info")
        summary_layout = QVBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(5)
        self.summary_title_label = QLabel()
        self.summary_title_label.setObjectName("pvp_deck_info_line")
        summary_layout.addWidget(self.summary_title_label)
        self.summary_labels: list[QLabel] = []
        for _index in range(7):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            summary_layout.addWidget(label)
            self.summary_labels.append(label)
        root.addWidget(self.summary_frame)
        root.addStretch(1)
        self.retranslate_ui()

    def set_active_session(self, session: PvpActiveDraftSession | None) -> None:
        self._active_session = session
        self.refresh()

    def refresh(self) -> None:
        session = self._active_session
        if session is None:
            self.summary_title_label.setText(tr("app_shell.pvp.play.left_idle_title"))
            lines = [tr("app_shell.pvp.play.setup_on_right")]
        else:
            self.summary_title_label.setText(tr("app_shell.pvp.play.active_local_draft"))
            lines = _active_draft_summary_lines(session)
        for index, label in enumerate(self.summary_labels):
            text = lines[index] if index < len(lines) else ""
            label.setText(text)
            label.setVisible(bool(text))

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.play.title"))
        self.mode_label.setText(tr("app_shell.pvp.play.mode_local_hotseat"))
        self.refresh()


class PvpDraftCardButton(QPushButton):
    card_clicked = Signal(str, str)

    def __init__(
        self,
        *,
        seat: str,
        card: Mapping[str, Any],
        draft_complete: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.seat = seat
        self.character_id = _text(card.get("character_id"))
        status = _text(card.get("status")) or "available"
        legal = bool(card.get("is_current_legal_target")) and not draft_complete
        self.setObjectName("pvp_draft_card")
        self.setProperty("seat", seat)
        self.setProperty("characterId", self.character_id)
        self.setProperty("status", status)
        self.setProperty("legalTarget", legal)
        self.setProperty("activeSeat", bool(card.get("is_active_seat_card")))
        self.setText(_draft_card_text(card))
        self.setEnabled(legal)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if legal
            else Qt.CursorShape.ArrowCursor
        )
        self.clicked.connect(
            lambda _checked=False: self.card_clicked.emit(self.seat, self.character_id)
        )
        _refresh_qss(self)


class PvpDraftWorkspace(QWidget):
    card_clicked = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PvpDraftWorkspace")
        self.setStyleSheet(PVP_DRAFT_WORKSPACE_STYLE)
        self._active_session: PvpActiveDraftSession | None = None
        self._status_text = ""
        self.card_buttons_by_key: dict[tuple[str, str], PvpDraftCardButton] = {}
        self.legal_card_buttons: list[PvpDraftCardButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.empty_frame = QFrame()
        self.empty_frame.setObjectName("pvp_draft_empty")
        empty_layout = QVBoxLayout(self.empty_frame)
        empty_layout.setContentsMargins(12, 12, 12, 12)
        empty_layout.setSpacing(6)
        self.empty_title_label = QLabel()
        self.empty_title_label.setObjectName("pvp_deck_info_line")
        empty_layout.addWidget(self.empty_title_label)
        self.empty_body_label = QLabel()
        self.empty_body_label.setObjectName("small_muted")
        self.empty_body_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_body_label)
        root.addWidget(self.empty_frame)

        self.board_frame = QFrame()
        self.board_frame.setObjectName("pvp_draft_banner")
        board_layout = QVBoxLayout(self.board_frame)
        board_layout.setContentsMargins(12, 12, 12, 12)
        board_layout.setSpacing(8)

        self.action_title_label = QLabel()
        self.action_title_label.setObjectName("pvp_deck_info_line")
        self.action_title_label.setWordWrap(True)
        board_layout.addWidget(self.action_title_label)

        self.action_detail_label = QLabel()
        self.action_detail_label.setObjectName("small_muted")
        self.action_detail_label.setWordWrap(True)
        board_layout.addWidget(self.action_detail_label)
        root.addWidget(self.board_frame)

        self.scroll_area = OverlayVerticalScrollArea()
        self.scroll_area.setObjectName("pvp_draft_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setObjectName("pvp_draft_scroll_viewport")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("pvp_draft_scroll_content")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(10)
        self.scroll_area.setWidget(self.scroll_content)
        root.addWidget(self.scroll_area, 1)

        self.completed_frame = QFrame()
        self.completed_frame.setObjectName("pvp_draft_completed")
        completed_layout = QVBoxLayout(self.completed_frame)
        completed_layout.setContentsMargins(10, 10, 10, 10)
        completed_layout.setSpacing(5)
        self.completed_title_label = QLabel()
        self.completed_title_label.setObjectName("pvp_deck_info_line")
        completed_layout.addWidget(self.completed_title_label)
        self.completed_labels: list[QLabel] = []
        for _index in range(5):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            completed_layout.addWidget(label)
            self.completed_labels.append(label)
        root.addWidget(self.completed_frame)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.retranslate_ui()
        self.refresh()

    def set_active_session(
        self,
        session: PvpActiveDraftSession | None,
        *,
        status_text: str = "",
    ) -> None:
        self._active_session = session
        self._status_text = status_text
        self.refresh()

    def refresh(self) -> None:
        session = self._active_session
        has_session = session is not None
        self.empty_frame.setVisible(not has_session)
        self.board_frame.setVisible(has_session)
        self.scroll_area.setVisible(has_session)
        self.completed_frame.setVisible(has_session)
        self.status_label.setText(self._status_text)
        self.status_label.setVisible(bool(self._status_text))
        self.card_buttons_by_key.clear()
        self.legal_card_buttons.clear()
        _clear_layout(self.scroll_layout)

        if session is None:
            self.board_frame.setProperty("complete", False)
            _refresh_qss(self.board_frame)
            self._refresh_completed(None)
            return

        board = session.board_dict()
        complete = _draft_is_complete(board)
        self.board_frame.setProperty("complete", complete)
        _refresh_qss(self.board_frame)
        self.action_title_label.setText(_draft_action_title(board))
        self.action_detail_label.setText(_draft_action_detail(board))

        seats = _mapping(board.get("seats"))
        for seat in ("player_1", "player_2"):
            self.scroll_layout.addWidget(self._build_seat_zone(seat, _mapping(seats.get(seat)), complete))
        self.scroll_layout.addStretch(1)
        self._refresh_completed(board)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_title_label.setText(tr("app_shell.pvp.draft.no_active_title"))
        self.empty_body_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self.completed_title_label.setText(tr("app_shell.pvp.draft.completed_title"))
        self.refresh()

    def _build_seat_zone(
        self,
        seat: str,
        seat_board: Mapping[str, Any],
        draft_complete: bool,
    ) -> QFrame:
        zone = QFrame()
        zone.setObjectName("pvp_draft_zone")
        zone.setProperty("activeSeat", _seat_is_active(seat_board))
        _refresh_qss(zone)
        layout = QVBoxLayout(zone)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        title = QLabel(_seat_title(seat, seat_board))
        title.setObjectName("pvp_deck_info_line")
        layout.addWidget(title)

        deck = _mapping(seat_board.get("deck"))
        info = QLabel(
            tr("app_shell.pvp.draft.deck_counts").format(
                characters=int(deck.get("character_count") or 0),
                weapons=int(deck.get("weapon_stack_count") or 0),
            )
        )
        info.setObjectName("small_muted")
        layout.addWidget(info)

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(6)
        grid_layout.setVerticalSpacing(6)
        columns = 4
        cards = seat_board.get("cards")
        if not isinstance(cards, list):
            cards = []
        for index, card_value in enumerate(cards):
            card = _mapping(card_value)
            button = PvpDraftCardButton(
                seat=seat,
                card=card,
                draft_complete=draft_complete,
            )
            button.card_clicked.connect(self.card_clicked.emit)
            key = (seat, button.character_id)
            self.card_buttons_by_key[key] = button
            if button.property("legalTarget"):
                self.legal_card_buttons.append(button)
            grid_layout.addWidget(button, index // columns, index % columns)
        layout.addWidget(grid_widget)
        return zone

    def _refresh_completed(self, board: Mapping[str, Any] | None) -> None:
        visible = bool(board and _draft_is_complete(board))
        self.completed_frame.setVisible(visible)
        lines = _completed_draft_lines(board) if visible and board is not None else []
        for index, label in enumerate(self.completed_labels):
            text = lines[index] if index < len(lines) else ""
            label.setText(text)
            label.setVisible(bool(text))


class PvpWorkspace(QWidget):
    state_changed = Signal()
    page_changed = Signal(str)
    active_draft_changed = Signal()

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
        self.setObjectName("PvpWorkspace")
        self.active_page_id = PVP_PAGE_DECKS
        self.active_draft_session: PvpActiveDraftSession | None = None
        self._last_play_status = ""
        self._last_draft_status = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.decks_workspace = PvpDecksWorkspace(
            db_path=db_path,
            deck_dir=deck_dir,
            character_assets_provider=character_assets_provider,
            weapon_assets_provider=weapon_assets_provider,
        )
        self.play_workspace = PvpPlayWorkspace()
        self.draft_workspace = PvpDraftWorkspace()
        self.stack.addWidget(self.decks_workspace)
        self.stack.addWidget(self.play_workspace)
        self.stack.addWidget(self.draft_workspace)
        self.decks_workspace.state_changed.connect(self._on_decks_state_changed)
        self.draft_workspace.card_clicked.connect(self.apply_draft_card_click)
        self._sync_play_workspace()
        self._sync_draft_workspace()

    @property
    def character_assets(self) -> list[dict[str, Any]]:
        return self.decks_workspace.character_assets

    @property
    def weapon_assets(self) -> list[dict[str, Any]]:
        return self.decks_workspace.weapon_assets

    @property
    def presets(self) -> list[PvpDeckPreset]:
        return self.decks_workspace.presets

    @property
    def selected_deck_id(self) -> str:
        return self.decks_workspace.selected_deck_id

    def selected_preset(self) -> PvpDeckPreset | None:
        return self.decks_workspace.selected_preset()

    def set_page(self, page_id: str) -> None:
        page_id = (
            page_id
            if page_id in {PVP_PAGE_DECKS, PVP_PAGE_PLAY, PVP_PAGE_DRAFT}
            else PVP_PAGE_DECKS
        )
        previous = self.active_page_id
        self.active_page_id = page_id
        if page_id == PVP_PAGE_PLAY:
            widget = self.play_workspace
        elif page_id == PVP_PAGE_DRAFT:
            widget = self.draft_workspace
        else:
            widget = self.decks_workspace
        self.stack.setCurrentWidget(widget)
        self._sync_play_workspace()
        self._sync_draft_workspace()
        if previous != page_id:
            self.page_changed.emit(page_id)

    def refresh_account_data(
        self,
        *,
        reload_presets: bool = False,
        emit_signal: bool = True,
    ) -> None:
        self.decks_workspace.refresh_account_data(
            reload_presets=reload_presets,
            emit_signal=False,
        )
        self._sync_play_workspace()
        self._sync_draft_workspace()
        if emit_signal:
            self.state_changed.emit()

    def retranslate_ui(self) -> None:
        self.decks_workspace.retranslate_ui()
        self.play_workspace.retranslate_ui()
        self.draft_workspace.retranslate_ui()
        self._sync_play_workspace()
        self._sync_draft_workspace()

    def preset_by_id(self, deck_id: str) -> PvpDeckPreset | None:
        for preset in self.decks_workspace.presets:
            if preset.deck_id == deck_id:
                return preset
        return None

    def play_deck_options(self) -> tuple[PvpDeckPreset, ...]:
        return tuple(self.decks_workspace.presets)

    def default_player_1_deck_id(self) -> str:
        selected_id = self.decks_workspace.selected_deck_id
        if selected_id and self.preset_by_id(selected_id) is not None:
            return selected_id
        for preset in self.decks_workspace.presets:
            status = self.deck_start_status(preset.deck_id, player_label="Player 1")
            if status.ready:
                return preset.deck_id
        return self.decks_workspace.presets[0].deck_id if self.decks_workspace.presets else ""

    def default_player_2_deck_id(self, player_1_deck_id: str = "") -> str:
        presets = self.decks_workspace.presets
        if not presets:
            return ""
        if len(presets) == 1:
            return player_1_deck_id or presets[0].deck_id
        return presets[0].deck_id

    def deck_start_status(
        self,
        deck_id: str,
        *,
        player_label: str,
    ) -> PvpDeckStartStatus:
        preset = self.preset_by_id(deck_id)
        if preset is None:
            return PvpDeckStartStatus(
                preset=None,
                draft_deck=None,
                report=None,
                text=tr("app_shell.pvp.play.deck_missing"),
                ready=False,
            )
        try:
            draft_deck = deck_preset_to_draft_deck(
                preset,
                self.decks_workspace.character_assets,
                self.decks_workspace.weapon_assets,
                player_nickname=player_label,
            )
            report = validate_draft_deck(draft_deck)
        except Exception as exc:
            return PvpDeckStartStatus(
                preset=preset,
                draft_deck=None,
                report=None,
                text=tr("app_shell.pvp.play.deck_error").format(error=str(exc)),
                ready=False,
            )
        codes = tuple(report.issue_codes())
        if report.ready:
            text = tr("app_shell.pvp.play.deck_ready")
        else:
            text = tr("app_shell.pvp.play.deck_invalid").format(
                issues=len(codes),
                codes=_compact_issue_codes(codes),
            )
        return PvpDeckStartStatus(
            preset=preset,
            draft_deck=draft_deck,
            report=report,
            text=text,
            ready=report.ready,
            issue_codes=codes,
        )

    def can_start_local_draft(self, player_1_deck_id: str, player_2_deck_id: str) -> bool:
        return (
            self.deck_start_status(player_1_deck_id, player_label="Player 1").ready
            and self.deck_start_status(player_2_deck_id, player_label="Player 2").ready
        )

    def start_local_draft(self, player_1_deck_id: str, player_2_deck_id: str) -> bool:
        player_1_status = self.deck_start_status(
            player_1_deck_id,
            player_label="Player 1",
        )
        player_2_status = self.deck_start_status(
            player_2_deck_id,
            player_label="Player 2",
        )
        if (
            not player_1_status.ready
            or not player_2_status.ready
            or player_1_status.draft_deck is None
            or player_2_status.draft_deck is None
            or player_1_status.preset is None
            or player_2_status.preset is None
        ):
            self._last_play_status = tr("app_shell.pvp.play.start_blocked")
            self.state_changed.emit()
            return False

        player_1_deck = player_1_status.draft_deck
        player_2_deck = (
            copy_deck_for_player_2(player_1_deck)
            if player_1_deck_id == player_2_deck_id
            else player_2_status.draft_deck
        )
        controller = FreeDraftController.from_decks(
            player_1_deck,
            player_2_deck,
            source_mode="local_hot_seat",
        )
        if not controller.state.setup_ready:
            self._last_play_status = tr("app_shell.pvp.play.start_blocked")
            self.state_changed.emit()
            return False

        self.active_draft_session = PvpActiveDraftSession(
            player_1_deck_id=player_1_status.preset.deck_id,
            player_1_deck_name=player_1_status.preset.name,
            player_2_deck_id=player_2_status.preset.deck_id,
            player_2_deck_name=player_2_status.preset.name,
            controller=controller,
        )
        self._last_play_status = ""
        self._last_draft_status = ""
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.set_page(PVP_PAGE_DRAFT)
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def clear_active_draft(self) -> None:
        if self.active_draft_session is None:
            return
        self.active_draft_session = None
        self._last_draft_status = ""
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()

    def apply_draft_card_click(self, seat: str, character_id: str) -> bool:
        session = self.active_draft_session
        if session is None:
            self._last_draft_status = tr("app_shell.pvp.draft.no_active_title")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        board = session.board_dict()
        if _draft_is_complete(board):
            self._last_draft_status = tr("app_shell.pvp.draft.already_completed")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        if not _is_legal_card(board, seat, character_id):
            self._last_draft_status = tr("app_shell.pvp.draft.illegal_target")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        try:
            action = session.controller.apply_current_action(character_id)
        except FreeDraftControllerActionRejected as exc:
            code = getattr(exc, "code", "") or str(exc)
            self._last_draft_status = tr("app_shell.pvp.draft.action_rejected").format(
                code=code
            )
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False

        self._last_draft_status = tr("app_shell.pvp.draft.action_accepted").format(
            action=_draft_action_label(action.action_type),
            target=character_id,
        )
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def last_play_status(self) -> str:
        return self._last_play_status

    def last_draft_status(self) -> str:
        return self._last_draft_status

    def _on_decks_state_changed(self) -> None:
        self._sync_play_workspace()
        self.state_changed.emit()

    def _sync_play_workspace(self) -> None:
        self.play_workspace.set_active_session(self.active_draft_session)

    def _sync_draft_workspace(self) -> None:
        self.draft_workspace.set_active_session(
            self.active_draft_session,
            status_text=self._last_draft_status,
        )


PVP_DECKS_RIGHT_PANEL_STYLE = f"""
QLineEdit {{
    min-height: 28px;
    padding: 4px 8px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_APP};
    color: {UI_TEXT_PRIMARY};
}}
QComboBox {{
    min-height: 28px;
    padding: 3px 8px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_APP};
    color: {UI_TEXT_PRIMARY};
}}
QComboBox:disabled {{
    color: {UI_TEXT_MUTED};
    background: {UI_BG_BUTTON};
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
QPushButton#pvp_primary_button,
QPushButton#pvp_secondary_button {{
    min-height: 28px;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 800;
}}
QPushButton#pvp_primary_button {{
    border: 1px solid {UI_STATE_SUCCESS};
    background: #24452d;
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#pvp_primary_button:hover {{
    background: #2d5938;
}}
QPushButton#pvp_primary_button:disabled {{
    border-color: #343b49;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
}}
QPushButton#pvp_secondary_button {{
    border: 1px solid {UI_BORDER_DEFAULT};
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_SECONDARY};
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




class PvpPlayRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.player_1_deck_id = ""
        self.player_2_deck_id = ""
        self._refreshing = False
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.mode_label = QLabel()
        self.mode_label.setObjectName("small_muted")
        self.mode_label.setWordWrap(True)
        root.addWidget(self.mode_label)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("small_muted")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.player_1_label = QLabel()
        self.player_1_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.player_1_label)
        self.player_1_combo = QComboBox()
        self.player_1_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_1_combo)
        self.player_1_status_label = QLabel()
        self.player_1_status_label.setObjectName("small_muted")
        self.player_1_status_label.setWordWrap(True)
        root.addWidget(self.player_1_status_label)

        self.player_2_label = QLabel()
        self.player_2_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.player_2_label)
        self.player_2_combo = QComboBox()
        self.player_2_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_2_combo)
        self.player_2_status_label = QLabel()
        self.player_2_status_label.setObjectName("small_muted")
        self.player_2_status_label.setWordWrap(True)
        root.addWidget(self.player_2_status_label)

        self.start_button = QPushButton()
        self.start_button.setObjectName("pvp_primary_button")
        self.start_button.clicked.connect(self._on_start_clicked)
        root.addWidget(self.start_button)

        self.active_frame = QFrame()
        self.active_frame.setObjectName("pvp_deck_expanded_info")
        active_layout = QVBoxLayout(self.active_frame)
        active_layout.setContentsMargins(8, 8, 8, 8)
        active_layout.setSpacing(4)
        self.active_title_label = QLabel()
        self.active_title_label.setObjectName("pvp_deck_info_line")
        active_layout.addWidget(self.active_title_label)
        self.active_summary_labels: list[QLabel] = []
        for _index in range(7):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            active_layout.addWidget(label)
            self.active_summary_labels.append(label)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("pvp_secondary_button")
        self.clear_button.clicked.connect(self.workspace.clear_active_draft)
        active_layout.addWidget(self.clear_button)
        root.addWidget(self.active_frame)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        self.workspace.state_changed.connect(self.refresh)
        self.workspace.active_draft_changed.connect(self.refresh)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            options = self.workspace.play_deck_options()
            option_ids = {preset.deck_id for preset in options}
            if self.player_1_deck_id not in option_ids:
                self.player_1_deck_id = self.workspace.default_player_1_deck_id()
            if self.player_2_deck_id not in option_ids:
                self.player_2_deck_id = self.workspace.default_player_2_deck_id(
                    self.player_1_deck_id
                )
            self.player_1_deck_id = self._sync_combo(
                self.player_1_combo,
                self.player_1_deck_id,
                options,
            )
            self.player_2_deck_id = self._sync_combo(
                self.player_2_combo,
                self.player_2_deck_id,
                options,
            )

            has_decks = bool(options)
            for widget in (
                self.player_1_label,
                self.player_1_combo,
                self.player_1_status_label,
                self.player_2_label,
                self.player_2_combo,
                self.player_2_status_label,
                self.start_button,
            ):
                widget.setVisible(True)
                widget.setEnabled(has_decks)
            self.empty_label.setVisible(not has_decks)
            if not has_decks:
                self.start_button.setEnabled(False)
                self.player_1_status_label.setText("")
                self.player_2_status_label.setText("")
            else:
                player_1_status = self.workspace.deck_start_status(
                    self.player_1_deck_id,
                    player_label="Player 1",
                )
                player_2_status = self.workspace.deck_start_status(
                    self.player_2_deck_id,
                    player_label="Player 2",
                )
                self.player_1_status_label.setText(player_1_status.text)
                self.player_2_status_label.setText(player_2_status.text)
                self.start_button.setEnabled(
                    player_1_status.ready and player_2_status.ready
                )
            self._refresh_active_summary()
            status = self.workspace.last_play_status()
            self.status_label.setText(status)
            self.status_label.setVisible(bool(status))
        finally:
            self._refreshing = False

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.play.title"))
        self.mode_label.setText(tr("app_shell.pvp.play.mode_local_hotseat"))
        self.empty_label.setText(tr("app_shell.pvp.play.no_decks"))
        self.player_1_label.setText(tr("app_shell.pvp.play.player_1_deck"))
        self.player_2_label.setText(tr("app_shell.pvp.play.player_2_deck"))
        self.start_button.setText(tr("app_shell.pvp.play.start_local_draft"))
        self.active_title_label.setText(tr("app_shell.pvp.play.active_local_draft"))
        self.clear_button.setText(tr("app_shell.pvp.play.clear_active_draft"))
        self.refresh()

    def _sync_combo(
        self,
        combo: QComboBox,
        selected_id: str,
        options: tuple[PvpDeckPreset, ...],
    ) -> str:
        combo.blockSignals(True)
        try:
            combo.clear()
            for preset in options:
                combo.addItem(preset.name, preset.deck_id)
            if not options:
                return ""
            index = combo.findData(selected_id)
            if index < 0:
                index = 0
            combo.setCurrentIndex(index)
            return _text(combo.currentData())
        finally:
            combo.blockSignals(False)

    def _on_selection_changed(self) -> None:
        if self._refreshing:
            return
        self.player_1_deck_id = _text(self.player_1_combo.currentData())
        self.player_2_deck_id = _text(self.player_2_combo.currentData())
        self.refresh()

    def _on_start_clicked(self) -> None:
        if self.workspace.start_local_draft(
            self.player_1_deck_id,
            self.player_2_deck_id,
        ):
            self.refresh()

    def _refresh_active_summary(self) -> None:
        session = self.workspace.active_draft_session
        self.active_frame.setVisible(session is not None)
        lines = _active_draft_summary_lines(session) if session is not None else []
        for index, label in enumerate(self.active_summary_labels):
            text = lines[index] if index < len(lines) else ""
            label.setText(text)
            label.setVisible(bool(text))


class PvpDraftRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("small_muted")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.status_frame = QFrame()
        self.status_frame.setObjectName("pvp_deck_expanded_info")
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setContentsMargins(8, 8, 8, 8)
        status_layout.setSpacing(5)
        self.status_labels: list[QLabel] = []
        for _index in range(5):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            status_layout.addWidget(label)
            self.status_labels.append(label)
        root.addWidget(self.status_frame)

        self.log_title_label = QLabel()
        self.log_title_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.log_title_label)

        self.log_labels: list[QLabel] = []
        for _index in range(8):
            label = QLabel()
            label.setObjectName("small_muted")
            label.setWordWrap(True)
            root.addWidget(label)
            self.log_labels.append(label)

        self.clear_button = QPushButton()
        self.clear_button.setObjectName("pvp_secondary_button")
        self.clear_button.clicked.connect(self.workspace.clear_active_draft)
        root.addWidget(self.clear_button)

        self.play_button = QPushButton()
        self.play_button.setObjectName("pvp_secondary_button")
        self.play_button.clicked.connect(lambda: self.workspace.set_page(PVP_PAGE_PLAY))
        root.addWidget(self.play_button)

        self.message_label = QLabel()
        self.message_label.setObjectName("small_muted")
        self.message_label.setWordWrap(True)
        root.addWidget(self.message_label)
        root.addStretch(1)

        self.workspace.state_changed.connect(self.refresh)
        self.workspace.active_draft_changed.connect(self.refresh)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        session = self.workspace.active_draft_session
        has_session = session is not None
        self.empty_label.setVisible(not has_session)
        self.status_frame.setVisible(has_session)
        self.log_title_label.setVisible(has_session)
        self.clear_button.setVisible(has_session)
        self.clear_button.setEnabled(has_session)
        self.play_button.setVisible(True)
        self.message_label.setText(self.workspace.last_draft_status())
        self.message_label.setVisible(bool(self.message_label.text()))

        if session is None:
            for label in (*self.status_labels, *self.log_labels):
                label.clear()
                label.setVisible(False)
            return

        board = session.board_dict()
        status_lines = _draft_panel_status_lines(board)
        for index, label in enumerate(self.status_labels):
            text = status_lines[index] if index < len(status_lines) else ""
            label.setText(text)
            label.setVisible(bool(text))

        log_lines = _draft_action_log_lines(board, limit=len(self.log_labels))
        for index, label in enumerate(self.log_labels):
            text = log_lines[index] if index < len(log_lines) else ""
            label.setText(text)
            label.setVisible(bool(text))

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self.log_title_label.setText(tr("app_shell.pvp.draft.action_log_title"))
        self.clear_button.setText(tr("app_shell.pvp.draft.abandon"))
        self.play_button.setText(tr("app_shell.pvp.draft.back_to_play"))
        self.refresh()


class PvpRightPanelHost(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.decks_panel = PvpDecksRightPanel(workspace.decks_workspace)
        self.play_panel = PvpPlayRightPanel(workspace)
        self.draft_panel = PvpDraftRightPanel(workspace)
        self.stack.addWidget(self.decks_panel)
        self.stack.addWidget(self.play_panel)
        self.stack.addWidget(self.draft_panel)
        self.workspace.page_changed.connect(self._sync_page_from_workspace)
        self.set_page(workspace.active_page_id)

    def set_page(self, page_id: str) -> None:
        self.workspace.set_page(page_id)
        self._sync_page_from_workspace(self.workspace.active_page_id)

    def current_page(self) -> str:
        return self.workspace.active_page_id

    def retranslate_ui(self) -> None:
        self.decks_panel.retranslate_ui()
        self.play_panel.retranslate_ui()
        self.draft_panel.retranslate_ui()

    def _sync_page_from_workspace(self, page_id: str) -> None:
        if page_id == PVP_PAGE_PLAY:
            widget = self.play_panel
        elif page_id == PVP_PAGE_DRAFT:
            widget = self.draft_panel
        else:
            widget = self.decks_panel
        self.stack.setCurrentWidget(widget)


def _active_draft_summary_lines(
    session: PvpActiveDraftSession,
) -> list[str]:
    board = session.board_dict()
    draft_system = _mapping(board.get("draft_system"))
    requirement = board.get("current_requirement")
    requirement_text = _format_requirement(requirement if isinstance(requirement, Mapping) else None)
    progress = _mapping(board.get("progress"))
    action_log = board.get("action_log")
    action_log_count = len(action_log) if isinstance(action_log, list) else 0
    return [
        tr("app_shell.pvp.play.summary_p1").format(name=session.player_1_deck_name),
        tr("app_shell.pvp.play.summary_p2").format(name=session.player_2_deck_name),
        tr("app_shell.pvp.play.summary_system").format(
            system_id=_text(draft_system.get("system_id")),
        ),
        tr("app_shell.pvp.play.summary_requirement").format(
            requirement=requirement_text,
        ),
        tr("app_shell.pvp.play.summary_legal_targets").format(
            count=int(progress.get("legal_target_count") or 0),
        ),
        tr("app_shell.pvp.play.summary_action_log").format(
            count=action_log_count,
        ),
        tr("app_shell.pvp.play.summary_open_draft"),
    ]


def _draft_is_complete(board: Mapping[str, Any]) -> bool:
    status = _mapping(board.get("status"))
    return bool(status.get("draft_finished")) or board.get("current_requirement") is None


def _draft_action_title(board: Mapping[str, Any]) -> str:
    if _draft_is_complete(board):
        return tr("app_shell.pvp.draft.completed_title")
    requirement = _mapping(board.get("current_requirement"))
    return tr("app_shell.pvp.draft.current_action").format(
        seat=_seat_label(_text(requirement.get("active_seat"))),
        action=_draft_action_label(_text(requirement.get("expected_action_type"))),
    )


def _draft_action_detail(board: Mapping[str, Any]) -> str:
    progress = _mapping(board.get("progress"))
    action_log = board.get("action_log")
    action_log_count = len(action_log) if isinstance(action_log, list) else 0
    return tr("app_shell.pvp.draft.progress_line").format(
        step=int(progress.get("current_step_number") or 0),
        total=int(progress.get("schedule_steps_total") or 0),
        legal=int(progress.get("legal_target_count") or 0),
        actions=int(progress.get("actions_accepted") or action_log_count),
        actions_total=int(progress.get("actions_total_expected") or 0),
    )


def _draft_panel_status_lines(board: Mapping[str, Any]) -> list[str]:
    draft_system = _mapping(board.get("draft_system"))
    progress = _mapping(board.get("progress"))
    requirement = _mapping(board.get("current_requirement"))
    if _draft_is_complete(board):
        requirement_text = tr("app_shell.pvp.draft.completed_title")
    else:
        requirement_text = _format_requirement(requirement)
    return [
        tr("app_shell.pvp.play.summary_system").format(
            system_id=_text(draft_system.get("system_id")),
        ),
        tr("app_shell.pvp.play.summary_requirement").format(
            requirement=requirement_text,
        ),
        tr("app_shell.pvp.play.summary_legal_targets").format(
            count=int(progress.get("legal_target_count") or 0),
        ),
        tr("app_shell.pvp.draft.accepted_actions").format(
            count=int(progress.get("actions_accepted") or 0),
            total=int(progress.get("actions_total_expected") or 0),
        ),
        tr("app_shell.pvp.draft.status").format(
            status=(
                tr("app_shell.pvp.draft.completed")
                if _draft_is_complete(board)
                else tr("app_shell.pvp.draft.in_progress")
            ),
        ),
    ]


def _draft_action_log_lines(
    board: Mapping[str, Any],
    *,
    limit: int,
) -> list[str]:
    action_log = board.get("action_log")
    if not isinstance(action_log, list) or not action_log:
        return [tr("app_shell.pvp.draft.action_log_empty")]
    rows = action_log[-limit:]
    return [
        tr("app_shell.pvp.draft.action_log_row").format(
            index=int(_mapping(row).get("sequence") or _mapping(row).get("index") or 0),
            seat=_seat_label(_text(_mapping(row).get("seat"))),
            action=_draft_action_label(_text(_mapping(row).get("action_type"))),
            target=_text(_mapping(row).get("target_display_name"))
            or _text(_mapping(row).get("target_id")),
        )
        for row in rows
    ]


def _completed_draft_lines(board: Mapping[str, Any]) -> list[str]:
    action_log = board.get("action_log")
    rows = [_mapping(row) for row in action_log] if isinstance(action_log, list) else []
    return [
        tr("app_shell.pvp.draft.final_picks").format(
            seat=_seat_label("player_1"),
            items=_joined_action_targets(rows, seat="player_1", action_type="pick_character"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_1"),
            items=_joined_action_targets(rows, seat="player_1", action_type="ban_character"),
        ),
        tr("app_shell.pvp.draft.final_picks").format(
            seat=_seat_label("player_2"),
            items=_joined_action_targets(rows, seat="player_2", action_type="pick_character"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_2"),
            items=_joined_action_targets(rows, seat="player_2", action_type="ban_character"),
        ),
        tr("app_shell.pvp.play.summary_action_log").format(count=len(rows)),
    ]


def _joined_action_targets(
    rows: list[dict[str, Any]],
    *,
    seat: str,
    action_type: str,
) -> str:
    values = [
        _text(row.get("target_display_name")) or _text(row.get("target_id"))
        for row in rows
        if row.get("seat") == seat and row.get("action_type") == action_type
    ]
    return ", ".join(values) if values else tr("app_shell.pvp.draft.none")


def _is_legal_card(board: Mapping[str, Any], seat: str, character_id: str) -> bool:
    seats = _mapping(board.get("seats"))
    seat_board = _mapping(seats.get(seat))
    cards = seat_board.get("cards")
    if not isinstance(cards, list):
        return False
    for card_value in cards:
        card = _mapping(card_value)
        if _text(card.get("character_id")) == character_id:
            return bool(card.get("is_current_legal_target"))
    return False


def _draft_card_text(card: Mapping[str, Any]) -> str:
    name = _text(card.get("display_name")) or _text(card.get("character_id"))
    meta = " ".join(
        part
        for part in (
            _text(card.get("element")),
            _text(card.get("weapon_type")),
            _level_text(card.get("level")),
            _constellation_text(card.get("constellation")),
        )
        if part
    )
    status = _draft_card_status_label(_text(card.get("status")))
    return "\n".join(part for part in (name, meta, status) if part)


def _seat_title(seat: str, seat_board: Mapping[str, Any]) -> str:
    deck = _mapping(seat_board.get("deck"))
    nickname = _text(seat_board.get("nickname"))
    deck_name = _text(deck.get("deck_name"))
    return tr("app_shell.pvp.draft.seat_title").format(
        seat=_seat_label(seat),
        nickname=nickname or _seat_label(seat),
        deck=deck_name,
    )


def _seat_is_active(seat_board: Mapping[str, Any]) -> bool:
    cards = seat_board.get("cards")
    if not isinstance(cards, list):
        return False
    return any(bool(_mapping(card).get("is_active_seat_card")) for card in cards)


def _seat_label(seat: str) -> str:
    if seat == "player_1":
        return tr("app_shell.pvp.draft.player_1")
    if seat == "player_2":
        return tr("app_shell.pvp.draft.player_2")
    return seat


def _draft_action_label(action_type: str) -> str:
    if action_type == "pick_character":
        return tr("app_shell.pvp.draft.pick")
    if action_type == "ban_character":
        return tr("app_shell.pvp.draft.ban")
    return action_type


def _draft_card_status_label(status: str) -> str:
    labels = {
        "available": tr("app_shell.pvp.draft.available"),
        "legal_target": tr("app_shell.pvp.draft.legal_target"),
        "globally_banned": tr("app_shell.pvp.draft.banned"),
        "picked_by_self": tr("app_shell.pvp.draft.picked"),
        "picked_by_opponent": tr("app_shell.pvp.draft.picked"),
        "blocked_by_opponent_pick": tr("app_shell.pvp.draft.blocked"),
        "unavailable": tr("app_shell.pvp.draft.unavailable"),
        "invalid": tr("app_shell.pvp.draft.invalid"),
        "unsupported_traveler": tr("app_shell.pvp.draft.invalid"),
    }
    return labels.get(status, status)


def _level_text(value: Any) -> str:
    level = int(value or 0)
    return f"Lv.{level}" if level else ""


def _constellation_text(value: Any) -> str:
    constellation = int(value or 0)
    return f"C{constellation}" if constellation else "C0"


def _format_requirement(requirement: Mapping[str, Any] | None) -> str:
    if not requirement:
        return tr("app_shell.pvp.play.requirement_none")
    parts = [
        _text(requirement.get("phase")),
        _text(requirement.get("active_seat")),
        _text(requirement.get("expected_action_type")),
    ]
    return " / ".join(part for part in parts if part)


def _compact_issue_codes(codes: tuple[str, ...]) -> str:
    if not codes:
        return ""
    visible = ", ".join(codes[:4])
    if len(codes) > 4:
        visible += ", ..."
    return f": {visible}"


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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _refresh_qss(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


__all__ = [
    "PVP_PAGE_DECKS",
    "PVP_PAGE_DRAFT",
    "PVP_PAGE_PLAY",
    "PvpActiveDraftSession",
    "PvpDraftCardButton",
    "PvpDraftRightPanel",
    "PvpDraftWorkspace",
    "PvpDeckAssetIconLabel",
    "PvpDecksRightPanel",
    "PvpDecksWorkspace",
    "PvpPlayRightPanel",
    "PvpPlayWorkspace",
    "PvpRightPanelHost",
    "PvpWorkspace",
]
