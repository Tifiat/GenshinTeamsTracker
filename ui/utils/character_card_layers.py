"""Presentation layers for neutral portraits; never generates account bitmaps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from hoyolab_export.asset_paths import character_background_path
from ui.character_assets import filter_icon_path, metadata_int
from ui.utils.pixel_icon_grid import (
    PixelIconGridBackground,
    PixelIconGridBadge,
    PixelIconGridItem,
    PixelIconGridOverlayIcon,
)
from ui.utils.ui_palette import (
    UI_BG_PANEL,
    UI_CHARACTER_RARITY_BACKGROUNDS,
    UI_ELEMENT_ACCENTS,
)


def with_character_card_layers(
    item: PixelIconGridItem,
    character: Mapping[str, Any],
    *,
    show_constellation: bool = True,
) -> PixelIconGridItem:
    rarity = metadata_int(character.get("rarity"))
    colors = UI_CHARACTER_RARITY_BACKGROUNDS.get(rarity)
    background = None
    if colors is not None:
        path = character_background_path(rarity)
        background = PixelIconGridBackground(*colors, icon_path=str(path) if path else "")
    element = str(character.get("element") or "").strip().lower()
    overlays = item.overlay_icons
    if element in UI_ELEMENT_ACCENTS:
        overlays += (PixelIconGridOverlayIcon(
            icon_path=str(filter_icon_path(f"element_{element}.png")),
            size_ratio=72 / 296,
            right_overhang_ratio=-8 / 72,
            top_overhang_ratio=-8 / 72,
            position="top_left",
        ),)
    badges = item.badges
    constellation = character.get("constellation")
    if show_constellation and constellation is not None:
        badges += (PixelIconGridBadge(
            text=f"C{metadata_int(constellation)}",
            color=UI_BG_PANEL,
            position="top_right",
            width=24,
            height=18,
            margin=2,
            font_size=8,
        ),)
    return replace(item, background=background, overlay_icons=overlays, badges=badges)
