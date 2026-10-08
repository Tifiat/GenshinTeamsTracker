"""Keep child processes launchable without relocating run inputs or outputs."""

from __future__ import annotations

import os
from pathlib import Path


WINDOWS_CURRENT_DIRECTORY_LIMIT = 260


def windows_current_directory_units(directory: str) -> int:
    """CreateProcess cwd includes UTF-16, a trailing separator and a NUL.

    See Microsoft SetCurrentDirectory: long-path file access does not remove
    the CreateProcessW current-directory restriction.
    """
    units = len(directory.encode("utf-16-le")) // 2 + 1
    return units if directory.endswith(("\\", "/")) else units + 1


def optimizer_process_workdir(directory: str | Path) -> str:
    """Use the closest launchable ancestor; all file arguments stay absolute.

    No global cwd change, temporary directory, file copy or registry setting.
    A missing requested cwd is an error, not a reason to use another folder.
    """
    path = Path(directory)
    if os.name != "nt":
        return str(path)
    path = path.absolute()
    if not path.is_dir():
        raise NotADirectoryError(f"Optimizer process directory is unavailable: {path}")
    candidate = path
    while True:
        if windows_current_directory_units(str(candidate)) <= WINDOWS_CURRENT_DIRECTORY_LIMIT:
            if candidate.is_dir():
                return str(candidate)
        if candidate.parent == candidate:
            raise OSError("No existing ancestor fits the Windows process-directory limit")
        candidate = candidate.parent
