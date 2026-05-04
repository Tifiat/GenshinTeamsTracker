import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

CROP_INSET = 1
IGNORED_CHARACTER_IDS = {
    10000118,  # Манекен (ж)
    10000117,  # Манекен (м)
}
IGNORED_WEAPON_RARITIES = {1, 2}

def icon_key(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(str(url))
    return Path(parsed.path).name.lower()


def contains(outer: dict[str, float], inner: dict[str, float], tolerance: float = 0.75) -> bool:
    return (
        inner["left"] >= outer["left"] - tolerance
        and inner["top"] >= outer["top"] - tolerance
        and inner["right"] <= outer["right"] + tolerance
        and inner["bottom"] <= outer["bottom"] + tolerance
    )


def center_y(rect: dict[str, float]) -> float:
    return (rect["top"] + rect["bottom"]) / 2


def center_x(rect: dict[str, float]) -> float:
    return (rect["left"] + rect["right"]) / 2


def first_parent_class(item: dict[str, Any]) -> str:
    parents = item.get("parentChain") or []
    if not parents:
        return ""
    return parents[0].get("className") or ""


def class_tokens(item: dict[str, Any]) -> set[str]:
    return set(str(item.get("className") or "").split())


def is_card(item: dict[str, Any]) -> bool:
    class_name = str(item.get("className") or "")
    classes = class_tokens(item)

    return (
        item.get("tag") == "DIV"
        and "role-share" in classes
        and "role-share-container" not in classes
        and "role-rarity-" in class_name
        and isinstance(item.get("rect_root_relative"), dict)
    )


def is_portrait(item: dict[str, Any]) -> bool:
    return (
        item.get("tag") == "IMG"
        and "role-img" in class_tokens(item)
        and isinstance(item.get("rect_root_relative"), dict)
    )


def is_weapon_icon(item: dict[str, Any]) -> bool:
    return (
        item.get("tag") == "IMG"
        and isinstance(item.get("rect_root_relative"), dict)
        and "role-weapon-info" in first_parent_class(item)
    )


def get_scale(layout: dict[str, Any]) -> float:
    clone_probe = layout.get("html2canvasCloneProbe") or {}
    options = clone_probe.get("html2canvasOptions") or {}
    scale = options.get("scale")
    if scale:
        return float(scale)

    exporter = layout.get("exporter") or {}
    scale = exporter.get("scale")
    if scale:
        return float(scale)

    return 4.0


def src_of(item: dict[str, Any] | None) -> str:
    if not item:
        return ""

    images = item.get("images") or []
    if not images:
        return ""

    first = images[0] or {}
    return first.get("currentSrc") or first.get("src") or ""


def crop_box(rect: dict[str, float], scale: float) -> tuple[int, int, int, int]:
    left = math.ceil(rect["left"] * scale) + CROP_INSET
    top = math.ceil(rect["top"] * scale) + CROP_INSET
    right = math.floor(rect["right"] * scale) - CROP_INSET
    bottom = math.floor(rect["bottom"] * scale) - CROP_INSET
    return left, top, right, bottom


def character_crop_box(rect: dict[str, float], scale: float) -> tuple[int, int, int, int]:
    return crop_box(rect, scale)


def weapon_crop_box(rect: dict[str, float], scale: float) -> tuple[int, int, int, int]:
    return crop_box(rect, scale)


def raw_scaled_box(rect: dict[str, float], scale: float) -> tuple[int, int, int, int]:
    return (
        math.floor(rect["left"] * scale),
        math.floor(rect["top"] * scale),
        math.ceil(rect["right"] * scale),
        math.ceil(rect["bottom"] * scale),
    )


def clamp_box(box: tuple[int, int, int, int], image: Image.Image) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    width, height = image.size

    left = max(0, min(width, left))
    top = max(0, min(height, top))
    right = max(0, min(width, right))
    bottom = max(0, min(height, bottom))

    if right <= left or bottom <= top:
        raise ValueError(f"Invalid crop box after clamp: {box} -> {(left, top, right, bottom)}")

    return left, top, right, bottom


def normalize_character(character: dict[str, Any] | None) -> dict[str, Any] | None:
    if not character:
        return None

    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "rarity": character.get("rarity"),
        "element": character.get("element"),
        "level": character.get("level"),
        "constellation": character.get("constellation"),
        "weapon_type": character.get("weapon_type"),
        "weapon_type_name": character.get("weapon_type_name"),
        "icon": character.get("icon"),
        "side_icon": character.get("side_icon"),
    }


