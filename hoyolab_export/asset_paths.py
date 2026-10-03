"""Lightweight lookups for locally imported image layers and variants."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import HOYOLAB_DATA_DIR, PROJECT_ROOT


MANIFEST_PATH = HOYOLAB_DATA_DIR / "crop_manifest.json"


@lru_cache(maxsize=4)
def _read_manifest(mtime_ns: int, ctime_ns: int, size: int, file_id: int) -> dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def current_manifest() -> dict[str, Any]:
    try:
        stat = MANIFEST_PATH.stat()
    except OSError:
        return {}
    return _read_manifest(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)


def existing_manifest_asset(value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def character_variant_path(character_id: object, variant: str) -> Path | None:
    if variant not in {"crop", "pvp", "history", "portrait"}:
        raise ValueError("Unknown character image variant")
    wanted = str(character_id or "")
    for asset in current_manifest().get("characterAssets", []):
        if isinstance(asset, dict) and str((asset.get("character") or {}).get("id") or "") == wanted:
            return existing_manifest_asset(asset.get(variant))
    return None


def weapon_transparent_icon_path(weapon_id: object, display_path: str | Path) -> Path | None:
    """Reuse a raw layer only for the exact locally imported weapon bitmap."""
    wanted = str(weapon_id or "")
    displayed = Path(display_path)
    if not displayed.is_absolute():
        displayed = PROJECT_ROOT / displayed
    for asset in current_manifest().get("weaponAssets", []):
        if not isinstance(asset, dict) or str((asset.get("weapon") or {}).get("id") or "") != wanted:
            continue
        crop = existing_manifest_asset(asset.get("crop"))
        if crop is not None and crop.resolve() == displayed.resolve():
            return existing_manifest_asset(asset.get("icon"))
    return None


def element_icon_path(element: str) -> Path | None:
    shared = current_manifest().get("sharedAssets") or {}
    elements = shared.get("elements") or {}
    return existing_manifest_asset(elements.get(str(element or "").lower()))
