"""Immutable, seat-stable ledger for a short series of completed PvP games."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import math
from types import MappingProxyType
from typing import Any, Mapping

from .match_result import MATCH_STATUS_DRAW, MATCH_STATUS_FINISHED, MatchResult
from .schedule import SEAT_PLAYER_1, SEAT_PLAYER_2


SERIES_STATUS_IN_PROGRESS = "in_progress"
SERIES_STATUS_FINISHED = MATCH_STATUS_FINISHED
SERIES_STATUS_DRAW = MATCH_STATUS_DRAW
_SEATS = (SEAT_PLAYER_1, SEAT_PLAYER_2)


def _decimal_seconds(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{field} must be a finite number of seconds")
    try:
        seconds = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number of seconds") from exc
    if not seconds.is_finite() or seconds < 0:
        raise ValueError(f"{field} must be a finite nonnegative number of seconds")
    return seconds


def _score_for_seat(result: MatchResult, seat: str) -> Decimal:
    timers = result.player_1_timers if seat == SEAT_PLAYER_1 else result.player_2_timers
    if timers.seat != seat or not isinstance(timers.chambers, tuple):
        raise ValueError(f"invalid timers for {seat}")
    for chamber in timers.chambers:
        if isinstance(chamber.elapsed_seconds, bool) or not isinstance(chamber.elapsed_seconds, int) or chamber.elapsed_seconds < 0:
            raise ValueError(f"invalid elapsed_seconds for {seat}")
    if result.source_scoring is None:
        return Decimal(timers.total_elapsed_seconds)
    if not isinstance(result.source_scoring, Mapping):
        raise ValueError("source_scoring must be a mapping")
    if result.source_scoring.get("mode") != "SHIYU":
        raise ValueError("unknown source_scoring mode")
    per_seat = result.source_scoring.get("per_seat")
    if not isinstance(per_seat, Mapping):
        raise ValueError("source_scoring.per_seat is required")
    row = per_seat.get(seat)
    if not isinstance(row, Mapping) or "adjusted_seconds" not in row:
        raise ValueError(f"source_scoring.per_seat.{seat}.adjusted_seconds is required")
    return _decimal_seconds(row["adjusted_seconds"], field=f"{seat}.adjusted_seconds")


def _result_scores(result: MatchResult) -> tuple[Decimal, Decimal]:
    if not isinstance(result, MatchResult):
        raise TypeError("result must be a MatchResult")
    if result.technical_losses or result.status not in (MATCH_STATUS_FINISHED, MATCH_STATUS_DRAW):
        raise ValueError("series games require finished or drawn results without technical losses")
    _decimal_seconds(result.seconds_difference, field="seconds_difference")
    player_1 = _score_for_seat(result, SEAT_PLAYER_1)
    player_2 = _score_for_seat(result, SEAT_PLAYER_2)
    winner = SEAT_PLAYER_1 if player_1 < player_2 else SEAT_PLAYER_2 if player_2 < player_1 else None
    expected_status = MATCH_STATUS_DRAW if winner is None else MATCH_STATUS_FINISHED
    if result.status != expected_status or result.winner_seat != winner:
        raise ValueError("match status and winner disagree with its scored seconds")
    return player_1, player_2


def _serialized_seconds(value: Decimal) -> int | str:
    """Retain exact fractional values in JSON-compatible output."""
    return int(value) if value == value.to_integral_value() else str(value)


def _freeze_scoring(value: Any) -> Any:
    """Detach source scoring from caller-owned dictionaries and lists."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("source_scoring keys must be strings")
        return MappingProxyType({key: _freeze_scoring(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_scoring(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("source_scoring values must be finite")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("source_scoring values must be finite")
    if value is None or isinstance(value, (str, int, float, bool, Decimal)):
        return value
    raise ValueError("source_scoring contains an unsupported value")


def _json_scoring(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_scoring(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_scoring(item) for item in value]
    if isinstance(value, Decimal):
        return _serialized_seconds(value)
    return value


def _snapshot_result(result: MatchResult) -> MatchResult:
    if result.source_scoring is None:
        return result
    return replace(result, source_scoring=_freeze_scoring(result.source_scoring))


@dataclass(frozen=True, slots=True)
class TournamentGame:
    game_index: int
    first_seat: str
    result: MatchResult
    player_1_adjusted_seconds: Decimal
    player_2_adjusted_seconds: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_index": self.game_index,
            "first_seat": self.first_seat,
            "adjusted_seconds": {
                SEAT_PLAYER_1: _serialized_seconds(self.player_1_adjusted_seconds),
                SEAT_PLAYER_2: _serialized_seconds(self.player_2_adjusted_seconds),
            },
            "result": _json_scoring(self.result.to_dict()),
        }


@dataclass(frozen=True, slots=True)
class TournamentSeries:
    configured_games: int = 1
    initial_first_seat: str = SEAT_PLAYER_1
    alternate_first: bool = True
    games: tuple[TournamentGame, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.configured_games, bool) or not isinstance(self.configured_games, int) or not 1 <= self.configured_games <= 9:
            raise ValueError("configured_games must be an integer from 1 through 9")
        if self.initial_first_seat not in _SEATS:
            raise ValueError("initial_first_seat must be player_1 or player_2")
        if not isinstance(self.alternate_first, bool):
            raise ValueError("alternate_first must be a boolean")
        if not isinstance(self.games, tuple) or len(self.games) > self.configured_games:
            raise ValueError("games must be a tuple within the configured series length")
        frozen_games: list[TournamentGame] = []
        for index, game in enumerate(self.games, 1):
            if not isinstance(game, TournamentGame) or game.game_index != index or game.first_seat != self.first_seat_for_game(index):
                raise ValueError("series games must be sequential with the configured first seat")
            scores = _result_scores(game.result)
            if (not isinstance(game.player_1_adjusted_seconds, Decimal)
                    or not isinstance(game.player_2_adjusted_seconds, Decimal)):
                raise ValueError("stored game scores must be Decimal values")
            if scores != (game.player_1_adjusted_seconds, game.player_2_adjusted_seconds):
                raise ValueError("stored game scores disagree with the result")
            frozen_games.append(replace(game, result=_snapshot_result(game.result)))
        object.__setattr__(self, "games", tuple(frozen_games))

    def first_seat_for_game(self, game_index: int) -> str:
        if isinstance(game_index, bool) or not isinstance(game_index, int) or not 1 <= game_index <= self.configured_games:
            raise ValueError("game_index is outside the configured series")
        if not self.alternate_first or game_index % 2 == 1:
            return self.initial_first_seat
        return SEAT_PLAYER_2 if self.initial_first_seat == SEAT_PLAYER_1 else SEAT_PLAYER_1

    @property
    def next_game_index(self) -> int | None:
        return None if self.complete else len(self.games) + 1

    @property
    def complete(self) -> bool:
        return len(self.games) == self.configured_games

    @property
    def totals(self) -> Mapping[str, Decimal]:
        return {
            SEAT_PLAYER_1: sum((game.player_1_adjusted_seconds for game in self.games), Decimal(0)),
            SEAT_PLAYER_2: sum((game.player_2_adjusted_seconds for game in self.games), Decimal(0)),
        }

    @property
    def seconds_difference(self) -> Decimal:
        totals = self.totals
        return abs(totals[SEAT_PLAYER_1] - totals[SEAT_PLAYER_2])

    @property
    def winner_seat(self) -> str | None:
        if not self.complete:
            return None
        totals = self.totals
        return SEAT_PLAYER_1 if totals[SEAT_PLAYER_1] < totals[SEAT_PLAYER_2] else SEAT_PLAYER_2 if totals[SEAT_PLAYER_2] < totals[SEAT_PLAYER_1] else None

    @property
    def status(self) -> str:
        if not self.complete:
            return SERIES_STATUS_IN_PROGRESS
        return SERIES_STATUS_DRAW if self.winner_seat is None else SERIES_STATUS_FINISHED

    def with_game_result(self, game_index: int, result: MatchResult) -> TournamentSeries:
        self.first_seat_for_game(game_index)
        if game_index <= len(self.games):
            if isinstance(result, MatchResult) and _json_scoring(result.to_dict()) == self.games[game_index - 1].to_dict()["result"]:
                return self
            raise ValueError("a recorded game cannot be overwritten with a different result")
        if game_index != len(self.games) + 1:
            raise ValueError("games must be recorded in order")
        player_1, player_2 = _result_scores(result)
        game = TournamentGame(game_index, self.first_seat_for_game(game_index), _snapshot_result(result), player_1, player_2)
        return replace(self, games=self.games + (game,))

    def to_dict(self) -> dict[str, Any]:
        totals = self.totals
        return {
            "configured_games": self.configured_games,
            "initial_first_seat": self.initial_first_seat,
            "alternate_first": self.alternate_first,
            "games": [game.to_dict() for game in self.games],
            "next_game_index": self.next_game_index,
            "complete": self.complete,
            "totals": {seat: _serialized_seconds(totals[seat]) for seat in _SEATS},
            "status": self.status,
            "winner_seat": self.winner_seat,
            "seconds_difference": _serialized_seconds(self.seconds_difference),
        }
