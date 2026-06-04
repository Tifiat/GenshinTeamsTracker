"""Switch AppShell's current Abyss period to an existing cached source-data period.

This is a future/debug utility, not a production runtime path. It only rewrites
the local period reference consumed by AppShell and never fetches or mutates the
source-data cache itself.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_workspace.abyss.source_data_cache import (  # noqa: E402
    DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR,
    cached_abyss_floor_source_data_path,
    load_cached_abyss_floor_source_data,
)
from run_workspace.abyss.source_data_runtime import (  # noqa: E402
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    read_cached_hoyolab_abyss_period,
)


DEBUG_PERIOD_SOURCE = "tools_future_abyss_period_switch"
DEBUG_WARNING = "debug_period_override_from_cached_source_data"
BACKUP_SUFFIX = ".debug_backup.json"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True, slots=True)
class PeriodSwitchResult:
    status: str
    period_start: str | None = None
    period_end: str | None = None
    floor: int | None = None
    period_path: str | None = None
    cache_path: str | None = None
    backup_path: str | None = None
    backup_status: str = ""
    dry_run: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodStart": self.period_start,
            "periodEnd": self.period_end,
            "floor": self.floor,
            "periodPath": self.period_path,
            "cachePath": self.cache_path,
            "backupPath": self.backup_path,
            "backupStatus": self.backup_status,
            "dryRun": self.dry_run,
            "warnings": list(self.warnings),
        }


def list_cached_periods(
    *,
    floor: int = 12,
    cache_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    base_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR
    if not base_dir.is_dir():
        return []
    periods: list[dict[str, Any]] = []
    for period_dir in sorted(base_dir.iterdir(), key=lambda path: path.name):
        if not period_dir.is_dir() or not DATE_PATTERN.fullmatch(period_dir.name):
            continue
        path = cached_abyss_floor_source_data_path(
            period_dir.name,
            floor=floor,
            cache_dir=base_dir,
        )
        if not path.is_file():
            continue
        item: dict[str, Any] = {
            "periodStart": period_dir.name,
            "floor": floor,
            "cachePath": str(path),
        }
        try:
            data = load_cached_abyss_floor_source_data(
                period_dir.name,
                floor=floor,
                cache_dir=base_dir,
            )
        except Exception as exc:  # pragma: no cover - defensive debug report path
            item["warning"] = f"cache_unreadable:{type(exc).__name__}"
        else:
            if data is not None:
                item["periodEnd"] = data.period.end_date
                item["enemyRows"] = len(data.enemy_rows)
                item["matched"] = data.matched_count
                item["unmatched"] = data.unmatched_count
                item["ambiguous"] = data.ambiguous_count
        periods.append(item)
    return periods


def switch_current_period_to_cached_source_data(
    period_start: str,
    *,
    floor: int = 12,
    cache_dir: str | Path | None = None,
    period_path: str | Path | None = None,
    backup_path: str | Path | None = None,
    write_backup: bool = True,
    replace_backup: bool = False,
    dry_run: bool = False,
) -> PeriodSwitchResult:
    normalized_period = _normalize_period_start(period_start)
    cache_base = Path(cache_dir) if cache_dir is not None else DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR
    target_period_path = (
        Path(period_path) if period_path is not None else DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    )
    target_backup_path = (
        Path(backup_path)
        if backup_path is not None
        else target_period_path.with_name(target_period_path.name + BACKUP_SUFFIX)
    )
    cache_path = cached_abyss_floor_source_data_path(
        normalized_period,
        floor=floor,
        cache_dir=cache_base,
    )
    data = load_cached_abyss_floor_source_data(
        normalized_period,
        floor=floor,
        cache_dir=cache_base,
    )
    if data is None:
        raise SystemExit(
            f"Cached Abyss source-data does not exist for {normalized_period} floor {floor}: "
            f"{cache_path}"
        )
    current_period = read_cached_hoyolab_abyss_period(target_period_path)

    backup_status = ""
    if write_backup and target_period_path.is_file():
        if target_backup_path.exists() and not replace_backup:
            backup_status = "preserved_existing"
        else:
            backup_status = "would_create" if dry_run else "created"
            if not dry_run:
                target_backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_period_path, target_backup_path)
    elif write_backup:
        backup_status = "no_current_period_file"
    else:
        backup_status = "disabled"

    period_end = _period_end_for_payload(
        data.period.start_date,
        data.period.end_date,
        current_period_end=(
            current_period.end_date
            if current_period is not None
            and current_period.start_date == data.period.start_date
            else None
        ),
    )
    payload = _period_payload_from_cached_data(
        data,
        cache_path=cache_path,
        period_end=period_end,
    )
    if not dry_run:
        target_period_path.parent.mkdir(parents=True, exist_ok=True)
        target_period_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return PeriodSwitchResult(
        status="would_switch" if dry_run else "switched",
        period_start=data.period.start_date,
        period_end=period_end,
        floor=data.floor,
        period_path=str(target_period_path),
        cache_path=str(cache_path),
        backup_path=str(target_backup_path) if write_backup else None,
        backup_status=backup_status,
        dry_run=dry_run,
        warnings=(DEBUG_WARNING,),
    )


def restore_period_backup(
    *,
    period_path: str | Path | None = None,
    backup_path: str | Path | None = None,
    dry_run: bool = False,
) -> PeriodSwitchResult:
    target_period_path = (
        Path(period_path) if period_path is not None else DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    )
    target_backup_path = (
        Path(backup_path)
        if backup_path is not None
        else target_period_path.with_name(target_period_path.name + BACKUP_SUFFIX)
    )
    if not target_backup_path.is_file():
        raise SystemExit(f"Backup period file does not exist: {target_backup_path}")
    if not dry_run:
        target_period_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_backup_path, target_period_path)
    period = read_cached_hoyolab_abyss_period(target_backup_path)
    return PeriodSwitchResult(
        status="would_restore_backup" if dry_run else "restored_backup",
        period_start=None if period is None else period.start_date,
        period_end=None if period is None else period.end_date,
        period_path=str(target_period_path),
        backup_path=str(target_backup_path),
        backup_status="used",
        dry_run=dry_run,
    )


def current_period_report(
    *,
    period_path: str | Path | None = None,
) -> dict[str, Any]:
    target_period_path = (
        Path(period_path) if period_path is not None else DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    )
    period = read_cached_hoyolab_abyss_period(target_period_path)
    return {
        "periodPath": str(target_period_path),
        "exists": target_period_path.is_file(),
        "periodStart": None if period is None else period.start_date,
        "periodEnd": None if period is None else period.end_date,
        "rawPeriod": None if period is None else period.raw_period,
        "sourcePath": None if period is None else period.source_path,
    }


def _period_payload_from_cached_data(
    data: Any,
    *,
    cache_path: Path,
    period_end: str | None,
) -> dict[str, Any]:
    raw_period = data.period.start_date
    if period_end:
        raw_period = f"{data.period.start_date}/{period_end}"
    return {
        "rawPeriod": raw_period,
        "startDate": data.period.start_date,
        "endDate": period_end,
        "sourcePath": str(cache_path),
        "source": DEBUG_PERIOD_SOURCE,
        "warnings": [DEBUG_WARNING],
        "fallback": True,
        "sourceMetadata": {
            "tool": "tools/future/abyss_period_switch.py",
            "cachePath": str(cache_path),
            "floor": data.floor,
            "switchedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }


def _period_end_for_payload(
    period_start: str,
    cached_period_end: str | None,
    *,
    current_period_end: str | None = None,
) -> str | None:
    if current_period_end:
        return current_period_end
    return _safe_monthly_period_end(period_start, cached_period_end)


def _safe_monthly_period_end(period_start: str, period_end: str | None) -> str | None:
    start_date = _date_from_text(period_start)
    end_date = _date_from_text(period_end)
    if start_date is None or end_date is None:
        return None
    if (end_date - start_date).days < 20:
        return None
    return end_date.isoformat()


def _date_from_text(value: str | None) -> date | None:
    if not value:
        return None
    match = DATE_PATTERN.search(str(value))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_period_start(period_start: str) -> str:
    match = DATE_PATTERN.fullmatch(str(period_start).strip())
    if not match:
        raise SystemExit(f"Unsupported period start date: {period_start!r}")
    return match.group(0)


def _print_report(report: Any, *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if isinstance(report, list):
        if not report:
            print("No cached Abyss source-data periods found.")
            return
        for item in report:
            print(
                f"{item.get('periodStart')} floor={item.get('floor')} "
                f"rows={item.get('enemyRows')} matched={item.get('matched')} "
                f"cache={item.get('cachePath')}"
            )
        return
    if isinstance(report, PeriodSwitchResult):
        report = report.to_dict()
    if isinstance(report, dict):
        for key, value in report.items():
            print(f"{key}={value}")
        return
    print(str(report))


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Switch AppShell's current Abyss period reference to an already "
            "cached source-data period. This tool does not fetch network data."
        )
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="List cached source-data periods.")
    action.add_argument("--show-current", action="store_true", help="Show the current AppShell period reference.")
    action.add_argument("--period-start", help="Switch to this cached period start date YYYY-MM-DD.")
    action.add_argument("--restore-backup", action="store_true", help="Restore the debug backup period file.")
    parser.add_argument("--floor", type=int, default=12, help="Abyss floor. Default: 12.")
    parser.add_argument("--cache-dir", help="Override source-data cache root.")
    parser.add_argument("--period-path", help="Override AppShell period-ref path.")
    parser.add_argument("--backup-path", help="Override debug backup path.")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup the current period file before switching.")
    parser.add_argument("--replace-backup", action="store_true", help="Replace an existing debug backup before switching.")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without writing files.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    if args.list:
        report = list_cached_periods(floor=args.floor, cache_dir=args.cache_dir)
    elif args.show_current:
        report = current_period_report(period_path=args.period_path)
    elif args.restore_backup:
        report = restore_period_backup(
            period_path=args.period_path,
            backup_path=args.backup_path,
            dry_run=args.dry_run,
        )
    else:
        report = switch_current_period_to_cached_source_data(
            args.period_start,
            floor=args.floor,
            cache_dir=args.cache_dir,
            period_path=args.period_path,
            backup_path=args.backup_path,
            write_backup=not args.no_backup,
            replace_backup=args.replace_backup,
            dry_run=args.dry_run,
        )
    _print_report(
        report.to_dict() if isinstance(report, PeriodSwitchResult) else report,
        output_format=args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
