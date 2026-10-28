import unittest

from tools.experiments.gcsim.all_sets_inventory_regression.report import (
    render_report,
    render_top_three_builds,
)


def request_artifact(artifact_id, slot, main_key, main_value, substats):
    return {
        "artifact_id": artifact_id,
        "slot": slot,
        "set_uid": "gladiators_finale",
        "rarity": 5,
        "level": 20,
        "main_stat": {"key": main_key, "value": main_value},
        "substats": [
            {"key": key, "value": value} for key, value in substats
        ],
    }


def candidate(rank, dps, artifact_ids):
    return {
        "rank": rank,
        "measured": {"dps": str(dps), "standard_error": "1.0"},
        "builds": [
            {
                "wearer_key": "gaming",
                "artifact_ids": artifact_ids,
                "main_stats": {
                    "sands": "АТК 46,6%",
                    "goblet": "Пиро 46,6%",
                    "circlet": "КШ 31,1%",
                },
                "sets": [{"name": "Gladiator's Finale", "count": 4}],
            }
        ],
    }


def product(dps):
    return {"candidates": [{"rank": 1, "measured": {"dps": str(dps), "standard_error": "1.0"}, "builds": []}]}


class PlayerBuildReportTests(unittest.TestCase):
    def test_top_three_uses_frozen_request_rows_and_shows_only_rank_changes(self):
        top_one_ids = {
            "flower": 101,
            "plume": 102,
            "sands": 103,
            "goblet": 104,
            "circlet": 105,
        }
        top_two_ids = {**top_one_ids, "goblet": 204}
        top_three_ids = {**top_one_ids, "circlet": 205}
        request_rows = [
            request_artifact(101, "flower", "hp", "4780", [("atk_percent", "0.0466"), ("crit_rate", "0.0311")]),
            request_artifact(102, "plume", "atk", "311", [("crit_damage", "0.0622")]),
            request_artifact(103, "sands", "atk_percent", "0.466", [("em", "23.31")]),
            request_artifact(104, "goblet", "pyro_damage_bonus", "0.466", [("crit_rate", "0.0311")]),
            request_artifact(105, "circlet", "crit_rate", "0.311", [("atk_percent", "0.0466")]),
            request_artifact(204, "goblet", "hydro_damage_bonus", "0.466", [("crit_damage", "0.0622")]),
            request_artifact(205, "circlet", "crit_damage", "0.622", [("energy_recharge", "0.0583")]),
        ]
        row = {
            "product": {
                "candidates": [
                    candidate(1, 1000, top_one_ids),
                    candidate(2, 990, top_two_ids),
                    candidate(3, 980, top_three_ids),
                ]
            },
            "inventory_search": {"finalist_artifact_rows": request_rows},
        }

        rendered = "\n".join(render_top_three_builds(row))
        top_two = rendered.split("Топ-2 —", 1)[1].split("Топ-3 —", 1)[0]
        top_three = rendered.split("Топ-3 —", 1)[1]

        self.assertIn("Топ-1 — 1000,0 DPS", rendered)
        self.assertIn("| gaming | Цветок | 101 | HP 4780 | АТК 4,7%, КШ 3,1% |", rendered)
        self.assertIn("Топ-2 — 990,0 DPS", rendered)
        self.assertIn("Кубок", top_two)
        self.assertIn("#104", top_two)
        self.assertIn("#204", top_two)
        self.assertNotIn("Цветок", top_two)
        self.assertIn("Топ-3 — 980,0 DPS", rendered)
        self.assertIn("Корона", top_three)
        self.assertIn("#105", top_three)
        self.assertIn("#205", top_three)
        self.assertNotIn("Кубок", top_three)

    def test_missing_frozen_request_rows_omits_top_three_section(self):
        row = {"product": {"candidates": [candidate(1, 1000, {"flower": 101})]}}

        self.assertEqual(render_top_three_builds(row), [])

    def test_report_separates_retained_success_from_latest_consumer_and_defers_gaming(self):
        ids = [
            "gaming_melt_all_sets",
            "lunar_crystallize_all_sets",
            "lunar_charged_all_sets",
            "lunar_bloom_all_sets",
            "bountiful_core_all_sets",
            "chiori_lunar_crystallize_all_sets",
            "spread_all_sets",
            "aggravate_all_sets",
            "vaporize_all_sets",
            "burgeon_all_sets",
            "burning_all_sets",
            "physical_all_sets",
            "other_one_all_sets",
            "other_two_all_sets",
        ]
        before = {
            "runs": [
                {
                    "id": case_id,
                    "mode": "all_sets",
                    "product": product(100),
                    "engine_identity": "same-engine",
                }
                for case_id in ids
            ]
        }
        after = {
            "matrix_status": "row_complete_awaiting_parent_review",
            "runs": [
                {
                    "id": case_id,
                    "success": True,
                    "product": product(110),
                    "engine_identity": "same-engine",
                    "optimizer_sha256": "old-consumer",
                    "attempt": 1,
                    "inventory_search": {},
                }
                for case_id in ids[:5]
            ]
            + [
                {
                    "id": "chiori_lunar_crystallize_all_sets",
                    "success": True,
                    "product": {
                        **product(120),
                        "warnings": ["opaque_formula_boundaries_present"],
                    },
                    "engine_identity": "same-engine",
                    "optimizer_sha256": "latest-consumer",
                    "attempt": 2,
                    "inventory_search": {},
                }
            ],
        }

        rendered = render_report(before, after)

        self.assertIn("Successful retained non-Gaming rows: 5/13", rendered)
        self.assertIn("Latest consumer SHA `latest-consumer` appears on 1/13 non-Gaming row receipts", rendered)
        self.assertIn("not a same-input or accuracy certificate", rendered)
        self.assertIn("Gaming is historical/deferred, not accepted by this continuation.", rendered)
        self.assertIn("historical/deferred", rendered)
        self.assertIn("earlier matrix receipt; not rerun in this continuation", rendered)
        self.assertIn("opaque_formula_boundaries_present", rendered)


if __name__ == "__main__":
    unittest.main()
