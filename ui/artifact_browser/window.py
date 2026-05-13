from __future__ import annotations

import json

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QSize
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from hoyolab_export.paths import HOYOLAB_CHARACTER_ASSETS_DIR, PROJECT_ROOT
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    WEAPON_TYPE_FILTERS,
    character_id,
    character_matches_filters,
    character_name,
    character_sort_key,
    manifest_asset_items,
)
from ui.utils.icon_utils import auto_contrast_svg_icon, auto_contrast_svg_pixmap
from ui.utils.marquee_label import MarqueeButton
from ui.utils.pixmap_utils import (
    make_diagonal_split_pixmap,
    scale_trimmed_pixmap,
)
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
from .list_model import ArtifactListModel
from .models import ARTIFACT_POSITIONS
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

TARGET_PANEL_WIDTH = 330
TARGET_PANEL_MARGINS = (7, 10, 7, 10)
TARGET_PANEL_SPACING = 8

TARGET_HEADER_SPACING = 6
TARGET_HEADER_BALANCE_WIDTH = 72
TARGET_RESET_BUTTON_WIDTH = 72
TARGET_RESET_BUTTON_MIN_HEIGHT = 24
TARGET_RESET_BUTTON_PADDING_VERTICAL = 2
TARGET_RESET_BUTTON_PADDING_HORIZONTAL = 8
TARGET_RESET_BUTTON_RADIUS = 6

TARGET_BODY_SPACING = 6

TARGET_FILTER_BUTTON_SIZE = 30
TARGET_FILTER_ICON_SIZE = 26
TARGET_FILTER_PADDING = 2
TARGET_FILTER_BORDER_WIDTH = 0
TARGET_FILTER_RADIUS = 15
TARGET_FILTER_SPACING = 4

TARGET_ITEM_MIN_HEIGHT = 34
TARGET_ITEM_PADDING_VERTICAL = 3
TARGET_ITEM_PADDING_HORIZONTAL = 6
TARGET_ITEM_ICON_SIZE = 38

TARGET_ITEM_SPACING = 4

BUILD_TARGET_PREVIEW_ROW_HEIGHT = 40
BUILD_TARGET_PREVIEW_SPACING = 0
BUILD_TARGET_PREVIEW_ICON_SIZE = 40
BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_SIZE = 36
BUILD_TARGET_PREVIEW_HINT_WIDTH = 32
BUILD_TARGET_PREVIEW_HINT_ICON_SIZE = 20
BUILD_TARGET_PREVIEW_EDGE_BACKGROUND = QColor(0, 0, 0)
BUILD_TARGET_PREVIEW_HINT_ICON_OFFSET_X = 10
BUILD_TARGET_PREVIEW_HINT_ICON_OFFSET_Y = 0
BUILD_TARGET_PREVIEW_UNIVERSAL_BG_PATH = (
    PROJECT_ROOT / "assets" / "ui" / "bg" / "bg_4-5.png"
)
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BACKGROUND = "#40577a"
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_BORDER = "#475066"
BUILD_TARGET_PREVIEW_UNIVERSAL_CARD_RADIUS = 8
BUILD_TARGET_PREVIEW_UNIVERSAL_SVG_OFFSET_Y = 4
UI_ICON_BUTTON_BACKGROUND = "#222630"
UI_ICON_DEFAULT_SIZE = 24

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
QPushButton#close_button {
    min-width: 90px;
}
QLabel#status_label {
    color: #aab0bd;
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
QPushButton#custom_save_button {
    border-color: #4e9b61;
    background: #24452d;
}
QPushButton#custom_save_button:hover {
    background: #2d5938;
}
QPushButton#custom_cancel_button {
    border-color: #b85b5b;
    background: #4a2529;
}
QPushButton#custom_cancel_button:hover {
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
QLabel#panel_title {
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
}
""" + f"""
QPushButton#target_filter_button {{
    min-width: {TARGET_FILTER_BUTTON_SIZE}px;
    max-width: {TARGET_FILTER_BUTTON_SIZE}px;
    min-height: {TARGET_FILTER_BUTTON_SIZE}px;
    max-height: {TARGET_FILTER_BUTTON_SIZE}px;
    padding: {TARGET_FILTER_PADDING}px;
    border: {TARGET_FILTER_BORDER_WIDTH}px solid transparent;
    border-radius: {TARGET_FILTER_RADIUS}px;
    background: #202228;
}}
QPushButton#target_filter_button:hover {{
    background: #292c34;
}}
QPushButton#target_filter_button:checked {{
    border-color: #7da7ff;
    background: #303848;
}}
QPushButton#target_item {{
    min-height: {TARGET_ITEM_MIN_HEIGHT}px;
    padding: {TARGET_ITEM_PADDING_VERTICAL}px {TARGET_ITEM_PADDING_HORIZONTAL}px;
    text-align: left;
}}
QPushButton#target_item:checked {{
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
BUILD_ROW_BONUS_STACK_WIDTH = 42
BUILD_ROW_BONUS_STACK_HEIGHT = 34
BUILD_ROW_BONUS_STACK_MARGIN = 1
BUILD_ROW_BONUS_DIAGONAL_ICON_SIZE = 32
BUILD_ROW_BONUS_DIAGONAL_FEATHER = 3
BUILD_ROW_STAT_BADGE_WIDTH = 42
BUILD_ROW_STAT_BADGE_HEIGHT = 34
BUILD_ROW_STAT_BADGE_MAX_CHARS = 5
BUILD_ROW_NAME_WIDTH = 206
HOYOLAB_MANIFEST_FILE = PROJECT_ROOT / "data" / "hoyolab" / "crop_manifest.json"
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


