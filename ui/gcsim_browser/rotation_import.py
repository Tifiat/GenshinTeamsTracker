"""Public database picker. Network work never runs on the GUI thread."""

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from localization import tr
from run_workspace.gcsim.rotation_database import DatabaseMember, rank_records, search_team
from run_workspace.gcsim.rotation_import import RotationImportError, prepare_rotation
from run_workspace.gcsim.rotation_editor import parse
from run_workspace.gcsim.rotation_editor.readable import render


class SearchWorker(QThread):
    result = Signal(object)

    def __init__(self, keys, parent=None, search=search_team):
        super().__init__(parent)
        self.keys, self.search = keys, search

    def run(self):
        self.result.emit(self.search(self.keys, cancelled=self.isInterruptionRequested))

    def stop(self):
        self.requestInterruption()
        self.wait()


def plain_label(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class RotationImportDialog(QDialog):
    chosen = Signal(str)

    def __init__(self, team, environment, shell, *, names=None, catalog=None,
                 set_choices=(), parent=None, search=search_team):
        super().__init__(parent)
        self.setWindowTitle(tr("rotation.import.title"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(1100, 780)
        self.team, self.environment, self.shell = team, environment, shell
        self.names = names or {}
        self.characters = {item.gcsim_key: item for item in catalog.characters} if catalog else {}
        self.weapons = {item.gcsim_key: item.display_name for item in catalog.weapons} if catalog else {}
        self.set_names = {item.gcsim_key: item.display_name for item in set_choices}
        self.desired = tuple(DatabaseMember(item.key, item.constellation, item.weapon, item.refinement) for item in team.members)
        self.records, self.prepared = (), None
        layout = QVBoxLayout(self)
        self.status = plain_label(tr("rotation.import.searching"))
        layout.addWidget(self.status)
        layout.addWidget(plain_label(tr("rotation.import.order")))
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)
        self.results = QListWidget()
        self.results.setMinimumHeight(160)
        self.results.currentRowChanged.connect(self._preview)
        splitter.addWidget(self.results)
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        self.description, self.readable, self.code, self.original = (QPlainTextEdit() for _ in range(4))
        for widget, key in ((self.description, "description"), (self.readable, "readable"),
                            (self.code, "code"), (self.original, "original")):
            widget.setReadOnly(True)
            self.tabs.addTab(widget, tr("rotation.import." + key))
        self.notice = plain_label("")
        layout.addWidget(self.notice)
        buttons = QHBoxLayout()
        self.load_button = QPushButton(tr("rotation.import.load"))
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self._choose)
        close = QPushButton(tr("rotation.import.close"))
        close.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.load_button)
        layout.addLayout(buttons)
        self.worker = SearchWorker(team.keys, self, search)
        self.worker.result.connect(self._received)
        # Closing the picker cancels at the next page boundary. Its retained
        # owner keeps the worker alive until the bounded request completes.
        QApplication.instance().aboutToQuit.connect(self.worker.stop)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        QApplication.instance().aboutToQuit.disconnect(self.worker.stop)

    def reject(self):
        self.worker.requestInterruption()
        super().reject()

    def _received(self, result):
        self.records = rank_records(result.records, self.desired)
        key = "rotation.import.found" if result.complete else "rotation.import.partial"
        if not self.records:
            key = "rotation.import.empty" if result.complete else "rotation.import.failed"
        self.status.setText(tr(key, count=len(self.records)))
        for record in self.records:
            desired = {member.key: member for member in self.desired}
            same_cons = all(member.constellation is not None and member.constellation == desired[member.key].constellation for member in record.members)
            same_weapons = all(member.weapon is not None and member.weapon == desired[member.key].weapon for member in record.members)
            match = tr("rotation.import.exact" if same_cons and same_weapons else "rotation.import.weapons" if same_cons else "rotation.import.constellations")
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.addWidget(plain_label(match + " · " + record.id))
            cards = QHBoxLayout()
            texts = []
            by_key = {member.key: member for member in record.members}
            for key in self.team.keys:
                member = by_key[key]
                cons = "?" if member.constellation is None else str(member.constellation)
                refine = "?" if member.refinement is None else str(member.refinement)
                sets = ", ".join(f"{self.set_names.get(key, key)} ×{count}" for key, count in member.sets.items()) or "—"
                text = f"{self.names.get(member.key, member.key)} C{cons}\n{self.weapons.get(member.weapon, member.weapon) or '?'} R{refine}\n{sets}"
                texts.append(text)
                card = QWidget()
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(0, 0, 0, 0)
                entry = self.characters.get(member.key)
                if entry and entry.icon_path:
                    picture = QPixmap(entry.icon_path)
                    if not picture.isNull():
                        icon = QLabel()
                        icon.setPixmap(picture.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        card_layout.addWidget(icon)
                card_layout.addWidget(plain_label(text), 1)
                cards.addWidget(card, 1)
            row_layout.addLayout(cards)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.AccessibleTextRole, match + " " + " | ".join(texts))
            item.setSizeHint(row.sizeHint())
            self.results.addItem(item)
            self.results.setItemWidget(item, row)
        if self.records:
            self.results.setCurrentRow(0)

    def _preview(self, index):
        self.prepared = None
        self.load_button.setEnabled(False)
        if not 0 <= index < len(self.records):
            return
        record = self.records[index]
        self.description.setPlainText(record.description or tr("rotation.import.no_description"))
        self.original.setPlainText(record.config)
        self.code.clear()
        self.readable.clear()
        try:
            self.prepared = prepare_rotation(record.config, self.shell, self.environment.dialect, self.team.keys)
        except (RotationImportError, ValueError, RecursionError) as error:
            self.notice.setText(tr(str(error)) if isinstance(error, RotationImportError) else tr("rotation.import.syntax"))
            return
        self.code.setPlainText(self.prepared.source)
        document = parse(self.prepared.program, self.environment.dialect)
        self.readable.setPlainText(render(document, tr, resolve_name=self.names.get).compact_text())
        self.notice.setText("\n".join(tr(key) for key in self.prepared.notices))
        self.load_button.setEnabled(True)

    def _choose(self):
        if self.prepared is not None:
            self.chosen.emit(self.prepared.source)

