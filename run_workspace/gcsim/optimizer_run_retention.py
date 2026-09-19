"""Bounded Go-run diagnostics, never account data or engine installations.

The session holds an OS lease until all child processes have returned. Cleanup
recognizes only our leased or completed run directories, preserves active/pinned
runs, and retains the newest result even if that single run exceeds the budget.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import sys

from .cleanup import DEFAULT_RUN_DIR_KEEP_COUNT, DEFAULT_RUN_DIR_MAX_BYTES
from .engine_store import PROJECT_ROOT


DEFAULT_GO_RUN_ROOT = PROJECT_ROOT / "data" / "gcsim" / "optimizer-go-runs"
RUN_LEASE = ".gtt-active.lock"
RUN_PIN = ".gtt-retain"


def _is_link(path: Path) -> bool:
    if sys.platform == "win32":
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return path.is_symlink()


@contextmanager
def run_directory_lease(run_dir: Path):
    """Non-blocking OS lease; process death releases it without PID heuristics."""
    with (run_dir / RUN_LEASE).open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        acquire()
        try:
            yield
        finally:
            handle.seek(0)
            release()


def _tree_size(path: Path) -> int:
    total = 0
    for parent, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not _is_link(Path(parent) / d)]
        for name in files:
            item = Path(parent) / name
            if not _is_link(item):
                total += item.stat().st_size
    return total


def prune_go_optimizer_runs(
    root: str | Path = DEFAULT_GO_RUN_ROOT,
    *,
    keep_count: int = DEFAULT_RUN_DIR_KEEP_COUNT,
    max_bytes: int = DEFAULT_RUN_DIR_MAX_BYTES,
    protected_paths: tuple[Path, ...] = (),
    dry_run: bool = True,
) -> dict:
    """Inspect by default; apply only inside this exact non-linked run root.

    Unrecognized directories and filesystem errors fail closed. Pins are manual
    diagnostic exceptions; the report exposes their bytes rather than claiming
    the entire root fits the ordinary retention budget.
    """
    original = Path(root).absolute()
    resolved = original.resolve()
    if original != resolved or resolved == PROJECT_ROOT.resolve() or resolved.parent == resolved:
        raise ValueError("Unsafe optimizer run root")
    report = dict(status="missing", dry_run=dry_run, root=str(resolved),
                  deleted_paths=[], deleted_bytes=0, kept_paths=[], kept_bytes=0,
                  protected_paths=[], protected_bytes=0, skipped_paths=[], errors=[])
    if not resolved.exists():
        return report
    explicit = {Path(p).resolve() for p in protected_paths}
    entries = []
    for path in resolved.iterdir():
        if not path.is_dir():
            continue
        if _is_link(path) or path.resolve().parent != resolved:
            report["skipped_paths"].append(str(path))
            continue
        result_name = next(
            (
                marker
                for prefix, marker in (
                    ("selected-", "selected-result.json"),
                    ("all_sets-", "selected-result.json"),
                    ("theory-", "theory-result.json"),
                )
                if path.name.startswith(prefix)
            ),
            "",
        )
        recognized = bool(result_name) and (
            (path / result_name).is_file() or (path / RUN_LEASE).is_file()
        )
        if not recognized:
            report["skipped_paths"].append(str(path))
            continue
        try:
            size = _tree_size(path)
            entries.append((path.stat().st_mtime_ns, path, size))
        except OSError as exc:
            report["errors"].append(f"{path.name}: {exc}")
    report["status"] = "dry_run" if dry_run else "pruned"
    kept = 0
    retained_any = False
    for _, path, size in sorted(entries, reverse=True):
        try:
            # The lease is also consulted in dry-run mode, but never created for
            # legacy runs during preview. Completed legacy jobs have no lease.
            protected = path in explicit or (path / RUN_PIN).exists()
            if not protected and (path / RUN_LEASE).exists():
                try:
                    with run_directory_lease(path):
                        pass
                except OSError:
                    protected = True
            if protected:
                report["protected_paths"].append(str(path))
                report["protected_bytes"] += size
                retained_any = True
                continue
            fits = report["kept_bytes"] + report["protected_bytes"] + size <= max(0, max_bytes)
            if kept < max(0, keep_count) and (fits or not retained_any):
                report["kept_paths"].append(str(path))
                report["kept_bytes"] += size
                kept += 1
                retained_any = True
                continue
            if not dry_run:
                if _is_link(path) or path.resolve().parent != resolved:
                    raise ValueError("Optimizer run changed its deletion boundary")
                shutil.rmtree(path)
            report["deleted_paths"].append(str(path))
            report["deleted_bytes"] += size
        except (OSError, ValueError) as exc:
            report["errors"].append(f"{path.name}: {exc}")
    if report["errors"]:
        report["status"] = "partial_failure"
    report["over_budget_bytes"] = max(0, report["kept_bytes"] + report["protected_bytes"] - max_bytes)
    return report


def prune_go_optimizer_runs_best_effort(root: str | Path, run_dir: Path) -> dict:
    try:
        return prune_go_optimizer_runs(root, protected_paths=(run_dir,), dry_run=False)
    except Exception as exc:  # retention cannot replace success/cancel/error
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
