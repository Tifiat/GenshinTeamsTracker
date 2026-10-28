from __future__ import annotations

import csv
import io
import json
import unittest
from copy import deepcopy

from run_workspace.gcsim.optimizer_go_requests import GcsimOptimizerGoError
from tools.experiments.gcsim.theory_full_output.table import (
    STAT_KEYS,
    build_theory_full_output,
    render_theory_full_output,
)


WEARERS = ("w1", "w2", "w3", "w4")
MAINS = ("hp", "atk", "em", "hydro_damage_bonus", "healing_bonus")
LINES = (
    (0, 1, 2, 3),
    (1, 2, 3, 5),
    (0, 2, 3, 4),
    (0, 1, 2, 3),
    (0, 1, 2, 3),
)


def _packages(first_set: str, *, second_actor_set: str = "set-b") -> list[dict]:
    return [
        {"wearer_key": "w1", "sets": [{"set_uid": first_set, "count": 4}]},
        {"wearer_key": "w2", "sets": [
            {"set_uid": second_actor_set, "count": 2},
            {"set_uid": "set-c", "count": 2},
        ]},
        {"wearer_key": "w3", "sets": [{"set_uid": "set-d", "count": 4}]},
        {"wearer_key": "w4", "sets": [{"set_uid": "set-e", "count": 2}]},
    ]


def _actor_witness(*, shifted_crit_upgrade: bool = False) -> tuple[dict, dict]:
    upgrades_by_slot = (
        [0, 0, 0, 5] if shifted_crit_upgrade else [5, 0, 0, 0],
        [5, 0, 0, 0],
        [5, 0, 0, 0],
        [5, 0, 0, 0],
        [5, 0, 0, 0] if shifted_crit_upgrade else [0, 0, 0, 5],
    )
    actor_witness = {
        "Mains": list(MAINS),
        "Lines": [list(lines) for lines in LINES],
        "Upgrades": [list(upgrades) for upgrades in upgrades_by_slot],
    }
    roll_units = [0.0] * len(STAT_KEYS)
    for lines, upgrades in zip(LINES, upgrades_by_slot):
        for stat_index, upgrade in zip(lines, upgrades):
            roll_units[stat_index] += 1 + upgrade
    allocation = {
        "wearer_key": "",
        "main_stats": dict(zip(("flower", "plume", "sands", "goblet", "circlet"), MAINS)),
        "substats": [
            {"stat_key": stat_key, "roll_units": units, "stat_value": units}
            for stat_key, units in zip(STAT_KEYS, roll_units)
        ],
        "spent_roll_units": 45,
        "unspent_roll_units": 0,
    }
    return actor_witness, allocation


def _family(family_id: str, aliases: list[dict], *, shifted_crit_upgrade: bool = False) -> dict:
    actor_witness, actor_allocation = _actor_witness(shifted_crit_upgrade=shifted_crit_upgrade)
    allocations = []
    mains = []
    lines = []
    upgrades = []
    for wearer in WEARERS:
        allocation = deepcopy(actor_allocation)
        allocation["wearer_key"] = wearer
        allocations.append(allocation)
        mains.append(list(actor_witness["Mains"]))
        lines.append(deepcopy(actor_witness["Lines"]))
        upgrades.append(deepcopy(actor_witness["Upgrades"]))
    row = {
        "family": family_id,
        "formula_dps": 1234.5 if family_id == "family-co" else 1200.0,
        "deficit_percent": 0.0 if family_id == "family-co" else 2.8,
        "refinement_level": 0,
        "allocations": allocations,
        "witness45": {"Mains": mains, "Lines": lines, "Upgrades": upgrades},
        "aliases": aliases,
    }
    if family_id == "family-pending":
        row["reason"] = "refinement_limit"
    return row


def _alias(tuple_key: str, context_char: str, packages: list[dict]) -> dict:
    return {
        "tuple_key": tuple_key,
        "context_sha256": context_char * 64,
        "uncertainty": ["source operand is bounded"],
        "packages": packages,
    }


def make_snapshot() -> dict:
    co_aliases = [
        _alias("tuple-1", "a", _packages("set-a")),
        _alias("tuple-2", "b", _packages("set-x", second_actor_set="set-b")),
    ]
    pending_aliases = [_alias("tuple-3", "c", _packages("set-a"))]
    unavailable = [{
        "tuple_key": "tuple-4",
        "reasons": ["source tuple unavailable"],
        "packages": _packages("set-unavailable"),
    }]
    return {
        "schema_version": 2,
        "schema_kind": "gtt_gcsim_optimizer_theory_result_v2",
        "status": "success",
        "request_sha256": "1" * 64,
        "session_id": "session-1",
        "snapshot_version": 3,
        "phase": "deep_baseline",
        "reference_score": 1234.5,
        "practical_band_percent": 3,
        "sensitivity_band_percent": 2,
        "co_leaders": [_family("family-co", co_aliases)],
        "pending": [_family("family-pending", pending_aliases, shifted_crit_upgrade=True)],
        "unavailable": unavailable,
        "total_found_families": 2,
        "total_found_tuples": 3,
        "found_group_families": 1,
        "found_group_tuples": 2,
        "sensitivity_group_families": 1,
        "sensitivity_group_tuples": 1,
        "domain_tuples": "4",
        "unseen_tuples": "0",
        "full_cartesian_covered": True,
    }


