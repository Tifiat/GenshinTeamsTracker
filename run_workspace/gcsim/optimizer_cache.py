"""Content-addressed persistent cache primitives for GCSIM optimizer work."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Mapping, Sequence
import uuid

from .engine_store import PROJECT_ROOT


GCSIM_OPTIMIZER_CACHE_SCHEMA_VERSION = 1
DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "gcsim_optimizer"
DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES = 20_000
DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_GCSIM_OPTIMIZER_CACHE_PRUNE_INTERVAL_SECONDS = 5 * 60
DEFAULT_GCSIM_OPTIMIZER_CACHE_STALE_TEMP_SECONDS = 60 * 60
_GCSIM_OPTIMIZER_CACHE_RETENTION_MARKER = ".retention-check"
_GCSIM_OPTIMIZER_CACHE_RETENTION_LOCK = threading.Lock()


class GcsimOptimizerCacheError(RuntimeError):
    """Raised when a cache entry cannot be safely persisted."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCachePruneResult:
    status: str
    dry_run: bool
    root: str
    deleted_paths: tuple[str, ...] = ()
    deleted_bytes: int = 0
    kept_count: int = 0
    kept_bytes: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "root": self.root,
            "deleted_paths": list(self.deleted_paths),
            "deleted_bytes": self.deleted_bytes,
            "kept_count": self.kept_count,
            "kept_bytes": self.kept_bytes,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCacheIdentity:
    engine_sha256: str
    engine_version: str
    source_config_sha256: str
    mode: str
    optimizer_options: tuple[tuple[str, str], ...] = ()
    catalog_fingerprint: str = ""
    candidate_key: str = ""
    schema_version: int = GCSIM_OPTIMIZER_CACHE_SCHEMA_VERSION

    @property
    def cache_key(self) -> str:
        payload = _canonical_json(self.to_dict()).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": int(self.schema_version),
            "engine_sha256": self.engine_sha256,
            "engine_version": self.engine_version,
            "source_config_sha256": self.source_config_sha256,
            "mode": self.mode,
            "optimizer_options": [list(item) for item in self.optimizer_options],
            "catalog_fingerprint": self.catalog_fingerprint,
            "candidate_key": self.candidate_key,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "GcsimOptimizerCacheIdentity":
        raw_options = payload.get("optimizer_options", ())
        options: list[tuple[str, str]] = []
        if isinstance(raw_options, Sequence) and not isinstance(raw_options, (str, bytes)):
            for item in raw_options:
                if (
                    isinstance(item, Sequence)
                    and not isinstance(item, (str, bytes))
                    and len(item) == 2
                ):
                    options.append((str(item[0]), str(item[1])))
        return cls(
            schema_version=int(payload.get("schema_version", 0) or 0),
            engine_sha256=str(payload.get("engine_sha256", "")),
            engine_version=str(payload.get("engine_version", "")),
            source_config_sha256=str(payload.get("source_config_sha256", "")),
            mode=str(payload.get("mode", "")),
            optimizer_options=tuple(options),
            catalog_fingerprint=str(payload.get("catalog_fingerprint", "")),
            candidate_key=str(payload.get("candidate_key", "")),
        )


