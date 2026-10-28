"""Materialize immutable History snapshot assets inside a saved bundle."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Mapping

from run_workspace.history_snapshot import HistorySnapshotBundle


class HistorySnapshotAssetError(ValueError):
    """Raised when a required frozen History asset cannot be materialized."""


def materialize_history_snapshot_bundle_assets(
    bundle: HistorySnapshotBundle,
    bundle_dir: str | Path,
    *,
    source_roots: tuple[str | Path, ...] = (),
) -> HistorySnapshotBundle:
    """Copy every declared asset and return a bundle with local references."""

    destination_root = Path(bundle_dir)
    roots = (destination_root, *(Path(root) for root in source_roots))
    resolved_sources: dict[str, Path] = {}
    for ref in bundle.asset_refs:
        source_text = str(ref.path).strip()
        if not source_text or source_text in resolved_sources:
            continue
        source = _resolve_source_path(source_text, roots)
        if source is None:
            raise HistorySnapshotAssetError(
                f"Required History snapshot asset is missing: {source_text}"
            )
        resolved_sources[source_text] = source

    replacements: dict[str, dict[str, str]] = {}
    for source_text, source in resolved_sources.items():
        content = source.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        suffix = _safe_suffix(source.suffix)
        relative_path = Path("assets") / sha256[:2] / f"{sha256}{suffix}"
        destination = destination_root / relative_path
        _write_bytes_atomic(destination, content)
        replacements[source_text] = {
            "path": relative_path.as_posix(),
            "sha256": sha256,
            "mime_type": mimetypes.guess_type(source.name)[0]
            or "application/octet-stream",
        }

    payload = _rewrite_asset_references(bundle.to_dict(), replacements)
    return HistorySnapshotBundle.from_dict(payload)


def _resolve_source_path(
    value: str,
    source_roots: tuple[Path, ...],
) -> Path | None:
    candidate = Path(value).expanduser()
    candidates = (candidate,) if candidate.is_absolute() else tuple(
        root / candidate for root in source_roots
    )
    for path in candidates:
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _rewrite_asset_references(
    value: Any,
    replacements: Mapping[str, Mapping[str, str]],
) -> Any:
    if isinstance(value, Mapping):
        original_path = value.get("path")
        result = {
            key: _rewrite_asset_references(item, replacements)
            for key, item in value.items()
        }
        replacement = (
            replacements.get(original_path)
            if isinstance(original_path, str)
            else None
        )
        if replacement is not None:
            result.update(replacement)
        return result
    if isinstance(value, list):
        return [_rewrite_asset_references(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_asset_references(item, replacements) for item in value)
    if isinstance(value, str) and value in replacements:
        return replacements[value]["path"]
    return value


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(content).digest()
    if path.exists() and hashlib.sha256(path.read_bytes()).digest() == content_hash:
        return
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_bytes(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _safe_suffix(value: str) -> str:
    suffix = value.casefold()
    if (
        suffix.startswith(".")
        and len(suffix) <= 10
        and all(char.isalnum() for char in suffix[1:])
    ):
        return suffix
    return ".bin"


__all__ = [
    "HistorySnapshotAssetError",
    "materialize_history_snapshot_bundle_assets",
]
