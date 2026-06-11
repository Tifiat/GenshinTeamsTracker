from __future__ import annotations

import unittest

from hoyolab_export.artifact_build_snapshot import build_artifact_build_snapshot
from hoyolab_export.stat_normalization import (
    STAT_UNIT_FLAT,
    STAT_UNIT_RATIO,
    WARNING_STAT_PROPERTY_TYPE_UNKNOWN,
    normalize_artifact_build_snapshot_stats,
    normalize_artifact_stat_total,
    normalized_stats_to_gcsim_add_stats,
)


class StatNormalizationTest(unittest.TestCase):
    def test_percent_point_hp_is_converted_to_ratio(self) -> None:
        stat = normalize_artifact_stat_total(
            {"property_type": 3, "property_name": "HP%", "raw_value": 46.6}
        )

        self.assertEqual(stat.key, "hp_percent")
        self.assertEqual(stat.gcsim_key, "hp%")
        self.assertEqual(stat.unit, STAT_UNIT_RATIO)
        self.assertAlmostEqual(stat.value or 0, 0.466)
        self.assertEqual(stat.source_numeric, 46.6)

    def test_crit_rate_is_converted_to_gcsim_ratio(self) -> None:
        stat = normalize_artifact_stat_total(
            {"property_type": 20, "property_name": "CRIT Rate", "raw_value": 31.1}
        )

        self.assertEqual(stat.key, "crit_rate")
        self.assertEqual(stat.gcsim_key, "cr")
        self.assertAlmostEqual(stat.value or 0, 0.311)

    def test_flat_em_is_preserved(self) -> None:
        stat = normalize_artifact_stat_total(
            {"property_type": 28, "property_name": "EM", "raw_value": 187}
        )

        self.assertEqual(stat.key, "elemental_mastery")
        self.assertEqual(stat.gcsim_key, "em")
        self.assertEqual(stat.unit, STAT_UNIT_FLAT)
        self.assertEqual(stat.value, 187)

    def test_unknown_property_type_warns(self) -> None:
        stat = normalize_artifact_stat_total(
            {"property_type": 999, "property_name": "Mystery", "raw_value": 1}
        )

        self.assertIn(WARNING_STAT_PROPERTY_TYPE_UNKNOWN, stat.warnings)
        self.assertEqual(stat.gcsim_key, "")

    def test_artifact_build_snapshot_block_preserves_provenance(self) -> None:
        snapshot = build_artifact_build_snapshot(
            {
                "total_stats": [
                    {"property_type": 20, "property_name": "CR", "raw_value": 31.1},
                    {"property_type": 22, "property_name": "CD", "raw_value": 62.2},
                ],
                "crit_value": 124.4,
                "proc_count": 9,
            },
            build_preset={"id": 7, "name": "Smoke"},
        )

        block = normalize_artifact_build_snapshot_stats(snapshot)
        self.assertEqual(block.source_notes["build_id"], 7)
        self.assertTrue(block.source_notes["crit_value_is_virtual"])
        self.assertEqual(len(block.values), 2)

    def test_gcsim_add_stats_excludes_virtual_metrics(self) -> None:
        snapshot = build_artifact_build_snapshot(
            {
                "total_stats": [
                    {"property_type": 20, "property_name": "CR", "raw_value": 31.1},
                    {"property_type": 28, "property_name": "EM", "raw_value": 187},
                ],
                "crit_value": 124.4,
                "proc_count": 9,
            }
        )

        block = normalize_artifact_build_snapshot_stats(snapshot)
        add_stats = normalized_stats_to_gcsim_add_stats(block)

        self.assertEqual(set(add_stats), {"cr", "em"})
        self.assertAlmostEqual(add_stats["cr"], 0.311)
        self.assertEqual(add_stats["em"], 187)
        self.assertNotIn("crit_value", add_stats)
        self.assertNotIn("proc_count", add_stats)


if __name__ == "__main__":
    unittest.main()