def normalize_weapon(weapon: dict[str, Any] | None) -> dict[str, Any] | None:
    if not weapon:
        return None

    equipped_by = weapon.get("equipped_by")
    if not isinstance(equipped_by, dict):
        equipped_by = None

    return {
        "id": weapon.get("id"),
        "name": weapon.get("name"),
        "rarity": weapon.get("rarity"),
        "type": weapon.get("type"),
        "type_name": weapon.get("type_name"),
        "level": weapon.get("level"),
        "refinement": weapon.get("refinement"),
        "icon": weapon.get("icon"),
        "equipped_by": {
            "id": equipped_by.get("id"),
            "name": equipped_by.get("name"),
        } if equipped_by else None,
    }

def is_ignored_character(character: dict[str, Any] | None) -> bool:
    if not character:
        return False
    return character.get("id") in IGNORED_CHARACTER_IDS


def is_ignored_weapon(weapon: dict[str, Any] | None) -> bool:
    if not weapon:
        return False
    return weapon.get("rarity") in IGNORED_WEAPON_RARITIES


def character_tooltip(character: dict[str, Any] | None) -> str:
    if not character:
        return ""

    name = character.get("name") or ""
    level = character.get("level")

    if level:
        return f"{name} lvl {level}"
    return name


def weapon_variant_key(weapon: dict[str, Any]) -> tuple[Any, Any]:
    return weapon.get("refinement"), weapon.get("level")


def update_weapon_asset_tooltip(asset: dict[str, Any]) -> None:
    lines = [asset.get("name") or ""]

    variants = asset.get("variants") or []
    for i, variant in enumerate(variants, start=1):
        refinement = variant.get("refinement")
        level = variant.get("level")
        count = variant.get("count", 1)

        line = f"{i}. R{refinement} lvl {level}"
        if count > 1:
            line += f" x{count}"

        lines.append(line)

    asset["tooltip"] = "\n".join(line for line in lines if line)


def add_weapon_variant(asset: dict[str, Any], weapon: dict[str, Any]) -> None:
    refinement, level = weapon_variant_key(weapon)

    for variant in asset["variants"]:
        if variant.get("refinement") == refinement and variant.get("level") == level:
            variant["count"] += 1
            update_weapon_asset_tooltip(asset)
            return

    asset["variants"].append(
        {
            "refinement": refinement,
            "level": level,
            "count": 1,
        }
    )
    update_weapon_asset_tooltip(asset)

def character_icon_keys(character: dict[str, Any]) -> set[str]:
    keys = {
        icon_key(character.get("icon")),
        icon_key(character.get("side_icon")),
    }
    return {key for key in keys if key}


def weapon_icon_keys(weapon: dict[str, Any]) -> set[str]:
    keys = {icon_key(weapon.get("icon"))}
    return {key for key in keys if key}


