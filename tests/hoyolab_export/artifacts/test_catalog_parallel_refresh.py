from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hoyolab_export.artifact_db import connect_db, init_db
from hoyolab_export.artifact_set_catalog import update_artifact_set_catalog
from hoyolab_export.hoyowiki_catalog_refresh import (
    refresh_weapon_stats_catalog_entries,
)
from hoyolab_export.weapon_stats_catalog import (
    build_weapon_stats_catalog,
    parse_weapon_stats_page,
    read_weapon_stats_cache,
    write_weapon_stats_cache,
)


def _weapon_page(name: str) -> dict[str, object]:
    return {
        "name": name,
        "modules": [
            {
                "components": [
                    {
                        "component_id": "baseInfo",
                        "data": json.dumps(
                            {
                                "list": [
                                    {"key": "Type", "value": ["Bow"]},
                                    {
                                        "key": "Secondary Attributes",
                                        "value": ["Energy Recharge"],
                                    },
                                    {
                                        "key": "Windfall",
                                        "value": ["CRIT Hits generate particles."],
                                    },
                                ]
                            }
                        ),
                    },
                    {
                        "component_id": "ascension",
                        "data": json.dumps(
                            {
                                "list": [
                                    {
                                        "key": "Lv.1",
                                        "combatList": [
                                            {
                                                "key": "",
                                                "values": [
                                                    "ATK before Ascension",
                                                    "ATK after Ascension",
                                                    "Energy Recharge",
                                                ],
                                            },
                                            {"key": "", "values": ["-", "41", "13.3%"]},
                                        ],
                                    }
                                ]
                            }
                        ),
                    },
                ]
            }
        ],
    }


def _track_concurrency(active_lock: threading.Lock, state: dict[str, int]):
    class Tracker:
        def __enter__(self):
            with active_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])

        def __exit__(self, *_args):
            with active_lock:
                state["active"] -= 1

    return Tracker()


