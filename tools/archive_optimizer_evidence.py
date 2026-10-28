"""N0 lossless evidence compaction, not a general backup or deletion utility.

The exact reviewed plan is optimizer_deep_cleanup.json. One bounded archive
replaces diagnostic-only raw witnesses; active N1 inputs stay expanded. This
tool never removes source directories. The PowerShell cleaner verifies this
archive before its separately guarded literal-path deletions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INDEX = "gtt-evidence-index.json"


def unlinked(path: Path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 1024):
            raise ValueError(f"Linked evidence path: {part}")


def path_inside(root: Path, name: str) -> Path:
    path = root / name
    unlinked(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"Invalid evidence path: {name}")
    return resolved


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def source_files(root, plan, *, allow_missing=False):
    excluded = {path_inside(root, r["path"]) for r in plan["delete_directories"]}
    for row in plan["archive_directories"]:
        base = path_inside(root, row["path"])
        if allow_missing and not base.exists():
            continue  # previous guarded cleanup may have completed this root
        if not base.is_dir():
            raise ValueError(f"Missing evidence source: {base}")
        for parent, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if Path(parent) / d not in excluded)
            for name in (*dirs, *files):
                item = Path(parent) / name
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
                    raise ValueError(f"Linked evidence content: {item}")
            for name in sorted(files):
                yield Path(parent) / name


def prepare_archive(root: Path, plan: dict) -> dict:
    root = root.resolve()
    archive = path_inside(root, plan["archive_path"])
    receipt_path = path_inside(root, plan["archive_manifest_path"])
    if archive.exists() or receipt_path.exists():
        raise ValueError("Archive/receipt already exists; verify it, do not stack or overwrite backups")
    partial = archive.with_suffix(".zip.partial")
    unlinked(partial)
    entries, totals = {}, {}
    created = False
    try:
        with zipfile.ZipFile(partial, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            created = True
            for source in source_files(root, plan):
                name = source.relative_to(root).as_posix()
                if name in entries:
                    raise ValueError(f"Overlapping archive roots: {name}")
                before = source.stat()
                value = hashlib.sha256()
                with source.open("rb") as incoming, bundle.open(name, "w", force_zip64=True) as outgoing:
                    for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                        value.update(chunk)
                        outgoing.write(chunk)
                after = source.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError(f"Evidence changed during archive: {name}")
                entries[name] = dict(bytes=before.st_size, sha256=value.hexdigest())
                if bundle.fp.tell() > plan["archive_max_bytes"]:
                    raise ValueError("Archive exceeded its bounded storage budget")
            bundle.writestr(INDEX, json.dumps(entries, separators=(",", ":")))
        if partial.stat().st_size > plan["archive_max_bytes"]:
            raise ValueError("Archive exceeded its bounded storage budget")
        # Read every compressed member back and compare independent byte hashes.
        verify_members(partial, entries)
        for row in plan["archive_directories"]:
            totals[row["path"]] = sum(v["bytes"] for k, v in entries.items() if k.startswith(row["path"] + "/"))
        partial.rename(archive)
        result = dict(schema_version=1, owner=plan["owner"], archive_path=plan["archive_path"],
                      archive_sha256=digest(archive), archive_bytes=archive.stat().st_size,
                      original_bytes=sum(totals.values()), source_roots_bytes=totals,
                      archived_files=len(entries), verification="every_member_SHA256_and_ZIP_CRC_pass",
                      restore="Extract only needed members into managed scratch; index records original relative paths and hashes.",
                      lifecycle=plan["lifecycle"])
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if created and partial.exists():
            partial.unlink()  # only our newly created incomplete archive


def verify_members(archive: Path, entries: dict):
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist()) != {*entries, INDEX}:
            raise ValueError("Archive member set mismatch")
        for name, row in entries.items():
            value = hashlib.sha256()
            size = 0
            with bundle.open(name) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    value.update(chunk)
                    size += len(chunk)
            if size != row["bytes"] or value.hexdigest() != row["sha256"]:
                raise ValueError(f"Archive member hash mismatch: {name}")


def verify_before_cleanup(root: Path, plan: dict):
    root = root.resolve()
    archive = path_inside(root, plan["archive_path"])
    receipt = json.loads(path_inside(root, plan["archive_manifest_path"]).read_bytes())
    if receipt["archive_sha256"] != digest(archive):
        raise ValueError("Archive hash mismatch")
    with zipfile.ZipFile(archive) as bundle:
        entries = json.loads(bundle.read(INDEX))
    verify_members(archive, entries)
    current = set()
    for source in source_files(root, plan, allow_missing=True):
        name = source.relative_to(root).as_posix()
        current.add(name)
        if name not in entries or digest(source) != entries[name]["sha256"]:
            raise ValueError(f"Source changed since archive: {name}")
    present_roots = [r["path"] + "/" for r in plan["archive_directories"] if path_inside(root, r["path"]).exists()]
    expected = {name for name in entries if any(name.startswith(prefix) for prefix in present_roots)}
    if current != expected:
        raise ValueError("Source file set changed since archive")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    plan = json.loads(Path(__file__).with_name("optimizer_deep_cleanup.json").read_bytes())
    if args.verify:
        verify_before_cleanup(ROOT, plan)
        print("Archive and current original hashes verified; cleanup may proceed.")
    else:
        result = prepare_archive(ROOT, plan)
        print(json.dumps({k:v for k,v in result.items() if k != "source_roots_bytes"}))
