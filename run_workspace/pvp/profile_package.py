"""Versioned PvP profile packages for scoped build-flow data providers."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Protocol

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH

from .deck_preset import (
    DEFAULT_PVP_DECK_PRESET_DIR,
    PvpDeckPreset,
    deck_preset_from_mapping,
    load_deck_presets,
)
from .weapon_identity import WeaponObservedStackRef, weapon_observed_stack_key


PVP_PROFILE_FORMAT = "genshin-teams-tracker-pvp-profile"
PVP_PROFILE_VERSION = 1
PVP_PROFILE_EXTENSION = ".gttpvp"
PVP_PROFILE_MANIFEST_NAME = "manifest.json"
PVP_PROFILE_DECKS_NAME = "decks.json"
PVP_PROFILE_DB_NAME = "account_slice.sqlite"
PVP_PROFILE_DECKS_KIND = "gtt.pvp_profile_decks"

_ALLOWED_PROFILE_ENTRIES = frozenset(
    {
        PVP_PROFILE_MANIFEST_NAME,
        PVP_PROFILE_DECKS_NAME,
        PVP_PROFILE_DB_NAME,
    }
)


class PvpProfilePackageError(ValueError):
    """Raised when a PvP profile package is malformed or unsupported."""


class PvpProfileProvider(Protocol):
    """Data-provider boundary for scoped PvP build-flow contexts."""

    @property
    def db_path(self) -> Path:
        """SQLite DB path consumed by existing AppShell/browser classes."""

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]:
        """Return PvP deck presets available for this scoped profile."""


@dataclass(frozen=True, slots=True)
class PvpProfilePackageOptions:
    nickname: str = ""
    player_label: str = ""
    created_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class PvpProfileExportReport:
    path: Path
    manifest: Mapping[str, Any]
    deck_presets: tuple[PvpDeckPreset, ...]
    counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ImportedPvpProfile:
    path: Path
    manifest: Mapping[str, Any]
    deck_presets: tuple[PvpDeckPreset, ...]
    db_path: Path
    _temp_dir: Any = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        temp_dir = self._temp_dir
        self._temp_dir = None
        if temp_dir is not None:
            temp_dir.cleanup()

    def __enter__(self) -> "ImportedPvpProfile":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class LocalPvpProfileProvider:
    """Provider for a local player using the app's current SQLite DB directly."""

    source_db_path: str | Path | None = None
    deck_dir: str | Path = DEFAULT_PVP_DECK_PRESET_DIR

    @property
    def db_path(self) -> Path:
        return Path(self.source_db_path) if self.source_db_path is not None else Path(
            ARTIFACT_DB_PATH
        )

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]:
        return tuple(load_deck_presets(self.deck_dir))


@dataclass(slots=True)
class ImportedPvpProfileProvider:
    """Provider wrapper around an imported `.gttpvp` profile package."""

    profile: ImportedPvpProfile

    @property
    def db_path(self) -> Path:
        return self.profile.db_path

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]:
        return self.profile.deck_presets

    def close(self) -> None:
        self.profile.close()


def export_pvp_profile_package(
    output_path: str | Path,
    *,
    deck_dir: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
    db_path: str | Path = ARTIFACT_DB_PATH,
    deck_ids: Iterable[str] | None = None,
    options: PvpProfilePackageOptions | None = None,
) -> PvpProfileExportReport:
    """Export selected local PvP decks plus a filtered SQLite account slice."""

    options = options or PvpProfilePackageOptions()
    output = _normalize_profile_output_path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    deck_presets = _select_deck_presets(load_deck_presets(deck_dir), deck_ids)
    source_db = Path(db_path)
    if not source_db.exists():
        raise FileNotFoundError(source_db)

    with tempfile.TemporaryDirectory() as temp_dir:
        account_slice = Path(temp_dir) / PVP_PROFILE_DB_NAME
        _backup_sqlite_db(source_db, account_slice)
        counts = _filter_account_slice(account_slice, deck_presets)
        manifest = _profile_manifest(options=options, counts=counts)
        decks_payload = _decks_payload(deck_presets)

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                PVP_PROFILE_MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            archive.writestr(
                PVP_PROFILE_DECKS_NAME,
                json.dumps(decks_payload, ensure_ascii=False, indent=2) + "\n",
            )
            archive.write(account_slice, PVP_PROFILE_DB_NAME)

    return PvpProfileExportReport(
        path=output,
        manifest=manifest,
        deck_presets=deck_presets,
        counts=counts,
    )


