"""Lightweight lookups for locally imported image layers and variants."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import HOYOLAB_DATA_DIR, PROJECT_ROOT
from run_workspace.profile_context import ACCOUNT_ROOT, account_asset_path


MANIFEST_PATH = HOYOLAB_DATA_DIR / "crop_manifest.json"


@dataclass
class _AssetLookupBatch:
    manifest: dict[str, Any] | None = None
    assets: dict[str, Path | None] = field(default_factory=dict)
    resolved: dict[Path, Path] = field(default_factory=dict)


_LOOKUP_BATCH: ContextVar[_AssetLookupBatch | None] = ContextVar("asset_lookup_batch", default=None)


@contextmanager
def asset_lookup_batch() -> Iterator[None]:
    """Reuse checks within one synchronous asset-list read, never across refreshes.

    Imports/profile changes must finish before reading UI assets. Thread-local
    context and finally-reset also keep another reader or a failed read fresh.
    """
    if _LOOKUP_BATCH.get() is not None:
        yield
        return
    token = _LOOKUP_BATCH.set(_AssetLookupBatch())
    try:
        yield
    finally:
        _LOOKUP_BATCH.reset(token)


def _resolved_path(path: Path) -> Path:
    batch = _LOOKUP_BATCH.get()
    if batch is None:
        return path.resolve()
    if path not in batch.resolved:
        batch.resolved[path] = path.resolve()
    return batch.resolved[path]


@lru_cache(maxsize=4)
def _read_manifest(mtime_ns: int, ctime_ns: int, size: int, file_id: int) -> dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def current_manifest() -> dict[str, Any]:
    batch = _LOOKUP_BATCH.get()
    if batch is not None and batch.manifest is not None:
        return batch.manifest
    try:
        stat = MANIFEST_PATH.stat()
    except OSError:
        manifest = {}
    else:
        manifest = _read_manifest(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    if batch is not None:
        batch.manifest = manifest
    return manifest


def existing_manifest_asset(value: object) -> Path | None:
    if not value:
        return None
    batch = _LOOKUP_BATCH.get()
    key = str(value)
    if batch is not None and key in batch.assets:
        return batch.assets[key]
    result = _existing_manifest_asset(key)
    if batch is not None:
        batch.assets[key] = result
    return result


def _existing_manifest_asset(value: str) -> Path | None:
    path = Path(str(value))
    if not path.is_absolute():
        path = account_asset_path(path)
    try:
        _resolved_path(path).relative_to(_resolved_path(ACCOUNT_ROOT))
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
        if crop is not None and _resolved_path(crop) == _resolved_path(displayed):
            return existing_manifest_asset(asset.get("icon"))
    return None


def element_icon_path(element: str) -> Path | None:
    shared = current_manifest().get("sharedAssets") or {}
    elements = shared.get("elements") or {}
    return existing_manifest_asset(elements.get(str(element or "").lower()))
