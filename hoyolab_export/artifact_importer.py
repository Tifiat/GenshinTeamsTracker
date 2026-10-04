import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .artifact_fingerprint import (
    artifact_content_fingerprint,
    artifact_source_content_fingerprint,
    stable_hash,
)
from .artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    init_db,
    replace_current_equipment,
    replace_substats,
    upsert_artifact,
)
from .artifact_set_catalog import (
    UnmappedArtifactSetError,
    ensure_artifact_set_catalog,
    resolve_hoyolab_set_uid,
)


def unwrap_hoyolab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # browser_fetch_json result:
    # { ok, status, json: { retcode, data, ... } }
    if isinstance(payload.get("json"), dict):
        return payload["json"]

    # character_detail_probe result:
    # { request, response: { json: { retcode, data, ... } } }
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("json"), dict):
        return response["json"]

    return payload


def property_name(
    property_map: dict[str, Any],
    property_type: int | None,
) -> str | None:
    if property_type is None:
        return None

    item = property_map.get(str(property_type))
    if not isinstance(item, dict):
        return str(property_type)

    return item.get("name") or item.get("filter_name") or str(property_type)


def normalize_property(
    prop: dict[str, Any] | None,
    property_map: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(prop, dict):
        return None

    property_type = prop.get("property_type")

    return {
        "property_type": property_type,
        "property_name": property_name(property_map, property_type),
        "value": next((prop[key] for key in ("value", "final", "base")
                       if prop.get(key) is not None and prop.get(key) != ""), ""),
        "times": prop.get("times"),
    }


def artifact_fingerprint(
    relic: dict[str, Any],
    main_property: dict[str, Any] | None,
    substats: list[dict[str, Any]],
) -> str:
    relic_set = relic.get("set") if isinstance(relic.get("set"), dict) else {}

    def fingerprint_property(prop: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(prop, dict):
            return None

        return {
            "property_type": prop.get("property_type"),
            "value": prop["value"] if prop.get("value") is not None else "",
            "times": prop.get("times"),
        }

    fingerprint_substats = [
        fingerprint_property(item)
        for item in substats
        if isinstance(item, dict)
    ]

    # character_id intentionally not included:
    # if artifact moves to another character, it should still be the same artifact.
    #
    # Display/localized names intentionally not included:
    # changing HoYoLAB language or property_map name/filter_name must not create duplicates.
    payload = {
        "relic_id": relic.get("id"),
        "set_id": relic_set.get("id"),
        "pos": relic.get("pos"),
        "rarity": relic.get("rarity"),
        "level": relic.get("level"),
        "main_property": fingerprint_property(main_property),
        "substats": sorted(
            fingerprint_substats,
            key=lambda item: (
                item.get("property_type") or 0,
                str(item.get("value") or ""),
                item.get("times") or 0,
            ),
        ),
    }

    return stable_hash(payload)


def normalize_relic(
    relic: dict[str, Any],
    property_map: dict[str, Any],
) -> dict[str, Any]:
    relic_set = relic.get("set") if isinstance(relic.get("set"), dict) else {}
    main_property = normalize_property(relic.get("main_property"), property_map)

    substats = []
    for item in relic.get("sub_property_list") or []:
        normalized = normalize_property(item, property_map)
        if normalized:
            substats.append(normalized)

    return {
        "fingerprint": artifact_fingerprint(relic, main_property, substats),
        "relic_id": relic.get("id"),
        "name": relic.get("name") or "",
        "set_id": relic_set.get("id"),
        "set_name": relic_set.get("name"),
        "pos": relic.get("pos"),
        "pos_name": relic.get("pos_name"),
        "rarity": relic.get("rarity"),
        "level": relic.get("level"),
        "main_property": main_property,
        "substats": substats,
    }


def import_character_details_payload(
    payload: dict[str, Any],
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    conn: sqlite3.Connection | None = None,
    initialize: bool = True,
    allow_unmapped_sets: bool = False,
    skip_unmapped_sets: bool | None = None,
) -> dict[str, Any]:
    if conn is not None:
        if initialize:
            raise ValueError("Caller-owned connections require initialize=False")
        return _import_character_details_payload(
            payload,
            conn=conn,
            set_catalog_summary={"source": "caller"},
            allow_unmapped_sets=allow_unmapped_sets or bool(skip_unmapped_sets),
        )

    set_catalog_summary: dict[str, Any] = {}
    if initialize:
        set_catalog_summary = ensure_artifact_set_catalog(
            db_path=db_path,
            allow_network=False,
        )

    with closing(connect_db(db_path)) as owned_conn:
        if initialize:
            init_db(owned_conn)
        with owned_conn:
            return _import_character_details_payload(
                payload,
                conn=owned_conn,
                set_catalog_summary=set_catalog_summary,
                allow_unmapped_sets=allow_unmapped_sets or bool(skip_unmapped_sets),
            )


def _import_character_details_payload(
    payload: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    set_catalog_summary: dict[str, Any],
    allow_unmapped_sets: bool,
) -> dict[str, Any]:
    hoyolab_payload = unwrap_hoyolab_payload(payload)

    if hoyolab_payload.get("retcode") != 0:
        raise RuntimeError(
            f"HoYoLAB detail payload retcode={hoyolab_payload.get('retcode')} "
            f"message={hoyolab_payload.get('message')}"
        )

    data = hoyolab_payload.get("data") or {}
    characters = data.get("list") or []
    property_map = data.get("property_map") or {}

    if not isinstance(characters, list):
        raise RuntimeError("HoYoLAB detail payload has no data.list array")

    summary = {
        "characters": len(characters),
        "relics_seen": 0,
        "artifacts_inserted": 0,
        "artifacts_existing": 0,
        "equipment_rows": 0,
        "set_catalog": set_catalog_summary,
        "relics_skipped_unmapped": 0,
        "unmapped_sets": [],
        "relics_unresolved_set": 0,
        "unresolved_sets": [],
        "equipment_updated": True,
    }
    equipment_rows = []

    previous_equipment = {
        (int(row["character_id"]), int(row["pos"])): int(row["artifact_id"])
        for row in conn.execute("SELECT character_id, pos, artifact_id FROM artifact_equipment")
    }
    observed_artifact_ids: set[int] = set()
    seen_characters: set[int] = set()
    unresolved_sets_by_id: dict[int, dict[str, Any]] = {}

    for character in characters:
        base = character.get("base") or {}

        character_id = base.get("id")
        character_name = base.get("name") or ""

        if not character_id:
            continue
        character_id = int(character_id)
        if character_id in seen_characters:
            raise ValueError("Duplicate character in HoYoLAB detail snapshot")
        seen_characters.add(character_id)
        seen_positions: set[int] = set()

        for relic in character.get("relics") or []:
            if not isinstance(relic, dict):
                continue

            normalized = normalize_relic(relic, property_map)
            position = int(normalized["pos"])
            if position in seen_positions:
                raise ValueError("Duplicate artifact slot in HoYoLAB detail snapshot")
            seen_positions.add(position)
            summary["relics_seen"] += 1

            set_uid = None
            try:
                set_uid = resolve_hoyolab_set_uid(
                    conn,
                    hoyolab_set_id=normalized["set_id"],
                    display_name=normalized["set_name"],
                )
            except UnmappedArtifactSetError:
                if not allow_unmapped_sets:
                    raise
                summary["relics_unresolved_set"] += 1
                try:
                    set_id_key = int(normalized["set_id"])
                except (TypeError, ValueError):
                    set_id_key = normalized["set_id"]
                unresolved_sets_by_id.setdefault(
                    set_id_key,
                    {
                        "hoyolab_set_id": normalized["set_id"],
                        "name": normalized["set_name"],
                        "reason": "canonical set mapping unavailable",
                    },
                )

            main_property = normalized["main_property"] or {}
            source_content_fingerprint = artifact_source_content_fingerprint(
                set_id=normalized["set_id"],
                pos=normalized["pos"],
                rarity=normalized["rarity"],
                level=normalized["level"],
                main_property_type=main_property.get("property_type"),
                main_property_value=main_property.get("value"),
                substats=normalized["substats"],
            )
            content_fingerprint = (
                artifact_content_fingerprint(
                    set_uid=set_uid,
                    pos=normalized["pos"],
                    rarity=normalized["rarity"],
                    level=normalized["level"],
                    main_property_type=main_property.get("property_type"),
                    main_property_value=main_property.get("value"),
                    substats=normalized["substats"],
                )
                if set_uid is not None
                else None
            )

            artifact_id, inserted = upsert_artifact(
                conn,
                fingerprint=normalized["fingerprint"],
                content_fingerprint=content_fingerprint,
                source_content_fingerprint=source_content_fingerprint,
                relic_id=normalized["relic_id"],
                name=normalized["name"],
                set_id=normalized["set_id"],
                set_uid=set_uid,
                set_name=normalized["set_name"],
                pos=normalized["pos"],
                pos_name=normalized["pos_name"],
                rarity=normalized["rarity"],
                level=normalized["level"],
                main_property_type=main_property.get("property_type"),
                main_property_name=main_property.get("property_name"),
                main_property_value=main_property.get("value"),
                import_source="hoyolab",
                import_format="character_detail",
                json_imported=False,
                observed_artifact_ids=observed_artifact_ids,
                preferred_artifact_id=previous_equipment.get((character_id, position)),
            )
            observed_artifact_ids.add(artifact_id)

            if inserted:
                summary["artifacts_inserted"] += 1
            else:
                summary["artifacts_existing"] += 1

            replace_substats(conn, artifact_id, normalized["substats"])

            equipment_rows.append(
                {
                    "artifact_id": artifact_id,
                    "character_id": character_id,
                    "character_name": character_name,
                    "pos": normalized["pos"],
                }
            )

    summary["unresolved_sets"] = list(unresolved_sets_by_id.values())
    # Keep the previous summary key as a read-compatible alias; unresolved
    # relics are stored, so nothing is actually skipped.
    summary["unmapped_sets"] = summary["unresolved_sets"]
    replace_current_equipment(conn, equipment_rows)
    summary["equipment_rows"] = len(equipment_rows)

    return summary


def import_character_details_file(
    input_path: str | Path,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    input_path = Path(input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return import_character_details_payload(payload, db_path=db_path)
