"""Allowlisted, project-relative HoYoLAB card artwork shipped with the app.

These files are immutable package resources. Account manifests may reference
their relative names, but account cleanup must never own or remove them.
"""

from __future__ import annotations

from pathlib import Path


ELEMENT_ASSETS = {
    name: f"assets/filters/element_{name}.png"
    for name in ("anemo", "cryo", "dendro", "electro", "geo", "hydro", "pyro")
}
BACKGROUND_ASSETS = {
    rarity: f"assets/card_backgrounds/rarity_{rarity}.png"
    for rarity in (3, 4, 5)
}
BUNDLED_ASSET_PATHS = frozenset((*ELEMENT_ASSETS.values(), *BACKGROUND_ASSETS.values()))


def element_asset_relative(element: object) -> str | None:
    return ELEMENT_ASSETS.get(str(element or "").strip().lower())


def background_asset_relative(rarity: object) -> str | None:
    try:
        key = int(str(rarity).strip())
    except (TypeError, ValueError):
        return None
    return BACKGROUND_ASSETS.get(key)


def bundled_asset_path(value: object, *, project_root: Path) -> Path | None:
    """Resolve only a known shipped path, independent of the selected account."""
    if not isinstance(value, (str, Path)):
        return None
    relative = Path(value)
    if relative.is_absolute() or relative.as_posix() not in BUNDLED_ASSET_PATHS:
        return None
    path = project_root / relative
    try:
        path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def bundled_shared_assets(project_root: Path) -> dict[str, dict[str, str]]:
    """Manifest projection of existing shipped resources, including unused art."""
    available_elements = {
        element: relative for element, relative in ELEMENT_ASSETS.items()
        if bundled_asset_path(relative, project_root=project_root) is not None
    }
    available_backgrounds = {
        str(rarity): relative for rarity, relative in BACKGROUND_ASSETS.items()
        if bundled_asset_path(relative, project_root=project_root) is not None
    }
    return {
        "elements": available_elements,
        "characterBackgrounds": {
            rarity: relative for rarity, relative in available_backgrounds.items()
            if rarity in {"4", "5"}
        },
        "weaponBackgrounds": available_backgrounds,
    }
