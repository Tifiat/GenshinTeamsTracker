from pathlib import Path

from run_workspace.app_settings import get_app_bool_setting, set_app_bool_setting
from .account_equipment import AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT


CHANGE_EQUIPMENT_SETTING = "hoyolab_change_equipment_on_import"


def change_equipment_on_import(*, settings_file: str | Path | None = None) -> bool:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    return get_app_bool_setting(
        CHANGE_EQUIPMENT_SETTING, AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT, **kwargs
    )


def set_change_equipment_on_import(enabled: bool, *, settings_file: str | Path | None = None) -> None:
    kwargs = {} if settings_file is None else {"settings_file": settings_file}
    set_app_bool_setting(CHANGE_EQUIPMENT_SETTING, enabled, **kwargs)
