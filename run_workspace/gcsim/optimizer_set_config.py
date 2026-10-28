"""Artifact-set override adapter for theoretical GCSIM optimizer candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from .config_structure import (
    build_gcsim_structural_view,
    find_gcsim_statement_terminator,
    has_noncanonical_gcsim_line_separator,
    is_canonical_gcsim_statement_row,
)


OPTIMIZER_SET_CONFIG_READY = "ready"
OPTIMIZER_SET_CONFIG_EMPTY = "config_empty"
OPTIMIZER_SET_CONFIG_NONCANONICAL_STATEMENT = "noncanonical_statement"
OPTIMIZER_SET_CONFIG_NO_CHARACTERS = "no_characters"
OPTIMIZER_SET_CONFIG_INVALID_CHARACTER = "invalid_character"
OPTIMIZER_SET_CONFIG_INVALID_SET_KEY = "invalid_set_key"
OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH = "assignment_mismatch"
OPTIMIZER_SET_CONFIG_INSERTION_POINT_MISSING = "insertion_point_missing"


_CHARACTER_LINE_RE = re.compile(
    r"^\s*(?P<character>[a-z]+)\s+char\b[^;]*;",
    re.IGNORECASE,
)
_WEAPON_LINE_RE = re.compile(
    r"^\s*(?P<character>[a-z]+)\s+add\s+weapon\b[^;]*;",
    re.IGNORECASE,
)
_SET_LINE_RE = re.compile(
    r"^\s*(?P<character>[a-z]+)\s+add\s+set\b[^;]*;",
    re.IGNORECASE,
)
_STATS_LINE_RE = re.compile(
    r"^\s*(?P<character>[a-z]+)\s+add\s+stats\b[^;]*;",
    re.IGNORECASE,
)
_SET_CONFIG_SENSITIVE_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+\s+"
    r"(?:char\b|add\s+(?:weapon|set|stats)\b)",
    re.IGNORECASE,
)
_CHARACTER_KEY_RE = re.compile(r"^[a-z]+$")
_SET_KEY_RE = re.compile(r"^[a-z0-9]+$")


@dataclass(frozen=True, slots=True)
class GcsimFourPieceSetAssignment:
    character_key: str
    set_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "character_key": self.character_key,
            "set_key": self.set_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetConfigIssue:
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
class GcsimOptimizerSetConfigResult:
    status: str
    ready: bool
    config_text: str = ""
    assignments: tuple[GcsimFourPieceSetAssignment, ...] = ()
    issues: tuple[GcsimOptimizerSetConfigIssue, ...] = ()
    source_notes: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "config_text": self.config_text,
            "assignments": [item.to_dict() for item in self.assignments],
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def render_gcsim_four_piece_set_overrides(
    config_text: str,
    assignments: Mapping[str, str],
    *,
    require_full_team: bool = True,
) -> GcsimOptimizerSetConfigResult:
    """Replace artifact-set rows with one modeled 4p package per assignment.

    Full-team candidate rendering is the safe default. ``require_full_team=False``
    exists for the one-wearer screening stage and preserves all unassigned
    characters' existing set rows.
    """

    text = str(config_text or "")
    if not text.strip():
        return _not_ready(
            GcsimOptimizerSetConfigIssue(
                OPTIMIZER_SET_CONFIG_EMPTY,
                "config_text",
                "A fully assembled GCSIM config is required.",
            )
        )
    if has_noncanonical_gcsim_line_separator(text):
        return _not_ready(
            GcsimOptimizerSetConfigIssue(
                OPTIMIZER_SET_CONFIG_NONCANONICAL_STATEMENT,
                "config_text",
                "Character/equipment rows must use canonical LF or CRLF "
                "separators.",
            )
        )
    structural_view = build_gcsim_structural_view(text)
    for match in _SET_CONFIG_SENSITIVE_STATEMENT_RE.finditer(structural_view):
        terminator = find_gcsim_statement_terminator(
            structural_view,
            match.end(),
        )
        if not is_canonical_gcsim_statement_row(
            structural_view,
            token_start=match.start(),
            terminator_index=terminator,
        ):
            return _not_ready(
                GcsimOptimizerSetConfigIssue(
                    OPTIMIZER_SET_CONFIG_NONCANONICAL_STATEMENT,
                    "config_text",
                    "Character/equipment statements must each occupy one "
                    "canonical semicolon-terminated row.",
                )
            )
    lines = text.splitlines(keepends=True)
    character_order: list[str] = []
    weapon_indices: dict[str, int] = {}
    stats_indices: dict[str, int] = {}
    set_indices: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        match = _CHARACTER_LINE_RE.match(line)
        if match:
            key = match.group("character").casefold()
            if key not in character_order:
                character_order.append(key)
        match = _WEAPON_LINE_RE.match(line)
        if match:
            weapon_indices[match.group("character").casefold()] = index
        match = _STATS_LINE_RE.match(line)
        if match:
            stats_indices.setdefault(match.group("character").casefold(), index)
        match = _SET_LINE_RE.match(line)
        if match:
            set_indices.setdefault(match.group("character").casefold(), []).append(index)
    if not character_order:
        return _not_ready(
            GcsimOptimizerSetConfigIssue(
                OPTIMIZER_SET_CONFIG_NO_CHARACTERS,
                "config_text",
                "The config contains no character declarations.",
            )
        )

    normalized: dict[str, str] = {}
    issues: list[GcsimOptimizerSetConfigIssue] = []
    for raw_character, raw_set in assignments.items():
        character_key = str(raw_character or "").strip().casefold()
        set_key = str(raw_set or "").strip().casefold()
        if not _CHARACTER_KEY_RE.fullmatch(character_key):
            issues.append(
                GcsimOptimizerSetConfigIssue(
                    OPTIMIZER_SET_CONFIG_INVALID_CHARACTER,
                    f"assignments.{character_key or '<missing>'}",
                    "Character key must contain lowercase ASCII letters only.",
                    character_key,
                )
            )
            continue
        if not _SET_KEY_RE.fullmatch(set_key):
            issues.append(
                GcsimOptimizerSetConfigIssue(
                    OPTIMIZER_SET_CONFIG_INVALID_SET_KEY,
                    f"assignments.{character_key}",
                    "Artifact set key must contain lowercase ASCII letters or digits only.",
                    character_key,
                )
            )
            continue
        if character_key in normalized:
            issues.append(
                GcsimOptimizerSetConfigIssue(
                    OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH,
                    f"assignments.{character_key}",
                    (
                        "More than one assignment key normalizes to the same "
                        "character; the set choice is ambiguous."
                    ),
                    character_key,
                )
            )
            continue
        normalized[character_key] = set_key

    expected = set(character_order)
    supplied = set(normalized)
    for character_key in sorted(supplied - expected):
        issues.append(
            GcsimOptimizerSetConfigIssue(
                OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH,
                f"assignments.{character_key}",
                "Set assignment does not belong to a declared character.",
                character_key,
            )
        )
    if require_full_team:
        for character_key in character_order:
            if character_key not in supplied:
                issues.append(
                    GcsimOptimizerSetConfigIssue(
                        OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH,
                        f"assignments.{character_key}",
                        "A set assignment is required for every character.",
                        character_key,
                    )
                )
    for character_key in character_order:
        if character_key not in supplied:
            continue
        if character_key not in weapon_indices and character_key not in stats_indices:
            issues.append(
                GcsimOptimizerSetConfigIssue(
                    OPTIMIZER_SET_CONFIG_INSERTION_POINT_MISSING,
                    "config_text",
                    "Assigned character has no weapon or stats insertion point.",
                    character_key,
                )
            )
    if issues:
        return GcsimOptimizerSetConfigResult(
            status=issues[0].status,
            ready=False,
            issues=tuple(issues),
        )

    insertion_after: dict[int, list[str]] = {}
    removed: set[int] = set()
    rendered_assignments: list[GcsimFourPieceSetAssignment] = []
    for character_key in character_order:
        if character_key not in normalized:
            continue
        removed.update(set_indices.get(character_key, ()))
        insertion_index = weapon_indices.get(character_key)
        if insertion_index is None:
            insertion_index = stats_indices[character_key] - 1
        line = (
            f'{character_key} add set="{normalized[character_key]}" count=4;'
        )
        insertion_after.setdefault(insertion_index, []).append(line)
        rendered_assignments.append(
            GcsimFourPieceSetAssignment(character_key, normalized[character_key])
        )

    output: list[str] = []
    for index, line in enumerate(lines):
        if index not in removed:
            output.append(line)
        for inserted in insertion_after.get(index, ()):
            output.append(_with_line_ending(inserted, line))
    return GcsimOptimizerSetConfigResult(
        status=OPTIMIZER_SET_CONFIG_READY,
        ready=True,
        config_text="".join(output),
        assignments=tuple(rendered_assignments),
        source_notes={
            "set_package": "complete_4p_plus_offpiece",
            "require_full_team": bool(require_full_team),
            "preserved_unassigned_set_rows": not require_full_team,
        },
    )


def _with_line_ending(rendered: str, original: str) -> str:
    if original.endswith("\r\n"):
        return rendered + "\r\n"
    if original.endswith("\n"):
        return rendered + "\n"
    if original.endswith("\r"):
        return rendered + "\r"
    return rendered + "\n"


def _not_ready(issue: GcsimOptimizerSetConfigIssue) -> GcsimOptimizerSetConfigResult:
    return GcsimOptimizerSetConfigResult(
        status=issue.status,
        ready=False,
        issues=(issue,),
    )
