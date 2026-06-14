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


class PvpPostDraftTargetSlotWidget(QFrame):
    clicked = Signal()
    clear_assignment_requested = Signal()
    clear_weapon_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clickable = False
        self._portrait_path = ""
        self._weapon_path = ""
        self._weapon_tooltip_controller = None
        self._clear_tooltip_controller = None
        self.setObjectName("pvp-team-slot")
        self.setFixedSize(92, 82)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        root.addLayout(top)

        self.portrait_label = QLabel("")
        self.portrait_label.setObjectName("pvp-target-slot-portrait")
        self.portrait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait_label.setFixedSize(46, 46)
        top.addWidget(self.portrait_label)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(3)
        top.addLayout(side)

        self.weapon_label = QLabel("")
        self.weapon_label.setObjectName("pvp-target-slot-weapon")
        self.weapon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weapon_label.setFixedSize(28, 28)
        side.addWidget(self.weapon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.clear_button = QPushButton("x")
        self.clear_button.setObjectName("row_cancel_button")
        self.clear_button.clicked.connect(self.clear_assignment_requested.emit)
        side.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.name_label = QLabel("")
        self.name_label.setObjectName("pvp-target-slot-name")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedHeight(16)
        root.addWidget(self.name_label)

    def configure(
        self,
        *,
        seat: str,
        team_index: int,
        slot_index: int,
        character_id: str,
        character_name: str,
        empty_label: str,
        portrait_path: str,
        weapon_stack_key: str,
        weapon_name: str,
        weapon_image_path: str,
        weapon_tooltip: str,
        selected_assignment: bool,
        selected_weapon_character: bool,
        clear_mode: str,
        clickable: bool,
    ) -> None:
        self._clickable = bool(clickable)
        self._portrait_path = portrait_path
        self._weapon_path = weapon_image_path
        has_character = bool(character_id)
        has_weapon = bool(weapon_stack_key)
        self.setProperty("seat", seat)
        self.setProperty("teamIndex", team_index)
        self.setProperty("slotIndex", slot_index)
        self.setProperty("characterId", character_id)
        self.setProperty("stackKey", weapon_stack_key)
        self.setProperty("hasCharacter", has_character)
        self.setProperty("selectedAssignment", selected_assignment)
        self.setProperty("selectedWeaponCharacter", selected_weapon_character)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._clickable
            else Qt.CursorShape.ArrowCursor
        )

        portrait_loaded = _set_label_hidpi_pixmap(
            self.portrait_label,
            portrait_path,
            QSize(46, 46),
            surface="pvp_postdraft_target_portrait",
        )
        self.setProperty("hasPortraitPixmap", portrait_loaded)
        self.portrait_label.setProperty("hasPixmap", portrait_loaded)
        if not portrait_loaded:
            self.portrait_label.setText(_slot_portrait_fallback(character_name, slot_index))

        weapon_loaded = _set_label_hidpi_pixmap(
            self.weapon_label,
            weapon_image_path,
            QSize(24, 24),
            surface="pvp_postdraft_target_weapon",
        )
        self.setProperty("hasWeaponPixmap", weapon_loaded)
        self.weapon_label.setProperty("hasPixmap", weapon_loaded)
        self.weapon_label.setProperty("assigned", has_weapon)
        if not weapon_loaded:
            self.weapon_label.setText("W" if has_weapon else "-")
        self._weapon_tooltip_controller = _set_custom_tooltip_text(
            self.weapon_label,
            self._weapon_tooltip_controller,
            weapon_tooltip or weapon_name,
        )

        self.clear_button.setVisible(clear_mode in {"assignment", "weapon"})
        self.clear_button.setEnabled(
            (clear_mode == "assignment" and has_character)
            or (clear_mode == "weapon" and has_weapon)
        )
        try:
            self.clear_button.clicked.disconnect()
        except RuntimeError:
            pass
        if clear_mode == "weapon":
            self.clear_button.clicked.connect(self.clear_weapon_requested.emit)
            clear_text = tr("app_shell.pvp.post.clear_weapon")
        else:
            self.clear_button.clicked.connect(self.clear_assignment_requested.emit)
            clear_text = ""
        self._clear_tooltip_controller = _set_custom_tooltip_text(
            self.clear_button,
            self._clear_tooltip_controller,
            clear_text,
        )

        self.name_label.setText(character_name if has_character else empty_label)
        _refresh_qss(self)
        _refresh_qss(self.portrait_label)
        _refresh_qss(self.weapon_label)

    def click(self) -> None:
        if self._clickable:
            self.clicked.emit()

    def refresh_hidpi_pixmaps(self) -> None:
        _set_label_hidpi_pixmap(
            self.portrait_label,
            self._portrait_path,
            QSize(46, 46),
            surface="pvp_postdraft_target_portrait",
        )
        _set_label_hidpi_pixmap(
            self.weapon_label,
            self._weapon_path,
            QSize(24, 24),
            surface="pvp_postdraft_target_weapon",
        )

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.Show,
        ):
            self.refresh_hidpi_pixmaps()
        return super().event(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._clickable:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


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
QFrame#pvp_draft_result_zone {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 6px;
    background: {UI_BG_PANEL};
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
QFrame#pvp_postdraft_match_panel {{
    background: transparent;
    border: none;
}}
QFrame#pvp-postdraft-target-player-1,
QFrame#pvp-postdraft-target-player-2 {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL};
}}
QFrame#pvp-postdraft-target-player-1 {{
    border-left: 4px solid {UI_ACCENT_TEAM_1};
}}
QFrame#pvp-postdraft-target-player-2 {{
    border-left: 4px solid {UI_ACCENT_TEAM_2};
}}
QFrame#pvp-team-half,
QFrame#pvp-timer-area {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_PANEL_RAISED};
}}
QFrame#pvp-team-slot {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_PANEL_RAISED};
    color: {UI_TEXT_SECONDARY};
}}
QFrame#pvp-team-slot[hasCharacter="true"] {{
    color: {UI_TEXT_PRIMARY};
}}
QFrame#pvp-team-slot[selectedAssignment="true"],
QFrame#pvp-team-slot[selectedWeaponCharacter="true"] {{
    border-color: {UI_STATE_SUCCESS};
    background: #203b28;
}}
QLabel#pvp-target-slot-portrait {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
    font-size: 10px;
    font-weight: 800;
}}
QLabel#pvp-target-slot-portrait[hasPixmap="true"] {{
    background: transparent;
}}
QLabel#pvp-target-slot-weapon {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
    font-size: 10px;
    font-weight: 800;
}}
QLabel#pvp-target-slot-weapon[assigned="true"] {{
    color: {UI_TEXT_SECONDARY};
}}
QLabel#pvp-target-slot-name {{
    color: {UI_TEXT_SECONDARY};
    background: transparent;
    border: none;
    font-size: 10px;
    font-weight: 700;
}}
QFrame#pvp-timer-row {{
    border: none;
    background: transparent;
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

        self.match_frame = QFrame()
        self.match_frame.setObjectName("pvp_postdraft_match_panel")
        self.match_layout = QVBoxLayout(self.match_frame)
        self.match_layout.setContentsMargins(0, 0, 0, 0)
        self.match_layout.setSpacing(6)
        root.addWidget(self.match_frame, 1)
        self.target_zone_frames_by_seat: dict[str, QFrame] = {}
        self.team_slot_buttons_by_key: dict[tuple[str, int, int], PvpPostDraftTargetSlotWidget] = {}
        self.timer_inputs_by_key: dict[tuple[str, int], QLineEdit] = {}
        self.timer_total_labels_by_seat: dict[str, QLabel] = {}

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

        self.stage_button = QPushButton()
        self.stage_button.setObjectName("pvp_primary_button")
        self.stage_button.clicked.connect(self._on_stage_button_clicked)
        root.addWidget(self.stage_button)

        self.result_zone_frames: dict[tuple[str, str], QFrame] = {}
        self.result_zone_title_labels: dict[tuple[str, str], QLabel] = {}
        self.result_zone_value_labels: dict[tuple[str, str], QLabel] = {}
        for seat in ("player_1", "player_2"):
            for zone in ("picked", "banned"):
                frame = QFrame()
                frame.setObjectName("pvp_draft_result_zone")
                frame_layout = QVBoxLayout(frame)
                frame_layout.setContentsMargins(8, 7, 8, 7)
                frame_layout.setSpacing(3)
                title = QLabel()
                title.setObjectName("pvp_draft_result_title")
                frame_layout.addWidget(title)
                value = QLabel()
                value.setObjectName(
                    "pvp_draft_result_picks"
                    if zone == "picked"
                    else "pvp_draft_result_bans"
                )
                value.setWordWrap(True)
                frame_layout.addWidget(value)
                root.addWidget(frame)
                key = (seat, zone)
                self.result_zone_frames[key] = frame
                self.result_zone_title_labels[key] = title
                self.result_zone_value_labels[key] = value

        self.log_title_label = QLabel()
        self.log_title_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.log_title_label)

        self.log_labels: list[QLabel] = []
        for _index in range(5):
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

        self.workspace.state_changed.connect(self.refresh)
        self.workspace.active_draft_changed.connect(self.refresh)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        session = self.workspace.active_draft_session
        has_session = session is not None
        self.empty_label.setVisible(not has_session)
        self.match_frame.setVisible(False)
        self.status_frame.setVisible(has_session)
        self.log_title_label.setVisible(has_session)
        self.clear_button.setVisible(has_session)
        self.clear_button.setEnabled(has_session)
        self.stage_button.setVisible(has_session)
        self.play_button.setVisible(True)
        self.message_label.setText(self.workspace.last_draft_status())
        self.message_label.setVisible(bool(self.message_label.text()))

        if session is None:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
            for label in (*self.status_labels, *self.log_labels):
                label.clear()
                label.setVisible(False)
            for frame in self.result_zone_frames.values():
                frame.setVisible(False)
            self.stage_button.setVisible(False)
            return

        board = session.board_dict()
        stage = self.workspace.draft_stage
        post_draft_stage = _is_post_draft_stage(stage)
        if post_draft_stage:
            self._rebuild_match_panel(board, stage)
        else:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
        self.match_frame.setVisible(post_draft_stage)
        status_lines = _draft_panel_status_lines(board, stage=stage, workspace=self.workspace)
        for index, label in enumerate(self.status_labels):
            text = status_lines[index] if index < len(status_lines) else ""
            label.setText(text)
            label.setVisible(bool(text))

        self._refresh_stage_button(board, stage)

        show_draft_summary = stage in {
            PVP_DRAFT_STAGE_DRAFT,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        } and not post_draft_stage
        for key, frame in self.result_zone_frames.items():
            seat, zone = key
            self.result_zone_title_labels[key].setText(
                _draft_result_zone_title(seat, zone)
            )
            self.result_zone_value_labels[key].setText(
                _draft_result_zone_text(board, seat=seat, zone=zone)
            )
            frame.setVisible(show_draft_summary)

        log_lines = _draft_action_log_lines(board, limit=len(self.log_labels))
        self.log_title_label.setVisible(show_draft_summary)
        for index, label in enumerate(self.log_labels):
            text = log_lines[index] if index < len(log_lines) else ""
            label.setText(text)
            label.setVisible(show_draft_summary and bool(text))

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self.log_title_label.setText(tr("app_shell.pvp.draft.action_log_title"))
        self.clear_button.setText(tr("app_shell.pvp.draft.abandon"))
        self.play_button.setText(tr("app_shell.pvp.draft.back_to_play"))
        self.refresh()

    def _refresh_stage_button(self, board: Mapping[str, Any], stage: str) -> None:
        if stage == PVP_DRAFT_STAGE_DRAFT:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_assignment"))
            self.stage_button.setVisible(_draft_is_complete(board))
            self.stage_button.setEnabled(_draft_is_complete(board))
            return
        if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_weapons"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.assignment_ready())
            return
        if stage == PVP_DRAFT_STAGE_WEAPONS:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_timers"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.weapons_ready())
            return
        if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
            self.stage_button.setText(tr("app_shell.pvp.post.finalize_result"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.timers_ready())
            return
        self.stage_button.setVisible(False)

    def _on_stage_button_clicked(self) -> None:
        stage = self.workspace.draft_stage
        if stage == PVP_DRAFT_STAGE_DRAFT:
            self.workspace.continue_to_assignment()
        elif stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.workspace.continue_to_weapons()
        elif stage == PVP_DRAFT_STAGE_WEAPONS:
            self.workspace.continue_to_timers()
        elif stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
            self.workspace.finalize_match_result()

    def _clear_match_registries(self) -> None:
        self.target_zone_frames_by_seat.clear()
        self.team_slot_buttons_by_key.clear()
        self.timer_inputs_by_key.clear()
        self.timer_total_labels_by_seat.clear()

    def _rebuild_match_panel(self, board: Mapping[str, Any], stage: str) -> None:
        _clear_layout(self.match_layout)
        self._clear_match_registries()
        session = self.workspace.active_draft_session
        if session is None:
            return
        for seat in PVP_SEATS:
            zone = QFrame()
            zone.setObjectName(_postdraft_target_object_name(seat))
            zone.setProperty("seat", seat)
            zone_layout = QVBoxLayout(zone)
            zone_layout.setContentsMargins(7, 7, 7, 7)
            zone_layout.setSpacing(5)
            self.target_zone_frames_by_seat[seat] = zone

            title = QLabel(_seat_label(seat))
            title.setObjectName("pvp_draft_result_title")
            zone_layout.addWidget(title)

            teams_row = QHBoxLayout()
            teams_row.setContentsMargins(0, 0, 0, 0)
            teams_row.setSpacing(5)
            for team_index in range(2):
                teams_row.addWidget(
                    self._build_target_team(board, session, stage, seat, team_index),
                    1,
                )
            zone_layout.addLayout(teams_row)

            self._add_timer_result_area(zone_layout, session, stage, seat)
            self.match_layout.addWidget(zone, 1)

    def _build_target_team(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pvp-team-half")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        title = QLabel(
            tr("app_shell.pvp.post.team_title").format(index=team_index + 1)
        )
        title.setObjectName("small_muted")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(3)
        slots = _assignment_slots(self.workspace._draft_view_state(), seat)
        for slot_index in range(4):
            grid.addWidget(
                self._build_target_slot(
                    board,
                    session,
                    stage,
                    seat,
                    team_index,
                    slot_index,
                    slots[team_index][slot_index],
                ),
                slot_index // 2,
                slot_index % 2,
            )
        layout.addLayout(grid)
        return frame

    def _build_target_slot(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
        character_id: str | None,
    ) -> PvpPostDraftTargetSlotWidget:
        character_name = (
            _entry_display_name_for_id(board, character_id)
            if character_id
            else ""
        )
        portrait_path = _asset_image_path(
            self.workspace.draft_workspace._character_assets_by_id.get(
                character_id or "",
            )
        )
        stack_key = _weapon_assignment_map(self.workspace._draft_view_state(), seat).get(
            character_id or "",
            "",
        )
        weapon_name = _weapon_display_name(session, seat, stack_key)
        weapon_image_path = _asset_image_path(
            self.workspace.draft_workspace._weapon_assets_by_stack_key.get(stack_key)
        )
        slot = PvpPostDraftTargetSlotWidget()
        slot.configure(
            seat=seat,
            team_index=team_index,
            slot_index=slot_index,
            character_id=character_id or "",
            character_name=character_name,
            empty_label=tr("app_shell.pvp.post.empty_slot").format(index=slot_index + 1),
            portrait_path=portrait_path,
            weapon_stack_key=stack_key,
            weapon_name=weapon_name,
            weapon_image_path=weapon_image_path,
            weapon_tooltip=_postdraft_weapon_tooltip(session, seat, stack_key),
            selected_assignment=bool(
                _selected_assignment_character(self.workspace._draft_view_state())
                == (seat, character_id)
            ),
            selected_weapon_character=bool(
                _selected_weapon_character(self.workspace._draft_view_state())
                == (seat, character_id)
            ),
            clear_mode=(
                "assignment"
                if stage == PVP_DRAFT_STAGE_ASSIGNMENT
                else "weapon"
                if stage == PVP_DRAFT_STAGE_WEAPONS and character_id and stack_key
                else ""
            ),
            clickable=bool(
                stage == PVP_DRAFT_STAGE_ASSIGNMENT
                or (stage == PVP_DRAFT_STAGE_WEAPONS and character_id)
            ),
        )
        slot.clicked.connect(
            lambda s=seat, t=team_index, i=slot_index: (
                self._on_target_slot_clicked(stage, s, t, i)
            )
        )
        slot.clear_assignment_requested.connect(
            lambda s=seat, t=team_index, i=slot_index: (
                self.workspace.clear_assignment_slot(s, t, i)
            )
        )
        if character_id:
            slot.clear_weapon_requested.connect(
                lambda s=seat, c=character_id: self.workspace.clear_weapon_assignment(s, c)
            )
        self.team_slot_buttons_by_key[(seat, team_index, slot_index)] = slot
        return slot

    def _on_target_slot_clicked(
        self,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
    ) -> None:
        if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.workspace.assign_selected_character_to_slot(seat, team_index, slot_index)
            return
        character_id = self.workspace.assignment_slots_by_seat[seat][team_index][slot_index]
        if character_id and stage == PVP_DRAFT_STAGE_WEAPONS:
            self.workspace.select_weapon_character(seat, character_id)

    def _add_timer_result_area(
        self,
        layout: QVBoxLayout,
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
    ) -> None:
        timer_frame = QFrame()
        timer_frame.setObjectName("pvp-timer-area")
        timer_layout = QVBoxLayout(timer_frame)
        timer_layout.setContentsMargins(5, 5, 5, 5)
        timer_layout.setSpacing(3)
        show_inputs = stage == PVP_DRAFT_STAGE_TIMERS_RESULTS
        show_result = stage == PVP_DRAFT_STAGE_COMPLETED_RESULT
        if show_inputs or show_result:
            for index, chamber_id in enumerate(PVP_TIMER_CHAMBERS):
                row = QFrame()
                row.setObjectName("pvp-timer-row")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                label = QLabel(f"T{chamber_id}")
                label.setObjectName("pvp_deck_info_line")
                row_layout.addWidget(label)
                if show_inputs:
                    line = QLineEdit()
                    line.setPlaceholderText("mm:ss")
                    line.setText(self.workspace.timer_texts_by_seat[seat][index])
                    line.textChanged.connect(
                        lambda text, s=seat, i=index: self._on_timer_text_changed(s, i, text)
                    )
                    self.timer_inputs_by_key[(seat, index)] = line
                    row_layout.addWidget(line, 1)
                else:
                    value = QLabel(_completed_timer_text(session, seat, index))
                    value.setObjectName("pvp_deck_info_line")
                    row_layout.addWidget(value, 1)
                timer_layout.addWidget(row)
        else:
            dps = QLabel(tr("app_shell.pvp.post.dps_unavailable"))
            dps.setObjectName("small_muted")
            timer_layout.addWidget(dps)
        total = QLabel(
            tr("app_shell.pvp.post.timer_total").format(
                total=_format_seconds(_postdraft_timer_total(session, self.workspace._draft_view_state(), seat)),
            )
        )
        total.setObjectName("small_muted")
        self.timer_total_labels_by_seat[seat] = total
        timer_layout.addWidget(total)
        if show_result:
            result = QLabel(_result_line_for_seat(session, seat))
            result.setObjectName("pvp_deck_info_line")
            result.setWordWrap(True)
            timer_layout.addWidget(result)
        layout.addWidget(timer_frame)

    def _on_timer_text_changed(self, seat: str, index: int, text: str) -> None:
        self.workspace.set_timer_text(seat, index, text)
        total_label = self.timer_total_labels_by_seat.get(seat)
        if total_label is None:
            return
        total = 0
        for timer_index in range(len(PVP_TIMER_CHAMBERS)):
            line = self.timer_inputs_by_key.get((seat, timer_index))
            seconds = _parse_timer_text(line.text() if line is not None else "")
            if seconds is not None:
                total += seconds
        total_label.setText(
            tr("app_shell.pvp.post.timer_total").format(
                total=_format_seconds(total),
            )
        )


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


def _draft_panel_status_lines(
    board: Mapping[str, Any],
    *,
    stage: str = PVP_DRAFT_STAGE_DRAFT,
    workspace: PvpWorkspace | None = None,
) -> list[str]:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT and workspace is not None:
        selected = workspace.selected_assignment_character
        selected_text = (
            f"{_seat_short_label(selected[0])} "
            f"{_entry_display_name_for_id(board, selected[1])}"
            if selected is not None
            else tr("app_shell.pvp.post.none_selected")
        )
        return [
            tr("app_shell.pvp.post.stage_assignment"),
            tr("app_shell.pvp.post.assignment_panel_status").format(
                p1=sum(
                    1
                    for team in workspace.assignment_slots_by_seat["player_1"]
                    for character_id in team
                    if character_id
                ),
                p2=sum(
                    1
                    for team in workspace.assignment_slots_by_seat["player_2"]
                    for character_id in team
                    if character_id
                ),
            ),
            tr("app_shell.pvp.post.selected_character").format(
                character=selected_text,
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.assignment_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_WEAPONS and workspace is not None:
        selected = workspace.selected_weapon_character
        selected_text = (
            f"{_seat_short_label(selected[0])} "
            f"{_entry_display_name_for_id(board, selected[1])}"
            if selected is not None
            else tr("app_shell.pvp.post.none_selected")
        )
        return [
            tr("app_shell.pvp.post.stage_weapons"),
            tr("app_shell.pvp.post.weapon_panel_status").format(
                p1=len(workspace.weapon_assignments_by_seat["player_1"]),
                p2=len(workspace.weapon_assignments_by_seat["player_2"]),
            ),
            tr("app_shell.pvp.post.selected_character").format(
                character=selected_text,
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.weapons_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS and workspace is not None:
        view_state = workspace._draft_view_state()
        return [
            tr("app_shell.pvp.post.stage_timers"),
            tr("app_shell.pvp.post.timer_panel_status").format(
                p1=_valid_timer_count(view_state, "player_1"),
                p2=_valid_timer_count(view_state, "player_2"),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_1"),
                total=_format_seconds(_timer_total_seconds(view_state, "player_1")),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_2"),
                total=_format_seconds(_timer_total_seconds(view_state, "player_2")),
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.timers_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT and workspace is not None:
        result = (
            workspace.active_draft_session.controller.state.match_result
            if workspace.active_draft_session is not None
            else None
        )
        if result is None:
            return [tr("app_shell.pvp.post.stage_result")]
        payload = result.to_dict()
        return [
            tr("app_shell.pvp.post.stage_result"),
            tr("app_shell.pvp.post.result_status").format(
                status=_text(payload.get("status")),
                winner=(
                    _seat_label(_text(payload.get("winner_seat")))
                    if payload.get("winner_seat")
                    else tr("app_shell.pvp.draft.none")
                ),
                diff=int(payload.get("seconds_difference") or 0),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_1"),
                total=_format_seconds(_mapping(payload.get("totals")).get("player_1")),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_2"),
                total=_format_seconds(_mapping(payload.get("totals")).get("player_2")),
            ),
        ]

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


def _ready_text(value: bool) -> str:
    return (
        tr("app_shell.pvp.post.ready_yes")
        if value
        else tr("app_shell.pvp.post.ready_no")
    )


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
            items=_draft_result_zone_text(board, seat="player_1", zone="picked"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_1"),
            items=_draft_result_zone_text(board, seat="player_1", zone="banned"),
        ),
        tr("app_shell.pvp.draft.final_picks").format(
            seat=_seat_label("player_2"),
            items=_draft_result_zone_text(board, seat="player_2", zone="picked"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_2"),
            items=_draft_result_zone_text(board, seat="player_2", zone="banned"),
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


def _unified_pool(board: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(board.get("unified_pool"))


def _unified_pool_entries(board: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = _unified_pool(board).get("entries")
    if not isinstance(entries, list):
        return []
    return [_mapping(entry) for entry in entries]


def _draft_main_pool_entries(board: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        entry
        for entry in _unified_pool_entries(board)
        if _text(entry.get("zone")) == "pool"
    ]


def _draft_entries_by_id(board: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _text(entry.get("character_id")): entry
        for entry in _unified_pool_entries(board)
        if _text(entry.get("character_id"))
    }


def _owner_seats(entry: Mapping[str, Any]) -> tuple[str, ...]:
    seats = entry.get("owner_seats")
    if not isinstance(seats, list):
        return ()
    return tuple(_text(seat) for seat in seats if _text(seat))


def _draft_unified_pool_summary(
    board: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
) -> str:
    progress = _mapping(board.get("progress"))
    shared_count = sum(1 for entry in entries if len(_owner_seats(entry)) > 1)
    return tr("app_shell.pvp.draft.unified_pool_summary").format(
        pool=len(entries),
        shared=shared_count,
        legal=int(progress.get("legal_target_count") or 0),
    )


def _draft_unified_card_text(entry: Mapping[str, Any]) -> str:
    name = _text(entry.get("display_name")) or _text(entry.get("character_id"))
    meta = " ".join(
        part
        for part in (
            _text(entry.get("element")),
            _text(entry.get("weapon_type")),
            _level_text(entry.get("level")),
        )
        if part
    )
    ownership = _draft_ownership_text(entry)
    status = _draft_card_status_label(_text(entry.get("status")))
    return "\n".join(part for part in (name, meta, ownership, status) if part)


def _draft_ownership_text(entry: Mapping[str, Any]) -> str:
    per_seat = _mapping(entry.get("per_seat"))
    parts: list[str] = []
    for seat in _owner_seats(entry):
        metadata = _mapping(per_seat.get(seat))
        parts.append(
            f"{_seat_short_label(seat)} {_constellation_text(metadata.get('constellation'))}"
        )
    return " | ".join(parts)


def _seat_short_label(seat: str) -> str:
    if seat == "player_1":
        return "P1"
    if seat == "player_2":
        return "P2"
    return seat


def _draft_action_from_unified_pool(
    board: Mapping[str, Any],
    action_payload: Mapping[str, Any],
) -> tuple[str, str] | None:
    action_type = _text(action_payload.get("type"))
    target_type = _text(action_payload.get("target_type"))
    character_id = _text(action_payload.get("character_id"))
    if (
        action_type not in {"ban_character", "pick_character"}
        or target_type != "character"
        or not character_id
    ):
        return None
    entry = _draft_entries_by_id(board).get(character_id)
    if not entry or not bool(entry.get("is_current_legal_target")):
        return None
    entry_action = _mapping(entry.get("action"))
    if (
        _text(entry_action.get("type")) != action_type
        or _text(entry_action.get("target_type")) != target_type
        or _text(entry_action.get("character_id")) != character_id
    ):
        return None
    return action_type, character_id


def _draft_result_zone_title(seat: str, zone: str) -> str:
    label = tr("app_shell.pvp.draft.picked") if zone == "picked" else tr("app_shell.pvp.draft.banned")
    return f"{_seat_label(seat)} · {label}"


def _draft_result_zone_text(
    board: Mapping[str, Any],
    *,
    seat: str,
    zone: str,
) -> str:
    result_zones = _mapping(_unified_pool(board).get("result_zones"))
    seat_zones = _mapping(result_zones.get(seat))
    character_ids = seat_zones.get(zone)
    if not isinstance(character_ids, list) or not character_ids:
        return tr("app_shell.pvp.draft.none")
    entries_by_id = _draft_entries_by_id(board)
    labels = [
        _draft_entry_display_name(entries_by_id.get(_text(character_id)), _text(character_id))
        for character_id in character_ids
    ]
    return ", ".join(label for label in labels if label) or tr("app_shell.pvp.draft.none")


def _draft_entry_display_name(
    entry: Mapping[str, Any] | None,
    fallback: str,
) -> str:
    if entry is None:
        return fallback
    return _text(entry.get("display_name")) or fallback


def _empty_assignment_slots_by_seat() -> dict[str, list[list[str | None]]]:
    return {
        seat: [[None for _slot in range(4)] for _team in range(2)]
        for seat in PVP_SEATS
    }


def _draft_stage(view_state: Mapping[str, Any]) -> str:
    stage = _text(view_state.get("stage"))
    return stage if stage in PVP_DRAFT_STAGE_VALUES else PVP_DRAFT_STAGE_DRAFT


def _draft_stage_title(board: Mapping[str, Any], stage: str) -> str:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
        return tr("app_shell.pvp.post.assignment_title")
    if stage == PVP_DRAFT_STAGE_WEAPONS:
        return tr("app_shell.pvp.post.weapons_title")
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
        return tr("app_shell.pvp.post.timers_title")
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT:
        return tr("app_shell.pvp.post.result_summary_title")
    return _draft_action_title(board)


def _draft_stage_detail(
    board: Mapping[str, Any],
    stage: str,
    view_state: Mapping[str, Any],
) -> str:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
        return tr("app_shell.pvp.post.assignment_detail").format(
            p1=len(_assigned_character_ids(view_state, "player_1")),
            p2=len(_assigned_character_ids(view_state, "player_2")),
        )
    if stage == PVP_DRAFT_STAGE_WEAPONS:
        return tr("app_shell.pvp.post.weapons_detail").format(
            p1=len(_weapon_assignment_map(view_state, "player_1")),
            p2=len(_weapon_assignment_map(view_state, "player_2")),
        )
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
        return tr("app_shell.pvp.post.timers_detail").format(
            p1=_valid_timer_count(view_state, "player_1"),
            p2=_valid_timer_count(view_state, "player_2"),
        )
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT:
        return tr("app_shell.pvp.post.result_detail")
    return _draft_action_detail(board)


def _selected_assignment_character(
    view_state: Mapping[str, Any],
) -> tuple[str, str] | None:
    return _seat_character_pair(view_state.get("selected_assignment_character"))


def _selected_weapon_character(
    view_state: Mapping[str, Any],
) -> tuple[str, str] | None:
    return _seat_character_pair(view_state.get("selected_weapon_character"))


def _seat_character_pair(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    seat = _text(value[0])
    character_id = _text(value[1])
    if seat not in PVP_SEATS or not character_id:
        return None
    return seat, character_id


def _assignment_slots(
    view_state: Mapping[str, Any],
    seat: str,
) -> list[list[str | None]]:
    slots = [[None for _slot in range(4)] for _team in range(2)]
    source = _mapping(view_state.get("assignment_slots")).get(seat)
    if not isinstance(source, list):
        return slots
    for team_index, team_value in enumerate(source[:2]):
        if not isinstance(team_value, list):
            continue
        for slot_index, character_id in enumerate(team_value[:4]):
            text = _text(character_id)
            slots[team_index][slot_index] = text or None
    return slots


def _assigned_character_ids(
    view_state: Mapping[str, Any],
    seat: str,
) -> tuple[str, ...]:
    return tuple(
        character_id
        for team in _assignment_slots(view_state, seat)
        for character_id in team
        if character_id
    )


def _picked_character_ids(board: Mapping[str, Any], seat: str) -> tuple[str, ...]:
    result_zones = _mapping(_unified_pool(board).get("result_zones"))
    picked = _mapping(result_zones.get(seat)).get("picked")
    if not isinstance(picked, list):
        return ()
    return tuple(_text(character_id) for character_id in picked if _text(character_id))


def _entry_display_name_for_id(board: Mapping[str, Any], character_id: str) -> str:
    return _draft_entry_display_name(
        _draft_entries_by_id(board).get(character_id),
        character_id,
    )


def _weapon_assignment_map(
    view_state: Mapping[str, Any],
    seat: str,
) -> dict[str, str]:
    values = _mapping(_mapping(view_state.get("weapon_assignments")).get(seat))
    return {
        _text(character_id): _text(stack_key)
        for character_id, stack_key in values.items()
        if _text(character_id) and _text(stack_key)
    }


def _compatible_weapon_stacks(
    session: PvpActiveDraftSession,
    seat: str,
    character_id: str,
) -> tuple[Any, ...]:
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return ()
    character = deck.character_by_id.get(character_id)
    if character is None:
        return ()
    character_weapon_type = _filter_token(character.weapon_type)
    stacks = [
        stack
        for stack in deck.weapons
        if _filter_token(stack.weapon_type) == character_weapon_type
    ]
    return tuple(
        sorted(
            stacks,
            key=lambda stack: (
                stack.display_name.casefold(),
                -(stack.rarity or 0),
                -(stack.level or 0),
                -(stack.refinement or 0),
                stack.stack_key,
            ),
        )
    )


def _weapon_stack_remaining(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
    stack_key: str,
    *,
    selected_character_id: str = "",
) -> int:
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return 0
    stack = deck.weapon_stack_by_key.get(stack_key)
    if stack is None:
        return 0
    available = max(0, int(stack.count or 0))
    used = sum(
        1
        for character_id, assigned_stack_key in _weapon_assignment_map(
            view_state,
            seat,
        ).items()
        if assigned_stack_key == stack_key and character_id != selected_character_id
    )
    return max(0, available - used)


def _weapon_stack_is_assignable(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
    character_id: str,
    stack_key: str,
) -> bool:
    if character_id not in set(_assigned_character_ids(view_state, seat)):
        return False
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return False
    character = deck.character_by_id.get(character_id)
    stack = deck.weapon_stack_by_key.get(stack_key)
    if character is None or stack is None:
        return False
    if _filter_token(character.weapon_type) != _filter_token(stack.weapon_type):
        return False
    return _weapon_stack_remaining(
        session,
        view_state,
        seat,
        stack_key,
        selected_character_id=character_id,
    ) > 0


def _weapon_display_name(
    session: PvpActiveDraftSession,
    seat: str,
    stack_key: str,
) -> str:
    if not stack_key:
        return ""
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return ""
    stack = deck.weapon_stack_by_key.get(stack_key)
    return stack.display_name if stack is not None else stack_key


def _timer_text(view_state: Mapping[str, Any], seat: str, index: int) -> str:
    values = _mapping(view_state.get("timer_texts")).get(seat)
    if not isinstance(values, list) or not (0 <= index < len(values)):
        return ""
    return _text(values[index])


def _parse_timer_text(text: str) -> int | None:
    value = _text(text)
    if not value:
        return None
    if ":" not in value:
        try:
            seconds = int(value)
        except ValueError:
            return None
        return seconds if seconds >= 0 else None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    minutes_text, seconds_text = parts
    if not minutes_text.isdigit() or not seconds_text.isdigit():
        return None
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    if seconds >= 60:
        return None
    return minutes * 60 + seconds


def _timer_total_seconds(view_state: Mapping[str, Any], seat: str) -> int:
    total = 0
    for index in range(len(PVP_TIMER_CHAMBERS)):
        seconds = _parse_timer_text(_timer_text(view_state, seat, index))
        if seconds is not None:
            total += seconds
    return total


def _valid_timer_count(view_state: Mapping[str, Any], seat: str) -> int:
    return sum(
        1
        for index in range(len(PVP_TIMER_CHAMBERS))
        if _parse_timer_text(_timer_text(view_state, seat, index)) is not None
    )


def _format_seconds(value: Any) -> str:
    try:
        seconds = max(0, int(value or 0))
    except (TypeError, ValueError):
        seconds = 0
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _post_draft_team_weapon_summary(
    session: PvpActiveDraftSession | None,
    board: Mapping[str, Any],
    seat: str,
) -> str:
    if session is None:
        return ""
    state = session.controller.state
    team_assignment = state.team_assignments.get(seat)
    if team_assignment is None:
        return tr("app_shell.pvp.post.team_summary_missing").format(
            seat=_seat_label(seat),
        )
    weapon_assignment = state.weapon_assignments.get(seat)
    weapon_by_character = {
        assignment.character_id: assignment.weapon_stack_key
        for assignment in (weapon_assignment.assignments if weapon_assignment else ())
    }
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        deck = None
    team_parts: list[str] = []
    for team in sorted(team_assignment.teams, key=lambda item: item.team_index):
        character_parts: list[str] = []
        for character_id in team.character_ids:
            character_name = _entry_display_name_for_id(board, character_id)
            stack_key = weapon_by_character.get(character_id, "")
            weapon_name = ""
            if deck is not None and stack_key:
                stack = deck.weapon_stack_by_key.get(stack_key)
                weapon_name = stack.display_name if stack is not None else stack_key
            character_parts.append(
                f"{character_name} ({weapon_name or tr('app_shell.pvp.draft.none')})"
            )
        team_parts.append(
            tr("app_shell.pvp.post.team_summary_team").format(
                index=team.team_index + 1,
                characters=", ".join(character_parts)
                or tr("app_shell.pvp.draft.none"),
            )
        )
    return tr("app_shell.pvp.post.team_summary").format(
        seat=_seat_label(seat),
        teams=" | ".join(team_parts),
    )


def _result_chamber_timer_lines(payload: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for seat, timer_key in (
        ("player_1", "player_1_timers"),
        ("player_2", "player_2_timers"),
    ):
        chambers = _mapping(payload.get(timer_key)).get("chambers")
        if not isinstance(chambers, list):
            continue
        for index, chamber_value in enumerate(chambers):
            chamber = _mapping(chamber_value)
            chamber_id = _text(chamber.get("chamber_id")) or str(index + 1)
            seconds = chamber.get("normalized_elapsed_seconds")
            if seconds is None:
                seconds = chamber.get("elapsed_seconds")
            lines.append(
                tr("app_shell.pvp.post.timer_chamber_line").format(
                    seat=_seat_label(seat),
                    chamber=chamber_id,
                    total=_format_seconds(seconds),
                )
            )
    return lines


def _is_post_draft_stage(stage: str) -> bool:
    return stage in {
        PVP_DRAFT_STAGE_ASSIGNMENT,
        PVP_DRAFT_STAGE_WEAPONS,
        PVP_DRAFT_STAGE_TIMERS_RESULTS,
        PVP_DRAFT_STAGE_COMPLETED_RESULT,
    }


def _postdraft_source_object_name(seat: str) -> str:
    if seat == "player_1":
        return "pvp-postdraft-source-player-1"
    return "pvp-postdraft-source-player-2"


def _postdraft_target_object_name(seat: str) -> str:
    if seat == "player_1":
        return "pvp-postdraft-target-player-1"
    return "pvp-postdraft-target-player-2"


def _character_assets_by_id(
    assets: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for asset in assets:
        character_id = character_id_from_asset(asset)
        if character_id:
            result[character_id] = dict(asset)
    return result


def _weapon_assets_by_stack_key(
    assets: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for asset in assets:
        weapon_ref = weapon_ref_from_asset(asset)
        if weapon_ref is not None and weapon_ref.key:
            result[weapon_ref.key] = dict(asset)
            metadata = _mapping(asset.get("metadata"))
            weapon = _mapping(metadata.get("weapon"))
            for weapon_type in (
                weapon_ref.weapon_type,
                weapon.get("weapon_type_name"),
                weapon.get("type_name"),
                weapon.get("type"),
            ):
                fallback_key = weapon_observed_stack_key(
                    weapon_id=weapon_ref.weapon_id,
                    weapon_type=weapon_type,
                    rarity=weapon_ref.rarity,
                    level=weapon_ref.level,
                    refinement=weapon_ref.refinement,
                )
                if fallback_key:
                    result.setdefault(fallback_key, dict(asset))
    return result


def _asset_image_path(asset: Mapping[str, Any] | None) -> str:
    if asset is None:
        return ""
    metadata = _mapping(asset.get("metadata"))
    character = _mapping(metadata.get("character"))
    weapon = _mapping(metadata.get("weapon"))
    for value in (
        character.get("portrait_path"),
        character.get("local_portrait_path"),
        character.get("side_icon_path"),
        character.get("icon_path"),
        weapon.get("icon_path"),
        weapon.get("local_icon_path"),
        asset.get("path"),
    ):
        path = _existing_local_asset_path(value)
        if path:
            return path
    return ""


def _existing_local_asset_path(value: Any) -> str:
    path_text = _text(value)
    if not path_text:
        return ""
    path = Path(path_text)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(PVP_BROWSER_PROJECT_ROOT / path)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return ""


def _postdraft_grid_scroll_area(
    grid: PixelIconGrid,
    *,
    object_name: str,
    maximum_height: int,
) -> OverlayVerticalScrollArea:
    scroll = OverlayVerticalScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("pvp-postdraft-source-grid-viewport")
    content = QWidget()
    content.setObjectName("pvp-postdraft-source-grid-content")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(grid)
    scroll.setWidget(content)
    scroll.setMaximumHeight(maximum_height)
    scroll.setMinimumHeight(min(maximum_height, max(1, grid.minimumSizeHint().height() + 4)))
    return scroll


def _postdraft_character_tooltip(name: str, *, assigned: bool) -> str:
    lines = [_text(name)]
    if assigned:
        lines.append(tr("app_shell.pvp.post.assigned_marker"))
    return "\n".join(line for line in lines if line)


def _postdraft_weapon_tooltip(
    session: PvpActiveDraftSession,
    seat: str,
    stack_key: str,
) -> str:
    if not stack_key:
        return ""
    try:
        stack = session.controller.session_state.deck_for(seat).weapon_stack_by_key.get(stack_key)
    except Exception:
        stack = None
    if stack is None:
        return stack_key
    parts = [stack.display_name or stack_key]
    meta: list[str] = []
    if stack.refinement is not None:
        meta.append(f"R{stack.refinement}")
    if stack.level is not None:
        meta.append(f"Lv.{stack.level}")
    if stack.count:
        meta.append(f"x{stack.count}")
    if meta:
        parts.append(" | ".join(meta))
    return "\n".join(part for part in parts if part)


def _slot_portrait_fallback(character_name: str, slot_index: int) -> str:
    name = _text(character_name)
    if not name:
        return str(slot_index + 1)
    for character in name:
        if character.strip():
            return character.upper()
    return str(slot_index + 1)


def _set_custom_tooltip_text(owner: QWidget, controller, text: str):
    if controller is None:
        return install_custom_tooltip(owner, text)
    controller.set_text(text)
    return controller


def _set_label_hidpi_pixmap(
    label: QLabel,
    image_path: str,
    size: QSize,
    *,
    surface: str,
) -> bool:
    label.clear()
    path = _existing_local_asset_path(image_path)
    if not path:
        return False
    result = load_hidpi_pixmap(
        path,
        size,
        dpr=label.devicePixelRatioF(),
        aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
        transform_mode=Qt.TransformationMode.SmoothTransformation,
        cache=_PVP_DECK_ICON_PIXMAP_CACHE,
        surface=surface,
    )
    if result.pixmap.isNull():
        return False
    label.setPixmap(result.pixmap)
    return True


def _postdraft_timer_total(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
) -> int:
    result = session.controller.state.match_result
    if result is not None:
        return int(_mapping(result.to_dict().get("totals")).get(seat) or 0)
    return _timer_total_seconds(view_state, seat)


def _completed_timer_text(
    session: PvpActiveDraftSession,
    seat: str,
    index: int,
) -> str:
    result = session.controller.state.match_result
    if result is None:
        return "--:--"
    timer_key = "player_1_timers" if seat == "player_1" else "player_2_timers"
    chambers = _mapping(result.to_dict().get(timer_key)).get("chambers")
    if not isinstance(chambers, list) or not (0 <= index < len(chambers)):
        return "--:--"
    chamber = _mapping(chambers[index])
    seconds = chamber.get("normalized_elapsed_seconds")
    if seconds is None:
        seconds = chamber.get("elapsed_seconds")
    return _format_seconds(seconds)


def _result_line_for_seat(session: PvpActiveDraftSession, seat: str) -> str:
    result = session.controller.state.match_result
    if result is None:
        return ""
    payload = result.to_dict()
    winner = _text(payload.get("winner_seat"))
    if not winner:
        outcome = tr("app_shell.pvp.post.result_draw")
    elif winner == seat:
        outcome = tr("app_shell.pvp.post.result_win")
    else:
        outcome = tr("app_shell.pvp.post.result_loss")
    return tr("app_shell.pvp.post.result_seat_line").format(
        result=outcome,
        diff=int(payload.get("seconds_difference") or 0),
    )


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
        "picked": tr("app_shell.pvp.draft.picked"),
        "banned": tr("app_shell.pvp.draft.banned"),
        "blocked": tr("app_shell.pvp.draft.blocked"),
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
