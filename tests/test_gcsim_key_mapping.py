from __future__ import annotations

import unittest

from hoyolab_export.artifact_stats import CRIT_RATE, HP_PERCENT
from run_workspace.gcsim.config_readiness import (
    READINESS_READY,
    GcsimArtifactBuildInput,
    GcsimArtifactSetInput,
    GcsimCharacterInput,
    GcsimTalentInput,
    GcsimTeamInput,
    GcsimWeaponInput,
    audit_gcsim_team_readiness,
)
from run_workspace.gcsim.key_mapping import (
    ENTITY_ARTIFACT_SET,
    ENTITY_CHARACTER,
    ENTITY_WEAPON,
    STATUS_AMBIGUOUS,
    STATUS_DISPLAY_NAME_ONLY_REJECTED,
    STATUS_READY,
    STATUS_UNSUPPORTED_TRAVELER,
    WARNING_DISPLAY_NAME_SOURCE_REJECTED,
    WARNING_PRODUCTION_MAPPING_DATA_MISSING,
    WARNING_TRAVELER_DEFERRED,
    build_key_mapping_report,
    key_mapping_record_to_ref,
    mapping_records_from_payload,
    mapping_refs_by_identity,
)


def ready_payload() -> dict:
    return {
        "schema_version": 1,
        "kind": "gcsim_key_mapping_seed_v1",
        "source_kind": "curated_test_fixture",
        "source_name": "unit-test",
        "records": [
            {
                "entity_type": ENTITY_CHARACTER,
                "project_id": "10000021",
                "canonical_name": "Mona",
                "gcsim_key": "mona",
            },
            {
                "entity_type": ENTITY_WEAPON,
                "project_id": "14405",
                "canonical_name": "Favonius Codex",
                "gcsim_key": "favoniuscodex",
            },
            {
                "entity_type": ENTITY_ARTIFACT_SET,
                "project_id": "NoblesseOblige",
                "canonical_name": "Noblesse Oblige",
                "gcsim_key": "noblesseoblige",
            },
        ],
    }


