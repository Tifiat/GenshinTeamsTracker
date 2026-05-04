import json
import math
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "tests" / "probe_layout_output"


def latest_probe_dir() -> Path:
    dirs = [p for p in OUTPUT_ROOT.iterdir() if p.is_dir()]
    if not dirs:
        raise SystemExit("No probe_layout_output folders found")
    return max(dirs, key=lambda p: p.stat().st_mtime)


def pick_image(folder: Path) -> Path:
    images = [
        p for p in folder.glob("*.png")
        if p.name not in {
            "page_screenshot.png",
            "exported_image_overlay.png",
            "role_cards_overlay.png",
            "crop_manifest_overlay.png",
        }
        and not p.name.endswith("_overlay.png")
    ]
    if not images:
        raise SystemExit("No exported PNG found")
    return max(images, key=lambda p: Image.open(p).size[0] * Image.open(p).size[1])


def read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        for key in ("characters", "weapons", "items", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("characters", "weapons", "items", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]

    return []


def load_account_data(folder: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    characters_path = folder / "account_characters.json"
    weapons_path = folder / "account_weapons.json"

    characters = as_list(read_json_if_exists(characters_path))
    weapons = as_list(read_json_if_exists(weapons_path))

    return characters, weapons, {
        "charactersPath": str(characters_path) if characters_path.exists() else None,
        "weaponsPath": str(weapons_path) if weapons_path.exists() else None,
        "charactersCount": len(characters),
        "weaponsCount": len(weapons),
    }


def icon_key(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(str(url))
    return Path(parsed.path).name.lower()


def contains(outer: dict, inner: dict, tolerance: float = 0.75) -> bool:
    return (
        inner["left"] >= outer["left"] - tolerance
        and inner["top"] >= outer["top"] - tolerance
        and inner["right"] <= outer["right"] + tolerance
        and inner["bottom"] <= outer["bottom"] + tolerance
    )


def center_y(rect: dict) -> float:
    return (rect["top"] + rect["bottom"]) / 2


def center_x(rect: dict) -> float:
    return (rect["left"] + rect["right"]) / 2


def first_parent_class(item: dict) -> str:
    parents = item.get("parentChain") or []
    if not parents:
        return ""
    return parents[0].get("className") or ""


def is_card(item: dict) -> bool:
    class_name = item.get("className") or ""
    classes = set(class_name.split())

    return (
        item.get("tag") == "DIV"
        and "role-share" in classes
        and "role-share-container" not in classes
        and "role-rarity-" in class_name
        and item.get("rect_root_relative")
    )


def is_portrait(item: dict) -> bool:
    return (
        item.get("tag") == "IMG"
        and "role-img" in (item.get("className") or "")
        and item.get("rect_root_relative")
    )


def is_weapon_icon(item: dict) -> bool:
    return (
        item.get("tag") == "IMG"
        and item.get("rect_root_relative")
        and "role-weapon-info" in first_parent_class(item)
    )


def crop_box(rect: dict, scale: float) -> tuple[int, int, int, int]:
    left = math.ceil(rect["left"] * scale) + 3
    top = math.ceil(rect["top"] * scale) + 3
    right = math.floor(rect["right"] * scale) - 5
    bottom = math.floor(rect["bottom"] * scale) - 5
    return left, top, right, bottom


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


def get_scale(probe: dict) -> float:
    clone_probe = probe.get("html2canvasCloneProbe") or {}
    options = clone_probe.get("html2canvasOptions") or {}
    scale = options.get("scale")
    if scale:
        return float(scale)

    exporter = probe.get("exporter") or {}
    scale = exporter.get("scale")
    if scale:
        return float(scale)

    return 4.0


def src_of(item: dict | None) -> str:
    if not item:
        return ""

    images = item.get("images") or []
    if not images:
        return ""

    first = images[0] or {}
    return first.get("currentSrc") or first.get("src") or ""


def clean_previous_crops(folder: Path) -> None:
    for pattern in (
        "crops/characters/char_*.png",
        "crops/weapons/weapon_*.png",
    ):
        for path in folder.glob(pattern):
            path.unlink()


def normalize_character(character: dict | None) -> dict | None:
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


def normalize_weapon(weapon: dict | None) -> dict | None:
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


def validate_match(
    index: int,
    card_data: dict[str, Any],
    character: dict | None,
    weapon: dict | None,
) -> dict[str, Any]:
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
        "characterIndexExists": character is not None,
        "weaponIndexExists": weapon is not None,
        "portraitIconMatches": bool(portrait_key and portrait_key == character_icon_key),
        "weaponIconMatches": bool(weapon_key and weapon_key == weapon_icon_key),
        "weaponEquippedByMatchesCharacter": bool(
            character_id is not None
            and equipped_by_id is not None
            and character_id == equipped_by_id
        ),
    }

    warnings = []
    if not checks["characterIndexExists"]:
        warnings.append("No account character at this index")
    if not checks["weaponIndexExists"]:
        warnings.append("No account weapon at this index")
    if character is not None and not checks["portraitIconMatches"]:
        warnings.append("portraitSrc does not match account character icon")
    if weapon is not None and not checks["weaponIconMatches"]:
        warnings.append("weaponSrc does not match account weapon icon")
    if character is not None and weapon is not None and not checks["weaponEquippedByMatchesCharacter"]:
        warnings.append("weapon equipped_by does not match character id")

    return {
        "strategy": "index",
        "status": "ok" if not warnings else "warning",
        "index": index,
        "portraitIconKey": portrait_key,
        "characterIconKey": character_icon_key,
        "weaponIconKey": weapon_key,
        "accountWeaponIconKey": weapon_icon_key,
        "checks": checks,
        "warnings": warnings,
    }


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_probe_dir()
    probe_path = folder / "layout_probe.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))

    image_path = pick_image(folder)
    image = Image.open(image_path).convert("RGB")
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    scale = get_scale(probe)

    characters, account_weapons, account_meta = load_account_data(folder)

    items = (probe.get("rootDiscovery") or {}).get("imageLike") or []

    cards = [x for x in items if is_card(x)]
    portraits = [x for x in items if is_portrait(x)]
    weapons = [x for x in items if is_weapon_icon(x)]

    cards.sort(key=lambda x: (center_y(x["rect_root_relative"]), center_x(x["rect_root_relative"])))

    role_cards = []

    chars_dir = folder / "crops" / "characters"
    weapons_dir = folder / "crops" / "weapons"
    chars_dir.mkdir(parents=True, exist_ok=True)
    weapons_dir.mkdir(parents=True, exist_ok=True)

    clean_previous_crops(folder)

    for index, card in enumerate(cards):
        card_rect = card["rect_root_relative"]

        inside_portraits = [
            x for x in portraits
            if contains(card_rect, x["rect_root_relative"])
        ]
        inside_weapons = [
            x for x in weapons
            if contains(card_rect, x["rect_root_relative"])
        ]

        portrait = inside_portraits[0] if inside_portraits else None
        weapon_icon = inside_weapons[0] if inside_weapons else None

        portrait_rect = portrait.get("rect_root_relative") if portrait else None
        weapon_rect = weapon_icon.get("rect_root_relative") if weapon_icon else None

        char_crop_rel = None
        weapon_crop_rel = None

        if portrait_rect:
            char_crop = chars_dir / f"char_{index:03}.png"
            image.crop(clamp_box(crop_box(portrait_rect, scale), image)).save(char_crop)
            char_crop_rel = str(char_crop.relative_to(folder)).replace("\\", "/")

        if weapon_rect:
            weapon_crop = weapons_dir / f"weapon_{index:03}.png"
            image.crop(clamp_box(crop_box(weapon_rect, scale), image)).save(weapon_crop)
            weapon_crop_rel = str(weapon_crop.relative_to(folder)).replace("\\", "/")

        character = characters[index] if index < len(characters) else None
        account_weapon = account_weapons[index] if index < len(account_weapons) else None

        card_data = {
            "index": index,
            "cardText": card.get("textPreview") or "",
            "cardClassName": card.get("className") or "",
            "cardRect": card_rect,
            "portraitRect": portrait_rect,
            "weaponRect": weapon_rect,
            "portraitSrc": src_of(portrait),
            "weaponSrc": src_of(weapon_icon),
            "crops": {
                "character": char_crop_rel,
                "weapon": weapon_crop_rel,
            },
        }

        match = validate_match(
            index=index,
            card_data=card_data,
            character=character,
            weapon=account_weapon,
        )

        normalized_character = normalize_character(character)
        normalized_weapon = normalize_weapon(account_weapon)

        card_data["match"] = match
        card_data["character"] = normalized_character
        card_data["weapon"] = normalized_weapon
        card_data["sort"] = {
            "index": index,
            "character_name": (normalized_character or {}).get("name") or card_data["cardText"],
            "character_level": (normalized_character or {}).get("level") or 0,
            "character_rarity": (normalized_character or {}).get("rarity") or 0,
            "element": (normalized_character or {}).get("element") or "",
            "weapon_name": (normalized_weapon or {}).get("name") or "",
            "weapon_level": (normalized_weapon or {}).get("level") or 0,
            "weapon_rarity": (normalized_weapon or {}).get("rarity") or 0,
        }

        role_cards.append(card_data)

        draw.rectangle(crop_box(card_rect, scale), outline=(255, 0, 0), width=2)

        if portrait_rect:
            draw.rectangle(crop_box(portrait_rect, scale), outline=(0, 255, 0), width=3)

        if weapon_rect:
            draw.rectangle(crop_box(weapon_rect, scale), outline=(0, 128, 255), width=3)

    out_json = folder / "crop_manifest_preview.json"
    out_overlay = folder / "crop_manifest_overlay.png"

    matched_characters = sum(1 for x in role_cards if x.get("character"))
    matched_weapons = sum(1 for x in role_cards if x.get("weapon"))
    ok_matches = sum(1 for x in role_cards if (x.get("match") or {}).get("status") == "ok")
    warning_matches = sum(1 for x in role_cards if (x.get("match") or {}).get("status") == "warning")

    out_json.write_text(
        json.dumps(
            {
                "sourceProbe": str(probe_path),
                "image": image_path.name,
                "scale": scale,
                "cardsCount": len(role_cards),
                "matchedCharacters": matched_characters,
                "matchedWeapons": matched_weapons,
                "okMatches": ok_matches,
                "warningMatches": warning_matches,
                "account": account_meta,
                "cards": role_cards,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    overlay.save(out_overlay)

    print("folder:", folder)
    print("image:", image_path.name, image.size)
    print("scale:", scale)
    print("cards:", len(cards))
    print("portraits:", len(portraits))
    print("weapons:", len(weapons))
    print("account characters:", len(characters))
    print("account weapons:", len(account_weapons))
    print("matched characters:", f"{matched_characters}/{len(role_cards)}")
    print("matched weapons:", f"{matched_weapons}/{len(role_cards)}")
    print("ok matches:", f"{ok_matches}/{len(role_cards)}")
    print("warning matches:", f"{warning_matches}/{len(role_cards)}")
    print("created:", out_json)
    print("created:", out_overlay)

    for c in role_cards[:10]:
        character = c.get("character") or {}
        weapon_data = c.get("weapon") or {}
        match = c.get("match") or {}
        print(
            c["index"],
            "status:",
            match.get("status"),
            "char:",
            character.get("name"),
            "weapon:",
            weapon_data.get("name"),
            "crop:",
            c["crops"],
            "text:",
            c["cardText"][:80],
        )

    if warning_matches:
        print()
        print("Warnings:")
        for c in role_cards:
            match = c.get("match") or {}
            if match.get("status") != "warning":
                continue
            print(
                c["index"],
                (c.get("character") or {}).get("name"),
                "->",
                "; ".join(match.get("warnings") or []),
            )


if __name__ == "__main__":
    main()