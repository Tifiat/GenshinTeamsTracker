import json
import os
from pathlib import Path
from typing import Any


LOCALES_DIR = Path(__file__).resolve().parent / "locales"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = PROJECT_ROOT / "settings.json"
DEFAULT_LANGUAGE = "ru"
LANGUAGE_OPTIONS = [
    ("ru", "🇷🇺 Русский"),
    ("en", "🇺🇸 English"),
    ("pt-br", "🇧🇷 Português"),
]
_catalog_cache: dict[str, dict[str, str]] = {}


def _normalize_language(language: str | None) -> str:
    value = (language or DEFAULT_LANGUAGE).strip().lower().replace("_", "-")
    if not value:
        return DEFAULT_LANGUAGE

    aliases = {
        "pt": "pt-br",
        "pt-br": "pt-br",
        "br": "pt-br",
    }
    value = aliases.get(value, value)

    supported = {code for code, _label in LANGUAGE_OPTIONS}
    if value in supported:
        return value

    base = value.split("-", 1)[0]
    return aliases.get(base, base if base in supported else DEFAULT_LANGUAGE)


def _read_settings_language() -> str | None:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    value = data.get("ui_language")
    return str(value) if value else None


def _write_settings_language(language: str) -> None:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    data["ui_language"] = _normalize_language(language)
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _initial_language() -> str:
    env_language = os.environ.get("GTT_LANGUAGE") or os.environ.get("GTT_LANG")
    if env_language:
        return _normalize_language(env_language)
    return _normalize_language(_read_settings_language())


_language = _initial_language()


def _load_catalog(language: str) -> dict[str, str]:
    language = _normalize_language(language)
    if language in _catalog_cache:
        return _catalog_cache[language]

    path = LOCALES_DIR / f"{language}.json"
    if not path.exists() and language != DEFAULT_LANGUAGE:
        path = LOCALES_DIR / f"{DEFAULT_LANGUAGE}.json"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    catalog = {str(key): str(value) for key, value in data.items()}
    _catalog_cache[language] = catalog
    return catalog


def available_languages() -> list[str]:
    if not LOCALES_DIR.exists():
        return [DEFAULT_LANGUAGE]
    languages = sorted(path.stem for path in LOCALES_DIR.glob("*.json"))
    return languages or [DEFAULT_LANGUAGE]


def language_options() -> list[tuple[str, str]]:
    available = set(available_languages())
    return [(code, label) for code, label in LANGUAGE_OPTIONS if code in available]


def set_language(language: str, *, persist: bool = False) -> None:
    global _language
    normalized = _normalize_language(language)
    _language = normalized if normalized in available_languages() else DEFAULT_LANGUAGE
    if persist:
        _write_settings_language(_language)


def get_language() -> str:
    return _normalize_language(_language)


def tr(key: str, **kwargs: Any) -> str:
    language = get_language()
    catalog = _load_catalog(language)
    fallback = _load_catalog(DEFAULT_LANGUAGE)
    text = catalog.get(key) or fallback.get(key) or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return text
