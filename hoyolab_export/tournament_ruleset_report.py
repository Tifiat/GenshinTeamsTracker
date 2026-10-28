from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .tournament_ruleset import (
    TournamentRulesetV1,
    load_tournament_ruleset_from_csv_paths,
    load_tournament_ruleset_json,
    validate_tournament_ruleset,
)


def build_ruleset_validation_report(
    ruleset: TournamentRulesetV1,
) -> dict[str, Any]:
    return {
        "ruleset": {
            "schema_version": ruleset.schema_version,
            "name": ruleset.name,
            "source": ruleset.source,
            "source_url": ruleset.source_url,
            "character_count": len(ruleset.characters),
            "weapon_count": len(ruleset.weapons),
            "weapon_override_count": len(ruleset.weapon_overrides),
            "tier_count": len(ruleset.tiers),
            "script_code_present": bool(ruleset.draft_config.script_code),
        },
        "validation": validate_tournament_ruleset(ruleset).to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a normalized tournament ruleset JSON/CSV input.",
    )
    parser.add_argument("--ruleset-json")
    parser.add_argument("--name", default="CSV ruleset")
    parser.add_argument("--characters-csv")
    parser.add_argument("--weapons-csv")
    parser.add_argument("--tiers-csv")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    if args.ruleset_json:
        ruleset = load_tournament_ruleset_json(Path(args.ruleset_json))
    else:
        ruleset = load_tournament_ruleset_from_csv_paths(
            name=args.name,
            characters_csv=args.characters_csv,
            weapons_csv=args.weapons_csv,
            tiers_csv=args.tiers_csv,
        )
    print(
        json.dumps(
            build_ruleset_validation_report(ruleset),
            ensure_ascii=False,
            indent=args.indent,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
