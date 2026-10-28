from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QWidget

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db
from hoyolab_export.account_storage import (
    AccountCharacterRuntimeRecord,
    AccountWeaponObservedStack,
    get_account_character,
    list_account_characters,
    list_account_weapon_observed_stacks,
)
from hoyolab_export.account_equipment import list_equipped_weapon_owners
from hoyolab_export.artifact_stats import (
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    DEF_PERCENT,
    ENERGY_RECHARGE,
    HEALING_BONUS,
    HP_PERCENT,
    PHYSICAL_DAMAGE,
    PYRO_DAMAGE,
    ELECTRO_DAMAGE,
    HYDRO_DAMAGE,
    DENDRO_DAMAGE,
    ANEMO_DAMAGE,
    GEO_DAMAGE,
    CRYO_DAMAGE,
    property_name,
)
from hoyolab_export.crop_manifest import IGNORED_CHARACTER_IDS, IGNORED_WEAPON_RARITIES
from hoyolab_export.asset_paths import character_variant_path, element_icon_path
from hoyolab_export.paths import PROJECT_ROOT
from hoyolab_export.character_trait_catalog import (
    TRAIT_HEXEREI,
    TRAIT_MOONSIGN,
    TRAIT_STANDARD_5_STAR,
)
from localization import get_language
from ui.artifact_browser.stat_types import localized_stat_label
from ui.utils.icon_utils import tinted_svg_pixmap

FILTER_ASSETS_DIR = PROJECT_ROOT / "assets" / "filters"
TEAM_BONUS_ASSETS_DIR = PROJECT_ROOT / "assets" / "team_bonus"

STANDARD_FILTER_ALL = "all"
STANDARD_FILTER_ONLY = "only"
STANDARD_FILTER_EXCLUDE = "exclude"

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


def filter_icon_path(icon_name: str) -> Path:
    """Use imported HoYoLAB element layers after an import; keep preimport icons."""
    if icon_name.startswith("element_") and icon_name.endswith(".png"):
        imported = element_icon_path(icon_name[len("element_"):-4])
        if imported is not None:
            return imported
    return FILTER_ASSETS_DIR / icon_name


def refresh_imported_element_filter_icons(root: QWidget) -> None:
    """Refresh already-visible filter buttons after import or profile switch."""
    for button in root.findChildren(QPushButton):
        icon_name = button.property("elementIconName")
        if not isinstance(icon_name, str) or not icon_name:
            continue
        path = filter_icon_path(icon_name)
        if path.is_file():
            button.setIcon(QIcon(str(path)))

CHARACTER_TRAIT_FILTERS = [
    (TRAIT_MOONSIGN, "../team_bonus/Moonsign.png", "filter.trait.moonsign"),
    (TRAIT_HEXEREI, "../team_bonus/Hexerei.png", "filter.trait.hexerei"),
]

CHARACTER_STANDARD_FILTER = (
    TRAIT_STANDARD_5_STAR,
    "standard.png",
    "filter.standard_5_star",
)


def standard_character_filter_icon(
    mode: str,
    *,
    size: int = 24,
) -> QIcon:
    base = QIcon(str(FILTER_ASSETS_DIR / CHARACTER_STANDARD_FILTER[1])).pixmap(size, size)
    if mode != STANDARD_FILTER_EXCLUDE:
        return QIcon(base)

    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(0, 0, base)
    painter.drawPixmap(0, 0, tinted_svg_pixmap("ban", size, "#ef4444"))
    painter.end()
    return QIcon(canvas)

PERCENT_PROPERTY_TYPES = {
    HP_PERCENT,
    ATK_PERCENT,
    DEF_PERCENT,
    CRIT_RATE,
    CRIT_DAMAGE,
    ENERGY_RECHARGE,
    HEALING_BONUS,
    PHYSICAL_DAMAGE,
    PYRO_DAMAGE,
    ELECTRO_DAMAGE,
    HYDRO_DAMAGE,
    DENDRO_DAMAGE,
    ANEMO_DAMAGE,
    GEO_DAMAGE,
    CRYO_DAMAGE,
}


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


