from __future__ import annotations

import unittest
from pathlib import Path

from run_workspace.pvp.weapon_identity import (
    WeaponObservedStackRef,
    dedupe_weapon_observed_stack_refs,
    draft_weapon_stack_from_observed_ref,
    weapon_observed_stack_ref_from_asset,
    weapon_observed_stack_ref_from_mapping,
    weapon_observed_stack_refs_from_assets,
)


class WeaponObservedStackIdentityTests(unittest.TestCase):
    def test_extracts_weapon_fingerprint_from_account_browser_asset(self) -> None:
        asset = _weapon_asset(
            "13407",
            "Favonius Lance",
            fingerprint="observed-stack-fingerprint",
            known_count=3,
        )

        ref = weapon_observed_stack_ref_from_asset(asset)

        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.weapon_fingerprint, "observed-stack-fingerprint")
        self.assertEqual(ref.key, "observed-stack-fingerprint")
        self.assertEqual(ref.weapon_id, "13407")
        self.assertEqual(ref.count, 3)
        self.assertEqual(ref.known_count, 3)

    def test_fallback_key_is_structured_and_excludes_display_and_source_fields(self) -> None:
        first = _weapon_asset(
            "11401",
            "Localized Name A",
            fingerprint="",
            path=r"C:\private\weapons\a.png",
            source_row_index=1,
            equipped_character_name="Owner A",
        )
        second = _weapon_asset(
            "11401",
            "Localized Name B",
            fingerprint="",
            path=r"D:\other\weapons\b.png",
            source_row_index=99,
            equipped_character_name="Owner B",
        )

        first_ref = weapon_observed_stack_ref_from_asset(first)
        second_ref = weapon_observed_stack_ref_from_asset(second)

        self.assertIsNotNone(first_ref)
        self.assertIsNotNone(second_ref)
        assert first_ref is not None and second_ref is not None
        self.assertEqual(first_ref.key, second_ref.key)
        self.assertEqual(first_ref.key, "11401|1|4|90|5")
        for forbidden in (
            "Localized",
            "private",
            "other",
            ".png",
            "Owner",
            "source_row",
            "icon",
        ):
            self.assertNotIn(forbidden.casefold(), first_ref.key.casefold())

    def test_same_stack_identity_dedupes_to_one_ref(self) -> None:
        refs = weapon_observed_stack_refs_from_assets(
            [
                _weapon_asset("13407", "Lance A", fingerprint="same-stack"),
                _weapon_asset("13407", "Lance B", fingerprint="same-stack"),
            ]
        )

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].key, "same-stack")

    def test_known_count_is_stack_count_not_copy_id(self) -> None:
        ref = weapon_observed_stack_ref_from_asset(
            _weapon_asset("15401", "Bow", fingerprint="bow-stack", known_count=4)
        )

        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.count, 4)
        payload = ref.to_dict()
        self.assertEqual(payload["count"], 4)
        for forbidden_key in ("weapon_copy_id", "copy_id", "weapon_instance_id", "row_id"):
            self.assertNotIn(forbidden_key, payload)

    def test_parses_existing_deck_preset_json_field_shapes(self) -> None:
        source_key_ref = weapon_observed_stack_ref_from_mapping(
            {
                "source_key": "legacy-source-key",
                "id": "13407",
                "type_name": "polearm",
                "rarity": "4",
                "level": "90",
                "refinement": "5",
                "known_count": "2",
            }
        )
        variant_ref = weapon_observed_stack_ref_from_mapping(
            {
                "variant_key": "legacy-variant-key",
                "weapon_id": "11401",
                "weapon_type": "1",
                "count": 1,
            }
        )

        self.assertEqual(source_key_ref.weapon_fingerprint, "legacy-source-key")
        self.assertEqual(source_key_ref.weapon_id, "13407")
        self.assertEqual(source_key_ref.weapon_type, "polearm")
        self.assertEqual(source_key_ref.count, 2)
        self.assertEqual(variant_ref.weapon_fingerprint, "legacy-variant-key")
        self.assertEqual(variant_ref.weapon_id, "11401")

    def test_converts_ref_to_backend_draft_weapon_stack(self) -> None:
        ref = WeaponObservedStackRef(
            weapon_fingerprint="stack",
            weapon_id="13407",
            weapon_type="13",
            rarity=4,
            level=80,
            refinement=3,
            count=2,
        )
        asset = _weapon_asset(
            "13407",
            "Favonius Lance",
            fingerprint="stack",
            weapon_type=13,
            weapon_type_name="Polearm",
            rarity=4,
            level=90,
            refinement=5,
            known_count=3,
        )

        stack = draft_weapon_stack_from_observed_ref(ref=ref, asset=asset)

        self.assertEqual(stack.weapon_id, "13407")
        self.assertEqual(stack.display_name, "Favonius Lance")
        self.assertEqual(stack.weapon_type, "Polearm")
        self.assertEqual(stack.rarity, 4)
        self.assertEqual(stack.level, 90)
        self.assertEqual(stack.refinement, 5)
        self.assertEqual(stack.count, 3)
        stack_payload = stack.to_dict()
        self.assertNotIn("weapon_copy_id", stack_payload)
        self.assertNotIn("weapon_instance_id", stack_payload)

    def test_dedupe_helper_accepts_refs_only_by_observed_stack_key(self) -> None:
        refs = dedupe_weapon_observed_stack_refs(
            (
                WeaponObservedStackRef(weapon_fingerprint="a", weapon_id="1"),
                WeaponObservedStackRef(weapon_fingerprint="a", weapon_id="1"),
                WeaponObservedStackRef(weapon_id="2", weapon_type="1", rarity=4),
            )
        )

        self.assertEqual(tuple(ref.key for ref in refs), ("a", "2|1|4||"))


def _weapon_asset(
    weapon_id: str,
    name: str,
    *,
    fingerprint: str | None = "fingerprint",
    weapon_type: int = 1,
    weapon_type_name: str = "Sword",
    rarity: int = 4,
    level: int = 90,
    refinement: int = 5,
    known_count: int = 1,
    path: str = "weapon.png",
    source_row_index: int = 0,
    equipped_character_name: str = "",
) -> dict:
    weapon = {
        "id": weapon_id,
        "name": name,
        "weapon_type": weapon_type,
        "weapon_type_name": weapon_type_name,
        "type_name": weapon_type_name,
        "rarity": rarity,
        "level": level,
        "refinement": refinement,
        "known_count": known_count,
        "local_icon_path": path,
        "icon_path": path,
        "icon_url": f"https://example.test/{Path(path).name}",
        "equipped_by": {
            "id": "1001",
            "name": equipped_character_name,
        },
    }
    if fingerprint is not None:
        if fingerprint:
            weapon["source_key"] = fingerprint
    return {
        "path": path,
        "filename": Path(path).name,
        "metadata": {
            "known_count": known_count,
            "weapon": weapon,
            "source_metadata": {
                "source_row_index": source_row_index,
                "equipped_character_name": equipped_character_name,
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
