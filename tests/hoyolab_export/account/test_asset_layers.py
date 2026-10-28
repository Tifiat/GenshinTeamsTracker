from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hoyolab_export import asset_layers


def _fake_download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    color = (240, 80, 70, 220) if require_transparency else (70, 80, 190, 255)
    Image.new("RGBA", (64, 64), color).save(destination)


class LayeredAssetCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_opaque_portrait_is_rejected_before_staging(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (64, 64), "purple").save(source, format="PNG")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "portrait.png"
            with patch("hoyolab_export.asset_layers.urllib.request.urlopen", return_value=io.BytesIO(source.getvalue())):
                with self.assertRaisesRegex(ValueError, "transparent"):
                    asset_layers._download_image(
                        "https://act.hoyolab.com/portrait.png", destination,
                        require_transparency=True,
                    )
            self.assertFalse(destination.exists())

    async def test_shared_layers_and_constellation_only_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            characters = [
                {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1, "icon": "https://act.hoyolab.com/portrait11.png"},
                {"id": 12, "element": "Pyro", "rarity": 4, "constellation": 2, "icon": "https://act.hoyolab.com/portrait12.png"},
            ]
            weapons = [{"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}]
            cards = [
                {"portrait": character["icon"], "element": "https://act.hoyolab.com/element.png",
                 "characterBackground": "https://act.hoyolab.com/character-bg.png",
                 "weaponBackground": "https://act.hoyolab.com/weapon-bg.png", "weaponRarity": "4"}
                for character in characters
            ]
            patches = (
                patch.object(asset_layers, "PROJECT_ROOT", root),
                patch.object(asset_layers, "HOYOLAB_CHARACTER_ASSETS_DIR", root / "assets/hoyolab/characters"),
                patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "assets/hoyolab/weapons"),
                patch.object(asset_layers, "SHARED_ASSETS_DIR", root / "assets/hoyolab/shared"),
                patch.object(asset_layers, "_download_image", side_effect=_fake_download),
            )
            for context in patches:
                context.start()
                self.addCleanup(context.stop)
            stage = root / "stage"
            first = await asset_layers.prepare_layered_assets(characters=characters, weapons=weapons, cards=cards, staging_root=stage)
            self.assertEqual(first["assetsDownloaded"], 6)
            self.assertEqual(first["assetsRendered"], 7)
            self.assertEqual(len(first["sharedAssets"]["elements"]), 1)
            for file in stage.rglob("*.png"):
                final = root / file.relative_to(stage)
                final.parent.mkdir(parents=True, exist_ok=True)
                file.replace(final)

            characters[0]["constellation"] = 3
            second = await asset_layers.prepare_layered_assets(characters=characters, weapons=weapons, cards=cards, staging_root=stage)
            self.assertEqual(second["assetsDownloaded"], 0)
            self.assertEqual(second["assetsRendered"], 1)
            self.assertEqual(first["characterAssets"][0]["pvp"], second["characterAssets"][0]["pvp"])
            self.assertEqual(first["characterAssets"][0]["history"], second["characterAssets"][0]["history"])
            self.assertNotEqual(first["characterAssets"][0]["crop"], second["characterAssets"][0]["crop"])
            with Image.open(root / first["characterAssets"][0]["history"]) as history:
                with Image.open(root / first["characterAssets"][0]["pvp"]) as pvp:
                    self.assertNotEqual(history.getpixel((10, 10)), pvp.getpixel((10, 10)))
            legacy = root / "assets/hoyolab/characters/legacy_crop.png"
            legacy.write_bytes(b"preserve")
            obsolete_source = root / "assets/hoyolab/characters/portrait_v2_obsolete.png"
            obsolete_source.write_bytes(b"retire")
            self.assertEqual(asset_layers.cleanup_unused_v2_assets(second), [])
            self.assertTrue((root / first["characterAssets"][0]["crop"]).exists())
            self.assertTrue((root / second["characterAssets"][0]["pvp"]).exists())
            self.assertTrue(legacy.exists())
            self.assertFalse(obsolete_source.exists())

    async def test_same_rarity_background_is_downloaded_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 0,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            weapon = {"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}
            with patch.object(asset_layers, "PROJECT_ROOT", root), \
                 patch.object(asset_layers, "HOYOLAB_CHARACTER_ASSETS_DIR", root / "assets/hoyolab/characters"), \
                 patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "assets/hoyolab/weapons"), \
                 patch.object(asset_layers, "SHARED_ASSETS_DIR", root / "assets/hoyolab/shared"), \
                 patch.object(asset_layers, "_download_image", side_effect=_fake_download):
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[], staging_root=root / "stage",
                )
            self.assertEqual(manifest["assetsDownloaded"], 4)
            shared = manifest["sharedAssets"]
            self.assertEqual(shared["characterBackgrounds"]["4"], shared["weaponBackgrounds"]["4"])


if __name__ == "__main__":
    unittest.main()
