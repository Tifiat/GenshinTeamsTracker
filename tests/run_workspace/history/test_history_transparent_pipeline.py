"""Synthetic asset -> team data -> frozen History contracts; no live account/UI.

Distinct byte fixtures identify the selected layer and its copied contents.
Raster decoding is outside this seam; existing painter tests cover it.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hoyolab_export import asset_paths
from hoyolab_export.account_storage import AccountCharacterRuntimeRecord, AccountWeaponObservedStack
from hoyolab_export.team_card_data import build_character_details_data
from run_workspace import profile_context
from run_workspace.history_snapshot import HistorySnapshotBundleStore
from run_workspace.history_snapshot_builder import build_history_snapshot_bundle
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS
from run_workspace.session import RunSessionController
from tests.run_workspace.history.test_history_snapshot_builder import (
    _context, _right_panel_model, _slot_vm, _teams_vm,
)
from ui.character_assets import account_character_asset_item


class TransparentHistoryPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="gtt-history-pipeline-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.active = self.project / "data" / "profiles" / ("a" * 32)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target in (
            "subprocess.Popen", "os.system", "socket.create_connection",
            "socket.getaddrinfo", "socket.socket.connect", "sqlite3.connect",
            "PySide6.QtCore.QProcess.start", "PySide6.QtCore.QProcess.startDetached",
            "run_workspace.profile_context.bootstrap_profile",
        ):
            guard = self.stack.enter_context(patch(
                target, side_effect=AssertionError(f"Unexpected external operation: {target}"),
            ))
            self.addCleanup(guard.assert_not_called)
        self.stack.enter_context(patch.object(profile_context, "PROJECT_ROOT", self.project))
        self.stack.enter_context(patch.object(profile_context, "ACCOUNT_ROOT", self.active))
        self.stack.enter_context(patch.object(profile_context, "PROFILE_ID", "a" * 32))
        self.stack.enter_context(patch.object(asset_paths, "ACCOUNT_ROOT", self.active))
        manifest_path = self.active / "data" / "hoyolab" / "crop_manifest.json"
        self.stack.enter_context(patch.object(asset_paths, "MANIFEST_PATH", manifest_path))
        asset_paths._read_manifest.cache_clear()
        self.addCleanup(asset_paths._read_manifest.cache_clear)

        self.layers = {
            key: self.active / "assets" / "hoyolab" / "fixture" / f"{key}.png"
            for key in ("character_crop", "raw_portrait", "composed_history", "weapon_crop", "raw_weapon")
        }
        for name, path in self.layers.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"synthetic:{name}".encode())
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        relative = lambda key: self.layers[key].relative_to(self.active).as_posix()
        manifest_path.write_text(json.dumps({
            "characterAssets": [{
                "character": {"id": 10000021},
                "crop": relative("character_crop"), "portrait": relative("raw_portrait"),
                "history": relative("composed_history"),
            }],
            "weaponAssets": [{
                "weapon": {"id": 15403},
                "crop": relative("weapon_crop"), "icon": relative("raw_weapon"),
            }],
        }), encoding="utf-8")

    def _assert_pipeline(
        self, character_bitmap: Path, weapon_bitmap: Path,
        *, expanded: Path | None, frozen_weapon: Path,
    ) -> None:
        character = AccountCharacterRuntimeRecord(
            character_id="10000021", name="Fixture Hero", element="Pyro", rarity=4,
            level=1, constellation=6, portrait_path=str(character_bitmap),
        )
        weapon = AccountWeaponObservedStack(
            id=1, weapon_fingerprint="fixture-weapon", weapon_id="15403",
            name="Fixture Bow", rarity=4, level=1, refinement=1, icon_path=str(weapon_bitmap),
        )
        item = account_character_asset_item(character)
        self.assertIsNotNone(item)
        character_input = item["metadata"]["character"]
        weapon_input = weapon.to_team_builder_weapon_ref()
        input_before = deepcopy((character_input, weapon_input))

        # No injected History keys: both inputs above came through real resolvers.
        details = build_character_details_data(
            account_character=character_input, account_weapon=weapon_input,
        ).to_dict()
        self.assertEqual((character_input, weapon_input), input_before)
        self.assertEqual(details["account_character"]["portrait_path"], str(character_bitmap))
        self.assertEqual(details["account_character"].get("portrait_history_path", ""),
                         str(expanded) if expanded else "")
        self.assertEqual(details["account_weapon"]["icon_path"], str(weapon_bitmap))
        self.assertEqual(details["account_weapon"].get("icon_transparent_path", ""),
                         str(frozen_weapon) if frozen_weapon != weapon_bitmap else "")

        session = RunSessionController.empty()
        session.team_state = (
            session.team_state.set_character(0, 0, character_input)
            .set_weapon(0, 0, weapon_input)
            .attach_character_details_data(0, 0, details)
        )
        before = deepcopy(session.state)
        # The live panel still exposes baked images. The snapshot must prefer
        # the optional raw paths propagated through team_card_data.
        live_slot = replace(
            _slot_vm(0, 0, character_title="Fixture Hero"),
            portrait_path=str(character_bitmap), weapon_image_path=str(weapon_bitmap),
            weapon_label="Fixture Bow",
        )
        panel = _right_panel_model(mode=MODE_ABYSS, teams=_teams_vm(overrides={(0, 0): live_slot}))
        bundle = build_history_snapshot_bundle(session.state, panel, _context())
        slot = bundle.teams[0].slots[0]
        self.assertEqual(slot.character.portrait_ref, str(character_bitmap))
        self.assertEqual(slot.character.expanded_portrait_ref, str(expanded) if expanded else "")
        self.assertEqual(slot.weapon.icon_ref, str(frozen_weapon))
        self.assertEqual(slot.character.constellation, 6)

        expected = (expanded or character_bitmap).read_bytes(), frozen_weapon.read_bytes()
        store = HistorySnapshotBundleStore(self.root / "saved")
        destination = store.write_bundle_grouped(bundle, copy_assets=True, asset_source_roots=(self.root,))
        for ref in bundle.asset_refs:
            Path(ref.path).unlink(missing_ok=True)
        # A frozen read must remain independent after its sources disappear.
        with patch.object(asset_paths, "current_manifest", side_effect=AssertionError("Live manifest read")) as live:
            saved = store.read_bundle(bundle.bundle_id)
            saved_slot = saved.teams[0].slots[0]
            frozen = (
                saved_slot.character.expanded_portrait_ref or saved_slot.character.portrait_ref,
                saved_slot.weapon.icon_ref,
            )
            for ref, content in zip(frozen, expected):
                self.assertTrue(ref.startswith("assets/"))
                self.assertEqual((destination.parent / ref).read_bytes(), content)
            live.assert_not_called()
        self.assertEqual(session.state, before)

    def test_matching_import_prefers_raw_over_composed_through_team_data_and_freeze(self) -> None:
        self._assert_pipeline(
            self.layers["character_crop"], self.layers["weapon_crop"],
            expanded=self.layers["raw_portrait"], frozen_weapon=self.layers["raw_weapon"],
        )

    def test_nonmatching_active_bitmaps_freeze_their_own_fallbacks(self) -> None:
        character, weapon = self.active / "different-character.png", self.active / "different-weapon.png"
        character.write_bytes(b"different active character")
        weapon.write_bytes(b"different active weapon")
        self._assert_pipeline(character, weapon, expanded=None, frozen_weapon=weapon)

    def test_foreign_packaged_bitmaps_do_not_borrow_active_import_layers(self) -> None:
        guest = self.root / "guest-package"
        guest.mkdir()
        character, weapon = guest / "character.png", guest / "weapon.png"
        character.write_bytes(b"guest character")
        weapon.write_bytes(b"guest weapon")
        self._assert_pipeline(character, weapon, expanded=None, frozen_weapon=weapon)

    def test_missing_raw_layers_keep_matching_composed_portrait_and_weapon_fallback(self) -> None:
        self.layers["raw_portrait"].unlink()
        self.layers["raw_weapon"].unlink()
        self._assert_pipeline(
            self.layers["character_crop"], self.layers["weapon_crop"],
            expanded=self.layers["composed_history"], frozen_weapon=self.layers["weapon_crop"],
        )


if __name__ == "__main__":
    unittest.main()
