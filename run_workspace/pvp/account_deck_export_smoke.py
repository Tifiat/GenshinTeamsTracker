"""Dry-run smoke for exporting a Free Draft deck from local account data."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .account_deck_export import (
    AccountDeckDataProvider,
    AccountDeckExportOptions,
    AccountDeckExportReport,
    LocalAccountSQLiteDeckDataProvider,
    default_account_deck_output_path,
    export_free_draft_deck_from_account,
    write_account_draft_deck,
)


class AccountDeckExportSmokeError(RuntimeError):
    """Raised when account deck export cannot produce a usable local deck."""


@dataclass(frozen=True, slots=True)
class AccountDeckExportSmokeReport:
    export_report: AccountDeckExportReport
    wrote_file: bool = False
    output_path: str = ""

    @property
    def ready(self) -> bool:
        return self.export_report.validation_report.ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "wrote_file": self.wrote_file,
            "output_path": self.output_path,
            "export_report": self.export_report.to_dict(),
        }


def run_account_deck_export_smoke(
    *,
    provider: AccountDeckDataProvider | None = None,
    options: AccountDeckExportOptions | None = None,
    write: bool = False,
    output_path: str | Path | None = None,
) -> AccountDeckExportSmokeReport:
    options = options or AccountDeckExportOptions()
    report = export_free_draft_deck_from_account(
        provider or LocalAccountSQLiteDeckDataProvider(),
        options=options,
    )
    wrote_file = False
    final_output_path = ""
    if write:
        if not report.validation_report.ready:
            raise AccountDeckExportSmokeError(
                "Refusing to write an invalid PvP deck JSON."
            )
        target = (
            Path(output_path)
            if output_path is not None
            else default_account_deck_output_path(
                exported_at_utc=report.deck.source.exported_at_utc
            )
        )
        final_output_path = str(write_account_draft_deck(report.deck, target))
        wrote_file = True
    return AccountDeckExportSmokeReport(
        export_report=report,
        wrote_file=wrote_file,
        output_path=final_output_path,
    )


def format_account_deck_export_smoke_report(
    report: AccountDeckExportSmokeReport,
) -> str:
    export = report.export_report
    counts = export.counts
    source = export.source_summary
    export_issue_codes = ", ".join(export.issue_codes()) or "none"
    validation_issue_codes = ", ".join(export.validation_report.issue_codes()) or "none"
    output_line = (
        f"Output: {report.output_path}"
        if report.wrote_file
        else "Output: dry-run, no files written"
    )
    return "\n".join(
        (
            "PvP account deck export smoke",
            (
                "Source: "
                f"provider={source.get('provider', 'unknown')}, "
                f"db_exists={str(source.get('db_exists', 'n/a')).lower()}"
            ),
            (
                "Exported: "
                f"characters={counts.characters_exported}/{counts.characters_seen}, "
                f"weapons={counts.weapons_exported}/{counts.weapon_stacks_seen}, "
                f"traveler_skipped={counts.traveler_entries_skipped}, "
                f"missing_id_skipped={counts.entries_skipped_missing_id}, "
                f"invalid_skipped={counts.entries_skipped_unsupported_shape}, "
                f"weapon_rows_merged={counts.weapon_stack_rows_merged}"
            ),
            (
                "Validation: "
                f"ready={str(export.validation_report.ready).lower()}, "
                f"status={export.validation_report.status}"
            ),
            f"Export issue codes: {export_issue_codes}",
            f"Validation issue codes: {validation_issue_codes}",
            output_line,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run backend-only PvP Free Draft deck export from local account "
            "SQLite runtime data."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    parser.add_argument("--db", default="", help="Optional account SQLite DB path.")
    parser.add_argument("--deck-name", default="", help="Deck name metadata.")
    parser.add_argument("--nickname", default="", help="Optional player nickname metadata.")
    parser.add_argument(
        "--language",
        default="unknown",
        help="Privacy-safe display language metadata to place in the deck source.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the exported deck JSON instead of dry-run only.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Implies --write.",
    )
    args = parser.parse_args(argv)

    options = AccountDeckExportOptions(
        deck_name=args.deck_name or "Local Account Free Draft Deck",
        nickname=args.nickname,
        language=args.language,
    )
    provider = LocalAccountSQLiteDeckDataProvider(args.db or None)
    try:
        report = run_account_deck_export_smoke(
            provider=provider,
            options=options,
            write=bool(args.write or args.output),
            output_path=args.output or None,
        )
    except Exception as exc:
        print(f"PvP account deck export smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_account_deck_export_smoke_report(report))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
