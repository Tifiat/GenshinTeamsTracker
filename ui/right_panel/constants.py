from __future__ import annotations

from ui.right_panel.common.metrics import RIGHT_PANEL_PROTOTYPE_MIN_WIDTH

RIGHT_OPERATIONS_DOCK_WIDTH = RIGHT_PANEL_PROTOTYPE_MIN_WIDTH
RIGHT_DOCK_PAGE_RUN = "run"
RIGHT_DOCK_PAGE_ACCOUNT = "account"
RIGHT_DOCK_PAGE_HISTORY = "history"
RIGHT_DOCK_PAGE_PVP = "pvp"
RIGHT_DOCK_POLICY_RUN = "run"
RIGHT_DOCK_POLICY_HISTORY = "history"
RIGHT_DOCK_POLICY_PVP = "pvp"
RIGHT_DOCK_ACCOUNT_ICON_SIZE = 18

__all__ = [name for name in globals() if name.startswith("RIGHT_")]