class BuildTargetPreviewEdgeHint(QWidget):
    def __init__(self, icon_name: str, side: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.side = side
        self.setFixedWidth(BUILD_TARGET_PREVIEW_HINT_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.icon = auto_contrast_svg_pixmap(
            icon_name,
            BUILD_TARGET_PREVIEW_HINT_ICON_SIZE,
            BUILD_TARGET_PREVIEW_EDGE_BACKGROUND,
        )
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        edge_color = QColor(BUILD_TARGET_PREVIEW_EDGE_BACKGROUND)
        edge_color.setAlpha(255)
        clear_color = QColor(BUILD_TARGET_PREVIEW_EDGE_BACKGROUND)
        clear_color.setAlpha(0)
        if self.side == "left":
            gradient.setColorAt(0.0, edge_color)
            gradient.setColorAt(1.0, clear_color)
        else:
            gradient.setColorAt(0.0, clear_color)
            gradient.setColorAt(1.0, edge_color)
        painter.fillRect(self.rect(), gradient)

        ratio = self.icon.devicePixelRatio() or 1.0
        icon_width = self.icon.width() / ratio
        icon_height = self.icon.height() / ratio
        offset_x = (
            -BUILD_TARGET_PREVIEW_HINT_ICON_OFFSET_X
            if self.side == "left"
            else BUILD_TARGET_PREVIEW_HINT_ICON_OFFSET_X
        )
        x = int((self.width() - icon_width) / 2) + offset_x
        y = int((self.height() - icon_height) / 2) + BUILD_TARGET_PREVIEW_HINT_ICON_OFFSET_Y
        painter.drawPixmap(x, y, self.icon)


class BuildTargetPreviewStrip(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_value = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        layout.addWidget(self.scroll_area, 1)

        self.content = QWidget()
        self.content.setFixedHeight(BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        self.content_layout = QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(BUILD_TARGET_PREVIEW_SPACING)
        self.content_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.scroll_area.setWidget(self.content)

        for widget in (self.scroll_area.viewport(), self.content):
            widget.installEventFilter(self)

        hbar = self.scroll_area.horizontalScrollBar()
        hbar.valueChanged.connect(self.update_hints)
        hbar.rangeChanged.connect(lambda _min, _max: self.update_hints())

        self.left_hint = BuildTargetPreviewEdgeHint("chevron-left", "left", self)
        self.right_hint = BuildTargetPreviewEdgeHint("chevron-right", "right", self)
        self.refresh_content_width()

    def clear_targets(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.refresh_content_width()

    def add_target_widget(self, widget: QWidget) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.content_layout.addWidget(widget)
        widget.show()

    def finish_update(self) -> None:
        self.refresh_content_width()
        self.update_hints()

    def refresh_content_width(self) -> None:
        width = 0
        widget_count = 0

        for index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                continue
            widget_width = widget.width() or widget.sizeHint().width()
            width += widget_width
            widget_count += 1

        if widget_count > 1:
            width += BUILD_TARGET_PREVIEW_SPACING * (widget_count - 1)

        viewport_width = max(0, self.scroll_area.viewport().width())

        if widget_count == 0:
            width = viewport_width
            self.scroll_area.horizontalScrollBar().setValue(0)
        else:
            width = max(width, viewport_width)

        self.content.setFixedSize(width, BUILD_TARGET_PREVIEW_ROW_HEIGHT)
        self.content_layout.activate()
        self.content.updateGeometry()
        self.scroll_area.viewport().update()
        self.update_hints()

    def update_hints(self) -> None:
        has_widgets = any(
            self.content_layout.itemAt(i).widget() is not None
            for i in range(self.content_layout.count())
        )

        if not has_widgets:
            self.left_hint.hide()
            self.right_hint.hide()
            return

        hbar = self.scroll_area.horizontalScrollBar()
        can_scroll_left = hbar.value() > hbar.minimum()
        can_scroll_right = hbar.value() < hbar.maximum()
        self.left_hint.setVisible(can_scroll_left)
        self.right_hint.setVisible(can_scroll_right)
        self.left_hint.raise_()
        self.right_hint.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.left_hint.setGeometry(
            0,
            0,
            BUILD_TARGET_PREVIEW_HINT_WIDTH,
            self.height(),
        )
        self.right_hint.setGeometry(
            self.width() - BUILD_TARGET_PREVIEW_HINT_WIDTH,
            0,
            BUILD_TARGET_PREVIEW_HINT_WIDTH,
            self.height(),
        )
        self.refresh_content_width()
        self.update_hints()

    def _handle_wheel_scroll(self, event) -> bool:
        hbar = self.scroll_area.horizontalScrollBar()
        if hbar.maximum() <= hbar.minimum():
            return False

        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            delta = -pixel_delta.y() if pixel_delta.y() else pixel_delta.x()
        else:
            angle_delta = event.angleDelta()
            raw_delta = -angle_delta.y() if angle_delta.y() else angle_delta.x()
            delta = int(raw_delta / 120 * BUILD_TARGET_PREVIEW_ICON_SIZE)

        if not delta:
            return False

        hbar.setValue(hbar.value() + delta)
        return True

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._dragging = True
                self._drag_start_x = int(event.globalPosition().x())
                self._drag_start_value = self.scroll_area.horizontalScrollBar().value()
                return True
        elif event.type() == QEvent.Type.MouseMove and self._dragging:
            delta = self._drag_start_x - int(event.globalPosition().x())
            self.scroll_area.horizontalScrollBar().setValue(
                self._drag_start_value + delta
            )
            return True
        elif event.type() == QEvent.Type.MouseButtonRelease and self._dragging:
            self._dragging = False
            return True
        elif event.type() == QEvent.Type.Wheel:
            if self._handle_wheel_scroll(event):
                event.accept()
                return True
        return super().eventFilter(watched, event)


class ArtifactBrowserWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle(tr("artifact.browser.title"))
        self.resize(1180, 760)
        self.setStyleSheet(WINDOW_STYLE)

        self.current_pos = 1
        self.store = ArtifactBrowserStore.load_from_db()
        self.model = ArtifactListModel(self.store, self)
        self.delegate = ArtifactCardDelegate(self)

        self.sets_filter_enabled = True
        self.selected_game_set_ids: set[str] = set()
        self.selected_custom_set_ids: set[int] = set()
        self.selected_sort_stat_types: list[int] = []
        self._sort_popup: SortStatsPopup | None = None
        self._sets_popup: SetsFilterPopup | None = None
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
        self.build_target_element_filters: set[str] = set()
        self.build_target_weapon_filters: set[str] = set()
        self.build_target_rarity_filters: set[int] = set()
        self.editing_build_id: int | None = None
        self.editing_build_name: str = ""
        self.editing_build_slots: dict[int, int] = {}
        self.editing_build_targets: list[dict] = []
        self.editing_build_dirty = False
        self._build_target_keys_before_edit: set[str] | None = None
        self.pending_delete_build_id: int | None = None
        self.build_preset_row_buttons: dict[int, QPushButton] = {}
        self.build_row_name_input: QLineEdit | None = None
        self.build_slot_rows: dict[int, QFrame] = {}
        self.build_slot_icon_labels: dict[int, QLabel] = {}
        self.build_slot_stat_labels: dict[int, QLabel] = {}
        self.build_bonus_layout: QHBoxLayout | None = None
        self.build_summary_stats_layout: QGridLayout | None = None
        self.load_build_target_items()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_top_bar(root)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        self._build_list_view(content)
        self._build_build_target_selector(content)
        self._build_build_panel(content)
        root.addLayout(content, 1)
        self._build_bottom_bar(root)

        self.load_build_presets()
        self.apply_current_filters()
        self.update_custom_edit_bar()
        self.update_build_panel()

    def _build_top_bar(self, root: QVBoxLayout) -> None:
        top_frame = QFrame()
        top_frame.setObjectName("top_bar")

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
        self.sort_button.clicked.connect(self.show_sort_popup)
        top.addWidget(self.sort_button)
        self.sets_button.setObjectName("sets_button")
        self.sets_button.clicked.connect(self.show_sets_popup)
        top.addWidget(self.sets_button)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")
        top.addWidget(self.status_label)

        root.addWidget(top_frame)

    def _build_list_view(self, root: QVBoxLayout) -> None:
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setFlow(QListView.Flow.LeftToRight)
        self.list_view.setWrapping(True)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setMovement(QListView.Movement.Static)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setGridSize(QSize(GRID_SIZE.width(), GRID_SIZE.height()))
        self.list_view.setSpacing(0)
        self.list_view.setMouseTracking(True)
        self.list_view.setProperty("artifactEditMode", False)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.clicked.connect(self.on_artifact_clicked)


        root.addWidget(self.list_view, 1)

    def _build_build_target_selector(self, root) -> None:
        panel = QFrame()
        panel.setObjectName("build_target_panel")
        panel.setFixedWidth(TARGET_PANEL_WIDTH)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*TARGET_PANEL_MARGINS)
        layout.setSpacing(TARGET_PANEL_SPACING)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(TARGET_HEADER_SPACING)

        self.build_target_title_label = QLabel(tr("artifact.build.targets_title"))
        self.build_target_title_label.setObjectName("panel_title")
        self.build_target_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addSpacing(TARGET_HEADER_BALANCE_WIDTH)
        header_row.addWidget(self.build_target_title_label, 1)

        self.build_target_reset_button = QPushButton(tr("artifact.build.targets_reset"))
        self.build_target_reset_button.setObjectName("target_reset_button")
        self.build_target_reset_button.setFixedWidth(TARGET_RESET_BUTTON_WIDTH)
        self.build_target_reset_button.clicked.connect(self.reset_build_targets)
        header_row.addWidget(self.build_target_reset_button)
        layout.addLayout(header_row)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(TARGET_BODY_SPACING)

        filter_column = QVBoxLayout()
        filter_column.setContentsMargins(0, 0, 0, 0)
        filter_column.setSpacing(TARGET_FILTER_SPACING)
        for filters, selected in (
            (ELEMENT_FILTERS, self.build_target_element_filters),
            (CHARACTER_RARITY_FILTERS, self.build_target_rarity_filters),
            (WEAPON_TYPE_FILTERS, self.build_target_weapon_filters),
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
        filter_column.addStretch()
        body.addLayout(filter_column)

        target_scroll = QScrollArea()
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
        button.setIcon(QIcon(str(FILTER_ASSETS_DIR / icon_name)))
        button.setIconSize(QSize(TARGET_FILTER_ICON_SIZE, TARGET_FILTER_ICON_SIZE))
        button.setToolTip(tr(tooltip_key))
        button.clicked.connect(
            lambda checked=False, v=value, values=selected_values: self.on_build_target_filter_clicked(
                values,
                v,
                checked,
            )
        )
        return button

    def _build_build_panel(self, root) -> None:
        panel = QFrame()
        panel.setObjectName("build_panel")
        panel.setFixedWidth(384)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(7, 10, 7, 10)
        layout.setSpacing(8)

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

        self.build_preset_list_scroll = QScrollArea()
        self.build_preset_list_scroll.setWidgetResizable(True)
        self.build_preset_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        list_content = QWidget()
        self.build_preset_list_layout = QVBoxLayout(list_content)
        self.build_preset_list_layout.setContentsMargins(0, 0, 0, 0)
        self.build_preset_list_layout.setSpacing(5)
        self.build_preset_list_layout.addStretch()
        self.build_preset_list_scroll.setWidget(list_content)
        layout.addWidget(self.build_preset_list_scroll, 1)

        preview_block = QFrame()
        preview_block.setObjectName("build_preview_block")
        preview_block.setFixedHeight(285)
        preview_layout = QVBoxLayout(preview_block)
        preview_layout.setContentsMargins(0, 8, 0, 0)
        preview_layout.setSpacing(6)

        self.build_target_placeholder = BuildTargetPreviewStrip()
        preview_layout.addWidget(self.build_target_placeholder)

        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(3)
        preview_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        for pos in ARTIFACT_POSITIONS:
            preview_row.addWidget(self._make_build_slot_row(pos))
        self.build_bonus_container = QFrame()
        self.build_bonus_container.setFixedSize(87, 67)
        self.build_bonus_layout = QHBoxLayout(self.build_bonus_container)
        self.build_bonus_layout.setContentsMargins(0, 0, 0, 0)
        self.build_bonus_layout.setSpacing(3)
        self.build_bonus_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.build_bonus_container)
        preview_layout.addLayout(preview_row)

        stats_block = QFrame()
        stats_block.setObjectName("summary_block")
        stats_block.setFixedHeight(136)
        stats_layout = QVBoxLayout(stats_block)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        self.build_summary_stats_layout = QGridLayout()
        self.build_summary_stats_layout.setContentsMargins(0, 0, 0, 0)
        self.build_summary_stats_layout.setHorizontalSpacing(6)
        self.build_summary_stats_layout.setVerticalSpacing(5)
        stats_layout.addLayout(self.build_summary_stats_layout)
        preview_layout.addWidget(stats_block)
        layout.addWidget(preview_block)

        root.addWidget(panel)

    def _make_build_slot_row(self, pos: int) -> QFrame:
        row = QFrame()
        row.setObjectName("build_slot_mini")
        row.setFixedSize(48, 67)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(1)

        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        stat_label = QLabel("")
        stat_label.setObjectName("mini_stat_badge")
        stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stat_label.setFixedWidth(40)
        stat_label.setFixedHeight(18)
        layout.addWidget(stat_label)

        self.build_slot_rows[pos] = row
        self.build_slot_icon_labels[pos] = icon_label
        self.build_slot_stat_labels[pos] = stat_label
        return row

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("status_label")

        self.edit_mode_label = QLabel("")
        self.edit_mode_label.setObjectName("status_label")
        bottom.addWidget(self.edit_mode_label)

        self.save_edit_button = QPushButton()
        self.save_edit_button.setObjectName("custom_save_button")
        self.save_edit_button.setIcon(self._ui_icon("save"))
        self.save_edit_button.clicked.connect(self.save_active_edit)
        bottom.addWidget(self.save_edit_button)

        self.cancel_edit_button = QPushButton()
        self.cancel_edit_button.setObjectName("custom_cancel_button")
        self.cancel_edit_button.setIcon(self._ui_icon("x"))
        self.cancel_edit_button.clicked.connect(self.cancel_active_edit)
        bottom.addWidget(self.cancel_edit_button)

        bottom.addWidget(self.empty_label)

        bottom.addStretch()

        self.close_button = QPushButton(tr("common.close"))
        self.close_button.setObjectName("close_button")
        self.close_button.clicked.connect(self.close)
        bottom.addWidget(self.close_button)

        root.addLayout(bottom)

    def _position_label(self, pos: int) -> str:
        label_key = ARTIFACT_POSITION_LABEL_KEYS.get(pos)
        return tr(label_key) if label_key else str(pos)

    def _ui_icon(self, name: str) -> QIcon:
        return auto_contrast_svg_icon(
            name,
            UI_ICON_DEFAULT_SIZE,
            UI_ICON_BUTTON_BACKGROUND,
        )

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

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("artifact.browser.title"))

        for pos, button in self.position_buttons.items():
            button.setText(self._position_label(pos))

        self.close_button.setText(tr("common.close"))
        self.save_edit_button.setToolTip(self.active_save_tooltip())
        self.cancel_edit_button.setToolTip(self.active_cancel_tooltip())
        self.build_title_label.setText(tr("artifact.build.presets_title"))
        self.build_target_title_label.setText(tr("artifact.build.targets_title"))
        self.build_target_reset_button.setText(tr("artifact.build.targets_reset"))
        self.build_target_hint_label.setText(tr("artifact.build.no_target_hint"))
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

    def set_position(self, pos: int) -> None:
        self.current_pos = pos
        self.apply_current_filters()

    def on_sets_filter_enabled_changed(self, checked: bool) -> None:
        self.sets_filter_enabled = checked
        self.update_sets_filter_switch_text()
        self.apply_current_filters()

    def show_sets_popup(self) -> None:
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

        button_pos = self.sets_button.mapToGlobal(QPoint(0, self.sets_button.height() + 4))
        self._move_popup_inside_screen(self._sets_popup, button_pos)
        self._sets_popup.show()
        self._sets_popup.raise_()
        self._sets_popup.activateWindow()

    def show_sort_popup(self) -> None:
        if self._sort_popup is None:
            self._sort_popup = SortStatsPopup(
                selected_stat_types=self.selected_sort_stat_types,
                on_selection_changed=self.on_sort_selection_changed,
                parent=self,
            )

        button_pos = self.sort_button.mapToGlobal(QPoint(0, self.sort_button.height() + 4))
        self._move_popup_inside_screen(self._sort_popup, button_pos)
        self._sort_popup.show()
        self._sort_popup.raise_()
        self._sort_popup.activateWindow()

    def _move_popup_inside_screen(self, popup: QWidget, preferred_pos: QPoint) -> None:
        popup_size = popup.sizeHint().expandedTo(popup.minimumSize())
        popup.resize(popup_size)

        screen = self.sets_button.screen() or self.screen() or QApplication.primaryScreen()
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
            above_pos = self.sets_button.mapToGlobal(
                QPoint(0, -popup_size.height() - 4)
            )
            y = above_pos.y() if above_pos.y() >= available.y() else max_y

        if y < available.y():
            y = available.y()

        popup.move(QPoint(x, y))

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
        if not self.store.database_exists:
            self.model.set_artifact_ids([])
            self.status_label.setText(tr("artifact.browser.database_missing"))
            self.empty_label.setText(tr("artifact.browser.import_first"))
            return

        base_ids = self.store.ids_for_position(self.current_pos)
        visible_ids = list(base_ids)

        selected_any_sets = bool(self.selected_game_set_ids or self.selected_custom_set_ids)

        if self.sets_filter_enabled and selected_any_sets:
            allowed_ids: set[int] = set()
            allowed_ids.update(self.store.ids_for_game_sets(self.selected_game_set_ids))
            allowed_ids.update(self.store.ids_for_custom_sets(self.selected_custom_set_ids))
            visible_ids = [
                artifact_id
                for artifact_id in base_ids
                if artifact_id in allowed_ids
            ]

        visible_ids = self.store.sort_artifact_ids(
            visible_ids,
            self.selected_sort_stat_types,
        )
        priority_ids = self.current_highlight_artifact_ids()
        if priority_ids:
            visible_ids = sorted(
                visible_ids,
                key=lambda artifact_id: 0 if artifact_id in priority_ids else 1,
            )
        self.model.set_artifact_ids(visible_ids)
        self.update_status(len(visible_ids), len(base_ids))

    def update_status(self, visible_count: int, total_count: int) -> None:
        slot_name = self._position_label(self.current_pos)
        self.status_label.setText(f"{slot_name}: {visible_count}/{total_count}")

        if total_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty"))
        elif visible_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty_for_sets"))
        else:
            self.empty_label.setText("")

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

        self.store = ArtifactBrowserStore.load_from_db()
        self.model.set_store(self.store)
        self.load_build_target_items()
        if not keep_custom_edit:
            self.finish_custom_set_edit()
            self.finish_build_preset_edit()
        if reset_popup:
            if self._sets_popup is not None:
                self._sets_popup.close()
            self._sets_popup = None
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

    def load_build_target_items(self) -> None:
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
        manifest = self.load_hoyolab_manifest()
        assets = manifest_asset_items(
            manifest,
            "characterAssets",
            HOYOLAB_CHARACTER_ASSETS_DIR,
        )
        for asset in assets:
            char_id = character_id(asset)
            if char_id is None:
                continue
            key = self._character_target_key(char_id)
            self.build_target_items_by_key[key] = {
                "key": key,
                "target_type": "character",
                "character_id": char_id,
                "character_name": character_name(asset),
                "asset": asset,
                "path": asset.get("path"),
            }

    def load_hoyolab_manifest(self) -> dict:
        if not HOYOLAB_MANIFEST_FILE.exists():
            return {}
        try:
            with open(HOYOLAB_MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"Failed to load HoYoLAB manifest: {exc}")
            return {}

    def refresh_build_target_list(self) -> None:
        if not hasattr(self, "build_target_list_layout"):
            return

        self._clear_layout(self.build_target_list_layout)
        self.build_target_buttons_by_key.clear()
        self.build_target_reset_button.setEnabled(bool(self.selected_build_target_keys))

        universal = self.build_target_items_by_key.get(BUILD_TARGET_UNIVERSAL_KEY)
        if universal:
            self.build_target_list_layout.addWidget(self._make_build_target_button(universal))

        character_items = [
            item
            for key, item in self.build_target_items_by_key.items()
            if key != BUILD_TARGET_UNIVERSAL_KEY
            and character_matches_filters(
                item.get("asset") or {},
                self.build_target_element_filters,
                self.build_target_weapon_filters,
                self.build_target_rarity_filters,
            )
        ]
        character_items.sort(key=lambda item: character_sort_key(item.get("asset") or {}))
        for item in character_items:
            self.build_target_list_layout.addWidget(self._make_build_target_button(item))
        self.build_target_list_layout.addStretch()

    def _make_build_target_button(self, item: dict) -> QPushButton:
        key = item["key"]
        button = QPushButton(item.get("character_name") or "")
        button.setObjectName("target_item")
        button.setCheckable(True)
        button.setChecked(key in self.selected_build_target_keys)
        path = item.get("path")
        if key == BUILD_TARGET_UNIVERSAL_KEY:
            button.setIcon(QIcon(self._make_universal_target_preview_pixmap()))
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
        elif path:
            button.setIcon(QIcon(str(path)))
            button.setIconSize(QSize(TARGET_ITEM_ICON_SIZE, TARGET_ITEM_ICON_SIZE))
        button.clicked.connect(
            lambda checked=False, value=key: self.toggle_build_target(value)
        )
        self.build_target_buttons_by_key[key] = button
        return button

    def on_build_target_filter_clicked(self, selected_values: set, value, checked: bool) -> None:
        if checked:
            selected_values.add(value)
        else:
            selected_values.discard(value)
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
        if key in next_keys:
            next_keys.remove(key)
        else:
            next_keys.add(key)

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
        self.refresh_build_target_list()
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
        return []

    def preset_matches_selected_targets(self, preset: dict) -> bool:
        if not self.selected_build_target_keys:
            return False
        preset_keys = self.target_keys_from_targets(preset.get("targets") or [])
        return self.selected_build_target_keys.issubset(preset_keys)

    def load_build_presets(self) -> None:
        self.build_presets = list_build_presets()
        self.refresh_build_preset_list()

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
            return

        for preset in filtered_presets:
            self.build_preset_list_layout.addWidget(self._make_build_preset_row(preset))
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
            select_button.setFixedWidth(BUILD_ROW_NAME_WIDTH)
            select_button.clicked.connect(
                lambda _checked=False, value=build_id: self.select_build_preset(value)
            )
            layout.addWidget(select_button, 1)
            self.build_preset_row_buttons[build_id] = select_button

        if not editing_this_row:
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
            layout.addWidget(confirm_button)

            cancel_button = QPushButton()
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.setIcon(self._ui_icon("x"))
            cancel_button.setToolTip(tr("common.cancel"))
            cancel_button.clicked.connect(self.cancel_delete_build_preset)
            layout.addWidget(cancel_button)
            return row

        if editing_this_row:
            save_button = QPushButton()
            save_button.setObjectName("row_save_button")
            save_button.setIcon(self._ui_icon("check"))
            save_button.setToolTip(tr("artifact.build.save"))
            save_button.clicked.connect(self.save_build_preset_edit)
            layout.addWidget(save_button)

            cancel_button = QPushButton()
            cancel_button.setObjectName("row_cancel_button")
            cancel_button.setIcon(self._ui_icon("x"))
            cancel_button.setToolTip(tr("artifact.build.cancel"))
            cancel_button.clicked.connect(self.cancel_build_preset_edit)
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

    def _trim_transparent_pixmap(self, pixmap: QPixmap) -> QPixmap:
        image = pixmap.toImage()
        if image.isNull():
            return pixmap

        left = image.width()
        right = -1
        top = image.height()
        bottom = -1

        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() <= 0:
                    continue
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)

        if right < left or bottom < top:
            return pixmap

        return pixmap.copy(QRect(left, top, right - left + 1, bottom - top + 1))

    def _apply_diagonal_alpha(
        self,
        pixmap: QPixmap,
        *,
        keep_top_left: bool,
        feather: int,
    ) -> QPixmap:
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        if image.isNull():
            return pixmap

        width = image.width()
        height = image.height()
        denominator_x = max(1, width - 1)
        denominator_y = max(1, height - 1)
        feather_band = max(0.001, feather / max(1, min(width, height)))

        for y in range(height):
            for x in range(width):
                color = image.pixelColor(x, y)
                if color.alpha() <= 0:
                    continue

                signed = (x / denominator_x) + (y / denominator_y) - 1.0
                if keep_top_left:
                    if signed <= -feather_band:
                        alpha_factor = 1.0
                    elif signed >= feather_band:
                        alpha_factor = 0.0
                    else:
                        alpha_factor = (feather_band - signed) / (2 * feather_band)
                else:
                    if signed >= feather_band:
                        alpha_factor = 1.0
                    elif signed <= -feather_band:
                        alpha_factor = 0.0
                    else:
                        alpha_factor = (signed + feather_band) / (2 * feather_band)

                color.setAlpha(int(color.alpha() * alpha_factor))
                image.setPixelColor(x, y, color)

        return QPixmap.fromImage(image)

    def _make_diagonal_split_set_bonus_pixmap(
        self,
        active_sets: list[dict],
        artifact_ids: list[int],
    ) -> QPixmap | None:
        bottom_right_icon = self._make_set_icon_pixmap(
            active_sets[0],
            BUILD_ROW_BONUS_DIAGONAL_ICON_SIZE,
            artifact_ids,
        )
        top_left_icon = self._make_set_icon_pixmap(
            active_sets[1],
            BUILD_ROW_BONUS_DIAGONAL_ICON_SIZE,
            artifact_ids,
        )
        if bottom_right_icon is None or top_left_icon is None:
            return None

        return make_diagonal_split_pixmap(
            bottom_right_icon,
            top_left_icon,
            size=BUILD_ROW_BONUS_DIAGONAL_ICON_SIZE,
            feather=BUILD_ROW_BONUS_DIAGONAL_FEATHER,
        )

    def _make_set_icon_pixmap(
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

        return scale_trimmed_pixmap(pixmap, icon_size)

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
            return label

        available_height = (
            BUILD_ROW_BONUS_STACK_HEIGHT - BUILD_ROW_BONUS_STACK_MARGIN * 2
        )
        icon_size = (
            available_height
            if len(active_sets) <= 1
            else available_height // 2
        )
        icon_pixmaps = [
            self._make_set_bonus_pixmap(item, icon_size, artifact_ids)
            for item in active_sets
        ]
        icon_pixmaps = [
            pixmap
            for pixmap in icon_pixmaps
            if pixmap is not None and not pixmap.isNull()
        ]
        if not icon_pixmaps:
            return None

        stack = QWidget()
        stack.setObjectName("build_row_bonus_stack")
        stack.setFixedSize(BUILD_ROW_BONUS_STACK_WIDTH, BUILD_ROW_BONUS_STACK_HEIGHT)
        layout = QVBoxLayout(stack)
        layout.setContentsMargins(
            0,
            BUILD_ROW_BONUS_STACK_MARGIN,
            0,
            BUILD_ROW_BONUS_STACK_MARGIN,
        )
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for pixmap in icon_pixmaps:
            label = QLabel()
            label.setFixedSize(icon_size, icon_size)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setPixmap(pixmap)
            layout.addWidget(label)

        return stack

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

    def start_build_preset_edit(self, build_id: int) -> None:
        if not self.confirm_discard_custom_edit():
            return
        if self.editing_build_dirty and build_id != self.editing_build_id:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            return
        self.finish_custom_set_edit()
        preset = get_build_preset(build_id)
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

    def select_build_preset(self, build_id: int) -> None:
        if self.edit_selection_mode != EDIT_MODE_NONE:
            self.empty_label.setText(tr("artifact.build.finish_edit_first"))
            self.refresh_build_preset_list()
            return

        preset = get_build_preset(build_id)
        if preset is None:
            return

        self.ensure_build_target_items(preset.get("targets") or [])
        self.selected_build_id = int(build_id)
        self.selected_build_slots = {
            int(slot["pos"]): int(slot["artifact_id"])
            for slot in preset.get("slots", [])
        }
        self.selected_build_targets = list(preset.get("targets") or [])
        self.pending_delete_build_id = None
        self.build_name_input.blockSignals(True)
        self.build_name_input.setText("")
        self.build_name_input.blockSignals(False)
        self.update_build_panel()
        self.update_build_create_controls()
        self.update_edit_selection_mode()
        self.apply_current_filters()
        self.refresh_build_preset_list()

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
        editing = self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
        has_selection = editing or bool(self.selected_build_id)
        slots = self.editing_build_slots if editing else self.selected_build_slots

        for pos in ARTIFACT_POSITIONS:
            artifact_id = slots.get(pos) if has_selection else None
            self.update_build_slot_row(pos, artifact_id)

        self.update_build_target_preview()
        self.update_build_summary()
        self.update_build_create_controls()

    def update_build_target_preview(self) -> None:
        self.build_target_placeholder.clear_targets()
        for target in self.current_preview_build_targets():
            self.build_target_placeholder.add_target_widget(
                self._make_target_preview_cell(target)
            )
        self.build_target_placeholder.finish_update()

    def _make_target_preview_cell(self, target: dict) -> QWidget:
        key = self.target_key_from_target(target)
        item = self.build_target_items_by_key.get(key or "")
        label = QLabel()
        label.setFixedSize(
            BUILD_TARGET_PREVIEW_ICON_SIZE,
            BUILD_TARGET_PREVIEW_ICON_SIZE,
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if target.get("target_type") == "universal":
            label.setPixmap(self._make_universal_target_preview_pixmap())
            label.setToolTip(tr("artifact.build.target_universal"))
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            return label

        if item and item.get("path"):
            pixmap = QPixmap(str(item["path"]))
            if not pixmap.isNull():
                label.setPixmap(
                    pixmap.scaled(
                        BUILD_TARGET_PREVIEW_ICON_SIZE,
                        BUILD_TARGET_PREVIEW_ICON_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        if label.pixmap() is None:
            name = str(target.get("character_name") or "?")
            label.setText(name[:2])
        label.setToolTip(str(target.get("character_name") or ""))
        return label

    def update_build_create_controls(self) -> None:
        new_draft = (
            self.edit_selection_mode == EDIT_MODE_BUILD_PRESET
            and self.editing_build_id is None
        )
        self.new_build_button.setObjectName(
            "row_save_button" if new_draft else "icon_button"
        )
        self.new_build_button.setIcon(self._ui_icon("check" if new_draft else "plus"))
        self.new_build_button.setToolTip(
            tr("artifact.build.save") if new_draft else tr("artifact.build.new")
        )
        self.cancel_new_build_button.setVisible(new_draft)
        for button in (self.new_build_button, self.cancel_new_build_button):
            button.style().unpolish(button)
            button.style().polish(button)

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
                        40,
                        40,
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
                40,
                40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def current_build_artifact_ids(self) -> set[int]:
        if self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            return set(self.editing_build_slots.values())
        return set(self.selected_build_slots.values())

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
        slots = self.editing_build_slots if editing else self.selected_build_slots

        if not slots:
            self.fill_build_stat_summary({})
            return

        try:
            if editing and self.editing_build_id is not None and not self.editing_build_dirty:
                summary = calculate_build_summary(build_id=self.editing_build_id)
            elif not editing and self.selected_build_id is not None:
                summary = calculate_build_summary(build_id=self.selected_build_id)
            else:
                summary = calculate_build_summary(slots=slots)
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

    def _make_set_bonus_cell(self, item: dict) -> QFrame:
        cell = QFrame()
        cell.setObjectName("build_slot_mini")
        cell.setFixedSize(42, 67)
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        icon = QLabel()
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._make_set_bonus_pixmap(
            item,
            34,
            self.current_build_artifact_ids(),
        )
        if pixmap is not None:
            icon.setPixmap(pixmap)
        if icon.pixmap() is None:
            count = str(item["count"])
            icon.setText(f"{str(item.get('set_name') or item.get('set_uid') or '?')[:2]}{count}")
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
            label.setFixedHeight(20)
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
        delete_build_preset(int(build_id))
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
        self.edit_mode_label.setVisible(editing)
        self.save_edit_button.setVisible(editing)
        self.cancel_edit_button.setVisible(editing)
        self.save_edit_button.setToolTip(self.active_save_tooltip())
        self.cancel_edit_button.setToolTip(self.active_cancel_tooltip())
        self.list_view.setProperty("artifactEditMode", editing)
        self.list_view.style().unpolish(self.list_view)
        self.list_view.style().polish(self.list_view)
        self.list_view.viewport().update()

        if self.edit_selection_mode == EDIT_MODE_CUSTOM_SET:
            self.edit_mode_label.setText(
                tr(
                    "artifact.custom.editing_status",
                    name=self.editing_custom_set_name,
                    count=len(self.editing_custom_artifact_ids),
                )
            )
        elif self.edit_selection_mode == EDIT_MODE_BUILD_PRESET:
            self.edit_mode_label.setText(
                tr("artifact.build.editing_status", name=self.editing_build_name)
            )
        else:
            self.edit_mode_label.setText("")

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
