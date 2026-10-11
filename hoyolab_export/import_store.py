"""Durable, account-bound HoYoLAB snapshot publication.

The source snapshot is stored before publication so a failed core transaction
can be retried using the same attempt ID. Schema preparation is deliberately
separate from the transaction: several legacy initializers use executescript.
"""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .account_equipment import apply_hoyolab_equipment_snapshot
from .account_storage import (
    DEFAULT_SIDE_ICON_CACHE_DIR,
    build_account_gcsim_key_resolver,
    refresh_account_reference_fields,
    sync_account_storage_from_sources,
    weapon_equipment_from_detail_rows,
)
from .artifact_db import ARTIFACT_DB_PATH, connect_db, init_db
from .artifact_importer import import_character_details_payload, unwrap_hoyolab_payload
from .character_region_catalog import load_character_region_catalog
from .character_identity import sync_character_identity_from_account_rows
from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH, read_character_base_stats_cache,
)
from .character_trait_catalog import load_character_trait_catalog
from .crop_manifest import IGNORED_CHARACTER_IDS
from .traveler_variants import account_traveler_id
from .weapon_stats_catalog import WEAPON_STATS_CACHE_PATH, read_weapon_stats_cache


MAX_COMMITTED_ATTEMPTS = 10
MAX_PENDING_ATTEMPTS = 10
PENDING_RETENTION_DAYS = 30
_SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:cookie|authorization|password|secret|token|session|headers)(?:$|_)",
    re.IGNORECASE,
)


class ImportStoreError(RuntimeError):
    """A snapshot could not be safely published."""


class AccountBindingMismatch(ImportStoreError):
    """This database is already bound to another HoYoLAB role."""


