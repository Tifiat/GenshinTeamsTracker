"""Assemble generated GCSIM character blocks with a manual rotation shell.

This backend/dev boundary keeps the current manual Chasca/Ororon/Furina/Bennett
rotation script separate from generated account-derived character/equipment
blocks. The shell may provide options, energy, placeholder target, active
character, and script text only. It must not be used as account truth.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from run_workspace.gcsim.config_blocks import (
    GcsimCharacterConfigBlock,
    GcsimConfigBlockIssue,
)


ASSEMBLY_READY = "ready"
ASSEMBLY_BLOCK_NOT_READY = "character_block_not_ready"
ASSEMBLY_SHELL_MISSING = "shell_missing"
ASSEMBLY_SHELL_CONTAINS_MANUAL_CHARACTER_BLOCKS = (
    "shell_contains_manual_character_blocks"
)

WARNING_SHELL_TARGET_PLACEHOLDER_NOT_ENEMY_TRUTH = (
    "shell_target_placeholder_not_enemy_truth"
)

SMOKE_FIXTURE_DIR = Path(__file__).resolve().parent / "smoke_fixtures"
CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH = (
    SMOKE_FIXTURE_DIR / "rotation_chasca_ororon_furina_bennett.txt"
)

_ACTIVE_RE = re.compile(r"^\s*active\s+([A-Za-z0-9_]+)\s*;", re.IGNORECASE)
_TARGET_RE = re.compile(r"^\s*target\b", re.IGNORECASE)
_CHAR_BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s+char\b", re.IGNORECASE)
_ADD_BLOCK_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+)\s+add\s+(weapon|set|stats)\b",
    re.IGNORECASE,
)
_CHARACTER_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s+char\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GcsimConfigAssemblyIssue:
    status: str
    field: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class GcsimCharacterBlockSummary:
    index: int
    ready: bool
    status: str
    character_key: str = ""
    line_count: int = 0
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigBlockIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "ready": self.ready,
            "status": self.status,
            "character_key": self.character_key,
            "line_count": self.line_count,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimRotationShellAudit:
    ready: bool
    status: str
    shell_source: str = ""
    active_character_key: str = ""
    target_placeholder_lines: tuple[str, ...] = ()
    manual_block_lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigAssemblyIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "status": self.status,
            "shell_source": self.shell_source,
            "active_character_key": self.active_character_key,
            "target_placeholder_lines": list(self.target_placeholder_lines),
            "manual_block_lines": list(self.manual_block_lines),
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimFullConfigAssembly:
    status: str
    ready: bool
    config_text: str = ""
    shell_source: str = ""
    active_character_key: str = ""
    block_summaries: tuple[GcsimCharacterBlockSummary, ...] = ()
    shell_audit: GcsimRotationShellAudit | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigAssemblyIssue, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "config_text": self.config_text,
            "shell_source": self.shell_source,
            "active_character_key": self.active_character_key,
            "block_summaries": [
                summary.to_dict() for summary in self.block_summaries
            ],
            "shell_audit": (
                self.shell_audit.to_dict()
                if self.shell_audit is not None
                else None
            ),
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def assemble_gcsim_full_config(
    character_blocks: Iterable[GcsimCharacterConfigBlock],
    shell_text: str,
    *,
    shell_source: str = "",
) -> GcsimFullConfigAssembly:
    blocks = tuple(character_blocks)
    block_summaries = tuple(
        _block_summary(index, block) for index, block in enumerate(blocks)
    )
    shell_audit = audit_rotation_shell(shell_text, shell_source=shell_source)
    warnings: list[str] = []
    issues: list[GcsimConfigAssemblyIssue] = []

    for summary in block_summaries:
        warnings.extend(summary.warnings)
        if not summary.ready:
            issues.append(
                GcsimConfigAssemblyIssue(
                    ASSEMBLY_BLOCK_NOT_READY,
                    f"character_blocks[{summary.index}]",
                    f"Character block {summary.index} is not ready: {summary.status}.",
                )
            )
    warnings.extend(shell_audit.warnings)
    issues.extend(shell_audit.issues)

    status = _status_from_issues(issues)
    if status != ASSEMBLY_READY:
        return GcsimFullConfigAssembly(
            status=status,
            ready=False,
            shell_source=shell_source,
            active_character_key=shell_audit.active_character_key,
            block_summaries=block_summaries,
            shell_audit=shell_audit,
            warnings=_dedupe_tuple(warnings),
            issues=tuple(issues),
            source_notes=_source_notes(),
        )

    config_text = _join_config_parts(
        *(block.text for block in blocks),
        shell_text,
    )
    return GcsimFullConfigAssembly(
        status=ASSEMBLY_READY,
        ready=True,
        config_text=config_text,
        shell_source=shell_source,
        active_character_key=shell_audit.active_character_key,
        block_summaries=block_summaries,
        shell_audit=shell_audit,
        warnings=_dedupe_tuple(warnings),
        issues=(),
        source_notes=_source_notes(),
    )


def assemble_gcsim_full_config_from_shell_path(
    character_blocks: Iterable[GcsimCharacterConfigBlock],
    shell_path: str | Path = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
) -> GcsimFullConfigAssembly:
    path = Path(shell_path)
    try:
        shell_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return GcsimFullConfigAssembly(
            status=ASSEMBLY_SHELL_MISSING,
            ready=False,
            shell_source=str(path),
            issues=(
                GcsimConfigAssemblyIssue(
                    ASSEMBLY_SHELL_MISSING,
                    "shell_path",
                    f"Rotation shell was not found: {path}",
                ),
            ),
            source_notes=_source_notes(),
        )
    return assemble_gcsim_full_config(
        character_blocks,
        shell_text,
        shell_source=str(path),
    )


def audit_rotation_shell(
    shell_text: str,
    *,
    shell_source: str = "",
) -> GcsimRotationShellAudit:
    warnings: list[str] = []
    issues: list[GcsimConfigAssemblyIssue] = []
    active_character_key = ""
    target_lines: list[str] = []
    manual_lines: list[str] = []

    for line in str(shell_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        active_match = _ACTIVE_RE.match(line)
        if active_match:
            active_character_key = active_match.group(1)
        if _TARGET_RE.match(line):
            target_lines.append(stripped)
        if _CHAR_BLOCK_RE.match(line) or _ADD_BLOCK_RE.match(line):
            manual_lines.append(stripped)

    if target_lines:
        warnings.append(WARNING_SHELL_TARGET_PLACEHOLDER_NOT_ENEMY_TRUTH)
    if manual_lines:
        issues.append(
            GcsimConfigAssemblyIssue(
                ASSEMBLY_SHELL_CONTAINS_MANUAL_CHARACTER_BLOCKS,
                "shell_text",
                (
                    "Rotation shell contains manual character/equipment/stat "
                    "blocks; generated blocks must be the only account truth."
                ),
            )
        )

    status = _status_from_issues(issues)
    return GcsimRotationShellAudit(
        ready=status == ASSEMBLY_READY,
        status=status,
        shell_source=shell_source,
        active_character_key=active_character_key,
        target_placeholder_lines=tuple(target_lines),
        manual_block_lines=tuple(manual_lines),
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def _block_summary(
    index: int,
    block: GcsimCharacterConfigBlock,
) -> GcsimCharacterBlockSummary:
    return GcsimCharacterBlockSummary(
        index=index,
        ready=block.ready,
        status=block.status,
        character_key=_character_key_from_block(block),
        line_count=len(block.lines),
        warnings=block.warnings,
        issues=block.issues,
    )


def _character_key_from_block(block: GcsimCharacterConfigBlock) -> str:
    for line in block.lines:
        match = _CHARACTER_KEY_RE.match(line)
        if match:
            return match.group(1)
    return ""


def _join_config_parts(*parts: str) -> str:
    cleaned = [part.strip() for part in parts if str(part or "").strip()]
    return "\n\n".join(cleaned) + ("\n" if cleaned else "")


def _status_from_issues(issues: Iterable[GcsimConfigAssemblyIssue]) -> str:
    for status in (
        ASSEMBLY_SHELL_MISSING,
        ASSEMBLY_SHELL_CONTAINS_MANUAL_CHARACTER_BLOCKS,
        ASSEMBLY_BLOCK_NOT_READY,
    ):
        if any(issue.status == status for issue in issues):
            return status
    return ASSEMBLY_READY


def _source_notes() -> dict[str, Any]:
    return {
        "rotation_shell_is_account_truth": False,
        "target_line_is_enemy_truth": False,
        "enemy_truth_source": "-gtt-wave-scenario",
        "full_run_config_generation": "backend_dev_foundation_only",
    }


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)
