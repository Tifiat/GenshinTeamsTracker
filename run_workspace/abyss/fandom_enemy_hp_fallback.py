"""Production-safe Fandom enemy-page HP fallback for Abyss source data."""

from __future__ import annotations

import math
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import Any, Callable
from urllib.parse import urljoin

from .source_data import (
    HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
    MATCH_CONFIDENCE_HIGH,
    MATCH_CONFIDENCE_MEDIUM,
    MATCH_CONFIDENCE_NONE,
    MATCH_METHOD_FANDOM_ENEMY_PAGE_FALLBACK,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
    rebuild_abyss_floor_source_data_with_rows,
)
from .source_data_fetchers import (
    FANDOM_BASE_URL,
    AbyssSourceFetchError,
    HtmlNode,
    _compact_text,
    _direct_elements,
    _fetch_rendered_html,
    _find_all,
    _first,
    _has_class,
    _heading_level,
    _headline_id,
    _parse_fragment,
    page_title_from_fandom_url,
)


DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER = 3.75
DEFAULT_FANDOM_ENEMY_PAGE_WORKERS = 5
HP_FALLBACK_MODE_AUTO = "auto"
HP_FALLBACK_MODE_NANOKA_ONLY = "nanoka-only"
HP_FALLBACK_MODE_FANDOM_ONLY = "fandom-only"
HP_FALLBACK_MODE_CHOICES = (
    HP_FALLBACK_MODE_AUTO,
    HP_FALLBACK_MODE_NANOKA_ONLY,
    HP_FALLBACK_MODE_FANDOM_ONLY,
)

GENERIC_HEADING_TOKENS = {
    "level",
    "scaling",
    "stat",
    "stats",
}
GENERIC_STATS_TABLE_HEADINGS = {
    "normal",
    "stats",
}
GENERIC_STATS_LAND_HEADINGS = {
    "land",
}
GENERIC_STATS_UNDERWATER_HEADINGS = {
    "underwater",
}
UNDERWATER_VARIANT_TOKENS = {
    "underwater",
    "waterborne",
}


@dataclass(frozen=True, slots=True)
class EnemyPage:
    requested_url: str
    resolved_url: str
    requested_title: str
    resolved_title: str
    html_root: HtmlNode
    redirects: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class HpTableCandidate:
    index: int
    heading_path: tuple[str, ...]
    heading_ids: tuple[str | None, ...]
    level_hp: dict[int, int]
    table_source_path: str
    extraction_note: str


@dataclass(frozen=True, slots=True)
class FandomEnemyHpFallbackResult:
    data: AbyssFloorSourceData
    attempted: int
    resolved: int
    unresolved: int
    page_fetches: int
    page_cache_hits: int
    hp_multiplier: float
    mode: str
    workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS
    warnings: tuple[str, ...] = ()


EnemyPageFetcher = Callable[[str], EnemyPage]


def normalize_hp_fallback_mode(value: str | None) -> str:
    mode = str(value or HP_FALLBACK_MODE_AUTO).strip().lower()
    if mode not in HP_FALLBACK_MODE_CHOICES:
        choices = ", ".join(HP_FALLBACK_MODE_CHOICES)
        raise ValueError(f"Unsupported Abyss HP fallback mode: {value!r}. Expected one of: {choices}.")
    return mode


