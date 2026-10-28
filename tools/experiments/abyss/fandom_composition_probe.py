"""Experiment-only probe for Fandom Spiral Abyss composition pages.

This script is intentionally separate from production Abyss fixture code. It
parses MediaWiki-rendered HTML so wave headings, separators, card containers,
enemy links, icons, and card count text stay observable for source research.
The 2026-02-16 Fisher regression is pinned here as an output validation check,
not as parser input.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


FANDOM_BASE_URL = "https://genshin-impact.fandom.com"
FANDOM_API_URL = f"{FANDOM_BASE_URL}/api.php"
USER_AGENT = "GenshinTeamsTracker-FandomCompositionProbe/1.0"
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


class ProbeError(RuntimeError):
    """Raised when the experimental source cannot be fetched or parsed."""


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
        self, tag: str, attrs: list[tuple[str, str | None]]
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


def _fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ProbeError(f"Failed to fetch {url}: {exc}") from exc


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        payload = json.loads(_fetch_bytes(url).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Failed to decode JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProbeError(f"Expected a JSON object from {url}")
    return payload


def page_title_from_fandom_url(url: str) -> str:
    path = urlparse(url).path
    marker = "/wiki/"
    if marker not in path:
        raise ProbeError(f"Fandom period URL must contain /wiki/: {url}")
    return unquote(path.split(marker, 1)[1]).strip("/")


def mediawiki_parse_api_url(page_title: str) -> str:
    encoded = quote(page_title, safe="/:")
    return f"{FANDOM_API_URL}?action=parse&page={encoded}&prop=text|sections&format=json"


def fetch_rendered_html(page_title: str) -> tuple[str, dict[str, Any]]:
    api_url = mediawiki_parse_api_url(page_title)
    payload = _fetch_json(api_url)
    try:
        rendered_html = str(payload["parse"]["text"]["*"])
    except KeyError as exc:
        raise ProbeError(f"Unexpected Fandom parse response for {page_title}") from exc
    return rendered_html, payload.get("parse", {})


def parse_fragment(value: str) -> HtmlNode:
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


def _find_all(
    node: HtmlNode,
    predicate: Any,
) -> list[HtmlNode]:
    return [child for child in _iter_nodes(node) if predicate(child)]


def _first(
    node: HtmlNode,
    predicate: Any,
) -> HtmlNode | None:
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


def _absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("data:"):
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
    return _absolute_url(image.attrs.get("data-src") or image.attrs.get("src"))


def _enemy_from_card(
    card: HtmlNode,
    *,
    floor: int,
    chamber: int,
    side: str,
    side_number: int,
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
        page_url = _absolute_url(link.attrs.get("href"))
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
    side_number: int,
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
                    warnings.append(
                        f"wave_increment_inferred_from_hr:{current_wave}"
                    )
                pending_hr_separator = False
                card_index = len(ensure_wave(current_wave))
                ensure_wave(current_wave).append(
                    _enemy_from_card(
                        child,
                        floor=floor,
                        chamber=chamber,
                        side=side,
                        side_number=side_number,
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
            {
                "wave": wave_number,
                "enemies": enemies,
                "warnings": [],
            }
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
                side_number=side_number,
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


def _find_chamber_side(
    floors: list[dict[str, Any]], floor: int, chamber: int, side: int
) -> dict[str, Any] | None:
    for floor_item in floors:
        if floor_item.get("floor") != floor:
            continue
        for chamber_item in floor_item.get("chambers", []):
            if chamber_item.get("chamber") != chamber:
                continue
            for side_item in chamber_item.get("sides", []):
                if side_item.get("side") == side:
                    return side_item
    return None


def _known_regression_checks(
    *,
    source_url: str,
    floors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if _period_date_from_url(source_url) != "2026-02-16":
        return []
    side = _find_chamber_side(floors, 12, 1, 1)
    observed: list[dict[str, Any]] = []
    if side is not None:
        for wave in side.get("waves", []):
            observed.append(
                {
                    "wave": wave.get("wave"),
                    "enemies": [
                        {
                            "display_name": enemy.get("display_name"),
                            "count": enemy.get("count"),
                        }
                        for enemy in wave.get("enemies", [])
                    ],
                }
            )
    expected_wave_ok = len(observed) == 5
    expected_enemy_ok = all(
        len(wave["enemies"]) == 1
        and wave["enemies"][0]["display_name"] == "Fisher of Hidden Depths"
        and wave["enemies"][0]["count"] == 3
        for wave in observed
    )
    return [
        {
            "id": "2026-02-16_floor12_chamber1_first_half_fisher_waves",
            "passed": bool(expected_wave_ok and expected_enemy_ok),
            "expected": (
                "Floor 12 Chamber 1 First Half has 5 sequential waves; "
                "each wave contains Fisher of Hidden Depths x3."
            ),
            "observed": observed,
        }
    ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    page_title = page_title_from_fandom_url(args.period_url)
    rendered_html, parse_payload = fetch_rendered_html(page_title)
    root = parse_fragment(rendered_html)
    floors_to_parse = args.floor or [
        int(match.group(1))
        for match in re.finditer(r"Floor_(\d+)", rendered_html)
    ]
    floors_to_parse = sorted(set(floors_to_parse))
    floors = [_parse_floor(root, floor=floor) for floor in floors_to_parse]
    regression_checks = _known_regression_checks(
        source_url=args.period_url,
        floors=floors,
    )
    sections = parse_payload.get("sections", [])
    return {
        "probe": {
            "name": "fandom_spiral_abyss_composition_probe",
            "experimental": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "warnings": [
                "Research/debug output only; do not wire this script into production UI.",
                "This probe parses Fandom MediaWiki rendered HTML and should report "
                "shape changes instead of silently guessing composition.",
                "HP is intentionally not joined here; Nanoka remains the primary "
                "resolved HP source.",
            ],
            "regression_checks": regression_checks,
        },
        "source": {
            "url": args.period_url,
            "page_title": page_title,
            "mediawiki_parse_api_url": mediawiki_parse_api_url(page_title),
            "period_date_from_url": _period_date_from_url(args.period_url),
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
        "floors": floors,
        "enemy_rows": _all_enemy_rows(floors),
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experiment-only Fandom Spiral Abyss composition probe. "
            "Parses rendered MediaWiki HTML into floor/chamber/side/wave/card JSON."
        )
    )
    parser.add_argument(
        "--period-url",
        required=True,
        help=(
            "Fandom period URL, for example "
            "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-02-16"
        ),
    )
    parser.add_argument(
        "--floor",
        action="append",
        type=int,
        help="Limit output to one floor. May be supplied more than once.",
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
                        "name": "fandom_spiral_abyss_composition_probe",
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
    failed_checks = [
        check
        for check in report["probe"].get("regression_checks", [])
        if not check.get("passed")
    ]
    return 2 if failed_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
