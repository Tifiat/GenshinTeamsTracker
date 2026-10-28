from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from run_workspace.gcsim.snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    DEFAULT_SNAP_MONSTER_RAW_URL,
    SNAP_CACHE_STATUS_HIT,
    SNAP_CACHE_STATUS_INVALID,
    SNAP_CACHE_STATUS_MISSING,
    SNAP_REFRESH_STATUS_SUCCESS,
    SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL,
    SNAP_SOURCE_KIND_LOCAL_PATH,
    SNAP_SOURCE_KIND_MANAGED_CACHE,
    SNAP_SOURCE_KIND_REMOTE_URL,
    SNAP_TITLE_STATUS_AMBIGUOUS,
    SNAP_TITLE_STATUS_MISSING,
    SNAP_TITLE_STATUS_RESOLVED,
    SnapMonsterTitleSourceError,
    load_default_remote_snap_monster_title_index,
    load_cached_snap_monster_title_index,
    load_snap_monster_title_index,
    refresh_cached_snap_monster_title_index,
    snap_monster_raw_url,
)


class GcsimSnapMonsterTitlesTest(unittest.TestCase):
    def test_loads_name_title_records_from_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Assault Specialist Mek - Pneuma",
                            "Title": "Assault Specialist Mek",
                            "HpBase": 123,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(lookup.candidates[0].title, "Assault Specialist Mek")
        self.assertEqual(index.source_kind, SNAP_SOURCE_KIND_LOCAL_PATH)

    def test_loads_simple_wrapper_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "Name": "Tenebrous Mimesis - Anemo Hilichurl Rogue",
                                "Title": "Tenebrous Mimiflora",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Tenebrous Mimesis - Anemo Hilichurl Rogue")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(lookup.candidates[0].title, "Tenebrous Mimiflora")

    def test_duplicate_name_with_same_title_is_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_RESOLVED)
        self.assertEqual(len(lookup.candidates), 1)

    def test_duplicate_name_with_different_titles_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps(
                    [
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"},
                        {"Name": "Assault Specialist Mek - Pneuma", "Title": "Clockwork Mek"},
                    ]
                ),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Assault Specialist Mek - Pneuma")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_AMBIGUOUS)
        self.assertIn(
            "snap_title_ambiguous_for_name:assaultspecialistmekpneuma",
            lookup.warnings,
        )

    def test_missing_name_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster.json"
            path.write_text(
                json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}]),
                encoding="utf-8",
            )

            index = load_snap_monster_title_index(path)
            lookup = index.lookup("Missing Enemy")

        self.assertEqual(lookup.status, SNAP_TITLE_STATUS_MISSING)
        self.assertIn("snap_title_missing_for_name:missingenemy", lookup.warnings)

    def test_raw_url_loader_uses_fake_fetcher(self) -> None:
        calls: list[tuple[str, float]] = []

        def fake_fetch(url: str, timeout: float) -> str:
            calls.append((url, timeout))
            return json.dumps(
                [{"Name": "Assault Specialist Mek - Pneuma", "Title": "Assault Specialist Mek"}]
            )

        index = load_snap_monster_title_index(
            DEFAULT_SNAP_MONSTER_RAW_URL,
            fetcher=fake_fetch,
        )

        self.assertEqual(calls[0][0], DEFAULT_SNAP_MONSTER_RAW_URL)
        self.assertEqual(index.source_kind, SNAP_SOURCE_KIND_REMOTE_URL)
        self.assertEqual(index.resolved_url, DEFAULT_SNAP_MONSTER_RAW_URL)
        self.assertEqual(index.lookup("Assault Specialist Mek - Pneuma").status, SNAP_TITLE_STATUS_RESOLVED)

    def test_github_blob_url_converts_to_raw_url(self) -> None:
        calls: list[str] = []

        def fake_fetch(url: str, _timeout: float) -> str:
            calls.append(url)
            return json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}])

        index = load_snap_monster_title_index(
            DEFAULT_SNAP_MONSTER_GITHUB_URL,
            fetcher=fake_fetch,
        )

        self.assertEqual(snap_monster_raw_url(DEFAULT_SNAP_MONSTER_GITHUB_URL), DEFAULT_SNAP_MONSTER_RAW_URL)
        self.assertEqual(calls, [DEFAULT_SNAP_MONSTER_RAW_URL])
        self.assertEqual(index.source_ref, DEFAULT_SNAP_MONSTER_GITHUB_URL)

    def test_default_remote_constant_points_to_snap_monster_json(self) -> None:
        self.assertEqual(
            DEFAULT_SNAP_MONSTER_GITHUB_URL,
            "https://github.com/wangdage12/Snap.Metadata/blob/main/Genshin/EN/Monster.json",
        )
        self.assertEqual(
            DEFAULT_SNAP_MONSTER_RAW_URL,
            "https://raw.githubusercontent.com/wangdage12/Snap.Metadata/main/Genshin/EN/Monster.json",
        )

    def test_default_remote_loader_marks_source_kind(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}])

        index = load_default_remote_snap_monster_title_index(fetcher=fake_fetch)

        self.assertEqual(index.source_kind, SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL)
        self.assertEqual(index.resolved_url, DEFAULT_SNAP_MONSTER_RAW_URL)

    def test_remote_fetch_failure_is_controlled(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            raise URLError("offline")

        with self.assertRaises(SnapMonsterTitleSourceError) as ctx:
            load_snap_monster_title_index(DEFAULT_SNAP_MONSTER_RAW_URL, fetcher=fake_fetch)

        self.assertIn("remote fetch failed", str(ctx.exception))

    def test_invalid_remote_json_is_controlled(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return "{not-json"

        with self.assertRaises(SnapMonsterTitleSourceError) as ctx:
            load_snap_monster_title_index(DEFAULT_SNAP_MONSTER_RAW_URL, fetcher=fake_fetch)

        self.assertIn("invalid JSON", str(ctx.exception))

    def test_invalid_remote_shape_is_controlled(self) -> None:
        def fake_fetch(_url: str, _timeout: float) -> str:
            return json.dumps({"unexpected": []})

        with self.assertRaises(SnapMonsterTitleSourceError) as ctx:
            load_snap_monster_title_index(DEFAULT_SNAP_MONSTER_RAW_URL, fetcher=fake_fetch)

        self.assertIn("list of objects with Name and Title", str(ctx.exception))

    def test_load_cached_snap_monster_title_index_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_cached_snap_monster_title_index(Path(tmp) / "Monster.json")

        self.assertEqual(result.status, SNAP_CACHE_STATUS_MISSING)
        self.assertFalse(result.ready)

    def test_load_cached_snap_monster_title_index_reports_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Monster.json"
            path.write_text(
                json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}]),
                encoding="utf-8",
            )

            result = load_cached_snap_monster_title_index(path)

        self.assertEqual(result.status, SNAP_CACHE_STATUS_HIT)
        self.assertTrue(result.ready)
        assert result.index is not None
        self.assertEqual(result.index.source_kind, SNAP_SOURCE_KIND_MANAGED_CACHE)
        self.assertEqual(result.index.lookup("Known Enemy").status, SNAP_TITLE_STATUS_RESOLVED)

    def test_load_cached_snap_monster_title_index_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Monster.json"
            path.write_text("{not-json", encoding="utf-8")

            result = load_cached_snap_monster_title_index(path)

        self.assertEqual(result.status, SNAP_CACHE_STATUS_INVALID)
        self.assertFalse(result.ready)
        self.assertIn("invalid", result.error)

    def test_refresh_cached_snap_monster_title_index_writes_cache_and_meta(self) -> None:
        calls: list[str] = []

        def fake_fetch(url: str, _timeout: float) -> str:
            calls.append(url)
            return json.dumps([{"Name": "Known Enemy", "Title": "Known Enemy"}])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap" / "Monster.json"
            result = refresh_cached_snap_monster_title_index(path, fetcher=fake_fetch)
            cached = load_cached_snap_monster_title_index(path)
            meta_path = path.with_suffix(".meta.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        self.assertEqual(calls, [DEFAULT_SNAP_MONSTER_RAW_URL])
        self.assertEqual(result.status, SNAP_REFRESH_STATUS_SUCCESS)
        self.assertTrue(result.ready)
        self.assertTrue(cached.ready)
        self.assertEqual(meta["resolved_url"], DEFAULT_SNAP_MONSTER_RAW_URL)


if __name__ == "__main__":
    unittest.main()
