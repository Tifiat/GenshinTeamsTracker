"""Allowlisted portable PvP profiles, isolated from normal account storage."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable, Mapping, Protocol

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from hoyolab_export.traveler import is_traveler_id
from .deck_preset import DEFAULT_PVP_DECK_PRESET_DIR, PvpDeckPreset, deck_preset_from_mapping, load_deck_presets
from .abyss_rules import AbyssRuleset
from .profile_assets import ASSET_MANIFEST_NAME, ASSET_MEMBER_PATTERN, ProfileAssetError, build_profile_assets, validate_profile_assets
from .profile_schema import (
    ProfileSchemaError,
    contains_absolute_local_path,
    create_profile_slice,
    materialize_runtime_db,
    validate_profile_slice,
)

PVP_PROFILE_FORMAT = "genshin-teams-tracker-pvp-profile"
PVP_PROFILE_VERSION = 3
PVP_PROFILE_EXTENSION = ".gttpvp"
PVP_PROFILE_MANIFEST_NAME = "manifest.json"
PVP_PROFILE_DECKS_NAME = "decks.json"
PVP_PROFILE_DB_NAME = "account_slice.sqlite"
PVP_PROFILE_DECKS_KIND = "gtt.pvp_profile_decks"
PVP_PROFILE_ASSETS_NAME = ASSET_MANIFEST_NAME
PROFILE_INVENTORY_SCOPE = "all_artifacts_deck_character_builds"
MAX_PROFILE_BYTES = 128 * 1024 * 1024
MAX_PROFILE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_PROFILE_JSON_BYTES = 1024 * 1024
MAX_PROFILE_MEMBERS = 4096
MAX_PROFILE_COMPRESSION_RATIO = 200

_CORE_MEMBERS = frozenset({PVP_PROFILE_MANIFEST_NAME, PVP_PROFILE_DECKS_NAME, PVP_PROFILE_DB_NAME, PVP_PROFILE_ASSETS_NAME})
_MANIFEST_KEYS = frozenset({"format", "version", "schema_version", "created_at_utc", "created_by", "app_version", "nickname", "player_label", "locale", "abyss_period_id", "inventory_scope", "contents", "counts", "files"})
_DECK_KEYS = frozenset({"schema_version", "kind", "deck_id", "name", "ruleset_id", "character_ids", "weapon_refs", "created_at_utc", "updated_at_utc"})
_WEAPON_REF_KEYS = frozenset({"weapon_fingerprint", "weapon_id", "weapon_type", "rarity", "level", "refinement", "count"})


class PvpProfilePackageError(ValueError):
    """The package failed the portable profile contract."""


class PvpProfileProvider(Protocol):
    @property
    def db_path(self) -> Path: ...

    @property
    def metadata(self) -> Mapping[str, Any]: ...

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]: ...


@dataclass(frozen=True, slots=True)
class PvpProfilePackageOptions:
    nickname: str = ""
    player_label: str = ""
    created_at_utc: str = ""
    locale: str = ""
    abyss_period_id: str = ""
    app_version: str = ""


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
    source_db_path: Path
    character_asset_paths: Mapping[str, Path] = field(default_factory=dict)
    weapon_asset_paths: Mapping[str, Path] = field(default_factory=dict)
    _temp_dir: Any = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _runtime_users: int = field(default=0, init=False, repr=False)
    _lifecycle_lock: Any = field(default_factory=RLock, init=False, repr=False)

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closed = True
            self._cleanup_if_unused()

    def retain_runtime(self) -> Callable[[], None]:
        """A cancelled background reader must finish before its source is removed."""
        with self._lifecycle_lock:
            if self._closed:
                raise PvpProfilePackageError("PvP profile provider is closed.")
            self._runtime_users += 1
        released = False

        def release() -> None:
            nonlocal released
            with self._lifecycle_lock:
                if not released:
                    released = True
                    self._runtime_users -= 1
                    self._cleanup_if_unused()

        return release

    def _cleanup_if_unused(self) -> None:
        if self._closed and not self._runtime_users and self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def __enter__(self) -> "ImportedPvpProfile":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class LocalPvpProfileProvider:
    source_db_path: str | Path | None = None
    deck_dir: str | Path = DEFAULT_PVP_DECK_PRESET_DIR
    profile_metadata: Mapping[str, Any] = field(default_factory=dict)
    period_id_provider: Callable[[], str] | None = field(default=None, repr=False)

    @property
    def db_path(self) -> Path:
        return Path(self.source_db_path if self.source_db_path is not None else ARTIFACT_DB_PATH)

    @property
    def metadata(self) -> Mapping[str, Any]:
        metadata = dict(self.profile_metadata)
        if self.period_id_provider is not None:
            metadata["abyss_period_id"] = self.period_id_provider()
        return metadata

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]:
        return tuple(load_deck_presets(self.deck_dir))


@dataclass(slots=True)
class ImportedPvpProfileProvider:
    profile: ImportedPvpProfile

    @property
    def db_path(self) -> Path:
        if self.profile._closed:
            raise PvpProfilePackageError("PvP profile provider is closed.")
        return self.profile.db_path

    @property
    def metadata(self) -> Mapping[str, Any]:
        return {key: self.profile.manifest[key] for key in ("nickname", "player_label", "locale", "abyss_period_id")}

    def load_deck_presets(self) -> tuple[PvpDeckPreset, ...]:
        if self.profile._closed:
            raise PvpProfilePackageError("PvP profile provider is closed.")
        return self.profile.deck_presets

    def close(self) -> None:
        self.profile.close()

    def retain_runtime(self) -> Callable[[], None]:
        return self.profile.retain_runtime()


def export_pvp_profile_package(
    output_path: str | Path, *,
    deck_dir: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
    db_path: str | Path = ARTIFACT_DB_PATH,
    deck_ids: Iterable[str] | None = None,
    options: PvpProfilePackageOptions | None = None,
    character_asset_paths: Mapping[str, str | Path] | None = None,
    weapon_asset_paths: Mapping[str, str | Path] | None = None,
) -> PvpProfileExportReport:
    """Publish atomically; failure never replaces an existing output file."""
    output = Path(output_path)
    if output.suffix.lower() != PVP_PROFILE_EXTENSION:
        output = output.with_suffix(PVP_PROFILE_EXTENSION)
    source = Path(db_path).resolve(strict=True)
    if output.resolve() == source:
        raise PvpProfilePackageError("Cannot replace the profile source database.")
    presets = tuple(replace(preset, extra={}) for preset in _select_deck_presets(load_deck_presets(deck_dir), deck_ids))
    options = options or PvpProfilePackageOptions()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="gttpvp-export-", dir=output.parent) as temporary:
            root = Path(temporary)
            portable = root / PVP_PROFILE_DB_NAME
            counts = create_profile_slice(source, portable, presets)
            asset_map, bitmaps = build_profile_assets(
                source, portable, root, character_paths=character_asset_paths,
                weapon_paths=weapon_asset_paths,
            )
            files = {PVP_PROFILE_DB_NAME: portable, **bitmaps}
            for member, payload in (
                (PVP_PROFILE_DECKS_NAME, _deck_collection_payload(presets)),
                (PVP_PROFILE_ASSETS_NAME, asset_map),
            ):
                target = root / member
                target.write_bytes(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                    if member == PVP_PROFILE_DECKS_NAME else _json_bytes(payload)
                )
                files[member] = target
            records = {
                name: {"size": target.stat().st_size, "sha256": _file_hash(target)}
                for name, target in sorted(files.items())
            }
            manifest = _profile_manifest(options, counts, records)
            manifest_path = root / PVP_PROFILE_MANIFEST_NAME
            manifest_path.write_bytes(_json_bytes(manifest))
            files[PVP_PROFILE_MANIFEST_NAME] = manifest_path
            staged = root / "profile.gttpvp"
            with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, target in sorted(files.items()):
                    archive.write(target, name)
            # Use the actual import gates before publishing our own output.
            with import_pvp_profile_package(staged) as verified:
                if dict(verified.manifest["counts"]) != counts:
                    raise PvpProfilePackageError("PvP export count mismatch.")
            staged.replace(output)
    except (ProfileSchemaError, ProfileAssetError, sqlite3.DatabaseError, zipfile.BadZipFile) as exc:
        raise PvpProfilePackageError(str(exc)) from exc
    return PvpProfileExportReport(output, manifest, presets, counts)


def import_pvp_profile_package(
    package_path: str | Path, *, temp_root: str | Path | None = None,
) -> ImportedPvpProfile:
    """Validate all bytes and references before exposing a provider to Play."""
    path = Path(package_path)
    if path.stat().st_size > MAX_PROFILE_BYTES:
        raise PvpProfilePackageError("PvP archive exceeds the size limit.")
    temporary = tempfile.TemporaryDirectory(prefix="gttpvp-import-", dir=temp_root)
    try:
        root = Path(temporary.name)
        with zipfile.ZipFile(path, "r") as archive:
            members = _validate_entries(archive)
            manifest = _load_json(archive, PVP_PROFILE_MANIFEST_NAME)
            _validate_manifest(manifest, members)
            for name in sorted(set(members) - {PVP_PROFILE_MANIFEST_NAME}):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                record = manifest["files"][name]
                if members[name].file_size != record["size"]:
                    raise PvpProfilePackageError("PvP member size mismatch.")
                digest, size = hashlib.sha256(), 0
                with archive.open(name) as src, target.open("wb") as dst:
                    while chunk := src.read(64 * 1024):
                        size += len(chunk)
                        if size > record["size"]:
                            raise PvpProfilePackageError("PvP member exceeds declared size.")
                        digest.update(chunk)
                        dst.write(chunk)
                if size != record["size"] or digest.hexdigest() != record["sha256"]:
                    raise PvpProfilePackageError("PvP member hash mismatch.")
        decks = _load_decks(_json_object((root / PVP_PROFILE_DECKS_NAME).read_bytes()))
        portable = root / PVP_PROFILE_DB_NAME
        validate_profile_slice(portable, decks, manifest["counts"])
        characters, weapons = validate_profile_assets(
            _json_object((root / PVP_PROFILE_ASSETS_NAME).read_bytes()),
            portable, set(members), root,
        )
        runtime = root / "runtime.sqlite"
        materialize_runtime_db(portable, runtime, characters, weapons)
        return ImportedPvpProfile(path, manifest, decks, runtime, portable, characters, weapons, temporary)
    except Exception as exc:
        temporary.cleanup()
        if isinstance(exc, (ProfileSchemaError, ProfileAssetError, sqlite3.DatabaseError, zipfile.BadZipFile, EOFError)):
            raise PvpProfilePackageError(str(exc)) from exc
        raise


def _validate_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_PROFILE_MEMBERS:
        raise PvpProfilePackageError("Too many PvP profile members.")
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in entries:
        name = info.filename
        if name not in _CORE_MEMBERS and not ASSET_MEMBER_PATTERN.fullmatch(name):
            raise PvpProfilePackageError("Unexpected or unsafe PvP profile entry.")
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if name in members or info.is_dir() or file_type not in {0, stat.S_IFREG} or info.orig_filename != name:
            raise PvpProfilePackageError("Duplicate or non-file PvP profile entry.")
        if info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise PvpProfilePackageError("Unsupported PvP profile compression/encryption.")
        limit = MAX_PROFILE_JSON_BYTES if name.endswith(".json") else MAX_PROFILE_MEMBER_BYTES
        if info.file_size < 0 or info.file_size > limit or info.file_size > max(info.compress_size, 1) * MAX_PROFILE_COMPRESSION_RATIO:
            raise PvpProfilePackageError("PvP profile member exceeds size/compression limits.")
        total += info.file_size
        if total > MAX_PROFILE_BYTES:
            raise PvpProfilePackageError("PvP profile exceeds total size limit.")
        members[name] = info
    if not _CORE_MEMBERS <= members.keys():
        raise PvpProfilePackageError("PvP profile is missing required files.")
    return members


def _profile_manifest(
    options: PvpProfilePackageOptions, counts: Mapping[str, int],
    files: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "format": PVP_PROFILE_FORMAT, "version": PVP_PROFILE_VERSION,
        "schema_version": PVP_PROFILE_VERSION,
        "created_at_utc": options.created_at_utc or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "created_by": "GenshinTeamsTracker", "app_version": options.app_version,
        "nickname": options.nickname, "player_label": options.player_label,
        "locale": options.locale, "abyss_period_id": options.abyss_period_id,
        "inventory_scope": PROFILE_INVENTORY_SCOPE,
        "contents": {"decks": PVP_PROFILE_DECKS_NAME, "account_slice": PVP_PROFILE_DB_NAME, "assets": PVP_PROFILE_ASSETS_NAME},
        "counts": dict(sorted(counts.items())), "files": dict(files),
    }


def _validate_manifest(
    payload: Mapping[str, Any], members: Mapping[str, zipfile.ZipInfo],
) -> None:
    if set(payload) != _MANIFEST_KEYS or payload.get("format") != PVP_PROFILE_FORMAT:
        raise PvpProfilePackageError("Unsupported PvP profile manifest.")
    for key in ("version", "schema_version"):
        if type(payload[key]) is not int or payload[key] != PVP_PROFILE_VERSION:
            raise PvpProfilePackageError("Unsupported PvP profile version; re-export with the current format.")
    for key in ("created_at_utc", "created_by", "app_version", "nickname", "player_label", "locale", "abyss_period_id"):
        if (
            not isinstance(payload[key], str)
            or len(payload[key]) > 256
            or "\x00" in payload[key]
            or contains_absolute_local_path(payload[key])
        ):
            raise PvpProfilePackageError("Invalid PvP profile metadata.")
    if payload["inventory_scope"] != PROFILE_INVENTORY_SCOPE or payload["contents"] != {"decks": PVP_PROFILE_DECKS_NAME, "account_slice": PVP_PROFILE_DB_NAME, "assets": PVP_PROFILE_ASSETS_NAME}:
        raise PvpProfilePackageError("Unsupported PvP profile content scope.")
    counts = payload["counts"]
    if not isinstance(counts, dict) or any(type(value) is not int or value < 0 for value in counts.values()):
        raise PvpProfilePackageError("Invalid PvP profile counts.")
    records = payload["files"]
    if not isinstance(records, dict) or set(records) != set(members) - {PVP_PROFILE_MANIFEST_NAME}:
        raise PvpProfilePackageError("PvP profile file manifest mismatch.")
    for record in records.values():
        if not isinstance(record, dict) or set(record) != {"size", "sha256"}:
            raise PvpProfilePackageError("Invalid PvP file hash/size record.")
        if type(record["size"]) is not int or record["size"] < 0 or not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise PvpProfilePackageError("Invalid PvP file hash/size record.")


def _deck_collection_payload(presets) -> dict[str, Any]:
    """Keep one allowlisted snapshot per content hash in the exchange package."""
    decks, snapshots = [], {}
    for preset in presets:
        deck = preset.to_dict()
        snapshot = deck.pop("rules_snapshot", None)
        if snapshot:
            rules = _exchange_rules_snapshot(snapshot)
            snapshots[rules.content_hash] = rules.to_dict()
            deck["rules_snapshot_ref"] = rules.content_hash
        decks.append(deck)
    payload = {"schema_version": PVP_PROFILE_VERSION, "kind": PVP_PROFILE_DECKS_KIND, "decks": decks}
    if snapshots:
        payload["rules_snapshots"] = snapshots
    return payload


def _exchange_rules_snapshot(snapshot) -> AbyssRuleset:
    rules = AbyssRuleset.from_dict(snapshot)
    values = [rules.to_dict()]
    while values:
        value = values.pop()
        if isinstance(value, dict):
            values.extend(value.values())
        elif isinstance(value, list):
            values.extend(value)
        elif isinstance(value, str) and ("\x00" in value or contains_absolute_local_path(value)):
            raise PvpProfilePackageError("Local paths are not allowed in portable rules.")
    return rules


def _load_decks(payload: Mapping[str, Any]) -> tuple[PvpDeckPreset, ...]:
    if (set(payload) - {"rules_snapshots"}) != {"schema_version", "kind", "decks"} or type(payload.get("schema_version")) is not int or payload["schema_version"] != PVP_PROFILE_VERSION or payload["kind"] != PVP_PROFILE_DECKS_KIND:
        raise PvpProfilePackageError("Unsupported PvP decks payload.")
    snapshots = payload.get("rules_snapshots", {})
    if not isinstance(snapshots, dict) or len(snapshots) > 128:
        raise PvpProfilePackageError("Invalid rules snapshot collection.")
    for key, snapshot in snapshots.items():
        try:
            rules = _exchange_rules_snapshot(snapshot)
            if key != rules.content_hash:
                raise ValueError("Rules hash mismatch")
        except (ValueError, TypeError) as exc:
            raise PvpProfilePackageError("Invalid rules snapshot.") from exc
    decks = payload["decks"]
    if not isinstance(decks, list) or not 1 <= len(decks) <= 128:
        raise PvpProfilePackageError("Invalid PvP deck collection.")
    presets = []
    used_snapshots = set()
    for deck in decks:
        if not isinstance(deck, dict) or (set(deck) - {"rules_snapshot", "rules_snapshot_ref"}) != _DECK_KEYS:
            raise PvpProfilePackageError("Unexpected PvP deck fields.")
        if "rules_snapshot_ref" in deck:
            ref = deck["rules_snapshot_ref"]
            if "rules_snapshot" in deck or not isinstance(ref, str) or ref not in snapshots:
                raise PvpProfilePackageError("Invalid deck rules reference.")
            used_snapshots.add(ref)
            deck = {key: value for key, value in deck.items() if key != "rules_snapshot_ref"}
            deck["rules_snapshot"] = snapshots[ref]
        elif "rules_snapshot" in deck:
            try:
                _exchange_rules_snapshot(deck["rules_snapshot"])
            except (ValueError, TypeError) as exc:
                raise PvpProfilePackageError("Invalid inline rules snapshot.") from exc
        for key in ("deck_id", "name", "ruleset_id", "created_at_utc", "updated_at_utc", "kind"):
            if (
                not isinstance(deck[key], str)
                or len(deck[key]) > 256
                or "\x00" in deck[key]
                or contains_absolute_local_path(deck[key])
            ):
                raise PvpProfilePackageError("Invalid PvP deck metadata.")
        if type(deck["schema_version"]) is not int:
            raise PvpProfilePackageError("Invalid PvP deck schema version.")
        ids, refs = deck["character_ids"], deck["weapon_refs"]
        if not isinstance(ids, list) or len(ids) > 512 or any(not _valid_deck_character_id(item) for item in ids) or len(set(ids)) != len(ids):
            raise PvpProfilePackageError("Invalid or duplicate PvP deck character ids.")
        if not isinstance(refs, list) or len(refs) > 2048:
            raise PvpProfilePackageError("Invalid PvP deck weapon references.")
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != _WEAPON_REF_KEYS:
                raise PvpProfilePackageError("Unexpected PvP weapon reference fields.")
            for key in ("weapon_fingerprint", "weapon_id", "weapon_type"):
                if (
                    not isinstance(ref[key], str)
                    or len(ref[key]) > 256
                    or "\x00" in ref[key]
                    or contains_absolute_local_path(ref[key])
                ):
                    raise PvpProfilePackageError("Invalid PvP weapon reference.")
            for key in ("rarity", "level", "refinement", "count"):
                if ref[key] is not None and type(ref[key]) is not int:
                    raise PvpProfilePackageError("Invalid PvP weapon reference number.")
        try:
            preset = deck_preset_from_mapping(deck)
        except (ValueError, TypeError) as exc:
            raise PvpProfilePackageError("Invalid PvP deck preset.") from exc
        if len(preset.weapon_refs) != len(refs) or preset.deck_id != deck["deck_id"] or not preset.deck_id:
            raise PvpProfilePackageError("Duplicate/invalid PvP deck references or id.")
        presets.append(preset)
    if len({preset.deck_id for preset in presets}) != len(presets):
        raise PvpProfilePackageError("Duplicate PvP deck ids.")
    if used_snapshots != set(snapshots):
        raise PvpProfilePackageError("Unreferenced rules snapshot.")
    return tuple(presets)


def _valid_deck_character_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if re.fullmatch(r"[1-9][0-9]{0,9}", value):
        return True
    try:
        numeric_id = int(value)
    except ValueError:
        return False
    return (
        numeric_id < 0
        and str(numeric_id) == value
        and is_traveler_id(numeric_id)
    )


def _select_deck_presets(
    presets: Iterable[PvpDeckPreset], deck_ids: Iterable[str] | None,
) -> tuple[PvpDeckPreset, ...]:
    all_presets = tuple(presets)
    if deck_ids is None:
        selected = all_presets
    else:
        ids = {str(item).strip() for item in deck_ids}
        if not ids <= {preset.deck_id for preset in all_presets}:
            raise PvpProfilePackageError("Unknown PvP deck selected for export.")
        selected = tuple(preset for preset in all_presets if preset.deck_id in ids)
    if not selected:
        raise PvpProfilePackageError("Select at least one PvP deck for export.")
    return selected


def _load_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    with archive.open(name) as source:
        data = source.read(MAX_PROFILE_JSON_BYTES + 1)
    if len(data) > MAX_PROFILE_JSON_BYTES:
        raise PvpProfilePackageError("PvP JSON exceeds size limit.")
    return _json_object(data)


def _json_object(data: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PvpProfilePackageError("Duplicate PvP JSON property.")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise PvpProfilePackageError("Invalid PvP JSON number.")

    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PvpProfilePackageError("Invalid PvP JSON.") from exc
    if not isinstance(payload, dict):
        raise PvpProfilePackageError("PvP JSON root must be an object.")
    return payload


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


__all__ = [
    "ImportedPvpProfile", "ImportedPvpProfileProvider", "LocalPvpProfileProvider",
    "PVP_PROFILE_DB_NAME", "PVP_PROFILE_DECKS_KIND", "PVP_PROFILE_DECKS_NAME",
    "PVP_PROFILE_EXTENSION", "PVP_PROFILE_FORMAT", "PVP_PROFILE_MANIFEST_NAME",
    "PVP_PROFILE_VERSION", "PVP_PROFILE_ASSETS_NAME", "PvpProfileExportReport",
    "PvpProfilePackageError", "PvpProfilePackageOptions", "PvpProfileProvider",
    "export_pvp_profile_package", "import_pvp_profile_package",
]
