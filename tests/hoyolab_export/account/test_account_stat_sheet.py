from __future__ import annotations

import unittest

from hoyolab_export.account_stat_sheet import (
    PROPERTY_TOTAL_ATK,
    PROPERTY_TOTAL_DEF,
    PROPERTY_TOTAL_HP,
    PROPERTY_WEAPON_BASE_ATK,
    WARNING_BASE_ATK_MISSING,
    WARNING_BASE_DEF_MISSING,
    extract_account_character_base_values,
    extract_account_weapon_property_values,
    parse_account_character_stat_sheet,
)


def detail_record() -> dict:
    return {
        "base": {
            "id": 10000050,
            "name": "Thoma",
        },
        "base_properties": [
            {"property_type": PROPERTY_TOTAL_HP, "base": "8440", "add": "13732", "final": "22173"},
            {"property_type": PROPERTY_TOTAL_ATK, "base": "594", "add": "550", "final": "1143"},
            {"property_type": PROPERTY_TOTAL_DEF, "base": "613", "add": "274", "final": "887"},
        ],
        "extra_properties": [
            {"property_type": 20, "base": "54.8%", "add": "", "final": "54.8%"},
            {"property_type": 22, "base": "63.2%", "add": "", "final": "63.2%"},
        ],
        "element_properties": [
            {"property_type": 40, "base": "46.6%", "add": "", "final": "46.6%"},
        ],
        "selected_properties": [
            {"property_type": PROPERTY_TOTAL_HP, "base": "8440", "add": "13732", "final": "22173"},
            {"property_type": 20, "base": "54.8%", "add": "", "final": "54.8%"},
        ],
        "weapon": {
            "id": 13407,
            "name": "Favonius Lance",
            "level": 70,
            "affix_level": 5,
            "promote_level": 4,
            "desc": "Generates particles.",
            "main_property": {
                "property_type": PROPERTY_WEAPON_BASE_ATK,
                "base": "",
                "add": "",
                "final": "429",
            },
            "sub_property": {
                "property_type": 23,
                "base": "",
                "add": "",
                "final": "25.2%",
            },
        },
    }


class AccountStatSheetTest(unittest.TestCase):
    def test_parse_preserves_property_type_rows_without_localized_names(self) -> None:
        sheet = parse_account_character_stat_sheet(detail_record())

        self.assertEqual(sheet.character_id, "10000050")
        self.assertEqual(sheet.character_name, "Thoma")
        self.assertEqual([row.property_type for row in sheet.base_properties], [2000, 2001, 2002])
        self.assertEqual(sheet.extra_properties[0].property_type, 20)
        self.assertEqual(sheet.element_properties[0].property_type, 40)
        self.assertEqual(sheet.selected_properties[1].final, "54.8%")

    def test_parse_weapon_main_sub_properties_and_metadata(self) -> None:
        weapon = extract_account_weapon_property_values(detail_record())

        self.assertEqual(weapon.id, "13407")
        self.assertEqual(weapon.level, 70)
        self.assertEqual(weapon.refinement, 5)
        self.assertEqual(weapon.promote_level, 4)
        self.assertEqual(weapon.desc, "Generates particles.")
        self.assertEqual(weapon.main_property.property_type, PROPERTY_WEAPON_BASE_ATK)
        self.assertEqual(weapon.main_property.final, "429")
        self.assertEqual(weapon.sub_property.property_type, 23)
        self.assertEqual(weapon.sub_property.final, "25.2%")

    def test_derives_character_base_atk_from_sheet_atk_minus_weapon_atk(self) -> None:
        values = extract_account_character_base_values(detail_record())

        self.assertEqual(values.base_hp, "8440")
        self.assertEqual(values.base_atk, "165")
        self.assertEqual(values.base_def, "613")
        self.assertEqual(values.warnings, ())

    def test_missing_optional_lists_are_empty_and_missing_base_rows_warn(self) -> None:
        sheet = parse_account_character_stat_sheet({"base": {"id": 1, "name": "Amber"}})
        values = extract_account_character_base_values(sheet)

        self.assertEqual(sheet.base_properties, ())
        self.assertEqual(sheet.extra_properties, ())
        self.assertEqual(sheet.element_properties, ())
        self.assertEqual(sheet.selected_properties, ())
        self.assertIn(WARNING_BASE_ATK_MISSING, values.warnings)
        self.assertIn(WARNING_BASE_DEF_MISSING, values.warnings)


if __name__ == "__main__":
    unittest.main()
