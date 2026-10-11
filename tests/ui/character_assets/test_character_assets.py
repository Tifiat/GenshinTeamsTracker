from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import call, patch

from PIL import Image
from PySide6.QtWidgets import QApplication

from hoyolab_export.account_storage import (
    AccountCharacterRuntimeRecord,
    AccountWeaponObservedStack,
)
from hoyolab_export import asset_paths
from run_workspace import profile_context
from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_variant_id
from localization import get_language, set_language
from ui.character_browser.icon_grid_adapter import build_asset_grid_items
from ui.character_assets import (
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    account_character_asset_item,
    asset_path_from_manifest_crop,
    account_weapon_stack_asset_item,
    character_matches_filters,
    character_sort_key,
    filter_icon_path,
    pvp_character_asset_item,
)


class CharacterAssetRuntimeItemsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._language = get_language()

    def tearDown(self) -> None:
        set_language(self._language)

    def test_absolute_browser_and_weapon_assets_follow_managed_profile_boundaries(self) -> None:
        from ui.app_shell import _existing_project_file_path, _normalized_character_image_paths

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            active_id, other_id = "a"*32, "b"*32
            active = project/"data/profiles"/active_id
            foreign = project/"data/profiles"/other_id/"assets/hoyolab/portrait.png"
            legacy = project/"assets/hoyolab/portrait.png"
            external = Path(temporary)/"guest-package/portrait.png"
            for path in (foreign, active/"assets/hoyolab/portrait.png", external):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            with (
                patch.object(profile_context, "PROJECT_ROOT", project),
                patch.object(profile_context, "ACCOUNT_ROOT", active),
                patch.object(profile_context, "PROFILE_ID", active_id),
                patch("ui.character_assets.character_variant_path", return_value=None),
            ):
                self.assertEqual(asset_path_from_manifest_crop(str(legacy)), active/"assets/hoyolab/portrait.png")
                self.assertEqual(asset_path_from_manifest_crop(str(external)), external)
                self.assertFalse(asset_path_from_manifest_crop(str(foreign)).is_file())
                self.assertEqual(_existing_project_file_path(str(legacy)), str(active/"assets/hoyolab/portrait.png"))
                self.assertEqual(_existing_project_file_path(str(external)), str(external))
                self.assertEqual(_existing_project_file_path(str(foreign)), "")
                self.assertEqual(_existing_project_file_path(str(project)), "")
                normalized = _normalized_character_image_paths({"portrait_path": str(external)}, asset_path=str(foreign))
                self.assertEqual(normalized["portrait_path"], str(external))
                hero = account_character_asset_item(AccountCharacterRuntimeRecord(
                    character_id="1001", name="Hero", element="Pyro", portrait_path=str(foreign)))
                self.assertNotEqual(hero["path"], foreign)
                self.assertIsNone(account_weapon_stack_asset_item(AccountWeaponObservedStack(
                    id=1, weapon_fingerprint="foreign", weapon_id="1001", name="Weapon", rarity=4, icon_path=str(foreign))))

    def test_ordinary_constellation_is_a_runtime_badge_on_the_same_raw_portrait(self) -> None:
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baked, raw = root / "char_v2_old.png", root / "raw.png"
            for path in (baked, raw):
                Image.new("RGBA", (8, 8), "blue").save(path)
            record = AccountCharacterRuntimeRecord(character_id="1001", name="Hero", element="Geo", rarity=4,
                                                   constellation=0, portrait_path=str(baked))
            with patch("ui.character_assets.character_variant_path", side_effect=lambda _id, variant: {
                "crop": baked, "portrait": raw,
            }.get(variant)):
                first = account_character_asset_item(record)
                second = account_character_asset_item(replace(record, constellation=6))
            self.assertEqual(first["path"], raw)
            self.assertEqual(second["path"], raw)
            for asset, expected in ((first, "C0"), (second, "C6")):
                grid_item = build_asset_grid_items([asset], key_for_asset=lambda _asset: "1001").items[0]
                self.assertEqual([badge.text for badge in grid_item.badges], [expected])
                self.assertEqual(grid_item.badges[0].position, "top_right")
                self.assertEqual(len(grid_item.overlay_icons), 1)
                self.assertIsNotNone(grid_item.background)

    def test_missing_neutral_portrait_never_reuses_a_known_baked_constellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            baked = Path(temporary) / "char_v2_old.png"
            Image.new("RGBA", (8, 8), "blue").save(baked)
            record = AccountCharacterRuntimeRecord(character_id="1001", name="Hero", element="Geo", rarity=4,
                                                   constellation=4, portrait_path=str(baked))
            with patch("ui.character_assets.character_variant_path", side_effect=lambda _id, variant: baked if variant == "crop" else None):
                asset = account_character_asset_item(record)
            self.assertNotEqual(asset["path"], baked)
            self.assertEqual(asset["path"], filter_icon_path("element_geo.png"))
            self.assertTrue(asset["metadata"]["portrait_missing"])

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
        set_language("ru")
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

    def test_pvp_variant_keeps_seat_badges_outside_portrait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            browser = folder / "browser.png"
            pvp = folder / "pvp.png"
            browser.write_bytes(b"browser")
            pvp.write_bytes(b"pvp")
            item = {
                "path": browser,
                "metadata": {
                    "portrait_pvp_path": str(pvp),
                    "character": {"id": "1", "portrait_path": str(browser), "constellation": 6},
                    "owner_badges": [{"label": "C6"}],
                },
            }
            converted = pvp_character_asset_item(item)
            self.assertEqual(converted["path"], pvp)
            self.assertEqual(converted["metadata"]["character"]["portrait_path"], str(pvp))
            self.assertEqual(converted["metadata"]["owner_badges"], [{"label": "C6"}])
            self.assertEqual(item["path"], browser)

    def test_foreign_profile_keeps_packaged_portrait_when_no_neutral_variant_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            portrait = Path(tmp) / "guest.png"
            portrait.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(character_id="1001", name="Guest", portrait_path=str(portrait))
            with patch("ui.character_assets.character_variant_path", return_value=None) as lookup:
                item = account_character_asset_item(record)
            self.assertEqual(lookup.call_args_list, [call("1001", "crop"), call("1001", "portrait")])
            self.assertNotIn("portrait_pvp_path", item["metadata"])

    def test_foreign_profile_reuses_neutral_variant_by_game_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            browser = folder / "browser.png"
            guest = folder / "guest.png"
            pvp = folder / "pvp.png"
            browser.write_bytes(b"browser")
            guest.write_bytes(b"guest")
            pvp.write_bytes(b"pvp")
            record = AccountCharacterRuntimeRecord(character_id="1001", name="Guest", constellation=6, portrait_path=str(guest))
            with patch("ui.character_assets.character_variant_path", side_effect=lambda _id, variant: {
                "crop": browser, "portrait": pvp,
            }.get(variant)):
                item = account_character_asset_item(record)
            self.assertEqual(item["metadata"]["portrait_pvp_path"], str(pvp))
            self.assertNotIn("portrait_history_path", item["metadata"])
            converted = pvp_character_asset_item(item)
            self.assertEqual(converted["path"], pvp)
            self.assertEqual(converted["metadata"]["character"]["constellation"], 6)

    def test_pvp_does_not_reuse_baked_browser_when_transparent_layer_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            browser = Path(tmp) / "baked.png"
            browser.write_bytes(b"browser-with-background-and-constellation")
            item = {"path": browser, "metadata": {"source": "account_sqlite",
                "character": {"id": "1001", "constellation": 6,
                    "portrait_path": str(browser), "side_icon_path": str(browser), "icon_path": str(browser)}}}
            converted = pvp_character_asset_item(item)
            self.assertFalse(converted["path"].is_file())
            self.assertEqual(converted["metadata"]["character"]["portrait_path"], "")
            self.assertEqual(converted["metadata"]["character"]["side_icon_path"], "")
            self.assertEqual(converted["metadata"]["character"]["icon_path"], "")
            self.assertEqual(converted["metadata"]["character"]["constellation"], 6)

    def test_pvp_preserves_known_neutral_side_portrait_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            portrait = Path(tmp) / "side.png"
            portrait.write_bytes(b"png")
            record = AccountCharacterRuntimeRecord(
                character_id="1001", name="Hero", element="Pyro", rarity=5,
                constellation=3, side_icon_path=str(portrait),
            )
            with patch("ui.character_assets.character_variant_path", return_value=None):
                item = account_character_asset_item(record)
            converted = pvp_character_asset_item(item)
            self.assertEqual(converted["path"], portrait)
            self.assertEqual(converted["metadata"]["character"]["portrait_path"], str(portrait))
            self.assertEqual(converted["metadata"]["character"]["constellation"], 3)

    def test_pvp_never_treats_a_directory_as_a_missing_portrait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            converted = pvp_character_asset_item({
                "path": Path(tmp), "metadata": {
                    "source": "account_sqlite", "portrait_is_neutral": True,
                    "portrait_pvp_path": tmp, "character": {"id": "1"},
                },
            })
            self.assertEqual(converted["metadata"]["character"]["portrait_path"], "")

    def test_history_uses_raw_portrait_and_weapon_only_for_matching_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {key: root / f"{key}.png" for key in (
                "browser", "portrait", "history", "weapon", "raw_weapon", "guest",
            )}
            for key in ("weapon", "raw_weapon"):
                paths[key] = root / "assets" / "hoyolab" / "weapons" / f"{key}.png"
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            character = AccountCharacterRuntimeRecord(character_id="1001", name="Hero", portrait_path=str(paths["browser"]))
            with patch("ui.character_assets.character_variant_path", side_effect=lambda _id, variant: {
                "crop": paths["browser"], "portrait": paths["portrait"], "history": paths["history"],
            }.get(variant)):
                item = account_character_asset_item(character)
            self.assertEqual(item["path"], paths["portrait"])
            self.assertTrue(item["metadata"]["portrait_is_neutral"])
            self.assertEqual(item["metadata"]["character"]["portrait_history_path"], str(paths["portrait"]))
            manifest = {"weaponAssets": [{
                "weapon": {"id": 21},
                "crop": paths["weapon"].relative_to(root).as_posix(),
                "icon": paths["raw_weapon"].relative_to(root).as_posix(),
            }]}
            with (
                patch.object(asset_paths, "ACCOUNT_ROOT", root),
                patch("run_workspace.profile_context.ACCOUNT_ROOT", root),
                patch.object(asset_paths, "current_manifest", return_value=manifest),
            ):
                weapon = AccountWeaponObservedStack(id=1, weapon_fingerprint="weapon", weapon_id="21", name="Weapon", rarity=4,
                                                   icon_path=str(paths["weapon"]))
                self.assertEqual(weapon.to_team_builder_weapon_ref()["icon_transparent_path"], str(paths["raw_weapon"]))
                guest = AccountWeaponObservedStack(id=2, weapon_fingerprint="guest", weapon_id="21", name="Guest", rarity=4,
                                                  icon_path=str(paths["guest"]))
                self.assertEqual(guest.to_team_builder_weapon_ref()["icon_transparent_path"], "")


    def test_element_filter_always_uses_shipped_asset_even_with_an_old_manifest(self) -> None:
        with patch.object(asset_paths, "current_manifest", return_value={
            "sharedAssets": {"elements": {"geo": "assets/hoyolab/shared/old_geo.png"}},
        }):
            self.assertEqual(filter_icon_path("element_geo.png"), asset_paths.PROJECT_ROOT / "assets/filters/element_geo.png")

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

    def test_traveler_variants_reuse_neutral_portrait_and_layer_each_element(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            portrait = root / "portrait.png"
            baked_anchor = root / "baked_cryo.png"
            Image.new("RGBA", (24, 24), "white").save(portrait)
            Image.new("RGBA", (24, 24), "red").save(baked_anchor)
            source_id = 10000005
            records = []
            for element in TRAVELER_ELEMENTS:
                character_id = (
                    source_id
                    if element == "Cryo"
                    else traveler_variant_id(source_id, element)
                )
                records.append(AccountCharacterRuntimeRecord(
                    character_id=str(character_id),
                    name="Lumine",
                    element=element,
                    rarity=5,
                    level=90,
                    constellation=4,
                    portrait_path=str(baked_anchor),
                    traits=("standard_5_star",),
                    is_standard_5_star=True,
                ))

            def manifest_path(character_id, variant):
                self.assertEqual(character_id, source_id)
                return {
                    "crop": baked_anchor,
                    "portrait": portrait,
                }.get(variant)

            with patch(
                "ui.character_assets.character_variant_path",
                side_effect=manifest_path,
            ):
                assets = [account_character_asset_item(record) for record in records]

            self.assertTrue(all(asset is not None for asset in assets))
            items = [asset for asset in assets if asset is not None]
            for record, asset in zip(records, items):
                character = asset["metadata"]["character"]
                self.assertEqual(asset["path"], portrait)
                self.assertTrue(asset["metadata"]["portrait_is_neutral"])
                self.assertEqual(character["source_character_id"], str(source_id))
                self.assertEqual(
                    character["canonical_name"],
                    f"Traveler ({record.element})",
                )
                self.assertEqual(character["element"], record.element)
                self.assertEqual(character["portrait_path"], str(portrait))
                self.assertTrue(character["is_standard_5_star"])
                self.assertEqual(asset["metadata"]["portrait_pvp_path"], str(portrait))

                self.assertTrue(character_matches_filters(
                    asset, {record.element}, set(), set(),
                    standard_filter=STANDARD_FILTER_ONLY,
                ))
                wrong_element = next(
                    value for value in TRAVELER_ELEMENTS if value != record.element
                )
                self.assertFalse(character_matches_filters(
                    asset, {wrong_element}, set(), set(),
                ))
                self.assertFalse(character_matches_filters(
                    asset, set(), set(), set(),
                    standard_filter=STANDARD_FILTER_EXCLUDE,
                ))

            icons = root / "filter_icons"
            icons.mkdir()
            with patch(
                "ui.utils.character_card_layers.filter_icon_path",
                side_effect=lambda name: icons / name,
            ):
                grid = build_asset_grid_items(
                    items,
                    key_for_asset=lambda asset: asset["metadata"]["character"]["id"],
                )
            self.assertEqual(len({item.item_id for item in grid.items}), 7)
            self.assertEqual(
                [Path(item.overlay_icons[0].icon_path).name for item in grid.items],
                [f"element_{element.lower()}.png" for element in TRAVELER_ELEMENTS],
            )
            sorted_names = [
                asset["metadata"]["character"]["canonical_name"]
                for asset in sorted(items, key=character_sort_key)
            ]
            self.assertEqual(sorted_names, sorted(sorted_names, key=str.casefold))

    def test_traveler_missing_portrait_uses_side_icon_then_element_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baked_anchor = root / "baked_pyro.png"
            side_icon = root / "side_icon.png"
            fallback_icon = root / "element_pyro.png"
            for path in (baked_anchor, side_icon, fallback_icon):
                Image.new("RGBA", (24, 24), "white").save(path)
            character_id = traveler_variant_id(10000007, "Pyro")
            record = AccountCharacterRuntimeRecord(
                character_id=str(character_id),
                name="Aether",
                element="Pyro",
                rarity=5,
                level=80,
                constellation=3,
                portrait_path=str(baked_anchor),
                side_icon_path=str(side_icon),
                traits=("standard_5_star",),
                is_standard_5_star=True,
            )

            with patch(
                "ui.character_assets.character_variant_path",
                side_effect=lambda _character_id, variant: (
                    baked_anchor if variant == "crop" else None
                ),
            ):
                side_item = account_character_asset_item(record)
            self.assertEqual(side_item["path"], side_icon)
            self.assertTrue(side_item["metadata"]["portrait_missing"])
            self.assertEqual(pvp_character_asset_item(side_item)["path"], side_icon)

            record = AccountCharacterRuntimeRecord(
                character_id=str(character_id),
                name="Aether",
                element="Pyro",
                rarity=5,
                level=80,
                constellation=3,
                portrait_path=str(baked_anchor),
                traits=("standard_5_star",),
                is_standard_5_star=True,
            )
            with (
                patch(
                    "ui.character_assets.character_variant_path",
                    return_value=None,
                ),
                patch(
                    "ui.character_assets.filter_icon_path",
                    return_value=fallback_icon,
                ),
            ):
                fallback_item = account_character_asset_item(record)
            self.assertIsNotNone(fallback_item)
            self.assertEqual(fallback_item["path"], fallback_icon)
            self.assertNotEqual(fallback_item["path"], baked_anchor)
            self.assertTrue(fallback_item["metadata"]["portrait_missing"])
            self.assertEqual(
                pvp_character_asset_item(fallback_item)["path"],
                fallback_icon,
            )

    def test_missing_imported_element_layer_uses_tracked_filter_icon(self) -> None:
        for element in TRAVELER_ELEMENTS:
            icon_name = f"element_{element.lower()}.png"
            with patch("ui.character_assets.element_icon_path", return_value=None):
                path = filter_icon_path(icon_name)
            self.assertEqual(path.name, icon_name)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
