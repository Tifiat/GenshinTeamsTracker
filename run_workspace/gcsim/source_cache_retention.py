"""Conservative retention for completed official GCSIM source downloads.

Only paired, recognizable archive/expanded source versions are owned here.
The default operation is a dry run; the official updater opts in to deletion
after it has acquired and protected its current version.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from .engine_store import GcsimEngineStore, MANIFEST_FILE_NAME, load_engine_manifest
from .source_acquisition import OfficialGcsimSourceAcquisition, _safe_name


DEFAULT_SOURCE_KEEP_COUNT = 2
DEFAULT_SOURCE_MAX_BYTES = 512 * 1024 * 1024
_REQUIRED_FILES = ("go.mod", "cmd/gcsim/main.go")
_REQUIRED_DIRS = ("pkg/simulator", "pkg/model")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class SourceCacheRetentionResult:
    status: str
    dry_run: bool
    deleted_paths: tuple[str, ...] = ()
    deleted_bytes: int = 0
    protected_paths: tuple[str, ...] = ()
    unowned_paths: tuple[str, ...] = ()
    retained_bytes: int = 0
    over_budget_bytes: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "deleted_paths": list(self.deleted_paths),
            "deleted_bytes": self.deleted_bytes,
            "protected_paths": list(self.protected_paths),
            "unowned_paths": list(self.unowned_paths),
            "retained_bytes": self.retained_bytes,
            "over_budget_bytes": self.over_budget_bytes,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class _Version:
    tag: str
    archive: Path
    expanded: Path
    size: int
    mtime: float


def retain_official_source_cache(
    *,
    acquisition: OfficialGcsimSourceAcquisition,
    store: GcsimEngineStore,
    dry_run: bool = True,
    keep_count: int = DEFAULT_SOURCE_KEEP_COUNT,
    max_bytes: int = DEFAULT_SOURCE_MAX_BYTES,
) -> SourceCacheRetentionResult:
    """Plan or prune old completed versions, preserving all known references.

    Any unrecognized entry, unsafe path, or unreadable reference aborts the
    whole plan before deletion. The acquisition establishes which cache the
    updater just wrote, including when an explicit cache root was requested.
    """

    try:
        if keep_count < 1 or max_bytes < 0:
            raise ValueError("Source retention limits must be nonnegative; keep_count >= 1")
        root = Path(acquisition.cache_dir).absolute()
        archives = root / "archives"
        expanded = root / "expanded"
        current_tag = _safe_name(acquisition.source_ref.tag)
        current_archive = archives / f"{current_tag}.zip"
        current_expanded = expanded / current_tag
        if (Path(acquisition.archive_path).absolute() != current_archive or
                Path(acquisition.source_dir).absolute() != current_expanded):
            raise ValueError("Acquired source is not in the official cache layout")
        for path in (root, archives, expanded, current_archive, current_expanded):
            _check_ancestors(path)
        if not root.is_dir() or not archives.is_dir() or not expanded.is_dir():
            raise ValueError("Official source cache layout is incomplete")
        # An extraction or temporary download may be in progress. Its owner is
        # not known to this retention pass, so leave the entire cache alone.
        extracting = root / "extracting"
        _check_ancestors(extracting)
        if extracting.exists() and any(extracting.iterdir()):
            raise ValueError("Source extraction is in progress or unrecognized")
        unexpected_roots = [p for p in root.iterdir() if p.name not in {"archives", "expanded", "extracting"}]
        if unexpected_roots:
            raise ValueError("Source cache contains unrecognized root entries")

        archive_entries = tuple(archives.iterdir())
        expanded_entries = tuple(expanded.iterdir())
        archive_by_tag = {}
        expanded_by_tag = {}
        for path in archive_entries:
            if path.suffix != ".zip" or _safe_name(path.stem) != path.stem or not path.is_file():
                raise ValueError(f"Unrecognized source archive entry: {path}")
            archive_by_tag[path.stem] = path
        for path in expanded_entries:
            if _safe_name(path.name) != path.name or not path.is_dir():
                raise ValueError(f"Unrecognized expanded source entry: {path}")
            expanded_by_tag[path.name] = path
        if set(archive_by_tag) != set(expanded_by_tag):
            raise ValueError("Unpaired source archive or expanded tree")
        if current_tag not in archive_by_tag:
            raise ValueError("Current acquired source is not a completed cache version")

        versions = []
        for tag in sorted(archive_by_tag):
            archive = archive_by_tag[tag]
            tree = expanded_by_tag[tag]
            archive_size = _checked_tree_size(archive)
            tree_size = _checked_tree_size(tree)
            _check_source_tree(tree)
            _check_source_archive(archive)
            versions.append(_Version(tag, archive, tree, archive_size + tree_size,
                                     max(archive.stat().st_mtime, tree.stat().st_mtime)))

        referenced = _referenced_source_paths(store)
        protected = {current_tag}
        for version in versions:
            if (version.archive.resolve() in referenced or
                    version.expanded.resolve() in referenced):
                protected.add(version.tag)
        ordered = sorted(versions, key=lambda item: (item.mtime, item.tag), reverse=True)
        kept = set(protected)
        for version in ordered:
            if len(kept) >= keep_count:
                break
            kept.add(version.tag)
        # Preserve the newest complete version even if it alone exceeds the
        # byte budget; older unprotected versions can still be reclaimed.
        newest_tag = ordered[0].tag
        kept.add(newest_tag)
        total = sum(version.size for version in versions if version.tag in kept)
        for version in reversed(ordered):
            if total <= max_bytes:
                break
            if version.tag in protected or version.tag == newest_tag:
                continue
            if version.tag in kept:
                kept.remove(version.tag)
                total -= version.size
        victims = [version for version in versions if version.tag not in kept]
        target_paths = tuple(path for version in victims for path in (version.archive, version.expanded))
        # Complete the full preflight before the first remove. Repeat path
        # safety checks immediately before each delete to narrow race exposure.
        for path in target_paths:
            _check_ancestors(path)
            _checked_tree_size(path)
        planned_bytes = sum(version.size for version in victims)
        if not dry_run:
            completed: list[str] = []
            completed_bytes = 0
            for path in target_paths:
                try:
                    _check_ancestors(path)
                    path_bytes = _checked_tree_size(path)
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                except (OSError, ValueError) as exc:
                    return SourceCacheRetentionResult(
                        status="failed", dry_run=False,
                        deleted_paths=tuple(completed), deleted_bytes=completed_bytes,
                        protected_paths=tuple(str(p) for version in versions
                                              if version.tag in protected
                                              for p in (version.archive, version.expanded)),
                        error=str(exc),
                    )
                completed.append(str(path))
                completed_bytes += path_bytes
        return SourceCacheRetentionResult(
            status="dry_run" if dry_run else "pruned",
            dry_run=dry_run,
            deleted_paths=tuple(str(path) for path in target_paths),
            deleted_bytes=planned_bytes,
            protected_paths=tuple(str(path) for version in versions if version.tag in protected
                                  for path in (version.archive, version.expanded)),
            retained_bytes=total,
            over_budget_bytes=max(0, total - max_bytes),
        )
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        return SourceCacheRetentionResult(
            status="skipped_unsafe", dry_run=dry_run, error=str(exc),
            unowned_paths=(str(acquisition.cache_dir),),
        )


def _check_ancestors(path: Path) -> None:
    for item in (path, *path.parents):
        if not item.exists() and not item.is_symlink():
            continue
        info = item.lstat()
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise ValueError(f"Linked or reparse source cache path: {item}")


def _checked_tree_size(path: Path) -> int:
    _check_ancestors(path)
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        return info.st_size
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"Nonregular source cache entry: {path}")
    total = 0
    for item in path.iterdir():
        total += _checked_tree_size(item)
    return total


def _check_source_tree(path: Path) -> None:
    for relative in _REQUIRED_FILES:
        if not (path / relative).is_file():
            raise ValueError(f"Unrecognized source tree: {path}")
    for relative in _REQUIRED_DIRS:
        if not (path / relative).is_dir():
            raise ValueError(f"Unrecognized source tree: {path}")


def _check_source_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        roots = set()
        files = set()
        for member in members:
            pure = PurePosixPath(member.filename)
            if (pure.is_absolute() or ".." in pure.parts or "\\" in member.filename or
                    not pure.parts or pure.parts[0] in {"", "."} or
                    stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError(f"Unsafe source archive member: {member.filename}")
            roots.add(pure.parts[0])
            if not member.is_dir():
                files.add("/".join(pure.parts[1:]))
        if len(roots) != 1 or not set(_REQUIRED_FILES).issubset(files) or not all(
            any(name.startswith(f"{directory}/") for name in files)
            for directory in _REQUIRED_DIRS
        ):
            raise ValueError(f"Unrecognized source archive: {path}")


def _referenced_source_paths(store: GcsimEngineStore) -> set[Path]:
    referenced: set[Path] = set()
    _check_ancestors(store.root_dir.absolute())
    _check_ancestors(store.active_state_path.absolute())
    # Every retained success/diagnostic manifest matters, including inactive
    # engines. A live staging directory makes the reference set incomplete.
    for directory in (store.engines_dir, store.failed_dir, store.staging_dir):
        _check_ancestors(directory.absolute())
        if not directory.exists():
            continue
        if directory == store.staging_dir and any(directory.iterdir()):
            raise ValueError("Engine staging is live or unrecognized")
        for engine in directory.iterdir():
            _check_ancestors(engine.absolute())
            if not engine.is_dir():
                raise ValueError(f"Unrecognized engine entry: {engine}")
            manifest_path = engine / MANIFEST_FILE_NAME
            if not manifest_path.exists():
                if directory == store.engines_dir:
                    raise ValueError(f"Retained engine has no manifest: {engine}")
                continue  # Failed diagnostic copies may predate manifest creation.
            _check_ancestors(manifest_path.absolute())
            manifest = load_engine_manifest(engine)
            if not manifest.source_path or not Path(manifest.source_path).is_absolute():
                raise ValueError(f"Retained engine has malformed source path: {engine}")
            referenced.add(Path(manifest.source_path).resolve())
            archive = manifest.metadata.get("source_archive_path", "")
            if archive:
                if not Path(archive).is_absolute():
                    raise ValueError(f"Retained engine has malformed source archive path: {engine}")
                referenced.add(Path(archive).resolve())
    # Validate active/rollback state, including malformed or missing targets.
    for engine_id in (store.active_engine_id(), store.rollback_engine_id()):
        if engine_id and not (store.engines_dir / engine_id).is_dir():
            raise ValueError(f"Referenced engine is missing: {engine_id}")
    return referenced
