from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .weapon_stats_catalog import (
    DEFAULT_HOYOWIKI_LANGUAGE,
    WeaponStatsCatalog,
    WeaponStatsEntry,
    normalize_hoyowiki_language,
    read_weapon_stats_cache,
    weapon_stats_cache_path_for_language,
)


VALUE_TYPE_FLAT = "flat"
VALUE_TYPE_PERCENT_POINTS = "percent_points"

ALL_ELEMENTAL_DMG_BONUS = "ALL_ELEMENTAL_DMG_BONUS"

STATIC_DISPLAY_STAT_KEYS = {
    "HP_FLAT",
    "HP_PERCENT",
    "ATK_FLAT",
    "ATK_PERCENT",
    "DEF_FLAT",
    "DEF_PERCENT",
    "ELEMENTAL_MASTERY",
    "ENERGY_RECHARGE",
    "CRIT_RATE",
    "CRIT_DMG",
    "PYRO_DMG_BONUS",
    "HYDRO_DMG_BONUS",
    "ELECTRO_DMG_BONUS",
    "CRYO_DMG_BONUS",
    "ANEMO_DMG_BONUS",
    "GEO_DMG_BONUS",
    "DENDRO_DMG_BONUS",
    "PHYSICAL_DMG_BONUS",
    ALL_ELEMENTAL_DMG_BONUS,
    "HEALING_BONUS",
}

_CONDITION_MARKERS = (
    " if ",
    " after ",
    " when ",
    " while ",
    " using ",
    " use ",
    " uses ",
    " used ",
    " within ",
    " stack",
    " duration",
    " lasts ",
    " for 6s",
    " for 5s",
    " for 12s",
    " triggered",
    " trigger",
    " off-field",
    " on-field",
    " party",
    " opponent",
    " reaction",
)

_UNSUPPORTED_DISPLAY_MARKERS = (
    "elemental skill dmg",
    "elemental burst dmg",
    "elemental skill crit rate",
    "elemental burst crit rate",
    "elemental skill crit dmg",
    "elemental burst crit dmg",
    "normal attack crit rate",
    "charged attack crit rate",
    "plunging attack crit rate",
    "normal attack crit dmg",
    "charged attack crit dmg",
    "plunging attack crit dmg",
    "elemental skill",
    "elemental burst",
    "res ",
    " res",
    "shield strength",
    "incoming healing",
)

_DURATION_PATTERN = re.compile(
    r"\b(?:for|within)\s+\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b",
    flags=re.IGNORECASE,
)

_STAT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (r"all elemental dmg bonus|elemental dmg bonus for all elements", ALL_ELEMENTAL_DMG_BONUS, VALUE_TYPE_PERCENT_POINTS),
    (r"pyro dmg bonus", "PYRO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"hydro dmg bonus", "HYDRO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"electro dmg bonus", "ELECTRO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"cryo dmg bonus", "CRYO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"anemo dmg bonus", "ANEMO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"geo dmg bonus", "GEO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"dendro dmg bonus", "DENDRO_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"physical dmg(?: bonus)?", "PHYSICAL_DMG_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"crit rate", "CRIT_RATE", VALUE_TYPE_PERCENT_POINTS),
    (r"crit dmg|crit damage", "CRIT_DMG", VALUE_TYPE_PERCENT_POINTS),
    (r"energy recharge", "ENERGY_RECHARGE", VALUE_TYPE_PERCENT_POINTS),
    (r"healing bonus|healing effectiveness|character healing effectiveness", "HEALING_BONUS", VALUE_TYPE_PERCENT_POINTS),
    (r"elemental mastery", "ELEMENTAL_MASTERY", VALUE_TYPE_FLAT),
    (r"(?:max )?hp", "HP_PERCENT", VALUE_TYPE_PERCENT_POINTS),
    (r"\batk\b(?!\s*(?:spd|dmg))|attack(?!\s*(?:spd|dmg))", "ATK_PERCENT", VALUE_TYPE_PERCENT_POINTS),
    (r"\bdef\b|defense", "DEF_PERCENT", VALUE_TYPE_PERCENT_POINTS),
)


