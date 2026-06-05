from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from run_workspace.gcsim.snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    DEFAULT_SNAP_MONSTER_RAW_URL,
    SNAP_SOURCE_KIND_DEFAULT_REMOTE_URL,
    SNAP_SOURCE_KIND_LOCAL_PATH,
    SNAP_SOURCE_KIND_REMOTE_URL,
    SNAP_TITLE_STATUS_AMBIGUOUS,
    SNAP_TITLE_STATUS_MISSING,
    SNAP_TITLE_STATUS_RESOLVED,
    SnapMonsterTitleSourceError,
    load_default_remote_snap_monster_title_index,
    load_snap_monster_title_index,
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


if __name__ == "__main__":
    unittest.main()
