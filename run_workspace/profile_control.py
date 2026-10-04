"""Apply profile changes only between UI processes, after handles close."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from typing import Iterator

from .account_profiles import (
    PROJECT_ROOT, activate_profile, clear_all_profiles, create_profile,
    delete_profile, list_profiles, profile_root,
)
from .app_settings import reset_app_settings

ACTION_ENV = "GTT_PROFILE_ACTION_FILE"
OPERATIONS = frozenset({"new", "activate", "delete", "reset"})
_PROFILE_ID = re.compile(r"[0-9a-f]{32}\Z")
_ACTION_FILE = re.compile(r"[0-9a-f]{32}\.json\Z")
_ACTION_TEMP = re.compile(r"\.request-[A-Za-z0-9_-]+\.tmp\Z")
_BROWSER_MARKERS = ("SingletonLock", "SingletonSocket", "SingletonCookie")


def _is_reparse(path: Path) -> bool:
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


def _validate_request(operation: str, profile_id: str) -> None:
    if operation not in OPERATIONS:
        raise ValueError("Unsupported account operation")
    if operation in {"activate", "delete"}:
        if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
            raise ValueError("Account operation requires a valid profile ID")
    elif profile_id != "":
        raise ValueError("This account operation must not name a profile")


@contextmanager
def _file_lock(path: Path, *, label: str, create: bool) -> Iterator[None]:
    if _is_reparse(path.parent) or _is_reparse(path):
        raise RuntimeError(f"Unsafe {label} lock path")
    if not create and not _exists(path):
        yield
        return
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | (os.O_CREAT if create else 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Cannot open {label} lock") from exc
    with os.fdopen(descriptor, "r+b") as file:
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(f"{label} is already running") from exc
            try:
                yield
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError(f"{label} is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@contextmanager
def profile_operation_lock(*, project_root: Path = PROJECT_ROOT) -> Iterator[None]:
    """Shared nonblocking gate for CLI imports and profile operations."""
    root = Path(project_root).absolute()
    if _is_reparse(root / "data"):
        raise RuntimeError("Profile operation data directory is a link or junction")
    with _file_lock(root / "data" / "profile-operations.lock",
                    label="Profile operation/import", create=True):
        yield


@contextmanager
def profile_supervisor_lock(*, project_root: Path = PROJECT_ROOT) -> Iterator[None]:
    """Exclusive lease for one AppShell or legacy main UI lifetime."""
    root = Path(project_root).absolute()
    if _is_reparse(root / "data"):
        raise RuntimeError("Profile supervisor data directory is a link or junction")
    with _file_lock(root / "data" / "profile-supervisor.lock",
                    label="Application supervisor", create=True):
        yield


def _preflight_browser(root: Path) -> None:
    profile_dir = root / "hoyolab_export" / "profile"
    for path in (root / "hoyolab_export", profile_dir):
        if _is_reparse(path):
            raise RuntimeError("Browser profile path is a link or junction")
    if not profile_dir.exists():
        return
    if any(_exists(profile_dir / marker) for marker in _BROWSER_MARKERS):
        raise RuntimeError("A login browser still owns this account profile")
    from hoyolab_export.auth import AuthStatus, get_auth_status
    if get_auth_status(profile_dir) == AuthStatus.PROFILE_LOCKED:
        raise RuntimeError("A login browser still owns this account profile")


def _preflight_import_lock(root: Path) -> None:
    lock = root / "debug" / "hoyolab_import.lock"
    if _is_reparse(lock.parent) or _is_reparse(lock):
        raise RuntimeError("Import lock path is a link or junction")
    with _file_lock(lock, label="HoYoLAB import", create=False):
        pass


def _preflight_affected_profile(root: Path) -> None:
    if _is_reparse(root):
        raise RuntimeError("Account profile root is a link or junction")
    _preflight_browser(root)
    _preflight_import_lock(root)


def request_profile_operation(operation: str, profile_id: str = "") -> None:
    _validate_request(operation, profile_id)
    raw = os.environ.get(ACTION_ENV)
    if not raw:
        raise RuntimeError("Open the application through ui.app_shell_smoke to switch profiles")
    destination = Path(raw).absolute()
    expected_parent = PROJECT_ROOT / "data" / ".profile-actions"
    if (destination.parent != expected_parent or _ACTION_FILE.fullmatch(destination.name) is None
            or _is_reparse(expected_parent) or _is_reparse(destination)):
        raise RuntimeError("Invalid profile operation destination")
    if destination.exists():
        raise RuntimeError("An account operation has already been requested")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                     prefix=".request-", suffix=".tmp", delete=False) as file:
        temporary = Path(file.name)
        json.dump({"operation": operation, "profile_id": profile_id}, file)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def apply_profile_operation(operation: str, profile_id: str = "", *,
                            project_root: Path = PROJECT_ROOT) -> None:
    """Apply a request only after the previous UI process has exited."""
    _validate_request(operation, profile_id)
    project_root = Path(project_root).absolute()
    with profile_operation_lock(project_root=project_root):
        if operation == "new":
            create_profile(project_root=project_root)
        elif operation == "activate":
            _preflight_affected_profile(profile_root(profile_id, project_root=project_root))
            activate_profile(profile_id, project_root=project_root)
        elif operation == "delete":
            _preflight_affected_profile(profile_root(profile_id, project_root=project_root))
            delete_profile(profile_id, project_root=project_root)
        elif operation == "reset":
            from .profile_legacy import _checked_project_root, _preflight, clear_legacy_account_data
            for item in list_profiles(project_root=project_root):
                _preflight_affected_profile(profile_root(item["id"], project_root=project_root))
            _preflight_affected_profile(project_root)
            _preflight(_checked_project_root(project_root))
            settings = project_root / "settings.json"
            if _is_reparse(settings):
                raise RuntimeError("Settings file is a link or junction")
            clear_all_profiles(project_root=project_root)
            clear_legacy_account_data(project_root=project_root)
            reset_app_settings(settings)


def _cleanup_stale_actions(action_dir: Path) -> None:
    """Remove only prior supervisor request nodes while holding its lease."""
    for child in action_dir.iterdir():
        if _ACTION_FILE.fullmatch(child.name) or _ACTION_TEMP.fullmatch(child.name):
            if child.is_dir() and not _is_reparse(child):
                raise RuntimeError("Profile action path is unexpectedly a directory")
            child.unlink()


def supervise_app(argv: list[str]) -> int:
    """Recreate immutable account context on switch; reject another UI."""
    data = PROJECT_ROOT / "data"
    action_dir = data / ".profile-actions"
    if _is_reparse(data) or _is_reparse(action_dir):
        raise RuntimeError("Profile action directory must not be a link or junction")
    with profile_supervisor_lock(project_root=PROJECT_ROOT):
        action_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_stale_actions(action_dir)
        action_file = action_dir / f"{uuid.uuid4().hex}.json"
        environment = os.environ.copy()
        environment.pop("GTT_ACCOUNT_PROFILE", None)
        environment.pop("GTT_PROFILE_ACTION_ERROR", None)
        environment[ACTION_ENV] = str(action_file)
        try:
            while True:
                result = subprocess.run(
                    [sys.executable, "-m", "ui.app_shell_smoke", "--profile-child", *argv],
                    cwd=PROJECT_ROOT, env=environment,
                )
                if not action_file.exists():
                    return result.returncode
                try:
                    if result.returncode:
                        raise RuntimeError("The application exited unexpectedly; profile change was not applied")
                    if _is_reparse(action_file):
                        raise RuntimeError("Profile action file is a link or junction")
                    action = json.loads(action_file.read_text(encoding="utf-8"))
                    if not isinstance(action, dict) or set(action) != {"operation", "profile_id"}:
                        raise ValueError("Malformed account operation request")
                    _validate_request(action["operation"], action["profile_id"])
                    apply_profile_operation(action["operation"], action["profile_id"])
                    environment.pop("GTT_PROFILE_ACTION_ERROR", None)
                except Exception as exc:
                    environment["GTT_PROFILE_ACTION_ERROR"] = str(exc)[:500]
                    if result.returncode:
                        return result.returncode
                finally:
                    action_file.unlink(missing_ok=True)
        finally:
            action_file.unlink(missing_ok=True)


__all__ = [
    "ACTION_ENV", "OPERATIONS", "profile_operation_lock", "profile_supervisor_lock",
    "request_profile_operation", "apply_profile_operation", "supervise_app",
]