@dataclass(frozen=True, slots=True)
class DisplayStatEffect:
    stat_key: str
    value: float
    value_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stat_key": self.stat_key,
            "value": self.value,
            "value_type": self.value_type,
        }


def init_display_stat_effect_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS artifact_set_display_stat_effects (
            set_uid TEXT NOT NULL,
            pieces_required INTEGER NOT NULL,
            stat_key TEXT NOT NULL,
            value REAL NOT NULL,
            value_type TEXT NOT NULL,
            updated_at TEXT,
            PRIMARY KEY (set_uid, pieces_required, stat_key),
            FOREIGN KEY (set_uid) REFERENCES artifact_sets(set_uid) ON DELETE CASCADE,
            CHECK (pieces_required IN (2, 4)),
            CHECK (value_type IN ('flat', 'percent_points'))
        );

        CREATE TABLE IF NOT EXISTS weapon_display_stat_effects (
            weapon_id INTEGER NOT NULL,
            refinement INTEGER NOT NULL,
            stat_key TEXT NOT NULL,
            value REAL NOT NULL,
            value_type TEXT NOT NULL,
            weapon_catalog_entry_page_id TEXT,
            updated_at TEXT,
            PRIMARY KEY (weapon_id, refinement, stat_key),
            CHECK (refinement BETWEEN 1 AND 5),
            CHECK (value_type IN ('flat', 'percent_points'))
        );

        CREATE TABLE IF NOT EXISTS display_stat_formula_effects_experimental (
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            refinement INTEGER,
            formula_key TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            apply_enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (source_kind, source_id, refinement, formula_key)
        );

        CREATE TABLE IF NOT EXISTS weapon_passive_tooltips (
            weapon_id INTEGER NOT NULL,
            lang TEXT NOT NULL,
            passive_name TEXT NOT NULL DEFAULT '',
            passive_text TEXT NOT NULL DEFAULT '',
            weapon_catalog_entry_page_id TEXT,
            updated_at TEXT,
            source TEXT NOT NULL DEFAULT 'hoyowiki_weapon_base_info',
            PRIMARY KEY (weapon_id, lang)
        );
        """
    )


def detect_static_display_stat_effects(text: str) -> tuple[DisplayStatEffect, ...]:
    source = _clean_text(text)
    if not source:
        return ()
    first_clause = _first_clause(source)
    lowered = f" {first_clause.casefold()} "
    if any(marker in lowered for marker in _CONDITION_MARKERS):
        return ()
    if _DURATION_PATTERN.search(first_clause):
        return ()
    if any(marker in lowered for marker in _UNSUPPORTED_DISPLAY_MARKERS):
        return ()

    values = _number_values(first_clause)
    if not values:
        return ()

    for pattern, stat_key, default_value_type in _STAT_PATTERNS:
        if not re.search(pattern, first_clause, flags=re.IGNORECASE):
            continue
        value_type = VALUE_TYPE_PERCENT_POINTS if "%" in first_clause else default_value_type
        resolved_key = stat_key
        if stat_key in {"HP_PERCENT", "ATK_PERCENT", "DEF_PERCENT"} and "%" not in first_clause:
            value_type = VALUE_TYPE_FLAT
        if stat_key == "HP_PERCENT" and value_type == VALUE_TYPE_FLAT:
            resolved_key = "HP_FLAT"
        elif stat_key == "ATK_PERCENT" and value_type == VALUE_TYPE_FLAT:
            resolved_key = "ATK_FLAT"
        elif stat_key == "DEF_PERCENT" and value_type == VALUE_TYPE_FLAT:
            resolved_key = "DEF_FLAT"
        if resolved_key not in STATIC_DISPLAY_STAT_KEYS:
            return ()
        return (DisplayStatEffect(resolved_key, values[0], value_type),)
    return ()


def detect_weapon_static_display_stat_effects(text: str) -> tuple[tuple[int, DisplayStatEffect], ...]:
    source = _clean_text(text)
    if not source:
        return ()
    first_clause = _first_clause(source)
    effects = detect_static_display_stat_effects(first_clause)
    if not effects:
        return ()
    numbers = _number_values(first_clause)
    if len(numbers) < 5:
        numbers = [effects[0].value] * 5
    return tuple(
        (
            refinement,
            DisplayStatEffect(
                effects[0].stat_key,
                numbers[refinement - 1],
                effects[0].value_type,
            ),
        )
        for refinement in range(1, 6)
    )


def upsert_artifact_set_display_stat_effects_for_description(
    conn: sqlite3.Connection,
    *,
    set_uid: str,
    pieces_required: int,
    description: str,
    updated_at: str | None = None,
) -> int:
    init_display_stat_effect_tables(conn)
    set_uid = str(set_uid or "").strip()
    try:
        pieces_required = int(pieces_required)
    except (TypeError, ValueError):
        return 0
    if not set_uid or pieces_required not in {2, 4}:
        return 0
    if pieces_required != 2:
        conn.execute(
            """
            DELETE FROM artifact_set_display_stat_effects
            WHERE set_uid = ? AND pieces_required = ?
            """,
            (set_uid, pieces_required),
        )
        return 0

    conn.execute(
        """
        DELETE FROM artifact_set_display_stat_effects
        WHERE set_uid = ? AND pieces_required = ?
        """,
        (set_uid, pieces_required),
    )
    effects = detect_static_display_stat_effects(description)
    for effect in effects:
        conn.execute(
            """
            INSERT INTO artifact_set_display_stat_effects (
                set_uid, pieces_required, stat_key, value, value_type, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_uid, pieces_required, stat_key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (
                set_uid,
                pieces_required,
                effect.stat_key,
                effect.value,
                effect.value_type,
                updated_at,
            ),
        )
    return len(effects)


