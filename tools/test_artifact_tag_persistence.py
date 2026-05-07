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
    get_or_create_tag,
    tag_artifact,
)
from hoyolab_export.artifact_importer import import_character_details_file


TEST_TAG_NAME = "test_keep_after_import"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        help="Path to character_detail_batch_result.json",
    )
    parser.add_argument(
        "--db",
        default=str(ARTIFACT_DB_PATH),
        help="SQLite DB path",
    )
    args = parser.parse_args()

    with connect_db(args.db) as conn:
        artifact = conn.execute(
            """
            SELECT id, name, fingerprint
            FROM artifacts
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()

        if artifact is None:
            raise RuntimeError("No artifacts in DB. Import artifacts first.")

        artifact_id = int(artifact["id"])
        artifact_name = artifact["name"]

        tag_id = get_or_create_tag(conn, TEST_TAG_NAME, color="#d9b56f")
        tag_artifact(conn, artifact_id, tag_id)
        conn.commit()

        print("[tag-test] Tagged artifact before reimport:")
        print(f"  artifact_id: {artifact_id}")
        print(f"  artifact_name: {artifact_name}")
        print(f"  tag: {TEST_TAG_NAME}")

    summary = import_character_details_file(args.input, db_path=args.db)

    with connect_db(args.db) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM artifact_tag_links
            WHERE artifact_id = ?
              AND tag_id = (
                  SELECT id FROM artifact_tags WHERE name = ?
              )
            """,
            (artifact_id, TEST_TAG_NAME),
        ).fetchone()

        tag_still_exists = int(row["count"]) > 0

    print()
    print("[tag-test] Reimport summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print()
    if tag_still_exists:
        print("[tag-test] OK: tag survived reimport.")
        return 0

    print("[tag-test] FAILED: tag was lost after reimport.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())