class ArtifactSetParallelRefreshTest(unittest.TestCase):
    def test_detail_failures_are_isolated_and_fetches_are_bounded(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            items = [
                {
                    "entry_page_id": str(index),
                    "name": f"Parallel Set {index}",
                    "display_field": (
                        {"flower_of_life_icon_url": f"https://cdn.example/fallback-{index}.png"}
                        if index == 0
                        else {}
                    ),
                }
                for index in range(8)
            ]
            state = {"active": 0, "maximum": 0}
            active_lock = threading.Lock()
            downloaded: list[str] = []

            def fetch_detail(entry_id: str, *, language: str) -> dict[str, object]:
                self.assertEqual(language, "en-us")
                with _track_concurrency(active_lock, state):
                    time.sleep(0.035)
                    if entry_id == "0":
                        raise RuntimeError("network failure https://example.org/private?token=secret")
                    return {"icons": {1: f"https://cdn.example/{entry_id}.png"}}

            def write_icon(url: str, destination: Path) -> None:
                downloaded.append(url)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"icon")

            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                side_effect=fetch_detail,
            ), patch(
                "hoyolab_export.artifact_set_catalog.extract_piece_icons_from_entry_page",
                side_effect=lambda page: page["icons"],
            ), patch(
                "hoyolab_export.artifact_set_catalog.download_file",
                side_effect=write_icon,
            ), patch(
                "hoyolab_export.artifact_set_catalog.local_icon_path",
                side_effect=lambda set_uid, pos: root / "icons" / f"{set_uid}_{pos}.png",
            ):
                summary = update_artifact_set_catalog(
                    db_path=db_path,
                    list_fetcher=lambda **_kwargs: items,
                )

            self.assertGreater(state["maximum"], 1)
            self.assertLessEqual(state["maximum"], 4)
            self.assertEqual(summary["sets_upserted"], 8)
            self.assertEqual(summary["icons_downloaded"], 8)
            self.assertEqual(len(summary["errors"]), 1)
            self.assertEqual(summary["errors"][0]["entry_page_id"], "0")
            self.assertEqual(summary["errors"][0]["stage"], "detail_fetch")
            self.assertEqual(summary["errors"][0]["error"]["type"], "RuntimeError")
            self.assertNotIn("secret", str(summary["errors"]))
            self.assertEqual(len(downloaded), 8)

    def test_warm_missing_only_catalog_skips_cached_entry_and_icon_work(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            icon_path = root / "icons" / "KnownSet_1.png"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(b"cached")
            with closing(connect_db(db_path)) as conn, conn:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO artifact_sets (
                        set_uid, hoyowiki_entry_id, fallback_name, source, updated_at
                    ) VALUES ('KnownSet', 'known', 'Known Set', 'seed', 'now')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO artifact_set_piece_icons (
                        set_uid, pos, icon_url, local_path, updated_at
                    ) VALUES ('KnownSet', 1, 'https://cdn.example/known.png', 'cached.png', 'now')
                    """
                )

            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                side_effect=AssertionError("cached metadata should be reused"),
            ), patch(
                "hoyolab_export.artifact_set_catalog.download_file",
                side_effect=AssertionError("cached icon should not download"),
            ), patch(
                "hoyolab_export.artifact_set_catalog.local_icon_path",
                return_value=icon_path,
            ):
                summary = update_artifact_set_catalog(
                    db_path=db_path,
                    missing_only=True,
                    list_fetcher=lambda **_kwargs: [
                        {
                            "entry_page_id": "known",
                            "name": "Known Set",
                            "display_field": {"flower_of_life_icon_url": "https://cdn.example/known.png"},
                        }
                    ],
                )

            self.assertEqual(summary["sets_skipped_existing"], 1)
            self.assertEqual(summary["sets_upserted"], 0)
            self.assertEqual(summary["icons_downloaded"], 0)

    def test_missing_only_retries_only_incomplete_entry_then_clears_retry_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            items = [
                {
                    "entry_page_id": "healthy",
                    "name": "Healthy Retry Set",
                    "display_field": {},
                },
                {
                    "entry_page_id": "broken",
                    "name": "Broken Retry Set",
                    "display_field": {},
                },
            ]
            icon_path_by_set = {
                "HealthyRetrySet": root / "icons" / "healthy.png",
                "BrokenRetrySet": root / "icons" / "broken.png",
            }
            detail_calls: list[str] = []
            icon_calls: list[str] = []
            broken_attempts = 0

            def fetch_detail(entry_id: str, *, language: str) -> dict[str, object]:
                self.assertEqual(language, "en-us")
                detail_calls.append(entry_id)
                with closing(connect_db(db_path)) as conn:
                    self.assertIsNotNone(conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='artifact_set_catalog_retry'"
                    ).fetchone())
                return {"icons": {1: f"https://cdn.example/{entry_id}.png"}}

            def download_icon(url: str, destination: Path) -> None:
                nonlocal broken_attempts
                icon_calls.append(url)
                if url.endswith("/broken.png"):
                    broken_attempts += 1
                    if broken_attempts <= 3:
                        raise urllib.error.URLError("temporary transport failure")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"icon")

            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                side_effect=fetch_detail,
            ), patch(
                "hoyolab_export.artifact_set_catalog.extract_piece_icons_from_entry_page",
                side_effect=lambda page: page["icons"],
            ), patch(
                "hoyolab_export.artifact_set_catalog.download_file",
                side_effect=download_icon,
            ), patch(
                "hoyolab_export.artifact_set_catalog.local_icon_path",
                side_effect=lambda set_uid, _pos: icon_path_by_set[set_uid],
            ), patch("hoyolab_export.artifact_set_catalog.time.sleep"):
                first = update_artifact_set_catalog(
                    db_path=db_path,
                    list_fetcher=lambda **_kwargs: items,
                )
                self.assertEqual(first["icons_failed"], 1)
                with closing(connect_db(db_path)) as conn:
                    retry_rows = [tuple(row) for row in conn.execute(
                        "SELECT entry_page_id, failure_stage FROM artifact_set_catalog_retry"
                    )]
                self.assertEqual(retry_rows, [("broken", "icon_download")])

                detail_calls.clear()
                icon_calls.clear()
                second = update_artifact_set_catalog(
                    db_path=db_path,
                    missing_only=True,
                    list_fetcher=lambda **_kwargs: items,
                )

            self.assertEqual(detail_calls, ["broken"])
            self.assertEqual(icon_calls, ["https://cdn.example/broken.png"])
            self.assertEqual(second["sets_skipped_existing"], 1)
            self.assertEqual(second["sets_upserted"], 1)
            self.assertEqual(second["icons_downloaded"], 1)
            self.assertFalse(second["errors"])
            with closing(connect_db(db_path)) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM artifact_set_catalog_retry"
                ).fetchone()[0], 0)

    def test_retry_state_is_pruned_when_entry_leaves_valid_catalog_list(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            removed_item = {
                "entry_page_id": "removed",
                "name": "Removed Retry Set",
                "display_field": {},
            }
            with closing(connect_db(db_path)) as conn, conn:
                init_db(conn)
                conn.execute(
                    """CREATE TABLE artifact_set_catalog_retry (
                        entry_page_id TEXT PRIMARY KEY,
                        failure_stage TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    "INSERT INTO artifact_set_catalog_retry VALUES ('removed', 'icon_download', 'now')"
                )
                conn.execute(
                    """INSERT INTO artifact_sets (
                        set_uid, hoyowiki_entry_id, fallback_name, source, updated_at
                    ) VALUES ('HealthyRetrySet', 'healthy', 'Healthy Retry Set', 'seed', 'now')"""
                )

            healthy_icon = root / "icons" / "healthy.png"
            healthy_icon.parent.mkdir(parents=True)
            healthy_icon.write_bytes(b"cached")
            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                side_effect=AssertionError("removed retry entry should be pruned"),
            ), patch(
                "hoyolab_export.artifact_set_catalog.download_file",
                side_effect=AssertionError("healthy cache should be skipped"),
            ), patch(
                "hoyolab_export.artifact_set_catalog.local_icon_path",
                return_value=healthy_icon,
            ):
                summary = update_artifact_set_catalog(
                    db_path=db_path,
                    missing_only=True,
                    list_fetcher=lambda **_kwargs: [
                        {
                            "entry_page_id": "healthy",
                            "name": "Healthy Retry Set",
                            "display_field": {
                                "flower_of_life_icon_url": "https://cdn.example/healthy.png",
                            },
                        }
                    ],
                )

            self.assertEqual(summary["sets_skipped_existing"], 1)
            with closing(connect_db(db_path)) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM artifact_set_catalog_retry"
                ).fetchone()[0], 0)

    def test_fetcher_can_write_database_while_catalog_details_are_fetching(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            items = [
                {"entry_page_id": str(index), "name": f"Probe Set {index}", "display_field": {}}
                for index in range(4)
            ]
            writer_lock = threading.Lock()
            written_probes: list[str] = []

            def fetch_detail(entry_id: str, *, language: str) -> dict[str, object]:
                self.assertEqual(language, "en-us")
                probe_id = f"probe-{entry_id}"
                with writer_lock:
                    with closing(sqlite3.connect(db_path, timeout=0.2)) as writer, writer:
                        writer.execute(
                            """
                            INSERT INTO artifact_sets (
                                set_uid, hoyowiki_entry_id, fallback_name, source, updated_at
                            ) VALUES (?, ?, ?, 'probe', 'now')
                            """,
                            (f"WriterProbe{entry_id}", probe_id, probe_id),
                        )
                    written_probes.append(probe_id)
                return {"icons": {}}

            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                side_effect=fetch_detail,
            ), patch(
                "hoyolab_export.artifact_set_catalog.extract_piece_icons_from_entry_page",
                return_value={},
            ):
                summary = update_artifact_set_catalog(
                    db_path=db_path,
                    list_fetcher=lambda **_kwargs: items,
                )

            self.assertEqual(len(written_probes), 4)
            self.assertEqual(summary["sets_upserted"], 4)
            self.assertFalse(summary["errors"])


