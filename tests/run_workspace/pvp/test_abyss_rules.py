from __future__ import annotations

import unittest

from hoyolab_export.traveler import TRAVELER_ELEMENTS, traveler_variant_id
from run_workspace.pvp.abyss_rules import AbyssRulesError, AbyssRuleset, evaluate_deck
from run_workspace.pvp.deck import DRAFT_DECK_KIND, DraftCharacter, DraftDeck, DraftWeaponStack
from run_workspace.pvp.tier_allocation import allocate_requirements


IDS = {name: f"{index:024x}" for index, name in enumerate(
    ("version1", "family1", "a", "b", "trav_anemo", "trav_dendro", "w", "simple",
     "trav_geo", "trav_electro", "trav_hydro", "trav_pyro", "trav_cryo"), 1)}


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


def _traveler_source() -> tuple[dict, list[dict], list[dict]]:
    system, agents, engines = _source()
    rows = {
        "Anemo": (IDS["trav_anemo"], 11, 5),
        "Geo": (IDS["trav_geo"], 15, 2),
        "Electro": (IDS["trav_electro"], 14, 3),
        "Dendro": (IDS["trav_dendro"], 13, 6),
        "Hydro": (IDS["trav_hydro"], 16, 4),
        "Pyro": (IDS["trav_pyro"], 17, 7),
        "Cryo": (IDS["trav_cryo"], 12, 8),
    }
    existing = {row["_id"] for row in agents}
    cost_rows = {row["agent"]: row for row in system["costs"]["agents"]}
    for element in TRAVELER_ELEMENTS:
        source_id, attribute, price = rows[element]
        if source_id not in existing:
            agents.append({"_id": source_id, "enkaId": "10000007", "attribute": attribute,
                           "name": {"en": "Traveler"}})
        if source_id in cost_rows:
            cost_rows[source_id]["costs"] = [price] * 7 + [0, 0]
        else:
            row = {"agent": source_id, "costs": [price] * 7 + [0, 0]}
            system["costs"]["agents"].append(row)
            cost_rows[source_id] = row
    system["preset"]["rules"] = [
        {"type": "required_agents", "agents": [IDS["trav_pyro"]]},
    ]
    system["draft"] = {"minMaxCosts": {"agents": [0, 0], "engines": [0, 0]},
                       "minMaxCount": {"agents": [0, 0], "engines": [0, 0]}}
    return system, agents, engines


def _character(game_id: str, element: str, *, level: int | None = 90,
               constellation: int | None = 0) -> DraftCharacter:
    return DraftCharacter(game_id, game_id, element, "SWORD", 5, level, constellation)


def _screenshot_scale_source():
    """Synthetic identities; only tier counts/total match the 9 Oct user screenshot."""
    system, _, _ = _source()
    system["main"]["title"] = "Synthetic 78-character roster"
    system["costs"].update(agents=[], engines=[], agentsBundles=[], tiers=[
        {"tier": tier, "minCost": low, "maxCost": high}
        for tier, low, high in ((0, 1, 14), (1, 15, 44), (2, 45, 49), (3, 50, 64), (4, 65, 1000))
    ])
    system["draft"] = {"minMaxCosts": {"agents": [520, 0], "engines": [0, 0]},
                       "minMaxCount": {"agents": [0, 0], "engines": [0, 0]}}
    system["preset"] = {"ddAgents": [], "rules": [
        {"type": "requires", "to": 4, "from": [{"agent": 1, "specification": 0}, {"agent": 1, "specification": 1}]},
        {"type": "requires", "to": 3, "from": [{"agent": 1}]},
        {"type": "equals", "to": 1, "from": [{"agent": 0}] * 3, "fromCost": 19},
        {"type": "equals", "to": 1, "from": [{"agent": 0}] * 4, "fromCost": 20},
        {"type": "max_count", "count": 50},
    ]}
    agents, characters = [], []
    for tier, count, cost in ((0, 19, 7), (1, 17, 20), (2, 1, 47), (3, 3, 50), (4, 2, 70), (None, 36, 0)):
        for local_index in range(count):
            index = len(agents)
            sid, cid = f"{100 + index:024x}", str(90000000 + index)
            price = cost + (11 if tier == 1 and local_index < 7 else 0)
            agents.append({"_id": sid, "enkaId": cid, "attribute": 17,
                           "name": {"en": f"Fixture {index + 1}"}})
            system["costs"]["agents"].append({"agent": sid, "costs": [price] * 7 + [0, 0], "specification": 0})
            if local_index % 2 == 0:
                system["preset"]["ddAgents"].append(cid)
            characters.append(_character(cid, "PYRO"))
    return (system, agents, []), tuple(characters)


def _deck(*characters: DraftCharacter, weapons: tuple[DraftWeaponStack, ...] = ()) -> DraftDeck:
    return DraftDeck(1, DRAFT_DECK_KIND, "Synthetic", characters=characters, weapons=weapons)


