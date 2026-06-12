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
        self._energy_mode_preview = ""
        self._targets_preview_by_team: tuple[tuple[str, ...], ...] = ((), ())
        self._last_result_text = ""
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

        self.context_section, context_layout = _make_section()
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
        context_layout.addLayout(header)

        context_grid = QGridLayout()
        context_grid.setContentsMargins(0, 0, 0, 0)
        context_grid.setHorizontalSpacing(8)
        context_grid.setVerticalSpacing(4)
        self.mode_context_label = QLabel()
        self.team_context_label = QLabel()
        self.target_context_label = QLabel()
        self.energy_context_label = QLabel()
        self.readiness_context_label = QLabel()
        for label in (
            self.mode_context_label,
            self.team_context_label,
            self.target_context_label,
            self.energy_context_label,
            self.readiness_context_label,
        ):
            label.setWordWrap(True)
        context_grid.addWidget(self.mode_context_label, 0, 0)
        context_grid.addWidget(self.team_context_label, 0, 1)
        context_grid.addWidget(self.target_context_label, 1, 0)
        context_grid.addWidget(self.energy_context_label, 1, 1)
        context_grid.addWidget(self.readiness_context_label, 2, 0, 1, 2)
        context_layout.addLayout(context_grid)
        layout.addWidget(self.context_section)

        self.team_tabs = QTabWidget()
        self.team_tabs.setDocumentMode(True)
        self.team_tab_widgets: list[QWidget] = [
            self._make_team_tab(0),
            self._make_team_tab(1),
        ]
        self.team_tabs.addTab(self.team_tab_widgets[0], "")
        self.team_tabs.addTab(self.team_tab_widgets[1], "")
        self.team_tabs.currentChanged.connect(self._refresh_targets_preview)
        self.team_tabs.currentChanged.connect(lambda _index: self._refresh_context())
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
        self.rotation_tabs = QTabWidget()
        self.rotation_tabs.setDocumentMode(True)
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)
        self.rotation_editor = QPlainTextEdit()
        self.rotation_editor.setPlainText(DEFAULT_ROTATION_CODE)
        self.rotation_editor.textChanged.connect(self.rotation_text_changed.emit)
        self.rotation_editor.setMinimumHeight(180)
        code_layout.addWidget(self.rotation_editor)
        self.rotation_tabs.addTab(code_tab, "")

        readable_tab = QWidget()
        readable_layout = QVBoxLayout(readable_tab)
        readable_layout.setContentsMargins(8, 8, 8, 8)
        self.readable_placeholder = QLabel()
        self.readable_placeholder.setWordWrap(True)
        readable_layout.addWidget(self.readable_placeholder)
        readable_layout.addStretch(1)
        self.rotation_tabs.addTab(readable_tab, "")

        builder_tab = QWidget()
        builder_layout = QVBoxLayout(builder_tab)
        builder_layout.setContentsMargins(8, 8, 8, 8)
        self.builder_placeholder = QLabel()
        self.builder_placeholder.setWordWrap(True)
        builder_layout.addWidget(self.builder_placeholder)
        builder_layout.addStretch(1)
        self.rotation_tabs.addTab(builder_tab, "")
        self.rotation_tabs.setTabEnabled(1, False)
        self.rotation_tabs.setTabEnabled(2, False)
        rotation_layout.addWidget(self.rotation_tabs)

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
        actions.addStretch(1)
        actions.addWidget(self.prepare_button)
        actions.addWidget(self.run_all_button)
        actions.addWidget(self.run_selected_button)
        rotation_layout.addLayout(actions)
        layout.addWidget(self.rotation_section)

        self.results_section, results_layout = _make_section()
        self.results_title = QLabel()
        self.results_title.setObjectName("GcsimBrowserSectionTitle")
        results_layout.addWidget(self.results_title)
        self.result_summary_label = QLabel()
        self.result_summary_label.setWordWrap(True)
        self.result_summary_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        results_layout.addWidget(self.result_summary_label)
        self.advanced_button = QPushButton()
        self.advanced_button.setCheckable(True)
        self.advanced_button.clicked.connect(self._toggle_advanced_details)
        results_layout.addWidget(self.advanced_button)
        self.results_placeholder = QLabel()
        self.results_placeholder.setWordWrap(True)
        self.results_placeholder.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.results_placeholder.setVisible(False)
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
        energy_mode_label: str = "",
    ) -> None:
        self._target_mode_preview = target_mode_label
        self._energy_mode_preview = energy_mode_label
        self._targets_preview_by_team = preview_by_team
        self._refresh_targets_preview()
        self._refresh_context()

    def retranslate_ui(self) -> None:
        self.title_label.setText(_fallback("gcsim.browser.title", "GCSIM Browser"))
        self.status_label.setText(
            _fallback(
                "gcsim.browser.status_skeleton",
                "Runtime team",
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
            _fallback("gcsim.browser.rotation", "Rotation")
        )
        self.rotation_tabs.setTabText(0, _fallback("gcsim.browser.rotation_code", "Code"))
        self.rotation_tabs.setTabText(
            1,
            _fallback("gcsim.browser.rotation_readable", "Readable"),
        )
        self.rotation_tabs.setTabText(
            2,
            _fallback("gcsim.browser.rotation_builder", "Builder"),
        )
        self.readable_placeholder.setText(
            _fallback(
                "gcsim.browser.rotation_readable_placeholder",
                "Readable rotation view is reserved for a later pass. Raw code remains the working input.",
            )
        )
        self.builder_placeholder.setText(
            _fallback(
                "gcsim.browser.rotation_builder_placeholder",
                "Action builder is reserved for a later pass. No-code buttons are not wired yet.",
            )
        )
        self.prepare_button.setText(
            _fallback("gcsim.browser.prepare", "Check readiness")
        )
        self.run_selected_button.setText(
            _fallback("gcsim.browser.run_selected", "Run chamber")
        )
        if self._mode == MODE_DPS_DUMMY:
            self.run_selected_button.setText(
                _fallback("gcsim.browser.run_dps_dummy", "Run DPS Dummy")
            )
        self.run_all_button.setText(
            _fallback("gcsim.browser.run_all", "Run 3 chambers")
        )

        self.results_title.setText(
            _fallback("gcsim.browser.results", "Run summary")
        )
        advanced_key = (
            "gcsim.browser.advanced_hide"
            if self.advanced_button.isChecked()
            else "gcsim.browser.advanced_show"
        )
        advanced_fallback = (
            "Hide Advanced / Debug"
            if self.advanced_button.isChecked()
            else "Show Advanced / Debug"
        )
        self.advanced_button.setText(_fallback(advanced_key, advanced_fallback))
        if not self._last_result_text:
            self.result_summary_label.setText(self._empty_result_summary())
            self.results_placeholder.setText("")
        self._update_mode_visibility()
        self._refresh_context()

    def _make_team_tab(self, team_index: int) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

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
        self._refresh_context()

    def _select_chamber(self, chamber_index: int) -> None:
        self._selected_chamber_index = max(0, min(2, int(chamber_index)))
        for index, button in enumerate(self.chamber_buttons):
            button.setChecked(index == self._selected_chamber_index)
        self._refresh_targets_preview()
        self._refresh_context()

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
        self._set_result_text(
            _fallback("gcsim.browser.prepare_requested", "Checking readiness...")
        )
        self.prepare_requested.emit(team_index, self.rotation_editor.toPlainText())

    def _request_run_selected_chamber(self) -> None:
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        chamber = self._selected_chamber_index + 1
        self._set_result_text(
            _fallback("gcsim.browser.run_requested", "Running chamber...")
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
        self._set_result_text(
            _fallback("gcsim.browser.run_all_requested", "Running 3 chambers...")
        )
        self.run_all_requested.emit(team_index, self.rotation_editor.toPlainText())

    def set_actions_busy(self, busy: bool, *, message: str = "") -> None:
        self.prepare_button.setEnabled(not busy)
        self.run_selected_button.setEnabled(not busy)
        self.run_all_button.setEnabled(not busy and self._mode == MODE_ABYSS)
        if message:
            self._set_result_text(message)

    def set_prepare_result_text(self, text: str) -> None:
        self._set_result_text(
            text.strip()
            or _fallback("gcsim.browser.results_placeholder", "No prepare report.")
        )

    def _refresh_context(self) -> None:
        if not hasattr(self, "mode_context_label"):
            return
        mode_text = (
            _fallback("right_panel.mode.dps_dummy", "DPS Dummy")
            if self._mode == MODE_DPS_DUMMY
            else _fallback("right_panel.mode.abyss", "Abyss")
        )
        team_index = (
            0 if self._mode == MODE_DPS_DUMMY else max(0, self.team_tabs.currentIndex())
        )
        team_text = _fallback("gcsim.browser.context_team", "Team {number}").format(
            number=team_index + 1
        )
        if self._mode == MODE_ABYSS:
            target_mode = self._target_mode_preview or _fallback(
                "gcsim.browser.target_mode_placeholder",
                "Target mode: follows right panel",
            )
            target_text = _fallback(
                "gcsim.browser.context_target_abyss",
                "C{chamber} / {target_mode}",
            ).format(
                chamber=self._selected_chamber_index + 1,
                target_mode=target_mode,
            )
        else:
            target_text = _fallback(
                "gcsim.browser.context_target_dummy",
                "DPS Dummy target from rotation code",
            )
        energy_text = self._energy_mode_preview or _fallback(
            "gcsim.browser.context_energy_app_setting",
            "Energy: app setting",
        )
        status_text = _fallback(
            "gcsim.browser.context_readiness",
            "Readiness: check or run to validate current team.",
        )
        self.mode_context_label.setText(
            _fallback("gcsim.browser.context_mode", "Mode: {mode}").format(
                mode=mode_text
            )
        )
        self.team_context_label.setText(team_text)
        self.target_context_label.setText(target_text)
        self.energy_context_label.setText(energy_text)
        self.readiness_context_label.setText(status_text)

    def _set_result_text(self, text: str) -> None:
        self._last_result_text = text.strip()
        self.result_summary_label.setText(self._result_summary_text(self._last_result_text))
        self.results_placeholder.setText(self._last_result_text)
        self.results_placeholder.setVisible(
            self.advanced_button.isChecked() and bool(self._last_result_text)
        )

    def _result_summary_text(self, text: str) -> str:
        if not text.strip():
            return self._empty_result_summary()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headline = lines[0] if lines else ""
        summary: list[str] = []
        if headline:
            summary.append(headline)
        for prefix in (
            "Prepare status:",
            "Ready:",
            "Status:",
            "Batch status:",
            "Error category:",
            "Observed clear time:",
            "DPS mean:",
            "Avg total damage/run:",
            "Dummy target HP:",
            "Dummy target resist:",
            "Energy mode:",
            "Scenario:",
        ):
            match = _first_line_with_prefix(lines, prefix)
            if match:
                summary.append(match)
        chamber_lines = [
            line for line in lines if len(line) > 1 and line[0] == "C" and line[1].isdigit()
        ]
        if chamber_lines:
            summary.extend(chamber_lines[:3])
        readiness_index = next(
            (
                index
                for index, line in enumerate(lines)
                if line.startswith("Readiness")
                or line.startswith("Blocked")
                or line.startswith("Missing")
            ),
            -1,
        )
        if readiness_index >= 0:
            summary.extend(lines[readiness_index : readiness_index + 4])
        if len(summary) <= 1 and len(lines) > 1:
            summary.extend(lines[1:4])
        return "\n".join(_dedupe_text(summary))

    def _empty_result_summary(self) -> str:
        return _fallback(
            "gcsim.browser.results_placeholder",
            "Run output appears here: status, Sim DPS, duration, damage and warnings.",
        )

    def _toggle_advanced_details(self, checked: bool) -> None:
        self.results_placeholder.setVisible(bool(checked) and bool(self._last_result_text))
        key = "gcsim.browser.advanced_hide" if checked else "gcsim.browser.advanced_show"
        fallback = "Hide Advanced / Debug" if checked else "Show Advanced / Debug"
        self.advanced_button.setText(_fallback(key, fallback))


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


def _first_line_with_prefix(lines: list[str], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix):
            return line
    return ""


def _dedupe_text(lines: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line or line in seen:
            continue
        seen.add(line)
        result.append(line)
    return result


def _fallback(key: str, fallback: str) -> str:
    value = tr(key)
    return fallback if value == key else value
