"""Public, disposable 600-artifact Chasca account fixture.

Run only through the adjacent managed probe. This module uses current main
runtime APIs, with no account import or live catalog/database copy. The
versioned set selection and PRNG seed are in spec.json. A future reviewed
numerical gate can consume a measured receipt; this factory never writes one.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import sqlite3
from typing import Any

from hoyolab_export.artifact_db import create_build_preset, init_db
from hoyolab_export.artifact_fingerprint import artifact_content_fingerprint
from hoyolab_export.stat_normalization import STAT_MAPPINGS_BY_NORMALIZED_KEY
from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
    compatible_weapons,
    load_active_virtual_artifact_set_choices,
    load_active_virtual_roster_catalog,
)


SPEC_PATH = Path(__file__).with_name("spec.json")
STAMP = "2026-01-01T00:00:00+00:00"
SLOTS = {1: "flower", 2: "plume", 3: "sands", 4: "goblet", 5: "circlet"}
MAIN = {
    1: [("hp_flat", "HP", "4780")] * 5,
    2: [("atk_flat", "ATK", "311")] * 5,
    3: [("atk_percent", "ATK%", "46.6%"), ("hp_percent", "HP%", "46.6%"),
        ("elemental_mastery", "Elemental Mastery", "187"),
        ("energy_recharge", "Energy Recharge", "51.8%"),
        ("atk_percent", "ATK%", "46.6%")],
    4: [("anemo_dmg_bonus", "Anemo DMG", "46.6%"),
        ("hydro_dmg_bonus", "Hydro DMG", "46.6%"),
        ("electro_dmg_bonus", "Electro DMG", "46.6%"),
        ("atk_percent", "ATK%", "46.6%"), ("hp_percent", "HP%", "46.6%")],
    5: [("crit_rate", "CRIT Rate", "31.1%"),
        ("crit_damage", "CRIT DMG", "62.2%"),
        ("hp_percent", "HP%", "46.6%"),
        ("atk_percent", "ATK%", "46.6%"),
        ("elemental_mastery", "Elemental Mastery", "187")],
}
# Legal five-star substat roll tiers. Four distinct initial stats + five
# upgrades at +20; times count the initial roll and repeated upgrades.
ROLLS = {
    "hp_flat": ("209", "239", "269", "299"),
    "atk_flat": ("14", "16", "18", "19"),
    "def_flat": ("16", "19", "21", "23"),
    "hp_percent": ("4.1", "4.7", "5.3", "5.8"),
    "atk_percent": ("4.1", "4.7", "5.3", "5.8"),
    "def_percent": ("5.1", "5.8", "6.6", "7.3"),
    "elemental_mastery": ("16", "19", "21", "23"),
    "energy_recharge": ("4.5", "5.2", "5.8", "6.5"),
    "crit_rate": ("2.7", "3.1", "3.5", "3.9"),
    "crit_damage": ("5.4", "6.2", "7.0", "7.8"),
}
NAMES = {
    "hp_flat": "HP", "atk_flat": "ATK", "def_flat": "DEF",
    "hp_percent": "HP%", "atk_percent": "ATK%", "def_percent": "DEF%",
    "elemental_mastery": "Elemental Mastery", "energy_recharge": "Energy Recharge",
    "crit_rate": "CRIT Rate", "crit_damage": "CRIT DMG",
}


def _mapping(key: str):
    item = STAT_MAPPINGS_BY_NORMALIZED_KEY.get(key)
    if item is None:
        raise ValueError(f"Current main stat mapping lacks {key}")
    return item


def _substats(seed: int, artifact_id: int, main_key: str) -> list[dict[str, Any]]:
    rng = random.Random(f"{seed}:{artifact_id}")
    keys = rng.sample([key for key in ROLLS if key != main_key], 4)
    counts = {key: 1 for key in keys}
    for _ in range(5):
        counts[rng.choice(keys)] += 1
    result = []
    for key in keys:
        value = sum((Decimal(rng.choice(ROLLS[key])) for _ in range(counts[key])), Decimal(0))
        result.append({
            "property_type": _mapping(key).property_type,
            "property_name": NAMES[key],
            "value": format(value, "f") + ("%" if key.endswith("percent") or key in {
                "energy_recharge", "crit_rate", "crit_damage"} else ""),
            "times": counts[key],
        })
    assert len(result) == 4 and sum(row["times"] for row in result) == 9
    return result


def _artifact_id(set_index: int, slot: int, variant: int) -> int:
    return set_index * 25 + (slot - 1) * 5 + variant + 1


def create_fixture(root: Path, engine_store_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Create the fixture in a fresh managed-job child and return its receipt."""
    spec_bytes = SPEC_PATH.read_bytes()
    spec = json.loads(spec_bytes)
    if spec.get("schema_kind") != "public_chasca_full_account_probe_v1":
        raise ValueError("Unsupported Chasca probe spec")
    keys = tuple(spec["set_keys"])
    profiles = tuple(spec["profiles"])
    if len(keys) != 24 or len(set(keys)) != 24 or len(profiles) != 4:
        raise ValueError("Fixture must pin 24 unique sets and four profiles")
    if int(spec["variants_per_set_slot"]) != 5 or int(spec["rarity"]) != 5:
        raise ValueError("Fixture requires five level-20 variants per five-star set slot")
    store = GcsimEngineStore(engine_store_dir)
    installation = store.get_active_engine()
    if installation is None:
        raise RuntimeError("No selected GCSIM engine")
    context = load_active_gcsim_optimizer_engine_context(store_dir=engine_store_dir)
    if context.engine_id != spec["engine_id"] or context.artifact_sha256 != spec["engine_artifact_sha256"]:
        raise RuntimeError("Selected engine differs from pinned Chasca fixture identity")
    catalog = context.catalog
    for key in keys:
        item = catalog.get(key)
        if item is None or item.max_rarity != 5 or not item.registered or not item.complete_four_piece_modeled:
            raise ValueError(f"Pinned set is not a modeled five-star 4-piece in selected engine: {key}")

    root = Path(root).resolve(strict=True)
    db_path = root / "chasca-public-600.db"
    if db_path.exists():
        raise FileExistsError(db_path)
    roster = load_active_virtual_roster_catalog(store=store)
    characters = {item.gcsim_key.casefold(): item for item in roster.characters}
    weapons = {item.gcsim_key.casefold(): item for item in roster.weapons}
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    selected_slots: list[dict[str, Any]] = []
    selected_receipt: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    try:
        init_db(connection)
        # The virtual picker resolves actual engine-backed UIDs. On this empty
        # synthetic DB it falls back to the engine's key; never invent one.
        choices = {item.gcsim_key.casefold(): item for item in
                   load_active_virtual_artifact_set_choices(db_path, language="en-us", store=store)}
        if any(key not in choices or not choices[key].set_uid.strip() for key in keys):
            raise ValueError("Selected engine lacks an artifact-set UID for a pinned key")
        names = {str(p["selected_set_key"]): str(p["selected_set_name"]) for p in profiles}
        for key in keys:
            choice = choices[key]
            name = names.get(key, choice.display_name)
            connection.execute(
                "INSERT INTO artifact_sets (set_uid, hoyowiki_entry_id, fallback_name, display_name, source, updated_at) "
                "VALUES (?, ?, ?, ?, 'synthetic_probe', ?)",
                (choice.set_uid, f"synthetic:{key}", name, name, STAMP),
            )
            connection.execute(
                "INSERT INTO artifact_set_names (set_uid, lang, name, normalized_name, updated_at) "
                "VALUES (?, 'en-us', ?, ?, ?)",
                (choice.set_uid, name, name.casefold(), STAMP),
            )
        for set_index, key in enumerate(keys):
            set_uid = choices[key].set_uid
            set_name = names.get(key, choices[key].display_name)
            for slot, slot_key in SLOTS.items():
                for variant in range(5):
                    artifact_id = _artifact_id(set_index, slot, variant)
                    main_key, main_name, main_value = MAIN[slot][variant]
                    substats = _substats(int(spec["seed"]), artifact_id, main_key)
                    content = artifact_content_fingerprint(
                        set_uid=set_uid, pos=slot, rarity=5, level=20,
                        main_property_type=_mapping(main_key).property_type,
                        main_property_value=main_value, substats=substats,
                    )
                    if content in fingerprints:
                        raise ValueError(f"Duplicate synthetic artifact content at {artifact_id}")
                    fingerprints.add(content)
                    physical = hashlib.sha256(f"chasca-public-v1:{artifact_id}".encode()).hexdigest()
                    connection.execute(
                        "INSERT INTO artifacts (id, fingerprint, content_fingerprint, name, set_uid, set_name, "
                        "pos, pos_name, rarity, level, main_property_type, main_property_name, "
                        "main_property_value, first_seen_at, last_seen_at, import_source, import_format, json_imported) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, 20, ?, ?, ?, ?, ?, 'synthetic_probe', 'chasca_public_v1', 0)",
                        (artifact_id, physical, content, f"Synthetic {key} {slot_key} {variant}",
                         set_uid, set_name, slot, slot_key, _mapping(main_key).property_type,
                         main_name, main_value, STAMP, STAMP),
                    )
                    connection.executemany(
                        "INSERT INTO artifact_substats (artifact_id, slot_index, property_type, property_name, value, times) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        [(artifact_id, index, row["property_type"], row["property_name"],
                          row["value"], row["times"]) for index, row in enumerate(substats)],
                    )

        for index, profile in enumerate(profiles):
            character_key = str(profile["character_key"]).casefold()
            weapon_key = str(profile["weapon_key"]).casefold()
            character, weapon = characters.get(character_key), weapons.get(weapon_key)
            if character is None or weapon is None or weapon not in compatible_weapons(character, roster.weapons):
                raise ValueError(f"Selected engine has no compatible {character_key}/{weapon_key} pair")
            set_key = str(profile["selected_set_key"])
            if set_key not in keys:
                raise ValueError(f"Selected set is absent from inventory: {set_key}")
            set_index = keys.index(set_key)
            variants = tuple(int(v) for v in profile["baseline_variants"])
            if len(variants) != 5 or any(v < 0 or v > 4 for v in variants):
                raise ValueError("Baseline variants must name one owned item per slot")
            build_slots = {slot: _artifact_id(set_index, slot, variants[slot - 1]) for slot in SLOTS}
            character_id = 900_001 + index
            connection.execute(
                "INSERT INTO account_characters (character_id, name, catalog_english_name, gcsim_character_key, "
                "gcsim_character_key_status, gcsim_character_key_method, updated_at) "
                "VALUES (?, ?, ?, ?, 'ready', 'synthetic_probe', ?)",
                (character_id, profile["name"], profile["name"], character.gcsim_key, STAMP),
            )
            build_name = f"Chasca probe {profile['name']} fixed 4p"
            build_id = create_build_preset(
                connection, name=build_name, slots=build_slots,
                targets=[{"target_type": "gcsim_character", "gcsim_character_key": character.gcsim_key,
                          "character_name": profile["name"]}],
            )
            for slot, slot_key in SLOTS.items():
                connection.execute(
                    "INSERT INTO account_character_equipped_artifacts "
                    "(character_id, slot_key, artifact_id, source, updated_at) "
                    "VALUES (?, ?, ?, 'manual', ?)",
                    (character_id, slot_key, build_slots[slot], STAMP),
                )
            choice = choices[set_key]
            bonus = GcsimVirtualSetBonus(
                set_uid=choice.set_uid, display_name=str(profile["selected_set_name"]),
                gcsim_key=choice.gcsim_key, piece_count=4,
            )
            override = GcsimVirtualSlotOverride(
                team_index=0, slot_index=index, character_key=character.gcsim_key,
                character_name=str(profile["name"]), character_weapon_type=character.weapon_type,
                constellation=int(profile["constellation"]), refinement=int(profile["refinement"]),
                character_level=90, talent_normal=int(profile["talents"][0]),
                talent_skill=int(profile["talents"][1]), talent_burst=int(profile["talents"][2]),
                weapon_level=90, weapon_promote_level=6, artifact_build_id=build_id,
                artifact_build_name=build_name, artifact_set_bonuses=(bonus,),
            ).with_weapon(weapon)
            selected_slots.append({"slot_index": index, "gcsim_virtual_override": override.to_dict()})
            selected_receipt.append({
                "character": character.gcsim_key, "weapon": weapon.gcsim_key,
                "refinement": int(profile["refinement"]), "constellation": int(profile["constellation"]),
                "character_level": 90, "weapon_level": 90, "talents": list(profile["talents"]),
                "selected_set_name": str(profile["selected_set_name"]),
                "selected_set_key": choice.gcsim_key, "selected_set_uid": choice.set_uid,
                "baseline_artifact_ids": [build_slots[slot] for slot in SLOTS],
            })
        connection.commit()
    finally:
        connection.close()
    if len(fingerprints) != 600 or len({x for p in selected_receipt for x in p["baseline_artifact_ids"]}) != 20:
        raise AssertionError("Synthetic inventory/baseline count mismatch")
    receipt = {
        "schema_kind": spec["schema_kind"], "spec_sha256": hashlib.sha256(spec_bytes.replace(b"\r\n", b"\n")).hexdigest(),
        "engine_id": context.engine_id, "engine_artifact_sha256": context.artifact_sha256,
        "engine_binding_sha256": context.binding_sha256,
        "seed": int(spec["seed"]), "artifact_count": 600,
        "content_fingerprints_sha256": hashlib.sha256(
            "\n".join(sorted(fingerprints)).encode("utf-8")
        ).hexdigest(),
        "selected": selected_receipt,
        "set_uids": [{"key": key, "uid": choices[key].set_uid, "max_rarity": 5} for key in keys],
        "rotation_sha256": hashlib.sha256(spec["rotation"].encode()).hexdigest(),
    }
    return db_path, {"slots": selected_slots}, receipt
