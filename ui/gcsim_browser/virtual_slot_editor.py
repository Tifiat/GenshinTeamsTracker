from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualArtifactSetChoice,
    GcsimVirtualRosterCatalog,
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
    max_virtual_promote_level,
)
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_STATE_DANGER, UI_STATE_SUCCESS, UI_TEXT_MUTED


_POPUP_STYLE = """
QWidget#VirtualGcsimPopup {
    background: #24262a;
    border: 1px solid #555b66;
}
QPushButton[compact="true"] { min-height: 22px; padding: 1px 5px; }
QLabel[muted="true"] { color: #9da3ad; }
"""


class VirtualGcsimProfilePopup(QWidget):
    profile_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("VirtualGcsimPopup")
        self.setStyleSheet(_POPUP_STYLE)
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)
        root.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 700;")
        header.addWidget(self.title_label, 1)
        close_button = QPushButton("×")
        close_button.setProperty("compact", True)
        close_button.setFixedWidth(26)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        self.talent_normal_spin = _optional_spin(15)
        self.talent_skill_spin = _optional_spin(15)
        self.talent_burst_spin = _optional_spin(15)
        self.weapon_ascension_combo = _ascension_combo()
        self.talents_label = QLabel()
        self.weapon_label = QLabel()
        grid.addWidget(self.talents_label, 0, 0)
        talents = QHBoxLayout()
        talents.setContentsMargins(0, 0, 0, 0)
        talents.setSpacing(4)
        for prefix, spin in (
            ("N", self.talent_normal_spin),
            ("E", self.talent_skill_spin),
            ("Q", self.talent_burst_spin),
        ):
            label = QLabel(prefix)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            talents.addWidget(label)
            talents.addWidget(spin)
        grid.addLayout(talents, 0, 1, 1, 2)
        grid.addWidget(self.weapon_label, 1, 0)
        grid.addWidget(self.weapon_ascension_combo, 1, 1, 1, 2)
        root.addLayout(grid)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        for control in (
            self.talent_normal_spin,
            self.talent_skill_spin,
            self.talent_burst_spin,
            self.weapon_ascension_combo,
        ):
            if isinstance(control, QSpinBox):
                control.valueChanged.connect(self._emit_profile)
            else:
                control.currentIndexChanged.connect(self._emit_profile)
        self.retranslate_ui()

    def set_override(self, override: GcsimVirtualSlotOverride | None) -> None:
        self._syncing = True
        try:
            self.talent_normal_spin.setValue((override.talent_normal or 0) if override else 0)
            self.talent_skill_spin.setValue((override.talent_skill or 0) if override else 0)
            self.talent_burst_spin.setValue((override.talent_burst or 0) if override else 0)
            _select_data(
                self.weapon_ascension_combo,
                override.weapon_promote_level if override else None,
            )
            missing = override.missing_core_profile_fields if override else ()
            self.status_label.setText(
                tr("gcsim.virtual_editor.profile_incomplete")
                if missing
                else tr("gcsim.virtual_editor.profile_complete")
            )
            self.status_label.setStyleSheet(
                f"color: {UI_STATE_DANGER};" if missing else f"color: {UI_STATE_SUCCESS};"
            )
        finally:
            self._syncing = False

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("gcsim.virtual_editor.profile"))
        self.talents_label.setText(tr("gcsim.virtual_editor.talents_short"))
        self.weapon_label.setText(tr("gcsim.virtual_editor.weapon_ascension_short"))

    def _emit_profile(self, *_args: object) -> None:
        if self._syncing:
            return
        self.profile_requested.emit(
            {
                "talent_normal": _optional_spin_value(self.talent_normal_spin),
                "talent_skill": _optional_spin_value(self.talent_skill_spin),
                "talent_burst": _optional_spin_value(self.talent_burst_spin),
                "weapon_promote_level": self.weapon_ascension_combo.currentData(),
            }
        )


class _SetBonusRow(QPushButton):
    requested = Signal(str)

    def __init__(self, choice: GcsimVirtualArtifactSetChoice) -> None:
        super().__init__()
        self.choice = choice
        self.setProperty("compact", True)
        if choice.icon_path and Path(choice.icon_path).is_file():
            self.setIcon(QIcon(choice.icon_path))
            self.setIconSize(QSize(22, 22))
        self.clicked.connect(lambda _checked=False: self.requested.emit(choice.set_uid))
        self.set_piece_count(0)

    def set_piece_count(self, count: int) -> None:
        suffix = "—" if count <= 0 else f"{count}p"
        self.setText(f"{self.choice.display_name}  ·  {suffix}")
        self.setProperty("selected", count > 0)
        self.style().unpolish(self)
        self.style().polish(self)


