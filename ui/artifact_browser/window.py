from __future__ import annotations

import html
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QSize, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from hoyolab_export.paths import PROJECT_ROOT
from hoyolab_export.character_region_catalog import (
    REGION_ICON_FILES,
    REGION_LABEL_KEYS,
    REGION_ORDER,
    load_character_region_catalog,
    normalize_character_name,
)
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    CHARACTER_STANDARD_FILTER,
    CHARACTER_TRAIT_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    STANDARD_FILTER_ALL,
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    WEAPON_TYPE_FILTERS,
    character_id,
    character_matches_filters,
    character_name,
    character_sort_key,
    load_account_character_asset_items,
    standard_character_filter_icon,
)
from ui.utils.icon_utils import auto_contrast_svg_icon, auto_contrast_svg_pixmap
from ui.utils.drag_scroll import DragScrollArea
from ui.utils.filter_button_style import (
    FILTER_BUTTON_BORDER_WIDTH,
    FILTER_BUTTON_ICON_SIZE,
    FILTER_BUTTON_PADDING,
    FILTER_BUTTON_SIZE,
    filter_button_style,
)
from ui.utils.marquee_label import MarqueeButton
from ui.utils.pixmap_utils import (
    count_badge_style_cache_key,
    draw_count_badge,
    load_persistent_pixmap,
    make_diagonal_split_pixmap,
    pixmap_cache_key_digest,
    save_persistent_pixmap,
    scale_trimmed_pixmap_to_size,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_BG_APP, UI_TEXT_PRIMARY
from run_workspace.perf import log_perf, perf_ms, perf_now
from ui.utils.overlay_scroll import (
    OverlayVerticalScrollArea,
    install_overlay_vertical_scrollbar,
)
from hoyolab_export.account_equipment import (
    ARTIFACT_POS_BY_SLOT_KEY,
    EquipmentChangeResult,
    EquipmentError,
    equip_artifact,
    get_equipped_artifact_owner,
    list_equipped_artifacts_for_character,
    unequip_artifact_slot,
)
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db
from .list_model import ArtifactRoles
from .queries import (
    calculate_build_summary,
    create_custom_set,
    delete_custom_set,
    get_custom_set_artifact_ids,
    get_build_preset,
    list_build_presets,
    replace_custom_set_artifacts,
    save_build_preset,
    delete_build_preset,
)
from .card_delegate import ArtifactCardDelegate, GRID_SIZE
from .filter_popup import SetsFilterPopup
from .json_import_actions import (
    json_imports_available,
    run_artiscan_import_action,
    run_clear_json_imports_action,
)
from .list_model import ArtifactListModel
from .models import ARTIFACT_POSITIONS
from .region_popup import RegionFilterPopup
from .store import ArtifactBrowserStore
from .sort_popup import SortStatsPopup
from .stat_types import (
    ANEMO_DAMAGE,
    ATK_FLAT,
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    CRYO_DAMAGE,
    DEF_PERCENT,
    DEF_FLAT,
    DENDRO_DAMAGE,
    ELECTRO_DAMAGE,
    ELEMENTAL_MASTERY,
    ENERGY_RECHARGE,
    GEO_DAMAGE,
    HEALING_BONUS,
    HP_FLAT,
    HP_PERCENT,
    HYDRO_DAMAGE,
    PHYSICAL_DAMAGE,
    PYRO_DAMAGE,
    stat_badge,
)
from localization import tr

TARGET_PANEL_WIDTH = 144
TARGET_PANEL_MIN_WIDTH = 144
TARGET_PANEL_MAX_WIDTH = 410
TARGET_PANEL_MARGINS = (0, 8, 5, 8)
TARGET_PANEL_SPACING = 6
BUILD_PANEL_WIDTH = 384
ARTIFACT_GRID_FIT_PADDING = 4
ARTIFACT_LIST_MIN_WIDTH = GRID_SIZE.width() + ARTIFACT_GRID_FIT_PADDING
CONTENT_LAYOUT_SPACING = 0
CONTENT_TARGET_BUILD_SPACING = 4
ADAPTIVE_TARGET_RESIZE_DELAY_MS = 650
ADAPTIVE_TARGET_RESIZE_SETTLE_MS = 40

TARGET_HEADER_SPACING = 4
TARGET_HEADER_LEFT_INSET = 5
TARGET_HEADER_BALANCE_WIDTH = 72
TARGET_RESET_BUTTON_WIDTH = 30
TARGET_RESET_BUTTON_MIN_HEIGHT = 24
TARGET_RESET_BUTTON_PADDING_VERTICAL = 2
TARGET_RESET_BUTTON_PADDING_HORIZONTAL = 8
TARGET_RESET_BUTTON_RADIUS = 6

TARGET_BODY_SPACING = 0
TARGET_TITLE_MIN_WIDTH = 54

TARGET_FILTER_BUTTON_SIZE = FILTER_BUTTON_SIZE
TARGET_FILTER_ICON_SIZE = FILTER_BUTTON_ICON_SIZE
TARGET_FILTER_CONTENT_SIZE = TARGET_FILTER_BUTTON_SIZE - 2 * (
    FILTER_BUTTON_BORDER_WIDTH + FILTER_BUTTON_PADDING
)
TARGET_FILTER_BUTTON_STYLE = filter_button_style(
    "target_filter_button",
    content_size=TARGET_FILTER_CONTENT_SIZE,
)
TARGET_FILTER_LANE_EXTRA = 5
TARGET_FILTER_LANE_WIDTH = TARGET_FILTER_BUTTON_SIZE + TARGET_FILTER_LANE_EXTRA
TARGET_FILTER_LANE_INSET_LEFT = TARGET_FILTER_LANE_EXTRA // 2
TARGET_FILTER_LANE_INSET_RIGHT = TARGET_FILTER_LANE_EXTRA - TARGET_FILTER_LANE_INSET_LEFT
TARGET_FILTER_SPACING = 4

TARGET_ITEM_MIN_HEIGHT = 34
TARGET_ITEM_BORDER_WIDTH = 1
TARGET_ITEM_PADDING_VERTICAL = 0
TARGET_ITEM_PADDING_HORIZONTAL = 0
TARGET_ITEM_BUTTON_HEIGHT = 44
TARGET_ITEM_CONTENT_HEIGHT = TARGET_ITEM_BUTTON_HEIGHT - TARGET_ITEM_BORDER_WIDTH * 2
TARGET_ITEM_ICON_SIZE = TARGET_ITEM_CONTENT_HEIGHT
TARGET_ITEM_MIN_WIDTH = 88

TARGET_ITEM_SPACING = 4


@dataclass(frozen=True)
class AssignmentWidthFit:
    columns: int
    assignment_width: int
    artifact_viewport_width: int
    remainder: int
    total_used_width: int


def calculate_assignment_width_fit(
    *,
    content_width: int,
    preset_panel_width: int,
    fixed_internal_gaps: int,
    assignment_min_width: int,
    column_step: int,
) -> AssignmentWidthFit | None:
    content_width = int(content_width)
    preset_panel_width = int(preset_panel_width)
    fixed_internal_gaps = int(fixed_internal_gaps)
    assignment_min_width = int(assignment_min_width)
    column_step = int(column_step)

    if (
        content_width <= 0
        or preset_panel_width < 0
        or fixed_internal_gaps < 0
        or assignment_min_width <= 0
        or column_step <= 0
    ):
        return None

    available = content_width - preset_panel_width - fixed_internal_gaps
    max_artifact_width = available - assignment_min_width
    if max_artifact_width < column_step:
        return None

    columns, remainder = divmod(max_artifact_width, column_step)
    if columns <= 0:
        return None

    artifact_viewport_width = columns * column_step
    assignment_width = assignment_min_width + remainder
    total_used_width = (
        preset_panel_width
        + fixed_internal_gaps
        + assignment_width
        + artifact_viewport_width
    )
    if assignment_width < assignment_min_width or total_used_width > content_width:
        return None

    return AssignmentWidthFit(
        columns=columns,
        assignment_width=assignment_width,
        artifact_viewport_width=artifact_viewport_width,
        remainder=remainder,
        total_used_width=total_used_width,
    )


class AdaptiveAssignmentPanel(QFrame):
    def __init__(self, minimum_width: int, preferred_width: int, parent=None):
        super().__init__(parent)
        self._preferred_width = max(int(minimum_width), int(preferred_width))
        self.setMinimumWidth(int(minimum_width))
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

    def set_preferred_width(self, width: int) -> None:
        width = max(self.minimumWidth(), int(width))
        if self._preferred_width == width:
            return
        self._preferred_width = width
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        hint.setWidth(self._preferred_width)
        return hint

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        hint.setWidth(self.minimumWidth())
        return hint


class AdaptiveJsonActionRow(QWidget):
    def __init__(self, minimum_width: int, preferred_width: int, parent=None):
        super().__init__(parent)
        self._preferred_width = max(int(minimum_width), int(preferred_width))
        self.setMinimumWidth(int(minimum_width))
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

    def set_preferred_width(self, width: int) -> None:
        width = max(self.minimumWidth(), int(width))
        if self._preferred_width == width:
            return
        self._preferred_width = width
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        hint.setWidth(self._preferred_width)
        return hint

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        hint.setWidth(self.minimumWidth())
        return hint

BUILD_TARGET_PREVIEW_ROW_HEIGHT = 40
BUILD_TARGET_PREVIEW_SPACING = 0
BUILD_TARGET_PREVIEW_ICON_SIZE = 40
BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_SIZE = 36
BUILD_TARGET_PREVIEW_HINT_WIDTH = 32
BUILD_TARGET_PREVIEW_HINT_ICON_SIZE = 20
BUILD_TARGET_PREVIEW_EDGE_BACKGROUND = QColor(0, 0, 0)
BUILD_TARGET_PREVIEW_UNIVERSAL_BG_PATH = (
    PROJECT_ROOT / "assets" / "ui" / "bg" / "bg_4-5.png"
)
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND = "#40577a"
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BORDER = "#475066"
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_RADIUS = 8
BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_OFFSET_Y = 4
BUILD_TARGET_PREVIEW_CACHE_VERSION = "target_preview_strip_v1"
BUILD_TARGET_PREVIEW_ICON_CACHE_DIR = (
    PROJECT_ROOT / "data" / "cache" / "ui" / "target_preview_icons"
)
BUILD_TARGET_PREVIEW_STRIP_CACHE_DIR = (
    PROJECT_ROOT / "data" / "cache" / "ui" / "target_preview_strips"
)
UI_ICON_BUTTON_BACKGROUND = "#222630"
UI_ICON_DEFAULT_SIZE = 24

PANEL_TITLE_STYLE = f"""
QLabel#panel_title {{
    color: {UI_TEXT_PRIMARY};
    font-weight: 700;
    font-size: 14px;
    background: transparent;
    border: none;
    padding: 0;
    qproperty-alignment: 'AlignCenter';
}}
"""

WINDOW_STYLE = """
QWidget {
    background: #17191f;
    color: #eeeeee;
    font-size: 13px;
}
QPushButton {
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid #3d4350;
    border-radius: 8px;
    background: #222630;
    color: #eeeeee;
}
QPushButton:hover {
    background: #2b303b;
}
QPushButton:checked {
    border-color: #7da7ff;
    background: #303848;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#filter_switch {
    min-width: 42px;
    max-width: 42px;
}
QPushButton#filter_switch:checked {
    border-color: #7da7ff;
    background: #30415f;
}
QPushButton#sets_button {
    min-width: 110px;
}
QLabel#status_label {
    color: #aab0bd;
    background: transparent;
}
QFrame#equipment_zone {
    border: 1px solid #343b49;
    border-radius: 8px;
    background: #20242d;
}
QFrame#equipment_zone[equipMode="true"] {
    border-color: #7dd7b7;
    background: #1f302d;
}
QLabel#equipment_target_label {
    color: #cbd3df;
    font-size: 12px;
}
QLabel#equipment_zone_label {
    color: #ffffff;
    font-weight: 700;
    background: transparent;
    qproperty-alignment: 'AlignCenter';
}
QPushButton#equipment_zone_action_button {
    min-height: 30px;
    padding: 4px 10px;
    font-weight: 800;
}
QPushButton#equipment_zone_action_button:disabled {
    color: #798291;
    background: #222630;
    border-color: #343b49;
}
QFrame#top_bar {
    border: 1px solid #2b3039;
    border-radius: 10px;
    background: #1f222a;
}
QListView {
    border: none;
    outline: none;
    background: #17191f;
}
QListView[artifactEditMode="true"] {
    background: #203861;
    border: 1px solid #4f8ee8;
    border-radius: 8px;
}
QListView::item {
    background: transparent;
}
QLineEdit {
    min-height: 28px;
    padding: 4px 8px;
    border: 1px solid #3d4350;
    border-radius: 6px;
    background: #17191f;
    color: #eeeeee;
}
QPushButton#json_edit_save_button {
    border-color: #4e9b61;
    background: #24452d;
}
QPushButton#json_edit_save_button:hover {
    background: #2d5938;
}
QPushButton#json_edit_cancel_button {
    border-color: #b85b5b;
    background: #4a2529;
}
QPushButton#json_edit_cancel_button:hover {
    background: #5c2d32;
}
QPushButton#row_save_button {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
    border-color: #4e9b61;
    background: #24452d;
}
QPushButton#row_save_button:hover {
    background: #2d5938;
}
QPushButton#row_cancel_button {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
    border-color: #b85b5b;
    background: #4a2529;
}
QPushButton#row_cancel_button:hover {
    background: #5c2d32;
}
QFrame#build_panel {
    border: 1px solid #2b3039;
    border-radius: 10px;
    background: #1f222a;
}
QFrame#build_target_panel {
    border: 1px solid #2b3039;
    border-radius: 10px;
    background: #1f222a;
}
""" + PANEL_TITLE_STYLE + """
QLabel#target_panel_title,
QPushButton#target_panel_title {
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
    background: transparent;
    border: none;
    padding: 0;
}
""" + TARGET_FILTER_BUTTON_STYLE + f"""
QWidget#build_target_preview_strip {{
    background: {UI_BG_APP};
    border: none;
}}
QLabel#build_target_preview_content {{
    background: transparent;
    border: none;
}}
QPushButton#target_item {{
    min-height: {TARGET_ITEM_CONTENT_HEIGHT}px;
    max-height: {TARGET_ITEM_CONTENT_HEIGHT}px;
    padding: {TARGET_ITEM_PADDING_VERTICAL}px {TARGET_ITEM_PADDING_HORIZONTAL}px;
    text-align: left;
}}
QPushButton#target_item:checked {{
    border-color: #d6b35f;
    background: #3a3224;
}}
QPushButton#target_item[operationTarget="true"] {{
    border-color: #7dd7b7;
    background: #20332e;
}}
QPushButton#target_item[operationTarget="true"]:checked {{
    border-color: #d6b35f;
    background: #3a3224;
}}
QPushButton#target_reset_button {{
    min-height: {TARGET_RESET_BUTTON_MIN_HEIGHT}px;
    padding: {TARGET_RESET_BUTTON_PADDING_VERTICAL}px {TARGET_RESET_BUTTON_PADDING_HORIZONTAL}px;
    border-radius: {TARGET_RESET_BUTTON_RADIUS}px;
    color: #d6dce8;
    background: #242833;
}}
QPushButton#target_reset_button:hover {{
    background: #2d3340;
}}
QPushButton#target_reset_button:disabled {{
    color: #687080;
    background: #20232b;
    border-color: #303541;
}}
""" + """
QLabel#target_hint {
    color: rgba(220, 226, 238, 190);
    font-size: 14px;
    line-height: 1.35;
}
QLabel#slot_label {
    color: #dce5f7;
    background: #222630;
    border: 1px solid #343b49;
    border-radius: 6px;
    padding: 5px 7px;
}
QFrame#build_slot_row,
QFrame#summary_block {
    border: 1px solid #343b49;
    border-radius: 7px;
    background: #222630;
}
QFrame#build_slot_mini {
    border: 1px solid #343b49;
    border-radius: 6px;
    background: #222630;
}
QFrame#build_preview_block {
    border-top: 1px solid #343b49;
    background: #1f222a;
}
QLabel#mini_stat_badge {
    color: #d9e2ff;
    background: #2d3340;
    border: 1px solid #475066;
    border-radius: 5px;
    padding: 1px 3px;
    font-size: 11px;
    font-weight: 600;
}
QFrame#build_row_stat_badge {
    color: #d9e2ff;
    background: #2d3340;
    border: 1px solid #475066;
    border-radius: 5px;
    padding: 0px;
}
QLabel#build_row_stat_badge_line {
    color: #d9e2ff;
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#build_row_stat_badge_line[topLine="true"] {
    border-bottom: 1px solid #475066;
}
QWidget#build_row_bonus_stack,
QWidget#build_row_bonus_stack QLabel {
    background: transparent;
}
QLabel#small_muted {
    color: #aab0bd;
    font-size: 12px;
}
QLabel#stat_pill {
    color: #d9e2ff;
    background: #2d3340;
    border: 1px solid #475066;
    border-radius: 6px;
    padding: 2px 6px;
    font-weight: 600;
}
QPushButton#icon_button {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
}
"""


ARTIFACT_POSITION_LABEL_KEYS = {
    1: "artifact.position.flower",
    2: "artifact.position.plume",
    3: "artifact.position.sands",
    4: "artifact.position.goblet",
    5: "artifact.position.circlet",
}

ARTIFACT_PLACEHOLDER_ICON_NAMES = {
    1: "flower.png",
    2: "plume.png",
    3: "sands.png",
    4: "goblet.png",
    5: "circlet.png",
}

BUILD_PREVIEW_STAT_CELLS = 10
BUILD_PREVIEW_BLOCK_HEIGHT = 285
BUILD_PREVIEW_LAYOUT_TOP_MARGIN = 8
BUILD_PREVIEW_LAYOUT_SPACING = 6
BUILD_PREVIEW_ROW_SPACING = 3
BUILD_PREVIEW_SLOT_CARD_WIDTH = 52
BUILD_PREVIEW_SLOT_CARD_HEIGHT = 82
BUILD_PREVIEW_SLOT_CONTENT_MARGIN = 2
BUILD_PREVIEW_SLOT_CONTENT_SPACING = 1
BUILD_PREVIEW_SLOT_ICON_SIZE = 48
BUILD_PREVIEW_SLOT_STAT_WIDTH = 48
BUILD_PREVIEW_SLOT_STAT_HEIGHT = 22
BUILD_PREVIEW_BONUS_CONTAINER_WIDTH = 90
BUILD_PREVIEW_BONUS_CONTAINER_HEIGHT = 82
BUILD_PREVIEW_BONUS_CELL_WIDTH = 43
BUILD_PREVIEW_BONUS_CELL_HEIGHT = 82
BUILD_PREVIEW_BONUS_ICON_SIZE = 39
BUILD_PREVIEW_SUMMARY_HEIGHT = 136
BUILD_PREVIEW_SUMMARY_MARGIN = 8
BUILD_PREVIEW_SUMMARY_HORIZONTAL_SPACING = 6
BUILD_PREVIEW_SUMMARY_VERTICAL_SPACING = 5
BUILD_PREVIEW_STAT_LABEL_HEIGHT = 20
BUILD_ROW_BONUS_STACK_WIDTH = 42
BUILD_ROW_BONUS_STACK_HEIGHT = 34
BUILD_ROW_BONUS_DIAGONAL_FEATHER = 3
BUILD_ROW_BONUS_DIAGONAL_DIRECTION = "bottom_left_to_top_right"
BUILD_ROW_BONUS_CACHE_VERSION = "preset_bonus_icon_v1"
BUILD_ROW_BONUS_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "ui" / "preset_bonus_icons"
BUILD_ROW_BONUS_ICON_PADDING = 1
BUILD_ROW_BONUS_TRIM_ALPHA_THRESHOLD = 16
BUILD_ROW_STAT_BADGE_WIDTH = 42
BUILD_ROW_STAT_BADGE_HEIGHT = 34
BUILD_ROW_STAT_BADGE_MAX_CHARS = 5
BUILD_TARGET_UNIVERSAL_KEY = "universal"

PERCENT_STAT_TYPES = {
    HP_PERCENT,
    ATK_PERCENT,
    DEF_PERCENT,
    CRIT_RATE,
    CRIT_DAMAGE,
    ENERGY_RECHARGE,
    HEALING_BONUS,
    PHYSICAL_DAMAGE,
    PYRO_DAMAGE,
    ELECTRO_DAMAGE,
    HYDRO_DAMAGE,
    DENDRO_DAMAGE,
    ANEMO_DAMAGE,
    GEO_DAMAGE,
    CRYO_DAMAGE,
}

BUILD_ROW_MAIN_STAT_BADGES = {
    HP_FLAT: "HP",
    HP_PERCENT: "HP",
    ATK_FLAT: "ATK",
    ATK_PERCENT: "ATK",
    DEF_FLAT: "DEF",
    DEF_PERCENT: "DEF",
    CRIT_RATE: "CR",
    CRIT_DAMAGE: "CD",
    ENERGY_RECHARGE: "ER",
    HEALING_BONUS: "HEAL",
    ELEMENTAL_MASTERY: "EM",
    PHYSICAL_DAMAGE: "PHYS",
    PYRO_DAMAGE: "PYRO",
    ELECTRO_DAMAGE: "ELECT",
    HYDRO_DAMAGE: "HYDRO",
    DENDRO_DAMAGE: "DENDR",
    ANEMO_DAMAGE: "ANEMO",
    GEO_DAMAGE: "GEO",
    CRYO_DAMAGE: "KRYO",
}

EDIT_MODE_NONE = "none"
EDIT_MODE_CUSTOM_SET = "custom_set"
EDIT_MODE_BUILD_PRESET = "build_preset"


class BuildTargetPreviewStrip(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("build_target_preview_strip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = DragScrollArea(
            orientation=Qt.Orientation.Horizontal,
            wheel_step=BUILD_TARGET_PREVIEW_ICON_SIZE,
            edge_hint_size=BUILD_TARGET_PREVIEW_HINT_WIDTH,
            edge_icon_size=BUILD_TARGET_PREVIEW_HINT_ICON_SIZE,
            edge_background=BUILD_TARGET_PREVIEW_EDGE_BACKGROUND.name(),
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        layout.addWidget(self.scroll_area, 1)

        self.content = QLabel()
        self.content.setObjectName("build_target_preview_content")
        self.content.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.content.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        self._has_content = False
        self._strip_width = 0
        self.scroll_area.setWidget(self.content)
        self.scroll_area.set_edge_hints_enabled(False)

        self.refresh_content_width()

    def clear_targets(self) -> None:
        self.set_strip_pixmap(QPixmap())

    def set_strip_pixmap(self, pixmap: QPixmap | None) -> None:
        self.content.clear()
        self._has_content = pixmap is not None and not pixmap.isNull()
        self._strip_width = pixmap.width() if self._has_content else 0
        self.scroll_area.set_edge_hints_enabled(self._has_content)
        if self._has_content:
            self.content.setPixmap(pixmap)
        self.refresh_content_width()

    def finish_update(self) -> None:
        self.refresh_content_width()
        self.scroll_area.update_edge_hints()

    def refresh_content_width(self) -> None:
        viewport_width = max(0, self.scroll_area.viewport().width())

        if not self._has_content:
            width = viewport_width
            self.scroll_area.horizontalScrollBar().setValue(0)
        else:
            width = max(self._strip_width, viewport_width)

        self.content.setFixedSize(width, BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        self.content.updateGeometry()
        self.scroll_area.viewport().update()
        self.scroll_area.update_edge_hints()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_content_width()
        self.scroll_area.update_edge_hints()


class ArtifactBrowserWindow(QWidget):
    equipment_changed = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        embedded: bool = False,
        db_path: str | Path = ARTIFACT_DB_PATH,
        character_asset_items: list[dict] | None = None,
    ):
        init_start = perf_now()
        super().__init__(parent)
        self.embedded = bool(embedded)
        self.db_path = Path(db_path)
        if not self.embedded:
            self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle(tr("artifact.browser.title"))
        if self.embedded:
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Ignored,
            )
        if not self.embedded:
            self.resize(1180, 760)
        self.setStyleSheet(WINDOW_STYLE)
        self._preloaded_character_asset_items = (
            list(character_asset_items) if character_asset_items is not None else None
        )

        self.current_pos = 1
        store_start = perf_now()
        self.store = ArtifactBrowserStore.load_from_db(self.db_path)
        store_ms = perf_ms(store_start)
        model_start = perf_now()
        self.model = ArtifactListModel(self.store, self)
        self.delegate = ArtifactCardDelegate(self)
        model_ms = perf_ms(model_start)

        self.sets_filter_enabled = True
        self.selected_game_set_ids: set[str] = set()
        self.selected_custom_set_ids: set[int] = set()
        self.selected_sort_stat_types: list[int] = []
        self._sort_popup: SortStatsPopup | None = None
        self._sets_popup: SetsFilterPopup | None = None
        self._suppress_next_sort_popup_open = False
        self._suppress_next_sets_popup_open = False
        self.position_buttons: dict[int, QPushButton] = {}
        self.edit_selection_mode = EDIT_MODE_NONE
        self.editing_custom_set_id: int | None = None
        self.editing_custom_set_name: str = ""
        self.editing_custom_artifact_ids: set[int] = set()
        self.editing_custom_dirty = False
        self.build_presets: list[dict] = []
        self.selected_build_id: int | None = None
        self.selected_build_slots: dict[int, int] = {}
        self.selected_build_targets: list[dict] = []
        self.selected_build_target_keys: set[str] = set()
        self.build_target_items_by_key: dict[str, dict] = {}
        self.build_target_buttons_by_key: dict[str, QPushButton] = {}
        self._build_target_buttons_initialized = False
        self._build_target_button_order: list[str] = []
        self._build_target_list_stretch_added = False
        self.build_target_element_filters: set[str] = set()
        self.build_target_weapon_filters: set[str] = set()
        self.build_target_rarity_filters: set[int] = set()
        self.build_target_region_filters: set[str] = set()
        self.build_target_trait_filters: set[str] = set()
        self.build_target_standard_filter = STANDARD_FILTER_ALL
        self._region_popup: RegionFilterPopup | None = None
        self._suppress_next_region_popup_open = False
        self.build_target_filter_buttons: list[tuple[QPushButton, set, object]] = []
        self._character_region_by_name: dict[str, dict] = {}
        self._region_names_by_key: dict[str, str] = {}
        self.build_target_filter_reset_button: QPushButton | None = None
        self.build_target_region_button: QPushButton | None = None
        self.editing_build_id: int | None = None
        self.editing_build_name: str = ""
        self.editing_build_slots: dict[int, int] = {}
        self.editing_build_targets: list[dict] = []
        self.editing_build_dirty = False
        self._build_target_keys_before_edit: set[str] | None = None
        self.pending_delete_build_id: int | None = None
        self.build_preset_row_buttons: dict[int, QPushButton] = {}
        self.build_row_name_input: QLineEdit | None = None
        self._right_panel_operation_target: dict | None = None
        self._right_panel_target_selection_suppressed = False
        self.operation_target_character_id: int | None = None
        self.operation_target_character_name = ""
        self.operation_target_source: str | None = None
        self.equip_mode_enabled = False
        self.applied_current_equipment_label = ""
        self.current_equipment_preview_slots: dict[int, int] = {}
        self.build_slot_rows: dict[int, QFrame] = {}
        self.build_slot_icon_labels: dict[int, QLabel] = {}
        self.build_slot_stat_labels: dict[int, QLabel] = {}
        self.build_bonus_layout: QHBoxLayout | None = None
        self.build_summary_stats_layout: QGridLayout | None = None
        self._build_row_source_icon_cache: dict[tuple, QPixmap] = {}
        self._build_row_bonus_pixmap_cache: dict[str, QPixmap] = {}
        self._target_preview_icon_cache: dict[str, QPixmap] = {}
        self._target_preview_strip_cache: dict[str, QPixmap] = {}
        self._universal_target_icon: QIcon | None = None
        self.artifact_grid_overlay_scrollbar = None
        self.import_json_button: QPushButton | None = None
        self.clear_json_button: QPushButton | None = None
        self.json_action_row_widget: AdaptiveJsonActionRow | None = None
        self._artifact_column_count = 0
        self.content_layout: QHBoxLayout | None = None
        self.build_target_panel: QFrame | None = None
        self.build_panel: QFrame | None = None
        self._resize_event_count = 0
        self._adaptive_update_count = 0
        self._last_adaptive_target_layout_key: tuple[int, int, int, int, int, int] | None = None
        self._adaptive_target_resize_timer = QTimer(self)
        self._adaptive_target_resize_timer.setSingleShot(True)
        self._adaptive_target_resize_timer.timeout.connect(
            self.update_adaptive_target_panel_width
        )
        target_load_start = perf_now()
        self.load_build_target_items()
        target_load_ms = perf_ms(target_load_start)

        ui_start = perf_now()
        root = QVBoxLayout(self)
        if self.embedded:
            root.setContentsMargins(4, 4, 0, 4)
            root.setSpacing(6)
        else:
            root.setContentsMargins(10, 10, 10, 10)
            root.setSpacing(8)

        self._build_top_bar(root)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(CONTENT_LAYOUT_SPACING)
        self.content_layout = content
        self._build_list_view(content)
        self._build_build_target_selector(content)
        self.target_build_gap_widget = QWidget()
        self.target_build_gap_widget.setFixedWidth(CONTENT_TARGET_BUILD_SPACING)
        self.target_build_gap_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        content.addWidget(self.target_build_gap_widget)
        self._build_build_panel(content)
        root.addLayout(content, 1)
        self.empty_label = QLabel("")
        self._prewarm_transient_edit_controls()
        ui_ms = perf_ms(ui_start)

        preset_start = perf_now()
        self.load_build_presets()
        preset_ms = perf_ms(preset_start)
        filter_start = perf_now()
        self.apply_current_filters()
        filter_ms = perf_ms(filter_start)
        self.update_custom_edit_bar()
        build_panel_start = perf_now()
        self.update_build_panel()
        build_panel_ms = perf_ms(build_panel_start)
        if not self.embedded:
            self.schedule_adaptive_target_panel_width_update(delay_ms=0)
        log_perf(
            "artifact_browser_init",
            embedded=self.embedded,
            total=perf_ms(init_start),
            store=store_ms,
            model=model_ms,
            targets=target_load_ms,
            ui=ui_ms,
            presets=preset_ms,
            filter=filter_ms,
            build_panel=build_panel_ms,
            artifacts=self.model.rowCount(),
            resize_events=self._resize_event_count,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_event_count += 1
        if self.embedded and not self.isVisible():
            return
        self.schedule_adaptive_target_panel_width_update(
            delay_ms=ADAPTIVE_TARGET_RESIZE_SETTLE_MS
            if self.embedded
            else ADAPTIVE_TARGET_RESIZE_DELAY_MS
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._adaptive_target_resize_timer.stop()
        self.update_adaptive_target_panel_width()

    def schedule_adaptive_target_panel_width_update(
        self,
        delay_ms: int = ADAPTIVE_TARGET_RESIZE_DELAY_MS,
    ) -> None:
        if not hasattr(self, "_adaptive_target_resize_timer"):
            return
        if self.model.rowCount() <= 0:
            return
        self._adaptive_target_resize_timer.start(max(0, int(delay_ms)))

    def update_adaptive_target_panel_width(self) -> None:
        if self.content_layout is None or self.build_target_panel is None:
            return
        if self.model.rowCount() <= 0:
            return

        top_level = self.window()
        top_before = top_level.size()
        left_workspace = self.parentWidget()
        if left_workspace is not None and left_workspace.parentWidget() is not None:
            left_workspace = left_workspace.parentWidget()
        self._adaptive_update_count += 1
        content_width = self.content_layout.geometry().width()
        if content_width <= 0:
            return

        spacing = max(0, self.content_layout.spacing())
        fixed_panel_width = (
            self.build_panel.width()
            if self.build_panel is not None and self.build_panel.width() > 0
            else BUILD_PANEL_WIDTH
        )
        grid_width = GRID_SIZE.width()
        viewport_chrome_width = max(
            0,
            self.list_view.width() - self.list_view.viewport().width(),
        )
        fixed_internal_gaps = (
            spacing
            + CONTENT_TARGET_BUILD_SPACING
            + viewport_chrome_width
            + ARTIFACT_GRID_FIT_PADDING
        )
        layout_key = (
            content_width,
            fixed_panel_width,
            viewport_chrome_width,
            TARGET_PANEL_MIN_WIDTH,
            grid_width,
        )
        if layout_key == self._last_adaptive_target_layout_key:
            return
        self._last_adaptive_target_layout_key = layout_key

        fit = calculate_assignment_width_fit(
            content_width=content_width,
            preset_panel_width=fixed_panel_width,
            fixed_internal_gaps=fixed_internal_gaps,
            assignment_min_width=TARGET_PANEL_MIN_WIDTH,
            column_step=grid_width,
        )
        if fit is None:
            if isinstance(self.build_target_panel, AdaptiveAssignmentPanel):
                self.build_target_panel.set_preferred_width(TARGET_PANEL_MIN_WIDTH)
            self._set_json_button_column_mode(1)
            return

        self._set_json_button_column_mode(fit.columns)
        applied = False
        if abs(self.build_target_panel.width() - fit.assignment_width) > 1:
            if isinstance(self.build_target_panel, AdaptiveAssignmentPanel):
                self.build_target_panel.set_preferred_width(fit.assignment_width)
            else:
                self.build_target_panel.setMinimumWidth(TARGET_PANEL_MIN_WIDTH)
                self.build_target_panel.setMaximumWidth(fit.assignment_width)
            applied = True
        top_after = top_level.size()
        log_perf(
            "artifact_browser_grid_layout",
            embedded=self.embedded,
            top_before=f"{top_before.width()}x{top_before.height()}",
            top_after=f"{top_after.width()}x{top_after.height()}",
            left_workspace=left_workspace.width() if left_workspace is not None else "-",
            content_width=content_width,
            fixed_panel=fixed_panel_width,
            fixed_gaps=fixed_internal_gaps,
            target_panel=fit.assignment_width,
            target_current=self.build_target_panel.width(),
            target_min=TARGET_PANEL_MIN_WIDTH,
            target_default=TARGET_PANEL_WIDTH,
            preset_panel=fixed_panel_width,
            viewport=self.list_view.viewport().width(),
            columns=fit.columns,
            artifact_viewport=fit.artifact_viewport_width,
            trailing_gap=fit.remainder,
            total_used=fit.total_used_width,
            applied=applied,
            adaptive_runs=self._adaptive_update_count,
            resize_events=self._resize_event_count,
        )

    def _build_top_bar(self, root: QVBoxLayout) -> None:
        top_frame = QFrame()
        top_frame.setObjectName("top_bar")
        if self.embedded:
            top_frame.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )

        top = QHBoxLayout(top_frame)
        top.setContentsMargins(8, 8, 8, 8)
        top.setSpacing(6)

        self.slot_group = QButtonGroup(self)
        self.slot_group.setExclusive(True)

        for pos in ARTIFACT_POSITIONS:
            button = QPushButton(self._position_label(pos))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=pos: self.set_position(value))
            self.slot_group.addButton(button, pos)
            self.position_buttons[pos] = button
            top.addWidget(button)

            if pos == 1:
                button.setChecked(True)

        top.addStretch()

        self.sets_filter_switch = QPushButton()
        self.sets_filter_switch.setObjectName("filter_switch")
        self.sets_filter_switch.setCheckable(True)
        self.sets_filter_switch.setChecked(True)
        self.update_sets_filter_switch_text()
        self.sets_filter_switch.clicked.connect(self.on_sets_filter_enabled_changed)
        top.addWidget(self.sets_filter_switch)

        self.sets_button = QPushButton(tr("artifact.sets.button"))
        self.sort_button = QPushButton(tr("artifact.sort.button"))
        self.sort_button.pressed.connect(self.on_sort_button_pressed)
        self.sort_button.clicked.connect(self.show_sort_popup)
        top.addWidget(self.sort_button)
        self.sets_button.setObjectName("sets_button")
        self.sets_button.pressed.connect(self.on_sets_button_pressed)
        self.sets_button.clicked.connect(self.show_sets_popup)
        top.addWidget(self.sets_button)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")
        status_policy = self.status_label.sizePolicy()
        status_policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self.status_label.setSizePolicy(status_policy)
        top.addWidget(self.status_label)

        root.addWidget(top_frame)

    def _build_list_view(self, root: QVBoxLayout) -> None:
        panel = QWidget()
        panel.setMinimumWidth(ARTIFACT_LIST_MIN_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setFlow(QListView.Flow.LeftToRight)
        self.list_view.setWrapping(True)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setMovement(QListView.Movement.Static)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setGridSize(QSize(GRID_SIZE.width(), GRID_SIZE.height()))
        self.list_view.setSpacing(0)
        self.list_view.setMinimumWidth(ARTIFACT_LIST_MIN_WIDTH)
        self.list_view.verticalScrollBar().setSingleStep(20)
        self.artifact_grid_overlay_scrollbar = install_overlay_vertical_scrollbar(
            self.list_view
        )
        self.list_view.setMouseTracking(True)
        self.list_view.setProperty("artifactEditMode", False)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.clicked.connect(self.on_artifact_clicked)
        layout.addWidget(self.list_view, 1)

        action_row_widget = AdaptiveJsonActionRow(
            GRID_SIZE.width(),
            GRID_SIZE.width(),
        )
        self.json_action_row_widget = action_row_widget
        action_row = QHBoxLayout(action_row_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)

        self.import_json_button = MarqueeButton(tr("artifact.json.import_button"))
        self.import_json_button.setObjectName("json_action_button")
        self.import_json_button.clicked.connect(self.import_artiscan_json)
        action_row.addWidget(self.import_json_button)

        self.clear_json_button = MarqueeButton(tr("artifact.json.clear_button"))
        self.clear_json_button.setObjectName("json_action_button")
        self.clear_json_button.clicked.connect(self.clear_json_imports)
        action_row.addWidget(self.clear_json_button)

        self._set_json_button_column_mode(1)
        layout.addWidget(action_row_widget)
        root.addWidget(panel, 1)
        self.update_json_import_actions()

    def _set_json_button_column_mode(self, columns: int) -> None:
        if (
            self.json_action_row_widget is None
            or self.import_json_button is None
            or self.clear_json_button is None
        ):
            return
        columns = max(1, int(columns))
        if self._artifact_column_count == columns:
            return
        self._artifact_column_count = columns

        row_layout = self.json_action_row_widget.layout()
        spacing = row_layout.spacing() if row_layout is not None else 0
        row_width = GRID_SIZE.width() * columns if columns >= 2 else GRID_SIZE.width()
        button_width = max(0, (row_width - spacing) // 2)
        compact_button_width = max(0, (GRID_SIZE.width() - spacing) // 2)
        self.json_action_row_widget.set_preferred_width(row_width)
        for button in (self.import_json_button, self.clear_json_button):
            button.setMinimumWidth(compact_button_width)
            button.setMaximumWidth(button_width)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        self.json_action_row_widget.updateGeometry()

    def _build_build_target_selector(self, root) -> None:
        panel = AdaptiveAssignmentPanel(
            TARGET_PANEL_MIN_WIDTH,
            TARGET_PANEL_WIDTH,
        )
        panel.setObjectName("build_target_panel")
        panel.setMaximumWidth(TARGET_PANEL_MIN_WIDTH + GRID_SIZE.width() - 1)
        panel.resize(TARGET_PANEL_WIDTH, panel.height())
        self.build_target_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*TARGET_PANEL_MARGINS)
        layout.setSpacing(TARGET_PANEL_SPACING)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(TARGET_HEADER_LEFT_INSET, 0, 0, 0)
        header_row.setSpacing(TARGET_HEADER_SPACING)

        self.build_target_title_label = MarqueeButton(
            tr("artifact.build.targets_title")
        )
        self.build_target_title_label.setObjectName("target_panel_title")
        self.build_target_title_label.setFlat(True)
        self.build_target_title_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.build_target_title_label.setMinimumWidth(TARGET_TITLE_MIN_WIDTH)
        self.build_target_title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.build_target_filter_reset_button = (
            self._make_build_target_filter_reset_button()
        )
        header_row.addWidget(self.build_target_filter_reset_button)
        header_row.addWidget(self.build_target_title_label, 1)

        self.build_target_reset_button = QPushButton(tr("artifact.build.targets_reset"))
        self.build_target_reset_button.setObjectName("target_reset_button")
        self.build_target_reset_button.setFixedWidth(TARGET_RESET_BUTTON_WIDTH)
        self.build_target_reset_button.setText("")
        self.build_target_reset_button.setIcon(self._ui_icon("x"))
        self.build_target_reset_button.setIconSize(
            QSize(UI_ICON_DEFAULT_SIZE, UI_ICON_DEFAULT_SIZE)
        )
        self.build_target_reset_button.setToolTip(tr("artifact.build.targets_reset"))
        self.build_target_reset_button.clicked.connect(self.reset_build_targets)
        header_row.addWidget(self.build_target_reset_button)
        layout.addLayout(header_row)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(TARGET_BODY_SPACING)

        filter_scroll = DragScrollArea(
            orientation=Qt.Orientation.Vertical,
            wheel_step=TARGET_FILTER_BUTTON_SIZE + TARGET_FILTER_SPACING,
            edge_hint_size=TARGET_FILTER_BUTTON_SIZE,
            edge_icon_size=TARGET_FILTER_ICON_SIZE,
            edge_background=BUILD_TARGET_PREVIEW_EDGE_BACKGROUND.name(),
        )
        filter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        filter_scroll.setWidgetResizable(True)
        filter_scroll.setFixedWidth(TARGET_FILTER_LANE_WIDTH)
        filter_content = QWidget()
        filter_column = QVBoxLayout(filter_content)
        filter_column.setContentsMargins(
            TARGET_FILTER_LANE_INSET_LEFT,
            0,
            TARGET_FILTER_LANE_INSET_RIGHT,
            0,
        )
        filter_column.setSpacing(TARGET_FILTER_SPACING)
        for filters, selected in (
            (ELEMENT_FILTERS, self.build_target_element_filters),
            (CHARACTER_RARITY_FILTERS, self.build_target_rarity_filters),
            (WEAPON_TYPE_FILTERS, self.build_target_weapon_filters),
            (CHARACTER_TRAIT_FILTERS, self.build_target_trait_filters),
        ):
            for value, icon_name, tooltip_key in filters:
                filter_column.addWidget(
                    self._make_build_target_filter_button(
                        value,
                        icon_name,
                        tooltip_key,
                        selected,
                    )
                )
        self.build_target_region_button = self._make_build_target_region_filter_button()
        filter_column.addWidget(self.build_target_region_button)
        self.build_target_standard_button = self._make_build_target_standard_filter_button()
        filter_column.addWidget(self.build_target_standard_button)
        filter_column.addStretch()
        filter_scroll.setWidget(filter_content)
        body.addWidget(filter_scroll)

        target_scroll = OverlayVerticalScrollArea()
        self.build_target_scroll = target_scroll
        target_scroll.setWidgetResizable(True)
        target_scroll.setFrameShape(QFrame.Shape.NoFrame)
        target_content = QWidget()
        self.build_target_list_layout = QVBoxLayout(target_content)
        self.build_target_list_layout.setContentsMargins(0, 0, 0, 0)
        self.build_target_list_layout.setSpacing(TARGET_ITEM_SPACING)
        target_scroll.setWidget(target_content)
        body.addWidget(target_scroll, 1)

        layout.addLayout(body, 1)
        root.addWidget(panel)
        self.refresh_build_target_list()

    def _make_build_target_filter_button(
        self,
        value,
        icon_name: str,
        tooltip_key: str,
        selected_values: set,
    ) -> QPushButton:
        button = QPushButton()
        button.setObjectName("target_filter_button")
        button.setCheckable(True)
        button.setStyleSheet(TARGET_FILTER_BUTTON_STYLE)
        button.setIcon(QIcon(str(FILTER_ASSETS_DIR / icon_name)))
        button.setIconSize(QSize(TARGET_FILTER_ICON_SIZE, TARGET_FILTER_ICON_SIZE))
        button.clicked.connect(
            lambda checked=False, v=value, values=selected_values: self.on_build_target_filter_clicked(
                values,
                v,
                checked,
            )
        )
        self.build_target_filter_buttons.append((button, selected_values, value))
        return button

    def _make_build_target_filter_reset_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("target_filter_button")
        button.setStyleSheet(TARGET_FILTER_BUTTON_STYLE)
        button.setIcon(QIcon(str(FILTER_ASSETS_DIR / "Icon_Back.png")))
        button.setIconSize(QSize(TARGET_FILTER_ICON_SIZE, TARGET_FILTER_ICON_SIZE))
        button.clicked.connect(self.reset_build_target_filters)
        return button

    def _make_build_target_region_filter_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("target_filter_button")
        button.setStyleSheet(TARGET_FILTER_BUTTON_STYLE)
        button.setCheckable(True)
        button.setChecked(bool(self.build_target_region_filters))
        button.setIcon(QIcon(str(FILTER_ASSETS_DIR / "Statue.png")))
        button.setIconSize(QSize(TARGET_FILTER_ICON_SIZE, TARGET_FILTER_ICON_SIZE))
        button.pressed.connect(self.on_build_target_region_button_pressed)
        button.clicked.connect(self.show_region_filter_popup)
        return button

    def _make_build_target_standard_filter_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("target_filter_button")
        button.setStyleSheet(TARGET_FILTER_BUTTON_STYLE)
        button.setCheckable(False)
        button.setIcon(
            standard_character_filter_icon(
                STANDARD_FILTER_ALL,
                size=TARGET_FILTER_ICON_SIZE,
            )
        )
        button.setIconSize(QSize(TARGET_FILTER_ICON_SIZE, TARGET_FILTER_ICON_SIZE))
        button.setProperty("standardOnly", False)

        def cycle_standard_filter() -> None:
            if self.build_target_standard_filter == STANDARD_FILTER_ALL:
                self.build_target_standard_filter = STANDARD_FILTER_ONLY
            elif self.build_target_standard_filter == STANDARD_FILTER_ONLY:
                self.build_target_standard_filter = STANDARD_FILTER_EXCLUDE
            else:
                self.build_target_standard_filter = STANDARD_FILTER_ALL
            button.setProperty(
                "standardOnly",
                self.build_target_standard_filter == STANDARD_FILTER_ONLY,
            )
            button.style().unpolish(button)
            button.style().polish(button)
            button.setIcon(
                standard_character_filter_icon(
                    self.build_target_standard_filter,
                    size=TARGET_FILTER_ICON_SIZE,
                )
            )
            self.sync_build_target_filter_buttons()
            self.refresh_build_target_list()

        button.clicked.connect(cycle_standard_filter)
        return button

    def _build_build_panel(self, root) -> None:
        panel = QFrame()
        panel.setObjectName("build_panel")
        panel.setFixedWidth(BUILD_PANEL_WIDTH)
        self.build_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(7, 10, 7, 10)
        layout.setSpacing(8)

        self.equipment_zone_frame = QFrame()
        self.equipment_zone_frame.setObjectName("equipment_zone")
        equipment_layout = QVBoxLayout(self.equipment_zone_frame)
        equipment_layout.setContentsMargins(8, 7, 8, 7)
        equipment_layout.setSpacing(5)

        self.equipment_target_label = QLabel()
        self.equipment_target_label.setObjectName("equipment_target_label")
        self.equipment_target_label.setWordWrap(True)
        equipment_layout.addWidget(self.equipment_target_label)

        equipment_row = QHBoxLayout()
        equipment_row.setContentsMargins(0, 0, 0, 0)
        equipment_row.setSpacing(6)
        self.equipment_zone_label = QLabel()
        self.equipment_zone_label.setObjectName("equipment_zone_label")
        equipment_row.addWidget(self.equipment_zone_label, 1)
        self.equipment_zone_action_button = QPushButton()
        self.equipment_zone_action_button.setObjectName("equipment_zone_action_button")
        self.equipment_zone_action_button.setEnabled(False)
        self.equipment_zone_action_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.equipment_zone_action_button.clicked.connect(
            self.apply_selected_build_preset_to_current_equipment
        )
        equipment_row.addWidget(self.equipment_zone_action_button, 1)
        equipment_layout.addLayout(equipment_row)
        layout.addWidget(self.equipment_zone_frame)

        self.build_title_label = QLabel(tr("artifact.build.presets_title"))
        self.build_title_label.setObjectName("panel_title")
        layout.addWidget(self.build_title_label)

        self.build_create_row_widget = QWidget()
        create_row = QHBoxLayout(self.build_create_row_widget)
        create_row.setContentsMargins(0, 0, 0, 0)
        create_row.setSpacing(6)
        self.build_name_input = QLineEdit()
        self.build_name_input.setPlaceholderText(tr("artifact.build.name_placeholder"))
        self.build_name_input.textChanged.connect(self.on_build_name_changed)
        self.build_name_input.installEventFilter(self)
        create_row.addWidget(self.build_name_input, 1)

        self.new_build_button = QPushButton()
        self.new_build_button.setObjectName("icon_button")
        self.new_build_button.setIcon(self._ui_icon("plus"))
        self.new_build_button.setToolTip(tr("artifact.build.new"))
        self.new_build_button.clicked.connect(self.on_build_create_button_clicked)
        create_row.addWidget(self.new_build_button)

        self.cancel_new_build_button = QPushButton()
        self.cancel_new_build_button.setObjectName("row_cancel_button")
        self.cancel_new_build_button.setIcon(self._ui_icon("x"))
        self.cancel_new_build_button.setToolTip(tr("artifact.build.cancel"))
        self.cancel_new_build_button.clicked.connect(self.cancel_build_preset_edit)
        create_row.addWidget(self.cancel_new_build_button)
        layout.addWidget(self.build_create_row_widget)

        self.build_target_hint_label = QLabel(tr("artifact.build.no_target_hint"))
        self.build_target_hint_label.setObjectName("target_hint")
        self.build_target_hint_label.setWordWrap(True)
        self.build_target_hint_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        layout.addWidget(self.build_target_hint_label, 1)

        self.build_preset_list_scroll = OverlayVerticalScrollArea()
        self.build_preset_list_scroll.setWidgetResizable(True)
        self.build_preset_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.build_preset_list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        list_content = QWidget()
        self.build_preset_list_layout = QVBoxLayout(list_content)
        self.build_preset_list_layout.setContentsMargins(0, 0, 0, 0)
        self.build_preset_list_layout.setSpacing(5)
        self.build_preset_list_layout.addStretch()
        self.build_preset_list_scroll.setWidget(list_content)
        layout.addWidget(self.build_preset_list_scroll, 1)

        preview_block = QFrame()
        preview_block.setObjectName("build_preview_block")
        preview_block.setFixedHeight(BUILD_PREVIEW_BLOCK_HEIGHT)
        preview_layout = QVBoxLayout(preview_block)
        preview_layout.setContentsMargins(0, BUILD_PREVIEW_LAYOUT_TOP_MARGIN, 0, 0)
        preview_layout.setSpacing(BUILD_PREVIEW_LAYOUT_SPACING)

        self.build_target_placeholder = BuildTargetPreviewStrip()
        preview_layout.addWidget(self.build_target_placeholder)

        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(BUILD_PREVIEW_ROW_SPACING)
        preview_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        for pos in ARTIFACT_POSITIONS:
            preview_row.addWidget(self._make_build_slot_row(pos))
        self.build_bonus_container = QFrame()
        self.build_bonus_container.setFixedSize(
            BUILD_PREVIEW_BONUS_CONTAINER_WIDTH,
            BUILD_PREVIEW_BONUS_CONTAINER_HEIGHT,
        )
        self.build_bonus_layout = QHBoxLayout(self.build_bonus_container)
        self.build_bonus_layout.setContentsMargins(0, 0, 0, 0)
        self.build_bonus_layout.setSpacing(BUILD_PREVIEW_ROW_SPACING)
        self.build_bonus_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.build_bonus_container)
        preview_layout.addLayout(preview_row)

        stats_block = QFrame()
        stats_block.setObjectName("summary_block")
        stats_block.setFixedHeight(BUILD_PREVIEW_SUMMARY_HEIGHT)
        stats_layout = QVBoxLayout(stats_block)
        stats_layout.setContentsMargins(
            BUILD_PREVIEW_SUMMARY_MARGIN,
            BUILD_PREVIEW_SUMMARY_MARGIN,
            BUILD_PREVIEW_SUMMARY_MARGIN,
            BUILD_PREVIEW_SUMMARY_MARGIN,
        )
        self.build_summary_stats_layout = QGridLayout()
        self.build_summary_stats_layout.setContentsMargins(0, 0, 0, 0)
        self.build_summary_stats_layout.setHorizontalSpacing(
            BUILD_PREVIEW_SUMMARY_HORIZONTAL_SPACING
        )
        self.build_summary_stats_layout.setVerticalSpacing(
            BUILD_PREVIEW_SUMMARY_VERTICAL_SPACING
        )
        stats_layout.addLayout(self.build_summary_stats_layout)
        preview_layout.addWidget(stats_block)
        layout.addWidget(preview_block)

        root.addWidget(panel)

    def _make_build_slot_row(self, pos: int) -> QFrame:
        row = QFrame()
        row.setObjectName("build_slot_mini")
        row.setFixedSize(BUILD_PREVIEW_SLOT_CARD_WIDTH, BUILD_PREVIEW_SLOT_CARD_HEIGHT)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
        )
        layout.setSpacing(BUILD_PREVIEW_SLOT_CONTENT_SPACING)

        icon_label = QLabel()
        icon_label.setFixedSize(
            BUILD_PREVIEW_SLOT_ICON_SIZE,
            BUILD_PREVIEW_SLOT_ICON_SIZE,
        )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        stat_label = QLabel("")
        stat_label.setObjectName("mini_stat_badge")
        stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stat_label.setFixedWidth(BUILD_PREVIEW_SLOT_STAT_WIDTH)
        stat_label.setFixedHeight(BUILD_PREVIEW_SLOT_STAT_HEIGHT)
        layout.addWidget(stat_label)

        self.build_slot_rows[pos] = row
        self.build_slot_icon_labels[pos] = icon_label
        self.build_slot_stat_labels[pos] = stat_label
        return row

    def _position_label(self, pos: int) -> str:
        label_key = ARTIFACT_POSITION_LABEL_KEYS.get(pos)
        return tr(label_key) if label_key else str(pos)

    def _ui_icon(self, name: str) -> QIcon:
        return auto_contrast_svg_icon(
            name,
            UI_ICON_DEFAULT_SIZE,
            UI_ICON_BUTTON_BACKGROUND,
        )

    def _prewarm_transient_edit_controls(self) -> None:
        for icon_name in ("check", "x", "save", "edit", "delete", "plus"):
            self._ui_icon(icon_name)
        for button in (
            self.new_build_button,
            self.cancel_new_build_button,
        ):
            self._prepare_button_for_first_show(button)
        for object_name, icon_name in (
            ("row_save_button", "save"),
            ("row_cancel_button", "x"),
        ):
            button = QPushButton(self)
            button.setObjectName(object_name)
            button.setIcon(self._ui_icon(icon_name))
            self._prepare_button_for_first_show(button)
            button.deleteLater()

    def _prepare_button_for_first_show(self, button: QPushButton) -> None:
        button.ensurePolished()
        button.sizeHint()
        button.minimumSizeHint()

    def _prepare_row_action_button(self, button: QPushButton) -> None:
        self._prepare_button_for_first_show(button)

    def _load_scaled_center_crop_pixmap(self, path, size: int) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)

        source_size = reader.size()
        if (
            source_size.isValid()
            and source_size.width() > 0
            and source_size.height() > 0
        ):
            scale = max(size / source_size.width(), size / source_size.height())
            reader.setScaledSize(
                QSize(
                    max(size, int(source_size.width() * scale + 0.5)),
                    max(size, int(source_size.height() * scale + 0.5)),
                )
            )
            image = reader.read()
            if not image.isNull():
                return QPixmap.fromImage(image)

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return QPixmap()
        return pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _make_universal_target_preview_pixmap(self) -> QPixmap:
        size = BUILD_TARGET_PREVIEW_ICON_SIZE
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, size, size),
            BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_RADIUS,
            BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_RADIUS,
        )
        painter.setClipPath(path)

        background = self._load_scaled_center_crop_pixmap(
            BUILD_TARGET_PREVIEW_UNIVERSAL_BG_PATH,
            size,
        )
        if background.isNull():
            painter.fillRect(
                QRect(0, 0, size, size),
                QColor(BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND),
            )
        else:
            painter.drawPixmap(
                (size - background.width()) // 2,
                (size - background.height()) // 2,
                background,
            )

        icon = auto_contrast_svg_pixmap(
            "users",
            BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_SIZE,
            BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND,
        )
        ratio = icon.devicePixelRatio() or 1.0
        icon_width = icon.width() / ratio
        icon_height = icon.height() / ratio
        painter.drawPixmap(
            int((size - icon_width) / 2),
            int((size - icon_height) / 2) + BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_OFFSET_Y,
            icon,
        )
        painter.end()
        return canvas

    def _cached_universal_target_icon(self) -> QIcon:
        if self._universal_target_icon is None:
            self._universal_target_icon = QIcon(
                self._make_universal_target_preview_pixmap()
            )
        return QIcon(self._universal_target_icon)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("artifact.browser.title"))

        for pos, button in self.position_buttons.items():
            button.setText(self._position_label(pos))

        self.build_title_label.setText(tr("artifact.build.presets_title"))
        self.build_target_title_label.setText(tr("artifact.build.targets_title"))
        self.build_target_reset_button.setText(tr("artifact.build.targets_reset"))
        self.build_target_hint_label.setText(tr("artifact.build.no_target_hint"))
        self.update_json_import_actions()
        if BUILD_TARGET_UNIVERSAL_KEY in self.build_target_items_by_key:
            self.build_target_items_by_key[BUILD_TARGET_UNIVERSAL_KEY][
                "character_name"
            ] = tr("artifact.build.target_universal")
        self.new_build_button.setToolTip(tr("artifact.build.new"))
        self.cancel_new_build_button.setToolTip(tr("artifact.build.cancel"))
        self.build_name_input.setPlaceholderText(tr("artifact.build.name_placeholder"))
        self.update_sets_filter_switch_text()
        self.update_sets_button_text()
        self.update_sort_button_text()
        self.refresh_build_target_list()
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.apply_current_filters()

    def set_right_panel_operation_target(self, target: dict | None) -> None:
        old_key = self._right_panel_operation_target_key()
        self._right_panel_operation_target = self._normalized_operation_target(
            target,
            source="right_panel",
        )
        new_key = self._right_panel_operation_target_key()
        selection_changed = False

        if new_key != old_key:
            self._right_panel_target_selection_suppressed = False
            if self._right_panel_operation_target is not None and new_key:
                self._ensure_operation_target_item(self._right_panel_operation_target)
                next_keys = {new_key}
                selection_changed = next_keys != self.selected_build_target_keys
                self.selected_build_target_keys = next_keys
                if self.edit_selection_mode == EDIT_MODE_NONE:
                    self.selected_build_id = None
                    self.selected_build_slots = {}
                    self.selected_build_targets = []
                self.pending_delete_build_id = None
        elif self._right_panel_operation_target is not None and new_key:
            self._ensure_operation_target_item(self._right_panel_operation_target)

        self.refresh_equipment_target_state()
        if selection_changed:
            self.refresh_build_target_list()
            self.refresh_build_preset_list()
            self.update_build_panel()
            self.update_edit_selection_mode()
            if self.edit_selection_mode == EDIT_MODE_NONE:
                self.apply_current_filters()
        else:
            self._sync_build_target_button_selection()
            self.update_build_panel()

    def refresh_equipment_target_state(self) -> None:
        previous_target = (
            self.operation_target_source,
            self.operation_target_character_id,
        )
        target = self._right_panel_operation_target or self._browser_operation_target()
        if target is None:
            self.operation_target_character_id = None
            self.operation_target_character_name = ""
            self.operation_target_source = None
            self.equip_mode_enabled = False
        else:
            self.operation_target_character_id = target["character_id"]
            self.operation_target_character_name = target.get("character_name") or ""
            self.operation_target_source = target.get("source") or "artifact_browser"
            self.equip_mode_enabled = True
        current_target = (
            self.operation_target_source,
            self.operation_target_character_id,
        )
        if current_target != previous_target:
            self.applied_current_equipment_label = ""
        self._update_equipment_zone()

    def _right_panel_operation_target_key(self) -> str | None:
        if self._right_panel_operation_target is None:
            return None
        character_id_value = self._right_panel_operation_target.get("character_id")
        if character_id_value is None:
            return None
        try:
            return self._character_target_key(int(character_id_value))
        except (TypeError, ValueError):
            return None

    def _browser_operation_target(self) -> dict | None:
        targets = []
        for key in self.selected_build_target_keys:
            if key == BUILD_TARGET_UNIVERSAL_KEY:
                continue
            item = self.build_target_items_by_key.get(key)
            target = self._normalized_operation_target(item, source="artifact_browser")
            if target is not None:
                targets.append(target)
        return targets[0] if len(targets) == 1 else None

    def _normalized_operation_target(self, target: dict | None, *, source: str) -> dict | None:
        if not target:
            return None
        character_id_value = target.get("character_id")
        if character_id_value is None:
            return None
        try:
            character_id_value = int(character_id_value)
        except (TypeError, ValueError):
            return None
        return {
            "character_id": character_id_value,
            "character_name": str(
                target.get("character_name")
                or target.get("name")
                or character_id_value
            ),
            "source": source,
        }

    def _ensure_operation_target_item(self, target: dict) -> None:
        character_id_value = target.get("character_id")
        if character_id_value is None:
            return
        try:
            key = self._character_target_key(int(character_id_value))
        except (TypeError, ValueError):
            return
        if key in self.build_target_items_by_key:
            return
        self.build_target_items_by_key[key] = {
            "key": key,
            "target_type": "character",
            "character_id": int(character_id_value),
            "character_name": target.get("character_name") or str(character_id_value),
            "asset": None,
            "path": None,
        }

    def _update_equipment_zone(self) -> None:
        if not hasattr(self, "equipment_target_label"):
            return

        self.equipment_zone_frame.setProperty("equipMode", self.equip_mode_enabled)
        self.equipment_zone_frame.style().unpolish(self.equipment_zone_frame)
        self.equipment_zone_frame.style().polish(self.equipment_zone_frame)

        self.equipment_target_label.setText("")
        self.equipment_target_label.setVisible(False)

        preset_preview_active = (
            self.selected_build_id is not None
            and self.edit_selection_mode == EDIT_MODE_NONE
        )
        apply_text = tr("artifact.equipment.apply_preset")
        self.equipment_zone_action_button.setText(apply_text)
        self.equipment_zone_action_button.setVisible(preset_preview_active)
        self.equipment_zone_action_button.setEnabled(
            self.equip_mode_enabled and preset_preview_active
        )
        self.equipment_zone_label.setVisible(not preset_preview_active)
        if preset_preview_active:
            self.equipment_zone_label.setText("")
        else:
            target_name = (
                self.operation_target_character_name
                or str(self.operation_target_character_id)
                if self.operation_target_character_id is not None
                else tr("artifact.build.character_not_selected")
            )
            applied_label = self.applied_current_equipment_label.strip()
            equipment_label = (
                tr(
                    "artifact.build.applied_preset_for_character",
                    preset=applied_label,
                    name=target_name,
                )
                if applied_label
                else tr(
                    "artifact.build.current_equipment_for_character",
                    name=target_name,
                )
            )
            self.equipment_zone_label.setText(equipment_label)

    def _target_button_checked(self, key: str) -> bool:
        return key in self.selected_build_target_keys

    def _sync_build_target_button_selection(self) -> None:
        operation_key = self._right_panel_operation_target_key()
        if self.build_target_reset_button is not None:
            self.build_target_reset_button.setEnabled(bool(self.selected_build_target_keys))
        for key, button in self.build_target_buttons_by_key.items():
            was_blocked = button.blockSignals(True)
            button.setChecked(self._target_button_checked(key))
            button.setProperty("operationTarget", key == operation_key)
            button.style().unpolish(button)
            button.style().polish(button)
            button.blockSignals(was_blocked)

    def set_position(self, pos: int) -> None:
        self.current_pos = pos
        self.apply_current_filters()

    def on_sets_filter_enabled_changed(self, checked: bool) -> None:
        self.sets_filter_enabled = checked
        self.update_sets_filter_switch_text()
        self.apply_current_filters()

    def show_sets_popup(self) -> None:
        if self._suppress_next_sets_popup_open:
            self._suppress_next_sets_popup_open = False
            return

        if self._sets_popup is None:
            self._sets_popup = SetsFilterPopup(
                game_sets=self.store.game_set_options,
                custom_sets=self.store.custom_set_options,
                selected_game_set_ids=self.selected_game_set_ids,
                selected_custom_set_ids=self.selected_custom_set_ids,
                on_selection_changed=self.on_sets_selection_changed,
                on_custom_set_create=self.create_and_edit_custom_set,
                on_custom_set_edit=self.start_custom_set_edit,
                on_custom_set_delete=self.delete_custom_set_from_popup,
                parent=self,
            )
            self._sets_popup.installEventFilter(self)

        button_pos = self.sets_button.mapToGlobal(QPoint(0, self.sets_button.height() + 4))
        self._move_popup_inside_screen(self._sets_popup, button_pos)
        self._sets_popup.show()
        self._sets_popup.raise_()
        self._sets_popup.activateWindow()

    def show_sort_popup(self) -> None:
        if self._suppress_next_sort_popup_open:
            self._suppress_next_sort_popup_open = False
            return

        if self._sort_popup is None:
            self._sort_popup = SortStatsPopup(
                selected_stat_types=self.selected_sort_stat_types,
                on_selection_changed=self.on_sort_selection_changed,
                parent=self,
            )
            self._sort_popup.installEventFilter(self)

        button_pos = self.sort_button.mapToGlobal(QPoint(0, self.sort_button.height() + 4))
        self._move_popup_inside_screen(self._sort_popup, button_pos)
        self._sort_popup.show()
        self._sort_popup.raise_()
        self._sort_popup.activateWindow()

    def on_sets_button_pressed(self) -> None:
        if self._sets_popup is not None and self._sets_popup.isVisible():
            self._suppress_next_sets_popup_open = True
            self._sets_popup.close()

    def on_sort_button_pressed(self) -> None:
        if self._sort_popup is not None and self._sort_popup.isVisible():
            self._suppress_next_sort_popup_open = True
            self._sort_popup.close()

    def on_build_target_region_button_pressed(self) -> None:
        if self._region_popup is not None and self._region_popup.isVisible():
            self._suppress_next_region_popup_open = True
            self._region_popup.close()

    def show_region_filter_popup(self) -> None:
        if self.build_target_region_button is None:
            return

        if self._suppress_next_region_popup_open:
            self._suppress_next_region_popup_open = False
            self._sync_build_target_region_filter_button()
            return

        self._sync_build_target_region_filter_button()

        if self._region_popup is None:
            self._region_popup = RegionFilterPopup(
                options=self._build_region_filter_options(),
                selected_region_keys=self.build_target_region_filters,
                on_selection_changed=self.on_region_filter_selection_changed,
                parent=self,
            )
            self._region_popup.installEventFilter(self)

        popup_size = self._region_popup.sizeHint().expandedTo(
            self._region_popup.minimumSize()
        )
        button_pos = self.build_target_region_button.mapToGlobal(
            QPoint(-popup_size.width() - 4, 0)
        )
        self._move_popup_inside_screen(
            self._region_popup,
            button_pos,
            anchor=self.build_target_region_button,
        )
        self._region_popup.show()
        self._region_popup.raise_()
        self._region_popup.activateWindow()

    def _move_popup_inside_screen(
        self,
        popup: QWidget,
        preferred_pos: QPoint,
        *,
        anchor: QWidget | None = None,
    ) -> None:
        anchor = anchor or self.sets_button
        popup_size = popup.sizeHint().expandedTo(popup.minimumSize())
        popup.resize(popup_size)

        screen = anchor.screen() or self.screen() or QApplication.primaryScreen()
        if screen is None:
            popup.move(preferred_pos)
            return

        available = screen.availableGeometry()

        x = preferred_pos.x()
        y = preferred_pos.y()

        max_x = available.x() + available.width() - popup_size.width()
        max_y = available.y() + available.height() - popup_size.height()

        if x > max_x:
            x = max_x
        if x < available.x():
            x = available.x()

        if y > max_y:
            above_pos = anchor.mapToGlobal(
                QPoint(0, -popup_size.height() - 4)
            )
            y = above_pos.y() if above_pos.y() >= available.y() else max_y

        if y < available.y():
            y = available.y()

        popup.move(QPoint(x, y))

    def on_region_filter_selection_changed(self, selected_region_keys: set[str]) -> None:
        self.build_target_region_filters = set(selected_region_keys)
        self.sync_build_target_filter_buttons()
        self.refresh_build_target_list()

    def _sync_build_target_region_filter_button(self) -> None:
        if self.build_target_region_button is None:
            return
        self.build_target_region_button.setChecked(bool(self.build_target_region_filters))

    def on_sets_selection_changed(
        self,
        selected_game_set_ids: set[str],
        selected_custom_set_ids: set[int],
    ) -> None:
        self.selected_game_set_ids = set(selected_game_set_ids)
        self.selected_custom_set_ids = set(selected_custom_set_ids)
        self.update_sets_button_text()
        self.apply_current_filters()

    def on_sort_selection_changed(self, selected_stat_types: list[int]) -> None:
        self.selected_sort_stat_types = list(selected_stat_types[:4])
        self.update_sort_button_text()
        self.apply_current_filters()

    def update_sort_button_text(self) -> None:
        count = len(self.selected_sort_stat_types)
        self.sort_button.setText(
            tr("artifact.sort.button_count", count=count)
            if count
            else tr("artifact.sort.button")
        )

    def update_sets_button_text(self) -> None:
        count = len(self.selected_game_set_ids) + len(self.selected_custom_set_ids)
        self.sets_button.setText(
            tr("artifact.sets.button_count", count=count)
            if count
            else tr("artifact.sets.button")
        )

    def update_sets_filter_switch_text(self) -> None:
        self.sets_filter_switch.setText(
            tr("artifact.sets.filter_on")
            if self.sets_filter_enabled
            else tr("artifact.sets.filter_off")
        )

    def apply_current_filters(self) -> None:
        total_start = perf_now()
        if not self.store.database_exists:
            model_start = perf_now()
            model_changed = self._set_visible_artifact_ids([])
            model_ms = perf_ms(model_start)
            self.status_label.setText(tr("artifact.browser.database_missing"))
            self.empty_label.setText(tr("artifact.browser.import_first"))
            log_perf(
                "artifact_filter_apply",
                total=perf_ms(total_start),
                database_missing=True,
                model=model_ms,
                model_changed=model_changed,
                visible=0,
                total_count=0,
            )
            return

        base_start = perf_now()
        base_ids = self.store.ids_for_position(self.current_pos)
        visible_ids = list(base_ids)
        base_ms = perf_ms(base_start)

        selected_any_sets = bool(self.selected_game_set_ids or self.selected_custom_set_ids)

        set_filter_start = perf_now()
        if self.sets_filter_enabled and selected_any_sets:
            allowed_ids: set[int] = set()
            allowed_ids.update(self.store.ids_for_game_sets(self.selected_game_set_ids))
            allowed_ids.update(self.store.ids_for_custom_sets(self.selected_custom_set_ids))
            visible_ids = [
                artifact_id
                for artifact_id in base_ids
                if artifact_id in allowed_ids
            ]
        set_filter_ms = perf_ms(set_filter_start)

        sort_start = perf_now()
        visible_ids = self.store.sort_artifact_ids(
            visible_ids,
            self.selected_sort_stat_types,
        )
        sort_ms = perf_ms(sort_start)

        priority_start = perf_now()
        priority_ids = self.current_highlight_artifact_ids()
        if priority_ids:
            visible_ids = sorted(
                visible_ids,
                key=lambda artifact_id: 0 if artifact_id in priority_ids else 1,
            )
        priority_ms = perf_ms(priority_start)

        model_start = perf_now()
        model_changed = self._set_visible_artifact_ids(visible_ids)
        model_ms = perf_ms(model_start)

        status_start = perf_now()
        self.update_status(len(visible_ids), len(base_ids))
        status_ms = perf_ms(status_start)
        log_perf(
            "artifact_filter_apply",
            total=perf_ms(total_start),
            pos=self.current_pos,
            base=base_ms,
            set_filter=set_filter_ms,
            sort=sort_ms,
            priority=priority_ms,
            model=model_ms,
            status=status_ms,
            model_changed=model_changed,
            selected_sets=len(self.selected_game_set_ids) + len(self.selected_custom_set_ids),
            sort_stats=len(self.selected_sort_stat_types),
            visible=len(visible_ids),
            total_count=len(base_ids),
        )

    def _set_visible_artifact_ids(self, visible_ids: list[int]) -> bool:
        if list(visible_ids) == self.model.artifact_ids:
            return False
        self.model.set_artifact_ids(visible_ids)
        return True

    def update_status(self, visible_count: int, total_count: int) -> None:
        slot_name = self._position_label(self.current_pos)
        self.status_label.setText(f"{slot_name}: {visible_count}/{total_count}")

        if total_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty"))
        elif visible_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty_for_sets"))
        else:
            self.empty_label.setText("")

    def update_json_import_actions(self) -> None:
        if self.import_json_button is None or self.clear_json_button is None:
            return
        if self.edit_selection_mode != EDIT_MODE_NONE:
            self._set_json_action_button(
                self.import_json_button,
                object_name="json_edit_save_button",
                text="",
                icon_name="save",
                tooltip=self.active_save_tooltip(),
                callback=self.save_active_edit,
                enabled=True,
            )
            self._set_json_action_button(
                self.clear_json_button,
                object_name="json_edit_cancel_button",
                text="",
                icon_name="x",
                tooltip=self.active_cancel_tooltip(),
                callback=self.cancel_active_edit,
                enabled=True,
            )
            return

        self._set_json_action_button(
            self.import_json_button,
            object_name="json_action_button",
            text=tr("artifact.json.import_button"),
            icon_name=None,
            tooltip="",
            callback=self.import_artiscan_json,
            enabled=True,
        )
        self._set_json_action_button(
            self.clear_json_button,
            object_name="json_action_button",
            text=tr("artifact.json.clear_button"),
            icon_name=None,
            tooltip="",
            callback=self.clear_json_imports,
            enabled=json_imports_available(),
        )

    def _set_json_action_button(
        self,
        button: QPushButton,
        *,
        object_name: str,
        text: str,
        icon_name: str | None,
        tooltip: str,
        callback,
        enabled: bool,
    ) -> None:
        try:
            button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        button.setObjectName(object_name)
        button.setText(text)
        button.setIcon(self._ui_icon(icon_name) if icon_name is not None else QIcon())
        button.setToolTip(tooltip)
        button.setEnabled(enabled)
        button.clicked.connect(callback)
        button.style().unpolish(button)
        button.style().polish(button)
        self._prepare_button_for_first_show(button)

    def _confirm_json_action(self) -> bool:
        return (
            self.confirm_discard_custom_edit()
            and self.confirm_discard_build_edit()
        )

    def _reload_after_json_action(self) -> None:
        self.reload_from_database(
            reset_filters=False,
            reset_sort=False,
            confirm_custom_edit=False,
        )

    def import_artiscan_json(self) -> None:
        run_artiscan_import_action(
            self,
            confirm_ready=self._confirm_json_action,
            reload_database=self._reload_after_json_action,
            update_actions=self.update_json_import_actions,
        )

    def clear_json_imports(self) -> None:
        run_clear_json_imports_action(
            self,
            confirm_ready=self._confirm_json_action,
            reload_database=self._reload_after_json_action,
            update_actions=self.update_json_import_actions,
        )

    def reload_from_database(
        self,
        *,
        keep_custom_edit: bool = False,
        reset_filters: bool = True,
        reset_sort: bool = True,
        reset_popup: bool = True,
        confirm_custom_edit: bool = True,
    ) -> None:
        if confirm_custom_edit and not keep_custom_edit:
            if not self.confirm_discard_custom_edit():
                return
            if not self.confirm_discard_build_edit():
                return

        self.store = ArtifactBrowserStore.load_from_db(self.db_path)
        self.model.set_store(self.store)
        self._clear_build_row_pixmap_cache()
        self._clear_target_preview_pixmap_cache()
        self.load_build_target_items()
        if not keep_custom_edit:
            self.finish_custom_set_edit()
            self.finish_build_preset_edit()
        if reset_popup:
            if self._sets_popup is not None:
                self._sets_popup.close()
            self._sets_popup = None
            if self._region_popup is not None:
                self._region_popup.close()
            self._region_popup = None
        if reset_filters:
            self.selected_game_set_ids.clear()
            self.selected_custom_set_ids.clear()
        self.update_sets_button_text()
        self.apply_current_filters()
        if reset_sort:
            self._sort_popup = None
            self.selected_sort_stat_types.clear()
            self.update_sort_button_text()
        self.load_build_presets()
        self.refresh_build_target_list()
        self.update_json_import_actions()
        self.update_custom_edit_bar()
        self.update_build_panel()

    def on_artifact_clicked(self, index) -> None:
        artifact = index.data(ArtifactRoles.ArtifactRole)
        if artifact is None:
            return

        if self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            self.toggle_custom_set_artifact(artifact.id)
            return

        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.assign_build_artifact(artifact.id)
            return

        if self.equip_mode_enabled:
            self.equip_clicked_artifact(artifact.id)

    def equip_clicked_artifact(self, artifact_id: int) -> None:
        if not self.equip_mode_enabled or self.operation_target_character_id is None:
            return
        try:
            artifact_id = int(artifact_id)
        except (TypeError, ValueError):
            return
        try:
            with closing(connect_db(self.db_path)) as conn:
                result = equip_artifact(
                    conn,
                    self.operation_target_character_id,
                    artifact_id,
                )
                conn.commit()
        except EquipmentError as exc:
            self.status_label.setText(str(exc))
            log_perf("artifact_equip_failed", artifact_id=artifact_id, error=str(exc))
            return
        except Exception as exc:
            self.status_label.setText(str(exc))
            log_perf("artifact_equip_failed", artifact_id=artifact_id, error=str(exc))
            return

        self.refresh_equipment_target_state()
        self.applied_current_equipment_label = ""
        self.refresh_current_equipment_markers(result.affected_artifact_ids)
        self.update_build_panel()
        self.update_edit_selection_mode()
        self.equipment_changed.emit(result)

    def refresh_current_equipment_markers(self, artifact_ids) -> None:
        artifact_ids = sorted({int(artifact_id) for artifact_id in artifact_ids or []})
        if not artifact_ids:
            return

        owners = self._current_equipment_owners(artifact_ids)
        changed_rows: list[int] = []
        for artifact_id in artifact_ids:
            try:
                artifact = self.store.artifact(artifact_id)
            except KeyError:
                continue
            owner = owners.get(artifact_id)
            next_owner_id = (
                int(owner["character_id"])
                if owner is not None and owner.get("character_id") is not None
                else None
            )
            next_name = str(owner.get("character_name") or "") if owner else ""
            next_icon_path = (
                self._resolve_existing_path(owner.get("side_icon_path"))
                if owner
                else None
            )
            if (
                artifact.character_name == next_name
                and artifact.owner_character_id == next_owner_id
                and artifact.owner_icon_path == next_icon_path
            ):
                continue
            artifact.character_name = next_name
            artifact.owner_character_id = next_owner_id
            artifact.owner_icon_path = next_icon_path
            changed_rows.extend(
                row
                for row, row_artifact_id in enumerate(self.model.artifact_ids)
                if int(row_artifact_id) == artifact_id
            )

        for row in changed_rows:
            index = self.model.index(row, 0)
            self.model.dataChanged.emit(
                index,
                index,
                [ArtifactRoles.ArtifactRole, Qt.ItemDataRole.DisplayRole],
            )
        if changed_rows:
            self.list_view.viewport().update()

    def _current_equipment_owners(self, artifact_ids: list[int]) -> dict[int, dict]:
        if not artifact_ids:
            return {}
        placeholders = ",".join("?" for _ in artifact_ids)
        try:
            with closing(connect_db(self.db_path)) as conn:
                rows = conn.execute(
                    f"""
                    SELECT
                        equipped.artifact_id,
                        equipped.character_id,
                        characters.name AS character_name
                        , characters.side_icon_path AS side_icon_path
                    FROM account_character_equipped_artifacts AS equipped
                    JOIN account_characters AS characters
                        ON characters.character_id = equipped.character_id
                    WHERE equipped.artifact_id IN ({placeholders})
                    """,
                    tuple(artifact_ids),
                ).fetchall()
        except Exception as exc:
            log_perf("artifact_owner_marker_refresh_failed", error=str(exc))
            return {}
        return {
            int(row["artifact_id"]): {
                "character_id": int(row["character_id"]),
                "character_name": str(row["character_name"] or ""),
                "side_icon_path": str(row["side_icon_path"] or ""),
            }
            for row in rows
        }

    @staticmethod
    def _resolve_existing_path(path_value) -> Path | None:
        text = str(path_value or "").strip()
        if not text:
            return None
        path = Path(text)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path if path.exists() and path.is_file() else None

    def apply_selected_build_preset_to_current_equipment(self) -> None:
        if (
            not self.equip_mode_enabled
            or self.operation_target_character_id is None
            or self.selected_build_id is None
            or self.edit_selection_mode != EDIT_MODE_NONE
        ):
            return

        target_character_id = int(self.operation_target_character_id)
        applied_label = self._selected_build_preset_name()
        preset_slots = {
            int(pos): int(artifact_id)
            for pos, artifact_id in self.selected_build_slots.items()
            if artifact_id is not None
        }

        if not self._confirm_selected_preset_conflicts(
            target_character_id,
            preset_slots.values(),
        ):
            return

        affected_character_ids: set[int] = set()
        affected_artifact_ids: set[int] = set()
        changed = False
        try:
            with closing(connect_db(self.db_path)) as conn:
                for pos in ARTIFACT_POSITIONS:
                    artifact_id = preset_slots.get(pos)
                    if artifact_id is None:
                        result = unequip_artifact_slot(
                            conn,
                            target_character_id,
                            pos,
                            source="preset_equip",
                        )
                    else:
                        result = equip_artifact(
                            conn,
                            target_character_id,
                            artifact_id,
                            source="preset_equip",
                        )
                    changed = changed or result.changed
                    affected_character_ids.update(result.affected_character_ids)
                    affected_artifact_ids.update(result.affected_artifact_ids)
                conn.commit()
        except EquipmentError as exc:
            self.status_label.setText(str(exc))
            log_perf("artifact_preset_equip_failed", error=str(exc))
            return
        except Exception as exc:
            self.status_label.setText(str(exc))
            log_perf("artifact_preset_equip_failed", error=str(exc))
            return

        self.selected_build_id = None
        self.selected_build_slots = {}
        self.selected_build_targets = []
        self.pending_delete_build_id = None
        self.applied_current_equipment_label = (
            applied_label or tr("artifact.build.current_equipment")
        )
        self.refresh_current_equipment_markers(affected_artifact_ids)
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.update_build_create_controls()
        self.update_edit_selection_mode()
        self.equipment_changed.emit(
            EquipmentChangeResult(
                operation="apply_build_preset",
                changed=changed,
                affected_character_ids=tuple(sorted(affected_character_ids)),
                affected_artifact_ids=tuple(sorted(affected_artifact_ids)),
            )
        )

    def _selected_build_preset_name(self) -> str:
        selected_id = self.selected_build_id
        if selected_id is None:
            return ""
        for preset in self.build_presets:
            try:
                if int(preset.get("id")) == int(selected_id):
                    return str(preset.get("name") or "").strip()
            except (TypeError, ValueError):
                continue
        preset = get_build_preset(int(selected_id), db_path=self.db_path)
        return str((preset or {}).get("name") or "").strip()

    def _confirm_selected_preset_conflicts(
        self,
        target_character_id: int,
        artifact_ids,
    ) -> bool:
        conflict_character_ids = self._preset_conflict_character_ids(
            target_character_id,
            artifact_ids,
        )
        if not conflict_character_ids:
            return True
        return self.confirm_preset_equipment_conflicts(conflict_character_ids)

    def _preset_conflict_character_ids(
        self,
        target_character_id: int,
        artifact_ids,
    ) -> tuple[int, ...]:
        owners: set[int] = set()
        try:
            with closing(connect_db(self.db_path)) as conn:
                for artifact_id in artifact_ids:
                    owner = get_equipped_artifact_owner(conn, artifact_id)
                    if owner is not None and int(owner) != int(target_character_id):
                        owners.add(int(owner))
        except Exception as exc:
            log_perf("artifact_preset_conflict_check_failed", error=str(exc))
            return ()
        return tuple(sorted(owners))

    def confirm_preset_equipment_conflicts(
        self,
        character_ids: tuple[int, ...],
    ) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("artifact.equipment.apply_preset"))
        dialog.setText(tr("artifact.equipment.conflict_confirm"))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        icon_pixmap = self._conflict_character_strip_pixmap(character_ids)
        if icon_pixmap is not None and not icon_pixmap.isNull():
            dialog.setIconPixmap(icon_pixmap)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def _conflict_character_strip_pixmap(
        self,
        character_ids: tuple[int, ...],
    ) -> QPixmap | None:
        targets = [
            self._equipment_character_target(character_id)
            for character_id in character_ids
        ]
        targets = [target for target in targets if target is not None]
        if not targets:
            return None
        return self._cached_target_preview_strip(targets)

    def _equipment_character_target(self, character_id: int) -> dict | None:
        key = self._character_target_key(character_id)
        item = self.build_target_items_by_key.get(key)
        if item is not None:
            return {
                "target_type": "character",
                "character_id": character_id,
                "character_name": item.get("character_name") or str(character_id),
            }
        try:
            with closing(connect_db(self.db_path)) as conn:
                row = conn.execute(
                    """
                    SELECT name
                    FROM account_characters
                    WHERE character_id = ?
                    """,
                    (character_id,),
                ).fetchone()
        except Exception:
            row = None
        return {
            "target_type": "character",
            "character_id": character_id,
            "character_name": (row["name"] if row is not None else str(character_id)),
        }

    def toggle_custom_set_artifact(self, artifact_id: int) -> None:
        if artifact_id in self.editing_custom_artifact_ids:
            self.editing_custom_artifact_ids.remove(artifact_id)
        else:
            self.editing_custom_artifact_ids.add(artifact_id)

        self.editing_custom_dirty = True
        self.update_edit_selection_mode()

    def create_and_edit_custom_set(self, name: str) -> None:
        name = name.strip()
        if not name:
            self.empty_label.setText(tr("artifact.custom.empty_name"))
            return

        if not self.confirm_discard_custom_edit():
            return
        if not self.confirm_discard_build_edit():
            return

        tag_id = create_custom_set(name)
        if self._sets_popup is not None:
            self._sets_popup.close()
            self._sets_popup = None
        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            confirm_custom_edit=False,
        )
        self.start_custom_set_edit(tag_id)
        self._sets_popup = None

    def start_custom_set_edit(self, tag_id: int) -> None:
        if self.editing_build_dirty:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            return
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.finish_build_preset_edit()

        if tag_id != self.editing_custom_set_id:
            if not self.confirm_discard_custom_edit():
                return

        option = next(
            (
                option
                for option in self.store.custom_set_options
                if option.tag_id == tag_id
            ),
            None,
        )

        self.editing_custom_set_id = int(tag_id)
        self.editing_custom_set_name = option.name if option else str(tag_id)
        self.editing_custom_artifact_ids = get_custom_set_artifact_ids(tag_id)
        self.editing_custom_dirty = False

        if tag_id in self.selected_custom_set_ids:
            self.selected_custom_set_ids.remove(tag_id)
            self.update_sets_button_text()
            self.apply_current_filters()

        self.edit_selection_mode = EDIT_MODE_CUSTOM_SET
        self.update_edit_selection_mode()

        if self._sets_popup is not None:
            self._sets_popup.close()
            self._sets_popup = None

    def _clear_layout(self, layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _load_character_region_data(self) -> None:
        self._character_region_by_name = {}
        self._region_names_by_key = {}

        try:
            entries = load_character_region_catalog(self.store.content_language)
        except Exception as exc:
            print(f"Failed to load HoYoWiki character region catalog: {exc}")
            entries = []

        for entry in entries:
            normalized_name = str(entry.get("normalized_name") or "").strip()
            region_key = str(entry.get("region_key") or "").strip()
            region_name = str(entry.get("region_name") or "").strip()
            if not normalized_name or not region_key:
                continue

            self._character_region_by_name.setdefault(normalized_name, entry)
            if region_name:
                self._region_names_by_key.setdefault(region_key, region_name)

    @staticmethod
    def _with_character_region(asset: dict, entry: dict | None) -> dict:
        if not entry:
            return asset

        region_key = str(entry.get("region_key") or "").strip()
        if not region_key:
            return asset

        asset_copy = dict(asset)
        metadata = dict(asset_copy.get("metadata") or {})
        character = dict(metadata.get("character") or {})
        character["region_key"] = region_key
        character["region_name"] = str(entry.get("region_name") or "").strip()
        metadata["character"] = character
        metadata["region_key"] = region_key
        asset_copy["metadata"] = metadata
        return asset_copy

    def load_build_target_items(self) -> None:
        self._load_character_region_data()
        self.build_target_items_by_key = {
            BUILD_TARGET_UNIVERSAL_KEY: {
                "key": BUILD_TARGET_UNIVERSAL_KEY,
                "target_type": "universal",
                "character_id": None,
                "character_name": tr("artifact.build.target_universal"),
                "asset": None,
                "path": None,
            }
        }
        if self._preloaded_character_asset_items is not None:
            assets = list(self._preloaded_character_asset_items)
        else:
            assets = load_account_character_asset_items()

        for asset in assets:
            char_id = character_id(asset)
            if char_id is None:
                continue
            region_entry = self._character_region_by_name.get(
                normalize_character_name(character_name(asset))
            )
            asset = self._with_character_region(asset, region_entry)
            key = self._character_target_key(char_id)
            self.build_target_items_by_key[key] = {
                "key": key,
                "target_type": "character",
                "character_id": char_id,
                "character_name": character_name(asset),
                "asset": asset,
                "path": asset.get("path"),
                "region_key": (region_entry or {}).get("region_key") or "",
                "region_name": (region_entry or {}).get("region_name") or "",
            }

    def _region_icon_path(self, region_key: str) -> Path | None:
        icon_name = REGION_ICON_FILES.get(region_key)
        if icon_name:
            path = FILTER_ASSETS_DIR / icon_name
            if path.exists():
                return path

        fallback = FILTER_ASSETS_DIR / "Map.png"
        return fallback if fallback.exists() else None

    def _region_display_name(self, region_key: str) -> str:
        label_key = REGION_LABEL_KEYS.get(region_key)
        if label_key:
            return tr(label_key)

        return (
            self._region_names_by_key.get(region_key)
            or region_key.replace("_", " ").replace("-", " ").title()
        )

    def _build_region_filter_options(self) -> list[dict]:
        counts: dict[str, int] = {}
        for key, item in self.build_target_items_by_key.items():
            if key == BUILD_TARGET_UNIVERSAL_KEY:
                continue
            region_key = str(item.get("region_key") or "")
            if not region_key:
                continue
            counts[region_key] = counts.get(region_key, 0) + 1

        keys = [
            key
            for key in REGION_ORDER
            if key in counts or key in self.build_target_region_filters
        ]
        extra_keys = sorted(
            key
            for key in set(counts) | set(self.build_target_region_filters)
            if key not in REGION_ORDER
        )
        keys.extend(extra_keys)

        return [
            {
                "key": key,
                "name": self._region_display_name(key),
                "count": counts.get(key, 0),
                "icon_path": self._region_icon_path(key),
            }
            for key in keys
        ]

    def refresh_build_target_list(self) -> None:
        total_start = perf_now()
        if not hasattr(self, "build_target_list_layout"):
            return

        self.build_target_reset_button.setEnabled(bool(self.selected_build_target_keys))
        sync_start = perf_now()
        self.sync_build_target_filter_buttons()
        sync_ms = perf_ms(sync_start)

        ensure_start = perf_now()
        created_buttons = self._ensure_build_target_buttons()
        ensure_ms = perf_ms(ensure_start)

        filter_start = perf_now()
        visible_keys = self._visible_build_target_keys()
        filter_ms = perf_ms(filter_start)

        update_start = perf_now()
        shown_count = 0
        hidden_count = 0
        for key in self._build_target_button_order:
            button = self.build_target_buttons_by_key.get(key)
            if button is None:
                continue
            should_show = key in visible_keys
            if button.property("targetVisible") != should_show:
                if should_show:
                    shown_count += 1
                else:
                    hidden_count += 1
                button.setProperty("targetVisible", should_show)
                button.setVisible(should_show)
            self._sync_build_target_button_state(key, button)
        update_ms = perf_ms(update_start)
        visible_character_count = max(
            0,
            len([key for key in visible_keys if key != BUILD_TARGET_UNIVERSAL_KEY]),
        )
        log_perf(
            "artifact_target_filter_refresh",
            total=perf_ms(total_start),
            sync=sync_ms,
            ensure=ensure_ms,
            filter=filter_ms,
            update=update_ms,
            mode="in_place",
            created_buttons=created_buttons,
            shown=shown_count,
            hidden=hidden_count,
            visible=visible_character_count,
            total_targets=max(0, len(self.build_target_items_by_key) - 1),
            standard=self.build_target_standard_filter,
            selected_filters=int(self.any_build_target_filters_selected()),
        )

    def _make_build_target_button(self, item: dict) -> QPushButton:
        key = item["key"]
        button = MarqueeButton(item.get("character_name") or "")
        button.setObjectName("target_item")
        button.setCheckable(True)
        button.setMinimumWidth(TARGET_ITEM_MIN_WIDTH)
        button.setFixedHeight(TARGET_ITEM_BUTTON_HEIGHT)
        button.setChecked(self._target_button_checked(key))
        button.setProperty("operationTarget", key == self._right_panel_operation_target_key())
        button.setProperty("targetIconSource", "")
        button.setProperty("targetVisible", True)
        path = item.get("path")
        if key == BUILD_TARGET_UNIVERSAL_KEY:
            button.setIcon(self._cached_universal_target_icon())
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
            button.setProperty("targetIconSource", BUILD_TARGET_UNIVERSAL_KEY)
        elif path:
            button.setIcon(QIcon(str(path)))
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
            button.setProperty("targetIconSource", str(path))
        button.clicked.connect(
            lambda checked=False, value=key: self.toggle_build_target(value)
        )
        self.build_target_buttons_by_key[key] = button
        return button

    def _ensure_build_target_buttons(self) -> int:
        created = 0
        if not self._build_target_buttons_initialized:
            for item in self._ordered_build_target_items():
                key = item["key"]
                if key in self.build_target_buttons_by_key:
                    continue
                button = self._make_build_target_button(item)
                self.build_target_list_layout.addWidget(button)
                self._build_target_button_order.append(key)
                created += 1
            self.build_target_list_layout.addStretch()
            self._build_target_list_stretch_added = True
            self._build_target_buttons_initialized = True
            return created

        for item in self._ordered_build_target_items():
            key = item["key"]
            button = self.build_target_buttons_by_key.get(key)
            if button is None:
                button = self._make_build_target_button(item)
                insert_at = self._build_target_insert_index(key)
                self.build_target_list_layout.insertWidget(insert_at, button)
                self._build_target_button_order.insert(insert_at, key)
                created += 1
            else:
                self._sync_build_target_button_content(button, item)
        if not self._build_target_list_stretch_added:
            self.build_target_list_layout.addStretch()
            self._build_target_list_stretch_added = True
        return created

    def _ordered_build_target_items(self) -> list[dict]:
        universal = self.build_target_items_by_key.get(BUILD_TARGET_UNIVERSAL_KEY)
        character_items = [
            item
            for key, item in self.build_target_items_by_key.items()
            if key != BUILD_TARGET_UNIVERSAL_KEY
        ]
        character_items.sort(key=lambda item: character_sort_key(item.get("asset") or {}))
        return ([universal] if universal else []) + character_items

    def _build_target_insert_index(self, key: str) -> int:
        ordered_keys = [item["key"] for item in self._ordered_build_target_items()]
        try:
            desired_index = ordered_keys.index(key)
        except ValueError:
            desired_index = len(self._build_target_button_order)
        return min(desired_index, len(self._build_target_button_order))

    def _visible_build_target_keys(self) -> set[str]:
        visible_keys = {BUILD_TARGET_UNIVERSAL_KEY}
        operation_key = self._right_panel_operation_target_key()
        for key, item in self.build_target_items_by_key.items():
            if key == BUILD_TARGET_UNIVERSAL_KEY:
                continue
            if (
                key in self.selected_build_target_keys
                or key == operation_key
                or character_matches_filters(
                    item.get("asset") or {},
                    self.build_target_element_filters,
                    self.build_target_weapon_filters,
                    self.build_target_rarity_filters,
                    self.build_target_region_filters,
                    self.build_target_trait_filters,
                    self.build_target_standard_filter,
                )
            ):
                visible_keys.add(key)
        return visible_keys

    def _sync_build_target_button_content(self, button: QPushButton, item: dict) -> None:
        text = item.get("character_name") or ""
        if button.text() != text:
            button.setText(text)
        icon_source = BUILD_TARGET_UNIVERSAL_KEY if item["key"] == BUILD_TARGET_UNIVERSAL_KEY else str(item.get("path") or "")
        if button.property("targetIconSource") == icon_source:
            return
        if item["key"] == BUILD_TARGET_UNIVERSAL_KEY:
            button.setIcon(self._cached_universal_target_icon())
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
        elif item.get("path"):
            button.setIcon(QIcon(str(item.get("path"))))
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
        else:
            button.setIcon(QIcon())
        button.setProperty("targetIconSource", icon_source)

    def _sync_build_target_button_state(self, key: str, button: QPushButton) -> None:
        operation_target = key == self._right_panel_operation_target_key()
        checked = self._target_button_checked(key)
        was_blocked = button.blockSignals(True)
        if button.isChecked() != checked:
            button.setChecked(checked)
        if button.property("operationTarget") != operation_target:
            button.setProperty("operationTarget", operation_target)
            button.style().unpolish(button)
            button.style().polish(button)
        button.blockSignals(was_blocked)

    def on_build_target_filter_clicked(self, selected_values: set, value, checked: bool) -> None:
        if checked:
            selected_values.add(value)
        else:
            selected_values.discard(value)
        self.sync_build_target_filter_buttons()
        self.refresh_build_target_list()

    def any_build_target_filters_selected(self) -> bool:
        return bool(
            self.build_target_element_filters
            or self.build_target_weapon_filters
            or self.build_target_rarity_filters
            or self.build_target_region_filters
            or self.build_target_trait_filters
            or self.build_target_standard_filter != STANDARD_FILTER_ALL
        )

    def sync_build_target_filter_buttons(self) -> None:
        for button, selected_values, value in self.build_target_filter_buttons:
            button.setChecked(value in selected_values)
        self._sync_build_target_region_filter_button()
        if getattr(self, "build_target_standard_button", None) is not None:
            self.build_target_standard_button.setProperty(
                "standardOnly",
                self.build_target_standard_filter == STANDARD_FILTER_ONLY
            )
            self.build_target_standard_button.style().unpolish(
                self.build_target_standard_button
            )
            self.build_target_standard_button.style().polish(
                self.build_target_standard_button
            )
            self.build_target_standard_button.setIcon(
                standard_character_filter_icon(
                    self.build_target_standard_filter,
                    size=TARGET_FILTER_ICON_SIZE,
                )
            )
        if self._region_popup is not None:
            self._region_popup.set_selected_region_keys(
                self.build_target_region_filters
            )
        if self.build_target_filter_reset_button is not None:
            self.build_target_filter_reset_button.setEnabled(
                self.any_build_target_filters_selected()
            )

    def reset_build_target_filters(self) -> None:
        if not self.any_build_target_filters_selected():
            return

        self.build_target_element_filters.clear()
        self.build_target_weapon_filters.clear()
        self.build_target_rarity_filters.clear()
        self.build_target_region_filters.clear()
        self.build_target_trait_filters.clear()
        self.build_target_standard_filter = STANDARD_FILTER_ALL
        self.sync_build_target_filter_buttons()
        self.refresh_build_target_list()

    def reset_build_targets(self) -> None:
        if not self.selected_build_target_keys:
            return

        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            if not self.confirm_discard_build_edit():
                self.refresh_build_target_list()
                return
            if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
                self.finish_build_preset_edit()

        if self._right_panel_operation_target_key() in self.selected_build_target_keys:
            self._right_panel_target_selection_suppressed = True
        self.selected_build_target_keys.clear()
        self.selected_build_id = None
        self.selected_build_slots = {}
        self.selected_build_targets = []
        self.pending_delete_build_id = None
        self.refresh_build_target_list()
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.update_edit_selection_mode()
        self.apply_current_filters()

    def toggle_build_target(self, key: str) -> None:
        next_keys = set(self.selected_build_target_keys)
        operation_key = self._right_panel_operation_target_key()
        if key in next_keys:
            next_keys.remove(key)
            if key == operation_key:
                self._right_panel_target_selection_suppressed = True
        else:
            next_keys.add(key)
            if key == operation_key:
                self._right_panel_target_selection_suppressed = False

        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET and not next_keys:
            self.empty_label.setText(tr("artifact.build.no_target_hint"))
            self.refresh_build_target_list()
            return

        self.selected_build_target_keys = next_keys
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.editing_build_targets = self.targets_from_selected_build_keys()
            self.editing_build_dirty = True
        else:
            self.selected_build_id = None
            self.selected_build_slots = {}
            self.selected_build_targets = []

        self.pending_delete_build_id = None
        self._sync_build_target_button_selection()
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.update_edit_selection_mode()
        if self.edit_selection_mode == EDIT_MODE_NONE:
            self.apply_current_filters()

    def _character_target_key(self, character_id_value: int) -> str:
        return f"character:{int(character_id_value)}"

    def target_key_from_target(self, target: dict) -> str | None:
        target_type = target.get("target_type")
        if target_type == "universal":
            return BUILD_TARGET_UNIVERSAL_KEY
        if target_type == "character" and target.get("character_id") is not None:
            return self._character_target_key(int(target["character_id"]))
        return None

    def target_keys_from_targets(self, targets: list[dict]) -> set[str]:
        keys = set()
        for target in targets:
            key = self.target_key_from_target(target)
            if key:
                keys.add(key)
        return keys

    def targets_from_selected_build_keys(self) -> list[dict]:
        targets = []
        for key in sorted(self.selected_build_target_keys):
            item = self.build_target_items_by_key.get(key)
            if item is None:
                continue
            if key == BUILD_TARGET_UNIVERSAL_KEY:
                targets.append({"target_type": "universal"})
            else:
                targets.append(
                    {
                        "target_type": "character",
                        "character_id": item["character_id"],
                        "character_name": item.get("character_name") or "",
                    }
                )
        return targets

    def ensure_build_target_items(self, targets: list[dict]) -> None:
        for target in targets:
            key = self.target_key_from_target(target)
            if not key or key in self.build_target_items_by_key:
                continue
            if target.get("target_type") != "character":
                continue
            self.build_target_items_by_key[key] = {
                "key": key,
                "target_type": "character",
                "character_id": target.get("character_id"),
                "character_name": target.get("character_name") or "",
                "asset": None,
                "path": None,
            }

    def current_preview_build_targets(self) -> list[dict]:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            return list(self.editing_build_targets)
        if self.selected_build_id is not None:
            return list(self.selected_build_targets)
        if self.equip_mode_enabled and self.operation_target_character_id is not None:
            target = {
                "target_type": "character",
                "character_id": self.operation_target_character_id,
                "character_name": self.operation_target_character_name,
            }
            return [target]
        return []

    def preset_matches_selected_targets(self, preset: dict) -> bool:
        if not self.selected_build_target_keys:
            return False
        preset_keys = self.target_keys_from_targets(preset.get("targets") or [])
        return self.selected_build_target_keys.issubset(preset_keys)

    def load_build_presets(self) -> None:
        self.build_presets = list_build_presets(db_path=self.db_path)
        self.refresh_build_preset_list()

    def _sync_build_preset_row_selection(self) -> None:
        for build_id, button in self.build_preset_row_buttons.items():
            was_blocked = button.blockSignals(True)
            button.setChecked(int(build_id) == self.selected_build_id)
            button.blockSignals(was_blocked)

    def refresh_build_preset_list(self) -> None:
        self._clear_layout(self.build_preset_list_layout)
        self.build_preset_row_buttons.clear()
        self.build_row_name_input = None

        has_targets = bool(self.selected_build_target_keys)
        self.build_create_row_widget.setVisible(has_targets)
        self.build_preset_list_scroll.setVisible(has_targets)
        self.build_target_hint_label.setVisible(not has_targets)
        if not has_targets:
            if self.edit_selection_mode == EDIT_MODE_NONE:
                self.selected_build_id = None
                self.selected_build_slots = {}
                self.selected_build_targets = []
            return

        filtered_presets = [
            preset
            for preset in self.build_presets
            if self.preset_matches_selected_targets(preset)
            or (
                self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
                and self.editing_build_id is not None
                and int(preset["id"]) == self.editing_build_id
            )
        ]
        if (
            self.selected_build_id is not None
            and self.edit_selection_mode == EDIT_MODE_NONE
            and all(int(preset["id"]) != self.selected_build_id for preset in filtered_presets)
        ):
            self.selected_build_id = None
            self.selected_build_slots = {}
            self.selected_build_targets = []

        if not filtered_presets:
            empty_label = QLabel(tr("artifact.build.empty_presets"))
            empty_label.setObjectName("status_label")
            empty_label.setWordWrap(True)
            self.build_preset_list_layout.addWidget(empty_label)
            empty_label.show()
            return

        for preset in filtered_presets:
            row = self._make_build_preset_row(preset)
            self.build_preset_list_layout.addWidget(row)
            row.show()
            for child in row.findChildren(QWidget):
                child.show()
        self.build_preset_list_layout.addStretch()

    def on_build_create_button_clicked(self) -> None:
        if (
            self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
            and self.editing_build_id is None
        ):
            self.save_build_preset_edit()
            return
        self.start_new_build_preset()

    def _make_build_preset_row(self, preset: dict) -> QFrame:
        build_id = int(preset["id"])
        pending = self.pending_delete_build_id == build_id
        editing_this_row = (
            self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
            and self.editing_build_id == build_id
        )

        row = QFrame()
        row.setObjectName("build_slot_row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(5)

        if editing_this_row:
            name_input = QLineEdit()
            name_input.setText(self.editing_build_name)
            name_input.setPlaceholderText(tr("artifact.build.name_placeholder"))
            name_input.textChanged.connect(self.on_inline_build_name_changed)
            layout.addWidget(name_input, 1)
            self.build_row_name_input = name_input
            name_input.setFocus()
            name_input.selectAll()
        else:
            select_button = MarqueeButton(
                tr(
                    "artifact.build.preset_row",
                    name=preset["name"],
                    count=preset["slot_count"],
                )
            )
            select_button.setCheckable(True)
            select_button.setChecked(build_id == self.selected_build_id)
            select_button.clicked.connect(
                lambda _checked=False, value=build_id: self.select_build_preset(value)
            )
            layout.addWidget(select_button, 1)
            self.build_preset_row_buttons[build_id] = select_button

        if not editing_this_row and not pending:
            self._add_build_preset_row_metadata(layout, preset)

        if pending:
            confirm_label = QLabel(tr("artifact.build.delete_confirm_short"))
            confirm_label.setObjectName("small_muted")
            layout.addWidget(confirm_label)

            confirm_button = QPushButton()
            confirm_button.setObjectName("row_save_button")
            confirm_button.setIcon(self._ui_icon("check"))
            confirm_button.setToolTip(tr("artifact.build.delete"))
            confirm_button.clicked.connect(
                lambda _checked=False, value=build_id: self.confirm_delete_build_preset(value)
            )
            self._prepare_row_action_button(confirm_button)
            layout.addWidget(confirm_button)

            cancel_button = QPushButton()
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.setIcon(self._ui_icon("x"))
            cancel_button.setToolTip(tr("common.cancel"))
            cancel_button.clicked.connect(self.cancel_delete_build_preset)
            self._prepare_row_action_button(cancel_button)
            layout.addWidget(cancel_button)
            return row

        if editing_this_row:
            save_button = QPushButton()
            save_button.setObjectName("row_save_button")
            save_button.setIcon(self._ui_icon("save"))
            save_button.setToolTip(tr("artifact.build.save"))
            save_button.clicked.connect(self.save_build_preset_edit)
            self._prepare_row_action_button(save_button)
            layout.addWidget(save_button)

            cancel_button = QPushButton()
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.setIcon(self._ui_icon("x"))
            cancel_button.setToolTip(tr("artifact.build.cancel"))
            cancel_button.clicked.connect(self.cancel_build_preset_edit)
            self._prepare_row_action_button(cancel_button)
            layout.addWidget(cancel_button)
            return row

        edit_button = QPushButton()
        edit_button.setObjectName("icon_button")
        edit_button.setIcon(self._ui_icon("edit"))
        edit_button.setToolTip(tr("artifact.build.edit"))
        edit_button.clicked.connect(
            lambda _checked=False, value=build_id: self.start_build_preset_edit(value)
        )
        layout.addWidget(edit_button)

        delete_button = QPushButton()
        delete_button.setObjectName("icon_button")
        delete_button.setIcon(self._ui_icon("delete"))
        delete_button.setToolTip(tr("artifact.build.delete"))
        delete_button.clicked.connect(
            lambda _checked=False, value=build_id: self.request_delete_build_preset(value)
        )
        layout.addWidget(delete_button)
        return row

    def _add_build_preset_row_metadata(
        self,
        layout: QHBoxLayout,
        preset: dict,
    ) -> None:
        slots: list[dict] = []
        active_sets: list[dict] = []
        artifact_ids: list[int] = []
        main_stats = ("N/D", "N/D")

        try:
            slots = list(preset.get("slots") or [])
            set_counts = self._set_counts_from_build_slots(slots)
            active_sets = self._active_set_bonus_items(set_counts)
            artifact_ids = [
                int(slot["artifact_id"])
                for slot in slots
                if slot.get("artifact_id") is not None
            ]
            main_stats = self._build_row_main_stats(slots)
        except Exception:
            active_sets = []
            artifact_ids = []
            main_stats = ("N/D", "N/D")

        try:
            bonus_stack = self._make_build_row_bonus_stack(active_sets, artifact_ids)
        except Exception:
            bonus_stack = None

        if bonus_stack is None:
            bonus_stack = self._make_build_row_no_bonus_badge()

        layout.addWidget(bonus_stack)

        layout.addWidget(self._make_build_row_main_stat_badge(*main_stats))

    @staticmethod
    def _set_counts_from_build_slots(slots: list[dict]) -> list[dict]:
        counts_by_key: dict[str, dict] = {}
        for slot in slots:
            set_uid = str(slot.get("set_uid") or "")
            set_name = str(slot.get("set_name") or "")
            key = set_uid or set_name
            if not key:
                continue

            item = counts_by_key.setdefault(
                key,
                {
                    "set_uid": set_uid,
                    "set_name": set_name,
                    "count": 0,
                },
            )
            item["count"] += 1

        return sorted(
            counts_by_key.values(),
            key=lambda item: (
                -int(item["count"]),
                str(item["set_name"]).casefold(),
                str(item["set_uid"]).casefold(),
            ),
        )

    def _build_row_main_stats(self, slots: list[dict]) -> tuple[str, str]:
        stats_by_pos = {
            int(slot.get("pos")): self._build_row_main_stat_badge(
                slot.get("main_property_type")
            )
            for slot in slots
            if slot.get("pos") in (3, 4)
        }
        return stats_by_pos.get(3, "N/D"), stats_by_pos.get(4, "N/D")

    def _make_build_row_main_stat_badge(self, sands: str, goblet: str) -> QFrame:
        badge = QFrame()
        badge.setObjectName("build_row_stat_badge")
        badge.setFixedSize(BUILD_ROW_STAT_BADGE_WIDTH, BUILD_ROW_STAT_BADGE_HEIGHT)

        layout = QVBoxLayout(badge)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for index, text in enumerate((sands, goblet)):
            line = QLabel(text)
            line.setObjectName("build_row_stat_badge_line")
            if index == 0:
                line.setProperty("topLine", True)
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.setFixedHeight(BUILD_ROW_STAT_BADGE_HEIGHT // 2)
            layout.addWidget(line)

        return badge

    def _make_build_row_no_bonus_badge(self) -> QFrame:
        badge = QFrame()
        badge.setObjectName("build_row_stat_badge")
        badge.setFixedSize(BUILD_ROW_BONUS_STACK_WIDTH, BUILD_ROW_BONUS_STACK_HEIGHT)

        layout = QVBoxLayout(badge)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for index, text in enumerate(("NO", "BONUS")):
            line = QLabel(text)
            line.setObjectName("build_row_stat_badge_line")
            if index == 0:
                line.setProperty("topLine", True)
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.setFixedHeight(BUILD_ROW_BONUS_STACK_HEIGHT // 2)
            layout.addWidget(line)

        return badge

    def _build_row_main_stat_badge(self, property_type) -> str:
        if property_type is None or property_type == "":
            return "N/D"

        try:
            label = BUILD_ROW_MAIN_STAT_BADGES[int(property_type)]
        except (KeyError, TypeError, ValueError):
            try:
                label = self._stat_badge_text(int(property_type)).replace("%", "").upper()
            except (TypeError, ValueError):
                return "N/D"

        label = str(label).strip().upper()
        if not label:
            return "N/D"
        return label[:BUILD_ROW_STAT_BADGE_MAX_CHARS]

    def _clear_build_row_pixmap_cache(self) -> None:
        self._build_row_source_icon_cache.clear()
        self._build_row_bonus_pixmap_cache.clear()

    def _build_row_set_icon_path(
        self,
        item: dict,
        artifact_ids,
    ) -> str | None:
        icon_path = self._set_icon_path_for_summary(
            item.get("set_uid") or "",
            artifact_ids,
        )
        return str(icon_path) if icon_path else None

    def _normalized_build_row_icon_path(self, icon_path: str) -> Path:
        path = Path(icon_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def _build_row_icon_file_identity(self, icon_path: str) -> dict | None:
        path = self._normalized_build_row_icon_path(icon_path)
        try:
            stat = path.stat()
        except OSError:
            return None
        return {
            "path": str(path.resolve()),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }

    def _cached_final_build_row_bonus_pixmap(self, cache_key: dict) -> QPixmap | None:
        memory_key = pixmap_cache_key_digest(cache_key)
        cached = self._build_row_bonus_pixmap_cache.get(memory_key)
        if cached is not None:
            return cached

        cached = load_persistent_pixmap(BUILD_ROW_BONUS_CACHE_DIR, cache_key)
        if cached is not None:
            self._build_row_bonus_pixmap_cache[memory_key] = cached
            return cached
        return None

    def _store_final_build_row_bonus_pixmap(
        self,
        cache_key: dict,
        pixmap: QPixmap,
    ) -> QPixmap:
        memory_key = pixmap_cache_key_digest(cache_key)
        self._build_row_bonus_pixmap_cache[memory_key] = pixmap
        save_persistent_pixmap(BUILD_ROW_BONUS_CACHE_DIR, cache_key, pixmap)
        return pixmap

    def _build_row_single_bonus_cache_key(
        self,
        icon_path: str,
        count: int,
        badge_text: str,
    ) -> dict | None:
        source = self._build_row_icon_file_identity(icon_path)
        if source is None:
            return None
        return {
            "version": BUILD_ROW_BONUS_CACHE_VERSION,
            "kind": "compact_preset_row_bonus",
            "mode": f"single_{count}p",
            "sources": [source],
            "width": BUILD_ROW_BONUS_STACK_WIDTH,
            "height": BUILD_ROW_BONUS_STACK_HEIGHT,
            "padding": BUILD_ROW_BONUS_ICON_PADDING,
            "alpha_threshold": BUILD_ROW_BONUS_TRIM_ALPHA_THRESHOLD,
            "badge_text": badge_text,
            "badge_style": count_badge_style_cache_key(),
        }

    def _build_row_split_bonus_cache_key(
        self,
        bottom_left_path: str,
        top_right_path: str,
    ) -> dict | None:
        bottom_left_source = self._build_row_icon_file_identity(bottom_left_path)
        top_right_source = self._build_row_icon_file_identity(top_right_path)
        if bottom_left_source is None or top_right_source is None:
            return None
        return {
            "version": BUILD_ROW_BONUS_CACHE_VERSION,
            "kind": "compact_preset_row_bonus",
            "mode": "split_2p_2p",
            "sources": [bottom_left_source, top_right_source],
            "width": BUILD_ROW_BONUS_STACK_WIDTH,
            "height": BUILD_ROW_BONUS_STACK_HEIGHT,
            "padding": BUILD_ROW_BONUS_ICON_PADDING,
            "alpha_threshold": BUILD_ROW_BONUS_TRIM_ALPHA_THRESHOLD,
            "diagonal": {
                "direction": BUILD_ROW_BONUS_DIAGONAL_DIRECTION,
                "feather": BUILD_ROW_BONUS_DIAGONAL_FEATHER,
            },
            "badge_text": "2",
            "badge_style": count_badge_style_cache_key(),
        }

    def _cached_build_row_source_icon_pixmap(
        self,
        icon_path: str,
    ) -> QPixmap | None:
        path = self._normalized_build_row_icon_path(icon_path)
        source = self._build_row_icon_file_identity(icon_path)
        if source is None:
            return None
        cache_key = (
            source["path"],
            source["mtime_ns"],
            source["size"],
            BUILD_ROW_BONUS_STACK_WIDTH,
            BUILD_ROW_BONUS_STACK_HEIGHT,
            BUILD_ROW_BONUS_ICON_PADDING,
            BUILD_ROW_BONUS_TRIM_ALPHA_THRESHOLD,
        )
        cached = self._build_row_source_icon_cache.get(cache_key)
        if cached is not None:
            return cached

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None

        scaled = scale_trimmed_pixmap_to_size(
            pixmap,
            BUILD_ROW_BONUS_STACK_WIDTH,
            BUILD_ROW_BONUS_STACK_HEIGHT,
            padding=BUILD_ROW_BONUS_ICON_PADDING,
            alpha_threshold=BUILD_ROW_BONUS_TRIM_ALPHA_THRESHOLD,
        )
        self._build_row_source_icon_cache[cache_key] = scaled
        return scaled

    def _make_diagonal_split_set_bonus_pixmap(
        self,
        active_sets: list[dict],
        artifact_ids: list[int],
    ) -> QPixmap | None:
        bottom_left_path = self._build_row_set_icon_path(active_sets[0], artifact_ids)
        top_right_path = self._build_row_set_icon_path(active_sets[1], artifact_ids)
        if bottom_left_path is None or top_right_path is None:
            return None

        cache_key = self._build_row_split_bonus_cache_key(bottom_left_path, top_right_path)
        if cache_key is None:
            return None
        cached = self._cached_final_build_row_bonus_pixmap(cache_key)
        if cached is not None:
            return cached

        bottom_left_icon = self._cached_build_row_source_icon_pixmap(bottom_left_path)
        top_right_icon = self._cached_build_row_source_icon_pixmap(top_right_path)
        if bottom_left_icon is None or top_right_icon is None:
            return None

        composite = make_diagonal_split_pixmap(
            bottom_left_icon,
            top_right_icon,
            width=BUILD_ROW_BONUS_STACK_WIDTH,
            height=BUILD_ROW_BONUS_STACK_HEIGHT,
            feather=BUILD_ROW_BONUS_DIAGONAL_FEATHER,
        )
        pixmap = draw_count_badge(composite, "2")
        return self._store_final_build_row_bonus_pixmap(cache_key, pixmap)

    def _make_build_row_single_set_bonus_pixmap(
        self,
        item: dict,
        artifact_ids,
    ) -> QPixmap | None:
        icon_path = self._build_row_set_icon_path(item, artifact_ids)
        if icon_path is None:
            return None

        count = int(item.get("count") or 0)
        badge_text = str(count) if count in (2, 4) else ""
        cache_key = self._build_row_single_bonus_cache_key(
            icon_path,
            count,
            badge_text,
        )
        if cache_key is None:
            return None
        cached = self._cached_final_build_row_bonus_pixmap(cache_key)
        if cached is not None:
            return cached

        pixmap = self._cached_build_row_source_icon_pixmap(icon_path)
        if pixmap is None or pixmap.isNull():
            return None

        final_pixmap = draw_count_badge(pixmap, badge_text) if badge_text else pixmap
        return self._store_final_build_row_bonus_pixmap(cache_key, final_pixmap)

    def _make_build_row_bonus_stack(
        self,
        active_sets: list[dict],
        artifact_ids: list[int],
    ) -> QWidget | None:
        active_sets = active_sets[:2]
        if len(active_sets) == 2:
            pixmap = self._make_diagonal_split_set_bonus_pixmap(active_sets, artifact_ids)
            if pixmap is None or pixmap.isNull():
                return None

            label = QLabel()
            label.setObjectName("build_row_bonus_stack")
            label.setFixedSize(BUILD_ROW_BONUS_STACK_WIDTH, BUILD_ROW_BONUS_STACK_HEIGHT)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setPixmap(pixmap)
            rows: list[tuple[int, str]] = []
            for item in active_sets:
                rows.extend(self._set_bonus_tooltip_rows(item))
            self._install_set_bonus_tooltip(label, rows)
            return label

        if not active_sets:
            return None

        pixmap = self._make_build_row_single_set_bonus_pixmap(
            active_sets[0],
            artifact_ids,
        )
        if pixmap is None or pixmap.isNull():
            return None

        label = QLabel()
        label.setObjectName("build_row_bonus_stack")
        label.setFixedSize(BUILD_ROW_BONUS_STACK_WIDTH, BUILD_ROW_BONUS_STACK_HEIGHT)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pixmap)
        self._install_set_bonus_tooltip(label, self._set_bonus_tooltip_rows(active_sets[0]))
        return label

    def start_new_build_preset(self) -> None:
        if not self.selected_build_target_keys:
            self.empty_label.setText(tr("artifact.build.no_target_hint"))
            return
        if not self.confirm_discard_custom_edit():
            return
        if self.editing_build_dirty:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            return
        self.finish_custom_set_edit()
        self.selected_build_id = None
        self.selected_build_slots = {}
        self.selected_build_targets = []
        self._build_target_keys_before_edit = set(self.selected_build_target_keys)
        self.editing_build_id = None
        self.editing_build_name = self.build_name_input.text().strip()
        self.editing_build_slots = {}
        self.editing_build_targets = self.targets_from_selected_build_keys()
        self.editing_build_dirty = False
        self.pending_delete_build_id = None
        self.edit_selection_mode = EDIT_MODE_BUILD_PRESET
        self.update_build_panel()
        self.update_edit_selection_mode()
        self.refresh_build_preset_list()
        self._activate_preset_edit_layout()

    def start_build_preset_edit(self, build_id: int) -> None:
        if not self.confirm_discard_custom_edit():
            return
        if self.editing_build_dirty and build_id != self.editing_build_id:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            return
        self.finish_custom_set_edit()
        preset = get_build_preset(build_id, db_path=self.db_path)
        if preset is None:
            return

        self.ensure_build_target_items(preset.get("targets") or [])
        self._build_target_keys_before_edit = set(self.selected_build_target_keys)
        self.selected_build_id = int(build_id)
        self.editing_build_id = int(build_id)
        self.editing_build_name = preset["name"]
        self.editing_build_slots = {
            int(slot["pos"]): int(slot["artifact_id"])
            for slot in preset.get("slots", [])
        }
        self.selected_build_slots = dict(self.editing_build_slots)
        self.editing_build_targets = list(preset.get("targets") or [])
        self.selected_build_targets = list(self.editing_build_targets)
        self.selected_build_target_keys = self.target_keys_from_targets(self.editing_build_targets)
        self.editing_build_dirty = False
        self.pending_delete_build_id = None
        self.edit_selection_mode = EDIT_MODE_BUILD_PRESET
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)
        self.update_build_panel()
        self.update_build_create_controls()
        self.update_edit_selection_mode()
        self.refresh_build_target_list()
        self.refresh_build_preset_list()
        self._activate_preset_edit_layout()
        QTimer.singleShot(0, self._focus_inline_build_name_input)

    def select_build_preset(self, build_id: int) -> None:
        if self.edit_selection_mode != EDIT_MODE_NONE:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            self.refresh_build_preset_list()
            return

        if self.selected_build_id == int(build_id):
            self.selected_build_id = None
            self.selected_build_slots = {}
            self.selected_build_targets = []
            self.pending_delete_build_id = None
            self._sync_build_preset_row_selection()
            self.update_build_panel()
            self.update_build_create_controls()
            self.update_edit_selection_mode()
            self.apply_current_filters()
            return

        preset = get_build_preset(build_id, db_path=self.db_path)
        if preset is None:
            return

        self.ensure_build_target_items(preset.get("targets") or [])
        self.selected_build_id = int(build_id)
        self.selected_build_slots = {
            int(slot["pos"]): int(slot["artifact_id"])
            for slot in preset.get("slots", [])
        }
        self.selected_build_targets = list(preset.get("targets") or [])
        had_pending_delete = self.pending_delete_build_id is not None
        self.pending_delete_build_id = None
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)
        if had_pending_delete:
            self.refresh_build_preset_list()
        else:
            self._sync_build_preset_row_selection()
        self.update_build_panel()
        self.update_build_create_controls()
        self.update_edit_selection_mode()
        self.apply_current_filters()

    def _focus_inline_build_name_input(self) -> None:
        if (
            self.edit_selection_mode != EDIT_MODE_BUILD_PRESET
            or self.build_row_name_input is None
        ):
            return
        self.build_row_name_input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.build_row_name_input.selectAll()

    def _activate_preset_edit_layout(self) -> None:
        content = self.build_preset_list_scroll.widget()
        if content is not None and content.layout() is not None:
            content.layout().activate()
            content.updateGeometry()
        if self.build_preset_list_scroll.layout() is not None:
            self.build_preset_list_scroll.layout().activate()
        root_layout = self.layout()
        if root_layout is not None:
            root_layout.activate()
        self.updateGeometry()
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        if content is not None and content.layout() is not None:
            content.layout().activate()
        if root_layout is not None:
            root_layout.activate()

    def assign_build_artifact(self, artifact_id: int) -> None:
        try:
            artifact = self.store.artifact(artifact_id)
        except KeyError:
            return

        pos = int(artifact.pos)
        if self.editing_build_slots.get(pos) == int(artifact.id):
            self.editing_build_slots.pop(pos, None)
        else:
            self.editing_build_slots[pos] = int(artifact.id)
        self.editing_build_dirty = True
        self.update_build_panel()
        self.update_edit_selection_mode()

    def save_build_preset_edit(self) -> None:
        if not self.selected_build_target_keys:
            self.empty_label.setText(tr("artifact.build.no_target_hint"))
            return
        name = self.editing_build_name.strip()
        self.editing_build_name = name
        targets = self.targets_from_selected_build_keys()
        restore_target_keys = (
            set(self._build_target_keys_before_edit)
            if self._build_target_keys_before_edit is not None
            else None
        )
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)

        build_id = save_build_preset(
            build_id=self.editing_build_id,
            name=name,
            slots=self.editing_build_slots,
            targets=targets,
            db_path=self.db_path,
        )
        self.selected_build_id = build_id
        self.selected_build_slots = dict(self.editing_build_slots)
        self.selected_build_targets = list(targets)
        self.editing_build_id = None
        self.editing_build_name = ""
        self.editing_build_slots = {}
        self.editing_build_targets = []
        self.editing_build_dirty = False
        if restore_target_keys is not None:
            self.selected_build_target_keys = restore_target_keys
        self._build_target_keys_before_edit = None
        self.edit_selection_mode = EDIT_MODE_NONE
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)
        self.load_build_presets()
        self.refresh_build_target_list()
        self.update_build_panel()
        self.update_edit_selection_mode()
        self.apply_current_filters()

    def cancel_build_preset_edit(self) -> None:
        self.finish_build_preset_edit()

    def finish_build_preset_edit(self) -> None:
        self.editing_build_id = None
        self.editing_build_name = ""
        self.editing_build_slots = {}
        self.editing_build_targets = []
        self.editing_build_dirty = False
        if self._build_target_keys_before_edit is not None:
            self.selected_build_target_keys = set(self._build_target_keys_before_edit)
            self._build_target_keys_before_edit = None
        self.edit_selection_mode = EDIT_MODE_NONE
        self.pending_delete_build_id = None
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)
        self.update_build_create_controls()
        self.refresh_build_target_list()
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.update_edit_selection_mode()

    def update_build_panel(self) -> None:
        self.refresh_equipment_target_state()
        editing = self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
        slots = self._preview_slots()
        has_selection = editing or bool(self.selected_build_id) or bool(slots)

        for pos in ARTIFACT_POSITIONS:
            artifact_id = slots.get(pos) if has_selection else None
            self.update_build_slot_row(pos, artifact_id)

        self.update_build_target_preview()
        self.update_build_summary()
        self.update_build_create_controls()

    def _preview_slots(self) -> dict[int, int]:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            return self.editing_build_slots
        if self.selected_build_id is not None:
            return self.selected_build_slots
        return self._current_equipment_slots_for_operation_target()

    def _current_equipment_slots_for_operation_target(self) -> dict[int, int]:
        character_id = self.operation_target_character_id
        if not self.equip_mode_enabled or character_id is None:
            self.current_equipment_preview_slots = {}
            return {}

        try:
            with closing(connect_db(self.db_path)) as conn:
                rows = list_equipped_artifacts_for_character(conn, character_id)
        except Exception as exc:
            log_perf(
                "artifact_current_equipment_preview_failed",
                character_id=character_id,
                error=str(exc),
            )
            self.current_equipment_preview_slots = {}
            return {}

        slots: dict[int, int] = {}
        for row in rows:
            pos = ARTIFACT_POS_BY_SLOT_KEY.get(str(row.slot_key))
            if pos is not None:
                slots[int(pos)] = int(row.artifact_id)
        self.current_equipment_preview_slots = dict(slots)
        return slots

    def update_build_target_preview(self) -> None:
        strip_pixmap = self._cached_target_preview_strip(
            self.current_preview_build_targets()
        )
        self.build_target_placeholder.set_strip_pixmap(strip_pixmap)

    def _clear_target_preview_pixmap_cache(self) -> None:
        self._target_preview_icon_cache.clear()
        self._target_preview_strip_cache.clear()

    def _target_preview_file_identity(self, path_value) -> dict:
        path = Path(path_value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        resolved_path = path.resolve()
        try:
            stat = resolved_path.stat()
        except OSError:
            return {
                "path": str(resolved_path),
                "missing": True,
            }
        return {
            "path": str(resolved_path),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }

    def _target_preview_cache_memory_key(self, cache_key: dict) -> str:
        return pixmap_cache_key_digest(cache_key)

    def _target_preview_item_for_target(self, target: dict) -> tuple[str, dict | None]:
        key = self.target_key_from_target(target)
        return key or "", self.build_target_items_by_key.get(key or "")

    def _target_preview_icon_cache_key(self, target: dict) -> dict:
        key, item = self._target_preview_item_for_target(target)
        if target.get("target_type") == "universal":
            return {
                "version": BUILD_TARGET_PREVIEW_CACHE_VERSION,
                "kind": "target_preview_icon",
                "target_type": "universal",
                "target_key": BUILD_TARGET_UNIVERSAL_KEY,
                "icon_size": BUILD_TARGET_PREVIEW_ICON_SIZE,
                "background": self._target_preview_file_identity(
                    BUILD_TARGET_PREVIEW_UNIVERSAL_BG_PATH
                ),
                "card": {
                    "background": BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND,
                    "border": BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BORDER,
                    "radius": BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_RADIUS,
                },
                "svg": {
                    "name": "users",
                    "size": BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_SIZE,
                    "offset_y": BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_OFFSET_Y,
                    "auto_contrast_background": BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND,
                },
            }

        character_id_value = (
            item.get("character_id") if item else target.get("character_id")
        )
        character_name_value = str(
            (item or {}).get("character_name")
            or target.get("character_name")
            or "?"
        )
        path_value = (item or {}).get("path")
        if path_value:
            return {
                "version": BUILD_TARGET_PREVIEW_CACHE_VERSION,
                "kind": "target_preview_icon",
                "target_type": "character",
                "target_key": key,
                "character_id": character_id_value,
                "source": self._target_preview_file_identity(path_value),
                "icon_size": BUILD_TARGET_PREVIEW_ICON_SIZE,
                "scaling": "keep_aspect_ratio_centered",
                "fallback_text": character_name_value[:2],
            }

        return {
            "version": BUILD_TARGET_PREVIEW_CACHE_VERSION,
            "kind": "target_preview_icon",
            "target_type": "character_fallback",
            "target_key": key,
            "character_id": character_id_value,
            "icon_size": BUILD_TARGET_PREVIEW_ICON_SIZE,
            "fallback_text": character_name_value[:2],
        }

    def _make_character_target_preview_pixmap(
        self,
        source_path: str | None,
        fallback_text: str,
    ) -> QPixmap:
        size = BUILD_TARGET_PREVIEW_ICON_SIZE
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)

        if source_path:
            pixmap = QPixmap(source_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter = QPainter(canvas)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.drawPixmap(
                    (size - scaled.width()) // 2,
                    (size - scaled.height()) // 2,
                    scaled,
                )
                painter.end()
                return canvas

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor("#d8d4c8"))
        painter.drawText(
            QRect(0, 0, size, size),
            Qt.AlignmentFlag.AlignCenter,
            fallback_text or "?",
        )
        painter.end()
        return canvas

    def _generate_target_preview_icon(self, target: dict, cache_key: dict) -> QPixmap:
        if cache_key.get("target_type") == "universal":
            return self._make_universal_target_preview_pixmap()

        source = cache_key.get("source") or {}
        source_path = None if source.get("missing") else source.get("path")
        return self._make_character_target_preview_pixmap(
            source_path,
            str(cache_key.get("fallback_text") or "?"),
        )

    def _cached_target_preview_icon(
        self,
        target: dict,
        cache_key: dict,
    ) -> QPixmap | None:
        memory_key = self._target_preview_cache_memory_key(cache_key)
        cached = self._target_preview_icon_cache.get(memory_key)
        if cached is not None:
            return cached

        cached = load_persistent_pixmap(BUILD_TARGET_PREVIEW_ICON_CACHE_DIR, cache_key)
        if cached is not None:
            self._target_preview_icon_cache[memory_key] = cached
            return cached

        pixmap = self._generate_target_preview_icon(target, cache_key)
        if pixmap.isNull():
            return None

        self._target_preview_icon_cache[memory_key] = pixmap
        save_persistent_pixmap(BUILD_TARGET_PREVIEW_ICON_CACHE_DIR, cache_key, pixmap)
        return pixmap

    def _target_preview_strip_cache_key(
        self,
        targets: list[dict],
    ) -> tuple[dict, list[tuple[dict, dict, str]]]:
        entries = []
        icon_items = []
        for index, target in enumerate(targets):
            target_key, _item = self._target_preview_item_for_target(target)
            icon_key = self._target_preview_icon_cache_key(target)
            entries.append(
                {
                    "index": index,
                    "target_key": target_key,
                    "icon_key": icon_key,
                }
            )
            icon_items.append((target, icon_key, target_key))

        return {
            "version": BUILD_TARGET_PREVIEW_CACHE_VERSION,
            "kind": "target_preview_strip",
            "entries": entries,
            "row_height": BUILD_TARGET_PREVIEW_ROW_HEIGHT,
            "icon_size": BUILD_TARGET_PREVIEW_ICON_SIZE,
            "spacing": BUILD_TARGET_PREVIEW_SPACING,
            "background": "transparent",
        }, icon_items

    def _compose_target_preview_strip(
        self,
        icon_items: list[tuple[dict, dict, str]],
    ) -> QPixmap:
        count = len(icon_items)
        if count == 0:
            return QPixmap()

        width = (
            count * BUILD_TARGET_PREVIEW_ICON_SIZE
            + max(0, count - 1) * BUILD_TARGET_PREVIEW_SPACING
        )
        canvas = QPixmap(width, BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x = 0
        for target, icon_key, _target_key in icon_items:
            icon = self._cached_target_preview_icon(target, icon_key)
            if icon is not None and not icon.isNull():
                painter.drawPixmap(
                    x,
                    (BUILD_TARGET_PREVIEW_ROW_HEIGHT - icon.height()) // 2,
                    icon,
                )
            x += BUILD_TARGET_PREVIEW_ICON_SIZE + BUILD_TARGET_PREVIEW_SPACING
        painter.end()
        return canvas

    def _cached_target_preview_strip(self, targets: list[dict]) -> QPixmap:
        if not targets:
            return QPixmap()

        cache_key, icon_items = self._target_preview_strip_cache_key(targets)
        memory_key = self._target_preview_cache_memory_key(cache_key)
        cached = self._target_preview_strip_cache.get(memory_key)
        if cached is not None:
            return cached

        cached = load_persistent_pixmap(BUILD_TARGET_PREVIEW_STRIP_CACHE_DIR, cache_key)
        if cached is not None:
            self._target_preview_strip_cache[memory_key] = cached
            return cached

        pixmap = self._compose_target_preview_strip(icon_items)
        if not pixmap.isNull():
            self._target_preview_strip_cache[memory_key] = pixmap
            save_persistent_pixmap(
                BUILD_TARGET_PREVIEW_STRIP_CACHE_DIR,
                cache_key,
                pixmap,
            )
        return pixmap

    def update_build_create_controls(self) -> None:
        new_draft = (
            self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
            and self.editing_build_id is None
        )
        self.new_build_button.setObjectName(
            "row_save_button" if new_draft else "icon_button"
        )
        self.new_build_button.setIcon(self._ui_icon("save" if new_draft else "plus"))
        self.new_build_button.setToolTip(
            tr("artifact.build.save") if new_draft else tr("artifact.build.new")
        )
        self.cancel_new_build_button.setVisible(new_draft)
        for button in (self.new_build_button, self.cancel_new_build_button):
            button.style().unpolish(button)
            button.style().polish(button)
            self._prepare_button_for_first_show(button)

    def on_build_name_changed(self, text: str) -> None:
        if (
            self.edit_selection_mode != EDIT_MODE_BUILD_PRESET
            or self.editing_build_id is not None
        ):
            return
        self.editing_build_name = text
        self.editing_build_dirty = True

    def on_inline_build_name_changed(self, text: str) -> None:
        if (
            self.edit_selection_mode != EDIT_MODE_BUILD_PRESET
            or self.editing_build_id is None
        ):
            return
        self.editing_build_name = text
        self.editing_build_dirty = True

    def clear_build_slot(self, pos: int) -> None:
        if pos not in self.editing_build_slots:
            return

        self.editing_build_slots.pop(pos, None)
        self.editing_build_dirty = True
        self.update_build_panel()

    def update_build_slot_row(self, pos: int, artifact_id: int | None) -> None:
        slot_name = self._position_label(pos)
        if artifact_id is None:
            self._set_slot_placeholder_icon(pos)
            self.build_slot_icon_labels[pos].setToolTip(slot_name)
            self.build_slot_stat_labels[pos].setText("-")
            return

        try:
            artifact = self.store.artifact(artifact_id)
        except KeyError:
            self.build_slot_icon_labels[pos].clear()
            self.build_slot_icon_labels[pos].setText("?")
            self.build_slot_icon_labels[pos].setToolTip(slot_name)
            self.build_slot_stat_labels[pos].setText(tr("artifact.build.slot_missing"))
            return

        self.build_slot_icon_labels[pos].setText("")
        self.build_slot_icon_labels[pos].clear()
        if artifact.icon_path:
            pixmap = QPixmap(str(artifact.icon_path))
            if not pixmap.isNull():
                self.build_slot_icon_labels[pos].setPixmap(
                    pixmap.scaled(
                        BUILD_PREVIEW_SLOT_ICON_SIZE,
                        BUILD_PREVIEW_SLOT_ICON_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

        self.build_slot_icon_labels[pos].setToolTip(
            f"{slot_name}: {artifact.name or artifact.set_name}"
        )
        self.build_slot_stat_labels[pos].setText(self._compact_main_stat_text(artifact))

    def _set_slot_placeholder_icon(self, pos: int) -> None:
        icon_label = self.build_slot_icon_labels[pos]
        icon_label.clear()
        icon_path = (
            PROJECT_ROOT
            / "assets"
            / "ui"
            / "art_placeholder"
            / ARTIFACT_PLACEHOLDER_ICON_NAMES[pos]
        )
        pixmap = QPixmap(str(icon_path))
        if pixmap.isNull():
            icon_label.setText("-")
            return
        icon_label.setPixmap(
            pixmap.scaled(
                BUILD_PREVIEW_SLOT_ICON_SIZE,
                BUILD_PREVIEW_SLOT_ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def current_build_artifact_ids(self) -> set[int]:
        return set(self._preview_slots().values())

    def current_highlight_artifact_ids(self) -> set[int]:
        if self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            return set(self.editing_custom_artifact_ids)
        return self.current_build_artifact_ids()

    def _compact_main_stat_text(self, artifact) -> str:
        return self._stat_badge_text(artifact.main_property_type)

    def update_build_summary(self) -> None:
        self._clear_layout(self.build_bonus_layout)
        self._clear_layout(self.build_summary_stats_layout)

        editing = self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
        slots = self._preview_slots()

        if not slots:
            self.fill_build_stat_summary({})
            return

        try:
            if editing and self.editing_build_id is not None and not self.editing_build_dirty:
                summary = calculate_build_summary(
                    build_id=self.editing_build_id,
                    db_path=self.db_path,
                )
            elif not editing and self.selected_build_id is not None:
                summary = calculate_build_summary(
                    build_id=self.selected_build_id,
                    db_path=self.db_path,
                )
            else:
                summary = calculate_build_summary(slots=slots, db_path=self.db_path)
        except Exception as exc:
            label = QLabel(tr("artifact.build.summary_error", error=str(exc)))
            label.setObjectName("small_muted")
            self.build_summary_stats_layout.addWidget(label, 0, 0)
            return

        if not summary:
            self.fill_build_stat_summary({})
            return

        self.fill_build_bonus_summary(summary.get("set_counts") or [])
        self.fill_build_stat_summary(summary)

    def fill_build_bonus_summary(self, set_counts: list[dict]) -> None:
        active_sets = self._active_set_bonus_items(set_counts)

        if not active_sets:
            return

        for item in active_sets[:2]:
            self.build_bonus_layout.addWidget(self._make_set_bonus_cell(item))

    @staticmethod
    def _active_set_bonus_items(set_counts: list[dict]) -> list[dict]:
        active_sets = []
        for item in set_counts:
            count = int(item.get("count") or 0)
            if count >= 4:
                active = dict(item)
                active["count"] = 4
                active_sets.append(active)
            elif count >= 2:
                active = dict(item)
                active["count"] = 2
                active_sets.append(active)
        return active_sets

    @staticmethod
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

    def _set_bonus_tooltip_rows(self, item: dict) -> list[tuple[int, str]]:
        set_uid = str(item.get("set_uid") or "").strip()
        if not set_uid:
            return []

        count = int(item.get("count") or 0)
        piece_counts = (2, 4) if count >= 4 else (2,) if count >= 2 else ()
        rows: list[tuple[int, str]] = []

        for piece_count in piece_counts:
            description = self.store.set_bonus_description(set_uid, piece_count)
            description = self._clean_set_bonus_description(description or "")
            if description:
                rows.append((piece_count, description))

        return rows

    def _set_bonus_tooltip_html(self, rows: list[tuple[int, str]]) -> str:
        rendered_rows = []
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
            return ""

        return (
            "<table cellspacing='0' cellpadding='0' "
            "style='color: #f4ead8; font-size: 12px; font-weight: 600;'>"
            f"{''.join(rendered_rows)}"
            "</table>"
        )

    def _install_set_bonus_tooltip(self, widget: QWidget, rows: list[tuple[int, str]]) -> None:
        tooltip = self._set_bonus_tooltip_html(rows)
        if tooltip:
            install_custom_tooltip(widget, tooltip)

    def _make_set_bonus_cell(self, item: dict) -> QFrame:
        cell = QFrame()
        cell.setObjectName("build_slot_mini")
        cell.setFixedSize(
            BUILD_PREVIEW_BONUS_CELL_WIDTH,
            BUILD_PREVIEW_BONUS_CELL_HEIGHT,
        )
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
            BUILD_PREVIEW_SLOT_CONTENT_MARGIN,
        )
        layout.setSpacing(0)

        icon = QLabel()
        icon.setFixedSize(
            BUILD_PREVIEW_BONUS_ICON_SIZE,
            BUILD_PREVIEW_BONUS_ICON_SIZE,
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._make_set_bonus_pixmap(
            item,
            BUILD_PREVIEW_BONUS_ICON_SIZE,
            self.current_build_artifact_ids(),
        )
        if pixmap is not None:
            icon.setPixmap(pixmap)
        if icon.pixmap() is None:
            count = str(item["count"])
            icon.setText(f"{str(item.get('set_name') or item.get('set_uid') or '?')[:2]}{count}")
        self._install_set_bonus_tooltip(icon, self._set_bonus_tooltip_rows(item))
        layout.addWidget(icon)
        return cell

    def _make_set_bonus_pixmap(
        self,
        item: dict,
        icon_size: int,
        artifact_ids,
    ) -> QPixmap | None:
        icon_path = self._set_icon_path_for_summary(
            item.get("set_uid") or "",
            artifact_ids,
        )
        if not icon_path:
            return None

        pixmap = QPixmap(str(icon_path))
        if pixmap.isNull():
            return None

        canvas = QPixmap(icon_size, icon_size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scaled = pixmap.scaled(
            icon_size,
            icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(
            (icon_size - scaled.width()) // 2,
            (icon_size - scaled.height()) // 2,
            scaled,
        )
        badge_size = min(13, max(8, round(icon_size * 0.38)))
        badge_rect = QRect(
            icon_size - badge_size - 1,
            icon_size - badge_size - 1,
            badge_size,
            badge_size,
        )
        painter.setPen(QPen(QColor("#8f7440"), 1))
        painter.setBrush(QColor("#4a3b22"))
        badge_radius = max(3, badge_size // 3)
        painter.drawRoundedRect(badge_rect, badge_radius, badge_radius)
        font = QFont(painter.font())
        font.setPointSize(max(5, round(icon_size * 0.24)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f0d58a"))
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            str(item["count"]),
        )
        painter.end()
        return canvas

    def _set_icon_path_for_summary(self, set_uid: str, artifact_ids=None):
        if artifact_ids is None:
            artifact_ids = self.current_build_artifact_ids()

        for artifact_id in artifact_ids:
            try:
                artifact = self.store.artifact(artifact_id)
            except KeyError:
                continue
            if artifact.set_uid == set_uid and artifact.set_icon_path:
                return artifact.set_icon_path

        return None

    def fill_build_stat_summary(self, summary: dict) -> None:
        stats_by_type = {
            int(item["property_type"]): item
            for item in summary.get("total_stats") or []
        }
        rows: list[tuple[str, str]] = []

        if summary.get("crit_value"):
            rows.append(("CV", self._format_stat_value(None, summary["crit_value"])))
        if summary.get("proc_count"):
            rows.append((tr("artifact.stat.proc_count"), self._format_stat_value(None, summary["proc_count"])))

        for property_type in (CRIT_RATE, CRIT_DAMAGE):
            item = stats_by_type.pop(property_type, None)
            if item:
                rows.append((self._stat_badge_text(property_type), self._format_stat_value(property_type, item["raw_value"])))

        for property_type in (
            PHYSICAL_DAMAGE,
            PYRO_DAMAGE,
            ELECTRO_DAMAGE,
            HYDRO_DAMAGE,
            DENDRO_DAMAGE,
            ANEMO_DAMAGE,
            GEO_DAMAGE,
            CRYO_DAMAGE,
            HEALING_BONUS,
        ):
            item = stats_by_type.pop(property_type, None)
            if item:
                rows.append((self._stat_badge_text(property_type), self._format_stat_value(property_type, item["raw_value"])))

        for property_type in (ENERGY_RECHARGE, ELEMENTAL_MASTERY):
            item = stats_by_type.pop(property_type, None)
            if item:
                rows.append((self._stat_badge_text(property_type), self._format_stat_value(property_type, item["raw_value"])))

        for label, percent_type, flat_type in (
            ("ATK", ATK_PERCENT, ATK_FLAT),
            ("HP", HP_PERCENT, HP_FLAT),
            ("DEF", DEF_PERCENT, DEF_FLAT),
        ):
            percent_item = stats_by_type.pop(percent_type, None)
            flat_item = stats_by_type.pop(flat_type, None)
            if percent_item and flat_item:
                value = (
                    f"{self._format_stat_value(percent_type, percent_item['raw_value'])}"
                    f" + {self._format_stat_value(flat_type, flat_item['raw_value'])}"
                )
                rows.append((label, value))
            elif percent_item:
                rows.append((self._stat_badge_text(percent_type), self._format_stat_value(percent_type, percent_item["raw_value"])))
            elif flat_item:
                rows.append((self._stat_badge_text(flat_type), self._format_stat_value(flat_type, flat_item["raw_value"])))

        for property_type, item in sorted(stats_by_type.items()):
            rows.append((self._stat_badge_text(property_type), self._format_stat_value(property_type, item["raw_value"])))

        for index in range(BUILD_PREVIEW_STAT_CELLS):
            if index < len(rows):
                badge, value = rows[index]
                text = f"{badge} {value}"
            else:
                text = ""
            label = QLabel(text)
            label.setFixedHeight(BUILD_PREVIEW_STAT_LABEL_HEIGHT)
            if text:
                label.setObjectName("stat_pill")
            self.build_summary_stats_layout.addWidget(label, index // 2, index % 2)

    def _stat_badge_text(self, property_type: int) -> str:
        try:
            return stat_badge(int(property_type))
        except KeyError:
            return str(property_type)

    def _format_stat_value(self, property_type: int | None, value: float | int) -> str:
        suffix = "%" if property_type in PERCENT_STAT_TYPES else ""
        return f"{float(value):g}{suffix}"

    def request_delete_build_preset(self, build_id: int) -> None:
        if self.edit_selection_mode != EDIT_MODE_NONE:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            return
        self.pending_delete_build_id = int(build_id)
        self.refresh_build_preset_list()

    def cancel_delete_build_preset(self) -> None:
        self.pending_delete_build_id = None
        self.refresh_build_preset_list()

    def confirm_delete_build_preset(self, build_id: int) -> None:
        if self.pending_delete_build_id != int(build_id):
            return
        delete_build_preset(int(build_id), db_path=self.db_path)
        if self.selected_build_id == int(build_id):
            self.selected_build_id = None
            self.selected_build_slots = {}
        self.finish_build_preset_edit()
        self.load_build_presets()
        self.update_edit_selection_mode()
        self.apply_current_filters()

    def active_save_tooltip(self) -> str:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            return tr("artifact.build.save")
        return tr("artifact.custom.save")

    def active_cancel_tooltip(self) -> str:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            return tr("artifact.build.cancel")
        return tr("artifact.custom.cancel")

    def save_active_edit(self) -> None:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.save_build_preset_edit()
        elif self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            self.save_custom_set_edit()

    def cancel_active_edit(self) -> None:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.cancel_build_preset_edit()
        elif self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            self.cancel_custom_set_edit()

    def update_edit_selection_mode(self) -> None:
        editing = self.edit_selection_mode != EDIT_MODE_NONE
        ids = self.current_highlight_artifact_ids()
        self.delegate.set_edit_selection_artifact_ids(ids)

        self.update_json_import_actions()
        self.list_view.setProperty("artifactEditMode", editing)
        self.list_view.style().unpolish(self.list_view)
        self.list_view.style().polish(self.list_view)
        self.list_view.viewport().update()

    def save_custom_set_edit(self) -> None:
        self._save_custom_set_edit(reload_after=True)

    def _save_custom_set_edit(self, *, reload_after: bool) -> None:
        if self.editing_custom_set_id is None:
            return

        replace_custom_set_artifacts(
            self.editing_custom_set_id,
            self.editing_custom_artifact_ids,
        )
        self.finish_custom_set_edit()
        if not reload_after:
            return

        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            confirm_custom_edit=False,
        )

    def cancel_custom_set_edit(self) -> None:
        self.finish_custom_set_edit()

    def delete_custom_set_from_popup(self, tag_id: int):
        if not self.confirm_discard_custom_edit():
            return self.store.custom_set_options

        delete_custom_set(tag_id)

        if self.editing_custom_set_id == tag_id:
            self.finish_custom_set_edit()

        self.selected_custom_set_ids.discard(tag_id)
        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            reset_popup=False,
            confirm_custom_edit=False,
        )
        self.update_sets_button_text()
        self.apply_current_filters()
        return self.store.custom_set_options

    def confirm_discard_custom_edit(self) -> bool:
        if not self.editing_custom_dirty:
            return True

        box = QMessageBox(self)
        box.setWindowTitle(tr("artifact.custom.unsaved_title"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            tr(
                "artifact.custom.unsaved_message",
                name=self.editing_custom_set_name,
            )
        )

        save_button = box.addButton(
            tr("artifact.custom.unsaved_save"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = box.addButton(
            tr("artifact.custom.unsaved_discard"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = box.addButton(
            tr("artifact.custom.unsaved_cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(save_button)
        box.exec()

        clicked_button = box.clickedButton()
        if clicked_button == save_button:
            self._save_custom_set_edit(reload_after=True)
            return True
        if clicked_button == discard_button:
            self.finish_custom_set_edit()
            return True
        if clicked_button == cancel_button:
            return False
        return False

    def confirm_discard_build_edit(self) -> bool:
        if not self.editing_build_dirty:
            return True

        box = QMessageBox(self)
        box.setWindowTitle(tr("artifact.build.unsaved_title"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            tr(
                "artifact.build.unsaved_message",
                name=self.editing_build_name or tr("artifact.build.default_name"),
            )
        )

        save_button = box.addButton(
            tr("artifact.custom.unsaved_save"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = box.addButton(
            tr("artifact.custom.unsaved_discard"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = box.addButton(
            tr("artifact.custom.unsaved_cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(save_button)
        box.exec()

        clicked_button = box.clickedButton()
        if clicked_button == save_button:
            self.save_build_preset_edit()
            return True
        if clicked_button == discard_button:
            self.finish_build_preset_edit()
            return True
        if clicked_button == cancel_button:
            return False
        return False

    def eventFilter(self, watched, event) -> bool:
        if watched is self._sets_popup and event.type() == QEvent.Type.Hide:
            button_pos = self.sets_button.mapFromGlobal(QCursor.pos())
            if self.sets_button.rect().contains(button_pos):
                self._suppress_next_sets_popup_open = True

        if watched is self._sort_popup and event.type() == QEvent.Type.Hide:
            button_pos = self.sort_button.mapFromGlobal(QCursor.pos())
            if self.sort_button.rect().contains(button_pos):
                self._suppress_next_sort_popup_open = True

        if watched is self._region_popup and event.type() == QEvent.Type.Hide:
            if self.build_target_region_button is not None:
                button_pos = self.build_target_region_button.mapFromGlobal(
                    QCursor.pos()
                )
                if self.build_target_region_button.rect().contains(button_pos):
                    self._suppress_next_region_popup_open = True

        if (
            watched is self.build_name_input
            and event.type() == QEvent.Type.KeyPress
            and self.edit_selection_mode == EDIT_MODE_NONE
        ):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.on_build_create_button_clicked()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.build_name_input.clear()
                event.accept()
                return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self.edit_selection_mode != EDIT_MODE_NONE:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.save_active_edit()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_active_edit()
                event.accept()
                return

        if self.pending_delete_build_id is not None:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.confirm_delete_build_preset(self.pending_delete_build_id)
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_delete_build_preset()
                event.accept()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self.confirm_discard_custom_edit() and self.confirm_discard_build_edit():
            event.accept()
        else:
            event.ignore()

    def finish_custom_set_edit(self) -> None:
        self.editing_custom_set_id = None
        self.editing_custom_set_name = ""
        self.editing_custom_artifact_ids.clear()
        self.editing_custom_dirty = False
        if self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            self.edit_selection_mode = EDIT_MODE_NONE

        self.update_edit_selection_mode()

    def update_custom_edit_bar(self) -> None:
        self.update_edit_selection_mode()
