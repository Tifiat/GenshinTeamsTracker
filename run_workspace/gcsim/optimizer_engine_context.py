"""Verified engine/source binding for production optimizer work.

The set catalog, executable, and manifest must describe one prepared engine
snapshot.  Low-level renderers and runners remain useful for tests, but a
cacheable/searchable optimizer operation should start from this context so it
cannot validate sets against one source tree and execute another binary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .artifact_set_catalog import (
    GcsimArtifactSetCatalog,
    load_gcsim_artifact_set_catalog,
)
from .engine_store import (
    DEFAULT_GCSIM_ENGINE_STORE_DIR,
    MANIFEST_FILE_NAME,
    GcsimEngineInstallation,
    GcsimEngineManifest,
    GcsimEngineStore,
    GcsimEngineStoreError,
)


class GcsimOptimizerEngineContextError(RuntimeError):
    """Raised when executable and source provenance cannot be bound safely."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerEngineContext:
    engine_id: str
    engine_root: str
    engine_version: str
    optimizer_contract_version: str
    artifact_path: str
    artifact_sha256: str
    engine_tree_sha256: str
    catalog: GcsimArtifactSetCatalog
    manifest_artifact_sha256: str
    manifest_engine_tree_sha256: str
    binding_sha256: str
    trusted: bool
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "engine_id": self.engine_id,
            "engine_root": self.engine_root,
            "engine_version": self.engine_version,
            "optimizer_contract_version": self.optimizer_contract_version,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "engine_tree_sha256": self.engine_tree_sha256,
            "catalog_fingerprint": self.catalog.source_fingerprint,
            "manifest_artifact_sha256": self.manifest_artifact_sha256,
            "manifest_engine_tree_sha256": self.manifest_engine_tree_sha256,
            "binding_sha256": self.binding_sha256,
            "trusted": self.trusted,
            "issues": list(self.issues),
        }


def load_active_gcsim_optimizer_engine_context(
    *,
    store_dir: str | Path = DEFAULT_GCSIM_ENGINE_STORE_DIR,
    require_resealed: bool = True,
) -> GcsimOptimizerEngineContext:
    """Load the active engine and verify its manifest against current bytes."""

    try:
        installation = GcsimEngineStore(store_dir).get_active_engine()
    except GcsimEngineStoreError as exc:
        raise GcsimOptimizerEngineContextError(str(exc)) from exc
    if installation is None:
        raise GcsimOptimizerEngineContextError(
            "No active GCSIM engine is configured."
        )
    return build_gcsim_optimizer_engine_context(
        installation,
        require_resealed=require_resealed,
    )


def build_gcsim_optimizer_engine_context(
    installation: GcsimEngineInstallation,
    *,
    require_resealed: bool = True,
) -> GcsimOptimizerEngineContext:
    """Bind one installed manifest, source tree, catalog, and executable."""

    root = Path(installation.path).expanduser().resolve()
    manifest = installation.manifest
    artifact_path = _manifest_artifact_path(root, manifest)
    if not artifact_path.is_file():
        raise GcsimOptimizerEngineContextError(
            f"Optimizer engine artifact is missing: {artifact_path}"
        )

    actual_artifact_sha256 = _sha256_file(artifact_path)
    actual_engine_tree_sha256 = _engine_tree_sha256(root)
    expected_artifact_sha256 = str(
        manifest.metadata.get("artifact_sha256", "") or ""
    ).strip().casefold()
    expected_engine_tree_sha256 = str(manifest.engine_tree_hash or "").strip().casefold()
    issues: list[str] = []
    if not expected_artifact_sha256:
        issues.append("manifest_artifact_sha256_missing")
    elif expected_artifact_sha256 != actual_artifact_sha256:
        issues.append("manifest_artifact_sha256_mismatch")
    if not expected_engine_tree_sha256:
        issues.append("manifest_engine_tree_sha256_missing")
    elif expected_engine_tree_sha256 != actual_engine_tree_sha256:
        issues.append("manifest_engine_tree_sha256_mismatch")

    catalog = load_gcsim_artifact_set_catalog(root)
    engine_version = _engine_version(manifest)
    binding_payload = {
        "engine_id": manifest.engine_id,
        "engine_version": engine_version,
        "optimizer_contract_version": manifest.source_label,
        "artifact_sha256": actual_artifact_sha256,
        "engine_tree_sha256": actual_engine_tree_sha256,
        "catalog_fingerprint": catalog.source_fingerprint,
    }
    binding_sha256 = hashlib.sha256(
        json.dumps(
            binding_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    trusted = not issues
    if require_resealed and not trusted:
        raise GcsimOptimizerEngineContextError(
            "Active GCSIM optimizer engine is not resealed: " + ", ".join(issues)
        )
    return GcsimOptimizerEngineContext(
        engine_id=manifest.engine_id,
        engine_root=str(root),
        engine_version=engine_version,
        optimizer_contract_version=manifest.source_label,
        artifact_path=str(artifact_path),
        artifact_sha256=actual_artifact_sha256,
        engine_tree_sha256=actual_engine_tree_sha256,
        catalog=catalog,
        manifest_artifact_sha256=expected_artifact_sha256,
        manifest_engine_tree_sha256=expected_engine_tree_sha256,
        binding_sha256=binding_sha256,
        trusted=trusted,
        issues=tuple(issues),
    )


def _manifest_artifact_path(root: Path, manifest: GcsimEngineManifest) -> Path:
    for key in ("artifact_relative_path", "artifact_path"):
        raw = str(manifest.metadata.get(key, "") or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        resolved = candidate if candidate.is_absolute() else root / candidate
        resolved = resolved.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise GcsimOptimizerEngineContextError(
                "Optimizer artifact path escapes the installed engine root."
            ) from exc
        return resolved
    raise GcsimOptimizerEngineContextError(
        "Active engine manifest has no optimizer artifact path."
    )


def _engine_version(manifest: GcsimEngineManifest) -> str:
    for value in (
        manifest.metadata.get("gtt_upstream_version"),
        manifest.metadata.get("artifact_version_stdout"),
        manifest.metadata.get("upstream_ref"),
        manifest.source_label,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return manifest.engine_id


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _engine_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        if item.relative_to(root).as_posix() == MANIFEST_FILE_NAME:
            continue
        relative = item.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


__all__ = [
    "GcsimOptimizerEngineContext",
    "GcsimOptimizerEngineContextError",
    "build_gcsim_optimizer_engine_context",
    "load_active_gcsim_optimizer_engine_context",
]
