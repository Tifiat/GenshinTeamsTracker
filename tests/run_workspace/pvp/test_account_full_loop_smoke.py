from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from run_workspace.pvp.account_deck_export import (
    AccountDeckCharacterRow,
    AccountDeckExportOptions,
    AccountDeckWeaponStackRow,
    FakeAccountDeckDataProvider,
    export_free_draft_deck_from_account,
)
from run_workspace.pvp.account_deck_copy import copy_deck_for_player_2
from run_workspace.pvp.account_full_loop_smoke import (
    ISSUE_DRAFT_PLAN_NOT_READY,
    format_account_full_loop_smoke_report,
    main,
    run_account_full_loop_smoke,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from run_workspace.pvp.validation import validate_draft_deck


class AccountFullLoopSmokeTests(unittest.TestCase):
    def test_copies_account_deck_into_independent_player_2_scope(self) -> None:
        export = export_free_draft_deck_from_account(_provider(character_count=24))

        copied = copy_deck_for_player_2(export.deck)

        self.assertIsNot(copied, export.deck)
        self.assertEqual(copied.character_ids, export.deck.character_ids)
        self.assertEqual(len(copied.weapons), len(export.deck.weapons))
        self.assertNotEqual(copied.deck_name, export.deck.deck_name)
        self.assertTrue(copied.source.extra["copied_for_account_full_loop_smoke"])
        self.assertTrue(validate_draft_deck(copied).ready)

    def test_fake_account_full_loop_smoke_reaches_result(self) -> None:
        report = run_account_full_loop_smoke(
            provider=_provider(character_count=24),
            options=AccountDeckExportOptions(
                deck_name="Account Loop Fixture",
                nickname="fixture",
                language="en",
                exported_at_utc="2026-06-12T00:00:00Z",
            ),
        )

        self.assertTrue(report.ready)
        self.assertEqual(report.action_plan.action_count, 22)
        self.assertEqual(
            report.action_plan.final_state.state_hash(),
            report.replay_state_hash,
        )
        self.assertEqual(
            len(report.action_plan.final_state.picked_character_ids_for(SEAT_PLAYER_1)),
            8,
        )
        self.assertEqual(
            len(report.action_plan.final_state.picked_character_ids_for(SEAT_PLAYER_2)),
            8,
        )
        self.assertTrue(report.player_1_team_plan.ready)
        self.assertTrue(report.player_2_team_plan.ready)
        self.assertTrue(report.player_1_weapon_plan.ready)
        self.assertTrue(report.player_2_weapon_plan.ready)
        self.assertEqual(report.match_result.winner_seat, SEAT_PLAYER_1)
        self.assertEqual(report.match_result.seconds_difference, 30)

        text = format_account_full_loop_smoke_report(report)
        self.assertIn("PvP account full-loop smoke", text)
        self.assertIn("ready=true", text)
        self.assertIn("diff=30s", text)

    def test_fake_account_full_loop_reports_small_copied_deck_gap(self) -> None:
        report = run_account_full_loop_smoke(provider=_provider(character_count=12))

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_DRAFT_PLAN_NOT_READY, report.issue_codes())
        self.assertIsNotNone(report.action_plan)
        self.assertFalse(report.action_plan.ready)

    def test_json_main_output_is_parseable(self) -> None:
        report = run_account_full_loop_smoke(provider=_provider(character_count=24))
        stdout = io.StringIO()

        with patch(
            "run_workspace.pvp.account_full_loop_smoke.run_account_full_loop_smoke",
            return_value=report,
        ):
            with redirect_stdout(stdout):
                exit_code = main(["--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["planner"]["action_count"], 22)
        self.assertNotIn("deck", payload["export"])


def _provider(*, character_count: int) -> FakeAccountDeckDataProvider:
    return FakeAccountDeckDataProvider(
        characters=_characters(character_count),
        weapon_stacks=_weapons(),
        source_summary={"fixture": True},
    )


def _characters(character_count: int) -> tuple[AccountDeckCharacterRow, ...]:
    weapon_types = (1, 12, 13, 11, 10)
    elements = ("Pyro", "Hydro", "Electro", "Cryo", "Geo")
    return tuple(
        AccountDeckCharacterRow(
            character_id=f"test_char_{index:02d}",
            display_name=f"Character {index:02d}",
            element=elements[(index - 1) % len(elements)],
            weapon_type=weapon_types[(index - 1) % len(weapon_types)],
            rarity=5 if index % 2 else 4,
            level=80 + (index % 20),
            constellation=index % 7,
        )
        for index in range(1, character_count + 1)
    )


def _weapons() -> tuple[AccountDeckWeaponStackRow, ...]:
    return (
        AccountDeckWeaponStackRow(
            "weapon_sword",
            "Sword",
            1,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_bow",
            "Bow",
            12,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_polearm",
            "Polearm",
            13,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_claymore",
            "Claymore",
            11,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_catalyst",
            "Catalyst",
            10,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
    )


if __name__ == "__main__":
    unittest.main()
