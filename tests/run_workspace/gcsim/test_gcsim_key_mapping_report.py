from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.key_mapping import (
    DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH,
    ENTITY_ARTIFACT_SET,
    ENTITY_CHARACTER,
    ENTITY_WEAPON,
    STATUS_READY,
    WARNING_PRODUCTION_MAPPING_DATA_MISSING,
    load_default_mapping_seed_records,
    mapping_refs_by_identity,
)
from run_workspace.gcsim.key_mapping_report import (
    build_default_key_mapping_report,
    build_key_mapping_report_from_seed,
    main,
)


class GcsimKeyMappingReportTest(unittest.TestCase):
    def test_default_seed_file_loads_expected_tiny_records(self) -> None:
        records = load_default_mapping_seed_records()

        self.assertTrue(DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH.exists())
        self.assertEqual(len(records), 3)
        identities = {(record.entity_type, record.project_id) for record in records}
        self.assertEqual(
            identities,
            {
                (ENTITY_CHARACTER, "10000021"),
                (ENTITY_WEAPON, "14405"),
                (ENTITY_ARTIFACT_SET, "NoblesseOblige"),
            },
        )
        self.assertTrue(all(record.status == STATUS_READY for record in records))

    def test_default_seed_report_keeps_production_missing_warning(self) -> None:
        report = build_default_key_mapping_report()
        data = report.to_dict()

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
        self.assertIn(WARNING_PRODUCTION_MAPPING_DATA_MISSING, data["warnings"])

    def test_default_seed_records_convert_to_mapping_refs(self) -> None:
        refs = mapping_refs_by_identity(load_default_mapping_seed_records())

        self.assertEqual(refs[(ENTITY_CHARACTER, "10000021")].gcsim_key, "mona")
        self.assertEqual(refs[(ENTITY_WEAPON, "14405")].gcsim_key, "favoniuscodex")
        self.assertEqual(
            refs[(ENTITY_ARTIFACT_SET, "NoblesseOblige")].gcsim_key,
            "noblesseoblige",
        )

    def test_report_cli_text_and_json_use_explicit_temp_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed = Path(tmp) / "seed.json"
            seed.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "gcsim_key_mapping_seed_v1",
                        "source_kind": "curated_dev_seed",
                        "source_name": "unit-test",
                        "records": [
                            {
                                "entity_type": ENTITY_CHARACTER,
                                "project_id": "10000021",
                                "canonical_name": "Mona",
                                "gcsim_key": "mona",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            text_stdout = io.StringIO()
            with contextlib.redirect_stdout(text_stdout):
                text_code = main(["--seed", str(seed), "--format", "text"])

            json_stdout = io.StringIO()
            with contextlib.redirect_stdout(json_stdout):
                json_code = main(["--seed", str(seed), "--format", "json"])

        self.assertEqual(text_code, 0)
        self.assertIn("GCSIM key mapping report", text_stdout.getvalue())
        self.assertIn("character: ready=1", text_stdout.getvalue())
        self.assertEqual(json_code, 0)
        payload = json.loads(json_stdout.getvalue())
        self.assertEqual(payload["total"], 1)
        self.assertIn(WARNING_PRODUCTION_MAPPING_DATA_MISSING, payload["warnings"])

    def test_trusted_flag_suppresses_production_missing_warning(self) -> None:
        report = build_key_mapping_report_from_seed(
            DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH,
            production_mapping_source_present=True,
        )

        self.assertNotIn(
            WARNING_PRODUCTION_MAPPING_DATA_MISSING,
            report.to_dict()["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
