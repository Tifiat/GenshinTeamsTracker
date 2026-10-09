from __future__ import annotations

import unittest

from run_workspace.pvp.abyss_rules import AbyssRulesError, AbyssRuleset, evaluate_deck
from run_workspace.pvp.deck import DRAFT_DECK_KIND, DraftCharacter, DraftDeck, DraftWeaponStack


IDS = {name: f"{index:024x}" for index, name in enumerate(
    ("version1", "family1", "a", "b", "trav_anemo", "trav_dendro", "w", "simple"), 1)}


def _replace_ids(value):
    if isinstance(value, dict):
        return {key: _replace_ids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item) for item in value]
    if isinstance(value, str):
        return IDS.get(value, value)
    return value


def _source() -> tuple[dict, list[dict], list[dict]]:
    agents = [
        {"_id": "a", "enkaId": "1001", "attribute": 17, "name": {"en": "Pyro A", "ru": "Пиро А"}},
        {"_id": "b", "enkaId": "1002", "attribute": 16, "name": {"en": "Hydro B"}},
        {"_id": "trav_anemo", "enkaId": "10000007", "attribute": 11, "name": {"en": "Traveler"}},
        {"_id": "trav_dendro", "enkaId": "10000007", "attribute": 13, "name": {"en": "Traveler"}},
    ]
    engines = [{"_id": "w", "enkaId": "2001"}, {"_id": "simple", "enkaId": "2002"}]
    system = {
        "_id": "version1", "root": "family1", "ref": None, "updatedAt": "2026-10-09T00:00:00Z",
        "main": {"title": "Synthetic Abyss"},
        "costs": {
            "system": "DEFAULT", "costLimit": 4,
            "agents": [
                {"agent": "a", "costs": [10, 11, 12, 13, 14, 15, 16, 5, 1], "specification": 0},
                {"agent": "b", "costs": [15] * 7 + [0, 0], "specification": 1,
                 "disableCostLimit": True},
                {"agent": "trav_anemo", "costs": [5] * 7 + [0, 0]},
                {"agent": "trav_dendro", "costs": [6] * 7 + [0, 0]},
            ],
            "engines": [
                {"engine": "w", "costs": [3, 4, 5, 6, 7, 2],
                 "bis": [{"agent": "a", "costs": [8, 9, 10, 11, 12, 0]}]},
                {"engine": "simple", "costs": [2, 3, 4, 5, 6, 0]},
            ],
            "agentsBundles": [{"cost": 4, "agents": [
                {"agent": "a", "mindscape": 0, "mindscapeMax": 0},
                {"agent": "b", "mindscape": 2},
            ]}],
            "tiers": [{"tier": 0, "minCost": 1, "maxCost": 9},
                      {"tier": 1, "minCost": 10, "maxCost": 19},
                      {"tier": 4, "minCost": 20, "maxCost": 100}],
        },
        "draft": {"minMaxCosts": {"agents": [20, 40], "engines": [0, 0]},
                  "minMaxCount": {"agents": [2, 3], "engines": [0, 0]}},
        "preset": {"rules": [
            {"type": "requires", "from": [{"agent": 1, "specification": 0}], "to": 4},
            {"type": "equals", "from": [{"agent": 0}, {"agent": 0}], "fromCost": 12, "to": 1},
            {"type": "required_agents", "agents": ["a", "trav_dendro"]},
            {"type": "max_count", "count": 3},
        ], "ddAgents": ["1001"]},
    }
    return _replace_ids(system), _replace_ids(agents), _replace_ids(engines)


def _character(game_id: str, element: str, *, level: int | None = 90,
               constellation: int | None = 0) -> DraftCharacter:
    return DraftCharacter(game_id, game_id, element, "SWORD", 5, level, constellation)


def _deck(*characters: DraftCharacter, weapons: tuple[DraftWeaponStack, ...] = ()) -> DraftDeck:
    return DraftDeck(1, DRAFT_DECK_KIND, "Synthetic", characters=characters, weapons=weapons)


def _weapon(game_id: str, refinement: int = 1, count: int = 1) -> DraftWeaponStack:
    return DraftWeaponStack(game_id, game_id, "SWORD", 5, 90, refinement, count)