def import_pvp_profile_package(
    package_path: str | Path,
    *,
    temp_root: str | Path | None = None,
) -> ImportedPvpProfile:
    """Load a `.gttpvp` package into a managed temp DB path."""

    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(path)

    temp_dir = tempfile.TemporaryDirectory(dir=Path(temp_root) if temp_root else None)
    try:
        temp_path = Path(temp_dir.name)
        db_path = temp_path / PVP_PROFILE_DB_NAME

        with zipfile.ZipFile(path, "r") as archive:
            _validate_profile_entries(archive)
            manifest = _load_profile_manifest(archive)
            deck_presets = _load_profile_decks(archive)
            with archive.open(PVP_PROFILE_DB_NAME, "r") as source, db_path.open(
                "wb"
            ) as destination:
                shutil.copyfileobj(source, destination)

        return ImportedPvpProfile(
            path=path,
            manifest=manifest,
            deck_presets=deck_presets,
            db_path=db_path,
            _temp_dir=temp_dir,
        )
    except Exception:
        temp_dir.cleanup()
        raise


def _profile_manifest(
    *,
    options: PvpProfilePackageOptions,
    counts: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "format": PVP_PROFILE_FORMAT,
        "version": PVP_PROFILE_VERSION,
        "created_at_utc": options.created_at_utc or _utc_stamp(),
        "created_by": "GenshinTeamsTracker",
        "nickname": _text(options.nickname),
        "player_label": _text(options.player_label),
        "contents": {
            "decks": PVP_PROFILE_DECKS_NAME,
            "account_slice": PVP_PROFILE_DB_NAME,
        },
        "counts": dict(sorted(counts.items())),
    }


def _decks_payload(deck_presets: tuple[PvpDeckPreset, ...]) -> dict[str, Any]:
    return {
        "schema_version": PVP_PROFILE_VERSION,
        "kind": PVP_PROFILE_DECKS_KIND,
        "decks": [preset.to_dict() for preset in deck_presets],
    }


