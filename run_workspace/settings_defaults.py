"""Central defaults for keys stored in the application settings file.

Add every new persistent application setting to ``DEFAULT_SETTINGS`` so reset
and first-read behavior stay in one place. Caller-provided defaults remain a
compatibility fallback for settings keys unknown to this registry.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "ui_language": "ru",
    "ui_use_system_scaling": False,
    "hoyolab_change_equipment_on_import": True,
    "hoyolab_login_hint_dismissed": False,
    "abyss_fact_dps_multi_target_enabled": False,
    "gcsim_boosted_energy_enabled": False,
    "gcsim_optimizer_fast_mode": False,
    "gcsim_optimizer_expanded_limits": False,
    "gcsim_optimizer_set_group_limit": 3,
    "gcsim_optimizer_builds_per_group": 3,
    "pvp_player_1_color": "#42d9f5",
    "pvp_player_2_color": "#d9f25c",
}

_DYNAMIC_OPTIMIZER_LIMITS = {
    "gcsim_optimizer_set_group_limit",
    "gcsim_optimizer_builds_per_group",
}
_FAST_OPTIMIZER_LIMITS = {
    "gcsim_optimizer_set_group_limit": 5,
    "gcsim_optimizer_builds_per_group": 21,
}


def _boolean(value: object, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def default_for(
    key: str,
    settings_context: Mapping[str, Any] | None = None,
    fallback: Any = None,
) -> Any:
    """Return a fresh default, resolving dependent defaults from settings.

    Optimizer output limits follow fast mode: 3/3 in normal mode and 5/21 in
    fast mode. The context is the current settings mapping, when available.
    """
    setting_key = str(key)
    if setting_key in DEFAULT_SETTINGS:
        if setting_key in _DYNAMIC_OPTIMIZER_LIMITS:
            context = settings_context or {}
            fast_default = bool(DEFAULT_SETTINGS["gcsim_optimizer_fast_mode"])
            fast_mode = _boolean(
                context.get("gcsim_optimizer_fast_mode", fast_default),
                fast_default,
            )
            if fast_mode:
                return _FAST_OPTIMIZER_LIMITS[setting_key]
            return deepcopy(DEFAULT_SETTINGS[setting_key])
        return deepcopy(DEFAULT_SETTINGS[setting_key])
    return deepcopy(fallback)


def settings_default(
    key: str,
    context: Mapping[str, Any] | None = None,
    fallback: Any = None,
) -> Any:
    """Named public wrapper for resolving a setting's central default."""
    return default_for(key, settings_context=context, fallback=fallback)


def default_settings() -> dict[str, Any]:
    """Return an independent map of defaults for a fresh settings file."""
    result = deepcopy(DEFAULT_SETTINGS)
    for key in _DYNAMIC_OPTIMIZER_LIMITS:
        result[key] = default_for(key, settings_context=result)
    return result


__all__ = [
    "DEFAULT_SETTINGS",
    "default_for",
    "default_settings",
    "settings_default",
]
