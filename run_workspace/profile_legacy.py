"""Allowlisted, resumable move of pre-profile account data into one profile."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .account_profiles import (
    AccountProfileError,
    PROJECT_ROOT,
    UnknownAccountProfile,
    list_profiles,
    profile_root,
)


ACCOUNT_RELATIVE_PATHS = (
    "data/artifacts.db",
    "data/artifacts.db-wal",
    "data/artifacts.db-shm",
    "data/hoyolab",
    "assets/hoyolab",
    "hoyolab_export/profile",
    "debug/hoyolab",
    "state.json",
    "runs_history.json",
    "data/history",
    "data/pvp",
    "data/gcsim/runs",
    "data/gcsim/farming-runs",
    "data/gcsim/optimizer-runs",
    "data/gcsim/optimizer-go-runs",
    "data/cache/gcsim_optimizer",
)
_MIGRATION_JOURNAL = ".legacy-migration.json"
_JOURNAL_SCHEMA_VERSION = 1
_LOGGER = logging.getLogger(__name__)
_DERIVED_RELATIVE_PATHS = frozenset({
    "data/gcsim/runs", "data/gcsim/farming-runs", "data/gcsim/optimizer-runs",
    "data/gcsim/optimizer-go-runs", "data/cache/gcsim_optimizer",
})


class LegacyProfileDataError(AccountProfileError):
    """Legacy account data cannot be moved or removed without ambiguity."""


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _has_content(path: Path) -> bool:
    if not _exists(path):
        return False
    if _is_link_or_reparse(path) or not path.is_dir():
        return True
    return any(_has_content(child) for child in path.iterdir())


def _checked_project_root(project_root: str | Path) -> Path:
    root = Path(project_root).absolute()
    if not root.is_dir() or _is_link_or_reparse(root):
        raise LegacyProfileDataError("Project root must be an ordinary directory")
    return root


def _owned_path(root: Path, relative: str) -> Path:
    if relative not in ACCOUNT_RELATIVE_PATHS:
        raise LegacyProfileDataError("Path is not in the legacy account allowlist")
    path = root.joinpath(*relative.split("/"))
    if os.path.commonpath((str(root), str(path))) != str(root):
        raise LegacyProfileDataError("Account path escapes its managed root")
    return path


def _check_ancestors(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise LegacyProfileDataError("Account path escapes its managed root") from exc
    current = root
    if _is_link_or_reparse(current):
        raise LegacyProfileDataError(f"Managed root is a link or junction: {current}")
    for part in relative.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise LegacyProfileDataError(f"Account path is a link or junction: {current}")


def _check_tree(path: Path) -> None:
    if not _exists(path):
        return
    if _is_link_or_reparse(path):
        raise LegacyProfileDataError(f"Account path is a link or junction: {path}")
    if path.is_dir():
        for child in path.iterdir():
            _check_tree(child)


def _preflight(root: Path, target_root: Path | None = None) -> None:
    for relative in ACCOUNT_RELATIVE_PATHS:
        source = _owned_path(root, relative)
        _check_ancestors(root, source)
        _check_tree(source)
        if target_root is not None:
            destination = _owned_path(target_root, relative)
            _check_ancestors(target_root, destination)
            _check_tree(destination)


def _registered_profile_root(profile_id: str, root: Path) -> Path:
    registered = {item["id"] for item in list_profiles(project_root=root)}
    if profile_id not in registered:
        raise UnknownAccountProfile(f"Unknown account profile: {profile_id}")
    target = profile_root(profile_id, project_root=root)
    if not target.is_dir() or _is_link_or_reparse(target):
        raise LegacyProfileDataError("Registered profile root is missing or unsafe")
    return target


def _journal_path(target_root: Path) -> Path:
    path = target_root / _MIGRATION_JOURNAL
    if _is_link_or_reparse(path):
        raise LegacyProfileDataError("Migration journal is a link or junction")
    return path


def _read_journal(path: Path, profile_id: str) -> tuple[str, ...] | None:
    if not _exists(path):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyProfileDataError("Migration journal cannot be read") from exc
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "profile_id", "paths", "started_at"
    } or type(data["schema_version"]) is not int or data["schema_version"] != _JOURNAL_SCHEMA_VERSION \
            or data["profile_id"] != profile_id or not isinstance(data["paths"], list) \
            or not isinstance(data["started_at"], str):
        raise LegacyProfileDataError("Migration journal is malformed or belongs to another profile")
    paths = tuple(data["paths"])
    if (not paths or any(not isinstance(item, str) or item not in ACCOUNT_RELATIVE_PATHS for item in paths)
            or len(set(paths)) != len(paths)):
        raise LegacyProfileDataError("Migration journal contains unsafe account paths")
    return paths


def _write_journal(path: Path, profile_id: str, paths: tuple[str, ...]) -> None:
    data = {
        "schema_version": _JOURNAL_SCHEMA_VERSION,
        "profile_id": profile_id,
        "paths": list(paths),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".legacy-migration-", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_owned_path(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def has_legacy_account_data(*, project_root: str | Path = PROJECT_ROOT) -> bool:
    """Check only the fixed legacy account allowlist, without creating state."""
    root = _checked_project_root(project_root)
    return any(_has_content(_owned_path(root, relative)) for relative in ACCOUNT_RELATIVE_PATHS)


def startup_legacy_migration_needed(
    profile_id: str, *, project_root: str | Path = PROJECT_ROOT,
) -> bool:
    """Keep orphan derived outputs separate from an already populated profile.

    A journal always owns recovery. Real legacy account state still triggers
    the collision checks; this does not merge, delete or adopt either copy.
    The broad legacy-data predicate remains unchanged for explicit full reset.
    """
    root = _checked_project_root(project_root)
    target_root = _registered_profile_root(profile_id, root)
    if _exists(_journal_path(target_root)):
        return True
    legacy = tuple(relative for relative in ACCOUNT_RELATIVE_PATHS
                   if _has_content(_owned_path(root, relative)))
    if not legacy:
        return False
    if any(relative not in _DERIVED_RELATIVE_PATHS for relative in legacy):
        return True
    for relative in ACCOUNT_RELATIVE_PATHS:
        if relative in _DERIVED_RELATIVE_PATHS:
            continue
        destination = _owned_path(target_root, relative)
        _check_ancestors(root, destination)
        if _has_content(destination):
            for source_relative in legacy:
                source = _owned_path(root, source_relative)
                _check_ancestors(root, source)
                _check_tree(source)
            _LOGGER.warning(
                "Legacy simulation outputs remain outside the selected account profile; "
                "they are preserved separately, not migrated or deleted: %s", ", ".join(legacy),
            )
            return False
    return True


def migrate_legacy_account_data(
    profile_id: str, *, project_root: str | Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Move account-owned legacy roots, resuming an interrupted journal exactly."""
    root = _checked_project_root(project_root)
    target_root = _registered_profile_root(profile_id, root)
    journal = _journal_path(target_root)
    _preflight(root, target_root)
    planned = _read_journal(journal, profile_id)
    if planned is None:
        planned = tuple(
            relative for relative in ACCOUNT_RELATIVE_PATHS
            if _has_content(_owned_path(root, relative))
        )
        if not planned:
            return {"profile_id": profile_id, "moved": [], "already_moved": []}
        if any(_exists(_owned_path(target_root, relative)) for relative in ACCOUNT_RELATIVE_PATHS):
            raise LegacyProfileDataError("Target profile already contains account data")
        _write_journal(journal, profile_id, planned)
    else:
        for relative in planned:
            source = _owned_path(root, relative)
            destination = _owned_path(target_root, relative)
            if _exists(source) == _exists(destination):
                raise LegacyProfileDataError(
                    f"Interrupted migration has both or neither copy: {relative}"
                )
        for relative in ACCOUNT_RELATIVE_PATHS:
            if relative not in planned and _has_content(_owned_path(root, relative)):
                raise LegacyProfileDataError("New legacy data appeared during migration")

    moved: list[str] = []
    already_moved: list[str] = []
    for relative in planned:
        source = _owned_path(root, relative)
        destination = _owned_path(target_root, relative)
        _check_ancestors(root, source)
        _check_ancestors(target_root, destination)
        _check_tree(source)
        _check_tree(destination)
        if _exists(source) and _exists(destination):
            raise LegacyProfileDataError(f"Both legacy and profile paths exist: {relative}")
        if not _exists(source):
            if not _exists(destination):
                raise LegacyProfileDataError(f"Legacy path vanished during migration: {relative}")
            already_moved.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        _check_ancestors(target_root, destination)
        _replace_owned_path(source, destination)
        moved.append(relative)
    journal.unlink()
    return {"profile_id": profile_id, "moved": moved, "already_moved": already_moved}


def _remove_tree(path: Path) -> None:
    if not _exists(path):
        return
    if _is_link_or_reparse(path):
        raise LegacyProfileDataError(f"Legacy path changed into a link: {path}")
    if path.is_dir():
        for child in path.iterdir():
            _remove_tree(child)
        path.rmdir()
    else:
        path.unlink()


def clear_legacy_account_data(*, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    """Remove exact allowlisted legacy roots after all profile processes stop."""
    root = _checked_project_root(project_root)
    _preflight(root)
    removed: list[str] = []
    for relative in ACCOUNT_RELATIVE_PATHS:
        path = _owned_path(root, relative)
        if _exists(path):
            _remove_tree(path)
            removed.append(relative)
    return {"removed": removed}


__all__ = [
    "ACCOUNT_RELATIVE_PATHS", "LegacyProfileDataError", "has_legacy_account_data",
    "startup_legacy_migration_needed",
    "migrate_legacy_account_data", "clear_legacy_account_data",
]
