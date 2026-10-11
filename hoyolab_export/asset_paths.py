"""Lightweight lookups for locally imported image layers and variants."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .bundled_assets import background_asset_relative, bundled_asset_path, element_asset_relative
from .paths import HOYOLAB_DATA_DIR, PROJECT_ROOT
from run_workspace.profile_context import ACCOUNT_ROOT, account_asset_path


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
        bundled = bundled_asset_path(path, project_root=PROJECT_ROOT)
        if bundled is not None:
            return bundled
        # A missing or unlisted package resource cannot resolve through an
        # account directory, including the legacy project-root account.
        if path.parts[:2] in {("assets", "filters"), ("assets", "card_backgrounds")}:
            return None
        path = account_asset_path(path)
    try:
        path.resolve().relative_to(ACCOUNT_ROOT.resolve())
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
        displayed = account_asset_path(displayed)
    for asset in current_manifest().get("weaponAssets", []):
        if not isinstance(asset, dict) or str((asset.get("weapon") or {}).get("id") or "") != wanted:
            continue
        crop = existing_manifest_asset(asset.get("crop"))
        if crop is not None and crop.resolve() == displayed.resolve():
            return existing_manifest_asset(asset.get("icon"))
    return None


def element_icon_path(element: str) -> Path | None:
    return bundled_asset_path(element_asset_relative(element), project_root=PROJECT_ROOT)


def character_background_path(rarity: int) -> Path | None:
    return bundled_asset_path(background_asset_relative(rarity), project_root=PROJECT_ROOT)
