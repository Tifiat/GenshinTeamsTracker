"""Opt-in Snap monster Name -> Title fallback for GCSIM enemy type matching.

This helper intentionally reads only the `Name` and `Title` fields from the
managed cached Snap Monster.json, the official online Snap.Metadata
`Monster.json` refresh source, or an explicit dev/offline local file. It is a
last-resort name/title bridge for enemy type matching and must not be used as
HP, stat, resist, wave, or enemy-count truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .enemy_type_registry import (
    PROJECT_ROOT,
    GcsimEnemyNameCandidate,
    normalize_gcsim_enemy_name,
)


DEFAULT_SNAP_MONSTER_GITHUB_URL = (
    "https://github.com/wangdage12/Snap.Metadata/blob/main/Genshin/EN/Monster.json"
)
DEFAULT_SNAP_MONSTER_RAW_URL = (
    "https://raw.githubusercontent.com/wangdage12/Snap.Metadata/main/Genshin/EN/Monster.json"
)
DEFAULT_SNAP_MONSTER_FETCH_TIMEOUT_SECONDS = 20.0
DEFAULT_SNAP_MONSTER_CACHE_PATH = (
    PROJECT_ROOT / "data" / "cache" / "gcsim" / "snap_metadata" / "Monster.json"
)

SNAP_TITLE_SOURCE_KIND = "snap_monster_title"
SNAP_TITLE_STATUS_MISSING = "missing"
SNAP_TITLE_STATUS_RESOLVED = "resolved"
SNAP_TITLE_STATUS_AMBIGUOUS = "ambiguous"
SNAP_SOURCE_KIND_LOCAL_PATH = "local_path"
SNAP_SOURCE_KIND_REMOTE_URL = "remote_url"
SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL = "default_remote_url"
SNAP_SOURCE_KIND_MANAGED_CACHE = "managed_cache"

SNAP_CACHE_STATUS_HIT = "cache_hit"
SNAP_CACHE_STATUS_MISSING = "cache_missing"
SNAP_CACHE_STATUS_INVALID = "cache_invalid"
SNAP_CACHE_STATUS_REMOTE_NOT_NEEDED = "remote_not_needed"
SNAP_REFRESH_STATUS_SUCCESS = "remote_refresh_success"
SNAP_REFRESH_STATUS_FAILED = "remote_refresh_failed"
SNAP_REFRESH_STATUS_NOT_NEEDED = "remote_not_needed"

SnapJsonFetcher = Callable[[str, float], str | bytes]


class SnapMonsterTitleSourceError(ValueError):
    """Raised for controlled Snap source loading errors."""


@dataclass(frozen=True, slots=True)
class SnapMonsterCacheLoadResult:
    status: str
    cache_path: str
    index: "SnapMonsterTitleIndex | None" = None
    error: str = ""

    @property
    def ready(self) -> bool:
        return self.status == SNAP_CACHE_STATUS_HIT and self.index is not None

    def to_dict(self) -> dict[str, str]:
        return {
            "cache_status": self.status,
            "cache_path": self.cache_path,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterCacheRefreshResult:
    status: str
    cache_path: str
    source_url: str
    resolved_url: str
    index: "SnapMonsterTitleIndex | None" = None
    fetched_at_utc: str = ""
    error: str = ""

    @property
    def ready(self) -> bool:
        return self.status == SNAP_REFRESH_STATUS_SUCCESS and self.index is not None

    def to_dict(self) -> dict[str, str]:
        return {
            "refresh_status": self.status,
            "cache_path": self.cache_path,
            "source_url": self.source_url,
            "resolved_url": self.resolved_url,
            "fetched_at_utc": self.fetched_at_utc,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleCandidate:
    source_name: str
    title: str

    @property
    def normalized_source_name(self) -> str:
        return normalize_gcsim_enemy_name(self.source_name)

    @property
    def normalized_title(self) -> str:
        return normalize_gcsim_enemy_name(self.title)

    def to_name_candidate(self) -> GcsimEnemyNameCandidate:
        return GcsimEnemyNameCandidate(
            source_kind=SNAP_TITLE_SOURCE_KIND,
            source_name=self.title,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "title": self.title,
            "normalized_source_name": self.normalized_source_name,
            "normalized_title": self.normalized_title,
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleLookup:
    status: str
    source_name: str
    candidates: tuple[SnapMonsterTitleCandidate, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == SNAP_TITLE_STATUS_RESOLVED and bool(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_name": self.source_name,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleIndex:
    titles_by_normalized_name: Mapping[str, tuple[SnapMonsterTitleCandidate, ...]]
    source_path: str = ""
    source_kind: str = ""
    source_ref: str = ""
    resolved_url: str = ""

    def lookup(self, source_name: str) -> SnapMonsterTitleLookup:
        normalized = normalize_gcsim_enemy_name(source_name)
        if not normalized:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_MISSING,
                source_name=str(source_name or ""),
                warnings=("snap_title_source_name_empty",),
            )
        candidates = self.titles_by_normalized_name.get(normalized, ())
        if not candidates:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_MISSING,
                source_name=str(source_name or ""),
                warnings=(f"snap_title_missing_for_name:{normalized}",),
            )
        normalized_titles = {candidate.normalized_title for candidate in candidates}
        if len(normalized_titles) > 1:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_AMBIGUOUS,
                source_name=str(source_name or ""),
                candidates=candidates,
                warnings=(f"snap_title_ambiguous_for_name:{normalized}",),
            )
        return SnapMonsterTitleLookup(
            status=SNAP_TITLE_STATUS_RESOLVED,
            source_name=str(source_name or ""),
            candidates=candidates[:1],
        )

    def title_candidates_for_names(
        self,
        name_candidates: tuple[GcsimEnemyNameCandidate, ...] | list[GcsimEnemyNameCandidate],
    ) -> SnapMonsterTitleLookup:
        resolved: list[SnapMonsterTitleCandidate] = []
        missing_warnings: list[str] = []
        seen_titles: set[str] = set()
        source_names: list[str] = []
        for name_candidate in name_candidates:
            source_names.append(name_candidate.source_name)
            lookup = self.lookup(name_candidate.source_name)
            if lookup.status == SNAP_TITLE_STATUS_AMBIGUOUS:
                return SnapMonsterTitleLookup(
                    status=SNAP_TITLE_STATUS_AMBIGUOUS,
                    source_name=name_candidate.source_name,
                    candidates=lookup.candidates,
                    warnings=lookup.warnings,
                )
            if not lookup.ready:
                missing_warnings.extend(lookup.warnings)
                continue
            candidate = lookup.candidates[0]
            if candidate.normalized_title in seen_titles:
                continue
            seen_titles.add(candidate.normalized_title)
            resolved.append(candidate)
        if len(resolved) > 1:
            names = ",".join(candidate.normalized_title for candidate in resolved)
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_AMBIGUOUS,
                source_name="|".join(source_names),
                candidates=tuple(resolved),
                warnings=(f"snap_title_multiple_titles_for_candidates:{names}",),
            )
        if resolved:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_RESOLVED,
                source_name=resolved[0].source_name,
                candidates=(resolved[0],),
            )
        return SnapMonsterTitleLookup(
            status=SNAP_TITLE_STATUS_MISSING,
            source_name="|".join(source_names),
            warnings=tuple(missing_warnings) or ("snap_title_missing_for_all_candidates",),
        )


    def source_report(self) -> dict[str, str]:
        return {
            "kind": self.source_kind,
            "source": self.source_ref or self.source_path,
            "resolved_url": self.resolved_url,
        }


def load_snap_monster_title_index(
    source: str | Path,
    *,
    fetcher: SnapJsonFetcher | None = None,
    timeout_seconds: float = DEFAULT_SNAP_MONSTER_FETCH_TIMEOUT_SECONDS,
    source_kind: str | None = None,
) -> SnapMonsterTitleIndex:
    source_ref = str(source)
    if _is_http_url(source_ref):
        resolved_url = snap_monster_raw_url(source_ref)
        payload = _load_remote_snap_json(
            resolved_url,
            fetcher=fetcher,
            timeout_seconds=timeout_seconds,
        )
        return _index_from_payload(
            payload,
            source_path=source_ref,
            source_kind=source_kind or SNAP_SOURCE_KIND_REMOTE_URL,
            source_ref=source_ref,
            resolved_url=resolved_url,
        )
    source_path = Path(source)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SnapMonsterTitleSourceError(
            f"Snap monster JSON invalid JSON at {source_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise SnapMonsterTitleSourceError(
            f"Snap monster JSON local file unavailable at {source_path}: {exc}"
        ) from exc
    return _index_from_payload(
        payload,
        source_path=str(source_path),
        source_kind=source_kind or SNAP_SOURCE_KIND_LOCAL_PATH,
        source_ref=str(source_path),
    )


def load_default_remote_snap_monster_title_index(
    *,
    fetcher: SnapJsonFetcher | None = None,
    timeout_seconds: float = DEFAULT_SNAP_MONSTER_FETCH_TIMEOUT_SECONDS,
) -> SnapMonsterTitleIndex:
    return load_snap_monster_title_index(
        DEFAULT_SNAP_MONSTER_GITHUB_URL,
        fetcher=fetcher,
        timeout_seconds=timeout_seconds,
        source_kind=SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL,
    )


def load_cached_snap_monster_title_index(
    cache_path: str | Path | None = None,
) -> SnapMonsterCacheLoadResult:
    path = Path(cache_path) if cache_path is not None else DEFAULT_SNAP_MONSTER_CACHE_PATH
    if not path.is_file():
        return SnapMonsterCacheLoadResult(
            status=SNAP_CACHE_STATUS_MISSING,
            cache_path=str(path),
            error=f"cached Snap Monster.json not found: {path}",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        index = _index_from_payload(
            payload,
            source_path=str(path),
            source_kind=SNAP_SOURCE_KIND_MANAGED_CACHE,
            source_ref=str(path),
            resolved_url=DEFAULT_SNAP_MONSTER_RAW_URL,
        )
    except (OSError, SnapMonsterTitleSourceError, json.JSONDecodeError) as exc:
        return SnapMonsterCacheLoadResult(
            status=SNAP_CACHE_STATUS_INVALID,
            cache_path=str(path),
            error=f"cached Snap Monster.json invalid at {path}: {exc}",
        )
    return SnapMonsterCacheLoadResult(
        status=SNAP_CACHE_STATUS_HIT,
        cache_path=str(path),
        index=index,
    )


def refresh_cached_snap_monster_title_index(
    cache_path: str | Path | None = None,
    *,
    source_url: str = DEFAULT_SNAP_MONSTER_GITHUB_URL,
    fetcher: SnapJsonFetcher | None = None,
    timeout_seconds: float = DEFAULT_SNAP_MONSTER_FETCH_TIMEOUT_SECONDS,
) -> SnapMonsterCacheRefreshResult:
    path = Path(cache_path) if cache_path is not None else DEFAULT_SNAP_MONSTER_CACHE_PATH
    resolved_url = snap_monster_raw_url(source_url)
    try:
        payload, _text = _load_remote_snap_json_with_text(
            resolved_url,
            fetcher=fetcher,
            timeout_seconds=timeout_seconds,
        )
        index = _index_from_payload(
            payload,
            source_path=str(path),
            source_kind=SNAP_SOURCE_KIND_MANAGED_CACHE,
            source_ref=str(path),
            resolved_url=resolved_url,
        )
        fetched_at = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(path, payload)
        _write_json_atomic(
            path.with_suffix(".meta.json"),
            {
                "source_url": source_url,
                "resolved_url": resolved_url,
                "fetched_at_utc": fetched_at,
                "cache_kind": "snap_monster_title_cache",
            },
        )
    except (OSError, SnapMonsterTitleSourceError, json.JSONDecodeError) as exc:
        return SnapMonsterCacheRefreshResult(
            status=SNAP_REFRESH_STATUS_FAILED,
            cache_path=str(path),
            source_url=source_url,
            resolved_url=resolved_url,
            error=str(exc),
        )
    return SnapMonsterCacheRefreshResult(
        status=SNAP_REFRESH_STATUS_SUCCESS,
        cache_path=str(path),
        source_url=source_url,
        resolved_url=resolved_url,
        index=index,
        fetched_at_utc=fetched_at,
    )


def snap_monster_raw_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        raise SnapMonsterTitleSourceError(f"Snap monster URL must use HTTP(S): {source_url}")
    if parsed.netloc.casefold() == "raw.githubusercontent.com":
        return source_url
    if parsed.netloc.casefold() != "github.com":
        return source_url
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "blob":
        return source_url
    owner, repo, _blob, branch = parts[:4]
    raw_path = "/".join(parts[4:])
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{raw_path}"


def _index_from_payload(
    payload: Any,
    *,
    source_path: str,
    source_kind: str,
    source_ref: str,
    resolved_url: str = "",
) -> SnapMonsterTitleIndex:
    try:
        records = _monster_records(payload)
    except ValueError as exc:
        raise SnapMonsterTitleSourceError(str(exc)) from exc
    grouped: dict[str, list[SnapMonsterTitleCandidate]] = {}
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        name = str(record.get("Name") or "").strip()
        title = str(record.get("Title") or "").strip()
        normalized_name = normalize_gcsim_enemy_name(name)
        normalized_title = normalize_gcsim_enemy_name(title)
        if not normalized_name or not normalized_title:
            continue
        key = (normalized_name, normalized_title)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(normalized_name, []).append(
            SnapMonsterTitleCandidate(source_name=name, title=title)
        )
    return SnapMonsterTitleIndex(
        titles_by_normalized_name={
            name: tuple(candidates) for name, candidates in grouped.items()
        },
        source_path=source_path,
        source_kind=source_kind,
        source_ref=source_ref,
        resolved_url=resolved_url,
    )


def _load_remote_snap_json(
    url: str,
    *,
    fetcher: SnapJsonFetcher | None,
    timeout_seconds: float,
) -> Any:
    payload, _text = _load_remote_snap_json_with_text(
        url,
        fetcher=fetcher,
        timeout_seconds=timeout_seconds,
    )
    return payload


def _load_remote_snap_json_with_text(
    url: str,
    *,
    fetcher: SnapJsonFetcher | None,
    timeout_seconds: float,
) -> tuple[Any, str]:
    try:
        raw = fetcher(url, timeout_seconds) if fetcher else _fetch_url_text(url, timeout_seconds)
    except HTTPError as exc:
        raise SnapMonsterTitleSourceError(
            f"Snap monster JSON HTTP error {exc.code} for {url}: {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SnapMonsterTitleSourceError(
            f"Snap monster JSON remote fetch failed for {url}: {exc}"
        ) from exc
    try:
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else str(raw)
        return json.loads(text), text
    except json.JSONDecodeError as exc:
        raise SnapMonsterTitleSourceError(
            f"Snap monster JSON invalid JSON from {url}: {exc}"
        ) from exc


def _fetch_url_text(url: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"User-Agent": "GenshinTeamsTracker-dev"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8-sig")


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _monster_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("items", "data", "monsters"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Snap monster JSON must be a list of objects with Name and Title")


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)
