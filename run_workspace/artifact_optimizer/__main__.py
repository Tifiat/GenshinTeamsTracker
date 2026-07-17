from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from hoyolab_export.artifact_stats import CRIT_DAMAGE, CRIT_RATE

from .models import ArtifactOptimizationRequest, ArtifactSetRequirement
from .repository import optimize_artifacts_from_db


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        weights = _parse_pairs(args.weight, value_type=float)
        if not weights:
            # Existing project Crit Value convention: 2 * CRIT Rate + CRIT DMG.
            weights = {CRIT_RATE: 2.0, CRIT_DAMAGE: 1.0}
        minimum_stats = _parse_pairs(args.minimum_stat, value_type=float)
        fixed = _parse_pairs(args.fixed, value_type=int)
        allowed_main_stats = _parse_allowed_main_stats(args.main_stat)
        set_requirements = tuple(
            ArtifactSetRequirement(set_key=key, minimum_count=int(value))
            for key, value in _parse_text_pairs(args.require_set).items()
        )
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    request = ArtifactOptimizationRequest(
        weights=weights,
        top_k=args.top_k,
        minimum_stats=minimum_stats,
        set_requirements=set_requirements,
        fixed_artifact_ids_by_pos=fixed,
        excluded_artifact_ids=frozenset(args.exclude),
        allowed_main_stats_by_pos=allowed_main_stats,
        minimum_rarity=args.minimum_rarity,
        minimum_level=args.minimum_level,
        allow_equipped_artifacts=not args.exclude_equipped,
        target_character_id=args.target_character_id,
        per_slot_limit=None if args.exact else args.per_slot_limit,
        per_set_limit=None if args.exact else args.per_set_limit,
        max_combinations=(
            None if args.max_combinations == 0 else args.max_combinations
        ),
    )
    report = optimize_artifacts_from_db(
        request,
        db_path=Path(args.db_path),
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Search real account artifacts with an additive stat proxy. "
            "Without --weight, uses the project's Crit Value proxy."
        )
    )
    parser.add_argument("--db-path", default=str(ARTIFACT_DB_PATH))
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="PROPERTY_TYPE=WEIGHT",
    )
    parser.add_argument(
        "--minimum-stat",
        action="append",
        default=[],
        metavar="PROPERTY_TYPE=VALUE",
    )
    parser.add_argument(
        "--require-set",
        action="append",
        default=[],
        metavar="SET_KEY=COUNT",
    )
    parser.add_argument(
        "--main-stat",
        action="append",
        default=[],
        metavar="POS=PROPERTY_TYPE[,PROPERTY_TYPE]",
    )
    parser.add_argument(
        "--fixed",
        action="append",
        default=[],
        metavar="POS=ARTIFACT_ID",
    )
    parser.add_argument("--exclude", action="append", type=int, default=[])
    parser.add_argument("--exclude-equipped", action="store_true")
    parser.add_argument("--target-character-id", type=int)
    parser.add_argument("--minimum-rarity", type=int)
    parser.add_argument("--minimum-level", type=int)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--per-slot-limit", type=int, default=32)
    parser.add_argument("--per-set-limit", type=int, default=8)
    parser.add_argument("--max-combinations", type=int, default=2_000_000)
    parser.add_argument(
        "--exact",
        action="store_true",
        help="Disable lossy candidate shortlisting (combination cap still applies).",
    )
    return parser


def _parse_pairs(
    values: Iterable[str],
    *,
    value_type,
) -> dict[int, float] | dict[int, int]:
    result = {}
    for item in values:
        key, value = _split_pair(item)
        result[int(key)] = value_type(value)
    return result


def _parse_text_pairs(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in values:
        key, value = _split_pair(item)
        result[key.strip()] = int(value)
    return result


def _parse_allowed_main_stats(
    values: Iterable[str],
) -> dict[int, frozenset[int]]:
    result: dict[int, frozenset[int]] = {}
    for item in values:
        key, value = _split_pair(item)
        result[int(key)] = frozenset(
            int(part.strip()) for part in value.split(",") if part.strip()
        )
    return result


def _split_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"Expected KEY=VALUE, got {value!r}")
    key, item_value = value.split("=", 1)
    if not key.strip() or not item_value.strip():
        raise argparse.ArgumentTypeError(f"Expected KEY=VALUE, got {value!r}")
    return key.strip(), item_value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
