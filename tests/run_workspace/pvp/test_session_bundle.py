from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from run_workspace.pvp.account_deck_export import (
    AccountDeckCharacterRow,
    AccountDeckWeaponStackRow,
    FakeAccountDeckDataProvider,
)
from run_workspace.pvp.account_full_loop_smoke import run_account_full_loop_smoke
from run_workspace.pvp.full_loop_smoke import run_default_full_loop_smoke
from run_workspace.pvp.session_bundle import (
    ISSUE_BUNDLE_DRAFT_REPLAY_FAILED,
    ISSUE_BUNDLE_FINAL_STATE_HASH_MISMATCH,
    ISSUE_BUNDLE_MISSING_DECK,
    ISSUE_BUNDLE_UNKNOWN_DRAFT_SYSTEM,
    build_session_bundle_from_account_full_loop_report,
    build_session_bundle_from_full_loop_report,
    calculate_bundle_hash,
    load_session_bundle_from_json_text,
    session_bundle_to_json_text,
    verify_session_bundle,
)
from run_workspace.pvp.session_bundle_smoke import (
    main,
    run_session_bundle_smoke,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1


class SessionBundleTests(unittest.TestCase):
    def test_synthetic_full_loop_builds_roundtrippable_bundle(self) -> None:
        source = run_default_full_loop_smoke()

        bundle = build_session_bundle_from_full_loop_report(
            source,
            created_at_utc="2026-06-12T00:00:00Z",
        )
        roundtripped = load_session_bundle_from_json_text(session_bundle_to_json_text(bundle))
        verification = verify_session_bundle(roundtripped)

        self.assertTrue(verification.ready)
        self.assertEqual(roundtripped.kind, "gtt.pvp_session_bundle")
        self.assertEqual(roundtripped.draft_system.system_id, "free_draft_v0")
        self.assertEqual(len(roundtripped.accepted_actions), 22)
        self.assertEqual(roundtripped.final_state_hash, source.state_hash)
        self.assertEqual(roundtripped.replay_state_hash, source.replay_state_hash)
        self.assertEqual(
            roundtripped.decks[SEAT_PLAYER_1].to_dict(),
            bundle.decks[SEAT_PLAYER_1].to_dict(),
        )
        self.assertEqual(calculate_bundle_hash(bundle), calculate_bundle_hash(roundtripped))

    def test_account_full_loop_fake_provider_builds_bundle_without_real_data(self) -> None:
        source = run_account_full_loop_smoke(provider=_provider(character_count=24))

        bundle = build_session_bundle_from_account_full_loop_report(
            source,
            created_at_utc="2026-06-12T00:00:00Z",
        )
        verification = verify_session_bundle(bundle)

        self.assertTrue(source.ready)
        self.assertTrue(verification.ready)
        self.assertEqual(bundle.source["source_mode"], "account")
        self.assertEqual(len(bundle.decks["player_1"].characters), 24)
        self.assertEqual(len(bundle.accepted_actions), 22)

    def test_tampered_action_log_fails_replay_with_stable_issue(self) -> None:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())
        payload = bundle.to_dict()
        payload["draft"]["accepted_actions"][0]["character_id"] = "not_in_any_deck"

        verification = verify_session_bundle(payload)

        self.assertFalse(verification.ready)
        self.assertIn(ISSUE_BUNDLE_DRAFT_REPLAY_FAILED, verification.issue_codes())

    def test_tampered_final_hash_fails_with_stable_issue(self) -> None:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())
        payload = bundle.to_dict()
        payload["draft"]["final_state_hash"] = "bad_hash"

        verification = verify_session_bundle(payload)

        self.assertFalse(verification.ready)
        self.assertIn(ISSUE_BUNDLE_FINAL_STATE_HASH_MISMATCH, verification.issue_codes())

    def test_missing_deck_fails_with_stable_issue(self) -> None:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())
        payload = bundle.to_dict()
        del payload["decks"]["player_2"]

        verification = verify_session_bundle(payload)

        self.assertFalse(verification.ready)
        self.assertIn(ISSUE_BUNDLE_MISSING_DECK, verification.issue_codes())

    def test_unknown_draft_system_fails_with_stable_issue(self) -> None:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())
        payload = bundle.to_dict()
        payload["draft_system"]["system_id"] = "future_system"

        verification = verify_session_bundle(payload)

        self.assertFalse(verification.ready)
        self.assertIn(ISSUE_BUNDLE_UNKNOWN_DRAFT_SYSTEM, verification.issue_codes())

    def test_session_bundle_smoke_helper_is_structured_and_dry_run(self) -> None:
        report = run_session_bundle_smoke()

        self.assertTrue(report.ready)
        self.assertEqual(report.source_mode, "synthetic")
        self.assertFalse(report.wrote_file)
        self.assertEqual(len(report.bundle.accepted_actions), 22)
        self.assertTrue(report.verification_report.ready)

    def test_session_bundle_smoke_json_main_output_parses(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["draft_system"]["system_id"], "free_draft_v0")
        self.assertEqual(payload["action_count"], 22)

    def test_session_bundle_smoke_write_uses_requested_generated_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "bundle.json"

            report = run_session_bundle_smoke(write=True, output_path=output_path)

            self.assertTrue(report.ready)
            self.assertTrue(report.wrote_file)
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "gtt.pvp_session_bundle")
            self.assertTrue(verify_session_bundle(payload).ready)


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
        AccountDeckWeaponStackRow("weapon_sword", "Sword", 1, rarity=4, level=90, refinement=5, count=8),
        AccountDeckWeaponStackRow("weapon_bow", "Bow", 12, rarity=4, level=90, refinement=5, count=8),
        AccountDeckWeaponStackRow("weapon_polearm", "Polearm", 13, rarity=4, level=90, refinement=5, count=8),
        AccountDeckWeaponStackRow("weapon_claymore", "Claymore", 11, rarity=4, level=90, refinement=5, count=8),
        AccountDeckWeaponStackRow("weapon_catalyst", "Catalyst", 10, rarity=4, level=90, refinement=5, count=8),
    )


if __name__ == "__main__":
    unittest.main()
