"""Run disposable optimizer research with a bounded, automatically cleaned scope.

N0 storage repair, 2026-09-17; see DATA_RUNTIME_BOUNDARIES.md. Only this runner's
new job directory is disposable, never legacy scratch, saved results or engines.
Keep small receipts explicitly outside the job before exit. This is not a sandbox:
commands must put their generated outputs under {scratch}, and must not detach.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_workspace.gcsim.optimizer_run_retention import run_directory_lease

MANAGED_ROOT = ROOT / ".codex_tmp" / "managed-optimizer"


def assert_unlinked(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and
                getattr(item.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Linked scratch path: {item}")


def remove_owned_job(job: Path, root: Path) -> int:
    assert_unlinked(job)
    if job.parent != root or not job.name.startswith("job-"):
        raise ValueError("Refusing a non-job cleanup target")
    # Reject nested junctions before rmtree; no following outside content.
    pending, size = [job], 0
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ValueError(f"Linked scratch content: {entry.path}")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(entry.path)
                else:
                    size += info.st_size
    def writable_retry(operation, name, error):
        # Go module downloads can be read-only. Only newly owned job files here.
        os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
        operation(name)
    shutil.rmtree(job, onerror=writable_retry)
    return size


@contextmanager
def managed_scratch(root: Path = MANAGED_ROOT):
    root = Path(root).absolute()
    assert_unlinked(root)
    root.mkdir(parents=True, exist_ok=True)
    assert_unlinked(root / ".gtt-active.lock")
    # Root lease serializes creation and deletion. Never guess whether an orphan
    # child survived a force-killed parent: leftovers block the next allocation.
    with run_directory_lease(root):
        leftovers = list(root.glob("job-*"))
        if leftovers:
            raise RuntimeError(f"Unfinished scratch needs inspection before another run: {leftovers[0]}")
        job = Path(tempfile.mkdtemp(prefix="job-", dir=root))
        try:
            yield job
        finally:
            try:
                removed_bytes = remove_owned_job(job, root)
                print(f"Disposable output removed: {removed_bytes} bytes; job no longer exists.", flush=True)
            except (OSError, ValueError):
                warnings.warn(f"Scratch cleanup failed; next run is blocked: {job}", RuntimeWarning)
                raise


def run_experiment(command: list[str], *, timeout: float, root: Path = MANAGED_ROOT) -> int:
    if not command or timeout <= 0:
        raise ValueError("A command and positive timeout are required")
    with managed_scratch(root) as job:
        cache, temporary = job / "go-cache", job / "temp"
        cache.mkdir()
        temporary.mkdir()
        env = dict(os.environ, GTT_SCRATCH_DIR=str(job),
                   GTT_MANAGED_GO_CACHE=str(cache), GOCACHE=str(cache),
                   GOTMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
        args = [arg.replace("{scratch}", str(job)) for arg in command]
        print(f"Disposable optimizer workspace: {job}", flush=True)
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL)
        try:
            return process.wait(timeout=timeout)
        finally:
            if process.poll() is None:
                if sys.platform == "win32":
                    # Stop descendants before deleting their workspace; no shell.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.kill()
                process.wait(timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run_experiment(command, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
