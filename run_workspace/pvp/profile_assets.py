"""Neutral, portable bitmap assets; account stats never enter these images."""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from hoyolab_export.asset_paths import character_variant_path
from run_workspace.profile_context import account_asset_path


ASSET_MANIFEST_NAME = "assets.json"
ASSET_MANIFEST_VERSION = 1
ASSET_MEMBER_PATTERN = re.compile(r"assets/[0-9a-f]{64}\.png\Z")
MAX_BITMAP_BYTES = 16 * 1024 * 1024
MAX_BITMAP_PIXELS = 2048 * 2048


class ProfileAssetError(ValueError):
    pass


def profile_asset_ids(db_path: Path) -> tuple[set[str], set[str]]:
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        characters = {str(row[0]) for row in conn.execute("SELECT character_id FROM account_characters")}
        weapons = {str(row[0]) for row in conn.execute("SELECT weapon_id FROM account_weapon_observed_stacks")}
    return characters, weapons


def build_profile_assets(
    source_db: Path,
    portable_db: Path,
    output_root: Path,
    *,
    character_paths: Mapping[str, str | Path] | None = None,
    weapon_paths: Mapping[str, str | Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Reuse transparent character source layers, never baked browser crops.

    Explicit character paths are the caller's neutral-asset boundary. Without
    them use the common `portrait` layer, not a background/element composite.
    """
    character_ids, weapon_ids = profile_asset_ids(portable_db)
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as conn:
        observed_paths = {
            str(row[0]): _source_path(row[1])
            for row in conn.execute("SELECT weapon_id, icon_path FROM account_weapon_observed_stacks ORDER BY weapon_fingerprint")
            if str(row[0]) in weapon_ids
        }
    maps: dict[str, dict[str, str]] = {"characters": {}, "weapons": {}}
    placeholders: dict[str, list[str]] = {"characters": [], "weapons": []}
    files: dict[str, Path] = {}
    for kind, ids, supplied in (
        ("characters", character_ids, character_paths),
        ("weapons", weapon_ids, weapon_paths),
    ):
        for game_id in sorted(ids):
            if supplied is not None and game_id in supplied:
                path = Path(supplied[game_id])
                if not path.is_file():
                    raise ProfileAssetError(f"Missing explicitly supplied {kind} asset: {game_id}")
            elif kind == "characters":
                path = character_variant_path(game_id, "portrait")
            else:
                path = observed_paths.get(game_id)
            if path is None or not path.is_file():
                placeholders[kind].append(game_id)
                color = (0, 0, 0, 0) if kind == "characters" else (62, 68, 78, 255)
                image = Image.new("RGBA", (72, 72), color)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                data = buffer.getvalue()
            else:
                data = _neutral_png(path)
            member = "assets/" + hashlib.sha256(data).hexdigest() + ".png"
            maps[kind][game_id] = member
            if member not in files:
                target = output_root / member
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                files[member] = target
    return {"schema_version": ASSET_MANIFEST_VERSION, **maps, "placeholders": placeholders}, files


def validate_profile_assets(
    payload: Mapping[str, Any],
    portable_db: Path,
    members: set[str],
    root: Path,
) -> tuple[dict[str, Path], dict[str, Path]]:
    if set(payload) != {"schema_version", "characters", "weapons", "placeholders"}:
        raise ProfileAssetError("Invalid PvP asset manifest fields.")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != ASSET_MANIFEST_VERSION:
        raise ProfileAssetError("Unsupported PvP asset manifest version.")
    expected = profile_asset_ids(portable_db)
    placeholders = payload["placeholders"]
    if not isinstance(placeholders, dict) or set(placeholders) != {"characters", "weapons"}:
        raise ProfileAssetError("Invalid PvP placeholder map.")
    referenced: set[str] = set()
    result = []
    for kind, ids in zip(("characters", "weapons"), expected):
        entries = payload[kind]
        if not isinstance(entries, dict) or set(entries) != ids:
            raise ProfileAssetError(f"PvP {kind} asset ids do not match the profile.")
        missing = placeholders[kind]
        if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing) or len(set(missing)) != len(missing) or not set(missing) <= ids:
            raise ProfileAssetError("Invalid PvP placeholder ids.")
        paths = {}
        for game_id, member in entries.items():
            if not isinstance(member, str) or not ASSET_MEMBER_PATTERN.fullmatch(member) or member not in members:
                raise ProfileAssetError("Missing or unsafe PvP bitmap reference.")
            paths[game_id] = root / member
            referenced.add(member)
        result.append(paths)
    if referenced != {name for name in members if name.startswith("assets/")}:
        raise ProfileAssetError("Unreferenced PvP bitmap member.")
    for member in referenced:
        path = root / member
        if path.stat().st_size > MAX_BITMAP_BYTES:
            raise ProfileAssetError("PvP bitmap exceeds the size limit.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != Path(member).stem:
            raise ProfileAssetError("PvP bitmap name does not match its content hash.")
        try:
            with Image.open(path) as bitmap:
                if bitmap.format != "PNG" or bitmap.mode != "RGBA" or bitmap.info or getattr(bitmap, "n_frames", 1) != 1:
                    raise ProfileAssetError("PvP bitmaps must be plain, single-frame RGBA PNGs.")
                _check_image_size(bitmap.size)
                bitmap.verify()
            with Image.open(path) as bitmap:
                bitmap.load()
                if bitmap.info:
                    raise ProfileAssetError("PvP bitmap metadata is not allowed.")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ProfileAssetError("Invalid PvP bitmap.") from exc
    return result[0], result[1]


def _neutral_png(path: Path) -> bytes:
    if path.stat().st_size > MAX_BITMAP_BYTES:
        raise ProfileAssetError("PvP bitmap exceeds the size limit.")
    try:
        with Image.open(path) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                raise ProfileAssetError("Unsupported PvP bitmap format.")
            _check_image_size(source.size)
            # Reconstruct pixels so EXIF, comments and local provenance vanish.
            image = Image.frombytes("RGBA", source.size, source.convert("RGBA").tobytes())
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProfileAssetError("Invalid PvP source bitmap.") from exc


def _check_image_size(size: tuple[int, int]) -> None:
    width, height = size
    if width <= 0 or height <= 0 or width > 2048 or height > 2048 or width * height > MAX_BITMAP_PIXELS:
        raise ProfileAssetError("PvP bitmap dimensions exceed the limit.")


def _source_path(value: object) -> Path | None:
    if not value:
        return None
    return account_asset_path(str(value))
