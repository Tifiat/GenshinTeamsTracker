"""Shared inventory selection frame; caller-owned portraits stay separate."""

from __future__ import annotations

from ui.utils.pixel_icon_grid import PixelIconGridOutline
from ui.utils.ui_palette import UI_INVENTORY_SELECTION_ACCENT


def inventory_selection_outline(*, selected: bool) -> PixelIconGridOutline | None:
    """Use the established PvP frame for equipped/selected inventory cards."""
    if not selected:
        return None
    return PixelIconGridOutline(
        color=UI_INVENTORY_SELECTION_ACCENT,
        width=2,
        radius=4,
        alpha=255,
    )
