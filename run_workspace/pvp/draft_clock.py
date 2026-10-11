"""Pure, monotonic clock for one local PvP draft.

The caller owns action acceptance and any decision made after expiry. Advance
only after the reducer accepts an action, using the next action's distinct key.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import monotonic
from types import MappingProxyType
from typing import Callable, Mapping

from .schedule import PVP_SEATS


@dataclass(frozen=True, slots=True)
class DraftClockSnapshot:
    action_key: object | None
    active_seat: str | None
    pick_remaining_ms: float
    reserve_remaining_ms: Mapping[str, float]
    paused: bool
    expired: bool
    finished: bool
    running: bool


class DraftClock:
    """Per-action pick allowance plus persistent per-seat reserve.

    ``now`` returns monotonic seconds. A backwards sample is clamped to the
    latest observed instant, so an expired action cannot become live again.
    """

    def __init__(
        self,
        pick_time_ms: int,
        reserve_time_ms: int,
        *,
        now: Callable[[], float] = monotonic,
    ) -> None:
        for name, value in (("pick_time_ms", pick_time_ms),
                            ("reserve_time_ms", reserve_time_ms)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not callable(now):
            raise TypeError("now must be callable")
        self._pick_us = pick_time_ms * 1000
        self._reserve_us = reserve_time_ms * 1000
        self._now = now
        self._last_sample_us: int | None = None
        self._spent_us = {seat: 0 for seat in PVP_SEATS}
        self._action_key: object | None = None
        self._active_seat: str | None = None
        self._action_started_us: int | None = None
        self._paused_since_us: int | None = None
        self._paused_action_us = 0
        self._expired = False
        self._finished = False
        self._finished_elapsed_us = 0

    def start(self, action_key: object, seat: str) -> None:
        """Start the first action; call exactly once for a draft."""
        self._require_action(action_key, seat)
        if self._action_started_us is not None or self._finished:
            raise RuntimeError("draft clock has already started or finished")
        instant = self._sample_us()
        self._action_key = action_key
        self._active_seat = seat
        self._action_started_us = instant

    def advance(self, action_key: object, seat: str) -> bool:
        """Commit an accepted action and start its successor.

        The same action key means the reducer has not moved. In that case this
        method does nothing and returns False. A distinct key returns True.
        """
        self._require_action(action_key, seat)
        if self._action_started_us is None or self._finished:
            raise RuntimeError("draft clock is not active")
        if action_key == self._action_key:
            return False
        instant = self._sample_us()
        self._settle(instant)
        self._action_key = action_key
        self._active_seat = seat
        self._action_started_us = instant
        self._paused_action_us = 0
        self._paused_since_us = instant if self._paused_since_us is not None else None
        self._expired = False
        return True

    accept = advance

    def pause(self) -> None:
        if self._action_started_us is None or self._finished or self._paused_since_us is not None:
            return
        instant = self._sample_us()
        self._observe_expiry(instant)
        self._paused_since_us = instant

    def resume(self) -> None:
        if self._paused_since_us is None or self._finished:
            return
        instant = self._sample_us()
        self._paused_action_us += instant - self._paused_since_us
        self._paused_since_us = None

    def finish(self) -> None:
        if self._finished:
            return
        if self._action_started_us is not None:
            instant = self._sample_us()
            self._finished_elapsed_us = self._elapsed_us(instant)
            self._settle(instant)
        self._finished = True
        self._paused_since_us = None

    def snapshot(self) -> DraftClockSnapshot:
        """Return an immutable view; polling does not repeatedly spend reserve."""
        instant = self._sample_us() if self._action_started_us is not None and not self._finished else None
        if instant is not None:
            self._observe_expiry(instant)
        elapsed_us = (self._finished_elapsed_us if self._finished
                      else self._elapsed_us(instant))
        active_reserve_use = (max(0, elapsed_us - self._pick_us)
                              if self._pick_us and not self._finished else 0)
        reserves = {
            seat: max(0, self._reserve_us - spent - (
                active_reserve_use if seat == self._active_seat else 0
            )) / 1000
            for seat, spent in self._spent_us.items()
        }
        return DraftClockSnapshot(
            action_key=self._action_key,
            active_seat=self._active_seat,
            pick_remaining_ms=max(0, self._pick_us - elapsed_us) / 1000
            if self._pick_us else 0,
            reserve_remaining_ms=MappingProxyType(reserves),
            paused=self._paused_since_us is not None,
            expired=self._expired,
            finished=self._finished,
            running=(self._action_started_us is not None and self._pick_us > 0
                     and not self._finished and self._paused_since_us is None
                     and not self._expired),
        )

    def _sample_us(self) -> int:
        raw = self._now()
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
            raise ValueError("now must return finite monotonic seconds")
        sampled = round(raw * 1_000_000)
        if self._last_sample_us is None or sampled > self._last_sample_us:
            self._last_sample_us = sampled
        return self._last_sample_us

    def _elapsed_us(self, instant: int | None) -> int:
        if instant is None or self._action_started_us is None:
            return 0
        end = self._paused_since_us if self._paused_since_us is not None else instant
        return max(0, end - self._action_started_us - self._paused_action_us)

    def _observe_expiry(self, instant: int) -> None:
        if self._pick_us == 0 or self._expired or self._finished:
            return
        assert self._active_seat is not None
        available = self._pick_us + self._reserve_us - self._spent_us[self._active_seat]
        if self._elapsed_us(instant) >= available:
            self._expired = True

    def _settle(self, instant: int) -> None:
        self._observe_expiry(instant)
        if self._pick_us == 0 or self._active_seat is None:
            return
        used = max(0, self._elapsed_us(instant) - self._pick_us)
        self._spent_us[self._active_seat] = min(
            self._reserve_us, self._spent_us[self._active_seat] + used
        )

    @staticmethod
    def _require_action(action_key: object, seat: str) -> None:
        if action_key is None:
            raise ValueError("action_key must identify a draft action")
        if seat not in PVP_SEATS:
            raise ValueError(f"unknown draft seat: {seat!r}")
