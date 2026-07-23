"""Render theoretical artifact main stats for GCSIM's substat optimizer.

The ordinary account config contains one aggregate ``add stats`` row per
character.  That row mixes artifact main stats and substats, so upstream
GCSIM cannot use it as substat-optimizer input.  This module replaces those
rows at the already-assembled config boundary.  Character, weapon, set,
target, option, and rotation lines are deliberately left untouched.

Pinned GCSIM v2.42.2 identifies a main-stat row by its leading five-star
flower value (``hp=4780``).  It then derives substat limits from the exact
five artifact main stats in that row.  The renderer therefore emits one and
only one five-main-stat row for every declared character and never carries
account substats into theoretical optimizer input.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .config_structure import (
    build_gcsim_structural_view,
    find_gcsim_statement_terminator,
    has_noncanonical_gcsim_line_separator,
    is_canonical_gcsim_statement_row,
)


OPTIMIZER_CONFIG_READY = "ready"
OPTIMIZER_CONFIG_EMPTY = "config_empty"
OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT = "noncanonical_statement"
OPTIMIZER_CONFIG_INVALID_CHARACTER = "invalid_character"
OPTIMIZER_CONFIG_DUPLICATE_CHARACTER = "duplicate_character"
OPTIMIZER_CONFIG_LAYOUT_MISMATCH = "layout_mismatch"
OPTIMIZER_CONFIG_INVALID_LAYOUT = "invalid_main_stat_layout"
OPTIMIZER_CONFIG_STATS_ROW_MISSING = "stats_row_missing"
OPTIMIZER_CONFIG_ORPHAN_STATS_ROW = "orphan_stats_row"
OPTIMIZER_CONFIG_OFFPIECE_MISMATCH = "offpiece_layout_mismatch"
OPTIMIZER_CONFIG_INVALID_OFFPIECE = "invalid_offpiece_slot"


# Values intentionally mirror pkg/optimization/substats.go in pinned
# GCSIM v2.42.2.  Strings keep emitted config stable and avoid float-format
# drift at the engine contract boundary.
FIVE_STAR_MAIN_STAT_VALUES: Mapping[str, str] = {
    "hp": "4780",
    "atk": "311",
    "hp%": "0.466",
    "atk%": "0.466",
    "def%": "0.583",
    "em": "186.5",
    "er": "0.518",
    "cr": "0.311",
    "cd": "0.622",
    "pyro%": "0.466",
    "hydro%": "0.466",
    "electro%": "0.466",
    "cryo%": "0.466",
    "anemo%": "0.466",
    "geo%": "0.466",
    "dendro%": "0.466",
    "phys%": "0.583",
    "heal": "0.359",
}

# Exact max-level four-star values accepted by the pinned optimizer's 0.5%
# main-stat tolerance. A four-star-only 4p package has four such slots and one
# five-star off-piece. Upstream identifies the row when flower HP is either
# 3571 (4-star flower) or 4780 (5-star flower used as the off-piece).
FOUR_STAR_MAIN_STAT_VALUES: Mapping[str, str] = {
    "hp": "3571",
    "atk": "232",
    "hp%": "0.348",
    "atk%": "0.348",
    "def%": "0.435",
    "em": "139",
    "er": "0.387",
    "cr": "0.232",
    "cd": "0.464",
    "pyro%": "0.348",
    "hydro%": "0.348",
    "electro%": "0.348",
    "cryo%": "0.348",
    "anemo%": "0.348",
    "geo%": "0.348",
    "dendro%": "0.348",
    "phys%": "0.435",
    "heal": "0.268",
}

ARTIFACT_MAIN_STAT_SLOTS = ("flower", "plume", "sands", "goblet", "circlet")

LEGAL_FIVE_STAR_SANDS_MAIN_STATS = (
    "hp%",
    "atk%",
    "def%",
    "em",
    "er",
)
LEGAL_FIVE_STAR_GOBLET_MAIN_STATS = (
    "hp%",
    "atk%",
    "def%",
    "em",
    "pyro%",
    "hydro%",
    "electro%",
    "cryo%",
    "anemo%",
    "geo%",
    "dendro%",
    "phys%",
)
LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS = (
    "hp%",
    "atk%",
    "def%",
    "em",
    "cr",
    "cd",
    "heal",
)


_CHARACTER_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+char\b[^;]*;",
    re.IGNORECASE,
)
_STATS_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+add\s+stats\b[^;]*;",
    re.IGNORECASE,
)
_MAIN_STATS_SENSITIVE_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+\s+"
    r"(?:char\b|add\s+stats\b)",
    re.IGNORECASE,
)
_PINNED_OPTIMIZER_CHARACTER_RE = re.compile(r"^[a-z]+$")
_OPTIONS_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])options\b",
    re.IGNORECASE,
)
_WORKERS_OPTION_RE = re.compile(
    r"(?<![A-Za-z0-9_])workers\s*=\s*[^\s;]+",
    re.IGNORECASE,
)

_STATUS_PRIORITY = (
    OPTIMIZER_CONFIG_EMPTY,
    OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT,
    OPTIMIZER_CONFIG_INVALID_CHARACTER,
    OPTIMIZER_CONFIG_DUPLICATE_CHARACTER,
    OPTIMIZER_CONFIG_LAYOUT_MISMATCH,
    OPTIMIZER_CONFIG_INVALID_LAYOUT,
    OPTIMIZER_CONFIG_STATS_ROW_MISSING,
    OPTIMIZER_CONFIG_ORPHAN_STATS_ROW,
    OPTIMIZER_CONFIG_OFFPIECE_MISMATCH,
    OPTIMIZER_CONFIG_INVALID_OFFPIECE,
)


@dataclass(frozen=True, slots=True)
class GcsimFiveStarMainStatLayout:
    """Legal variable main stats for sands, goblet, and circlet.

    Flower and plume are fixed to five-star flat HP and flat ATK.  Keeping
    them out of caller input prevents an optimizer candidate from accidentally
    producing fewer or more than five artifact main stats.
    """

    sands: str
    goblet: str
    circlet: str

    def to_dict(self) -> dict[str, str]:
        return {
            "sands": self.sands,
            "goblet": self.goblet,
            "circlet": self.circlet,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerConfigIssue:
    status: str
    field: str
    message: str = ""
    character_key: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
            "character_key": self.character_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCharacterMainStats:
    character_key: str
    layout: GcsimFiveStarMainStatLayout
    line: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_key": self.character_key,
            "layout": self.layout.to_dict(),
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerConfigRenderResult:
    status: str
    ready: bool
    config_text: str = ""
    characters: tuple[GcsimOptimizerCharacterMainStats, ...] = ()
    issues: tuple[GcsimOptimizerConfigIssue, ...] = ()
    source_notes: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "config_text": self.config_text,
            "characters": [item.to_dict() for item in self.characters],
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def render_gcsim_substat_optimizer_config(
    config_text: str,
    main_stat_layouts: Mapping[
        str,
        GcsimFiveStarMainStatLayout | Mapping[str, Any],
    ],
) -> GcsimOptimizerConfigRenderResult:
    """Replace aggregate artifact stats with legal theoretical main stats.

    All existing ``<character> add stats`` rows are treated as disposable
    artifact-stat material.  The first row for each character is replaced by
    a five-main-stat row and any later row (for example substats from an older
    optimizer output) is removed.  Every other input line is preserved.
    """

    text = str(config_text or "")
    if not text.strip():
        issue = GcsimOptimizerConfigIssue(
            OPTIMIZER_CONFIG_EMPTY,
            "config_text",
            "A fully assembled GCSIM config is required.",
        )
        return _not_ready((issue,))

    if has_noncanonical_gcsim_line_separator(text):
        issue = GcsimOptimizerConfigIssue(
            OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT,
            "config_text",
            "Optimizer config rows must use canonical LF or CRLF separators.",
        )
        return _not_ready((issue,))

    structural_view = build_gcsim_structural_view(text)
    for match in _MAIN_STATS_SENSITIVE_STATEMENT_RE.finditer(structural_view):
        terminator = find_gcsim_statement_terminator(
            structural_view,
            match.end(),
        )
        if not is_canonical_gcsim_statement_row(
            structural_view,
            token_start=match.start(),
            terminator_index=terminator,
        ):
            issue = GcsimOptimizerConfigIssue(
                OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT,
                "config_text",
                "Character and add-stats statements must each occupy one "
                "canonical semicolon-terminated row.",
            )
            return _not_ready((issue,))

    lines = text.splitlines(keepends=True)
    character_order: list[str] = []
    character_counts: dict[str, int] = {}
    stats_indices: dict[str, list[int]] = {}

    for index, line in enumerate(lines):
        character_match = _CHARACTER_LINE_RE.match(line)
        if character_match:
            character_key = character_match.group("character")
            if character_key not in character_counts:
                character_order.append(character_key)
            character_counts[character_key] = character_counts.get(character_key, 0) + 1

        stats_match = _STATS_LINE_RE.match(line)
        if stats_match:
            stats_indices.setdefault(stats_match.group("character"), []).append(index)

    issues: list[GcsimOptimizerConfigIssue] = []
    if not character_order:
        issues.append(
            GcsimOptimizerConfigIssue(
                OPTIMIZER_CONFIG_INVALID_CHARACTER,
                "config_text",
                "The config contains no character declarations.",
            )
        )

    for character_key in character_order:
        if not _PINNED_OPTIMIZER_CHARACTER_RE.fullmatch(character_key):
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_INVALID_CHARACTER,
                    "config_text",
                    (
                        "Pinned GCSIM optimizer recognizes lowercase ASCII-letter "
                        "character shortcut keys only."
                    ),
                    character_key,
                )
            )
        if character_counts[character_key] != 1:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_DUPLICATE_CHARACTER,
                    "config_text",
                    "Each optimizer config character must be declared exactly once.",
                    character_key,
                )
            )

    normalized_layouts = _normalize_layouts(main_stat_layouts, issues=issues)
    expected_keys = set(character_order)
    supplied_keys = {
        str(raw_character_key or "").strip()
        for raw_character_key in main_stat_layouts
    }
    for character_key in character_order:
        if character_key not in supplied_keys:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_LAYOUT_MISMATCH,
                    f"main_stat_layouts.{character_key}",
                    "A five-star main-stat layout is required for every character.",
                    character_key,
                )
            )
    for character_key in sorted(supplied_keys - expected_keys):
        issues.append(
            GcsimOptimizerConfigIssue(
                OPTIMIZER_CONFIG_LAYOUT_MISMATCH,
                f"main_stat_layouts.{character_key}",
                "The main-stat layout does not belong to a declared character.",
                character_key,
            )
        )

    for character_key in character_order:
        if not stats_indices.get(character_key):
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_STATS_ROW_MISSING,
                    "config_text",
                    "The assembled character block has no replaceable add-stats row.",
                    character_key,
                )
            )
    for character_key in sorted(set(stats_indices) - expected_keys):
        issues.append(
            GcsimOptimizerConfigIssue(
                OPTIMIZER_CONFIG_ORPHAN_STATS_ROW,
                "config_text",
                "An add-stats row has no matching character declaration.",
                character_key,
            )
        )

    status = _status_from_issues(issues)
    if status != OPTIMIZER_CONFIG_READY:
        return _not_ready(tuple(issues))

    rendered_characters: list[GcsimOptimizerCharacterMainStats] = []
    replacement_by_index: dict[int, str] = {}
    removed_indices: set[int] = set()
    for character_key in character_order:
        layout = normalized_layouts[character_key]
        main_stat_line = render_five_star_main_stat_line(character_key, layout)
        indices = stats_indices[character_key]
        replacement_by_index[indices[0]] = _with_original_line_ending(
            main_stat_line,
            lines[indices[0]],
        )
        removed_indices.update(indices[1:])
        rendered_characters.append(
            GcsimOptimizerCharacterMainStats(
                character_key=character_key,
                layout=layout,
                line=main_stat_line,
            )
        )

    output_lines: list[str] = []
    for index, line in enumerate(lines):
        if index in removed_indices:
            continue
        output_lines.append(replacement_by_index.get(index, line))

    return GcsimOptimizerConfigRenderResult(
        status=OPTIMIZER_CONFIG_READY,
        ready=True,
        config_text="".join(output_lines),
        characters=tuple(rendered_characters),
        issues=(),
        source_notes={
            "input": "fully_assembled_gcsim_config",
            "artifact_stats": "theoretical_five_star_main_stats_only",
            "account_substats_carried_forward": False,
            "flower_main_stat": "hp=4780",
            "plume_main_stat": "atk=311",
            "optimizer_contract": "gcsim_v2.42.2",
        },
    )


def render_five_star_main_stat_line(
    character_key: str,
    layout: GcsimFiveStarMainStatLayout | Mapping[str, Any],
) -> str:
    """Render one exact five-token main-stat row.

    This lower-level helper raises ``ValueError`` for programmer errors.  Use
    :func:`render_gcsim_substat_optimizer_config` at external/backend input
    boundaries to receive typed issues instead.
    """

    key = str(character_key or "").strip()
    if not _PINNED_OPTIMIZER_CHARACTER_RE.fullmatch(key):
        raise ValueError(
            "Pinned GCSIM optimizer character keys must contain lowercase "
            "ASCII letters only."
        )
    normalized = _layout_input(layout)
    layout_error = _layout_error(normalized)
    if layout_error:
        raise ValueError(layout_error)

    stats = (
        ("hp", FIVE_STAR_MAIN_STAT_VALUES["hp"]),
        ("atk", FIVE_STAR_MAIN_STAT_VALUES["atk"]),
        (normalized.sands, FIVE_STAR_MAIN_STAT_VALUES[normalized.sands]),
        (normalized.goblet, FIVE_STAR_MAIN_STAT_VALUES[normalized.goblet]),
        (normalized.circlet, FIVE_STAR_MAIN_STAT_VALUES[normalized.circlet]),
    )
    rendered_stats = " ".join(f"{stat}={value}" for stat, value in stats)
    return f"{key} add stats {rendered_stats};"


def render_gcsim_four_star_set_optimizer_config(
    config_text: str,
    main_stat_layouts: Mapping[
        str,
        GcsimFiveStarMainStatLayout | Mapping[str, Any],
    ],
    offpiece_slots: Mapping[str, str],
) -> GcsimOptimizerConfigRenderResult:
    """Render selected four-star-only 4p packages plus five-star off-pieces.

    Stat-type legality is identical to the five-star layout contract. Rarity is
    applied per slot so upstream can identify exactly four four-star mains while
    the caller remains free to enumerate every possible off-piece position.
    Characters absent from ``offpiece_slots`` keep normal five-star layouts, so
    one team candidate may mix four-star-only and five-star artifact sets.
    """

    base = render_gcsim_substat_optimizer_config(config_text, main_stat_layouts)
    if not base.ready:
        return base
    character_keys = tuple(item.character_key for item in base.characters)
    normalized_offpiece_input: dict[str, str] = {}
    issues: list[GcsimOptimizerConfigIssue] = []
    for raw_character_key, raw_slot in offpiece_slots.items():
        character_key = str(raw_character_key or "").strip()
        if character_key in normalized_offpiece_input:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_DUPLICATE_CHARACTER,
                    f"offpiece_slots.{character_key}",
                    (
                        "More than one off-piece key normalizes to the same "
                        "character; the slot choice is ambiguous."
                    ),
                    character_key,
                )
            )
            continue
        normalized_offpiece_input[character_key] = str(raw_slot or "")
    supplied_keys = set(normalized_offpiece_input)
    expected_keys = set(character_keys)
    for character_key in sorted(supplied_keys - expected_keys):
        issues.append(
            GcsimOptimizerConfigIssue(
                OPTIMIZER_CONFIG_OFFPIECE_MISMATCH,
                f"offpiece_slots.{character_key}",
                "The off-piece slot does not belong to a declared character.",
                character_key,
            )
        )
    normalized_slots: dict[str, str] = {}
    for character_key in sorted(supplied_keys.intersection(expected_keys)):
        slot = normalized_offpiece_input[character_key].strip().casefold()
        if slot not in ARTIFACT_MAIN_STAT_SLOTS:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_INVALID_OFFPIECE,
                    f"offpiece_slots.{character_key}",
                    f"Illegal off-piece slot: {slot}.",
                    character_key,
                )
            )
        normalized_slots[character_key] = slot
    if issues:
        return _not_ready(tuple(issues))

    replacements: dict[str, str] = {}
    rendered_characters: list[GcsimOptimizerCharacterMainStats] = []
    for item in base.characters:
        if item.character_key in normalized_slots:
            line = render_four_star_set_main_stat_line(
                item.character_key,
                item.layout,
                offpiece_slot=normalized_slots[item.character_key],
            )
        else:
            line = item.line
        replacements[item.character_key] = line
        rendered_characters.append(
            GcsimOptimizerCharacterMainStats(
                character_key=item.character_key,
                layout=item.layout,
                line=line,
            )
        )

    output_lines: list[str] = []
    for line in base.config_text.splitlines(keepends=True):
        match = _STATS_LINE_RE.match(line)
        if match and match.group("character") in replacements:
            output_lines.append(
                _with_original_line_ending(replacements[match.group("character")], line)
            )
        else:
            output_lines.append(line)
    return GcsimOptimizerConfigRenderResult(
        status=OPTIMIZER_CONFIG_READY,
        ready=True,
        config_text="".join(output_lines),
        characters=tuple(rendered_characters),
        issues=(),
        source_notes={
            **dict(base.source_notes),
            "artifact_stats": "theoretical_four_star_set_plus_five_star_offpiece",
            "flower_main_stat": "hp=4780_or_3571_by_offpiece",
            "four_star_set_offpiece_slots": dict(normalized_slots),
        },
    )


def render_four_star_set_main_stat_line(
    character_key: str,
    layout: GcsimFiveStarMainStatLayout | Mapping[str, Any],
    *,
    offpiece_slot: str,
) -> str:
    """Render four four-star mains and one five-star off-piece main."""

    key = str(character_key or "").strip()
    if not _PINNED_OPTIMIZER_CHARACTER_RE.fullmatch(key):
        raise ValueError(
            "Pinned GCSIM optimizer character keys must contain lowercase "
            "ASCII letters only."
        )
    normalized = _layout_input(layout)
    layout_error = _layout_error(normalized)
    if layout_error:
        raise ValueError(layout_error)
    offpiece = str(offpiece_slot or "").strip().casefold()
    if offpiece not in ARTIFACT_MAIN_STAT_SLOTS:
        raise ValueError(f"Illegal off-piece slot: {offpiece or '<missing>'}.")
    slot_stats = (
        ("flower", "hp"),
        ("plume", "atk"),
        ("sands", normalized.sands),
        ("goblet", normalized.goblet),
        ("circlet", normalized.circlet),
    )
    rendered_stats = " ".join(
        f"{stat}={(FIVE_STAR_MAIN_STAT_VALUES if slot == offpiece else FOUR_STAR_MAIN_STAT_VALUES)[stat]}"
        for slot, stat in slot_stats
    )
    return f"{key} add stats {rendered_stats};"


def iter_legal_four_star_set_main_stat_layouts(
) -> Iterable[tuple[GcsimFiveStarMainStatLayout, str]]:
    """Yield every legal stat layout for each possible five-star off-piece."""

    for layout in iter_legal_five_star_main_stat_layouts():
        for offpiece_slot in ARTIFACT_MAIN_STAT_SLOTS:
            yield layout, offpiece_slot


def iter_legal_five_star_main_stat_layouts(
) -> Iterable[GcsimFiveStarMainStatLayout]:
    """Yield every slot-legal five-star sands/goblet/circlet layout."""

    for sands in LEGAL_FIVE_STAR_SANDS_MAIN_STATS:
        for goblet in LEGAL_FIVE_STAR_GOBLET_MAIN_STATS:
            for circlet in LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS:
                yield GcsimFiveStarMainStatLayout(
                    sands=sands,
                    goblet=goblet,
                    circlet=circlet,
                )


def apply_gcsim_optimizer_worker_budget(
    config_text: str,
    worker_count: int,
) -> str:
    """Write one explicit GCSIM worker count into an assembled config."""

    if isinstance(worker_count, bool) or not isinstance(worker_count, int):
        raise ValueError("worker_count must be an integer")
    if worker_count <= 0:
        raise ValueError("worker_count must be positive")
    text = str(config_text or "")
    if has_noncanonical_gcsim_line_separator(text):
        raise ValueError(
            "assembled optimizer options must use one canonical LF or CRLF row"
        )
    structural_view = build_gcsim_structural_view(text)
    matches = tuple(_OPTIONS_STATEMENT_RE.finditer(structural_view))
    if len(matches) != 1:
        raise ValueError(
            "assembled optimizer config must contain exactly one options statement"
        )
    match = matches[0]
    terminator = find_gcsim_statement_terminator(structural_view, match.end())
    if not is_canonical_gcsim_statement_row(
        structural_view,
        token_start=match.start(),
        terminator_index=terminator,
    ):
        raise ValueError(
            "assembled optimizer options statement must occupy one canonical row"
        )
    body = _WORKERS_OPTION_RE.sub(
        "",
        structural_view[match.end() : terminator],
    )
    body = " ".join(body.split())
    body = (f" {body}" if body else "") + f" workers={worker_count}"
    replacement = f"{text[match.start() : match.end()]}{body};"
    return text[: match.start()] + replacement + text[terminator + 1 :]


def _normalize_layouts(
    layouts: Mapping[str, GcsimFiveStarMainStatLayout | Mapping[str, Any]],
    *,
    issues: list[GcsimOptimizerConfigIssue],
) -> dict[str, GcsimFiveStarMainStatLayout]:
    result: dict[str, GcsimFiveStarMainStatLayout] = {}
    seen_character_keys: set[str] = set()
    for raw_character_key, raw_layout in layouts.items():
        character_key = str(raw_character_key or "").strip()
        if character_key in seen_character_keys:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_DUPLICATE_CHARACTER,
                    f"main_stat_layouts.{character_key}",
                    (
                        "More than one main-stat layout key normalizes to the "
                        "same character; the layout is ambiguous."
                    ),
                    character_key,
                )
            )
            continue
        seen_character_keys.add(character_key)
        try:
            layout = _layout_input(raw_layout)
        except (AttributeError, TypeError, ValueError):
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_INVALID_LAYOUT,
                    f"main_stat_layouts.{character_key}",
                    "Main-stat layout must provide sands, goblet, and circlet.",
                    character_key,
                )
            )
            continue

        error = _layout_error(layout)
        if error:
            issues.append(
                GcsimOptimizerConfigIssue(
                    OPTIMIZER_CONFIG_INVALID_LAYOUT,
                    f"main_stat_layouts.{character_key}",
                    error,
                    character_key,
                )
            )
            continue
        result[character_key] = layout
    return result


def _layout_input(
    value: GcsimFiveStarMainStatLayout | Mapping[str, Any],
) -> GcsimFiveStarMainStatLayout:
    if isinstance(value, GcsimFiveStarMainStatLayout):
        return GcsimFiveStarMainStatLayout(
            sands=_stat_key(value.sands),
            goblet=_stat_key(value.goblet),
            circlet=_stat_key(value.circlet),
        )
    if not isinstance(value, Mapping):
        raise TypeError("Main-stat layout must be a mapping or typed layout.")
    return GcsimFiveStarMainStatLayout(
        sands=_stat_key(value.get("sands")),
        goblet=_stat_key(value.get("goblet")),
        circlet=_stat_key(value.get("circlet")),
    )


def _layout_error(layout: GcsimFiveStarMainStatLayout) -> str:
    if layout.sands not in LEGAL_FIVE_STAR_SANDS_MAIN_STATS:
        return f"Illegal five-star sands main stat: {layout.sands or '<missing>'}."
    if layout.goblet not in LEGAL_FIVE_STAR_GOBLET_MAIN_STATS:
        return f"Illegal five-star goblet main stat: {layout.goblet or '<missing>'}."
    if layout.circlet not in LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS:
        return f"Illegal five-star circlet main stat: {layout.circlet or '<missing>'}."
    return ""


def _stat_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _with_original_line_ending(rendered: str, original: str) -> str:
    if original.endswith("\r\n"):
        return rendered + "\r\n"
    if original.endswith("\n"):
        return rendered + "\n"
    if original.endswith("\r"):
        return rendered + "\r"
    return rendered


def _status_from_issues(issues: Iterable[GcsimOptimizerConfigIssue]) -> str:
    issues = tuple(issues)
    for status in _STATUS_PRIORITY:
        if any(issue.status == status for issue in issues):
            return status
    return OPTIMIZER_CONFIG_READY


def _not_ready(
    issues: tuple[GcsimOptimizerConfigIssue, ...],
) -> GcsimOptimizerConfigRenderResult:
    return GcsimOptimizerConfigRenderResult(
        status=_status_from_issues(issues),
        ready=False,
        config_text="",
        issues=issues,
        source_notes={
            "input": "fully_assembled_gcsim_config",
            "account_substats_carried_forward": False,
            "optimizer_contract": "gcsim_v2.42.2",
        },
    )