class VirtualGcsimBuildPopup(QWidget):
    build_requested = Signal(dict)
    set_bonuses_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("VirtualGcsimPopup")
        self.setStyleSheet(_POPUP_STYLE)
        self.setMinimumWidth(390)
        self.resize(430, 470)
        self._syncing = False
        self._choices: dict[str, GcsimVirtualArtifactSetChoice] = {}
        self._rows: dict[str, _SetBonusRow] = {}
        self._selected: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)
        root.setSpacing(6)
        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 700;")
        header.addWidget(self.title_label, 1)
        close_button = QPushButton("×")
        close_button.setProperty("compact", True)
        close_button.setFixedWidth(26)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        self.saved_build_label = QLabel()
        root.addWidget(self.saved_build_label)
        self.saved_build_combo = _search_combo()
        self.saved_build_combo.currentIndexChanged.connect(self._build_changed)
        root.addWidget(self.saved_build_combo)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)
        self.set_bonus_label = QLabel()
        root.addWidget(self.set_bonus_label)
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._filter_rows)
        root.addWidget(self.search_edit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(3)
        self.rows_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.rule_label = QLabel()
        self.rule_label.setWordWrap(True)
        self.rule_label.setProperty("muted", True)
        root.addWidget(self.rule_label)
        self.retranslate_ui()

    def set_context(
        self,
        *,
        override: GcsimVirtualSlotOverride | None,
        artifact_builds: Iterable[Mapping[str, object]],
        set_choices: Iterable[GcsimVirtualArtifactSetChoice],
    ) -> None:
        self._syncing = True
        try:
            self.saved_build_combo.clear()
            self.saved_build_combo.addItem(tr("gcsim.virtual_editor.no_saved_build"), None)
            for item in artifact_builds:
                build_id = int(item.get("id") or 0)
                if build_id <= 0:
                    continue
                self.saved_build_combo.addItem(str(item.get("name") or build_id), build_id)
            _select_data(
                self.saved_build_combo,
                override.artifact_build_id if override else None,
            )
            self._replace_set_rows(tuple(set_choices))
            self._selected = {
                item.set_uid: int(item.piece_count)
                for item in (override.artifact_set_bonuses if override else ())
            }
            self._refresh_rows()
        finally:
            self._syncing = False

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("gcsim.virtual_editor.build"))
        self.saved_build_label.setText(tr("gcsim.virtual_editor.saved_stats_build"))
        self.set_bonus_label.setText(tr("gcsim.virtual_editor.set_bonuses"))
        self.search_edit.setPlaceholderText(tr("gcsim.virtual_editor.search_sets"))
        self.rule_label.setText(tr("gcsim.virtual_editor.set_rule"))

    def _replace_set_rows(
        self,
        choices: tuple[GcsimVirtualArtifactSetChoice, ...],
    ) -> None:
        for row in self._rows.values():
            row.deleteLater()
        self._rows.clear()
        self._choices = {item.set_uid: item for item in choices}
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for choice in choices:
            row = _SetBonusRow(choice)
            row.requested.connect(self._cycle_set)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self._rows[choice.set_uid] = row

    def _cycle_set(self, set_uid: str) -> None:
        choice = self._choices.get(set_uid)
        if choice is None:
            return
        current = self._selected.get(set_uid, 0)
        complete = 4 in self._selected.values() or len(self._selected) >= 2
        if current == 4:
            self._selected.pop(set_uid, None)
        elif current == 2:
            if len(self._selected) == 1 and choice.four_piece_available:
                self._selected[set_uid] = 4
            else:
                self._selected.pop(set_uid, None)
        elif not complete:
            self._selected[set_uid] = 2
        self._refresh_rows()
        self._emit_sets()

    def _refresh_rows(self) -> None:
        for set_uid, row in self._rows.items():
            row.set_piece_count(self._selected.get(set_uid, 0))

    def _filter_rows(self, text: str) -> None:
        needle = str(text or "").strip().casefold()
        for choice in self._choices.values():
            self._rows[choice.set_uid].setVisible(
                not needle or needle in choice.display_name.casefold()
            )

    def _build_changed(self, _index: int) -> None:
        if self._syncing:
            return
        build_id = int(self.saved_build_combo.currentData() or 0)
        self.build_requested.emit(
            {
                "artifact_build_id": build_id or None,
                "artifact_build_name": self.saved_build_combo.currentText().strip()
                if build_id
                else "",
            }
        )

    def _emit_sets(self) -> None:
        payload: list[dict[str, object]] = []
        for set_uid in sorted(self._selected, key=str.casefold):
            choice = self._choices[set_uid]
            payload.append(
                GcsimVirtualSetBonus(
                    set_uid=choice.set_uid,
                    display_name=choice.display_name,
                    gcsim_key=choice.gcsim_key,
                    piece_count=self._selected[set_uid],
                ).to_dict()
            )
        self.set_bonuses_requested.emit(payload)


