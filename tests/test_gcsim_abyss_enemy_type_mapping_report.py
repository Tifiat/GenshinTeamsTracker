from __future__ import annotations

from io import StringIO
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from run_workspace.abyss.source_data import rebuild_abyss_floor_source_data_with_rows
from run_workspace.abyss.source_data_cache import save_abyss_floor_source_data
from run_workspace.gcsim.abyss_enemy_type_mapping_report import (
    build_abyss_enemy_type_coverage_report,
    main,
)
from run_workspace.gcsim.abyss_wave_scenario import (
    AbyssEnemyTypeMapping,
    AbyssEnemyTypeMappingRecord,
    IDENTITY_KIND_FANDOM_PAGE_TITLE,
    IDENTITY_KIND_NANOKA_MONSTER_ID,
)
from tests.test_gcsim_abyss_wave_scenario import _source_data


def _mapping() -> AbyssEnemyTypeMapping:
    return AbyssEnemyTypeMapping(
        records=(
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                source_id="first",
                gcsim_type="battlehardenedgroundedgeoshroom",
            ),
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_FANDOM_PAGE_TITLE,
                source_id="Second Enemy",
                gcsim_type="dummy",
            ),
        ),
        mapping_name="coverage_mapping",
    )


class GcsimAbyssEnemyTypeMappingReportTest(unittest.TestCase):
    def test_coverage_report_counts_resolved_missing_and_hp_gaps(self) -> None:
        data = _source_data()
        rows = list(data.enemy_rows)
        rows[1] = replace(rows[1], nanoka_hp=None)
        data = rebuild_abyss_floor_source_data_with_rows(data, rows)

        report = build_abyss_enemy_type_coverage_report([data], _mapping())

        self.assertEqual(report.total_rows, 2)
        self.assertEqual(report.resolved_by_source_kind[IDENTITY_KIND_NANOKA_MONSTER_ID], 1)
        self.assertEqual(report.resolved_by_source_kind[IDENTITY_KIND_FANDOM_PAGE_TITLE], 1)
        self.assertEqual(report.missing_mappings, 0)
        self.assertEqual(report.ambiguous_mappings, 0)
        self.assertEqual(report.hp_present_type_missing, 0)
        self.assertEqual(report.type_present_hp_missing, 1)

    def test_coverage_report_lists_unresolved_identities(self) -> None:
        data = _source_data()
        report = build_abyss_enemy_type_coverage_report(
            [data],
            AbyssEnemyTypeMapping(
                records=(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="first",
                        gcsim_type="dummy",
                    ),
                )
            ),
        )

        self.assertEqual(report.missing_mappings, 1)
        self.assertEqual(report.hp_present_type_missing, 1)
        self.assertEqual(report.unresolved_rows[0]["enemy"], "Second Enemy")
        self.assertGreater(len(report.unresolved_rows[0]["available_identities"]), 0)

    def test_cli_json_report_loads_temp_cache_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = save_abyss_floor_source_data(_source_data(), cache_dir=root / "cache")
            mapping_path = root / "mapping.json"
            mapping_path.write_text(
                json.dumps(
                    {
                        "mapping_name": "cli_mapping",
                        "records": [
                            {
                                "source_kind": IDENTITY_KIND_NANOKA_MONSTER_ID,
                                "source_id": "first",
                                "gcsim_type": "dummy",
                            },
                            {
                                "source_kind": IDENTITY_KIND_FANDOM_PAGE_TITLE,
                                "source_id": "Second Enemy",
                                "gcsim_type": "dummy",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            code = main(
                [
                    "--enemy-type-map",
                    str(mapping_path),
                    "--cache-file",
                    str(cache_path),
                    "--format",
                    "json",
                ],
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["report"]["total_rows"], 2)
        self.assertEqual(payload["report"]["missing_mappings"], 0)


if __name__ == "__main__":
    unittest.main()
