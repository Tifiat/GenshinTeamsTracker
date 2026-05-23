from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from .artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    init_db,
    list_artifact_set_bonus_descriptions,
    upsert_artifact_set_bonus_description,
)
from .paths import PROJECT_ROOT


HOYOWIKI_API_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"
HOYOWIKI_ENTRY_PAGE_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/entry_page"
ARTIFACT_SET_ICON_DIR = PROJECT_ROOT / "assets" / "artifact_sets"
SEED_CATALOG_PATH = PROJECT_ROOT / "data" / "static" / "artifact_set_catalog.json"

USER_AGENT = "GenshinTeamsTracker/1.0"
CANONICAL_LANGUAGE = "en-us"
SEED_CATALOG_SCHEMA_VERSION = 3

PIECE_ICON_FIELDS = {
    1: "flower_of_life_icon_url",
    2: "plume_of_death_icon_url",
    3: "sands_of_eon_icon_url",
    4: "goblet_of_eonothem_icon_url",
    5: "circlet_of_logos_icon_url",
}
BONUS_DESCRIPTION_FIELDS = {
    2: "two_set_effect",
    4: "four_set_effect",
}
ARTIFACT_POSITION_TO_POS = {
    "flower of life": 1,
    "plume of death": 2,
    "sands of eon": 3,
    "goblet of eonothem": 4,
    "circlet of logos": 5,
}
_APOSTROPHE_TRANSLATION = str.maketrans(
    {
        "'": "",
        "`": "",
        "\u00b4": "",
        "\u2018": "",
        "\u2019": "",
        "\u201a": "",
        "\u201b": "",
        "\u2032": "",
        "\uff07": "",
    }
)

