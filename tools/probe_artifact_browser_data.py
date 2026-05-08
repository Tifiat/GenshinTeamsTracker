from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ui.artifact_browser.models import ARTIFACT_POSITIONS
from ui.artifact_browser.queries import artifact_db_exists, list_artifacts_by_position


def main() -> int:
    if not artifact_db_exists():
        print("data/artifacts.db не найден")
        return 1

    for pos, label in ARTIFACT_POSITIONS.items():
        artifacts = list_artifacts_by_position(pos)
        print(f"{label}: {len(artifacts)}")

        for artifact in artifacts[:3]:
            icon_status = "icon ok" if artifact.icon_path else "no icon"
            equipped = artifact.character_name or "не надет"
            print(
                f"  #{artifact.id} {artifact.set_name} +{artifact.level} "
                f"{artifact.main_property_name} {artifact.main_property_value} "
                f"CV={artifact.cv} {icon_status} · {equipped}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())