def _weapon(game_id: str, refinement: int = 1, count: int = 1) -> DraftWeaponStack:
    return DraftWeaponStack(game_id, game_id, "SWORD", 5, 90, refinement, count)


class AbyssRulesTests(unittest.TestCase):
    def test_traveler_variants_keep_element_prices_and_pyro_required_rule(self):
        rules = AbyssRuleset.from_source(*_traveler_source())
        game_id = 10000005  # public source rows use Lumine's 10000007 alias
        prices = dict(zip(TRAVELER_ELEMENTS, (5, 2, 3, 6, 4, 7, 8)))
        characters = tuple(
            _character(
                str(game_id) if element == "Anemo" else str(traveler_variant_id(game_id, element)),
                element.upper(),
                constellation=0,
            )
            for element in TRAVELER_ELEMENTS
        )

        report = evaluate_deck(_deck(*characters), rules)

        self.assertEqual(
            {character.element: row["cost"] for character, row in zip(characters, report.character_rows)},
            {element.upper(): prices[element] for element in TRAVELER_ELEMENTS},
        )
        self.assertNotIn("required_characters_missing", {issue.code for issue in report.issues})

        without_pyro = tuple(character for character in characters if character.element != "PYRO")
        missing_required = evaluate_deck(_deck(*without_pyro), rules)
        self.assertIn("required_characters_missing", {issue.code for issue in missing_required.issues})

    def test_traveler_rule_lookup_never_guesses_an_element(self):
        rules = AbyssRuleset.from_source(*_traveler_source())
        ambiguous = evaluate_deck(_deck(_character("10000005", "")), rules)
        wrong = evaluate_deck(_deck(_character(str(traveler_variant_id(10000005, "Pyro")), "HYDRO")), rules)

        self.assertIn("character_variant_ambiguous", {issue.code for issue in ambiguous.issues})
        self.assertIsNone(ambiguous.character_rows[0]["source_id"])
        self.assertIn("character_unmapped", {issue.code for issue in wrong.issues})
        self.assertIsNone(wrong.character_rows[0]["source_id"])

    def test_missing_element_anchor_stays_ambiguous_with_one_source_row(self):
        system, agents, engines = _source()
        agents = [row for row in agents if row["_id"] != IDS["trav_dendro"]]
        system["costs"]["agents"] = [
            row for row in system["costs"]["agents"]
            if row["agent"] != IDS["trav_dendro"]
        ]
        system["preset"]["rules"] = [
            {"type": "required_agents", "agents": [IDS["trav_anemo"]]},
        ]
        rules = AbyssRuleset.from_source(system, agents, engines)

        report = evaluate_deck(_deck(_character("10000007", "")), rules)

        self.assertIn("character_variant_ambiguous", {issue.code for issue in report.issues})
        self.assertIsNone(report.character_rows[0]["source_id"])
        self.assertIsNone(report.character_rows[0]["cost"])

    def test_screenshot_scale_roster_with_zero_prices_keeps_known_allocation(self):
        source, characters = _screenshot_scale_source()
        rules = AbyssRuleset.from_source(*source)
        report = evaluate_deck(_deck(*characters), rules)
        self.assertEqual(report.character_total, 887)
        self.assertEqual(report.character_count, 78)
        self.assertEqual(report.tier_counts, {"0": 19, "1": 17, "2": 1, "3": 3, "4": 2})
        self.assertEqual(sum(row["tier_status"] == "outside" for row in report.character_rows), 36)
        allocation = allocate_requirements(report.character_rows, rules.to_dict()["preset_rules"])
        self.assertEqual(allocation["status"], "pass")
        self.assertEqual([(row["covered"], row["selected"]) for row in allocation["rules"]], [(2, 2), (3, 3)])
        self.assertEqual([row["filled"] for row in allocation["rules"][0]["slots"]], [2, 2])
        self.assertEqual([row["used"] for row in allocation["equals"]], [0, 0])
        self.assertIn("max_character_count_exceeded", {issue.code for issue in report.issues})

    def test_tier_classification_distinguishes_outside_unknown_and_ambiguous(self):
        source, characters = _screenshot_scale_source()
        rules = AbyssRuleset.from_source(*source)
        zero = characters[-1]
        self.assertEqual(evaluate_deck(_deck(zero), rules).character_rows[0]["tier_status"], "outside")
        source[0]["costs"]["tiers"][0]["minCost"] = 0
        inside = evaluate_deck(_deck(zero), AbyssRuleset.from_source(*source)).character_rows[0]
        self.assertEqual((inside["tier"], inside["tier_status"]), (0, "known"))
        missing = _character(zero.character_id, "PYRO", level=None)
        self.assertEqual(evaluate_deck(_deck(missing), rules).character_rows[0]["tier_status"], "unknown")
        source[0]["costs"]["tiers"][1]["minCost"] = 0
        ambiguous = evaluate_deck(_deck(zero), AbyssRuleset.from_source(*source)).character_rows[0]
        self.assertEqual((ambiguous["tier"], ambiguous["tier_status"]), (None, "ambiguous"))
        source[0]["costs"]["tiers"] = []
        missing_bands = AbyssRuleset.from_source(*source)
        missing_report = evaluate_deck(_deck(zero), missing_bands)
        self.assertEqual(missing_report.character_rows[0]["tier_status"], "unknown")
        self.assertEqual(allocate_requirements(missing_report.character_rows, missing_bands.to_dict()["preset_rules"])["status"], "unknown")

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
        system, agents, engines = _source()
        system["costs"]["agents"][2]["specification"] = 0
        system["costs"]["agents"][3]["specification"] = 1
        agents.append({"_id": "f" * 24, "enkaId": "1003", "attribute": 12,
                       "name": {"en": "Unpriced Cryo"}})
        rules = AbyssRuleset.from_source(system, agents, engines)
        deck = _deck(_character("10000007", "DENDRO"), _character("1001", "PYRO"),
                     _character("1002", "HYDRO"), _character("missing", "CRYO"),
                     _character("1003", "CRYO"))
        report = evaluate_deck(deck, rules)
        self.assertEqual(report.character_rows[0]["source_id"], IDS["trav_dendro"])
        self.assertEqual(report.character_rows[0]["specification"], 1)
        self.assertIsNone(report.character_rows[3]["specification"])
        self.assertIsNone(report.character_rows[4]["specification"])
        codes = {issue.code for issue in report.issues}
        self.assertIn("max_character_count_exceeded", codes)
        self.assertIn("bound_maximum_exceeded", codes)
        self.assertIn("character_unmapped", codes)
        self.assertIsNone(report.character_total)
        ambiguous = evaluate_deck(_deck(_character("10000007", "")), rules)
        self.assertIn("character_variant_ambiguous", {issue.code for issue in ambiguous.issues})
        self.assertIsNone(ambiguous.character_rows[0]["specification"])
        self.assertIsNone(ambiguous.character_total)

    def test_evaluated_roles_follow_preset_dd_membership_and_rule_roles(self) -> None:
        system, agents, engines = _source()
        for row in system["costs"]["agents"]:
            row["specification"] = 0
        system["costs"]["agents"][0]["costs"][0] = 20
        rules = AbyssRuleset.from_source(system, agents, engines)
        snapshot = rules.to_dict()
        self.assertEqual({row["specification"] for row in snapshot["characters"]}, {0})
        self.assertEqual(snapshot["dd_character_ids"], ["1001"])

        deck = _deck(_character("1001", "PYRO", constellation=0),
                     _character("1002", "HYDRO", constellation=2))
        report = evaluate_deck(deck, rules)
        self.assertEqual(report.character_rows[0]["specification"], 0)
        self.assertEqual(report.character_rows[1]["specification"], 1)
        self.assertEqual(allocate_requirements(report.character_rows, snapshot["preset_rules"])["status"], "fail")

        support_rules = [dict(rule) for rule in snapshot["preset_rules"]]
        support_rules[0] = {**support_rules[0], "from": [{"tier": 1, "specification": 1}]}
        support_snapshot = {**snapshot, "preset_rules": support_rules}
        support_ruleset = AbyssRuleset.from_dict(support_snapshot)
        support_report = evaluate_deck(deck, support_ruleset)
        self.assertEqual(support_report.character_rows[1]["specification"], 1)
        self.assertEqual(allocate_requirements(support_report.character_rows, support_rules)["status"], "pass")

        self.assertEqual(report.bundle_candidates[0]["match"], "matched")

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
        french = AbyssRuleset.from_source(system, agents, engines)
        self.assertEqual(french.source["cost_system"], "FRENCH_COST")
        self.assertNotIn("cost_system", rules.source)
        self.assertEqual(AbyssRuleset.from_dict(french.to_dict()).content_hash, french.content_hash)
        system["costs"]["system"] = "UNKNOWN"
        with self.assertRaisesRegex(AbyssRulesError, "Unsupported Abyss cost mode"):
            AbyssRuleset.from_source(system, agents, engines)

    def test_snapshot_cost_mode_allowlist_and_french_cap(self) -> None:
        rules = AbyssRuleset.from_source(*_source())
        payload = rules.to_dict()
        payload["source"]["cost_system"] = "DEFAULT"
        self.assertEqual(AbyssRuleset.from_dict(payload).source["cost_system"], "DEFAULT")
        payload["source"]["cost_system"] = "FRENCH_COST"
        self.assertEqual(AbyssRuleset.from_dict(payload).source["cost_system"], "FRENCH_COST")
        payload["french_difference_cap"] = None
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)
        payload["french_difference_cap"] = 4
        payload["source"]["cost_system"] = "UNKNOWN"
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_dict(payload)

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
