from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT


HOYOWIKI_CHARACTER_LIST_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"
CHARACTER_REGION_CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "hoyowiki" / "character_region_catalog.json"
CHARACTER_REGION_MENU_ID = "2"
CHARACTER_REGION_CACHE_SCHEMA_VERSION = 1
CHARACTER_REGION_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
USER_AGENT = "GenshinTeamsTracker/1.0"

REGION_ORDER = [
    "mond",
    "liyue",
    "inazuma",
    "sumeru",
    "fontaine",
    "natlan",
    "nod_krai",
    "snezhnaya",
    "other",
]

REGION_ICON_FILES = {
    "mond": "mond.png",
    "liyue": "liyue.png",
    "inazuma": "inazuma.png",
    "sumeru": "sumeru.png",
    "fontaine": "fontaine.png",
    "natlan": "natlan.png",
    "nod_krai": "Nod-Krai.png",
    "snezhnaya": "snezhnaya.png",
    "other": "Map.png",
}

REGION_LABEL_KEYS = {
    "mond": "filter.region.mond",
    "liyue": "filter.region.liyue",
    "inazuma": "filter.region.inazuma",
    "sumeru": "filter.region.sumeru",
    "fontaine": "filter.region.fontaine",
    "natlan": "filter.region.natlan",
    "nod_krai": "filter.region.nod_krai",
    "snezhnaya": "filter.region.snezhnaya",
    "other": "filter.region.other",
}

_REGION_ALIASES = {
    "mond": "mond",
    "mondstadt": "mond",
    "monstadt": "mond",
    "монд": "mond",
    "мондштадт": "mond",
    "liyue": "liyue",
    "li yue": "liyue",
    "ли юэ": "liyue",
    "inazuma": "inazuma",
    "инадзума": "inazuma",
    "sumeru": "sumeru",
    "сумеру": "sumeru",
    "fontaine": "fontaine",
    "фонтейн": "fontaine",
    "natlan": "natlan",
    "натлан": "natlan",
    "nod krai": "nod_krai",
    "nod-krai": "nod_krai",
    "nod_krai": "nod_krai",
    "нод край": "nod_krai",
    "нод-край": "nod_krai",
    "snezhnaya": "snezhnaya",
    "снежная": "snezhnaya",
    "other": "other",
    "outro": "other",
    "другое": "other",
}


def normalize_language(language: str | None) -> str:
    value = str(language or "").strip().replace("_", "-").lower()
    if not value or value == "en":
        return "en-us"
    return value


def normalize_character_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_region_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = text.replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    alias = _REGION_ALIASES.get(text)
    if alias:
        return alias

    slug = re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")
    return slug or "other"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_cache(path: Path = CHARACTER_REGION_CACHE_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": CHARACTER_REGION_CACHE_SCHEMA_VERSION,
            "source": "hoyowiki",
            "languages": {},
        }


def _write_cache(cache: dict[str, Any], path: Path = CHARACTER_REGION_CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _language_cache_is_fresh(language_cache: dict[str, Any]) -> bool:
    fetched_at = float(language_cache.get("fetched_at_unix") or 0)
    return time.time() - fetched_at < CHARACTER_REGION_CACHE_MAX_AGE_SECONDS


def _extract_region_values(item: dict[str, Any]) -> list[str]:
    filter_values = item.get("filter_values") or {}
    region = filter_values.get("character_region") or {}
    values = region.get("values") or []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _catalog_entry_from_item(item: dict[str, Any], *, language: str) -> dict[str, Any] | None:
    name = str(item.get("name") or "").strip()
    entry_page_id = str(item.get("entry_page_id") or "").strip()
    regions = _extract_region_values(item)
    region_name = regions[0] if regions else ""
    region_key = normalize_region_key(region_name)

    if not name or not entry_page_id:
        return None

    return {
        "entry_page_id": entry_page_id,
        "name": name,
        "normalized_name": normalize_character_name(name),
        "region_key": region_key,
        "region_name": region_name,
        "lang": language,
    }


def fetch_hoyowiki_character_regions(language: str) -> list[dict[str, Any]]:
    language = normalize_language(language)
    result: list[dict[str, Any]] = []
    page_num = 1
    page_size = 30

    while True:
        body = json.dumps(
            {
                "filters": [],
                "menu_id": CHARACTER_REGION_MENU_ID,
                "page_num": page_num,
                "page_size": page_size,
                "use_es": True,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            HOYOWIKI_CHARACTER_LIST_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Referer": "https://wiki.hoyolab.com",
                "x-rpc-language": language,
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("retcode") != 0:
            raise RuntimeError(
                f"HoYoWiki retcode={payload.get('retcode')} message={payload.get('message')}"
            )

        data = payload.get("data") or {}
        items = data.get("list") or []
        for item in items:
            if isinstance(item, dict):
                entry = _catalog_entry_from_item(item, language=language)
                if entry is not None:
                    result.append(entry)

        total = int(data.get("total") or len(result))
        if len(result) >= total or not items:
            break
        page_num += 1

    return result


def load_character_region_catalog(
    language: str,
    *,
    allow_network: bool = True,
    cache_path: Path = CHARACTER_REGION_CACHE_PATH,
) -> list[dict[str, Any]]:
    language = normalize_language(language)
    cache = _read_cache(cache_path)
    languages = cache.setdefault("languages", {})
    language_cache = languages.get(language) or {}

    cached_entries = list(language_cache.get("entries") or [])
    if cached_entries and _language_cache_is_fresh(language_cache):
        return cached_entries

    if not allow_network:
        return cached_entries

    try:
        entries = fetch_hoyowiki_character_regions(language)
    except Exception as exc:
        print(f"[Character Region Catalog] Could not update {language}: {exc}")
        return cached_entries

    languages[language] = {
        "source": "hoyowiki",
        "lang": language,
        "fetched_at": _utc_now(),
        "fetched_at_unix": time.time(),
        "entries": entries,
    }
    cache["schema_version"] = CHARACTER_REGION_CACHE_SCHEMA_VERSION
    cache["source"] = "hoyowiki"
    _write_cache(cache, cache_path)
    return entries
