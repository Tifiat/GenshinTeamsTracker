"""Download unique HoYoLAB card layers and render local display variants.

The inventory API owns portrait/weapon URLs. The live card DOM only supplies
the small shared element and rarity layer URLs; no browser-rendered bitmap is
used as an image source. Versioned output names avoid stale Qt pixmap caches.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from .crop_manifest import IGNORED_CHARACTER_IDS, IGNORED_WEAPON_RARITIES, character_asset_key, icon_key
from .paths import HOYOLAB_CHARACTER_ASSETS_DIR, HOYOLAB_WEAPON_ASSETS_DIR, HOYOLAB_SHARED_ASSETS_DIR, PROJECT_ROOT


SHARED_ASSETS_DIR = HOYOLAB_SHARED_ASSETS_DIR
RENDER_VERSION = "v2"
ELEMENTS = {"pyro", "hydro", "electro", "cryo", "anemo", "geo", "dendro"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000

# Public frontend assets observed in HoYoLAB's saved export layout on
# 2026-09-26. The character/list API does not include these shared layers and
# the share-card DOM is absent until the expensive full-image export starts.
# Live card URLs, when available, supersede these defaults below.
_STATIC_BASE = "https://act.hoyolab.com/app/community-game-records-sea/images/"
STATIC_ELEMENTS = {
    "pyro": _STATIC_BASE + "UI_Buff_Element_Fire.065c510d.png",
    "hydro": _STATIC_BASE + "UI_Buff_Element_Water.5b620394.png",
    "electro": _STATIC_BASE + "UI_Buff_Element_Elect.4c08c57a.png",
    "cryo": _STATIC_BASE + "UI_Buff_Element_Frost.95c777ac.png",
    "anemo": _STATIC_BASE + "UI_Buff_Element_Wind.bf653cfd.png",
    "geo": _STATIC_BASE + "UI_Buff_Element_Roach.bb164efa.png",
    "dendro": _STATIC_BASE + "UI_Buff_Element_Grass.dd061cc0.png",
}
STATIC_RARITY_BACKGROUNDS = {
    1: _STATIC_BASE + "roleStarBg1.8c3ec3b6.png",
    2: _STATIC_BASE + "roleStarBg2.5da2d605.png",
    3: _STATIC_BASE + "roleStarBg3.251efcc0.png",
    4: _STATIC_BASE + "roleStarBg4.0b20569c.png",
    5: _STATIC_BASE + "roleStarBg5.30180c91.png",
}


async def capture_card_layer_sources(page) -> list[dict[str, str]]:
    """Read only image URLs and rarity classes from the live share cards."""
    cards = await page.evaluate(
        """() => [...document.querySelectorAll('.role-share')].map(card => {
          const cssUrl = el => {
            if (!el) return '';
            const value = getComputedStyle(el).backgroundImage;
            const match = value && value.match(/url\\([\"']?(https:\\/\\/[^\"')]+)/);
            return match ? match[1] : '';
          };
          const src = el => el ? (el.currentSrc || el.src || '') : '';
          const avatar = card.querySelector('.role-avatar');
          const weapon = card.querySelector('.role-weapon-info');
          const weaponImg = weapon && weapon.querySelector('img');
          return {
            portrait: src(card.querySelector('img.role-img')),
            element: src(card.querySelector('img.role-element')),
            characterBackground: cssUrl(avatar),
            weaponBackground: cssUrl(weaponImg),
            weapon: src(weaponImg),
            characterRarity: (String(card.className).match(/role-rarity-(\\d+)/) || [])[1] || '',
            weaponRarity: (String(weapon?.className || '').match(/weapon-rarity-(\\d+)/) || [])[1] || ''
          };
        })"""
    )
    return [dict(card) for card in cards if isinstance(card, dict)]


def _fingerprint(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _download_image(url: str, destination: Path, *, require_transparency: bool = False) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host.endswith(".hoyolab.com") or host.endswith(".hoyoverse.com")):
        raise ValueError("Unexpected HoYoLAB image host")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://act.hoyolab.com/"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("HoYoLAB image is empty or too large")
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("HoYoLAB image exceeds pixel limit")
        image.load()
        rgba = image.convert("RGBA")
        if require_transparency:
            low, high = rgba.getchannel("A").getextrema()
            if low == 255 or high == 0:
                raise ValueError("HoYoLAB portrait/weapon source has no usable transparent image")
        destination.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(destination, format="PNG")


def _layer_file(staging_root: Path, final: Path) -> Path:
    staged = staging_root / final.relative_to(PROJECT_ROOT)
    return staged if staged.is_file() else final


def _render_character(
    staging_root: Path, destination: Path, *, portrait: Path, background: Path,
    element: Path | None = None, constellation: int | None = None,
) -> None:
    with Image.open(_layer_file(staging_root, background)) as source:
        canvas = source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS)
    with Image.open(_layer_file(staging_root, portrait)) as source:
        canvas.alpha_composite(source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS))
    if element is not None:
        with Image.open(_layer_file(staging_root, element)) as source:
            canvas.alpha_composite(source.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS), (8, 8))
    if constellation is not None:
        badge = Image.new("RGBA", (58, 50), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle((0, 0, 57, 49), radius=10, fill=(35, 32, 48, 190))
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except OSError:
            font = ImageFont.load_default()
        draw.text((17, 7), str(constellation), font=font, fill="white")
        canvas.alpha_composite(badge, (238, 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)


def _render_weapon(staging_root: Path, destination: Path, *, icon: Path, background: Path) -> None:
    with Image.open(_layer_file(staging_root, background)) as source:
        canvas = source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    with Image.open(_layer_file(staging_root, icon)) as source:
        canvas.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)


async def prepare_layered_assets(
    *, characters: list[dict], weapons: list[dict], cards: list[dict], staging_root: Path,
    refresh_images: bool = False,
) -> dict:
    """Stage cache misses and return a manifest compatible with SQLite sync."""
    cards_by_icon = {icon_key(card.get("portrait")): card for card in cards if card.get("portrait")}
    elements: dict[str, str] = dict(STATIC_ELEMENTS)
    character_backgrounds: dict[int, str] = dict(STATIC_RARITY_BACKGROUNDS)
    weapon_backgrounds: dict[int, str] = dict(STATIC_RARITY_BACKGROUNDS)
    for character in characters:
        card = cards_by_icon.get(icon_key(character.get("icon")))
        if card is None:
            continue
        element = str(character.get("element") or "").lower()
        rarity = int(character.get("rarity") or 0)
        if element in ELEMENTS and card.get("element"):
            elements[element] = card["element"]
        if rarity and card.get("characterBackground"):
            character_backgrounds[rarity] = card["characterBackground"]
        weapon_rarity = int(card.get("weaponRarity") or 0)
        if weapon_rarity and card.get("weaponBackground"):
            weapon_backgrounds[weapon_rarity] = card["weaponBackground"]

    wanted_chars = [c for c in characters if c.get("id") not in IGNORED_CHARACTER_IDS and c.get("icon")]
    wanted_weapons = [w for w in weapons if w.get("rarity") not in IGNORED_WEAPON_RARITIES and w.get("icon")]
    missing = []
    for character in wanted_chars:
        if str(character.get("element") or "").lower() not in elements or int(character.get("rarity") or 0) not in character_backgrounds:
            missing.append(f"character {character.get('id')}")
    for weapon in wanted_weapons:
        if int(weapon.get("rarity") or 0) not in weapon_backgrounds:
            missing.append(f"weapon rarity {weapon.get('rarity')}")
    if missing:
        raise RuntimeError("HoYoLAB card layer URLs missing: " + ", ".join(missing[:8]))

    downloads: dict[Path, tuple[str, bool]] = {}
    def raw_path(folder: Path, role: str, key: object, url: str) -> Path:
        path = folder / f"{role}_{RENDER_VERSION}_{key}_{_fingerprint(url)}.png"
        if refresh_images or not path.is_file():
            downloads[path] = (url, role in {"portrait", "weapon_icon"})
        return path

    required_elements = {str(c["element"]).lower() for c in wanted_chars}
    required_character_rarities = {int(c["rarity"]) for c in wanted_chars}
    required_weapon_rarities = {int(w["rarity"]) for w in wanted_weapons}
    element_paths = {key: raw_path(SHARED_ASSETS_DIR, "element", key, elements[key]) for key in sorted(required_elements)}
    # The frontend often uses the same rarity bitmap for both card types.
    # Key by source URL so it is fetched and stored only once in that case.
    char_bg_paths = {key: raw_path(SHARED_ASSETS_DIR, "rarity_bg", key, character_backgrounds[key]) for key in sorted(required_character_rarities)}
    weapon_bg_paths = {key: raw_path(SHARED_ASSETS_DIR, "rarity_bg", key, weapon_backgrounds[key]) for key in sorted(required_weapon_rarities)}
    portrait_paths = {str(c["id"]): raw_path(HOYOLAB_CHARACTER_ASSETS_DIR, "portrait", c["id"], c["icon"]) for c in wanted_chars}
    weapon_icon_paths = {
        (str(w["id"]), str(w["icon"])):
            raw_path(HOYOLAB_WEAPON_ASSETS_DIR, "weapon_icon", w["id"], w["icon"])
        for w in wanted_weapons
    }

    semaphore = asyncio.Semaphore(8)
    async def download(final: Path, url: str, require_transparency: bool) -> None:
        async with semaphore:
            await asyncio.to_thread(_download_image, url, staging_root / final.relative_to(PROJECT_ROOT), require_transparency=require_transparency)
    await asyncio.gather(*(download(path, url, require_transparency) for path, (url, require_transparency) in downloads.items()))

    render_jobs: list[tuple[Callable[..., None], dict[str, object]]] = []
    character_assets = []
    for character in wanted_chars:
        cid = str(character["id"])
        element = str(character["element"]).lower()
        rarity = int(character["rarity"])
        constellation = character.get("constellation")
        source_key = _fingerprint(portrait_paths[cid].name, char_bg_paths[rarity].name)
        with_element_key = _fingerprint(source_key, element_paths[element].name)
        history = HOYOLAB_CHARACTER_ASSETS_DIR / f"char_history_{RENDER_VERSION}_{cid}_{source_key}.png"
        pvp = HOYOLAB_CHARACTER_ASSETS_DIR / f"char_pvp_{RENDER_VERSION}_{cid}_{with_element_key}.png"
        browser = HOYOLAB_CHARACTER_ASSETS_DIR / f"char_{RENDER_VERSION}_{cid}_{_fingerprint(with_element_key, constellation)}.png"
        for path, layer, badge in ((history, None, None), (pvp, element_paths[element], None), (browser, element_paths[element], constellation)):
            if refresh_images or not path.is_file():
                render_jobs.append((_render_character, {
                    "staging_root": staging_root, "destination": staging_root / path.relative_to(PROJECT_ROOT),
                    "portrait": portrait_paths[cid], "background": char_bg_paths[rarity],
                    "element": layer, "constellation": badge,
                }))
        character_assets.append({
            "assetKey": character_asset_key(character), "character": character,
            "crop": _relative(browser), "pvp": _relative(pvp), "history": _relative(history),
            "portrait": _relative(portrait_paths[cid]),
        })

    weapon_assets = []
    seen_weapon_sources = set()
    for weapon in wanted_weapons:
        wid = str(weapon["id"])
        source_key = (wid, str(weapon["icon"]))
        if source_key in seen_weapon_sources:
            continue
        seen_weapon_sources.add(source_key)
        icon = weapon_icon_paths[source_key]
        background = weapon_bg_paths[int(weapon["rarity"])]
        composite = HOYOLAB_WEAPON_ASSETS_DIR / f"weapon_{RENDER_VERSION}_{wid}_{_fingerprint(icon.name, background.name)}.png"
        if refresh_images or not composite.is_file():
            render_jobs.append((_render_weapon, {
                "staging_root": staging_root, "destination": staging_root / composite.relative_to(PROJECT_ROOT),
                "icon": icon, "background": background,
            }))
        weapon_assets.append({"assetKey": icon_key(weapon["icon"]), "iconKey": icon_key(weapon["icon"]), "weapon": weapon, "crop": _relative(composite), "icon": _relative(icon)})

    render_semaphore = asyncio.Semaphore(8)
    async def render(func: Callable[..., None], kwargs: dict[str, object]) -> None:
        async with render_semaphore:
            await asyncio.to_thread(func, **kwargs)
    await asyncio.gather(*(render(func, kwargs) for func, kwargs in render_jobs))

    return {
        "version": 2, "source": {"method": "separate_hoyolab_layers"},
        "cardsCount": len(wanted_chars), "matchedCharacters": len(character_assets),
        "matchedWeapons": len(weapon_assets), "okMatches": len(character_assets), "warningMatches": 0,
        "characterAssets": character_assets, "weaponAssets": weapon_assets,
        "sharedAssets": {
            "elements": {key: _relative(path) for key, path in element_paths.items()},
            "characterBackgrounds": {str(key): _relative(path) for key, path in char_bg_paths.items()},
            "weaponBackgrounds": {str(key): _relative(path) for key, path in weapon_bg_paths.items()},
        },
        "assetsDownloaded": len(downloads), "assetsRendered": len(render_jobs),
    }


def cleanup_unused_v2_assets(manifest: Mapping[str, object]) -> list[str]:
    """Retire unused raw layers while preserving older display images.

    PvP profile slices can still refer to a previously rendered card bitmap.
    They do not carry their own image files, so those composites must survive
    later imports of the local account.
    """
    referenced = set()
    for asset in (*manifest.get("characterAssets", []), *manifest.get("weaponAssets", [])):
        if isinstance(asset, Mapping):
            referenced.update(str(value) for key, value in asset.items() if key in {"crop", "pvp", "history", "portrait", "icon"})
    shared = manifest.get("sharedAssets", {})
    if isinstance(shared, Mapping):
        for group in shared.values():
            if isinstance(group, Mapping):
                referenced.update(str(value) for value in group.values())
    failures: list[str] = []
    for folder in (HOYOLAB_CHARACTER_ASSETS_DIR, HOYOLAB_WEAPON_ASSETS_DIR, SHARED_ASSETS_DIR):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.png"):
            if path.name.startswith(("char_v2_", "char_pvp_v2_", "char_history_v2_", "weapon_v2_")):
                continue
            if f"_{RENDER_VERSION}_" in path.name and _relative(path) not in referenced:
                try:
                    path.unlink()
                except OSError:
                    failures.append(_relative(path))
    return failures
