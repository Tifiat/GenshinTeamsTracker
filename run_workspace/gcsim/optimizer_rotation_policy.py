"""Bound unsafe high-HP infinite rotations only inside optimizer execution.

GCSIM treats a target with HP as damage mode and then ignores ``duration``;
``while 1`` therefore runs until that target dies.  The optimizer's pinned
999,999,999-HP dummy makes such a trace impractically large.  For this exact
combination, the optimizer uses GCSIM's documented/default 90-second duration
mode while preserving the user's editor text and original source receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .config_structure import (
    GCSIM_FARMING_STATIC_TARGET_HP,
    build_gcsim_structural_view,
    find_gcsim_statement_terminator,
    has_unbounded_gcsim_loop,
)


DEFAULT_OPTIMIZER_LOOP_DURATION_SECONDS = 90
ROTATION_AUTO_BOUNDED_WARNING = "rotation_infinite_loop_auto_bounded"

_TARGET_RE = re.compile(r"(?<![A-Za-z0-9_])target\b", re.IGNORECASE)
_OPTIONS_RE = re.compile(r"(?<![A-Za-z0-9_])options\b", re.IGNORECASE)
_PINNED_HP_RE = re.compile(
    rf"[ \t]+hp\s*=\s*{GCSIM_FARMING_STATIC_TARGET_HP}(?:\.0+)?\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])duration\s*=\s*(?P<duration>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class OptimizerRotationPolicyResult:
    source_text: str
    optimizer_text: str
    changed: bool
    duration_seconds: float | None = None
    warning_code: str = ""


def normalize_optimizer_rotation_shell(
    shell_text: str,
) -> OptimizerRotationPolicyResult:
    """Return a duration-mode optimizer copy for the exact unsafe combination."""

    source = str(shell_text or "")
    if not has_unbounded_gcsim_loop(source):
        return OptimizerRotationPolicyResult(source, source, False)
    structural = build_gcsim_structural_view(source)
    targets = tuple(_TARGET_RE.finditer(structural))
    options = tuple(_OPTIONS_RE.finditer(structural))
    if len(targets) != 1 or len(options) != 1:
        return OptimizerRotationPolicyResult(source, source, False)

    target_end = find_gcsim_statement_terminator(structural, targets[0].end())
    options_end = find_gcsim_statement_terminator(structural, options[0].end())
    if target_end < 0 or options_end < 0:
        return OptimizerRotationPolicyResult(source, source, False)
    target_body = structural[targets[0].end() : target_end]
    hp_matches = tuple(_PINNED_HP_RE.finditer(target_body))
    if len(hp_matches) != 1:
        return OptimizerRotationPolicyResult(source, source, False)

    options_body = structural[options[0].end() : options_end]
    duration_matches = tuple(_DURATION_RE.finditer(options_body))
    if len(duration_matches) > 1:
        return OptimizerRotationPolicyResult(source, source, False)
    duration = float(
        duration_matches[0].group("duration")
        if duration_matches
        else DEFAULT_OPTIMIZER_LOOP_DURATION_SECONDS
    )
    if duration <= 0:
        return OptimizerRotationPolicyResult(source, source, False)

    hp_match = hp_matches[0]
    hp_start = targets[0].end() + hp_match.start()
    hp_end = targets[0].end() + hp_match.end()
    edits: list[tuple[int, int, str]] = [(hp_start, hp_end, "")]
    if not duration_matches:
        edits.append(
            (
                options_end,
                options_end,
                f" duration={DEFAULT_OPTIMIZER_LOOP_DURATION_SECONDS}",
            )
        )
    optimizer_text = source
    for start, end, replacement in sorted(edits, reverse=True):
        optimizer_text = optimizer_text[:start] + replacement + optimizer_text[end:]
    return OptimizerRotationPolicyResult(
        source_text=source,
        optimizer_text=optimizer_text,
        changed=True,
        duration_seconds=duration,
        warning_code=ROTATION_AUTO_BOUNDED_WARNING,
    )


__all__ = [
    "DEFAULT_OPTIMIZER_LOOP_DURATION_SECONDS",
    "OptimizerRotationPolicyResult",
    "ROTATION_AUTO_BOUNDED_WARNING",
    "normalize_optimizer_rotation_shell",
]
