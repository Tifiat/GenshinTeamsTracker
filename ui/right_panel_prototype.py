from __future__ import annotations

import html
import re
from functools import lru_cache

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    RightPanelBonusSourceDisplayItem,
    RightPanelBuildMiniSetViewModel,
    RightPanelChamberRowViewModel,
    RightPanelDetailRowViewModel,
    RightPanelGcsimStatusViewModel,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
    RightPanelSlotPrototypeViewModel,
    RightPanelTeamPrototypeViewModel,
)
from ui.utils.pixmap_utils import (
    draw_count_badge,
    make_diagonal_split_pixmap,
    scale_trimmed_pixmap_to_size,
)
from ui.utils.horizontal_scroll import HorizontalDragScrollArea
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from ui.artifact_browser.queries import list_set_bonus_description_map


RIGHT_PANEL_PROTOTYPE_MIN_WIDTH = 700
RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH = 680
SLOT_CARD_MARGIN = 5
SLOT_PORTRAIT_SIZE = 96
SLOT_EQUIP_BOX_SIZE = 46
SLOT_EQUIP_ICON_SIZE = 42
SLOT_WEAPON_ICON_SIZE = 52
SLOT_BUILD_BONUS_FEATHER = 3
SLOT_TOP_SPACING = 2
SLOT_CLUSTER_WIDTH = SLOT_PORTRAIT_SIZE + SLOT_TOP_SPACING + SLOT_EQUIP_BOX_SIZE
SLOT_BADGE_HEIGHT = 22
SLOT_WARNING_BADGE_WIDTH = SLOT_EQUIP_BOX_SIZE
SLOT_CARD_WIDTH = SLOT_CLUSTER_WIDTH + SLOT_CARD_MARGIN * 2
SLOT_CARD_FIXED_HEIGHT = 154
SLOT_NAME_HEIGHT = 18

_FIT_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap | None] = {}


