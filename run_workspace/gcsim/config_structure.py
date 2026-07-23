"""Small lexer-compatible structural helpers for app-owned GCSIM configs.

GCSIM treats newlines as whitespace and semicolons as statement terminators.
Most application renderers intentionally operate on canonical one-statement
rows, so security/provenance checks must not mistake physical lines for parser
boundaries.  This module hides comments and quoted strings without changing
text offsets, then exposes the minimal boundary checks shared by those
renderers.
"""

from __future__ import annotations

import re


_PYTHON_ONLY_LINE_SEPARATORS = frozenset(
    ("\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
)
GCSIM_FARMING_STATIC_TARGET_HP = 999_999_999
_CHARACTER_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<character>[A-Za-z0-9_]+)\s+char\b",
    re.IGNORECASE,
)
_TARGET_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])target\b",
    re.IGNORECASE,
)
_OPTIONS_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])options\b",
    re.IGNORECASE,
)
_SENSITIVE_CONFIG_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"target\b|options\b|"
    r"[A-Za-z0-9_]+\s+(?:char\b|add\s+(?:weapon|set|stats)\b)"
    r")",
    re.IGNORECASE,
)
_TARGET_HP_RE = re.compile(
    r"(?<![A-Za-z0-9_])hp\s*=\s*(?P<hp>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_TARGET_TYPE_RE = re.compile(
    r"(?<![A-Za-z0-9_])type\s*=",
    re.IGNORECASE,
)
_GTT_WAVE_DIRECTIVE_RE = re.compile(
    r"(?im)^\s*(?:#|//)\s*gtt_wave(?:_[A-Za-z0-9_]+)?\b"
)


def has_noncanonical_gcsim_line_separator(config_text: str) -> bool:
    """Return whether Python row splitting disagrees with GCSIM's LF lexer."""

    text = str(config_text or "")
    for index, character in enumerate(text):
        if character == "\r":
            if index + 1 >= len(text) or text[index + 1] != "\n":
                return True
        elif character in _PYTHON_ONLY_LINE_SEPARATORS:
            return True
    return False


def build_gcsim_structural_view(config_text: str) -> str:
    """Return an offset-preserving view with comments/strings blanked out."""

    text = str(config_text or "")
    chars = list(text)
    index = 0
    length = len(chars)
    while index < length:
        current = chars[index]
        if current == "#" or (
            current == "/" and index + 1 < length and chars[index + 1] == "/"
        ):
            while index < length and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue
        if current == '"':
            chars[index] = " "
            index += 1
            while index < length:
                current = chars[index]
                if current == "\n":
                    break
                chars[index] = " "
                index += 1
                if current == "\\" and index < length:
                    if chars[index] != "\n":
                        chars[index] = " "
                        index += 1
                    continue
                if current == '"':
                    break
            continue
        index += 1
    return "".join(chars)


def build_gcsim_comment_free_view(config_text: str) -> str:
    """Blank lexer comments while preserving strings and all text offsets."""

    text = str(config_text or "")
    chars = list(text)
    index = 0
    length = len(chars)
    while index < length:
        current = chars[index]
        if current == '"':
            index += 1
            while index < length:
                current = chars[index]
                index += 1
                if current == "\\" and index < length:
                    if chars[index] != "\n":
                        index += 1
                    continue
                if current == '"' or current == "\n":
                    break
            continue
        if current == "#" or (
            current == "/" and index + 1 < length and chars[index + 1] == "/"
        ):
            while index < length and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue
        index += 1
    return "".join(chars)


def find_gcsim_statement_terminator(
    structural_view: str,
    token_end: int,
) -> int:
    """Locate the engine-visible semicolon following a structural token."""

    if isinstance(token_end, bool) or not isinstance(token_end, int):
        raise TypeError("token_end must be an integer")
    if token_end < 0 or token_end > len(structural_view):
        raise ValueError("token_end is outside structural_view")
    return structural_view.find(";", token_end)


