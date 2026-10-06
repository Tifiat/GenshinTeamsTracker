"""Immutable account location, selected before account modules are imported."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from contextlib import closing

from .account_profiles import (
    PROJECT_ROOT, active_profile, ensure_active_profile, list_profiles,
    profile_root, update_profile_metadata,
)

PROFILE_ENV = "GTT_ACCOUNT_PROFILE"


def _bound_identity(database: Path) -> tuple[str, str] | None:
    """Read only the verified binding, never infer an owner from account rows."""
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'hoyolab_account_binding'"
            ).fetchone()
            if table is None:
                return None
            row = conn.execute(
                "SELECT account_uid, server FROM hoyolab_account_binding WHERE singleton = 1"
            ).fetchone()
            return (str(row[0]), str(row[1])) if row else None
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("Cannot inspect the legacy account binding") from exc


def bootstrap_profile() -> Path:
    """Select the managed root at an application/CLI boundary, never on test import."""
    from .profile_legacy import startup_legacy_migration_needed, migrate_legacy_account_data

    selected = active_profile(project_root=PROJECT_ROOT)
    inherited_id = os.environ.get(PROFILE_ENV)
    if inherited_id:
        # Import subprocesses must retain their parent's identity even if another
        # process attempts to change the registry's active selection.
        selected = next((p for p in list_profiles(project_root=PROJECT_ROOT)
                         if p["id"] == inherited_id), None)
        if selected is None:
            raise RuntimeError("The selected account profile no longer exists")
    if selected is None:
        selected = ensure_active_profile(project_root=PROJECT_ROOT)
    root = profile_root(selected["id"], project_root=PROJECT_ROOT)
    if not root.is_dir():
        raise RuntimeError("The selected account profile directory is missing")
    migration_pending = startup_legacy_migration_needed(selected["id"], project_root=PROJECT_ROOT)
    if migration_pending:
        if selected["imported"]:
            raise RuntimeError(
                "Legacy account data cannot be merged into an imported profile; "
                "select an empty draft profile first"
            )
        binding = _bound_identity(PROJECT_ROOT / "data" / "artifacts.db") or _bound_identity(
            root / "data" / "artifacts.db"
        )
        if binding is not None:
            metadata = selected["metadata"]
            current = (str(metadata.get("uid") or ""), str(metadata.get("server") or "").casefold())
            if all(current) and current != (binding[0], binding[1].casefold()):
                raise RuntimeError("Legacy account binding conflicts with the selected draft profile")
            for other in list_profiles(project_root=PROJECT_ROOT):
                other_metadata = other["metadata"]
                if (other["id"] != selected["id"]
                        and str(other_metadata.get("uid") or "") == binding[0]
                        and str(other_metadata.get("server") or "").casefold() == binding[1].casefold()):
                    raise RuntimeError("Legacy account binding belongs to another profile")
        migrate_legacy_account_data(selected["id"], project_root=PROJECT_ROOT)
    if not selected["imported"]:
        binding = _bound_identity(root / "data" / "artifacts.db")
        if binding is not None:
            selected = update_profile_metadata(
                selected["id"], {"uid": binding[0], "server": binding[1]}, imported=True,
                project_root=PROJECT_ROOT,
            )
    os.environ[PROFILE_ENV] = selected["id"]
    global PROFILE_ID, ACCOUNT_ROOT
    PROFILE_ID = selected["id"]
    ACCOUNT_ROOT = root
    return root


PROFILE_ID = os.environ.get(PROFILE_ENV)
# Library imports and fixture tests retain the historical path without writes.
# Every actual launcher bootstraps before importing domain/UI modules.
ACCOUNT_ROOT = profile_root(PROFILE_ID) if PROFILE_ID else PROJECT_ROOT


def account_asset_path(value: str | Path) -> Path:
    """Resolve portable account-relative paths, accepting old project paths."""
    def within_account(relative: Path) -> Path:
        candidate = ACCOUNT_ROOT / relative
        return candidate if candidate.resolve().is_relative_to(ACCOUNT_ROOT.resolve()) else (
            ACCOUNT_ROOT / ".unavailable-account-asset"
        )

    path = Path(value)
    if path.is_absolute():
        # Older account rows may contain absolute paths from before migration.
        # Never return an absolute asset owned by a different saved profile.
        try:
            relative = path.relative_to(PROJECT_ROOT / "data" / "profiles")
        except ValueError:
            pass
        else:
            if len(relative.parts) > 1 and relative.parts[0] == PROFILE_ID:
                return within_account(Path(*relative.parts[1:]))
            return ACCOUNT_ROOT / ".unavailable-account-asset"
        try:
            legacy_relative = path.relative_to(PROJECT_ROOT)
        except ValueError:
            return path
        if legacy_relative.parts[:2] in {
            ("assets", "hoyolab"), ("data", "hoyolab"),
            ("data", "history"), ("data", "pvp"),
        }:
            return within_account(legacy_relative)
        return path
    if path.parts[:2] == ("data", "profiles") and len(path.parts) > 3:
        # Portable restores must never reach into another saved account.
        return within_account(Path(*path.parts[3:]))
    if path.parts[:2] in {("assets", "hoyolab"), ("data", "hoyolab"),
                           ("data", "history"), ("data", "pvp")}:
        return within_account(path)
    return PROJECT_ROOT / path
