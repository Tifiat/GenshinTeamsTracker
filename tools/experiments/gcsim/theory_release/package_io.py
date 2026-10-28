"""Exact Git-object assembly and owned scratch I/O for a frozen Theory package."""
from __future__ import annotations

from contextlib import contextmanager
import difflib
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
from typing import Iterator
from uuid import uuid4


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(path: str) -> PurePosixPath:
    if not isinstance(path, str) or not path or any(c in path for c in '\\:<>"|?*'):
        raise ValueError("invalid relative path")
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ValueError("control character in path")
    parts = path.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
    }
    if (PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive
            or any(p in ("", ".", "..") or p.endswith((".", " "))
                   or p.split(".")[0].upper() in reserved for p in parts)):
        raise ValueError("unsafe or noncanonical relative path")
    return PurePosixPath(path)


def _paths(paths: list[str]) -> list[str]:
    """Reject file/directory and case aliases before any destination writes."""
    seen: dict[str, tuple[str, bool]] = {}
    out = []
    for value in paths:
        relative = safe_relative(value)
        for count in range(1, len(relative.parts) + 1):
            name = "/".join(relative.parts[:count])
            is_file = count == len(relative.parts)
            prior = seen.get(name.casefold())
            if prior is not None and (prior != (name, is_file) or is_file):
                raise ValueError("duplicate, case-colliding or overlapping file path")
            seen[name.casefold()] = (name, is_file)
        out.append(str(relative))
    return out


