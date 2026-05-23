from __future__ import annotations

import unittest

from ui.artifact_browser.models import ArtifactItem, ArtifactSubstat
from ui.artifact_browser.stat_types import (
    CRIT_DAMAGE,
    CRIT_RATE,
    CRIT_VALUE,
    ELEMENTAL_MASTERY,
)
from ui.artifact_browser.store import ArtifactBrowserStore


def artifact(
    artifact_id: int,
    *,
    main_type: int,
    main_value: str,
    substats: list[tuple[int, str]],
) -> ArtifactItem:
    return ArtifactItem(
        id=artifact_id,
        name=f"Artifact {artifact_id}",
        set_id=None,
        set_uid="set",
        set_name="Set",
        pos=5,
        pos_name="Circlet",
        rarity=5,
        level=20,
        main_property_type=main_type,
        main_property_name=str(main_type),
        main_property_value=main_value,
        substats=[
            ArtifactSubstat(
                slot_index=index,
                property_type=property_type,
                property_name=str(property_type),
                value=value,
            )
            for index, (property_type, value) in enumerate(substats)
        ],
    )


class ArtifactSortingTest(unittest.TestCase):
    def test_crit_value_first_prioritizes_crit_main_circlets(self) -> None:
        crit_damage_with_em = artifact(
            1,
            main_type=CRIT_DAMAGE,
            main_value="62.2%",
            substats=[(CRIT_RATE, "5%"), (ELEMENTAL_MASTERY, "40")],
        )
        crit_rate_without_em = artifact(
            2,
            main_type=CRIT_RATE,
            main_value="31.1%",
            substats=[(CRIT_DAMAGE, "10%")],
        )
        elemental_mastery_with_more_substat_cv = artifact(
            3,
            main_type=ELEMENTAL_MASTERY,
            main_value="187",
            substats=[(CRIT_RATE, "35%"), (CRIT_DAMAGE, "20%")],
        )

        store = ArtifactBrowserStore(
            database_exists=True,
            artifacts=[
                elemental_mastery_with_more_substat_cv,
                crit_rate_without_em,
                crit_damage_with_em,
            ],
        )

        sorted_ids = store.sort_artifact_ids(
            [3, 2, 1],
            [CRIT_VALUE, ELEMENTAL_MASTERY],
        )

        self.assertEqual(sorted_ids, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