class WeaponEntryParallelRefreshTest(unittest.TestCase):
    def test_missing_weapon_entries_are_bounded_cached_and_written_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = root / "weapons.json"
            cached = parse_weapon_stats_page(
                _weapon_page("Cached Weapon"),
                entry_page_id="cached",
                language="en-us",
            )
            existing_catalog = build_weapon_stats_catalog([cached], language="en-us")
            active_lock = threading.Lock()
            state = {"active": 0, "maximum": 0}
            fetched_ids: list[str] = []

            def fetch_detail(entry_id: str, _language: str) -> dict[str, object]:
                with _track_concurrency(active_lock, state):
                    fetched_ids.append(entry_id)
                    time.sleep(0.035)
                    if entry_id == "broken":
                        raise RuntimeError("network failure https://example.org/private?token=secret")
                    return _weapon_page(f"Weapon {entry_id}")

            with patch(
                "hoyolab_export.hoyowiki_catalog_refresh.write_weapon_stats_cache",
                wraps=write_weapon_stats_cache,
            ) as write_mock:
                result = refresh_weapon_stats_catalog_entries(
                    ["cached", "one", "two", "three", "four", "five", "broken"],
                    cache_path=cache_path,
                    existing_catalog=existing_catalog,
                    detail_fetcher=fetch_detail,
                )

            cache = read_weapon_stats_cache(cache_path)
            self.assertNotIn("cached", fetched_ids)
            self.assertGreater(state["maximum"], 1)
            self.assertLessEqual(state["maximum"], 4)
            self.assertEqual(result.skipped_existing, 1)
            self.assertEqual(result.fetched, 5)
            self.assertEqual(result.failed, 1)
            self.assertEqual(result.failures[0].entry_page_id, "broken")
            self.assertNotIn("secret", result.failures[0].error)
            self.assertEqual(write_mock.call_count, 1)
            self.assertIsNotNone(cache)
            self.assertEqual(
                {entry.entry_page_id for entry in cache.entries},
                {"cached", "one", "two", "three", "four", "five"},
            )


if __name__ == "__main__":
    unittest.main()
