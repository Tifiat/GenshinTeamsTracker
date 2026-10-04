"""Small, process-safe registry for isolated local account profile roots."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SCHEMA_VERSION = 1
_PROFILE_ID = re.compile(r"[0-9a-f]{32}\Z")
_SERVER = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
_METADATA_KEYS = frozenset({
    "uid", "server", "nickname", "world_level", "adventure_rank",
    "avatar_url", "avatar_path",
})


class AccountProfileError(RuntimeError):
    """A profile registry or filesystem operation cannot be completed safely."""


class InvalidAccountProfileRegistry(AccountProfileError):
    """The on-disk registry is malformed or points outside managed roots."""


class UnknownAccountProfile(AccountProfileError):
    """A requested profile ID is not registered."""


class DuplicateAccountProfile(AccountProfileError):
    """Another profile already owns this UID/server pair."""

    def __init__(self, existing_profile_id: str) -> None:
        self.existing_profile_id = existing_profile_id
        super().__init__(f"Account already belongs to profile {existing_profile_id}")


def _id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
        raise ValueError("Profile ID must be a lowercase 32-character UUID hex string")
    return profile_id


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _checked_root(project_root: str | Path) -> Path:
    root = Path(project_root).absolute()
    if not root.is_dir() or _is_link_or_reparse(root):
        raise AccountProfileError("Project root must be an existing ordinary directory")
    return root


def _checked_child(parent: Path, name: str) -> Path:
    child = parent / name
    if _is_link_or_reparse(child):
        raise AccountProfileError(f"Managed path is a link or junction: {child}")
    return child


def _paths(project_root: str | Path) -> tuple[Path, Path, Path]:
    root = _checked_root(project_root)
    data = _checked_child(root, "data")
    profiles = _checked_child(data, "profiles")
    registry = _checked_child(profiles, "registry.json")
    return profiles, registry, _checked_child(data, "account_profiles.lock")


def profile_root(profile_id: str, *, project_root: str | Path = PROJECT_ROOT) -> Path:
    """Return a safe physical root; callers decide when to create contents."""
    profiles, _, _ = _paths(project_root)
    return _checked_child(profiles, _id(profile_id))


def _empty_registry() -> dict[str, Any]:
    return {"schema_version": REGISTRY_SCHEMA_VERSION, "active_profile_id": None, "profiles": []}


def _clean_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    text = value.strip()
    if len(text) > limit or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError(f"{field} is too long or contains control characters")
    return text


def _clean_metadata(metadata: Mapping[str, Any], *, strict_keys: bool = False) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise ValueError("Profile metadata must be a mapping")
    if strict_keys and set(metadata) - _METADATA_KEYS:
        raise InvalidAccountProfileRegistry("Registry has unknown metadata fields")
    clean: dict[str, Any] = {}
    for key in _METADATA_KEYS:
        if key not in metadata:
            continue
        value = metadata[key]
        if value is None:
            continue
        if key == "uid":
            if isinstance(value, bool) or re.fullmatch(r"[0-9]{1,32}", str(value)) is None \
                    or int(value) <= 0:
                raise ValueError("uid must be a numeric account ID")
            clean[key] = str(int(value))
        elif key == "server":
            text = _clean_text(value, key, 32)
            if _SERVER.fullmatch(text) is None:
                raise ValueError("server has unsupported characters")
            clean[key] = text
        elif key in {"world_level", "adventure_rank"}:
            if isinstance(value, bool) or not str(value).isdigit() or int(value) > 999:
                raise ValueError(f"{key} must be an integer from 0 to 999")
            clean[key] = int(value)
        elif key == "nickname":
            clean[key] = _clean_text(value, key, 80)
        elif key == "avatar_url":
            text = _clean_text(value, key, 2048)
            parsed = urlsplit(text)
            if text and (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password):
                raise ValueError("avatar_url must be an HTTPS URL without credentials")
            clean[key] = text
        elif key == "avatar_path":
            text = _clean_text(value, key, 512)
            path = PurePosixPath(text)
            if text and ("\\" in text or ":" in text or path.is_absolute() or
                         any(part in {"", ".", ".."} for part in text.split("/"))):
                raise ValueError("avatar_path must stay inside the profile root")
            clean[key] = text
    return clean


def _validate_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "active_profile_id", "profiles"
    } or type(data["schema_version"]) is not int or data["schema_version"] != REGISTRY_SCHEMA_VERSION:
        raise InvalidAccountProfileRegistry("Unsupported or malformed profile registry")
    profiles = data["profiles"]
    if not isinstance(profiles, list):
        raise InvalidAccountProfileRegistry("Profile registry entries must be a list")
    seen_ids: set[str] = set()
    seen_accounts: set[tuple[str, str]] = set()
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {"id", "created_at", "imported", "metadata"}:
            raise InvalidAccountProfileRegistry("Malformed profile registry entry")
        try:
            profile_id = _id(item["id"])
            created = datetime.fromisoformat(item["created_at"])
            metadata = _clean_metadata(item["metadata"], strict_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidAccountProfileRegistry("Invalid profile entry data") from exc
        if created.tzinfo is None or type(item["imported"]) is not bool:
            raise InvalidAccountProfileRegistry("Profile timestamp or imported flag is invalid")
        if item["metadata"] != metadata:
            raise InvalidAccountProfileRegistry("Profile metadata is not canonical")
        if profile_id in seen_ids:
            raise InvalidAccountProfileRegistry("Duplicate profile ID")
        seen_ids.add(profile_id)
        identity = _account_identity(metadata)
        if identity is not None:
            if identity in seen_accounts:
                raise InvalidAccountProfileRegistry("Duplicate account identity in registry")
            seen_accounts.add(identity)
        if item["imported"] and identity is None:
            raise InvalidAccountProfileRegistry("Imported profile has no account identity")
    active = data["active_profile_id"]
    if active is not None and active not in seen_ids:
        raise InvalidAccountProfileRegistry("Active profile is not registered")
    return data


def _read_registry(registry_path: Path) -> dict[str, Any]:
    if not registry_path.exists():
        if registry_path.parent.is_dir() and any(
            child.name != "registry.json" and _PROFILE_ID.fullmatch(child.name)
            for child in registry_path.parent.iterdir()
        ):
            raise InvalidAccountProfileRegistry(
                "Profile directories exist without a registry; explicit recovery is required"
            )
        return _empty_registry()
    try:
        return _validate_registry(json.loads(registry_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidAccountProfileRegistry("Profile registry cannot be read") from exc


def _write_registry(registry_path: Path, registry: dict[str, Any]) -> None:
    _validate_registry(registry)
    if any(_is_link_or_reparse(path) for path in (
        registry_path.parent.parent, registry_path.parent, registry_path,
    )):
        raise AccountProfileError("Registry path became a link or junction")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=registry_path.parent,
            prefix=".registry-", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(registry, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, registry_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _mutation_lock(project_root: str | Path) -> Iterator[Path]:
    profiles, registry_path, lock_path = _paths(project_root)
    profiles.parent.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(profiles.parent):
        raise AccountProfileError("Managed data root became a link or junction")
    profiles.mkdir(exist_ok=True)
    if _is_link_or_reparse(profiles) or _is_link_or_reparse(lock_path):
        raise AccountProfileError("Managed registry or lock path is a link or junction")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    with os.fdopen(descriptor, "r+b") as lock_file:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EDEADLK}:
                        raise
                    time.sleep(0.05)
            try:
                yield registry_path
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield registry_path
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _entry(registry: dict[str, Any], profile_id: str) -> dict[str, Any]:
    for item in registry["profiles"]:
        if item["id"] == profile_id:
            return item
    raise UnknownAccountProfile(f"Unknown account profile: {profile_id}")


def _account_identity(metadata: Mapping[str, Any]) -> tuple[str, str] | None:
    uid = str(metadata.get("uid") or "")
    server = str(metadata.get("server") or "").casefold()
    return (uid, server) if uid and server else None


def _check_duplicate(registry: dict[str, Any], profile_id: str, metadata: Mapping[str, Any]) -> None:
    identity = _account_identity(metadata)
    if identity is None:
        return
    for item in registry["profiles"]:
        if item["id"] != profile_id and _account_identity(item["metadata"]) == identity:
            raise DuplicateAccountProfile(item["id"])


def list_profiles(*, project_root: str | Path = PROJECT_ROOT,
                  include_drafts: bool = True) -> list[dict[str, Any]]:
    """Read registered profiles without creating directories or files."""
    _, registry_path, _ = _paths(project_root)
    registry = _read_registry(registry_path)
    return [json.loads(json.dumps(item)) for item in registry["profiles"]
            if include_drafts or item["imported"]]


def active_profile(*, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any] | None:
    _, registry_path, _ = _paths(project_root)
    registry = _read_registry(registry_path)
    active = registry["active_profile_id"]
    if active and not profile_root(active, project_root=project_root).is_dir():
        raise InvalidAccountProfileRegistry("Active profile directory is missing")
    return json.loads(json.dumps(_entry(registry, active))) if active else None


def _new_entry() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "imported": False,
        "metadata": {},
    }


def _create_locked(registry: dict[str, Any], registry_path: Path, *, activate: bool) -> dict[str, Any]:
    entry = _new_entry()
    root = profile_root(entry["id"], project_root=registry_path.parent.parent.parent)
    root.mkdir()
    registry["profiles"].append(entry)
    if activate:
        registry["active_profile_id"] = entry["id"]
    try:
        _write_registry(registry_path, registry)
    except Exception:
        root.rmdir()
        raise
    return json.loads(json.dumps(entry))


def create_profile(*, project_root: str | Path = PROJECT_ROOT,
                   activate: bool = True) -> dict[str, Any]:
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        return _create_locked(registry, registry_path, activate=activate)


def ensure_active_profile(*, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    """Create a draft only if no profile exists; otherwise activate the oldest."""
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        active = registry["active_profile_id"]
        if active:
            if not profile_root(active, project_root=project_root).is_dir():
                raise InvalidAccountProfileRegistry("Active profile directory is missing")
            return json.loads(json.dumps(_entry(registry, active)))
        if registry["profiles"]:
            chosen = min(registry["profiles"], key=lambda item: (item["created_at"], item["id"]))
            if not profile_root(chosen["id"], project_root=project_root).is_dir():
                raise InvalidAccountProfileRegistry("Registered profile directory is missing")
            registry["active_profile_id"] = chosen["id"]
            _write_registry(registry_path, registry)
            return json.loads(json.dumps(chosen))
        return _create_locked(registry, registry_path, activate=True)


def activate_profile(profile_id: str, *, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    profile_id = _id(profile_id)
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        entry = _entry(registry, profile_id)
        root = profile_root(profile_id, project_root=project_root)
        if not root.is_dir():
            raise AccountProfileError("Registered profile directory is missing")
        if registry["active_profile_id"] != profile_id:
            registry["active_profile_id"] = profile_id
            _write_registry(registry_path, registry)
        return json.loads(json.dumps(entry))


def update_profile_metadata(
    profile_id: str, metadata: Mapping[str, Any], *,
    project_root: str | Path = PROJECT_ROOT, imported: bool | None = None,
) -> dict[str, Any]:
    profile_id = _id(profile_id)
    cleaned = _clean_metadata(metadata)
    if imported is not None and type(imported) is not bool:
        raise ValueError("imported must be a boolean")
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        entry = _entry(registry, profile_id)
        merged = dict(entry["metadata"])
        merged.update(cleaned)
        _check_duplicate(registry, profile_id, merged)
        if imported and _account_identity(merged) is None:
            raise ValueError("Imported profile requires UID and server")
        if imported is False and entry["imported"]:
            raise ValueError("An imported profile cannot become a draft")
        entry["metadata"] = merged
        if imported is not None:
            entry["imported"] = imported
        _write_registry(registry_path, registry)
        return json.loads(json.dumps(entry))


def _delete_tree_safely(root: Path) -> None:
    if not root.exists() and not _is_link_or_reparse(root):
        return
    if _is_link_or_reparse(root) or not root.is_dir():
        raise AccountProfileError("Profile root is a link, junction, or non-directory")

    # Preflight first so a link anywhere in a profile cannot cause partial
    # deletion before the unsafe node is discovered.
    def preflight(folder: Path) -> None:
        for child in folder.iterdir():
            if _is_link_or_reparse(child):
                raise AccountProfileError(f"Profile contains a link or junction: {child}")
            if child.is_dir():
                preflight(child)

    def remove(folder: Path) -> None:
        for child in folder.iterdir():
            if _is_link_or_reparse(child):
                raise AccountProfileError(f"Profile changed during deletion: {child}")
            if child.is_dir():
                remove(child)
            else:
                child.unlink()
        folder.rmdir()

    preflight(root)
    remove(root)


def delete_profile(profile_id: str, *, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    profile_id = _id(profile_id)
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        _entry(registry, profile_id)
        _delete_tree_safely(profile_root(profile_id, project_root=project_root))
        registry["profiles"] = [item for item in registry["profiles"] if item["id"] != profile_id]
        if registry["active_profile_id"] == profile_id:
            remaining = registry["profiles"]
            chosen = min(remaining, key=lambda item: (item["created_at"], item["id"])) if remaining else None
            registry["active_profile_id"] = chosen["id"] if chosen else None
        _write_registry(registry_path, registry)
        return {
            "deleted_profile_id": profile_id,
            "active_profile_id": registry["active_profile_id"],
            "remaining_profiles": len(registry["profiles"]),
        }


def clear_all_profiles(*, project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    """Delete registered profile roots and registry, leaving settings alone."""
    with _mutation_lock(project_root) as registry_path:
        registry = _read_registry(registry_path)
        deleted: list[str] = []
        for item in list(registry["profiles"]):
            profile_id = item["id"]
            _delete_tree_safely(profile_root(profile_id, project_root=project_root))
            registry["profiles"] = [row for row in registry["profiles"] if row["id"] != profile_id]
            if registry["active_profile_id"] == profile_id:
                registry["active_profile_id"] = None
            _write_registry(registry_path, registry)
            deleted.append(profile_id)
        registry_path.unlink(missing_ok=True)
        return {"deleted_profile_ids": deleted, "active_profile_id": None}


__all__ = [
    "AccountProfileError", "DuplicateAccountProfile", "InvalidAccountProfileRegistry",
    "UnknownAccountProfile", "PROJECT_ROOT", "REGISTRY_SCHEMA_VERSION",
    "profile_root", "list_profiles", "active_profile", "ensure_active_profile",
    "create_profile", "activate_profile", "update_profile_metadata",
    "delete_profile", "clear_all_profiles",
]
