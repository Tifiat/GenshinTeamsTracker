"""Offline validation of reviewed current Theory config packaging."""
from __future__ import annotations

import copy
from io import BytesIO
import json
import unittest
import zipfile

from tools.experiments.gcsim.theory_audit import export_current_configs as export


class TheoryCurrentConfigExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        projection = export.base.read_object(export.PROJECTION)
        team = "burning"
        if team not in projection["witnesses"]:
            raise AssertionError("The saved Burning current replay witness is required")
        cls.team = team
        cls.projection = {
            "owner": export.OWNER,
            "current_teams": [team],
            "witnesses": {team: projection["witnesses"][team]},
        }

    def test_requires_explicit_complete_or_released_reviewed_set(self):
        with self.assertRaisesRegex(ValueError, "all 14"):
            export.build_files([self.team], projection=self.projection)
        with self.assertRaisesRegex(ValueError, "team list"):
            export.build_files([self.team, "taser"], release_partial=True, projection=self.projection)
        with self.assertRaisesRegex(ValueError, "unique"):
            export.build_files([self.team, self.team], release_partial=True, projection=self.projection)

    def test_stale_projection_changed_vector_and_engine_refused(self):
        stale = copy.deepcopy(self.projection)
        stale["witnesses"][self.team]["current_search_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Stale current search"):
            export.build_files([self.team], release_partial=True, projection=stale)

        witness = self.projection["witnesses"][self.team]
        current = export.report.read(export.report.receipt(self.team))
        replay = export.base.read_object(export._relative_file(witness["replay_path"]))
        binding = current["binding"]
        changed = copy.deepcopy(current)
        changed["product"]["candidates"][0]["allocations"][0]["unspent_roll_units"] = 999
        with self.assertRaisesRegex(ValueError, "vector/runtime"):
            export._validate_records(
                self.team, changed, replay, witness,
                active_engine_id=binding["engine_id"],
                active_artifact_sha256=binding["engine_artifact_sha256"],
            )
        with self.assertRaisesRegex(ValueError, "vector/runtime"):
            export._validate_records(
                self.team, current, replay, witness,
                active_engine_id="different-engine",
                active_artifact_sha256=binding["engine_artifact_sha256"],
            )
        changed_replay = copy.deepcopy(replay)
        changed_replay["input"]["config_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "config hash"):
            export._validate_records(
                self.team, current, changed_replay, witness,
                active_engine_id=binding["engine_id"],
                active_artifact_sha256=binding["engine_artifact_sha256"],
            )

    def test_old_forecast_can_differ_but_current_witness_must_match(self):
        witness = self.projection["witnesses"][self.team]
        current = export.report.read(export.report.receipt(self.team))
        replay = export.base.read_object(export._relative_file(witness["replay_path"]))
        binding = current["binding"]
        old_forecast = copy.deepcopy(replay)
        old_forecast["input"]["candidate"]["formula_dps"] += 1
        self.assertEqual(
            export._validate_records(
                self.team, current, old_forecast, witness,
                active_engine_id=binding["engine_id"],
                active_artifact_sha256=binding["engine_artifact_sha256"],
            ),
            replay["input"]["config_text"],
        )
        stale_witness = copy.deepcopy(witness)
        stale_witness["current_formula_dps"] += 1
        with self.assertRaisesRegex(ValueError, "vector/runtime"):
            export._validate_records(
                self.team, current, replay, stale_witness,
                active_engine_id=binding["engine_id"],
                active_artifact_sha256=binding["engine_artifact_sha256"],
            )

    def test_deterministic_zip_config_and_checksum_roundtrip(self):
        files = export.build_files([self.team], release_partial=True, projection=self.projection)
        self.assertEqual(sorted(files), ["README.md", f"{self.team}/config.txt", "checksums.json"])
        first, second = export.archive_bytes(files), export.archive_bytes(files)
        self.assertEqual(first, second)
        with zipfile.ZipFile(BytesIO(first)) as archive:
            self.assertEqual(sorted(archive.namelist()), sorted(files))
            manifest = json.loads(archive.read("checksums.json"))
            row = manifest["teams"][0]
            exported = archive.read(row["config_file"]).decode("utf-8")
            self.assertEqual(export.base.text_digest(exported), row["exported_config_sha256"])
            self.assertEqual(export.base.text_digest(archive.read("README.md").decode("utf-8")),
                             manifest["readme_sha256"])
        witness = self.projection["witnesses"][self.team]
        replay = export.base.read_object(export._relative_file(witness["replay_path"]))
        saved = replay["input"]["config_text"]
        self.assertEqual(exported, export.base.ordinary_options(saved, 128))
        self.assertEqual([line for line in exported.splitlines() if not line.startswith("options ")],
                         [line for line in saved.splitlines() if not line.startswith("options ")])


if __name__ == "__main__":
    unittest.main()
