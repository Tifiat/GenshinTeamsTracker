from __future__ import annotations

import unittest

from run_workspace.gcsim.virtual_roster import (
    GcsimCatalogWeapon,
    GcsimVirtualSlotOverride,
    compatible_weapons,
    max_virtual_promote_level,
    max_virtual_talent_level,
    parse_character_catalog,
    parse_weapon_catalog,
)


CHARACTERS = '''
var CharacterMap = map[keys.Char]*model.AvatarData{
    keys.TestHero: {
        Id: 1,
        Key: "testhero",
        WeaponClass: model.WeaponType_WEAPON_POLE,
        IconName: "UI_AvatarIcon_TestHero",
        Stats: &model.AvatarStatsData{BaseHp: 1},
    },
    keys.SwordHero: {
        Key: "swordhero",
        WeaponClass: model.WeaponType_WEAPON_SWORD_ONE_HAND,
    },
}
'''

WEAPONS = '''
var WeaponMap = map[keys.Weapon]*model.WeaponData{
    keys.TestSpear: {
        Key: "testspear",
        WeaponClass: model.WeaponType_WEAPON_POLE,
        ImageName: "UI_EquipIcon_TestSpear",
        BaseStats: &model.WeaponStatsData{BaseProps: nil},
    },
    keys.TestBow: {
        Key: "testbow",
        WeaponClass: model.WeaponType_WEAPON_BOW,
    },
}
'''


class GcsimVirtualRosterTest(unittest.TestCase):
    def test_virtual_level_uses_highest_legal_ascension_at_boundaries(self) -> None:
        expected = {
            20: (1, 1),
            40: (2, 2),
            50: (3, 4),
            60: (4, 6),
            70: (5, 8),
            80: (6, 10),
            90: (6, 10),
        }
        for level, (phase, talent) in expected.items():
            with self.subTest(level=level):
                self.assertEqual(max_virtual_promote_level(level), phase)
                self.assertEqual(max_virtual_talent_level(level), talent)

    def test_override_derives_80_as_80_over_90_and_moves_as_one_profile(self) -> None:
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=1,
            character_key="testhero",
            character_name="TestHero",
            character_weapon_type="polearm",
            character_level=80,
            character_promote_level=5,
            talent_normal=10,
            talent_skill=10,
            talent_burst=10,
        )

        moved = override.moved_to(1, 3)

        self.assertEqual(override.character_promote_level, 6)
        self.assertEqual((moved.team_index, moved.slot_index), (1, 3))
        self.assertEqual(moved.character_key, override.character_key)
        self.assertEqual(moved.talent_skill, 10)
    def test_catalog_parser_keeps_stable_key_and_weapon_type(self) -> None:
        characters = tuple(parse_character_catalog(CHARACTERS))
        weapons = tuple(parse_weapon_catalog(WEAPONS))

        self.assertEqual([item.gcsim_key for item in characters], ["testhero", "swordhero"])
        self.assertEqual(characters[0].weapon_type, "polearm")
        self.assertEqual(characters[0].icon_name, "UI_AvatarIcon_TestHero")
        self.assertEqual(weapons[0].weapon_type, "polearm")
        self.assertEqual(weapons[0].icon_name, "UI_EquipIcon_TestSpear")
        self.assertEqual(
            [item.gcsim_key for item in compatible_weapons(characters[0], weapons)],
            ["testspear"],
        )

    def test_virtual_override_validates_ranges_and_weapon_compatibility(self) -> None:
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=2,
            character_key="testhero",
            character_name="TestHero",
            character_weapon_type="polearm",
            constellation=6,
        ).with_weapon(
            GcsimCatalogWeapon(
                gcsim_key="testspear",
                display_name="TestSpear",
                weapon_type="polearm",
            )
        )
        payload = override.to_dict()

        self.assertEqual(payload["character"]["gcsim_key"], "testhero")
        self.assertEqual(payload["character"]["constellation"], 6)
        self.assertEqual(payload["weapon"]["refinement"], 1)
        self.assertEqual(payload["profile_status"], "incomplete")

        with self.assertRaises(ValueError):
            GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=0,
                character_key="testhero",
                character_name="TestHero",
                character_weapon_type="polearm",
                constellation=7,
            )

        with self.assertRaises(ValueError):
            GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=0,
                character_key="testhero",
                character_name="TestHero",
                character_weapon_type="polearm",
                weapon_key="testbow",
                weapon_name="TestBow",
                weapon_type="bow",
            )

    def test_complete_profile_serializes_explicit_inputs(self) -> None:
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=0,
            character_key="testhero",
            character_name="TestHero",
            character_weapon_type="polearm",
            weapon_key="testspear",
            weapon_name="TestSpear",
            weapon_type="polearm",
            constellation=2,
            refinement=4,
            character_level=90,
            character_promote_level=6,
            talent_normal=8,
            talent_skill=10,
            talent_burst=9,
            weapon_level=90,
            weapon_promote_level=6,
            artifact_build_id=42,
            artifact_build_name="Virtual build",
        )

        payload = override.to_dict()

        self.assertEqual(payload["profile_status"], "ready")
        self.assertEqual(payload["missing_profile_fields"], [])
        self.assertEqual(payload["character"]["level"], 90)
        self.assertEqual(payload["character"]["talents"]["skill"], 10)
        self.assertEqual(payload["weapon"]["level"], 90)
        self.assertEqual(payload["artifact_build_id"], 42)


if __name__ == "__main__":
    unittest.main()
