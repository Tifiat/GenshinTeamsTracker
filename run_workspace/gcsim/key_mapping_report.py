"""Dev report for the tiny committed GCSIM key-mapping seed.

This backend-only CLI reports explicit seed coverage. It does not fetch data,
scan account/runtime state, infer keys from names, generate GCSIM configs, or
claim production-complete mapping coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .key_mapping import (
    DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH,
    GcsimKeyMappingReport,
    build_key_mapping_report,
    load_default_mapping_seed_records,
    load_mapping_records_from_json,
)


def build_default_key_mapping_report(
    *,
    production_mapping_source_present: bool = False,
) -> GcsimKeyMappingReport:
    return build_key_mapping_report(
        load_default_mapping_seed_records(),
        production_mapping_source_present=production_mapping_source_present,
    )


def build_key_mapping_report_from_seed(
    seed_path: str | Path | None = None,
    *,
    production_mapping_source_present: bool = False,
) -> GcsimKeyMappingReport:
    records = (
        load_default_mapping_seed_records()
        if seed_path is None
        else load_mapping_records_from_json(seed_path)
    )
    return build_key_mapping_report(
        records,
        production_mapping_source_present=production_mapping_source_present,
    )


def format_key_mapping_report_text(
    report: GcsimKeyMappingReport,
    *,
    seed_path: str | Path | None = None,
) -> str:
    report_dict = report.to_dict()
    lines = [
        "GCSIM key mapping report",
        f"seed={seed_path or DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH}",
        f"total={report.total}",
        "counts:",
    ]
    counts = report.counts_by_entity_status
    if counts:
        for entity_type, status_counts in counts.items():
            status_text = ", ".join(
                f"{status}={count}"
                for status, count in status_counts.items()
            )
            lines.append(f"  {entity_type}: {status_text}")
    else:
        lines.append("  none")
    lines.extend(
        [
            f"missing={len(report.missing_records)}",
            f"ambiguous={len(report.ambiguous_records)}",
        ]
    )
    warnings = report_dict.get("warnings", {})
    if warnings:
        warning_text = ", ".join(
            f"{key}={value}"
            for key, value in sorted(warnings.items())
        )
        lines.append(f"warnings={warning_text}")
    else:
        lines.append("warnings=none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report the explicit GCSIM key-mapping seed coverage.",
    )
    parser.add_argument(
        "--seed",
        default=None,
        help="Optional explicit GCSIM key mapping seed JSON path.",
    )
    parser.add_argument(
        "--trusted-production-source",
        action="store_true",
        help=(
            "Suppress production_mapping_data_missing only for a trusted "
            "complete production source. Do not use for the default dev seed."
        ),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = build_key_mapping_report_from_seed(
        args.seed,
        production_mapping_source_present=args.trusted_production_source,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=True, sort_keys=True))
    else:
        print(format_key_mapping_report_text(report, seed_path=args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
