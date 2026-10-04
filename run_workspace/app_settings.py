from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .settings_defaults import default_for, default_settings


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
    payload = json.dumps(settings, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def get_app_setting(
    key: str,
    default: Any = None,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> Any:
    settings = read_app_settings(settings_file)
    effective_default = default_for(key, settings_context=settings, fallback=default)
    return settings.get(key, effective_default)


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
    settings = read_app_settings(settings_file)
    effective_default = default_for(key, settings_context=settings, fallback=default)
    value = settings.get(key, effective_default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(effective_default)


def set_app_bool_setting(
    key: str,
    value: bool,
    *,
    settings_file: str | Path = SETTINGS_FILE,
) -> None:
    set_app_setting(key, bool(value), settings_file=settings_file)


def reset_app_settings(
    settings_file: str | Path = SETTINGS_FILE,
) -> dict[str, Any]:
    """Clear saved preferences and return the effective fresh defaults.

    Replacing the file with an empty object also clears obsolete or future
    suppression keys that are not part of the current defaults registry.
    """
    write_app_settings({}, settings_file)
    return default_settings()
