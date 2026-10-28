from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schedule import SEAT_PLAYER_1, SEAT_PLAYER_2


MATCH_STATUS_FINISHED = "finished"
MATCH_STATUS_DRAW = "draw"
MATCH_STATUS_TECHNICAL_LOSS = "technical_loss"


@dataclass(frozen=True, slots=True)
class ChamberTimer:
    room_id: str
    chamber_id: str
    elapsed_seconds: int

    def normalized_elapsed_seconds(self) -> int:
        return max(0, int(self.elapsed_seconds))

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "chamber_id": self.chamber_id,
            "elapsed_seconds": self.elapsed_seconds,
            "normalized_elapsed_seconds": self.normalized_elapsed_seconds(),
        }


@dataclass(frozen=True, slots=True)
class PlayerMatchTimers:
    seat: str
    chambers: tuple[ChamberTimer, ...]

    @property
    def total_elapsed_seconds(self) -> int:
        return sum(item.normalized_elapsed_seconds() for item in self.chambers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "chambers": [item.to_dict() for item in self.chambers],
        }


@dataclass(frozen=True, slots=True)
class TechnicalLoss:
    seat: str
    reason: str
    issue_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "reason": self.reason,
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    player_1_timers: PlayerMatchTimers
    player_2_timers: PlayerMatchTimers
    status: str
    winner_seat: str | None
    seconds_difference: int
    technical_losses: tuple[TechnicalLoss, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "winner_seat": self.winner_seat,
            "seconds_difference": self.seconds_difference,
            "totals": {
                SEAT_PLAYER_1: self.player_1_timers.total_elapsed_seconds,
                SEAT_PLAYER_2: self.player_2_timers.total_elapsed_seconds,
            },
            "player_1_timers": self.player_1_timers.to_dict(),
            "player_2_timers": self.player_2_timers.to_dict(),
            "technical_losses": [item.to_dict() for item in self.technical_losses],
        }


def calculate_match_result(
    player_1_timers: PlayerMatchTimers,
    player_2_timers: PlayerMatchTimers,
    *,
    technical_losses: tuple[TechnicalLoss, ...] = (),
) -> MatchResult:
    loss_seats = {item.seat for item in technical_losses}
    player_1_total = player_1_timers.total_elapsed_seconds
    player_2_total = player_2_timers.total_elapsed_seconds

    if SEAT_PLAYER_1 in loss_seats and SEAT_PLAYER_2 in loss_seats:
        return MatchResult(
            player_1_timers=player_1_timers,
            player_2_timers=player_2_timers,
            status=MATCH_STATUS_TECHNICAL_LOSS,
            winner_seat=None,
            seconds_difference=0,
            technical_losses=technical_losses,
        )
    if SEAT_PLAYER_1 in loss_seats:
        return MatchResult(
            player_1_timers=player_1_timers,
            player_2_timers=player_2_timers,
            status=MATCH_STATUS_TECHNICAL_LOSS,
            winner_seat=SEAT_PLAYER_2,
            seconds_difference=abs(player_1_total - player_2_total),
            technical_losses=technical_losses,
        )
    if SEAT_PLAYER_2 in loss_seats:
        return MatchResult(
            player_1_timers=player_1_timers,
            player_2_timers=player_2_timers,
            status=MATCH_STATUS_TECHNICAL_LOSS,
            winner_seat=SEAT_PLAYER_1,
            seconds_difference=abs(player_1_total - player_2_total),
            technical_losses=technical_losses,
        )
    if player_1_total < player_2_total:
        return _finished_result(
            player_1_timers,
            player_2_timers,
            winner_seat=SEAT_PLAYER_1,
        )
    if player_2_total < player_1_total:
        return _finished_result(
            player_1_timers,
            player_2_timers,
            winner_seat=SEAT_PLAYER_2,
        )
    return MatchResult(
        player_1_timers=player_1_timers,
        player_2_timers=player_2_timers,
        status=MATCH_STATUS_DRAW,
        winner_seat=None,
        seconds_difference=0,
        technical_losses=technical_losses,
    )


def _finished_result(
    player_1_timers: PlayerMatchTimers,
    player_2_timers: PlayerMatchTimers,
    *,
    winner_seat: str,
) -> MatchResult:
    return MatchResult(
        player_1_timers=player_1_timers,
        player_2_timers=player_2_timers,
        status=MATCH_STATUS_FINISHED,
        winner_seat=winner_seat,
        seconds_difference=abs(
            player_1_timers.total_elapsed_seconds
            - player_2_timers.total_elapsed_seconds
        ),
    )
