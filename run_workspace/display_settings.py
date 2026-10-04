from __future__ import annotations

from pathlib import Path

from run_workspace.app_settings import get_app_bool_setting, set_app_bool_setting
from run_workspace.settings_defaults import settings_default


USE_SYSTEM_SCALING_SETTING = "ui_use_system_scaling"
USE_SYSTEM_SCALING_DEFAULT = bool(settings_default(USE_SYSTEM_SCALING_SETTING))


def use_system_scaling(*, settings_file: str | Path | None = None) -> bool:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    return get_app_bool_setting(
        USE_SYSTEM_SCALING_SETTING, USE_SYSTEM_SCALING_DEFAULT, **kwargs
    )


def set_use_system_scaling(
    enabled: bool, *, settings_file: str | Path | None = None
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(USE_SYSTEM_SCALING_SETTING, enabled, **kwargs)
