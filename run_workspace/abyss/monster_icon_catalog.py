"""Nanoka's general monster catalog for icon-only enemy enrichment."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from urllib.parse import urljoin, urlparse
from typing import Any

from run_workspace.abyss.source_data import (
    MANUAL_ALIAS_PAIRS,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
    _normalize_enemy_name,
    rebuild_abyss_floor_source_data_with_rows,
)
from run_workspace.abyss.source_data_fetchers import (
    AbyssSourceFetchError,
    NANOKA_ICON_BASE,
    NANOKA_SITE_BASE,
    _FetchedDataUrlParser,
    _fetch_json,
    _fetch_text,
)


NanokaMonsterIconCatalog = dict[str, tuple[str, ...]]

NANOKA_MONSTER_PAGE_URL = f"{NANOKA_SITE_BASE}/monster"
NANOKA_STATIC_ROOT = "https://static.nanoka.cc/"
NANOKA_STATIC_HOST = "static.nanoka.cc"
FETCH_TIMEOUT_SECONDS = 20

_ICON_KEY_RE = re.compile(r"[A-Za-z0-9_]+\Z")
_VERSIONED_JSON_PATH_RE = re.compile(
    r"/gi/(?P<version>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<document>tower|monster)\.json\Z"
)

_ICON_NAME_ALIASES: dict[str, str] = {
    fandom_name: nanoka_name
    for (fandom_name, nanoka_name) in MANUAL_ALIAS_PAIRS
}
_ICON_NAME_ALIASES.update(
    {
        _normalize_enemy_name("Battle-Hardened Chimeric Burrowbeast"):
            _normalize_enemy_name("Chimeric Burrowbeast"),
        _normalize_enemy_name("Battle-Hardened Fireblade Shock Trooper"):
            _normalize_enemy_name("Oprichniki Fireblade Shock Trooper"),
    }
)


def parse_nanoka_monster_icon_catalog(payload: Mapping[str, Any]) -> NanokaMonsterIconCatalog:
    """Build normalized-name entries from Nanoka's monster.json object."""

    if not isinstance(payload, Mapping):
        raise AbyssSourceFetchError("Expected a Nanoka monster catalog JSON object.")

    urls_by_name: dict[str, set[str]] = defaultdict(set)
    for monster in payload.values():
        if not isinstance(monster, Mapping):
            continue
        english_name = monster.get("en")
        icon_key = monster.get("icon")
        if not isinstance(english_name, str) or not english_name.strip():
            continue
        if not isinstance(icon_key, str) or _ICON_KEY_RE.fullmatch(icon_key) is None:
            continue
        normalized_name = _normalize_enemy_name(english_name)
        if not normalized_name:
            continue
        urls_by_name[normalized_name].add(f"{NANOKA_ICON_BASE}/{icon_key}.webp")

    catalog = {
        normalized_name: tuple(sorted(icon_urls))
        for normalized_name, icon_urls in urls_by_name.items()
    }
    if not catalog:
        raise AbyssSourceFetchError(
            "Nanoka monster catalog contained no safe English name/icon entries."
        )
    return catalog


def _versioned_nanoka_json_url(url: str, *, expected_document: str) -> tuple[str, str] | None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError):
        return None

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != NANOKA_STATIC_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None

    match = _VERSIONED_JSON_PATH_RE.fullmatch(parsed.path)
    if match is None or match.group("document") != expected_document:
        return None
    return match.group("version"), match.group("document")


def _monster_json_url_from_manifest(manifest_url: str) -> str:
    versioned_path = _versioned_nanoka_json_url(
        manifest_url,
        expected_document="tower",
    )
    if versioned_path is None:
        raise AbyssSourceFetchError(
            "Nanoka tower manifest URL must be an HTTPS static.nanoka.cc "
            "versioned /gi/<version>/tower.json URL."
        )
    version, _document = versioned_path
    return f"https://{NANOKA_STATIC_HOST}/gi/{version}/monster.json"


def _discover_monster_json_url() -> str:
    html = _fetch_text(NANOKA_MONSTER_PAGE_URL, timeout=FETCH_TIMEOUT_SECONDS)
    parser = _FetchedDataUrlParser()
    parser.feed(html)

    candidate_urls: set[str] = set()
    for data_url in parser.data_urls:
        absolute_url = urljoin(NANOKA_STATIC_ROOT, data_url)
        if _versioned_nanoka_json_url(
            absolute_url,
            expected_document="monster",
        ) is not None:
            candidate_urls.add(absolute_url)

    if len(candidate_urls) != 1:
        raise AbyssSourceFetchError(
            "Nanoka monster page did not identify exactly one versioned "
            "monster.json URL."
        )
    return next(iter(candidate_urls))


def fetch_nanoka_monster_icon_catalog(
    manifest_url: str | None = None,
) -> NanokaMonsterIconCatalog:
    """Fetch Nanoka's general monster catalog with a bounded request timeout.

    When a verified tower manifest URL is available, derive the matching
    version's monster.json URL from it. Otherwise, discover the current URL from
    Nanoka's general monster page. Fetch/parse errors are left for the caller to
    handle as an optional icon-source failure.
    """

    monster_json_url = (
        _monster_json_url_from_manifest(manifest_url)
        if manifest_url is not None
        else _discover_monster_json_url()
    )
    payload = _fetch_json(monster_json_url, timeout=FETCH_TIMEOUT_SECONDS)
    return parse_nanoka_monster_icon_catalog(payload)


def resolve_nanoka_icon_url(
    display_name: str,
    catalog: Mapping[str, tuple[str, ...]],
) -> str | None:
    """Resolve one unambiguous icon by normalized name or an explicit alias."""

    normalized_name = _normalize_enemy_name(display_name)
    if not normalized_name:
        return None

    if normalized_name in catalog:
        return _single_catalog_url(catalog[normalized_name])

    alias_name = _ICON_NAME_ALIASES.get(normalized_name)
    if alias_name is None:
        return None
    return _single_catalog_url(catalog.get(alias_name, ()))


def _single_catalog_url(icon_urls: tuple[str, ...]) -> str | None:
    distinct_urls = {url for url in icon_urls if isinstance(url, str) and url}
    if len(distinct_urls) != 1:
        return None
    return next(iter(distinct_urls))


def enrich_missing_monster_icons(
    data: AbyssFloorSourceData,
    catalog: Mapping[str, tuple[str, ...]],
) -> AbyssFloorSourceData:
    """Fill missing Nanoka icon URLs while preserving HP joins and wave data."""

    updated_rows = []
    changed = False
    for row in data.enemy_rows:
        icon_url = (
            resolve_nanoka_icon_url(row.primary_display_name, catalog)
            if not row.nanoka_icon_url
            else None
        )
        if icon_url is None:
            updated_rows.append(row)
            continue
        updated_row = replace(row, nanoka_icon_url=icon_url)
        changed = True
        updated_rows.append(updated_row)

    if not changed:
        return data

    return rebuild_abyss_floor_source_data_with_rows(
        data,
        tuple(updated_rows),
    )