def rebuild_artifact_set_display_stat_effects(
    conn: sqlite3.Connection,
    *,
    lang: str = "en-us",
) -> int:
    init_display_stat_effect_tables(conn)
    conn.execute("DELETE FROM artifact_set_display_stat_effects")
    rows = conn.execute(
        """
        SELECT set_uid, piece_count, description, updated_at
        FROM artifact_set_bonus_descriptions
        WHERE lang = ?
        """,
        (lang,),
    ).fetchall()
    total = 0
    for row in rows:
        total += upsert_artifact_set_display_stat_effects_for_description(
            conn,
            set_uid=row["set_uid"],
            pieces_required=row["piece_count"],
            description=row["description"],
            updated_at=row["updated_at"],
        )
    return total


def rebuild_weapon_display_stat_effects(
    conn: sqlite3.Connection,
    *,
    weapon_catalog: WeaponStatsCatalog | None = None,
    weapon_wiki: Mapping[str, Any] | None = None,
    updated_at: str | None = None,
) -> int:
    init_display_stat_effect_tables(conn)
    weapon_catalog = weapon_catalog or read_weapon_stats_cache()
    if weapon_catalog is None:
        return 0
    entry_to_weapon_id = weapon_entry_page_id_to_weapon_id_map(weapon_wiki or {})
    conn.execute("DELETE FROM weapon_display_stat_effects")
    total = 0
    for entry in weapon_catalog.entries:
        weapon_id = entry_to_weapon_id.get(str(entry.entry_page_id))
        if weapon_id is None:
            continue
        for passive in entry.reference_info.passive_fields:
            for text in passive.values:
                for refinement, effect in detect_weapon_static_display_stat_effects(text):
                    conn.execute(
                        """
                        INSERT INTO weapon_display_stat_effects (
                            weapon_id,
                            refinement,
                            stat_key,
                            value,
                            value_type,
                            weapon_catalog_entry_page_id,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(weapon_id, refinement, stat_key) DO UPDATE SET
                            value = excluded.value,
                            value_type = excluded.value_type,
                            weapon_catalog_entry_page_id = excluded.weapon_catalog_entry_page_id,
                            updated_at = excluded.updated_at
                        """,
                        (
                            weapon_id,
                            refinement,
                            effect.stat_key,
                            effect.value,
                            effect.value_type,
                            str(entry.entry_page_id),
                            updated_at,
                        ),
                    )
                    total += 1
    return total


