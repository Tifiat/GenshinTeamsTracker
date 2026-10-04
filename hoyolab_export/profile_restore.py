"""Restore a portable archive into a new isolated account, preserving the active one."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from contextlib import closing

from run_workspace.account_profiles import (
    PROJECT_ROOT, create_profile, delete_profile, profile_root, update_profile_metadata,
)
from run_workspace.profile_control import profile_operation_lock
from .import_store import get_active_account_binding
from .offline_profile import import_offline_profile


def _check_restored_database(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError("Offline profile has no account database")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise RuntimeError("Offline account database failed integrity check")
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("Offline account database is unreadable") from exc


def restore_saved_profile(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> dict:
    with profile_operation_lock(project_root=project_root):
        profile = create_profile(project_root=project_root, activate=False)
        key = profile["id"]
        root = profile_root(key, project_root=project_root)
        try:
            result = import_offline_profile(path, target_root=root)
            database = root / "data" / "artifacts.db"
            _check_restored_database(database)
            binding = get_active_account_binding(database)
            summary_path = root / "data" / "hoyolab" / "account_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
            if not isinstance(summary, dict):
                raise RuntimeError("Offline account summary is invalid")
            if binding:
                if (summary.get("uid") not in (None, "", binding["account_uid"])
                        or (summary.get("server") not in (None, "")
                            and str(summary["server"]).casefold() != binding["server"].casefold())):
                    raise RuntimeError("Offline account summary conflicts with its verified database binding")
                summary.update(uid=binding["account_uid"], server=binding["server"])
            elif summary.get("uid") or summary.get("server"):
                raise RuntimeError("Offline account summary has no verified database binding")
            profile = update_profile_metadata(key, summary, imported=bool(binding), project_root=project_root)
            return {**result, "profile": profile}
        except BaseException:
            delete_profile(key, project_root=project_root)
            raise
