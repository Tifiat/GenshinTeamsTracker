from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS, MODE_DPS_DUMMY


DEFAULT_ROTATION_CODE = """options swap_delay=12 iteration=1000;
energy every interval=480,720 amount=1;
target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=999999999;

active furina;

for let i=0; i<4; i=i+1 {
  if is_even(i) {
    furina skill, dash, burst;
  }
  ororon burst, skill;
  bennett skill, burst;
  chasca skill;
  chasca aim:4;
  chasca aim[bullets=4];
  if is_even(i) {
    chasca burst;
  }
}
wait(82);
"""


@dataclass(frozen=True, slots=True)
class GcsimBrowserTeamSlotPreview:
    name: str = ""
    weapon: str = ""
    sets: str = ""
    status: str = ""


class GcsimBrowserWorkspace(QWidget):
    prepare_requested = Signal(int, str)
    run_selected_requested = Signal(int, int, str)
    run_all_requested = Signal(int, str)
    rotation_text_changed = Signal()

    """First visual shell for the future GCSIM Browser.

    This widget owns only the local editor/preview UI. AppShell wires backend
    prepare/run workers and decides whether successful results are persisted.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: str = MODE_ABYSS,
    ) -> None:
        super().__init__(parent)
        self._mode = mode if mode in {MODE_ABYSS, MODE_DPS_DUMMY} else MODE_ABYSS
        self._selected_chamber_index = 0
        self._target_mode_preview = ""
        self._targets_preview_by_team: tuple[tuple[str, ...], ...] = ((), ())
        self._team_previews: list[list[GcsimBrowserTeamSlotPreview]] = [
            [GcsimBrowserTeamSlotPreview() for _ in range(4)],
            [GcsimBrowserTeamSlotPreview() for _ in range(4)],
        ]
        self._team_cards: list[list[_TeamCard]] = []
        self._team_notes: list[QLabel] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("GcsimBrowserTitle")
        header.addWidget(self.title_label, 1)
        self.status_label = QLabel()
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(self.status_label, 0)
        layout.addLayout(header)

        self.team_tabs = QTabWidget()
        self.team_tabs.setDocumentMode(True)
        self.team_tab_widgets: list[QWidget] = [
            self._make_team_tab(0),
            self._make_team_tab(1),
        ]
        self.team_tabs.addTab(self.team_tab_widgets[0], "")
        self.team_tabs.addTab(self.team_tab_widgets[1], "")
        self.team_tabs.currentChanged.connect(self._refresh_targets_preview)
        layout.addWidget(self.team_tabs)

        self.targets_section, targets_layout = _make_section()
        self.targets_title = QLabel()
        self.targets_title.setObjectName("GcsimBrowserSectionTitle")
        targets_layout.addWidget(self.targets_title)

        chamber_row = QHBoxLayout()
        chamber_row.setContentsMargins(0, 0, 0, 0)
        chamber_row.setSpacing(6)
        self.chamber_buttons: list[QPushButton] = []
        for _index in range(3):
            button = QPushButton()
            chamber_index = _index
            button.setCheckable(True)
            button.setEnabled(True)
            button.setChecked(chamber_index == 0)
            button.clicked.connect(
                lambda _checked=False, value=chamber_index: self._select_chamber(value)
            )
            self.chamber_buttons.append(button)
            chamber_row.addWidget(button)
        chamber_row.addStretch(1)
        self.target_mode_label = QLabel()
        chamber_row.addWidget(self.target_mode_label)
        targets_layout.addLayout(chamber_row)

        self.targets_placeholder = QLabel()
        self.targets_placeholder.setWordWrap(True)
        self.targets_placeholder.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        targets_layout.addWidget(self.targets_placeholder)
        layout.addWidget(self.targets_section)

        self.defaults_section, defaults_layout = _make_section()
        self.defaults_title = QLabel()
        self.defaults_title.setObjectName("GcsimBrowserSectionTitle")
        defaults_layout.addWidget(self.defaults_title)
        self.defaults_label = QLabel()
        self.defaults_label.setWordWrap(True)
        defaults_layout.addWidget(self.defaults_label)
        layout.addWidget(self.defaults_section)

        self.rotation_section, rotation_layout = _make_section()
        self.rotation_title = QLabel()
        self.rotation_title.setObjectName("GcsimBrowserSectionTitle")
        rotation_layout.addWidget(self.rotation_title)
        self.rotation_editor = QPlainTextEdit()
        self.rotation_editor.setPlainText(DEFAULT_ROTATION_CODE)
        self.rotation_editor.textChanged.connect(self.rotation_text_changed.emit)
        self.rotation_editor.setMinimumHeight(180)
        rotation_layout.addWidget(self.rotation_editor)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.prepare_button = QPushButton()
        self.prepare_button.setEnabled(True)
        self.prepare_button.clicked.connect(self._request_prepare_config)
        self.run_selected_button = QPushButton()
        self.run_selected_button.setEnabled(True)
        self.run_selected_button.clicked.connect(self._request_run_selected_chamber)
        self.run_all_button = QPushButton()
        self.run_all_button.setEnabled(True)
        self.run_all_button.clicked.connect(self._request_run_all_chambers)
        actions.addWidget(self.prepare_button)
        actions.addWidget(self.run_selected_button)
        actions.addWidget(self.run_all_button)
        actions.addStretch(1)
        rotation_layout.addLayout(actions)
        layout.addWidget(self.rotation_section)

        self.results_section, results_layout = _make_section()
        self.results_title = QLabel()
        self.results_title.setObjectName("GcsimBrowserSectionTitle")
        results_layout.addWidget(self.results_title)
        self.results_placeholder = QLabel()
        self.results_placeholder.setWordWrap(True)
        self.results_placeholder.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        results_layout.addWidget(self.results_placeholder)
        layout.addWidget(self.results_section)

        layout.addStretch(1)
        self.retranslate_ui()

    def set_mode(self, mode: str) -> None:
        normalized = mode if mode in {MODE_ABYSS, MODE_DPS_DUMMY} else MODE_ABYSS
        if normalized == self._mode:
            return
        self._mode = normalized
        self._update_mode_visibility()
        self.retranslate_ui()

    def set_team_preview(
        self,
        team_index: int,
        slots: list[GcsimBrowserTeamSlotPreview],
    ) -> None:
        if team_index < 0 or team_index >= len(self._team_cards):
            return
        normalized_slots = list(slots[:4])
        while len(normalized_slots) < 4:
            normalized_slots.append(GcsimBrowserTeamSlotPreview())
        self._team_previews[team_index] = normalized_slots
        for slot_index, card in enumerate(self._team_cards[team_index]):
            card.set_preview(normalized_slots[slot_index])

    def set_abyss_targets_preview(
        self,
        *,
        target_mode_label: str = "",
        preview_by_team: tuple[tuple[str, ...], ...] = ((), ()),
    ) -> None:
        self._target_mode_preview = target_mode_label
        self._targets_preview_by_team = preview_by_team
        self._refresh_targets_preview()

    def retranslate_ui(self) -> None:
        self.title_label.setText(_fallback("gcsim.browser.title", "GCSIM Browser"))
        self.status_label.setText(
            _fallback(
                "gcsim.browser.status_skeleton",
                "Selected-team backend",
            )
        )
        self.team_tabs.setTabText(0, _fallback("gcsim.browser.team_1", "Team 1"))
        self.team_tabs.setTabText(1, _fallback("gcsim.browser.team_2", "Team 2"))

        for note in self._team_notes:
            note.setText(
                _fallback(
                    "gcsim.browser.team_placeholder",
                    "Readiness uses current runtime team, weapon and artifact state.",
                )
            )
        for team_index, cards in enumerate(self._team_cards):
            for slot_index, card in enumerate(cards):
                card.set_preview(self._team_previews[team_index][slot_index])

        self.targets_title.setText(
            _fallback("gcsim.browser.targets", "Abyss targets")
        )
        self.target_mode_label.setText(
            self._target_mode_preview
            or
            _fallback(
                "gcsim.browser.target_mode_placeholder",
                "Target mode: follows right panel",
            )
        )
        for index, button in enumerate(self.chamber_buttons, start=1):
            button.setText(f"C{index}")
        self.targets_placeholder.setText(
            self._current_targets_preview_text()
        )

        self.defaults_title.setText(
            _fallback("gcsim.browser.defaults", "Run defaults")
        )
        self.defaults_label.setText(
            _fallback(
                "gcsim.browser.defaults_placeholder",
                "Iterations: from rotation code · Boosted energy: app setting",
            )
        )

        self.rotation_title.setText(
            _fallback("gcsim.browser.rotation", "Rotation code")
        )
        self.prepare_button.setText(
            _fallback("gcsim.browser.prepare", "Debug: prepare config")
        )
        self.run_selected_button.setText(
            _fallback("gcsim.browser.run_selected", "Run selected chamber")
        )
        if self._mode == MODE_DPS_DUMMY:
            self.run_selected_button.setText("Run DPS Dummy")
        self.run_all_button.setText(
            _fallback("gcsim.browser.run_all", "Run 3 chambers")
        )

        self.results_title.setText(_fallback("gcsim.browser.results", "Results"))
        self.results_placeholder.setText(
            _fallback(
                "gcsim.browser.results_placeholder",
                "Per-chamber clear time, DPS, warnings and generated config links will appear here.",
            )
        )
        self._update_mode_visibility()

    def _make_team_tab(self, team_index: int) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        cards: list[_TeamCard] = []
        for slot_index in range(4):
            card = _TeamCard()
            card.setObjectName(f"gcsimTeamCard{team_index}_{slot_index}")
            grid.addWidget(card, 0, slot_index)
            cards.append(card)
        self._team_cards.append(cards)
        layout.addWidget(grid_widget)

        note = QLabel()
        note.setWordWrap(True)
        self._team_notes.append(note)
        layout.addWidget(note)
        return tab

    def _update_mode_visibility(self) -> None:
        is_abyss = self._mode == MODE_ABYSS
        self.team_tabs.setTabVisible(1, is_abyss)
        self.targets_section.setVisible(is_abyss)
        self.run_all_button.setVisible(is_abyss)
        self.run_all_button.setEnabled(is_abyss and self.run_selected_button.isEnabled())

    def _select_chamber(self, chamber_index: int) -> None:
        self._selected_chamber_index = max(0, min(2, int(chamber_index)))
        for index, button in enumerate(self.chamber_buttons):
            button.setChecked(index == self._selected_chamber_index)
        self._refresh_targets_preview()

    def _refresh_targets_preview(self) -> None:
        if not hasattr(self, "targets_placeholder"):
            return
        self.targets_placeholder.setText(self._current_targets_preview_text())

    def _current_targets_preview_text(self) -> str:
        if self._mode != MODE_ABYSS:
            return _fallback(
                "gcsim.browser.targets_placeholder",
                "Chamber waves, enemy HP and resolved GCSIM target types will appear here.",
            )
        team_index = max(0, min(1, int(self.team_tabs.currentIndex())))
        team_rows = (
            self._targets_preview_by_team[team_index]
            if team_index < len(self._targets_preview_by_team)
            else ()
        )
        if self._selected_chamber_index < len(team_rows):
            text = team_rows[self._selected_chamber_index].strip()
            if text:
                return text
        return _fallback(
            "gcsim.browser.targets_placeholder",
            "Chamber waves, enemy HP and resolved GCSIM target types will appear here.",
        )

    def _request_prepare_config(self) -> None:
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        self.results_placeholder.setText(
            _fallback("gcsim.browser.prepare_requested", "Preparing config...")
        )
        self.prepare_requested.emit(team_index, self.rotation_editor.toPlainText())

    def _request_run_selected_chamber(self) -> None:
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        chamber = self._selected_chamber_index + 1
        self.results_placeholder.setText(
            _fallback("gcsim.browser.run_requested", "Running selected chamber...")
        )
        self.run_selected_requested.emit(
            team_index,
            chamber,
            self.rotation_editor.toPlainText(),
        )

    def _request_run_all_chambers(self) -> None:
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        self.results_placeholder.setText(
            _fallback("gcsim.browser.run_all_requested", "Running 3 chambers...")
        )
        self.run_all_requested.emit(team_index, self.rotation_editor.toPlainText())

    def set_actions_busy(self, busy: bool, *, message: str = "") -> None:
        self.prepare_button.setEnabled(not busy)
        self.run_selected_button.setEnabled(not busy)
        self.run_all_button.setEnabled(not busy and self._mode == MODE_ABYSS)
        if message:
            self.results_placeholder.setText(message)

    def set_prepare_result_text(self, text: str) -> None:
        self.results_placeholder.setText(
            text.strip()
            or _fallback("gcsim.browser.results_placeholder", "No prepare report.")
        )


class _TeamCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.name_label = QLabel()
        self.name_label.setObjectName("GcsimBrowserTeamName")
        self.weapon_label = QLabel()
        self.sets_label = QLabel()
        self.status_label = QLabel()

        for label in (
            self.name_label,
            self.weapon_label,
            self.sets_label,
            self.status_label,
        ):
            label.setWordWrap(True)
            layout.addWidget(label)

        self.set_preview(GcsimBrowserTeamSlotPreview())

    def set_preview(self, preview: GcsimBrowserTeamSlotPreview) -> None:
        self.name_label.setText(
            preview.name or _fallback("gcsim.browser.empty_slot", "Empty slot")
        )
        self.weapon_label.setText(
            preview.weapon
            or _fallback("gcsim.browser.weapon_pending", "Weapon: pending")
        )
        self.sets_label.setText(
            preview.sets or _fallback("gcsim.browser.sets_pending", "Build: pending")
        )
        self.status_label.setText(
            preview.status
            or _fallback("gcsim.browser.status_placeholder", "Not checked")
        )


def _make_section() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)
    return frame, layout


def _fallback(key: str, fallback: str) -> str:
    value = tr(key)
    return fallback if value == key else value