def build(snapshot: dict | None = None) -> dict:
    return build_theory_full_output(
        snapshot or make_snapshot(),
        team_key="theory_fixture",
        wearer_names={"w1": "Alpha", "w2": "Beta", "w3": "Gamma", "w4": "Delta"},
        set_names={"set-a": "Localized A", "set-b": "Localized B"},
        public_context={
            "energy_mode": "infinite",
            "prediction_status": "unverified",
            "proc_facts": {"status": "unknown", "reason": "no bound source facts"},
        },
    )


class TheoryFullOutputTableTests(unittest.TestCase):
    def test_noncrit_upgrade_counts_come_from_full45_upgrades(self) -> None:
        snapshot = make_snapshot()
        report = build(snapshot)
        first_combo = next(row for row in report["combinations"] if row["tuple_key"] == "tuple-1")
        actor = first_combo["actors"][0]

        for source_allocation, actor_projection in zip(
            snapshot["co_leaders"][0]["allocations"], first_combo["actors"]
        ):
            self.assertEqual(actor_projection["initial_line_units"], 20)
            self.assertEqual(actor_projection["total_upgrade_units"], 25)
            self.assertEqual(actor_projection["total_roll_units"], 45)
            self.assertEqual(sum(stat["roll_units"] for stat in source_allocation["substats"]), 45)

        self.assertEqual(actor["total_upgrade_units"], 25)
        self.assertEqual(actor["initial_line_units"], 20)
        self.assertEqual(actor["total_roll_units"], 45)
        self.assertEqual(actor["noncrit_upgrade_units"], 20)
        self.assertEqual(actor["noncrit_upgrade_by_stat"], {"atk": 15, "atk_percent": 5})
        self.assertNotIn("crit_rate", actor["noncrit_upgrade_by_stat"])
        self.assertNotIn("crit_damage", actor["noncrit_upgrade_by_stat"])
        self.assertEqual(actor["table_mains"], {
            "sands": "em", "goblet": "hydro_damage_bonus", "circlet": "healing_bonus",
        })
        self.assertEqual(snapshot["co_leaders"][0]["allocations"][0]["spent_roll_units"], 45)

    def test_aliases_keep_whole_tuple_membership_without_cartesian_expansion(self) -> None:
        report = build()
        self.assertEqual(len(report["combinations"]), 3)
        self.assertEqual(len({row["combination_id"] for row in report["combinations"]}), 3)
        self.assertEqual(len(report["actor_rows"]), 12)

        co_family = report["families"][0]
        co_combinations = [row for row in report["combinations"] if row["publication_state"] == "co_leader"]
        self.assertEqual(co_family["combination_ids"], [row["combination_id"] for row in co_combinations])
        self.assertTrue(all(row["co_leader_band"] is True for row in co_combinations))
        self.assertTrue(all(row["co_leader_band"] is None for row in report["combinations"] if row["publication_state"] == "pending"))

        by_tuple = {row["tuple_key"]: row for row in report["combinations"]}
        self.assertEqual(by_tuple["tuple-1"]["packages"][0]["sets"], [{"set_uid": "set-a", "count": 4}])
        self.assertEqual(by_tuple["tuple-2"]["packages"][0]["sets"], [{"set_uid": "set-x", "count": 4}])
        self.assertEqual(by_tuple["tuple-1"]["actors"][1]["package"]["sets"], [
            {"set_uid": "set-b", "count": 2}, {"set_uid": "set-c", "count": 2},
        ])
        self.assertNotEqual(by_tuple["tuple-1"]["combination_id"], by_tuple["tuple-2"]["combination_id"])

        w1_options = [row for row in report["grouped_options"] if row["wearer_key"] == "w1"]
        set_a = next(row for row in w1_options if row["sets"] == [{"set_uid": "set-a", "count": 4}])
        self.assertEqual(set(set_a["combination_ids"]), {
            by_tuple["tuple-1"]["combination_id"],
            by_tuple["tuple-3"]["combination_id"],
        })
        self.assertEqual(report["summary"]["pending_combinations"], 1)
        self.assertEqual(report["summary"]["unavailable_combinations"], 1)
        self.assertEqual(report["summary"]["unseen_tuples"], "0")

    def test_aliases_share_witness_hash_and_distinct_witness_has_distinct_id(self) -> None:
        report = build()
        by_tuple = {row["tuple_key"]: row for row in report["combinations"]}
        self.assertEqual(by_tuple["tuple-1"]["witness_id"], by_tuple["tuple-2"]["witness_id"])
        self.assertNotEqual(by_tuple["tuple-1"]["witness_id"], by_tuple["tuple-3"]["witness_id"])
        self.assertEqual(by_tuple["tuple-1"]["family_formula_dps"], 1234.5)
        self.assertEqual(by_tuple["tuple-1"]["family_deficit_percent"], 0.0)
        self.assertEqual(by_tuple["tuple-1"]["context_sha256"], "a" * 64)
        self.assertEqual(by_tuple["tuple-1"]["uncertainty"], ["source operand is bounded"])

    def test_json_csv_and_grouped_membership_round_trip_counts(self) -> None:
        report = build()
        artifacts = render_theory_full_output(report)
        decoded = json.loads(artifacts["json"])
        self.assertEqual(decoded["roundtrip_counts"], report["roundtrip_counts"])
        self.assertEqual(decoded["source_snapshot"], report["source_snapshot"])
        self.assertEqual(decoded["summary"]["energy_mode"], "infinite")
        self.assertEqual(decoded["summary"]["prediction_status"], "unverified")
        self.assertIn("proc-факты", artifacts["summary_ru"])
        self.assertIn("неизвестны", artifacts["summary_ru"])
        self.assertIn("не является подтверждённым DPS GCSim", artifacts["summary_ru"])

        csv_rows = list(csv.DictReader(io.StringIO(artifacts["csv"])))
        self.assertEqual(len(csv_rows), len(report["actor_rows"]) + len(report["unavailable_actor_rows"]))
        for combo_id in {row["combination_id"] for row in csv_rows}:
            combo_rows = [row for row in csv_rows if row["combination_id"] == combo_id]
            self.assertEqual(len(combo_rows), 4)
            for row in combo_rows:
                self.assertEqual(len(json.loads(row["packages_json"])), 4)
        grouped = list(csv.DictReader(io.StringIO(artifacts["grouped_options_tsv"]), delimiter="\t"))
        self.assertEqual(len(grouped), len(report["grouped_options"]))
        known_combo_ids = {row["combination_id"] for row in report["combinations"]}
        for row in grouped:
            self.assertTrue(set(json.loads(row["combination_ids_json"])).issubset(known_combo_ids))

    def test_missing_proc_context_is_reported_as_unknown(self) -> None:
        report = build_theory_full_output(
            make_snapshot(),
            team_key="theory_fixture",
            wearer_names={},
            public_context={"energy_mode": "infinite"},
        )
        self.assertIsNone(report["summary"]["proc_facts"])
        self.assertEqual(report["summary"]["prediction_status"], "unverified")
        self.assertIn("proc-факты: неизвестны", report["summary_ru"])
        self.assertEqual(report["combinations"][0]["actors"][0]["wearer_name"], "w1")

    def test_identity_mutations_are_rejected_by_existing_snapshot_transport(self) -> None:
        base = make_snapshot()
        mutations = []

        bad_schema = deepcopy(base)
        bad_schema["schema_version"] = 3
        mutations.append(("schema", bad_schema))

        owner_lost = deepcopy(base)
        owner_lost["co_leaders"][0]["aliases"][0]["packages"][0]["wearer_key"] = "missing"
        mutations.append(("owner_lost", owner_lost))

        owner_duplicated = deepcopy(base)
        owner_duplicated["co_leaders"][0]["aliases"][0]["packages"][1]["wearer_key"] = "w1"
        mutations.append(("owner_duplicated", owner_duplicated))

        mains_mismatch = deepcopy(base)
        mains_mismatch["co_leaders"][0]["witness45"]["Mains"][0][2] = "atk"
        mutations.append(("mains", mains_mismatch))

        duplicate_line = deepcopy(base)
        duplicate_line["co_leaders"][0]["witness45"]["Lines"][0][0] = [0, 0, 2, 3]
        mutations.append(("lines", duplicate_line))

        off_quarter = deepcopy(base)
        off_quarter["co_leaders"][0]["witness45"]["Upgrades"][0][0][0] = 0.1
        mutations.append(("upgrades", off_quarter))

        roll_mismatch = deepcopy(base)
        roll_mismatch["co_leaders"][0]["allocations"][0]["substats"][0]["roll_units"] += 0.25
        mutations.append(("allocation_projection", roll_mismatch))

        duplicate_tuple = deepcopy(base)
        duplicate_tuple["co_leaders"][0]["aliases"][1]["tuple_key"] = "tuple-1"
        mutations.append(("duplicate_alias", duplicate_tuple))

        for label, mutated in mutations:
            with self.subTest(label=label), self.assertRaises(GcsimOptimizerGoError):
                build(mutated)

    def test_ids_are_stable_and_caller_snapshot_is_not_mutated(self) -> None:
        snapshot = make_snapshot()
        before = deepcopy(snapshot)
        first = build(snapshot)
        second = build(snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(
            [row["combination_id"] for row in first["combinations"]],
            [row["combination_id"] for row in second["combinations"]],
        )
        self.assertEqual(first["source_snapshot_sha256"], second["source_snapshot_sha256"])


if __name__ == "__main__":
    unittest.main()
