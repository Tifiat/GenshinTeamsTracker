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
from run_workspace.pvp.match_result import ChamberTimer, PlayerMatchTimers
from run_workspace.pvp.session import (
    CharacterWeaponAssignment,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    validate_team_assignment,
    validate_weapon_assignment,
)
from run_workspace.pvp.validation import DeckValidationReport, validate_draft_deck
from run_workspace.pvp.weapon_identity import weapon_observed_stack_key
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
    PixelIconGridItem,
    PixelIconGridMetrics,
    PixelIconGridOutline,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.right_panel.pvp._shared import *
from ui.utils.ui_palette import (
    UI_ACCENT_TEAM_1,
    UI_ACCENT_TEAM_2,
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
PVP_DRAFT_STAGE_DRAFT = "draft"
PVP_DRAFT_STAGE_ASSIGNMENT = "assignment"
PVP_DRAFT_STAGE_WEAPONS = "weapons"
PVP_DRAFT_STAGE_TIMERS_RESULTS = "timers_results"
PVP_DRAFT_STAGE_COMPLETED_RESULT = "completed_result"
PVP_DRAFT_STAGE_VALUES = (
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
)
PVP_SEATS = ("player_1", "player_2")
PVP_TIMER_CHAMBERS = ("1", "2", "3")
PVP_BROWSER_PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
QFrame#pvp_draft_pool_frame,
QFrame#pvp_draft_result_zone,
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
QFrame#pvp_draft_pool_frame[active="true"] {{
    border-color: {UI_STATE_SUCCESS};
    background: #18291f;
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
    min-width: 136px;
    max-width: 136px;
    min-height: 88px;
    max-height: 88px;
    padding: 6px;
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
QPushButton#pvp_draft_card[ownerP1="true"] {{
    border-left: 4px solid {UI_ACCENT_TEAM_1};
}}
QPushButton#pvp_draft_card[ownerP2="true"] {{
    border-right: 4px solid {UI_ACCENT_TEAM_2};
}}
QPushButton#pvp_draft_card[sharedOwner="true"] {{
    border-color: #d6b35f;
    background: #2d2d28;
}}
QPushButton#pvp_draft_card[status="blocked"],
QPushButton#pvp_draft_card[status="invalid"] {{
    border-color: #69512d;
    background: #352a1d;
    color: {UI_TEXT_SECONDARY};
}}
QPushButton#pvp_draft_card:disabled {{
    color: {UI_TEXT_MUTED};
}}
QLabel#pvp_draft_pool_empty {{
    color: {UI_TEXT_MUTED};
    padding: 10px;
    font-size: 12px;
}}
QLabel#pvp_draft_result_title {{
    color: {UI_TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 800;
}}
QLabel#pvp_draft_result_picks {{
    color: {UI_TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#pvp_draft_result_bans {{
    color: {UI_TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 600;
}}
QFrame#pvp_postdraft_source_frame,
QFrame#pvp-postdraft-source-player-1,
QFrame#pvp-postdraft-source-player-2 {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL};
}}
QFrame#pvp-postdraft-source-player-1 {{
    border-left: 4px solid {UI_ACCENT_TEAM_1};
}}
QFrame#pvp-postdraft-source-player-2 {{
    border-left: 4px solid {UI_ACCENT_TEAM_2};
}}
QWidget#pvp-postdraft-source-grid-wrap,
QWidget#pvp-postdraft-source-grid-content,
QWidget#pvp-postdraft-source-grid-viewport {{
    background: transparent;
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


