"""Manual and reusable cleanup for generated local GCSIM state."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil

from .engine_store import (
    DEFAULT_FAILED_ENGINE_KEEP_COUNT,
    DEFAULT_GCSIM_ENGINE_STORE_DIR,
    DEFAULT_SUCCESSFUL_ENGINE_KEEP_COUNT,
    GcsimEngineStore,
    PROJECT_ROOT,
)
from .optimizer_cache import (
    DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR,
    DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES,
    DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES,
    prune_gcsim_optimizer_cache,
)
from .runtime_probe import cleanup_go_build_cache


DEFAULT_GCSIM_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "runs"
DEFAULT_GCSIM_FARMING_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "farming-runs"
DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "optimizer-runs"
DEFAULT_RUN_DIR_KEEP_COUNT = 50
DEFAULT_RUN_DIR_MAX_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class GcsimRunDirPruneResult:
    status: str
    dry_run: bool
    root: str
    deleted_paths: tuple[str, ...] = ()
    deleted_bytes: int = 0
    kept_paths: tuple[str, ...] = ()
    kept_bytes: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "root": self.root,
            "deleted_paths": list(self.deleted_paths),
            "deleted_bytes": self.deleted_bytes,
            "kept_paths": list(self.kept_paths),
            "kept_bytes": self.kept_bytes,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimLocalCleanupReport:
    dry_run: bool
    engine_store: dict
    go_build_cache: dict
    run_dirs: dict
    farming_run_dirs: dict
    optimizer_run_dirs: dict
    optimizer_cache: dict

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "engine_store": self.engine_store,
            "go_build_cache": self.go_build_cache,
            "run_dirs": self.run_dirs,
            "farming_run_dirs": self.farming_run_dirs,
            "optimizer_run_dirs": self.optimizer_run_dirs,
            "optimizer_cache": self.optimizer_cache,
        }


def cleanup_gcsim_local_state(
    *,
    dry_run: bool = True,
    store_dir: str | Path | None = None,
    keep_successful_engines: int = DEFAULT_SUCCESSFUL_ENGINE_KEEP_COUNT,
    keep_failed_engines: int = DEFAULT_FAILED_ENGINE_KEEP_COUNT,
    clean_go_cache: bool = True,
    go_work_dir: str | Path | None = None,
    run_root: str | Path | None = None,
    keep_run_dirs: int = DEFAULT_RUN_DIR_KEEP_COUNT,
    max_run_dir_bytes: int = DEFAULT_RUN_DIR_MAX_BYTES,
    farming_run_root: str | Path | None = None,
    keep_farming_run_dirs: int = DEFAULT_RUN_DIR_KEEP_COUNT,
    max_farming_run_dir_bytes: int = DEFAULT_RUN_DIR_MAX_BYTES,
    optimizer_run_root: str | Path | None = None,
    keep_optimizer_run_dirs: int = DEFAULT_RUN_DIR_KEEP_COUNT,
    max_optimizer_run_dir_bytes: int = DEFAULT_RUN_DIR_MAX_BYTES,
    optimizer_cache_root: str | Path | None = None,
    keep_optimizer_cache_entries: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES,
    max_optimizer_cache_bytes: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES,
) -> GcsimLocalCleanupReport:
    store = GcsimEngineStore(store_dir or DEFAULT_GCSIM_ENGINE_STORE_DIR)
    try:
        engine_result = store.prune_generated_state(
            keep_successful=keep_successful_engines,
            keep_failed=keep_failed_engines,
            dry_run=dry_run,
        ).to_dict()
        engine_result["status"] = "dry_run" if dry_run else "pruned"
    except Exception as exc:  # noqa: BLE001 - cleanup command should report all sections.
        engine_result = {
            "status": "failed",
            "dry_run": dry_run,
            "deleted_paths": [],
            "deleted_bytes": 0,
            "error": str(exc),
        }

    go_result = (
        cleanup_go_build_cache(go_work_dir=go_work_dir, dry_run=dry_run).to_dict()
        if clean_go_cache
        else {
            "status": "skipped",
            "path": str((Path(go_work_dir) if go_work_dir else PROJECT_ROOT / ".go") / "build-cache"),
            "deleted_bytes": 0,
            "dry_run": dry_run,
            "error": "",
        }
    )
    run_result = prune_gcsim_run_dirs(
        run_root=run_root,
        keep_count=keep_run_dirs,
        max_total_bytes=max_run_dir_bytes,
        dry_run=dry_run,
    ).to_dict()
    farming_run_result = prune_gcsim_run_dirs(
        run_root=farming_run_root or DEFAULT_GCSIM_FARMING_RUNS_DIR,
        keep_count=keep_farming_run_dirs,
        max_total_bytes=max_farming_run_dir_bytes,
        dry_run=dry_run,
    ).to_dict()
    optimizer_run_result = prune_gcsim_run_dirs(
        run_root=optimizer_run_root or DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR,
        keep_count=keep_optimizer_run_dirs,
        max_total_bytes=max_optimizer_run_dir_bytes,
        dry_run=dry_run,
    ).to_dict()
    optimizer_cache_result = prune_gcsim_optimizer_cache(
        cache_root=optimizer_cache_root or DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR,
        max_entries=keep_optimizer_cache_entries,
        max_total_bytes=max_optimizer_cache_bytes,
        dry_run=dry_run,
    ).to_dict()
    return GcsimLocalCleanupReport(
        dry_run=bool(dry_run),
        engine_store=engine_result,
        go_build_cache=go_result,
        run_dirs=run_result,
        farming_run_dirs=farming_run_result,
        optimizer_run_dirs=optimizer_run_result,
        optimizer_cache=optimizer_cache_result,
    )


def prune_gcsim_run_dirs(
    *,
    run_root: str | Path | None = None,
    keep_count: int = DEFAULT_RUN_DIR_KEEP_COUNT,
    max_total_bytes: int = DEFAULT_RUN_DIR_MAX_BYTES,
    dry_run: bool = False,
) -> GcsimRunDirPruneResult:
    root = Path(run_root) if run_root is not None else DEFAULT_GCSIM_RUNS_DIR
    if not root.exists():
        return GcsimRunDirPruneResult(
            status="missing",
            dry_run=bool(dry_run),
            root=str(root),
        )
    if not root.is_dir():
        return GcsimRunDirPruneResult(
            status="invalid_path",
            dry_run=bool(dry_run),
            root=str(root),
            error="GCSIM run root exists but is not a directory.",
        )

    entries = [
        (path, _directory_size(path), _path_mtime(path))
        for path in root.iterdir()
        if path.is_dir()
    ]
    newest = sorted(entries, key=lambda item: item[2], reverse=True)
    keep_limit = max(0, int(keep_count))
    byte_limit = max(0, int(max_total_bytes))
    kept: list[tuple[Path, int]] = []
    deleted: list[tuple[Path, int]] = []
    kept_bytes = 0
    for path, size, _mtime in newest:
        within_count = len(kept) < keep_limit
        within_bytes = kept_bytes + size <= byte_limit if byte_limit else True
        if within_count and (within_bytes or not kept):
            kept.append((path, size))
            kept_bytes += size
        else:
            deleted.append((path, size))

    deleted_paths: list[str] = []
    deleted_bytes = 0
    for path, size in deleted:
        deleted_paths.append(str(path))
        deleted_bytes += size
        if not dry_run:
            _safe_remove_tree(path, root=root)

    return GcsimRunDirPruneResult(
        status="dry_run" if dry_run else "pruned",
        dry_run=bool(dry_run),
        root=str(root),
        deleted_paths=tuple(deleted_paths),
        deleted_bytes=deleted_bytes,
        kept_paths=tuple(str(path) for path, _size in kept),
        kept_bytes=kept_bytes,
    )


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_remove_tree(path: Path, *, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise RuntimeError(f"Refusing to remove path outside GCSIM run root: {path}")
    shutil.rmtree(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean generated local GCSIM engines, run dirs, and Go build cache."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete generated cleanup targets. Default is dry-run.",
    )
    parser.add_argument("--store-dir", default=None, help="Optional engine store root.")
    parser.add_argument(
        "--keep-successful-engines",
        type=int,
        default=DEFAULT_SUCCESSFUL_ENGINE_KEEP_COUNT,
        help="Successful generated engines to keep, including the active engine.",
    )
    parser.add_argument(
        "--keep-failed-engines",
        type=int,
        default=DEFAULT_FAILED_ENGINE_KEEP_COUNT,
        help="Failed generated engine folders to keep for diagnostics.",
    )
    parser.add_argument(
        "--keep-go-build-cache",
        action="store_true",
        help="Do not delete the project-local .go/build-cache.",
    )
    parser.add_argument("--go-work-dir", default=None, help="Optional Go work root.")
    parser.add_argument("--run-root", default=None, help="Optional GCSIM run root.")
    parser.add_argument(
        "--keep-run-dirs",
        type=int,
        default=DEFAULT_RUN_DIR_KEEP_COUNT,
        help="Recent GCSIM run dirs to keep.",
    )
    parser.add_argument(
        "--max-run-dir-mb",
        type=int,
        default=DEFAULT_RUN_DIR_MAX_BYTES // (1024 * 1024),
        help="Maximum kept GCSIM run-dir bytes, in MB.",
    )
    parser.add_argument(
        "--farming-run-root",
        default=None,
        help="Optional ordinary optimizer-screen run root.",
    )
    parser.add_argument(
        "--keep-farming-run-dirs",
        type=int,
        default=DEFAULT_RUN_DIR_KEEP_COUNT,
        help="Recent ordinary optimizer-screen diagnostic dirs to keep.",
    )
    parser.add_argument(
        "--max-farming-run-dir-mb",
        type=int,
        default=DEFAULT_RUN_DIR_MAX_BYTES // (1024 * 1024),
        help="Maximum kept ordinary optimizer-screen diagnostic bytes, in MB.",
    )
    parser.add_argument(
        "--optimizer-run-root",
        default=None,
        help="Optional two-stage optimizer run root.",
    )
    parser.add_argument(
        "--keep-optimizer-run-dirs",
        type=int,
        default=DEFAULT_RUN_DIR_KEEP_COUNT,
        help="Recent two-stage optimizer diagnostic dirs to keep.",
    )
    parser.add_argument(
        "--max-optimizer-run-dir-mb",
        type=int,
        default=DEFAULT_RUN_DIR_MAX_BYTES // (1024 * 1024),
        help="Maximum kept two-stage optimizer diagnostic bytes, in MB.",
    )
    parser.add_argument(
        "--optimizer-cache-root",
        default=None,
        help="Optional persistent optimizer cache root.",
    )
    parser.add_argument(
        "--keep-optimizer-cache-entries",
        type=int,
        default=DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES,
        help="Newest persistent optimizer cache entries to keep.",
    )
    parser.add_argument(
        "--max-optimizer-cache-mb",
        type=int,
        default=DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES // (1024 * 1024),
        help="Maximum persistent optimizer cache bytes, in MB.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = cleanup_gcsim_local_state(
        dry_run=not args.apply,
        store_dir=args.store_dir,
        keep_successful_engines=args.keep_successful_engines,
        keep_failed_engines=args.keep_failed_engines,
        clean_go_cache=not args.keep_go_build_cache,
        go_work_dir=args.go_work_dir,
        run_root=args.run_root,
        keep_run_dirs=args.keep_run_dirs,
        max_run_dir_bytes=int(args.max_run_dir_mb) * 1024 * 1024,
        farming_run_root=args.farming_run_root,
        keep_farming_run_dirs=args.keep_farming_run_dirs,
        max_farming_run_dir_bytes=int(args.max_farming_run_dir_mb) * 1024 * 1024,
        optimizer_run_root=args.optimizer_run_root,
        keep_optimizer_run_dirs=args.keep_optimizer_run_dirs,
        max_optimizer_run_dir_bytes=int(args.max_optimizer_run_dir_mb) * 1024 * 1024,
        optimizer_cache_root=args.optimizer_cache_root,
        keep_optimizer_cache_entries=args.keep_optimizer_cache_entries,
        max_optimizer_cache_bytes=int(args.max_optimizer_cache_mb) * 1024 * 1024,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_text(report))
    return 0


def _format_text(report: GcsimLocalCleanupReport) -> str:
    data = report.to_dict()
    engine = data["engine_store"]
    go_cache = data["go_build_cache"]
    runs = data["run_dirs"]
    farming_runs = data["farming_run_dirs"]
    optimizer_runs = data["optimizer_run_dirs"]
    optimizer_cache = data["optimizer_cache"]
    lines = [
        "GCSIM local cleanup",
        f"dry_run={str(report.dry_run).lower()}",
        (
            "engine_store="
            f"status={engine.get('status', '')} "
            f"deleted_bytes={engine.get('deleted_bytes', 0)} "
            f"deleted_count={len(engine.get('deleted_paths') or [])}"
        ),
        (
            "go_build_cache="
            f"status={go_cache.get('status', '')} "
            f"deleted_bytes={go_cache.get('deleted_bytes', 0)} "
            f"path={go_cache.get('path', '')}"
        ),
        (
            "run_dirs="
            f"status={runs.get('status', '')} "
            f"deleted_bytes={runs.get('deleted_bytes', 0)} "
            f"deleted_count={len(runs.get('deleted_paths') or [])} "
            f"kept_count={len(runs.get('kept_paths') or [])}"
        ),
        (
            "farming_run_dirs="
            f"status={farming_runs.get('status', '')} "
            f"deleted_bytes={farming_runs.get('deleted_bytes', 0)} "
            f"deleted_count={len(farming_runs.get('deleted_paths') or [])} "
            f"kept_count={len(farming_runs.get('kept_paths') or [])}"
        ),
        (
            "optimizer_run_dirs="
            f"status={optimizer_runs.get('status', '')} "
            f"deleted_bytes={optimizer_runs.get('deleted_bytes', 0)} "
            f"deleted_count={len(optimizer_runs.get('deleted_paths') or [])} "
            f"kept_count={len(optimizer_runs.get('kept_paths') or [])}"
        ),
        (
            "optimizer_cache="
            f"status={optimizer_cache.get('status', '')} "
            f"deleted_bytes={optimizer_cache.get('deleted_bytes', 0)} "
            f"deleted_count={len(optimizer_cache.get('deleted_paths') or [])} "
            f"kept_count={optimizer_cache.get('kept_count', 0)}"
        ),
    ]
    if engine.get("deleted_paths"):
        lines.append("engine_deleted=" + ", ".join(engine["deleted_paths"]))
    if runs.get("deleted_paths"):
        lines.append("run_dirs_deleted=" + ", ".join(runs["deleted_paths"]))
    if farming_runs.get("deleted_paths"):
        lines.append(
            "farming_run_dirs_deleted=" + ", ".join(farming_runs["deleted_paths"])
        )
    if optimizer_runs.get("deleted_paths"):
        lines.append(
            "optimizer_run_dirs_deleted=" + ", ".join(optimizer_runs["deleted_paths"])
        )
    if optimizer_cache.get("deleted_paths"):
        lines.append(
            "optimizer_cache_deleted=" + ", ".join(optimizer_cache["deleted_paths"])
        )
    for key, section in (
        ("engine_store_error", engine),
        ("go_build_cache_error", go_cache),
        ("run_dirs_error", runs),
        ("farming_run_dirs_error", farming_runs),
        ("optimizer_run_dirs_error", optimizer_runs),
        ("optimizer_cache_error", optimizer_cache),
    ):
        if section.get("error"):
            lines.append(f"{key}={section['error']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
