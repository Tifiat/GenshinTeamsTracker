from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ui.utils.pixel_icon_grid import (
    PixelIconGridFill,
    PixelIconGridItem,
    PixelIconGridOutline,
    PixelIconGridOverlayIcon,
)


@dataclass(frozen=True)
class AssetGridBuildResult:
    items: tuple[PixelIconGridItem, ...]
    assets_by_id: dict[str, dict[str, Any]]


def build_asset_grid_items(
    assets: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    key_for_asset: Callable[[dict[str, Any]], str],
    outline_for_asset: Callable[[dict[str, Any], str], PixelIconGridOutline | None] | None = None,
    overlay_fill_for_asset: Callable[[dict[str, Any], str], PixelIconGridFill | None] | None = None,
    overlay_icons_for_asset: Callable[[dict[str, Any], str], tuple[PixelIconGridOverlayIcon, ...]] | None = None,
    properties_for_asset: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> AssetGridBuildResult:
    items: list[PixelIconGridItem] = []
    assets_by_id: dict[str, dict[str, Any]] = {}
    used_keys: set[str] = set()
    for index, asset in enumerate(assets):
        item_id = _text(key_for_asset(asset))
        if not item_id:
            item_id = _fallback_item_id(asset, index)
        if item_id in used_keys:
            item_id = f"{item_id}#{index}"
        used_keys.add(item_id)
        assets_by_id[item_id] = dict(asset)
        items.append(
            PixelIconGridItem(
                item_id=item_id,
                icon_path=_text(asset.get("path")),
                label=_text(asset.get("filename")),
                tooltip=_text(asset.get("tooltip")),
                outline=(
                    outline_for_asset(asset, item_id)
                    if outline_for_asset is not None
                    else None
                ),
                overlay_fill=(
                    overlay_fill_for_asset(asset, item_id)
                    if overlay_fill_for_asset is not None
                    else None
                ),
                overlay_icons=(
                    overlay_icons_for_asset(asset, item_id)
                    if overlay_icons_for_asset is not None
                    else ()
                ),
                properties=(
                    properties_for_asset(asset, item_id)
                    if properties_for_asset is not None
                    else {}
                ),
            )
        )
    return AssetGridBuildResult(items=tuple(items), assets_by_id=assets_by_id)


def _fallback_item_id(asset: dict[str, Any], index: int) -> str:
    path = asset.get("path")
    if path:
        try:
            return f"path:{Path(path).resolve()}"
        except OSError:
            return f"path:{path}"
    filename = _text(asset.get("filename"))
    if filename:
        return f"filename:{filename}"
    return f"item:{index}"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
