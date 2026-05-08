from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .card_delegate import ArtifactCardDelegate, GRID_SIZE
from .list_model import ArtifactListModel
from .models import ARTIFACT_POSITIONS
from .store import ArtifactBrowserStore


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
QListView::item {
    background: transparent;
}
"""


class ArtifactBrowserWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle("Артефакты")
        self.resize(1180, 760)
        self.setStyleSheet(WINDOW_STYLE)

        self.current_pos = 1
        self.store = ArtifactBrowserStore.load_from_db()
        self.model = ArtifactListModel(self.store, self)
        self.delegate = ArtifactCardDelegate(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_top_bar(root)
        self._build_list_view(root)
        self._build_bottom_bar(root)

        self.load_position(1)

    def _build_top_bar(self, root: QVBoxLayout) -> None:
        top_frame = QFrame()
        top_frame.setObjectName("top_bar")

        top = QHBoxLayout(top_frame)
        top.setContentsMargins(8, 8, 8, 8)
        top.setSpacing(6)

        self.slot_group = QButtonGroup(self)
        self.slot_group.setExclusive(True)

        for pos, label in ARTIFACT_POSITIONS.items():
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=pos: self.load_position(value))
            self.slot_group.addButton(button, pos)
            top.addWidget(button)

            if pos == 1:
                button.setChecked(True)

        top.addStretch()

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
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)

        root.addWidget(self.list_view, 1)

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("status_label")
        bottom.addWidget(self.empty_label)

        bottom.addStretch()

        close_button = QPushButton("Закрыть")
        close_button.setObjectName("close_button")
        close_button.clicked.connect(self.close)
        bottom.addWidget(close_button)

        root.addLayout(bottom)

    def load_position(self, pos: int) -> None:
        self.current_pos = pos

        if not self.store.database_exists:
            self.model.set_artifact_ids([])
            self.status_label.setText("База артефактов не найдена")
            self.empty_label.setText("Сначала импортируйте данные из HoYoLAB.")
            return

        artifact_ids = self.store.ids_for_position(pos)
        self.model.set_artifact_ids(artifact_ids)

        slot_name = ARTIFACT_POSITIONS[pos]
        count = len(artifact_ids)

        self.status_label.setText(f"{slot_name}: {count}")
        self.empty_label.setText("" if count else "Артефакты не найдены.")

    def reload_from_database(self) -> None:
        self.store = ArtifactBrowserStore.load_from_db()
        self.model.set_store(self.store)
        self.load_position(self.current_pos)