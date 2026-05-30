from __future__ import annotations

# Shared dark UI palette for new/reworked widgets.
# Existing legacy QSS blocks may still contain literal colors; migrate them only
# when touching those areas for real UI work.

UI_BG_APP = "#17191f"
UI_BG_PANEL = "#1f222a"
UI_BG_BUTTON = "#222630"
UI_BG_BUTTON_HOVER = "#2b303b"
UI_BG_BUTTON_CHECKED = "#303848"
UI_BG_FILTER_IDLE = "transparent"
UI_BG_FILTER_HOVER = "rgba(78, 145, 255, 0.10)"
UI_BG_FILTER_CHECKED = "rgba(78, 145, 255, 0.14)"

UI_BORDER_PANEL = "#2b3039"
UI_BORDER_DEFAULT = "#3d4350"
UI_BORDER_SELECTED = "#7da7ff"
UI_BORDER_FILTER_SELECTED = "#4e91ff"

UI_TEXT_PRIMARY = "#eeeeee"
