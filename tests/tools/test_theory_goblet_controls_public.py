from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.experiments.gcsim.theory_goblet_controls.projection import project_trace
from tools.experiments.gcsim.theory_goblet_controls.storage import cleanup_public_exports


def _provider(kind: str, key: str, owner: int, pieces: int, *, known: bool = True) -> dict:
    return {
        "known": known,
        "kind": kind,
        "key": key,
        "owner_index": owner,
        "piece_count": pieces,
    }


def _raw_trace() -> dict:
    petra = _provider("set", "archaicpetra", 2, 4)
    aubade = _provider("set", "aubadeofmorningstarandmoon", 1, 4)
    silken = _provider("set", "silkenmoonsserenade", 0, 4)
    unknown = _provider("unattributed", "unknown", -1, 0, known=False)
    return {
        "schema_version": 6,
        "engine_version": "gcsim-v2.45.0-test",
        "seed": "742031889",
        "duration_frames": 120,
        "character_keys": ["xilonen", "furina", "columbina", "chiori"],
        "context_sha256": "a" * 64,
        "request_sha256": "b" * 64,
        "source_config_sha256": "c" * 64,
        "compiled_action_sha256": "d" * 64,
        "target_sha256": "e" * 64,
        "formula_sha256": "f" * 64,
        "source_manifest_body_sha256": "1" * 64,
        "hits": [
            {
                "hit_id": 11,
                "frame": 10,
                "actor_index": 3,
                "target_type": 0,
                "reported_damage": 100.0,
                "stat_contributions": [{
                    "provider": petra,
                    "recipient_index": 3,
                    "modifier_key": "archaic-4pc",
                    "accepted": True,
                    "values": {"dmg%": 0.35},
                    "modifier_eval_event_id": "state-event:0",
                }],
            },
            {
                "hit_id": 12,
                "frame": 12,
                "actor_index": 2,
                "target_type": 2,
                "reported_damage": 900.0,
            },
            {
                "hit_id": 13,
                "frame": 30,
                "actor_index": 0,
                "target_type": 0,
                "reported_damage": 50.0,
                "stat_contributions": [
                    {
                        "provider": petra,
                        "recipient_index": 3,
                        "modifier_key": "archaic-4pc",
                        "accepted": True,
                        "values": {"dmg%": 0.35},
                        "modifier_eval_event_id": "state-event:0",
                    },
                    {
                        "provider": unknown,
                        "recipient_index": 0,
                        "modifier_key": "unattributed",
                        "accepted": False,
                        "values": {},
                        "modifier_eval_event_id": "",
                    },
                ],
            },
            {
                "hit_id": 14,
                "frame": 40,
                "actor_index": 1,
                "target_type": 0,
                "reported_damage": 25.0,
                "stat_contributions": [{
                    "provider": silken,
                    "recipient_index": 1,
                    "modifier_key": "silken-moons-4pc",
                    "accepted": True,
                    "values": {"em": 60.0},
                    "modifier_eval_event_id": "state-event:1",
                }],
                "reaction_bonus_contributions": [{
                    "provider": aubade,
                    "modifier_key": "aubade-4pc",
                    "value": 0.2,
                }],
            },
            {
                "hit_id": 15,
                "frame": 42,
                "actor_index": 1,
                "target_type": 1,
                "reported_damage": 300.0,
            },
        ],
        "provider_transitions": [{
            "frame": 9,
            "channel": "stat",
            "recipient_index": 3,
            "modifier_key": "archaic-4pc",
            "transition": "added",
            "provider": petra,
        }],
        "state_events": [
            {
                "event_id": "state-event:0",
                "frame": 9,
                "kind": "modifier_eval",
                "source_id": "source-petra",
                "source_occurrence_id": "occ-petra",
                "provider": petra,
                "channel": "stat",
                "key": "archaic-4pc",
                "owner_index": 3,
                "output": {"dmg%": 0.35},
            },
            {
                "event_id": "state-event:1",
                "frame": 38,
                "kind": "modifier_eval",
                "source_id": "source-silken",
                "source_occurrence_id": "occ-silken",
                "provider": silken,
                "channel": "stat",
                "key": "silken-moons-4pc",
                "owner_index": 1,
                "output": {"em": 60.0},
            },
        ],
        "source_occurrences": [
            {
                "occurrence_id": "occ-petra",
                "source_id": "source-petra",
                "seam": "event_callback",
                "frame": 8,
                "parent_occurrence_id": None,
                "provider": petra,
                "terminal_event_id": "state-event:0",
            },
            {
                "occurrence_id": "occ-silken",
                "source_id": "source-silken",
                "seam": "event_callback",
                "frame": 37,
                "parent_occurrence_id": None,
                "provider": silken,
                "terminal_event_id": "state-event:1",
            },
        ],
    }


