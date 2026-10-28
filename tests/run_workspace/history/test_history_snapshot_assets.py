from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HistoryAssetRefSnapshot,
    HistoryCharacterSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleStore,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
)
from run_workspace.history_snapshot_assets import HistorySnapshotAssetError


class HistorySnapshotAssetTests(unittest.TestCase):
    def test_grouped_write_copies_assets_and_rewrites_all_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            source_root = temp_root / "source"
            source_root.mkdir()
            source = source_root / "portrait.png"
            content = b"synthetic-history-portrait"
            source.write_bytes(content)
            store = HistorySnapshotBundleStore(temp_root / "history")

            snapshot_path = store.write_bundle_grouped(
                _bundle_with_portrait("portrait.png"),
                copy_assets=True,
                asset_source_roots=(source_root,),
            )
            source.unlink()
            stored = store.read_bundle("asset-test")

            expected_hash = hashlib.sha256(content).hexdigest()
            stored_ref = stored.asset_refs[0]
            self.assertEqual(stored_ref.sha256, expected_hash)
            self.assertEqual(stored_ref.mime_type, "image/png")
            self.assertTrue(stored_ref.path.startswith("assets/"))
            self.assertEqual(
                stored.teams[0].slots[0].character.portrait_ref,
                stored_ref.path,
            )
            self.assertEqual(
                stored.teams[0].slots[0].asset_refs[0].path,
                stored_ref.path,
            )
            self.assertEqual(
                (snapshot_path.parent / stored_ref.path).read_bytes(),
                content,
            )

    def test_missing_required_asset_aborts_snapshot_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HistorySnapshotBundleStore(Path(tmp) / "history")

            with self.assertRaises(HistorySnapshotAssetError):
                store.write_bundle_grouped(
                    _bundle_with_portrait("missing.png"),
                    copy_assets=True,
                    asset_source_roots=(Path(tmp),),
                )

            self.assertFalse(store.grouped_snapshot_path(_bundle_with_portrait("missing.png")).exists())


def _bundle_with_portrait(path: str) -> HistorySnapshotBundle:
    asset_ref = HistoryAssetRefSnapshot(
        path=path,
        role="character_portrait",
        label="Thoma",
    )
    return HistorySnapshotBundle(
        bundle_id="asset-test",
        created_at="2026-06-18T12:00:00Z",
        run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
        source="unit_test",
        content_language="en-us",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            name="Thoma",
                            portrait_ref=path,
                        ),
                        asset_refs=(asset_ref,),
                    ),
                ),
            ),
        ),
        asset_refs=(asset_ref,),
    )


if __name__ == "__main__":
    unittest.main()
