from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any

from hoyolab_export.artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    build_artifact_build_snapshot,
)
from hoyolab_export.artifact_db import (
    ARTIFACT_DB_PATH,
    calculate_raw_build_summary,
)

from .models import (
    ArtifactBuildCandidate,
    ArtifactOptimizationReport,
    ArtifactOptimizationRequest,
    OptimizerArtifact,
)
from .solver import FinalBuildEvaluator, optimize_artifacts


def connect_artifact_db_readonly(
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def load_optimizer_artifacts(
    conn: sqlite3.Connection,
) -> tuple[OptimizerArtifact, ...]:
    artifact_rows = conn.execute(
        """
        SELECT
            id,
            name,
            set_uid,
            set_name,
            pos,
            rarity,
            level,
            main_property_type,
            main_property_value
        FROM artifacts
        WHERE pos IN (1, 2, 3, 4, 5)
        ORDER BY id
        """
    ).fetchall()
    stats_by_artifact: defaultdict[int, defaultdict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in artifact_rows:
        property_type = _optional_int(row["main_property_type"])
        if property_type is not None:
            stats_by_artifact[int(row["id"])][property_type] += _raw_stat_value(
                row["main_property_value"]
            )

    if artifact_rows:
        substat_rows = conn.execute(
            """
            SELECT artifact_id, property_type, value
            FROM artifact_substats
            ORDER BY artifact_id, slot_index
            """
        ).fetchall()
        for row in substat_rows:
            property_type = _optional_int(row["property_type"])
            if property_type is None:
                continue
            stats_by_artifact[int(row["artifact_id"])][property_type] += (
                _raw_stat_value(row["value"])
            )

    equipped_by_artifact = _load_equipped_character_ids(conn)
    result: list[OptimizerArtifact] = []
    for row in artifact_rows:
        artifact_id = int(row["id"])
        set_uid = str(row["set_uid"] or "").strip()
        set_name = str(row["set_name"] or "").strip()
        result.append(
            OptimizerArtifact(
                artifact_id=artifact_id,
                pos=int(row["pos"]),
                set_key=_artifact_set_key(
                    artifact_id=artifact_id,
                    set_uid=set_uid,
                    set_name=set_name,
                ),
                set_uid=set_uid,
                set_name=set_name,
                name=str(row["name"] or ""),
                rarity=_optional_int(row["rarity"]),
                level=_optional_int(row["level"]),
                main_property_type=_optional_int(row["main_property_type"]),
                stats=tuple(
                    (property_type, round(float(value), 6))
                    for property_type, value in sorted(
                        stats_by_artifact[artifact_id].items()
                    )
                ),
                equipped_character_ids=equipped_by_artifact.get(
                    artifact_id,
                    (),
                ),
            )
        )
    return tuple(result)


def optimize_artifacts_from_db(
    request: ArtifactOptimizationRequest,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    final_evaluator: FinalBuildEvaluator | None = None,
) -> ArtifactOptimizationReport:
    with closing(connect_artifact_db_readonly(db_path)) as conn:
        artifacts = load_optimizer_artifacts(conn)
    return optimize_artifacts(
        artifacts,
        request,
        final_evaluator=final_evaluator,
    )


def build_candidate_snapshot(
    conn: sqlite3.Connection,
    candidate: ArtifactBuildCandidate,
) -> ArtifactBuildSnapshot:
    summary = calculate_raw_build_summary(
        conn,
        slots=candidate.artifact_id_map(),
    )
    return build_artifact_build_snapshot(summary)


def _load_equipped_character_ids(
    conn: sqlite3.Connection,
) -> dict[int, tuple[int, ...]]:
    table_exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'artifact_equipment'
        """
    ).fetchone()
    if table_exists is None:
        return {}
    rows = conn.execute(
        """
        SELECT artifact_id, character_id
        FROM artifact_equipment
        ORDER BY artifact_id, character_id
        """
    ).fetchall()
    result: defaultdict[int, list[int]] = defaultdict(list)
    for row in rows:
        result[int(row["artifact_id"])].append(int(row["character_id"]))
    return {
        artifact_id: tuple(sorted(set(character_ids)))
        for artifact_id, character_ids in result.items()
    }


def _artifact_set_key(
    *,
    artifact_id: int,
    set_uid: str,
    set_name: str,
) -> str:
    if set_uid:
        return set_uid
    if set_name:
        return f"name:{' '.join(set_name.casefold().split())}"
    # Unknown-set artifacts must not accidentally form a fake 2p/4p set.
    return f"artifact:{artifact_id}"


def _raw_stat_value(value: Any) -> float:
    text = str(value or "").strip().replace("%", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid artifact stat value: {value!r}") from exc


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
