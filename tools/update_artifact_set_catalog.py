from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.artifact_set_catalog import (
    export_seed_catalog,
    update_artifact_set_catalog,
)


def main() -> int:
    summary = update_artifact_set_catalog()
    seed_path = export_seed_catalog()

    print()
    print("Artifact set catalog updated")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"seed_catalog: {seed_path}")

    if summary.get("icons_failed"):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())