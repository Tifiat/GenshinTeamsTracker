from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from run_workspace.pvp.deck import (
    DRAFT_DECK_KIND,
    DRAFT_DECK_SCHEMA_VERSION,
    DraftCharacter,
    DraftDeck,
    DraftDeckPlayer,
    DraftDeckRulesetRef,
    DraftDeckSource,
    DraftWeaponStack,
    load_draft_deck,
)
from run_workspace.pvp.full_loop_smoke import default_full_loop_actions
from run_workspace.pvp.schedule import (
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
)
from run_workspace.pvp.session import (
    DraftAction,
    DraftSessionState,
    PlayerTeamAssignment,
    TeamAssignment,
    apply_draft_action,
    create_draft_session,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PVP_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp"


def load_sample_decks() -> tuple[DraftDeck, DraftDeck]:
    return (
        load_draft_deck(PVP_SAMPLE_DIR / "free_draft_player_1_deck.json"),
        load_draft_deck(PVP_SAMPLE_DIR / "free_draft_player_2_deck.json"),
    )


def default_draft_actions() -> tuple[DraftAction, ...]:
    return default_full_loop_actions()


def play_default_sample_draft() -> DraftSessionState:
    player_1_deck, player_2_deck = load_sample_decks()
    state = create_draft_session(player_1_deck, player_2_deck)
    for action in default_draft_actions():
        state = apply_draft_action(state, action)
    return state


def completed_sample_state(
    *,
    player_1_picks: tuple[str, ...] | None = None,
    player_2_picks: tuple[str, ...] | None = None,
) -> DraftSessionState:
    player_1_deck, player_2_deck = load_sample_decks()
    schedule = build_default_free_draft_v0_schedule()
    return replace(
        create_draft_session(player_1_deck, player_2_deck),
        step_index=len(schedule.steps),
        action_index=0,
        player_1_picked_character_ids=player_1_picks
        or tuple(f"test_p1_char_{index:02d}" for index in range(1, 9)),
        player_2_picked_character_ids=player_2_picks
        or tuple(f"test_p2_char_{index:02d}" for index in range(1, 9)),
    )


def team_assignment(seat: str, character_ids: tuple[str, ...]) -> PlayerTeamAssignment:
    return PlayerTeamAssignment(
        seat=seat,
        teams=(
            TeamAssignment(team_index=0, character_ids=character_ids[:4]),
            TeamAssignment(team_index=1, character_ids=character_ids[4:8]),
        ),
    )


def stack_key_for(deck: DraftDeck, weapon_type: str) -> str:
    for weapon in deck.weapons:
        if weapon.weapon_type == weapon_type:
            return weapon.stack_key
    raise AssertionError(f"No fixture weapon stack for {weapon_type}")


def synthetic_deck(
    prefix: str,
    *,
    shared_character_ids: tuple[str, ...] = (),
    character_count: int = 12,
) -> DraftDeck:
    weapon_types = ("SWORD", "BOW", "POLEARM", "CLAYMORE", "CATALYST")
    characters: list[DraftCharacter] = []
    for character_id in shared_character_ids:
        characters.append(_character(character_id, "Shared Character", "SWORD"))
    while len(characters) < character_count:
        index = len(characters) + 1
        weapon_type = weapon_types[(index - 1) % len(weapon_types)]
        characters.append(
            _character(
                f"{prefix}_char_{index:02d}",
                f"{prefix.upper()} Character {index:02d}",
                weapon_type,
            )
        )
    return DraftDeck(
        schema_version=DRAFT_DECK_SCHEMA_VERSION,
        kind=DRAFT_DECK_KIND,
        deck_name=f"{prefix} deck",
        ruleset_ref=DraftDeckRulesetRef(),
        player=DraftDeckPlayer(nickname=prefix),
        source=DraftDeckSource(app="tests", language="en", extra={"test_fixture": True}),
        characters=tuple(characters),
        weapons=tuple(
            DraftWeaponStack(
                weapon_id=f"test_weapon_{weapon_type.casefold()}",
                display_name=f"Test {weapon_type.title()}",
                weapon_type=weapon_type,
                rarity=4,
                level=90,
                refinement=5,
                count=8,
            )
            for weapon_type in weapon_types
        ),
    )


def _character(character_id: str, name: str, weapon_type: str) -> DraftCharacter:
    return DraftCharacter(
        character_id=character_id,
        display_name=name,
        element="PYRO",
        weapon_type=weapon_type,
        rarity=5,
        level=90,
        constellation=0,
    )
