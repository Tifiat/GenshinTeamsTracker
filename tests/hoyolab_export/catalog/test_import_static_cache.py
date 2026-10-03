from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.import_static_cache import ImportArtifactSetLists


class ImportArtifactSetListsTest(unittest.TestCase):
    def test_one_fetch_per_language_then_persisted_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_artifact_sets",
            side_effect=lambda *, language: [{"language": language}],
        ) as fetch:
            first = ImportArtifactSetLists(cache_dir=tmp)
            self.assertEqual(first(language="en-us"), [{"language": "en-us"}])
            self.assertEqual(first(language="en-us"), [{"language": "en-us"}])
            self.assertEqual(first(language="ru-ru"), [{"language": "ru-ru"}])
            self.assertEqual(fetch.call_count, 2)
            second = ImportArtifactSetLists(cache_dir=tmp)
            self.assertEqual(second(language="en-us"), [{"language": "en-us"}])
            self.assertEqual(second.sources["en-us"], "fresh_cache")
            self.assertEqual(fetch.call_count, 2)

    def test_stale_cache_is_refreshed_and_can_fallback_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact_set_list.en-us.json"
            path.write_text(json.dumps({
                "schemaVersion": 1, "language": "en-us",
                "fetchedAtUnix": time.time() - 100,
                "items": [{"name": "old"}],
            }), encoding="utf-8")
            with patch("hoyolab_export.artifact_set_catalog.fetch_hoyowiki_artifact_sets",
                       side_effect=RuntimeError("offline")):
                cached = ImportArtifactSetLists(cache_dir=tmp, ttl_seconds=10)
                self.assertEqual(cached(language="en-us"), [{"name": "old"}])
                self.assertEqual(cached.sources["en-us"], "stale_cache_after_fetch_error")
            with patch("hoyolab_export.artifact_set_catalog.fetch_hoyowiki_artifact_sets",
                       return_value=[{"name": "new"}]) as fetch:
                refreshed = ImportArtifactSetLists(cache_dir=tmp, ttl_seconds=10)
                self.assertEqual(refreshed(language="en-us"), [{"name": "new"}])
                fetch.assert_called_once_with(language="en-us")
                self.assertEqual(refreshed.sources["en-us"], "network")

    def test_cache_retention_removes_old_owned_file_and_preserves_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "hoyolab_export.import_static_cache.MAX_CACHE_FILES", 1,
        ), patch(
            "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_artifact_sets",
            side_effect=lambda *, language: [{"language": language}],
        ):
            other = Path(tmp) / "character_trait_catalog.json"
            other.write_text("other cache", encoding="utf-8")
            cache = ImportArtifactSetLists(cache_dir=tmp)
            cache(language="en-us")
            cache(language="ru-ru")
            self.assertEqual(len(list(Path(tmp).glob("artifact_set_list.*.json"))), 1)
            self.assertTrue((Path(tmp) / "artifact_set_list.ru-ru.json").exists())
            self.assertEqual(other.read_text(encoding="utf-8"), "other cache")

    def test_cache_retention_reports_partial_delete_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "hoyolab_export.import_static_cache.MAX_CACHE_FILES", 0,
        ):
            path = Path(tmp) / "artifact_set_list.en-us.json"
            path.write_text("{}", encoding="utf-8")
            cache = ImportArtifactSetLists(cache_dir=tmp)
            with patch.object(Path, "unlink", side_effect=OSError("in use")):
                cache._prune()
            self.assertTrue(path.exists())
            self.assertEqual(cache.cleanup_failures, [f"{path.name}: could not retire cache"])

    def test_cache_retention_does_not_follow_outside_root_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "keep.json"
            target.write_text("outside", encoding="utf-8")
            link = Path(tmp) / "artifact_set_list.en-us.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            cache = ImportArtifactSetLists(cache_dir=tmp)
            cache._prune()
            self.assertEqual(target.read_text(encoding="utf-8"), "outside")
            self.assertTrue(link.is_symlink())
            self.assertEqual(cache.cleanup_failures, [f"{link.name}: linked cache left untouched"])


if __name__ == "__main__":
    unittest.main()