def apply_fandom_enemy_page_hp_fallback(
    data: AbyssFloorSourceData,
    *,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    mode: str = HP_FALLBACK_MODE_AUTO,
    enemy_page_fetcher: EnemyPageFetcher = None,
    enemy_page_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
) -> FandomEnemyHpFallbackResult:
    """Fill missing/forced enemy HP from Fandom enemy level/HP tables.

    `auto` only fills rows without Nanoka HP. `fandom-only` forces every row to
    use Fandom enemy-page HP. `nanoka-only` returns the input unchanged.
    """

    normalized_mode = normalize_hp_fallback_mode(mode)
    workers = _normalize_worker_count(enemy_page_workers)
    if normalized_mode == HP_FALLBACK_MODE_NANOKA_ONLY:
        return FandomEnemyHpFallbackResult(
            data=data,
            attempted=0,
            resolved=0,
            unresolved=0,
            page_fetches=0,
            page_cache_hits=0,
            hp_multiplier=float(hp_multiplier),
            mode=normalized_mode,
            workers=workers,
        )

    fetcher = enemy_page_fetcher or fetch_enemy_page
    rows: list[AbyssEnemySourceRow] = []
    page_cache: dict[str, EnemyPage] = {}
    page_errors: dict[str, Exception] = {}
    table_cache: dict[str, tuple[HpTableCandidate, ...]] = {}
    attempted = 0
    resolved = 0
    page_cache_hits = 0
    global_warnings: set[str] = set()
    attempt_rows: list[AbyssEnemySourceRow] = []

    for row in data.enemy_rows:
        should_attempt = (
            normalized_mode == HP_FALLBACK_MODE_FANDOM_ONLY
            or row.nanoka_hp is None
        )
        if not should_attempt:
            continue
        attempt_rows.append(row)

    page_fetches = _prefetch_enemy_pages(
        attempt_rows,
        page_cache=page_cache,
        page_errors=page_errors,
        fetcher=fetcher,
        workers=workers,
    )
    page_cache_hits = max(
        0,
        sum(1 for row in attempt_rows if row.fandom_enemy_page_url) - page_fetches,
    )

    for row in data.enemy_rows:
        should_attempt = (
            normalized_mode == HP_FALLBACK_MODE_FANDOM_ONLY
            or row.nanoka_hp is None
        )
        if not should_attempt:
            rows.append(row)
            continue
        attempted += 1
        fallback_row, fetch_state = _row_with_fallback_hp(
            row,
            hp_multiplier=float(hp_multiplier),
            force=normalized_mode == HP_FALLBACK_MODE_FANDOM_ONLY,
            page_cache=page_cache,
            page_errors=page_errors,
            table_cache=table_cache,
            fetcher=fetcher,
        )
        if fallback_row.nanoka_hp is not None and fallback_row.hp_source == HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK:
            resolved += 1
        for warning in fallback_row.warnings:
            if warning.startswith("fandom_enemy_page_hp_"):
                global_warnings.add(warning)
        rows.append(fallback_row)

    unresolved = attempted - resolved
    if attempted:
        global_warnings.add(f"fandom_enemy_page_hp_fallback_attempted:{attempted}")
    if resolved:
        global_warnings.add(f"fandom_enemy_page_hp_fallback_resolved:{resolved}")
    if unresolved:
        global_warnings.add(f"fandom_enemy_page_hp_fallback_unresolved:{unresolved}")
    rebuilt = rebuild_abyss_floor_source_data_with_rows(
        data,
        tuple(rows),
        global_warnings=tuple(global_warnings),
    )
    return FandomEnemyHpFallbackResult(
        data=rebuilt,
        attempted=attempted,
        resolved=resolved,
        unresolved=unresolved,
        page_fetches=page_fetches,
        page_cache_hits=page_cache_hits,
        hp_multiplier=float(hp_multiplier),
        mode=normalized_mode,
        workers=workers,
        warnings=tuple(sorted(global_warnings)),
    )


def _prefetch_enemy_pages(
    rows: list[AbyssEnemySourceRow],
    *,
    page_cache: dict[str, EnemyPage],
    page_errors: dict[str, Exception],
    fetcher: EnemyPageFetcher,
    workers: int,
) -> int:
    urls = sorted(
        {
            str(row.fandom_enemy_page_url)
            for row in rows
            if row.fandom_enemy_page_url
        }
    )
    if not urls:
        return 0
    if workers <= 1 or len(urls) == 1:
        for url in urls:
            try:
                page_cache[url] = fetcher(url)
            except Exception as exc:  # noqa: BLE001 - fallback reports per-row failures.
                page_errors[url] = exc
        return len(urls)
    with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as executor:
        future_by_url = {executor.submit(fetcher, url): url for url in urls}
        for future in as_completed(future_by_url):
            url = future_by_url[future]
            try:
                page_cache[url] = future.result()
            except Exception as exc:  # noqa: BLE001 - fallback reports per-row failures.
                page_errors[url] = exc
    return len(urls)


