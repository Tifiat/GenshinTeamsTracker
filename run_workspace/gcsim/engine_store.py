"""Transactional local engine-store prototype for the GCSIM integration.

This module intentionally does not download, build, or run the real GCSIM
engine yet. It pins the lifecycle contract from
`docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md`: copy an official/source-like
tree, apply a local GTT patch stack through a replaceable backend, write a
manifest, and activate the new engine only after all checks pass.

The default patch backend is a simple overlay-directory copier so tests can
exercise the transaction without requiring `git apply` or real GCSIM source.
Production-oriented git/apply patching and optional build-artifact checks live
behind the same transactional store boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Callable, Mapping, Protocol


GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION = 1
GCSIM_ENGINE_STATE_SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GCSIM_ENGINE_STORE_DIR = PROJECT_ROOT / "data" / "gcsim" / "engines"
DEFAULT_SUCCESSFUL_ENGINE_KEEP_COUNT = 2
DEFAULT_FAILED_ENGINE_KEEP_COUNT = 1
MANIFEST_FILE_NAME = "gtt_engine_manifest.json"
ACTIVE_ENGINE_FILE_NAME = "active_engine.json"
ENGINE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GcsimEngineStoreError(RuntimeError):
    """Raised for controlled engine-store failures."""


@dataclass(frozen=True, slots=True)
class GcsimPatchResult:
    applied: bool
    backend: str
    patch_count: int = 0
    warnings: tuple[str, ...] = ()
    error: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "backend": self.backend,
            "patch_count": self.patch_count,
            "warnings": list(self.warnings),
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def success(
        cls,
        *,
        backend: str,
        patch_count: int = 0,
        warnings: tuple[str, ...] = (),
        metadata: Mapping[str, str] | None = None,
    ) -> "GcsimPatchResult":
        return cls(
            applied=True,
            backend=backend,
            patch_count=int(patch_count),
            warnings=tuple(warnings),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        backend: str,
        error: str,
        patch_count: int = 0,
        warnings: tuple[str, ...] = (),
        metadata: Mapping[str, str] | None = None,
    ) -> "GcsimPatchResult":
        return cls(
            applied=False,
            backend=backend,
            patch_count=int(patch_count),
            warnings=tuple(warnings),
            error=str(error),
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class GcsimEngineManifest:
    engine_id: str
    source_label: str
    source_path: str
    source_tree_hash: str
    engine_tree_hash: str
    prepared_at_utc: str
    patch_backend: str
    patch_count: int
    patch_warnings: tuple[str, ...] = ()
    patch_metadata: Mapping[str, str] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: int = GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "source_label": self.source_label,
            "source_path": self.source_path,
            "source_tree_hash": self.source_tree_hash,
            "engine_tree_hash": self.engine_tree_hash,
            "prepared_at_utc": self.prepared_at_utc,
            "patch_backend": self.patch_backend,
            "patch_count": self.patch_count,
            "patch_warnings": list(self.patch_warnings),
            "patch_metadata": dict(self.patch_metadata),
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "GcsimEngineManifest":
        schema_version = int(data.get("schema_version", 0))
        if schema_version != GCSIM_ENGINE_MANIFEST_SCHEMA_VERSION:
            raise GcsimEngineStoreError(
                f"Unsupported GCSIM engine manifest schema: {schema_version!r}"
            )
        return cls(
            engine_id=str(data["engine_id"]),
            source_label=str(data["source_label"]),
            source_path=str(data["source_path"]),
            source_tree_hash=str(data["source_tree_hash"]),
            engine_tree_hash=str(data["engine_tree_hash"]),
            prepared_at_utc=str(data["prepared_at_utc"]),
            patch_backend=str(data["patch_backend"]),
            patch_count=int(data["patch_count"]),
            patch_warnings=tuple(str(item) for item in data.get("patch_warnings", ())),
            patch_metadata={
                str(key): str(value)
                for key, value in dict(data.get("patch_metadata", {})).items()
            },
            capabilities=tuple(str(item) for item in data.get("capabilities", ())),
            metadata={
                str(key): str(value)
                for key, value in dict(data.get("metadata", {})).items()
            },
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class GcsimEngineInstallation:
    engine_id: str
    path: Path
    manifest: GcsimEngineManifest


@dataclass(frozen=True, slots=True)
class GcsimEngineUpdateResult:
    success: bool
    activated: bool
    engine_id: str
    engine_path: Path | None
    manifest: GcsimEngineManifest | None
    patch_result: GcsimPatchResult
    previous_active_engine_id: str | None = None
    failed_engine_path: Path | None = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class GcsimEngineStorePruneResult:
    dry_run: bool
    deleted_paths: tuple[str, ...] = ()
    deleted_bytes: int = 0
    kept_successful_engine_ids: tuple[str, ...] = ()
    kept_failed_engine_ids: tuple[str, ...] = ()
    active_engine_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "deleted_paths": list(self.deleted_paths),
            "deleted_bytes": self.deleted_bytes,
            "kept_successful_engine_ids": list(self.kept_successful_engine_ids),
            "kept_failed_engine_ids": list(self.kept_failed_engine_ids),
            "active_engine_id": self.active_engine_id,
        }


class PatchBackend(Protocol):
    name: str

    def apply(self, *, engine_dir: Path, patch_stack_dir: Path | None) -> GcsimPatchResult:
        """Apply GTT patches to `engine_dir` and return a controlled result."""


class OverlayPatchBackend:
    """Test/prototype backend that overlays files from a patch-stack directory."""

    name = "overlay"

    def apply(self, *, engine_dir: Path, patch_stack_dir: Path | None) -> GcsimPatchResult:
        if patch_stack_dir is None:
            return GcsimPatchResult.success(backend=self.name, patch_count=0)
        patch_stack_dir = Path(patch_stack_dir)
        if not patch_stack_dir.exists():
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"Patch stack does not exist: {patch_stack_dir}",
            )
        if not patch_stack_dir.is_dir():
            return GcsimPatchResult.failure(
                backend=self.name,
                error=f"Patch stack is not a directory: {patch_stack_dir}",
            )

        patch_count = 0
        try:
            for source in sorted(path for path in patch_stack_dir.rglob("*") if path.is_file()):
                relative = source.relative_to(patch_stack_dir)
                target = engine_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                patch_count += 1
        except OSError as exc:
            return GcsimPatchResult.failure(
                backend=self.name,
                error=str(exc),
                patch_count=patch_count,
            )
        return GcsimPatchResult.success(backend=self.name, patch_count=patch_count)


class GcsimEngineStore:
    def __init__(self, root_dir: str | Path | None = None):
        self.root_dir = Path(root_dir) if root_dir is not None else DEFAULT_GCSIM_ENGINE_STORE_DIR
        self.engines_dir = self.root_dir / "engines"
        self.staging_dir = self.root_dir / "staging"
        self.failed_dir = self.root_dir / "failed"
        self.active_state_path = self.root_dir / ACTIVE_ENGINE_FILE_NAME

    def prepare_engine_update(
        self,
        *,
        source_dir: str | Path,
        patch_stack_dir: str | Path | None = None,
        source_label: str,
        engine_id: str | None = None,
        patch_backend: PatchBackend | None = None,
        capabilities: tuple[str, ...] = (),
        metadata: Mapping[str, str] | None = None,
        smoke_check: Callable[[Path], bool | str | None] | None = None,
    ) -> GcsimEngineUpdateResult:
        """Prepare and activate a new engine only if patch/checks succeed."""

        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise GcsimEngineStoreError(f"Source engine directory does not exist: {source_dir}")
        engine_id = engine_id or _default_engine_id(source_label)
        _validate_engine_id(engine_id)
        previous_active = self.active_engine_id()
        patch_backend = patch_backend or OverlayPatchBackend()
        patch_stack = None if patch_stack_dir is None else Path(patch_stack_dir)

        self._ensure_dirs()
        final_dir = self.engines_dir / engine_id
        staging_dir = self.staging_dir / engine_id
        failed_dir = self.failed_dir / engine_id
        if final_dir.exists():
            raise GcsimEngineStoreError(f"Engine already exists: {engine_id}")
        _safe_remove_tree(staging_dir, root=self.root_dir)

        patch_result = GcsimPatchResult.failure(
            backend=patch_backend.name,
            error="Patch step did not run.",
        )
        try:
            shutil.copytree(source_dir, staging_dir)
            patch_result = patch_backend.apply(
                engine_dir=staging_dir,
                patch_stack_dir=patch_stack,
            )
            if not patch_result.applied:
                failed_path = self._preserve_failed_engine(staging_dir, failed_dir)
                return GcsimEngineUpdateResult(
                    success=False,
                    activated=False,
                    engine_id=engine_id,
                    engine_path=None,
                    manifest=None,
                    patch_result=patch_result,
                    previous_active_engine_id=previous_active,
                    failed_engine_path=failed_path,
                    error=patch_result.error,
                )

            smoke_error = _run_smoke_check(smoke_check, staging_dir)
            if smoke_error:
                failed_path = self._preserve_failed_engine(staging_dir, failed_dir)
                return GcsimEngineUpdateResult(
                    success=False,
                    activated=False,
                    engine_id=engine_id,
                    engine_path=None,
                    manifest=None,
                    patch_result=patch_result,
                    previous_active_engine_id=previous_active,
                    failed_engine_path=failed_path,
                    error=smoke_error,
                )

            manifest = GcsimEngineManifest(
                engine_id=engine_id,
                source_label=str(source_label),
                source_path=str(source_dir.resolve()),
                source_tree_hash=_directory_sha256(source_dir),
                engine_tree_hash=_directory_sha256(staging_dir),
                prepared_at_utc=_utc_now_text(),
                patch_backend=patch_result.backend,
                patch_count=patch_result.patch_count,
                patch_warnings=patch_result.warnings,
                patch_metadata=patch_result.metadata,
                capabilities=tuple(capabilities),
                metadata=dict(metadata or {}),
            )
            _write_manifest(staging_dir / MANIFEST_FILE_NAME, manifest)
            shutil.move(str(staging_dir), str(final_dir))
            self.activate_engine(engine_id)
            return GcsimEngineUpdateResult(
                success=True,
                activated=True,
                engine_id=engine_id,
                engine_path=final_dir,
                manifest=manifest,
                patch_result=patch_result,
                previous_active_engine_id=previous_active,
            )
        except Exception as exc:  # noqa: BLE001 - transactional failure boundary.
            failed_path = (
                self._preserve_failed_engine(staging_dir, failed_dir)
                if staging_dir.exists()
                else None
            )
            return GcsimEngineUpdateResult(
                success=False,
                activated=False,
                engine_id=engine_id,
                engine_path=None,
                manifest=None,
                patch_result=patch_result,
                previous_active_engine_id=previous_active,
                failed_engine_path=failed_path,
                error=str(exc),
            )

    def activate_engine(self, engine_id: str) -> GcsimEngineInstallation:
        _validate_engine_id(engine_id)
        engine_dir = self.engines_dir / engine_id
        manifest = load_engine_manifest(engine_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": GCSIM_ENGINE_STATE_SCHEMA_VERSION,
            "active_engine_id": engine_id,
        }
        _write_json_atomic(self.active_state_path, payload)
        return GcsimEngineInstallation(
            engine_id=engine_id,
            path=engine_dir,
            manifest=manifest,
        )

    def active_engine_id(self) -> str | None:
        if not self.active_state_path.exists():
            return None
        try:
            payload = json.loads(self.active_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GcsimEngineStoreError(
                f"Could not read active GCSIM engine state: {exc}"
            ) from exc
        if payload.get("schema_version") != GCSIM_ENGINE_STATE_SCHEMA_VERSION:
            raise GcsimEngineStoreError(
                "Unsupported active GCSIM engine state schema: "
                f"{payload.get('schema_version')!r}"
            )
        engine_id = payload.get("active_engine_id")
        return str(engine_id) if engine_id else None

    def get_active_engine(self) -> GcsimEngineInstallation | None:
        engine_id = self.active_engine_id()
        if engine_id is None:
            return None
        engine_dir = self.engines_dir / engine_id
        if not engine_dir.exists():
            raise GcsimEngineStoreError(
                f"Active GCSIM engine folder is missing: {engine_id}"
            )
        return GcsimEngineInstallation(
            engine_id=engine_id,
            path=engine_dir,
            manifest=load_engine_manifest(engine_dir),
        )

    def prune_generated_state(
        self,
        *,
        keep_successful: int = DEFAULT_SUCCESSFUL_ENGINE_KEEP_COUNT,
        keep_failed: int = DEFAULT_FAILED_ENGINE_KEEP_COUNT,
        dry_run: bool = False,
    ) -> GcsimEngineStorePruneResult:
        """Prune old generated engine copies without touching the active engine."""

        self._ensure_dirs()
        active_engine_id = self.active_engine_id()
        successful_entries = _engine_dir_entries(self.engines_dir)
        failed_entries = _engine_dir_entries(self.failed_dir)

        kept_successful = _kept_successful_engine_ids(
            successful_entries,
            active_engine_id=active_engine_id,
            keep_successful=keep_successful,
        )
        kept_failed = _kept_failed_engine_ids(
            failed_entries,
            keep_failed=keep_failed,
        )
        delete_dirs: list[Path] = []
        delete_dirs.extend(
            entry
            for entry in successful_entries
            if entry.name not in set(kept_successful)
        )
        delete_dirs.extend(
            entry
            for entry in failed_entries
            if entry.name not in set(kept_failed)
        )
        delete_dirs.extend(_engine_dir_entries(self.staging_dir))

        deleted_paths: list[str] = []
        deleted_bytes = 0
        for path in delete_dirs:
            size = _directory_size(path)
            deleted_paths.append(str(path))
            deleted_bytes += size
            if not dry_run:
                _safe_remove_tree(path, root=self.root_dir)

        return GcsimEngineStorePruneResult(
            dry_run=bool(dry_run),
            deleted_paths=tuple(deleted_paths),
            deleted_bytes=deleted_bytes,
            kept_successful_engine_ids=kept_successful,
            kept_failed_engine_ids=kept_failed,
            active_engine_id=active_engine_id,
        )

    def _ensure_dirs(self) -> None:
        self.engines_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def _preserve_failed_engine(self, staging_dir: Path, failed_dir: Path) -> Path:
        if not staging_dir.exists():
            return failed_dir
        _safe_remove_tree(failed_dir, root=self.root_dir)
        failed_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging_dir), str(failed_dir))
        return failed_dir


def load_engine_manifest(engine_dir: str | Path) -> GcsimEngineManifest:
    path = Path(engine_dir) / MANIFEST_FILE_NAME
    if not path.exists():
        raise GcsimEngineStoreError(f"GCSIM engine manifest is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GcsimEngineStoreError(
            f"Could not read GCSIM engine manifest {path}: {exc}"
        ) from exc
    return GcsimEngineManifest.from_dict(payload)


def _write_manifest(path: Path, manifest: GcsimEngineManifest) -> None:
    _write_json_atomic(path, manifest.to_dict())


def _write_json_atomic(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _engine_dir_entries(path: Path) -> tuple[Path, ...]:
    if not path.exists():
        return ()
    return tuple(item for item in path.iterdir() if item.is_dir())


def _kept_successful_engine_ids(
    entries: tuple[Path, ...],
    *,
    active_engine_id: str | None,
    keep_successful: int,
) -> tuple[str, ...]:
    keep_count = max(1, int(keep_successful))
    by_name = {entry.name: entry for entry in entries}
    kept: list[str] = []
    if active_engine_id and active_engine_id in by_name:
        kept.append(active_engine_id)
    newest = sorted(
        entries,
        key=lambda item: _path_mtime(item),
        reverse=True,
    )
    for entry in newest:
        if entry.name in kept:
            continue
        if len(kept) >= keep_count:
            break
        kept.append(entry.name)
    return tuple(kept)


def _kept_failed_engine_ids(
    entries: tuple[Path, ...],
    *,
    keep_failed: int,
) -> tuple[str, ...]:
    keep_count = max(0, int(keep_failed))
    if keep_count <= 0:
        return ()
    newest = sorted(
        entries,
        key=lambda item: _path_mtime(item),
        reverse=True,
    )
    return tuple(entry.name for entry in newest[:keep_count])


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _default_engine_id(source_label: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", source_label.strip()).strip("-._")
    if not normalized:
        normalized = "engine"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{normalized}-{stamp}"


def _validate_engine_id(engine_id: str) -> None:
    if not ENGINE_ID_PATTERN.fullmatch(engine_id):
        raise GcsimEngineStoreError(
            "GCSIM engine id must contain only letters, numbers, '.', '_', or '-' "
            f"and start with a letter or number: {engine_id!r}"
        )


def _safe_remove_tree(path: Path, *, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise GcsimEngineStoreError(f"Refusing to remove path outside engine store: {path}")
    if path.exists():
        shutil.rmtree(path)


def _run_smoke_check(
    smoke_check: Callable[[Path], bool | str | None] | None,
    engine_dir: Path,
) -> str:
    if smoke_check is None:
        return ""
    try:
        result = smoke_check(engine_dir)
    except Exception as exc:  # noqa: BLE001 - smoke failures must not activate.
        return str(exc)
    if result is False:
        return "Engine smoke check returned false."
    if isinstance(result, str) and result:
        return result
    return ""


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
