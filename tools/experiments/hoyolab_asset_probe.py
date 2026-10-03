"""Inspect one live HoYoLAB card without running the account import.

Run with ``.venv/Scripts/python.exe -m tools.experiments.hoyolab_asset_probe``.
The fixed output folder under debug/hoyolab is owned by this probe. A later
successful probe replaces its known files; normal import clears debug/hoyolab.
Only the selected character's name/IDs, image metadata, and image files are
saved there; no authentication material is saved. Static layer URLs come from
the versioned importer source map (or the legacy layout for old profiles),
while portrait and weapon URLs come from the live character/list response.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from hoyolab_export.auth import AuthStatus, get_auth_status
from hoyolab_export.collect_account_inventory import (
    build_inventory,
    wait_for_character_list_response,
)
from hoyolab_export.hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from hoyolab_export.import_pipeline import get_export_page
from hoyolab_export.paths import HOYOLAB_DATA_DIR, HOYOLAB_DEBUG_DIR, HOYOLAB_PROFILE_DIR, PROJECT_ROOT
from hoyolab_export.run_import import import_run_lock


OUTPUT_DIR = HOYOLAB_DEBUG_DIR / "single_asset_probe"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_PNG_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 100 * 1024 * 1024
OUTPUT_NAMES = {
    "portrait.png", "weapon.png", "element.png", "character_background.png",
    "weapon_background.png", "existing_crop.png", "assembled_character.png",
    "assembled_character_constellation.png", "assembled_weapon.png", "preview.png", "probe.json",
}


def _url_name(url: str) -> str:
    if url.startswith("data:"):
        return "[inline image]"
    return Path(urlparse(url).path).name


def _download_png(url: str, path: Path) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Asset source must be an HTTPS URL")
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://act.hoyolab.com/"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
        media_type = response.headers.get_content_type()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Asset is empty or exceeds the 5 MiB probe limit")
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("Asset exceeds the 4 megapixel probe limit")
        image.load()
        dimensions = list(image.size)
        alpha = "A" in image.getbands() or "transparency" in image.info
        image.save(path, format="PNG")
    if path.stat().st_size > MAX_PNG_BYTES:
        path.unlink()
        raise ValueError("Decoded PNG exceeds the 16 MiB probe limit")
    return {
        "sourceFile": _url_name(url),
        "sourceSha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "contentType": media_type,
        "downloadedBytes": len(data),
        "size": dimensions,
        "hasAlpha": alpha,
        "downloadAndDecodeSeconds": round(time.perf_counter() - started, 3),
    }


def _css_url(value: str | None) -> str:
    match = re.search(r"url\([\"']?(https://[^\"')]+)", str(value or ""))
    return match.group(1) if match else ""


def _cached_card_sources(character_id: int, weapon_rarity: int) -> dict:
    manifest_path = HOYOLAB_DATA_DIR / "crop_manifest.json"
    layout_path = HOYOLAB_DATA_DIR / "layout.json"
    if not manifest_path.is_file():
        raise RuntimeError("The local image manifest is needed to identify HoYoLAB's card layers")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") == 2:
        from hoyolab_export.asset_layers import STATIC_ELEMENTS, STATIC_RARITY_BACKGROUNDS
        asset = next(
            (item for item in manifest.get("characterAssets") or []
             if (item.get("character") or {}).get("id") == character_id),
            None,
        )
        if asset is None:
            raise RuntimeError("Selected character is missing from the current image manifest")
        character = asset["character"]
        return {
            "urls": {
                "element": STATIC_ELEMENTS[str(character["element"]).lower()],
                "character_background": STATIC_RARITY_BACKGROUNDS[int(character["rarity"])],
                "weapon_background": STATIC_RARITY_BACKGROUNDS[int(weapon_rarity)],
            },
            "cardIndex": None,
            "cardClass": "",
            "capturedAt": None,
            "previousPortraitFile": _url_name(character.get("icon") or ""),
            "previousWeaponFile": "",
            "existingCrop": asset.get("crop") or "",
        }
    if not layout_path.is_file():
        raise RuntimeError("The legacy export layout is missing")
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    card = next(
        (item for item in manifest.get("cards") or []
         if (item.get("character") or {}).get("id") == character_id),
        None,
    )
    if card is None:
        raise RuntimeError("Selected character is missing from the last local layout")
    items = (layout.get("rootDiscovery") or {}).get("imageLike") or []
    card_positions = [
        index for index, item in enumerate(items)
        if item.get("tag") == "DIV"
        and "role-share" in str(item.get("className") or "").split()
    ]
    card_index = int(card["index"])
    if card_index >= len(card_positions):
        raise RuntimeError("Selected card index exceeds the last local layout")
    start = card_positions[card_index]
    end = card_positions[card_index + 1] if card_index + 1 < len(card_positions) else len(items)
    section = items[start:end]
    def matching(class_name: str):
        return next((item for item in section if class_name in str(item.get("className") or "").split()), None)
    avatar = matching("role-avatar")
    element = matching("role-element")
    weapon_info = matching("role-weapon-info")
    weapon_background = next(
        (item for item in section
         if item.get("tag") == "IMG"
         and any("role-weapon-info" in str(parent.get("className") or "").split()
                 for parent in item.get("parentChain") or [])
         and _css_url(item.get("backgroundImage"))),
        None,
    )
    element_images = (element or {}).get("images") or []
    static_urls = {
        "element": (element_images[0].get("currentSrc") or element_images[0].get("src")) if element_images else "",
        "character_background": _css_url((avatar or {}).get("backgroundImage")),
        "weapon_background": _css_url((weapon_background or {}).get("backgroundImage")),
    }
    if not all(static_urls.values()) or weapon_info is None:
        raise RuntimeError("Last local layout does not expose all three static image layers")
    return {
        "urls": static_urls,
        "cardIndex": card_index,
        "cardClass": section[0].get("className"),
        "capturedAt": layout.get("capturedAt"),
        "previousPortraitFile": _url_name(card.get("portraitSrc") or ""),
        "previousWeaponFile": _url_name(card.get("weaponSrc") or ""),
        "existingCrop": (card.get("crops") or {}).get("character") or "",
    }


def _assemble_examples(folder: Path, constellation: int | None) -> None:
    from PIL import ImageDraw, ImageFont

    with Image.open(folder / "character_background.png") as source:
        canvas = source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS)
    with Image.open(folder / "portrait.png") as source:
        portrait = source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS)
    with Image.open(folder / "element.png") as source:
        element = source.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    canvas.alpha_composite(portrait)
    canvas.alpha_composite(element, (8, 8))
    canvas.save(folder / "assembled_character.png")
    with_constellation = canvas.copy()
    if constellation is not None:
        badge = Image.new("RGBA", (58, 50), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle((0, 0, 57, 49), radius=10, fill=(35, 32, 48, 190))
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except OSError:
            font = ImageFont.load_default()
        draw.text((17, 7), str(constellation), font=font, fill="white")
        with_constellation.alpha_composite(badge, (238, 0))
    with_constellation.save(folder / "assembled_character_constellation.png")

    with Image.open(folder / "weapon_background.png") as source:
        weapon_canvas = source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    with Image.open(folder / "weapon.png") as source:
        weapon = source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    weapon_canvas.alpha_composite(weapon)
    weapon_canvas.save(folder / "assembled_weapon.png")


def _make_preview(folder: Path) -> None:
    labels = [
        ("portrait", "portrait.png"), ("element", "element.png"),
        ("character background", "character_background.png"),
        ("weapon", "weapon.png"), ("weapon background", "weapon_background.png"),
        ("assembled without C", "assembled_character.png"),
        ("assembled with C", "assembled_character_constellation.png"),
        ("assembled weapon", "assembled_weapon.png"),
    ]
    if (folder / "existing_crop.png").is_file():
        labels.append(("existing crop", "existing_crop.png"))
    from PIL import ImageDraw
    width, height = 960, 950
    preview = Image.new("RGB", (width, height), "#20232b")
    draw = ImageDraw.Draw(preview)
    for index, (label, name) in enumerate(labels):
        x = 16 + (index % 3) * 315
        y = 18 + (index // 3) * 310
        with Image.open(folder / name) as source:
            image = source.convert("RGBA")
            image.thumbnail((285, 264))
            tile = Image.new("RGBA", image.size, "#707783")
            tile.alpha_composite(image)
            preview.paste(tile.convert("RGB"), (x + (285 - image.width) // 2, y + 28))
        draw.text((x, y), label, fill="white")
    preview.save(folder / "preview.png")


def _publish(folder: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    marker = OUTPUT_DIR / "probe.json"
    if any(OUTPUT_DIR.iterdir()) and not marker.is_file():
        raise RuntimeError("Probe output folder has unowned files; refusing to replace it")
    if marker.is_file():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous.get("producer") != "hoyolab_asset_probe":
            raise RuntimeError("Probe output marker has an unexpected owner")
        unknown = {path.name for path in OUTPUT_DIR.iterdir()} - OUTPUT_NAMES
        if unknown:
            raise RuntimeError("Probe output folder has unexpected files; refusing to replace it")
    for name in OUTPUT_NAMES:
        old_path = OUTPUT_DIR / name
        if old_path.is_file():
            old_path.unlink()
    for path in folder.iterdir():
        path.replace(OUTPUT_DIR / path.name)


async def _card_info(page, portrait_url: str) -> dict:
    return await page.evaluate(
        """(portraitUrl) => {
          const basename = (url) => { try { return new URL(url).pathname.split('/').pop(); } catch { return ''; } };
          const wanted = basename(portraitUrl);
          const cards = [...document.querySelectorAll('.role-share')];
          const card = cards.find(el => [...el.querySelectorAll('img.role-img')]
            .some(img => basename(img.currentSrc || img.src) === wanted));
          if (!card) {
            const matches = [...document.querySelectorAll('img')]
              .filter(img => basename(img.currentSrc || img.src) === wanted);
            return {found: false, cards: cards.length, images: document.images.length,
              matchingImages: matches.map(img => ({className: String(img.className || ''),
                parents: [...(function*(el) { let n=el.parentElement; for(let i=0;n&&i<5;i++,n=n.parentElement) yield String(n.className || ''); })(img)]})),
              sampleClasses: [...document.querySelectorAll('[class*="role"]')]
                .slice(0, 35).map(el => String(el.className || '')),
              sampleImages: [...document.querySelectorAll('img')].slice(0, 55).map(img => ({
                className: String(img.className || ''), file: basename(img.currentSrc || img.src),
                parent: String(img.parentElement?.className || '')
              }))};
          }
          card.setAttribute('data-gtt-single-asset-probe', '1');
          const box = (el) => {
            const r = el.getBoundingClientRect();
            const c = card.getBoundingClientRect();
            return {x: r.x-c.x, y: r.y-c.y, width: r.width, height: r.height};
          };
          const nodes = [card, ...card.querySelectorAll('*')];
          const visual = [];
          for (const el of nodes) {
            const s = getComputedStyle(el);
            const before = getComputedStyle(el, '::before');
            const after = getComputedStyle(el, '::after');
            const img = el.tagName === 'IMG' ? (el.currentSrc || el.src || '') : '';
            if (img || s.backgroundImage !== 'none' || before.backgroundImage !== 'none'
                || after.backgroundImage !== 'none' || /element|weapon|rarity|background|bg/i.test(String(el.className))) {
              visual.push({tag: el.tagName, className: String(el.className || '').slice(0, 180),
                image: img, background: s.backgroundImage, before: before.backgroundImage,
                after: after.backgroundImage, box: box(el),
                loaded: el.tagName === 'IMG' ? el.complete && el.naturalWidth > 0 : null});
            }
          }
          return {found: true, cards: cards.length, cardBox: box(card), visual};
        }""",
        portrait_url,
    )


async def _run(inspect_only: bool) -> dict:
    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise RuntimeError("HoYoLAB profile is not logged in")
    started = time.perf_counter()
    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=HOYOLAB_DEBUG_DIR,
        scale=1,
    )
    context = None
    try:
        context = await exporter._create_context()
        page = await get_export_page(context)
        inventory_future = await wait_for_character_list_response(page)
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        await exporter._wait_until_ready_or_login(page, timeout_ms=60_000)
        await exporter._click_with_popup_retry(page, ".block-title-right")
        await page.locator(".me-share__btn").first.wait_for(state="visible", timeout=30_000)
        inventory = await asyncio.wait_for(inventory_future, timeout=60)
        characters, weapons = build_inventory(inventory)
        character = next(
            item for item in characters
            if isinstance(item.get("id"), int) and item["id"] not in {10000117, 10000118}
            and item.get("icon")
        )
        weapon = next((item for item in weapons if item.get("equipped_by", {}).get("id") == character["id"]), None)
        info = await _card_info(page, character["icon"])
        result = {
            "characterId": character["id"],
            "characterName": character.get("name"),
            "element": character.get("element"),
            "rarity": character.get("rarity"),
            "constellation": character.get("constellation"),
            "weaponId": weapon.get("id") if weapon else None,
            "browserAndInventorySeconds": round(time.perf_counter() - started, 3),
            "card": info,
        }
        if inspect_only:
            return result
        if weapon is None or not weapon.get("icon"):
            raise RuntimeError("Selected character has no weapon URL in the live inventory")
        static = _cached_card_sources(character["id"], int(weapon["rarity"]))
        urls = {
            "portrait": character["icon"],
            "weapon": weapon["icon"],
            **static["urls"],
        }
        with tempfile.TemporaryDirectory(prefix="single-asset-probe-", dir=HOYOLAB_DEBUG_DIR) as temp:
            folder = Path(temp)
            assets = {}
            download_started = time.perf_counter()
            for kind, url in urls.items():
                assets[kind] = await asyncio.to_thread(_download_png, url, folder / f"{kind}.png")
            result["assetDownloadAndDecodeSeconds"] = round(time.perf_counter() - download_started, 3)
            result["totalToAssetsReadySeconds"] = round(time.perf_counter() - started, 3)
            result["staticLayerProvenance"] = {
                key: value for key, value in static.items() if key not in {"urls", "existingCrop"}
            }
            result["assets"] = assets
            result["assembledPreview"] = (
                "Approximate layering at the last export's measured card dimensions; "
                "not a pixel-exact HoYoLAB render."
            )
            crop = static["existingCrop"]
            if crop:
                crop_path = (PROJECT_ROOT / crop).resolve()
                try:
                    crop_path.relative_to((PROJECT_ROOT / "assets" / "hoyolab" / "characters").resolve())
                except ValueError:
                    crop_path = None
                if crop_path is not None and crop_path.is_file() and crop_path.stat().st_size <= MAX_PNG_BYTES:
                    shutil.copyfile(crop_path, folder / "existing_crop.png")
            _assemble_examples(folder, character.get("constellation"))
            _make_preview(folder)
            result.pop("card")
            result["producer"] = "hoyolab_asset_probe"
            result["files"] = sorted(path.name for path in folder.iterdir()) + ["probe.json"]
            (folder / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if sum(path.stat().st_size for path in folder.iterdir()) > MAX_OUTPUT_BYTES:
                raise ValueError("Probe output exceeds the 100 MiB retention limit")
            _publish(folder)
        return result
    finally:
        if context is not None:
            await close_export_context(context)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Inspect card layers without downloading")
    args = parser.parse_args()
    with import_run_lock():
        result = asyncio.run(_run(args.inspect))
    if args.inspect:
        visual = result["card"].get("visual", [])
        print(json.dumps({
            "characterId": result["characterId"],
            "element": result["element"],
            "browserAndInventorySeconds": result["browserAndInventorySeconds"],
            "cardCount": result["card"]["cards"],
            "found": result["card"].get("found"),
            "images": result["card"].get("images"),
            "matchingImages": result["card"].get("matchingImages"),
            "sampleClasses": result["card"].get("sampleClasses"),
            "sampleImages": result["card"].get("sampleImages"),
            "visual": [
                {**item, "image": _url_name(item["image"])} for item in visual
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
