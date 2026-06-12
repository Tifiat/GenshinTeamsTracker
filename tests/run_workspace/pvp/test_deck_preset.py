from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.pvp.deck_preset import (
    DeckPresetError,
    PVP_DECK_PRESET_KIND,
    PVP_DECK_PRESET_SCHEMA_VERSION,
    create_deck_preset_from_account_assets,
    deck_preset_to_draft_deck,
    delete_deck_preset,
    load_deck_presets,
    rename_deck_preset,
    save_deck_preset,
    weapon_ref_from_asset,
)
from run_workspace.pvp.validation import validate_draft_deck


class PvpDeckPresetTests(unittest.TestCase):
    def test_save_load_rename_delete_roundtrip(self) -> None:
        now = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            preset = create_deck_preset_from_account_assets(
                [_character_asset("20000001", "Localized")],
                [_weapon_asset("11401", "Localized Sword")],
                name="Main",
                deck_id="deck-main",
                now=now,
            )

            path = save_deck_preset(preset, temp_dir)
            loaded = load_deck_presets(temp_dir)

            self.assertEqual(path, Path(temp_dir) / "deck-main.json")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].deck_id, "deck-main")
            self.assertEqual(loaded[0].name, "Main")

            renamed = rename_deck_preset(loaded[0], "Renamed", now=now)
            save_deck_preset(renamed, temp_dir)
            self.assertEqual(load_deck_presets(temp_dir)[0].name, "Renamed")
            self.assertTrue(delete_deck_preset("deck-main", temp_dir))
            self.assertEqual(load_deck_presets(temp_dir), [])

    def test_backend_draft_deck_files_in_same_directory_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "backend_deck.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "gtt.pvp_deck",
                        "deck_name": "Backend Export",
                        "characters": [],
                        "weapons": [],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(load_deck_presets(temp_dir), [])

    def test_saved_preset_identity_excludes_local_names_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preset = create_deck_preset_from_account_assets(
                [
                    _character_asset(
                        "20000001",
                        "Локализованное Имя",
                        path=r"C:\private\portraits\name.png",
                    )
                ],
                [
                    _weapon_asset(
                        "11401",
                        "Локализованный Меч",
                        weapon_type_name="Локализованный Тип",
                        path=r"C:\private\weapons\sword.png",
                    )
                ],
                name="Identity Test",
                deck_id="identity-test",
            )

            saved_text = save_deck_preset(preset, temp_dir).read_text(encoding="utf-8")

            self.assertIn(PVP_DECK_PRESET_KIND, saved_text)
            self.assertNotIn("Локализованное Имя", saved_text)
            self.assertNotIn("Локализованный Меч", saved_text)
            self.assertNotIn("Локализованный Тип", saved_text)
            self.assertNotIn("private", saved_text)
            self.assertNotIn(".png", saved_text)

    def test_create_from_account_assets_selects_all_and_prefers_fingerprint(self) -> None:
        chars = [_character_asset(str(20000000 + index), f"Char {index}") for index in range(3)]
        weapons = [
            _weapon_asset("11401", "Sword A", fingerprint="observed-stack-a"),
            _weapon_asset("11402", "Sword B", fingerprint="observed-stack-b"),
        ]

        preset = create_deck_preset_from_account_assets(
            chars,
            weapons,
            name="All",
            deck_id="all",
        )

        self.assertEqual(preset.character_ids, ("20000000", "20000001", "20000002"))
        self.assertEqual(
            tuple(ref.weapon_fingerprint for ref in preset.weapon_refs),
            ("observed-stack-a", "observed-stack-b"),
        )
        self.assertEqual(weapon_ref_from_asset(weapons[0]).key, "observed-stack-a")

    def test_conversion_to_backend_draft_deck_validates_with_current_assets(self) -> None:
        chars = [
            _character_asset(str(20000000 + index), f"Char {index}")
            for index in range(11)
        ]
        weapons = [
            _weapon_asset("11401", "Sword A", weapon_type=1, weapon_type_name="Sword"),
            _weapon_asset("13407", "Lance A", weapon_type=13, weapon_type_name="Polearm"),
        ]
        preset = create_deck_preset_from_account_assets(
            chars,
            weapons,
            name="Ready",
            deck_id="ready",
        )

        draft_deck = deck_preset_to_draft_deck(preset, chars, weapons)
        report = validate_draft_deck(draft_deck)

        self.assertTrue(report.ready, report.issue_codes())
        self.assertEqual(draft_deck.deck_name, "Ready")
        self.assertEqual(len(draft_deck.characters), 11)
        self.assertEqual(len(draft_deck.weapons), 2)
        self.assertEqual(draft_deck.source.extra["preset_id"], "ready")

    def test_empty_account_does_not_create_fake_deck(self) -> None:
        with self.assertRaises(DeckPresetError):
            create_deck_preset_from_account_assets([], [], name="Empty")


def _character_asset(
    character_id: str,
    name: str,
    *,
    weapon_type: int = 1,
    weapon_type_name: str = "Sword",
    path: str = "portrait.png",
) -> dict:
    return {
        "path": path,
        "filename": Path(path).name,
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "element": "Pyro",
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "rarity": 5,
                "level": 90,
                "constellation": 0,
                "local_portrait_path": path,
            }
        },
    }


def _weapon_asset(
    weapon_id: str,
    name: str,
    *,
    weapon_type: int = 1,
    weapon_type_name: str = "Sword",
    rarity: int = 4,
    fingerprint: str = "",
    path: str = "weapon.png",
) -> dict:
    return {
        "path": path,
        "filename": Path(path).name,
        "metadata": {
            "known_count": 1,
            "weapon": {
                "id": weapon_id,
                "name": name,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "type_name": weapon_type_name,
                "rarity": rarity,
                "level": 90,
                "refinement": 5,
                "known_count": 1,
                "source_key": fingerprint or f"fingerprint-{weapon_id}",
                "local_icon_path": path,
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
