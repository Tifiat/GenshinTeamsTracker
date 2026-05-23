from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hoyolab_export.account_storage import (
    AccountCharacterRuntimeRecord,
    AccountWeaponObservedStack,
)
from localization import get_language, set_language
from ui.character_assets import (
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    account_character_asset_item,
    account_weapon_stack_asset_item,
    character_matches_filters,
)


class CharacterAssetRuntimeItemsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._language = get_language()

    def tearDown(self) -> None:
        set_language(self._language)

    def test_character_asset_item_uses_sqlite_runtime_record_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            portrait = Path(tmp) / "char.png"
            portrait.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(
                character_id="1001",
                name="Test Hero",
                element="Pyro",
                rarity=4,
                level=70,
                constellation=6,
                portrait_path=str(portrait),
                side_icon_path="assets/hoyolab/characters/side_icons/char_1001.png",
                base_hp=1000,
                base_atk=200,
                base_def=500,
            )

            item = account_character_asset_item(record)

        self.assertIsNotNone(item)
        metadata = item["metadata"]
        self.assertEqual(metadata["source"], "account_sqlite")
        self.assertEqual(metadata["character"]["id"], "1001")
        self.assertEqual(metadata["character"]["base_atk"], 200)
        self.assertIn("Lv.70", item["tooltip"])

    def test_weapon_asset_item_uses_observed_stack_count_not_instance_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "weapon.png"
            icon.write_bytes(b"png")
            record = AccountWeaponObservedStack(
                id=7,
                weapon_fingerprint="fingerprint",
                weapon_id="13407",
                name="Favonius Lance",
                rarity=4,
                level=70,
                refinement=5,
                promote_level=4,
                base_atk=429,
                secondary_property_type=23,
                secondary_stat_value=25.2,
                icon_path=str(icon),
                known_count=3,
            )

            item = account_weapon_stack_asset_item(record)

        self.assertIsNotNone(item)
        metadata = item["metadata"]
        self.assertEqual(metadata["source"], "account_sqlite_observed_weapon_stack")
        self.assertEqual(metadata["weapon"]["id"], "13407")
        self.assertEqual(metadata["weapon"]["known_count"], 3)
        self.assertEqual(metadata["known_count"], 3)
        self.assertIn("x3", item["tooltip"])
        self.assertIn("Восстановление энергии 25.2%", item["tooltip"])
        self.assertNotIn("Energy Recharge", item["tooltip"])
        self.assertNotIn("P23", item["tooltip"])

    def test_weapon_asset_tooltip_uses_current_ui_language_for_stat_label(self) -> None:
        set_language("en")
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "weapon.png"
            icon.write_bytes(b"png")
            record = AccountWeaponObservedStack(
                id=9,
                weapon_fingerprint="crit",
                weapon_id="15304",
                name="Slingshot",
                rarity=3,
                level=90,
                refinement=5,
                base_atk=354,
                secondary_property_type=20,
                secondary_stat_value=31.2,
                icon_path=str(icon),
            )

            item = account_weapon_stack_asset_item(record)

        self.assertIsNotNone(item)
        self.assertIn("CRIT Rate 31.2%", item["tooltip"])
        self.assertNotIn("P20", item["tooltip"])

    def test_weapon_asset_item_hides_ignored_low_rarity_weapons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "weapon.png"
            icon.write_bytes(b"png")
            record = AccountWeaponObservedStack(
                id=8,
                weapon_fingerprint="low-rarity",
                weapon_id="11101",
                name="Dull Blade",
                rarity=1,
                level=1,
                refinement=1,
                icon_path=str(icon),
                known_count=2,
            )

            item = account_weapon_stack_asset_item(record)

        self.assertIsNone(item)

    def test_character_asset_item_hides_ignored_mannequin_even_with_side_icon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            side_icon = Path(tmp) / "side.png"
            side_icon.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(
                character_id="10000117",
                name="Mannequin",
                level=1,
                side_icon_path=str(side_icon),
            )

            item = account_character_asset_item(record)

        self.assertIsNone(item)

    def test_character_asset_item_falls_back_to_side_icon_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            side_icon = Path(tmp) / "side.png"
            side_icon.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(
                character_id="1002",
                name="Side Only",
                level=20,
                side_icon_path=str(side_icon),
            )

            item = account_character_asset_item(record)

        self.assertIsNotNone(item)
        self.assertEqual(item["path"].name, "side.png")

    def test_character_asset_metadata_carries_identity_tags_for_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            portrait = Path(tmp) / "char.png"
            portrait.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(
                character_id="1003",
                name="Mona",
                element="Hydro",
                rarity=5,
                level=90,
                portrait_path=str(portrait),
                region_key="mond",
                region_name="Mondstadt",
                traits=("hexerei", "standard_5_star"),
                is_standard_5_star=True,
            )

            item = account_character_asset_item(record)

        self.assertIsNotNone(item)
        self.assertEqual(item["metadata"]["character"]["region_key"], "mond")
        self.assertIn("hexerei", item["metadata"]["character"]["traits"])
        self.assertTrue(
            character_matches_filters(
                item,
                set(),
                set(),
                set(),
                trait_filters={"hexerei"},
                standard_filter=STANDARD_FILTER_ONLY,
            )
        )
        self.assertFalse(
            character_matches_filters(
                item,
                set(),
                set(),
                set(),
                standard_filter=STANDARD_FILTER_EXCLUDE,
            )
        )


if __name__ == "__main__":
    unittest.main()
