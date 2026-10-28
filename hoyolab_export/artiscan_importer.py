from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    create_artifact_import_batch,
    find_artifact_id_by_content_fingerprint,
    init_db,
    replace_substats,
    update_artifact_import_batch_summary,
    upsert_artifact,
)
from .artifact_fingerprint import artifact_content_fingerprint
from .artifact_set_catalog import ensure_artifact_set_catalog
from .artifact_stats import (
    artiscan_max_main_stat_value,
    artiscan_property_type,
    format_artiscan_substat_value,
    property_name,
)


ARTISCAN_SLOT_TO_POS = {
    "flower": 1,
    "plume": 2,
    "sands": 3,
    "goblet": 4,
    "circlet": 5,
}

ARTIFACT_POSITION_NAMES = {
    1: "Flower",
    2: "Plume",
    3: "Sands",
    4: "Goblet",
    5: "Circlet",
}


def _counter_increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _artiscan_root_info(payload: dict[str, Any]) -> tuple[str, str, str]:
    export_format = str(payload.get("format") or "").strip()
    source = str(payload.get("source") or "").strip()
    version = str(payload.get("version") or "").strip()

    if export_format.casefold() != "good" or source.casefold() != "artiscan":
        raise RuntimeError(
            "Unsupported artifact JSON format: "
            f"format={export_format!r}, source={source!r}"
        )

    if not isinstance(payload.get("artifacts"), list):
        raise RuntimeError("Artiscan JSON has no artifacts array")

    return export_format, source, version


def _resolve_artiscan_set(conn, set_key: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT set_uid, fallback_name
        FROM artifact_sets
        WHERE artiscan_set_key = ?
        """,
        (set_key,),
    ).fetchone()
    if row is None:
        return None
    return str(row["set_uid"]), str(row["fallback_name"] or row["set_uid"])


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_artiscan_artifact(
    conn,
    artifact: dict[str, Any],
    *,
    index: int,
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        summary["skipped_invalid"] += 1
        summary["errors"].append(f"artifact[{index}]: expected object")
        return None

    slot_key = str(artifact.get("slotKey") or "").strip()
    pos = ARTISCAN_SLOT_TO_POS.get(slot_key)
    if pos is None:
        summary["skipped_invalid"] += 1
        _counter_increment(summary["missing_slot_mappings"], slot_key or "<empty>")
        return None

    set_key = str(artifact.get("setKey") or "").strip()
    set_info = _resolve_artiscan_set(conn, set_key)
    if set_info is None:
        summary["skipped_invalid"] += 1
        _counter_increment(summary["missing_set_mappings"], set_key or "<empty>")
        return None
    set_uid, set_name = set_info

    rarity = _parse_int(artifact.get("rarity"))
    level = _parse_int(artifact.get("level"))
    main_stat_key = str(artifact.get("mainStatKey") or "").strip()
    main_property_type = artiscan_property_type(main_stat_key)
    main_property_value = (
        artiscan_max_main_stat_value(rarity, main_stat_key)
        if rarity is not None
        else None
    )

    if main_property_type is None or not main_property_value:
        summary["skipped_invalid"] += 1
        _counter_increment(
            summary["missing_stat_mappings"],
            f"{rarity or '<rarity>'}:{main_stat_key or '<empty>'}",
        )
        return None

    substats = []
    for substat_index, substat in enumerate(artifact.get("substats") or []):
        if not isinstance(substat, dict):
            summary["errors"].append(
                f"artifact[{index}].substats[{substat_index}]: expected object"
            )
            continue

        stat_key = str(substat.get("key") or "").strip()
        property_type = artiscan_property_type(stat_key)
        value = format_artiscan_substat_value(stat_key, substat.get("value"))

        if property_type is None or not value:
            _counter_increment(
                summary["missing_stat_mappings"],
                stat_key or "<empty>",
            )
            continue

        substats.append(
            {
                "property_type": property_type,
                "property_name": property_name(property_type),
                "value": value,
                "times": None,
            }
        )

    content_fingerprint = artifact_content_fingerprint(
        set_uid=set_uid,
        pos=pos,
        rarity=rarity,
        level=level,
        main_property_type=main_property_type,
        main_property_value=main_property_value,
        substats=substats,
    )
    pos_name = ARTIFACT_POSITION_NAMES[pos]

    return {
        "fingerprint": f"artiscan:{content_fingerprint}",
        "content_fingerprint": content_fingerprint,
        "relic_id": None,
        "name": f"{set_name} {pos_name}",
        "set_id": None,
        "set_uid": set_uid,
        "set_name": set_name,
        "pos": pos,
        "pos_name": pos_name,
        "rarity": rarity,
        "level": level,
        "main_property_type": main_property_type,
        "main_property_name": property_name(main_property_type),
        "main_property_value": main_property_value,
        "substats": substats,
    }


def import_artiscan_file(
    input_path: str | Path,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    input_path = Path(input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Artiscan JSON root must be an object")

    export_format, source, version = _artiscan_root_info(payload)
    artifacts = payload["artifacts"]

    summary: dict[str, Any] = {
        "source_file": str(input_path),
        "format": export_format,
        "source": source,
        "version": version,
        "total": len(artifacts),
        "inserted": 0,
        "skipped_duplicates": 0,
        "skipped_invalid": 0,
        "missing_set_mappings": {},
        "missing_stat_mappings": {},
        "missing_slot_mappings": {},
        "errors": [],
        "batch_id": None,
    }

    ensure_artifact_set_catalog(db_path=db_path, allow_network=False)

    with connect_db(db_path) as conn:
        init_db(conn)
        batch_id = create_artifact_import_batch(
            conn,
            source="artiscan",
            format=export_format,
            source_file=str(input_path),
            summary=summary,
        )
        summary["batch_id"] = batch_id

        for index, artifact in enumerate(artifacts):
            normalized = _normalize_artiscan_artifact(
                conn,
                artifact,
                index=index,
                summary=summary,
            )
            if normalized is None:
                continue

            if find_artifact_id_by_content_fingerprint(
                conn,
                normalized["content_fingerprint"],
            ):
                summary["skipped_duplicates"] += 1
                continue

            artifact_id, inserted = upsert_artifact(
                conn,
                fingerprint=normalized["fingerprint"],
                content_fingerprint=normalized["content_fingerprint"],
                relic_id=normalized["relic_id"],
                name=normalized["name"],
                set_id=normalized["set_id"],
                set_uid=normalized["set_uid"],
                set_name=normalized["set_name"],
                pos=normalized["pos"],
                pos_name=normalized["pos_name"],
                rarity=normalized["rarity"],
                level=normalized["level"],
                main_property_type=normalized["main_property_type"],
                main_property_name=normalized["main_property_name"],
                main_property_value=normalized["main_property_value"],
                import_source="artiscan",
                import_format=export_format,
                import_batch_id=batch_id,
                json_imported=True,
            )
            if inserted:
                summary["inserted"] += 1
                replace_substats(conn, artifact_id, normalized["substats"])
            else:
                summary["skipped_duplicates"] += 1

        update_artifact_import_batch_summary(conn, batch_id, summary)
        conn.commit()

    return summary
