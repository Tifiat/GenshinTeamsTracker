"""Experiment-only probe for current Nanoka Spiral Abyss tower data.

This script intentionally has no production imports. It discovers Nanoka's
versioned static JSON routes from the public tower page and prints a report for
manual review.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


NANOKA_SITE_BASE = "https://gi.nanoka.cc"
NANOKA_TOWER_INDEX_URL = f"{NANOKA_SITE_BASE}/tower"
NANOKA_ICON_BASE = "https://static.nanoka.cc/assets/gi"
SOURCE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
USER_AGENT = "GenshinTeamsTracker-NanokaTowerProbe/1.0"


class ProbeError(RuntimeError):
    """Raised when the experimental source cannot be discovered or decoded."""


class _FetchedDataUrlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.data_urls: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "script":
            return
        attr_map = dict(attrs)
        data_url = attr_map.get("data-url")
        if "data-sveltekit-fetched" in attr_map and data_url:
            self.data_urls.append(data_url)


def _fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ProbeError(f"Failed to fetch {url}: {exc}") from exc


def _fetch_text(url: str) -> str:
    return _fetch_bytes(url).decode("utf-8")


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        payload = json.loads(_fetch_text(url))
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Failed to decode JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProbeError(f"Expected a JSON object from {url}")
    return payload


def _discover_manifest_url() -> str:
    parser = _FetchedDataUrlParser()
    parser.feed(_fetch_text(NANOKA_TOWER_INDEX_URL))
    candidates = [
        url for url in parser.data_urls if url.rstrip("/").endswith("/tower.json")
    ]
    if not candidates:
        raise ProbeError(
            "Nanoka tower page did not expose an embedded fetched tower.json URL"
        )
    return candidates[0]


def _static_data_base_url(manifest_url: str) -> str:
    suffix = "/tower.json"
    normalized = manifest_url.rstrip("/")
    if not normalized.endswith(suffix):
        raise ProbeError(f"Unexpected Nanoka tower manifest URL: {manifest_url}")
    return normalized[: -len(suffix)]


def _data_version(manifest_url: str) -> str | None:
    match = re.search(r"/gi/([^/]+)/tower\.json$", manifest_url)
    return match.group(1) if match else None


def _parse_source_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, SOURCE_TIMESTAMP_FORMAT)
    except ValueError:
        return None


def _parse_reference_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    normalized = value.replace("T", " ")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProbeError(
            "--at must use an ISO-like timestamp such as 2026-06-02 12:30:00"
        ) from exc
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone().replace(tzinfo=None)
    return timestamp


def _summary_is_live(summary: dict[str, Any], reference_time: datetime) -> bool:
    begin = _parse_source_timestamp(summary.get("live_begin"))
    end = _parse_source_timestamp(summary.get("live_end"))
    return bool(begin and end and begin <= reference_time <= end)


def _summary_sort_key(summary: dict[str, Any]) -> tuple[datetime, int, str]:
    timestamp = (
        _parse_source_timestamp(summary.get("live_begin"))
        or _parse_source_timestamp(summary.get("begin"))
        or datetime.min
    )
    raw_id = str(summary.get("id", ""))
    try:
        numeric_id = int(raw_id)
    except ValueError:
        numeric_id = -1
    return timestamp, numeric_id, raw_id


def _tower_summaries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = manifest.get("tower")
    if isinstance(raw_items, list):
        return [item for item in raw_items if isinstance(item, dict)]

    summaries: list[dict[str, Any]] = []
    for tower_id, summary in manifest.items():
        if isinstance(summary, dict):
            summaries.append({"id": str(tower_id), **summary})
    if not summaries:
        raise ProbeError("Nanoka tower manifest does not contain tower summaries")
    return summaries


def _choose_tower_summary(
    summaries: list[dict[str, Any]],
    *,
    tower_id: str | None,
    history_index: int | None,
    reference_time: datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    by_id = {str(item.get("id")): item for item in summaries}

    if tower_id is not None:
        summary = by_id.get(str(tower_id))
        if summary is None:
            warnings.append(
                f"Tower id {tower_id} is absent from the discovered manifest; "
                "the detail JSON route will still be attempted."
            )
            summary = {"id": str(tower_id)}
        return summary, {"mode": "explicit_tower_id", "tower_id": str(tower_id)}, warnings

    ordered = sorted(summaries, key=_summary_sort_key, reverse=True)
    if history_index is not None:
        if history_index < 0 or history_index >= len(ordered):
            raise ProbeError(
                f"--history-index must be in range 0..{max(0, len(ordered) - 1)}"
            )
        summary = ordered[history_index]
        return (
            summary,
            {
                "mode": "history_index",
                "history_index": history_index,
                "ordering": "descending live_begin if present, then begin, then numeric tower id",
                "tower_id": str(summary.get("id")),
                "manifest_tower_count": len(ordered),
            },
            warnings,
        )

    live_candidates = [
        item for item in summaries if _summary_is_live(item, reference_time)
    ]
    if not live_candidates:
        raise ProbeError(
            "No live tower interval contains the reference timestamp "
            f"{reference_time.strftime(SOURCE_TIMESTAMP_FORMAT)}"
        )
    live_candidates.sort(key=_summary_sort_key, reverse=True)
    if len(live_candidates) > 1:
        warnings.append(
            "Multiple manifest live intervals contain the reference timestamp; "
            "the newest live_begin interval was selected."
        )
    summary = live_candidates[0]
    return (
        summary,
        {
            "mode": "active_live",
            "reference_timestamp": reference_time.strftime(SOURCE_TIMESTAMP_FORMAT),
            "matching_tower_ids": [
                str(candidate.get("id")) for candidate in live_candidates
            ],
            "tower_id": str(summary.get("id")),
        },
        warnings,
    )


def _sorted_mapping_items(mapping: Any) -> list[tuple[str, Any]]:
    if not isinstance(mapping, dict):
        return []

    def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        key = item[0]
        try:
            return int(key), key
        except ValueError:
            return sys.maxsize, key

    return sorted(mapping.items(), key=sort_key)


def _normalized_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.lower()))


def _candidate_key(value: Any) -> str | None:
    normalized = _normalized_name(value)
    return normalized.replace(" ", "") if normalized else None


def _nanoka_display_hp(value: Any) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    return int(math.floor(float(value) + 0.5))


def _enemy_report(
    enemy: Any,
    *,
    floor_number: str,
    chamber_number: str,
    side_number: int,
    source_side: str,
    enemy_index: int,
    level: Any,
) -> dict[str, Any]:
    source_path = (
        f'$.floor["{floor_number}"].room["{chamber_number}"]'
        f".{source_side}[{enemy_index}]"
    )
    warnings: list[str] = []
    if not isinstance(enemy, dict):
        return {
            "floor": int(floor_number),
            "chamber": int(chamber_number),
            "side": side_number,
            "wave": 1,
            "enemy_index": enemy_index + 1,
            "raw_source_path": source_path,
            "warnings": ["Enemy entry is not a JSON object."],
        }

    monster_id = enemy.get("id")
    name = enemy.get("name")
    icon_key = enemy.get("icon")
    hp_resolved = enemy.get("hp")
    hp_display = _nanoka_display_hp(hp_resolved)

    for field_name, field_value in (
        ("id", monster_id),
        ("name", name),
        ("hp", hp_resolved),
    ):
        if field_value in (None, ""):
            warnings.append(f"Missing Nanoka enemy field: {field_name}.")
    if icon_key in (None, ""):
        warnings.append("Missing Nanoka enemy icon key.")

    return {
        "floor": int(floor_number),
        "chamber": int(chamber_number),
        "side": side_number,
        "wave": 1,
        "enemy_index": enemy_index + 1,
        "enemy_display_name": name,
        "level": level,
        "hp_display": hp_display,
        "hp_display_formatted": f"{hp_display:,}" if hp_display is not None else None,
        "hp_resolved": hp_resolved,
        "monster_id": monster_id,
        "icon_key": icon_key,
        "icon_url": f"{NANOKA_ICON_BASE}/{icon_key}.webp" if icon_key else None,
        "enemy_detail_url": (
            f"{NANOKA_SITE_BASE}/monster/{monster_id}" if monster_id else None
        ),
        "raw_source_path": source_path,
        "hp_source_path": f"{source_path}.hp",
        "matching_debug": {
            "normalized_enemy_name": _normalized_name(name),
            "candidate_gcsim_key": _candidate_key(name),
            "candidate_gcsim_id": str(monster_id) if monster_id is not None else None,
            "match_method": (
                "nanoka_monster_id_and_normalized_display_name_candidate_only"
            ),
            "warnings": [
                "Candidate only; not verified against generated GCSIM data.",
                "GCSIM HP must not be trusted as factual Abyss HP.",
            ],
        },
        "warnings": warnings,
    }


def _tower_report(
    *,
    tower_id: str,
    summary: dict[str, Any],
    detail: dict[str, Any],
    manifest_url: str,
    detail_url: str,
    reference_time: datetime,
    selected_floors: set[int] | None,
) -> dict[str, Any]:
    warnings = [
        "Nanoka detail JSON exposes side enemy arrays but no explicit wave groups; "
        "wave=1 is inferred for each side."
    ]
    floors: list[dict[str, Any]] = []
    enemy_rows: list[dict[str, Any]] = []

    for floor_number, floor in _sorted_mapping_items(detail.get("floor")):
        if selected_floors and int(floor_number) not in selected_floors:
            continue
        if not isinstance(floor, dict):
            warnings.append(f'Floor {floor_number} is not a JSON object.')
            continue
        chambers: list[dict[str, Any]] = []
        for chamber_number, chamber in _sorted_mapping_items(floor.get("room")):
            if not isinstance(chamber, dict):
                warnings.append(
                    f"Floor {floor_number} chamber {chamber_number} is not a JSON object."
                )
                continue
            sides: list[dict[str, Any]] = []
            for side_number, source_side in ((1, "first"), (2, "second")):
                raw_enemies = chamber.get(source_side)
                if not isinstance(raw_enemies, list):
                    warnings.append(
                        f"Floor {floor_number} chamber {chamber_number} "
                        f"{source_side} side has no enemy list."
                    )
                    raw_enemies = []
                enemies = [
                    _enemy_report(
                        enemy,
                        floor_number=floor_number,
                        chamber_number=chamber_number,
                        side_number=side_number,
                        source_side=source_side,
                        enemy_index=enemy_index,
                        level=chamber.get("level"),
                    )
                    for enemy_index, enemy in enumerate(raw_enemies)
                ]
                enemy_rows.extend(enemies)
                sides.append(
                    {
                        "side": side_number,
                        "source_side": source_side,
                        "waves": [
                            {
                                "wave": 1,
                                "inferred": True,
                                "enemies": enemies,
                            }
                        ],
                    }
                )
            chambers.append(
                {
                    "chamber": int(chamber_number),
                    "level": chamber.get("level"),
                    "condition_type": chamber.get("type"),
                    "conditions": chamber.get("cond"),
                    "sides": sides,
                }
            )
        floors.append(
            {
                "floor": int(floor_number),
                "hp_ability": floor.get("hp_ability"),
                "buffs": floor.get("buff"),
                "first_half_buff": floor.get("first_half_buff"),
                "second_half_buff": floor.get("second_half_buff"),
                "chambers": chambers,
            }
        )

    return {
        "tower_id": str(tower_id),
        "active_live": _summary_is_live(summary, reference_time),
        "source_urls": {
            "page_url": f"{NANOKA_SITE_BASE}/tower/{tower_id}",
            "manifest_json_url": manifest_url,
            "detail_json_url": detail_url,
        },
        "period": {
            "summary_begin": summary.get("begin"),
            "summary_end": summary.get("end"),
            "live_begin": summary.get("live_begin"),
            "live_end": summary.get("live_end"),
            "detail_open": detail.get("open"),
            "detail_close": detail.get("close"),
        },
        "display_name": summary.get("en"),
        "leyline": detail.get("leyline"),
        "floors": floors,
        "enemy_rows": enemy_rows,
        "warnings": warnings,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    reference_time = _parse_reference_timestamp(args.at)
    manifest_url = _discover_manifest_url()
    static_data_base_url = _static_data_base_url(manifest_url)
    manifest = _fetch_json(manifest_url)
    summaries = _tower_summaries(manifest)
    summary, selection, warnings = _choose_tower_summary(
        summaries,
        tower_id=args.tower_id,
        history_index=args.history_index,
        reference_time=reference_time,
    )
    tower_id = str(summary.get("id"))
    detail_url = f"{static_data_base_url}/{args.locale}/tower/{tower_id}.json"
    detail = _fetch_json(detail_url)
    selected_floors = set(args.floor) if args.floor else None

    return {
        "probe": {
            "name": "nanoka_abyss_tower_probe",
            "experimental": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "warnings": [
                "Research/debug output only; do not wire this script into production UI.",
                "Nanoka timestamps are compared as source-local naive timestamps because "
                "the public JSON does not declare a timezone.",
                "GCSIM HP must not be trusted as factual Abyss HP.",
                *warnings,
            ],
        },
        "discovery": {
            "tower_index_page_url": NANOKA_TOWER_INDEX_URL,
            "manifest_json_url": manifest_url,
            "static_data_base_url": static_data_base_url,
            "data_version": _data_version(manifest_url),
            "route_kind": "sveltekit_embedded_fetched_json_url",
            "selection": selection,
        },
        "towers": [
            _tower_report(
                tower_id=tower_id,
                summary=summary,
                detail=detail,
                manifest_url=manifest_url,
                detail_url=detail_url,
                reference_time=reference_time,
                selected_floors=selected_floors,
            )
        ],
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experiment-only probe for Nanoka Spiral Abyss tower JSON. "
            "Default mode discovers and fetches the currently live tower."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--tower-id",
        help="Fetch an explicit Nanoka tower id, for example 119.",
    )
    mode.add_argument(
        "--history-index",
        type=int,
        help=(
            "Fetch a manifest history item by descending live/begin timestamp; "
            "0 selects the newest manifest item."
        ),
    )
    parser.add_argument(
        "--floor",
        action="append",
        type=int,
        help="Limit output to one floor. May be supplied more than once.",
    )
    parser.add_argument(
        "--locale",
        default="en",
        help="Nanoka localized static JSON folder. Default: en.",
    )
    parser.add_argument(
        "--at",
        help=(
            "Override the timestamp used by live discovery, for example "
            "'2026-06-02 12:30:00'."
        ),
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
    try:
        report = build_report(args)
    except ProbeError as exc:
        print(
            json.dumps(
                {
                    "probe": {
                        "name": "nanoka_abyss_tower_probe",
                        "experimental": True,
                    },
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
