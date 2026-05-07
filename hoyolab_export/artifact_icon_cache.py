from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_db import ARTIFACT_DB_PATH, connect_db, init_db
from .paths import PROJECT_ROOT


ARTIFACT_ICON_DIR = PROJECT_ROOT / "assets" / "hoyolab" / "artifacts"
USER_AGENT = "GenshinTeamsTracker/1.0"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _resolve_stored_path(local_path: str | None) -> Path | None:
    if not local_path:
        return None

    path = Path(local_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _safe_icon_filename(icon_id: int, icon_key: str | None) -> str:
    filename = (icon_key or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    filename = _SAFE_FILENAME_RE.sub("_", filename).strip("._")

    if not filename:
        filename = f"artifact_icon_{icon_id}.png"
    elif "." not in filename:
        filename = f"{filename}.png"

    return filename.lower()


def _download(url: str, destination: Path, *, timeout: float) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()

    if not data:
        raise RuntimeError("empty image response")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(destination)


def cache_artifact_icons(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    icon_dir: str | Path = ARTIFACT_ICON_DIR,
    timeout: float = 4.0,
    max_seconds: float = 20.0,
) -> dict[str, Any]:
    """Download public HoYoLAB artifact icons and persist local_path in SQLite.

    Icon download failures are collected in the returned summary and do not raise,
    because a temporary CDN/network problem should not break the whole HoYoLAB import.
    """

    icon_dir = Path(icon_dir)
    summary: dict[str, Any] = {
        "icons_total": 0,
        "already_cached": 0,
        "downloaded": 0,
        "updated_paths": 0,
        "skipped_due_to_budget": 0,
        "failed": 0,
        "errors": [],
    }

    started_at = time.monotonic()

    with connect_db(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                id,
                icon_key,
                icon_url,
                local_path
            FROM artifact_icons
            ORDER BY id
            """
        ).fetchall()

        summary["icons_total"] = len(rows)

        for row_index, row in enumerate(rows):
            if max_seconds > 0 and time.monotonic() - started_at >= max_seconds:
                summary["skipped_due_to_budget"] = len(rows) - row_index
                break

            icon_id = int(row["id"])
            icon_key = row["icon_key"] or ""
            icon_url = row["icon_url"] or ""
            stored_path = _resolve_stored_path(row["local_path"])
            target_path = icon_dir / _safe_icon_filename(icon_id, icon_key)
            target_local_path = _project_relative(target_path)

            if stored_path is not None and stored_path.exists() and stored_path.is_file():
                summary["already_cached"] += 1
                continue

            if target_path.exists() and target_path.is_file():
                conn.execute(
                    "UPDATE artifact_icons SET local_path = ?, updated_at = ? WHERE id = ?",
                    (target_local_path, datetime.now(timezone.utc).isoformat(timespec="seconds"), icon_id),
                )
                summary["already_cached"] += 1
                summary["updated_paths"] += 1
                continue

            if not icon_url:
                summary["failed"] += 1
                if len(summary["errors"]) < 5:
                    summary["errors"].append(
                        {"icon_id": icon_id, "icon_key": icon_key, "error": "missing icon_url"}
                    )
                continue

            try:
                _download(icon_url, target_path, timeout=timeout)
            except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                summary["failed"] += 1
                if len(summary["errors"]) < 5:
                    summary["errors"].append(
                        {"icon_id": icon_id, "icon_key": icon_key, "error": str(exc)}
                    )
                continue

            conn.execute(
                "UPDATE artifact_icons SET local_path = ?, updated_at = ? WHERE id = ?",
                (target_local_path, datetime.now(timezone.utc).isoformat(timespec="seconds"), icon_id),
            )
            summary["downloaded"] += 1
            summary["updated_paths"] += 1

        conn.commit()

    return summary
