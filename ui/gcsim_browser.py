from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
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


DEFAULT_ROTATION_CODE = """for let i=0; i<4; i=i+1 {
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
    """First visual shell for the future GCSIM Browser.

    This widget is intentionally UI-only:
    - no backend calls;
    - no GCSIM artifact runs;
    - no right-panel persistence;
    - no result writeback.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: str = MODE_ABYSS,
    ) -> None:
        super().__init__(parent)
        self._mode = mode if mode in {MODE_ABYSS, MODE_DPS_DUMMY} else MODE_ABYSS

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
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        layout.addWidget(self.team_tabs)

        self.targets_section, targets_layout = _make_section()
        self.targets_title = QLabel()
        self.targets_title.setObjectName("GcsimBrowserSectionTitle")
        targets_layout.addWidget(self.targets_title)

        chamber_row = QHBoxLayout()
        chamber_row.setContentsMargins(0, 0, 0, 0)
        chamber_row.setSpacing(6)
        self.chamber_buttons: list[QPushButton] = []
        for index in range(3):
            button = QPushButton()
            button.setCheckable(True)
            button.setEnabled(False)
            self.chamber_buttons.append(button)
            chamber_row.addWidget(button)
        chamber_row.addStretch(1)
        self.target_mode_label = QLabel()
        chamber_row.addWidget(self.target_mode_label)
        targets_layout.addLayout(chamber_row)

        self.targets_placeholder = QLabel()
        self.targets_placeholder.setWordWrap(True)
        self.targets_placeholder.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
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
        self.rotation_editor.setMinimumHeight(180)
        rotation_layout.addWidget(self.rotation_editor)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.prepare_button = QPushButton()
        self.prepare_button.setEnabled(False)
        self.run_selected_button = QPushButton()
        self.run_selected_button.setEnabled(False)
        self.run_all_button = QPushButton()
        self.run_all_button.setEnabled(False)
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
        self.results_placeholder.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
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
        if team_index < 0 or team_index >= len(self.team_tab_widgets):
            return
        grid = self.team_tab_widgets[team_index].findChild(QGridLayout)
        if grid is None:
            return
        for slot_index, slot in enumerate(slots[:4]):
            card = self.team_tab_widgets[team_index].findChild(
                QFrame,
                f"gcsimTeamCard{team_index}_{slot_index}",
            )
            if card is None:
                continue
            labels = card.findChildren(QLabel)
            if len(labels) < 4:
                continue
            labels[0].setText(slot.name or _fallback("gcsim.browser.empty_slot", "Empty slot"))
            labels[1].setText(slot.weapon or _fallback("gcsim.browser.weapon_pending", "Weapon: pending"))
            labels[2].setText(slot.sets or _fallback("gcsim.browser.sets_pending", "Sets: pending"))
            labels[3].setText(slot.status or _fallback("gcsim.browser.status_placeholder", "Not checked"))

    def retranslate_ui(self) -> None:
        self.title_label.setText(_fallback("gcsim.browser.title", "GCSIM Browser"))
        self.status_label.setText(
            _fallback("gcsim.browser.status_skeleton", "UI skeleton · backend not connected")
        )
        self.team_tabs.setTabText(0, _fallback("gcsim.browser.team_1", "Team 1"))
        self.team_tabs.setTabText(1, _fallback("gcsim.browser.team_2", "Team 2"))
        self.targets_title.setText(_fallback("gcsim.browser.targets", "Abyss targets"))
        self.target_mode_label.setText(
            _fallback("gcsim.browser.target_mode_placeholder", "Target mode: follows right panel")
        )
        for index, button in enumerate(self.chamber_buttons, start=1):
            button.setText(f"C{index}")
        self.targets_placeholder.setText(
            _fallback(
                "gcsim.browser.targets_placeholder",
                "Chamber waves, enemy HP and resolved GCSIM target types will appear here.",
            )
        )
        self.defaults_title.setText(_fallback("gcsim.browser.defaults", "Run defaults"))
        self.defaults_label.setText(
            _fallback(
                "gcsim.browser.defaults_placeholder",
                "Iterations: 100 · Boosted energy: dev-only placeholder",
            )
        )
        self.rotation_title.setText(_fallback("gcsim.browser.rotation", "Rotation code"))
        self.prepare_button.setText(_fallback("gcsim.browser.prepare", "Prepare config"))
        self.run_selected_button.setText(
            _fallback("gcsim.browser.run_selected", "Run selected chamber")
        )
        self.run_all_button.setText(_fallback("gcsim.browser.run_all", "Run 3 chambers"))
        self.results_title.setText(_fallback("gcsim.browser.results", "Results"))
        self.results_placeholder.setText(