def load_account_character_asset_items(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[dict]:
    with closing(connect_db(db_path)) as conn:
        return [
            item
            for item in (
                account_character_asset_item(record)
                for record in list_account_characters(conn)
            )
            if item is not None
        ]


def load_account_weapon_stack_asset_items(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[dict]:
    with closing(connect_db(db_path)) as conn:
        characters_by_id = {
            str(record.character_id): record
            for record in list_account_characters(conn)
        }
        return [
            item
            for item in (
                account_weapon_stack_asset_item(
                    record,
                    owner_badges=_weapon_owner_badges(
                        characters_by_id,
                        list_equipped_weapon_owners(conn, record.weapon_fingerprint),
                    ),
                )
                for record in list_account_weapon_observed_stacks(conn)
            )
            if item is not None
        ]


def load_weapon_owner_badges_for_fingerprints(
    fingerprints: set[str],
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, list[dict[str, Any]]]:
    """Refresh ownership after an equip action without rebuilding the weapon catalog."""
    wanted = {str(value).strip() for value in fingerprints if str(value).strip()}
    if not wanted:
        return {}
    with closing(connect_db(db_path)) as conn:
        owners_by_fingerprint = {
            fingerprint: list_equipped_weapon_owners(conn, fingerprint)
            for fingerprint in wanted
        }
        owner_ids = {
            character_id
            for owners in owners_by_fingerprint.values()
            for character_id in owners
        }
        characters_by_id: dict[str, AccountCharacterRuntimeRecord] = {}
        for character_id in owner_ids:
            record = get_account_character(conn, character_id)
            if record is not None:
                characters_by_id[str(character_id)] = record
    return {
        fingerprint: _weapon_owner_badges(characters_by_id, owners)
        for fingerprint, owners in owners_by_fingerprint.items()
    }


def account_character_asset_item(
    record: AccountCharacterRuntimeRecord,
) -> dict[str, Any] | None:
    if _optional_int(record.character_id) in IGNORED_CHARACTER_IDS:
        return None

    path = _existing_project_path(record.portrait_path) or _existing_project_path(
        record.side_icon_path
    )
    if path is None:
        return None

    character_ref = record.to_team_builder_character_ref()
    metadata = {
        "source": "account_sqlite",
        "character": character_ref,
        "region_key": record.region_key,
        "region_name": record.region_name,
        "traits": list(record.traits),
        "is_standard_5_star": record.is_standard_5_star,
        "talents": [talent.to_dict() for talent in record.talents],
        "source_metadata": dict(record.source_metadata or {}),
        "warnings": list(record.warnings),
    }
    # A packaged PvP account contains SQLite but no separate image manifest.
    # Reuse local variants only when its browser bitmap is exactly the one in
    # the current manifest; a matching ID alone could belong to another owner.
    manifest_browser = character_variant_path(record.character_id, "crop")
    matching_variants = manifest_browser is not None and manifest_browser.resolve() == path.resolve()
    pvp_path = character_variant_path(record.character_id, "pvp") if matching_variants else None
    history_path = character_variant_path(record.character_id, "history") if matching_variants else None
    if pvp_path is not None:
        metadata["portrait_pvp_path"] = str(pvp_path)
    if history_path is not None:
        metadata["portrait_history_path"] = str(history_path)
        character_ref["portrait_history_path"] = str(history_path)
    return {
        "path": path,
        "filename": path.name,
        "tooltip": _character_tooltip(record),
        "metadata": metadata,
    }


def pvp_character_asset_item(asset: dict[str, Any]) -> dict[str, Any]:
    """Swap only the baked image; per-seat PvP constellation badges stay intact."""
    metadata = dict(asset.get("metadata") or {})
    pvp_path = _existing_project_path(metadata.get("portrait_pvp_path"))
    if pvp_path is None:
        return asset
    character = dict(metadata.get("character") or {})
    character["portrait_path"] = str(pvp_path)
    character["local_portrait_path"] = str(pvp_path)
    metadata["character"] = character
    return {**asset, "path": pvp_path, "filename": pvp_path.name, "metadata": metadata}


def account_weapon_stack_asset_item(
    record: AccountWeaponObservedStack,
    *,
    owner_badges: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if record.rarity in IGNORED_WEAPON_RARITIES:
        return None

    path = _existing_project_path(record.icon_path)
    if path is None:
        return None

    metadata = {
        "source": "account_sqlite_observed_weapon_stack",
        "weapon": record.to_team_builder_weapon_ref(),
        "name": record.name,
        "known_count": record.known_count,
        "variants": [],
        "source_metadata": dict(record.source_metadata or {}),
        "warnings": list(record.warnings),
    }
    if owner_badges:
        metadata["owner_badges"] = list(owner_badges)
        metadata["extra_owner_count"] = max(0, len(owner_badges) - 1)
    return {
        "path": path,
        "filename": path.name,
        "tooltip": _weapon_tooltip(record),
        "metadata": metadata,
    }


def _weapon_owner_badges(
    characters_by_id: dict[str, AccountCharacterRuntimeRecord],
    owner_character_ids: tuple[int, ...],
) -> list[dict[str, Any]]:
    badges: list[dict[str, Any]] = []
    for character_id in owner_character_ids:
        record = characters_by_id.get(str(character_id))
        if record is None:
            continue
        side_icon_path = _existing_project_path(record.side_icon_path)
        if side_icon_path is None:
            continue
        badges.append(
            {
                "character_id": str(record.character_id),
                "name": record.name,
                "side_icon_path": str(side_icon_path),
            }
        )
    return badges


def _existing_project_path(value: str | Path | None) -> Path | None:
    path = asset_path_from_manifest_crop(str(value or ""))
    if path is None or not path.exists():
        return None
    return path


def _character_tooltip(record: AccountCharacterRuntimeRecord) -> str:
    parts = [record.name or record.character_id]
    meta = []
    if record.level is not None:
        meta.append(f"Lv.{record.level}")
    if record.constellation is not None:
        meta.append(f"C{record.constellation}")
    if record.element:
        meta.append(record.element)
    if meta:
        parts.append(" | ".join(meta))
    return "\n".join(parts)


def _weapon_tooltip(record: AccountWeaponObservedStack) -> str:
    parts = [record.name or record.weapon_id]
    meta = []
    if record.refinement is not None:
        meta.append(f"R{record.refinement}")
    if record.level is not None:
        meta.append(f"Lv.{record.level}")
    if record.base_atk is not None:
        meta.append(f"ATK {_format_stat_number(record.base_atk)}")
    if record.secondary_property_type is not None and record.secondary_stat_value is not None:
        meta.append(
            f"{_stat_display_label(record.secondary_property_type)} "
            f"{_format_stat_value(record.secondary_property_type, record.secondary_stat_value)}"
        )
    if record.known_count > 1:
        meta.append(f"x{record.known_count}")
    if meta:
        parts.append(" | ".join(meta))
    return "\n".join(parts)


def _format_stat_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _format_stat_value(property_type: int | None, value: float) -> str:
    text = _format_stat_number(value)
    if property_type in PERCENT_PROPERTY_TYPES:
        return f"{text}%"
    return text


def _stat_display_label(property_type: int | None) -> str:
    label = property_name(property_type)
    if property_type is None:
        return "Stat"
    if label is None or label == str(property_type):
        return f"Stat {property_type}"
    return localized_stat_label(
        property_type,
        language=get_language(),
        fallback=label,
    )


def _optional_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    region_filters: set[str] | None = None,
    trait_filters: set[str] | None = None,
    standard_filter: str = STANDARD_FILTER_ALL,
) -> bool:
    region_filters = region_filters or set()
    trait_filters = trait_filters or set()
    metadata = asset.get("metadata")
    if not metadata:
        return True

    character = character_metadata(asset)
    element = character.get("element")
    weapon_type = str(character.get("weapon_type_name") or "").lower()
    rarity = metadata_int(character.get("rarity"))
    region_key = str(character.get("region_key") or metadata.get("region_key") or "")
    traits = set(character.get("traits") or metadata.get("traits") or [])
    is_standard = bool(
        character.get("is_standard_5_star")
        or metadata.get("is_standard_5_star")
        or TRAIT_STANDARD_5_STAR in traits
    )

    if element_filters and element not in element_filters:
        return False
    if weapon_filters and weapon_type not in weapon_filters:
        return False
    if rarity_filters and rarity not in rarity_filters:
        return False
    if region_filters and region_key not in region_filters:
        return False
    if trait_filters and not traits.intersection(trait_filters):
        return False
    if standard_filter == STANDARD_FILTER_ONLY and not is_standard:
        return False
    if standard_filter == STANDARD_FILTER_EXCLUDE and is_standard:
        return False

    return True


def character_sort_key(asset: dict):
    character = character_metadata(asset)
    rarity = metadata_int(character.get("rarity"))
    level = metadata_int(character.get("level"))
    name = character_name(asset).casefold()
    return (-rarity, -level, name, str(asset.get("filename") or ""))
