"""Exact allowlist cleanup for explicitly accepted Stage16 public exports."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA_KIND = "gtt_theory_goblet_controls_validation_v1"
EXPORT_NAMES = frozenset({"comparison.json", "proc-evidence.json"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_REPARSE_POINT = 0x400


def _unlinked(path: Path) -> None:
    """Reject symlink/junction components, including a dangling final link."""
    for current in (*reversed(path.parents), path):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if (stat.S_ISLNK(info.st_mode) or
                    getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT):
                raise ValueError("linked retained evidence path")


def _inventory(receipt: Any) -> list[tuple[str, int, str]]:
    if not isinstance(receipt, dict) or receipt.get("schema_kind") != SCHEMA_KIND:
        raise ValueError("Stage16 validation receipt required")
    records = receipt.get("retained_public_files")
    if not isinstance(records, list):
        raise ValueError("exact retained export inventory required")

    validated: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for row in records:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ValueError("retained export inventory row must contain only path, bytes and sha256")
        name = row["path"]
        if not isinstance(name, str) or name not in EXPORT_NAMES or name in seen:
            raise ValueError("invalid or duplicate retained export")
        byte_count = row["bytes"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise ValueError("retained export byte count must be a non-negative integer")
        digest = row["sha256"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("retained export SHA256 must be lowercase hex")
        seen.add(name)
        validated.append((name, byte_count, digest))
    return validated


def cleanup_public_exports(
    root: Path,
    receipt: dict,
    accepted_or_consolidated: bool = False,
) -> dict:
    """Delete only unchanged Stage16 comparison/projection exports.

    Acceptance or an authorized consolidation must be explicit. The complete
    inventory is validated before the first unlink; protocols, pins, receipts,
    reports and any unlisted files are outside this cleaner's authority.
    """
    if not accepted_or_consolidated:
        raise ValueError("human acceptance or authorized consolidation is required")

    root = Path(root).absolute()
    _unlinked(root)
    if not root.is_dir():
        raise ValueError("owned Stage16 evidence directory required")
    records = _inventory(receipt)

    files: list[tuple[Path, str, int, str]] = []
    for name, expected_bytes, expected_sha256 in records:
        target = root / name
        _unlinked(target)
        if not target.is_file():
            raise ValueError("retained export missing")
        body = target.read_bytes()
        if (len(body) != expected_bytes or
                hashlib.sha256(body).hexdigest() != expected_sha256):
            raise ValueError("retained export changed; consolidation must reconcile it")
        files.append((target, name, expected_bytes, expected_sha256))

    removed_bytes = 0
    for target, _name, expected_bytes, expected_sha256 in files:
        _unlinked(target)
        if not target.is_file():
            raise ValueError("retained export changed before deletion")
        body = target.read_bytes()
        if (len(body) != expected_bytes or
                hashlib.sha256(body).hexdigest() != expected_sha256):
            raise ValueError("retained export changed before deletion")
        target.unlink()
        removed_bytes += expected_bytes

    return {
        "removed_files": len(files),
        "removed_bytes": removed_bytes,
        "receipts_pins_protocols_and_reports_preserved": True,
    }


def main() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--accepted-or-authorized-consolidation", action="store_true")
    args = parser.parse_args()
    _unlinked(args.receipt.absolute())
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    result = cleanup_public_exports(args.receipt.parent, receipt,
        accepted_or_consolidated=args.accepted_or_authorized_consolidation)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
