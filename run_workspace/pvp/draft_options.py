"""Per-match overrides; a saved source rules snapshot is never modified."""
from dataclasses import dataclass
from math import isfinite
import re

from .abyss_rules import AbyssRuleset
from .schedule import PVP_SEATS, SEAT_PLAYER_1


@dataclass(frozen=True, slots=True)
class DraftMatchOptions:
    preban_cost_step: int | None = None
    pick_time_ms: int | None = None
    reserve_time_ms: int | None = None
    auto_on_expire: bool = True
    free_restarts: int | None = None
    paid_restarts: tuple[int | float, ...] | None = None
    first_seat: str = SEAT_PLAYER_1
    games_count: int = 1
    alternate_first: bool = True

    def __post_init__(self):
        if type(self.auto_on_expire) is not bool:
            raise ValueError("Invalid auto_on_expire")
        if type(self.first_seat) is not str or self.first_seat not in PVP_SEATS:
            raise ValueError("Invalid first_seat")
        if type(self.games_count) is not int or not 1 <= self.games_count <= 9:
            raise ValueError("Invalid games_count")
        if type(self.alternate_first) is not bool:
            raise ValueError("Invalid alternate_first")
        for name, maximum in (("preban_cost_step", 10000), ("pick_time_ms", 86400000),
                              ("reserve_time_ms", 86400000), ("free_restarts", 100)):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 0 <= value <= maximum):
                raise ValueError(f"Invalid {name}")
        paid = self.paid_restarts
        if paid is not None and (
            type(paid) is not tuple or len(paid) > 100
            or any(type(value) not in (int, float) or not 0 <= value <= 86400
                   or (type(value) is float and not isfinite(value)) for value in paid)
        ):
            raise ValueError("Invalid paid_restarts")

    def resolve(self, rules: AbyssRuleset | None) -> "DraftMatchOptions":
        phase = rules.to_dict().get("phase_picks", {}) if rules else {}
        match = rules.to_dict().get("phase_match", {}) if rules else {}
        source_keys = {"preban_cost_step": "preban_cost_step", "pick_time_ms": "pick_time",
                       "reserve_time_ms": "reserve_time"}
        resolved = {
            name: getattr(self, name) if getattr(self, name) is not None else phase.get(source_keys[name], 0)
            for name in source_keys
        }
        resolved["free_restarts"] = (self.free_restarts if self.free_restarts is not None
                                      else match.get("free_restarts", 0))
        resolved["paid_restarts"] = (self.paid_restarts if self.paid_restarts is not None
                                      else tuple(match.get("paid_restarts", ())))
        return DraftMatchOptions(
            **resolved,
            auto_on_expire=self.auto_on_expire,
            first_seat=self.first_seat,
            games_count=self.games_count,
            alternate_first=self.alternate_first,
        )

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


_PENALTY_NUMBER = re.compile(r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


def parse_restart_penalties(text: str) -> tuple[int | float, ...]:
    """Parse slash-separated seconds such as ``5 / 5 / 10`` for match setup."""
    if not isinstance(text, str):
        raise ValueError("Invalid paid_restarts")
    if not text.strip():
        return ()
    parts = text.split("/")
    if len(parts) > 100:
        raise ValueError("Invalid paid_restarts")
    result: list[int | float] = []
    for part in parts:
        token = part.strip()
        if _PENALTY_NUMBER.fullmatch(token) is None:
            raise ValueError("Invalid paid_restarts")
        value = float(token) if "." in token else int(token)
        if value > 86400 or (type(value) is float and not isfinite(value)):
            raise ValueError("Invalid paid_restarts")
        result.append(value)
    return tuple(result)
