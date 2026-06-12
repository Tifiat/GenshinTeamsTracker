"""Synthetic Free Draft board projection sample builder.

This module builds a small UI-contract sample from committed synthetic deck
fixtures. It does not read local account data, write files, or start UI code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .free_draft_controller import FreeDraftController


_PVP_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "samples" / "pvp"
DEFAULT_PLAYER_1_SAMPLE_DECK_PATH = _PVP_SAMPLE_DIR / "free_draft_player_1_deck.json"
DEFAULT_PLAYER_2_SAMPLE_DECK_PATH = _PVP_SAMPLE_DIR / "free_draft_player_2_deck.json"


def build_free_draft_board_contract_sample() -> dict[str, Any]:
    initial_controller = _sample_controller()
    initial = initial_controller.to_board_dict()

    after_two_controller = _sample_controller()
    for _ in range(2):
        legal_targets = after_two_controller.get_legal_targets()
        if not legal_targets:
            break
        after_two_controller.apply_current_action(legal_targets[0].character_id)
    after_two_actions = after_two_controller.to_board_dict()

    final_controller = _sample_controller()
    final_controller.complete_draft_with_first_legal_targets()
    final_controller.assign_deterministic_teams_and_weapons()
    final_controller.set_deterministic_timers()
    final = final_controller.to_board_dict()

    return {
        "kind": "gtt.pvp.free_draft_board_contract_sample",
        "schema_version": 1,
        "source": {
            "mode": "synthetic",
            "player_1_deck": "samples/pvp/free_draft_player_1_deck.json",
            "player_2_deck": "samples/pvp/free_draft_player_2_deck.json",
        },
        "sections": {
            "initial": initial,
            "after_two_actions": after_two_actions,
            "final": final,
        },
    }


def _sample_controller() -> FreeDraftController:
    return FreeDraftController.from_deck_files(
        DEFAULT_PLAYER_1_SAMPLE_DECK_PATH,
        DEFAULT_PLAYER_2_SAMPLE_DECK_PATH,
    )


__all__ = [
    "DEFAULT_PLAYER_1_SAMPLE_DECK_PATH",
    "DEFAULT_PLAYER_2_SAMPLE_DECK_PATH",
    "build_free_draft_board_contract_sample",
]
