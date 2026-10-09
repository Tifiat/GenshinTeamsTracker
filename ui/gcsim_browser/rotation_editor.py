"""Separate rotation workspace using the shared source-linked editor tree."""

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from localization import tr
from run_workspace.gcsim.rotation_editor import CodeGenerationError, Node, node
from run_workspace.gcsim.rotation_editor.conditions import PROFILE, actor_token, make_if, make_while
from run_workspace.gcsim.rotation_editor.context import context_for
from run_workspace.gcsim.rotation_editor.editing import Selection, insert, move, remove, wrap
from run_workspace.gcsim.rotation_editor.model import action
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.semantics import analyze, make_cycle, make_schedule
from run_workspace.gcsim.rotation_editor.session import EditorSession
from run_workspace.gcsim.rotation_editor.team import validate_team
from run_workspace.gcsim.rotation_editor.writer import Writer
from ui.gcsim_browser.rotation_properties import ConditionControl, ScheduleControl, VariantControl, combo
from ui.utils import ui_palette as palette


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def label(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class BlockButton(QPushButton):
    def __init__(self, text):
        super().__init__()
        self.setAccessibleName(text)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        caption = label(text)
        caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(caption)


class RotationEditorWindow(QWidget):
    applied = Signal(str)
    reload_requested = Signal()
    MAX_VISIBLE_BLOCKS = 400

    def __init__(self, source, dialect, *, names=None, character_options=None, allowed_actors=(), parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("RotationEditorWindow")
        self.setWindowTitle(tr("rotation.editor.title"))
        self.resize(1250, 820)
        self.setMinimumSize(800, 520)
        self.session = EditorSession(source, dialect, allowed_actors=allowed_actors, character_options=character_options or {})
        self.names = {dialect.character_aliases.get(key, key): (names or {}).get(dialect.character_aliases.get(key, key), key)
                      for key in allowed_actors if key in dialect.character_aliases or key in dialect.character_aliases.values()}
        self.display_names = names or {}
        self.character_options = character_options or {}
        self.selection = None
        self.selected_actor = ""
        self._property_mode = "selection"
        self._buttons = []
        self._updating = False
        self._visible_count = 0
        self._message = ""
        self._apply_block_reason = ""
        self._draft_incomplete = False
        self._navigation = []
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.undo_button = QPushButton(tr("rotation.editor.undo"))
        self.redo_button = QPushButton(tr("rotation.editor.redo"))
        self.delete_button = QPushButton(tr("rotation.editor.delete"))
        self.up_button, self.down_button = QPushButton("↑"), QPushButton("↓")
        self.apply_button = QPushButton(tr("rotation.editor.apply"))
        self.reload_button = QPushButton(tr("rotation.editor.reload"))
        self.reload_button.clicked.connect(self.reload_requested.emit)
        for button in (self.undo_button, self.redo_button, self.delete_button, self.up_button, self.down_button):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.reload_button)
        toolbar.addWidget(self.apply_button)
        layout.addLayout(toolbar)
        self.status = label("")
        layout.addWidget(self.status)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        self.readable_scroll = QScrollArea()
        self.readable_scroll.setWidgetResizable(True)
        self.document_panel = QWidget()
        self.document_layout = QVBoxLayout(self.document_panel)
        self.document_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.readable_scroll.setWidget(self.document_panel)
        self.tabs.addTab(self.readable_scroll, tr("rotation.editor.readable"))
        self.code = QPlainTextEdit()
        self.code.setUndoRedoEnabled(False)
        self.tabs.addTab(self.code, tr("rotation.editor.code"))
        self.side = QWidget()
        self.side.setMinimumWidth(300)
        side_layout = QVBoxLayout(self.side)
        splitter.addWidget(self.side)
        splitter.setSizes([840, 360])
        self.commands_title = label(tr("rotation.editor.commands"))
        side_layout.addWidget(self.commands_title)
        self.commands_scroll = QScrollArea()
        self.commands_scroll.setWidgetResizable(True)
        commands_panel = QWidget()
        self.commands_layout = QVBoxLayout(commands_panel)
        self.commands_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.commands_scroll.setWidget(commands_panel)
        side_layout.addWidget(self.commands_scroll, 1)
        side_layout.addWidget(label(tr("rotation.editor.properties")))
        self.properties_scroll = QScrollArea()
        self.properties_scroll.setWidgetResizable(True)
        properties_panel = QWidget()
        self.properties_layout = QVBoxLayout(properties_panel)
        self.properties_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.properties_scroll.setWidget(properties_panel)
        side_layout.addWidget(self.properties_scroll, 2)
        self.property_status = label("")
        side_layout.addWidget(self.property_status)
        self.details = QCheckBox(tr("rotation.editor.details"))
        side_layout.addWidget(self.details)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.flush_code)
        self.code.textChanged.connect(self._code_changed)
        self.tabs.currentChanged.connect(lambda _: self.flush_code())
        self.undo_button.clicked.connect(lambda: self._history(False))
        self.redo_button.clicked.connect(lambda: self._history(True))
        self.delete_button.clicked.connect(self.delete_selection)
        self.up_button.clicked.connect(lambda: self.move_selection(-1))
        self.down_button.clicked.connect(lambda: self.move_selection(1))
        self.apply_button.clicked.connect(self.apply)
        self.details.toggled.connect(self._toggle_details)
        for sequence, callback in ((QKeySequence.StandardKey.Undo, lambda: self._history(False)),
                                   (QKeySequence.StandardKey.Redo, lambda: self._history(True))):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        self.setStyleSheet(f"""
            QWidget#RotationEditorWindow {{ background: {palette.UI_BG_APP}; color: {palette.UI_TEXT_PRIMARY}; }}
            QFrame[rotationBlock=true] {{ background: {palette.UI_BG_PANEL}; border: 1px solid {palette.UI_BORDER_DEFAULT}; border-radius: 6px; }}
            QFrame[emptySlot=true] {{ background: {palette.UI_BG_FOREIGN_EQUIPPED}; border: 1px solid {palette.UI_STATE_DANGER}; border-radius: 6px; }}
            QPushButton {{ padding: 7px; text-align: left; }}
            QPushButton:checked {{ background: {palette.UI_BG_BUTTON_CHECKED}; border: 1px solid {palette.UI_BORDER_SELECTED}; }}
        """)
        self.refresh()

    def _button(self, text, callback, target):
        button = QPushButton(text)
        button.clicked.connect(lambda checked=False: callback())
        target.addWidget(button)
        return button

    def set_message(self, text):
        self._message = text
        self.status.setText(text)
        self.property_status.setText(text)

    def block_apply(self, reason):
        self._apply_block_reason = reason
        self._message = reason
        if self.flush_code():
            self.refresh()

    def set_team(self, actors, names):
        aliases = self.session.current.dialect.character_aliases
        self.session.allowed_actors = frozenset(aliases.get(key, key) for key in actors)
        self.names = {aliases.get(key, key): names.get(aliases.get(key, key), names.get(key, key))
                      for key in actors if aliases.get(key, key) in aliases.values()}
        self.display_names = names
        if self.selected_actor not in self.names:
            self.selected_actor = ""
            self._navigation.clear()
        if self.flush_code():
            self.refresh()

    def _code_changed(self):
        if not self._updating:
            self.apply_button.setEnabled(False)
            self.timer.start()

    def _toggle_details(self):
        if self.flush_code():
            self.refresh()

    def flush_code(self):
        if not self.timer.isActive() and self.code.toPlainText() == self.session.code_text():
            return True
        if self._draft_incomplete:
            return True
        self.timer.stop()
        try:
            source = self.code.toPlainText()
            if source != self.session.code_text():
                self.session.set_code(source)
                self.selection = None
                self.refresh()
        except (ValueError, RecursionError) as error:
            self.set_message(tr("rotation.editor.error", reason=str(error)))
            self.apply_button.setEnabled(False)
            return False
        return True

    def refresh(self):
        self._updating = True
        try:
            code = self.session.code_text()
            self._draft_incomplete = code is None
            with QSignalBlocker(self.code):
                if self.code.toPlainText() != (code or ""):
                    self.code.setPlainText(code or "")
                self.code.setReadOnly(code is None)
                self.code.setPlaceholderText(tr("rotation.editor.unfilled_code") if code is None else "")
            clear(self.document_layout)
            self._buttons.clear()
            self._visible_count = 0
            readable = render(self.session.current, tr, resolve_name=self.display_names.get)
            views = readable.items + (readable.details if self.details.isChecked() else ())
            for view in views:
                self._view(view, self.document_layout)
            if self.selection:
                match = next((selection for selection, _ in self._buttons if selection.node_id == self.selection.node_id
                              and (not self.selection.kind or selection.kind == self.selection.kind)), None)
                if match is not None:
                    self.selection = match
                elif not any(item.node_id == self.selection.node_id for item in self.session.current.root.walk()):
                    self.selection = None
            self._button(tr("rotation.editor.new_command"), self.select_end, self.document_layout)
            self.document_layout.addStretch(1)
            self.undo_button.setEnabled(self.session.can_undo)
            self.redo_button.setEnabled(self.session.can_redo)
            membership_errors = validate_team(self.session.current, self.session.allowed_actors)
            self.apply_button.setEnabled(self.session.current.syntax_complete and bool(self.names) and not membership_errors and not self._apply_block_reason)
            self.set_message(self._apply_block_reason or (tr("rotation.editor.unfilled_code") if code is None else
                tr("rotation.editor.syntax_issue") if not self.session.current.syntax_complete else
                tr("rotation.editor.team_empty") if not self.names else
                tr("rotation.editor.team_outside") if membership_errors else self._message))
            self._selection_changed()
        finally:
            self._updating = False

    def _view(self, view, target):
        self._visible_count += 1
        if self._visible_count > self.MAX_VISIBLE_BLOCKS:
            if self._visible_count == self.MAX_VISIBLE_BLOCKS + 1:
                target.addWidget(label(tr("rotation.editor.large_document")))
            return
        if view.kind == "diagnostic":
            target.addWidget(label(view.text))
            return
        box = QFrame()
        box.setProperty("rotationBlock", True)
        current = self.session.current.find(view.node_id)
        box.setProperty("emptySlot", view.kind == "hole" or any(child.kind == "hole" for child in current.children()))
        contents = QVBoxLayout(box)
        contents.setContentsMargins(8, 6, 8, 6)
        header = QHBoxLayout()
        select = BlockButton(view.text)
        select.setCheckable(True)
        selection = Selection.from_view(view)
        select.clicked.connect(lambda: self.select(selection, view.actor_key))
        self._buttons.append((selection, select))
        header.addWidget(select, 1)
        if view.kind not in {"branch", "hole", "unreachable"}:
            delete = QPushButton("×")
            delete.setFixedWidth(28)
            delete.clicked.connect(lambda: self.delete_selection(selection))
            header.addWidget(delete)
        contents.addLayout(header)
        for child in view.children:
            self._view(child, contents)
        if current.kind in {"block", "case_body"} or view.kind in {"cycle", "if", "while", "for", "schedule", "window"}:
            # The branch's own placeholder is the explicit destination for
            # else/nested insertions, rather than guessing from visible prose.
            self._button(tr("rotation.editor.add_here"), lambda: self.select(selection, view.actor_key), contents)
        target.addWidget(box)

    def select(self, selection, actor=None):
        if not self.flush_code():
            return
        self.selection = selection
        self._property_mode = "selection"
        if actor:
            self.selected_actor = actor
        self._selection_changed()

    def select_end(self):
        self.select(None)

    def _selection_changed(self):
        action_selection = False
        if self.selection:
            try:
                selected = self.session.current.find(self.selection.node_id)
                action_selection = selected.kind == "action"
                actor = context_for(self.session.current, self.selection.node_id).actor_key
                if actor and self._property_mode != "character":
                    self.selected_actor = actor if actor in self.names else ""
            except (StopIteration, KeyError):
                self.selection = None
        for selection, button in self._buttons:
            button.setChecked(self.selection == selection)
        self.delete_button.setEnabled(self.selection is not None and self.selection.kind not in {"hole", "branch", "unreachable"})
        self.up_button.setEnabled(self.selection is not None and self.selection.kind not in {"hole", "branch", "window", "unreachable"})
        self.down_button.setEnabled(self.up_button.isEnabled())
        clear(self.properties_layout)
        if self._property_mode == "character" and self.selected_actor in self.names:
            self._actor_actions()
            self._commands()
            return
        if self.selected_actor in self.names and not action_selection:
            self._actor_actions()
        if self.selection is None:
            self.properties_layout.addWidget(label(tr("rotation.editor.select_hint")))
            active = [item for item in self.session.current.root.get("items") if item.kind == "active"]
            token = active[-1].get("actor").get("value") if active else ""
            initial = self.session.current.dialect.character_aliases.get(token, token)
            self.properties_layout.addWidget(label(tr("rotation.editor.initial_actor")))
            actor = combo([(tr("rotation.editor.character"), "")] + [(text, key) for key, text in self.names.items()], initial)
            self.properties_layout.addWidget(actor)
            def set_initial():
                statement = node("active", actor=node("name", value=actor_token(self.session.current, actor.currentData())))
                if active:
                    self.session.replace(active[-1].node_id, statement)
                else:
                    self.session.edit_structure(insert, None, statement)
            selected_document = self.session.current
            self._button(tr("rotation.editor.set_initial_actor"), lambda: self._do(set_initial,
                expected_document=selected_document), self.properties_layout)
        else:
            try:
                selected_document = self.session.current
                context = context_for(self.session.current, self.selection.node_id)
                if context.actor_key and context.actor_key not in self.names:
                    self.selected_actor = ""
                for prop in context.properties:
                    self.properties_layout.addWidget(label(tr(prop.label_key)))
                    for key in prop.note_keys:
                        self.properties_layout.addWidget(label(tr(key)))
                    self._property(prop)
                if context.source:
                    source = QPlainTextEdit(context.source)
                    source.setReadOnly(True)
                    source.setMaximumHeight(130)
                    self.properties_layout.addWidget(source)
                if not context.properties:
                    self.properties_layout.addWidget(label(tr("rotation.editor.selected_block")))
                current = self.session.current.find(self.selection.node_id)
                if current.kind == "if":
                    otherwise = current.get("otherwise")
                    self._button(tr("rotation.editor.remove_else" if otherwise else "rotation.editor.add_else"),
                        lambda: self._do(lambda: self.session.replace(current.node_id,
                            current.changed(otherwise=None if otherwise else node("hole", slot="body"))), expected_document=selected_document), self.properties_layout)
            except (KeyError, StopIteration, ValueError, CodeGenerationError):
                self.selection = None
                self.properties_layout.addWidget(label(tr("rotation.editor.select_hint")))
        if self.selected_actor in self.names and action_selection:
            self._actor_actions()
        self._commands()

    def _property(self, prop):
        if not prop.editable:
            if isinstance(prop.value, Node):
                text = Writer(self.session.current).emit(prop.value)
            else:
                text = str(prop.value)
            self.properties_layout.addWidget(label(text + "\n" + tr("rotation.editor.detailed_only")))
            return
        if prop.editor == "integer":
            # QSpinBox is int32. Keep the full core range through a validated
            # decimal input; never clamp an imported count to a UI maximum.
            control = QLineEdit(str(prop.value))
            read = lambda: int(control.text())
        elif prop.editor == "condition":
            control = ConditionControl(self.names, prop.value)
            read = control.value
        elif prop.editor == "rotation_schedule":
            control = ScheduleControl(prop.value)
            read = control.value
        elif prop.editor == "action_variant":
            descriptor = self.character_options.get(self.selected_actor)
            actions = {item.name for item in descriptor.actions if not item.invalid} if descriptor else set()
            parameters = {(item.action, item.key) for item in descriptor.parameters} if descriptor else set()
            choices = tuple(item for item in prop.choices if item.action in actions and
                            (not item.parameter or (item.action, item.parameter) in parameters))
            if not choices:
                self.properties_layout.addWidget(label(tr("rotation.editor.options_missing")))
                return
            control = VariantControl(choices)
            read = control.value
        else:
            self.properties_layout.addWidget(label(tr("rotation.editor.detailed_only")))
            return
        self.properties_layout.addWidget(control)
        node_id = self.selection.node_id
        selected_document = self.session.current
        self._button(tr("rotation.editor.change"), lambda: self._do(lambda: self._edit_property(node_id, prop.key, read()),
            expected_document=selected_document), self.properties_layout)

    def _edit_property(self, node_id, key, value):
        self.session.edit_option(node_id, key, value)
        if key == "variant":
            self.set_message(tr("rotation.editor.variant_applied"))

    def _commands(self):
        clear(self.commands_layout)
        if self._navigation:
            self._button(tr("rotation.editor.back"), self._back, self.commands_layout)
        page = self._navigation[-1] if self._navigation else "root"
        if page == "characters":
            for key, text in self.names.items():
                self._button(text, lambda key=key: self._choose_actor(key), self.commands_layout)
            if not self.names:
                self.commands_layout.addWidget(label(tr("rotation.editor.team_empty")))
        elif page == "cycles":
            self._button(tr("rotation.editor.add_cycle"), lambda: self.add_statement(lambda: make_cycle(self.session.current, 4)), self.commands_layout)
            self._button(tr("rotation.editor.forever"), lambda: self.add_statement(lambda: make_cycle(self.session.current, None)), self.commands_layout)
            if self.selection:
                meaning = analyze(self.session.current)
                cycle = meaning.cycles.get(self.selection.node_id) or next(meaning.ancestor_cycles(self.selection.node_id), None)
                if cycle and cycle.counter:
                    schedule = ScheduleControl()
                    self.commands_layout.addWidget(schedule)
                    self._button(tr("rotation.editor.add_schedule"), lambda: self._do(lambda: self.session.edit_structure(insert, self.selection,
                        make_schedule(self.session.current, cycle.node_id, schedule.value()))), self.commands_layout)
                self._button(tr("rotation.editor.wrap_cycle"), lambda: self._do(lambda: self.session.edit_structure(wrap, self.selection,
                    make_cycle(self.session.current, 4))), self.commands_layout)
        elif page == "conditions":
            if self.session.current.dialect.identity == PROFILE:
                self._button(tr("rotation.editor.add_if"), lambda: self.add_statement(lambda: make_if(self.session.current)), self.commands_layout)
                self._button(tr("rotation.editor.add_while"), lambda: self.add_statement(lambda: make_while(self.session.current)), self.commands_layout)
            else:
                self.commands_layout.addWidget(label(tr("rotation.editor.generic_profile")))
            if self.selection:
                if self.session.current.dialect.identity == PROFILE:
                    self._button(tr("rotation.editor.wrap_if"), lambda: self._do(lambda: self.session.edit_structure(wrap, self.selection,
                        make_if(self.session.current))), self.commands_layout)
        elif page == "other":
            self.wait_amount = QSpinBox()
            self.wait_amount.setRange(1, 1000000)
            self.wait_amount.setValue(60)
            self.commands_layout.addWidget(label(tr("rotation.editor.wait_frames")))
            self.commands_layout.addWidget(self.wait_amount)
            self._button(tr("rotation.editor.add_wait"), lambda: self.add_statement(node("expression_stmt", value=node("call", function=node("name", value="wait"),
                arguments=(node("number", value=str(self.wait_amount.value())),)))), self.commands_layout)
        else:
            for key, page_name in (("characters", "characters"), ("cycles", "cycles"), ("conditions", "conditions"), ("other", "other")):
                self._button(tr("rotation.editor.page." + key), lambda page_name=page_name: self._navigate(page_name), self.commands_layout)

    def _actor_actions(self):
        self.properties_layout.addWidget(label(tr("rotation.editor.actions_for", actor=self.names[self.selected_actor])))
        metadata = self.character_options.get(self.selected_actor)
        documented = {item.name for item in metadata.actions if not item.invalid} if metadata and metadata.origin != "unavailable" else set()
        if not documented:
            self.properties_layout.addWidget(label(tr("rotation.editor.options_missing")))
        for name in ("skill", "burst", "attack", "charge", "aim", "dash", "jump", "high_plunge", "low_plunge", "walk", "swap"):
            if name in documented and name in self.session.current.dialect.actions:
                self._button(tr("rotation.action." + name), lambda name=name: self.add_statement(action(actor_token(self.session.current, self.selected_actor), name)), self.properties_layout)

    def _navigate(self, page):
        self._navigation.append(page)
        self._commands()

    def _back(self):
        self._navigation.pop()
        self._commands()

    def _choose_actor(self, key):
        if key not in self.names:
            self.set_message(tr("rotation.editor.team_outside"))
            return
        self.selected_actor = key
        self._property_mode = "character"
        self._selection_changed()

    def add_statement(self, statement):
        def edit():
            fresh = statement() if callable(statement) else statement
            self.session.edit_structure(insert, self.selection, fresh)
            self._property_mode = "selection"
            self.selection = Selection(fresh.get("actions")[0].node_id, "action") if fresh.kind == "action_line" else Selection(fresh.node_id)
        self._do(edit)

    def _do(self, operation, *, expected_document=None):
        before, had_selection = self.session.current, self.selection is not None
        if not self.flush_code():
            return
        if ((expected_document is not None and self.session.current is not expected_document)
                or (had_selection and self.session.current is not before)):
            self.set_message(tr("rotation.editor.code_updated"))
            return
        if any(item.severity == "error" for item in self.session.current.diagnostics) or any(
                item.kind == "unknown" for item in self.session.current.root.walk()):
            self.set_message(tr("rotation.editor.syntax_issue"))
            return
        try:
            self._message = ""
            operation()
            self.refresh()
            if self.selection and self.session.current.find(self.selection.node_id).kind == "action":
                self.properties_scroll.verticalScrollBar().setValue(0)
        except (ValueError, KeyError, StopIteration, RecursionError) as error:
            reason = tr("rotation.editor.team_outside") if str(error) == "rotation.team.outside" else tr("rotation.editor.team_empty") if str(error) == "rotation.team.empty" else str(error)
            self.set_message(tr("rotation.editor.error", reason=reason))

    def delete_selection(self, selection=None):
        selected = selection or self.selection
        if selected:
            def edit():
                meaning = analyze(self.session.current)
                selected_node = self.session.current.find(selected.node_id)
                ancestors = tuple(meaning.ancestors(selected.node_id))
                self.session.edit_structure(remove, selected)
                self.selection = None
                for ancestor in ancestors:
                    if ancestor.kind in {"action_line", "block", "case_body", "document"}:
                        try:
                            retained = self.session.current.find(ancestor.node_id)
                        except StopIteration:
                            continue
                        if retained.kind == "action_line":
                            self.selection = Selection(retained.get("actions")[-1].node_id, "action")
                        elif retained.kind != "document":
                            self.selection = Selection(retained.node_id, "branch" if selected_node.kind == "action" else "")
                        break
            self._do(edit)

    def move_selection(self, direction):
        if self.selection:
            self._do(lambda: self.session.edit_structure(move, self.selection, direction))

    def _history(self, redo):
        if not self.flush_code():
            return
        self.timer.stop()
        previous = self.selection
        ancestors = tuple(analyze(self.session.current).ancestors(previous.node_id)) if previous else ()
        self.session.redo() if redo else self.session.undo()
        self.selection = None
        for candidate in ((self.session.current.find(previous.node_id),) if previous and any(item.node_id == previous.node_id for item in self.session.current.root.walk()) else ancestors):
            if any(item.node_id == candidate.node_id for item in self.session.current.root.walk()) and candidate.kind != "document":
                self.selection = Selection(candidate.node_id, previous.kind if previous and candidate.node_id == previous.node_id else "")
                break
        self._message = ""
        self.refresh()

    def apply(self):
        def publish():
            if self._apply_block_reason:
                raise ValueError(self._apply_block_reason)
            self.session.commit(character_options=self.character_options, require_options=True)
            self.applied.emit(self.session.code_text())
            self.selection = None
        self._do(publish)

    def closeEvent(self, event):
        self.flush_code()
        super().closeEvent(event)
