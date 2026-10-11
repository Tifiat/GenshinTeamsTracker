"""Presentation layers for neutral portraits; never generates account bitmaps."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
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
    layer_path_cache: MutableMapping[tuple[str, str], str] | None = None,
    background_path: str | None = None,
    element_icon_path: str | None = None,
) -> PixelIconGridItem:
    rarity = metadata_int(character.get("rarity"))
    colors = UI_CHARACTER_RARITY_BACKGROUNDS.get(rarity)
    background = None
    if colors is not None:
        rarity_key = ("character_background", str(rarity))
        icon_path = background_path if background_path is not None else (
            layer_path_cache.get(rarity_key)
            if layer_path_cache is not None and rarity_key in layer_path_cache
            else None
        )
        if icon_path is None:
            path = character_background_path(rarity)
            icon_path = str(path) if path else ""
            if layer_path_cache is not None:
                layer_path_cache[rarity_key] = icon_path
        if background_path != "":
            background = PixelIconGridBackground(*colors, icon_path=icon_path)
    element = str(character.get("element") or "").strip().lower()
    overlays = item.overlay_icons
    if element in UI_ELEMENT_ACCENTS:
        element_key = ("element_icon", element)
        icon_path = element_icon_path if element_icon_path is not None else (
            layer_path_cache.get(element_key)
            if layer_path_cache is not None and element_key in layer_path_cache
            else None
        )
        if icon_path is None:
            icon_path = str(filter_icon_path(f"element_{element}.png"))
            if layer_path_cache is not None:
                layer_path_cache[element_key] = icon_path
        if icon_path:
            overlays += (PixelIconGridOverlayIcon(
                icon_path=icon_path,
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
