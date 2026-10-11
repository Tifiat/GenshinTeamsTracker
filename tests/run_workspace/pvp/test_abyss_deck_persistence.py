from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest

from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.deck_preset import (
    DeckPresetError, PvpDeckPreset, deck_preset_from_mapping, deck_preset_to_draft_deck,
    load_deck_presets, save_deck_preset, set_deck_preset_rules,
)
from run_workspace.pvp.profile_package import (
    export_pvp_profile_package, import_pvp_profile_package, _deck_collection_payload,
    _load_decks, PvpProfilePackageError,
)
from tests.run_workspace.pvp.test_abyss_rules import _source
from tests.run_workspace.pvp.test_profile_package import _create_account_db


class AbyssDeckPersistenceTest(unittest.TestCase):
    def test_shared_rules_are_deduplicated_and_validated_in_exchange(self):
        rules = AbyssRuleset.from_source(*_source())
        decks = tuple(set_deck_preset_rules(PvpDeckPreset(f"deck-{i}", "Abyss"), rules) for i in range(12))
        payload = _deck_collection_payload(decks)
        self.assertEqual(len(payload["rules_snapshots"]), 1)
        self.assertEqual(len(_load_decks(payload)), 12)
        self.assertLess(len(json.dumps(payload)), len(json.dumps([item.to_dict() for item in decks])) / 2)
        payload["decks"][0]["rules_snapshot_ref"] = "f" * 64
        with self.assertRaises(PvpProfilePackageError):
            _load_decks(payload)
        private = rules.to_dict()
        private["source"]["title"] = "C:/Users/private/source"
        deck = replace(decks[0], rules_snapshot=private)
        with self.assertRaises(PvpProfilePackageError):
            _deck_collection_payload((deck,))

    def test_optional_snapshot_preserves_old_free_draft_format(self):
        preset = PvpDeckPreset("deck-one", "Old")
        self.assertNotIn("rules_snapshot", preset.to_dict())
        self.assertEqual(deck_preset_from_mapping(preset.to_dict()), preset)

    def test_mismatched_and_unsafe_snapshot_are_rejected(self):
        rules = AbyssRuleset.from_source(*_source())
        preset = set_deck_preset_rules(PvpDeckPreset("rules", "Rules"), rules)
        payload = preset.to_dict()
        payload["ruleset_id"] = "abyss:" + "f" * 24
        with self.assertRaises(DeckPresetError):
            deck_preset_from_mapping(payload)
        payload = preset.to_dict()
        payload["rules_snapshot"]["credentials"] = "never-export"
        with self.assertRaises(DeckPresetError):
            deck_preset_from_mapping(payload)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(DeckPresetError):
            save_deck_preset(replace(preset, ruleset_id="free_draft_v0"), directory)

    def test_abyss_profile_export_import_keeps_pinned_rules_and_no_free_draft_minimum(self):
        rules = AbyssRuleset.from_source(*_source())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "source.sqlite"
            _create_account_db(db)
            preset = set_deck_preset_rules(PvpDeckPreset("abyss", "Abyss", character_ids=("1001", "1002")), rules)
            save_deck_preset(preset, root / "decks")
            export = export_pvp_profile_package(root / "exchange.gttpvp", deck_dir=root / "decks", db_path=db)
            with import_pvp_profile_package(export.path, temp_root=root) as imported:
                saved = imported.deck_presets[0]
                self.assertEqual(saved.ruleset_id, preset.ruleset_id)
                self.assertEqual(saved.rules_snapshot, preset.rules_snapshot)
                self.assertEqual(AbyssRuleset.from_dict(saved.rules_snapshot).content_hash, rules.content_hash)
                deck = deck_preset_to_draft_deck(saved, [], [])
                self.assertEqual(deck.ruleset_ref.ruleset_name, "Synthetic Abyss")
            self.assertFalse(imported.db_path.exists())
            self.assertEqual(load_deck_presets(root / "decks")[0].character_ids, ("1001", "1002"))
