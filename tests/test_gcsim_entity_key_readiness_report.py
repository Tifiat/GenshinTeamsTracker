from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.entity_key_readiness_report import (
    METHOD_EXACT_NORMALIZED_NAME,
    METHOD_EXPLICIT_SEED,
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_READY,
    STATUS_UNSUPPORTED_TRAVELER,
    WARNING_AUTO_EXACT_NOT_CURATED,
    WARNING_PRODUCTION_MAPPING_DATA_MISSING,
    WARNING_TRAVELER_DEFERRED,
    GcsimEntityRegistry,
    ProjectEntity,
    build_entity_key_coverage_report,
    load_project_entities_from_json,
    parse_gcsim_shortcut_keys_from_go_source,
)
from run_workspace.gcsim.key_mapping import (
    ENTITY_ARTIFACT_SET,
    ENTITY_CHARACTER,
    ENTITY_WEAPON,
    SOURCE_KIND_CURATED_TEST_FIXTURE,
    make_key_mapping_record,
)


def fixture_registry(**overrides) -> GcsimEntityRegistry:
    data = {
        "character_keys": ("mona",),
        "weapon_keys": ("favoniuscodex",),
        "artifact_set_keys": ("noblesseoblige",),
    }
    data.update(overrides)
    return GcsimEntityRegistry(**data)


def report_for(entities, registry=None, seed_records=()):
    return build_entity_key_coverage_report(
        entities,
        registry or fixture_registry(),
        seed_records=seed_records,
    )


class GcsimEntityKeyReadinessReportTest(unittest.TestCase):
    def test_registry_parser_extracts_go_map_keys(self) -> None:
        source = """
var CharNameToKey = map[string]keys.Char{
    "mona": keys.Mona,
    "kaedeharakazuha": keys.Kazuha,
}
"""

        self.assertEqual(
            parse_gcsim_shortcut_keys_from_go_source(source),
            ("kaedeharakazuha", "mona"),
        )

    def test_exact_normalized_character_match_succeeds(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000021",
                    display_name="Mona",
                ),
            )
        )
        entry = report.entries[0]

        self.assertEqual(entry.status, STATUS_READY)
        self.assertEqual(entry.method, METHOD_EXACT_NORMALIZED_NAME)
        self.assertEqual(entry.gcsim_key, "mona")
        self.assertIn(WARNING_AUTO_EXACT_NOT_CURATED, entry.warnings)

    def test_exact_normalized_weapon_match_succeeds(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_WEAPON,
                    project_id="14405",
                    display_name="Favonius Codex",
                ),
            )
        )

        self.assertEqual(report.entries[0].status, STATUS_READY)
        self.assertEqual(report.entries[0].gcsim_key, "favoniuscodex")

    def test_exact_normalized_artifact_set_match_succeeds(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_ARTIFACT_SET,
                    project_id="NoblesseOblige",
                    display_name="Noblesse Oblige",
                ),
            )
        )

        self.assertEqual(report.entries[0].status, STATUS_READY)
        self.assertEqual(report.entries[0].gcsim_key, "noblesseoblige")

    def test_missing_entity_is_reported(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000099",
                    display_name="Future Hero",
                ),
            )
        )

        self.assertEqual(report.entries[0].status, STATUS_MISSING)
        self.assertEqual(report.missing_entries[0].normalized_candidate, "futurehero")

    def test_duplicate_normalized_registry_candidates_are_ambiguous(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000099",
                    display_name="Future Hero",
                ),
            ),
            registry=fixture_registry(character_keys=("futurehero", "future-hero")),
        )

        self.assertEqual(report.entries[0].status, STATUS_AMBIGUOUS)
        self.assertEqual(
            report.entries[0].candidates,
            ("futurehero", "future-hero"),
        )

    def test_traveler_is_unsupported_deferred(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000007",
                    display_name="Traveler",
                ),
            ),
            registry=fixture_registry(character_keys=("travelerpyro",)),
        )

        self.assertEqual(report.entries[0].status, STATUS_UNSUPPORTED_TRAVELER)
        self.assertIn(WARNING_TRAVELER_DEFERRED, report.entries[0].warnings)

    def test_traveler_variant_name_is_still_unsupported_deferred(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="7306",
                    display_name="Traveler (Pyro)",
                ),
            ),
            registry=fixture_registry(character_keys=("travelerpyro",)),
        )

        self.assertEqual(report.entries[0].status, STATUS_UNSUPPORTED_TRAVELER)
        self.assertEqual(report.entries[0].gcsim_key, "")

    def test_explicit_seed_override_wins_over_automatic_candidate(self) -> None:
        seed = make_key_mapping_record(
            entity_type=ENTITY_CHARACTER,
            project_id="10000021",
            canonical_name="Mona",
            gcsim_key="mona",
            source_kind=SOURCE_KIND_CURATED_TEST_FIXTURE,
            source_name="unit-test",
        )
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000021",
                    display_name="Not Mona",
                ),
            ),
            registry=fixture_registry(character_keys=("notmona", "mona")),
            seed_records=(seed,),
        )

        entry = report.entries[0]
        self.assertEqual(entry.status, STATUS_READY)
        self.assertEqual(entry.method, METHOD_EXPLICIT_SEED)
        self.assertEqual(entry.gcsim_key, "mona")
        self.assertNotIn(WARNING_AUTO_EXACT_NOT_CURATED, entry.warnings)

    def test_display_normalized_source_is_not_curated_production_mapping(self) -> None:
        report = report_for(
            (
                ProjectEntity(
                    entity_type=ENTITY_CHARACTER,
                    project_id="10000021",
                    display_name="Mona",
                    source_name="display-name-fixture",
                ),
            )
        )

        entry = report.entries[0]
        self.assertEqual(entry.status, STATUS_READY)
        self.assertEqual(entry.method, METHOD_EXACT_NORMALIZED_NAME)
        self.assertIn(WARNING_AUTO_EXACT_NOT_CURATED, entry.warnings)
        self.assertIn(
            WARNING_PRODUCTION_MAPPING_DATA_MISSING,
            report.to_dict()["warnings"],
        )

    def test_project_entity_json_loader_supports_explicit_fixture_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "entities.json"
            path.write_text(
                json.dumps(
                    {
                        "characters": [
                            {
                                "project_id": "10000021",
                                "display_name": "Mona",
                            }
                        ],
                        "weapons": [
                            {
                                "project_id": "14405",
                                "display_name": "Favonius Codex",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            entities = load_project_entities_from_json(path)

        self.assertEqual(
            [(item.entity_type, item.project_id) for item in entities],
            [(ENTITY_CHARACTER, "10000021"), (ENTITY_WEAPON, "14405")],
        )


if __name__ == "__main__":
    unittest.main()
