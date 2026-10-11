"""Automated fixture checks; real Decks/Play smoke acceptance is user-owned."""

from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PIL import Image
from tests.ui.pvp_browser._period_fixture import fixture_period_provider_kwargs, fixture_profile_options

from run_workspace.pvp.deck_preset import PvpDeckPreset, save_deck_preset, weapon_ref_from_asset
from run_workspace.pvp.profile_package import export_pvp_profile_package
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from tests.ui.pvp_browser.test_pvp_browser import (
    _asset_character_id, _create_test_asset_images, _seed_pvp_build_db,
    _valid_character_assets, _weapon_asset,
)


class PvpProfileIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        portrait, weapon = _create_test_asset_images(str(self.root))
        self.local_portrait = Path(portrait)
        self.remote_portrait = self.root / "remote-portrait.png"
        for path, color in ((self.local_portrait, (30, 90, 170, 255)),
                            (self.remote_portrait, (180, 60, 40, 255))):
            image = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
            image.paste(color, (8, 8, 64, 64))
            image.save(path)
        self.local_characters = _valid_character_assets(24, image_path=portrait)
        for asset in self.local_characters:
            asset["metadata"]["character"]["constellation"] = 0
        self.remote_characters = copy.deepcopy(_valid_character_assets(25, image_path=str(self.remote_portrait)))
        for asset in self.remote_characters:
            asset["metadata"]["character"].update(level=80, constellation=6)
        self.local_weapons = [_weapon_asset("11401", "Fixture sword", weapon_type=1,
            weapon_type_name="Sword", known_count=24, image_path=weapon)]
        self.remote_weapons = copy.deepcopy(self.local_weapons)
        self.remote_weapons[0]["metadata"]["known_count"] = 12
        self.remote_weapons[0]["metadata"]["weapon"]["known_count"] = 12
        self.local_db = self.root / "local.sqlite"
        remote_db = self.remote_db = self.root / "remote.sqlite"
        _seed_pvp_build_db(self.local_db, characters=self.local_characters, weapons=self.local_weapons)
        _seed_pvp_build_db(remote_db, characters=self.remote_characters, weapons=self.remote_weapons)
        self.local_decks = self.root / "local-decks"
        remote_decks = self.remote_decks = self.root / "remote-decks"
        for deck_id, characters, weapons, directory in (
            ("local", self.local_characters, self.local_weapons, self.local_decks),
            ("remote", self.remote_characters, self.remote_weapons, remote_decks),
        ):
            save_deck_preset(PvpDeckPreset(deck_id=deck_id, name=deck_id,
                character_ids=tuple(_asset_character_id(asset) for asset in characters),
                weapon_refs=tuple(weapon_ref_from_asset(asset) for asset in weapons)), directory)
        self.package = self.root / "remote.gttpvp"
        export_pvp_profile_package(
            self.package,
            db_path=remote_db,
            deck_dir=remote_decks,
            options=fixture_profile_options(),
            character_asset_paths={_asset_character_id(asset): self.remote_portrait for asset in self.remote_characters},
        )
        self.workspace = PvpWorkspace(
            **fixture_period_provider_kwargs(),
            db_path=self.local_db,
            deck_dir=self.local_decks,
            character_assets_provider=lambda: self.local_characters,
            weapon_assets_provider=lambda: self.local_weapons,
        )
        self.addCleanup(self.workspace.close)
        self.source_hash = hashlib.sha256(self.local_db.read_bytes()).hexdigest()
        self.local_files = {path.name: path.read_bytes() for path in self.local_decks.iterdir()}
        self.assertTrue(self.workspace.import_profile_for_seat("player_2", self.package))

    def test_same_id_stats_are_independent_and_portrait_is_shared(self) -> None:
        local = self.workspace.deck_start_status("local", player_label="Player 1", seat="player_1")
        remote = self.workspace.deck_start_status("remote", player_label="Player 2", seat="player_2")
        self.assertTrue(local.ready, local.text)
        self.assertTrue(remote.ready, remote.text)
        character_id = _asset_character_id(self.local_characters[0])
        self.assertEqual(local.draft_deck.character_by_id[character_id].constellation, 0)
        self.assertEqual(remote.draft_deck.character_by_id[character_id].constellation, 6)
        local_asset = self.workspace._build_character_assets_for_seat("player_1")[0]
        remote_asset = self.workspace._build_character_assets_for_seat("player_2")[0]
        self.assertEqual(Path(local_asset["path"]), Path(remote_asset["path"]))
        self.assertEqual(remote_asset["metadata"]["portrait_pvp_path"], str(local_asset["path"]))
        self.assertEqual(remote_asset["metadata"]["character"]["level"], 80)
        from ui.character_browser.icon_grid_adapter import build_asset_grid_items

        for asset, expected in ((local_asset, "C0"), (remote_asset, "C6")):
            item = build_asset_grid_items([asset], key_for_asset=_asset_character_id).items[0]
            self.assertIsNotNone(item.background)
            self.assertEqual(item.overlay_icons[0].position, "top_left")
            self.assertEqual([badge.text for badge in item.badges], [expected])
        self.assertTrue(self.workspace.start_local_draft("local", "remote"))
        draft = self.workspace.draft_workspace
        expected_portrait = str(local_asset["path"])
        for scope in ("player_1", "player_2", "all"):
            draft._set_pool_scope(scope)
            item = draft.pool_items_by_character_id[character_id]
            self.assertEqual(item.icon_path, expected_portrait)
            self.assertIsNotNone(item.background)
            self.assertEqual(item.overlay_icons[0].position, "top_left")
            self.assertEqual({badge.text for badge in item.badges}, {"C0", "C6"})
        remote_only_id = _asset_character_id(self.remote_characters[-1])
        remote_only = draft.pool_items_by_character_id[remote_only_id]
        self.assertFalse(remote_only.properties["ownerP1"])
        self.assertTrue(remote_only.properties["ownerP2"])
        self.assertTrue(Path(remote_only.icon_path).is_file())
        panel = PvpDraftRightPanel(self.workspace)
        self.addCleanup(panel.close)
        for _ in range(22):
            if self.workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
                break
            self.assertTrue(draft.click_legal_character_for_test())
            board = self.workspace.active_draft_session.board_dict()
            for seat in ("player_1", "player_2"):
                for zone in ("picked", "banned"):
                    for item in panel._result_zone_items(board, seat=seat, zone=zone):
                        if item.item_id in {_asset_character_id(asset) for asset in self.local_characters}:
                            self.assertEqual(item.icon_path, expected_portrait)
        self.assertTrue(self.workspace.continue_to_assignment())
        first = self.workspace.build_flow_context.seat("player_1")
        second = self.workspace.build_flow_context.seat("player_2")
        self.assertIsNot(first.controller, second.controller)
        self.assertIsNot(first.equipment_state, second.equipment_state)
        self.assertNotEqual(first.db_path, second.db_path)
        self.assertEqual(hashlib.sha256(self.local_db.read_bytes()).hexdigest(), self.source_hash)
        self.assertEqual({path.name: path.read_bytes() for path in self.local_decks.iterdir()}, self.local_files)

    def test_all_shared_characters_keep_local_portraits(self) -> None:
        save_deck_preset(PvpDeckPreset(deck_id="remote", name="remote",
            character_ids=tuple(_asset_character_id(asset) for asset in self.local_characters),
            weapon_refs=tuple(weapon_ref_from_asset(asset) for asset in self.remote_weapons)), self.remote_decks)
        export_pvp_profile_package(
            self.package,
            db_path=self.remote_db,
            deck_dir=self.remote_decks,
            options=fixture_profile_options(),
            character_asset_paths={_asset_character_id(asset): self.remote_portrait for asset in self.remote_characters},
        )
        self.assertTrue(self.workspace.import_profile_for_seat("player_2", self.package))
        shared = self.workspace._shared_character_assets()
        self.assertEqual(len(shared), 24)
        self.assertEqual({Path(asset["path"]) for asset in shared}, {self.local_portrait})
        imported = self.workspace.seat_profile_provider("player_2").profile
        self.assertNotIn(self.local_portrait, imported.character_asset_paths.values())

    def test_missing_local_portrait_uses_archive_even_for_shared_character(self) -> None:
        asset = self.workspace.decks_workspace.character_assets[0]
        character_id = _asset_character_id(asset)
        self.local_portrait.unlink()
        packaged = self.workspace.seat_profile_provider("player_2").profile.character_asset_paths[character_id]
        selected = next(asset for asset in self.workspace._shared_character_assets()
                        if _asset_character_id(asset) == character_id)
        self.assertEqual(Path(selected["path"]), packaged)
        with Image.open(packaged) as bitmap:
            self.assertEqual(bitmap.getpixel((0, 0))[3], 0)
            self.assertEqual(bitmap.getpixel((30, 30)), (180, 60, 40, 255))
        self.assertTrue(self.workspace.start_local_draft("local", "remote"))
        for scope in ("all", "player_1", "player_2"):
            self.workspace.draft_workspace._set_pool_scope(scope)
            self.assertEqual(self.workspace.draft_workspace.pool_items_by_character_id[character_id].icon_path,
                             str(packaged))

    def test_failed_replace_keeps_previous_provider_and_success_cleans_it(self) -> None:
        previous = self.workspace.seat_profile_provider("player_2")
        previous_root = previous.db_path.parent
        broken = self.root / "broken.gttpvp"
        broken.write_bytes(b"not a ZIP")
        self.assertFalse(self.workspace.import_profile_for_seat("player_2", broken))
        self.assertIs(self.workspace.seat_profile_provider("player_2"), previous)
        self.assertTrue(previous_root.exists())
        self.assertTrue(self.workspace.import_profile_for_seat("player_2", self.package))
        self.assertFalse(previous_root.exists())
        replacement_root = self.workspace.seat_profile_provider("player_2").db_path.parent
        self.workspace.use_local_profile_for_seat("player_2")
        self.assertFalse(replacement_root.exists())
        self.assertEqual(hashlib.sha256(self.local_db.read_bytes()).hexdigest(), self.source_hash)

    def test_shutdown_closes_both_selected_imported_providers(self) -> None:
        self.assertTrue(self.workspace.import_profile_for_seat("player_1", self.package))
        roots = [self.workspace.seat_profile_provider(seat).db_path.parent
                 for seat in ("player_1", "player_2")]
        self.workspace.close_profile_providers()
        self.assertTrue(all(not path.exists() for path in roots))


if __name__ == "__main__":
    unittest.main()
