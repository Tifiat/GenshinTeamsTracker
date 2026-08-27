from __future__ import annotations

from unittest import TestCase

from tools.experiments.gcsim_optimizer_m6_offline_forensic_checkpoint import (
    build_checkpoint,
)


class M6OfflineForensicCheckpointTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=build_checkpoint(workers=2)

    def test_exact_join_and_known_scorer_failure_are_reproduced(self):
        row=self.payload["join"]
        self.assertEqual(row["m4_n8_join_count"],208)
        self.assertEqual(row["m4_n32_join_count"],32)
        self.assertAlmostEqual(row["pearson_m4_vs_n32_exact"],0.41394851391420545)
        self.assertLess(row["spearman_m4_vs_n32_exact"],0.3)
        states=self.payload["three_state_forensics"]
        self.assertAlmostEqual(states["accepted_control"]["exact"]["team_dps"]["mean"],141846.9273156144)
        self.assertAlmostEqual(states["m4_top"]["exact"]["team_dps"]["mean"],101292.8917141633)
        self.assertAlmostEqual(states["exact_natural_top"]["exact"]["team_dps"]["mean"],113269.35986432519)

    def test_real_direction_replay_fails_closed_without_control_tuning(self):
        diagnosis=self.payload["typed_generation_diagnosis"]
        self.assertEqual(diagnosis["real_typed_operator_count"],0)
        self.assertFalse(diagnosis["authoritative_physical_bundle_evidence_persisted"])
        self.assertEqual(diagnosis["actual_direction_level_replay_status"],"blocked_fail_closed")
        self.assertFalse(diagnosis["real_domain_typed_generation_nonzero"])
        self.assertFalse(self.payload["next_bounded_milestone"]["accepted_control_ids_may_tune_generation"])
        self.assertEqual(self.payload["response_probe_count"],0)
        self.assertFalse(self.payload["gcsim_started"])

    def test_three_physical_states_are_complete_and_counted(self):
        for row in self.payload["three_state_forensics"].values():
            physical=row["physical"]
            self.assertEqual(len(physical["artifact_ids"]),20)
            self.assertEqual(len(set(physical["artifact_ids"])),20)
            self.assertEqual(len(physical["artifacts"]),20)
            self.assertEqual(set(physical["off_piece_slots"]),{"1","2","3","4"})
            self.assertTrue(physical["set_states"])
