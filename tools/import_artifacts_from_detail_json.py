import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db, count_rows
from hoyolab_export.artifact_importer import import_character_details_file


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

    summary = import_character_details_file(args.input, db_path=args.db)

    print("[artifact-import] Import summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    with connect_db(args.db) as conn:
        print()
        print("[artifact-import] DB rows:")
        print(json.dumps(count_rows(conn), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())