def _normalize_worker_count(value: int | str | None) -> int:
    try:
        return max(1, int(value or DEFAULT_FANDOM_ENEMY_PAGE_WORKERS))
    except (TypeError, ValueError):
        return DEFAULT_FANDOM_ENEMY_PAGE_WORKERS


def fetch_enemy_page(url: str) -> EnemyPage:
    requested_url = url
    requested_title = page_title_from_fandom_url(url)
    redirects: list[dict[str, str]] = []
    current_url = url
    current_title = requested_title
    for _ in range(5):
        rendered_html, parse_payload = _fetch_rendered_html(current_title)
        root = _parse_fragment(rendered_html)
        target = _redirect_target(root)
        if target is None:
            return EnemyPage(
                requested_url=requested_url,
                resolved_url=current_url,
                requested_title=requested_title,
                resolved_title=str(parse_payload.get("title") or current_title),
                html_root=root,
                redirects=tuple(redirects),
            )
        next_url, next_title = target
        redirects.append(
            {
                "from_url": current_url,
                "from_title": current_title,
                "to_url": next_url,
                "to_title": next_title,
            }
        )
        current_url = next_url
        current_title = page_title_from_fandom_url(next_url)
    raise AbyssSourceFetchError(f"Redirect loop while resolving {requested_url}")


def _row_with_fallback_hp(
    row: AbyssEnemySourceRow,
    *,
    hp_multiplier: float,
    force: bool,
    page_cache: dict[str, EnemyPage],
    page_errors: dict[str, Exception],
    table_cache: dict[str, tuple[HpTableCandidate, ...]],
    fetcher: EnemyPageFetcher,
) -> tuple[AbyssEnemySourceRow, str]:
    warnings = list(row.warnings)
    fetch_state = "none"
    page_url = row.fandom_enemy_page_url
    if not page_url:
        warnings.append("fandom_enemy_page_hp_url_missing")
        return replace(row, warnings=tuple(warnings)), fetch_state
    if page_url in page_errors:
        warnings.append(f"fandom_enemy_page_hp_fetch_or_parse_failed:{page_errors[page_url]}")
        return replace(row, warnings=tuple(warnings)), "error"
    try:
        page = page_cache.get(page_url)
        if page is None:
            page = fetcher(page_url)
            page_cache[page_url] = page
            fetch_state = "fetch"
        else:
            fetch_state = "cache"
        candidates = table_cache.get(page.resolved_url)
        if candidates is None:
            candidates = tuple(iter_hp_tables(page.html_root))
            table_cache[page.resolved_url] = candidates
        table, method, confidence, table_warnings = select_hp_table(
            list(candidates),
            enemy_name=row.primary_display_name,
        )
        warnings.extend(table_warnings)
        raw_hp = None
        if table is not None and row.display_level is not None:
            raw_hp = table.level_hp.get(row.display_level)
            if raw_hp is None:
                warnings.append(f"fandom_enemy_page_hp_missing_for_level:{row.display_level}")
        if raw_hp is None:
            warnings.append(f"fandom_enemy_page_hp_unavailable:{method}")
            return replace(row, warnings=tuple(warnings)), fetch_state
        resolved_hp = _display_hp(raw_hp * hp_multiplier)
        source_warnings = [
            "fandom_enemy_page_hp_fallback_used",
            f"fandom_enemy_page_hp_table_method:{method}",
            f"fandom_enemy_page_hp_table_confidence:{confidence}",
            f"fandom_enemy_page_hp_multiplier:{hp_multiplier:g}",
        ]
        if force and row.nanoka_hp is not None:
            source_warnings.append("nanoka_hp_overridden_by_forced_fandom_fallback")
        elif row.nanoka_hp is None:
            source_warnings.append("nanoka_hp_missing_used_fandom_enemy_page_fallback")
        warnings.extend(source_warnings)
        return (
            replace(
                row,
                nanoka_hp=resolved_hp,
                hp_source=HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
                match_method=MATCH_METHOD_FANDOM_ENEMY_PAGE_FALLBACK,
                match_confidence=confidence
                if confidence != MATCH_CONFIDENCE_NONE
                else MATCH_CONFIDENCE_MEDIUM,
                warnings=tuple(warnings),
            ),
            fetch_state,
        )
    except Exception as exc:  # noqa: BLE001 - fallback must keep source data usable.
        warnings.append(f"fandom_enemy_page_hp_fetch_or_parse_failed:{exc}")
        return replace(row, warnings=tuple(warnings)), fetch_state


