from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hoyolab_export import asset_paths, bundled_assets


class BundledAssetPathTest(unittest.TestCase):
    def test_manifest_paths_follow_relocated_package_and_reject_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = root / "account"
            account_icon = account / "assets/hoyolab/characters/portrait_v2_11.png"
            account_icon.parent.mkdir(parents=True)
            account_icon.write_bytes(b"account icon")
            outside = root / "outside.png"
            outside.write_bytes(b"outside")

            for location in ("package-a", "package-b"):
                package = root / location
                element = package / "assets/filters/element_pyro.png"
                background = package / "assets/card_backgrounds/rarity_4.png"
                for path in (element, background):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"bundled")
                with patch.object(asset_paths, "PROJECT_ROOT", package), \
                     patch.object(asset_paths, "ACCOUNT_ROOT", account), \
                     patch.object(asset_paths, "account_asset_path", side_effect=lambda value: account / value):
                    self.assertEqual(
                        asset_paths.existing_manifest_asset("assets/filters/element_pyro.png"), element,
                    )
                    self.assertEqual(
                        asset_paths.existing_manifest_asset("assets/card_backgrounds/rarity_4.png"),
                        background,
                    )
                    self.assertEqual(
                        asset_paths.existing_manifest_asset("assets/hoyolab/characters/portrait_v2_11.png"),
                        account_icon,
                    )
                    self.assertEqual(asset_paths.element_icon_path("Pyro"), element)
                    self.assertEqual(asset_paths.character_background_path(4), background)
                    self.assertEqual(bundled_assets.bundled_shared_assets(package), {
                        "elements": {"pyro": "assets/filters/element_pyro.png"},
                        "characterBackgrounds": {"4": "assets/card_backgrounds/rarity_4.png"},
                        "weaponBackgrounds": {"4": "assets/card_backgrounds/rarity_4.png"},
                    })
                    self.assertIsNone(asset_paths.existing_manifest_asset("assets/filters/arbitrary.png"))
                    self.assertIsNone(asset_paths.existing_manifest_asset("assets/card_backgrounds/rarity_6.png"))
                    self.assertIsNone(asset_paths.existing_manifest_asset("../outside.png"))
                    self.assertIsNone(asset_paths.existing_manifest_asset(outside))

    def test_missing_shipped_file_has_no_account_cache_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "package"
            account = root / "account"
            old_element = account / "assets/hoyolab/shared/element_v2_pyro_old.png"
            old_element.parent.mkdir(parents=True)
            old_element.write_bytes(b"old cache")
            with patch.object(asset_paths, "PROJECT_ROOT", package), \
                 patch.object(asset_paths, "ACCOUNT_ROOT", account), \
                 patch.object(asset_paths, "account_asset_path", side_effect=lambda value: account / value):
                self.assertIsNone(asset_paths.element_icon_path("pyro"))
                self.assertIsNone(asset_paths.character_background_path(4))
                self.assertIsNone(
                    asset_paths.existing_manifest_asset("assets/filters/element_pyro.png")
                )


if __name__ == "__main__":
    unittest.main()
