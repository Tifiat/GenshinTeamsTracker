from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .artifact_build_snapshot import ArtifactBuildSnapshot, build_artifact_build_snapshot
from .artifact_db import (
    ARTIFACT_DB_PATH,
    calculate_raw_build_summary,
    get_build_preset,
    list_build_presets,
)
from .character_stat_snapshot_smoke import (
    build_character_stat_snapshot_smoke_report_from_paths,
)


ARTIFACT_BUILD_SNAPSHOT_SMOKE_SCHEMA_VERSION = 1

ERROR_AMBIGUOUS_BUILD_NAME = "ambiguous_build_name"
ERROR_BUILD_PRESET_NOT_FOUND = "build_preset_not_found"
ERROR_BUILD_SELECTOR_REQUIRED = "build_selector_required"

WARNING_CHARACTER_SNAPSHOT_SMOKE_SKIPPED = "character_snapshot_smoke_skipped"


class ArtifactBuildSnapshotSmokeError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "details": self.details,
        }


def build_artifact_build_snapshot_smoke_report_from_db(
    *,
    build_id: int | None = None,
    build_name: str | None = None,
    db_path: str | Path = ARTIFACT_DB_PATH,
    include_character_snapshot: bool = True,
) -> dict[str, Any]:
    with closing(_connect_readonly_db(db_path)) as conn:
        preset = select_build_preset_for_smoke(
            conn,
            build_id=build_id,
            build_name=build_name,
        )
        summary = calculate_raw_build_summary(conn, build_id=int(preset["id"]))

    artifact_snapshot = build_artifact_build_snapshot(
        summary,
        build_preset=preset,
    )
    report = build_artifact_build_snapshot_smoke_report(
        build_preset=preset,
        raw_summary=summary,
        artifact_snapshot=artifact_snapshot,
        db_path=db_path,
    )

    if include_character_snapshot:
        report["character_snapshot_smoke"] = _character_snapshot_smoke(
            artifact_snapshot,
        )

    return report


def select_build_preset_for_smoke(
    conn: sqlite3.Connection,
    *,
    build_id: int | None = None,
    build_name: str | None = None,
) -> dict[str, Any]:
    if build_id is not None:
        preset = get_build_preset(conn, int(build_id))
        if preset is None:
            raise ArtifactBuildSnapshotSmokeError(
                ERROR_BUILD_PRESET_NOT_FOUND,
                f"Build preset id {int(build_id)} was not found.",
                details={"build_id": int(build_id)},
            )
        return preset

    name = str(build_name or "").strip()
    if not name:
        raise ArtifactBuildSnapshotSmokeError(
            ERROR_BUILD_SELECTOR_REQUIRED,
            "Pass --build-id or --build-name for artifact build snapshot smoke.",
        )

    matches = [
        preset
        for preset in list_build_presets(conn)
        if str(preset.get("name") or "") == name
    ]
    if not matches:
        raise ArtifactBuildSnapshotSmokeError(
            ERROR_BUILD_PRESET_NOT_FOUND,
            f"Build preset named {name!r} was not found.",
            details={"build_name": name},
        )
    if len(matches) > 1:
        raise ArtifactBuildSnapshotSmokeError(
            ERROR_AMBIGUOUS_BUILD_NAME,
            f"Build preset name {name!r} matched multiple presets.",
            details={
                "build_name": name,
                "matching_build_ids": [int(item["id"]) for item in matches],
            },
        )
    return get_build_preset(conn, int(matches[0]["id"])) or matches[0]