def find_character_by_icon(
    portrait_src: str,
    characters: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    portrait_key = icon_key(portrait_src)

    if not portrait_key:
        return None, "missing_portrait_icon"

    matches = [
        character for character in characters
        if portrait_key in character_icon_keys(character)
    ]

    if len(matches) == 1:
        return matches[0], "character_icon"

    if len(matches) > 1:
        return None, "ambiguous_character_icon"

    return None, "character_icon_not_found"


def find_weapon_by_icon_and_character(
    weapon_src: str,
    weapons: list[dict[str, Any]],
    character: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    weapon_key = icon_key(weapon_src)

    if not weapon_key:
        return None, "missing_weapon_icon"

    icon_matches = [
        weapon for weapon in weapons
        if weapon_key in weapon_icon_keys(weapon)
    ]

    if not icon_matches:
        return None, "weapon_icon_not_found"

    character_id = character.get("id") if isinstance(character, dict) else None
    character_name = character.get("name") if isinstance(character, dict) else None

    if character_id is not None:
        equipped_matches = [
            weapon for weapon in icon_matches
            if (weapon.get("equipped_by") or {}).get("id") == character_id
        ]
        if len(equipped_matches) == 1:
            return equipped_matches[0], "weapon_icon_and_character_id"

    if character_name:
        equipped_matches = [
            weapon for weapon in icon_matches
            if (weapon.get("equipped_by") or {}).get("name") == character_name
        ]
        if len(equipped_matches) == 1:
            return equipped_matches[0], "weapon_icon_and_character_name"

    if len(icon_matches) == 1:
        return icon_matches[0], "unique_weapon_icon"

    return None, "ambiguous_weapon_icon"


def match_api_record(
    index: int,
    card_data: dict[str, Any],
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    character, character_strategy = find_character_by_icon(
        card_data.get("portraitSrc") or "",
        characters,
    )

    weapon, weapon_strategy = find_weapon_by_icon_and_character(
        card_data.get("weaponSrc") or "",
        weapons,
        character,
    )

    portrait_key = icon_key(card_data.get("portraitSrc"))
    weapon_key = icon_key(card_data.get("weaponSrc"))
    character_icon_key = icon_key(character.get("icon")) if character else ""
    weapon_icon_key = icon_key(weapon.get("icon")) if weapon else ""

    equipped_by = weapon.get("equipped_by") if isinstance(weapon, dict) else None
    if not isinstance(equipped_by, dict):
        equipped_by = {}

    character_id = character.get("id") if isinstance(character, dict) else None
    equipped_by_id = equipped_by.get("id")

    checks = {
        "characterFound": character is not None,
        "weaponFound": weapon is not None,
        "portraitIconMatches": bool(
            portrait_key
            and character_icon_key
            and portrait_key == character_icon_key
        ),
        "weaponIconMatches": bool(
            weapon_key
            and weapon_icon_key
            and weapon_key == weapon_icon_key
        ),
        "weaponEquippedByMatchesCharacter": bool(
            character_id is not None
            and equipped_by_id is not None
            and character_id == equipped_by_id
        ),
    }

    warnings = []

    if character is None:
        warnings.append(f"Character match failed: {character_strategy}")

    if weapon is None:
        warnings.append(f"Weapon match failed: {weapon_strategy}")

    if character is not None and not checks["portraitIconMatches"]:
        warnings.append("portraitSrc does not match account character icon")

    if weapon is not None and not checks["weaponIconMatches"]:
        warnings.append("weaponSrc does not match account weapon icon")

    if character is not None and weapon is not None and not checks["weaponEquippedByMatchesCharacter"]:
        warnings.append("weapon equipped_by does not match character id")

    return character, weapon, {
        "strategy": "icon",
        "status": "ok" if not warnings else "warning",
        "index": index,
        "characterStrategy": character_strategy,
        "weaponStrategy": weapon_strategy,
        "portraitIconKey": portrait_key,
        "characterIconKey": character_icon_key,
        "weaponIconKey": weapon_key,
        "accountWeaponIconKey": weapon_icon_key,
        "checks": checks,
        "warnings": warnings,
    }


def extract_role_cards(layout: dict[str, Any]) -> list[dict[str, Any]]:
    items = (layout.get("rootDiscovery") or {}).get("imageLike") or []

    cards = [item for item in items if is_card(item)]
    portraits = [item for item in items if is_portrait(item)]
    weapons = [item for item in items if is_weapon_icon(item)]

    cards.sort(key=lambda item: (
        center_y(item["rect_root_relative"]),
        center_x(item["rect_root_relative"]),
    ))

    role_cards = []

    for index, card in enumerate(cards):
        card_rect = card["rect_root_relative"]

        inside_portraits = [
            item for item in portraits
            if contains(card_rect, item["rect_root_relative"])
        ]
        inside_weapons = [
            item for item in weapons
            if contains(card_rect, item["rect_root_relative"])
        ]

        inside_portraits.sort(key=lambda item: (
            center_y(item["rect_root_relative"]),
            center_x(item["rect_root_relative"]),
        ))
        inside_weapons.sort(key=lambda item: (
            center_y(item["rect_root_relative"]),
            center_x(item["rect_root_relative"]),
        ))

        portrait = inside_portraits[0] if inside_portraits else None
        weapon_icon = inside_weapons[0] if inside_weapons else None

        role_cards.append(
            {
                "index": index,
                "cardText": card.get("textPreview") or "",
                "cardClassName": card.get("className") or "",
                "cardRect": card_rect,
                "portraitRect": portrait.get("rect_root_relative") if portrait else None,
                "weaponRect": weapon_icon.get("rect_root_relative") if weapon_icon else None,
                "portraitSrc": src_of(portrait),
                "weaponSrc": src_of(weapon_icon),
            }
        )

    return role_cards


def path_for_manifest(path: Path | None, *, relative_to: Path | None = None) -> str | None:
    if path is None:
        return None

    if relative_to is not None:
        try:
            return path.relative_to(relative_to).as_posix()
        except ValueError:
            pass

    return path.as_posix()


def load_overlay_font(size: int = 18) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def safe_draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = (255, 255, 255),
    background: tuple[int, int, int] = (0, 0, 0),
) -> None:
    if not text:
        return

    x, y = xy
    try:
        bbox = draw.textbbox((x, y), text, font=font)
        draw.rectangle(
            (bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2),
            fill=background,
        )
        draw.text((x, y), text, fill=fill, font=font)
    except UnicodeEncodeError:
        fallback = text.encode("ascii", errors="replace").decode("ascii")
        bbox = draw.textbbox((x, y), fallback, font=font)
        draw.rectangle(
            (bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2),
            fill=background,
        )
        draw.text((x, y), fallback, fill=fill, font=font)


def build_crop_manifest(
    *,
    image_path: str | Path,
    layout: dict[str, Any],
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    character_output_dir: str | Path,
    weapon_output_dir: str | Path,
    manifest_path: str | Path | None = None,
    overlay_path: str | Path | None = None,
    relative_to: str | Path | None = None,
    source_layout_path: str | Path | None = None,
) -> dict[str, Any]:
    image_path = Path(image_path)
    character_output_dir = Path(character_output_dir)
    weapon_output_dir = Path(weapon_output_dir)
    manifest_path = Path(manifest_path) if manifest_path is not None else None
    overlay_path = Path(overlay_path) if overlay_path is not None else None
    relative_base = Path(relative_to) if relative_to is not None else None

    character_output_dir.mkdir(parents=True, exist_ok=True)
    weapon_output_dir.mkdir(parents=True, exist_ok=True)

    for path in character_output_dir.glob("char_*.png"):
        path.unlink()
    for path in weapon_output_dir.glob("weapon_*.png"):
        path.unlink()

    scale = get_scale(layout)
    role_cards = extract_role_cards(layout)

    with Image.open(image_path) as raw_image:
        image = raw_image.convert("RGB")

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    font = load_overlay_font(size=18)

    manifest_cards = []
    character_assets = []
    weapon_assets_by_icon: dict[str, dict[str, Any]] = {}

    for index, card in enumerate(role_cards):
        portrait_rect = card.get("portraitRect")
        weapon_rect = card.get("weaponRect")

        character, weapon, match = match_api_record(
            index=index,
            card_data=card,
            characters=characters,
            weapons=weapons,
        )

        normalized_character = normalize_character(character)
        normalized_weapon = normalize_weapon(weapon)

        character_ignored = is_ignored_character(normalized_character)
        weapon_ignored = is_ignored_weapon(normalized_weapon)

        character_path = None
        character_crop = None
        weapon_crop = None
        character_box = None
        weapon_box = None

        if portrait_rect:
            character_box = clamp_box(character_crop_box(portrait_rect, scale), image)

            if not character_ignored:
                character_path = character_output_dir / f"char_{index:03}.png"
                image.crop(character_box).save(character_path)
                character_crop = path_for_manifest(character_path, relative_to=relative_base)

                character_assets.append(
                    {
                        "index": index,
                        "crop": character_crop,
                        "character": normalized_character,
                        "tooltip": character_tooltip(normalized_character),
                    }
                )

        weapon_icon = icon_key((normalized_weapon or {}).get("icon")) or icon_key(card.get("weaponSrc"))

        if weapon_rect:
            weapon_box = clamp_box(weapon_crop_box(weapon_rect, scale), image)

            if not weapon_ignored and weapon_icon:
                weapon_asset = weapon_assets_by_icon.get(weapon_icon)

                if weapon_asset is None:
                    weapon_path = weapon_output_dir / f"weapon_{index:03}.png"
                    image.crop(weapon_box).save(weapon_path)

                    weapon_crop = path_for_manifest(weapon_path, relative_to=relative_base)
                    weapon_asset = {
                        "assetIndex": len(weapon_assets_by_icon),
                        "firstCardIndex": index,
                        "iconKey": weapon_icon,
                        "crop": weapon_crop,
                        "name": (normalized_weapon or {}).get("name") or "",
                        "weapon": normalized_weapon,
                        "variants": [],
                        "tooltip": "",
                    }
                    weapon_assets_by_icon[weapon_icon] = weapon_asset
                else:
                    weapon_crop = weapon_asset["crop"]

                if normalized_weapon:
                    add_weapon_variant(weapon_asset, normalized_weapon)

        card_data = {
            **card,
            "character": normalized_character,
            "weapon": normalized_weapon,
            "crops": {
                "character": character_crop,
                "weapon": weapon_crop,
            },
            "assets": {
                "characterIgnored": character_ignored,
                "weaponIgnored": weapon_ignored,
                "weaponIconKey": weapon_icon,
            },
            "cropBoxes": {
                "character": list(character_box) if character_box else None,
                "weapon": list(weapon_box) if weapon_box else None,
            },
            "sort": {
                "index": index,
                "character_name": (normalized_character or {}).get("name") or card.get("cardText") or "",
                "character_level": (normalized_character or {}).get("level") or 0,
                "character_rarity": (normalized_character or {}).get("rarity") or 0,
                "element": (normalized_character or {}).get("element") or "",
                "weapon_name": (normalized_weapon or {}).get("name") or "",
                "weapon_level": (normalized_weapon or {}).get("level") or 0,
                "weapon_rarity": (normalized_weapon or {}).get("rarity") or 0,
            },
        }

        card_data["match"] = match

        manifest_cards.append(card_data)

        if portrait_rect:
            rect = clamp_box(raw_scaled_box(portrait_rect, scale), image)
            draw.rectangle(rect, outline=(0, 255, 0), width=3)
            char_name = (normalized_character or {}).get("name") or f"char_{index:03}"
            safe_draw_text(
                draw,
                (rect[0] + 4, max(0, rect[1] - 22)),
                f"{index:03} {char_name}",
                font=font,
            )

        if weapon_rect:
            rect = clamp_box(raw_scaled_box(weapon_rect, scale), image)
            draw.rectangle(rect, outline=(0, 128, 255), width=3)
            weapon_name = (normalized_weapon or {}).get("name") or f"weapon_{index:03}"
            safe_draw_text(
                draw,
                (rect[0] + 4, rect[3] + 4),
                weapon_name,
                font=font,
            )

    matched_characters = sum(1 for item in manifest_cards if item.get("character"))
    matched_weapons = sum(1 for item in manifest_cards if item.get("weapon"))
    ok_matches = sum(1 for item in manifest_cards if (item.get("match") or {}).get("status") == "ok")
    warning_matches = sum(1 for item in manifest_cards if (item.get("match") or {}).get("status") == "warning")

    manifest = {
        "version": 1,
        "source": {
            "image": path_for_manifest(image_path, relative_to=relative_base),
            "layout": path_for_manifest(Path(source_layout_path), relative_to=relative_base)
            if source_layout_path
            else None,
            "scale": scale,
        },
        "imageSize": {
            "width": image.width,
            "height": image.height,
        },
        "cardsCount": len(manifest_cards),
        "matchedCharacters": matched_characters,
        "matchedWeapons": matched_weapons,
        "okMatches": ok_matches,
        "warningMatches": warning_matches,
        "characterAssets": character_assets,
        "weaponAssets": sorted(
            weapon_assets_by_icon.values(),
            key=lambda item: item["assetIndex"],
        ),
        "cards": manifest_cards,
    }

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if overlay_path is not None:
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(overlay_path)

    return manifest