def _load_profile_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        payload = json.loads(archive.read(PVP_PROFILE_MANIFEST_NAME).decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PvpProfilePackageError("Invalid PvP profile manifest.") from exc

    if not isinstance(payload, Mapping):
        raise PvpProfilePackageError("PvP profile manifest must be an object.")
    if payload.get("format") != PVP_PROFILE_FORMAT:
        raise PvpProfilePackageError("Unsupported PvP profile format.")
    if payload.get("version") != PVP_PROFILE_VERSION:
        raise PvpProfilePackageError("Unsupported PvP profile version.")
    return dict(payload)


def _load_profile_decks(archive: zipfile.ZipFile) -> tuple[PvpDeckPreset, ...]:
    try:
        payload = json.loads(archive.read(PVP_PROFILE_DECKS_NAME).decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PvpProfilePackageError("Invalid PvP profile decks payload.") from exc

    if not isinstance(payload, Mapping):
        raise PvpProfilePackageError("PvP profile decks payload must be an object.")
    if payload.get("schema_version") != PVP_PROFILE_VERSION:
        raise PvpProfilePackageError("Unsupported PvP profile decks version.")
    if payload.get("kind") != PVP_PROFILE_DECKS_KIND:
        raise PvpProfilePackageError("Unsupported PvP profile decks kind.")

    decks = payload.get("decks")
    if not isinstance(decks, list):
        raise PvpProfilePackageError("PvP profile decks must be a list.")

    try:
        return tuple(deck_preset_from_mapping(item) for item in decks)
    except ValueError as exc:
        raise PvpProfilePackageError("Invalid PvP deck preset in profile.") from exc


def _validate_profile_entries(archive: zipfile.ZipFile) -> None:
    names: set[str] = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = _safe_archive_name(info.filename)
        if name not in _ALLOWED_PROFILE_ENTRIES:
            raise PvpProfilePackageError(f"Unexpected PvP profile entry: {name}")
        names.add(name)

    missing = _ALLOWED_PROFILE_ENTRIES.difference(names)
    if missing:
        raise PvpProfilePackageError(
            "PvP profile package is missing entries: "
            + ", ".join(sorted(missing))
        )


def _filter_account_slice(
    db_path: Path,
    deck_presets: tuple[PvpDeckPreset, ...],
) -> dict[str, int]:
    character_ids = {
        value
        for value in (_optional_int(item) for item in _deck_character_ids(deck_presets))
        if value is not None
    }
    weapon_refs = tuple(
        ref
        for preset in deck_presets
        for ref in preset.weapon_refs
        if isinstance(ref, WeaponObservedStackRef)
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        kept_weapon_fingerprints = _filter_weapon_rows(conn, weapon_refs)
        _filter_character_rows(conn, character_ids)
        _filter_equipment_rows(conn, character_ids, kept_weapon_fingerprints)
        conn.commit()
        return {
            "deck_count": len(deck_presets),
            "character_count": _count_table(conn, "account_characters"),
            "weapon_stack_count": _count_table(conn, "account_weapon_observed_stacks"),
        }
    finally:
        conn.close()


def _filter_character_rows(
    conn: sqlite3.Connection,
    character_ids: set[int],
) -> None:
    for table in (
        "account_character_talents",
        "account_character_constellations",
        "account_characters",
        "character_identity",
    ):
        if not _table_exists(conn, table):
            continue
        _delete_rows_not_in(conn, table, "character_id", character_ids)


def _filter_weapon_rows(
    conn: sqlite3.Connection,
    weapon_refs: tuple[WeaponObservedStackRef, ...],
) -> set[str]:
    table = "account_weapon_observed_stacks"
    if not _table_exists(conn, table):
        return set()

    selected_fingerprints = {_text(ref.weapon_fingerprint) for ref in weapon_refs}
    selected_fingerprints.discard("")
    selected_keys = {_text(ref.key) for ref in weapon_refs}
    selected_keys.update(
        weapon_observed_stack_key(
            weapon_id=ref.weapon_id,
            weapon_type=ref.weapon_type,
            rarity=ref.rarity,
            level=ref.level,
            refinement=ref.refinement,
        )
        for ref in weapon_refs
        if ref.weapon_id
    )
    selected_keys.discard("")

    rows = conn.execute(
        f"""
        SELECT rowid AS _rowid, *
        FROM {table}
        """
    ).fetchall()
    delete_rowids: list[int] = []
    kept_fingerprints: set[str] = set()
    for row in rows:
        fingerprint = _text(row["weapon_fingerprint"])
        row_keys = {
            weapon_observed_stack_key(
                weapon_id=row["weapon_id"],
                weapon_type=row["weapon_type"],
                rarity=row["rarity"],
                level=row["level"],
                refinement=row["refinement"],
            ),
            weapon_observed_stack_key(
                weapon_id=row["weapon_id"],
                weapon_type=row["weapon_type_name"],
                rarity=row["rarity"],
                level=row["level"],
                refinement=row["refinement"],
            ),
        }
        keep = fingerprint in selected_fingerprints or bool(
            selected_keys.intersection(row_keys)
        )
        if keep:
            if fingerprint:
                kept_fingerprints.add(fingerprint)
        else:
            delete_rowids.append(int(row["_rowid"]))

    _delete_rowids(conn, table, delete_rowids)
    return kept_fingerprints


def _filter_equipment_rows(
    conn: sqlite3.Connection,
    character_ids: set[int],
    weapon_fingerprints: set[str],
) -> None:
    if _table_exists(conn, "account_character_equipped_artifacts"):
        _delete_rows_not_in(
            conn,
            "account_character_equipped_artifacts",
            "character_id",
            character_ids,
        )

    if _table_exists(conn, "account_character_equipped_weapons"):
        _delete_rows_not_in(
            conn,
            "account_character_equipped_weapons",
            "character_id",
            character_ids,
        )
        _delete_rows_not_in(
            conn,
            "account_character_equipped_weapons",
            "weapon_fingerprint",
            weapon_fingerprints,
        )


def _backup_sqlite_db(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(destination)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.DatabaseError:
        shutil.copy2(source, destination)


def _select_deck_presets(
    presets: Iterable[PvpDeckPreset],
    deck_ids: Iterable[str] | None,
) -> tuple[PvpDeckPreset, ...]:
    all_presets = tuple(presets)
    if deck_ids is None:
        return all_presets
    selected_ids = {_text(deck_id) for deck_id in deck_ids if _text(deck_id)}
    return tuple(preset for preset in all_presets if preset.deck_id in selected_ids)


def _deck_character_ids(deck_presets: tuple[PvpDeckPreset, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            character_id
            for preset in deck_presets
            for character_id in preset.character_ids
            if character_id
        )
    )


def _delete_rows_not_in(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    values: set[int] | set[str],
) -> None:
    if not values:
        conn.execute(f"DELETE FROM {table}")
        return
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"DELETE FROM {table} WHERE {column} NOT IN ({placeholders})",
        tuple(sorted(values)),
    )


def _delete_rowids(conn: sqlite3.Connection, table: str, rowids: list[int]) -> None:
    if not rowids:
        return
    placeholders = ", ".join("?" for _ in rowids)
    conn.execute(
        f"DELETE FROM {table} WHERE rowid IN ({placeholders})",
        tuple(rowids),
    )


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] if row is not None else 0)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


def _safe_archive_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".."} for part in path.parts):
        raise PvpProfilePackageError(f"Unsafe PvP profile entry: {name}")
    return path.as_posix()


def _normalize_profile_output_path(output_path: str | Path) -> Path:
    path = Path(output_path)
    if path.suffix.lower() != PVP_PROFILE_EXTENSION:
        return path.with_suffix(PVP_PROFILE_EXTENSION)
    return path


def _utc_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "ImportedPvpProfile",
    "ImportedPvpProfileProvider",
    "LocalPvpProfileProvider",
    "PVP_PROFILE_DB_NAME",
    "PVP_PROFILE_DECKS_KIND",
    "PVP_PROFILE_DECKS_NAME",
    "PVP_PROFILE_EXTENSION",
    "PVP_PROFILE_FORMAT",
    "PVP_PROFILE_MANIFEST_NAME",
    "PVP_PROFILE_VERSION",
    "PvpProfileExportReport",
    "PvpProfilePackageError",
    "PvpProfilePackageOptions",
    "PvpProfileProvider",
    "export_pvp_profile_package",
    "import_pvp_profile_package",
]