class PvpDraftUnifiedCardButton(QPushButton):
    card_clicked = Signal(dict)

    def __init__(
        self,
        *,
        entry: Mapping[str, Any],
        draft_complete: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.character_id = _text(entry.get("character_id"))
        self.owner_seats = tuple(_owner_seats(entry))
        status = _text(entry.get("status")) or "available"
        zone = _text(entry.get("zone")) or "pool"
        action = entry.get("action")
        self.action_payload = dict(action) if isinstance(action, Mapping) else {}
        legal = (
            bool(entry.get("is_current_legal_target"))
            and bool(self.action_payload)
            and not draft_complete
        )
        self.setObjectName("pvp_draft_card")
        self.setProperty("characterId", self.character_id)
        self.setProperty("status", status)
        self.setProperty("zone", zone)
        self.setProperty("legalTarget", legal)
        self.setProperty("ownerP1", "player_1" in self.owner_seats)
        self.setProperty("ownerP2", "player_2" in self.owner_seats)
        self.setProperty("sharedOwner", len(self.owner_seats) > 1)
        self.setText(_draft_unified_card_text(entry))
        self.setEnabled(legal)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if legal
            else Qt.CursorShape.ArrowCursor
        )
        self.clicked.connect(
            lambda _checked=False: self.card_clicked.emit(dict(self.action_payload))
        )
        _refresh_qss(self)


class PvpPostDraftGridItemHandle:
    def __init__(self, grid: PixelIconGrid, item_id: str) -> None:
        self.grid = grid
        self.item_id = item_id

    def click(self) -> bool:
        return self.grid.click_item_for_test(self.item_id)

    def isEnabled(self) -> bool:  # noqa: N802 - Qt-style test compatibility
        item = self.grid.item(self.item_id)
        return bool(item and item.enabled)

    def property(self, name: str) -> Any:  # noqa: A003, N802 - Qt-style compatibility
        return self.grid.item_property(self.item_id, name)