def iter_hp_tables(root: HtmlNode) -> list[HpTableCandidate]:
    candidates: list[HpTableCandidate] = []

    def walk(node: HtmlNode, heading_stack: list[tuple[int, str, str | None]]) -> None:
        current_stack = heading_stack
        for child in node.children:
            if not isinstance(child, HtmlNode):
                continue
            level = _heading_level(child)
            if level is not None:
                current_stack = [item for item in current_stack if item[0] < level]
                current_stack.append(
                    (
                        level,
                        _clean_heading(_compact_text(child)),
                        _headline_id(child),
                    )
                )
            if child.tag == "table":
                level_hp = _parse_level_hp_table(child)
                if level_hp:
                    index = len(candidates)
                    headings = tuple(item[1] for item in current_stack)
                    heading_ids = tuple(item[2] for item in current_stack)
                    source_bits = [
                        f"h{item[0]}#{item[2] or _normalize_name(item[1])}"
                        for item in current_stack
                    ]
                    candidates.append(
                        HpTableCandidate(
                            index=index,
                            heading_path=headings,
                            heading_ids=heading_ids,
                            level_hp=level_hp,
                            table_source_path="/".join(source_bits)
                            + f"/table.level_hp[{index}]",
                            extraction_note=(
                                "Parsed article-table Level/HP rows from Fandom "
                                "MediaWiki rendered enemy page HTML."
                            ),
                        )
                    )
            walk(child, current_stack.copy())

    walk(root, [])
    return candidates


def select_hp_table(
    candidates: list[HpTableCandidate],
    *,
    enemy_name: str,
) -> tuple[HpTableCandidate | None, str, str, list[str]]:
    warnings: list[str] = []
    if not candidates:
        return None, "no_level_hp_table", MATCH_CONFIDENCE_NONE, ["enemy_page_level_hp_table_missing"]
    if len(candidates) == 1:
        return candidates[0], "single_clear_table", MATCH_CONFIDENCE_HIGH, []

    scored = [(_score_table(candidate, enemy_name), candidate) for candidate in candidates]
    positive = [item for item in scored if item[0][0] > 0.0]
    if not positive:
        generic_stats = [
            (priority, candidate)
            for candidate in candidates
            if (priority := _generic_stats_candidate_priority(candidate, enemy_name=enemy_name))
            is not None
        ]
        if generic_stats:
            generic_stats.sort(key=lambda item: item[0])
            best_priority = generic_stats[0][0]
            tied = [candidate for priority, candidate in generic_stats if priority == best_priority]
            if len(tied) == 1:
                return (
                    tied[0],
                    "generic_stats_table_fallback",
                    MATCH_CONFIDENCE_MEDIUM,
                    ["selected_generic_stats_table_after_no_variant_heading_match"],
                )
            return (
                None,
                "multiple_generic_stats_tables_ambiguous",
                MATCH_CONFIDENCE_NONE,
                [
                    "multiple_generic_stats_tables_after_no_variant_heading_match:"
                    + ",".join(" > ".join(candidate.heading_path) for candidate in tied)
                ],
            )
        return (
            None,
            "multiple_tables_no_heading_match",
            MATCH_CONFIDENCE_NONE,
            ["multiple_level_hp_tables_no_heading_match"],
        )
    positive.sort(key=lambda item: item[0], reverse=True)
    best_score, best_candidate = positive[0]
    tied = [candidate for score, candidate in positive if score == best_score]
    if len(tied) > 1:
        return (
            None,
            "multiple_tables_ambiguous_heading_match",
            MATCH_CONFIDENCE_NONE,
            [
                "multiple_level_hp_tables_ambiguous_heading_match:"
                + ",".join(_candidate_heading_for_match(candidate) for candidate in tied)
            ],
        )
    ratio, exactish, _ = best_score
    method = "heading_exact_match" if exactish else "heading_token_match"
    confidence = MATCH_CONFIDENCE_HIGH if ratio >= 1.0 else MATCH_CONFIDENCE_MEDIUM
    warnings.append("selected_from_multiple_level_hp_tables_by_heading")
    return best_candidate, method, confidence, warnings


