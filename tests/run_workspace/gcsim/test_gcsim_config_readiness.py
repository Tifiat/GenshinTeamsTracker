from __future__ import annotations

import unittest

from hoyolab_export.artifact_stats import CRIT_RATE, HP_PERCENT
from run_workspace.gcsim.config_readiness import (
    READINESS_AMBIGUOUS_MAPPING,
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_TALENT_DATA,
    READINESS_MISSING_WEAPON,
    READINESS_READY,
    READINESS_UNSUPPORTED_TRAVELER,
    WARNING_DISPLAY_NAME_ONLY_MAPPING,
    WARNING_TRAVELER_DEFERRED,
    GcsimArtifactBuildInput,
    GcsimArtifactSetInput,
    GcsimCharacterInput,
    GcsimMappingRef,
    GcsimTalentInput,
    GcsimTeamInput,
    GcsimWeaponInput,
    audit_gcsim_team_readiness,
)


def ready_mapping(key: str) -> GcsimMappingRef:
    return GcsimMappingRef(gcsim_key=key, source="explicit_test_fixture")


def ready_artifacts() -> GcsimArtifactBuildInput:
    return GcsimArtifactBuildInput(
        artifact_ids_by_pos={1: 101, 2: 102, 3: 103, 4: 104, 5: 105},
        active_sets=(
            GcsimArtifactSetInput(
                set_uid="NoblesseOblige",
                piece_count=4,
                mapping=ready_mapping("noblesseoblige"),
            ),
        ),
        stat_totals=(
            {"property_type": HP_PERCENT, "raw_value": 46.6},
            {"property_type": CRIT_RATE, "raw_value": 31.1},
        ),
    )


def ready_character(**overrides) -> GcsimCharacterInput:
    data = {
        "project_character_id": "10000021",
        "display_name": "Mona",
        "level": 90,
        "max_level": 90,
        "constellation": 2,
        "mapping": ready_mapping("mona"),
        "weapon": GcsimWeaponInput(
            project_weapon_id="14405",
            display_name="Favonius Codex",
            level=90,
            refinement=5,
            mapping=ready_mapping("favoniuscodex"),
        ),
        "artifact_build": ready_artifacts(),
        "talents": GcsimTalentInput(
            normal=6,
            skill=9,
            burst=10,
            source_order_confirmed=True,
        ),
    }
    data.update(overrides)
    return GcsimCharacterInput(**data)


class GcsimConfigReadinessTest(unittest.TestCase):
    def test_ready_synthetic_team_fixture(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(characters=(ready_character(),))
        )

        self.assertTrue(audit.ready)
        self.assertEqual(audit.status, READINESS_READY)
        character = audit.character_audits[0]
        self.assertEqual(character.character_mapping.gcsim_key, "mona")
        self.assertEqual(character.weapon.mapping.gcsim_key, "favoniuscodex")
        self.assertEqual(character.artifacts.add_stats["hp%"], 0.466)
        self.assertEqual(character.artifacts.add_stats["cr"], 0.311)

    def test_missing_character_mapping_is_not_ready(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(ready_character(mapping=GcsimMappingRef()),)
            )
        )

        self.assertFalse(audit.ready)
        self.assertEqual(audit.status, READINESS_MISSING_MAPPING)
        fields = [issue.field for issue in audit.issues]
        self.assertIn("character.mapping", fields)

    def test_display_name_only_mapping_is_not_treated_as_ready(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(
                    ready_character(
                        mapping=GcsimMappingRef(
                            gcsim_key="Mona",
                            source="localized_display_name",
                        )
                    ),
                )
            )
        )

        self.assertFalse(audit.ready)
        self.assertEqual(audit.status, READINESS_MISSING_MAPPING)
        self.assertIn(WARNING_DISPLAY_NAME_ONLY_MAPPING, audit.warnings)
        character = audit.character_audits[0]
        self.assertEqual(character.character_mapping.gcsim_key, "")

    def test_traveler_is_deferred_even_with_mapping_key(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(
                    ready_character(
                        project_character_id="10000007",
                        display_name="Traveler",
                        mapping=ready_mapping("pyrotraveler"),
                    ),
                )
            )
        )

        self.assertFalse(audit.ready)
        self.assertEqual(audit.status, READINESS_UNSUPPORTED_TRAVELER)
        self.assertIn(WARNING_TRAVELER_DEFERRED, audit.warnings)

    def test_ambiguous_mapping_reports_ambiguous_status(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(
                    ready_character(
                        mapping=GcsimMappingRef(
                            gcsim_key="mona",
                            source="explicit_test_fixture",
                            ambiguous=True,
                        )
                    ),
                )
            )
        )

        self.assertFalse(audit.ready)
        self.assertEqual(audit.status, READINESS_AMBIGUOUS_MAPPING)

    def test_missing_weapon_artifact_and_talent_fields_are_controlled(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(
                    ready_character(
                        weapon=None,
                        artifact_build=None,
                        talents=None,
                    ),
                )
            )
        )

        self.assertFalse(audit.ready)
        statuses = {issue.status for issue in audit.issues}
        self.assertIn(READINESS_MISSING_WEAPON, statuses)
        self.assertIn(READINESS_MISSING_ARTIFACT_DATA, statuses)
        self.assertIn(READINESS_MISSING_TALENT_DATA, statuses)

    def test_missing_talent_order_is_not_crash_or_ready(self) -> None:
        audit = audit_gcsim_team_readiness(
            GcsimTeamInput(
                characters=(
                    ready_character(
                        talents=GcsimTalentInput(normal=6, skill=9, burst=10),
                    ),
                )
            )
        )

        self.assertFalse(audit.ready)
        statuses = {issue.status for issue in audit.issues}
        self.assertIn(READINESS_MISSING_TALENT_DATA, statuses)


if __name__ == "__main__":
    unittest.main()