_DASH_TRANSLATION = str.maketrans(
    {
        "-": " ",
        "\u2010": " ",
        "\u2011": " ",
        "\u2012": " ",
        "\u2013": " ",
        "\u2014": " ",
        "\u2212": " ",
        "\ufe58": " ",
        "\ufe63": " ",
        "\uff0d": " ",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve_project_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def normalize_language(language: str | None) -> str:
    value = str(language or "").strip().replace("_", "-").lower()
    if not value:
        return CANONICAL_LANGUAGE
    if value == "en":
        return CANONICAL_LANGUAGE
    return value


def normalize_set_name(name: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = text.casefold().strip()
    text = text.translate(_APOSTROPHE_TRANSLATION)
    text = text.translate(_DASH_TRANSLATION)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"_+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def set_uid_from_english_name(name: str) -> str:
    clean = name.replace("'", "").replace("\u2019", "")
    words = re.findall(r"[A-Za-z0-9]+", clean)
    return "".join(word[:1].upper() + word[1:] for word in words)


def local_icon_path(set_uid: str, pos: int) -> Path:
    return ARTIFACT_SET_ICON_DIR / f"{set_uid}_{pos}.png"


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    safe_path = quote(parts.path, safe="/")
    safe_query = quote(parts.query, safe="=&?/:,+%")
    return urlunsplit((parts.scheme, parts.netloc, safe_path, safe_query, parts.fragment))


def download_file(url: str, destination: Path, *, timeout: float = 20.0) -> None:
    request = urllib.request.Request(
        normalize_url(url),
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


def fetch_hoyowiki_artifact_sets(language: str = CANONICAL_LANGUAGE) -> list[dict[str, Any]]:
    language = normalize_language(language)
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

def fetch_hoyowiki_entry_page(
    entry_page_id: str,
    *,
    language: str = CANONICAL_LANGUAGE,
) -> dict[str, Any]:
    language = normalize_language(language)
    entry_page_id = str(entry_page_id or "").strip()
    if not entry_page_id:
        raise RuntimeError("empty HoYoWiki entry_page_id")

    url = f"{HOYOWIKI_ENTRY_PAGE_URL}?entry_page_id={quote(entry_page_id)}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://wiki.hoyolab.com",
            "x-rpc-language": language,
            "Accept": "application/json, text/plain, */*",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("retcode") != 0:
        raise RuntimeError(
            f"HoYoWiki entry_page retcode={payload.get('retcode')} "
            f"message={payload.get('message')}"
        )

    data = payload.get("data") or {}
    page = data.get("page") or {}
    if not isinstance(page, dict):
        raise RuntimeError(f"HoYoWiki entry_page has no page object: {entry_page_id}")

    return page


def _normalized_artifact_position(position: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(position or ""))
    text = text.casefold().strip()
    text = text.translate(_DASH_TRANSLATION)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _parse_component_json_data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if not isinstance(value, str) or not value.strip():
        return {}

    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def extract_piece_icons_from_entry_page(page: dict[str, Any]) -> dict[int, str]:
    """
    HoYoWiki detail page may have wrong artifact_list keys for some sets.
    Do NOT trust keys like sands_of_eon / plume_of_death here.
    Trust item["position"], because it is what the detail page displays.
    """
    modules = page.get("modules") or []
    if not isinstance(modules, list):
        return {}

    result: dict[int, str] = {}

    for module in modules:
        if not isinstance(module, dict):
            continue

        components = module.get("components") or []
        if not isinstance(components, list):
            continue

        for component in components:
            if not isinstance(component, dict):
                continue

            if component.get("component_id") != "artifact_list":
                continue

            data = _parse_component_json_data(component.get("data"))
            if not data:
                continue

            for piece in data.values():
                if not isinstance(piece, dict):
                    continue

                position = _normalized_artifact_position(piece.get("position"))
                pos = ARTIFACT_POSITION_TO_POS.get(position)
                icon_url = str(piece.get("icon_url") or "").strip()

                if not pos or not icon_url:
                    continue

                result[pos] = icon_url

    return result


def piece_icons_from_display_field(display_field: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}

    for pos, field_name in PIECE_ICON_FIELDS.items():
        icon_url = str(display_field.get(field_name) or "").strip()
        if icon_url:
            result[pos] = icon_url

    return result


def bonus_descriptions_from_display_field(display_field: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}

    for piece_count, field_name in BONUS_DESCRIPTION_FIELDS.items():
        description = str(display_field.get(field_name) or "").strip()
        if description:
            result[piece_count] = description

    return result


def _cached_piece_icon_url(conn, *, set_uid: str, pos: int) -> str:
    row = conn.execute(
        """
        SELECT icon_url
        FROM artifact_set_piece_icons
        WHERE set_uid = ?
            AND pos = ?
        """,
        (set_uid, pos),
    ).fetchone()

    return str(row["icon_url"] or "") if row else ""

def catalog_is_empty(conn) -> bool:
    row = conn.execute("SELECT COUNT(*) AS count FROM artifact_sets").fetchone()
    return int(row["count"] or 0) == 0


def _entry_page_id(item: dict[str, Any]) -> str:
    return str(item.get("entry_page_id") or "").strip()


def _entry_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or "").strip()


def _upsert_artifact_set_name(
    conn,
    *,
    set_uid: str,
    lang: str,
    name: str,
    now: str,
) -> bool:
    lang = normalize_language(lang)
    name = str(name or "").strip()
    normalized_name = normalize_set_name(name)
    if not set_uid or not lang or not name or not normalized_name:
        return False

    conn.execute(
        """
        INSERT INTO artifact_set_names (
            set_uid,
            lang,
            name,
            normalized_name,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(set_uid, lang) DO UPDATE SET
            name = excluded.name,
            normalized_name = excluded.normalized_name,
            updated_at = excluded.updated_at
        """,
        (set_uid, lang, name, normalized_name, now),
    )
    return True


def _upsert_artifact_set_bonus_descriptions(
    conn,
    *,
    set_uid: str,
    lang: str,
    descriptions: dict[int, str],
    now: str,
) -> int:
    count = 0

    for piece_count, description in sorted(descriptions.items()):
        if upsert_artifact_set_bonus_description(
            conn,
            set_uid=set_uid,
            lang=lang,
            piece_count=piece_count,
            description=description,
            source="hoyowiki",
            updated_at=now,
        ):
            count += 1

    return count


def _ensure_en_us_names_from_catalog(conn) -> int:
    now = utc_now()
    rows = conn.execute(
        """
        SELECT set_uid, fallback_name
        FROM artifact_sets
        WHERE fallback_name IS NOT NULL
            AND fallback_name != ''
            AND NOT EXISTS (
                SELECT 1
                FROM artifact_set_names
                WHERE artifact_set_names.set_uid = artifact_sets.set_uid
                    AND artifact_set_names.lang = ?
            )
        """,
        (CANONICAL_LANGUAGE,),
    ).fetchall()

    inserted = 0
    for row in rows:
        if _upsert_artifact_set_name(
            conn,
            set_uid=row["set_uid"],
            lang=CANONICAL_LANGUAGE,
            name=row["fallback_name"],
            now=now,
        ):
            inserted += 1

    return inserted


def _clear_legacy_entry_id_mappings(conn) -> int:
    rows = conn.execute(
        """
        SELECT set_uid
        FROM artifact_sets
        WHERE hoyolab_set_id IS NOT NULL
            AND CAST(hoyolab_set_id AS TEXT) = hoyowiki_entry_id
        """
    ).fetchall()
    if not rows:
        return 0

    conn.execute(
        """
        UPDATE artifact_sets
        SET hoyolab_set_id = NULL
        WHERE hoyolab_set_id IS NOT NULL
            AND CAST(hoyolab_set_id AS TEXT) = hoyowiki_entry_id
        """
    )
    return len(rows)


def update_artifact_set_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    language: str = CANONICAL_LANGUAGE,
    force_download: bool = False,
    missing_only: bool = False,
) -> dict[str, Any]:
    requested_language = normalize_language(language)
    summary: dict[str, Any] = {
        "language": CANONICAL_LANGUAGE,
        "requested_language": requested_language,
        "sets_seen": 0,
        "sets_existing": 0,
        "sets_missing": 0,
        "sets_skipped_existing": 0,
        "sets_upserted": 0,
        "names_upserted": 0,
        "bonus_descriptions_upserted": 0,
        "icons_seen": 0,
        "icons_downloaded": 0,
        "icons_already_cached": 0,
        "icons_failed": 0,
        "errors": [],
        "warnings": [],
    }
    if requested_language != CANONICAL_LANGUAGE:
        summary["warnings"].append(
            "Canonical artifact set catalog is always fetched from en-us; "
            f"localized names are handled by ensure_artifact_set_names({requested_language!r})."
        )

    items = fetch_hoyowiki_artifact_sets(language=CANONICAL_LANGUAGE)
    summary["sets_seen"] = len(items)

    now = utc_now()

    with connect_db(db_path) as conn:
        init_db(conn)
        existing_entry_ids = {
            str(row["hoyowiki_entry_id"] or "")
            for row in conn.execute(
                """
                SELECT hoyowiki_entry_id
                FROM artifact_sets
                WHERE hoyowiki_entry_id IS NOT NULL
                    AND hoyowiki_entry_id != ''
                """
            ).fetchall()
        }
        existing_set_uids = {
            str(row["set_uid"] or "")
            for row in conn.execute(
                """
                SELECT set_uid
                FROM artifact_sets
                WHERE set_uid IS NOT NULL
                    AND set_uid != ''
                """
            ).fetchall()
        }

        for item_index, item in enumerate(items, start=1):
            entry_id = _entry_page_id(item)
            fallback_name = _entry_name(item)

            if not entry_id or not fallback_name:
                continue

            set_uid = set_uid_from_english_name(fallback_name)
            if not set_uid:
                continue

            is_existing = entry_id in existing_entry_ids or set_uid in existing_set_uids
            if is_existing:
                summary["sets_existing"] += 1
            else:
                summary["sets_missing"] += 1

            if missing_only and is_existing and not force_download:
                summary["sets_skipped_existing"] += 1
                continue

            print(f"[{item_index}/{len(items)}] {set_uid}")

            display_field = item.get("display_field")
            if not isinstance(display_field, dict):
                display_field = {}
            try:
                detail_page = fetch_hoyowiki_entry_page(
                    entry_id,
                    language=CANONICAL_LANGUAGE,
                )
                piece_icons = extract_piece_icons_from_entry_page(detail_page)

                if not piece_icons:
                    summary["warnings"].append(
                        f"{set_uid}: detail artifact_list has no piece icons; "
                        "falling back to list display_field"
                    )
                    piece_icons = piece_icons_from_display_field(display_field)

            except (
                OSError,
                urllib.error.URLError,
                TimeoutError,
                RuntimeError,
                json.JSONDecodeError,
            ) as exc:
                summary["warnings"].append(
                    f"{set_uid}: could not fetch detail piece icons: {exc}; "
                    "falling back to list display_field"
                )
                piece_icons = piece_icons_from_display_field(display_field)

            conn.execute(
                """
                INSERT INTO artifact_sets (
                    set_uid,
                    hoyowiki_entry_id,
                    artiscan_set_key,
                    fallback_name,
                    source,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'hoyowiki', ?)
                ON CONFLICT(set_uid) DO UPDATE SET
                    hoyowiki_entry_id = excluded.hoyowiki_entry_id,
                    artiscan_set_key = COALESCE(artifact_sets.artiscan_set_key, excluded.artiscan_set_key),
                    fallback_name = excluded.fallback_name,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    set_uid,
                    entry_id,
                    set_uid,
                    fallback_name,
                    now,
                ),
            )
            summary["sets_upserted"] += 1

            if _upsert_artifact_set_name(
                conn,
                set_uid=set_uid,
                lang=CANONICAL_LANGUAGE,
                name=fallback_name,
                now=now,
            ):
                summary["names_upserted"] += 1

            summary["bonus_descriptions_upserted"] += (
                _upsert_artifact_set_bonus_descriptions(
                    conn,
                    set_uid=set_uid,
                    lang=CANONICAL_LANGUAGE,
                    descriptions=bonus_descriptions_from_display_field(display_field),
                    now=now,
                )
            )

            for pos, icon_url in sorted(piece_icons.items()):
                icon_url = str(icon_url or "").strip()
                if not icon_url:
                    continue

                summary["icons_seen"] += 1

                path = local_icon_path(set_uid, pos)
                local_path = project_relative(path)

                cached_icon_url = _cached_piece_icon_url(
                    conn,
                    set_uid=set_uid,
                    pos=pos,
                )
                should_download = (
                        force_download
                        or not path.exists()
                        or not path.is_file()
                        or cached_icon_url != icon_url
                )

                if not should_download:
                    summary["icons_already_cached"] += 1
                    print(f"  pos {pos}: cached")
                else:
                    try:
                        download_file(icon_url, path)
                        summary["icons_downloaded"] += 1
                        print(f"  pos {pos}: downloaded")
                    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                        summary["icons_failed"] += 1
                        print(f"  pos {pos}: failed: {exc}")
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

        _ensure_en_us_names_from_catalog(conn)
        backfill_artifact_set_uids(conn)
        conn.commit()

    conn.close()
    return summary


def export_seed_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    output_path: str | Path = SEED_CATALOG_PATH,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_db(db_path) as conn:
        init_db(conn)

        set_rows = conn.execute(
            """
            SELECT
                set_uid,
                hoyowiki_entry_id,
                artiscan_set_key,
                fallback_name,
                source,
                updated_at
            FROM artifact_sets
            ORDER BY fallback_name COLLATE NOCASE
            """
        ).fetchall()

        icon_rows = conn.execute(
            """
            SELECT
                set_uid,
                pos,
                icon_url,
                local_path,
                updated_at
            FROM artifact_set_piece_icons
            ORDER BY set_uid, pos
            """
        ).fetchall()

        name_rows = conn.execute(
            """
            SELECT
                set_uid,
                lang,
                name,
                normalized_name,
                updated_at
            FROM artifact_set_names
            ORDER BY set_uid, lang
            """
        ).fetchall()

        bonus_rows = list_artifact_set_bonus_descriptions(conn)

    icons_by_set: dict[str, list[dict[str, Any]]] = {}
    names_by_set: dict[str, list[dict[str, Any]]] = {}
    bonus_by_set: dict[str, list[dict[str, Any]]] = {}

    for row in icon_rows:
        icons_by_set.setdefault(row["set_uid"], []).append(
            {
                "pos": int(row["pos"]),
                "icon_url": row["icon_url"],
                "local_path": row["local_path"],
                "updated_at": row["updated_at"],
            }
        )

    for row in name_rows:
        names_by_set.setdefault(row["set_uid"], []).append(
            {
                "lang": row["lang"],
                "name": row["name"],
                "normalized_name": row["normalized_name"],
                "updated_at": row["updated_at"],
            }
        )

    for row in bonus_rows:
        set_uid = row["set_uid"]
        bonus_by_set.setdefault(set_uid, []).append(
            {
                "lang": row["lang"],
                "piece_count": int(row["piece_count"]),
                "description": row["description"],
                "source": row["source"],
                "updated_at": row["updated_at"],
            }
        )

    payload = {
        "schema_version": SEED_CATALOG_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "sets": [
            {
                "set_uid": row["set_uid"],
                "hoyowiki_entry_id": row["hoyowiki_entry_id"],
                "artiscan_set_key": row["artiscan_set_key"],
                "fallback_name": row["fallback_name"],
                "source": row["source"],
                "updated_at": row["updated_at"],
                "names": names_by_set.get(row["set_uid"], []),
                "icons": icons_by_set.get(row["set_uid"], []),
                "bonus_descriptions": bonus_by_set.get(row["set_uid"], []),
            }
            for row in set_rows
        ],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def seed_artifact_set_catalog_from_file(
    conn,
    *,
    seed_path: str | Path = SEED_CATALOG_PATH,
) -> dict[str, Any]:
    seed_path = Path(seed_path)

    if not seed_path.exists():
        return {"seeded": False, "reason": "seed file missing"}

    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    sets = payload.get("sets") or []

    now = utc_now()
    sets_inserted = 0
    icons_inserted = 0
    names_inserted = 0
    bonus_inserted = 0

    for item in sets:
        set_uid = item["set_uid"]

        conn.execute(
            """
            INSERT INTO artifact_sets (
                set_uid,
                hoyowiki_entry_id,
                artiscan_set_key,
                fallback_name,
                source,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_uid) DO UPDATE SET
                hoyowiki_entry_id = excluded.hoyowiki_entry_id,
                artiscan_set_key = COALESCE(artifact_sets.artiscan_set_key, excluded.artiscan_set_key),
                fallback_name = excluded.fallback_name,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                set_uid,
                item["hoyowiki_entry_id"],
                item.get("artiscan_set_key") or set_uid,
                item["fallback_name"],
                item.get("source") or "seed",
                now,
            ),
        )
        sets_inserted += 1

        if _upsert_artifact_set_name(
            conn,
            set_uid=set_uid,
            lang=CANONICAL_LANGUAGE,
            name=item["fallback_name"],
            now=now,
        ):
            names_inserted += 1

        for name_item in item.get("names") or []:
            if not isinstance(name_item, dict):
                continue
            if _upsert_artifact_set_name(
                conn,
                set_uid=set_uid,
                lang=name_item.get("lang") or CANONICAL_LANGUAGE,
                name=name_item.get("name") or "",
                now=now,
            ):
                names_inserted += 1

        for icon in item.get("icons") or []:
            local_path = icon["local_path"]

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
                (
                    set_uid,
                    int(icon["pos"]),
                    icon["icon_url"],
                    local_path,
                    now,
                ),
            )
            icons_inserted += 1

        for bonus in item.get("bonus_descriptions") or []:
            if not isinstance(bonus, dict):
                continue

            if upsert_artifact_set_bonus_description(
                conn,
                set_uid=set_uid,
                lang=bonus.get("lang") or CANONICAL_LANGUAGE,
                piece_count=bonus.get("piece_count"),
                description=bonus.get("description") or "",
                source=bonus.get("source") or "seed",
                updated_at=bonus.get("updated_at") or now,
            ):
                bonus_inserted += 1

    return {
        "seeded": True,
        "sets": sets_inserted,
        "icons": icons_inserted,
        "names": names_inserted,
        "bonus_descriptions": bonus_inserted,
    }