def _linked(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _ordinary(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    if _linked(info) or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError(f"linked or nonordinary path: {path}")
    return info


def _root(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("an absolute canonical root is required")
    for current in (*reversed(path.parents), path):
        try:
            _ordinary(current, directory=True)
        except FileNotFoundError:
            pass
    return path


def _child(root: Path, relative: str) -> Path:
    root = _root(root)
    path = root.joinpath(*safe_relative(relative).parts)
    path.relative_to(root)
    _root(path.parent)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return path
    if _linked(info) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"linked or nonordinary destination: {path}")
    return path


def _mkdir(path: Path) -> None:
    path = _root(path)
    for current in (*reversed(path.parents), path):
        try:
            _ordinary(current, directory=True)
        except FileNotFoundError:
            try:
                current.mkdir()
            except FileExistsError:
                pass
        _ordinary(current, directory=True)


def _read(root: Path, relative: str) -> bytes:
    path = _child(root, relative)
    _ordinary(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        info = os.fstat(source.fileno())
        if _linked(info) or not stat.S_ISREG(info.st_mode):
            raise ValueError("nonordinary opened source")
        data = source.read()
    _ordinary(path, directory=False)
    return data


def _write_new(path: Path, data: bytes) -> None:
    _root(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o644), "wb") as target:
        target.write(data)


def _write_files(dest: Path, files: dict[str, bytes]) -> None:
    dest = _root(dest)
    _paths(list(files))
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("destination must be absent or empty")
    for path in files:
        _child(dest, path)
    _mkdir(dest)
    for relative, data in files.items():
        path = _child(dest, relative)
        _mkdir(path.parent)
        _child(dest, relative)
        _write_new(path, data)


def _lines(data: bytes) -> list[str]:
    value = data.decode("utf-8")
    if "\r" in value or "\x00" in value:
        raise ValueError("source must be LF UTF-8 text, not binary or CR text")
    parts = value.split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def make_patch(path: str, before: bytes, after: bytes) -> str:
    relative = str(safe_relative(path))
    old, new = _lines(before), _lines(after)
    if before == after:
        raise ValueError("patch must change the declared file")
    rows = difflib.unified_diff(old, new, fromfile=f"a/{relative}" if before else "/dev/null",
                                tofile=f"b/{relative}", lineterm="\n")
    return "".join(row if row.endswith("\n") else row + "\n\\ No newline at end of file\n" for row in rows)


_HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n")


def apply_file_patch(path: str, before: bytes, text: str) -> bytes:
    relative = str(safe_relative(path))
    old = _lines(before)
    if not isinstance(text, str) or not text.endswith("\n") or "\r" in text or "\x00" in text:
        raise ValueError("patch must be complete LF UTF-8 text")
    rows = [p + "\n" for p in text.split("\n")[:-1]]
    if len(rows) < 3 or rows[0] not in (f"--- a/{relative}\n", "--- /dev/null\n") or rows[1] != f"+++ b/{relative}\n":
        raise ValueError("patch headers must name only the declared file")
    if rows[0] == "--- /dev/null\n" and before:
        raise ValueError("create patch has a nonempty before image")
    out: list[str] = []
    cursor, index, previous_start = 0, 2, -1
    changed = False
    while index < len(rows):
        match = _HUNK.fullmatch(rows[index])
        if match is None:
            raise ValueError("missing or unsupported hunk header")
        a, ac, b, bc = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
        start, output_start = (a - 1 if ac else a), (b - 1 if bc else b)
        if start < cursor or start <= previous_start or start > len(old) or output_start < 0 or ac + bc == 0:
            raise ValueError("overlapping or invalid hunk range")
        out.extend(old[cursor:start])
        cursor = start
        if output_start != len(out):
            raise ValueError("incorrect new hunk position")
        previous_start = start
        index += 1
        used_old = used_new = 0
        while index < len(rows) and not rows[index].startswith("@@ "):
            row = rows[index]
            if row[0] not in " +-":
                raise ValueError("unsupported or extra patch content")
            prefix, value = row[0], row[1:]
            index += 1
            if index < len(rows) and rows[index] == "\\ No newline at end of file\n":
                value = value[:-1]
                index += 1
            if prefix in " -":
                if cursor >= len(old) or old[cursor] != value:
                    raise ValueError("patch context differs from the exact before image")
                cursor += 1
                used_old += 1
            if prefix in " +":
                out.append(value)
                used_new += 1
            changed = changed or prefix in "+-"
        if used_old != ac or used_new != bc:
            raise ValueError("truncated or incorrect hunk counts")
    out.extend(old[cursor:])
    if not changed or any(not row.endswith("\n") for row in out[:-1]):
        raise ValueError("empty change or nonfinal unterminated line")
    return "".join(out).encode("utf-8")


def _hex(value: object, sizes: tuple[int, ...]) -> str:
    if not isinstance(value, str) or len(value) not in sizes or re.fullmatch(r"[0-9a-f]+", value) is None:
        raise ValueError("invalid digest or Git object ID")
    return value


def _git(repo: Path, *args: str, input_data: bytes | None = None) -> bytes:
    _root(repo)
    try:
        return subprocess.run(["git", "--literal-pathspecs", "-C", str(repo), *args], check=True,
                              input=input_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Git object read failed: {args[0]}") from exc


def _base(repo: Path, base: str) -> None:
    _hex(base, (40, 64))
    if _git(repo, "cat-file", "-t", base).strip() != b"commit":
        raise ValueError("base_head must name an exact commit")


_TREE_RECORD = re.compile(rb"(100644|100755|120000|160000) (blob|commit) ([0-9a-f]{40}|[0-9a-f]{64})")
_BATCH_HEADER = re.compile(rb"([0-9a-f]{40}|[0-9a-f]{64}) blob (0|[1-9][0-9]*)")


def _parse_git_tree(data: bytes) -> dict[str, tuple[str, str, str]]:
    if data and not data.endswith(b"\0"):
        raise ValueError("truncated Git tree metadata")
    entries: dict[str, tuple[str, str, str]] = {}
    for row in data.split(b"\0")[:-1]:
        metadata, separator, name = row.partition(b"\t")
        match = _TREE_RECORD.fullmatch(metadata)
        if not separator or not name or match is None:
            raise ValueError("malformed Git tree metadata")
        mode, kind, blob = (part.decode("ascii") for part in match.groups())
        if kind != ("commit" if mode == "160000" else "blob"):
            raise ValueError("Git tree mode and object type differ")
        path = name.decode("utf-8")
        if path in entries:
            raise ValueError("duplicate Git tree path")
        entries[path] = (mode, kind, blob)
    return entries


def _git_tree(repo: Path, base: str) -> dict[str, tuple[str, str, str]]:
    _base(repo, base)
    entries = _parse_git_tree(_git(repo, "ls-tree", "-r", "-z", "--full-tree", base))
    if any(len(row[2]) != len(base) for row in entries.values()):
        raise ValueError("Git tree object ID format differs from the base")
    return entries


def _entry(entries: dict[str, tuple[str, str, str]], path: str) -> str | None:
    safe_relative(path)
    entry = entries.get(path)
    if entry is None:
        if any(name.startswith(path + "/") for name in entries):
            raise ValueError("declared Git path names a directory")
        return None
    mode, kind, blob = entry
    if mode != "100644" or kind != "blob":
        raise ValueError("only the exact declared ordinary Git file is allowed")
    return _hex(blob, (40, 64))


def _parse_blob_batch(blobs: list[str], response: bytes) -> dict[str, bytes]:
    if len(set(blobs)) != len(blobs):
        raise ValueError("duplicate batch object request")
    out: dict[str, bytes] = {}
    offset = 0
    for blob in blobs:
        _hex(blob, (40, 64))
        newline = response.find(b"\n", offset)
        if newline < 0:
            raise ValueError("missing Git batch header")
        match = _BATCH_HEADER.fullmatch(response[offset:newline])
        if match is None or match[1].decode("ascii") != blob:
            raise ValueError("Git batch object identity/type/header mismatch")
        start, end = newline + 1, newline + 1 + int(match[2])
        if end >= len(response) or response[end:end + 1] != b"\n":
            raise ValueError("truncated or incorrect Git batch object length")
        data = response[start:end]
        framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        if hashlib.new("sha1" if len(blob) == 40 else "sha256", framed).hexdigest() != blob:
            raise ValueError("Git blob bytes do not match the requested object ID")
        out[blob] = data
        offset = end + 1
    if offset != len(response):
        raise ValueError("extra or unrequested Git batch content")
    return out


def _base_files(repo: Path, base: str, paths: list[str], *,
                entries: dict[str, tuple[str, str, str]] | None = None) -> tuple[dict[str, bytes], dict[str, dict]]:
    paths = _paths(paths)
    if entries is None:
        entries = _git_tree(repo, base)
    selected: dict[str, str] = {}
    for path in paths:
        blob = _entry(entries, path)
        if blob is None:
            raise ValueError(f"missing declared Git base file: {path}")
        selected[path] = blob
    blobs = list(dict.fromkeys(selected.values()))
    objects = _parse_blob_batch(blobs, _git(repo, "cat-file", "--batch",
                               input_data=("\n".join(blobs) + "\n").encode("ascii"))) if blobs else {}
    files: dict[str, bytes] = {}
    records: dict[str, dict] = {}
    for path, blob in selected.items():
        data = objects[blob]
        files[path] = data
        records[path] = {"base_git_blob": blob, "base_sha256": sha_bytes(data), "base_bytes": len(data)}
    return files, records


def export_git_files(repo: Path, base: str, paths: list[str], dest: Path) -> dict[str, dict]:
    files, records = _base_files(repo, base, paths)
    _write_files(dest, files)
    return records


def materialize_from_manifest(repo: Path, manifest: dict, bundle: Path, dest: Path) -> dict[str, dict]:
    if not isinstance(manifest, dict) or not {"base_head", "base_files", "patches"} <= manifest.keys():
        raise ValueError("incomplete manifest")
    base_rows, patches = manifest["base_files"], manifest["patches"]
    if not isinstance(base_rows, list) or not isinstance(patches, list):
        raise ValueError("manifest lists are required")
    for rows, required in ((base_rows, {"path", "sha256", "git_blob"}),
                           (patches, {"path", "payload", "payload_sha256", "before_sha256", "after_sha256"})):
        if any(not isinstance(row, dict) or not required <= row.keys() for row in rows):
            raise ValueError("incomplete manifest file or patch entry")
    base_paths = _paths([row["path"] for row in base_rows])
    patch_paths = _paths([row["path"] for row in patches])
    _paths(list(dict.fromkeys(base_paths + patch_paths)))
    payloads = _paths([row["payload"] for row in patches])
    _bundle_inventory(bundle, payloads)
    entries = _git_tree(repo, manifest["base_head"])
    files, records = _base_files(repo, manifest["base_head"], base_paths, entries=entries)
    for row in base_rows:
        record = records[row["path"]]
        if record["base_git_blob"] != _hex(row["git_blob"], (40, 64)) or record["base_sha256"] != _hex(row["sha256"], (64,)):
            raise ValueError("Git base identity or digest mismatch")
    for patch in patches:
        path, payload = str(safe_relative(patch["path"])), str(safe_relative(patch["payload"]))
        if path not in files and _entry(entries, path) is not None:
            raise ValueError("patch modifies an omitted Git base file")
        before = files.get(path, b"")
        if sha_bytes(before) != _hex(patch["before_sha256"], (64,)):
            raise ValueError("patch before digest mismatch")
        try:
            data = _read(bundle, payload)
        except FileNotFoundError as exc:
            raise ValueError(f"missing frozen patch payload: {payload}") from exc
        if sha_bytes(data) != _hex(patch["payload_sha256"], (64,)):
            raise ValueError("frozen patch digest mismatch")
        after = apply_file_patch(path, before, data.decode("utf-8"))
        if sha_bytes(after) != _hex(patch["after_sha256"], (64,)):
            raise ValueError("patch after digest mismatch")
        files[path] = after
        records.setdefault(path, {"base_git_blob": None, "base_sha256": sha_bytes(b""), "base_bytes": 0})
    for path, data in files.items():
        records[path].update(after_sha256=sha_bytes(data), after_bytes=len(data))
    _write_files(dest, files)
    return records


def _tree(job: Path) -> tuple[list[Path], list[Path]]:
    files, directories, pending = [], [], [job]
    while pending:
        directory = pending.pop()
        directory.relative_to(job)
        _root(directory)
        _ordinary(directory, directory=True)
        directories.append(directory)
        with os.scandir(directory) as children:
            for child in children:
                path = Path(child.path)
                path.relative_to(job)
                info = child.stat(follow_symlinks=False)
                if _linked(info):
                    raise ValueError(f"linked scratch child: {path}")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    files.append(path)
                else:
                    raise ValueError(f"nonordinary scratch child: {path}")
    return files, directories


def _bundle_inventory(bundle: Path, payloads: list[str]) -> None:
    bundle = _root(bundle)
    try:
        files, directories = _tree(bundle)
    except FileNotFoundError as exc:
        raise ValueError("frozen bundle is missing") from exc
    actual_files = _paths([path.relative_to(bundle).as_posix() for path in files])
    expected_dirs = {"/".join(safe_relative(path).parts[:i]) for path in payloads
                     for i in range(1, len(safe_relative(path).parts))}
    actual_dirs = {path.relative_to(bundle).as_posix() for path in directories if path != bundle}
    if set(actual_files) != set(payloads) or actual_dirs != expected_dirs:
        raise ValueError("extra or omitted frozen bundle payload/directory")


@contextmanager
def managed_job(root: Path) -> Iterator[dict]:
    """Lease one job; removed_bytes counts its data files, excluding the lease."""
    root = _root(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("scratch leftovers block a new job")
    _mkdir(root)
    identity = uuid4().hex
    lease, job = root / ".theory-release.lease", root / f"job-{identity}"
    token = (identity + "\n").encode("ascii")
    _write_new(lease, token)
    record = {"path": job, "removed_bytes": 0, "cleaned": False}
    created = False
    try:
        if set(root.iterdir()) != {lease}:
            raise ValueError("scratch changed while acquiring the lease")
        job.mkdir()
        created = True
        _ordinary(job, directory=True)
        yield record
    finally:
        try:
            if _read(root, lease.name) != token:
                raise ValueError("scratch lease identity changed")
            if job.parent != root or job.name != f"job-{identity}":
                raise ValueError("scratch job escaped its absolute root")
            try:
                job.lstat()
            except FileNotFoundError:
                if created:
                    raise ValueError("scratch job disappeared; no outside cleanup is permitted")
            else:
                files, directories = _tree(job)
                for path in files:
                    _root(path.parent)
                    size = _ordinary(path, directory=False).st_size
                    path.unlink()
                    record["removed_bytes"] += size
                for directory in reversed(directories):
                    _root(directory)
                    _ordinary(directory, directory=True)
                    directory.rmdir()
            if _read(root, lease.name) != token:
                raise ValueError("scratch lease identity changed before release")
            lease.unlink()
            record["cleaned"] = True
        except BaseException as exc:
            record["cleanup_error"] = str(exc)
            raise