class VirtualGcsimCardEditor(QWidget):
    character_requested = Signal(str)
    weapon_requested = Signal(str)
    constellation_requested = Signal(int)
    refinement_requested = Signal(int)
    profile_requested = Signal(dict)
    set_bonuses_requested = Signal(list)
    clear_requested = Signal()
    editing_cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog = GcsimVirtualRosterCatalog.empty()
        self._set_choices: tuple[GcsimVirtualArtifactSetChoice, ...] = ()
        self._override: GcsimVirtualSlotOverride | None = None
        self._artifact_builds: tuple[dict[str, object], ...] = ()
        self._syncing = False
        self._character_tooltips: dict[str, str] = {}
        self._weapon_tooltips: dict[str, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        first = QHBoxLayout()
        first.setContentsMargins(0, 0, 0, 0)
        first.setSpacing(4)
        self.character_icon = _compact_icon_label()
        self.character_combo = _search_combo()
        self.character_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.constellation_button = QPushButton("C0")
        self.constellation_button.setProperty("compact", True)
        self.constellation_button.setFixedWidth(36)
        self.character_level_spin = _optional_spin(90)
        self.character_level_spin.setPrefix("Lv ")
        self.character_level_spin.setFixedWidth(62)
        first.addWidget(self.character_icon)
        first.addWidget(self.character_combo, 1)
        first.addWidget(self.constellation_button)
        first.addWidget(self.character_level_spin)
        root.addLayout(first)

        second = QHBoxLayout()
        second.setContentsMargins(0, 0, 0, 0)
        second.setSpacing(4)
        self.weapon_icon = _compact_icon_label()
        self.weapon_combo = _search_combo()
        self.weapon_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refinement_button = QPushButton("R1")
        self.refinement_button.setProperty("compact", True)
        self.refinement_button.setFixedWidth(36)
        self.weapon_level_spin = _optional_spin(90)
        self.weapon_level_spin.setPrefix("Lv ")
        self.weapon_level_spin.setFixedWidth(62)
        second.addWidget(self.weapon_icon)
        second.addWidget(self.weapon_combo, 1)
        second.addWidget(self.refinement_button)
        second.addWidget(self.weapon_level_spin)
        root.addLayout(second)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.profile_button = QPushButton()
        self.build_button = QPushButton()
        self.build_summary_label = QLabel("—")
        self.build_summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.status_label = QLabel("!")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedWidth(16)
        self.clear_button = QPushButton("×")
        for button in (self.profile_button, self.build_button, self.clear_button):
            button.setProperty("compact", True)
        self.clear_button.setFixedWidth(26)
        actions.addWidget(self.profile_button)
        actions.addWidget(self.build_button)
        actions.addWidget(self.build_summary_label, 1)
        actions.addWidget(self.status_label)
        actions.addWidget(self.clear_button)
        root.addLayout(actions)

        self.profile_popup = VirtualGcsimProfilePopup(self)
        self.build_popup = VirtualGcsimBuildPopup(self)
        self.character_combo.currentIndexChanged.connect(self._character_changed)
        self.weapon_combo.currentIndexChanged.connect(self._weapon_changed)
        self.constellation_button.clicked.connect(self._cycle_constellation)
        self.character_level_spin.valueChanged.connect(self._character_level_changed)
        self.refinement_button.clicked.connect(self._cycle_refinement)
        self.weapon_level_spin.valueChanged.connect(self._weapon_level_changed)
        self.profile_button.clicked.connect(
            lambda _checked=False: _show_popup(self.profile_popup, self.profile_button)
        )
        self.build_button.clicked.connect(
            lambda _checked=False: _show_popup(self.build_popup, self.build_button)
        )
        self.clear_button.clicked.connect(self._clear_or_cancel)
        self.profile_popup.profile_requested.connect(self.profile_requested.emit)
        self.build_popup.build_requested.connect(self.profile_requested.emit)
        self.build_popup.set_bonuses_requested.connect(self.set_bonuses_requested.emit)
        install_custom_tooltip(
            self.character_combo,
            lambda: self._character_tooltips.get(
                str(self.character_combo.currentData() or ""), ""
            ),
        )
        install_custom_tooltip(
            self.weapon_combo,
            lambda: self._weapon_tooltips.get(
                str(self.weapon_combo.currentData() or ""), ""
            ),
        )
        install_custom_tooltip(
            self.profile_button,
            lambda: tr("gcsim.virtual_editor.profile"),
        )
        install_custom_tooltip(
            self.status_label,
            lambda: str(self.status_label.property("statusText") or ""),
        )
        self.retranslate_ui()

    def set_catalogs(
        self,
        catalog: GcsimVirtualRosterCatalog,
        set_choices: tuple[GcsimVirtualArtifactSetChoice, ...],
    ) -> None:
        self._catalog = catalog
        self._set_choices = tuple(set_choices)
        self._syncing = True
        try:
            self.character_combo.clear()
            self.character_combo.addItem("", "")
            self._character_tooltips.clear()
            for item in catalog.characters:
                self.character_combo.addItem(item.display_name, item.gcsim_key)
                self._character_tooltips[item.gcsim_key] = (
                    f"{item.display_name}\nGCSIM: {item.gcsim_key}\n{item.weapon_type}"
                )
        finally:
            self._syncing = False

    def set_context(
        self,
        *,
        override: GcsimVirtualSlotOverride | None,
        artifact_builds: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._override = override
        self._artifact_builds = tuple(dict(item) for item in artifact_builds)
        self._syncing = True
        try:
            _select_data(self.character_combo, override.character_key if override else "")
            self.constellation_button.setText(f"C{override.constellation if override else 0}")
            self.character_level_spin.setValue((override.character_level or 0) if override else 0)
            _set_compact_icon(
                self.character_icon,
                override.character_icon_path if override else "",
            )
            self._populate_weapons(override)
            self.refinement_button.setText(f"R{override.refinement if override else 1}")
            self.weapon_level_spin.setValue((override.weapon_level or 0) if override else 0)
            _set_compact_icon(
                self.weapon_icon,
                override.weapon_icon_path if override else "",
            )
            self.weapon_combo.setEnabled(override is not None)
            self.constellation_button.setEnabled(override is not None)
            self.character_level_spin.setEnabled(override is not None)
            self.refinement_button.setEnabled(override is not None and bool(override.weapon_key))
            self.weapon_level_spin.setEnabled(override is not None and bool(override.weapon_key))
            self.profile_button.setEnabled(override is not None)
            self.build_button.setEnabled(override is not None)
            self.profile_popup.set_override(override)
            self.build_popup.set_context(
                override=override,
                artifact_builds=self._artifact_builds,
                set_choices=self._set_choices,
            )
            self._refresh_summary()
        finally:
            self._syncing = False

    def begin_editing(self) -> None:
        self.character_combo.setFocus(Qt.FocusReason.OtherFocusReason)
        self.character_combo.showPopup()

    def retranslate_ui(self) -> None:
        self.character_combo.setPlaceholderText(tr("gcsim.virtual_editor.character"))
        self.weapon_combo.setPlaceholderText(tr("gcsim.virtual_editor.weapon"))
        self.profile_button.setText("…")
        self.profile_button.setAccessibleName(tr("gcsim.virtual_editor.profile"))
        self.build_button.setText(tr("gcsim.virtual_editor.build"))
        self.profile_popup.retranslate_ui()
        self.build_popup.retranslate_ui()

    def _populate_weapons(self, override: GcsimVirtualSlotOverride | None) -> None:
        self.weapon_combo.clear()
        self.weapon_combo.addItem("", "")
        self._weapon_tooltips.clear()
        if override is None:
            return
        for item in self._catalog.weapons:
            if item.weapon_type != override.character_weapon_type:
                continue
            self.weapon_combo.addItem(item.display_name, item.gcsim_key)
            self._weapon_tooltips[item.gcsim_key] = (
                f"{item.display_name}\nGCSIM: {item.gcsim_key}\n{item.weapon_type}"
            )
        _select_data(self.weapon_combo, override.weapon_key)

    def _character_changed(self, _index: int) -> None:
        if self._syncing:
            return
        key = str(self.character_combo.currentData() or "")
        if key:
            self.character_requested.emit(key)

    def _weapon_changed(self, _index: int) -> None:
        if not self._syncing:
            self.weapon_requested.emit(str(self.weapon_combo.currentData() or ""))

    def _cycle_constellation(self) -> None:
        if self._override is not None:
            self.constellation_requested.emit((self._override.constellation + 1) % 7)

    def _cycle_refinement(self) -> None:
        if self._override is not None and self._override.weapon_key:
            self.refinement_requested.emit((self._override.refinement % 5) + 1)

    def _character_level_changed(self, value: int) -> None:
        if self._syncing:
            return
        level = int(value) if value > 0 else None
        payload: dict[str, object] = {"character_level": level}
        if level is not None:
            payload["character_promote_level"] = max_virtual_promote_level(level)
        self.profile_requested.emit(payload)

    def _weapon_level_changed(self, value: int) -> None:
        if not self._syncing:
            self.profile_requested.emit({"weapon_level": int(value) if value > 0 else None})

    def _clear_or_cancel(self) -> None:
        if self._override is None:
            self.editing_cancelled.emit()
        else:
            self.clear_requested.emit()

    def _refresh_summary(self) -> None:
        override = self._override
        if override is None:
            text = tr("gcsim.virtual_editor.choose_character")
            self.build_summary_label.setText("—")
            self.status_label.setText("!")
            self.status_label.setProperty("statusText", text)
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        if override.missing_core_profile_fields:
            text = tr("gcsim.virtual_editor.card_profile_incomplete")
            color = UI_STATE_DANGER
        elif override.artifact_build_id is None:
            text = tr("gcsim.virtual_editor.card_theory_ready")
            color = UI_STATE_SUCCESS
        else:
            text = tr("gcsim.virtual_editor.card_ready")
            color = UI_STATE_SUCCESS
        if override.artifact_build_name:
            build_summary = override.artifact_build_name
        elif override.artifact_set_bonuses:
            build_summary = " + ".join(
                f"{item.display_name} {item.piece_count}p"
                for item in override.artifact_set_bonuses
            )
        else:
            build_summary = "—"
        self.build_summary_label.setText(build_summary)
        self.status_label.setText("✓" if color == UI_STATE_SUCCESS else "!")
        self.status_label.setProperty("statusText", text)
        self.status_label.setStyleSheet(f"color: {color};")


def _search_combo() -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    completer = combo.completer()
    if completer is not None:
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    return combo


def _optional_spin(maximum: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, int(maximum))
    spin.setSpecialValueText("—")
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return spin


def _optional_spin_value(spin: QSpinBox) -> int | None:
    value = int(spin.value())
    return value if value > 0 else None


def _compact_icon_label() -> QLabel:
    label = QLabel("?")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(22, 22)
    label.setStyleSheet("border: 1px solid #555b66; border-radius: 3px;")
    return label


def _set_compact_icon(label: QLabel, path: str) -> None:
    image_path = Path(str(path or ""))
    if image_path.is_file():
        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            label.setText("")
            label.setPixmap(
                pixmap.scaled(
                    20,
                    20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return
    label.setPixmap(QPixmap())
    label.setText("?")


def _ascension_combo() -> QComboBox:
    combo = QComboBox()
    combo.addItem("—", None)
    for phase in range(7):
        combo.addItem(f"A{phase}", phase)
    return combo


def _select_data(combo: QComboBox, value: object) -> None:
    index = combo.findData(value)
    combo.setCurrentIndex(max(0, index))


def _show_popup(popup: QWidget, anchor: QWidget) -> None:
    popup.adjustSize()
    origin = anchor.mapToGlobal(anchor.rect().bottomLeft())
    screen = anchor.screen()
    available = screen.availableGeometry() if screen is not None else None
    x, y = origin.x(), origin.y() + 2
    if available is not None:
        x = max(available.left(), min(x, available.right() - popup.width()))
        if y + popup.height() > available.bottom():
            y = max(available.top(), anchor.mapToGlobal(anchor.rect().topLeft()).y() - popup.height() - 2)
    popup.move(x, y)
    popup.show()
    popup.raise_()


__all__ = [
    "VirtualGcsimBuildPopup",
    "VirtualGcsimCardEditor",
    "VirtualGcsimProfilePopup",
]
