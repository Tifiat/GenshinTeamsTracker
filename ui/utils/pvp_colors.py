from __future__ import annotations

import re
from pathlib import Path

from run_workspace.app_settings import SETTINGS_FILE, get_app_setting, set_app_setting
from run_workspace.settings_defaults import settings_default


PVP_PLAYER_1_COLOR_DEFAULT = str(settings_default("pvp_player_1_color"))
PVP_PLAYER_2_COLOR_DEFAULT = str(settings_default("pvp_player_2_color"))
PVP_PLAYER_COLOR_DEFAULTS = {
    "player_1": PVP_PLAYER_1_COLOR_DEFAULT,
    "player_2": PVP_PLAYER_2_COLOR_DEFAULT,
}
PVP_PLAYER_COLOR_SETTING_KEYS = {
    "player_1": "pvp_player_1_color",
    "player_2": "pvp_player_2_color",
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_color_cache: dict[tuple[str, str], str] = {}


def pvp_player_color(
    seat: str,
    *,
    settings_file: str | Path | None = None,
) -> str:
    normalized_seat = _normalized_seat(seat)
    # Most callers are card builders/paint paths. Resolve the filesystem only
    # on a cache miss, not once per badge on every click or repaint.
    requested_path = Path(settings_file or SETTINGS_FILE).absolute()
    cache_key = (str(requested_path), normalized_seat)
    cached = _color_cache.get(cache_key)
    if cached is not None:
        return cached
    path = requested_path.resolve()
    value = _normalize_color(
        get_app_setting(
            PVP_PLAYER_COLOR_SETTING_KEYS[normalized_seat],
            PVP_PLAYER_COLOR_DEFAULTS[normalized_seat],
            settings_file=path,
        ),
        fallback=PVP_PLAYER_COLOR_DEFAULTS[normalized_seat],
    )
    _color_cache[cache_key] = value
    return value


def set_pvp_player_color(
    seat: str,
    color: str,
    *,
    settings_file: str | Path | None = None,
) -> str:
    normalized_seat = _normalized_seat(seat)
    path = Path(settings_file or SETTINGS_FILE).resolve()
    value = _normalize_color(
        color,
        fallback=PVP_PLAYER_COLOR_DEFAULTS[normalized_seat],
    )
    set_app_setting(
        PVP_PLAYER_COLOR_SETTING_KEYS[normalized_seat],
        value,
        settings_file=path,
    )
    # A relative path or junction may have populated another key for this file.
    # Writes are rare; invalidate aliases rather than returning an old colour.
    _color_cache.clear()
    _color_cache[(str(path), normalized_seat)] = value
    return value


def reset_pvp_player_colors(
    *,
    settings_file: str | Path | None = None,
) -> tuple[str, str]:
    values = tuple(
        set_pvp_player_color(
            seat,
            PVP_PLAYER_COLOR_DEFAULTS[seat],
            settings_file=settings_file,
        )
        for seat in ("player_1", "player_2")
    )
    return values[0], values[1]


def _normalized_seat(seat: str) -> str:
    value = str(seat or "").strip()
    if value not in PVP_PLAYER_COLOR_DEFAULTS:
        raise ValueError(f"Unsupported PvP seat: {seat!r}")
    return value


def _normalize_color(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text.lower() if _HEX_COLOR.fullmatch(text) else fallback


__all__ = [
    "PVP_PLAYER_1_COLOR_DEFAULT",
    "PVP_PLAYER_2_COLOR_DEFAULT",
    "PVP_PLAYER_COLOR_DEFAULTS",
    "PVP_PLAYER_COLOR_SETTING_KEYS",
    "pvp_player_color",
    "reset_pvp_player_colors",
    "set_pvp_player_color",
]
