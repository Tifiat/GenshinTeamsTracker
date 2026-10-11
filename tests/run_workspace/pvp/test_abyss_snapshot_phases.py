"""The optional execution projection never rewrites older deck snapshots."""
import hashlib
import json
import unittest

from run_workspace.pvp.abyss_rules import AbyssRulesError, AbyssRuleset
from tests.run_workspace.pvp.test_abyss_rules import IDS, _source


def source_with_phases():
    system, agents, engines = _source()
    system["phasePicks"] = {
        "flow": [{"type": "IMMUNE_BAN", "player": "player0"},
                 {"type": "PICK", "player": "player1"}],
        "absoluteImmune": [IDS["a"]], "prebanCostStep": 60,
        "pickTime": 60000, "reserveTime": 300000,
    }
    system["phaseTeams"] = {"maxEnginesCost": 500, "maxEnginesCostStep": 500,
                            "unrelatedSourceField": "not retained"}
    system["phaseMatch"] = {"freeRestarts": 3, "paidRestarts": [5, 5, 10]}
    return system, agents, engines


class AbyssSnapshotPhasesTest(unittest.TestCase):
    def test_old_snapshot_hash_and_shape_remain_exact(self):
        original = AbyssRuleset.from_source(*_source())
        data = original.to_dict()
        expected = hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True,
                                            separators=(",", ":")).encode("ascii")).hexdigest()
        self.assertNotIn("phase_picks", data)
        self.assertEqual(AbyssRuleset.from_dict(data).content_hash, expected)
        self.assertEqual(AbyssRuleset.from_dict(data).to_dict(), data)

    def test_fresh_source_projects_bounded_phases(self):
        rules = AbyssRuleset.from_source(*source_with_phases())
        data = rules.to_dict()
        self.assertEqual(data["phase_picks"]["absolute_immune"], [IDS["a"]])
        self.assertEqual(data["phase_picks"]["flow"][0], {"type": "IMMUNE_BAN", "player": "player0"})
        self.assertEqual(data["phase_teams"], {"max_engines_cost": 500, "max_engines_cost_step": 500})
        self.assertEqual(AbyssRuleset.from_dict(data).content_hash, rules.content_hash)

    def test_specialties_are_optional_and_bounded(self):
        system, agents, engines = source_with_phases()
        agents[0]["specialty"] = 5
        engines[0]["specialty"] = 5
        data = AbyssRuleset.from_source(system, agents, engines).to_dict()
        self.assertEqual(data["characters"][0]["specialty"], 5)
        self.assertEqual(data["weapons"][0]["specialty"], 5)
        self.assertNotIn("specialty", data["characters"][1])
        for bad in (0, 6, True, "5", None):
            with self.subTest(bad=bad):
                data["weapons"][0]["specialty"] = bad
                with self.assertRaises(AbyssRulesError):
                    AbyssRuleset.from_dict(data)

    def test_untrusted_bad_phases_are_rejected(self):
        mutations = (
            lambda data: data["phase_picks"]["flow"][0].update(type="UNKNOWN"),
            lambda data: data["phase_picks"]["flow"][0].update(type=[]),
            lambda data: data["phase_picks"]["flow"][0].update(player="player2"),
            lambda data: data["phase_picks"].update(pick_time=-1),
            lambda data: data["phase_picks"].update(absolute_immune=["f" * 24]),
            lambda data: data["phase_picks"].update(absolute_immune=[{}]),
            lambda data: data["phase_picks"].update(absolute_immune=[IDS["a"]] * 2),
            lambda data: data["phase_teams"].update(max_engines_cost=True),
            lambda data: data["phase_teams"].update(max_engines_cost_step=-1),
            lambda data: data["phase_teams"].update(extra=1),
            lambda data: data["phase_match"].update(paid_restarts=[-1]),
            lambda data: data["phase_match"].update(free_restarts=True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = AbyssRuleset.from_source(*source_with_phases()).to_dict()
                mutate(data)
                with self.assertRaises(AbyssRulesError):
                    AbyssRuleset.from_dict(data)


if __name__ == "__main__":
    unittest.main()
