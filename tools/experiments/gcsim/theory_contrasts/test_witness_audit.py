import copy
import unittest

from tools.experiments.gcsim.theory_contrasts.witness_audit import (
    SLOTS,
    STAT_KEYS,
    SUBSTAT_VALUES,
    audit_records,
)


def valid_state():
    mains = []
    lines = []
    upgrades = []
    for _actor in range(4):
        actor_mains = ["hp", "atk", "atk_percent", "hydro_damage_bonus", "crit_rate"]
        actor_lines = []
        actor_upgrades = []
        for slot, main in zip(SLOTS, actor_mains):
            eligible = [index for index, key in enumerate(STAT_KEYS) if key != main]
            actor_lines.append(eligible[:4])
            actor_upgrades.append([5.0, 0.0, 0.0, 0.0])
        mains.append(actor_mains)
        lines.append(actor_lines)
        upgrades.append(actor_upgrades)
    return {"Mains": mains, "Lines": lines, "Upgrades": upgrades}


def candidate(state=None, package_rows=None):
    state = copy.deepcopy(state if state is not None else valid_state())
    wearer_keys = ["alpha", "beta", "gamma", "delta"]
    if package_rows is None:
        package_rows = [
            {"sets": []},
            {"sets": [{"set_uid": "set-two", "count": 2}]},
            {"sets": [{"set_uid": "set-four", "count": 4}]},
            {"sets": [{"set_uid": "set-a", "count": 2}, {"set_uid": "set-b", "count": 2}]},
        ]
    packages = []
    allocations = []
    for actor, wearer in enumerate(wearer_keys):
        packages.append({"wearer_key": wearer, **copy.deepcopy(package_rows[actor])})
        main_stats = {slot: state["Mains"][actor][i] for i, slot in enumerate(SLOTS)}
        rolls = [0.0] * len(STAT_KEYS)
        for slot in range(5):
            for line, stat in enumerate(state["Lines"][actor][slot]):
                rolls[stat] += 1 + state["Upgrades"][actor][slot][line]
        allocations.append(
            {
                "wearer_key": wearer,
                "main_stats": main_stats,
                "spent_roll_units": 45,
                "unspent_roll_units": 0,
                "substats": [
                    {
                        "stat_key": key,
                        "roll_units": rolls[index],
                        "stat_value": rolls[index] * SUBSTAT_VALUES[key],
                    }
                    for index, key in enumerate(STAT_KEYS)
                ],
            }
        )
    return {
        "feasibility_witness": state,
        "formula_dps": 12345.0,
        "formula_family": "program:test",
        "allocations": allocations,
        "packages": packages,
    }


class WitnessAuditTests(unittest.TestCase):
    def test_recurses_best_top_witness_and_standalone_start(self):
        first = candidate()
        second = copy.deepcopy(first)
        second["packages"][0] = {"wearer_key": "alpha", "sets": [{"set_uid": "x", "count": 4}]}
        result = audit_records(
            [{"best": first, "top_witnesses": [copy.deepcopy(first), second], "start": valid_state()}]
        )
        self.assertEqual(result["occurrences"], 3)
        self.assertEqual(result["distinct_states"], 1)
        self.assertEqual(result["distinct_signatures"], 2)
        self.assertEqual(result["standalone_state_occurrences"], 1)
        self.assertEqual(result["package_profile_rows"], {"none": 2, "2p": 3, "4p": 4, "2+2": 3})
        self.assertEqual(result["package_rarity"], "unknown")
        self.assertFalse(result["package_rarity_inferred"])

    def test_rejects_illegal_main_and_upgrade_domain(self):
        bad_main = valid_state()
        bad_main["Mains"][0][0] = "atk"
        with self.assertRaisesRegex(ValueError, "illegal flower main"):
            audit_records([{"candidate": candidate(bad_main)}])

        bad_upgrade = valid_state()
        bad_upgrade["Upgrades"][0][0][0] = 5.25
        with self.assertRaisesRegex(ValueError, "exceeds five"):
            audit_records([{"candidate": candidate(bad_upgrade)}])

    def test_rejects_export_mismatch_and_bad_package_counts(self):
        bad_export = candidate()
        bad_export["allocations"][0]["substats"][0]["roll_units"] += 0.25
        with self.assertRaisesRegex(ValueError, "roll_units differ"):
            audit_records([{"candidate": bad_export}])

        bad_value = candidate()
        bad_value["allocations"][0]["substats"][0]["stat_value"] += 0.01
        with self.assertRaisesRegex(ValueError, "stat_value differ"):
            audit_records([{"candidate": bad_value}])

        bad_package = candidate()
        bad_package["packages"][0]["sets"] = [{"set_uid": "bad", "count": 3}]
        with self.assertRaisesRegex(ValueError, "count must be 2 or 4"):
            audit_records([{"candidate": bad_package}])

        noninteger_count = candidate()
        noninteger_count["packages"][0]["sets"] = [{"set_uid": "bad", "count": 2.0}]
        with self.assertRaisesRegex(ValueError, "count must be 2 or 4"):
            audit_records([{"candidate": noninteger_count}])

    def test_requires_exact_45_unit_budget(self):
        too_few = valid_state()
        too_few["Upgrades"][0][0][0] = 4.75
        with self.assertRaisesRegex(ValueError, "expected 45"):
            audit_records([{"start": too_few}])

    def test_rejects_nonzero_exported_unspent_rolls(self):
        bad_export = candidate()
        bad_export["allocations"][2]["unspent_roll_units"] = 0.25
        with self.assertRaisesRegex(ValueError, "zero unspent roll units"):
            audit_records([{"candidate": bad_export}])

    def test_fails_closed_on_candidate_without_witness(self):
        broken = candidate()
        del broken["feasibility_witness"]
        with self.assertRaisesRegex(ValueError, "missing feasibility_witness"):
            audit_records([{"best": broken}])

        nonfinite = candidate()
        nonfinite["formula_dps"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite number"):
            audit_records([{"candidate": nonfinite}])

    def test_validates_standalone_state_and_wearer_order(self):
        invalid_start = valid_state()
        invalid_start["Upgrades"][0][0][0] = 1.125
        with self.assertRaisesRegex(ValueError, "off-quarter"):
            audit_records([{"start": invalid_start}])

        wrong_order = candidate()
        wrong_order["packages"][0]["wearer_key"] = "beta"
        with self.assertRaisesRegex(ValueError, "wearer order differs"):
            audit_records([{"candidate": wrong_order}])


if __name__ == "__main__":
    unittest.main()