class GcsimOptimizerCacheStore:
    def __init__(
        self,
        root: str | Path = DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR,
        *,
        max_entries: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES,
        max_bytes: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES,
        prune_interval_seconds: float = (
            DEFAULT_GCSIM_OPTIMIZER_CACHE_PRUNE_INTERVAL_SECONDS
        ),
        auto_prune: bool = True,
    ) -> None:
        self.root = Path(root)
        self.max_entries = max(0, int(max_entries))
        self.max_bytes = max(0, int(max_bytes))
        self.prune_interval_seconds = max(0.0, float(prune_interval_seconds))
        self.auto_prune = bool(auto_prune)

    def get(self, identity: GcsimOptimizerCacheIdentity) -> dict[str, object] | None:
        path = self._entry_path(identity.cache_key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        raw_identity = payload.get("identity")
        result = payload.get("result")
        if not isinstance(raw_identity, dict) or not isinstance(result, dict):
            return None
        try:
            parsed_identity = GcsimOptimizerCacheIdentity.from_dict(raw_identity)
        except (TypeError, ValueError):
            return None
        if parsed_identity != identity or parsed_identity.cache_key != identity.cache_key:
            return None
        return dict(result)

    def put(
        self,
        identity: GcsimOptimizerCacheIdentity,
        result: Mapping[str, object],
    ) -> Path:
        if identity.schema_version != GCSIM_OPTIMIZER_CACHE_SCHEMA_VERSION:
            raise GcsimOptimizerCacheError(
                f"Unsupported optimizer cache schema: {identity.schema_version}"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._entry_path(identity.cache_key)
        payload = {
            "identity": identity.to_dict(),
            "result": dict(result),
        }
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp, path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise GcsimOptimizerCacheError(
                f"Could not write optimizer cache entry {path}: {exc}"
            ) from exc
        self._maybe_prune()
        return path

    def prune(self, *, dry_run: bool = False) -> GcsimOptimizerCachePruneResult:
        return prune_gcsim_optimizer_cache(
            cache_root=self.root,
            max_entries=self.max_entries,
            max_total_bytes=self.max_bytes,
            dry_run=dry_run,
        )

    def _entry_path(self, cache_key: str) -> Path:
        return self.root / f"{cache_key}.json"

    def _maybe_prune(self) -> None:
        if not self.auto_prune:
            return
        marker = self.root / _GCSIM_OPTIMIZER_CACHE_RETENTION_MARKER
        try:
            with _GCSIM_OPTIMIZER_CACHE_RETENTION_LOCK:
                now = time.time()
                try:
                    marker_age = now - marker.stat().st_mtime
                except FileNotFoundError:
                    marker_age = self.prune_interval_seconds
                if 0 <= marker_age < self.prune_interval_seconds:
                    return
                # Mark the check before the O(n) scan so concurrent stores skip it.
                marker.touch()
                self.prune()
        except (OSError, RuntimeError):
            # Retention is best-effort and must never turn a valid simulation
            # result into a cache-write failure.
            return


def prune_gcsim_optimizer_cache(
    *,
    cache_root: str | Path = DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR,
    max_entries: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_GCSIM_OPTIMIZER_CACHE_MAX_BYTES,
    stale_temp_seconds: float = DEFAULT_GCSIM_OPTIMIZER_CACHE_STALE_TEMP_SECONDS,
    dry_run: bool = False,
) -> GcsimOptimizerCachePruneResult:
    """Bound persistent cache files while preserving the newest reusable entries."""

    root = Path(cache_root)
    if not root.exists():
        return GcsimOptimizerCachePruneResult(
            status="missing",
            dry_run=bool(dry_run),
            root=str(root),
        )
    if not root.is_dir():
        return GcsimOptimizerCachePruneResult(
            status="invalid_path",
            dry_run=bool(dry_run),
            root=str(root),
            error="GCSIM optimizer cache root exists but is not a directory.",
        )

    entries: list[tuple[Path, int, float]] = []
    stale_temps: list[tuple[Path, int]] = []
    now = time.time()
    stale_after = max(0.0, float(stale_temp_seconds))
    for path in root.iterdir():
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.suffix == ".json":
            entries.append((path, int(stat.st_size), float(stat.st_mtime)))
        elif path.suffix == ".tmp" and now - stat.st_mtime >= stale_after:
            stale_temps.append((path, int(stat.st_size)))

    newest = sorted(
        entries,
        key=lambda item: (item[2], item[0].name),
        reverse=True,
    )
    entry_limit = max(0, int(max_entries))
    byte_limit = max(0, int(max_total_bytes))
    kept: list[tuple[Path, int]] = []
    deleted: list[tuple[Path, int]] = []
    kept_bytes = 0
    for path, size, _mtime in newest:
        within_count = len(kept) < entry_limit
        within_bytes = kept_bytes + size <= byte_limit
        if within_count and within_bytes:
            kept.append((path, size))
            kept_bytes += size
        else:
            deleted.append((path, size))
    deleted.extend(stale_temps)

    deleted_paths: list[str] = []
    deleted_bytes = 0
    for path, size in deleted:
        deleted_paths.append(str(path))
        deleted_bytes += size
        if not dry_run:
            _safe_remove_cache_file(path, root=root)

    return GcsimOptimizerCachePruneResult(
        status="dry_run" if dry_run else "pruned",
        dry_run=bool(dry_run),
        root=str(root),
        deleted_paths=tuple(deleted_paths),
        deleted_bytes=deleted_bytes,
        kept_count=len(kept),
        kept_bytes=kept_bytes,
    )


def _safe_remove_cache_file(path: Path, *, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path.parent != resolved_root:
        raise RuntimeError(
            f"Refusing to remove path outside GCSIM optimizer cache root: {path}"
        )
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def build_gcsim_optimizer_cache_identity(
    *,
    engine_path: str | Path,
    engine_version: str,
    source_config_text: str,
    mode: str,
    optimizer_options: Mapping[str, object] | Sequence[tuple[str, object]] = (),
    catalog_fingerprint: str = "",
    candidate_key: str = "",
) -> GcsimOptimizerCacheIdentity:
    artifact = Path(engine_path)
    engine_sha256 = _sha256_file(artifact)
    return build_gcsim_optimizer_cache_identity_from_sha256(
        engine_sha256=engine_sha256,
        engine_version=engine_version,
        source_config_text=source_config_text,
        mode=mode,
        optimizer_options=optimizer_options,
        catalog_fingerprint=catalog_fingerprint,
        candidate_key=candidate_key,
    )


def build_gcsim_optimizer_cache_identity_from_sha256(
    *,
    engine_sha256: str,
    engine_version: str,
    source_config_text: str,
    mode: str,
    optimizer_options: Mapping[str, object] | Sequence[tuple[str, object]] = (),
    catalog_fingerprint: str = "",
    candidate_key: str = "",
) -> GcsimOptimizerCacheIdentity:
    """Build cache identity from an already verified immutable engine digest."""

    source_config_sha256 = hashlib.sha256(
        str(source_config_text).encode("utf-8")
    ).hexdigest()
    if isinstance(optimizer_options, Mapping):
        raw_options = optimizer_options.items()
    else:
        raw_options = optimizer_options
    normalized_options = tuple(
        sorted(
            ((str(key), _stable_option_value(value)) for key, value in raw_options),
            key=lambda item: (item[0], item[1]),
        )
    )
    return GcsimOptimizerCacheIdentity(
        engine_sha256=str(engine_sha256),
        engine_version=str(engine_version),
        source_config_sha256=source_config_sha256,
        mode=str(mode),
        optimizer_options=normalized_options,
        catalog_fingerprint=str(catalog_fingerprint),
        candidate_key=str(candidate_key),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_option_value(value: object) -> str:
    if value is None or isinstance(value, (str, int, float, bool)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _canonical_json(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
