"""Small synthetic boundary cases for the public-source research projection."""
import copy
import unittest
from unittest.mock import patch

from tools.experiments.pvp_site_audit.abyss_rules_source import fetch_source, normalize_source


class AbyssSourceTest(unittest.TestCase):
    def setUp(self):
        self.agents = [{"_id": "a", "enkaId": "10000002", "name": {"en": "Ayaka"}}]
        self.engines = [{"_id": "w", "enkaId": "11401", "title": {"en": "Sword"}}]
        self.system = {
            "_id": "a" * 24, "main": {"title": "Synthetic", "editors": ["private-owner"]},
            "costs": {"system": "DEFAULT", "costLimit": 0,
                      "agents": [{"agent": "a", "costs": [13, 14, 17, 19, 30, 31, 34, 4.79, 1]}],
                      "engines": [{"engine": "w", "costs": [1, 2, 3, 4, 5, 7],
                                   "bis": [{"agent": "a", "costs": [2, 3, 4, 5, 6, 8]}]}]},
            "draft": {"minMaxCosts": {"agents": [520, 0]}},
            "preset": {"rules": [{"type": "required_agents", "agents": ["a"]},
                                 {"type": "requires", "from": [{"agent": 1}], "to": 3}]},
        }

    def test_maps_game_ids_and_distinguishes_caps_without_executing_constraints(self):
        original = copy.deepcopy(self.system)
        result = normalize_source(self.system, self.agents, self.engines)
        self.assertFalse(result["execution_ready"])
        character = result["characters"][0]
        self.assertEqual(character["character_id"], "10000002")
        self.assertEqual(character["costs_by_constellation"]["6"], 34)
        self.assertEqual(character["level_adjustment"]["percent"], 4.79)
        self.assertEqual(result["weapons"][0]["costs_by_refinement"]["5"], 5)
        self.assertEqual(result["weapons"][0]["off_specialty_cost"], 7)
        self.assertEqual(result["weapons"][0]["character_overrides"][0]["character_id"], "10000002")
        self.assertEqual(result["preset_rules_with_game_ids"][0]["agents"][0]["character_id"], "10000002")
        self.assertEqual(result["preset_rules_with_game_ids"][1]["from"], [{"agent": 1}])
        self.assertEqual(result["french_difference_cap"], 0)
        self.assertEqual(result["draft_bounds_raw"]["minMaxCosts"]["agents"], [520, 0])
        self.assertNotIn("private-owner", str(result))
        self.assertEqual(self.system, original)

    def test_unknown_catalog_id_fails_instead_of_inventing_a_zero_price(self):
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            normalize_source(self.system, [], self.engines)

    def test_same_game_id_keeps_element_variants_and_required_reference_distinct(self):
        self.agents[0]["attribute"] = 13
        self.agents.append({"_id": "b", "enkaId": "10000002", "attribute": 17})
        self.system["costs"]["agents"].append({"agent": "b", "costs": [25] * 9})
        self.system["preset"]["rules"][0]["agents"] = ["b"]
        result = normalize_source(self.system, self.agents, self.engines)
        self.assertEqual(len(result["characters"]), 2)
        self.assertEqual([row["source_attribute"] for row in result["characters"]], [13, 17])
        self.assertEqual(result["preset_rules_with_game_ids"][0]["agents"][0]["source_attribute"], 17)
        self.agents[1]["attribute"] = 13
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalize_source(self.system, self.agents, self.engines)

    def test_changed_cost_slots_and_nonfinite_values_fail(self):
        for costs in ([1] * 8, [1] * 8 + [float("nan")], [True] * 9):
            with self.subTest(costs=costs), self.assertRaises(ValueError):
                self.system["costs"]["agents"][0]["costs"] = costs
                normalize_source(self.system, self.agents, self.engines)

    def test_pinned_version_and_id_validation(self):
        with patch("tools.experiments.pvp_site_audit.abyss_rules_source.get_public_json") as get:
            with self.assertRaises(ValueError):
                fetch_source("../other")
            get.assert_not_called()
            get.return_value = ({"_id": "b" * 24}, "hash")
            with self.assertRaisesRegex(ValueError, "version"):
                fetch_source("a" * 24)
            self.assertEqual(get.call_count, 1)