class GcsimKeyMappingTest(unittest.TestCase):
    def test_ready_explicit_curated_records_report_counts(self) -> None:
        records = mapping_records_from_payload(ready_payload())
        report = build_key_mapping_report(
            records,
            production_mapping_source_present=True,
        )

        self.assertEqual(report.total, 3)
        self.assertEqual(
            report.counts_by_entity_status[ENTITY_CHARACTER][STATUS_READY],
            1,
        )
        self.assertEqual(
            report.counts_by_entity_status[ENTITY_WEAPON][STATUS_READY],
            1,
        )
        self.assertEqual(
            report.counts_by_entity_status[ENTITY_ARTIFACT_SET][STATUS_READY],
            1,
        )
        self.assertEqual(report.missing_records, ())
        self.assertEqual(report.ambiguous_records, ())
        self.assertEqual(records[0].to_mapping_ref().gcsim_key, "mona")

    def test_report_warns_when_only_fixture_mapping_source_exists(self) -> None:
        report = build_key_mapping_report(mapping_records_from_payload(ready_payload()))

        self.assertIn(
            WARNING_PRODUCTION_MAPPING_DATA_MISSING,
            report.to_dict()["warnings"],
        )

    def test_display_name_and_normalized_name_sources_are_rejected(self) -> None:
        records = mapping_records_from_payload(
            {
                "schema_version": 1,
                "records": [
                    {
                        "entity_type": ENTITY_CHARACTER,
                        "project_id": "10000021",
                        "canonical_name": "Mona",
                        "gcsim_key": "mona",
                        "source_kind": "display_name",
                        "source_name": "localized account name",
                    },
                    {
                        "entity_type": ENTITY_WEAPON,
                        "project_id": "14405",
                        "canonical_name": "Favonius Codex",
                        "gcsim_key": "favoniuscodex",
                        "source_kind": "normalized_name_guess",
                        "source_name": "name slug",
                    },
                ],
            }
        )

        self.assertEqual(records[0].status, STATUS_DISPLAY_NAME_ONLY_REJECTED)
        self.assertEqual(records[1].status, STATUS_DISPLAY_NAME_ONLY_REJECTED)
        self.assertEqual(records[0].gcsim_key, "")
        self.assertIn(WARNING_DISPLAY_NAME_SOURCE_REJECTED, records[0].warnings)
        self.assertEqual(key_mapping_record_to_ref(records[0]).gcsim_key, "")

    def test_ambiguous_mapping_stays_ambiguous(self) -> None:
        records = mapping_records_from_payload(
            {
                "schema_version": 1,
                "source_kind": "curated_test_fixture",
                "source_name": "unit-test",
                "records": [
                    {
                        "entity_type": ENTITY_CHARACTER,
                        "project_id": "10000099",
                        "canonical_name": "Future Hero",
                        "status": STATUS_AMBIGUOUS,
                        "candidates": ["futurehero", "futureheroalt"],
                    },
                ],
            }
        )
        report = build_key_mapping_report(
            records,
            production_mapping_source_present=True,
        )

        self.assertEqual(records[0].status, STATUS_AMBIGUOUS)
        self.assertEqual(records[0].gcsim_key, "")
        self.assertEqual(len(report.ambiguous_records), 1)
        self.assertTrue(key_mapping_record_to_ref(records[0]).ambiguous)

    def test_traveler_is_unsupported_even_with_key(self) -> None:
        records = mapping_records_from_payload(
            {
                "schema_version": 1,
                "source_kind": "curated_test_fixture",
                "source_name": "unit-test",
                "records": [
                    {
                        "entity_type": ENTITY_CHARACTER,
                        "project_id": "10000007",
                        "canonical_name": "Traveler",
                        "gcsim_key": "pyrotraveler",
                    },
                ],
            }
        )

        self.assertEqual(records[0].status, STATUS_UNSUPPORTED_TRAVELER)
        self.assertEqual(records[0].gcsim_key, "")
        self.assertIn(WARNING_TRAVELER_DEFERRED, records[0].warnings)

    def test_mapping_refs_feed_config_readiness(self) -> None:
        records = mapping_records_from_payload(ready_payload())
        refs = mapping_refs_by_identity(records)
        team = GcsimTeamInput(
            characters=(
                GcsimCharacterInput(
                    project_character_id="10000021",
                    display_name="Mona",
                    level=90,
                    max_level=90,
                    constellation=2,
                    mapping=refs[(ENTITY_CHARACTER, "10000021")],
                    weapon=GcsimWeaponInput(
                        project_weapon_id="14405",
                        display_name="Favonius Codex",
                        level=90,
                        refinement=5,
                        mapping=refs[(ENTITY_WEAPON, "14405")],
                    ),
                    artifact_build=GcsimArtifactBuildInput(
                        artifact_ids_by_pos={
                            1: 101,
                            2: 102,
                            3: 103,
                            4: 104,
                            5: 105,
                        },
                        active_sets=(
                            GcsimArtifactSetInput(
                                set_uid="NoblesseOblige",
                                piece_count=4,
                                mapping=refs[(ENTITY_ARTIFACT_SET, "NoblesseOblige")],
                            ),
                        ),
                        stat_totals=(
                            {"property_type": HP_PERCENT, "raw_value": 46.6},
                            {"property_type": CRIT_RATE, "raw_value": 31.1},
                        ),
                    ),
                    talents=GcsimTalentInput(
                        normal=6,
                        skill=9,
                        burst=10,
                        source_order_confirmed=True,
                    ),
                ),
            )
        )

        audit = audit_gcsim_team_readiness(team)

        self.assertTrue(audit.ready)
        self.assertEqual(audit.status, READINESS_READY)
        character = audit.character_audits[0]
        self.assertEqual(character.character_mapping.gcsim_key, "mona")
        self.assertEqual(character.weapon.mapping.gcsim_key, "favoniuscodex")
        self.assertEqual(
            character.artifacts.set_audits[0].mapping.gcsim_key,
            "noblesseoblige",
        )


if __name__ == "__main__":
    unittest.main()
