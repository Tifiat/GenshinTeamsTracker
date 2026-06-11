from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator

from .artifact_db import ARTIFACT_DB_PATH
from .paths import (
    HOYOLAB_ARTIFACT_ASSETS_DIR,
    HOYOLAB_ASSETS_DIR,
    HOYOLAB_CHARACTER_ASSETS_DIR,
    HOYOLAB_DATA_DIR,
    HOYOLAB_DEBUG_DIR,
    HOYOLAB_WEAPON_ASSETS_DIR,
    PROJECT_ROOT,
    clear_hoyolab_current_data,
    ensure_hoyolab_dirs,
)


PROFILE_FORMAT = "genshin-teams-tracker-offline-profile"
PROFILE_VERSION = 1
PROFILE_MANIFEST_NAME = "offline_profile_manifest.json"
PROFILE_EXPORT_STATE_FILE = HOYOLAB_DATA_DIR / "offline_export_state.json"
RUNS_HISTORY_PATH = PROJECT_ROOT / "runs_history.json"

PROFILE_DATA_FILES = (
    HOYOLAB_DATA_DIR / "account_language.json",
    HOYOLAB_DATA_DIR / "account_characters.json",
    HOYOLAB_DATA_DIR / "account_weapons.json",
    HOYOLAB_DATA_DIR / "crop_manifest.json",
    HOYOLAB_DATA_DIR / "account_character_details.json",
)
PROFILE_ASSET_DIRS = (
    HOYOLAB_CHARACTER_ASSETS_DIR,
    HOYOLAB_WEAPON_ASSETS_DIR,
    HOYOLAB_ARTIFACT_ASSETS_DIR,
)
RESTORABLE_FILES = {
    "data/hoyolab/account_language.json",
    "data/hoyolab/account_characters.json",
    "data/hoyolab/account_weapons.json",
    "data/hoyolab/crop_manifest.json",
    "data/hoyolab/account_character_details.json",
    "data/artifacts.db",
}
RESTORABLE_PREFIXES = (
    "assets/hoyolab/characters/",
    "assets/hoyolab/weapons/",
    "assets/hoyolab/artifacts/",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _artifact_db_sidecars() -> list[Path]:
    return [
        ARTIFACT_DB_PATH,
        Path(str(ARTIFACT_DB_PATH) + "-wal"),
        Path(str(ARTIFACT_DB_PATH) + "-shm"),
    ]


def _safe_project_relative(path: Path) -> str:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Refusing path outside project root: {resolved}") from exc
    return relative.as_posix()


def _iter_asset_files(folder: Path) -> Iterator[Path]:
    if not folder.exists():
        return

    for path in sorted(folder.rglob("*")):
        if path.is_file():
            yield path


def _backup_sqlite_db(source: Path, destination: Path) -> Path | None:
    if not source.exists():
        return None

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

    return destination


def _iter_current_profile_files(
    *,
    artifact_db_snapshot: Path | None = None,
) -> Iterator[tuple[Path, str]]:
    for path in PROFILE_DATA_FILES:
        if path.exists():
            yield path, _safe_project_relative(path)

    for folder in PROFILE_ASSET_DIRS:
        for path in _iter_asset_files(folder):
            yield path, _safe_project_relative(path)

    if ARTIFACT_DB_PATH.exists():
        yield artifact_db_snapshot or ARTIFACT_DB_PATH, "data/artifacts.db"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_from_files(
    *,
    artifact_db_snapshot: Path | None = None,
) -> dict[str, object]:
    digest = hashlib.sha256()
    files = []

    for path, archive_name in sorted(
        _iter_current_profile_files(artifact_db_snapshot=artifact_db_snapshot),
        key=lambda item: item[1],
    ):
        file_hash = _file_digest(path)
        files.append({"path": archive_name, "sha256": file_hash})
        digest.update(archive_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")

    return {
        "version": PROFILE_VERSION,
        "hash": digest.hexdigest(),
        "fileCount": len(files),
        "files": files,
    }


def current_profile_signature() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot = _backup_sqlite_db(
            ARTIFACT_DB_PATH,
            Path(temp_dir) / "artifacts.db",
        )
        return _signature_from_files(artifact_db_snapshot=snapshot)


def has_local_hoyolab_profile() -> bool:
    for path in PROFILE_DATA_FILES:
        if path.exists() and path.stat().st_size > 0:
            return True

    for folder in PROFILE_ASSET_DIRS:
        if folder.exists() and any(path.is_file() for path in folder.rglob("*")):
            return True

    return ARTIFACT_DB_PATH.exists() and ARTIFACT_DB_PATH.stat().st_size > 0


def _write_export_state(signature: dict[str, object], export_path: Path | None) -> None:
    PROFILE_EXPORT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_EXPORT_STATE_FILE.write_text(
        json.dumps(
            {
                "format": PROFILE_FORMAT,
                "version": PROFILE_VERSION,
                "exportedAt": utc_now(),
                "exportPath": str(export_path) if export_path else None,
                "signature": signature,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def mark_current_profile_exported(export_path: Path | None = None) -> dict[str, object]:
    signature = current_profile_signature()
    _write_export_state(signature, export_path)
    return signature


def is_current_profile_exported() -> bool:
    if not PROFILE_EXPORT_STATE_FILE.exists():
        return False

    try:
        state = json.loads(PROFILE_EXPORT_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False

    if state.get("format") != PROFILE_FORMAT:
        return False

    expected = state.get("signature")
    current = current_profile_signature()
    return isinstance(expected, dict) and expected.get("hash") == current.get("hash")


def export_offline_profile(zip_path: str | Path) -> dict[str, object]:
    ensure_hoyolab_dirs()

    output_path = Path(zip_path)
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        artifact_snapshot = _backup_sqlite_db(
            ARTIFACT_DB_PATH,
            Path(temp_dir) / "artifacts.db",
        )
        signature = _signature_from_files(artifact_db_snapshot=artifact_snapshot)

        included_files = []
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, archive_name in sorted(
                _iter_current_profile_files(artifact_db_snapshot=artifact_snapshot),
                key=lambda item: item[1],
            ):
                archive.write(path, archive_name)
                included_files.append(archive_name)

            archive.writestr(
                PROFILE_MANIFEST_NAME,
                json.dumps(
                    {
                        "format": PROFILE_FORMAT,
                        "version": PROFILE_VERSION,
                        "exportedAt": utc_now(),
                        "createdBy": "GenshinTeamsTracker",
                        "signature": signature,
                        "includedFiles": included_files,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

    _write_export_state(signature, output_path)

    return {
        "path": output_path,
        "includedFiles": included_files,
        "signature": signature,
    }


def _safe_archive_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".."} for part in path.parts):
        raise RuntimeError(f"Unsafe offline profile entry: {name}")
    return path.as_posix()


def _is_restorable_entry(name: str) -> bool:
    if name in RESTORABLE_FILES:
        return True
    return any(name.startswith(prefix) for prefix in RESTORABLE_PREFIXES)


def _project_target_for_archive_name(name: str) -> Path:
    target = (PROJECT_ROOT / name).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Offline profile entry escapes project root: {name}") from exc
    return target


def _delete_artifact_db() -> None:
    for path in _artifact_db_sidecars():
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def import_offline_profile(zip_path: str | Path) -> dict[str, object]:
    input_path = Path(zip_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    restored_files = []

    with zipfile.ZipFile(input_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            name = _safe_archive_name(info.filename)
            if name == PROFILE_MANIFEST_NAME:
                continue
            if not _is_restorable_entry(name):
                raise RuntimeError(f"Unexpected offline profile entry: {name}")

        clear_hoyolab_current_data()
        _delete_artifact_db()
        ensure_hoyolab_dirs()

        for info in archive.infolist():
            if info.is_dir():
                continue

            name = _safe_archive_name(info.filename)
            if name == PROFILE_MANIFEST_NAME:
                continue
            if not _is_restorable_entry(name):
                continue

            target = _project_target_for_archive_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            restored_files.append(name)

    ensure_hoyolab_dirs()
    signature = mark_current_profile_exported(input_path)

    return {
        "path": input_path,
        "restoredFiles": restored_files,
        "signature": signature,
    }


def clear_current_offline_profile(*, clear_history: bool) -> None:
    clear_hoyolab_current_data()
    _delete_artifact_db()
    ensure_hoyolab_dirs()

    if clear_history:
        try:
            RUNS_HISTORY_PATH.unlink()
        except FileNotFoundError:
            pass


def export_state_age_seconds() -> float | None:
    if not PROFILE_EXPORT_STATE_FILE.exists():
        return None

    try:
        return time.time() - PROFILE_EXPORT_STATE_FILE.stat().st_mtime
    except OSError:
        return None
