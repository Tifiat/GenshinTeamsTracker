from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QTimer, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.gcsim.optimizer_rotation_policy import (
    normalize_optimizer_rotation_shell,
)
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS, MODE_DPS_DUMMY
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualArtifactSetChoice,
    GcsimVirtualRosterCatalog,
    GcsimVirtualSlotOverride,
)
from ui.gcsim_browser.optimizer_result import (
    OptimizerResultBuildRow,
    OptimizerResultPage,
    OptimizerResultBuildsWidget,
)
from ui.gcsim_browser.virtual_slot_editor import VirtualGcsimCardEditor
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.toggle_switch import ToggleSwitch
from ui.utils.ui_palette import UI_TEXT_MUTED


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
    optimizer_selected_requested = Signal(int, str)
    optimizer_all_sets_requested = Signal(int, str)
    optimizer_theory_requested = Signal(int, str)
    optimizer_infinite_energy_changed = Signal(bool)
    optimizer_cancel_requested = Signal()
    optimizer_finish_requested = Signal()
    optimizer_build_save_requested = Signal(dict)
    virtual_character_requested = Signal(int, int, str)
    virtual_weapon_requested = Signal(int, int, str)
    virtual_constellation_requested = Signal(int, int, int)
    virtual_refinement_requested = Signal(int, int, int)
    virtual_profile_requested = Signal(int, int, dict)
    virtual_set_bonuses_requested = Signal(int, int, list)
    virtual_clear_requested = Signal(int, int)

    """First visual shell for the future GCSIM Browser.

    This widget owns only the local editor/preview UI. AppShell wires backend
    prepare/run workers and decides whether successful results are persisted.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: str = MODE_ABYSS,
        preparation_only: bool = False,
        scoped_build: bool = False,
    ) -> None:
        super().__init__(parent)
        self._mode = mode if mode in {MODE_ABYSS, MODE_DPS_DUMMY} else MODE_ABYSS
        self._preparation_only = bool(preparation_only)
        self._restricted_build = bool(scoped_build or preparation_only)
        self._run_admitted = not self._preparation_only
        self._actions_busy = False
        self._selected_chamber_index = 0
        self._optimizer_mode = "selected"
        self._optimizer_busy = False
        self._optimizer_finish_requested = False
        self._optimizer_finalizing = False
        self._optimizer_progress_value = 0
        self._optimizer_progress_sequence = -1
        self._optimizer_all_sets_available = False
        self._optimizer_theory_available = False
        self._target_mode_preview = ""
        self._energy_mode_preview = ""
        self._targets_preview_by_team: tuple[tuple[str, ...], ...] = ((), ())
        self._last_result_text = ""
        self._team_previews: list[list[GcsimBrowserTeamSlotPreview]] = [
            [GcsimBrowserTeamSlotPreview() for _ in range(4)],
            [GcsimBrowserTeamSlotPreview() for _ in range(4)],
        ]
        self._team_cards: list[list[_TeamCard]] = []
        self._virtual_catalog = GcsimVirtualRosterCatalog.empty()
        self._rotation_window = None
        self._rotation_environment = None
        self._rotation_base_source = ""
        self.rotation_team_provider = None
        self._rotation_team_context = None
        self._rotation_revision = 0
        self._import_generation = 0
        self._import_binding = None
        self._import_dialog = None
        self._virtual_set_choices: tuple[GcsimVirtualArtifactSetChoice, ...] = ()
        self._team_notes: list[QLabel] = []
        self._optimizer_elapsed_clock = QElapsedTimer()
        self._optimizer_elapsed_last_ms = 0
        self._optimizer_elapsed_terminal_stage = ""
        self._optimizer_elapsed_tick = QTimer(self)
        self._optimizer_elapsed_tick.setInterval(1000)
        self._optimizer_elapsed_tick.timeout.connect(self._refresh_optimizer_elapsed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setDocumentMode(True)
        root.addWidget(self.workspace_tabs, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_tabs.addTab(scroll, "")

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
        self.open_rotation_editor_button = QPushButton()
        self.open_rotation_editor_button.clicked.connect(self._open_rotation_editor)
        rotation_layout.addWidget(self.open_rotation_editor_button)
        self.import_rotation_button = QPushButton()
        self.import_rotation_button.clicked.connect(self._open_rotation_import)
        rotation_layout.addWidget(self.import_rotation_button)
        self.rotation_tabs = QTabWidget()
        self.rotation_tabs.setDocumentMode(True)
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)
        self.rotation_editor = QPlainTextEdit()
        self.rotation_editor.setPlainText(DEFAULT_ROTATION_CODE)
        self.rotation_editor.textChanged.connect(self.rotation_text_changed.emit)
        self.rotation_editor.textChanged.connect(self._rotation_source_changed)
        self.rotation_editor.setMinimumHeight(180)
        code_layout.addWidget(self.rotation_editor)
        self.rotation_tabs.addTab(code_tab, "")

        readable_tab = QWidget()
        readable_layout = QVBoxLayout(readable_tab)
        readable_layout.setContentsMargins(8, 8, 8, 8)
        self.readable_text = QPlainTextEdit()
        self.readable_text.setReadOnly(True)
        self.readable_text.setMinimumHeight(180)
        readable_layout.addWidget(self.readable_text)
        self.rotation_tabs.addTab(readable_tab, "")

        builder_tab = QWidget()
        builder_layout = QVBoxLayout(builder_tab)
        builder_layout.setContentsMargins(8, 8, 8, 8)
        self.builder_placeholder = QLabel()
        self.builder_placeholder.setWordWrap(True)
        builder_layout.addWidget(self.builder_placeholder)
        builder_layout.addStretch(1)
        self.rotation_tabs.addTab(builder_tab, "")
        self.rotation_tabs.setTabEnabled(1, True)
        self.rotation_tabs.setTabEnabled(2, False)
        self._readable_timer = QTimer(self)
        self._readable_timer.setSingleShot(True)
        self._readable_timer.setInterval(200)
        self._readable_timer.timeout.connect(self._refresh_readable)
        self.rotation_editor.textChanged.connect(self._schedule_readable)
        self.rotation_tabs.currentChanged.connect(self._rotation_tab_changed)
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

        optimizer_scroll = QScrollArea()
        optimizer_scroll.setWidgetResizable(True)
        optimizer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_tabs.addTab(optimizer_scroll, "")
        optimizer_content = QWidget()
        optimizer_scroll.setWidget(optimizer_content)
        optimizer_layout = QVBoxLayout(optimizer_content)
        optimizer_layout.setContentsMargins(8, 8, 8, 8)
        optimizer_layout.setSpacing(8)

        optimizer_intro, optimizer_intro_layout = _make_section()
        self.optimizer_title = QLabel()
        self.optimizer_title.setObjectName("GcsimBrowserSectionTitle")
        optimizer_intro_layout.addWidget(self.optimizer_title)
        self.optimizer_description = QLabel()
        self.optimizer_description.setWordWrap(True)
        optimizer_intro_layout.addWidget(self.optimizer_description)
        optimizer_layout.addWidget(optimizer_intro)
        self.workspace_tabs.setTabVisible(1, not self._restricted_build)

        optimizer_actions, optimizer_actions_layout = _make_section()
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        self.optimizer_selected_button = QPushButton()
        self.optimizer_selected_button.clicked.connect(
            self._request_optimizer_selected
        )
        self.optimizer_all_sets_button = QPushButton()
        self.optimizer_all_sets_button.setEnabled(False)
        self.optimizer_all_sets_button.clicked.connect(self._request_optimizer_all_sets)
        self.optimizer_theory_button = QPushButton()
        self.optimizer_theory_button.setEnabled(False)
        self.optimizer_theory_button.clicked.connect(self._request_optimizer_theory)
        mode_row.addWidget(self.optimizer_selected_button)
        mode_row.addWidget(self.optimizer_all_sets_button)
        mode_row.addWidget(self.optimizer_theory_button)
        mode_row.addStretch(1)
        self.optimizer_infinite_energy_label = QLabel()
        self.optimizer_infinite_energy_switch = ToggleSwitch()
        self.optimizer_infinite_energy_switch.toggled.connect(
            self._on_optimizer_infinite_energy_toggled
        )
        mode_row.addWidget(self.optimizer_infinite_energy_label)
        mode_row.addWidget(self.optimizer_infinite_energy_switch)
        optimizer_actions_layout.addLayout(mode_row)
        self.optimizer_future_note = QLabel()
        self.optimizer_future_note.setWordWrap(True)
        optimizer_actions_layout.addWidget(self.optimizer_future_note)
        self.optimizer_energy_note = QLabel()
        self.optimizer_energy_note.setWordWrap(True)
        self.optimizer_energy_note.setStyleSheet(f"color: {UI_TEXT_MUTED};")
        optimizer_actions_layout.addWidget(self.optimizer_energy_note)
        optimizer_layout.addWidget(optimizer_actions)

        optimizer_status, optimizer_status_layout = _make_section()
        self.optimizer_progress_label = QLabel()
        self.optimizer_progress_label.setWordWrap(True)
        optimizer_status_layout.addWidget(self.optimizer_progress_label)
        self.optimizer_elapsed_label = QLabel()
        self.optimizer_elapsed_label.setWordWrap(True)
        self.optimizer_elapsed_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
        optimizer_status_layout.addWidget(self.optimizer_elapsed_label)
        self.optimizer_progress_bar = QProgressBar()
        self.optimizer_progress_bar.setRange(0, 100)
        self.optimizer_progress_bar.setValue(0)
        self._optimizer_progress_animation = QPropertyAnimation(self.optimizer_progress_bar, b"value", self)
        self._optimizer_progress_animation.setDuration(400)
        self._optimizer_progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.optimizer_progress_bar.setTextVisible(False)
        optimizer_status_layout.addWidget(self.optimizer_progress_bar)
        optimizer_buttons = QHBoxLayout()
        optimizer_buttons.setContentsMargins(0, 0, 0, 0)
        optimizer_buttons.setSpacing(6)
        self.optimizer_cancel_button = QPushButton()
        self.optimizer_cancel_button.setEnabled(False)
        self.optimizer_cancel_button.clicked.connect(
            self.optimizer_cancel_requested.emit
        )
        self.optimizer_finish_button = QPushButton()
        self.optimizer_finish_button.setEnabled(False)
        self.optimizer_finish_button.clicked.connect(self._request_optimizer_finish)
        optimizer_buttons.addWidget(self.optimizer_cancel_button)
        optimizer_buttons.addWidget(self.optimizer_finish_button)
        optimizer_status_layout.addLayout(optimizer_buttons)
        self.optimizer_result = QPlainTextEdit()
        self.optimizer_result.setReadOnly(True)
        self.optimizer_result.setMinimumHeight(150)
        optimizer_status_layout.addWidget(self.optimizer_result)
        self.optimizer_result_builds = OptimizerResultBuildsWidget()
        self.optimizer_result_builds.save_requested.connect(
            self.optimizer_build_save_requested.emit
        )
        optimizer_status_layout.addWidget(self.optimizer_result_builds)
        optimizer_layout.addWidget(optimizer_status)
        optimizer_layout.addStretch(1)

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

    def _load_rotation_environment(self):
        # Source and metadata reads happen on this explicit user entry, not
        # during application startup or an unrelated browser refresh.
        from run_workspace.gcsim.engine_store import GcsimEngineStore
        from run_workspace.gcsim.rotation_editor.integration import load_environment

        installation = GcsimEngineStore().get_active_engine()
        if installation is None:
            raise ValueError(tr("rotation.editor.no_engine"))
        return load_environment(installation)

    def _current_rotation_team(self):
        from run_workspace.gcsim.rotation_editor.team import TeamContext
        index = 0 if self._mode == MODE_DPS_DUMMY else max(0, self.team_tabs.currentIndex())
        if self.rotation_team_provider is not None:
            return self.rotation_team_provider(index)
        return TeamContext(f"{self._mode}:{index}")

    def _rotation_names(self, environment, team):
        names = {item.gcsim_key: item.display_name for item in self._virtual_catalog.characters}
        names.update({member.key: member.name for member in team.members})
        for key in environment.dialect.character_aliases.values():
            localized = tr("rotation.character." + key)
            if localized != "rotation.character." + key:
                names[key] = localized
        return names

    def refresh_rotation_team_context(self):
        if not hasattr(self, "rotation_tabs"):
            return
        binding = self._current_rotation_team().search_binding
        if self._import_binding != binding:
            self._import_generation += 1
            self._import_binding = binding
        if self._rotation_window is not None:
            team = self._current_rotation_team()
            names = self._rotation_names(self._rotation_environment, team)
            self._rotation_window.set_team(team.keys, names)
            if team.binding != self._rotation_team_context.binding:
                self._rotation_window.block_apply(tr("rotation.editor.team_changed"))
        if self.rotation_tabs.currentIndex() == 1:
            self._refresh_readable()

    def _rotation_tab_changed(self, index):
        if index == 1:
            self._refresh_readable()

    def _rotation_source_changed(self):
        self._rotation_revision += 1

    def _import_state(self, environment, team):
        draft = self._rotation_window
        draft_state = (id(draft), id(draft.session.current), draft.code.document().revision()) if draft else None
        return self._rotation_revision, self._import_generation, team.search_binding, environment.identity, draft_state

    def _open_rotation_import(self):
        from ui.gcsim_browser.rotation_import import RotationImportDialog
        team = self._current_rotation_team()
        if len(team.keys) != 4 or team.unresolved:
            self.set_prepare_result_text(tr("rotation.import.team_required"))
            return
        try:
            environment = self._load_rotation_environment()
        except (OSError, ValueError, RuntimeError):
            self.set_prepare_result_text(tr("rotation.editor.no_engine"))
            return
        if self._import_dialog is not None:
            if self._import_dialog.worker.isRunning():
                self._import_dialog.show()
                self._import_dialog.raise_()
                return
            self._import_dialog.deleteLater()
        if self._rotation_window is not None:
            self._rotation_window.flush_code()
        if self._import_binding != team.search_binding:
            self._import_generation += 1
            self._import_binding = team.search_binding
        snapshot = self._import_state(environment, team)
        dialog = RotationImportDialog(team, environment, self.rotation_editor.toPlainText(),
            names=self._rotation_names(environment, team), catalog=self._virtual_catalog,
            set_choices=self._virtual_set_choices, parent=self)
        dialog.chosen.connect(lambda source: self._accept_rotation_import(source, snapshot, dialog))
        self._import_dialog = dialog
        dialog.show()

    def _accept_rotation_import(self, source, snapshot, dialog):
        team = self._current_rotation_team()
        try:
            environment = self._load_rotation_environment()
        except (OSError, ValueError, RuntimeError):
            dialog.notice.setText(tr("rotation.editor.no_engine"))
            return
        if self._import_state(environment, team) != snapshot:
            dialog.notice.setText(tr("rotation.import.stale"))
            dialog.load_button.setEnabled(False)
            return
        # Choosing an import explicitly replaces the draft. Preserve its undo
        # history where the same dialect/environment still owns the window.
        if self._rotation_window is not None and self._rotation_environment.identity == environment.identity:
            window = self._rotation_window
            window.timer.stop()
            try:
                window.session.set_code(source)
            except (ValueError, RecursionError):
                dialog.notice.setText(tr("rotation.import.syntax"))
                return
            window.selection = None
            window.refresh()
            window.set_team(team.keys, self._rotation_names(environment, team))
            window.block_apply("")
            self._rotation_team_context = team
            self._rotation_base_source = self.rotation_editor.toPlainText()
            window.refresh()
            window.show()
        else:
            if not self._create_rotation_window(environment, source, reset_base=True):
                dialog.notice.setText(tr("rotation.import.syntax"))
                return
        dialog.accept()
        if self._rotation_window is not None:
            self._rotation_window.raise_()
            self._rotation_window.activateWindow()

    def _schedule_readable(self):
        if self.rotation_tabs.currentIndex() == 1:
            self._readable_timer.start()

    def _refresh_readable(self):
        from run_workspace.gcsim.rotation_editor import parse
        from run_workspace.gcsim.rotation_editor.readable import render

        self._readable_timer.stop()
        try:
            environment = self._load_rotation_environment()
            team = self._current_rotation_team()
            names = self._rotation_names(environment, team)
            document = parse(self.rotation_editor.toPlainText(), environment.dialect)
            text = render(document, tr, resolve_name=names.get).compact_text()
            if not document.syntax_complete:
                text = tr("rotation.editor.syntax_issue") + "\n\n" + text
            self.readable_text.setPlainText(text)
        except (OSError, ValueError, RuntimeError, RecursionError) as error:
            self.readable_text.setPlainText(tr("rotation.editor.error", reason=str(error)))

    def _open_rotation_editor(self) -> None:
        try:
            environment = self._load_rotation_environment()
        except (OSError, ValueError, RuntimeError) as error:
            self.set_prepare_result_text(tr("rotation.editor.error", reason=str(error)))
            return
        source = self.rotation_editor.toPlainText()
        if self._rotation_window is not None:
            if not self._rotation_window.flush_code():
                self._rotation_window.show()
                return
            if self._rotation_environment.identity == environment.identity:
                # Preserve an unfinished draft and undo history on close/reopen.
                team = self._current_rotation_team()
                self._rotation_team_context = team
                self._rotation_window.set_team(team.keys, self._rotation_names(environment, team))
                self._rotation_window.block_apply("" if self.rotation_editor.toPlainText() == self._rotation_base_source else tr("rotation.editor.external_change"))
                self._rotation_window.show()
                self._rotation_window.raise_()
                self._rotation_window.activateWindow()
                return
            draft = self._rotation_window.session.code_text()
            if draft is None:
                self._rotation_window.block_apply(tr("rotation.editor.engine_change"))
                self._rotation_window.show()
                return
            source = draft
        self._create_rotation_window(environment, source, reset_base=self._rotation_window is None)

    def _create_rotation_window(self, environment, source: str, *, reset_base: bool) -> bool:
        from ui.gcsim_browser.rotation_editor import RotationEditorWindow

        team = self._current_rotation_team()
        names = self._rotation_names(environment, team)
        try:
            replacement = RotationEditorWindow(source, environment.dialect, names=names,
                character_options=environment.character_options, allowed_actors=team.keys, parent=self)
        except (ValueError, RecursionError) as error:
            if self._rotation_window is not None:
                self._rotation_window.set_message(tr("rotation.editor.error", reason=str(error)))
            else:
                self.set_prepare_result_text(tr("rotation.editor.error", reason=str(error)))
            return False
        if self._rotation_window is not None:
            self._rotation_window.close()
            self._rotation_window.deleteLater()
        self._rotation_environment = environment
        self._rotation_team_context = team
        self._rotation_window = replacement
        if reset_base:
            self._rotation_base_source = self.rotation_editor.toPlainText()
        self._rotation_window.applied.connect(self._apply_rotation_draft)
        self._rotation_window.reload_requested.connect(self._reload_rotation_draft)
        self._rotation_window.show()
        return True

    def _reload_rotation_draft(self) -> None:
        # Explicitly labeled destructive draft replacement, requested by a click.
        try:
            environment = self._load_rotation_environment()
        except (OSError, ValueError, RuntimeError) as error:
            self._rotation_window.set_message(tr("rotation.editor.error", reason=str(error)))
            return
        self._create_rotation_window(environment, self.rotation_editor.toPlainText(), reset_base=True)

    def _apply_rotation_draft(self, source: str) -> None:
        window = self._rotation_window
        team = self._current_rotation_team()
        if team.binding != self._rotation_team_context.binding:
            self.refresh_rotation_team_context()
            window.set_message(tr("rotation.editor.team_changed"))
            return
        from run_workspace.gcsim.rotation_editor import parse
        from run_workspace.gcsim.rotation_editor.team import validate_team
        try:
            document = parse(source, self._rotation_environment.dialect)
        except (ValueError, RecursionError):
            window.set_message(tr("rotation.editor.syntax_issue"))
            return
        if not document.syntax_complete:
            window.set_message(tr("rotation.editor.syntax_issue"))
            return
        if not team.keys or validate_team(document, team.keys):
            window.set_message(tr("rotation.editor.team_outside"))
            return
        try:
            environment = self._load_rotation_environment()
            if environment.identity != self._rotation_environment.identity:
                window.block_apply(tr("rotation.editor.engine_change"))
                return
        except (OSError, ValueError, RuntimeError):
            window.set_message(tr("rotation.editor.no_engine"))
            return
        if self.rotation_editor.toPlainText() != self._rotation_base_source:
            window.block_apply(tr("rotation.editor.external_change"))
            return
        self.rotation_editor.setPlainText(source)
        self._rotation_base_source = source
        window.set_message(tr("rotation.editor.applied"))

    def set_virtual_gcsim_catalogs(
        self,
        catalog: GcsimVirtualRosterCatalog,
        set_choices: tuple[GcsimVirtualArtifactSetChoice, ...],
    ) -> None:
        self._virtual_catalog = catalog
        self._virtual_set_choices = tuple(set_choices)
        for cards in self._team_cards:
            for card in cards:
                card.set_virtual_catalogs(catalog, self._virtual_set_choices)

    def set_virtual_gcsim_slot_context(
        self,
        team_index: int,
        slot_index: int,
        *,
        override: GcsimVirtualSlotOverride | None,
        artifact_builds: tuple[dict[str, object], ...] = (),
    ) -> None:
        if not (0 <= int(team_index) < len(self._team_cards)):
            return
        cards = self._team_cards[int(team_index)]
        if not (0 <= int(slot_index) < len(cards)):
            return
        cards[int(slot_index)].set_virtual_context(
            override=override,
            artifact_builds=artifact_builds,
        )

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
        self.workspace_tabs.setTabText(0, _fallback("gcsim.browser.simulation", "Simulation"))
        self.workspace_tabs.setTabText(1, "Artifact optimizer")
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
                card.retranslate_ui()
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
        self.open_rotation_editor_button.setText(tr("rotation.editor.open"))
        self.import_rotation_button.setText(tr("rotation.import.button"))
        self.rotation_tabs.setTabText(0, _fallback("gcsim.browser.rotation_code", "Code"))
        self.rotation_tabs.setTabText(
            1,
            _fallback("gcsim.browser.rotation_readable", "Readable"),
        )
        self.rotation_tabs.setTabText(
            2,
            _fallback("gcsim.browser.rotation_builder", "Builder"),
        )
        if self.rotation_tabs.currentIndex() == 1:
            self._refresh_readable()
        self.builder_placeholder.setText(
            _fallback(
                "rotation.editor.open",
                "Open rotation editor",
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
        self.optimizer_title.setText("Artifact optimizer")
        self.optimizer_description.setText(
            _fallback("gcsim.optimizer.selected_description",
                      "Uses the active team, current rotation and equipped 4-piece or 2+2 sets. Searches account artifacts without equipping them.")
        )
        self.optimizer_selected_button.setText("Selected Sets")
        self.optimizer_all_sets_button.setText("All Sets")
        self.optimizer_theory_button.setText("Theory")
        self.optimizer_infinite_energy_label.setText(
            _fallback("gcsim.optimizer.infinite_energy", "Infinite energy")
        )
        self.optimizer_future_note.setText(
            "Theory shows formula-guided farming targets rather than owned artifact IDs."
        )
        self._refresh_optimizer_energy_note()
        if not self.optimizer_progress_label.text():
            self.optimizer_progress_label.setText("Selected Sets is ready to start.")
        self.optimizer_result_builds.retranslate_ui()
        self._refresh_optimizer_elapsed()
        self.optimizer_cancel_button.setText("Cancel")
        self.optimizer_finish_button.setText(
            _fallback(
                "gcsim.optimizer.finish_button",
                "Finish and show result",
            )
        )

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
            card = _TeamCard(team_index=team_index, slot_index=slot_index)
            card.activate_virtual_button.setVisible(not self._restricted_build)
            card.setObjectName(f"gcsimTeamCard{team_index}_{slot_index}")
            card.virtual_character_requested.connect(
                lambda key, team=team_index, slot=slot_index: (
                    self.virtual_character_requested.emit(team, slot, key)
                )
            )
            card.virtual_weapon_requested.connect(
                lambda key, team=team_index, slot=slot_index: (
                    self.virtual_weapon_requested.emit(team, slot, key)
                )
            )
            card.virtual_constellation_requested.connect(
                lambda value, team=team_index, slot=slot_index: (
                    self.virtual_constellation_requested.emit(team, slot, value)
                )
            )
            card.virtual_refinement_requested.connect(
                lambda value, team=team_index, slot=slot_index: (
                    self.virtual_refinement_requested.emit(team, slot, value)
                )
            )
            card.virtual_profile_requested.connect(
                lambda value, team=team_index, slot=slot_index: (
                    self.virtual_profile_requested.emit(team, slot, value)
                )
            )
            card.virtual_set_bonuses_requested.connect(
                lambda value, team=team_index, slot=slot_index: (
                    self.virtual_set_bonuses_requested.emit(team, slot, value)
                )
            )
            card.virtual_clear_requested.connect(
                lambda team=team_index, slot=slot_index: (
                    self.virtual_clear_requested.emit(team, slot)
                )
            )
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
        self.run_all_button.setVisible(is_abyss and not self._preparation_only)
        self.run_selected_button.setVisible(not self._preparation_only)
        if self._preparation_only or not self._run_admitted:
            self.run_selected_button.setEnabled(False)
        if self._restricted_build:
            self.optimizer_selected_button.setEnabled(False)
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
        if self._preparation_only or not self._run_admitted or self._actions_busy or self._optimizer_busy:
            return
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
        if self._preparation_only or not self._run_admitted or self._actions_busy or self._optimizer_busy:
            return
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        self._set_result_text(
            _fallback("gcsim.browser.run_all_requested", "Running 3 chambers...")
        )
        self.run_all_requested.emit(team_index, self.rotation_editor.toPlainText())

    def _request_optimizer_selected(self) -> None:
        self._request_optimizer_mode("selected")

    def _request_optimizer_all_sets(self) -> None:
        self._request_optimizer_mode("all_sets")

    def _request_optimizer_theory(self) -> None:
        self._request_optimizer_mode("theory")

    def set_optimizer_all_sets_available(self, available: bool) -> None:
        self._optimizer_all_sets_available = bool(available)
        self.optimizer_all_sets_button.setEnabled(
            self._optimizer_all_sets_available and self.optimizer_selected_button.isEnabled()
        )

    def set_optimizer_theory_available(self, available: bool) -> None:
        self._optimizer_theory_available = bool(available)
        self.optimizer_theory_button.setEnabled(
            self._optimizer_theory_available and self.optimizer_selected_button.isEnabled()
        )

    def _request_optimizer_mode(self, mode: str) -> None:
        if self._restricted_build:
            return
        self._optimizer_mode = mode
        team_index = max(0, int(self.team_tabs.currentIndex()))
        if self._mode == MODE_DPS_DUMMY:
            team_index = 0
        rotation_text = self.rotation_editor.toPlainText()
        rotation_policy = normalize_optimizer_rotation_shell(rotation_text)
        self.optimizer_result.setPlainText("")
        self.optimizer_result_builds.clear()
        self._start_optimizer_elapsed()
        if rotation_policy.changed:
            duration = f"{float(rotation_policy.duration_seconds or 0):g}"
            notice = tr("gcsim.optimizer.rotation_auto_bounded").format(
                duration=duration
            )
            self.optimizer_result.setPlainText(notice)
            self.optimizer_progress_label.setText(notice)
        else:
            self.optimizer_progress_label.setText(
                tr("gcsim.optimizer.preparing_all")
                if mode == "all_sets"
                else "Preparing Theory input..."
                if mode == "theory"
                else "Preparing Selected Sets input..."
            )
        self.optimizer_progress_bar.setRange(0, 0)
        signal = (
            self.optimizer_all_sets_requested
            if mode == "all_sets"
            else self.optimizer_theory_requested
            if mode == "theory"
            else self.optimizer_selected_requested
        )
        signal.emit(
            team_index,
            rotation_text,
        )

    def set_optimizer_infinite_energy_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled)
        if self.optimizer_infinite_energy_switch.isChecked() != normalized:
            self.optimizer_infinite_energy_switch.blockSignals(True)
            try:
                self.optimizer_infinite_energy_switch.setChecked(normalized)
            finally:
                self.optimizer_infinite_energy_switch.blockSignals(False)
        self._refresh_optimizer_energy_note()

    def _on_optimizer_infinite_energy_toggled(self, enabled: bool) -> None:
        self._refresh_optimizer_energy_note()
        self.optimizer_infinite_energy_changed.emit(bool(enabled))

    def _refresh_optimizer_energy_note(self) -> None:
        if self.optimizer_infinite_energy_switch.isChecked():
            text = _fallback(
                "gcsim.optimizer.energy_infinite_note",
                "Energy mode: infinite. Selected behaves as before and does not "
                "require enough energy to cast bursts.",
            )
        else:
            text = _fallback(
                "gcsim.optimizer.energy_requirements_note",
                "Energy requirements enabled. The optimizer selects enough Energy "
                "Recharge for bursts and verifies the final build in an ordinary simulation.",
            )
        self.optimizer_energy_note.setText(text)

    def set_optimizer_busy(self, busy: bool) -> None:
        normalized_busy = bool(busy)
        if normalized_busy and not self._optimizer_busy:
            self._optimizer_finish_requested = False
            self._optimizer_finalizing = False
            self._optimizer_progress_value = 0
            self._optimizer_progress_sequence = -1
            self.optimizer_progress_bar.setRange(0, 100)
            self.optimizer_progress_bar.setValue(0)
            self.optimizer_progress_bar.setTextVisible(False)
        self._optimizer_busy = normalized_busy
        self.prepare_button.setEnabled(not busy)
        self.run_selected_button.setEnabled(not busy and not self._actions_busy and self._run_admitted)
        self.run_all_button.setEnabled(not busy and not self._actions_busy and self._mode == MODE_ABYSS and self._run_admitted)
        self.optimizer_selected_button.setEnabled(not busy and not self._restricted_build)
        self.optimizer_all_sets_button.setEnabled(not busy and self._optimizer_all_sets_available)
        self.optimizer_theory_button.setEnabled(not busy and self._optimizer_theory_available)
        self.optimizer_infinite_energy_switch.setEnabled(not busy)
        self.optimizer_cancel_button.setEnabled(busy)
        if not busy:
            self._optimizer_finish_requested = False
            self._optimizer_finalizing = False
        self._refresh_optimizer_finish_button()
        if busy and not self._optimizer_elapsed_clock.isValid():
            self._start_optimizer_elapsed()
        elif not busy and self._optimizer_elapsed_tick.isActive():
            self._stop_optimizer_elapsed("stopped")
        if not busy and self.optimizer_progress_bar.maximum() == 0:
            self.optimizer_progress_bar.setRange(0, 100)
            self.optimizer_progress_bar.setValue(self._optimizer_progress_value)

    def update_optimizer_progress(self, event: dict) -> None:
        completed = max(0, int(event.get("completed_work", 0)))
        total = max(0, int(event.get("total_work", 0)))
        stage = str(event.get("stage") or "working")
        sequence = event.get("sequence")
        if isinstance(sequence, int) and sequence < self._optimizer_progress_sequence:
            return
        if isinstance(sequence, int):
            self._optimizer_progress_sequence = sequence
        labels = {
            "validating_request": "Checking the request",
            "loading_evidence": "Reading the rotation formulas",
            "preparing_sources": _fallback(
                "gcsim.optimizer.preparing_sources",
                "Preparing optimizer source data",
            ),
            "capturing_schedule": _fallback(
                "gcsim.optimizer.capturing_schedule",
                "Capturing the rotation schedule",
            ),
            "compiling_formula": "Preparing the damage model",
            "searching": "Searching account artifacts",
            "preparing_replacements": _fallback(
                "gcsim.optimizer.preparing_replacements",
                "Preparing replacement options",
            ),
            "validating_finalists": _fallback(
                "gcsim.optimizer.validating_finalists",
                "Choosing finalists",
            ),
            "simulating_finalists": _fallback(
                "gcsim.optimizer.simulating_finalists",
                "Checking finalists in GCSIM",
            ),
            "finish_requested": _fallback(
                "gcsim.optimizer.finish_requested",
                "Stopping search; showing results found so far. If no complete build exists yet, this will be reported.",
            ),
            "finalizing": _fallback(
                "gcsim.optimizer.finalizing",
                "Finalizing and showing the best result",
            ),
            "completed": "Selected Sets complete",
            "cancelled": "Selected Sets cancelled",
            "failed": "Selected Sets failed",
            "finish_no_result": tr("gcsim.optimizer.finish_no_result_title"),
        }
        if self._optimizer_mode == "all_sets":
            for terminal in ("completed", "cancelled", "failed"):
                labels[terminal] = tr("gcsim.optimizer.all_" + terminal)
        elif self._optimizer_mode == "theory":
            labels.update(
                {
                    "searching": "Finding theoretical farming targets",
                    "completed": "Theory complete",
                    "cancelled": "Theory cancelled",
                    "failed": "Theory failed",
                }
            )
        finalizing_stages = {
            "preparing_replacements",
            "finalizing",
            "validating_finalists",
            "simulating_finalists",
            "completed",
            "cancelled",
            "failed",
            "finish_no_result",
        }
        if stage in finalizing_stages:
            self._optimizer_finalizing = True
            self._refresh_optimizer_finish_button()
        if self._optimizer_finish_requested and stage not in finalizing_stages:
            self.optimizer_progress_label.setText(
                _fallback(
                    "gcsim.optimizer.finish_requested",
                    "Stopping search; showing results found so far. If no complete build exists yet, this will be reported.",
                )
            )
        elif stage == "finalizing":
            self.optimizer_progress_label.setText(
                _fallback(
                    "gcsim.optimizer.finalizing",
                    "Finalizing and showing the best result",
                )
            )
        else:
            self.optimizer_progress_label.setText(labels.get(stage, stage))
        if stage in {"completed", "cancelled", "failed", "finish_no_result"}:
            self._stop_optimizer_elapsed(stage)
        if stage == "completed":
            self._optimizer_progress_value = 100
        else:
            stage_value = _optimizer_progress_value(stage, completed, total)
            if stage_value is not None:
                self._optimizer_progress_value = max(
                    self._optimizer_progress_value,
                    min(99, stage_value),
                )
        self.optimizer_progress_bar.setRange(0, 100)
        self.optimizer_progress_bar.setTextVisible(False)
        self._optimizer_progress_animation.stop()
        if stage in {"completed", "cancelled", "failed", "finish_no_result"} or not self.isVisible():
            self.optimizer_progress_bar.setValue(self._optimizer_progress_value)
        else:
            self._optimizer_progress_animation.setStartValue(self.optimizer_progress_bar.value())
            self._optimizer_progress_animation.setEndValue(self._optimizer_progress_value)
            self._optimizer_progress_animation.start()

    def _request_optimizer_finish(self) -> None:
        if (
            not self._optimizer_busy
            or self._optimizer_mode not in {"selected", "all_sets"}
            or self._optimizer_finish_requested
            or self._optimizer_finalizing
        ):
            return
        self._optimizer_finish_requested = True
        self._refresh_optimizer_finish_button()
        self.optimizer_progress_label.setText(
            _fallback(
                "gcsim.optimizer.finish_requested",
                "Stopping search; showing results found so far. If no complete build exists yet, this will be reported.",
            )
        )
        self.optimizer_finish_requested.emit()

    def _refresh_optimizer_finish_button(self) -> None:
        supported_mode = self._optimizer_mode in {"selected", "all_sets"}
        self.optimizer_finish_button.setEnabled(
            self._optimizer_busy
            and supported_mode
            and not self._optimizer_finish_requested
            and not self._optimizer_finalizing
        )

    def set_optimizer_result_text(self, text: str) -> None:
        self.optimizer_result.setPlainText(text.strip())

    def set_optimizer_result_builds(
        self,
        rows: tuple[OptimizerResultBuildRow, ...],
    ) -> None:
        self.optimizer_result_builds.set_rows(rows)

    def set_optimizer_result_pages(
        self,
        pages: tuple[OptimizerResultPage, ...],
    ) -> None:
        self.optimizer_result_builds.set_pages(pages)

    def set_optimizer_build_save_result(
        self,
        wearer_key: str,
        *,
        success: bool,
        message: str,
    ) -> None:
        self.optimizer_result_builds.set_save_result(
            wearer_key,
            success=success,
            message=message,
        )

    def _start_optimizer_elapsed(self) -> None:
        self._optimizer_elapsed_terminal_stage = ""
        self._optimizer_elapsed_last_ms = 0
        self._optimizer_progress_value = 0
        self._optimizer_progress_sequence = -1
        self._optimizer_progress_animation.stop()
        self.optimizer_progress_bar.setRange(0, 100)
        self.optimizer_progress_bar.setValue(0)
        self.optimizer_progress_bar.setTextVisible(False)
        self._optimizer_elapsed_clock.start()
        self._optimizer_elapsed_tick.start()
        self._refresh_optimizer_elapsed()

    def _stop_optimizer_elapsed(self, stage: str) -> None:
        if self._optimizer_elapsed_clock.isValid():
            self._optimizer_elapsed_last_ms = max(
                self._optimizer_elapsed_last_ms,
                int(self._optimizer_elapsed_clock.elapsed()),
            )
        self._optimizer_elapsed_terminal_stage = str(stage)
        self._optimizer_elapsed_tick.stop()
        self._refresh_optimizer_elapsed()

    def _refresh_optimizer_elapsed(self) -> None:
        if not self._optimizer_elapsed_clock.isValid():
            self.optimizer_elapsed_label.clear()
            return
        elapsed_ms = self._optimizer_elapsed_last_ms
        if self._optimizer_elapsed_clock.isValid() and not self._optimizer_elapsed_terminal_stage:
            elapsed_ms = max(elapsed_ms, int(self._optimizer_elapsed_clock.elapsed()))
        elapsed = _format_optimizer_elapsed(elapsed_ms)
        if self._optimizer_elapsed_terminal_stage == "completed":
            template = _fallback(
                "gcsim.optimizer.elapsed_completed",
                "Completed in {elapsed}",
            )
        elif self._optimizer_elapsed_terminal_stage:
            template = _fallback(
                "gcsim.optimizer.elapsed_stopped",
                "Stopped after {elapsed}",
            )
        else:
            template = _fallback(
                "gcsim.optimizer.elapsed_running",
                "Running for {elapsed}",
            )
        self.optimizer_elapsed_label.setText(
            template.format(elapsed=elapsed)
        )

    def set_actions_busy(self, busy: bool, *, message: str = "") -> None:
        self._actions_busy = bool(busy)
        self.prepare_button.setEnabled(not busy)
        self.run_selected_button.setEnabled(not busy and not self._optimizer_busy and self._run_admitted)
        self.run_all_button.setEnabled(not busy and not self._optimizer_busy and self._mode == MODE_ABYSS and self._run_admitted)
        self.optimizer_selected_button.setEnabled(not busy and not self._restricted_build)
        self.optimizer_all_sets_button.setEnabled(not busy and self._optimizer_all_sets_available)
        self.optimizer_theory_button.setEnabled(not busy and self._optimizer_theory_available)
        if message:
            self._set_result_text(message)

    def set_run_admission(self, allowed: bool, *, message: str = "") -> None:
        self._run_admitted = bool(allowed) and not self._preparation_only
        self.set_actions_busy(self._actions_busy)
        install_custom_tooltip(self.run_selected_button, message)
        install_custom_tooltip(self.run_all_button, message)

    def set_prepare_result_text(self, text: str) -> None:
        self._set_result_text(
            text.strip()
            or _fallback("gcsim.browser.results_placeholder", "No prepare report.")
        )

    def _refresh_context(self) -> None:
        if not hasattr(self, "mode_context_label"):
            return
        self.refresh_rotation_team_context()
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
        finish_note = _fallback(
            "gcsim.optimizer.search_finished_by_user",
            "Search ended early: the best result found so far is shown.",
        )
        if finish_note in lines and finish_note not in summary:
            summary.append(finish_note)
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
    virtual_character_requested = Signal(str)
    virtual_weapon_requested = Signal(str)
    virtual_constellation_requested = Signal(int)
    virtual_refinement_requested = Signal(int)
    virtual_profile_requested = Signal(dict)
    virtual_set_bonuses_requested = Signal(list)
    virtual_clear_requested = Signal()

    def __init__(
        self,
        *,
        team_index: int,
        slot_index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.team_index = int(team_index)
        self.slot_index = int(slot_index)
        self._preview = GcsimBrowserTeamSlotPreview()
        self._override: GcsimVirtualSlotOverride | None = None
        self._draft = False
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.preview_widget = QWidget()
        preview_layout = QVBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(3)
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
            preview_layout.addWidget(label)

        self.activate_virtual_button = QPushButton()
        self.activate_virtual_button.setProperty("compact", True)
        self.activate_virtual_button.clicked.connect(self._begin_virtual_edit)
        preview_layout.addWidget(self.activate_virtual_button)
        layout.addWidget(self.preview_widget)

        self.virtual_editor = VirtualGcsimCardEditor()
        self.virtual_editor.character_requested.connect(
            self.virtual_character_requested.emit
        )
        self.virtual_editor.weapon_requested.connect(self.virtual_weapon_requested.emit)
        self.virtual_editor.constellation_requested.connect(
            self.virtual_constellation_requested.emit
        )
        self.virtual_editor.refinement_requested.connect(
            self.virtual_refinement_requested.emit
        )
        self.virtual_editor.profile_requested.connect(self.virtual_profile_requested.emit)
        self.virtual_editor.set_bonuses_requested.connect(
            self.virtual_set_bonuses_requested.emit
        )
        self.virtual_editor.clear_requested.connect(self.virtual_clear_requested.emit)
        self.virtual_editor.editing_cancelled.connect(self._cancel_virtual_edit)
        layout.addWidget(self.virtual_editor)

        self.set_preview(GcsimBrowserTeamSlotPreview())

    def set_virtual_catalogs(
        self,
        catalog: GcsimVirtualRosterCatalog,
        set_choices: tuple[GcsimVirtualArtifactSetChoice, ...],
    ) -> None:
        self.virtual_editor.set_catalogs(catalog, set_choices)

    def set_virtual_context(
        self,
        *,
        override: GcsimVirtualSlotOverride | None,
        artifact_builds: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._override = override
        if override is not None:
            self._draft = False
        self.virtual_editor.set_context(
            override=override,
            artifact_builds=artifact_builds,
        )
        self._refresh_mode()

    def set_preview(self, preview: GcsimBrowserTeamSlotPreview) -> None:
        self._preview = preview
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
        self._refresh_mode()

    def retranslate_ui(self) -> None:
        self.activate_virtual_button.setText(
            tr("gcsim.virtual_editor.activate")
        )
        self.virtual_editor.retranslate_ui()

    def _begin_virtual_edit(self) -> None:
        self._draft = True
        self._refresh_mode()
        QTimer.singleShot(0, self.virtual_editor.begin_editing)

    def _cancel_virtual_edit(self) -> None:
        self._draft = False
        self._refresh_mode()

    def _refresh_mode(self) -> None:
        editing = self._draft or self._override is not None
        self.preview_widget.setVisible(not editing)
        self.virtual_editor.setVisible(editing)


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


def _format_optimizer_elapsed(elapsed_ms: int) -> str:
    total_seconds = max(0, int(elapsed_ms) // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _optimizer_progress_value(stage: str, completed: int, total: int) -> int | None:
    """Map stage-local work to a coarse phase position, not a time estimate."""

    phases = {
        "loading_evidence": 0,
        "preparing_sources": 0,
        "validating_request": 1,
        "capturing_schedule": 1,
        "compiling_formula": 2,
        "searching": 3,
        "preparing_replacements": 4,
        "finalizing": 4,
        "validating_finalists": 5,
        "simulating_finalists": 5,
    }
    phase = phases.get(stage)
    if phase is None:
        return None
    phase_fraction = min(1.0, max(0.0, completed / total)) if total > 0 else 0.0
    return round(((phase + phase_fraction) / 6) * 99)


def _fallback(key: str, fallback: str) -> str:
    value = tr(key)
    return fallback if value == key else value