class LegacyAccountBindingRequired(ImportStoreError):
    """Legacy account rows require a verified, explicit one-time binding."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _source_json(value: Mapping[str, Any]) -> str:
    def check(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if _SENSITIVE_KEY.search(str(key)):
                    raise ValueError(f"Import source contains a forbidden credential field: {key}")
                check(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                check(nested)

    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(account_uid: str | int, server: str) -> tuple[str, str]:
    uid = str(account_uid).strip()
    shard = str(server).strip()
    if not uid.isdigit() or not shard:
        raise ValueError("HoYoLAB role ID and server are required for account publication")
    return uid, shard


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result <= 0 or str(value).strip() != str(result):
        raise ValueError(f"{label} must be a positive integer")
    return result


def _validate_source(
    *, uid: str, server: str, characters: Any, weapons: Any, details: Any,
) -> None:
    if not isinstance(characters, list) or not characters:
        raise ValueError("HoYoLAB character inventory is empty")
    if not isinstance(weapons, list) or any(not isinstance(item, dict) for item in weapons):
        raise ValueError("HoYoLAB weapon inventory is malformed")
    requested: set[int] = set()
    seen_inventory: set[int] = set()
    for item in characters:
        if not isinstance(item, dict):
            raise ValueError("HoYoLAB character inventory has a malformed row")
        character_id = _positive_int(item.get("id"), "Character ID")
        if character_id in seen_inventory:
            raise ValueError("HoYoLAB character inventory has duplicate IDs")
        seen_inventory.add(character_id)
        if character_id not in IGNORED_CHARACTER_IDS:
            requested.add(character_id)
    if not requested:
        raise ValueError("HoYoLAB inventory has no real characters")
    if not isinstance(details, Mapping):
        raise ValueError("HoYoLAB character details are malformed")
    payload = unwrap_hoyolab_payload(details)
    if payload.get("retcode") != 0:
        raise ValueError("HoYoLAB character details did not succeed")
    data = payload.get("data")
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("HoYoLAB character detail rows are empty")
    returned: set[int] = set()
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get("base"), dict):
            raise ValueError("HoYoLAB character detail row is malformed")
        character_id = _positive_int(item["base"].get("id"), "Detail character ID")
        if character_id in returned:
            raise ValueError("HoYoLAB character detail has duplicate IDs")
        returned.add(character_id)
        relics = item.get("relics")
        if not isinstance(relics, list):
            raise ValueError("HoYoLAB relic rows are malformed")
        positions: set[int] = set()
        for relic in relics:
            if not isinstance(relic, dict):
                raise ValueError("HoYoLAB relic row is malformed")
            _positive_int(relic.get("id"), "Relic ID")
            position = _positive_int(relic.get("pos"), "Relic position")
            if position not in range(1, 6) or position in positions:
                raise ValueError("HoYoLAB relic slots are invalid or duplicated")
            positions.add(position)
            _positive_int(relic.get("rarity"), "Relic rarity")
            level = relic.get("level")
            if isinstance(level, bool) or not isinstance(level, int) or level < 0:
                raise ValueError("HoYoLAB relic level is malformed")
            relic_set = relic.get("set")
            if not isinstance(relic_set, dict):
                raise ValueError("HoYoLAB relic set is malformed")
            _positive_int(relic_set.get("id"), "Relic set ID")
            properties = [relic.get("main_property")]
            substats = relic.get("sub_property_list")
            if not isinstance(substats, list):
                raise ValueError("HoYoLAB relic substats are malformed")
            properties.extend(substats)
            for prop in properties:
                if not isinstance(prop, dict):
                    raise ValueError("HoYoLAB relic property is malformed")
                _positive_int(prop.get("property_type"), "Relic property type")
                if not any(prop.get(key) is not None and str(prop[key]).strip() for key in ("value", "final", "base")):
                    raise ValueError("HoYoLAB relic property value is missing")
    if not requested.issubset(returned):
        raise ValueError("HoYoLAB character detail IDs omit requested inventory IDs")
    for marker in (details, details.get("request"), payload, data):
        if not isinstance(marker, Mapping):
            continue
        body = marker.get("body") if isinstance(marker.get("body"), Mapping) else marker
        marker_uid = body.get("role_id") or body.get("game_uid")
        marker_server = body.get("server") or body.get("region")
        if marker_uid is not None and str(marker_uid) != uid:
            raise ValueError("HoYoLAB source role ID conflicts with import account")
        if marker_server is not None and str(marker_server) != server:
            raise ValueError("HoYoLAB source server conflicts with import account")


def prepare_import_store(db_path: str | Path = ARTIFACT_DB_PATH) -> Path:
    """Run all schema creation and migration before any import transaction."""
    path = Path(db_path)
    with closing(connect_db(path)) as conn:
        init_db(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hoyolab_account_binding (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                account_uid TEXT NOT NULL,
                server TEXT NOT NULL,
                bound_at TEXT NOT NULL,
                binding_method TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hoyolab_import_attempts (
                attempt_id TEXT PRIMARY KEY,
                account_uid TEXT NOT NULL,
                server TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'committed')),
                observed_at TEXT NOT NULL,
                change_equipment INTEGER NOT NULL,
                source_json TEXT NOT NULL,
                result_json TEXT,
                enrichment_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                committed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_hoyolab_import_attempts_account
                ON hoyolab_import_attempts(account_uid, server, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hoyolab_import_attempts_status
                ON hoyolab_import_attempts(status, created_at DESC);
            """
        )
        conn.commit()
    return path


def _attempt(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "attempt_id": row["attempt_id"],
        "account_uid": row["account_uid"],
        "server": row["server"],
        "status": row["status"],
        "observed_at": row["observed_at"],
        "change_equipment": bool(row["change_equipment"]),
        "source": json.loads(row["source_json"]),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "enrichment": json.loads(row["enrichment_json"]),
        "created_at": row["created_at"],
        "committed_at": row["committed_at"],
    }