def ensure_artifact_set_catalog(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    allow_network: bool = False,
    missing_only: bool = False,
) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        init_db(conn)

        if catalog_is_empty(conn):
            seed_summary = seed_artifact_set_catalog_from_file(conn)
            en_us_names = _ensure_en_us_names_from_catalog(conn)
            backfill_artifact_set_uids(conn)
            conn.commit()

            if seed_summary.get("seeded"):
                conn.close()
                return {
                    "source": "seed",
                    "en_us_names_from_catalog": en_us_names,
                    **seed_summary,
                }

        en_us_names = _ensure_en_us_names_from_catalog(conn)
        backfill_artifact_set_uids(conn)
        conn.commit()

    conn.close()
    if allow_network:
        summary = update_artifact_set_catalog(
            db_path=db_path,
            missing_only=missing_only,
        )
        return {"source": "network", **summary}

    return {"source": "existing", "en_us_names_from_catalog": en_us_names}


def ensure_artifact_set_names(
    lang: str | None,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    allow_network: bool = True,
) -> dict[str, Any]:
    lang = normalize_language(lang)
    catalog_summary = ensure_artifact_set_catalog(db_path=db_path, allow_network=False)

    with connect_db(db_path) as conn:
        init_db(conn)
        en_us_names = _ensure_en_us_names_from_catalog(conn)
        existing_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM artifact_set_names
            WHERE lang = ?
            """,
            (lang,),
        ).fetchone()
        existing_count = int(existing_row["count"] or 0)
        conn.commit()

    if lang == CANONICAL_LANGUAGE:
        return {
            "lang": lang,
            "source": "catalog",
            "existing": existing_count,
            "updated": en_us_names,
            "catalog": catalog_summary,
        }

    if not allow_network:
        return {
            "lang": lang,
            "source": "existing",
            "existing": existing_count,
            "updated": 0,
            "catalog": catalog_summary,
        }

    try:
        items = fetch_hoyowiki_artifact_sets(language=lang)
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        return {
            "lang": lang,
            "source": "fallback",
            "fallback_lang": CANONICAL_LANGUAGE,
            "existing": existing_count,
            "updated": 0,
            "error": str(exc),
            "catalog": catalog_summary,
        }

    now = utc_now()
    matched = 0
    skipped = 0

    with connect_db(db_path) as conn:
        init_db(conn)
        entry_rows = conn.execute(
            """
            SELECT set_uid, hoyowiki_entry_id
            FROM artifact_sets
            """
        ).fetchall()
        set_uid_by_entry_id = {
            str(row["hoyowiki_entry_id"]): row["set_uid"]
            for row in entry_rows
        }

        for item in items:
            entry_id = _entry_page_id(item)
            name = _entry_name(item)
            set_uid = set_uid_by_entry_id.get(entry_id)
            if not set_uid or not name:
                skipped += 1
                continue

            if _upsert_artifact_set_name(
                conn,
                set_uid=set_uid,
                lang=lang,
                name=name,
                now=now,
            ):
                matched += 1

        conn.commit()

    return {
        "lang": lang,
        "source": "hoyowiki",
        "existing": existing_count,
        "updated": matched,
        "skipped": skipped,
        "catalog": catalog_summary,
    }


def _ensure_artifact_set_bonus_descriptions_for_language(
    lang: str,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    allow_network: bool = True,
) -> dict[str, Any]:
    lang = normalize_language(lang)
    catalog_summary = ensure_artifact_set_catalog(db_path=db_path, allow_network=False)

    with connect_db(db_path) as conn:
        init_db(conn)
        existing_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM artifact_set_bonus_descriptions
            WHERE lang = ?
            """,
            (lang,),
        ).fetchone()
        existing_count = int(existing_row["count"] or 0)
        conn.commit()

    if not allow_network:
        return {
            "lang": lang,
            "source": "existing",
            "existing": existing_count,
            "updated": 0,
            "catalog": catalog_summary,
        }

    try:
        items = fetch_hoyowiki_artifact_sets(language=lang)
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        return {
            "lang": lang,
            "source": "fallback",
            "existing": existing_count,
            "updated": 0,
            "error": str(exc),
            "catalog": catalog_summary,
        }

    now = utc_now()
    updated = 0
    skipped = 0

    with connect_db(db_path) as conn:
        init_db(conn)
        entry_rows = conn.execute(
            """
            SELECT set_uid, hoyowiki_entry_id
            FROM artifact_sets
            """
        ).fetchall()
        set_uid_by_entry_id = {
            str(row["hoyowiki_entry_id"]): row["set_uid"]
            for row in entry_rows
        }

        for item in items:
            entry_id = _entry_page_id(item)
            set_uid = set_uid_by_entry_id.get(entry_id)
            if not set_uid:
                skipped += 1
                continue

            display_field = item.get("display_field")
            if not isinstance(display_field, dict):
                skipped += 1
                continue

            descriptions = bonus_descriptions_from_display_field(display_field)
            if not descriptions:
                skipped += 1
                continue

            updated += _upsert_artifact_set_bonus_descriptions(
                conn,
                set_uid=set_uid,
                lang=lang,
                descriptions=descriptions,
                now=now,
            )

        conn.commit()

    return {
        "lang": lang,
        "source": "hoyowiki",
        "existing": existing_count,
        "updated": updated,
        "skipped": skipped,
        "catalog": catalog_summary,
    }


