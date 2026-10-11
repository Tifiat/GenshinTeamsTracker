from __future__ import annotations

import asyncio
import io
import json
import threading
import time
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

from hoyolab_export import asset_layers


def _fake_download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    color = (240, 80, 70, 220) if require_transparency else (70, 80, 190, 255)
    Image.new("RGBA", (64, 64), color).save(destination)


def _patch_asset_paths(root: Path, stack: ExitStack) -> None:
    stack.enter_context(patch.object(asset_layers, "ACCOUNT_ROOT", root))
    stack.enter_context(patch.object(asset_layers, "HOYOLAB_CHARACTER_ASSETS_DIR", root / "assets/hoyolab/characters"))
    stack.enter_context(patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "assets/hoyolab/weapons"))


def _publish_stage(root: Path, staging_root: Path) -> None:
    for staged in staging_root.rglob("*.png"):
        final = root / staged.relative_to(staging_root)
        final.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(final)


class LayeredAssetCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_low_rarity_weapon_urls_never_enter_download_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weapons = [{"id": i, "rarity": rarity, "icon": f"https://act.hoyolab.com/weapon{i}.png"}
                       for i, rarity in enumerate((1, 2, "1", "2", 3, "3"), 1)]
            with patch.object(asset_layers, "ACCOUNT_ROOT", root), \
                 patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "weapons"), \
                 patch.object(asset_layers, "_download_image", side_effect=_fake_download) as download:
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[], weapons=weapons, cards=[], staging_root=root / "stage", refresh_images=True,
                )
            requested = {call.args[0] for call in download.call_args_list}
            self.assertTrue(all(weapon["icon"] not in requested for weapon in weapons[:4]))
            self.assertTrue(all(weapon["icon"] in requested for weapon in weapons[4:]))
            self.assertEqual([asset["weapon"]["id"] for asset in manifest["weaponAssets"]], [5, 6])

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

    async def test_shared_layers_and_constellation_only_change_reuses_neutral_card(self) -> None:
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
                patch.object(asset_layers, "ACCOUNT_ROOT", root),
                patch.object(asset_layers, "HOYOLAB_CHARACTER_ASSETS_DIR", root / "assets/hoyolab/characters"),
                patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "assets/hoyolab/weapons"),
                patch.object(asset_layers, "_download_image", side_effect=_fake_download),
            )
            for context in patches[:-1]:
                context.start()
                self.addCleanup(context.stop)
            downloader = patches[-1].start()
            self.addCleanup(patches[-1].stop)
            stage = root / "stage"
            first = await asset_layers.prepare_layered_assets(characters=characters, weapons=weapons, cards=cards, staging_root=stage)
            self.assertEqual(first["assetsDownloaded"], 3)
            self.assertEqual(first["assetsRendered"], 3)
            self.assertEqual(len(first["sharedAssets"]["elements"]), 1)
            self.assertEqual(
                {call.args[0] for call in downloader.call_args_list},
                {characters[0]["icon"], characters[1]["icon"], weapons[0]["icon"]},
            )
            self.assertEqual(first["sharedAssets"]["elements"]["pyro"], "assets/filters/element_pyro.png")
            self.assertEqual(
                first["sharedAssets"]["characterBackgrounds"]["4"],
                "assets/card_backgrounds/rarity_4.png",
            )
            for file in stage.rglob("*.png"):
                final = root / file.relative_to(stage)
                final.parent.mkdir(parents=True, exist_ok=True)
                file.replace(final)

            characters[0]["constellation"] = 3
            second = await asset_layers.prepare_layered_assets(characters=characters, weapons=weapons, cards=cards, staging_root=stage)
            self.assertEqual(second["assetsDownloaded"], 0)
            self.assertEqual(second["assetsRendered"], 0)
            self.assertEqual(first["characterAssets"][0]["pvp"], second["characterAssets"][0]["pvp"])
            self.assertEqual(first["characterAssets"][0]["history"], second["characterAssets"][0]["history"])
            self.assertEqual(first["characterAssets"][0]["crop"], second["characterAssets"][0]["crop"])
            self.assertEqual(downloader.call_count, 3)
            with Image.open(asset_layers.PROJECT_ROOT / "assets/card_backgrounds/rarity_4.png") as background:
                expected = background.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS)
            with Image.open(root / first["characterAssets"][0]["portrait"]) as portrait:
                expected.alpha_composite(portrait.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS))
            with Image.open(root / first["characterAssets"][0]["crop"]) as crop:
                self.assertIsNone(ImageChops.difference(crop.convert("RGBA"), expected).getbbox())
            legacy = root / "assets/hoyolab/characters/legacy_crop.png"
            legacy.write_bytes(b"preserve")
            obsolete_source = root / "assets/hoyolab/characters/portrait_v2_obsolete.png"
            obsolete_source.write_bytes(b"retire")
            self.assertEqual(asset_layers.cleanup_unused_v2_assets(second), [])
            self.assertTrue((root / first["characterAssets"][0]["crop"]).exists())
            self.assertTrue((root / second["characterAssets"][0]["pvp"]).exists())
            self.assertTrue(legacy.exists())
            self.assertFalse(obsolete_source.exists())

    async def test_all_seven_elements_and_rarity_backgrounds_are_bundled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elements = ("anemo", "cryo", "dendro", "electro", "geo", "hydro", "pyro")
            characters = [
                {"id": 100 + index, "element": element, "rarity": 4 + index % 2,
                 "icon": f"https://act.hoyolab.com/portrait-{index}.png"}
                for index, element in enumerate(elements)
            ]
            weapons = [
                {"id": 200 + rarity, "rarity": rarity,
                 "icon": f"https://act.hoyolab.com/weapon-{rarity}.png"}
                for rarity in (3, 4, 5)
            ]
            cards = [
                {"portrait": character["icon"],
                 "element": "https://act.hoyolab.com/unused-element.png",
                 "characterBackground": "https://act.hoyolab.com/unused-character-bg.png",
                 "weaponBackground": "https://act.hoyolab.com/unused-weapon-bg.png"}
                for character in characters
            ]
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                downloader = stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                manifest = await asset_layers.prepare_layered_assets(
                    characters=characters, weapons=weapons, cards=cards,
                    staging_root=root / "stage",
                )
            wanted_urls = {item["icon"] for item in (*characters, *weapons)}
            self.assertEqual({call.args[0] for call in downloader.call_args_list}, wanted_urls)
            self.assertEqual(manifest["assetTimings"]["download"]["jobs"], len(wanted_urls))
            self.assertEqual(manifest["assetsDownloaded"], len(wanted_urls))
            self.assertEqual(set(manifest["sharedAssets"]["elements"]), set(elements))
            self.assertEqual(set(manifest["sharedAssets"]["weaponBackgrounds"]), {"3", "4", "5"})
            self.assertEqual(set(manifest["sharedAssets"]["characterBackgrounds"]), {"4", "5"})
            self.assertEqual(manifest["assetsPending"], 0)

    async def test_same_rarity_background_is_shipped_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 0,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            weapon = {"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}
            with patch.object(asset_layers, "ACCOUNT_ROOT", root), \
                 patch.object(asset_layers, "HOYOLAB_CHARACTER_ASSETS_DIR", root / "assets/hoyolab/characters"), \
                 patch.object(asset_layers, "HOYOLAB_WEAPON_ASSETS_DIR", root / "assets/hoyolab/weapons"), \
                 patch.object(asset_layers, "_download_image", side_effect=_fake_download):
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[], staging_root=root / "stage",
                )
            self.assertEqual(manifest["assetsDownloaded"], 2)
            shared = manifest["sharedAssets"]
            self.assertEqual(shared["characterBackgrounds"]["4"], shared["weaponBackgrounds"]["4"])

    async def test_failed_portrait_is_local_and_other_assets_still_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            characters = [
                {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                 "icon": "https://act.hoyolab.com/portrait11.png"},
                {"id": 12, "element": "Hydro", "rarity": 5, "constellation": 2,
                 "icon": "https://act.hoyolab.com/portrait12.png"},
            ]
            weapons = [{"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}]
            cards = [
                {"portrait": character["icon"],
                 "element": f"https://act.hoyolab.com/element{character['id']}.png",
                 "characterBackground": f"https://act.hoyolab.com/character-bg{character['id']}.png",
                 "weaponBackground": "https://act.hoyolab.com/weapon-bg.png", "weaponRarity": "4"}
                for character in characters
            ]

            def download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
                if url.endswith("portrait11.png"):
                    raise urllib.error.URLError("https://private.invalid/session-cookie")
                _fake_download(url, destination, require_transparency=require_transparency)

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=download))
                manifest = await asset_layers.prepare_layered_assets(
                    characters=characters, weapons=weapons, cards=cards,
                    staging_root=root / "stage",
                )

            self.assertEqual(len(manifest["characterAssets"]), 2)
            self.assertEqual(manifest["characterAssets"][0]["portrait"], "")
            self.assertEqual(manifest["characterAssets"][0]["crop"], "")
            self.assertTrue(manifest["characterAssets"][1]["portrait"])
            self.assertTrue(manifest["characterAssets"][1]["crop"])
            self.assertTrue(manifest["weaponAssets"][0]["icon"])
            self.assertTrue(manifest["weaponAssets"][0]["crop"])
            self.assertGreater(manifest["assetsPending"], 0)
            self.assertIn(
                {"kind": "character_portrait", "key": "11", "reason": "download_failed"},
                manifest["assetErrors"],
            )
            self.assertNotIn("private.invalid", json.dumps(manifest["assetErrors"]))

    async def test_transient_download_retries_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4,
                         "icon": "https://act.hoyolab.com/retry-portrait.png"}
            calls = 0

            def download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
                nonlocal calls
                if url.endswith("retry-portrait.png"):
                    calls += 1
                    raise TimeoutError("private request detail")
                _fake_download(url, destination, require_transparency=require_transparency)

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=download))
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=root / "stage",
                )

            self.assertEqual(calls, asset_layers.MAX_DOWNLOAD_ATTEMPTS)
            self.assertEqual(manifest["characterAssets"][0]["portrait"], "")
            self.assertIn("download_failed", {item["reason"] for item in manifest["assetErrors"]})

    async def test_hot_cache_repeat_has_no_downloads_or_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            stage = root / "stage"
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                first = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )
                _publish_stage(root, stage)
                downloader = stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                second = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )

            self.assertTrue(first["characterAssets"][0]["crop"])
            self.assertEqual(downloader.call_count, 0)
            self.assertEqual(second["assetsDownloaded"], 0)
            self.assertEqual(second["assetsRendered"], 0)
            self.assertEqual(second["assetsPending"], 0)

    async def test_progress_and_timing_include_completed_cache_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            stage = root / "stage"
            first_events: list[tuple[str, int, int]] = []

            def flaky_progress(phase: str, completed: int, total: int) -> None:
                first_events.append((phase, completed, total))
                if phase == "download" and completed == 0:
                    raise RuntimeError("observer failure")

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                first = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                    progress_callback=flaky_progress,
                )
                _publish_stage(root, stage)

                second_events: list[tuple[str, int, int]] = []
                second = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                    progress_callback=lambda phase, completed, total: second_events.append(
                        (phase, completed, total)
                    ),
                )

            self.assertEqual(first["assetTimings"]["progressCallbackErrors"], 1)
            self.assertEqual(first["assetTimings"]["download"]["completed"],
                             first["assetTimings"]["download"]["jobs"])
            self.assertEqual(first["assetTimings"]["render"]["completed"],
                             first["assetTimings"]["render"]["jobs"])
            self.assertEqual(second["assetsDownloaded"], 0)
            self.assertEqual(second["assetsRendered"], 0)
            self.assertEqual(second["assetTimings"]["download"]["cacheHits"],
                             second["assetTimings"]["download"]["jobs"])
            self.assertEqual(second["assetTimings"]["render"]["cacheHits"],
                             second["assetTimings"]["render"]["jobs"])
            self.assertEqual(second["assetTimings"]["progressCallbackErrors"], 0)
            for phase in ("download", "render"):
                events = [event for event in second_events if event[0] == phase]
                self.assertTrue(events)
                self.assertEqual(events[0][1], 0)
                self.assertEqual(events[-1][1], events[-1][2])
                self.assertEqual([event[1] for event in events], sorted(event[1] for event in events))
            self.assertGreaterEqual(second["assetTimings"]["download"]["elapsedSeconds"], 0)
            self.assertGreaterEqual(second["assetTimings"]["render"]["elapsedSeconds"], 0)
            self.assertGreaterEqual(second["assetTimings"]["totalElapsedSeconds"], 0)

    async def test_download_metrics_count_validated_response_bytes_and_warm_cache_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            encoded = io.BytesIO()
            Image.new("RGBA", (64, 64), (240, 80, 70, 220)).save(encoded, format="PNG")
            response_bytes = encoded.getvalue()
            stage = root / "stage"

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def read(self, _limit: int) -> bytes:
                    time.sleep(0.005)
                    return response_bytes

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                opener = stack.enter_context(patch.object(
                    asset_layers.urllib.request, "urlopen", side_effect=lambda *_args, **_kwargs: FakeResponse(),
                ))
                first = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )
                _publish_stage(root, stage)

                cached_opener = stack.enter_context(patch.object(
                    asset_layers.urllib.request, "urlopen", side_effect=AssertionError("warm cache made a request"),
                ))
                second = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )

            first_metrics = first["assetTimings"]["download"]
            second_metrics = second["assetTimings"]["download"]
            self.assertEqual(opener.call_count, first_metrics["downloaded"])
            self.assertGreater(first_metrics["downloadedResponseBytes"], 0)
            self.assertEqual(first_metrics["downloadedResponseBytes"], len(response_bytes) * opener.call_count)
            self.assertGreater(first_metrics["requestReadSeconds"], 0)
            self.assertEqual(cached_opener.call_count, 0)
            self.assertEqual(second_metrics["downloadedResponseBytes"], 0)
            self.assertEqual(second_metrics["requestReadSeconds"], 0)

    async def test_corrupted_cached_portrait_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            stage = root / "stage"
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                first = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )
                _publish_stage(root, stage)
                cached_portrait = root / first["characterAssets"][0]["portrait"]
                cached_portrait.write_bytes(b"truncated PNG")
                downloader = stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                second = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )

            self.assertEqual(downloader.call_count, 1)
            self.assertEqual(second["assetsDownloaded"], 1)
            staged_portrait = stage / Path(second["characterAssets"][0]["portrait"])
            self.assertTrue(asset_layers._image_is_usable(staged_portrait, require_transparency=True))
            _publish_stage(root, stage)
            self.assertTrue(asset_layers._image_is_usable(cached_portrait, require_transparency=True))

    async def test_refresh_failure_keeps_valid_cached_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            stage = root / "stage"
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                first = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                )
                _publish_stage(root, stage)

                def fail_portrait_refresh(url: str, destination: Path, *, require_transparency: bool = False) -> None:
                    if url.endswith("portrait11.png"):
                        raise TimeoutError("private request detail")
                    _fake_download(url, destination, require_transparency=require_transparency)

                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=fail_portrait_refresh))
                refreshed = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[], cards=[], staging_root=stage,
                    refresh_images=True,
                )

            self.assertEqual(
                refreshed["characterAssets"][0]["portrait"],
                first["characterAssets"][0]["portrait"],
            )
            self.assertEqual(refreshed["assetsPending"], 0)
            self.assertIn(
                {"kind": "character_portrait", "key": "11", "reason": "download_failed"},
                refreshed["assetErrors"],
            )
            self.assertTrue(
                asset_layers._image_is_usable(
                    root / refreshed["characterAssets"][0]["portrait"],
                    require_transparency=True,
                )
            )

    async def test_missing_or_bad_bundle_ignores_old_shared_cache_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_root = root / "package"
            element_file = package_root / "assets/filters/element_pyro.png"
            element_file.parent.mkdir(parents=True)
            Image.new("RGBA", (72, 72), (255, 0, 0, 200)).save(element_file)
            background_file = package_root / "assets/card_backgrounds/rarity_4.png"
            old_shared = root / "assets/hoyolab/shared/rarity_bg_v2_4_old.png"
            old_shared.parent.mkdir(parents=True)
            Image.new("RGBA", (188, 188), "purple").save(old_shared)
            character = {"id": 11, "element": "Pyro", "rarity": 4,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            weapon = {"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "PROJECT_ROOT", package_root))
                downloader = stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                stage = root / "stage"
                missing = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[],
                    staging_root=stage,
                )
                _publish_stage(root, stage)
                background_file.parent.mkdir(parents=True)
                background_file.write_bytes(b"corrupt PNG")
                bad = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[], staging_root=stage,
                )
                Image.new("RGBA", (188, 188), "purple").save(background_file)
                repaired = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[], staging_root=stage,
                )

            for manifest in (missing, bad):
                self.assertEqual(manifest["assetsPending"], 3)
                self.assertEqual(manifest["characterAssets"][0]["crop"], "")
                self.assertEqual(manifest["weaponAssets"][0]["crop"], "")
                self.assertEqual(manifest["sharedAssets"]["characterBackgrounds"]["4"], "")
                self.assertIn(
                    {"kind": "shared_character_background", "key": "4", "reason": "bundled_unavailable"},
                    manifest["assetErrors"],
                )
            self.assertEqual(downloader.call_count, 2)
            self.assertEqual(repaired["assetsDownloaded"], 0)
            self.assertEqual(repaired["assetsRendered"], 2)
            self.assertEqual(repaired["assetsPending"], 0)
            self.assertEqual(
                repaired["sharedAssets"]["weaponBackgrounds"]["4"],
                "assets/card_backgrounds/rarity_4.png",
            )

    async def test_missing_element_and_rarity_metadata_is_localized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "unknown", "rarity": "?",
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            malformed_character = {"id": 12, "element": "Pyro", "rarity": 4, "icon": "https://["}
            weapon = {"id": 21, "rarity": "?", "icon": "https://act.hoyolab.com/weapon21.png"}

            def download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
                if url == "https://[":
                    raise ValueError("invalid private URL")
                _fake_download(url, destination, require_transparency=require_transparency)

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=download))
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[character, malformed_character], weapons=[weapon],
                    cards=[{"portrait": "https://["}], staging_root=root / "stage",
                )

            self.assertEqual(manifest["cardsCount"], 2)
            self.assertEqual(len(manifest["characterAssets"]), 2)
            self.assertTrue(manifest["characterAssets"][0]["portrait"])
            self.assertEqual(manifest["characterAssets"][0]["crop"], "")
            self.assertEqual(manifest["characterAssets"][1]["portrait"], "")
            self.assertTrue(manifest["weaponAssets"][0]["icon"])
            self.assertEqual(manifest["weaponAssets"][0]["crop"], "")
            kinds = {item["kind"] for item in manifest["assetErrors"]}
            self.assertIn("character_element", kinds)
            self.assertIn("character_rarity", kinds)
            self.assertIn("weapon_rarity", kinds)
            self.assertIn("invalid_source", {item["reason"] for item in manifest["assetErrors"]})
            self.assertNotIn("hoyolab.com", json.dumps(manifest["assetErrors"]))

    async def test_one_render_failure_does_not_abort_other_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character = {"id": 11, "element": "Pyro", "rarity": 4, "constellation": 1,
                         "icon": "https://act.hoyolab.com/portrait11.png"}
            weapon = {"id": 21, "rarity": 4, "icon": "https://act.hoyolab.com/weapon21.png"}
            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=_fake_download))
                stack.enter_context(patch.object(asset_layers, "_render_weapon", side_effect=OSError("private path")))
                manifest = await asset_layers.prepare_layered_assets(
                    characters=[character], weapons=[weapon], cards=[], staging_root=root / "stage",
                )

            self.assertTrue(manifest["characterAssets"][0]["crop"])
            self.assertTrue(manifest["weaponAssets"][0]["icon"])
            self.assertEqual(manifest["weaponAssets"][0]["crop"], "")
            self.assertIn(
                {"kind": "weapon_card", "key": "21", "reason": "render_failed"},
                manifest["assetErrors"],
            )

    async def test_cancellation_drains_started_asset_writers_and_cancels_queued_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            started = threading.Event()
            release = threading.Event()
            count_lock = threading.Lock()
            started_count = 0
            finished_count = 0
            characters = [
                {"id": 200 + index, "element": "Pyro", "rarity": 4,
                 "icon": f"https://act.hoyolab.com/cancel-portrait-{index}.png"}
                for index in range(12)
            ]
            cards = [
                {"portrait": character["icon"],
                 "element": f"https://act.hoyolab.com/cancel-element-{index}.png",
                 "characterBackground": "https://act.hoyolab.com/cancel-background.png"}
                for index, character in enumerate(characters)
            ]

            def blocking_download(
                url: str, destination: Path, *, require_transparency: bool = False,
            ) -> None:
                nonlocal started_count, finished_count
                with count_lock:
                    started_count += 1
                    started.set()
                try:
                    if not release.wait(5):
                        raise TimeoutError("fixture worker was not released")
                    _fake_download(url, destination, require_transparency=require_transparency)
                finally:
                    with count_lock:
                        finished_count += 1

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(
                    asset_layers, "_download_image", side_effect=blocking_download,
                ))
                task = asyncio.create_task(asset_layers.prepare_layered_assets(
                    characters=characters, weapons=[], cards=cards,
                    staging_root=root / "stage",
                ))
                started_in_worker = await asyncio.to_thread(started.wait, 3)
                returned_before_release = False
                queued_start_count = -1
                try:
                    self.assertTrue(started_in_worker)
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    await asyncio.sleep(0.03)
                    returned_before_release = task.done()
                    with count_lock:
                        queued_start_count = started_count
                finally:
                    # Always release workers, including when an assertion fails.
                    release.set()
                    outcome = await asyncio.gather(task, return_exceptions=True)

            self.assertIsInstance(outcome[0], asyncio.CancelledError)
            self.assertFalse(returned_before_release)
            self.assertLess(queued_start_count, len(characters) * 2 + 1)
            self.assertEqual(finished_count, started_count)
            self.assertEqual(started_count, queued_start_count)

    async def test_download_workers_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            characters = [
                {"id": 100 + index, "element": element, "rarity": 4,
                 "icon": f"https://act.hoyolab.com/portrait{index}.png"}
                for index, element in enumerate(("Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo"))
            ]
            cards = [
                {"portrait": character["icon"], "element": f"https://act.hoyolab.com/element{index}.png",
                 "characterBackground": "https://act.hoyolab.com/character-bg.png"}
                for index, character in enumerate(characters)
            ]
            lock = threading.Lock()
            active = 0
            maximum = 0

            def download(url: str, destination: Path, *, require_transparency: bool = False) -> None:
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                try:
                    time.sleep(0.02)
                    _fake_download(url, destination, require_transparency=require_transparency)
                finally:
                    with lock:
                        active -= 1

            with ExitStack() as stack:
                _patch_asset_paths(root, stack)
                stack.enter_context(patch.object(asset_layers, "_download_image", side_effect=download))
                await asset_layers.prepare_layered_assets(
                    characters=characters, weapons=[], cards=cards, staging_root=root / "stage",
                )

            self.assertGreater(maximum, 1)
            self.assertLessEqual(maximum, asset_layers.MAX_ASSET_WORKERS)


if __name__ == "__main__":
    unittest.main()
