"""Official GCSIM source acquisition helpers for the engine-update path.

This is a narrow backend/dev layer: it resolves official `genshinsim/gcsim`
GitHub releases, downloads a source archive, and expands it into a local source
cache. It does not patch, build, or run the engine; `engine_update.py` passes the
expanded source tree into `GcsimEngineStore`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from .engine_store import PROJECT_ROOT


GCSIM_UPSTREAM_REPO = "genshinsim/gcsim"
GITHUB_API_ROOT = "https://api.github.com"
DEFAULT_GCSIM_SOURCE_CACHE_DIR = PROJECT_ROOT / "data" / "gcsim" / "sources"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60


class GcsimSourceAcquisitionError(RuntimeError):
    """Raised for controlled official source acquisition failures."""


@dataclass(frozen=True, slots=True)
class OfficialGcsimSourceRef:
    requested_release: str
    tag: str
    archive_url: str
    html_url: str
    api_url: str
    upstream_repo: str = GCSIM_UPSTREAM_REPO


@dataclass(frozen=True, slots=True)
class OfficialGcsimSourceAcquisition:
    source_ref: OfficialGcsimSourceRef
    archive_path: Path
    source_dir: Path
    cache_dir: Path
    warnings: tuple[str, ...] = ()


def acquire_official_gcsim_source(
    *,
    release: str = "latest",
    cache_dir: str | Path | None = None,
    request_json: Callable[[str], dict] | None = None,
    download_url: Callable[[str, Path], None] | None = None,
) -> OfficialGcsimSourceAcquisition:
    """Resolve, download, and extract an official GCSIM source archive."""

    source_ref = resolve_official_gcsim_release(
        release=release,
        request_json=request_json,
    )
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_GCSIM_SOURCE_CACHE_DIR
    archive_dir = root / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{_safe_name(source_ref.tag)}.zip"
    downloader = download_url or _download_url
    downloader(source_ref.archive_url, archive_path)
    return acquire_official_gcsim_source_from_archive(
        source_ref=source_ref,
        archive_path=archive_path,
        cache_dir=root,
    )


def resolve_official_gcsim_release(
    *,
    release: str = "latest",
    request_json: Callable[[str], dict] | None = None,
) -> OfficialGcsimSourceRef:
    requested = str(release or "latest").strip()
    api_url = (
        f"{GITHUB_API_ROOT}/repos/{GCSIM_UPSTREAM_REPO}/releases/latest"
        if requested == "latest"
        else f"{GITHUB_API_ROOT}/repos/{GCSIM_UPSTREAM_REPO}/releases/tags/{requested}"
    )
    fetch_json = request_json or _request_json
    try:
        payload = fetch_json(api_url)
    except Exception as exc:  # noqa: BLE001 - convert network/json failures.
        raise GcsimSourceAcquisitionError(
            f"Could not resolve official GCSIM release {requested!r}: {exc}"
        ) from exc
    tag = str(payload.get("tag_name") or "").strip()
    archive_url = str(payload.get("zipball_url") or "").strip()
    html_url = str(payload.get("html_url") or "").strip()
    if not tag or not archive_url:
        raise GcsimSourceAcquisitionError(
            f"GitHub release response for {requested!r} has no tag/archive URL."
        )
    return OfficialGcsimSourceRef(
        requested_release=requested,
        tag=tag,
        archive_url=archive_url,
        html_url=html_url,
        api_url=api_url,
    )


def acquire_official_gcsim_source_from_archive(
    *,
    source_ref: OfficialGcsimSourceRef,
    archive_path: str | Path,
    cache_dir: str | Path | None = None,
) -> OfficialGcsimSourceAcquisition:
    """Extract an already available official source archive into cache."""

    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise GcsimSourceAcquisitionError(f"Source archive does not exist: {archive_path}")
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_GCSIM_SOURCE_CACHE_DIR
    expanded_root = root / "expanded"
    extract_temp = root / "extracting" / _safe_name(source_ref.tag)
    source_dir = expanded_root / _safe_name(source_ref.tag)
    _safe_remove_tree(extract_temp, root=root)
    _safe_remove_tree(source_dir, root=root)
    extract_temp.mkdir(parents=True, exist_ok=True)
    try:
        _extract_zip_safe(archive_path, extract_temp)
        extracted_source = _single_extracted_root(extract_temp)
        source_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted_source), str(source_dir))
    except Exception as exc:  # noqa: BLE001 - keep caller failure controlled.
        _safe_remove_tree(extract_temp, root=root)
        _safe_remove_tree(source_dir, root=root)
        raise GcsimSourceAcquisitionError(
            f"Could not extract official GCSIM source archive {archive_path}: {exc}"
        ) from exc
    _safe_remove_tree(extract_temp, root=root)
    return OfficialGcsimSourceAcquisition(
        source_ref=source_ref,
        archive_path=archive_path,
        source_dir=source_dir,
        cache_dir=root,
    )


def _request_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "GenshinTeamsTracker-GCSIM-source-updater",
        },
    )
    try:
        with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        raise GcsimSourceAcquisitionError(str(exc)) from exc


def _download_url(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "GenshinTeamsTracker-GCSIM-source-updater",
        },
    )
    temp = destination.with_name(destination.name + ".tmp")
    try:
        with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
            with temp.open("wb") as output:
                shutil.copyfileobj(response, output)
        temp.replace(destination)
    except (HTTPError, URLError, OSError) as exc:
        if temp.exists():
            temp.unlink()
        raise GcsimSourceAcquisitionError(
            f"Could not download official GCSIM source archive: {exc}"
        ) from exc


def _extract_zip_safe(archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = destination / member.filename
                resolved = target.resolve()
                if destination.resolve() not in resolved.parents and resolved != destination.resolve():
                    raise GcsimSourceAcquisitionError(
                        f"Archive member escapes destination: {member.filename}"
                    )
            archive.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise GcsimSourceAcquisitionError("Archive is not a valid zip file.") from exc


def _single_extracted_root(path: Path) -> Path:
    entries = [item for item in path.iterdir() if item.name not in {".", ".."}]
    if len(entries) != 1 or not entries[0].is_dir():
        raise GcsimSourceAcquisitionError(
            "Expected a single top-level source directory in GitHub archive."
        )
    return entries[0]


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip("-._")
    return name or "source"


def _safe_remove_tree(path: Path, *, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or (
        resolved_root not in resolved_path.parents and resolved_path != resolved_root
    ):
        raise GcsimSourceAcquisitionError(
            f"Refusing to remove path outside source cache: {path}"
        )
    if path.exists():
        shutil.rmtree(path)
