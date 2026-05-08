from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_db import ARTIFACT_DB_PATH, connect_db, init_db
from .paths import PROJECT_ROOT


HOYOWIKI_API_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"
ARTIFACT_SET_ICON_DIR = PROJECT_ROOT / "assets" / "artifact_sets"
USER_AGENT = "GenshinTeamsTracker/1.0"

PIECE_ICON_FIELDS = {
    1: "flower_of_life_icon_url",
    2: "plume_of_death_icon_url",
    3: "sands_of_eon_icon_url",
    4: "goblet_of_eonothem_icon_url",
    5: "circlet_of_logos_icon_url",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def set_uid_from_english_name(name: str) -> str:
    # Examples:
    #   "Obsidian Codex" -> ObsidianCodex
    #   "Gladiator's Finale" -> GladiatorsFinale
    #   "Ocean-Hued Clam" -> OceanHuedClam
    clean = name.replace("'", "").replace("’", "")
    words = re.findall(r"[A-Za-z0-9]+", clean)
    return "".join(word[:1].upper() + word[1:] for word in words)


def local_icon_path(set_uid: str, pos: int) -> Path:
    return ARTIFACT_SET_ICON_DIR / f"{set_uid}_{pos}.png"


def download_file(url: str, destination: Path, *, timeout: float = 20.0) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            "Referer": "https://wiki.hoyolab.com",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()

    if not data:
        raise RuntimeError("empty file response")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(destination)


def fetch_hoyowiki_artifact_sets(language: str = "en-us") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    page_num = 1
    page_size = 30

    while True:
        body = json.dumps(
            {
                "filters": [],
                "menu_id": "5",
                "page_num": page_num,
                "page_size": page_size,
                "use_es": True,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            HOYOWIKI_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Referer": "https://wiki.hoyolab.com",
                "x-rpc-language": language,
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("retcode") != 0:
            raise RuntimeError(
                f"HoYoWiki retcode={payload.get('retcode')} message={payload.get('message')}"
            )

        data = payload.get("data") or {}
        items = data.get("list") or []
        result.extend(items)

        total = int(data.get("total") or len(result))
        if len(result) >= total or not items:
            break

        page_num += 1

    return result


def update_artifact_set_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    language: str = "en-us",
    force_download: bool = False,
) -> dict[str, Any]:
    """Update local artifact set catalog and download all set piece icons.

    This is project knowledge, not account data. The artifact browser must use these
    local paths and must not download icons on UI open.
    """

    summary: dict[str, Any] = {
        "sets_seen": 0,
        "sets_upserted": 0,
        "icons_seen": 0,
        "icons_downloaded": 0,
        "icons_already_cached": 0,
        "icons_failed": 0,
        "errors": [],
    }

    items = fetch_hoyowiki_artifact_sets(language=language)
    summary["sets_seen"] = len(items)

    now = utc_now()

    with connect_db(db_path) as conn:
        init_db(conn)

        for item in items:
            entry_id = str(item.get("entry_page_id") or "").strip()
            fallback_name = str(item.get("name") or "").strip()

            if not entry_id or not fallback_name:
                continue

            set_uid = set_uid_from_english_name(fallback_name)
            if not set_uid:
                continue

            hoyolab_set_id: int | None
            try:
                hoyolab_set_id = int(entry_id)
            except ValueError:
                hoyolab_set_id = None

            display_field = item.get("display_field")
            if not isinstance(display_field, dict):
                display_field = {}

            conn.execute(
                """
                INSERT INTO artifact_sets (
                    set_uid,
                    hoyowiki_entry_id,
                    hoyolab_set_id,
                    artiscan_set_key,
                    display_name,
                    fallback_name,
                    source,
                    updated_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, 'hoyowiki', ?)
                ON CONFLICT(set_uid) DO UPDATE SET
                    hoyowiki_entry_id = excluded.hoyowiki_entry_id,
                    hoyolab_set_id = COALESCE(artifact_sets.hoyolab_set_id, excluded.hoyolab_set_id),
                    artiscan_set_key = COALESCE(artifact_sets.artiscan_set_key, excluded.artiscan_set_key),
                    fallback_name = excluded.fallback_name,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    set_uid,
                    entry_id,
                    hoyolab_set_id,
                    set_uid,
                    fallback_name,
                    now,
                ),
            )
            summary["sets_upserted"] += 1

            for pos, field_name in PIECE_ICON_FIELDS.items():
                icon_url = str(display_field.get(field_name) or "").strip()
                if not icon_url:
                    continue

                summary["icons_seen"] += 1
                path = local_icon_path(set_uid, pos)
                local_path = project_relative(path)

                if path.exists() and path.is_file() and not force_download:
                    summary["icons_already_cached"] += 1
                else:
                    try:
                        download_file(icon_url, path)
                        summary["icons_downloaded"] += 1
                    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                        summary["icons_failed"] += 1
                        if len(summary["errors"]) < 10:
                            summary["errors"].append(
                                {
                                    "set_uid": set_uid,
                                    "pos": pos,
                                    "error": str(exc),
                                }
                            )
                        continue

                conn.execute(
                    """
                    INSERT INTO artifact_set_piece_icons (
                        set_uid,
                        pos,
                        icon_url,
                        local_path,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(set_uid, pos) DO UPDATE SET
                        icon_url = excluded.icon_url,
                        local_path = excluded.local_path,
                        updated_at = excluded.updated_at
                    """,
                    (set_uid, pos, icon_url, local_path, now),
                )

        backfill_artifact_set_uids(conn)
        conn.commit()

    return summary


def backfill_artifact_set_uids(conn) -> None:
    """Link existing HoYoLAB artifacts to catalog by HoYoWiki/HoYoLAB set id."""

    conn.execute(
        """
        UPDATE artifacts
        SET set_uid = (
            SELECT artifact_sets.set_uid
            FROM artifact_sets
            WHERE artifact_sets.hoyolab_set_id = artifacts.set_id
        )
        WHERE set_uid IS NULL
            AND set_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM artifact_sets
                WHERE artifact_sets.hoyolab_set_id = artifacts.set_id
            )
        """
    )

    conn.execute(
        """
        UPDATE artifact_sets
        SET display_name = (
            SELECT artifacts.set_name
            FROM artifacts
            WHERE artifacts.set_uid = artifact_sets.set_uid
                AND artifacts.set_name IS NOT NULL
                AND artifacts.set_name != ''
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM artifacts
            WHERE artifacts.set_uid = artifact_sets.set_uid
                AND artifacts.set_name IS NOT NULL
                AND artifacts.set_name != ''
        )
        """
    )


def resolve_hoyolab_set_uid(
    conn,
    *,
    hoyolab_set_id: int | None,
    display_name: str | None,
) -> str:
    if hoyolab_set_id is None:
        raise RuntimeError("HoYoLAB relic set has no set_id")

    row = conn.execute(
        """
        SELECT set_uid
        FROM artifact_sets
        WHERE hoyolab_set_id = ?
        """,
        (hoyolab_set_id,),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Artifact set is missing from local HoYoWiki catalog: hoyolab_set_id={hoyolab_set_id}"
        )

    set_uid = str(row["set_uid"])

    if display_name:
        conn.execute(
            """
            UPDATE artifact_sets
            SET display_name = ?
            WHERE set_uid = ?
            """,
            (display_name, set_uid),
        )

    return set_uid


def should_refresh_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    max_age_hours: float = 168.0,
) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        return True

    with connect_db(db_path) as conn:
        init_db(conn)

        row = conn.execute(
            """
            SELECT MIN(updated_at) AS oldest_update, COUNT(*) AS count
            FROM artifact_sets
            """
        ).fetchone()

        if not row or int(row["count"] or 0) == 0:
            return True

        oldest = row["oldest_update"]
        if not oldest:
            return True

        try:
            oldest_dt = datetime.fromisoformat(str(oldest))
        except ValueError:
            return True

        age_seconds = time.time() - oldest_dt.timestamp()
        return age_seconds >= max_age_hours * 3600


def ensure_artifact_set_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    max_age_hours: float = 168.0,
) -> dict[str, Any]:
    if should_refresh_catalog(db_path=db_path, max_age_hours=max_age_hours):
        return update_artifact_set_catalog(db_path=db_path)

    with connect_db(db_path) as conn:
        init_db(conn)
        backfill_artifact_set_uids(conn)
        conn.commit()

    return {"skipped": True}