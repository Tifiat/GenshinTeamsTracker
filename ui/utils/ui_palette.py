from __future__ import annotations

# Shared semantic colors for new/reworked UI.
# Existing legacy QSS blocks may still contain literal colors; migrate them only
# when touching those areas for real UI work.

# Base surfaces
UI_BG_APP = "#17191f"
UI_BG_PANEL = "#1f222a"
UI_BG_PANEL_RAISED = "#222630"
UI_BG_INSET = "#15181d"
UI_BG_BUTTON = "#222630"
UI_BG_BUTTON_HOVER = "#2b303b"
UI_BG_BUTTON_CHECKED = "#303848"

# Filter controls
UI_BG_FILTER_IDLE = "transparent"
UI_BG_FILTER_HOVER = "rgba(78, 145, 255, 0.10)"
UI_BG_FILTER_CHECKED = "rgba(78, 145, 255, 0.14)"

# Borders
UI_BORDER_PANEL = "#2b3039"
UI_BORDER_DEFAULT = "#3d4350"
UI_BORDER_SELECTED = "#7da7ff"
UI_BORDER_FILTER_SELECTED = "#4e91ff"

# Text
UI_TEXT_PRIMARY = "#eeeeee"
UI_TEXT_SECONDARY = "#dce5f7"
UI_TEXT_MUTED = "#aab0bd"
UI_TEXT_ON_ACCENT = "#ffffff"

# Semantic states
UI_ACCENT_TEAM_1 = "#3ed47b"
UI_ACCENT_TEAM_2 = "#4e91ff"
UI_STATE_SUCCESS = "#56c779"
UI_STATE_DANGER = "#b85b5b"

# Specialized reusable UI visuals
UI_EQUIPPED_WEAPON_ACCENT = UI_STATE_SUCCESS
UI_BG_FOREIGN_EQUIPPED = "#2d2327"
UI_BG_FOREIGN_EQUIPPED_HOVER = "#38272d"
UI_BORDER_FOREIGN_EQUIPPED = UI_STATE_DANGER
