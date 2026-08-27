"""Canonical byte identity for GCSIM source and prepared engine trees."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def directory_sha256(
    path: str | Path,
    *,
    excluded_relative_paths: Iterable[str] = (),
) -> str:
    """Hash relative POSIX paths and bytes in case-sensitive lexical order."""

    root = Path(path)
    excluded = frozenset(
        str(item).replace("\\", "/") for item in excluded_relative_paths
    )
    files = sorted(
        (
            item
            for item in root.rglob("*")
            if item.is_file()
            and item.relative_to(root).as_posix() not in excluded
        ),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for item in files:
        relative = item.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


__all__ = ["directory_sha256"]
