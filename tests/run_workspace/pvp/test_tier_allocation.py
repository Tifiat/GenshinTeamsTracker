from __future__ import annotations

import unittest

from run_workspace.pvp.tier_allocation import allocate_requirements


def row(index: int, tier: int, role: int = 0, cost: int = 10, cid: str | None = None) -> dict:
    return {"index": index, "character_id": cid or f"{index:04d}",
            "source_id": f"source-{index}", "cost": cost, "tier": tier,
            "specification": role}


def requires(to: int, *slots: tuple[int, int | None]) -> dict:
    return {"type": "requires", "to": to,
            "from": [{"tier": tier, **({"specification": role} if role is not None else {})}
                     for tier, role in slots]}


def equals(to: int, cost: int, *slots: tuple[int, int | None]) -> dict:
    return {"type": "equals", "to": to, "from_cost": cost,
            "from": [{"tier": tier, **({"specification": role} if role is not None else {})}
                     for tier, role in slots]}


class TierAllocationTests(unittest.TestCase):
    def test_t4_t3_share_t1_without_reuse(self) -> None:
        rules = [requires(4, (1, 0), (1, None)), requires(3, (1, None))]
        rows = [row(0, 4), row(1, 3), row(2, 1, 0), row(3, 1, 1)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(sum(r["covered"] for r in result["rules"]), 1)
        allocated = [member for rule in result["rules"] for assignment in rule["assignments"]
                     for slot in assignment["slots"] if slot for member in slot["member_indexes"]]
        self.assertEqual(len(allocated), len(set(allocated)))
        self.assertTrue(result["complete"])

    def test_dd_scarcity_is_not_total_t1_count(self) -> None:
        rules = [requires(4, (1, 0), (1, None))]
        rows = [row(0, 4), row(1, 1, 1), row(2, 1, 1)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["rules"][0]["slots"][0]["filled"], 0)
        self.assertEqual(result["rules"][0]["slots"][1]["filled"], 1)

    def test_equals_threshold_and_distinct_members(self) -> None:
        rules = [requires(4, (1, None)), equals(1, 12, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 0, cost=7), row(2, 0, cost=5)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["groups"], [[1, 2]])
        rows[2]["cost"] = 4
        self.assertEqual(allocate_requirements(rows, rules)["status"], "fail")

    def test_decimal_equals_threshold(self) -> None:
        rules = [requires(4, (1, None)), equals(1, 0.8, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 0, cost=0.1), row(2, 0, cost=0.7)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["rules"][0]["assignments"][0]["slots"][0]["cost"], 0.8)

    def test_nongreedy_equals_competes_with_direct_t0(self) -> None:
        rules = [requires(4, (1, None)), requires(2, (0, None)),
                 equals(1, 10, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 2), row(2, 1), row(3, 0, cost=5), row(4, 0, cost=5)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["used"], 0)
        self.assertEqual([r["covered"] for r in result["rules"]], [1, 1])

    def test_backtracks_from_direct_to_equals_for_full_coverage(self) -> None:
        rules = [requires(4, (1, None)), requires(3, (1, 0)),
                 equals(1, 10, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 3), row(2, 1, 0),
                row(3, 0, cost=5), row(4, 0, cost=5)]
        result = allocate_requirements(rows, rules, equivalents_any_role=False)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["used"], 1)
        self.assertEqual(result["rules"][0]["assignments"][0]["slots"][0]["member_indexes"], [3, 4])
        self.assertEqual(result["rules"][1]["assignments"][0]["slots"][0]["member_indexes"], [2])

    def test_equals_can_rescue_high_tier_but_t0_is_global(self) -> None:
        rules = [requires(4, (1, None)), requires(2, (0, None)),
                 equals(1, 10, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 2), row(2, 0, cost=5), row(3, 0, cost=5)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(sum(r["covered"] for r in result["rules"]), 1)
        self.assertEqual(sum(r["slots"][0]["filled"] for r in result["rules"]), 1)

    def test_role0_and_role1_partial_counts(self) -> None:
        rules = [requires(4, (1, 0), (1, 1))]
        rows = [row(0, 4), row(1, 1, 0)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual([s["filled"] for s in result["rules"][0]["slots"]], [1, 0])

    def test_equals_role_policy(self) -> None:
        rules = [requires(4, (1, 0)), equals(1, 10, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 0, cost=5), row(2, 0, cost=5)]
        self.assertEqual(allocate_requirements(rows, rules)["status"], "pass")
        self.assertEqual(allocate_requirements(rows, rules, equivalents_any_role=False)["status"], "fail")

    def test_reorder_keeps_feasibility_and_canonical_target_priority(self) -> None:
        rules = [requires(4, (1, None))]
        rows = [row(0, 4, cid="z"), row(1, 4, cid="a"), row(2, 1, cid="b")]
        first = allocate_requirements(rows, rules)
        reordered = [dict(r, index=10 + i) for i, r in enumerate(reversed(rows))]
        second = allocate_requirements(reordered, rules)
        self.assertEqual((first["status"], second["status"]), ("fail", "fail"))
        first_winner = next(r["character_id"] for r in rows if any(
            a["target_index"] == r["index"] and a["complete"] for a in first["rules"][0]["assignments"]))
        second_winner = next(r["character_id"] for r in reordered if any(
            a["target_index"] == r["index"] and a["complete"] for a in second["rules"][0]["assignments"]))
        self.assertEqual((first_winner, second_winner), ("a", "a"))

    def test_budget_and_unknown_data_are_not_false_fail(self) -> None:
        rules = [requires(4, (1, None))]
        rows = [row(0, 4), row(1, 1)]
        budget_rows = [row(0, 4), row(1, 0, cost=5), row(2, 0, cost=5)]
        budget_rules = rules + [equals(1, 10, (0, None), (0, None))]
        budget_result = allocate_requirements(budget_rows, budget_rules, max_states=1)
        self.assertEqual(budget_result["status"], "unknown")
        self.assertEqual(budget_result["reason"], "budget")
        self.assertEqual(budget_result["complete"], False)
        rows[1]["cost"] = None
        self.assertEqual(allocate_requirements(rows, rules)["status"], "unknown")
        rows[1]["cost"] = 10
        rows[1]["specification"] = None
        self.assertEqual(allocate_requirements(rows, [requires(4, (1, 0))])["status"], "unknown")

    def test_option_budget_and_78_card_deck(self) -> None:
        rules = [requires(4, (1, None)), equals(1, 105, (0, None), (0, None))]
        rows = [row(0, 4)] + [row(i, 0, cost=5) for i in range(1, 78)]
        rows[-1]["cost"] = 100
        self.assertEqual(allocate_requirements(rows, rules, max_options=30)["status"], "unknown")
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["used"], 1)

    def test_truncated_four_member_groups_can_still_prove_pass(self) -> None:
        rules = [requires(4, (1, None)), equals(1, 20, *((0, None),) * 4)]
        rows = [row(0, 4)] + [row(i, 0, cost=5) for i in range(1, 80)]
        result = allocate_requirements(rows, rules, max_options=500)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["groups"], [[1, 2, 3, 4]])

    def test_four_identical_criteria_use_combinations(self) -> None:
        rules = [requires(4, (1, None)), equals(1, 100, *((0, None),) * 4)]
        rows = [row(0, 4)] + [row(i, 0, cost=5) for i in range(1, 15)]
        result = allocate_requirements(rows, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["reason"], "exhaustive allocation")

    def test_empty_demand_and_direct_pass_skip_large_equals_search(self) -> None:
        many_t0 = [row(i, 0, cost=5) for i in range(1, 79)]
        expensive = equals(1, 20, *((0, None),) * 4)
        self.assertEqual(allocate_requirements(many_t0, [expensive], max_options=10)["status"], "pass")
        rows = [row(0, 4), row(79, 1)] + many_t0
        result = allocate_requirements(rows, [requires(4, (1, None)), expensive], max_options=10)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["equals"][0]["used"], 0)

    def test_duplicate_physical_identity_is_unknown(self) -> None:
        rows = [row(0, 4), row(1, 1)]
        rows[1]["character_id"] = rows[0]["character_id"]
        self.assertEqual(allocate_requirements(rows, [requires(4, (1, None))])["status"], "unknown")
        rows[1]["character_id"] = "different"
        rows[1]["source_id"] = rows[0]["source_id"]
        self.assertEqual(allocate_requirements(rows, [requires(4, (1, None))])["status"], "unknown")

    def test_recursive_equals_chain_is_unknown(self) -> None:
        rules = [requires(4, (2, None)), equals(2, 10, (1, None), (1, None)),
                 equals(1, 10, (0, None), (0, None))]
        rows = [row(0, 4), row(1, 0, cost=5), row(2, 0, cost=5)]
        self.assertEqual(allocate_requirements(rows, rules)["status"], "unknown")

    def test_unknown_role_only_matters_to_relevant_exact_slot(self) -> None:
        rows = [row(0, 4), row(1, 1), row(2, 0)]
        rows[2]["specification"] = None
        self.assertEqual(allocate_requirements(rows, [requires(4, (1, 0))])["status"], "pass")
        rows[1]["specification"] = None
        self.assertEqual(allocate_requirements(rows, [requires(4, (1, 0))])["status"], "unknown")

    def test_unsupported_cycle_does_not_fail(self) -> None:
        rows = [row(0, 1)]
        self.assertEqual(allocate_requirements(rows, [requires(1, (1, None))])["status"], "unknown")

    def test_nested_requires_needs_an_explicit_recursive_policy(self) -> None:
        rows = [row(0, 4), row(1, 1), row(2, 0)]
        result = allocate_requirements(rows, [requires(4, (1, None)), requires(1, (0, None))])
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
