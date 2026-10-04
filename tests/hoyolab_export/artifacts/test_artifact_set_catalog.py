from __future__ import annotations

import json
import unittest
from contextlib import closing
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hoyolab_export.artifact_db import connect_db, init_db
from hoyolab_export.artifact_set_catalog import (
    UnmappedArtifactSetError,
    ensure_artifact_set_catalog,
    ensure_hoyolab_set_mapping,
    resolve_hoyolab_set_uid,
    update_artifact_set_catalog,
)


class ArtifactSetCatalogUpdateTest(unittest.TestCase):
    def test_missing_only_skips_existing_sets_without_detail_icon_work(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            with connect_db(db_path) as conn:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO artifact_sets (
                        set_uid,
                        hoyowiki_entry_id,
                        fallback_name,
                        source,
                        updated_at
                    )
                    VALUES ('ExistingSet', '100', 'Existing Set', 'seed', 'now')
                    """
                )
                conn.commit()
            conn.close()

            items = [
                {"entry_page_id": "100", "name": "Existing Set", "display_field": {}},
                {"entry_page_id": "200", "name": "New Set", "display_field": {}},
            ]

            with patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_artifact_sets",
                return_value=items,
            ), patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                return_value={},
            ) as detail_mock:
                summary = update_artifact_set_catalog(
                    db_path=db_path,
                    missing_only=True,
                )

            self.assertEqual(summary["sets_seen"], 2)
            self.assertEqual(summary["sets_existing"], 1)
            self.assertEqual(summary["sets_missing"], 1)
            self.assertEqual(summary["sets_skipped_existing"], 1)
            self.assertEqual(summary["sets_upserted"], 1)
            detail_mock.assert_called_once_with("200", language="en-us")


class ArtifactSetCatalogEnsureTest(unittest.TestCase):
    def _write_seed(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "sets": [
                        {
                            "set_uid": "SeedSet",
                            "hoyowiki_entry_id": "seed-entry",
                            "fallback_name": "Seed Set",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_empty_database_returns_seed_without_closing_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            seed_path = root / "seed.json"
            self._write_seed(seed_path)

            with patch("hoyolab_export.artifact_set_catalog.SEED_CATALOG_PATH", seed_path):
                summary = ensure_artifact_set_catalog(db_path=db_path, allow_network=False)

            self.assertEqual(summary["source"], "seed")
            self.assertTrue(summary["seeded"])
            with closing(connect_db(db_path)) as conn:
                row = conn.execute(
                    "SELECT fallback_name FROM artifact_sets WHERE set_uid = 'SeedSet'"
                ).fetchone()
            self.assertEqual(row["fallback_name"], "Seed Set")

    def test_seeded_catalog_still_runs_network_missing_only_refresh(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "artifacts.db"
            seed_path = root / "seed.json"
            self._write_seed(seed_path)
            items = [
                {"entry_page_id": "network-entry", "name": "Network Set", "display_field": {}}
            ]

            def list_fetcher(*, language: str) -> list[dict[str, object]]:
                self.assertEqual(language, "en-us")
                return items

            with patch("hoyolab_export.artifact_set_catalog.SEED_CATALOG_PATH", seed_path), patch(
                "hoyolab_export.artifact_set_catalog.fetch_hoyowiki_entry_page",
                return_value={},
            ) as detail_mock:
                summary = ensure_artifact_set_catalog(
                    db_path=db_path,
                    allow_network=True,
                    missing_only=True,
                    list_fetcher=list_fetcher,
                )

            self.assertEqual(summary["source"], "network")
            self.assertTrue(summary["seed"]["seeded"])
            self.assertEqual(summary["sets_upserted"], 1)
            detail_mock.assert_called_once_with("network-entry", language="en-us")
            with closing(connect_db(db_path)) as conn:
                rows = {
                    row["set_uid"]: row["hoyowiki_entry_id"]
                    for row in conn.execute(
                        "SELECT set_uid, hoyowiki_entry_id FROM artifact_sets"
                    )
                }
            self.assertEqual(rows["SeedSet"], "seed-entry")
            self.assertEqual(rows["NetworkSet"], "network-entry")


class ArtifactSetMappingTest(unittest.IsolatedAsyncioTestCase):
    def _create_catalog_db(self, db_path: Path) -> None:
        with closing(connect_db(db_path)) as conn, conn:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO artifact_sets (
                    set_uid, hoyowiki_entry_id, artiscan_set_key,
                    fallback_name, source, updated_at
                ) VALUES ('KnownSet', 'known-entry', 'KnownSet', 'Known Set', 'seed', 'now')
                """
            )

    def _account_details(self) -> dict[str, object]:
        return {
            "json": {
                "retcode": 0,
                "data": {
                    "list": [
                        {
                            "relics": [
                                {"set": {"id": 101, "name": "Set Conocido"}},
                                {"set": {"id": 202, "name": "Regalo Celestial"}},
                            ]
                        }
                    ]
                },
            }
        }

    def _english_details(self) -> dict[str, object]:
        return {
            "json": {
                "retcode": 0,
                "data": {
                    "list": [
                        {
                            "relics": [
                                {"set": {"id": 101, "name": "Known Set"}},
                                {"set": {"id": 202, "name": "Celestial Gift"}},
                            ]
                        }
                    ]
                },
            }
        }

    def _patch_english_details(self):
        return patch(
            "hoyolab_export.character_detail.fetch_character_details_batch",
            new=AsyncMock(return_value=self._english_details()),
        )

    async def test_allow_unmapped_returns_known_mapping_and_structured_details(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            self._create_catalog_db(db_path)

            with self._patch_english_details():
                summary = await ensure_hoyolab_set_mapping(
                    self._account_details(),
                    export_page=None,
                    real_ids=[1001],
                    db_path=db_path,
                    allow_unmapped=True,
                    english_details=self._english_details(),
                )

            self.assertEqual(summary["mapped"], 1)
            self.assertEqual(len(summary["unmapped"]), 1)
            unmapped = summary["unmapped"][0]
            self.assertEqual(unmapped["hoyolab_set_id"], 202)
            self.assertEqual(unmapped["display_name"], "Regalo Celestial")
            self.assertEqual(unmapped["en_name"], "Celestial Gift")
            self.assertEqual(unmapped["normalized_name"], "celestial gift")
            self.assertEqual(unmapped["reason"], "EN name not found in canonical catalog")
            with closing(connect_db(db_path)) as conn:
                row = conn.execute(
                    "SELECT hoyolab_set_id FROM artifact_sets WHERE set_uid = 'KnownSet'"
                ).fetchone()
            self.assertEqual(row["hoyolab_set_id"], 101)

    async def test_strict_mapping_still_raises_for_unmapped_canonical_name(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            self._create_catalog_db(db_path)

            with self._patch_english_details():
                with self.assertRaisesRegex(RuntimeError, "202: Celestial Gift"):
                    await ensure_hoyolab_set_mapping(
                        self._account_details(),
                        export_page=None,
                        real_ids=[1001],
                        db_path=db_path,
                        english_details=self._english_details(),
                    )

    async def test_unmapped_error_is_specific_but_missing_id_keeps_generic_error(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                with self.assertRaises(UnmappedArtifactSetError) as caught:
                    resolve_hoyolab_set_uid(
                        conn,
                        hoyolab_set_id=2150451,
                        display_name="Celestial Gift",
                    )

                self.assertEqual(caught.exception.hoyolab_set_id, 2150451)
                self.assertEqual(caught.exception.display_name, "Celestial Gift")
                with self.assertRaisesRegex(RuntimeError, "has no set_id"):
                    resolve_hoyolab_set_uid(
                        conn,
                        hoyolab_set_id=None,
                        display_name="Unknown",
                    )


if __name__ == "__main__":
    unittest.main()
