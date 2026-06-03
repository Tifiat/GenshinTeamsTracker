"""Experiment-only Fandom enemy-page HP fallback probe.

Nanoka remains the primary resolved HP source. This script explores whether
Fandom enemy pages can be used as a fallback/cross-check by selecting a
level/HP table from the enemy page based on the Fandom composition enemy name,
then applying an explicit Abyss HP multiplier. Nanoka, when provided, is used
only for comparison and never for selecting the Fandom table.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

try:
    import abyss_join_probe as join_probe
    import fandom_composition_probe as fandom_probe
except ImportError:
    from tools.experiments.abyss import abyss_join_probe as join_probe
    from tools.experiments.abyss import fandom_composition_probe as fandom_probe


GENERIC_HEADING_TOKENS = {
    "level",
    "scaling",
    "stat",
    "stats",
}


@dataclass(slots=True)
class EnemyPage:
    requested_url: str
    resolved_url: str
    requested_title: str
    resolved_title: str
    html_root: fandom_probe.HtmlNode
    redirects: list[dict[str, str]]


@dataclass(slots=True)
class HpTableCandidate:
    index: int
    heading_path: list[str]
    heading_ids: list[str | None]
    level_hp: dict[int, int]
    table_source_path: str
    extraction_note: str


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


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_number(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


def _display_hp(value: float | None) -> int | None:
    if value is None:
        return None
    return int(math.floor(value + 0.5))


def _format_hp(value: float | None) -> str | None:
    display = _display_hp(value)
    return f"{display:,}" if display is not None else None


def _redirect_target(root: fandom_probe.HtmlNode) -> tuple[str, str] | None:
    redirect = fandom_probe._first(
        root,
        lambda node: node.tag == "div"
        and fandom_probe._has_class(node, "redirectMsg"),
    )
    if redirect is None:
        return None
    link = fandom_probe._first(redirect, lambda node: node.tag == "a")
    if link is None:
        return None
    href = link.attrs.get("href")
    title = link.attrs.get("title") or fandom_probe._compact_text(link)
    if not href:
        return None
    return urljoin(fandom_probe.FANDOM_BASE_URL, href), title


def _fetch_enemy_page(url: str) -> EnemyPage:
    requested_url = url
    requested_title = fandom_probe.page_title_from_fandom_url(url)
    redirects: list[dict[str, str]] = []
    current_url = url
    current_title = requested_title
    for _ in range(5):
        rendered_html, parse_payload = fandom_probe.fetch_rendered_html(current_title)
        root = fandom_probe.parse_fragment(rendered_html)
        target = _redirect_target(root)
        if target is None:
            return EnemyPage(
                requested_url=requested_url,
                resolved_url=current_url,
                requested_title=requested_title,
                resolved_title=str(parse_payload.get("title") or current_title),
                html_root=root,
                redirects=redirects,
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
        current_title = fandom_probe.page_title_from_fandom_url(next_url)
    raise fandom_probe.ProbeError(f"Redirect loop while resolving {requested_url}")


def _row_cells(row: fandom_probe.HtmlNode) -> list[str]:
    return [
        fandom_probe._compact_text(cell)
        for cell in fandom_probe._direct_elements(row)
        if cell.tag in {"th", "td"}
    ]


def _parse_level_hp_table(table: fandom_probe.HtmlNode) -> dict[int, int] | None:
    if not fandom_probe._has_class(table, "article-table"):
        return None
    rows = fandom_probe._find_all(table, lambda node: node.tag == "tr")
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


def _iter_hp_tables(
    root: fandom_probe.HtmlNode,
) -> list[HpTableCandidate]:
    candidates: list[HpTableCandidate] = []

    def walk(node: fandom_probe.HtmlNode, heading_stack: list[tuple[int, str, str | None]]) -> None:
        current_stack = heading_stack
        for child in node.children:
            if not isinstance(child, fandom_probe.HtmlNode):
                continue
            level = fandom_probe._heading_level(child)
            if level is not None:
                current_stack = [
                    item for item in current_stack if item[0] < level
                ]
                current_stack.append(
                    (
                        level,
                        _clean_heading(fandom_probe._compact_text(child)),
                        fandom_probe._headline_id(child),
                    )
                )
            if child.tag == "table":
                level_hp = _parse_level_hp_table(child)
                if level_hp:
                    index = len(candidates)
                    headings = [item[1] for item in current_stack]
                    heading_ids = [item[2] for item in current_stack]
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


def _candidate_heading_for_match(candidate: HpTableCandidate) -> str:
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


def _select_hp_table(
    candidates: list[HpTableCandidate],
    *,
    enemy_name: str,
) -> tuple[HpTableCandidate | None, str, str, list[str]]:
    warnings: list[str] = []
    if not candidates:
        return None, "no_level_hp_table", "none", ["enemy_page_level_hp_table_missing"]
    if len(candidates) == 1:
        return candidates[0], "single_clear_table", "high", []

    scored = [
        (_score_table(candidate, enemy_name), candidate)
        for candidate in candidates
    ]
    positive = [
        item for item in scored if item[0][0] > 0.0
    ]
    if not positive:
        return (
            None,
            "multiple_tables_no_heading_match",
            "none",
            ["multiple_level_hp_tables_no_heading_match"],
        )
    positive.sort(key=lambda item: item[0], reverse=True)
    best_score, best_candidate = positive[0]
    tied = [
        candidate
        for score, candidate in positive
        if score == best_score
    ]
    if len(tied) > 1:
        return (
            None,
            "multiple_tables_ambiguous_heading_match",
            "none",
            [
                "multiple_level_hp_tables_ambiguous_heading_match:"
                + ",".join(_candidate_heading_for_match(candidate) for candidate in tied)
            ],
        )
    ratio, exactish, _ = best_score
    method = "heading_exact_match" if exactish else "heading_token_match"
    confidence = "high" if ratio >= 1.0 else "medium"
    warnings.append("selected_from_multiple_level_hp_tables_by_heading")
    return best_candidate, method, confidence, warnings


def _fallback_hp_row(
    row: dict[str, Any],
    *,
    page: EnemyPage | None,
    table: HpTableCandidate | None,
    table_match_method: str,
    table_match_confidence: str,
    hp_multiplier: float,
    multiplier_source: str,
    warnings: list[str],
) -> dict[str, Any]:
    level = _as_int(row.get("level"))
    raw_hp: int | None = None
    if table is not None and level is not None:
        raw_hp = table.level_hp.get(level)
        if raw_hp is None:
            warnings.append(f"level_hp_missing_for_level:{level}")
    resolved_hp = raw_hp * hp_multiplier if raw_hp is not None else None
    selected_heading = _candidate_heading_for_match(table) if table else None
    return {
        "floor": _as_int(row.get("floor")),
        "chamber": _as_int(row.get("chamber")),
        "side": _as_int(row.get("side")),
        "side_name": row.get("side_name"),
        "wave": _as_int(row.get("wave")),
        "count": _as_int(row.get("count")),
        "fandom_display_name": row.get("display_name"),
        "enemy_page_url": row.get("enemy_page_url"),
        "requested_enemy_page_url": page.requested_url if page else row.get("enemy_page_url"),
        "resolved_enemy_page_url": page.resolved_url if page else None,
        "redirects": page.redirects if page else [],
        "display_level": level,
        "selected_table_section_heading": selected_heading,
        "selected_table_heading_path": table.heading_path if table else [],
        "table_match_method": table_match_method,
        "table_match_confidence": table_match_confidence,
        "raw_enemy_page_hp": raw_hp,
        "raw_enemy_page_hp_formatted": f"{raw_hp:,}" if raw_hp is not None else None,
        "hp_multiplier": hp_multiplier,
        "hp_multiplier_source": multiplier_source,
        "fallback_resolved_hp": resolved_hp,
        "fallback_resolved_hp_display": _display_hp(resolved_hp),
        "fallback_resolved_hp_display_formatted": _format_hp(resolved_hp),
        "source_path": (
            f"{table.table_source_path}/level[{level}].hp"
            if table is not None and level is not None
            else None
        ),
        "extraction_note": table.extraction_note if table else None,
        "warnings": warnings,
    }


def _comparison_status(
    fallback_hp: float | None,
    nanoka_hp: float | None,
) -> tuple[str, float | None, float | None]:
    if fallback_hp is None or nanoka_hp is None:
        return "unavailable", None, None
    delta = fallback_hp - nanoka_hp
    pct = (delta / nanoka_hp * 100.0) if nanoka_hp else None
    if _display_hp(fallback_hp) == _display_hp(nanoka_hp):
        return "exact", delta, pct
    if pct is not None and abs(pct) <= 1.0:
        return "close", delta, pct
    return "different", delta, pct


def _join_rows_by_source_path(join_report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not join_report:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in join_report.get("joined_rows", []):
        source_path = row.get("fandom_raw_source_path")
        if source_path:
            result[str(source_path)] = row
    return result


def _attach_nanoka_comparison(
    fallback_row: dict[str, Any],
    join_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not join_row:
        fallback_row["nanoka_comparison"] = {
            "status": "unavailable",
            "warnings": ["nanoka_join_row_missing"],
        }
        return fallback_row
    nanoka_hp = _as_float(join_row.get("nanoka_hp"))
    fallback_hp = _as_float(fallback_row.get("fallback_resolved_hp"))
    status, delta, pct = _comparison_status(fallback_hp, nanoka_hp)
    delta_absolute = abs(delta) if delta is not None else None
    fallback_row["nanoka_comparison"] = {
        "status": status,
        "primary_display_name": join_row.get("primary_display_name"),
        "nanoka_display_name": join_row.get("nanoka_display_name"),
        "nanoka_monster_id": join_row.get("nanoka_monster_id"),
        "nanoka_hp": nanoka_hp,
        "nanoka_hp_display": join_row.get("nanoka_hp_display"),
        "nanoka_hp_display_formatted": join_row.get("nanoka_hp_display_formatted"),
        "match_method": join_row.get("match_method"),
        "match_confidence": join_row.get("match_confidence"),
        "delta_signed": delta,
        "delta_absolute": delta_absolute,
        "delta_absolute_display": _display_hp(delta_absolute)
        if delta_absolute is not None
        else None,
        "delta_percent": pct,
        "delta_percent_absolute": abs(pct) if pct is not None else None,
        "warnings": join_row.get("warnings", []),
    }
    return fallback_row


def _fandom_composition_report(args: argparse.Namespace) -> dict[str, Any]:
    return fandom_probe.build_report(
        argparse.Namespace(
            period_url=args.period_url,
            floor=args.floor,
            indent=2,
        )
    )


def _join_report(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.tower_id:
        return None
    return join_probe.build_report(
        argparse.Namespace(
            period_url=args.period_url,
            tower_id=str(args.tower_id),
            floor=args.floor,
            locale=args.locale,
            indent=2,
        )
    )


def _build_fallback_rows(
    composition_report: dict[str, Any],
    join_report: dict[str, Any] | None,
    *,
    hp_multiplier: float,
    multiplier_source: str,
) -> list[dict[str, Any]]:
    page_cache: dict[str, EnemyPage] = {}
    tables_cache: dict[str, list[HpTableCandidate]] = {}
    join_by_source = _join_rows_by_source_path(join_report)
    fallback_rows: list[dict[str, Any]] = []
    for row in composition_report.get("enemy_rows", []):
        warnings: list[str] = []
        page_url = row.get("enemy_page_url")
        page: EnemyPage | None = None
        table: HpTableCandidate | None = None
        table_method = "enemy_page_unavailable"
        table_confidence = "none"
        if not page_url:
            warnings.append("enemy_page_url_missing")
        else:
            try:
                page = page_cache.get(page_url)
                if page is None:
                    page = _fetch_enemy_page(page_url)
                    page_cache[page_url] = page
                candidates = tables_cache.get(page.resolved_url)
                if candidates is None:
                    candidates = _iter_hp_tables(page.html_root)
                    tables_cache[page.resolved_url] = candidates
                table, table_method, table_confidence, table_warnings = _select_hp_table(
                    candidates,
                    enemy_name=str(row.get("display_name") or ""),
                )
                warnings.extend(table_warnings)
            except Exception as exc:  # experiment should report page failures
                warnings.append(f"enemy_page_fetch_or_parse_failed:{exc}")
        fallback_row = _fallback_hp_row(
            row,
            page=page,
            table=table,
            table_match_method=table_method,
            table_match_confidence=table_confidence,
            hp_multiplier=hp_multiplier,
            multiplier_source=multiplier_source,
            warnings=warnings,
        )
        fallback_rows.append(
            _attach_nanoka_comparison(
                fallback_row,
                join_by_source.get(str(row.get("raw_source_path"))),
            )
        )
    return fallback_rows


def _comparison_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for row in rows:
        status = row.get("nanoka_comparison", {}).get("status", "unavailable")
        statuses[status] = statuses.get(status, 0) + 1
    unresolved = [
        {
            "fandom_display_name": row.get("fandom_display_name"),
            "floor": row.get("floor"),
            "chamber": row.get("chamber"),
            "side": row.get("side"),
            "wave": row.get("wave"),
            "table_match_method": row.get("table_match_method"),
            "table_match_confidence": row.get("table_match_confidence"),
            "warnings": row.get("warnings"),
        }
        for row in rows
        if row.get("fallback_resolved_hp") is None
    ]
    return {
        "row_count": len(rows),
        "fallback_hp_available_count": sum(
            1 for row in rows if row.get("fallback_resolved_hp") is not None
        ),
        "fallback_hp_unavailable_count": sum(
            1 for row in rows if row.get("fallback_resolved_hp") is None
        ),
        "nanoka_comparison_status_counts": statuses,
        "unresolved_fallback_rows": unresolved,
    }


def _find_row(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("fandom_display_name") == name:
            return row
    return None


def _composition_fisher_check(composition_report: dict[str, Any]) -> dict[str, Any] | None:
    source_url = composition_report.get("source", {}).get("url", "")
    if "2026-02-16" not in source_url:
        return None
    rows = [
        row
        for row in composition_report.get("enemy_rows", [])
        if row.get("floor") == 12
        and row.get("chamber") == 1
        and row.get("side") == 1
    ]
    observed = [
        {
            "wave": row.get("wave"),
            "display_name": row.get("display_name"),
            "count": row.get("count"),
        }
        for row in rows
    ]
    passed = len(rows) == 5 and all(
        row.get("display_name") == "Fisher of Hidden Depths"
        and row.get("count") == 3
        for row in rows
    )
    return {
        "id": "2026-02-16_floor12_chamber1_first_half_composition",
        "passed": passed,
        "expected": "Five sequential Fisher of Hidden Depths waves, count 3 each.",
        "observed": observed,
    }


def _rock_crab_check(rows: list[dict[str, Any]], source_url: str) -> dict[str, Any] | None:
    if "2026-05-16" not in source_url:
        return None
    row = _find_row(rows, "Battle-Scarred Rock Crab")
    if row is None:
        return {
            "id": "2026-05-16_battle_scarred_rock_crab_table",
            "passed": False,
            "expected": "Battle-Scarred table with raw Lv.100 HP 1,175,752.",
            "observed": None,
        }
    passed = (
        row.get("selected_table_section_heading") == "Battle-Scarred"
        and row.get("raw_enemy_page_hp") == 1175752
        and row.get("fallback_resolved_hp_display") == 4409070
    )
    return {
        "id": "2026-05-16_battle_scarred_rock_crab_table",
        "passed": passed,
        "expected": (
            "Select Battle-Scarred table by heading, raw Lv.100 HP 1,175,752, "
            "resolved HP 4,409,070 at multiplier 3.75."
        ),
        "observed": {
            "selected_table_section_heading": row.get("selected_table_section_heading"),
            "raw_enemy_page_hp": row.get("raw_enemy_page_hp"),
            "fallback_resolved_hp_display": row.get("fallback_resolved_hp_display"),
            "nanoka_status": row.get("nanoka_comparison", {}).get("status"),
            "nanoka_hp_display": row.get("nanoka_comparison", {}).get("nanoka_hp_display"),
        },
    }


def _special_case_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {
        "Battle-Scarred Rock Crab",
        "Hexadecatonic Battle-Hardened Mandragora",
        "Primo Geovishap (Cryo)",
    }
    return [
        {
            "fandom_display_name": row.get("fandom_display_name"),
            "selected_table_section_heading": row.get("selected_table_section_heading"),
            "table_match_method": row.get("table_match_method"),
            "table_match_confidence": row.get("table_match_confidence"),
            "raw_enemy_page_hp": row.get("raw_enemy_page_hp"),
            "fallback_resolved_hp_display_formatted": row.get(
                "fallback_resolved_hp_display_formatted"
            ),
            "nanoka_display_name": row.get("nanoka_comparison", {}).get(
                "nanoka_display_name"
            ),
            "nanoka_hp_display_formatted": row.get("nanoka_comparison", {}).get(
                "nanoka_hp_display_formatted"
            ),
            "comparison_status": row.get("nanoka_comparison", {}).get("status"),
            "delta_percent": row.get("nanoka_comparison", {}).get("delta_percent"),
            "warnings": row.get("warnings"),
        }
        for row in rows
        if row.get("fandom_display_name") in names
    ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    composition_report = _fandom_composition_report(args)
    join_report = _join_report(args)
    multiplier = float(args.hp_multiplier) if args.hp_multiplier is not None else 1.0
    multiplier_source = (
        "explicit_manual" if args.hp_multiplier is not None else "default_identity"
    )
    warnings = [
        "Research/debug output only; do not wire this script into production UI.",
        "Nanoka remains the primary resolved HP source; Fandom enemy-page HP is a fallback/cross-check.",
        "The Fandom table selector uses enemy-page headings and never chooses a table by closeness to Nanoka HP.",
    ]
    if args.hp_multiplier is None:
        warnings.append("No --hp-multiplier supplied; fallback HP uses identity multiplier 1.0.")
    rows = _build_fallback_rows(
        composition_report,
        join_report,
        hp_multiplier=multiplier,
        multiplier_source=multiplier_source,
    )
    regression_checks = [
        check
        for check in (
            _composition_fisher_check(composition_report),
            _rock_crab_check(rows, composition_report.get("source", {}).get("url", "")),
        )
        if check is not None
    ]
    return {
        "probe": {
            "name": "fandom_enemy_page_hp_fallback_probe",
            "experimental": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "warnings": warnings,
            "regression_checks": regression_checks,
        },
        "source": {
            "fandom_period_url": args.period_url,
            "tower_id": str(args.tower_id) if args.tower_id else None,
            "floor_requested": args.floor,
        },
        "hp_multiplier": {
            "value": multiplier,
            "source": multiplier_source,
        },
        "summary": _comparison_summary(rows),
        "special_case_rows": _special_case_rows(rows),
        "fallback_rows": rows,
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experiment-only Fandom enemy-page HP fallback probe. "
            "Parses level/HP tables and optionally compares fallback HP to Nanoka."
        )
    )
    parser.add_argument("--period-url", required=True)
    parser.add_argument("--tower-id")
    parser.add_argument(
        "--floor",
        action="append",
        type=int,
        help="Limit composition to one floor. May be supplied more than once.",
    )
    parser.add_argument(
        "--hp-multiplier",
        type=float,
        help="Explicit/manual Abyss HP multiplier, for example 3.75.",
    )
    parser.add_argument(
        "--locale",
        default="en",
        help="Nanoka localized static JSON folder when --tower-id is used. Default: en.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level. Default: 2.",
    )
    return parser


def main() -> int:
    parser = _build_argument_parser()
    args = parser.parse_args()
    report = build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=args.indent))
    failed = [
        check
        for check in report["probe"].get("regression_checks", [])
        if not check.get("passed")
    ]
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