class RightPanelPrototypeWidget(QWidget):
    """Standalone visual prototype for the future right panel."""

    mode_requested = Signal(str)
    slot_selected = Signal(int, int)
    external_bonuses_toggled = Signal(bool)

    def __init__(
        self,
        model: RightPanelPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("RightPanelPrototypeWidget")
        self.setMinimumWidth(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH)
        self._model = model
        self._slot_widgets: list[RightPanelSlotPrototypeWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = OverlayVerticalScrollArea(auto_hide_ms=850)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self._scroll)

        self._content = QWidget()
        self._content.setObjectName("RightPanelPrototypeContent")
        self._content.setMinimumWidth(RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(7)
        self._scroll.setWidget(self._content)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tabs_container = QWidget()
        self._tabs_layout = QHBoxLayout(self._tabs_container)
        self._tabs_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs_layout.setSpacing(6)
        self._layout.addWidget(self._tabs_container)
        self._create_tabs(model)

        self._teams_container = QWidget()
        self._teams_layout = QVBoxLayout(self._teams_container)
        self._teams_layout.setContentsMargins(0, 0, 0, 0)
        self._teams_layout.setSpacing(6)
        self._layout.addWidget(self._teams_container)

        self._chamber_table = ChamberTableBlockWidget()
        self._layout.addWidget(self._chamber_table)

        self._details_frame = SelectedCharacterDetailsWidget()
        self._details_frame.external_bonuses_toggled.connect(
            self.external_bonuses_toggled.emit
        )
        self._layout.addWidget(self._details_frame)

        self._actions = ActionBarPrototypeWidget(model.action_labels)
        self._layout.addWidget(self._actions)
        self._layout.addStretch(1)

        self.setStyleSheet(_stylesheet())
        self.set_model(model)

    def set_model(self, model: RightPanelPrototypeViewModel) -> None:
        QToolTip.hideText()
        self._model = model
        self._sync_tabs(model.mode)
        self._clear_layout(self._teams_layout)
        self._slot_widgets.clear()

        for team in model.teams:
            team_widget = RightPanelTeamPrototypeWidget(team)
            team_widget.slot_selected.connect(self.slot_selected.emit)
            self._slot_widgets.extend(team_widget.slot_widgets())
            self._teams_layout.addWidget(team_widget)

        self._chamber_table.set_rows(
            model.chamber_headers,
            model.chamber_rows,
            total_seconds=model.total_seconds,
            gcsim_status=model.gcsim_status,
        )
        self._details_frame.set_details(model.selected_details)
        self._actions.set_labels(model.action_labels)

    def recommended_standalone_size(self) -> QSize:
        self._content.adjustSize()
        hint = self._content.sizeHint()
        return QSize(
            max(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, hint.width()),
            max(1, hint.height() + self._scroll.frameWidth() * 2),
        )

    def _create_tabs(self, model: RightPanelPrototypeViewModel) -> None:
        for label in model.mode_tabs:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("ModeTabButton")
            mode = MODE_DPS_DUMMY if "DPS" in label else MODE_ABYSS
            button.clicked.connect(
                lambda _checked=False, value=mode: self.mode_requested.emit(value)
            )
            self._tab_group.addButton(button)
            self._tabs_layout.addWidget(button)

    def _sync_tabs(self, mode: str) -> None:
        for button in self._tab_group.buttons():
            should_check = (
                (mode == MODE_DPS_DUMMY and "DPS" in button.text())
                or (mode == MODE_ABYSS and "Abyss" in button.text())
            )
            button.setChecked(should_check)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class RightPanelTeamPrototypeWidget(QFrame):
    slot_selected = Signal(int, int)

    def __init__(
        self,
        model: RightPanelTeamPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("TeamSlotRow")
        self._slot_widgets: list[RightPanelSlotPrototypeWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(6)
        layout.addWidget(grid_container)

        for index, slot in enumerate(model.slots):
            widget = RightPanelSlotPrototypeWidget(slot)
            widget.clicked.connect(self.slot_selected.emit)
            self._slot_widgets.append(widget)
            grid.addWidget(widget, index // 4, index % 4)

    def slot_widgets(self) -> list["RightPanelSlotPrototypeWidget"]:
        return list(self._slot_widgets)


class RightPanelSlotPrototypeWidget(QFrame):
    clicked = Signal(int, int)

    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._model = model
        self.setObjectName("SlotCardSelected" if model.is_selected else "SlotCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(SLOT_CARD_WIDTH)
        self.setFixedHeight(SLOT_CARD_FIXED_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
        )
        outer.setSpacing(3)

        image_cluster = QWidget()
        image_cluster.setFixedWidth(SLOT_CLUSTER_WIDTH)
        cluster_layout = QVBoxLayout(image_cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(4)
        outer.addWidget(image_cluster, alignment=Qt.AlignmentFlag.AlignLeft)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SLOT_TOP_SPACING)
        cluster_layout.addLayout(top)

        portrait = QLabel(model.portrait_label)
        portrait.setObjectName("PortraitBox" if not model.is_empty else "PortraitBoxEmpty")
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait_size = QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE)
        portrait.setFixedSize(portrait_size)
        portrait_pixmap = _fit_pixmap(model.portrait_path, portrait_size)
        if portrait_pixmap is not None:
            portrait.setText("")
            portrait.setPixmap(portrait_pixmap)
        top.addWidget(portrait, alignment=Qt.AlignmentFlag.AlignLeft)

        side = QVBoxLayout()
        side.setSpacing(4)
        side.setContentsMargins(0, 0, 0, 0)
        top.addLayout(side)

        weapon = QLabel(model.weapon_square_label)
        weapon.setObjectName("MiniEquipBox")
        weapon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weapon.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)
        weapon_pixmap = _fit_pixmap(
            model.weapon_image_path,
            QSize(SLOT_WEAPON_ICON_SIZE, SLOT_WEAPON_ICON_SIZE),
        )
        if weapon_pixmap is not None:
            weapon.setText("")
            weapon.setPixmap(weapon_pixmap)
        if model.weapon_tooltip:
            install_custom_tooltip(weapon, model.weapon_tooltip)
        side.addWidget(weapon, alignment=Qt.AlignmentFlag.AlignLeft)

        artifact = BuildMiniSetStackWidget(model)
        side.addWidget(artifact, alignment=Qt.AlignmentFlag.AlignLeft)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)
        cluster_layout.addLayout(footer)

        badge = QLabel(model.stat_badge)
        badge.setObjectName("StatBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(SLOT_PORTRAIT_SIZE, SLOT_BADGE_HEIGHT)
        footer.addWidget(badge)
        footer.addSpacing(SLOT_TOP_SPACING)

        if model.warning_count:
            warning = QLabel(f"!{model.warning_count}", image_cluster)
            warning.setObjectName("WarningBadge")
            warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warning.setFixedSize(SLOT_WARNING_BADGE_WIDTH, SLOT_BADGE_HEIGHT)
            footer.addWidget(warning)
            install_custom_tooltip(warning, model.warning_tooltip)
        else:
            footer.addSpacing(SLOT_WARNING_BADGE_WIDTH)

        name = QLabel(model.character_title)
        name.setObjectName("SlotName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(False)
        name.setFixedHeight(SLOT_NAME_HEIGHT)
        outer.addWidget(name)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._model.team_index, self._model.slot_index)
        super().mousePressEvent(event)


class BuildMiniSetStackWidget(QLabel):
    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(model.artifact_square_label, parent)
        is_missing = model.artifact_square_label in {"Equip", "Fix", "ART"}
        self.setObjectName("MiniEquipBoxMissing" if is_missing else "MiniEquipBox")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)

        pixmap = _build_mini_set_stack_pixmap(model.build_mini_sets)
        if pixmap is None and model.artifact_image_path:
            pixmap = _fit_pixmap(
                model.artifact_image_path,
                QSize(SLOT_EQUIP_ICON_SIZE, SLOT_EQUIP_ICON_SIZE),
            )
        if pixmap is not None:
            self.setText("")
            self.setPixmap(pixmap)
        elif model.build_mini_sets:
            self.setText(_build_mini_set_fallback_text(model.build_mini_sets))

        tooltip = _build_mini_set_tooltip_html(model.build_mini_sets)
        if tooltip:
            install_custom_tooltip(self, tooltip)


class ChamberTableBlockWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InfoBlock")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(7)

    def set_rows(
        self,
        headers: tuple[str, ...],
        rows: tuple[RightPanelChamberRowViewModel, ...],
        *,
        total_seconds: int,
        gcsim_status: RightPanelGcsimStatusViewModel,
    ) -> None:
        _clear_layout(self._layout)

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)
        grid.setColumnMinimumWidth(0, 34)
        grid.setColumnStretch(0, 0)
        for column in range(1, 7):
            grid.setColumnStretch(column, 1)
        self._layout.addWidget(grid_container)

        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("TableHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if column == 0:
                label.setFixedWidth(34)
            grid.addWidget(label, 0, column)

        for row_index, row in enumerate(rows, start=1):
            values = (
                row.chamber_label,
                f"[{row.team1_time}] {row.team1_seconds}s",
                f"[{row.team2_time}] {row.team2_seconds}s",
                row.factual_team1,
                row.factual_team2,
                row.sim_team1,
                row.sim_team2,
            )
            for column, text in enumerate(values):
                label = QLabel(text)
                label.setObjectName("TableCellPrimary" if column == 0 else "TableCell")
                label.setAlignment(
                    Qt.AlignmentFlag.AlignLeft
                    if column == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                if column == 0:
                    label.setFixedWidth(34)
                grid.addWidget(label, row_index, column)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self._layout.addLayout(bottom)

        total = QLabel(f"Total: {total_seconds}s")
        total.setObjectName("SummaryLine")
        bottom.addWidget(total, 1)

        status = QLabel(gcsim_status.status)
        status.setObjectName("SubtleText")
        bottom.addWidget(status)

        button = QPushButton(gcsim_status.button_label)
        button.setObjectName("GhostButton")
        button.setEnabled(False)
        bottom.addWidget(button)


class SelectedCharacterDetailsWidget(QFrame):
    external_bonuses_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DetailsBlock")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)

    def set_details(self, details: RightPanelSelectedDetailsViewModel) -> None:
        _clear_layout(self._layout)

        if not details.has_selection:
            empty = QLabel("No selected character.")
            empty.setObjectName("SubtleText")
            empty.setWordWrap(True)
            self._layout.addWidget(empty)
            return

        body = QHBoxLayout()
        body.setSpacing(10)
        self._layout.addLayout(body)

        stats_frame = QFrame()
        stats_frame.setObjectName("StatsPanel")
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        stats_layout.setSpacing(6)
        body.addWidget(stats_frame, 2)

        for row in details.stat_rows:
            stats_layout.addLayout(_detail_row_layout(row, metric=False))
        stats_layout.addStretch(1)

        meta_frame = QFrame()
        meta_frame.setObjectName("MetaPanel")
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(8, 8, 8, 8)
        meta_layout.setSpacing(6)
        body.addWidget(meta_frame, 3)

        name = QLabel(details.character_name)
        name.setObjectName("DetailsName")
        name.setWordWrap(True)
        meta_layout.addWidget(name)

        chips = QHBoxLayout()
        chips.setSpacing(5)
        meta_layout.addLayout(chips)
        for text in _character_chips(details):
            chip = QLabel(text)
            chip.setObjectName("MetaChip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chips.addWidget(chip)
        chips.addStretch(1)

        self._add_weapon_summary(meta_layout, details)
        if details.crit_value is not None:
            self._add_cv_summary(meta_layout, details.crit_value)
        meta_layout.addStretch(1)

        bonus_strip = BonusSourceStripWidget()
        bonus_strip.external_bonuses_toggled.connect(self.external_bonuses_toggled.emit)
        bonus_strip.set_items(
            details.bonus_sources,
            external_bonuses_enabled=details.external_bonuses_enabled,
        )
        self._layout.addWidget(bonus_strip)

    def _add_weapon_summary(
        self,
        layout: QVBoxLayout,
        details: RightPanelSelectedDetailsViewModel,
    ) -> None:
        if not details.weapon_name and not details.weapon_icon_path:
            return
        weapon_bits = []
        if details.weapon_refinement is not None:
            weapon_bits.append(f"R{details.weapon_refinement}")
        if details.weapon_level is not None:
            weapon_bits.append(f"Lv.{details.weapon_level}")
        if details.weapon_base_atk:
            weapon_bits.append(f"ATK {details.weapon_base_atk}")
        if details.weapon_secondary_label and details.weapon_secondary_value:
            weapon_bits.append(
                f"{details.weapon_secondary_label} {details.weapon_secondary_value}"
            )

        frame = QFrame()
        frame.setObjectName("MetaSummaryBox")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(8)
        layout.addWidget(frame)

        icon = QLabel("WPN")
        icon.setObjectName("DetailsWeaponIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(48, 48)
        pixmap = _fit_pixmap(details.weapon_icon_path, QSize(50, 50))
        if pixmap is not None:
            icon.setText("")
            icon.setPixmap(pixmap)
        if details.weapon_tooltip:
            install_custom_tooltip(icon, details.weapon_tooltip)
        frame_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignLeft)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(4)
        frame_layout.addLayout(text_column, 1)

        weapon_name = QLabel(details.weapon_name)
        weapon_name.setObjectName("MetaValueStrong")
        weapon_name.setWordWrap(True)
        if details.weapon_tooltip:
            install_custom_tooltip(weapon_name, details.weapon_tooltip)
        text_column.addWidget(weapon_name)

        if weapon_bits:
            weapon_meta = QLabel(" · ".join(weapon_bits))
            weapon_meta.setObjectName("MetaValue")
            weapon_meta.setWordWrap(True)
            if details.weapon_tooltip:
                install_custom_tooltip(weapon_meta, details.weapon_tooltip)
            text_column.addWidget(weapon_meta)
        text_column.addStretch(1)

    def _add_cv_summary(self, layout: QVBoxLayout, crit_value: float) -> None:
        frame = QFrame()
        frame.setObjectName("MetaSummaryBox")
        row = QHBoxLayout()
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(8)
        frame.setLayout(row)
        layout.addWidget(frame)

        key = QLabel("CV")
        key.setObjectName("MetaLabel")
        row.addWidget(key)

        value = QLabel(f"{crit_value:g}")
        value.setObjectName("MetaValueStrong")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value, 1)

    def _add_meta_line(self, layout: QVBoxLayout, label: str, value: str) -> QLabel | None:
        if not value:
            return None
        row = QHBoxLayout()
        row.setSpacing(6)
        layout.addLayout(row)

        key = QLabel(label)
        key.setObjectName("MetaLabel")
        key.setFixedWidth(78)
        row.addWidget(key)

        text = QLabel(value)
        text.setObjectName("MetaValue")
        text.setWordWrap(True)
        row.addWidget(text, 1)
        return text


class BonusSourceStripWidget(QFrame):
    external_bonuses_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BonusSourceStrip")
        self._external_bonuses_enabled = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = HorizontalDragScrollArea(wheel_step=40)
        self._scroll.setObjectName("BonusSourceScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(28)
        self._scroll.clicked.connect(self._toggle_external_bonuses)
        root.addWidget(self._scroll)

        self._content = QWidget()
        self._layout = QHBoxLayout(self._content)
        self._layout.setContentsMargins(0, 1, 0, 1)
        self._layout.setSpacing(5)
        self._scroll.setWidget(self._content)

    def set_items(
        self,
        items: tuple[RightPanelBonusSourceDisplayItem, ...],
        *,
        external_bonuses_enabled: bool,
    ) -> None:
        _clear_layout(self._layout)
        self._external_bonuses_enabled = bool(external_bonuses_enabled)
        self.setProperty("active", self._external_bonuses_enabled)
        self.style().unpolish(self)
        self.style().polish(self)
        if not items:
            empty = QLabel("No external bonuses")
            empty.setObjectName("BonusStripEmpty")
            empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._layout.addWidget(empty)
            self._layout.addStretch(1)
            return
        for item in items:
            chip = BonusSourceChipWidget(item)
            chip.installEventFilter(self)
            self._layout.addWidget(chip)
        self._layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_external_bonuses()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _toggle_external_bonuses(self) -> None:
        self.external_bonuses_toggled.emit(not self._external_bonuses_enabled)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_external_bonuses()
                return True
        return super().eventFilter(watched, event)


class BonusSourceChipWidget(QFrame):
    def __init__(
        self,
        item: RightPanelBonusSourceDisplayItem,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("BonusSourceChip")
        self.setProperty("disabled", not item.applied)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 2, 5, 2)
        layout.setSpacing(4)

        icon = QLabel(item.label[:3].upper() if item.label else "BON")
        icon.setObjectName("BonusSourceIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(20, 20)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        pixmap = _fit_pixmap(item.icon_path, QSize(20, 20)) if item.icon_path else None
        if pixmap is not None:
            icon.setText("")
            icon.setPixmap(pixmap)
        layout.addWidget(icon)

        effects = QLabel(" · ".join(item.short_effects) if item.short_effects else item.label)
        effects.setObjectName("BonusSourceEffects")
        effects.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(effects)

        tooltip = _bonus_source_tooltip_html(item)
        if tooltip:
            install_custom_tooltip(self, tooltip)


def _bonus_source_tooltip_html(item: RightPanelBonusSourceDisplayItem) -> str:
    rows: list[str] = []
    title = html.escape(item.tooltip_title or item.label)
    if title:
        rows.append(f"<b>{title}</b>")
    if item.short_effects and item.source_kind != "weapon_passive_static":
        rows.append(html.escape(", ".join(item.short_effects)))
    if not item.applied and item.not_applied_reason:
        rows.append(
            f"<span style='color:#f09c9c;'>{html.escape(item.not_applied_reason)}</span>"
        )
    if item.tooltip_body:
        rows.append(html.escape(item.tooltip_body).replace("\n", "<br>"))
    return "<br>".join(rows)


class ActionBarPrototypeWidget(QFrame):
    def __init__(
        self,
        labels: tuple[str, ...],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ActionBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.set_labels(labels)

    def set_labels(self, labels: tuple[str, ...]) -> None:
        _clear_layout(self._layout)
        standard_icons = [
            QStyle.StandardPixmap.SP_BrowserReload,
            QStyle.StandardPixmap.SP_DialogSaveButton,
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
        ]
        style = QApplication.style()
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("ActionButton")
            if index < len(standard_icons):
                button.setIcon(style.standardIcon(standard_icons[index]))
            self._layout.addWidget(button)


def _detail_row_layout(
    row: RightPanelDetailRowViewModel,
    *,
    metric: bool,
) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(7)

    icon = QLabel(row.icon_label or row.label[:2].upper())
    icon.setObjectName("MetricIcon" if metric else "StatIcon")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setFixedSize(40, 24)
    layout.addWidget(icon)

    value = QLabel(row.value)
    value.setObjectName("MetricValue" if metric else "StatValue")
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(value, 1)
    return layout


def _character_chips(details: RightPanelSelectedDetailsViewModel) -> list[str]:
    chips: list[str] = []
    if details.constellation is not None:
        chips.append(f"C{details.constellation}")
    if details.character_level is not None:
        chips.append(f"Lv.{details.character_level}")
    if details.element:
        chips.append(details.element.upper())
    return chips


def _build_mini_set_stack_pixmap(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> QPixmap | None:
    active_sets = tuple(active_sets[:2])
    if not active_sets:
        return None

    icons = [
        _build_mini_set_icon_pixmap(item.icon_path)
        for item in active_sets
        if item.icon_path
    ]
    if len(active_sets) == 2 and len(icons) == 2:
        composite = make_diagonal_split_pixmap(
            icons[0],
            icons[1],
            width=SLOT_EQUIP_ICON_SIZE,
            height=SLOT_EQUIP_ICON_SIZE,
            feather=SLOT_BUILD_BONUS_FEATHER,
        )
        return draw_count_badge(composite, "2")

    if len(active_sets) == 1 and len(icons) == 1:
        count = active_sets[0].piece_count
        badge = str(count) if count in (2, 4) else ""
        return draw_count_badge(icons[0], badge) if badge else icons[0]

    return None


def _build_mini_set_icon_pixmap(path: str) -> QPixmap | None:
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return scale_trimmed_pixmap_to_size(
        pixmap,
        SLOT_EQUIP_ICON_SIZE,
        SLOT_EQUIP_ICON_SIZE,
        padding=1,
        alpha_threshold=16,
    )


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


def _fit_pixmap(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    key = (str(path), int(size.width()), int(size.height()))
    if key in _FIT_PIXMAP_CACHE:
        cached = _FIT_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    source = QPixmap(path)
    if source.isNull():
        _FIT_PIXMAP_CACHE[key] = None
        return None

    scaled = source.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    canvas = QPixmap(size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    x = max(0, (size.width() - scaled.width()) // 2)
    y = max(0, (size.height() - scaled.height()) // 2)
    painter.drawPixmap(x, y, scaled)
    painter.end()
    _FIT_PIXMAP_CACHE[key] = QPixmap(canvas)
    return canvas


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _stylesheet() -> str:
    return """
    #RightPanelPrototypeContent {
        background: #17191d;
        color: #edf0f2;
        font-size: 12px;
    }
    #ModeTabButton {
        min-height: 30px;
        border: 1px solid #3a3f49;
        border-radius: 6px;
        background: #22262d;
        color: #ccd3d9;
        font-weight: 600;
    }
    #ModeTabButton:checked {
        background: #d7b461;
        color: #17191d;
        border-color: #f1d486;
    }
    #TeamSlotRow, #InfoBlock, #DetailsBlock {
        border: 1px solid #363b43;
        border-radius: 8px;
        background: #202329;
    }
    #SectionTitle {
        color: #f1d486;
        font-weight: 800;
        font-size: 13px;
    }
    #SlotCard, #SlotCardSelected {
        border: 1px solid #3f4652;
        border-radius: 7px;
        background: #292e37;
    }
    #SlotCardSelected {
        border: 2px solid #d7b461;
        background: #303743;
    }
    #PortraitBox, #PortraitBoxEmpty {
        border-radius: 6px;
        border: 1px solid #52606d;
        background: #516679;
        color: #ffffff;
        font-size: 23px;
        font-weight: 900;
    }
    #PortraitBoxEmpty {
        background: #2b3037;
        color: #8b939c;
        border-style: dashed;
    }
    #MiniEquipBox, #MiniEquipBoxMissing {
        border-radius: 5px;
        border: 1px solid #626b78;
        background: #343a44;
        color: #edf2f5;
        font-size: 10px;
        font-weight: 800;
    }
    #MiniEquipBoxMissing {
        border-color: #b9825f;
        background: #4a382f;
        color: #ffd2ad;
    }
    #DetailsWeaponIcon {
        border-radius: 5px;
        border: 1px solid #626b78;
        background: #343a44;
        color: #edf2f5;
        font-size: 10px;
        font-weight: 800;
    }
    #MetaSummaryBox {
        border-radius: 5px;
        border: 1px solid #303741;
        background: #15181d;
    }
    #SlotName {
        color: #f8f3e7;
        font-weight: 800;
    }
    #StatBadge {
        min-height: 20px;
        border-radius: 4px;
        background: #111316;
        color: #e1e8ec;
        font-size: 9px;
        font-weight: 800;
        padding: 0px 1px;
    }
    #WarningBadge {
        min-height: 22px;
        border-radius: 4px;
        background: #8b3434;
        color: #fff3ef;
        font-size: 10px;
        font-weight: 900;
        padding: 0px 1px;
    }
    #TableHeader {
        color: #98c9bf;
        font-size: 10px;
        font-weight: 800;
    }
    #TableCell, #TableCellPrimary {
        min-height: 23px;
        border-radius: 4px;
        background: #15181d;
        color: #dce3e7;
        padding: 2px 5px;
        font-family: Consolas, "Courier New", monospace;
    }
    #TableCellPrimary {
        color: #f1d486;
        font-weight: 800;
        font-family: Arial, sans-serif;
    }
    #SummaryLine, #DetailsName {
        color: #ffffff;
        font-weight: 900;
    }
    #GhostButton, #ActionButton {
        border: 1px solid #4d5662;
        border-radius: 6px;
        background: #2d343d;
        color: #eef2f5;
        padding: 7px 10px;
        font-weight: 800;
    }
    #GhostButton:disabled {
        color: #9ca6ad;
        background: #242a31;
    }
    #SubtleText {
        color: #c7cdd2;
    }
    #StatsPanel, #MetaPanel {
        border: 1px solid #333941;
        border-radius: 6px;
        background: #181b20;
    }
    #MetricIcon, #StatIcon {
        border-radius: 4px;
        color: #111316;
        font-size: 10px;
        font-weight: 900;
    }
    #MetricIcon {
        background: #d7b461;
    }
    #StatIcon {
        background: #98c9bf;
    }
    #MetricValue, #StatValue {
        color: #edf2f5;
        font-weight: 800;
    }
    #MetaChip {
        border-radius: 4px;
        background: #314236;
        color: #d9f0df;
        font-size: 10px;
        font-weight: 900;
        padding: 3px 6px;
    }
    #MetaLabel {
        color: #98a7b1;
        font-size: 10px;
        font-weight: 700;
    }
    #MetaValue {
        color: #e6ecef;
        font-weight: 700;
    }
    #MetaValueStrong {
        color: #ffffff;
        font-weight: 900;
    }
    #SetsLine {
        border-radius: 5px;
        background: #111316;
        color: #f4ddb0;
        padding: 7px 8px;
        font-weight: 800;
    }
    #BonusSourceStrip {
        min-height: 28px;
        border-radius: 5px;
        border: 1px solid #3f4652;
        background: #111316;
        padding: 1px 3px;
    }
    #BonusSourceStrip[active="true"] {
        border-color: #d7b461;
        background: #15181d;
    }
    #BonusSourceStrip[active="false"] {
        border-color: #2d333b;
        background: #101216;
    }
    #BonusSourceScroll {
        background: transparent;
    }
    #BonusSourceChip {
        border: 1px solid #3f4652;
        border-radius: 5px;
        background: #222832;
    }
    #BonusSourceChip[disabled="true"] {
        border-color: #30343b;
        background: #191c21;
    }
    #BonusSourceChip[disabled="true"] #BonusSourceEffects {
        color: #8f99a4;
    }
    #BonusSourceIcon {
        border-radius: 4px;
        background: #303743;
        color: #f4ddb0;
        font-size: 9px;
        font-weight: 900;
    }
    #BonusSourceEffects {
        color: #f4ddb0;
        font-size: 10px;
        font-weight: 900;
    }
    #BonusStripEmpty {
        color: #8f99a4;
        font-size: 11px;
        font-weight: 700;
        padding: 4px 8px;
    }
    #ActionBar {
        background: transparent;
    }
    """
