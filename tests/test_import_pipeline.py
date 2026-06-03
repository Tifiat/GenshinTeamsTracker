from __future__ import annotations

import unittest
from unittest.mock import patch

from hoyolab_export.import_pipeline import (
    sync_account_storage_for_import,
    sync_static_reference_catalogs_for_import,
)


class ImportPipelineAccountStorageTest(unittest.TestCase):
    def test_account_storage_sync_downloads_side_icons_by_default(self) -> None:
        class FakeSummary:
            def to_dict(self) -> dict[str, object]:
                return {"characters_seen": 1, "weapon_stacks_seen": 1}

        with patch(
            "hoyolab_export.import_pipeline.sync_account_storage_from_local_files",
            return_value=FakeSummary(),
        ) as sync_mock:
            summary, error = sync_account_storage_for_import()

        self.assertIsNone(error)
        self.assertEqual(summary, {"characters_seen": 1, "weapon_stacks_seen": 1})
        sync_mock.assert_called_once_with(download_side_icons=True)

    def test_account_storage_sync_failure_is_nonfatal_result(self) -> None:
        with patch(
            "hoyolab_export.import_pipeline.sync_account_storage_from_local_files",
            side_effect=RuntimeError("db locked"),
        ):
            summary, error = sync_account_storage_for_import()

        self.assertIsNone(summary)
        self.assertEqual(error, "db locked")


class ImportPipelineStaticCatalogTest(unittest.TestCase):
    def test_static_catalog_sync_refreshes_artifact_sets_and_traits(self) -> None:
        class FakeTraitEntry:
            traits = ("moonsign",)
            source_character_entry_page_id = "10000001"
            name = "Test Character"
            icon_url = ""
            source_entry_page_id = "source"
            source_language = "en-us"

        class FakeTraitCatalog:
            source = "hoyowiki_team_bonus_entry"
            entries = (FakeTraitEntry(), FakeTraitEntry())
            fetched_at = "now"
            language = "en-us"

        with patch(
            "hoyolab_export.import_pipeline.ensure_artifact_set_catalog",
            return_value={"source": "network", "sets_seen": 1},
        ) as set_mock, patch(
            "hoyolab_export.import_pipeline.refresh_character_trait_catalog",
            return_value=FakeTraitCatalog(),
        ) as trait_mock:
            summary, error = sync_static_reference_catalogs_for_import()

        self.assertIsNone(error)
        set_mock.assert_called_once()
        self.assertTrue(set_mock.call_args.kwargs["allow_network"])
        self.assertTrue(set_mock.call_args.kwargs["missing_only"])
        trait_mock.assert_called_once_with()
        self.assertEqual(summary["artifactSetCatalog"]["source"], "network")
        self.assertEqual(summary["characterTraitCatalog"]["entries"], 2)

    def test_static_catalog_sync_failure_is_nonfatal_result(self) -> None:
        with patch(
            "hoyolab_export.import_pipeline.ensure_artifact_set_catalog",
            side_effect=RuntimeError("catalog offline"),
        ), patch(
            "hoyolab_export.import_pipeline.refresh_character_trait_catalog",
            side_effect=RuntimeError("traits offline"),
        ):
            summary, error = sync_static_reference_catalogs_for_import()

        self.assertEqual(summary, {})
        self.assertIn("artifact set catalog: catalog offline", error or "")
        self.assertIn("character trait catalog: traits offline", error or "")


if __name__ == "__main__":
    unittest.main()
