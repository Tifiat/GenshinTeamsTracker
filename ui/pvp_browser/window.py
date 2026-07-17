from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from localization import tr
from run_workspace.abyss.source_data import AbyssFloorSourceData
from run_workspace.abyss.source_data_runtime import (
    load_current_cached_abyss_floor_source_data,
)
from run_workspace.models import ABYSS_CHAMBER_START_SECONDS
from ui.character_browser.icon_grid_adapter import build_asset_grid_items
from ui.character_browser.filter_bar import CharacterFilterBar
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
from run_workspace.pvp.profile_package import (
    ImportedPvpProfileProvider,
    LocalPvpProfileProvider,
    PvpProfileProvider,
    export_pvp_profile_package,
    import_pvp_profile_package,
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
    PixelIconGridMetrics,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.pvp_browser.draft_order import PvpDraftOrderStrip
from ui.pvp_browser.timers import PvpTimersResultWidget
from ui.right_panel.common.seat_accent_frame import PvpSeatAccentFrame
from ui.right_panel.pvp._shared import (
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_DRAFT_STAGE_VALUES,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_DRAFT_IMMUNE_ACCENT,
    PVP_PAGE_DECKS,
    PVP_PAGE_DRAFT,
    PVP_PAGE_PLAY,
    PVP_POSTDRAFT_HEADER_HEIGHT,
    PVP_POSTDRAFT_SECTION_SPACING,
    PVP_SEATS,
    PVP_TIMER_CHAMBERS,
    _PVP_DECK_ICON_PIXMAP_CACHE,
    _active_draft_summary_lines,
    _asset_image_path,
    build_pvp_draft_grid_item,
    _character_assets_by_id,
    _clear_layout,
    _compact_issue_codes,
    _configure_postdraft_seat_label,
    _draft_action_from_unified_pool,
    _draft_is_complete,
    _draft_main_pool_entries,
    _draft_stage,
    _draft_stage_detail,
    _draft_stage_title,
    _draft_unified_pool_summary,
    _mapping,
    _parse_pvp_remaining_timer_text,
    _picked_character_ids,
    _postdraft_source_object_name,
    _pvp_deck_inactive_fill,
    _pvp_deck_item_properties,
    _pvp_deck_outline,
    _pvp_weapon_sort_key,
    _refresh_postdraft_seat_label_style,
    _refresh_qss,
    _seat_label,
    _seat_short_label,
    _text,
    _weapon_assets_by_stack_key,
    _weapon_type_filter_keys,
)
from ui.utils.ui_palette import (
    UI_BG_APP,
    UI_BG_BUTTON,
    UI_BG_BUTTON_CHECKED,
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
FILTER_BUTTON_STYLE = filter_button_style("app_shell_filter_button")


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
QPushButton#pvp_draft_pool_scope {{
    min-height: 27px;
    padding: 3px 12px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_SECONDARY};
    font-weight: 800;
}}
QPushButton#pvp_draft_pool_scope:checked {{
    border-color: {PVP_DRAFT_IMMUNE_ACCENT};
    background: {UI_BG_BUTTON_CHECKED};
    color: {UI_TEXT_PRIMARY};
}}
QFrame#pvp_draft_banner[complete="true"] {{
    border-color: {UI_STATE_SUCCESS};
}}
QScrollArea#pvp_draft_scroll {{
    background: transparent;
    border: none;
}}
QWidget#pvp_draft_scroll_viewport,
QWidget#pvp_draft_scroll_content {{
    background: transparent;
}}
QWidget#pvp_draft_unified_pool_grid,
QWidget#pvp_draft_order_strip {{
    background: transparent;
    border: none;
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
QFrame#pvp_postdraft_source_frame,
QFrame#pvp-postdraft-source-player-1,
QFrame#pvp-postdraft-source-player-2 {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL};
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

    def export_profile(self, output_path: str | Path) -> bool:
        try:
            report = export_pvp_profile_package(
                output_path,
                deck_dir=self.deck_dir,
                db_path=self.db_path,
            )
        except Exception as exc:
            self._last_status = str(exc) or exc.__class__.__name__
            self.state_changed.emit()
            return False
        self._last_status = tr("app_shell.pvp.profile.exported").format(
            path=str(report.path),
        )
        self.state_changed.emit()
        return True

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


