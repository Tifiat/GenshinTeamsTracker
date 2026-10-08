"""Bounded, identity-scoped character options from gcsim's structured docs.

These tables describe editor choices; they do not establish runtime mechanics.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
import time
from typing import Callable, Mapping
from urllib.request import urlopen
from uuid import uuid4


_TABLES = ("Actions", "Params", "Fields")
_RELATIVE = Path("ui/packages/docs/src/components")
_MAX_TABLE_BYTES = 2 * 1024 * 1024
_MAX_ITEMS = 256
_MAX_CHARACTERS = 512
_REVISION = re.compile(r"[0-9a-fA-F]{40}\Z")
_KEY = re.compile(r"[a-z0-9_]{1,80}\Z")
_ACTIVE_TEMPS: set[Path] = set()
_ACTIVE_TEMPS_LOCK = RLock()
_TEMP_MAX_AGE_SECONDS = 3600


def _string(value: object, label: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"invalid {label}")
    return value


@dataclass(frozen=True)
class EngineIdentity:
    engine_id: str
    source_fingerprint: str
    source_revision: str = ""

    def __post_init__(self) -> None:
        _string(self.engine_id, "engine id", 160)
        _string(self.source_fingerprint, "source fingerprint", 160)
        if not self.engine_id or not self.source_fingerprint:
            raise ValueError("engine identity is incomplete")
        if self.source_revision and not _REVISION.fullmatch(self.source_revision):
            raise ValueError("source revision must be a pinned 40-hex commit")


@dataclass(frozen=True)
class ActionOption:
    name: str
    invalid: bool
    note: str = ""


@dataclass(frozen=True)
class ParameterOption:
    action: str
    key: str
    description: str


@dataclass(frozen=True)
class FieldOption:
    key: str
    description: str


@dataclass(frozen=True)
class CharacterOptions:
    character_key: str
    identity: EngineIdentity
    actions: tuple[ActionOption, ...]
    parameters: tuple[ParameterOption, ...]
    fields: tuple[FieldOption, ...]
    origin: str
    warnings: tuple[str, ...] = ()


Tables = tuple[Mapping[str, object] | None, Mapping[str, object] | None, Mapping[str, object] | None]
Loader = Callable[[EngineIdentity], Tables]
FetchLoader = Callable[[EngineIdentity, tuple[str, ...]], Tables]


def _rows(table: Mapping[str, object], key: str) -> list[object]:
    if len(table) > _MAX_CHARACTERS:
        raise ValueError("character table exceeds limit")
    value = table.get(key, [])
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise ValueError("invalid character rows")
    return value


def read_character_options(
    identity: EngineIdentity,
    key: str,
    actions_mapping: Mapping[str, object],
    params_mapping: Mapping[str, object],
    fields_mapping: Mapping[str, object],
) -> CharacterOptions:
    """Validate source rows and retain only explicit documented options."""
    if not isinstance(identity, EngineIdentity) or not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("invalid character identity")
    if not all(isinstance(t, Mapping) for t in (actions_mapping, params_mapping, fields_mapping)):
        raise ValueError("invalid option table")
    if key not in actions_mapping:
        return CharacterOptions(key, identity, (), (), (), "unavailable", ("character_unknown",))
    actions = []
    for row in _rows(actions_mapping, key):
        if not isinstance(row, dict) or not isinstance(row.get("invalid"), bool):
            raise ValueError("invalid action row")
        actions.append(ActionOption(_string(row.get("ability"), "ability", 128), row["invalid"], _string(row.get("note", ""), "note")))
    parameters = []
    for row in _rows(params_mapping, key):
        if not isinstance(row, dict):
            raise ValueError("invalid parameter row")
        parameters.append(ParameterOption(_string(row.get("ability"), "ability", 128), _string(row.get("param"), "parameter", 128), _string(row.get("desc"), "description")))
    fields = []
    for row in _rows(fields_mapping, key):
        if not isinstance(row, dict):
            raise ValueError("invalid field row")
        fields.append(FieldOption(_string(row.get("field"), "field", 256), _string(row.get("desc"), "description")))
    return CharacterOptions(key, identity, tuple(actions), tuple(parameters), tuple(fields), "source")


def _read_json_bytes(data: bytes) -> Mapping[str, object]:
    if len(data) > _MAX_TABLE_BYTES:
        raise ValueError("option table exceeds byte limit")
    value = json.loads(data)
    if not isinstance(value, dict) or len(value) > _MAX_CHARACTERS:
        raise ValueError("invalid option table")
    return value


def load_local_tables(engine_root: Path) -> Tables:
    """Read only the three docs tables below an explicitly supplied engine root."""
    root = Path(engine_root)
    tables: list[Mapping[str, object] | None] = []
    for name in _TABLES:
        path = root / _RELATIVE / name / "character.dm.json"
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_TABLE_BYTES:
                raise ValueError("unsafe or oversized option table")
            with path.open("rb") as stream:
                tables.append(_read_json_bytes(stream.read(_MAX_TABLE_BYTES + 1)))
        except FileNotFoundError:
            tables.append(None)
    return tuple(tables)  # type: ignore[return-value]


def fetch_pinned_tables(
    identity: EngineIdentity,
    names: tuple[str, ...] = _TABLES,
    *,
    opener: Callable[..., object] = urlopen,
    timeout: float = 5.0,
) -> Tables:
    """Fetch metadata only from an explicitly pinned official source commit."""
    if not identity.source_revision:
        return (None, None, None)
    if not 0 < timeout <= 30:
        raise ValueError("invalid timeout")
    if any(name not in _TABLES for name in names):
        raise ValueError("invalid option table name")
    base = f"https://raw.githubusercontent.com/genshinsim/gcsim/{identity.source_revision}/ui/packages/docs/src/components"
    tables = []
    for name in _TABLES:
        if name in names:
            try:
                response = opener(f"{base}/{name}/character.dm.json", timeout=timeout)
                with response:
                    tables.append(_read_json_bytes(response.read(_MAX_TABLE_BYTES + 1)))
            except OSError:
                tables.append(None)
        else:
            tables.append(None)
    return tuple(tables)  # type: ignore[return-value]


class OptionCache:
    """Owns only versioned option files inside its injected directory."""

    SCHEMA = 1
    _PREFIX = "options-v1-"

    def __init__(self, root: Path, *, max_entries: int = 32, max_bytes: int = 4 * 1024 * 1024) -> None:
        if max_entries < 1 or max_bytes < 1024:
            raise ValueError("invalid cache limits")
        self.root = Path(root)
        self._PREFIX = f"options-v{self.SCHEMA}-"
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("cache root cannot be a symlink")
        self.cleanup()

    def _path(self, identity: EngineIdentity, key: str) -> Path:
        digest = sha256(json.dumps([asdict(identity), key], sort_keys=True).encode()).hexdigest()
        return self.root / f"{self._PREFIX}{digest}.json"

    def get(self, identity: EngineIdentity, key: str) -> CharacterOptions | None:
        path = self._path(identity, key)
        try:
            if path.is_symlink() or path.stat().st_size > self.max_bytes:
                return None
            raw = path.read_bytes()
            envelope = json.loads(raw)
            payload = envelope["payload"]
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            if envelope["schema"] != self.SCHEMA or envelope["checksum"] != sha256(canonical).hexdigest():
                return None
            if payload["identity"] != asdict(identity) or payload["character_key"] != key:
                return None
            actions = tuple(ActionOption(**x) for x in payload["actions"])
            params = tuple(ParameterOption(**x) for x in payload["parameters"])
            fields = tuple(FieldOption(**x) for x in payload["fields"])
            if any(len(x) > _MAX_ITEMS for x in (actions, params, fields)):
                return None
            if any(not isinstance(x.invalid, bool) for x in actions):
                return None
            for x in actions:
                _string(x.name, "ability", 128)
                _string(x.note, "note")
            for x in params:
                _string(x.action, "ability", 128)
                _string(x.key, "parameter", 128)
                _string(x.description, "description")
            for x in fields:
                _string(x.key, "field", 256)
                _string(x.description, "description")
            if not isinstance(payload["warnings"], list) or len(payload["warnings"]) > 8:
                return None
            for warning in payload["warnings"]:
                _string(warning, "warning", 256)
            return CharacterOptions(key, identity, actions, params, fields, "cache", tuple(payload["warnings"]))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def save(self, options: CharacterOptions) -> None:
        if options.origin in ("unavailable", "partial") or options.warnings:
            return
        payload = asdict(options)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        envelope = {"schema": self.SCHEMA, "checksum": sha256(canonical).hexdigest(), "payload": payload}
        data = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        if len(data) > self.max_bytes:
            return
        path = self._path(options.identity, options.character_key)
        temp = self.root / f"{self._PREFIX}{path.stem[len(self._PREFIX):]}.{uuid4().hex}.tmp"
        with self._lock:
            with _ACTIVE_TEMPS_LOCK:
                _ACTIVE_TEMPS.add(temp)
            try:
                with temp.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, path)
            finally:
                if temp.exists() and not temp.is_symlink():
                    temp.unlink()
                with _ACTIVE_TEMPS_LOCK:
                    _ACTIVE_TEMPS.discard(temp)
            self._cleanup_unlocked(protect=path)

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_unlocked()

    def _cleanup_unlocked(self, protect: Path | None = None) -> None:
        entries = []
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            managed = re.fullmatch(r"options-v([0-9]+)-[0-9a-f]{64}(?:\.[0-9a-f]{32})?\.(json|tmp)", path.name)
            if not managed or int(managed.group(1)) > self.SCHEMA:
                continue
            if int(managed.group(1)) < self.SCHEMA:
                path.unlink(missing_ok=True)
                continue
            suffix = path.suffix
            if suffix == ".tmp":
                with _ACTIVE_TEMPS_LOCK:
                    active = path in _ACTIVE_TEMPS
                try:
                    stale = time.time() - path.stat().st_mtime >= _TEMP_MAX_AGE_SECONDS
                except FileNotFoundError:
                    continue
                if not active and stale:
                    path.unlink(missing_ok=True)
            elif suffix == ".json" and re.fullmatch(r"options-v[0-9]+-[0-9a-f]{64}\.json", path.name):
                entries.append(path)
        def priority(path: Path) -> tuple[bool, float]:
            try:
                return path == protect, path.stat().st_mtime
            except FileNotFoundError:
                return False, -1
        entries.sort(key=priority, reverse=True)
        total = 0
        for index, path in enumerate(entries):
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue
            if index < self.max_entries and total + size <= self.max_bytes:
                total += size
            else:
                path.unlink(missing_ok=True)


class CharacterOptionService:
    """Asynchronously resolve options for the current engine identity."""

    def __init__(self, local_loader: Loader, cache: OptionCache, *, fetch_loader: FetchLoader | None = None, workers: int = 2) -> None:
        if workers not in (1, 2):
            raise ValueError("workers must be 1 or 2")
        self._local = local_loader
        self._fetch = fetch_loader
        self._cache = cache
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gcsim-options")
        self._lock = RLock()
        self._active: EngineIdentity | None = None
        self._pending: dict[tuple[EngineIdentity, str], Future[CharacterOptions]] = {}
        self._attempts: dict[tuple[EngineIdentity, str], int] = {}
        self._ready: dict[str, CharacterOptions] = {}
        self._tables_identity: EngineIdentity | None = None
        self._tables_future: Future[Tables] | None = None
        self._scheduled = 0
        self._closed = False

    def prepare(self, identity: EngineIdentity, characters: list[str] | tuple[str, ...]) -> dict[str, Future[CharacterOptions]]:
        if len(characters) > _MAX_CHARACTERS:
            raise ValueError("too many characters")
        return {key: self.select_character(identity, key) for key in characters}

    def select_character(self, identity: EngineIdentity, key: str, *, retry: bool = False) -> Future[CharacterOptions]:
        if not isinstance(identity, EngineIdentity) or not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ValueError("invalid selection")
        with self._lock:
            if self._closed:
                raise RuntimeError("service is closed")
            if identity != self._active:
                for stale in self._pending.values():
                    stale.cancel()
                self._active = identity
                self._ready.clear()
                self._pending.clear()
                self._attempts.clear()
                self._tables_identity = None
                self._tables_future = None
            request = (identity, key)
            if request not in self._pending and len(self._pending) >= _MAX_CHARACTERS:
                raise ValueError("too many selected characters")
            old = self._pending.get(request)
            if old is not None and not old.cancelled() and (not retry or not old.done()):
                if old.done() and key not in self._ready:
                    self._ready[key] = old.result()
                return old
            if old is not None and self._attempts.get(request, 0) >= 2:
                return old
            if self._scheduled >= 64:
                busy: Future[CharacterOptions] = Future()
                busy.set_result(CharacterOptions(key, identity, (), (), (), "unavailable", ("service_busy",)))
                return busy
            if retry:
                self._tables_identity = None
                self._tables_future = None
            future: Future[CharacterOptions] = Future()
            self._attempts[request] = self._attempts.get(request, 0) + 1
            self._pending[request] = future
            future.add_done_callback(lambda done, pair=request: self._finished(pair, done))
            self._scheduled += 1
            self._executor.submit(self._run_request, identity, key, future)
            return future

    def _run_request(self, identity: EngineIdentity, key: str, future: Future[CharacterOptions]) -> None:
        try:
            if not future.set_running_or_notify_cancel():
                return
            future.set_result(self._resolve(identity, key))
        finally:
            with self._lock:
                self._scheduled -= 1

    def _load_local_once(self, identity: EngineIdentity) -> Tables:
        with self._lock:
            if identity != self._active:
                stale = True
                producer = False
                shared = None
            elif self._tables_identity != identity or self._tables_future is None:
                stale = False
                self._tables_identity = identity
                self._tables_future = Future()
                producer = True
                shared = self._tables_future
            else:
                stale = False
                producer = False
                shared = self._tables_future
        if stale:
            return self._local(identity)
        if producer:
            try:
                loaded = self._local(identity)
                if len(loaded) != 3:
                    raise ValueError("local loader must return three tables")
                shared.set_result(loaded)
            except Exception as error:
                shared.set_exception(error)
        return shared.result()

    def _resolve(self, identity: EngineIdentity, key: str) -> CharacterOptions:
        try:
            self._cache.cleanup()
            cached = self._cache.get(identity, key)
            if cached is not None:
                return cached
            local = self._load_local_once(identity)
            tables = local
            new_character = tables[0] is not None and key not in tables[0]
            missing = tuple(name for i, name in enumerate(_TABLES) if tables[i] is None or new_character)
            fetched = False
            fetch_failed = False
            if self._fetch is not None and identity.source_revision and missing:
                try:
                    remote = self._fetch(identity, missing)
                    if len(remote) != 3:
                        raise ValueError("fetch loader must return three tables")
                    tables = tuple(remote[i] if _TABLES[i] in missing and remote[i] is not None else tables[i] for i in range(3))
                    fetched = any(remote[i] is not None for i, name in enumerate(_TABLES) if name in missing)
                except Exception:
                    fetch_failed = True
            if tables[0] is None:
                return CharacterOptions(key, identity, (), (), (), "unavailable", ("actions_unavailable",))
            warnings = tuple(f"{name.lower()}_unavailable" for i, name in enumerate(_TABLES) if tables[i] is None)
            if fetch_failed:
                warnings += ("fetch_failed",)
            result = read_character_options(identity, key, tables[0], tables[1] or {}, tables[2] or {})
            if result.origin != "unavailable":
                origin = "partial" if warnings else "mixed" if fetched and len(missing) < 3 else "official" if fetched else "local"
                result = replace(result, origin=origin, warnings=warnings)
                if not warnings:
                    try:
                        self._cache.save(result)
                    except OSError:
                        pass
            return result
        except Exception:
            return CharacterOptions(key, identity, (), (), (), "unavailable", ("source_error",))

    def _finished(self, pair: tuple[EngineIdentity, str], future: Future[CharacterOptions]) -> None:
        if future.cancelled():
            return
        result = future.result()
        with self._lock:
            if self._active == pair[0] and self._pending.get(pair) is future:
                self._ready[pair[1]] = result

    def result(self, identity: EngineIdentity, key: str) -> CharacterOptions | None:
        with self._lock:
            if identity != self._active:
                return None
            pending = self._pending.get((identity, key))
            if key not in self._ready and pending is not None and pending.done() and not pending.cancelled():
                self._ready[key] = pending.result()
            return self._ready.get(key)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> CharacterOptionService:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
