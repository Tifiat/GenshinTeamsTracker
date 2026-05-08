from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from .models import ArtifactItem
from .store import ArtifactBrowserStore


class ArtifactRoles:
    ArtifactIdRole = Qt.ItemDataRole.UserRole + 1
    ArtifactRole = Qt.ItemDataRole.UserRole + 2


class ArtifactListModel(QAbstractListModel):
    def __init__(self, store: ArtifactBrowserStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.artifact_ids: list[int] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.artifact_ids)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row < 0 or row >= len(self.artifact_ids):
            return None

        artifact_id = self.artifact_ids[row]
        artifact = self.store.artifact(artifact_id)

        if role == ArtifactRoles.ArtifactIdRole:
            return artifact_id

        if role == ArtifactRoles.ArtifactRole:
            return artifact

        if role == Qt.ItemDataRole.DisplayRole:
            return artifact.name

        return None

    def set_store(self, store: ArtifactBrowserStore) -> None:
        self.beginResetModel()
        self.store = store
        self.artifact_ids = []
        self.endResetModel()

    def set_artifact_ids(self, artifact_ids: list[int]) -> None:
        self.beginResetModel()
        self.artifact_ids = list(artifact_ids)
        self.endResetModel()

    def artifact_at(self, row: int) -> ArtifactItem | None:
        if row < 0 or row >= len(self.artifact_ids):
            return None
        return self.store.artifact(self.artifact_ids[row])