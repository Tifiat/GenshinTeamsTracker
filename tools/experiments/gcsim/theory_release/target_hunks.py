"""Relocate validated unified-diff hunks onto a nearby exact target image."""
from __future__ import annotations

from functools import lru_cache
import re

from . import package_io


_HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n")
_NO_NEWLINE = "\\ No newline at end of file\n"


def _text_lines(value: str, label: str) -> list[str]:
    if "\r" in value or "\x00" in value:
        raise ValueError(f"{label} must use LF UTF-8 text")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} is not valid UTF-8 text") from exc
    parts = value.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _byte_lines(value: bytes, label: str) -> list[str]:
    if not isinstance(value, bytes):
        raise ValueError(f"{label} must be bytes")
    try:
        decoded = value.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} must be UTF-8 text") from exc
    return _text_lines(decoded, label)


def _segments(events: list[tuple[str, str]]) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Keep each context row and each adjacent edit run as fixed patch intent."""
    result: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    index = 0
    while index < len(events):
        prefix, line = events[index]
        if prefix == " ":
            result.append(((line,), (line,)))
            index += 1
            continue
        old: list[str] = []
        new: list[str] = []
        while index < len(events) and events[index][0] != " ":
            prefix, line = events[index]
            if prefix == "-":
                old.append(line)
            else:
                new.append(line)
            index += 1
        result.append((tuple(old), tuple(new)))
    return result


def _only_shared_context(
    old: list[str], new: list[str], segments: list[tuple[tuple[str, ...], tuple[str, ...]]]
) -> bool:
    """Accept only extra lines retained identically on both sides of the edit."""
    @lru_cache(maxsize=None)
    def follows(segment: int, old_at: int, new_at: int) -> bool:
        if segment == len(segments):
            return old[old_at:] == new[new_at:]
        old_part, new_part = segments[segment]
        limit = min(len(old) - old_at, len(new) - new_at)
        for padding in range(limit + 1):
            if old[old_at:old_at + padding] != new[new_at:new_at + padding]:
                continue
            old_start, new_start = old_at + padding, new_at + padding
            old_end, new_end = old_start + len(old_part), new_start + len(new_part)
            if (old[old_start:old_end] == list(old_part)
                    and new[new_start:new_end] == list(new_part)
                    and follows(segment + 1, old_end, new_end)):
                return True
        return False

    return follows(0, 0, 0)


def _parse_hunks(patch: str) -> tuple[bool, list[dict[str, object]]]:
    if not isinstance(patch, str) or not patch.endswith("\n"):
        raise ValueError("patch must be complete LF UTF-8 text")
    _text_lines(patch, "patch")
    rows = [part + "\n" for part in patch.split("\n")[:-1]]
    creates = rows[0] == "--- /dev/null\n"
    hunks: list[dict[str, object]] = []
    index = 2
    while index < len(rows):
        match = _HUNK.fullmatch(rows[index])
        if match is None:
            raise ValueError("missing or unsupported hunk header")
        header = rows[index][:-1]
        index += 1
        events: list[tuple[str, str]] = []
        while index < len(rows) and not rows[index].startswith("@@ "):
            row = rows[index]
            index += 1
            if row == _NO_NEWLINE:
                if not events or not events[-1][1].endswith("\n"):
                    raise ValueError("misplaced no-newline marker")
                prefix, line = events[-1]
                events[-1] = (prefix, line[:-1])
                continue
            if not row or row[0] not in " +-":
                raise ValueError("unsupported hunk content")
            events.append((row[0], row[1:]))
        old = [line for prefix, line in events if prefix in " -"]
        new = [line for prefix, line in events if prefix in " +"]
        hunks.append({
            "header": header,
            "events": events,
            "segments": _segments(events),
            "old": old,
            "new": new,
        })
    if not hunks:
        raise ValueError("patch contains no hunks")
    return creates, hunks


def _matches(lines: list[str], context: list[str]) -> list[int]:
    if not context:
        return []
    width = len(context)
    return [start for start in range(len(lines) - width + 1)
            if lines[start:start + width] == context]


def _sha(lines: list[str]) -> str:
    return package_io.sha_bytes("".join(lines).encode("utf-8"))


def _record(index: int, hunk: dict[str, object], old: list[str], new: list[str],
            offset: int, status: str, overridden: bool) -> dict[str, object]:
    return {
        "index": index,
        "header": hunk["header"],
        "original_old_sha": _sha(hunk["old"]),
        "original_new_sha": _sha(hunk["new"]),
        "resolved_old_sha": _sha(old),
        "resolved_new_sha": _sha(new),
        "target_offset": offset,
        "status": status,
        "override": overridden,
    }


def relocate_hunks(
    path: str,
    original_before: bytes,
    target_before: bytes,
    patch: str,
    overrides: dict[int, tuple[str, str]] | None = None,
) -> tuple[bytes, list[dict]]:
    """Apply an exact source-validated patch to a shifted target.

    Hunk offsets in the audit are zero-based line offsets in the progressively
    updated target. Overrides are LF text pairs containing the complete old
    and new hunk contexts; added target context must occur identically in both.
    """
    # This exact source application owns patch syntax, hunk counts and paths.
    original_after = package_io.apply_file_patch(path, original_before, patch)
    target_lines = _byte_lines(target_before, "target source")
    creates, hunks = _parse_hunks(patch)

    if overrides is None:
        override_items: list[tuple[object, object]] = []
    elif isinstance(overrides, dict):
        override_items = list(overrides.items())
    else:
        raise ValueError("overrides must map hunk numbers to old/new contexts")
    override_map: dict[int, tuple[str, str]] = {}
    for number, value in override_items:
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("invalid override hunk number")
        if number in override_map:
            raise ValueError("duplicate override hunk number")
        if not isinstance(value, tuple) or len(value) != 2 or not all(isinstance(item, str) for item in value):
            raise ValueError("override must be an old/new text pair")
        override_map[number] = value
    if any(number > len(hunks) for number in override_map):
        raise ValueError("override names an unknown hunk")

    if creates:
        if target_before == original_after:
            if override_map:
                raise ValueError("override is unused for an already-created target")
            audit = []
            for number, hunk in enumerate(hunks, 1):
                old, new = hunk["old"], hunk["new"]
                audit.append(_record(number, hunk, old, new, 0, "already_after", False))
            return target_before, audit
        if target_before:
            raise ValueError("new-file patch collides with a nonempty target")
        if override_map:
            raise ValueError("override is unused for a new-file creation")
        audit = []
        for number, hunk in enumerate(hunks, 1):
            old, new = hunk["old"], hunk["new"]
            if old:
                raise ValueError("creation hunk unexpectedly consumes source context")
            target_lines.extend(new)
            audit.append(_record(number, hunk, old, new, 0, "applied", False))
        return "".join(target_lines).encode("utf-8"), audit

    audit = []
    used_overrides: set[int] = set()
    previous_end = 0
    for number, hunk in enumerate(hunks, 1):
        old, new = list(hunk["old"]), list(hunk["new"])
        overridden = number in override_map
        if overridden:
            used_overrides.add(number)
            old_text, new_text = override_map[number]
            resolved_old = _text_lines(old_text, "override old context")
            resolved_new = _text_lines(new_text, "override new context")
            if not _only_shared_context(resolved_old, resolved_new, hunk["segments"]):
                raise ValueError("override changes or drops original hunk intent")
            old, new = resolved_old, resolved_new
        if not old:
            raise ValueError("hunk has empty old context")
        positions = _matches(target_lines, old)
        if not positions:
            raise ValueError("full hunk context is missing from target")
        if len(positions) != 1:
            raise ValueError("full hunk context is ambiguous in target")
        offset = positions[0]
        if offset < previous_end:
            raise ValueError("target hunks are out of order or overlap")
        target_lines[offset:offset + len(old)] = new
        previous_end = offset + len(new)
        audit.append(_record(number, hunk, old, new, offset, "applied", overridden))
    if set(override_map) != used_overrides:
        raise ValueError("override was not used")
    return "".join(target_lines).encode("utf-8"), audit