def _redirect_target(root: HtmlNode) -> tuple[str, str] | None:
    redirect = _first(
        root,
        lambda node: node.tag == "div" and _has_class(node, "redirectMsg"),
    )
    if redirect is None:
        return None
    link = _first(redirect, lambda node: node.tag == "a")
    if link is None:
        return None
    href = link.attrs.get("href")
    title = link.attrs.get("title") or _compact_text(link)
    if not href:
        return None
    return urljoin(FANDOM_BASE_URL, href), title


def _row_cells(row: HtmlNode) -> list[str]:
    return [
        _compact_text(cell)
        for cell in _direct_elements(row)
        if cell.tag in {"th", "td"}
    ]


def _parse_level_hp_table(table: HtmlNode) -> dict[int, int] | None:
    if not _has_class(table, "article-table"):
        return None
    rows = _find_all(table, lambda node: node.tag == "tr")
    level_index: int | None = None
    hp_index: int | None = None
    result: dict[int, int] = {}
    for row in rows:
        cells = _row_cells(row)
        lowered = [cell.casefold() for cell in cells]
        if "level" in lowered and "hp" in lowered:
            level_index = lowered.index("level")
            hp_index = lowered.index("hp")
            continue
        if level_index is None or hp_index is None:
            continue
        if len(cells) <= max(level_index, hp_index):
            continue
        level = _parse_number(cells[level_index])
        hp = _parse_number(cells[hp_index])
        if level is not None and hp is not None:
            result[level] = hp
    return result or None


def _candidate_heading_for_match(candidate: HpTableCandidate | None) -> str:
    if candidate is None:
        return ""
    for heading in reversed(candidate.heading_path):
        tokens = _tokens(heading)
        if tokens and _normalize_name(heading) != "stats":
            return heading
    return " > ".join(candidate.heading_path)


def _score_table(candidate: HpTableCandidate, enemy_name: str) -> tuple[float, int, int]:
    name_tokens = set(_tokens(enemy_name))
    heading = _candidate_heading_for_match(candidate)
    heading_tokens = set(_tokens(heading))
    if not heading_tokens:
        return 0.0, 0, len(candidate.heading_path)
    overlap = len(name_tokens & heading_tokens)
    ratio = overlap / len(heading_tokens)
    exactish = int(_normalize_name(heading) in _normalize_name(enemy_name))
    return ratio, exactish, len(heading_tokens)


def _generic_stats_candidate_priority(
    candidate: HpTableCandidate,
    *,
    enemy_name: str,
) -> int | None:
    normalized_path = [_normalize_name(heading) for heading in candidate.heading_path]
    if "stats" not in normalized_path:
        return None
    match_heading = _normalize_name(_candidate_heading_for_match(candidate))
    if match_heading in GENERIC_STATS_TABLE_HEADINGS:
        return 0
    if match_heading in GENERIC_STATS_LAND_HEADINGS:
        return 1
    enemy_tokens = set(_tokens(enemy_name))
    if match_heading in GENERIC_STATS_UNDERWATER_HEADINGS and enemy_tokens & UNDERWATER_VARIANT_TOKENS:
        return 2
    return None


def _normalize_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def _tokens(value: Any) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return [
        token
        for token in re.findall(r"[a-z0-9]+", ascii_value.casefold())
        if token not in GENERIC_HEADING_TOKENS
    ]


def _clean_heading(value: str) -> str:
    return re.sub(r"\s*\[\]\s*$", "", value).strip()


def _parse_number(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


def _display_hp(value: float | None) -> int | None:
    if value is None:
        return None
    return int(math.floor(value + 0.5))
