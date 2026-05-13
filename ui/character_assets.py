from __future__ import annotations

from pathlib import Path

from hoyolab_export.paths import PROJECT_ROOT

FILTER_ASSETS_DIR = PROJECT_ROOT / "assets" / "filters"

ELEMENT_FILTERS = [
    ("Pyro", "element_pyro.png", "filter.element.pyro"),
    ("Hydro", "element_hydro.png", "filter.element.hydro"),
    ("Geo", "element_geo.png", "filter.element.geo"),
    ("Electro", "element_electro.png", "filter.element.electro"),
    ("Dendro", "element_dendro.png", "filter.element.dendro"),
    ("Cryo", "element_cryo.png", "filter.element.cryo"),
    ("Anemo", "element_anemo.png", "filter.element.anemo"),
]

WEAPON_TYPE_FILTERS = [
    ("sword", "weapon_sword.png", "filter.weapon_type.sword"),
    ("catalyst", "weapon_catalyst.png", "filter.weapon_type.catalyst"),
    ("claymore", "weapon_claymore.png", "filter.weapon_type.claymore"),
    ("bow", "weapon_bow.png", "filter.weapon_type.bow"),
    ("polearm", "weapon_polearm.png", "filter.weapon_type.polearm"),
]

CHARACTER_RARITY_FILTERS = [
    (5, "rarity_5.png", "filter.rarity.5"),
    (4, "rarity_4.png", "filter.rarity.4"),
]

WEAPON_RARITY_FILTERS = [
    (5, "rarity_5.png", "filter.rarity.5"),
    (4, "rarity_4.png", "filter.rarity.4"),
    (3, "rarity_3.png", "filter.rarity.3"),
]


def asset_path_from_manifest_crop(crop: str | None) -> Path | None:
    if not crop:
        return None

    path = Path(crop)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def folder_asset_items(directory: str | Path) -> list[dict]:
    directory = Path(directory)
    if not directory.exists():
        return []

    return [
        {
            "path": path,
            "filename": path.name,
            "tooltip": "",
            "metadata": None,
        }
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() == ".png"
    ]


def manifest_asset_items(
    manifest: dict,
    manifest_key: str,
    directory: str | Path,
) -> list[dict]:
    items = []
    seen_files = set()

    for asset in manifest.get(manifest_key, []):
        crop_path = asset_path_from_manifest_crop(asset.get("crop"))
        if crop_path is None or not crop_path.exists():
            continue

        items.append(
            {
                "path": crop_path,
                "filename": crop_path.name,
                "tooltip": asset.get("tooltip") or "",
                "metadata": asset,
            }
        )
        seen_files.add(crop_path.resolve())

    for item in folder_asset_items(directory):
        try:
            resolved = Path(item["path"]).resolve()
        except OSError:
            resolved = None
        if resolved is None or resolved not in seen_files:
            items.append(item)

    return items


def metadata_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def character_metadata(asset: dict) -> dict:
    metadata = asset.get("metadata") or {}
    return metadata.get("character") or {}


def character_id(asset: dict) -> int | None:
    character = character_metadata(asset)
    value = character.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def character_name(asset: dict) -> str:
    character = character_metadata(asset)
    return str(character.get("name") or asset.get("filename") or "")


def character_matches_filters(
    asset: dict,
    element_filters: set[str],
    weapon_filters: set[str],
    rarity_filters: set[int],
) -> bool:
    metadata = asset.get("metadata")
    if not metadata:
        return True

    character = character_metadata(asset)
    element = character.get("element")
    weapon_type = str(character.get("weapon_type_name") or "").lower()
    rarity = metadata_int(character.get("rarity"))

    if element_filters and element not in element_filters:
        return False
    if weapon_filters and weapon_type not in weapon_filters:
        return False
    if rarity_filters and rarity not in rarity_filters:
        return False

    return True


def character_sort_key(asset: dict):
    character = character_metadata(asset)
    rarity = metadata_int(character.get("rarity"))
    level = metadata_int(character.get("level"))
    name = character_name(asset).casefold()
    return (-rarity, -level, name, str(asset.get("filename") or ""))
