from __future__ import annotations

from pathlib import Path

from run_workspace.app_settings import get_app_bool_setting, set_app_bool_setting


ABYSS_FACT_DPS_MULTI_TARGET_SETTING = "abyss_fact_dps_multi_target_enabled"


def is_abyss_fact_dps_multi_target_enabled(
    *,
    settings_file: str | Path | None = None,
) -> bool:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    return get_app_bool_setting(
        ABYSS_FACT_DPS_MULTI_TARGET_SETTING,
        False,
        **kwargs,
    )


def set_abyss_fact_dps_multi_target_enabled(
    enabled: bool,
    *,
    settings_file: str | Path | None = None,
) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(
        ABYSS_FACT_DPS_MULTI_TARGET_SETTING,
        bool(enabled),
        **kwargs,
    )
