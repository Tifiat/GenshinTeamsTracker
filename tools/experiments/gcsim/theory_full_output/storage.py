"""Exact allowlist cleaner for retained Stage15 public exports.

Retention ends at human acceptance or authorized consolidation. Invoking this
cleaner requires that event explicitly; it never removes receipts or pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat


EXPORT_NAMES = frozenset(
    [f"{phase}-{kind}.json.gz" for phase in ("first", "breadth", "deep", "terminal")
     for kind in ("snapshot", "archive")]
    + ["final-archive.json.gz", "study-ledger.json.gz", "full-table.json.gz",
       "full-table.csv", "grouped-options.tsv", "TABLE_SUMMARY_RU.md"]
)


def _unlinked(path: Path) -> None:
    for current in (*reversed(path.parents), path):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("linked retained evidence path")


def cleanup_public_exports(root: Path, receipt: dict, *, accepted_or_consolidated: bool = False) -> dict:
    if not accepted_or_consolidated:
        raise ValueError("human acceptance or authorized consolidation is required")
    root = Path(root).absolute()
    _unlinked(root)
    if not root.is_dir() or receipt.get("schema_kind") != "gtt_theory_real_full_output_validation_v1":
        raise ValueError("owned Stage15 evidence and validation receipt required")
    records = receipt.get("retained_public_files")
    if not isinstance(records, list):
        raise ValueError("exact retained export inventory required")
    files = []
    seen = set()
    # Validate the complete inventory before deleting its first member.
    for row in records:
        name = row.get("path")
        if name not in EXPORT_NAMES or name in seen:
            raise ValueError("invalid or duplicate retained export")
        seen.add(name)
        target = root / name
        _unlinked(target)
        if not target.is_file():
            raise ValueError("retained export missing")
        body = target.read_bytes()
        if len(body) != row.get("bytes") or hashlib.sha256(body).hexdigest() != row.get("sha256"):
            raise ValueError("retained export changed; consolidation must reconcile it")
        files.append((target, len(body)))
    removed = 0
    for target, size in files:
        _unlinked(target)
        target.unlink()
        removed += size
    return {"removed_files": len(files), "removed_bytes": removed, "receipts_and_pins_preserved": True}


def main() -> int:
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
