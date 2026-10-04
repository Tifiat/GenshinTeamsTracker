"""Headless fixture integration; physical PvP smoke acceptance belongs to the user."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from hoyolab_export.artifact_db import create_build_preset, upsert_artifact_set_bonus_description
from hoyolab_export.account_equipment import equip_artifact
from run_workspace.pvp.deck_preset import PvpDeckPreset, save_deck_preset, weapon_ref_from_asset
from run_workspace.pvp.profile_package import export_pvp_profile_package
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel
from tests.ui.pvp_browser.test_pvp_browser import (
    _asset_character_id, _create_test_asset_images, _seed_pvp_build_db,
    _valid_character_assets, _weapon_asset,
)


class PvpBuildFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        portrait, weapon = _create_test_asset_images(str(self.root))
        self.characters = _valid_character_assets(24, image_path=portrait)
        self.weapons = [_weapon_asset("11401", "Fixture sword", weapon_type=1,
            weapon_type_name="Sword", known_count=24, image_path=weapon)]
        self.local_db = self.root / "local.sqlite"
        self.remote_db = self.root / "remote.sqlite"
        self.local_decks = self.root / "local-decks"
        remote_decks = self.root / "remote-decks"
        for label, path, directory in (("local", self.local_db, self.local_decks),
                                       ("remote", self.remote_db, remote_decks)):
            _seed_pvp_build_db(path, characters=self.characters, weapons=self.weapons)
            with closing(sqlite3.connect(path)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("""INSERT INTO artifact_sets(set_uid,hoyowiki_entry_id,display_name,fallback_name,updated_at)
                    VALUES ('fixture-set','hoyowiki-fixture','Fixture Set','Fixture Set','2026-01-01')""")
                upsert_artifact_set_bonus_description(conn, set_uid="fixture-set", lang="en-us",
                    piece_count=2, description="ATK +18%.")
                for artifact_id, pos in ((7, 1), (8, 1), (9, 2)):
                    conn.execute("""INSERT INTO artifacts
                        (id,fingerprint,name,set_uid,set_name,pos,pos_name,rarity,level,
                         main_property_type,main_property_name,main_property_value,first_seen_at,last_seen_at)
                        VALUES (?, ?, ?, 'fixture-set', 'Fixture Set', ?, 'Fixture', 5, 20,
                                1, 'HP', '4780', '2026-01-01', '2026-01-01')""",
                        (artifact_id, f"{label}-{artifact_id}", f"{label} artifact {artifact_id}", pos))
                create_build_preset(conn, name=f"{label} build", slots={1: 7, 2: 9},
                    targets=[{"target_type": "character", "character_id": int(_asset_character_id(asset)),
                              "character_name": "Fixture"} for asset in self.characters])
                equip_artifact(conn, int(_asset_character_id(self.characters[0])), 7)
                conn.commit()
            save_deck_preset(PvpDeckPreset(deck_id=label, name=label,
                character_ids=tuple(_asset_character_id(asset) for asset in self.characters),
                weapon_refs=tuple(weapon_ref_from_asset(asset) for asset in self.weapons)), directory)
        archive = self.root / "remote.gttpvp"
        export_pvp_profile_package(archive, db_path=self.remote_db, deck_dir=remote_decks,
            character_asset_paths={_asset_character_id(asset): portrait for asset in self.characters})
        self.workspace = PvpWorkspace(db_path=self.local_db, deck_dir=self.local_decks,
            character_assets_provider=lambda: self.characters, weapon_assets_provider=lambda: self.weapons)
        self.addCleanup(self.workspace.close)
        self.assertTrue(self.workspace.import_profile_for_seat("player_2", archive))
        self.assertTrue(self.workspace.start_local_draft("local", "remote"))
        for _ in range(22):
            if self.workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
                break
            self.assertTrue(self.workspace.draft_workspace.click_legal_character_for_test())
        self.assertTrue(self.workspace.continue_to_assignment())
        self.context = self.workspace.build_flow_context
        for seat in ("player_1", "player_2"):
            context = self.context.seat(seat)
            self.assertTrue(context.add_or_replace_character(next(asset for asset in context.character_assets
                if _asset_character_id(asset) == context.picked_character_ids[0])))
            context.controller.selected_team_index = 0
            context.controller.selected_slot_index = 0
        self.source_bytes = {path: path.read_bytes() for path in (self.local_db, self.remote_db,
            self.context.seat("player_2").db_path,
            self.workspace.seat_profile_provider("player_2").profile.source_db_path)}
        self.deck_bytes = {path.name: path.read_bytes() for path in self.local_decks.iterdir()}

    def assert_sources_unchanged(self) -> None:
        for path, original in self.source_bytes.items():
            self.assertEqual(path.read_bytes(), original, str(path))
        self.assertEqual({path.name: path.read_bytes() for path in self.local_decks.iterdir()}, self.deck_bytes)

class PvpArtifactBrowserTest(PvpBuildFixture):
    def test_browser_is_embedded_reused_and_isolated_per_player(self) -> None:
        first, second = (self.context.seat(seat) for seat in ("player_1", "player_2"))
        with patch("ui.artifact_browser.window.connect_db", side_effect=AssertionError("writable source")), \
             patch("ui.artifact_browser.window.load_account_character_asset_items", side_effect=AssertionError("global assets")), \
             patch("ui.artifact_browser.window.load_character_region_catalog", side_effect=AssertionError("global catalog")):
            self.assertTrue(self.workspace.open_build_artifacts("player_1"))
        browser = first.artifact_browser
        self.assertFalse(browser.isWindow())
        self.assertTrue(browser.read_only_source)
        self.assertFalse(browser.store.artifact(7).owner_character_id)
        browser.equip_clicked_artifact(7)
        character_id = first.picked_character_ids[0]
        self.assertEqual(first.equipment_state.artifact_ids_for_character(character_id), {"flower": 7})
        self.assertEqual(second.equipment_state.artifact_ids_for_character(character_id), {})
        details = first.controller.state.team(0).slot(0).character_details_data
        self.assertEqual(details["current_equipped_artifact_ids_by_slot"], {"flower": 7})
        self.assertIn("selected_build", details)
        self.workspace.close_build_browser()
        self.assertTrue(self.workspace.open_build_artifacts("player_2"))
        self.assertIsNot(second.artifact_browser, browser)
        self.assertEqual({item.name for item in second.artifact_browser.store.artifacts_by_id.values()},
                         {"remote artifact 7", "remote artifact 8", "remote artifact 9"})
        self.assertEqual(second.artifact_browser._current_equipment_slots_for_operation_target(), {})
        self.assertTrue(self.workspace.open_build_artifacts("player_1"))
        self.assertIs(first.artifact_browser, browser)
        self.assertEqual(browser._current_equipment_slots_for_operation_target(), {1: 7})
        self.assert_sources_unchanged()

    def test_apply_saved_build_updates_scoped_snapshot_and_invalidates_ready(self) -> None:
        context = self.context.seat("player_2")
        self.workspace.open_build_artifacts("player_2")
        browser = context.artifact_browser
        self.assertEqual([preset["name"] for preset in browser.build_presets], ["remote build"])
        context.ready = True
        browser.select_build_preset(browser.build_presets[0]["id"])
        browser.apply_selected_build_preset_to_current_equipment()
        self.assertFalse(context.ready)
        self.assertEqual(len(context.equipment_state.artifact_ids_for_character(context.picked_character_ids[0])), 2)
        self.assertEqual(self.context.seat("player_1").equipment_state.artifact_ids_for_character(context.picked_character_ids[0]), {})
        self.assertTrue(context.controller.state.team(0).slot(0).character_details_data["stat_snapshot"])
        _snapshot, effects = context.equipment_state.artifact_snapshot_for_character(context.picked_character_ids[0])
        self.assertEqual([(effect["stat_key"], effect["value"]) for effect in effects], [("ATK_PERCENT", 18.0)])
        self.assert_sources_unchanged()

    def test_source_edit_actions_are_unavailable_even_when_called_directly(self) -> None:
        self.workspace.open_build_artifacts("player_1")
        browser = self.context.seat("player_1").artifact_browser
        with patch("ui.artifact_browser.window.save_build_preset", side_effect=AssertionError("source save")), \
             patch("ui.artifact_browser.window.delete_build_preset", side_effect=AssertionError("source delete")), \
             patch("ui.artifact_browser.window.create_custom_set", side_effect=AssertionError("source tag")):
            browser.start_new_build_preset()
            browser.start_build_preset_edit(browser.build_presets[0]["id"])
            browser.save_build_preset_edit()
            browser.confirm_delete_build_preset(browser.build_presets[0]["id"])
            browser.create_and_edit_custom_set("blocked")
            browser._save_custom_set_edit(reload_after=True)
            browser.delete_custom_set_from_popup(1)
            browser.import_artiscan_json()
            browser.clear_json_imports()
        self.assertTrue(browser.build_create_row_widget.isHidden())
        self.assertTrue(browser.import_json_button.isHidden())
        self.assert_sources_unchanged()

    def test_right_panel_routes_artifacts_and_clear_drops_browsers_and_equipment(self) -> None:
        panel = PvpDraftRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.postdraft_artifact_buttons_by_seat["player_1"].click()
        self.assertEqual(self.context.browser_seat, "player_1")
        self.assertEqual(self.context.browser_kind, "artifact")
        self.assertEqual(self.workspace.draft_workspace.build_browser_stack.count(), 1)
        browser = self.context.seat("player_1").artifact_browser
        browser.equip_clicked_artifact(7)
        self.workspace.clear_active_draft()
        self.assertIsNone(self.workspace.build_flow_context)
        self.assertEqual(self.workspace.draft_workspace.build_browser_stack.count(), 0)
        self.assertTrue(self.workspace.draft_workspace.build_browser_frame.isHidden())
        self.assert_sources_unchanged()
