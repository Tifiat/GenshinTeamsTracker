"""Seed a registered linked worktree with the minimal existing offline runtime.

Run through tools/managed_optimizer_experiment.py so GTT_SCRATCH_DIR names an
owned disposable job. This command does not create a worktree or build engines.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import owned_job
from run_workspace.gcsim.tree_identity import directory_sha256


ENGINE_IDS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PROFILE_FILES = (
    "account_language.json", "account_characters.json", "account_weapons.json",
    "crop_manifest.json", "account_character_details.json",
)
ASSET_DIRS = (
    "assets/hoyolab/characters", "assets/hoyolab/weapons",
    "assets/hoyolab/shared", "assets/hoyolab/artifacts",
    "assets/characters", "assets/weapons", "assets/hd/characters",
    "assets/hd/weapons",
)
# Existing public cache defaults in hoyolab_export/{character_stats_catalog,
# character_region_catalog,character_trait_catalog,weapon_stats_catalog}.py.
PUBLIC_REFERENCE_FILES = (
    "data/cache/hoyowiki/character_stats_catalog.json",
    "data/cache/hoyowiki/character_region_catalog.json",
    "data/cache/hoyowiki/character_trait_catalog.json",
    "data/cache/hoyowiki/weapon_stats_catalog.json",
)
POINTER = Path("data/gcsim/engines/active_engine.json")
MANIFEST = "gtt_engine_manifest.json"
RECEIPT = Path(".codex_tmp/worker-runtime.json")


def _unlinked(path: Path) -> None:
    """Reject links and Windows reparse points, including existing ancestors."""
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and
                getattr(item.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Linked path: {item}")


def _plain_tree(path: Path) -> None:
    _unlinked(path)
    if path.is_dir():
        for parent, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                _unlinked(Path(parent) / name)


def _git_value(root: Path, option: str) -> Path:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", option],
                            text=True, capture_output=True, check=True)
    value = Path(result.stdout.strip())
    return (root / value).resolve() if not value.is_absolute() else value.resolve()


def _roots(source: Path, target: Path) -> tuple[Path, Path]:
    for path in (source, target):
        _unlinked(path)
        if not path.is_dir():
            raise ValueError(f"Missing worktree root: {path}")
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Source and target roots must be distinct and non-overlapping")
    if _git_value(source, "--show-toplevel") != source:
        raise ValueError("Source is not the exact Git worktree root")
    if _git_value(target, "--show-toplevel") != target:
        raise ValueError("Target is not the exact Git worktree root")
    if _git_value(source, "--git-common-dir") != _git_value(target, "--git-common-dir"):
        raise ValueError("Source and target are not linked worktrees of one repository")
    return source, target


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _engine_details(source: Path, engine_id: str) -> dict[str, str]:
    if not isinstance(engine_id, str) or not ENGINE_IDS.fullmatch(engine_id) or engine_id in (".", ".."):
        raise ValueError(f"Invalid engine ID: {engine_id!r}")
    root = source / "data/gcsim/engines/engines" / engine_id
    if not root.is_dir():
        raise ValueError(f"Missing engine: {engine_id}")
    _plain_tree(root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("engine_id") != engine_id:
        raise ValueError(f"Engine manifest identity mismatch: {engine_id}")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"Missing engine artifact metadata: {engine_id}")
    raw = metadata.get("artifact_relative_path") or metadata.get("artifact_path")
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"Missing engine artifact path: {engine_id}")
    relative = Path(raw)
    if relative.is_absolute() or relative.drive or ".." in relative.parts or relative == Path("."):
        raise ValueError(f"Unsafe engine artifact path: {engine_id}")
    artifact = root / relative
    _unlinked(artifact)
    if not artifact.is_file():
        raise ValueError(f"Missing engine artifact: {engine_id}")
    actual_artifact = _sha(artifact)
    actual_tree = directory_sha256(root, excluded_relative_paths=(MANIFEST,))
    if actual_artifact != str(metadata.get("artifact_sha256", "")).casefold():
        raise ValueError(f"Engine artifact hash mismatch: {engine_id}")
    if actual_tree != str(manifest.get("engine_tree_hash", "")).casefold():
        raise ValueError(f"Engine tree hash mismatch: {engine_id}")
    return {"id": engine_id, "artifact_relative_path": relative.as_posix(),
            "artifact_sha256": actual_artifact, "engine_tree_sha256": actual_tree,
            "full_tree_sha256": directory_sha256(root)}


def _backup_database(source: Path, destination: Path) -> None:
    _unlinked(source)
    for suffix in ("-wal", "-shm"):
        _unlinked(Path(str(source) + suffix))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # SQLite's read-only URI and backup API include committed WAL transactions.
    uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Database backup failed quick_check")


def _bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.is_dir() else path.stat().st_size


def _remove_new(path: Path, target: Path) -> None:
    if path == target or not path.is_relative_to(target):
        raise ValueError(f"Refusing cleanup outside target worktree: {path}")
    _plain_tree(path)
    if not path.resolve().is_relative_to(target.resolve()):
        raise ValueError(f"Refusing linked cleanup path: {path}")
    if path.is_dir():
        def writable_retry(operation, name, error):
            os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
            operation(name)
        shutil.rmtree(path, onerror=writable_retry)
    else:
        path.unlink()


def bootstrap(source_root: Path, target_root: Path) -> dict:
    job = owned_job()
    source, target = _roots(Path(source_root).absolute(), Path(target_root).absolute())
    pointer = source / POINTER
    _unlinked(pointer)
    state_bytes = pointer.read_bytes()
    state = json.loads(state_bytes)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("Invalid active engine pointer")
    active = state.get("active_engine_id")
    rollback = state.get("rollback_engine_id")
    if active is None:
        raise ValueError("No active engine")
    if rollback is not None and rollback == active:
        raise ValueError("Rollback engine equals active engine")
    engines = [_engine_details(source, item) for item in (active, rollback) if item is not None]

    # Each planned destination is either a fresh file or a fresh directory.
    dirs = [Path("data/gcsim/engines/engines") / item["id"] for item in engines]
    dirs += [Path(item) for item in ASSET_DIRS if (source / item).is_dir()]
    files = [POINTER, Path("native/gcsim_optimizer/gtt-optimizer.exe"), Path("data/artifacts.db")]
    files += [Path("data/hoyolab") / name for name in PROFILE_FILES
              if (source / "data/hoyolab" / name).is_file()]
    files += [Path(name) for name in PUBLIC_REFERENCE_FILES if (source / name).is_file()]
    files += [Path(name) for name in ("settings.json", "state.json") if (source / name).is_file()]
    files.append(RECEIPT)
    for relative in dirs + files:
        if relative != RECEIPT and not (source / relative).exists():
            raise ValueError(f"Missing runtime input: {relative}")
        _unlinked(target / relative)
        if (target / relative).exists():
            raise FileExistsError(f"Destination already exists: {target / relative}")
    for relative in dirs + files:
        if relative != RECEIPT and relative != Path("data/artifacts.db"):
            _plain_tree(source / relative)

    stage = Path(tempfile.mkdtemp(prefix="bootstrap-", dir=job))
    counters = {"engines": 0, "assets": 0, "files": 0, "database": 0}
    for relative in dirs:
        shutil.copytree(source / relative, stage / relative)
        counters["engines" if relative.parts[:4] == ("data", "gcsim", "engines", "engines") else "assets"] += _bytes(stage / relative)
    for relative in files:
        if relative in (RECEIPT, Path("data/artifacts.db")):
            continue
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
        counters["files"] += destination.stat().st_size
    _backup_database(source / "data/artifacts.db", stage / "data/artifacts.db")
    counters["database"] = (stage / "data/artifacts.db").stat().st_size

    if (stage / POINTER).read_bytes() != state_bytes or pointer.read_bytes() != state_bytes:
        raise ValueError("Active engine pointer changed during staging")
    for relative in dirs:
        _plain_tree(stage / relative)
        if directory_sha256(source / relative) != directory_sha256(stage / relative):
            raise ValueError(f"Runtime directory changed during staging: {relative}")
    for relative in files:
        if relative in (RECEIPT, Path("data/artifacts.db"), POINTER):
            continue
        _plain_tree(stage / relative)
        if _sha(source / relative) != _sha(stage / relative):
            raise ValueError(f"Runtime file changed during staging: {relative}")
    for item in engines:
        relative = Path("data/gcsim/engines/engines") / item["id"]
        if (directory_sha256(stage / relative) != item["full_tree_sha256"] or
                directory_sha256(source / relative) != item["full_tree_sha256"]):
            raise ValueError(f"Engine changed during staging: {item['id']}")
    consumer = Path("native/gcsim_optimizer/gtt-optimizer.exe")
    if _sha(source / consumer) != _sha(stage / consumer):
        raise ValueError("Native optimizer changed during staging")
    receipt = {"schema_version": 1, "source_root": str(source), "target_root": str(target),
               "python_interpreter": sys.executable, "active_engine_id": active,
               "rollback_engine_id": rollback, "engines": engines,
               "pointer_sha256": _sha(stage / POINTER), "consumer_sha256": _sha(stage / consumer),
               "database_sha256": _sha(stage / "data/artifacts.db"), "byte_counters": counters,
               "total_bytes": sum(counters.values())}
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(receipt_bytes) > 16 * 1024:
        raise ValueError("Runtime receipt exceeds 16 KiB")
    (stage / RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    (stage / RECEIPT).write_bytes(receipt_bytes)

    published: list[Path] = []
    made_parents: list[Path] = []
    try:
        for relative in dirs + files:
            destination = target / relative
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Destination appeared during staging: {destination}")
            missing = []
            parent = destination.parent
            while parent != target and not parent.exists():
                missing.append(parent)
                parent = parent.parent
            _unlinked(parent)
            for folder in reversed(missing):
                folder.mkdir()
                made_parents.append(folder)
            (stage / relative).rename(destination)
            published.append(destination)
    except BaseException:
        for path in reversed(published):
            _remove_new(path, target)
        for path in reversed(made_parents):
            if path == target or not path.is_relative_to(target):
                raise ValueError(f"Refusing cleanup outside target worktree: {path}")
            _plain_tree(path)
            path.rmdir()
        raise
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args()
    receipt = bootstrap(args.source_root, args.target_root)
    print(json.dumps({"receipt": str(Path(receipt["target_root"]) / RECEIPT),
                      "total_bytes": receipt["total_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