def _readonly_existing(db_path: str | Path) -> sqlite3.Connection | None:
    path = Path(db_path)
    if not path.is_file():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def get_import_attempt(db_path: str | Path, attempt_id: str) -> dict[str, Any] | None:
    existing = _readonly_existing(db_path)
    if existing is None:
        return None
    with closing(existing) as conn:
        if not _has_table(conn, "hoyolab_import_attempts"):
            return None
        return _attempt(conn.execute(
            "SELECT * FROM hoyolab_import_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone())


def get_import_result(db_path: str | Path, attempt_id: str) -> dict[str, Any] | None:
    existing = _readonly_existing(db_path)
    if existing is None:
        return None
    with closing(existing) as conn:
        if not _has_table(conn, "hoyolab_import_attempts"):
            return None
        row = conn.execute(
            "SELECT status, result_json FROM hoyolab_import_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None or row["status"] != "committed" or not row["result_json"]:
            return None
        return json.loads(row["result_json"])


def latest_committed_import(db_path: str | Path) -> dict[str, Any] | None:
    existing = _readonly_existing(db_path)
    if existing is None:
        return None
    with closing(existing) as conn:
        if not _has_table(conn, "hoyolab_import_attempts"):
            return None
        return _attempt(conn.execute(
            "SELECT * FROM hoyolab_import_attempts WHERE status = 'committed' "
            "ORDER BY committed_at DESC, rowid DESC LIMIT 1"
        ).fetchone())


def get_active_account_binding(db_path: str | Path) -> dict[str, str] | None:
    """Return the role permitted to update this database, including images-only work."""
    existing = _readonly_existing(db_path)
    if existing is None:
        return None
    with closing(existing) as conn:
        if not _has_table(conn, "hoyolab_account_binding"):
            return None
        row = conn.execute(
            "SELECT account_uid, server, bound_at, binding_method FROM hoyolab_account_binding "
            "WHERE singleton = 1"
        ).fetchone()
        return dict(row) if row is not None else None


def _equipment_revision(conn: sqlite3.Connection) -> str:
    inventory: dict[str, list[tuple[Any, ...]]] = {}
    for table, columns in (
        ("account_character_equipped_artifacts", "character_id, slot_key, artifact_id"),
        ("account_character_equipped_weapons", "character_id, weapon_fingerprint"),
        ("artifact_equipment", "character_id, pos, artifact_id"),
    ):
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        inventory[table] = (
            [tuple(row) for row in conn.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2")]
            if present else []
        )
    payload = json.dumps(inventory, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_equipment_revision(db_path: str | Path) -> str:
    """Read assignment revision before acquisition without creating the DB."""
    path = Path(db_path)
    if not path.exists():
        with sqlite3.connect(":memory:") as conn:
            return _equipment_revision(conn)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return _equipment_revision(conn)


def list_pending_import_attempts(db_path: str | Path) -> list[dict[str, Any]]:
    existing = _readonly_existing(db_path)
    if existing is None:
        return []
    with closing(existing) as conn:
        if not _has_table(conn, "hoyolab_import_attempts"):
            return []
        return [_attempt(row) for row in conn.execute(
            """SELECT pending.* FROM hoyolab_import_attempts AS pending
               WHERE pending.status = 'pending'
                 AND NOT EXISTS (
                   SELECT 1 FROM hoyolab_account_binding AS binding
                   WHERE binding.singleton = 1 AND (
                     binding.account_uid <> pending.account_uid
                     OR binding.server <> pending.server
                   )
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM hoyolab_import_attempts AS committed
                   WHERE committed.status = 'committed'
                     AND committed.account_uid = pending.account_uid
                     AND committed.server = pending.server
                     AND committed.rowid > pending.rowid
                 )
               ORDER BY pending.created_at DESC, pending.rowid DESC"""
        )]


def _prune_attempts(conn: sqlite3.Connection) -> None:
    # Retain the latest receipt/source and a bounded history. The newest
    # pending attempt remains replayable even past the TTL.
    conn.execute(
        """DELETE FROM hoyolab_import_attempts
           WHERE status = 'committed' AND attempt_id NOT IN (
               SELECT attempt_id FROM hoyolab_import_attempts
               WHERE status = 'committed'
               ORDER BY committed_at DESC, rowid DESC LIMIT ?
           )""",
        (MAX_COMMITTED_ATTEMPTS,),
    )
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PENDING_RETENTION_DAYS)).isoformat(timespec="seconds")
    conn.execute(
        """DELETE FROM hoyolab_import_attempts WHERE status = 'pending'
           AND created_at < ? AND attempt_id NOT IN (
               SELECT attempt_id FROM hoyolab_import_attempts
               WHERE status = 'pending' ORDER BY created_at DESC, rowid DESC LIMIT 1
           )""",
        (cutoff,),
    )
    conn.execute(
        """DELETE FROM hoyolab_import_attempts WHERE status = 'pending'
           AND attempt_id NOT IN (
               SELECT attempt_id FROM hoyolab_import_attempts
               WHERE status = 'pending' ORDER BY created_at DESC, rowid DESC LIMIT ?
           )""",
        (MAX_PENDING_ATTEMPTS,),
    )


def stage_import_attempt(
    db_path: str | Path,
    *,
    account_uid: str | int,
    server: str,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    account_character_details: Mapping[str, Any],
    content_language: str = "en-us",
    manifest: Mapping[str, Any] | None = None,
    change_equipment: bool = False,
    expected_equipment_revision: str | None = None,
    observed_at: str | None = None,
    attempt_id: str | None = None,
) -> str:
    """Durably stage an exact safe source snapshot before core publication.

    ``prepare_import_store`` must be called first. Repeating the same ID and
    exact contents is safe; changing any source or identity is rejected.
    """
    uid, shard = _identity(account_uid, server)
    if expected_equipment_revision is not None and not re.fullmatch(
        r"[0-9a-f]{64}", expected_equipment_revision
    ):
        raise ValueError("Equipment revision must be a SHA-256 fingerprint")
    _validate_source(
        uid=uid, server=shard, characters=account_characters,
        weapons=account_weapons, details=account_character_details,
    )
    attempt_id = attempt_id or str(uuid.uuid4())
    requested_observed_at = observed_at
    source_json = _source_json({
        "account_characters": account_characters,
        "account_weapons": account_weapons,
        "account_character_details": account_character_details,
        "content_language": content_language,
        "manifest": manifest or {},
        "expected_equipment_revision": expected_equipment_revision,
    })
    with closing(connect_db(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            binding = conn.execute(
                "SELECT account_uid, server FROM hoyolab_account_binding WHERE singleton = 1"
            ).fetchone()
            if binding is not None and (binding["account_uid"], binding["server"]) != (uid, shard):
                raise AccountBindingMismatch(
                    f"Database is bound to role {binding['account_uid']} on {binding['server']}"
                )
            row = conn.execute(
                "SELECT * FROM hoyolab_import_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is not None:
                same = (
                    row["account_uid"] == uid and row["server"] == shard
                    and row["source_json"] == source_json
                    and (requested_observed_at is None or row["observed_at"] == requested_observed_at)
                    and bool(row["change_equipment"]) == bool(change_equipment)
                )
                if not same:
                    raise ImportStoreError("Attempt ID already belongs to a different snapshot")
            else:
                observed_at = requested_observed_at or _now()
                conn.execute(
                    """INSERT INTO hoyolab_import_attempts
                       (attempt_id, account_uid, server, status, observed_at,
                        change_equipment, source_json, created_at)
                       VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
                    (attempt_id, uid, shard, observed_at, int(change_equipment), source_json, _now()),
                )
            _prune_attempts(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return attempt_id


def _legacy_data_exists(conn: sqlite3.Connection) -> bool:
    for table in (
        "account_characters", "account_weapon_observed_stacks",
        "account_character_equipped_artifacts", "account_character_equipped_weapons",
        "artifact_equipment",
    ):
        if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            return True
    return conn.execute(
        "SELECT 1 FROM artifacts WHERE import_source = 'hoyolab' LIMIT 1"
    ).fetchone() is not None


def _check_binding(conn: sqlite3.Connection, uid: str, server: str) -> bool:
    row = conn.execute(
        "SELECT account_uid, server FROM hoyolab_account_binding WHERE singleton = 1"
    ).fetchone()
    if row is not None:
        if (row["account_uid"], row["server"]) != (uid, server):
            raise AccountBindingMismatch(
                f"Database is bound to role {row['account_uid']} on {row['server']}"
            )
        return False
    if _legacy_data_exists(conn):
        raise LegacyAccountBindingRequired(
            "Existing account data has no verified role binding. Confirm its UID/server "
            "and call adopt_legacy_account_binding before replaying the staged attempt."
        )
    return True


def adopt_legacy_account_binding(
    db_path: str | Path, *, account_uid: str | int, server: str, verified: bool = False,
) -> None:
    """Bind pre-existing account rows only after external UID/server verification."""
    if not verified:
        raise LegacyAccountBindingRequired("Explicit UID/server verification is required")
    uid, shard = _identity(account_uid, server)
    with closing(connect_db(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT account_uid, server FROM hoyolab_account_binding WHERE singleton = 1"
            ).fetchone()
            if row is not None:
                if (row["account_uid"], row["server"]) != (uid, shard):
                    raise AccountBindingMismatch("Cannot replace a bound account role")
            elif not _legacy_data_exists(conn):
                raise LegacyAccountBindingRequired("No legacy account rows require adoption")
            else:
                conn.execute(
                    "INSERT INTO hoyolab_account_binding VALUES (1, ?, ?, ?, 'verified_legacy_adoption')",
                    (uid, shard, _now()),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def build_account_sync_context(
    content_language: str = "en-us",
    *,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_stats_catalog_path: str | Path = WEAPON_STATS_CACHE_PATH,
    gcsim_character_registry_source_path: str | Path | None = None,
    gcsim_weapon_registry_source_path: str | Path | None = None,
    enrich_gcsim_keys: bool = True,
    trait_catalog: Any = None,
) -> dict[str, Any]:
    """Load optional references from local caches, with no network or DB write."""
    def optional(loader, default):
        try:
            return loader()
        except Exception:
            return default

    if trait_catalog is None:
        trait_catalog = optional(load_character_trait_catalog, None)
    return {
        "character_stats_catalog": optional(
            lambda: read_character_base_stats_cache(character_stats_catalog_path), None
        ),
        "weapon_stats_catalog": optional(
            lambda: read_weapon_stats_cache(weapon_stats_catalog_path), None
        ),
        "character_region_entries": optional(
            lambda: load_character_region_catalog(content_language, allow_network=False), []
        ),
        "character_trait_entries": trait_catalog.entries if trait_catalog else (),
        "gcsim_key_resolver": optional(
            lambda: build_account_gcsim_key_resolver(
                character_source_path=gcsim_character_registry_source_path,
                weapon_source_path=gcsim_weapon_registry_source_path,
            ), None,
        ) if enrich_gcsim_keys else None,
    }


def commit_import_snapshot(
    db_path: str | Path,
    *,
    attempt_id: str,
    account_sync_context: Mapping[str, Any] | None = None,
    side_icon_cache_dir: str | Path = DEFAULT_SIDE_ICON_CACHE_DIR,
) -> dict[str, Any]:
    """Publish staged artifacts, account rows, equipment and receipt as one unit."""
    staged = get_import_attempt(db_path, attempt_id)
    if staged is None:
        raise ImportStoreError(f"Unknown import attempt: {attempt_id}")
    if staged["status"] == "committed":
        return staged["result"]
    source = staged["source"]
    context = dict(account_sync_context or build_account_sync_context(source["content_language"]))
    with closing(connect_db(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM hoyolab_import_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise ImportStoreError("Staged attempt was removed before publication")
            if row["status"] == "committed":
                conn.commit()
                return json.loads(row["result_json"])
            superseding = conn.execute(
                """SELECT attempt_id FROM hoyolab_import_attempts
                   WHERE status = 'committed' AND account_uid = ? AND server = ?
                     AND rowid > (SELECT rowid FROM hoyolab_import_attempts WHERE attempt_id = ?)
                   ORDER BY rowid DESC LIMIT 1""",
                (row["account_uid"], row["server"], attempt_id),
            ).fetchone()
            if superseding is not None:
                raise ImportStoreError(
                    f"Pending import attempt was superseded by {superseding['attempt_id']}"
                )
            needs_binding = _check_binding(conn, row["account_uid"], row["server"])
            current_equipment_revision = _equipment_revision(conn) if bool(row["change_equipment"]) else None
            artifact_summary = import_character_details_payload(
                source["account_character_details"], db_path=db_path,
                conn=conn, initialize=False, allow_unmapped_sets=True,
            )
            account_summary = sync_account_storage_from_sources(
                conn,
                account_characters=source["account_characters"],
                account_weapons=source["account_weapons"],
                account_character_details=source["account_character_details"],
                crop_manifest=source["manifest"],
                side_icon_cache_dir=side_icon_cache_dir,
                side_icon_downloader=None,
                initialize=False,
                **context,
            ).to_dict()
            equipment_summary: dict[str, Any] = {"applied": False, "reason": "disabled"}
            if bool(row["change_equipment"]):
                expected = source.get("expected_equipment_revision")
                if expected is None:
                    equipment_summary = {"applied": False, "reason": "revision_unavailable"}
                elif expected != current_equipment_revision:
                    equipment_summary = {"applied": False, "reason": "stale_equipment_revision"}
                elif not artifact_summary.get("equipment_updated", True):
                    equipment_summary = {"applied": False, "reason": "incomplete_artifact_observation"}
                else:
                    details = unwrap_hoyolab_payload(source["account_character_details"])
                    detail_rows = (details.get("data") or {}).get("list") or []
                    variant_ids = {
                        int(item["base"]["id"]): account_traveler_id(
                            conn, int(item["base"]["id"]), item["base"].get("element"),
                        ) for item in detail_rows
                    }
                    weapons = {
                        variant_ids.get(character_id, character_id): fingerprint
                        for character_id, fingerprint in weapon_equipment_from_detail_rows(detail_rows).items()
                    }
                    artifacts = [
                        (variant_ids.get(int(item["character_id"]), int(item["character_id"])), int(item["artifact_id"]))
                        for item in conn.execute(
                            "SELECT character_id, artifact_id FROM artifact_equipment"
                        )
                    ]
                    equipment_summary = apply_hoyolab_equipment_snapshot(
                        conn, artifacts=artifacts, weapons=weapons, initialize=False,
                    )
                    equipment_summary["applied"] = True
            if needs_binding:
                conn.execute(
                    "INSERT INTO hoyolab_account_binding VALUES (1, ?, ?, ?, 'first_import')",
                    (row["account_uid"], row["server"], _now()),
                )
            result = {
                "attempt_id": attempt_id,
                "account_uid": row["account_uid"],
                "server": row["server"],
                "observed_at": row["observed_at"],
                "status": "committed",
                "artifacts": artifact_summary,
                "account_storage": account_summary,
                "equipment": equipment_summary,
                "warnings": list(account_summary.get("warnings") or []) + (
                    ["equipment_not_applied:" + equipment_summary["reason"]]
                    if bool(row["change_equipment"]) and not equipment_summary["applied"] else []
                ),
            }
            enrichment = {
                kind: {"status": "pending", "result": {}, "updated_at": _now()}
                for kind in ("assets", "references", "projections", "abyss", "side_icons")
            }
            conn.execute(
                "UPDATE hoyolab_import_attempts SET status = 'committed', result_json = ?, "
                "enrichment_json = ?, committed_at = ? WHERE attempt_id = ?",
                (json.dumps(result, ensure_ascii=False, sort_keys=True),
                 json.dumps(enrichment, ensure_ascii=False, sort_keys=True), _now(), attempt_id),
            )
            _prune_attempts(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


def update_import_enrichment(
    db_path: str | Path, *, attempt_id: str, kind: str,
    status: str, result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record optional post-commit work without changing the core receipt."""
    if not kind or status not in {"pending", "complete", "failed"}:
        raise ValueError("Invalid enrichment kind or status")
    with closing(connect_db(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT status, enrichment_json FROM hoyolab_import_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None or row["status"] != "committed":
                raise ImportStoreError("Only committed attempts can record enrichment")
            enrichment = json.loads(row["enrichment_json"])
            enrichment[kind] = {"status": status, "result": dict(result or {}), "updated_at": _now()}
            conn.execute(
                "UPDATE hoyolab_import_attempts SET enrichment_json = ? WHERE attempt_id = ?",
                (json.dumps(enrichment, ensure_ascii=False, sort_keys=True), attempt_id),
            )
            conn.commit()
            return enrichment
        except Exception:
            conn.rollback()
            raise


def refresh_import_references(
    db_path: str | Path, *, attempt_id: str,
    account_sync_context: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Apply later local reference enrichment without replaying source rows."""
    active = latest_committed_import(db_path)
    if active is None or active["attempt_id"] != attempt_id:
        raise ImportStoreError("Reference refresh requires the current committed attempt")
    context = dict(account_sync_context or build_account_sync_context(
        active["source"]["content_language"]
    ))
    # This legacy helper initializes with executescript, so it is deliberately
    # outside the reference update transaction and the already-committed core.
    with closing(connect_db(db_path)) as conn:
        sync_character_identity_from_account_rows(
            conn,
            region_entries=context.get("character_region_entries") or (),
            trait_entries=context.get("character_trait_entries") or (),
            now=_now(),
        )
        conn.commit()
    with closing(connect_db(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            summary = refresh_account_reference_fields(
                conn,
                character_stats_catalog=context.get("character_stats_catalog"),
                weapon_stats_catalog=context.get("weapon_stats_catalog"),
                gcsim_key_resolver=context.get("gcsim_key_resolver"),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return summary