def rebuild_weapon_passive_tooltips(
    conn: sqlite3.Connection,
    *,
    weapon_catalog: WeaponStatsCatalog | None = None,
    weapon_wiki: Mapping[str, Any] | None = None,
    language: str | None = None,
    updated_at: str | None = None,
) -> int:
    """Store localized weapon passive text for runtime tooltips.

    This is display/reference text only. It is intentionally separate from
    `weapon_display_stat_effects`, which stores only whitelisted static stat rows.
    """

    init_display_stat_effect_tables(conn)
    lang = normalize_hoyowiki_language(
        language or (weapon_catalog.lang if weapon_catalog is not None else None)
    )
    if weapon_catalog is None:
        weapon_catalog = read_weapon_stats_cache(weapon_stats_cache_path_for_language(lang))
    if weapon_catalog is None:
        return 0

    entry_to_weapon_id = weapon_entry_page_id_to_weapon_id_map(weapon_wiki or {})
    weapon_ids = sorted(set(entry_to_weapon_id.values()))
    if weapon_ids:
        placeholders = ",".join("?" for _ in weapon_ids)
        conn.execute(
            f"""
            DELETE FROM weapon_passive_tooltips
            WHERE lang = ? AND weapon_id IN ({placeholders})
            """,
            (lang, *weapon_ids),
        )

    total = 0
    now = updated_at or _utc_now()
    for entry in weapon_catalog.entries:
        weapon_id = entry_to_weapon_id.get(str(entry.entry_page_id))
        if weapon_id is None:
            continue
        passive = _passive_tooltip_from_entry(entry)
        if not passive:
            continue
        conn.execute(
            """
            INSERT INTO weapon_passive_tooltips (
                weapon_id,
                lang,
                passive_name,
                passive_text,
                weapon_catalog_entry_page_id,
                updated_at,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, 'hoyowiki_weapon_base_info')
            ON CONFLICT(weapon_id, lang) DO UPDATE SET
                passive_name = excluded.passive_name,
                passive_text = excluded.passive_text,
                weapon_catalog_entry_page_id = excluded.weapon_catalog_entry_page_id,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            (
                weapon_id,
                lang,
                passive["passive_name"],
                passive["passive_text"],
                str(entry.entry_page_id),
                now,
            ),
        )
        total += 1
    return total


def get_weapon_passive_tooltip(
    conn: sqlite3.Connection,
    *,
    weapon_id: int | str | None,
    language: str | None = None,
    fallback_language: str | None = DEFAULT_HOYOWIKI_LANGUAGE,
) -> dict[str, Any]:
    weapon_id_int = _optional_int(weapon_id)
    if weapon_id_int is None:
        return {}
    languages = _dedupe_text(
        [
            normalize_hoyowiki_language(language),
            normalize_hoyowiki_language(fallback_language),
        ]
    )
    for lang in languages:
        try:
            row = conn.execute(
                """
                SELECT
                    weapon_id,
                    lang,
                    passive_name,
                    passive_text,
                    weapon_catalog_entry_page_id,
                    source,
                    updated_at
                FROM weapon_passive_tooltips
                WHERE weapon_id = ? AND lang = ?
                """,
                (weapon_id_int, lang),
            ).fetchone()
        except sqlite3.OperationalError:
            return {}
        if row is None:
            continue
        passive_name = str(row["passive_name"] or "").strip()
        passive_text = str(row["passive_text"] or "").strip()
        if not passive_name and not passive_text:
            continue
        return {
            "weapon_id": row["weapon_id"],
            "language": row["lang"],
            "passive_name": passive_name,
            "passive_text": passive_text,
            "weapon_catalog_entry_page_id": row["weapon_catalog_entry_page_id"],
            "source": row["source"],
            "updated_at": row["updated_at"],
        }
    return {}


def weapon_entry_page_id_to_weapon_id_map(weapon_wiki: Mapping[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for weapon_id_raw, url_raw in weapon_wiki.items():
        try:
            weapon_id = int(weapon_id_raw)
        except (TypeError, ValueError):
            continue
        match = re.search(r"/entry/(\d+)", str(url_raw or ""))
        if match:
            result.setdefault(match.group(1), weapon_id)
    return result


def read_weapon_wiki_from_account_detail_cache(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    node = data.get("json") if isinstance(data, dict) else {}
    node = node.get("data") if isinstance(node, dict) else {}
    weapon_wiki = node.get("weapon_wiki") if isinstance(node, dict) else {}
    return dict(weapon_wiki) if isinstance(weapon_wiki, Mapping) else {}


def _passive_tooltip_from_entry(entry: WeaponStatsEntry) -> dict[str, str]:
    for field_item in entry.reference_info.passive_fields:
        passive_name = str(field_item.key or "").strip()
        passive_text = "\n".join(
            str(value or "").strip()
            for value in field_item.values
            if str(value or "").strip()
        )
        if passive_name or passive_text:
            return {
                "passive_name": passive_name,
                "passive_text": passive_text,
            }
    return {}


def list_artifact_set_display_stat_effects_for_active_sets(
    conn: sqlite3.Connection,
    active_sets: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for active in active_sets:
        set_uid = str(active.get("set_uid") or "").strip()
        piece_count = _optional_int(active.get("piece_count") or active.get("count"))
        if not set_uid or piece_count is None:
            continue
        rows = conn.execute(
            """
            SELECT
                effects.set_uid,
                effects.pieces_required,
                effects.stat_key,
                effects.value,
                effects.value_type,
                descriptions.description
            FROM artifact_set_display_stat_effects AS effects
            LEFT JOIN artifact_set_bonus_descriptions AS descriptions
                ON descriptions.set_uid = effects.set_uid
                AND descriptions.piece_count = effects.pieces_required
                AND descriptions.lang = 'en-us'
            WHERE effects.set_uid = ? AND effects.pieces_required <= ?
            ORDER BY effects.pieces_required, effects.stat_key
            """,
            (set_uid, int(piece_count)),
        ).fetchall()
        result.extend(dict(row) for row in rows)
    return result


def list_weapon_display_stat_effects(
    conn: sqlite3.Connection,
    *,
    weapon_id: int | str | None,
    refinement: int | str | None,
) -> list[dict[str, Any]]:
    weapon_id_int = _optional_int(weapon_id)
    refinement_int = _optional_int(refinement)
    if weapon_id_int is None or refinement_int is None:
        return []
    rows = conn.execute(
        """
        SELECT weapon_id, refinement, stat_key, value, value_type, weapon_catalog_entry_page_id
        FROM weapon_display_stat_effects
        WHERE weapon_id = ? AND refinement = ?
        ORDER BY stat_key
        """,
        (weapon_id_int, refinement_int),
    ).fetchall()
    return [dict(row) for row in rows]


def _first_clause(text: str) -> str:
    parts = re.split(r"(?<=[.])\s+", text, maxsplit=1)
    return parts[0].strip()


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(text or ""))
    text = text.replace("\xa0", " ")
    return " ".join(text.split())


def _number_values(text: str) -> list[float]:
    return [
        float(match.group(1))
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%?", text)
    ]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_text(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
