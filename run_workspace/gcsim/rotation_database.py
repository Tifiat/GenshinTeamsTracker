"""Read public KQM gcsim rotations for an exact four-character team.

The upstream client uses ``https://db.kqm.gg/api/db?q=<JSON>``. The current
database UI sends ``query``, ``limit``, and ``skip`` inside that JSON. This
module never persists responses or sends account data beyond engine keys.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .rotation_editor.syntax import Dialect, parse


DB_URL = "https://db.kqm.gg"
API_URL = f"{DB_URL}/api/db"
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 20
DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class DatabaseMember:
    key: str
    constellation: int | None = None
    weapon: str | None = None
    refinement: int | None = None
    sets: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RotationRecord:
    id: str
    config: str
    description: str
    author: str
    url: str
    members: tuple[DatabaseMember, ...]


@dataclass(frozen=True)
class SearchResult:
    records: tuple[RotationRecord, ...]
    complete: bool
    error: str | None = None
    status: str = "ok"  # ok, empty, incomplete, error, or cancelled


def _fetch_json(url: str, timeout: float) -> object:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("database page exceeds response size limit")
    return json.loads(body)


def _explicit_zero_constellations(config: str, wanted: frozenset[str]) -> frozenset[str]:
    """Accept C0 only from one parsed top-level character declaration."""
    try:
        document = parse(config, Dialect({key: key for key in wanted}))
    except (ValueError, RecursionError):
        return frozenset()
    if not document.syntax_complete:
        return frozenset()
    declarations: dict[str, list[bool]] = {}
    for item in document.root.get("items"):
        if item.kind != "setup" or item.get("directive").get("value") != "char":
            continue
        actor = item.get("actor")
        key = actor.get("value") if actor is not None else None
        if key not in wanted:
            continue
        cons_entries = [entry for entry in item.get("entries") if entry.get("key").get("value") == "cons"]
        zero = False
        if len(cons_entries) == 1:
            values = cons_entries[0].get("values")
            zero = len(values) == 1 and values[0].kind == "number" and values[0].get("value") == "0"
        declarations.setdefault(key, []).append(zero)
    return frozenset(key for key, values in declarations.items() if values == [True])


def _member(raw: object, explicit_zero: frozenset[str]) -> DatabaseMember | None:
    if not isinstance(raw, dict):
        return None
    key = raw.get("name")
    if not isinstance(key, str) or not key.strip():
        return None
    cons = raw.get("cons")
    if isinstance(cons, bool) or not isinstance(cons, int) or not 0 <= cons <= 6:
        cons = 0 if "cons" not in raw and key.strip() in explicit_zero else None
    weapon_data = raw.get("weapon")
    weapon = None
    refinement = None
    if isinstance(weapon_data, dict):
        name = weapon_data.get("name")
        weapon = name.strip() if isinstance(name, str) and name.strip() else None
        refine = weapon_data.get("refine")
        if isinstance(refine, int) and not isinstance(refine, bool) and 1 <= refine <= 5:
            refinement = refine
    raw_sets = raw.get("sets")
    sets = {
        key: count for key, count in raw_sets.items()
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool) and count > 0
    } if isinstance(raw_sets, dict) else {}
    return DatabaseMember(key=key.strip(), constellation=cons, weapon=weapon, refinement=refinement, sets=sets)


def _record(raw: object, wanted: frozenset[str]) -> RotationRecord | None:
    if not isinstance(raw, dict):
        return None
    record_id = raw.get("_id", raw.get("id"))
    config = raw.get("config")
    summary = raw.get("summary")
    if not isinstance(record_id, str) or not _SAFE_ID.fullmatch(record_id):
        return None
    if not isinstance(config, str) or not config.strip() or not isinstance(summary, dict):
        return None
    team = summary.get("team")
    if not isinstance(team, list) or len(team) != 4:
        return None
    explicit_zero = _explicit_zero_constellations(config, wanted)
    members = tuple(_member(member, explicit_zero) for member in team)
    if any(member is None for member in members):
        return None
    typed_members = tuple(member for member in members if member is not None)
    if frozenset(member.key for member in typed_members) != wanted:
        return None
    description = raw.get("description")
    submitter = raw.get("submitter")
    return RotationRecord(
        id=record_id,
        config=config,
        description=description if isinstance(description, str) else "",
        author=str(submitter) if isinstance(submitter, (str, int)) else "",
        url=f"{DB_URL}/db/{record_id}",
        members=typed_members,
    )


def _claims_wanted_team(raw: object, wanted: frozenset[str]) -> bool:
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), dict):
        return True  # Unknown rows must not silently make a result look complete.
    summary = raw["summary"]
    names = summary.get("char_names")
    if isinstance(names, list) and len(names) == 4 and all(isinstance(name, str) for name in names):
        return frozenset(names) == wanted
    team = summary.get("team")
    if isinstance(team, list) and len(team) == 4 and all(isinstance(member, dict) for member in team):
        team_names = [member.get("name") for member in team]
        if all(isinstance(name, str) for name in team_names):
            return frozenset(team_names) == wanted
    return True


def _query_url(keys: Sequence[str], limit: int, skip: int) -> str:
    query = {
        "query": {"$and": [{"summary.char_names": key} for key in keys]},
        "limit": limit,
        "skip": skip,
        "sort": {"_id": 1},
    }
    return f"{API_URL}?q={quote(json.dumps(query, separators=(',', ':')))}"


def search_team(
    keys: Sequence[str],
    *,
    cancelled: Callable[[], bool] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    fetch_json: Callable[[str, float], object] | None = None,
) -> SearchResult:
    """Fetch exact four-character matches; report partial/error states explicitly.

    ``fetch_json`` is a test seam. Production uses bounded, no-store HTTPS GETs.
    Cancellation is checked between requests and while parsing returned rows.
    """
    if len(keys) != 4 or any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError("exactly four nonempty engine character keys are required")
    normalized = tuple(key.strip() for key in keys)
    wanted = frozenset(normalized)
    if len(wanted) != 4:
        raise ValueError("character keys must be distinct")
    if not 1 <= page_size <= 100 or not 1 <= max_pages <= 100 or timeout <= 0:
        raise ValueError("invalid database request bound")
    fetch = fetch_json or _fetch_json
    records: dict[str, RotationRecord] = {}
    malformed = False
    for page in range(max_pages):
        if cancelled and cancelled():
            return SearchResult(tuple(records.values()), False, "cancelled", "cancelled")
        try:
            payload = fetch(_query_url(normalized, page_size, page * page_size), timeout)
        except (HTTPError, URLError, OSError, ValueError, RecursionError) as exc:
            return SearchResult(tuple(records.values()), False, f"database request failed: {type(exc).__name__}", "error")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return SearchResult(tuple(records.values()), False, "database response has no data list", "error")
        page_rows = payload["data"]
        if len(page_rows) > page_size:
            return SearchResult(tuple(records.values()), False, "database page exceeds requested limit", "error")
        for raw in page_rows:
            if cancelled and cancelled():
                return SearchResult(tuple(records.values()), False, "cancelled", "cancelled")
            record = _record(raw, wanted)
            if record is None:
                # A different four-person team may be returned by a broad server filter.
                # Only malformed rows with the wanted summary names affect completeness.
                if _claims_wanted_team(raw, wanted):
                    malformed = True
                continue
            earlier = records.get(record.id)
            if earlier is None:
                records[record.id] = record
            elif earlier != record:
                malformed = True
        if len(page_rows) < page_size:
            if malformed:
                return SearchResult(tuple(records.values()), False, "some database rows were malformed or conflicted", "incomplete")
            found = tuple(records.values())
            return SearchResult(found, True, None, "ok" if found else "empty")
    return SearchResult(tuple(records.values()), False, "database page limit reached", "incomplete")


def rank_records(records: Sequence[RotationRecord], desired_members: Sequence[DatabaseMember]) -> tuple[RotationRecord, ...]:
    """Rank exact C+weapon, then exact C, then closest changed C.

    Refinement, sets, stats, DPS, talents, and API order never affect rank.
    Missing C/weapon data cannot qualify as an exact match.
    """
    if len(desired_members) != 4 or len({member.key for member in desired_members}) != 4:
        raise ValueError("four distinct desired members are required")
    desired = {member.key: member for member in desired_members}

    def score(record: RotationRecord) -> tuple[int, int, int, int, int, str]:
        actual = {member.key: member for member in record.members}
        if set(actual) != set(desired):
            return (4, 0, 0, 0, 0, record.id)
        unknown_c = sum(
            actual[key].constellation is None or desired[key].constellation is None
            for key in desired
        )
        changed_c = sum(
            actual[key].constellation != desired[key].constellation
            for key in desired
            if actual[key].constellation is not None and desired[key].constellation is not None
        )
        total_gap = sum(
            abs(actual[key].constellation - desired[key].constellation)
            for key in desired
            if actual[key].constellation is not None and desired[key].constellation is not None
        )
        unknown_weapon = sum(not actual[key].weapon or not desired[key].weapon for key in desired)
        changed_weapon = sum(
            actual[key].weapon != desired[key].weapon
            for key in desired
            if actual[key].weapon and desired[key].weapon
        )
        tier = 3 if unknown_c else 2 if changed_c else 1 if (changed_weapon or unknown_weapon) else 0
        return (tier, changed_c + unknown_c, total_gap, changed_weapon + unknown_weapon, unknown_weapon, record.id)

    return tuple(sorted(records, key=score))
