"""Developer smoke for PvP ruleset applicability/cost research fixtures.

This uses tiny synthetic ruleset JSON files under `samples/pvp/rulesets/`.
Those files are shaped after current parser contracts and public-source audits;
they are not raw Gentor/Abyss payload captures and should be replaced by a real
import adapter only after the backend contract is stable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hoyolab_export.tournament_ruleset import load_tournament_ruleset_json

from .deck import DraftDeck, load_draft_deck
from .ruleset_applicability import (
    RulesetApplicabilityReport,
    build_ruleset_applicability_report,
)
from .ruleset_costs import RulesetDeckCostReport, calculate_draft_deck_ruleset_cost


PVP_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PVP_PACKAGE_DIR.parents[1]
DEFAULT_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp"
DEFAULT_RULESET_SAMPLE_DIR = DEFAULT_SAMPLE_DIR / "rulesets"
DEFAULT_GTT_RULESET_PATH = DEFAULT_RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
DEFAULT_GENTOR_RULESET_PATH = (
    DEFAULT_RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"
)
DEFAULT_DECK_PATH = DEFAULT_SAMPLE_DIR / "free_draft_player_1_deck.json"


class RulesetApplicabilitySmokeError(RuntimeError):
    """Raised when the deterministic ruleset applicability smoke cannot complete."""


@dataclass(frozen=True, slots=True)
class RulesetApplicabilitySmokeReport:
    deck_name: str
    gtt_ruleset: RulesetApplicabilityReport
    gentor_like_ruleset: RulesetApplicabilityReport
    gtt_deck_cost: RulesetDeckCostReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_name": self.deck_name,
            "gtt_ruleset": self.gtt_ruleset.to_dict(),
            "gentor_like_ruleset": self.gentor_like_ruleset.to_dict(),
            "gtt_deck_cost": self.gtt_deck_cost.to_dict(),
        }


def run_default_ruleset_applicability_smoke(
    *,
    gtt_ruleset_path: str | Path = DEFAULT_GTT_RULESET_PATH,
    gentor_ruleset_path: str | Path = DEFAULT_GENTOR_RULESET_PATH,
    deck_path: str | Path = DEFAULT_DECK_PATH,
) -> RulesetApplicabilitySmokeReport:
    gtt_ruleset = load_tournament_ruleset_json(gtt_ruleset_path)
    gentor_like_ruleset = load_tournament_ruleset_json(gentor_ruleset_path)
    deck = load_draft_deck(deck_path)

    gtt_report = build_ruleset_applicability_report(gtt_ruleset)
    gentor_report = build_ruleset_applicability_report(gentor_like_ruleset)
    cost_report = calculate_draft_deck_ruleset_cost(deck, gtt_ruleset)

    if not gtt_report.ready_for_cost_preview:
        raise RulesetApplicabilitySmokeError("GTT ruleset fixture cannot price a deck.")
    if cost_report.total_cost <= 0:
        raise RulesetApplicabilitySmokeError("GTT deck cost did not produce a total.")
    if gtt_report.ready_for_schedule_execution:
        raise RulesetApplicabilitySmokeError(
            "GTT fixture unexpectedly derived an executable schedule."
        )
    if gentor_report.ready_for_schedule_execution:
        raise RulesetApplicabilitySmokeError(
            "Gentor-like fixture unexpectedly derived an executable schedule."
        )

    return RulesetApplicabilitySmokeReport(
        deck_name=deck.deck_name,
        gtt_ruleset=gtt_report,
        gentor_like_ruleset=gentor_report,
        gtt_deck_cost=cost_report,
    )


def format_smoke_report(report: RulesetApplicabilitySmokeReport) -> str:
    gtt = report.gtt_ruleset
    gentor = report.gentor_like_ruleset
    cost = report.gtt_deck_cost
    return "\n".join(
        (
            "PvP ruleset applicability smoke",
            f"Deck: {report.deck_name}",
            (
                "GTT fixture: "
                f"chars={gtt.character_cost_count}, "
                f"weapons={gtt.weapon_cost_count}, "
                f"overrides={gtt.weapon_override_count}, "
                f"cost_preview={str(gtt.ready_for_cost_preview).lower()}, "
                f"schedule={gtt.schedule_derivation.status}"
            ),
            (
                "Gentor-like fixture: "
                f"chars={gentor.character_cost_count}, "
                f"weapons={gentor.weapon_cost_count}, "
                f"script={str(gentor.has_unsupported_script_rules).lower()}, "
                f"schedule={gentor.schedule_derivation.status}"
            ),
            (
                "GTT deck cost: "
                f"characters={cost.character_total:g}, "
                f"weapons={cost.weapon_total:g}, "
                f"total={cost.total_cost:g}, "
                f"ready={str(cost.ready).lower()}"
            ),
            "Schedule derivation: unsupported until an explicit source adapter exists",
            f"GTT issue codes: {', '.join(gtt.issue_codes())}",
            f"Gentor-like issue codes: {', '.join(gentor.issue_codes())}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run backend-only PvP ruleset applicability fixture smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    args = parser.parse_args(argv)
    try:
        report = run_default_ruleset_applicability_smoke()
    except Exception as exc:
        print(f"PvP ruleset applicability smoke failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_smoke_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
