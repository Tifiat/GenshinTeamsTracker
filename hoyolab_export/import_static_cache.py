"""Bound network refreshes of public HoYoWiki lists during account import."""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from . import artifact_set_catalog
from .paths import PROJECT_ROOT


DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "hoyowiki"
ARTIFACT_SET_LIST_TTL_SECONDS = 6 * 60 * 60
MAX_CACHE_FILES = 8
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_SINGLE_CACHE_BYTES = 2 * 1024 * 1024


class ImportArtifactSetLists:
    """Fetch each language once per import and reuse recent saved responses.

    Explicit catalog update commands keep their existing network behavior;
    this cache is only supplied by the normal account import.
    """

    def __init__(
        self, *, cache_dir: str | Path = DEFAULT_CACHE_DIR,
        ttl_seconds: int = ARTIFACT_SET_LIST_TTL_SECONDS,
        force_network: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.force_network = force_network
        self._items: dict[str, list[dict[str, Any]]] = {}
        self.sources: dict[str, str] = {}
        self.cleanup_failures: list[str] = []

    def __call__(self, *, language: str) -> list[dict[str, Any]]:
        lang = artifact_set_catalog.normalize_language(language)
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", lang):
            raise ValueError("Unsupported HoYoWiki language for import cache")
        if lang in self._items:
            return self._items[lang]

        path = self.cache_dir / f"artifact_set_list.{lang}.json"
        cached = self._read(path, lang)
        if not self.force_network and cached is not None:
            age = time.time() - cached[0]
            if 0 <= age < self.ttl_seconds:
                self._items[lang] = cached[1]
                self.sources[lang] = "fresh_cache"
                return cached[1]

        try:
            items = artifact_set_catalog.fetch_hoyowiki_artifact_sets(language=lang)
            if not items:
                raise RuntimeError("HoYoWiki artifact set list is empty")
        except Exception:
            if cached is None:
                raise
            self._items[lang] = cached[1]
            self.sources[lang] = "stale_cache_after_fetch_error"
            return cached[1]

        self._items[lang] = items
        self.sources[lang] = "network"
        temporary: Path | None = None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps({"schemaVersion": 1, "language": lang,
                                  "fetchedAtUnix": time.time(), "items": items}, ensure_ascii=False).encode("utf-8")
            if len(encoded) <= MAX_SINGLE_CACHE_BYTES:
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as file:
                    temporary = Path(file.name)
                    file.write(encoded)
                temporary.replace(path)
            else:
                self.cleanup_failures.append(f"{path.name}: response exceeds cache size limit")
            self._prune()
        except OSError:
            # A cache write failure must not discard a successful fetch.
            self.cleanup_failures.append(f"{path.name}: could not write cache")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    self.cleanup_failures.append(f"{temporary.name}: could not retire temporary cache")
        return items

    def _prune(self) -> None:
        """Bound only files owned by this importer; leave links and other caches alone."""
        candidates: list[tuple[float, int, Path]] = []
        for path in self.cache_dir.glob("artifact_set_list.*.json"):
            if path.is_symlink():
                self.cleanup_failures.append(f"{path.name}: linked cache left untouched")
                continue
            try:
                stat = path.stat()
            except OSError:
                self.cleanup_failures.append(f"{path.name}: could not inspect cache")
                continue
            if path.is_file():
                candidates.append((stat.st_mtime, stat.st_size, path))
        candidates.sort(reverse=True)
        total = 0
        for index, (_, size, path) in enumerate(candidates):
            if index < MAX_CACHE_FILES and total + size <= MAX_CACHE_BYTES:
                total += size
                continue
            try:
                path.unlink()
            except OSError:
                self.cleanup_failures.append(f"{path.name}: could not retire cache")

    @staticmethod
    def _read(path: Path, language: str) -> tuple[float, list[dict[str, Any]]] | None:
        try:
            if path.is_symlink() or path.stat().st_size > MAX_SINGLE_CACHE_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schemaVersion") != 1 or payload.get("language") != language:
                return None
            fetched_at = float(payload["fetchedAtUnix"])
            items = payload["items"]
            if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
                return None
            return fetched_at, items
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None
