"""Production-safe Fandom/Nanoka fetchers for Abyss source data.

These helpers fetch only period composition plus Nanoka manifest/detail JSON.
They do not fetch individual Fandom enemy pages and do not depend on experiment
scripts. Cache writes live in `source_data_cache.py` / `source_data_update.py`
and Account/Data integration calls the update boundary instead of these helpers
directly.
"""

from __future__ import annotations

import html
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from time import perf_counter
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


FANDOM_BASE_URL = "https://genshin-impact.fandom.com"
FANDOM_API_URL = f"{FANDOM_BASE_URL}/api.php"
NANOKA_SITE_BASE = "https://gi.nanoka.cc"
NANOKA_TOWER_INDEX_URL = f"{NANOKA_SITE_BASE}/tower"
NANOKA_ICON_BASE = "https://static.nanoka.cc/assets/gi"
SOURCE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
USER_AGENT = "GenshinTeamsTracker-AbyssSourceData/1.0"
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class AbyssSourceFetchError(RuntimeError):
    """Raised when a live Abyss source cannot be fetched or parsed."""


class NanokaTowerPeriodNotFound(AbyssSourceFetchError):
    """Raised when Nanoka manifest has no tower matching a period."""


class NanokaTowerPeriodAmbiguous(AbyssSourceFetchError):
    """Raised when Nanoka manifest has multiple towers matching a period."""