class AbyssRulesTests(unittest.TestCase):
    def test_snapshot_is_pinned_allowlisted_and_roundtrips(self) -> None:
        system, agents, engines = _source()
        system["privateProfile"] = {"token": "never-copy"}
        rules = AbyssRuleset.from_source(system, agents, engines,
                                         sha256={"system": "a" * 64}, fetched_at="2026-10-09T01:00:00Z")
        payload = rules.to_dict()
        self.assertEqual(payload["source"]["system_id"], IDS["version1"])
        self.assertEqual(payload["source"]["root_id"], IDS["family1"])
        self.assertEqual(payload["source"]["sha256"]["system"], "a" * 64)
        self.assertEqual(payload["characters"][0]["names"], {"en": "Pyro A", "ru": "Пиро А"})
        self.assertNotIn("privateProfile", str(payload))
        self.assertEqual(AbyssRuleset.from_dict(payload).content_hash, rules.content_hash)
        payload["characters"][0]["constellation_costs"][0] = 999
        self.assertEqual(rules.to_dict()["characters"][0]["constellation_costs"][0], 10)

    def test_level_formula_tiers_and_incomplete_costs(self) -> None:
        rules = AbyssRuleset.from_source(*_source())
        report = evaluate_deck(_deck(_character("1001", "PYRO", level=95),
                                     _character("1002", "HYDRO", constellation=2)), rules)
        self.assertEqual(report.character_rows[0]["cost"], 12)  # ceil(10 * 1.05 + 1)
        self.assertEqual(report.character_base_total, 27)
        self.assertEqual(report.bundle_adjustment_total, 4)
        self.assertEqual(report.character_total, 31)
        self.assertEqual(report.tier_counts, {"1": 2})
        self.assertEqual(report.bundle_candidates[0]["members"][1]["constellation_min"], 2)
        self.assertEqual(report.bundle_candidates[0]["match"], "matched")
        self.assertIn("required_characters_missing", {issue.code for issue in report.issues})
        self.assertIn("bundle_application_unverified", {issue.code for issue in report.issues})
        self.assertIn("tier_combination_unverified", {issue.code for issue in report.issues})
        self.assertIn("french_difference_cap_unverified", {issue.code for issue in report.issues})
        self.assertFalse(report.ready)
        self.assertFalse(report.complete)
        at_100 = evaluate_deck(_deck(_character("1001", "PYRO", level=100)), rules)
        self.assertEqual(at_100.character_rows[0]["cost"], 13)  # ceil(10 * 1.10 + 2)
        missing = evaluate_deck(_deck(_character("1001", "PYRO", level=None)), rules)
        self.assertIsNone(missing.character_total)
        self.assertIn("character_level_unknown", {issue.code for issue in missing.issues})

    def test_weapon_prices_are_not_assigned_to_characters_by_guess(self) -> None:
        rules = AbyssRuleset.from_source(*_source())
        report = evaluate_deck(_deck(_character("1001", "PYRO"),
                                     weapons=(_weapon("2001", 2, 2), _weapon("2002", 1, 1))), rules)
        self.assertEqual(report.weapon_rows[0]["base_unit_cost"], 4)
        self.assertEqual(report.weapon_rows[0]["possible_unit_min"], 2)
        self.assertEqual(report.weapon_rows[0]["possible_unit_max"], 9)
        self.assertIsNone(report.weapon_rows[0]["resolved_unit_cost"])
        self.assertEqual(report.weapon_rows[1]["resolved_unit_cost"], 2)
        self.assertIsNone(report.weapon_total)
        self.assertEqual(report.weapon_count, 3)
        self.assertIn("weapon_assignment_needed", {issue.code for issue in report.issues})

    def test_variant_bounds_and_maximums(self) -> None:
        rules = AbyssRuleset.from_source(*_source())
        deck = _deck(_character("10000007", "DENDRO"), _character("1001", "PYRO"),
                     _character("1002", "HYDRO"), _character("missing", "CRYO"))
        report = evaluate_deck(deck, rules)
        self.assertEqual(report.character_rows[0]["source_id"], IDS["trav_dendro"])
        codes = {issue.code for issue in report.issues}
        self.assertIn("max_character_count_exceeded", codes)
        self.assertIn("bound_maximum_exceeded", codes)
        self.assertIn("character_unmapped", codes)
        self.assertIsNone(report.character_total)
        ambiguous = evaluate_deck(_deck(_character("10000007", "")), rules)
        self.assertIn("character_variant_ambiguous", {issue.code for issue in ambiguous.issues})
        self.assertIsNone(ambiguous.character_total)

    def test_corrupt_or_changed_source_is_rejected(self) -> None:
        source = _source()
        rules = AbyssRuleset.from_source(*source)
        payload = rules.to_dict()
        payload["profile"] = {"secret": True}
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)
        payload.pop("profile")
        payload["characters"][0]["constellation_costs"] = [1, 2]
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)
        changed, agents, engines = _source()
        changed["preset"]["rules"].append({"type": "unrecognized"})
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_source(changed, agents, engines)
        changed, agents, engines = _source()
        changed["costs"]["agents"][0]["costs"][0] = float("nan")
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_source(changed, agents, engines)

    def test_rootless_family_fallback_and_unsupported_cost_mode(self) -> None:
        system, agents, engines = _source()
        system["root"] = None
        rules = AbyssRuleset.from_source(system, agents, engines)
        self.assertEqual(rules.root_id, rules.system_id)
        self.assertFalse(rules.source["root_id_from_source"])
        system["costs"]["system"] = "FRENCH_COST"
        with self.assertRaisesRegex(AbyssRulesError, "Unsupported Abyss cost mode"):
            AbyssRuleset.from_source(system, agents, engines)

    def test_snapshot_rejects_cross_reference_and_oversized_names(self) -> None:
        rules = AbyssRuleset.from_source(*_source())
        payload = rules.to_dict()
        payload["bundles"][0]["members"][0]["game_id"] = "wrong"
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)
        payload = rules.to_dict()
        payload["characters"][0]["names"]["en"] = "x" * 513
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