def is_canonical_gcsim_statement_row(
    structural_view: str,
    *,
    token_start: int,
    terminator_index: int,
) -> bool:
    """Return whether a sensitive statement occupies one physical row."""

    if terminator_index < token_start or terminator_index >= len(structural_view):
        return False
    statement_text = structural_view[token_start : terminator_index + 1]
    # ``str.splitlines`` is what the downstream row renderers use.  Reject
    # every separator it recognizes (CR/LF, VT/FF, NEL, U+2028/U+2029, etc.);
    # otherwise row rewriting and the pinned lexer can disagree about structure.
    if len(statement_text.splitlines()) != 1:
        return False
    line_start = structural_view.rfind("\n", 0, token_start) + 1
    line_end = structural_view.find("\n", terminator_index + 1)
    if line_end < 0:
        line_end = len(structural_view)
    return (
        not structural_view[line_start:token_start].strip()
        and not structural_view[terminator_index + 1 : line_end].strip()
    )


def validate_gcsim_farming_static_config(config_text: str) -> tuple[str, ...]:
    """Validate the shared parser-safe farming target/options/row contract.

    The returned tuple is the engine-order list of character declarations.  A
    higher-level caller may additionally bind it to its own wearer identity.
    """

    text = str(config_text or "")
    if not text.strip() or "\x00" in text:
        raise ValueError("config_text must be non-empty and contain no NUL")
    if has_noncanonical_gcsim_line_separator(text):
        raise ValueError(
            "canonical semicolon-terminated rows require LF or CRLF; the "
            "config contains a non-canonical line separator"
        )

    structural_view = build_gcsim_structural_view(text)
    for match in _SENSITIVE_CONFIG_STATEMENT_RE.finditer(structural_view):
        terminator = find_gcsim_statement_terminator(
            structural_view,
            match.end(),
        )
        if not is_canonical_gcsim_statement_row(
            structural_view,
            token_start=match.start(),
            terminator_index=terminator,
        ):
            raise ValueError(
                "farming-sensitive GCSIM statements must each occupy one "
                "canonical semicolon-terminated row"
            )

    declared = tuple(
        match.group("character")
        for match in _CHARACTER_STATEMENT_RE.finditer(structural_view)
    )
    target_statements = tuple(_TARGET_STATEMENT_RE.finditer(structural_view))
    if len(target_statements) != 1:
        raise ValueError(
            "farming config must contain exactly one static target statement"
        )
    options_statements = tuple(_OPTIONS_STATEMENT_RE.finditer(structural_view))
    if len(options_statements) != 1:
        raise ValueError("farming config must contain exactly one options statement")

    target_match = target_statements[0]
    target_terminator = find_gcsim_statement_terminator(
        structural_view,
        target_match.end(),
    )
    target_body = structural_view[target_match.end() : target_terminator]
    hp_matches = tuple(_TARGET_HP_RE.finditer(target_body))
    if len(hp_matches) != 1 or float(hp_matches[0].group("hp")) <= 0:
        raise ValueError(
            "farming static target must carry one explicit positive hp value"
        )
    if _TARGET_TYPE_RE.search(target_body):
        raise ValueError(
            "farming static target must not carry a type profile that can "
            "overwrite the pinned hp value"
        )
    if float(hp_matches[0].group("hp")) != GCSIM_FARMING_STATIC_TARGET_HP:
        raise ValueError(
            "farming static target hp must equal the pinned high-HP dummy value "
            f"{GCSIM_FARMING_STATIC_TARGET_HP}"
        )
    if _GTT_WAVE_DIRECTIVE_RE.search(text):
        raise ValueError("farming config must not enable a GTT wave directive")
    return declared


__all__ = [
    "GCSIM_FARMING_STATIC_TARGET_HP",
    "build_gcsim_comment_free_view",
    "build_gcsim_structural_view",
    "find_gcsim_statement_terminator",
    "has_noncanonical_gcsim_line_separator",
    "is_canonical_gcsim_statement_row",
    "validate_gcsim_farming_static_config",
]