def ensure_artifact_set_bonus_descriptions(
    lang: str | None,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    allow_network: bool = True,
    include_english: bool = True,
) -> dict[str, Any]:
    requested_lang = normalize_language(lang)
    languages: list[str] = []

    if include_english:
        languages.append(CANONICAL_LANGUAGE)
    if requested_lang not in languages:
        languages.append(requested_lang)

    results = {
        language: _ensure_artifact_set_bonus_descriptions_for_language(
            language,
            db_path=db_path,
            allow_network=allow_network,
        )
        for language in languages
    }

    return {
        "requested_lang": requested_lang,
        "languages": languages,
        "results": results,
    }


def backfill_artifact_set_uids(conn) -> None:
    conn.execute(
        """
        UPDATE artifacts
        SET set_uid = (
            SELECT artifact_sets.set_uid
            FROM artifact_sets
            WHERE artifact_sets.hoyolab_set_id = artifacts.set_id
        )
        WHERE set_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM artifact_sets
                WHERE artifact_sets.hoyolab_set_id = artifacts.set_id
            )
            AND (
                set_uid IS NULL
                OR set_uid != (
                    SELECT artifact_sets.set_uid
                    FROM artifact_sets
                    WHERE artifact_sets.hoyolab_set_id = artifacts.set_id
                )
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


def _unwrap_hoyolab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("json"), dict):
        return payload["json"]

    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("json"), dict):
        return response["json"]

    return payload


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _collect_relic_sets(payload: dict[str, Any]) -> dict[int, set[str]]:
    hoyolab_payload = _unwrap_hoyolab_payload(payload)
    data = hoyolab_payload.get("data") or {}
    characters = data.get("list") or []
    result: dict[int, set[str]] = {}

    if not isinstance(characters, list):
        return result

    for character in characters:
        if not isinstance(character, dict):
            continue

        relics = character.get("relics") or []
        if not isinstance(relics, list):
            continue

        for relic in relics:
            if not isinstance(relic, dict):
                continue

            relic_set = relic.get("set")
            if not isinstance(relic_set, dict):
                continue

            set_id = _to_int(relic_set.get("id"))
            if set_id is None:
                continue

            name = str(relic_set.get("name") or "").strip()
            result.setdefault(set_id, set())
            if name:
                result[set_id].add(name)

    return result


def _first_name(names: set[str] | None) -> str:
    if not names:
        return ""
    return sorted(names)[0]


def _known_hoyolab_set_ids(conn, set_ids: list[int]) -> set[int]:
    if not set_ids:
        return set()

    placeholders = ",".join("?" for _ in set_ids)
    rows = conn.execute(
        f"""
        SELECT hoyolab_set_id
        FROM artifact_sets
        WHERE hoyolab_set_id IN ({placeholders})
        """,
        set_ids,
    ).fetchall()
    return {int(row["hoyolab_set_id"]) for row in rows if row["hoyolab_set_id"] is not None}


def _load_en_name_index(conn) -> tuple[dict[str, str], set[str]]:
    rows = conn.execute(
        """
        SELECT set_uid, normalized_name
        FROM artifact_set_names
        WHERE lang = ?
        """,
        (CANONICAL_LANGUAGE,),
    ).fetchall()

    index: dict[str, str] = {}
    duplicates: set[str] = set()
    for row in rows:
        normalized_name = str(row["normalized_name"] or "")
        set_uid = str(row["set_uid"] or "")
        if not normalized_name or not set_uid:
            continue
        existing = index.get(normalized_name)
        if existing and existing != set_uid:
            duplicates.add(normalized_name)
            continue
        index[normalized_name] = set_uid

    for duplicate in duplicates:
        index.pop(duplicate, None)

    return index, duplicates


async def ensure_hoyolab_set_mapping(
    character_details: dict[str, Any],
    export_page,
    real_ids: list[int] | list[dict[str, Any]],
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    localized_sets = _collect_relic_sets(character_details)
    set_ids = sorted(localized_sets)
    summary: dict[str, Any] = {
        "sets_in_payload": len(set_ids),
        "already_known": 0,
        "unknown_before_en_pass": 0,
        "mapped": 0,
        "legacy_entry_id_mappings_cleared": 0,
        "en_names": {},
    }

    ensure_artifact_set_catalog(db_path=db_path, allow_network=False)
    ensure_artifact_set_names(CANONICAL_LANGUAGE, db_path=db_path, allow_network=False)

    with connect_db(db_path) as conn:
        init_db(conn)
        cleared = _clear_legacy_entry_id_mappings(conn)
        known = _known_hoyolab_set_ids(conn, set_ids)
        conn.commit()

    summary["legacy_entry_id_mappings_cleared"] = cleared
    unknown_ids = [set_id for set_id in set_ids if set_id not in known]
    summary["already_known"] = len(set_ids) - len(unknown_ids)
    summary["unknown_before_en_pass"] = len(unknown_ids)

    if not unknown_ids:
        return summary

    from .character_detail import fetch_character_details_batch

    english_details = await fetch_character_details_batch(
        export_page,
        real_ids,
        language=CANONICAL_LANGUAGE,
    )
    english_sets = _collect_relic_sets(english_details)

    with connect_db(db_path) as conn:
        init_db(conn)
        name_index, duplicate_names = _load_en_name_index(conn)
        now = utc_now()
        unmatched: list[dict[str, Any]] = []

        for set_id in unknown_ids:
            en_name = _first_name(english_sets.get(set_id))
            summary["en_names"][str(set_id)] = en_name
            normalized_name = normalize_set_name(en_name)
            set_uid = name_index.get(normalized_name)

            if not en_name or not normalized_name:
                unmatched.append(
                    {
                        "hoyolab_set_id": set_id,
                        "en_name": en_name,
                        "reason": "missing EN relic set name",
                    }
                )
                continue

            if normalized_name in duplicate_names:
                unmatched.append(
                    {
                        "hoyolab_set_id": set_id,
                        "en_name": en_name,
                        "normalized_name": normalized_name,
                        "reason": "duplicate EN catalog name",
                    }
                )
                continue

            if not set_uid:
                unmatched.append(
                    {
                        "hoyolab_set_id": set_id,
                        "en_name": en_name,
                        "normalized_name": normalized_name,
                        "reason": "EN name not found in canonical catalog",
                    }
                )
                continue

            conflict = conn.execute(
                """
                SELECT set_uid
                FROM artifact_sets
                WHERE hoyolab_set_id = ?
                    AND set_uid != ?
                """,
                (set_id, set_uid),
            ).fetchone()
            if conflict is not None:
                unmatched.append(
                    {
                        "hoyolab_set_id": set_id,
                        "en_name": en_name,
                        "set_uid": set_uid,
                        "conflicting_set_uid": conflict["set_uid"],
                        "reason": "hoyolab_set_id is already mapped to another set",
                    }
                )
                continue

            display_name = _first_name(localized_sets.get(set_id)) or en_name
            conn.execute(
                """
                UPDATE artifact_sets
                SET hoyolab_set_id = ?,
                    display_name = COALESCE(NULLIF(display_name, ''), ?),
                    updated_at = ?
                WHERE set_uid = ?
                """,
                (set_id, display_name, now, set_uid),
            )
            summary["mapped"] += 1

        backfill_artifact_set_uids(conn)
        known_after = _known_hoyolab_set_ids(conn, set_ids)
        conn.commit()

    remaining = [set_id for set_id in set_ids if set_id not in known_after]
    if remaining:
        details_by_id = {item["hoyolab_set_id"]: item for item in unmatched}
        missing_details = [
            details_by_id.get(
                set_id,
                {
                    "hoyolab_set_id": set_id,
                    "en_name": _first_name(english_sets.get(set_id)),
                    "reason": "not mapped",
                },
            )
            for set_id in remaining
        ]
        pretty = "; ".join(
            f"{item['hoyolab_set_id']}: {item.get('en_name') or '<missing>'} ({item.get('reason')})"
            for item in missing_details
        )
        raise RuntimeError(
            "Could not map HoYoLAB artifact set ids through EN HoYoLAB details and "
            f"canonical HoYoWiki names: {pretty}"
        )

    return summary


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
            "Artifact set mapping was not prepared: "
            f"hoyolab_set_id={hoyolab_set_id}, display_name={display_name!r}"
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
