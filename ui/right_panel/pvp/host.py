from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ui.right_panel.pvp._shared import PVP_PAGE_DECKS, PVP_PAGE_DRAFT, PVP_PAGE_PLAY
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


class PvpRightPanelHost(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.decks_panel = PvpDecksRightPanel(workspace.decks_workspace)
        self.play_panel = PvpPlayRightPanel(workspace)
        self.draft_panel = PvpDraftRightPanel(workspace)
        self.stack.addWidget(self.decks_panel)
        self.stack.addWidget(self.play_panel)
        self.stack.addWidget(self.draft_panel)
        self.workspace.page_changed.connect(self._sync_page_from_workspace)
        self.set_page(workspace.active_page_id)

    def set_page(self, page_id: str) -> None:
        self.workspace.set_page(page_id)
        self._sync_page_from_workspace(self.workspace.active_page_id)

    def current_page(self) -> str:
        return self.workspace.active_page_id

    def retranslate_ui(self) -> None:
        self.decks_panel.retranslate_ui()
        self.play_panel.retranslate_ui()
        self.draft_panel.retranslate_ui()

    def _sync_page_from_workspace(self, page_id: str) -> None:
        if page_id == PVP_PAGE_PLAY:
            widget = self.play_panel
        elif page_id == PVP_PAGE_DRAFT:
            widget = self.draft_panel
        else:
            widget = self.decks_panel
        self.stack.setCurrentWidget(widget)


__all__ = ["PvpRightPanelHost"]