def build_artifact_build_snapshot_smoke_report(
    *,
    build_preset: dict[str, Any],
    raw_summary: dict[str, Any],
    artifact_snapshot: ArtifactBuildSnapshot,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    snapshot = artifact_snapshot.to_dict()
    return {
        "schema_version": ARTIFACT_BUILD_SNAPSHOT_SMOKE_SCHEMA_VERSION,
        "source_notes": {
            "artifact_db": Path(db_path).name,
            "db_read": True,
            "readonly_db_connection": True,
            "network_fetch": False,
            "ui_access": False,
            "sanitized": True,
            "identity_note": (
                "Build name is accepted only for explicit smoke/debug selection. "
                "Final app flows must pass build_id internally."
            ),
        },
        "selected_build": {
            "id": int(build_preset["id"]),
            "name": str(build_preset.get("name") or ""),
            "slot_count": len(build_preset.get("slots") or []),
            "target_count": len(build_preset.get("targets") or []),
        },
        "raw_summary_shape": {
            "keys": sorted(raw_summary.keys()),
            "total_stats_count": len(raw_summary.get("total_stats") or []),
            "set_counts_count": len(raw_summary.get("set_counts") or []),
        },
        "artifact_build_snapshot": {
            "build_id": snapshot["build_id"],
            "build_name": snapshot["build_name"],
            "artifact_ids_by_pos": snapshot["artifact_ids_by_pos"],
            "slot_count": len(snapshot["slots"]),
            "missing_positions": snapshot["missing_positions"],
            "set_counts": snapshot["set_counts"],
            "active_set_bonuses": snapshot["active_set_bonuses"],
            "stat_totals": snapshot["stat_totals"],
            "crit_value": snapshot["crit_value"],
            "proc_count": snapshot["proc_count"],
            "warnings": snapshot["warnings"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sanitized ArtifactBuildSnapshot smoke report from an "
            "explicit Artifact Browser build preset."
        )
    )
    parser.add_argument("--build-id", type=int, default=None)
    parser.add_argument("--build-name", default=None)
    parser.add_argument("--db-path", default=str(ARTIFACT_DB_PATH))
    parser.add_argument(
        "--no-character-snapshot",
        action="store_true",
        help="Skip optional CharacterStatSnapshot integration smoke.",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = build_artifact_build_snapshot_smoke_report_from_db(
            build_id=args.build_id,
            build_name=args.build_name,
            db_path=args.db_path,
            include_character_snapshot=not args.no_character_snapshot,
        )
    except ArtifactBuildSnapshotSmokeError as exc:
        _write_json(exc.to_dict(), output=args.output, stderr=True)
        return 1
    except Exception as exc:
        _write_json(
            {
                "error": "artifact_build_snapshot_smoke_failed",
                "message": str(exc),
            },
            output=args.output,
            stderr=True,
        )
        return 1

    _write_json(report, output=args.output)
    return 0


def _character_snapshot_smoke(
    artifact_snapshot: ArtifactBuildSnapshot,
) -> dict[str, Any]:
    try:
        character_report = build_character_stat_snapshot_smoke_report_from_paths(
            limit=1,
            artifact_summary=artifact_snapshot,
        )
    except Exception as exc:
        return {
            "warnings": [WARNING_CHARACTER_SNAPSHOT_SMOKE_SKIPPED],
            "error": str(exc),
        }

    snapshots = character_report.get("snapshots") or []
    if not snapshots:
        return {
            "warnings": [WARNING_CHARACTER_SNAPSHOT_SMOKE_SKIPPED],
            "selection": character_report.get("selection"),
        }

    snapshot = snapshots[0]
    artifact = snapshot.get("artifact") or {}
    artifact_summary = artifact.get("summary") or {}
    return {
        "language": character_report.get("language"),
        "account_character": snapshot.get("account_character"),
        "character_catalog": snapshot.get("character_catalog"),
        "status": snapshot.get("status"),
        "artifact_present": bool(artifact_summary),
        "artifact_build_id": artifact_summary.get("build_id"),
        "artifact_build_name": artifact_summary.get("build_name"),
        "artifact_missing_positions": artifact_summary.get("missing_positions"),
        "artifact_warnings": artifact.get("warnings", []),
        "snapshot_warnings": snapshot.get("warnings", []),
        "observations": snapshot.get("observations", {}),
    }


def _connect_readonly_db(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    uri_path = quote(resolved.as_posix(), safe="/:")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_json(data: dict[str, Any], *, output: str | None = None, stderr: bool = False) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        return

    stream = sys.stderr if stderr else sys.stdout
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass
    stream.write(text)
    stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
