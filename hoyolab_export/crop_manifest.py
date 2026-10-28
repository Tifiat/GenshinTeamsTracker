"""Legacy manifest name and stable account image identity helpers.

The screenshot crop engine was removed when the importer switched to direct
HoYoLAB image layers. Keep this small module for existing internal imports and
the versioned ``crop_manifest.json`` source-cache filename.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse


IGNORED_CHARACTER_IDS = {
    10000118,  # Mannequin (female)
    10000117,  # Mannequin (male)
}
IGNORED_WEAPON_RARITIES = {1, 2}


def icon_key(url: str | None) -> str:
    if not url:
        return ""
    return Path(urlparse(str(url)).path).name.lower()


def character_asset_key(character: dict[str, Any] | None) -> str:
    if not isinstance(character, dict):
        return ""
    character_id = character.get("id")
    element = character.get("element") or ""
    if character_id is not None:
        return f"id:{character_id}:element:{element}"
    keys = {icon_key(character.get("icon")), icon_key(character.get("side_icon"))} - {""}
    return f"icon:{sorted(keys)[0]}" if keys else ""


def weapon_asset_key(weapon_icon: str | None, weapon: dict[str, Any] | None = None) -> str:
    key = icon_key(weapon_icon)
    return key or (icon_key(weapon.get("icon")) if isinstance(weapon, dict) else "")
