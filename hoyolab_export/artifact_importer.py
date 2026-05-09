import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    init_db,
    replace_current_equipment,
    replace_substats,
    upsert_artifact,
)
from .artifact_set_catalog import (
    ensure_artifact_set_catalog,
    resolve_hoyolab_set_uid,
)
def stable_hash(data: Any) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


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
        "value": prop.get("value") or prop.get("final") or prop.get("base") or "",
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
            "value": prop.get("value") or "",
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
        "set_catalog": {},
    }
    summary["set_catalog"] = ensure_artifact_set_catalog(
        db_path=db_path,
        allow_network=False,
    )
    equipment_rows = []

    with connect_db(db_path) as conn:
        init_db(conn)

        for character in characters:
            base = character.get("base") or {}

            character_id = base.get("id")
            character_name = base.get("name") or ""

            if not character_id:
                continue

            for relic in character.get("relics") or []:
                if not isinstance(relic, dict):
                    continue

                normalized = normalize_relic(relic, property_map)
                summary["relics_seen"] += 1

                set_uid = resolve_hoyolab_set_uid(
                    conn,
                    hoyolab_set_id=normalized["set_id"],
                    display_name=normalized["set_name"],
                )

                main_property = normalized["main_property"] or {}

                artifact_id, inserted = upsert_artifact(
                    conn,
                    fingerprint=normalized["fingerprint"],
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
                )

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

        replace_current_equipment(conn, equipment_rows)
        summary["equipment_rows"] = len(equipment_rows)

        conn.commit()

    return summary


def import_character_details_file(
    input_path: str | Path,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    input_path = Path(input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return import_character_details_payload(payload, db_path=db_path)
