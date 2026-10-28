from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = PROJECT_ROOT / "settings.json"


def read_app_settings(settings_file: str | Path = SETTINGS_FILE) -> dict[str, Any]:
    path = Path(settings_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_app_settings(
    settings: dict[str, Any],
    settings_file: str | Path = SETTINGS_FILE,
) -> None:
    path = Path(settings_file)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_app_setting(
    key: str,
    default: Any = None,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> Any:
    return read_app_settings(settings_file).get(key, default)


def set_app_setting(
    key: str,
    value: Any,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> None:
    data = read_app_settings(settings_file)
    data[str(key)] = value
    write_app_settings(data, settings_file)


def get_app_bool_setting(
    key: str,
    default: bool = False,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> bool:
    value = get_app_setting(key, default, settings_file=settings_file)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def set_app_bool_setting(
    key: str,
    value: bool,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> None:
    set_app_setting(key, bool(value), settings_file=settings_file)
