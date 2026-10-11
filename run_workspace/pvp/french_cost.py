"""Signed source-variant price difference for Abyss FRENCH_COST rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .abyss_rules import AbyssRuleset, evaluate_deck
from .deck import DraftDeck


class FrenchCostError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FrenchCostDifferenceReport:
    signed_difference: Decimal
    absolute_difference: Decimal
    difference_cap: Decimal


def calculate_french_cost_difference(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    rules: AbyssRuleset,
) -> FrenchCostDifferenceReport:
    """Sum capped signed differences per source variant, treating absence as zero."""
    data = rules.to_dict()
    if data["source"].get("cost_system") != "FRENCH_COST":
        raise FrenchCostError("french_cost_mode_required", "Pinned rules do not use French cost mode.")
    raw_cap = data["french_difference_cap"]
    if raw_cap is None:
        raise FrenchCostError("french_cost_cap_missing", "French cost mode has no difference cap.")
    cap = Decimal(str(raw_cap))
    if not cap.is_finite() or cap < 0:
        raise FrenchCostError("french_cost_cap_invalid", "French cost cap must be finite and nonnegative.")
    source_rows = {row["source_id"]: row for row in data["characters"]}
    priced: list[dict[str, Decimal]] = []
    for deck in (player_1_deck, player_2_deck):
        by_variant: dict[str, Decimal] = {}
        for row in evaluate_deck(deck, rules).character_rows:
            source_id, raw_price = row["source_id"], row["cost"]
            if source_id is None or raw_price is None:
                raise FrenchCostError("french_cost_price_unknown", "A character variant has no known price.")
            price = Decimal(str(raw_price))
            if not price.is_finite():
                raise FrenchCostError("french_cost_price_unknown", "A character variant has a nonfinite price.")
            if source_id in by_variant:
                raise FrenchCostError("french_cost_variant_duplicate", "A roster repeats a source variant.")
            by_variant[source_id] = price
        priced.append(by_variant)
    signed = Decimal(0)
    for source_id in sorted(priced[0].keys() | priced[1].keys()):
        difference = priced[0].get(source_id, Decimal(0)) - priced[1].get(source_id, Decimal(0))
        if not source_rows[source_id]["disable_french_cap"]:
            difference = max(-cap, min(cap, difference))
        signed += difference
    return FrenchCostDifferenceReport(signed, abs(signed), cap)
