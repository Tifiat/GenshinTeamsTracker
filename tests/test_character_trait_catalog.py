from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hoyolab_export.character_trait_catalog import (
    HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
    HOYOWIKI_HEXEREI_SOURCE_URL,
    HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
    HOYOWIKI_MOONSIGN_SOURCE_URL,
    TRAIT_HEXEREI,
    TRAIT_MOONSIGN,
    TRAIT_STANDARD_5_STAR,
    character_trait_catalog_to_dict,
    entries_with_trait,
    extract_character_trait_entries_from_hoyowiki_page,
    list_seed_character_traits,
    normalize_character_trait_name,
    refresh_character_trait_catalog,
    traits_for_character_name,
)


class CharacterTraitCatalogTest(unittest.TestCase):
    def test_seed_contains_moonsign_and_hexerei_character_groups(self) -> None:
        seed = list_seed_character_traits()
        moonsign = entries_with_trait(TRAIT_MOONSIGN, entries=seed)
        hexerei = entries_with_trait(TRAIT_HEXEREI, entries=seed)

        self.assertEqual(len(moonsign), 10)
        self.assertEqual(len(hexerei), 9)
        self.assertIn("Aino", {entry.name for entry in moonsign})
        self.assertIn("Sucrose", {entry.name for entry in hexerei})
        self.assertEqual(len(entries_with_trait(TRAIT_STANDARD_5_STAR, entries=seed)), 8)

    def test_lookup_normalizes_character_names(self) -> None:
        seed = list_seed_character_traits()
        self.assertEqual(
            traits_for_character_name("  AINO ", entries=seed),
            (TRAIT_MOONSIGN,),
        )
        self.assertEqual(traits_for_character_name("Sucrose", entries=seed), (TRAIT_HEXEREI,))
        self.assertIn(
            TRAIT_STANDARD_5_STAR,
            traits_for_character_name("Mona", entries=seed),
        )
        self.assertIn(
            TRAIT_STANDARD_5_STAR,
            traits_for_character_name("Traveler", entries=seed),
        )
        self.assertEqual(normalize_character_trait_name("Moon-Sign Aino"), "moon sign aino")

    def test_catalog_dict_is_reference_seed_not_bonus_model(self) -> None:
        data = character_trait_catalog_to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["source_urls"][TRAIT_MOONSIGN], HOYOWIKI_MOONSIGN_SOURCE_URL)
        self.assertEqual(data["source_urls"][TRAIT_HEXEREI], HOYOWIKI_HEXEREI_SOURCE_URL)
        self.assertNotIn("bonuses", data)
        self.assertIn("does not define resonance bonuses", " ".join(data["notes"]))

    def test_seed_entries_carry_hoyowiki_source_ids(self) -> None:
        seed = list_seed_character_traits()
        moonsign = entries_with_trait(TRAIT_MOONSIGN, entries=seed)[0]
        hexerei = entries_with_trait(TRAIT_HEXEREI, entries=seed)[0]

        self.assertEqual(moonsign.source_url, HOYOWIKI_MOONSIGN_SOURCE_URL)
        self.assertEqual(moonsign.source_entry_page_id, HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID)
        self.assertEqual(hexerei.source_url, HOYOWIKI_HEXEREI_SOURCE_URL)
        self.assertEqual(hexerei.source_entry_page_id, HOYOWIKI_HEXEREI_ENTRY_PAGE_ID)

    def test_extracts_character_cards_from_hoyowiki_custom_entries(self) -> None:
        page = {
            "modules": [
                {
                    "components": [
                        {
                            "data": (
                                '{"data":"<custom-entry epid=\\"8397\\" '
                                'menuid=\\"2\\" name=\\"Aino\\" />'
                                '<custom-entry epid=\\"1\\" menuid=\\"99\\" '
                                'name=\\"Not Character\\" />"}'
                            )
                        }
                    ]
                }
            ]
        }

        entries = extract_character_trait_entries_from_hoyowiki_page(
            page,
            trait=TRAIT_MOONSIGN,
            source_url=HOYOWIKI_MOONSIGN_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
            source_section="Moonsign",
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "Aino")
        self.assertEqual(entries[0].source_character_entry_page_id, "8397")

    def test_refresh_writes_cache_from_fetcher(self) -> None:
        def fake_fetcher(entry_page_id: str, _language: str) -> dict:
            name = "Aino" if entry_page_id == HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID else "Sucrose"
            return {
                "modules": [
                    {
                        "components": [
                            {
                                "data": (
                                    '{"data":"<custom-entry epid=\\"1\\" '
                                    f'menuid=\\"2\\" name=\\"{name}\\" />"}}'
                                )
                            }
                        ]
                    }
                ]
            }

        with TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "traits.json"

            catalog = refresh_character_trait_catalog(
                cache_path=cache_path,
                page_fetcher=fake_fetcher,
            )

            self.assertTrue(cache_path.exists())
            self.assertEqual(
                sorted((entry.name, entry.traits[0]) for entry in catalog.entries),
                [
                    ("Aino", TRAIT_MOONSIGN),
                    ("Dehya", TRAIT_STANDARD_5_STAR),
                    ("Diluc", TRAIT_STANDARD_5_STAR),
                    ("Jean", TRAIT_STANDARD_5_STAR),
                    ("Keqing", TRAIT_STANDARD_5_STAR),
                    ("Mona", TRAIT_STANDARD_5_STAR),
                    ("Qiqi", TRAIT_STANDARD_5_STAR),
                    ("Sucrose", TRAIT_HEXEREI),
                    ("Tighnari", TRAIT_STANDARD_5_STAR),
                    ("Traveler", TRAIT_STANDARD_5_STAR),
                ],
            )


if __name__ == "__main__":
    unittest.main()
