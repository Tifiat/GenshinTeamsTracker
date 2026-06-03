"""Production Abyss source-data model boundary.

This module is the first production-safe boundary for factual Abyss source
data. It intentionally does not fetch live network data by itself yet: callers
must provide already fetched Fandom composition and optional Nanoka tower
reports, or inject narrow loader callables. The current experiment probes under
`tools/experiments/abyss/` may adapt to this boundary later, but production code
must not import those scripts as runtime dependencies.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


FANDOM_PERIOD_URL_TEMPLATE = (
    "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/{period_start}"
)

HP_SOURCE_NANOKA_RESOLVED = "nanoka_resolved_hp"
HP_SOURCE_UNAVAILABLE = "unavailable"

MATCH_CONFIDENCE_NONE = "none"
MATCH_CONFIDENCE_LOW = "low"
MATCH_CONFIDENCE_MEDIUM = "medium"
MATCH_CONFIDENCE_HIGH = "high"
MATCH_METHOD_AMBIGUOUS = "ambiguous"
MATCH_METHOD_CONTEXT_UNIQUE = "context_unique_remaining"
MATCH_METHOD_MANUAL_ALIAS = "manual_alias"
MATCH_METHOD_STRICT = "strict_name"
MATCH_METHOD_UNMATCHED = "unmatched"
MATCH_METHOD_VARIANT_STRIP = "variant_strip"

MATCHED_CONFIDENCES = {
    MATCH_CONFIDENCE_HIGH,
    MATCH_CONFIDENCE_MEDIUM,
    MATCH_CONFIDENCE_LOW,
}

MANUAL_ALIAS_PAIRS = {
    ("statueofmarbleandbrass", "legatusgolem"): (
        "Fandom period pages display the boss as Statue of Marble and Brass; "
        "Nanoka tower JSON uses Legatus Golem."
    ),
}

CompositionReportLoader = Callable[[str, int], Mapping[str, Any]]
NanokaReportLoader = Callable[[str, int], Mapping[str, Any]]


class AbyssSourceDataUnavailable(RuntimeError):
    """Raised when the source-data boundary has no composition input."""


@dataclass(frozen=True, slots=True)
class AbyssPeriod:
    start_date: str
    end_date: str | None
    source: str


@dataclass(frozen=True, slots=True)
class AbyssEnemySourceRow:
    floor: int
    chamber: int
    side: int
    side_name: str
    wave: int
    enemy_count: int
    display_level: int | None
    primary_display_name: str
    fandom_enemy_page_url: str | None
    fandom_icon_url: str | None
    matched_nanoka_display_name: str | None
    nanoka_monster_id: str | None
    nanoka_icon_url: str | None
    nanoka_enemy_detail_url: str | None
    nanoka_hp: int | None
    hp_source: str
    match_method: str
    match_confidence: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AbyssWaveSourceData:
    wave: int
    enemies: tuple[AbyssEnemySourceRow, ...]
    solo_target_hp: int | None
    multi_target_hp: int | None
    selected_solo_enemy_name: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AbyssChamberSideSourceData:
    floor: int
    chamber: int
    side: int
    side_name: str
    waves: tuple[AbyssWaveSourceData, ...]
    solo_target_hp: int | None
    multi_target_hp: int | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AbyssFloorSourceData:
    floor: int
    period: AbyssPeriod
    source_urls: Mapping[str, str]
    enemy_rows: tuple[AbyssEnemySourceRow, ...]
    side_summaries: tuple[AbyssChamberSideSourceData, ...]
    global_warnings: tuple[str, ...] = ()

    @property
    def matched_count(self) -> int:
        return sum(
            1 for row in self.enemy_rows if row.match_confidence in MATCHED_CONFIDENCES
        )

    @property
    def unmatched_count(self) -> int:
        return sum(1 for row in self.enemy_rows if row.match_method == MATCH_METHOD_UNMATCHED)

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for row in self.enemy_rows if row.match_method == MATCH_METHOD_AMBIGUOUS)

    def side_summary(self, chamber: int, side: int) -> AbyssChamberSideSourceData:
        for summary in self.side_summaries:
            if summary.chamber == chamber and summary.side == side:
                return summary
        raise ValueError(f"Unsupported Abyss chamber/side: {chamber}/{side}")


def period_url_for_start(period_start: str) -> str:
    return FANDOM_PERIOD_URL_TEMPLATE.format(period_start=period_start)


def load_abyss_floor12_source_data(
    period_start: str,
    tower_id: str,
    *,
    composition_report: Mapping[str, Any] | None = None,
    nanoka_report: Mapping[str, Any] | None = None,
    composition_loader: CompositionReportLoader | None = None,
    nanoka_loader: NanokaReportLoader | None = None,
    floor: int = 12,
) -> AbyssFloorSourceData:
    """Build Floor 12 source data from production-safe source reports.

    The default normal path is Fandom composition plus Nanoka resolved HP. This
    function does not import or run experiment scripts; callers can pass reports
    directly or inject production loaders. If Nanoka data is unavailable, enemy
    HP remains unavailable with source warnings. Fandom enemy-page HP fallback is
    intentionally out of scope for this first production boundary.
    """

    period_url = period_url_for_start(period_start)
    if composition_report is None and composition_loader is not None:
        composition_report = composition_loader(period_url, floor)
    if composition_report is None:
        raise AbyssSourceDataUnavailable(
            "Abyss source data requires a Fandom composition report or loader."
        )

    if nanoka_report is None and nanoka_loader is not None:
        nanoka_report = nanoka_loader(str(tower_id), floor)

    return build_abyss_floor_source_data_from_reports(
        period_start=period_start,
        tower_id=str(tower_id),
        floor=floor,
        composition_report=composition_report,
        nanoka_report=nanoka_report,
    )


def build_abyss_floor_source_data_from_reports(
    *,
    period_start: str,
    tower_id: str,
    floor: int,
    composition_report: Mapping[str, Any],
    nanoka_report: Mapping[str, Any] | None = None,
) -> AbyssFloorSourceData:
    joined_rows = _join_rows(composition_report, nanoka_report or {})
    source_rows = tuple(_to_source_row(row) for row in joined_rows)
    side_summaries = tuple(_build_side_summaries(source_rows))
    global_warnings = _global_warnings(composition_report, nanoka_report or {}, source_rows)
    return AbyssFloorSourceData(
        floor=floor,
        period=AbyssPeriod(
            start_date=period_start,
            end_date=_period_end_date(nanoka_report or {}),
            source="fandom_period_plus_nanoka_tower",
        ),
        source_urls=_source_urls(composition_report, nanoka_report or {}, tower_id=tower_id),
        enemy_rows=source_rows,
        side_summaries=side_summaries,
        global_warnings=global_warnings,
    )


def _normalize_enemy_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def _variant_stripped_normalized_name(value: Any) -> str:
    text = re.sub(r"\s*\([^)]*\)\s*$", "", str(value or ""))
    return _normalize_enemy_name(text)


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


def _display_hp(value: float | int | None) -> int | None:
    if value is None:
        return None
    return int(float(value) + 0.5)


def _nanoka_tower(nanoka_report: Mapping[str, Any]) -> Mapping[str, Any]:
    towers = nanoka_report.get("towers") or []
    if not towers:
        return {}
    tower = towers[0]
    return tower if isinstance(tower, Mapping) else {}


def _nanoka_candidates(
    nanoka_report: Mapping[str, Any],
) -> dict[tuple[int, int, int], list[Mapping[str, Any]]]:
    result: dict[tuple[int, int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in _nanoka_tower(nanoka_report).get("enemy_rows", []):
        floor = _as_int(row.get("floor"))
        chamber = _as_int(row.get("chamber"))
        side = _as_int(row.get("side"))
        if floor is None or chamber is None or side is None:
            continue
        result[(floor, chamber, side)].append(row)
    return result


def _nanoka_identity(candidate: Mapping[str, Any]) -> str:
    return "|".join(
        str(part or "")
        for part in (
            candidate.get("monster_id"),
            candidate.get("hp_source_path"),
            candidate.get("enemy_display_name"),
        )
    )


def _base_join_row(row: Mapping[str, Any]) -> dict[str, Any]:
    fandom_name = row.get("display_name")
    normalized = _normalize_enemy_name(fandom_name)
    return {
        "floor": _as_int(row.get("floor")),
        "chamber": _as_int(row.get("chamber")),
        "side": _as_int(row.get("side")),
        "side_name": str(row.get("side_name") or ""),
        "wave": _as_int(row.get("wave")) or 1,
        "primary_display_name": str(fandom_name or ""),
        "fandom_display_name": str(fandom_name or ""),
        "fandom_normalized_enemy_name": normalized,
        "fandom_enemy_count": _as_int(row.get("count")) or 1,
        "fandom_level": _as_int(row.get("level")),
        "fandom_enemy_page_url": row.get("enemy_page_url"),
        "fandom_icon_url": row.get("icon_url"),
    }


def _unmatched_row(base: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **base,
        "nanoka_display_name": None,
        "nanoka_monster_id": None,
        "nanoka_icon_url": None,
        "nanoka_enemy_detail_url": None,
        "nanoka_hp": None,
        "match_method": MATCH_METHOD_UNMATCHED,
        "match_confidence": MATCH_CONFIDENCE_NONE,
        "warnings": ["nanoka_match_unavailable"],
    }


def _ambiguous_row(
    base: Mapping[str, Any],
    *,
    method: str,
    candidates: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        **base,
        "nanoka_display_name": None,
        "nanoka_monster_id": None,
        "nanoka_icon_url": None,
        "nanoka_enemy_detail_url": None,
        "nanoka_hp": None,
        "match_method": MATCH_METHOD_AMBIGUOUS,
        "attempted_match_method": method,
        "match_confidence": MATCH_CONFIDENCE_NONE,
        "warnings": [f"nanoka_match_ambiguous:{method}:candidates={len(candidates)}"],
    }


def _matched_row(
    base: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    method: str,
    confidence: str,
    warnings: tuple[str, ...] = (),
) -> dict[str, Any]:
    row_warnings = list(warnings)
    fandom_level = _as_int(base.get("fandom_level"))
    nanoka_level = _as_int(candidate.get("level"))
    if fandom_level is not None and nanoka_level is not None and fandom_level != nanoka_level:
        row_warnings.append(f"level_mismatch:fandom={fandom_level}:nanoka={nanoka_level}")
    hp = _display_hp(_as_float(candidate.get("hp_resolved")))
    if hp is None:
        row_warnings.append("nanoka_hp_missing")
    return {
        **base,
        "nanoka_display_name": candidate.get("enemy_display_name"),
        "nanoka_monster_id": candidate.get("monster_id"),
        "nanoka_icon_url": candidate.get("icon_url"),
        "nanoka_enemy_detail_url": candidate.get("enemy_detail_url"),
        "nanoka_hp": hp,
        "nanoka_candidate_identity": _nanoka_identity(candidate),
        "match_method": method,
        "match_confidence": confidence,
        "warnings": row_warnings,
    }


def _candidate_normalized_name(candidate: Mapping[str, Any]) -> str:
    return _normalize_enemy_name(candidate.get("enemy_display_name"))


def _candidate_variant_stripped_name(candidate: Mapping[str, Any]) -> str:
    return _variant_stripped_normalized_name(candidate.get("enemy_display_name"))


def _match_candidates(
    base: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    method: str,
) -> dict[str, Any] | None:
    fandom_normalized = str(base.get("fandom_normalized_enemy_name") or "")
    fandom_stripped = _variant_stripped_normalized_name(base.get("fandom_display_name"))
    if method == MATCH_METHOD_STRICT:
        matches = [
            candidate
            for candidate in candidates
            if _candidate_normalized_name(candidate) == fandom_normalized
        ]
        warnings: tuple[str, ...] = ()
        confidence = MATCH_CONFIDENCE_HIGH
    elif method == MATCH_METHOD_MANUAL_ALIAS:
        matches = [
            candidate
            for candidate in candidates
            if (fandom_normalized, _candidate_normalized_name(candidate))
            in MANUAL_ALIAS_PAIRS
        ]
        warnings = tuple(
            [
                "non_strict_match:manual_alias",
                *[
                    MANUAL_ALIAS_PAIRS[
                        (fandom_normalized, _candidate_normalized_name(candidate))
                    ]
                    for candidate in matches[:1]
                ],
            ]
        )
        confidence = MATCH_CONFIDENCE_HIGH
    elif method == MATCH_METHOD_VARIANT_STRIP:
        if fandom_stripped == fandom_normalized:
            return None
        matches = [
            candidate
            for candidate in candidates
            if _candidate_variant_stripped_name(candidate) == fandom_stripped
        ]
        warnings = ("non_strict_match:variant_strip",)
        confidence = MATCH_CONFIDENCE_MEDIUM
    else:
        raise ValueError(f"Unsupported match method: {method}")

    if not matches:
        return None
    if len(matches) > 1:
        return _ambiguous_row(base, method=method, candidates=matches)
    return _matched_row(
        base,
        matches[0],
        method=method,
        confidence=confidence,
        warnings=warnings,
    )


def _initial_match_row(
    row: Mapping[str, Any],
    candidates_by_side: dict[tuple[int, int, int], list[Mapping[str, Any]]],
) -> dict[str, Any]:
    base = _base_join_row(row)
    side_key = (
        _as_int(base.get("floor")),
        _as_int(base.get("chamber")),
        _as_int(base.get("side")),
    )
    candidates = candidates_by_side.get(side_key, [])
    for method in (
        MATCH_METHOD_STRICT,
        MATCH_METHOD_MANUAL_ALIAS,
        MATCH_METHOD_VARIANT_STRIP,
    ):
        matched = _match_candidates(base, candidates, method=method)
        if matched is not None:
            return matched
    return _unmatched_row(base)


def _apply_context_unique_remaining(
    rows: list[dict[str, Any]],
    candidates_by_side: dict[tuple[int, int, int], list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    grouped_indexes: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        floor = _as_int(row.get("floor"))
        chamber = _as_int(row.get("chamber"))
        side = _as_int(row.get("side"))
        if floor is not None and chamber is not None and side is not None:
            grouped_indexes[(floor, chamber, side)].append(index)

    for side_key, indexes in grouped_indexes.items():
        unmatched_indexes = [
            index
            for index in indexes
            if rows[index].get("match_method") == MATCH_METHOD_UNMATCHED
        ]
        if len(unmatched_indexes) != 1:
            continue
        other_rows = [rows[index] for index in indexes if index != unmatched_indexes[0]]
        if any(row.get("match_method") == MATCH_METHOD_AMBIGUOUS for row in other_rows):
            continue
        if any(row.get("match_confidence") == MATCH_CONFIDENCE_NONE for row in other_rows):
            continue
        used_candidate_identities = {
            str(row.get("nanoka_candidate_identity"))
            for row in (rows[index] for index in indexes)
            if row.get("nanoka_candidate_identity")
        }
        unused_candidates = [
            candidate
            for candidate in candidates_by_side.get(side_key, [])
            if _nanoka_identity(candidate) not in used_candidate_identities
        ]
        if len(unused_candidates) != 1:
            continue
        index = unmatched_indexes[0]
        rows[index] = _matched_row(
            rows[index],
            unused_candidates[0],
            method=MATCH_METHOD_CONTEXT_UNIQUE,
            confidence=MATCH_CONFIDENCE_LOW,
            warnings=(
                "non_strict_match:context_unique_remaining",
                "Only one unmatched Fandom enemy and one unmatched Nanoka enemy "
                "remained in this chamber side after other rows matched.",
            ),
        )
    return rows


def _join_rows(
    composition_report: Mapping[str, Any],
    nanoka_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates_by_side = _nanoka_candidates(nanoka_report)
    rows = [
        _initial_match_row(row, candidates_by_side)
        for row in composition_report.get("enemy_rows", [])
    ]
    return _apply_context_unique_remaining(rows, candidates_by_side)


def _to_source_row(row: Mapping[str, Any]) -> AbyssEnemySourceRow:
    hp = _as_int(row.get("nanoka_hp"))
    return AbyssEnemySourceRow(
        floor=_as_int(row.get("floor")) or 0,
        chamber=_as_int(row.get("chamber")) or 0,
        side=_as_int(row.get("side")) or 0,
        side_name=str(row.get("side_name") or ""),
        wave=_as_int(row.get("wave")) or 1,
        enemy_count=_as_int(row.get("fandom_enemy_count")) or 1,
        display_level=_as_int(row.get("fandom_level")),
        primary_display_name=str(row.get("primary_display_name") or ""),
        fandom_enemy_page_url=_optional_str(row.get("fandom_enemy_page_url")),
        fandom_icon_url=_optional_str(row.get("fandom_icon_url")),
        matched_nanoka_display_name=_optional_str(row.get("nanoka_display_name")),
        nanoka_monster_id=_optional_str(row.get("nanoka_monster_id")),
        nanoka_icon_url=_optional_str(row.get("nanoka_icon_url")),
        nanoka_enemy_detail_url=_optional_str(row.get("nanoka_enemy_detail_url")),
        nanoka_hp=hp,
        hp_source=HP_SOURCE_NANOKA_RESOLVED if hp is not None else HP_SOURCE_UNAVAILABLE,
        match_method=str(row.get("match_method") or MATCH_METHOD_UNMATCHED),
        match_confidence=str(row.get("match_confidence") or MATCH_CONFIDENCE_NONE),
        warnings=tuple(str(warning) for warning in row.get("warnings", [])),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _build_side_summaries(
    rows: tuple[AbyssEnemySourceRow, ...],
) -> list[AbyssChamberSideSourceData]:
    grouped: dict[tuple[int, int, int], list[AbyssEnemySourceRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.floor, row.chamber, row.side)].append(row)
    return [
        _build_side_summary(floor, chamber, side, tuple(side_rows))
        for (floor, chamber, side), side_rows in sorted(grouped.items())
    ]


def _build_side_summary(
    floor: int,
    chamber: int,
    side: int,
    rows: tuple[AbyssEnemySourceRow, ...],
) -> AbyssChamberSideSourceData:
    waves: list[AbyssWaveSourceData] = []
    rows_by_wave: dict[int, list[AbyssEnemySourceRow]] = defaultdict(list)
    for row in rows:
        rows_by_wave[row.wave].append(row)
    for wave, wave_rows in sorted(rows_by_wave.items()):
        waves.append(_build_wave_summary(wave, tuple(wave_rows)))
    solo_values = [wave.solo_target_hp for wave in waves if wave.solo_target_hp is not None]
    multi_values = [wave.multi_target_hp for wave in waves if wave.multi_target_hp is not None]
    warnings = sorted(
        {
            warning
            for row in rows
            for warning in row.warnings
        }
        | {
            warning
            for wave_summary in waves
            for warning in wave_summary.warnings
        }
    )
    if any(row.nanoka_hp is None for row in rows):
        warnings.append("side_hp_partial_or_unavailable")
    return AbyssChamberSideSourceData(
        floor=floor,
        chamber=chamber,
        side=side,
        side_name=next((row.side_name for row in rows if row.side_name), ""),
        waves=tuple(waves),
        solo_target_hp=sum(solo_values) if solo_values else None,
        multi_target_hp=sum(multi_values) if multi_values else None,
        warnings=tuple(warnings),
    )


def _build_wave_summary(
    wave: int,
    rows: tuple[AbyssEnemySourceRow, ...],
) -> AbyssWaveSourceData:
    matched_rows = [row for row in rows if row.nanoka_hp is not None]
    selected_solo = max(matched_rows, key=lambda row: row.nanoka_hp or 0) if matched_rows else None
    warnings = [
        f"missing_hp:{row.primary_display_name}"
        for row in rows
        if row.nanoka_hp is None
    ]
    return AbyssWaveSourceData(
        wave=wave,
        enemies=rows,
        solo_target_hp=selected_solo.nanoka_hp if selected_solo else None,
        multi_target_hp=sum(
            (row.nanoka_hp or 0) * row.enemy_count for row in matched_rows
        )
        if matched_rows
        else None,
        selected_solo_enemy_name=selected_solo.primary_display_name
        if selected_solo
        else None,
        warnings=tuple(warnings),
    )


def _period_end_date(nanoka_report: Mapping[str, Any]) -> str | None:
    period = _nanoka_tower(nanoka_report).get("period", {})
    if not isinstance(period, Mapping):
        return None
    return _optional_str(
        period.get("detail_close")
        or period.get("summary_end")
        or period.get("live_end")
    )


def _source_urls(
    composition_report: Mapping[str, Any],
    nanoka_report: Mapping[str, Any],
    *,
    tower_id: str,
) -> Mapping[str, str]:
    source = composition_report.get("source", {})
    if not isinstance(source, Mapping):
        source = {}
    tower = _nanoka_tower(nanoka_report)
    nanoka_urls = tower.get("source_urls", {})
    if not isinstance(nanoka_urls, Mapping):
        nanoka_urls = {}
    result = {
        "fandom_period_url": str(
            source.get("url") or period_url_for_start(str(source.get("period_date_from_url") or ""))
        ),
        "fandom_mediawiki_parse_api_url": str(
            source.get("mediawiki_parse_api_url") or ""
        ),
        "nanoka_page_url": str(
            nanoka_urls.get("page_url") or f"https://gi.nanoka.cc/tower/{tower_id}/"
        ),
    }
    for key in ("manifest_json_url", "detail_json_url"):
        if nanoka_urls.get(key):
            result[f"nanoka_{key}"] = str(nanoka_urls[key])
    return result


def _global_warnings(
    composition_report: Mapping[str, Any],
    nanoka_report: Mapping[str, Any],
    rows: tuple[AbyssEnemySourceRow, ...],
) -> tuple[str, ...]:
    warnings: set[str] = set()
    for floor in composition_report.get("floors", []):
        for warning in floor.get("warnings", []):
            warnings.add(str(warning))
        for chamber in floor.get("chambers", []):
            for side in chamber.get("sides", []):
                for warning in side.get("warnings", []):
                    warnings.add(str(warning))
    if not _nanoka_tower(nanoka_report):
        warnings.add("nanoka_report_unavailable")
    probe = nanoka_report.get("probe", {})
    if isinstance(probe, Mapping):
        for warning in probe.get("warnings", []):
            warnings.add(str(warning))
    for row in rows:
        warnings.update(row.warnings)
    return tuple(sorted(warnings))