class TraceProjectionTests(unittest.TestCase):
    def test_enemy_totals_recipient_provenance_and_unknown_pickup(self):
        projected = project_trace(_raw_trace())
        self.assertEqual(projected["identity"]["actor_order"][2]["character_key"], "columbina")
        self.assertEqual(projected["identity"]["seed"], "742031889")
        self.assertEqual(projected["damage"]["enemy_reported_damage"], 175.0)
        self.assertEqual(projected["damage"]["actual_dps"], 87.5)
        self.assertEqual(projected["damage"]["excluded_non_enemy_hit_count"], 2)
        self.assertEqual(projected["damage"]["excluded_non_enemy_reported_damage"], 1200.0)

        petra = projected["petra"]
        group = petra["stat_contribution_groups"][0]
        self.assertEqual(group["provider"]["owner_index"], 2)
        self.assertEqual(group["recipient_index"], 3)
        self.assertNotEqual(group["provider"]["owner_index"], group["recipient_index"])
        self.assertEqual(group["first_frame"], 10)
        self.assertEqual(group["last_frame"], 30)
        self.assertEqual(group["hit_count"], 2)
        self.assertEqual(group["source_occurrence_proof_ids"], ["occ-petra"])
        self.assertEqual(petra["source_occurrence_proofs"][0]["source_id"], "source-petra")
        self.assertEqual(petra["modifier_eval_event_proofs"][0]["event_id"], "state-event:0")
        self.assertTrue(petra["runtime_contribution_observed"])
        self.assertEqual(petra["activation_route"], "unknown")
        self.assertEqual(petra["pickup"], {"status": "unknown", "picker_index": None})

        sets = projected["set_observations"]
        self.assertEqual(sets["aubadeofmorningstarandmoon"]["nonzero_reaction_bonus_contribution_count"], 1)
        self.assertEqual(sets["silkenmoonsserenade"]["accepted_nonzero_stat_contribution_count"], 1)

    def test_unknown_provider_is_ignored_and_missing_petra_stays_unknown(self):
        raw = _raw_trace()
        for hit in raw["hits"]:
            hit["stat_contributions"] = [
                row for row in hit.get("stat_contributions", [])
                if row["provider"]["key"] != "archaicpetra"
            ]
        raw["provider_transitions"] = []
        projected = project_trace(raw)
        self.assertFalse(projected["petra"]["runtime_contribution_observed"])
        self.assertEqual(projected["petra"]["runtime_contribution_count"], 0)
        self.assertEqual(projected["petra"]["pickup"]["status"], "unknown")
        self.assertEqual(projected["petra"]["activation_route"], "unknown")
        self.assertEqual(
            projected["set_observations"]["aubadeofmorningstarandmoon"]
            ["reaction_bonus_contribution_count"],
            1,
        )

    def test_nonfinite_damage_is_rejected(self):
        raw = _raw_trace()
        raw["hits"][0]["reported_damage"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            project_trace(raw)


class PublicExportCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt = {
            "schema_kind": "gtt_theory_goblet_controls_validation_v1",
            "retained_public_files": [],
        }
        for name in ("comparison.json", "proc-evidence.json"):
            body = (name + " public bytes").encode()
            (self.root / name).write_bytes(body)
            self.receipt["retained_public_files"].append({
                "path": name,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            })
        for name, body in (
            ("protocol.json", "protocol"),
            ("pins.json", "pins"),
            ("validation-01.json", "receipt"),
            ("report.md", "report"),
            ("foreign.csv", "foreign"),
        ):
            (self.root / name).write_text(body, encoding="utf-8")

    def test_gate_defaults_closed(self):
        with self.assertRaisesRegex(ValueError, "acceptance"):
            cleanup_public_exports(self.root, self.receipt)
        self.assertTrue((self.root / "comparison.json").exists())

    def test_exact_cleanup_preserves_protocol_pins_receipts_and_report(self):
        result = cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertEqual(result["removed_files"], 2)
        self.assertEqual(result["removed_bytes"], sum(row["bytes"] for row in self.receipt["retained_public_files"]))
        for name in ("comparison.json", "proc-evidence.json"):
            self.assertFalse((self.root / name).exists())
        for name in ("protocol.json", "pins.json", "validation-01.json", "report.md", "foreign.csv"):
            self.assertTrue((self.root / name).exists())

    def test_hash_mismatch_blocks_all_deletion(self):
        (self.root / "proc-evidence.json").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "comparison.json").exists())

    def test_unknown_or_unowned_path_blocks_all_deletion(self):
        self.receipt["retained_public_files"].append({
            "path": "../outside.json",
            "bytes": 1,
            "sha256": "0" * 64,
        })
        with self.assertRaisesRegex(ValueError, "invalid"):
            cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "comparison.json").exists())

    def test_symlink_export_is_rejected(self):
        target = self.root / "comparison.json"
        target.unlink()
        try:
            target.symlink_to(self.root / "foreign.csv")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "linked"):
            cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "proc-evidence.json").exists())

    def test_reparse_point_root_is_rejected(self):
        original_lstat = Path.lstat

        def fake_lstat(path):
            if path == self.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original_lstat(path)

        with patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(ValueError, "linked"):
                cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "comparison.json").exists())


if __name__ == "__main__":
    unittest.main()
