"""Offline selection and receipt-binding checks for the current Theory audit."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.theory_audit import run_lunar_audit as audit


class CurrentTheoryAuditSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = audit.load_json(audit.MANIFEST)

    def test_default_arguments_and_alternate_receipt_requirement(self):
        default = audit.parse_args([])
        self.assertEqual(default.run_id, audit.RUN_ID)
        self.assertEqual(default.receipt, audit.RECEIPT)
        alternate = audit.parse_args([
            "--run-id", "lunar_crystallize_theory",
            "--receipt", "docs/optimizer-evidence/current-lunar-crystallize.json",
        ])
        self.assertEqual(alternate.run_id, "lunar_crystallize_theory")
        self.assertEqual(alternate.receipt, Path("docs/optimizer-evidence/current-lunar-crystallize.json"))
        for args in (["--run-id", "lunar_crystallize_theory"],
                     ["--run-id", "lunar_crystallize_all_sets", "--receipt", "new.json"],
                     ["--run-id", "../../foreign_theory", "--receipt", "new.json"]):
            with self.subTest(args=args), patch("sys.stderr"), self.assertRaises(SystemExit):
                audit.parse_args(args)

    def test_all_current_theory_entries_select_one_complete_infinite_team(self):
        self.assertEqual(audit.sha256(audit.MANIFEST), audit.MANIFEST_SHA256)
        entries = audit.matrix._expanded_manifest_entries(self.manifest)
        theory = [row for row in entries if row["mode"] == "theory"]
        self.assertEqual(len(theory), 14)
        for row in theory:
            with self.subTest(run_id=row["id"]):
                selected = audit.select_theory_entry(self.manifest, row["id"])
                self.assertEqual(selected["id"], row["id"])
                self.assertEqual(len(selected["virtual_profiles"]), 4)
                self.assertIs(selected["infinite_energy"], True)
        with self.assertRaises(ValueError):
            audit.select_theory_entry(self.manifest, "unknown_theory")
        with self.assertRaises(ValueError):
            audit.select_theory_entry(self.manifest, "gaming_melt_all_sets")

    def test_rejects_ambiguous_finite_or_incomplete_manifest_row(self):
        cases = (
            lambda m: m["runs"].append(deepcopy(next(r for r in m["runs"] if r["id"] == "gaming_melt_theory"))),
            lambda m: next(r for r in m["runs"] if r["id"] == "gaming_melt_theory").update(infinite_energy=False),
            lambda m: m["teams"]["gaming_melt"]["virtual_profiles"].pop(),
            lambda m: m["teams"]["gaming_melt"]["virtual_profiles"][1].update(character_key="gaming"),
            lambda m: m["teams"]["gaming_melt"].update(rotation_file=None),
        )
        for change in cases:
            manifest = deepcopy(self.manifest)
            change(manifest)
            with self.assertRaises(ValueError):
                audit.select_theory_entry(manifest, "gaming_melt_theory")

    def test_default_input_schema_matches_immutable_audit_and_alternate_is_bound(self):
        original = audit.load_json(audit.RECEIPT)
        entry = audit.select_theory_entry(self.manifest, audit.RUN_ID)
        rotation = audit.matrix._resolve_inside_root(entry["rotation_file"])
        self.assertEqual(audit.input_binding(entry, rotation), original["input"])

        selected = audit.select_theory_entry(self.manifest, "lunar_crystallize_theory")
        selected_rotation = audit.matrix._resolve_inside_root(selected["rotation_file"])
        binding = audit.input_binding(selected, selected_rotation)
        self.assertEqual(set(binding), set(original["input"]))
        self.assertEqual(binding["run_id"], selected["id"])
        self.assertEqual(binding["team"], selected["team"])
        self.assertEqual(binding["manifest_sha256"], audit.MANIFEST_SHA256)
        self.assertEqual(binding["rotation_path"], selected["rotation_file"])
        self.assertEqual(binding["rotation_sha256"], audit.sha256(selected_rotation))
        self.assertEqual(binding["profiles_sha256"], audit.canonical_sha256(selected["virtual_profiles"]))
        self.assertEqual([row["character_key"] for row in binding["profiles"]], selected["characters"])

    def test_alternate_neutral_summary_has_no_jahoda_specific_witness(self):
        raw = {"neutral_members_read": 2, "neutral_member_channel_hit_counts": [{"seed": "one"}],
               "jahoda_swirl_event_windows": {"trigger_duration_coverage": "unverified"}}
        with patch.object(audit, "capture_summary", return_value=deepcopy(raw)):
            self.assertEqual(audit.scoped_capture_summary(Path("unused"), audit.RUN_ID), raw)
            alternate = audit.scoped_capture_summary(Path("unused"), "gaming_melt_theory")
        self.assertEqual(alternate["neutral_members_read"], 2)
        self.assertNotIn("jahoda_swirl_event_windows", alternate)


if __name__ == "__main__":
    unittest.main()
