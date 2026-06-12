"""Small helpers for account-derived PvP deck copies.

These helpers are backend contract utilities, not CLI smoke entrypoints. They
exist so controller/package imports do not need to import account smoke modules.
"""

from __future__ import annotations

from dataclasses import replace

from .deck import DraftDeck, DraftDeckPlayer, DraftDeckSource
from .schedule import SEAT_PLAYER_1


def copy_deck_for_player_2(deck: DraftDeck) -> DraftDeck:
    source_extra = {
        **dict(deck.source.extra),
        "copied_for_account_full_loop_smoke": True,
        "copied_from_seat": SEAT_PLAYER_1,
    }
    player_extra = {
        **dict(deck.player.extra),
        "copied_for_account_full_loop_smoke": True,
    }
    nickname = (
        f"{deck.player.nickname} (P2 Copy)"
        if deck.player.nickname
        else "account-copy-player-2"
    )
    return replace(
        deck,
        deck_name=f"{deck.deck_name} (Player 2 Copy)",
        player=DraftDeckPlayer(
            nickname=nickname,
            extra=player_extra,
        ),
        source=DraftDeckSource(
            app=deck.source.app,
            language=deck.source.language,
            exported_at_utc=deck.source.exported_at_utc,
            extra=source_extra,
        ),
        characters=tuple(deck.characters),
        weapons=tuple(deck.weapons),
    )


__all__ = ["copy_deck_for_player_2"]
