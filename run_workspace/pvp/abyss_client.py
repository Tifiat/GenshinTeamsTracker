"""Bounded, unauthenticated reads of the public Abyss rules source.

The returned source declarations are data for a separate adapter. This module
does not execute them, access accounts, or cache responses on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = "https://abyss.darte.gg/api/abyss"
PAGE_LIMIT = 50
MAX_SYSTEMS = 500
MAX_RESPONSE_BYTES = 4_000_000
REQUEST_TIMEOUT_SECONDS = 15
_SYSTEM_ID = re.compile(r"[0-9a-f]{24}\Z")


class AbyssSourceError(Exception):
    """A public source failure safe to show in the deck editor."""

    code = "abyss_source_error"


class AbyssTransportError(AbyssSourceError):
    code = "abyss_transport_error"


class AbyssSchemaError(AbyssSourceError):
    code = "abyss_schema_error"


class AbyssVersionError(AbyssSourceError):
    code = "abyss_version_error"


@dataclass(frozen=True, slots=True)
class AbyssRulesChoice:
    system_id: str
    family_id: str
    title: str
    updated_at: str


def _is_system_id(value: object) -> bool:
    return isinstance(value, str) and _SYSTEM_ID.fullmatch(value) is not None


def _get_public_json(path: str) -> Any:
    request = Request(
        API_BASE + path,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise AbyssTransportError("Could not load public Abyss rules") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AbyssSchemaError("Public Abyss response is too large")
    try:
        return json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise AbyssSchemaError("Public Abyss response is invalid") from exc


def _choice(row: object) -> tuple[AbyssRulesChoice, datetime, bool]:
    if not isinstance(row, dict):
        raise AbyssSchemaError("Public Abyss catalog changed")
    system_id = row.get("_id")
    family_id = row.get("root") or system_id
    title = row.get("main", {}).get("title") if isinstance(row.get("main"), dict) else None
    updated_at = row.get("updatedAt")
    archived = row.get("archived")
    if not _is_system_id(system_id) or not _is_system_id(family_id):
        raise AbyssSchemaError("Public Abyss catalog has an invalid version ID")
    if not isinstance(title, str) or not title.strip():
        raise AbyssSchemaError("Public Abyss catalog has no title")
    if not isinstance(updated_at, str) or type(archived) is not bool:
        raise AbyssSchemaError("Public Abyss catalog changed")
    try:
        updated_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if updated_time.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise AbyssSchemaError("Public Abyss catalog has an invalid update time") from exc
    return AbyssRulesChoice(system_id, family_id, title.strip(), updated_at), updated_time, archived


def list_latest_rulesets() -> tuple[AbyssRulesChoice, ...]:
    """Fetch all bounded catalog pages and choose each family's newest live version.

    The public endpoint is a Genshin rules catalog. Its current ``shiyu`` mode
    value is not a game discriminator, so no mode-name filter is applied.
    """
    latest: dict[str, tuple[AbyssRulesChoice, datetime]] = {}
    seen: set[str] = set()
    skip = 0
    count: int | None = None
    while count is None or skip < count:
        page = _get_public_json(f"/draft_systems?withDetails=true&skip={skip}&limit={PAGE_LIMIT}")
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise AbyssSchemaError("Public Abyss catalog changed")
        page_count = page.get("count")
        if type(page_count) is not int or not 0 <= page_count <= MAX_SYSTEMS:
            raise AbyssSchemaError("Public Abyss catalog exceeds its limit")
        if count is not None and page_count != count:
            raise AbyssSchemaError("Public Abyss catalog changed during loading")
        count = page_count
        items = page["items"]
        if len(items) > PAGE_LIMIT or skip + len(items) > count:
            raise AbyssSchemaError("Public Abyss catalog pagination changed")
        if not items and skip < count:
            raise AbyssSchemaError("Public Abyss catalog pagination stopped early")
        for row in items:
            choice, updated_time, archived = _choice(row)
            if choice.system_id in seen:
                raise AbyssSchemaError("Public Abyss catalog repeated a version")
            seen.add(choice.system_id)
            if archived:
                continue
            previous = latest.get(choice.family_id)
            if previous is None or (updated_time, choice.system_id) > (previous[1], previous[0].system_id):
                latest[choice.family_id] = (choice, updated_time)
        skip += len(items)
    return tuple(
        pair[0] for pair in sorted(
            latest.values(), key=lambda pair: (pair[1], pair[0].system_id), reverse=True,
        )
    )


def fetch_ruleset_source(system_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch a selected exact version and its public character/weapon catalogs."""
    if not _is_system_id(system_id):
        raise AbyssVersionError("Select a public Abyss rules version")
    system = _get_public_json(f"/draft_systems/{system_id}")
    if not isinstance(system, dict) or system.get("_id") != system_id:
        raise AbyssVersionError("Public Abyss returned a different rules version")
    agents = _get_public_json("/agents")
    engines = _get_public_json("/engines")
    if not isinstance(agents, list) or not all(isinstance(row, dict) for row in agents):
        raise AbyssSchemaError("Public Abyss character catalog changed")
    if not isinstance(engines, list) or not all(isinstance(row, dict) for row in engines):
        raise AbyssSchemaError("Public Abyss weapon catalog changed")
    return system, agents, engines