class PvpDraftWorkspace(QWidget):
    card_clicked = Signal(dict)
    assignment_character_clicked = Signal(str, str)
    assignment_slot_clicked = Signal(str, int, int)
    assignment_slot_clear_clicked = Signal(str, int, int)
    weapon_character_clicked = Signal(str, str)
    weapon_stack_clicked = Signal(str, str, str)
    weapon_clear_clicked = Signal(str, str)
    timer_text_changed = Signal(str, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PvpDraftWorkspace")
        self.setStyleSheet(PVP_DRAFT_WORKSPACE_STYLE)
        self._active_session: PvpActiveDraftSession | None = None
        self._status_text = ""
        self._view_state: Mapping[str, Any] = {}
        self._character_assets_by_id: dict[str, dict[str, Any]] = {}
        self._weapon_assets_by_stack_key: dict[str, dict[str, Any]] = {}
        self.card_buttons_by_character_id: dict[str, PvpDraftUnifiedCardButton] = {}
        self.card_buttons_by_key = self.card_buttons_by_character_id
        self.legal_card_buttons: list[PvpDraftUnifiedCardButton] = []
        self.assignment_character_buttons_by_key: dict[tuple[str, str], PvpPostDraftGridItemHandle] = {}
        self.assignment_slot_buttons_by_key: dict[tuple[str, int, int], QPushButton] = {}
        self.weapon_character_buttons_by_key: dict[tuple[str, str], QPushButton] = {}
        self.weapon_stack_buttons_by_key: dict[tuple[str, str], PvpPostDraftGridItemHandle] = {}
        self.source_zone_frames_by_seat: dict[str, QFrame] = {}
        self.source_character_grids_by_seat: dict[str, PixelIconGrid] = {}
        self.source_weapon_grids_by_seat: dict[str, PixelIconGrid] = {}
        self.timer_inputs_by_key: dict[tuple[str, int], QLineEdit] = {}
        self.timer_total_labels_by_seat: dict[str, QLabel] = {}

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
        view_state: Mapping[str, Any] | None = None,
        character_assets: Iterable[dict[str, Any]] = (),
        weapon_assets: Iterable[dict[str, Any]] = (),
    ) -> None:
        self._active_session = session
        self._status_text = status_text
        self._view_state = dict(view_state or {})
        self._character_assets_by_id = _character_assets_by_id(character_assets)
        self._weapon_assets_by_stack_key = _weapon_assets_by_stack_key(weapon_assets)
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
        self.assignment_character_buttons_by_key.clear()
        self.assignment_slot_buttons_by_key.clear()
        self.weapon_character_buttons_by_key.clear()
        self.weapon_stack_buttons_by_key.clear()
        self.source_zone_frames_by_seat.clear()
        self.source_character_grids_by_seat.clear()
        self.source_weapon_grids_by_seat.clear()
        self.timer_inputs_by_key.clear()
        self.timer_total_labels_by_seat.clear()
        _clear_layout(self.scroll_layout)

        if session is None:
            self.board_frame.setProperty("complete", False)
            _refresh_qss(self.board_frame)
            self._refresh_completed(None)
            return

        board = session.board_dict()
        complete = _draft_is_complete(board)
        stage = _draft_stage(self._view_state)
        self.board_frame.setProperty("complete", complete)
        _refresh_qss(self.board_frame)
        self.action_title_label.setText(_draft_stage_title(board, stage))
        self.action_detail_label.setText(_draft_stage_detail(board, stage, self._view_state))

        if stage in {
            PVP_DRAFT_STAGE_ASSIGNMENT,
            PVP_DRAFT_STAGE_WEAPONS,
            PVP_DRAFT_STAGE_TIMERS_RESULTS,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        }:
            self.scroll_layout.addWidget(self._build_post_draft_source_stage(board, stage))
        else:
            self.scroll_layout.addWidget(self._build_unified_pool(board, complete))
        self.scroll_layout.addStretch(1)
        self._refresh_completed(board if stage == PVP_DRAFT_STAGE_DRAFT else None)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_title_label.setText(tr("app_shell.pvp.draft.no_active_title"))
        self.empty_body_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self.completed_title_label.setText(tr("app_shell.pvp.draft.completed_title"))
        self.refresh()

    def _build_unified_pool(
        self,
        board: Mapping[str, Any],
        draft_complete: bool,
    ) -> QFrame:
        pool_frame = QFrame()
        pool_frame.setObjectName("pvp_draft_pool_frame")
        pool_frame.setProperty("active", not draft_complete)
        _refresh_qss(pool_frame)
        layout = QVBoxLayout(pool_frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        title = QLabel(tr("app_shell.pvp.draft.unified_pool_title"))
        title.setObjectName("pvp_deck_info_line")
        layout.addWidget(title)

        entries = _draft_main_pool_entries(board)
        info = QLabel(_draft_unified_pool_summary(board, entries))
        info.setObjectName("small_muted")
        info.setWordWrap(True)
        layout.addWidget(info)

        if not entries:
            empty = QLabel(tr("app_shell.pvp.draft.pool_empty"))
            empty.setObjectName("pvp_draft_pool_empty")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return pool_frame

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(6)
        grid_layout.setVerticalSpacing(6)
        columns = 5
        for index, entry_value in enumerate(entries):
            entry = _mapping(entry_value)
            button = PvpDraftUnifiedCardButton(
                entry=entry,
                draft_complete=draft_complete,
            )
            button.card_clicked.connect(self.card_clicked.emit)
            self.card_buttons_by_character_id[button.character_id] = button
            if button.property("legalTarget"):
                self.legal_card_buttons.append(button)
            grid_layout.addWidget(button, index // columns, index % columns)
        layout.addWidget(grid_widget)
        return pool_frame

    def _build_post_draft_source_stage(
        self,
        board: Mapping[str, Any],
        stage: str,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pvp_postdraft_source_frame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        session = self._active_session

        for seat in PVP_SEATS:
            section = QFrame()
            section.setObjectName(_postdraft_source_object_name(seat))
            section.setProperty("seat", seat)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(8, 8, 8, 8)
            section_layout.setSpacing(6)
            self.source_zone_frames_by_seat[seat] = section

            title = QLabel(
                tr("app_shell.pvp.post.source_zone_title").format(
                    seat=_seat_label(seat),
                )
            )
            title.setObjectName("pvp_draft_result_title")
            section_layout.addWidget(title)

            weapon_title = QLabel(tr("app_shell.pvp.post.source_weapons"))
            weapon_title.setObjectName("pvp_deck_info_line")
            section_layout.addWidget(weapon_title)
            if session is not None:
                weapon_grid = self._build_source_weapon_grid(session, seat, stage)
                section_layout.addWidget(
                    _postdraft_grid_scroll_area(
                        weapon_grid,
                        object_name="pvp-postdraft-source-weapon-scroll",
                        maximum_height=118,
                    )
                )

            picks_title = QLabel(tr("app_shell.pvp.post.source_picks"))
            picks_title.setObjectName("pvp_deck_info_line")
            section_layout.addWidget(picks_title)
            character_grid = self._build_source_character_grid(board, seat, stage)
            section_layout.addWidget(
                _postdraft_grid_scroll_area(
                    character_grid,
                    object_name="pvp-postdraft-source-character-scroll",
                    maximum_height=88,
                )
            )
            layout.addWidget(section, 1)
        return frame

    def _build_source_character_grid(
        self,
        board: Mapping[str, Any],
        seat: str,
        stage: str,
    ) -> PixelIconGrid:
        assets: list[dict[str, Any]] = []
        assigned_ids = set(_assigned_character_ids(self._view_state, seat))
        selected = _selected_assignment_character(self._view_state)
        for character_id in _picked_character_ids(board, seat):
            asset = dict(self._character_assets_by_id.get(character_id) or {})
            image_path = _asset_image_path(asset)
            name = _entry_display_name_for_id(board, character_id)
            asset.update(
                {
                    "path": image_path,
                    "filename": name,
                    "tooltip": _postdraft_character_tooltip(
                        name,
                        assigned=character_id in assigned_ids,
                    ),
                    "grid_id": character_id,
                    "seat": seat,
                    "character_id": character_id,
                    "assigned": character_id in assigned_ids,
                    "selected": selected == (seat, character_id),
                    "enabled": (
                        stage == PVP_DRAFT_STAGE_ASSIGNMENT
                        and character_id not in assigned_ids
                    ),
                    "has_image": bool(image_path),
                }
            )
            assets.append(asset)
        result = build_asset_grid_items(
            assets,
            key_for_asset=lambda asset: _text(asset.get("grid_id")),
            outline_for_asset=lambda asset, _item_id: (
                PixelIconGridOutline(
                    color=UI_STATE_SUCCESS,
                    width=2,
                    radius=6,
                    overhang=1,
                    badge_text="SEL",
                )
                if bool(asset.get("selected"))
                else None
            ),
            overlay_fill_for_asset=lambda asset, _item_id: (
                PixelIconGridFill(UI_BG_BUTTON, alpha=150)
                if bool(asset.get("assigned")) or not bool(asset.get("enabled"))
                else None
            ),
            properties_for_asset=lambda asset, _item_id: {
                "seat": _text(asset.get("seat")),
                "characterId": _text(asset.get("character_id")),
                "assigned": bool(asset.get("assigned")),
                "selected": bool(asset.get("selected")),
                "hasImage": bool(asset.get("has_image")),
            },
        )
        items = tuple(
            PixelIconGridItem(
                item_id=item.item_id,
                icon_path=item.icon_path,
                label=item.label,
                tooltip=item.tooltip,
                enabled=bool(result.assets_by_id[item.item_id].get("enabled")),
                outline=item.outline,
                overlay_fill=item.overlay_fill,
                overlay_icons=item.overlay_icons,
                properties=item.properties,
                pixmap_cache_key_parts=("pvp_postdraft_character", seat),
            )
            for item in result.items
        )
        grid = PixelIconGrid(
            metrics=PixelIconGridMetrics(
                item_width=56,
                item_height=62,
                gap_x=6,
                gap_y=6,
                margin_top=2,
                margin_bottom=2,
            ),
            surface="pvp_postdraft_source_character",
        )
        grid.setObjectName("pvp-postdraft-source-character-grid")
        grid.setProperty("seat", seat)
        grid.setProperty("kind", "characters")
        grid.set_items(items)
        grid.item_clicked.connect(
            lambda item_id, s=seat: self.assignment_character_clicked.emit(s, item_id)
        )
        self.source_character_grids_by_seat[seat] = grid
        for item_id in grid.item_ids():
            self.assignment_character_buttons_by_key[(seat, item_id)] = (
                PvpPostDraftGridItemHandle(grid, item_id)
            )
        return grid

    def _build_source_weapon_grid(
        self,
        session: PvpActiveDraftSession,
        seat: str,
        stage: str,
    ) -> PixelIconGrid:
        selected = _selected_weapon_character(self._view_state)
        selected_character_id = selected[1] if selected and selected[0] == seat else ""
        assets: list[dict[str, Any]] = []
        for stack in session.controller.session_state.deck_for(seat).weapons:
            remaining = _weapon_stack_remaining(
                session,
                self._view_state,
                seat,
                stack.stack_key,
                selected_character_id=selected_character_id,
            )
            compatible = bool(
                selected_character_id
                and _weapon_stack_is_assignable(
                    session,
                    self._view_state,
                    seat,
                    selected_character_id,
                    stack.stack_key,
                )
            )
            exhausted = remaining <= 0
            asset = dict(self._weapon_assets_by_stack_key.get(stack.stack_key) or {})
            image_path = _asset_image_path(asset)
            label = tr("app_shell.pvp.post.weapon_tile_text").format(
                weapon=stack.display_name,
                count=remaining,
            )
            asset.update(
                {
                    "path": image_path,
                    "filename": stack.display_name,
                    "tooltip": label,
                    "grid_id": stack.stack_key,
                    "seat": seat,
                    "stack_key": stack.stack_key,
                    "remaining": remaining,
                    "compatible": compatible,
                    "exhausted": exhausted,
                    "enabled": bool(
                        stage == PVP_DRAFT_STAGE_WEAPONS
                        and selected_character_id
                        and compatible
                        and not exhausted
                    ),
                    "has_image": bool(image_path),
                }
            )
            assets.append(asset)
        result = build_asset_grid_items(
            assets,
            key_for_asset=lambda asset: _text(asset.get("grid_id")),
            outline_for_asset=lambda asset, _item_id: (
                PixelIconGridOutline(
                    color=UI_STATE_SUCCESS,
                    width=2,
                    radius=6,
                    overhang=1,
                    badge_text=str(asset.get("remaining") or ""),
                )
                if bool(asset.get("compatible")) and not bool(asset.get("exhausted"))
                else None
            ),
            overlay_fill_for_asset=lambda asset, _item_id: (
                PixelIconGridFill(UI_BG_BUTTON, alpha=155)
                if bool(asset.get("exhausted")) or not bool(asset.get("enabled"))
                else None
            ),
            properties_for_asset=lambda asset, _item_id: {
                "seat": _text(asset.get("seat")),
                "stackKey": _text(asset.get("stack_key")),
                "remaining": int(asset.get("remaining") or 0),
                "compatible": bool(asset.get("compatible")),
                "exhausted": bool(asset.get("exhausted")),
                "hasImage": bool(asset.get("has_image")),
            },
        )
        items = tuple(
            PixelIconGridItem(
                item_id=item.item_id,
                icon_path=item.icon_path,
                label=item.label,
                tooltip=item.tooltip,
                enabled=bool(result.assets_by_id[item.item_id].get("enabled")),
                outline=item.outline,
                overlay_fill=item.overlay_fill,
                overlay_icons=item.overlay_icons,
                properties=item.properties,
                pixmap_cache_key_parts=("pvp_postdraft_weapon", seat),
            )
            for item in result.items
        )
        grid = PixelIconGrid(
            metrics=PixelIconGridMetrics(
                item_width=50,
                item_height=54,
                gap_x=6,
                gap_y=6,
                margin_top=2,
                margin_bottom=2,
            ),
            surface="pvp_postdraft_source_weapon",
        )
        grid.setObjectName("pvp-postdraft-source-weapon-grid")
        grid.setProperty("seat", seat)
        grid.setProperty("kind", "weapons")
        grid.set_items(items)
        grid.item_clicked.connect(
            lambda item_id, s=seat, c=selected_character_id: (
                self.weapon_stack_clicked.emit(s, c, item_id)
            )
        )
        self.source_weapon_grids_by_seat[seat] = grid
        for item_id in grid.item_ids():
            self.weapon_stack_buttons_by_key[(seat, item_id)] = (
                PvpPostDraftGridItemHandle(grid, item_id)
            )
        return grid

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
        self.draft_stage = PVP_DRAFT_STAGE_DRAFT
        self.assignment_slots_by_seat = _empty_assignment_slots_by_seat()
        self.selected_assignment_character: tuple[str, str] | None = None
        self.weapon_assignments_by_seat: dict[str, dict[str, str]] = {
            seat: {}
            for seat in PVP_SEATS
        }
        self.selected_weapon_character: tuple[str, str] | None = None
        self.timer_texts_by_seat: dict[str, list[str]] = {
            seat: [""] * len(PVP_TIMER_CHAMBERS)
            for seat in PVP_SEATS
        }

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
        self.draft_workspace.assignment_character_clicked.connect(
            self.select_assignment_character
        )
        self.draft_workspace.assignment_slot_clicked.connect(
            self.assign_selected_character_to_slot
        )
        self.draft_workspace.assignment_slot_clear_clicked.connect(
            self.clear_assignment_slot
        )
        self.draft_workspace.weapon_character_clicked.connect(
            self.select_weapon_character
        )
        self.draft_workspace.weapon_stack_clicked.connect(self.assign_weapon_stack)
        self.draft_workspace.weapon_clear_clicked.connect(self.clear_weapon_assignment)
        self.draft_workspace.timer_text_changed.connect(self.set_timer_text)
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
        self._reset_post_draft_state()
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
        self._reset_post_draft_state()
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()

    def apply_draft_card_click(self, action_payload: Mapping[str, Any]) -> bool:
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
        action_request = _draft_action_from_unified_pool(board, action_payload)
        if action_request is None:
            self._last_draft_status = tr("app_shell.pvp.draft.illegal_target")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        action_type, character_id = action_request
        try:
            action = session.controller.apply_current_action(
                character_id,
                expected_action_type=action_type,
            )
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

    def continue_to_assignment(self) -> bool:
        session = self.active_draft_session
        if session is None or not _draft_is_complete(session.board_dict()):
            self._last_draft_status = tr("app_shell.pvp.post.draft_not_complete")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self.draft_stage = PVP_DRAFT_STAGE_ASSIGNMENT
        self._last_draft_status = tr("app_shell.pvp.post.assignment_started")
        self._sync_draft_workspace()
        self.state_changed.emit()
        return True

    def select_assignment_character(self, seat: str, character_id: str) -> None:
        if seat not in PVP_SEATS or not character_id:
            return
        self.selected_assignment_character = (seat, character_id)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def assign_selected_character_to_slot(
        self,
        seat: str,
        team_index: int,
        slot_index: int,
    ) -> None:
        if seat not in PVP_SEATS:
            return
        slots = self.assignment_slots_by_seat[seat]
        if not (0 <= team_index < 2 and 0 <= slot_index < 4):
            return
        selected = self.selected_assignment_character
        if selected is None:
            existing = slots[team_index][slot_index]
            if existing:
                self.selected_assignment_character = (seat, existing)
                self._sync_draft_workspace()
                self.state_changed.emit()
            return
        selected_seat, character_id = selected
        if selected_seat != seat:
            return
        session = self.active_draft_session
        if session is None or character_id not in _picked_character_ids(
            session.board_dict(),
            seat,
        ):
            return
        for team in slots:
            for index, value in enumerate(team):
                if value == character_id:
                    team[index] = None
        slots[team_index][slot_index] = character_id
        self.selected_assignment_character = None
        self._clear_weapon_for_unassigned_characters(seat)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def clear_assignment_slot(self, seat: str, team_index: int, slot_index: int) -> None:
        if seat not in PVP_SEATS:
            return
        slots = self.assignment_slots_by_seat[seat]
        if not (0 <= team_index < 2 and 0 <= slot_index < 4):
            return
        slots[team_index][slot_index] = None
        self._clear_weapon_for_unassigned_characters(seat)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def assignment_ready(self) -> bool:
        session = self.active_draft_session
        if session is None:
            return False
        return all(
            validate_team_assignment(
                session.controller.session_state,
                self._team_assignment_for(seat),
            ).ready
            for seat in PVP_SEATS
        )

    def continue_to_weapons(self) -> bool:
        session = self.active_draft_session
        if session is None:
            return False
        try:
            for seat in PVP_SEATS:
                session.controller.set_team_assignment(self._team_assignment_for(seat))
        except FreeDraftControllerActionRejected as exc:
            self._last_draft_status = tr("app_shell.pvp.post.assignment_invalid").format(
                code=getattr(exc, "code", "") or str(exc),
            )
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self.draft_stage = PVP_DRAFT_STAGE_WEAPONS
        self.selected_assignment_character = None
        self._last_draft_status = tr("app_shell.pvp.post.weapons_started")
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def select_weapon_character(self, seat: str, character_id: str) -> None:
        if seat not in PVP_SEATS or not character_id:
            return
        self.selected_weapon_character = (seat, character_id)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def assign_weapon_stack(self, seat: str, character_id: str, stack_key: str) -> None:
        if seat not in PVP_SEATS or not character_id or not stack_key:
            return
        session = self.active_draft_session
        if session is None:
            return
        if not _weapon_stack_is_assignable(
            session,
            self._draft_view_state(),
            seat,
            character_id,
            stack_key,
        ):
            self._last_draft_status = tr("app_shell.pvp.post.weapon_invalid")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return
        self.weapon_assignments_by_seat[seat][character_id] = stack_key
        self._last_draft_status = ""
        self._sync_draft_workspace()
        self.state_changed.emit()

    def clear_weapon_assignment(self, seat: str, character_id: str) -> None:
        if seat in PVP_SEATS:
            self.weapon_assignments_by_seat[seat].pop(character_id, None)
            self._sync_draft_workspace()
            self.state_changed.emit()

    def weapons_ready(self) -> bool:
        session = self.active_draft_session
        if session is None:
            return False
        return all(
            validate_weapon_assignment(
                session.controller.session_state,
                self._team_assignment_for(seat),
                self._weapon_assignment_for(seat),
            ).ready
            for seat in PVP_SEATS
        )

    def continue_to_timers(self) -> bool:
        session = self.active_draft_session
        if session is None:
            return False
        try:
            for seat in PVP_SEATS:
                session.controller.set_weapon_assignment(self._weapon_assignment_for(seat))
        except FreeDraftControllerActionRejected as exc:
            self._last_draft_status = tr("app_shell.pvp.post.weapon_invalid_code").format(
                code=getattr(exc, "code", "") or str(exc),
            )
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self.draft_stage = PVP_DRAFT_STAGE_TIMERS_RESULTS
        self.selected_weapon_character = None
        self._last_draft_status = tr("app_shell.pvp.post.timers_started")
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def set_timer_text(self, seat: str, index: int, text: str) -> None:
        if seat not in PVP_SEATS or not (0 <= index < len(PVP_TIMER_CHAMBERS)):
            return
        self.timer_texts_by_seat[seat][index] = text
        self.state_changed.emit()

    def timers_ready(self) -> bool:
        return all(
            _parse_timer_text(self.timer_texts_by_seat[seat][index]) is not None
            for seat in PVP_SEATS
            for index in range(len(PVP_TIMER_CHAMBERS))
        )

    def finalize_match_result(self) -> bool:
        session = self.active_draft_session
        if session is None:
            return False
        if not self.weapons_ready():
            self._last_draft_status = tr("app_shell.pvp.post.weapon_invalid")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        if not self.timers_ready():
            self._last_draft_status = tr("app_shell.pvp.post.timers_invalid")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        timers = {
            seat: PlayerMatchTimers(
                seat=seat,
                chambers=tuple(
                    ChamberTimer(
                        room_id="local",
                        chamber_id=PVP_TIMER_CHAMBERS[index],
                        elapsed_seconds=_parse_timer_text(
                            self.timer_texts_by_seat[seat][index],
                        )
                        or 0,
                    )
                    for index in range(len(PVP_TIMER_CHAMBERS))
                ),
            )
            for seat in PVP_SEATS
        }
        session.controller.set_match_timers(timers["player_1"], timers["player_2"])
        self.draft_stage = PVP_DRAFT_STAGE_COMPLETED_RESULT
        self._last_draft_status = tr("app_shell.pvp.post.result_finalized")
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def last_play_status(self) -> str:
        return self._last_play_status

    def last_draft_status(self) -> str:
        return self._last_draft_status

    def _reset_post_draft_state(self) -> None:
        self.draft_stage = PVP_DRAFT_STAGE_DRAFT
        self.assignment_slots_by_seat = _empty_assignment_slots_by_seat()
        self.selected_assignment_character = None
        self.weapon_assignments_by_seat = {
            seat: {}
            for seat in PVP_SEATS
        }
        self.selected_weapon_character = None
        self.timer_texts_by_seat = {
            seat: [""] * len(PVP_TIMER_CHAMBERS)
            for seat in PVP_SEATS
        }

    def _draft_view_state(self) -> dict[str, Any]:
        return {
            "stage": self.draft_stage,
            "assignment_slots": {
                seat: [list(team) for team in self.assignment_slots_by_seat[seat]]
                for seat in PVP_SEATS
            },
            "selected_assignment_character": (
                list(self.selected_assignment_character)
                if self.selected_assignment_character is not None
                else None
            ),
            "weapon_assignments": {
                seat: dict(self.weapon_assignments_by_seat[seat])
                for seat in PVP_SEATS
            },
            "selected_weapon_character": (
                list(self.selected_weapon_character)
                if self.selected_weapon_character is not None
                else None
            ),
            "timer_texts": {
                seat: list(self.timer_texts_by_seat[seat])
                for seat in PVP_SEATS
            },
        }

    def _team_assignment_for(self, seat: str) -> PlayerTeamAssignment:
        slots = self.assignment_slots_by_seat.get(seat, [[None] * 4, [None] * 4])
        teams = tuple(
            TeamAssignment(
                team_index=team_index,
                character_ids=tuple(
                    character_id
                    for character_id in slots[team_index]
                    if character_id
                ),
            )
            for team_index in range(2)
        )
        return PlayerTeamAssignment(seat=seat, teams=teams)

    def _weapon_assignment_for(self, seat: str) -> PlayerWeaponAssignment:
        assigned = set(
            character_id
            for team in self.assignment_slots_by_seat.get(seat, [])
            for character_id in team
            if character_id
        )
        assignments = tuple(
            CharacterWeaponAssignment(
                character_id=character_id,
                weapon_stack_key=stack_key,
            )
            for character_id, stack_key in sorted(
                self.weapon_assignments_by_seat.get(seat, {}).items()
            )
            if character_id in assigned and stack_key
        )
        return PlayerWeaponAssignment(seat=seat, assignments=assignments)

    def _clear_weapon_for_unassigned_characters(self, seat: str) -> None:
        assigned = set(
            character_id
            for team in self.assignment_slots_by_seat.get(seat, [])
            for character_id in team
            if character_id
        )
        current = self.weapon_assignments_by_seat.get(seat, {})
        for character_id in list(current):
            if character_id not in assigned:
                current.pop(character_id, None)
        selected = self.selected_weapon_character
        if selected is not None and selected[0] == seat and selected[1] not in assigned:
            self.selected_weapon_character = None

    def _on_decks_state_changed(self) -> None:
        self._sync_play_workspace()
        self.state_changed.emit()

    def _sync_play_workspace(self) -> None:
        self.play_workspace.set_active_session(self.active_draft_session)

    def _sync_draft_workspace(self) -> None:
        self.draft_workspace.set_active_session(
            self.active_draft_session,
            status_text=self._last_draft_status,
            view_state=self._draft_view_state(),
            character_assets=self.character_assets,
            weapon_assets=self.weapon_assets,
        )















from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.pvp.draft.assignment.target_slot import PvpPostDraftTargetSlotWidget
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from ui.right_panel.pvp.host import PvpRightPanelHost
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


PvpDraftCardButton = PvpDraftUnifiedCardButton


__all__ = [
    "PVP_PAGE_DECKS",
    "PVP_PAGE_DRAFT",
    "PVP_PAGE_PLAY",
    "PvpActiveDraftSession",
    "PvpDraftCardButton",
    "PvpDraftUnifiedCardButton",
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