class PvpDraftWorkspace(QWidget):
    card_clicked = Signal(dict)
    timer_text_changed = Signal(str, int, str)
    finalize_result_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PvpDraftWorkspace")
        self.setStyleSheet(PVP_DRAFT_WORKSPACE_STYLE)
        self._active_session: PvpActiveDraftSession | None = None
        self._status_text = ""
        self._view_state: Mapping[str, Any] = {}
        self._build_flow_context: Any | None = None
        self._character_assets_by_id: dict[str, dict[str, Any]] = {}
        self._weapon_assets_by_stack_key: dict[str, dict[str, Any]] = {}
        self.pool_grid: PixelIconGrid | None = None
        self._draft_pool_frame: QFrame | None = None
        self._draft_pool_info_label: QLabel | None = None
        self._draft_pool_empty_label: QLabel | None = None
        self._pool_scope = "all"
        self._pool_scope_buttons: dict[str, QPushButton] = {}
        self.character_filter_bar: CharacterFilterBar | None = None
        self.pool_items_by_character_id: dict[str, Any] = {}
        self.legal_character_ids: tuple[str, ...] = ()
        self._draft_actions_by_character_id: dict[str, dict[str, Any]] = {}
        self.source_zone_frames_by_seat: dict[str, QFrame] = {}
        self.source_body_widgets_by_seat: dict[str, QWidget] = {}
        self.source_header_labels_by_seat: dict[str, QLabel] = {}
        self._scoped_build_source_frame: QFrame | None = None
        self._scoped_build_context_id: int | None = None
        self._timers_result_widget: PvpTimersResultWidget | None = None
        self._abyss_source_data: AbyssFloorSourceData | None = None

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

        self.order_strip = PvpDraftOrderStrip()
        board_layout.addWidget(self.order_strip)
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
        build_flow_context: Any | None = None,
        abyss_source_data: AbyssFloorSourceData | None = None,
    ) -> None:
        self._active_session = session
        self._status_text = status_text
        self._view_state = dict(view_state or {})
        self._build_flow_context = build_flow_context
        self._abyss_source_data = abyss_source_data
        self._character_assets_by_id = _character_assets_by_id(character_assets)
        self._weapon_assets_by_stack_key = _weapon_assets_by_stack_key(weapon_assets)
        self.refresh()

    def refresh(self) -> None:
        session = self._active_session
        has_session = session is not None
        self.title_label.setVisible(False)
        self.empty_frame.setVisible(not has_session)
        self.board_frame.setVisible(False)
        self.scroll_area.setVisible(has_session)
        self.status_label.setText(self._status_text)
        self.status_label.setVisible(bool(self._status_text))
        self.pool_items_by_character_id.clear()
        self.legal_character_ids = ()
        self._draft_actions_by_character_id.clear()

        if session is None:
            self.source_zone_frames_by_seat.clear()
            self.source_body_widgets_by_seat.clear()
            self.source_header_labels_by_seat.clear()
            self._scoped_build_source_frame = None
            self._scoped_build_context_id = None
            self._detach_build_source_widgets()
            self._draft_pool_frame = None
            self._draft_pool_info_label = None
            self._draft_pool_empty_label = None
            self.pool_grid = None
            _clear_layout(self.scroll_layout)
            self.board_frame.setProperty("complete", False)
            _refresh_qss(self.board_frame)
            self.order_strip.set_board({}, portrait_paths={})
            self.scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.set_postdraft_alignment_margins(0, 0)
            self.lock_postdraft_content_height(None)
            return

        stage = _draft_stage(self._view_state)
        timers_stage = stage in {
            PVP_DRAFT_STAGE_TIMERS_RESULTS,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        }
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if timers_stage
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if not timers_stage:
            self.scroll_area.horizontalScrollBar().setValue(0)
        post_draft_stage = stage in {
            PVP_DRAFT_STAGE_ASSIGNMENT,
            PVP_DRAFT_STAGE_WEAPONS,
            PVP_DRAFT_STAGE_TIMERS_RESULTS,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        }
        if stage not in {PVP_DRAFT_STAGE_ASSIGNMENT, PVP_DRAFT_STAGE_WEAPONS}:
            self.set_postdraft_alignment_margins(0, 0)
            self.lock_postdraft_content_height(None)
        board = {} if post_draft_stage else session.board_dict()
        complete = True if post_draft_stage else _draft_is_complete(board)
        self.board_frame.setVisible(stage == PVP_DRAFT_STAGE_DRAFT)
        self.board_frame.setProperty("complete", complete)
        _refresh_qss(self.board_frame)
        self.order_strip.setVisible(stage == PVP_DRAFT_STAGE_DRAFT)
        self.order_strip.set_board(
            board,
            portrait_paths={
                character_id: _asset_image_path(asset)
                for character_id, asset in self._character_assets_by_id.items()
            },
        )

        if stage in {
            PVP_DRAFT_STAGE_ASSIGNMENT,
            PVP_DRAFT_STAGE_WEAPONS,
        }:
            self._draft_pool_frame = None
            self._draft_pool_info_label = None
            self._draft_pool_empty_label = None
            self.pool_grid = None
            self._refresh_scoped_build_source_scroll_stage()
        elif stage in {
            PVP_DRAFT_STAGE_TIMERS_RESULTS,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        }:
            self.source_zone_frames_by_seat.clear()
            self.source_body_widgets_by_seat.clear()
            self.source_header_labels_by_seat.clear()
            self._scoped_build_source_frame = None
            self._scoped_build_context_id = None
            self._draft_pool_frame = None
            self._draft_pool_info_label = None
            self._draft_pool_empty_label = None
            self.pool_grid = None
            self._detach_build_source_widgets()
            timers_widget = self._build_timers_results_stage(stage)
            if self.scroll_layout.indexOf(timers_widget) < 0:
                _clear_layout(self.scroll_layout)
                self.scroll_layout.addWidget(timers_widget)
                self.scroll_layout.addStretch(1)
        else:
            self.source_zone_frames_by_seat.clear()
            self.source_body_widgets_by_seat.clear()
            self.source_header_labels_by_seat.clear()
            self._scoped_build_source_frame = None
            self._scoped_build_context_id = None
            self._detach_build_source_widgets()
            self._timers_result_widget = None
            pool_frame = self._build_unified_pool(board, complete)
            if self.scroll_layout.indexOf(pool_frame) < 0:
                _clear_layout(self.scroll_layout)
                self.scroll_layout.addWidget(pool_frame)
                self.scroll_layout.addStretch(1)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_title_label.setText(tr("app_shell.pvp.draft.no_active_title"))
        self.empty_body_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self._refresh_pool_scope_texts()
        self.refresh()

    def refresh_player_colors(self) -> None:
        self.order_strip.update()
        for frame in self.source_zone_frames_by_seat.values():
            if isinstance(frame, PvpSeatAccentFrame):
                frame.refresh_player_color()
        for seat, label in self.source_header_labels_by_seat.items():
            _refresh_postdraft_seat_label_style(label, seat=seat)
        if self._timers_result_widget is not None:
            self._timers_result_widget.refresh_player_colors()
        self.refresh()

    def _build_unified_pool(
        self,
        board: Mapping[str, Any],
        draft_complete: bool,
    ) -> QFrame:
        self.pool_items_by_character_id.clear()
        self.legal_character_ids = ()
        self._draft_actions_by_character_id.clear()
        pool_frame = self._draft_pool_frame
        if pool_frame is None:
            pool_frame = QFrame()
            pool_frame.setObjectName("pvp_draft_pool_frame")
            layout = QVBoxLayout(pool_frame)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(7)

            scope_row = QHBoxLayout()
            scope_row.setContentsMargins(0, 0, 0, 0)
            scope_row.setSpacing(4)
            scope_group = QButtonGroup(pool_frame)
            scope_group.setExclusive(True)
            for scope in ("all", "player_1", "player_2"):
                button = QPushButton()
                button.setObjectName("pvp_draft_pool_scope")
                button.setCheckable(True)
                button.setChecked(scope == self._pool_scope)
                button.clicked.connect(
                    lambda _checked=False, value=scope: self._set_pool_scope(value)
                )
                scope_group.addButton(button)
                scope_row.addWidget(button)
                self._pool_scope_buttons[scope] = button
            scope_row.addStretch(1)
            layout.addLayout(scope_row)
            self._refresh_pool_scope_texts()

            self.character_filter_bar = CharacterFilterBar(pool_frame)
            self.character_filter_bar.filters_changed.connect(
                self._refresh_draft_pool_filters,
            )
            layout.addWidget(self.character_filter_bar)

            self._draft_pool_info_label = QLabel()
            self._draft_pool_info_label.setObjectName("small_muted")
            self._draft_pool_info_label.setWordWrap(True)
            layout.addWidget(self._draft_pool_info_label)

            self.pool_grid = PixelIconGrid(
                metrics=PixelIconGridMetrics(
                    item_width=72,
                    item_height=72,
                    gap_x=5,
                    gap_y=5,
                    margin_top=2,
                    margin_bottom=2,
                ),
                surface="pvp_draft_unified_pool",
            )
            self.pool_grid.setObjectName("pvp_draft_unified_pool_grid")
            self.pool_grid.item_clicked.connect(self._on_pool_item_clicked)
            layout.addWidget(self.pool_grid)

            self._draft_pool_empty_label = QLabel(tr("app_shell.pvp.draft.pool_empty"))
            self._draft_pool_empty_label.setObjectName("pvp_draft_pool_empty")
            self._draft_pool_empty_label.setWordWrap(True)
            layout.addWidget(self._draft_pool_empty_label)

            self._draft_pool_frame = pool_frame
        pool_frame.setProperty("active", not draft_complete)
        _refresh_qss(pool_frame)

        entries = self._filtered_draft_pool_entries(board)
        if self._draft_pool_info_label is not None:
            self._draft_pool_info_label.setText(_draft_unified_pool_summary(board, entries))
        if self._draft_pool_empty_label is not None:
            self._draft_pool_empty_label.setVisible(not entries)
        if self.pool_grid is not None:
            self.pool_grid.setVisible(bool(entries))

        if not entries:
            if self.pool_grid is not None:
                self.pool_grid.set_items(())
            return pool_frame

        items = []
        legal_ids: list[str] = []
        for entry_value in entries:
            entry = _mapping(entry_value)
            character_id = _text(entry.get("character_id"))
            item = build_pvp_draft_grid_item(
                entry,
                portrait_path=_asset_image_path(
                    self._character_assets_by_id.get(character_id),
                ),
            )
            items.append(item)
            self.pool_items_by_character_id[character_id] = item
            action = item.properties.get("action")
            if item.enabled and isinstance(action, Mapping) and action:
                legal_ids.append(character_id)
                self._draft_actions_by_character_id[character_id] = dict(action)
        if self.pool_grid is not None:
            self.pool_grid.set_items(items)
        self.legal_character_ids = tuple(legal_ids)
        return pool_frame

    def _set_pool_scope(self, scope: str) -> None:
        if scope not in {"all", "player_1", "player_2"} or scope == self._pool_scope:
            return
        self._pool_scope = scope
        self._refresh_draft_pool_filters()

    def _refresh_pool_scope_texts(self) -> None:
        labels = {
            "all": tr("app_shell.pvp.draft.pool_scope_all"),
            "player_1": tr("app_shell.pvp.draft.pool_scope_player_1"),
            "player_2": tr("app_shell.pvp.draft.pool_scope_player_2"),
        }
        for scope, button in self._pool_scope_buttons.items():
            button.setText(labels[scope])

    def _refresh_draft_pool_filters(self) -> None:
        if self._active_session is None:
            return
        board = self._active_session.board_dict()
        self._build_unified_pool(board, _draft_is_complete(board))

    def _filtered_draft_pool_entries(
        self,
        board: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        entries = _draft_main_pool_entries(board)
        if self._pool_scope != "all":
            entries = [
                entry
                for entry in entries
                if self._pool_scope in tuple(entry.get("owner_seats") or ())
            ]
        filters = self.character_filter_bar
        if filters is not None:
            entries = [
                entry
                for entry in entries
                if (
                    (asset := self._character_assets_by_id.get(_text(entry.get("character_id"))))
                    is not None
                    and character_matches_filters(
                        asset,
                        filters.element_filters,
                        filters.weapon_filters,
                        filters.rarity_filters,
                        trait_filters=filters.trait_filters,
                        standard_filter=filters.standard_filter,
                    )
                )
            ]
        entries.sort(
            key=lambda entry: character_sort_key(
                self._character_assets_by_id.get(_text(entry.get("character_id")), {})
            )
        )
        return entries

    def click_legal_character_for_test(self, character_id: str | None = None) -> bool:
        target = character_id or (self.legal_character_ids[0] if self.legal_character_ids else "")
        return bool(self.pool_grid and target and self.pool_grid.click_item_for_test(target))

    def _on_pool_item_clicked(self, character_id: str) -> None:
        action = self._draft_actions_by_character_id.get(character_id)
        if action:
            self.card_clicked.emit(dict(action))

    def _detach_build_source_widgets(self) -> None:
        context = self._build_flow_context
        if context is None:
            return
        for seat_context in getattr(context, "seats", {}).values():
            source = getattr(seat_context, "source_workspace", None)
            if source is not None:
                # Keep the live source workspace inside the PvP workspace while
                # its old section is deleted. Reparenting a visible QWidget to
                # None briefly promotes it to a top-level Qt window.
                source.hide()
                source.setParent(self)

    def set_postdraft_alignment_margins(self, top: int, bottom: int) -> None:
        desired = (0, max(0, int(top)), 0, max(0, int(bottom)))
        margins = self.scroll_layout.contentsMargins()
        current = (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )
        if current != desired:
            self.scroll_layout.setContentsMargins(*desired)
            self.scroll_layout.invalidate()
            self.scroll_layout.activate()

    def lock_postdraft_content_height(self, height: int | None) -> None:
        if height is None:
            self.scroll_content.setMinimumHeight(0)
            self.scroll_content.setMaximumHeight(16777215)
            self.scroll_content.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            return
        self.scroll_content.setFixedHeight(max(1, int(height)))
        self.scroll_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.scroll_area.verticalScrollBar().setValue(0)

    def _refresh_scoped_build_source_scroll_stage(self) -> None:
        context_id = id(self._build_flow_context) if self._build_flow_context else None
        if (
            self._scoped_build_source_frame is not None
            and self._scoped_build_context_id == context_id
            and self.scroll_layout.indexOf(self._scoped_build_source_frame) >= 0
        ):
            self._update_scoped_build_source_stage()
            return
        self.source_zone_frames_by_seat.clear()
        self.source_body_widgets_by_seat.clear()
        self.source_header_labels_by_seat.clear()
        self._scoped_build_source_frame = None
        self._scoped_build_context_id = context_id
        self._detach_build_source_widgets()
        _clear_layout(self.scroll_layout)
        self.scroll_layout.addWidget(self._build_scoped_build_source_stage(), 1)

    def _build_scoped_build_source_stage(self) -> QFrame:
        frame = QFrame(self.scroll_content)
        frame.setObjectName("pvp_scoped_build_source_frame")
        self._scoped_build_source_frame = frame
        self._scoped_build_context_id = id(self._build_flow_context) if self._build_flow_context else None
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(PVP_POSTDRAFT_SECTION_SPACING)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        context = self._build_flow_context
        if context is None:
            empty = QLabel(tr("app_shell.pvp.post.build_context_missing"))
            empty.setObjectName("small_muted")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return frame
        for seat in PVP_SEATS:
            seat_context = context.seat(seat)
            if seat_context is None:
                continue
            section = PvpSeatAccentFrame(
                seat,
                frame,
                object_name=_postdraft_source_object_name(seat),
            )
            section.setProperty("seat", seat)
            section.setProperty("scopedBuildSource", True)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(PVP_POSTDRAFT_SECTION_SPACING)

            header = _configure_postdraft_seat_label(
                QLabel(section),
                seat=seat,
            )
            section_layout.addWidget(header)
            self.source_header_labels_by_seat[seat] = header

            body = QWidget(section)
            body.setObjectName("pvp_postdraft_source_body")
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(8, 0, 8, 8)
            body_layout.setSpacing(0)
            source = seat_context.source_workspace
            source.setParent(body)
            body_layout.addWidget(source, 1)
            section_layout.addWidget(body, 1)
            collapsed = seat in context.collapsed_seats
            layout.addWidget(section, 0 if collapsed else 1)
            # Keep the heavy child logically shown and collapse only its body
            # wrapper. Explicitly hiding/showing the grid child itself
            # schedules an unnecessary delayed grid reload on every expand.
            source.show()
            self.source_zone_frames_by_seat[seat] = section
            self.source_body_widgets_by_seat[seat] = body
            body.setVisible(not collapsed)
            section.setVisible(True)
            self._sync_scoped_source_zone_size(section, collapsed)
        return frame

    def _update_scoped_build_source_stage(self) -> None:
        context = self._build_flow_context
        if context is None:
            return
        for seat in PVP_SEATS:
            seat_context = context.seat(seat)
            section = self.source_zone_frames_by_seat.get(seat)
            body = self.source_body_widgets_by_seat.get(seat)
            if seat_context is None or section is None or body is None:
                self._scoped_build_source_frame = None
                self._refresh_scoped_build_source_scroll_stage()
                return
            collapsed = seat in context.collapsed_seats
            body.setVisible(not collapsed)
            section.setVisible(True)
            self._sync_scoped_source_zone_size(section, collapsed)
            if self._scoped_build_source_frame is not None:
                source_layout = self._scoped_build_source_frame.layout()
                section_index = source_layout.indexOf(section) if source_layout else -1
                if section_index >= 0:
                    source_layout.setStretch(section_index, 0 if collapsed else 1)
                    source_layout.invalidate()
                    source_layout.activate()
            source = seat_context.source_workspace
            if source.parent() is not body:
                source.hide()
                source.setParent(body)
                source.show()

    @staticmethod
    def _sync_scoped_source_zone_size(section: QFrame, collapsed: bool) -> None:
        if collapsed:
            section.setMinimumHeight(PVP_POSTDRAFT_HEADER_HEIGHT)
            section.setMaximumHeight(PVP_POSTDRAFT_HEADER_HEIGHT)
            section.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            return
        section.setMinimumHeight(0)
        section.setMaximumHeight(16777215)
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def _build_timers_results_stage(self, stage: str) -> PvpTimersResultWidget:
        if self._timers_result_widget is None:
            self._timers_result_widget = PvpTimersResultWidget()
            self._timers_result_widget.timer_text_changed.connect(
                self.timer_text_changed,
            )
            self._timers_result_widget.finalize_requested.connect(
                self.finalize_result_requested,
            )
        timer_texts = _mapping(self._view_state.get("timer_texts"))
        result = self._view_state.get("result")
        self._timers_result_widget.set_state(
            completed=stage == PVP_DRAFT_STAGE_COMPLETED_RESULT,
            timer_texts=timer_texts,
            result=result if isinstance(result, Mapping) else None,
            source_data=self._abyss_source_data,
        )
        return self._timers_result_widget

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
        abyss_source_data_provider: Callable[[], AbyssFloorSourceData | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PvpWorkspace")
        self.db_path = Path(db_path)
        self.deck_dir = resolve_deck_preset_dir(deck_dir)
        self._abyss_source_data_provider = (
            abyss_source_data_provider or load_current_cached_abyss_floor_source_data
        )
        self._abyss_source_data_loaded = False
        self._abyss_source_data: AbyssFloorSourceData | None = None
        self.active_page_id = PVP_PAGE_DECKS
        self.active_draft_session: PvpActiveDraftSession | None = None
        self._last_play_status = ""
        self._last_draft_status = ""
        self.draft_stage = PVP_DRAFT_STAGE_DRAFT
        self.build_flow_context: Any | None = None
        self._local_profile_provider = LocalPvpProfileProvider(
            source_db_path=self.db_path,
            deck_dir=self.deck_dir,
        )
        self._profile_providers_by_seat: dict[str, PvpProfileProvider] = {
            seat: self._local_profile_provider
            for seat in PVP_SEATS
        }
        self._profile_assets_by_seat: dict[
            str,
            tuple[list[dict[str, Any]], list[dict[str, Any]]],
        ] = {}
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
            db_path=self.db_path,
            deck_dir=self.deck_dir,
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
        self.draft_workspace.timer_text_changed.connect(self.set_timer_text)
        self.draft_workspace.finalize_result_requested.connect(
            self.finalize_match_result,
        )
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
        for seat, provider in self._profile_providers_by_seat.items():
            if provider is self._local_profile_provider:
                self._profile_assets_by_seat.pop(seat, None)
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

    def seat_profile_provider(self, seat: str) -> PvpProfileProvider:
        return self._profile_providers_by_seat.get(
            seat,
            self._local_profile_provider,
        )

    def seat_profile_is_imported(self, seat: str) -> bool:
        return isinstance(
            self.seat_profile_provider(seat),
            ImportedPvpProfileProvider,
        )

    def seat_profile_label(self, seat: str) -> str:
        provider = self.seat_profile_provider(seat)
        if isinstance(provider, ImportedPvpProfileProvider):
            manifest = provider.profile.manifest
            return (
                _text(manifest.get("nickname"))
                or _text(manifest.get("player_label"))
                or provider.profile.path.stem
            )
        return tr("app_shell.pvp.profile.local")

    def import_profile_for_seat(self, seat: str, package_path: str | Path) -> bool:
        if seat not in PVP_SEATS or self.active_draft_session is not None:
            return False
        try:
            profile = import_pvp_profile_package(package_path)
        except Exception as exc:
            self._last_play_status = str(exc) or exc.__class__.__name__
            self.state_changed.emit()
            return False
        previous = self._profile_providers_by_seat.get(seat)
        self._profile_providers_by_seat[seat] = ImportedPvpProfileProvider(profile)
        self._profile_assets_by_seat.pop(seat, None)
        if previous is not None and previous is not self._local_profile_provider:
            close = getattr(previous, "close", None)
            if callable(close):
                close()
        self._last_play_status = tr("app_shell.pvp.profile.imported").format(
            seat=_seat_label(seat),
            profile=self.seat_profile_label(seat),
        )
        self._sync_play_workspace()
        self.state_changed.emit()
        return True

    def use_local_profile_for_seat(self, seat: str) -> None:
        if seat not in PVP_SEATS or self.active_draft_session is not None:
            return
        previous = self._profile_providers_by_seat.get(seat)
        self._profile_providers_by_seat[seat] = self._local_profile_provider
        self._profile_assets_by_seat.pop(seat, None)
        if previous is not None and previous is not self._local_profile_provider:
            close = getattr(previous, "close", None)
            if callable(close):
                close()
        self._last_play_status = ""
        self._sync_play_workspace()
        self.state_changed.emit()

    def play_deck_options(self, seat: str = "player_1") -> tuple[PvpDeckPreset, ...]:
        provider = self.seat_profile_provider(seat)
        if provider is self._local_profile_provider:
            return tuple(self.decks_workspace.presets)
        return tuple(provider.load_deck_presets())

    def _profile_assets(
        self,
        seat: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        provider = self.seat_profile_provider(seat)
        if provider is self._local_profile_provider:
            return (
                list(self.decks_workspace.character_assets),
                list(self.decks_workspace.weapon_assets),
            )
        cached = self._profile_assets_by_seat.get(seat)
        if cached is None:
            cached = (
                list(load_account_character_asset_items(db_path=provider.db_path)),
                list(load_account_weapon_stack_asset_items(db_path=provider.db_path)),
            )
            self._profile_assets_by_seat[seat] = cached
        return (list(cached[0]), list(cached[1]))

    def _seat_preset_by_id(self, seat: str, deck_id: str) -> PvpDeckPreset | None:
        for preset in self.play_deck_options(seat):
            if preset.deck_id == deck_id:
                return preset
        return None

    def default_player_1_deck_id(self) -> str:
        presets = self.play_deck_options("player_1")
        selected_id = (
            self.decks_workspace.selected_deck_id
            if not self.seat_profile_is_imported("player_1")
            else ""
        )
        if selected_id and self._seat_preset_by_id("player_1", selected_id) is not None:
            return selected_id
        for preset in presets:
            status = self.deck_start_status(
                preset.deck_id,
                player_label="Player 1",
                seat="player_1",
            )
            if status.ready:
                return preset.deck_id
        return presets[0].deck_id if presets else ""

    def default_player_2_deck_id(self, player_1_deck_id: str = "") -> str:
        presets = self.play_deck_options("player_2")
        if not presets:
            return ""
        if (
            len(presets) == 1
            and self.seat_profile_provider("player_1")
            is self.seat_profile_provider("player_2")
        ):
            return player_1_deck_id or presets[0].deck_id
        return presets[0].deck_id

    def deck_start_status(
        self,
        deck_id: str,
        *,
        player_label: str,
        seat: str = "player_1",
    ) -> PvpDeckStartStatus:
        preset = self._seat_preset_by_id(seat, deck_id)
        if preset is None:
            return PvpDeckStartStatus(
                preset=None,
                draft_deck=None,
                report=None,
                text=tr("app_shell.pvp.play.deck_missing"),
                ready=False,
            )
        try:
            character_assets, weapon_assets = self._profile_assets(seat)
            draft_deck = deck_preset_to_draft_deck(
                preset,
                character_assets,
                weapon_assets,
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
            self.deck_start_status(
                player_1_deck_id,
                player_label="Player 1",
                seat="player_1",
            ).ready
            and self.deck_start_status(
                player_2_deck_id,
                player_label="Player 2",
                seat="player_2",
            ).ready
        )

    def start_local_draft(self, player_1_deck_id: str, player_2_deck_id: str) -> bool:
        player_1_status = self.deck_start_status(
            player_1_deck_id,
            player_label="Player 1",
            seat="player_1",
        )
        player_2_status = self.deck_start_status(
            player_2_deck_id,
            player_label="Player 2",
            seat="player_2",
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
            if (
                player_1_deck_id == player_2_deck_id
                and self.seat_profile_provider("player_1")
                is self.seat_profile_provider("player_2")
            )
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
            session.controller.apply_current_action(
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

        self._last_draft_status = ""
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
        if self._ensure_build_flow_context() is None:
            self._last_draft_status = tr("app_shell.pvp.post.build_context_missing")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self.draft_stage = PVP_DRAFT_STAGE_ASSIGNMENT
        self._last_draft_status = ""
        self._sync_draft_workspace()
        self.state_changed.emit()
        return True

    def _ensure_build_flow_context(self) -> Any | None:
        if self.build_flow_context is not None:
            return self.build_flow_context
        session = self.active_draft_session
        if session is None:
            return None
        from ui.pvp_browser.build_flow import PvpBuildFlowContext

        context = PvpBuildFlowContext.from_draft_session(
            session,
            db_path=self.db_path,
            deck_dir=self.deck_dir,
            character_assets=self.character_assets,
            weapon_assets=self.weapon_assets,
            providers_by_seat={
                seat: self.seat_profile_provider(seat)
                for seat in PVP_SEATS
            },
            character_assets_by_seat={
                seat: self._profile_assets(seat)[0]
                for seat in PVP_SEATS
            },
            weapon_assets_by_seat={
                seat: self._profile_assets(seat)[1]
                for seat in PVP_SEATS
            },
            parent=self.draft_workspace,
        )
        for seat, seat_context in context.seats.items():
            seat_context.source_workspace.character_clicked.connect(
                lambda _asset, s=seat: self._on_build_source_changed(s)
            )
            seat_context.source_workspace.weapon_clicked.connect(
                lambda _asset, s=seat: self._on_build_source_changed(s)
            )
        self.build_flow_context = context
        return context

    def _on_build_source_changed(self, seat: str) -> None:
        context = self.build_flow_context
        if context is not None:
            context.set_active_seat(seat)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def build_source_workspace(self, seat: str):
        context = self.build_flow_context
        seat_context = context.seat(seat) if context is not None else None
        return None if seat_context is None else seat_context.source_workspace

    def handle_build_character_clicked(self, seat: str, asset: Mapping[str, Any]) -> bool:
        context = self.build_flow_context
        seat_context = context.seat(seat) if context is not None else None
        if seat_context is None:
            return False
        changed = seat_context.add_or_replace_character(dict(asset))
        if changed:
            context.set_active_seat(seat)
            self._sync_draft_workspace()
            self.state_changed.emit()
        return changed

    def handle_build_weapon_clicked(self, seat: str, asset: Mapping[str, Any]) -> bool:
        context = self.build_flow_context
        seat_context = context.seat(seat) if context is not None else None
        if seat_context is None:
            return False
        changed = seat_context.assign_weapon_to_selected_slot(dict(asset))
        if changed:
            context.set_active_seat(seat)
            self._sync_draft_workspace()
            self.state_changed.emit()
        return changed

    def handle_build_slot_clicked(
        self,
        seat: str,
        team_index: int,
        slot_index: int,
    ) -> None:
        context = self.build_flow_context
        seat_context = context.seat(seat) if context is not None else None
        if seat_context is None:
            return
        context.set_active_seat(seat)
        seat_context.toggle_slot_selection(team_index, slot_index)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def handle_build_slot_dropped(
        self,
        seat: str,
        source_team_index: int,
        source_slot_index: int,
        target_team_index: int,
        target_slot_index: int,
    ) -> bool:
        context = self.build_flow_context
        seat_context = context.seat(seat) if context is not None else None
        if seat_context is None:
            return False
        changed = seat_context.swap_slots(
            source_team_index,
            source_slot_index,
            target_team_index,
            target_slot_index,
        )
        if changed:
            context.set_active_seat(seat)
            self._sync_draft_workspace()
            self.state_changed.emit()
        return changed

    def is_build_seat_collapsed(self, seat: str) -> bool:
        context = self.build_flow_context
        return bool(context is not None and seat in context.collapsed_seats)

    def toggle_build_seat_collapsed(self, seat: str) -> None:
        context = self.build_flow_context
        if context is None:
            return
        context.toggle_collapsed(seat)
        context.set_active_seat(seat)
        self._sync_draft_workspace()
        self.state_changed.emit()

    def ready_build_seat(self, seat: str) -> bool:
        context = self.build_flow_context
        session = self.active_draft_session
        if context is None or session is None:
            return False
        context.set_active_seat(seat)
        if not context.commit_ready(seat, session.controller):
            seat_context = context.seat(seat)
            code = "" if seat_context is None else seat_context.last_error
            self._last_draft_status = tr("app_shell.pvp.post.ready_invalid").format(
                code=_pvp_ready_error_text(code),
            )
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self._last_draft_status = ""
        if context.both_ready():
            self.draft_stage = PVP_DRAFT_STAGE_TIMERS_RESULTS
        self._sync_play_workspace()
        self._sync_draft_workspace()
        self.active_draft_changed.emit()
        self.state_changed.emit()
        return True

    def assignment_ready(self) -> bool:
        return bool(
            self.build_flow_context is not None
            and all(
                self.build_flow_context.ready_candidate(seat)
                for seat in PVP_SEATS
            )
        )

    def weapons_ready(self) -> bool:
        return bool(
            self.build_flow_context is not None
            and self.build_flow_context.both_ready()
        )

    def continue_to_timers(self) -> bool:
        if self.build_flow_context is None or not self.build_flow_context.both_ready():
            self._last_draft_status = tr("app_shell.pvp.post.ready_required")
            self._sync_draft_workspace()
            self.state_changed.emit()
            return False
        self.draft_stage = PVP_DRAFT_STAGE_TIMERS_RESULTS
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
            _parse_pvp_remaining_timer_text(
                self.timer_texts_by_seat[seat][index]
            )
            is not None
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
                        elapsed_seconds=ABYSS_CHAMBER_START_SECONDS
                        - (
                            _parse_pvp_remaining_timer_text(
                                self.timer_texts_by_seat[seat][index],
                            )
                            or ABYSS_CHAMBER_START_SECONDS
                        ),
                    )
                    for index in range(len(PVP_TIMER_CHAMBERS))
                ),
            )
            for seat in PVP_SEATS
        }
        session.controller.set_match_timers(timers["player_1"], timers["player_2"])
        self.draft_stage = PVP_DRAFT_STAGE_COMPLETED_RESULT
        self._last_draft_status = ""
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
        self._dispose_build_flow_context()
        self.timer_texts_by_seat = {
            seat: [""] * len(PVP_TIMER_CHAMBERS)
            for seat in PVP_SEATS
        }
        self._abyss_source_data_loaded = False
        self._abyss_source_data = None

    def _dispose_build_flow_context(self) -> None:
        context = self.build_flow_context
        self.build_flow_context = None
        if context is None:
            return
        for seat_context in getattr(context, "seats", {}).values():
            source = getattr(seat_context, "source_workspace", None)
            if source is not None:
                source.hide()
                source.setParent(self)
                source.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._dispose_build_flow_context()
        closed: set[int] = set()
        for provider in self._profile_providers_by_seat.values():
            if provider is self._local_profile_provider or id(provider) in closed:
                continue
            closed.add(id(provider))
            close = getattr(provider, "close", None)
            if callable(close):
                close()
        super().closeEvent(event)

    def _draft_view_state(self) -> dict[str, Any]:
        assignment_slots = {
            seat: [[None for _slot in range(4)] for _team in range(2)]
            for seat in PVP_SEATS
        }
        weapon_assignments = {seat: {} for seat in PVP_SEATS}
        build_status: dict[str, Any] = {}
        if self.build_flow_context is not None:
            build_status = self.build_flow_context.status_snapshot()
            for seat in PVP_SEATS:
                seat_context = self.build_flow_context.seat(seat)
                if seat_context is None:
                    continue
                assignment = seat_context.team_assignment()
                assignment_slots[seat] = [
                    list(team.character_ids)
                    for team in sorted(assignment.teams, key=lambda item: item.team_index)
                ]
                weapon_assignments[seat] = {
                    item.character_id: item.weapon_stack_key
                    for item in seat_context.weapon_assignment().assignments
                }
        return {
            "stage": self.draft_stage,
            "assignment_slots": assignment_slots,
            "weapon_assignments": weapon_assignments,
            "timer_texts": {
                seat: list(self.timer_texts_by_seat[seat])
                for seat in PVP_SEATS
            },
            "build_status": build_status,
            "result": (
                self.active_draft_session.controller.state.match_result.to_dict()
                if self.active_draft_session is not None
                and self.active_draft_session.controller.state.match_result is not None
                else None
            ),
        }

    def _current_abyss_source_data(self) -> AbyssFloorSourceData | None:
        if not self._abyss_source_data_loaded:
            self._abyss_source_data_loaded = True
            self._abyss_source_data = self._abyss_source_data_provider()
        return self._abyss_source_data

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
            build_flow_context=self.build_flow_context,
            abyss_source_data=(
                self._current_abyss_source_data()
                if self.draft_stage in {
                    PVP_DRAFT_STAGE_TIMERS_RESULTS,
                    PVP_DRAFT_STAGE_COMPLETED_RESULT,
                }
                else None
            ),
        )


def _pvp_ready_error_text(codes_text: str) -> str:
    codes = [code.strip() for code in str(codes_text or "").split(",") if code.strip()]
    if not codes:
        return tr("app_shell.pvp.post.ready_issue.invalid")
    unique_codes = tuple(dict.fromkeys(codes))
    if len(unique_codes) == 1:
        code = unique_codes[0]
        key = f"app_shell.pvp.post.ready_issue.{code}"
        text = tr(key)
        if text != key:
            if len(codes) > 1:
                return tr("app_shell.pvp.post.ready_issue.repeated").format(
                    issue=text,
                    count=len(codes),
                )
            return text
    return tr("app_shell.pvp.post.ready_issue.multiple")















from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from ui.right_panel.pvp.host import PvpRightPanelHost
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


__all__ = [
    "PVP_PAGE_DECKS",
    "PVP_PAGE_DRAFT",
    "PVP_PAGE_PLAY",
    "PvpActiveDraftSession",
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
