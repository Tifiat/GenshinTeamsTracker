import json
import math
import sys
from pathlib import Path

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
        }
        and not p.name.endswith("_overlay.png")
    ]
    if not images:
        raise SystemExit("No exported PNG found")
    return max(images, key=lambda p: Image.open(p).size[0] * Image.open(p).size[1])


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
    return (
        item.get("tag") == "DIV"
        and "role-share" in (item.get("className") or "")
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


def crop_box(rect: dict, scale: float, padding: int = 0) -> tuple[int, int, int, int]:
    left = math.floor(rect["left"] * scale) - padding
    top = math.floor(rect["top"] * scale) - padding
    right = math.ceil(rect["right"] * scale) + padding
    bottom = math.ceil(rect["bottom"] * scale) + padding
    return left, top, right, bottom


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_probe_dir()
    probe_path = folder / "layout_probe.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))

    image_path = pick_image(folder)
    image = Image.open(image_path).convert("RGB")
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    clone_probe = probe.get("html2canvasCloneProbe") or {}
    options = clone_probe.get("html2canvasOptions") or {}
    scale = options.get("scale") or (probe.get("exporter") or {}).get("scale") or 4

    items = (probe.get("rootDiscovery") or {}).get("imageLike") or []

    cards = [x for x in items if is_card(x)]
    portraits = [x for x in items if is_portrait(x)]
    weapons = [x for x in items if is_weapon_icon(x)]

    role_cards = []

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
        weapon = inside_weapons[0] if inside_weapons else None

        card_data = {
            "index": index,
            "cardText": card.get("textPreview") or "",
            "cardClassName": card.get("className") or "",
            "cardRect": card_rect,
            "portraitRect": portrait.get("rect_root_relative") if portrait else None,
            "weaponRect": weapon.get("rect_root_relative") if weapon else None,
            "portraitSrc": (
                ((portrait.get("images") or [{}])[0].get("currentSrc"))
                or ((portrait.get("images") or [{}])[0].get("src"))
                if portrait else ""
            ),
            "weaponSrc": (
                ((weapon.get("images") or [{}])[0].get("currentSrc"))
                or ((weapon.get("images") or [{}])[0].get("src"))
                if weapon else ""
            ),
        }
        role_cards.append(card_data)

        # card outline
        draw.rectangle(crop_box(card_rect, scale), outline=(255, 0, 0), width=2)

        if card_data["portraitRect"]:
            draw.rectangle(crop_box(card_data["portraitRect"], scale), outline=(0, 255, 0), width=3)

        if card_data["weaponRect"]:
            draw.rectangle(crop_box(card_data["weaponRect"], scale), outline=(0, 128, 255), width=3)

    role_cards.sort(key=lambda x: (center_y(x["cardRect"]), center_x(x["cardRect"])))

    out_json = folder / "role_cards_preview.json"
    out_overlay = folder / "role_cards_overlay.png"

    out_json.write_text(
        json.dumps(
            {
                "sourceProbe": str(probe_path),
                "image": image_path.name,
                "scale": scale,
                "cardsCount": len(role_cards),
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
    print("created:", out_json)
    print("created:", out_overlay)

    for c in role_cards[:10]:
        print(
            c["index"],
            "portrait:", bool(c["portraitRect"]),
            "weapon:", bool(c["weaponRect"]),
            "text:", c["cardText"][:80],
        )


if __name__ == "__main__":
    main()