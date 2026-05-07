import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    create_artifact_build,
    find_duplicate_artifacts_in_builds,
    get_artifact_build_slots,
    replace_artifact_build_slots,
)


TEST_PREFIX = "__test_build__"


def cleanup_test_builds(conn):
    conn.execute(
        "DELETE FROM artifact_builds WHERE name LIKE ?",
        (f"{TEST_PREFIX}%",),
    )
    conn.commit()


def pick_character_with_full_build(conn):
    row = conn.execute(
        """
        SELECT
            character_id,
            character_name,
            COUNT(*) AS artifact_count
        FROM artifact_equipment
        GROUP BY character_id, character_name
        HAVING COUNT(*) >= 5
        ORDER BY character_name
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        raise RuntimeError("No character with 5 equipped artifacts found.")

    return row


def load_character_slots(conn, character_id: int) -> dict[int, int]:
    rows = conn.execute(
        """
        SELECT pos, artifact_id
        FROM artifact_equipment
        WHERE character_id = ?
        ORDER BY pos
        """,
        (character_id,),
    ).fetchall()

    slots = {
        int(row["pos"]): int(row["artifact_id"])
        for row in rows
    }

    if len(slots) < 5:
        raise RuntimeError(f"Character {character_id} has less than 5 artifact slots.")

    return slots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(ARTIFACT_DB_PATH),
        help="SQLite DB path",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep created test builds in DB.",
    )
    args = parser.parse_args()

    with connect_db(args.db) as conn:
        cleanup_test_builds(conn)

        character = pick_character_with_full_build(conn)
        character_id = int(character["character_id"])
        character_name = character["character_name"]
        slots = load_character_slots(conn, character_id)

        print("[build-test] Picked character:")
        print(f"  {character_id} {character_name}")

        build_1 = create_artifact_build(
            conn,
            name=f"{TEST_PREFIX}original_{character_name}",
            character_id=character_id,
            character_name=character_name,
            notes="Temporary test build.",
        )
        replace_artifact_build_slots(conn, build_1, slots)

        build_2 = create_artifact_build(
            conn,
            name=f"{TEST_PREFIX}duplicate_{character_name}",
            character_id=character_id,
            character_name=character_name,
            notes="Temporary duplicate test build.",
        )
        replace_artifact_build_slots(conn, build_2, slots)

        conn.commit()

        loaded_slots = get_artifact_build_slots(conn, build_1)
        duplicates = find_duplicate_artifacts_in_builds(conn, [build_1, build_2])

        print()
        print("[build-test] Created builds:")
        print(f"  build_1: {build_1}")
        print(f"  build_2: {build_2}")

        print()
        print("[build-test] Loaded build_1 slots:")
        for row in loaded_slots:
            print(
                f"  pos={row['pos']} "
                f"artifact_id={row['artifact_id']} "
                f"{row['name']} / {row['main_property_name']} {row['main_property_value']}"
            )

        print()
        print("[build-test] Duplicate artifacts:")
        print(json.dumps(duplicates, ensure_ascii=False, indent=2))

        if len(loaded_slots) != 5:
            raise RuntimeError(f"Expected 5 slots, got {len(loaded_slots)}")

        if len(duplicates) != 5:
            raise RuntimeError(f"Expected 5 duplicate artifacts, got {len(duplicates)}")

        if not args.keep:
            cleanup_test_builds(conn)
            print()
            print("[build-test] Test builds cleaned up.")
        else:
            print()
            print("[build-test] Test builds kept in DB.")

    print()
    print("[build-test] OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())