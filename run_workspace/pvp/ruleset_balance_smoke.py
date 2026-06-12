"""Backend-only smoke for applying ruleset/balance data to PvP decks."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hoyolab_export.tournament_ruleset import load_tournament_ruleset_json

from .account_deck_export import (
    AccountDeckExportOptions,
    LocalAccountSQLiteDeckDataProvider,
    export_free_draft_deck_from_account,
)
from .full_loop_smoke import DEFAULT_PLAYER_1_DECK_PATH, run_default_full_loop_smoke
from .ruleset_balance import (
    RulesetDeckApplicationReport,
    apply_ruleset_balance_to_deck,
    apply_ruleset_balance_to_bundle,
    attach_ruleset_balance_summary_to_bundle,
)
from .session_bundle import (
    PvpSessionBundle,
    build_session_bundle_from_full_loop_report,
    calculate_bundle_hash,
    load_session_bundle_from_json_text,
    session_bundle_to_json_text,
    verify_session_bundle,
)
from .deck import load_draft_deck


PVP_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PVP_PACKAGE_DIR.parents[1]
DEFAULT_RULESET_PATH = (
    REPO_ROOT / "samples" / "pvp" / "rulesets" / "minimal_gtt_ruleset.json"
)


class RulesetBalanceSmokeError(RuntimeError):
    """Raised when the deterministic ruleset balance smoke cannot complete."""


@dataclass(frozen=True, slots=True)
class RulesetBalanceSmokeReport:
    source_mode: str
    ruleset_path: str
    deck_report: RulesetDeckApplicationReport
    bundle: PvpSessionBundle | None = None
    bundle_balance_summary: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return self.deck_report.ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "source_mode": self.source_mode,
            "ruleset_path": self.ruleset_path,
            "deck_report": self.deck_report.to_dict(),
            "bundle": (
                {
                    "session_id": self.bundle.session_id,
                    "bundle_hash": calculate_bundle_hash(self.bundle),
                    "verification": verify_session_bundle(self.bundle).to_dict(),
                    "roundtrip_preserves_balance_summary": (
                        "ruleset_balance"
                        in load_session_bundle_from_json_text(
                            session_bundle_to_json_text(self.bundle)
                        ).reports
                    ),
                }
                if self.bundle is not None
                else None
            ),
            "bundle_balance_summary": self.bundle_balance_summary,
        }


def run_ruleset_balance_smoke(
    *,
    ruleset_path: str | Path = DEFAULT_RULESET_PATH,
    use_account: bool = False,
    include_session_bundle: bool = False,
) -> RulesetBalanceSmokeReport:
    ruleset_path = Path(ruleset_path)
    ruleset = load_tournament_ruleset_json(ruleset_path)

    if use_account:
        export = export_free_draft_deck_from_account(
            LocalAccountSQLiteDeckDataProvider(),
            options=AccountDeckExportOptions(),
        )
        if not export.ready:
            raise RulesetBalanceSmokeError("Account deck export is not ready.")
        deck = export.deck
        source_mode = "account"
    else:
        deck = load_draft_deck(DEFAULT_PLAYER_1_DECK_PATH)
        source_mode = "synthetic"

    deck_report = apply_ruleset_balance_to_deck(deck, ruleset, seat="player_1")
    bundle = None
    bundle_summary = None
    if include_session_bundle:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())
        bundle_summary = dict(
            apply_ruleset_balance_to_bundle(bundle, ruleset, seats=("player_1",))
        )
        bundle = attach_ruleset_balance_summary_to_bundle(
            bundle,
            ruleset,
            seats=("player_1",),
        )
    return RulesetBalanceSmokeReport(
        source_mode=source_mode,
        ruleset_path=str(ruleset_path),
        deck_report=deck_report,
        bundle=bundle,
        bundle_balance_summary=bundle_summary,
    )


def format_ruleset_balance_smoke_report(report: RulesetBalanceSmokeReport) -> str:
    deck = report.deck_report
    ruleset = deck.ruleset_summary
    matching = deck.matching_summary
    costs = deck.cost_summary
    unsupported = ", ".join(
        restriction.code
        for restriction in deck.restrictions
        if restriction.status != "enforced"
    ) or "none"
    bundle_line = (
        f"Bundle balance summary: seats={len(report.bundle_balance_summary.get('seats', {}))}"
        if report.bundle_balance_summary is not None
        else "Bundle balance summary: not requested"
    )
    return "\n".join(
        (
            "PvP ruleset balance smoke",
            (
                "Ruleset: "
                f"{ruleset.get('ruleset_name', '')} "
                f"source={ruleset.get('source', '')}"
            ),
            f"Deck source mode: {report.source_mode}",
            (
                "Matches: "
                f"characters id={matching.character_id_matches}, "
                f"fallback={matching.character_fallback_name_matches}, "
                f"unmatched={matching.character_unmatched}; "
                f"weapons id={matching.weapon_id_matches}, "
                f"fallback={matching.weapon_fallback_name_matches}, "
                f"unmatched={matching.weapon_unmatched}"
            ),
            (
                "Costs: "
                f"characters={costs.character_cost_total}, "
                f"weapons={costs.weapon_cost_total}, "
                f"total={costs.total_cost}, "
                f"ready={str(costs.costs_ready).lower()}"
            ),
            f"Report status: {deck.status}",
            f"Unsupported/report-only feature codes: {unsupported}",
            bundle_line,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run backend-only PvP ruleset/balance application smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print compact JSON.")
    parser.add_argument(
        "--account",
        action="store_true",
        help="Use local account deck export instead of synthetic fixture deck.",
    )
    parser.add_argument(
        "--session-bundle",
        action="store_true",
        help="Build a synthetic session bundle and attach a compact balance summary.",
    )
    parser.add_argument(
        "--ruleset",
        default=str(DEFAULT_RULESET_PATH),
        help="Local JSON ruleset path. No network URLs are fetched.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_ruleset_balance_smoke(
            ruleset_path=args.ruleset,
            use_account=args.account,
            include_session_bundle=args.session_bundle,
        )
    except Exception as exc:
        print(f"PvP ruleset balance smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_ruleset_balance_smoke_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
