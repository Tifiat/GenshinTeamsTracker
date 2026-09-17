"""Per-record presentation assets, separate from immutable History bundles."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import tempfile

from run_workspace.app_settings import PROJECT_ROOT


ARTWORK_ROOT = PROJECT_ROOT / "data" / "history" / "presentation"


class HistoryArtworkStore:
    def __init__(self, root: str | Path = ARTWORK_ROOT):
        self.root = Path(root)

    def path(self, run, team_index: int) -> Path:
        if team_index not in (0, 1):
            raise ValueError("Invalid History team")
        # Both source path and identity scope decorations to this saved record.
        identity = f"{run.bundle_path.resolve()}\n{run.bundle_id}"
        key = sha256(identity.encode("utf-8")).hexdigest()
        return self.root / key / f"team-{team_index}.png"

    def paths(self, run) -> dict[int, Path]:
        return {t.team_index: path for t in run.teams
                if (path := self.path(run, t.team_index)).is_file()}

    def save(self, run, team_index: int, png: bytes) -> Path:
        path = self.path(run, team_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".art-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(png)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path

    def reset(self, run, team_index: int) -> None:
        self.path(run, team_index).unlink(missing_ok=True)
