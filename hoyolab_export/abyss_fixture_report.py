from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

from .abyss_sources import (
    AbyssChamberSideReport,
    AbyssPeriodRef,
    build_current_floor_12_fixture_reports_from_wikitext,
    fetch_fandom_wikitext,
    page_title_from_fandom_url,
)


ABYSS_FIXTURE_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class AbyssFixtureReport:
    schema_version: int
    period: AbyssPeriodRef
    chamber_sides: tuple[AbyssChamberSideReport, ...]
    source_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "period": self.period.to_dict(),
            "chamber_sides": [item.to_dict() for item in self.chamber_sides],
            "source_notes": list(self.source_notes),
        }


def build_abyss_fixture_report_from_wikitext(
    wikitext: str,
    *,
    period_url: str,
    floor: int = 12,
) -> AbyssFixtureReport:
    period = AbyssPeriodRef(
        source_url=period_url,
        page_title=page_title_from_fandom_url(period_url),
        floor=floor,
    )
    chamber_sides = build_current_floor_12_fixture_reports_from_wikitext(
        wikitext,
        period_url=period_url,
    )
    return AbyssFixtureReport(
        schema_version=ABYSS_FIXTURE_REPORT_SCHEMA_VERSION,
        period=period,
        chamber_sides=chamber_sides,
        source_notes=(
            "Current Floor 12 known enemy stats are seeded from ABYSS_HP_FIXTURE.md.",
            "2.5x is generic Fandom Floor 12 fallback; 3.75x is source-like Stage12_New2 estimate.",
        ),
    )


def build_abyss_fixture_report_from_period_url(
    period_url: str,
    *,
    floor: int = 12,
) -> AbyssFixtureReport:
    page_title = page_title_from_fandom_url(period_url)
    wikitext = fetch_fandom_wikitext(page_title)
    return build_abyss_fixture_report_from_wikitext(
        wikitext,
        period_url=period_url,
        floor=floor,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a sanitized Abyss Floor 12 fixture report from Fandom.",
    )
    parser.add_argument("--period-url", required=True)
    parser.add_argument("--floor", type=int, default=12)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    report = build_abyss_fixture_report_from_period_url(
        args.period_url,
        floor=args.floor,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
