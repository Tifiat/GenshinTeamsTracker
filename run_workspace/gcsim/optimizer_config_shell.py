"""Strict prepared-config shell boundary for the account artifact optimizer.

Milestone 1A removes only app-owned artifact ``add set``/``add stats`` rows
from an already prepared four-character GCSIM config.  It preserves every
other byte, inserts one inert marker per wearer for the later materializer, and
projects active source set rows only as editable UI suggestions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import re
from types import MappingProxyType

from .config_structure import (
    build_gcsim_structural_view,
    find_gcsim_statement_terminator,
    has_noncanonical_gcsim_line_separator,
    is_canonical_gcsim_statement_row,
    validate_gcsim_farming_static_config,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerWearerIdentity,
)


GCSIM_OPTIMIZER_CONFIG_SHELL_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER = "gtt_optimizer_artifact_block"

OPTIMIZER_CONFIG_SHELL_READY = "ready"
OPTIMIZER_CONFIG_SHELL_NOT_READY = "not_ready"

_CHARACTER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SET_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_CHARACTER_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+char\b[^;]*;"
)
_WEAPON_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+add\s+weapon\b[^;]*;",
    re.IGNORECASE,
)
_STATS_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+add\s+stats\b[^;]*;",
    re.IGNORECASE,
)
_SET_LINE_RE = re.compile(
    r'^\s*(?P<character>[A-Za-z0-9_]+)\s+add\s+set\s*=\s*"'
    r'(?P<set_key>[a-z0-9]+)"(?P<tail>[^;]*);',
    re.IGNORECASE,
)
_SENSITIVE_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+\s+"
    r"(?:char\b|add\s+(?:weapon|set|stats)\b)",
    re.IGNORECASE,
)
_ARTIFACT_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+\s+add\s+(?:set|stats)\b",
    re.IGNORECASE,
)
_SET_COUNT_RE = re.compile(
    r"(?<![A-Za-z0-9_])count\s*=\s*(?P<count>[0-9]+)"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_SET_PARAMS_RE = re.compile(
    r"\+\s*params\s*=\s*\[(?P<body>[^\]]*)\]",
    re.IGNORECASE,
)
_SET_PARAM_ENTRY_RE = re.compile(
    r"(?P<key>[a-z][a-z0-9_]*)\s*=\s*(?P<value>-?[0-9]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerConfigShellIssue:
    code: str
    message: str
    character_key: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "character_key": self.character_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSourceSetSuggestion:
    wearer: GcsimOptimizerWearerIdentity
    gcsim_set_key: str
    source_count: int
    set_parameters: Mapping[str, str | int | float | bool] = field(
        default_factory=dict
    )
    mapping_status: str = "unmapped"

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise TypeError("wearer must be a GcsimOptimizerWearerIdentity")
        if _SET_KEY_RE.fullmatch(self.gcsim_set_key) is None:
            raise ValueError("gcsim_set_key must be canonical")
        if (
            isinstance(self.source_count, bool)
            or not isinstance(self.source_count, int)
            or self.source_count < 2
            or self.source_count > 5
        ):
            raise ValueError("source_count must be between 2 and 5")
        if self.mapping_status not in {"ready", "unmapped", "unmodeled"}:
            raise ValueError("mapping_status is unsupported")
        object.__setattr__(
            self,
            "set_parameters",
            MappingProxyType(dict(sorted(self.set_parameters.items()))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "gcsim_set_key": self.gcsim_set_key,
            "source_count": self.source_count,
            "set_parameters": dict(self.set_parameters),
            "mapping_status": self.mapping_status,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSourceArtifactBlock:
    wearer: GcsimOptimizerWearerIdentity
    marker: str
    source_text_sha256: str
    source_set_row_count: int
    source_stats_row_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "marker": self.marker,
            "source_text_sha256": self.source_text_sha256,
            "source_set_row_count": self.source_set_row_count,
            "source_stats_row_count": self.source_stats_row_count,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerConfigShell:
    source_simulation_sha256: str
    source_config_sha256: str
    shell_sha256: str
    preserved_non_artifact_sha256: str
    config_text: str
    wearers: tuple[GcsimOptimizerWearerIdentity, ...]
    artifact_blocks: tuple[GcsimOptimizerSourceArtifactBlock, ...]
    source_set_suggestions: tuple[GcsimOptimizerSourceSetSuggestion, ...]
    schema_version: int = GCSIM_OPTIMIZER_CONFIG_SHELL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_CONFIG_SHELL_SCHEMA_VERSION:
            raise ValueError("unsupported optimizer config shell schema")
        for field_name in (
            "source_simulation_sha256",
            "source_config_sha256",
            "shell_sha256",
            "preserved_non_artifact_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if not self.config_text:
            raise ValueError("config_text must be non-empty")
        if _sha256_text(self.config_text) != self.shell_sha256:
            raise ValueError("shell_sha256 does not match config_text")
        if len(self.wearers) != 4 or len(self.artifact_blocks) != 4:
            raise ValueError("config shell requires four wearers and four markers")
        expected_markers = tuple(item.marker for item in self.artifact_blocks)
        if any(self.config_text.count(marker) != 1 for marker in expected_markers):
            raise ValueError("each artifact marker must occur exactly once")
        if _ARTIFACT_STATEMENT_RE.search(
            build_gcsim_structural_view(self.config_text)
        ):
            raise ValueError("config shell still contains artifact statements")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_simulation_sha256": self.source_simulation_sha256,
            "source_config_sha256": self.source_config_sha256,
            "shell_sha256": self.shell_sha256,
            "preserved_non_artifact_sha256": (
                self.preserved_non_artifact_sha256
            ),
            "config_text": self.config_text,
            "wearers": [item.to_dict() for item in self.wearers],
            "artifact_blocks": [item.to_dict() for item in self.artifact_blocks],
            "source_set_suggestions": [
                item.to_dict() for item in self.source_set_suggestions
            ],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerConfigShellResult:
    status: str
    ready: bool
    shell: GcsimOptimizerConfigShell | None = None
    issues: tuple[GcsimOptimizerConfigShellIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.ready != (self.shell is not None and not self.issues):
            raise ValueError("config shell result readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready": self.ready,
            "shell": None if self.shell is None else self.shell.to_dict(),
            "issues": [item.to_dict() for item in self.issues],
        }


def build_gcsim_optimizer_config_shell(
    config_text: str,
    *,
    source_simulation: GcsimOptimizerSourceSimulationIdentity,
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerConfigShellResult:
    """Remove four artifact blocks from one frozen prepared config."""

    text = str(config_text or "")
    issue = _preflight_issue(text, source_simulation, engine_context)
    if issue is not None:
        return _not_ready(issue)

    try:
        declared = validate_gcsim_farming_static_config(text)
    except ValueError as exc:
        return _not_ready(
            GcsimOptimizerConfigShellIssue(
                "source_config_structure_invalid",
                str(exc),
            )
        )
    normalized_declared = tuple(item.casefold() for item in declared)
    expected = tuple(
        item.gcsim_character_key for item in source_simulation.wearers
    )
    if normalized_declared != expected or len(normalized_declared) != 4:
        return _not_ready(
            GcsimOptimizerConfigShellIssue(
                "source_wearer_identity_mismatch",
                "Config declarations must exactly match four source wearers in order.",
            )
        )
    if any(_CHARACTER_KEY_RE.fullmatch(item) is None for item in expected):
        return _not_ready(
            GcsimOptimizerConfigShellIssue(
                "source_character_key_invalid",
                "Source character keys must be canonical lowercase GCSIM keys.",
            )
        )

    structural = build_gcsim_structural_view(text)
    for match in _SENSITIVE_STATEMENT_RE.finditer(structural):
        terminator = find_gcsim_statement_terminator(structural, match.end())
        if not is_canonical_gcsim_statement_row(
            structural,
            token_start=match.start(),
            terminator_index=terminator,
        ):
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_equipment_statement_noncanonical",
                    "Character/equipment statements must occupy canonical rows.",
                )
            )

    lines = text.splitlines(keepends=True)
    character_rows: dict[str, list[int]] = {}
    weapon_rows: dict[str, list[int]] = {}
    stats_rows: dict[str, list[int]] = {}
    set_rows: dict[str, list[tuple[int, _ParsedSetRow]]] = {}
    parse_issues: list[GcsimOptimizerConfigShellIssue] = []

    for index, line in enumerate(lines):
        character_match = _CHARACTER_LINE_RE.match(line)
        if character_match:
            key = character_match.group("character").casefold()
            character_rows.setdefault(key, []).append(index)
        weapon_match = _WEAPON_LINE_RE.match(line)
        if weapon_match:
            key = weapon_match.group("character").casefold()
            weapon_rows.setdefault(key, []).append(index)
        stats_match = _STATS_LINE_RE.match(line)
        if stats_match:
            key = stats_match.group("character").casefold()
            stats_rows.setdefault(key, []).append(index)
        if re.match(
            r"^\s*[A-Za-z0-9_]+\s+add\s+set\b",
            line,
            re.IGNORECASE,
        ):
            try:
                parsed_set = _parse_set_row(line)
            except ValueError as exc:
                parse_issues.append(
                    GcsimOptimizerConfigShellIssue(
                        "source_set_row_invalid",
                        str(exc),
                    )
                )
            else:
                set_rows.setdefault(parsed_set.character_key, []).append(
                    (index, parsed_set)
                )
    if parse_issues:
        return GcsimOptimizerConfigShellResult(
            status=OPTIMIZER_CONFIG_SHELL_NOT_READY,
            ready=False,
            issues=tuple(parse_issues),
        )

    declared_set = set(expected)
    referenced = set(character_rows) | set(weapon_rows) | set(stats_rows) | set(
        set_rows
    )
    orphans = sorted(referenced - declared_set)
    if orphans:
        return _not_ready(
            GcsimOptimizerConfigShellIssue(
                "source_equipment_orphan_character",
                f"Equipment rows reference undeclared characters: {orphans}.",
            )
        )

    removed_indices: set[int] = set()
    insertion_lines: dict[int, str] = {}
    blocks: list[GcsimOptimizerSourceArtifactBlock] = []
    suggestions: list[GcsimOptimizerSourceSetSuggestion] = []
    wearer_by_key = {
        item.gcsim_character_key: item for item in source_simulation.wearers
    }

    for key in expected:
        if len(character_rows.get(key, ())) != 1:
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_character_declaration_count_invalid",
                    "Each source wearer must have exactly one character row.",
                    key,
                )
            )
        if len(weapon_rows.get(key, ())) != 1:
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_weapon_row_count_invalid",
                    "Each source wearer must have exactly one weapon row.",
                    key,
                )
            )
        if len(stats_rows.get(key, ())) != 1:
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_stats_row_count_invalid",
                    "Each source wearer must have exactly one aggregate stats row.",
                    key,
                )
            )
        indexed_sets = set_rows.get(key, ())
        artifact_indices = sorted(
            [index for index, _item in indexed_sets] + stats_rows[key]
        )
        if artifact_indices != list(
            range(artifact_indices[0], artifact_indices[-1] + 1)
        ):
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_artifact_block_noncontiguous",
                    "Set/stats rows for one wearer must form one contiguous block.",
                    key,
                )
            )
        if weapon_rows[key][0] >= artifact_indices[0]:
            return _not_ready(
                GcsimOptimizerConfigShellIssue(
                    "source_artifact_block_order_invalid",
                    "Artifact rows must follow the wearer's weapon row.",
                    key,
                )
            )
        marker = _artifact_marker(wearer_by_key[key])
        source_block_text = "".join(lines[index] for index in artifact_indices)
        first_index = artifact_indices[0]
        insertion_lines[first_index] = _with_line_ending(marker, lines[first_index])
        removed_indices.update(artifact_indices)
        blocks.append(
            GcsimOptimizerSourceArtifactBlock(
                wearer=wearer_by_key[key],
                marker=marker.strip(),
                source_text_sha256=_sha256_text(source_block_text),
                source_set_row_count=len(indexed_sets),
                source_stats_row_count=1,
            )
        )
        seen_active: set[str] = set()
        for _index, parsed_set in indexed_sets:
            if parsed_set.count < 2:
                continue
            if parsed_set.set_key in seen_active:
                return _not_ready(
                    GcsimOptimizerConfigShellIssue(
                        "source_active_set_duplicate",
                        "One active set key may appear only once per wearer.",
                        key,
                    )
                )
            seen_active.add(parsed_set.set_key)
            suggestions.append(
                GcsimOptimizerSourceSetSuggestion(
                    wearer=wearer_by_key[key],
                    gcsim_set_key=parsed_set.set_key,
                    source_count=parsed_set.count,
                    set_parameters=parsed_set.parameters,
                    mapping_status=_set_mapping_status(
                        engine_context,
                        parsed_set.set_key,
                        parsed_set.count,
                    ),
                )
            )

    preserved_text = "".join(
        line for index, line in enumerate(lines) if index not in removed_indices
    )
    output: list[str] = []
    for index, line in enumerate(lines):
        marker_line = insertion_lines.get(index)
        if marker_line is not None:
            output.append(marker_line)
        if index not in removed_indices:
            output.append(line)
    shell_text = "".join(output)
    if _ARTIFACT_STATEMENT_RE.search(build_gcsim_structural_view(shell_text)):
        return _not_ready(
            GcsimOptimizerConfigShellIssue(
                "artifact_statement_survived",
                "Artifact set/stats rows survived shell construction.",
            )
        )

    shell = GcsimOptimizerConfigShell(
        source_simulation_sha256=source_simulation.identity_sha256,
        source_config_sha256=source_simulation.prepared_config_sha256,
        shell_sha256=_sha256_text(shell_text),
        preserved_non_artifact_sha256=_sha256_text(preserved_text),
        config_text=shell_text,
        wearers=source_simulation.wearers,
        artifact_blocks=tuple(blocks),
        source_set_suggestions=tuple(suggestions),
    )
    return GcsimOptimizerConfigShellResult(
        status=OPTIMIZER_CONFIG_SHELL_READY,
        ready=True,
        shell=shell,
    )


@dataclass(frozen=True, slots=True)
class _ParsedSetRow:
    character_key: str
    set_key: str
    count: int
    parameters: Mapping[str, str | int | float | bool]


def _parse_set_row(line: str) -> _ParsedSetRow:
    match = _SET_LINE_RE.match(line)
    if match is None:
        raise ValueError("Set row must use a quoted canonical GCSIM set key.")
    character_key = match.group("character").casefold()
    set_key = match.group("set_key").casefold()
    tail = match.group("tail")
    params_matches = tuple(_SET_PARAMS_RE.finditer(tail))
    if len(params_matches) > 1:
        raise ValueError("Set row may contain only one +params block.")
    count_view = list(tail)
    for params_match in params_matches:
        count_view[params_match.start() : params_match.end()] = (
            " " * (params_match.end() - params_match.start())
        )
    count_matches = tuple(_SET_COUNT_RE.finditer("".join(count_view)))
    if len(count_matches) != 1:
        raise ValueError("Set row requires exactly one integer count option.")
    count = int(count_matches[0].group("count"), 10)
    if count not in range(1, 6):
        raise ValueError("Set row count must be one integer from 1 through 5.")

    parameters: dict[str, str | int | float | bool] = {}
    consumed = [False] * len(tail)
    for option_match in (*count_matches, *params_matches):
        for index in range(option_match.start(), option_match.end()):
            consumed[index] = True
    if "".join(
        character
        for index, character in enumerate(tail)
        if not consumed[index]
    ).strip():
        raise ValueError("Set row contains unsupported trailing syntax.")

    if params_matches:
        body = params_matches[0].group("body")
        if not body.strip():
            raise ValueError("Set +params block must not be empty.")
        cursor = 0
        for entry in _SET_PARAM_ENTRY_RE.finditer(body):
            separator = body[cursor : entry.start()]
            if cursor == 0:
                if separator.strip():
                    raise ValueError("Set +params contains unsupported syntax.")
            elif separator.strip() != ",":
                raise ValueError("Set +params entries must be comma-separated.")
            key = entry.group("key").casefold()
            if key in parameters:
                raise ValueError(f"Set +params repeats key {key!r}.")
            parameters[key] = int(entry.group("value"), 10)
            cursor = entry.end()
        if body[cursor:].strip():
            raise ValueError("Set +params contains unsupported trailing syntax.")
        if not parameters:
            raise ValueError("Set +params contains no valid entries.")
    return _ParsedSetRow(
        character_key=character_key,
        set_key=set_key,
        count=count,
        parameters=MappingProxyType(parameters),
    )


def _preflight_issue(
    text: str,
    source: GcsimOptimizerSourceSimulationIdentity,
    engine: GcsimOptimizerEngineContext,
) -> GcsimOptimizerConfigShellIssue | None:
    if not isinstance(source, GcsimOptimizerSourceSimulationIdentity):
        return GcsimOptimizerConfigShellIssue(
            "source_simulation_invalid",
            "source_simulation must be typed.",
        )
    if not isinstance(engine, GcsimOptimizerEngineContext):
        return GcsimOptimizerConfigShellIssue(
            "engine_context_invalid",
            "engine_context must be typed.",
        )
    if not engine.trusted or engine.issues:
        return GcsimOptimizerConfigShellIssue(
            "engine_context_untrusted",
            "Config shell requires a trusted optimizer engine context.",
        )
    if (
        source.engine_binding_sha256 != engine.binding_sha256
        or source.catalog_fingerprint != engine.catalog.source_fingerprint
    ):
        return GcsimOptimizerConfigShellIssue(
            "engine_binding_mismatch",
            "Source simulation and engine/catalog binding differ.",
        )
    if not text.strip() or "\x00" in text:
        return GcsimOptimizerConfigShellIssue(
            "source_config_empty",
            "A non-empty prepared config without NUL is required.",
        )
    if has_noncanonical_gcsim_line_separator(text):
        return GcsimOptimizerConfigShellIssue(
            "source_config_line_separator_invalid",
            "Prepared config must use canonical LF or CRLF separators.",
        )
    if GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER in text:
        return GcsimOptimizerConfigShellIssue(
            "source_config_marker_collision",
            "Prepared config already contains an optimizer artifact marker.",
        )
    if _sha256_text(text) != source.prepared_config_sha256:
        return GcsimOptimizerConfigShellIssue(
            "source_config_identity_mismatch",
            "Prepared config text does not match its frozen source identity.",
        )
    return None


def _set_mapping_status(
    engine: GcsimOptimizerEngineContext,
    set_key: str,
    count: int,
) -> str:
    capability = engine.catalog.get(set_key)
    if capability is None or not capability.registered:
        return "unmapped"
    if count >= 4 and not capability.complete_four_piece_modeled:
        return "unmodeled"
    if count >= 2 and not capability.two_piece_modeled:
        return "unmodeled"
    return "ready"


def _artifact_marker(wearer: GcsimOptimizerWearerIdentity) -> str:
    return (
        f"# {GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER} "
        f"team_slot={wearer.team_slot} "
        f"character={wearer.gcsim_character_key}"
    )


def _with_line_ending(rendered: str, original: str) -> str:
    if original.endswith("\r\n"):
        return rendered + "\r\n"
    if original.endswith("\n"):
        return rendered + "\n"
    return rendered


def _not_ready(
    issue: GcsimOptimizerConfigShellIssue,
) -> GcsimOptimizerConfigShellResult:
    return GcsimOptimizerConfigShellResult(
        status=OPTIMIZER_CONFIG_SHELL_NOT_READY,
        ready=False,
        issues=(issue,),
    )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER",
    "GCSIM_OPTIMIZER_CONFIG_SHELL_SCHEMA_VERSION",
    "GcsimOptimizerConfigShell",
    "GcsimOptimizerConfigShellIssue",
    "GcsimOptimizerConfigShellResult",
    "GcsimOptimizerSourceArtifactBlock",
    "GcsimOptimizerSourceSetSuggestion",
    "OPTIMIZER_CONFIG_SHELL_NOT_READY",
    "OPTIMIZER_CONFIG_SHELL_READY",
    "build_gcsim_optimizer_config_shell",
]