@dataclass(frozen=True, slots=True)
class ResolvedAbyssPeriodSource:
    """Resolved current Abyss period from a non-HoYoLAB production source."""

    raw_period: str
    start_date: str
    end_date: str | None
    source: str
    source_path: str
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode | str"] = field(default_factory=list)


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = HtmlNode("document")
        self._stack: list[HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag.lower(), {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if node.tag == "br":
            self._stack[-1].children.append("\n")
        if node.tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = HtmlNode(tag.lower(), {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if node.tag == "br":
            self._stack[-1].children.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self._stack[-1].children.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._stack[-1].children.append(f"&#{name};")


class _FetchedDataUrlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.data_urls: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "script":
            return
        attr_map = dict(attrs)
        data_url = attr_map.get("data-url")
        if "data-sveltekit-fetched" in attr_map and data_url:
            self.data_urls.append(data_url)


def _fetch_bytes(url: str, *, timeout: int = 30) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AbyssSourceFetchError(f"Failed to fetch {url}: {exc}") from exc


def _fetch_text(url: str, *, timeout: int = 30) -> str:
    return _fetch_bytes(url, timeout=timeout).decode("utf-8")


def _fetch_json(url: str, *, timeout: int = 30) -> dict[str, Any]:
    try:
        payload = json.loads(_fetch_text(url, timeout=timeout))
    except json.JSONDecodeError as exc:
        raise AbyssSourceFetchError(f"Failed to decode JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AbyssSourceFetchError(f"Expected a JSON object from {url}")
    return payload


def page_title_from_fandom_url(url: str) -> str:
    path = urlparse(url).path
    marker = "/wiki/"
    if marker not in path:
        raise AbyssSourceFetchError(f"Fandom period URL must contain /wiki/: {url}")
    return unquote(path.split(marker, 1)[1]).strip("/")


def mediawiki_parse_api_url(page_title: str) -> str:
    encoded = quote(page_title, safe="/:")
    return f"{FANDOM_API_URL}?action=parse&page={encoded}&prop=text|sections&format=json"


def _fetch_rendered_html(page_title: str) -> tuple[str, dict[str, Any]]:
    api_url = mediawiki_parse_api_url(page_title)
    payload = _fetch_json(api_url)
    try:
        rendered_html = str(payload["parse"]["text"]["*"])
    except KeyError as exc:
        raise AbyssSourceFetchError(
            f"Unexpected Fandom parse response for {page_title}"
        ) from exc
    return rendered_html, payload.get("parse", {})


def _parse_fragment(value: str) -> HtmlNode:
    parser = FragmentParser()
    parser.feed(value)
    return parser.root


def _classes(node: HtmlNode) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _has_class(node: HtmlNode, class_name: str) -> bool:
    return class_name in _classes(node)


def _iter_nodes(node: HtmlNode) -> Iterable[HtmlNode]:
    for child in node.children:
        if isinstance(child, HtmlNode):
            yield child
            yield from _iter_nodes(child)


def _find_all(node: HtmlNode, predicate: Any) -> list[HtmlNode]:
    return [child for child in _iter_nodes(node) if predicate(child)]


def _first(node: HtmlNode, predicate: Any) -> HtmlNode | None:
    for child in _iter_nodes(node):
        if predicate(child):
            return child
    return None


def _direct_elements(node: HtmlNode, tag: str | None = None) -> list[HtmlNode]:
    return [
        child
        for child in node.children
        if isinstance(child, HtmlNode) and (tag is None or child.tag == tag)
    ]


def _content_children(root: HtmlNode) -> list[HtmlNode]:
    direct = _direct_elements(root)
    if len(direct) == 1 and direct[0].tag == "div":
        return _direct_elements(direct[0])
    return direct


def _text_content(node: HtmlNode | str) -> str:
    if isinstance(node, str):
        return html.unescape(node)
    return "".join(_text_content(child) for child in node.children)


def _compact_text(node: HtmlNode | str) -> str:
    return re.sub(r"\s+", " ", _text_content(node)).strip()


def _heading_level(node: HtmlNode) -> int | None:
    if re.fullmatch(r"h[1-6]", node.tag):
        return int(node.tag[1])
    return None


def _headline_id(node: HtmlNode) -> str | None:
    headline = _first(
        node,
        lambda child: child.tag == "span" and _has_class(child, "mw-headline"),
    )
    return headline.attrs.get("id") if headline else None


def _floor_section(root: HtmlNode, floor: int) -> tuple[list[HtmlNode], list[str]]:
    warnings: list[str] = []
    target_id = f"Floor_{floor}"
    top_level = _content_children(root)
    start_index = None
    start_level = None
    for index, node in enumerate(top_level):
        level = _heading_level(node)
        if level is not None and _headline_id(node) == target_id:
            start_index = index
            start_level = level
            break
    if start_index is None or start_level is None:
        return [], [f"floor_section_not_found:{floor}"]

    section: list[HtmlNode] = []
    for node in top_level[start_index + 1 :]:
        level = _heading_level(node)
        if level is not None and level <= start_level:
            break
        section.append(node)
    if not section:
        warnings.append(f"floor_section_empty:{floor}")
    return section, warnings


def _first_table(nodes: list[HtmlNode]) -> HtmlNode | None:
    for node in nodes:
        if node.tag == "table" and _has_class(node, "wikitable"):
            return node
        nested = _first(
            node,
            lambda child: child.tag == "table" and _has_class(child, "wikitable"),
        )
        if nested:
            return nested
    return None


def _rows(table: HtmlNode) -> list[HtmlNode]:
    return _find_all(table, lambda child: child.tag == "tr")


def _cell_label(row: HtmlNode) -> str:
    th = next(iter(_direct_elements(row, "th")), None)
    return _compact_text(th).casefold() if th else ""


def _first_data_cell(row: HtmlNode) -> HtmlNode | None:
    return next(iter(_direct_elements(row, "td")), None)


def _parse_int_text(value: str) -> int | None:
    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group(0)) if match else None


def _side_from_label(label: str) -> tuple[int, str] | None:
    if "first half" in label:
        return 1, "first"
    if "second half" in label:
        return 2, "second"
    return None


def _absolute_fandom_url(url: str | None) -> str | None:
    if not url or url.startswith("data:"):
        return None
    return urljoin(FANDOM_BASE_URL, url)


def _card_count(card: HtmlNode) -> tuple[int | None, list[str]]:
    text_node = _first(
        card,
        lambda child: child.tag == "span" and _has_class(child, "card-text"),
    )
    if text_node is None:
        return None, ["card_count_missing"]
    raw = _compact_text(text_node)
    count = _parse_int_text(raw)
    if count is None:
        return None, [f"card_count_not_numeric:{raw or '<empty>'}"]
    return count, []


def _card_caption_link(card: HtmlNode) -> HtmlNode | None:
    caption = _first(
        card,
        lambda child: child.tag == "span" and _has_class(child, "card-caption"),
    )
    if caption is None:
        return None
    return _first(caption, lambda child: child.tag == "a")


def _card_icon_url(card: HtmlNode) -> str | None:
    image_container = _first(
        card,
        lambda child: child.tag == "span"
        and _has_class(child, "card-image-container"),
    )
    if image_container is None:
        return None
    image = _first(image_container, lambda child: child.tag == "img")
    if image is None:
        return None
    return _absolute_fandom_url(image.attrs.get("data-src") or image.attrs.get("src"))


def _enemy_from_card(
    card: HtmlNode,
    *,
    floor: int,
    chamber: int,
    side: str,
    level: int | None,
    wave: int,
    card_index: int,
) -> dict[str, Any]:
    warnings: list[str] = []
    link = _card_caption_link(card)
    display_name = None
    page_url = None
    if link is not None:
        display_name = _compact_text(link) or link.attrs.get("title")
        page_url = _absolute_fandom_url(link.attrs.get("href"))
    else:
        warnings.append("card_caption_link_missing")
    if not display_name:
        display_name = card.attrs.get("title")
        warnings.append("enemy_name_missing_or_inferred")

    count, count_warnings = _card_count(card)
    warnings.extend(count_warnings)
    icon_url = _card_icon_url(card)
    if icon_url is None:
        warnings.append("enemy_icon_url_missing")

    raw_source_path = (
        f"floor[{floor}].chamber[{chamber}].side[{side}]"
        f".wave[{wave}].card[{card_index}]"
    )
    return {
        "display_name": display_name,
        "count": count,
        "enemy_page_url": page_url,
        "icon_url": icon_url,
        "level": level,
        "raw_source_path": raw_source_path,
        "extraction_note": (
            "Parsed from MediaWiki rendered HTML card-container: "
            "card-caption link, card-text count, and card-image-container img."
        ),
        "warnings": warnings,
    }


def _parse_enemy_cell(
    cell: HtmlNode,
    *,
    floor: int,
    chamber: int,
    side: str,
    level: int | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    waves: dict[int, list[dict[str, Any]]] = {}
    current_wave: int | None = None
    pending_hr_separator = False

    def ensure_wave(number: int) -> list[dict[str, Any]]:
        return waves.setdefault(number, [])

    def walk(node: HtmlNode) -> None:
        nonlocal current_wave, pending_hr_separator
        for child in node.children:
            if not isinstance(child, HtmlNode):
                continue
            if child.tag == "b":
                match = re.fullmatch(r"Wave\s+(\d+):?", _compact_text(child), re.I)
                if match:
                    current_wave = int(match.group(1))
                    ensure_wave(current_wave)
                    pending_hr_separator = False
                    continue
            if child.tag == "hr":
                if current_wave is None:
                    current_wave = 1
                    ensure_wave(current_wave)
                pending_hr_separator = True
                continue
            if child.tag == "div" and _has_class(child, "card-container"):
                if current_wave is None:
                    current_wave = 1
                    ensure_wave(current_wave)
                    warnings.append("wave_label_missing_defaulted_to_1")
                elif pending_hr_separator:
                    current_wave += 1
                    ensure_wave(current_wave)
                    warnings.append(f"wave_increment_inferred_from_hr:{current_wave}")
                pending_hr_separator = False
                card_index = len(ensure_wave(current_wave))
                ensure_wave(current_wave).append(
                    _enemy_from_card(
                        child,
                        floor=floor,
                        chamber=chamber,
                        side=side,
                        level=level,
                        wave=current_wave,
                        card_index=card_index,
                    )
                )
                continue
            walk(child)

    walk(cell)
    if not waves:
        warnings.append("enemy_cards_missing")
    return (
        [
            {"wave": wave_number, "enemies": enemies, "warnings": []}
            for wave_number, enemies in sorted(waves.items())
        ],
        warnings,
    )


def _parse_floor(root: HtmlNode, floor: int) -> dict[str, Any]:
    section, warnings = _floor_section(root, floor)
    table = _first_table(section)
    if table is None:
        return {
            "floor": floor,
            "chambers": [],
            "warnings": [*warnings, "floor_wikitable_not_found"],
        }

    chambers: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in _rows(table):
        th_cells = _direct_elements(row, "th")
        if th_cells:
            heading_text = _compact_text(th_cells[0])
            match = re.search(r"\bChamber\s+(\d+)\b", heading_text, re.I)
            if match:
                current = {
                    "chamber": int(match.group(1)),
                    "level": None,
                    "challenge_target": None,
                    "sides": [],
                    "warnings": [],
                }
                chambers.append(current)
                continue

        if current is None:
            continue

        label = _cell_label(row)
        data_cell = _first_data_cell(row)
        if data_cell is None:
            continue
        if "enemy" in label and "level" in label:
            current["level"] = _parse_int_text(_compact_text(data_cell))
            if current["level"] is None:
                current["warnings"].append("enemy_level_missing_or_non_numeric")
            continue
        if "challenge" in label and "target" in label:
            current["challenge_target"] = _compact_text(data_cell)
            continue
        side = _side_from_label(label)
        if side is not None and "enemies" in label:
            side_number, side_name = side
            waves, side_warnings = _parse_enemy_cell(
                data_cell,
                floor=floor,
                chamber=int(current["chamber"]),
                side=side_name,
                level=current.get("level"),
            )
            current["sides"].append(
                {
                    "side": side_number,
                    "side_name": side_name,
                    "display_level": current.get("level"),
                    "waves": waves,
                    "warnings": side_warnings,
                }
            )

    if not chambers:
        warnings.append("floor_chambers_not_found")
    return {
        "floor": floor,
        "source_path": f"h3#Floor_{floor} > table.wikitable",
        "chambers": chambers,
        "warnings": warnings,
    }


def _period_date_from_url(source_url: str) -> str | None:
    match = re.search(r"/(\d{4}-\d{2}-\d{2})(?:$|[/?#])", source_url)
    return match.group(1) if match else None


def _duration_text(root: HtmlNode) -> str | None:
    text = _compact_text(root)
    match = re.search(
        r"(?:lasted from|Duration:)\s+(.{0,140}?)(?=(?:\s+[A-Z][a-z]+ Moon|\s+Contents|\Z))",
        text,
        flags=re.I,
    )
    return match.group(1).strip(" .") if match else None


def _all_enemy_rows(floors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for floor in floors:
        floor_number = floor["floor"]
        for chamber in floor["chambers"]:
            chamber_number = chamber["chamber"]
            for side in chamber["sides"]:
                for wave in side["waves"]:
                    for enemy in wave["enemies"]:
                        rows.append(
                            {
                                "floor": floor_number,
                                "chamber": chamber_number,
                                "side": side["side"],
                                "side_name": side["side_name"],
                                "wave": wave["wave"],
                                **enemy,
                            }
                        )
    return rows


def fetch_fandom_composition_report(period_url: str, *, floor: int = 12) -> dict[str, Any]:
    total_start = perf_counter()
    page_title = page_title_from_fandom_url(period_url)
    fetch_start = perf_counter()
    rendered_html, parse_payload = _fetch_rendered_html(page_title)
    fetch_ms = _elapsed_ms(fetch_start)
    parse_start = perf_counter()
    root = _parse_fragment(rendered_html)
    floors = [_parse_floor(root, floor=floor)]
    parse_ms = _elapsed_ms(parse_start)
    sections = parse_payload.get("sections", [])
    return {
        "source": {
            "url": period_url,
            "page_title": page_title,
            "mediawiki_parse_api_url": mediawiki_parse_api_url(page_title),
            "period_date_from_url": _period_date_from_url(period_url),
            "duration_text": _duration_text(root),
            "sections": [
                {
                    "index": item.get("index"),
                    "level": item.get("level"),
                    "line": item.get("line"),
                    "anchor": item.get("anchor"),
                }
                for item in sections
                if isinstance(item, dict)
            ],
        },
        "timings_ms": {
            "fandom_rendered_html_fetch": fetch_ms,
            "fandom_composition_parse": parse_ms,
            "fandom_composition_total": _elapsed_ms(total_start),
        },
        "floors": floors,
        "enemy_rows": _all_enemy_rows(floors),
    }


def resolve_fandom_latest_period() -> ResolvedAbyssPeriodSource:
    """Resolve the latest Fandom Spiral Abyss Floors page as a fallback period."""

    index_title = "Spiral_Abyss/Floors"
    rendered_html, _parse_payload = _fetch_rendered_html(index_title)
    matches = sorted(
        set(re.findall(r"/wiki/Spiral_Abyss/Floors/(\d{4}-\d{2}-\d{2})", rendered_html))
    )
    if not matches:
        raise AbyssSourceFetchError("Fandom Spiral Abyss/Floors page has no period links.")
    start_date = matches[-1]
    period_url = f"{FANDOM_BASE_URL}/wiki/Spiral_Abyss/Floors/{start_date}"
    period_html, _period_payload = _fetch_rendered_html(page_title_from_fandom_url(period_url))
    period_root = _parse_fragment(period_html)
    duration_text = _duration_text(period_root) or ""
    parsed_dates = _dates_from_fandom_duration(duration_text)
    end_date = parsed_dates[1] if len(parsed_dates) >= 2 else None
    warnings: list[str] = []
    if not end_date:
        warnings.append("fandom_latest_period_end_unavailable")
    return ResolvedAbyssPeriodSource(
        raw_period=f"{start_date}/{end_date}" if end_date else start_date,
        start_date=start_date,
        end_date=end_date,
        source="fandom_latest_fallback",
        source_path=f"{mediawiki_parse_api_url(index_title)}#latest_period_link",
        warnings=tuple(warnings),
        metadata={
            "period_url": period_url,
            "duration_text": duration_text,
        },
    )


def _discover_nanoka_manifest_url() -> str:
    parser = _FetchedDataUrlParser()
    parser.feed(_fetch_text(NANOKA_TOWER_INDEX_URL, timeout=20))
    candidates = [
        url for url in parser.data_urls if url.rstrip("/").endswith("/tower.json")
    ]
    if not candidates:
        raise AbyssSourceFetchError(
            "Nanoka tower page did not expose an embedded fetched tower.json URL"
        )
    return urljoin(NANOKA_SITE_BASE, candidates[0])


def _static_data_base_url(manifest_url: str) -> str:
    suffix = "/tower.json"
    normalized = manifest_url.rstrip("/")
    if not normalized.endswith(suffix):
        raise AbyssSourceFetchError(f"Unexpected Nanoka tower manifest URL: {manifest_url}")
    return normalized[: -len(suffix)]


def _parse_source_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, SOURCE_TIMESTAMP_FORMAT)
    except ValueError:
        return None


def _source_date(value: Any) -> str | None:
    timestamp = _parse_source_timestamp(value)
    if timestamp is not None:
        return timestamp.date().isoformat()
    if isinstance(value, str):
        match = re.search(r"\d{4}-\d{2}-\d{2}", value)
        if match:
            return match.group(0)
    return None


def _summary_period_start_candidates(summary: dict[str, Any]) -> set[str]:
    return {
        value
        for value in (
            _source_date(summary.get("live_begin")),
            _source_date(summary.get("begin")),
        )
        if value is not None
    }


def _summary_period_end_candidates(summary: dict[str, Any]) -> set[str]:
    return {
        value
        for value in (
            _source_date(summary.get("live_end")),
            _source_date(summary.get("end")),
        )
        if value is not None
    }


def _summary_is_live(summary: dict[str, Any], reference_time: datetime) -> bool:
    begin = _parse_source_timestamp(summary.get("live_begin"))
    end = _parse_source_timestamp(summary.get("live_end"))
    return bool(begin and end and begin <= reference_time <= end)


def _tower_summaries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = manifest.get("tower")
    if isinstance(raw_items, list):
        return [item for item in raw_items if isinstance(item, dict)]
    summaries: list[dict[str, Any]] = []
    for tower_id, summary in manifest.items():
        if isinstance(summary, dict):
            summaries.append({"id": str(tower_id), **summary})
    if not summaries:
        raise AbyssSourceFetchError("Nanoka tower manifest does not contain tower summaries")
    return summaries


def _choose_tower_summary(
    summaries: list[dict[str, Any]],
    *,
    tower_id: str,
) -> tuple[dict[str, Any], list[str]]:
    by_id = {str(item.get("id")): item for item in summaries}
    summary = by_id.get(str(tower_id))
    if summary is not None:
        return summary, []
    return (
        {"id": str(tower_id)},
        [
            f"Tower id {tower_id} is absent from the discovered manifest; "
            "the detail JSON route will still be attempted."
        ],
    )


def resolve_nanoka_tower_summary_for_period(
    summaries: list[dict[str, Any]],
    *,
    period_start: str,
    period_end: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve one Nanoka tower summary by Abyss period dates."""

    normalized_start = str(period_start)
    normalized_end = str(period_end) if period_end else None
    matches = [
        summary
        for summary in summaries
        if normalized_start in _summary_period_start_candidates(summary)
        and (
            normalized_end is None
            or normalized_end in _summary_period_end_candidates(summary)
        )
    ]
    if not matches:
        end_hint = f" and end {normalized_end}" if normalized_end else ""
        raise NanokaTowerPeriodNotFound(
            f"Nanoka tower manifest has no tower for period start {normalized_start}{end_hint}."
        )
    if len(matches) > 1:
        tower_ids = ", ".join(str(summary.get("id")) for summary in matches)
        raise NanokaTowerPeriodAmbiguous(
            f"Nanoka tower manifest has multiple towers for period start {normalized_start}: {tower_ids}"
        )
    summary = matches[0]
    tower_id = summary.get("id")
    if tower_id in (None, ""):
        raise NanokaTowerPeriodNotFound(
            f"Nanoka tower manifest match for period start {normalized_start} has no id."
        )
    return summary, []


def resolve_nanoka_tower_id_for_period(
    manifest: dict[str, Any],
    *,
    period_start: str,
    period_end: str | None = None,
) -> str:
    """Resolve Nanoka's internal tower id from a manifest payload."""

    summary, _warnings = resolve_nanoka_tower_summary_for_period(
        _tower_summaries(manifest),
        period_start=period_start,
        period_end=period_end,
    )
    return str(summary["id"])


def resolve_nanoka_live_period(
    *,
    reference_time: datetime | None = None,
) -> ResolvedAbyssPeriodSource:
    """Resolve the currently live Nanoka tower period without fetching details."""

    manifest_url = _discover_nanoka_manifest_url()
    manifest = _fetch_json(manifest_url, timeout=20)
    summaries = _tower_summaries(manifest)
    now = reference_time or datetime.now()
    matches = [summary for summary in summaries if _summary_is_live(summary, now)]
    if not matches:
        raise NanokaTowerPeriodNotFound("Nanoka tower manifest has no live tower entry.")
    if len(matches) > 1:
        tower_ids = ", ".join(str(summary.get("id")) for summary in matches)
        raise NanokaTowerPeriodAmbiguous(
            f"Nanoka tower manifest has multiple live tower entries: {tower_ids}"
        )
    summary = matches[0]
    tower_id = summary.get("id")
    if tower_id in (None, ""):
        raise NanokaTowerPeriodNotFound("Nanoka live tower entry has no id.")
    start_date = _preferred_summary_period_start(summary)
    if not start_date:
        raise NanokaTowerPeriodNotFound("Nanoka live tower entry has no period start.")
    end_date = _preferred_summary_period_end(summary)
    warnings: list[str] = []
    if not end_date:
        warnings.append("nanoka_live_period_end_unavailable")
    return ResolvedAbyssPeriodSource(
        raw_period=f"{start_date}/{end_date}" if end_date else start_date,
        start_date=start_date,
        end_date=end_date,
        source="nanoka_live_fallback",
        source_path=f"{manifest_url}#tower[{tower_id}]",
        warnings=tuple(warnings),
        metadata={
            "tower_id": str(tower_id),
            "manifest_json_url": manifest_url,
            "tower_page_url": f"{NANOKA_SITE_BASE}/tower/{tower_id}/",
        },
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
    for field_name, field_value in (("id", monster_id), ("name", name), ("hp", hp_resolved)):
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
        "enemy_detail_url": f"{NANOKA_SITE_BASE}/monster/{monster_id}" if monster_id else None,
        "raw_source_path": source_path,
        "hp_source_path": f"{source_path}.hp",
        "matching_debug": {
            "normalized_enemy_name": _normalized_name(name),
            "candidate_gcsim_key": _candidate_key(name),
            "candidate_gcsim_id": str(monster_id) if monster_id is not None else None,
            "match_method": "nanoka_monster_id_and_normalized_display_name_candidate_only",
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
    selected_floor: int,
) -> dict[str, Any]:
    warnings = [
        "Nanoka detail JSON exposes side enemy arrays but no explicit wave groups; "
        "wave=1 is inferred for each side."
    ]
    floors: list[dict[str, Any]] = []
    enemy_rows: list[dict[str, Any]] = []
    for floor_number, floor in _sorted_mapping_items(detail.get("floor")):
        if int(floor_number) != int(selected_floor):
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
                        "waves": [{"wave": 1, "inferred": True, "enemies": enemies}],
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
        "active_live": _summary_is_live(summary, datetime.now()),
        "source_urls": {
            "page_url": f"{NANOKA_SITE_BASE}/tower/{tower_id}/",
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


def fetch_nanoka_tower_report(
    tower_id: str,
    *,
    floor: int = 12,
    locale: str = "en",
) -> dict[str, Any]:
    total_start = perf_counter()
    discovery_start = perf_counter()
    manifest_url = _discover_nanoka_manifest_url()
    discovery_ms = _elapsed_ms(discovery_start)
    static_data_base_url = _static_data_base_url(manifest_url)
    manifest_start = perf_counter()
    manifest = _fetch_json(manifest_url, timeout=20)
    summaries = _tower_summaries(manifest)
    manifest_ms = _elapsed_ms(manifest_start)
    lookup_start = perf_counter()
    summary, warnings = _choose_tower_summary(summaries, tower_id=str(tower_id))
    lookup_ms = _elapsed_ms(lookup_start)
    detail_url = f"{static_data_base_url}/{locale}/tower/{tower_id}.json"
    detail_start = perf_counter()
    detail = _fetch_json(detail_url, timeout=30)
    detail_ms = _elapsed_ms(detail_start)
    return {
        "probe": {
            "name": "nanoka_abyss_tower_source_fetch",
            "production_safe_debug": True,
            "warnings": [
                "Nanoka is the primary resolved HP source.",
                "Nanoka wave values are not used as composition authority.",
                *warnings,
            ],
        },
        "discovery": {
            "tower_index_page_url": NANOKA_TOWER_INDEX_URL,
            "manifest_json_url": manifest_url,
            "static_data_base_url": static_data_base_url,
            "selection": {
                "mode": "explicit_tower_id_override",
                "tower_id": str(tower_id),
            },
        },
        "timings_ms": {
            "nanoka_manifest_discovery": discovery_ms,
            "nanoka_manifest_fetch_parse": manifest_ms,
            "nanoka_explicit_tower_lookup": lookup_ms,
            "nanoka_detail_fetch_parse": detail_ms,
            "nanoka_total": _elapsed_ms(total_start),
        },
        "towers": [
            _tower_report(
                tower_id=str(tower_id),
                summary=summary,
                detail=detail,
                manifest_url=manifest_url,
                detail_url=detail_url,
                selected_floor=floor,
            )
        ],
    }


def fetch_nanoka_tower_report_for_period(
    period_start: str,
    *,
    period_end: str | None = None,
    floor: int = 12,
    locale: str = "en",
) -> dict[str, Any]:
    total_start = perf_counter()
    discovery_start = perf_counter()
    manifest_url = _discover_nanoka_manifest_url()
    discovery_ms = _elapsed_ms(discovery_start)
    static_data_base_url = _static_data_base_url(manifest_url)
    manifest_start = perf_counter()
    manifest = _fetch_json(manifest_url, timeout=20)
    summaries = _tower_summaries(manifest)
    manifest_ms = _elapsed_ms(manifest_start)
    lookup_start = perf_counter()
    summary, warnings = resolve_nanoka_tower_summary_for_period(
        summaries,
        period_start=period_start,
        period_end=period_end,
    )
    lookup_ms = _elapsed_ms(lookup_start)
    tower_id = str(summary["id"])
    detail_url = f"{static_data_base_url}/{locale}/tower/{tower_id}.json"
    detail_start = perf_counter()
    detail = _fetch_json(detail_url, timeout=30)
    detail_ms = _elapsed_ms(detail_start)
    return {
        "probe": {
            "name": "nanoka_abyss_tower_source_fetch",
            "production_safe_debug": True,
            "warnings": [
                "Nanoka is the primary resolved HP source.",
                "Nanoka wave values are not used as composition authority.",
                *warnings,
            ],
        },
        "discovery": {
            "tower_index_page_url": NANOKA_TOWER_INDEX_URL,
            "manifest_json_url": manifest_url,
            "static_data_base_url": static_data_base_url,
            "selection": {
                "mode": "period_start_lookup",
                "period_start": str(period_start),
                "period_end": str(period_end) if period_end else None,
                "tower_id": tower_id,
            },
        },
        "timings_ms": {
            "nanoka_manifest_discovery": discovery_ms,
            "nanoka_manifest_fetch_parse": manifest_ms,
            "nanoka_period_lookup": lookup_ms,
            "nanoka_detail_fetch_parse": detail_ms,
            "nanoka_total": _elapsed_ms(total_start),
        },
        "towers": [
            _tower_report(
                tower_id=tower_id,
                summary=summary,
                detail=detail,
                manifest_url=manifest_url,
                detail_url=detail_url,
                selected_floor=floor,
            )
        ],
    }


_FANDOM_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _preferred_summary_period_start(summary: dict[str, Any]) -> str | None:
    return _source_date(summary.get("live_begin")) or _source_date(summary.get("begin"))


def _preferred_summary_period_end(summary: dict[str, Any]) -> str | None:
    return _source_date(summary.get("live_end")) or _source_date(summary.get("end"))


def _dates_from_fandom_duration(value: str) -> list[str]:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", value or "")
    if dates:
        return dates
    parsed: list[str] = []
    for match in re.finditer(
        r"\b("
        r"January|February|March|April|May|June|July|August|September|October|November|December"
        r")\s+(\d{1,2}),\s*(\d{4})\b",
        value or "",
        flags=re.I,
    ):
        month = _FANDOM_MONTHS.get(match.group(1).lower())
        if not month:
            continue
        parsed.append(f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}")
    return parsed


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)
