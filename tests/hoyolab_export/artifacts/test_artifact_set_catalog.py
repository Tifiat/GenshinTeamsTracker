from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.artifact_db import connect_db, init_db
from hoyolab_export.artifact_set_catalog import update_artifact_set_catalog


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


if __name__ == "__main__":
    unittest.main()
