from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.experiments.gcsim.all_sets_inventory_regression.run import (
    LUNAR_JOINT_ATTEMPT4_AUTHORIZATION,
    MAX_AUTHORIZED_RECEIPT,
    MAX_AUTHORIZED_ROW,
    MAX_RECEIPT,
    receipt_bytes as json_bytes,
    preserve_before,
    store_after,
    extract_work,
    compact_search_work,
    validate_lunar_joint_attempt4,
)
from tools.experiments.gcsim.all_sets_inventory_regression.report import render_report, render_saved_repair


class InventoryRegressionRetentionTests(unittest.TestCase):
    def test_search_work_summary_preserves_totals_and_bounds_examples(self):
        rows = [{'lane': 'one' if i % 2 else 'two', 'Expansions': i,
                 'SearchSeconds': i / 10, 'formula_dps': 100-i} for i in range(200)]
        original = json.loads(json.dumps(rows))
        kept, summary = compact_search_work(rows)
        self.assertEqual(rows, original)
        self.assertLessEqual(len(kept), 64)
        self.assertFalse(summary['detail_complete'])
        self.assertEqual(summary['full_count'], 200)
        self.assertEqual(sum(x['count'] for x in summary['lanes'].values()), 200)
        self.assertEqual(sum(x['expansions'] for x in summary['lanes'].values()), sum(range(200)))
        self.assertIn(rows[0], kept)
        self.assertIn(rows[-1], kept)
        self.assertEqual(compact_search_work(rows[:4])[0], rows[:4])
        self.assertTrue(compact_search_work([])[1]['detail_complete'])

    def test_top_three_item_receipt_freezes_exact_stats_without_whole_inventory(self):
        with tempfile.TemporaryDirectory() as raw:
            scratch = Path(raw)
            run = scratch / 'runs' / 'one'
            run.mkdir(parents=True)
            items = [{'artifact_id': i, 'main_stat': {'key': 'atk', 'value': '311'},
                      'substats': [{'key': 'cr', 'value': '0.101'}]} for i in range(1, 6)]
            request = {'artifacts': items, 'context': {'prepared_config': {'text': 'same config'}}}
            (run / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            result = {'product_result': {'candidates': [
                {'artifacts': [{'artifact_id': i}]} for i in (3, 1, 3, 4, 5)]}}
            (run / 'all-sets-result.json').write_text(json.dumps(result), encoding='utf-8')
            work = extract_work(scratch)
            self.assertEqual(work['finalist_artifact_rows'], [items[0], items[2]])

    def test_receipt_compaction_cannot_change_inventory_identity_encoding(self):
        from tools.experiments.gcsim.all_sets_inventory_regression.run import json_bytes as identity_bytes
        value = [{"id": 9, "stats": {"atk": 1.0}}]
        expected = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        self.assertEqual(identity_bytes(value), expected)
        self.assertNotEqual(identity_bytes(value), json_bytes(value))

    def test_compact_encoding_preserves_every_field_and_prior_attempt(self):
        payload = {"runs": [{"id": "team", "attempt": 1, "success": False,
            "details": {"unicode": "Нилу", "value": -0.0, "missing": None}},
            {"id": "team", "attempt": 2, "values": [1.2345678901234567, 0, False]}]}
        encoded = json_bytes(payload)
        self.assertEqual(json.loads(encoded), payload)
        self.assertLess(len(encoded), len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")))

    @staticmethod
    def _authorized_payload():
        rows = [{'id': 'lunar_bloom_all_sets', 'attempt': i} for i in range(1, 4)]
        fourth = {
            'id': 'lunar_bloom_all_sets', 'attempt': 4,
            'attempt_authorization': dict(LUNAR_JOINT_ATTEMPT4_AUTHORIZATION),
        }
        return {'schema_version': 1, 'before_sha256': 'x', 'runs': rows + [fourth]}, fourth

    def test_compact_extraction_keeps_stabilization_and_all_verified_rows(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run = root / 'runs' / 'one'
            run.mkdir(parents=True)
            payload = {'neutral_stabilization': [{'single_stationary': True}],
                       'neutral_package_joint': [{'wearer_key': 'lunar'}],
                       'verification': {'iterations': 500, 'candidates': [{'rank': 7}]}}
            (run / 'all-sets-result.json').write_text(json.dumps(payload), encoding='utf-8')
            work = extract_work(root)
            self.assertEqual(work['neutral_stabilization'], payload['neutral_stabilization'])
            self.assertEqual(work['neutral_package_joint'], payload['neutral_package_joint'])
            self.assertEqual(work['verification'], payload['verification'])

    def test_lunar_attempt4_requires_exact_case_retry_and_three_prior_attempts(self):
        prior = [{'id': 'lunar_bloom_all_sets', 'attempt': i} for i in range(1, 4)]

        def args(**overrides):
            values = dict(
                authorize_lunar_bloom_joint_package_attempt_4=True,
                case='lunar_bloom_all_sets', retry=True, only=[],
            )
            values.update(overrides)
            return SimpleNamespace(**values)

        self.assertEqual(validate_lunar_joint_attempt4(args(), prior), LUNAR_JOINT_ATTEMPT4_AUTHORIZATION)
        for invalid_args, invalid_rows in (
            (args(case='other_row'), prior),
            (args(case=None), prior),
            (args(retry=False), prior),
            (args(only=['lunar_bloom_all_sets']), prior),
            (args(), prior + [{'id': 'lunar_bloom_all_sets', 'attempt': 4}]),
            (args(), [{'id': 'lunar_bloom_all_sets', 'attempt': i} for i in (1, 2, 4)]),
        ):
            with self.subTest(args=invalid_args, attempts=[row.get('attempt') for row in invalid_rows]):
                with self.assertRaises(ValueError):
                    validate_lunar_joint_attempt4(invalid_args, invalid_rows)

    def test_authorized_attempt4_appends_once_and_preserves_three_prior_attempts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / 'after.json'
            rows = [
                {'id': key, 'attempt': attempt, 'success': False}
                for key in ['lunar_bloom_all_sets', *(f'row_{i}' for i in range(13))]
                for attempt in range(1, 4)
            ]
            prior = [row.copy() for row in rows]
            fourth = {
                'id': 'lunar_bloom_all_sets', 'attempt': 4, 'success': False,
                'attempt_authorization': dict(LUNAR_JOINT_ATTEMPT4_AUTHORIZATION),
            }
            store_after(output, {'runs': rows + [fourth]}, root)
            saved = json.loads(output.read_text(encoding='utf-8'))['runs']
            self.assertEqual(saved[:len(prior)], prior)
            self.assertEqual(saved[-1], fourth)
            self.assertEqual(len(saved), 43)

            before = output.read_bytes()
            with self.assertRaises(ValueError):
                store_after(output, {'runs': saved + [{
                    'id': 'lunar_bloom_all_sets', 'attempt': 5,
                    'attempt_authorization': dict(LUNAR_JOINT_ATTEMPT4_AUTHORIZATION),
                }]}, root)
            self.assertEqual(output.read_bytes(), before)

    def test_authorized_row_and_legacy_receipt_have_separate_size_budgets(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / 'after.json'
            payload, fourth = self._authorized_payload()
            fourth['padding'] = ''
            fourth['padding'] = 'x' * (MAX_AUTHORIZED_ROW - len(json_bytes(fourth)))
            self.assertEqual(len(json_bytes(fourth)), MAX_AUTHORIZED_ROW)
            store_after(output, payload, root)

            before = output.read_bytes()
            fourth['padding'] += 'x'
            with self.assertRaises(ValueError):
                store_after(output, payload, root)
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse((root / 'after.pending.json').exists())

    def test_authorized_extension_keeps_legacy_cap_and_total_cap(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / 'after.json'
            payload, fourth = self._authorized_payload()
            legacy = dict(payload)
            legacy['runs'] = payload['runs'][:-1]
            legacy['runs'][0]['padding'] = ''
            legacy['runs'][0]['padding'] = 'x' * (MAX_RECEIPT - len(json_bytes(legacy)))
            self.assertEqual(len(json_bytes(legacy)), MAX_RECEIPT)
            self.assertLessEqual(len(json_bytes(payload)), MAX_AUTHORIZED_RECEIPT)
            store_after(output, payload, root)

            before = output.read_bytes()
            legacy['runs'][0]['padding'] += 'x'
            with self.assertRaises(ValueError):
                store_after(output, payload, root)
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse((root / 'after.pending.json').exists())

            # Check the total cap independently of per-component caps. Compact
            # JSON need not add the old repeated-indentation overhead on join.
            payload, fourth = self._authorized_payload()
            legacy = dict(payload)
            legacy['runs'] = payload['runs'][:-1]
            legacy['runs'][0]['padding'] = ''
            legacy['runs'][0]['padding'] = 'x' * (MAX_RECEIPT - len(json_bytes(legacy)))
            fourth['padding'] = ''
            fourth['padding'] = 'x' * (MAX_AUTHORIZED_ROW - len(json_bytes(fourth)))
            self.assertEqual(len(json_bytes(legacy)), MAX_RECEIPT)
            self.assertEqual(len(json_bytes(fourth)), MAX_AUTHORIZED_ROW)
            with patch("tools.experiments.gcsim.all_sets_inventory_regression.run.MAX_AUTHORIZED_RECEIPT",
                       len(json_bytes(payload)) - 1):
                with self.assertRaises(ValueError):
                    store_after(output, payload, root)
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse((root / 'after.pending.json').exists())

    def test_successor_report_distinguishes_backend_boundary_and_local_certificate(self):
        stage = dict(total_elapsed_ms=1000, search_seconds=.5, neutral_model={'RuleSeconds':.1},
            search_expansions=10, search_config={'cycles':2}, verification={'winner':dict(
                formula_dps=100, measured_dps=99, standard_error=1)})
        r = dict(source_run='saved', canonical_request_sha256='x', success=True,
            before=stage, after=stage, replay_wall_seconds=1.1, optimizer_sha256='y', engine_id='active')
        report = render_saved_repair(r)
        self.assertIn('NOT a fourth matrix retry', report)
        self.assertIn('not whole fresh UI time', report)
        self.assertIn('NOT a timeout or an exhaustive optimum', report)
        self.assertIn('n4000 feather comparison', report)

    def test_report_uses_latest_attempt_and_ordinary_measurement(self):
        # Synthetic receipt control, not an engine or search-quality witness.
        def row(dps, attempt):
            return {"id": "team", "mode": "all_sets", "success": True,
                    "attempt": attempt, "wall_seconds": 2.0,
                    "product": {"candidates": [{"formula_dps": 999999,
                        "measured": {"dps": dps, "standard_error": 1.0},
                        "builds": []}]}, "inventory_search": {"capture_members": 8}}
        before = {"runs": [row(100, 1)]}
        after = {"runs": [row(150, 1), row(120, 2)]}
        report = render_report(before, after)
        self.assertIn("| 100.0 | 120.0 | +20.00% |", report)
        self.assertIn("Attempt 2", report)
        self.assertNotIn("999999", report)
        self.assertNotIn("150.0", report)
        self.assertIn("not a physical button check", report)
        after["runs"][-1]["inventory_search"].update(search_algorithm="neutral_event_effects", neutral_cycles=[{"Prepared": 12, "Total": 12, "HeuristicSkipped": 4}])
        neutral = render_report(before, after)
        self.assertIn("prepared 12/12", neutral)
        self.assertIn("n500 once per finalist", neutral)
        self.assertNotIn("current engine was not rebuilt", neutral)
        self.assertIn("NOT an unfinished preparation queue or a timeout", neutral)
        after["runs"][-1]["inventory_search"]["neutral_package_joint"] = [
            {"Finished": True, "Proposals": 12, "Scored": 8, "Refined": 3, "Seconds": 1.5},
            {"Finished": False, "Proposals": 4, "Scored": 1, "Refined": 0, "Seconds": .5},
        ]
        joint = render_report(before, after)
        self.assertIn("1/2 bounded lanes completed", joint)
        self.assertIn("16 pair proposals", joint)
        self.assertIn("2.00s within search time", joint)
        self.assertIn("NOT an exhaustive joint optimum", joint)
        self.assertNotIn("region leaves left by work limits", neutral)
        after["review_notes"] = ["A dated earlier failure."]
        self.assertIn("Historical analysis at the first", render_report(before, after))

    def test_user_interruption_is_not_reported_as_completed_or_quality_failure(self):
        baseline = {"id": "team", "mode": "all_sets", "product": {"candidates": [
            {"measured": {"dps": 100, "standard_error": 1}, "builds": []}]}}
        stopped = {"id": "team", "success": False, "interrupted_by_user": True,
                   "interruption_note": "Stopped by user; original status retained.",
                   "error": "process exit 1", "wall_seconds": 12}
        report = render_report({"runs": [baseline]}, {"runs": [stopped],
            "matrix_status": "stopped_by_user", "stop_reason": "No automatic resume."})
        self.assertIn("Successful retained non-Gaming rows: 0/1; user-interrupted: 1", report)
        self.assertIn("| interrupted |", report)
        self.assertIn("process exit 1", report)
        self.assertIn("No automatic resume.", report)
        self.assertNotIn("| FAILED |", report)

    def test_original_is_preserved_and_existing_evidence_is_immutable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, output = root / "original.json", root / "docs/before.json"
            original = b'{"historical_failure": true}\r\n'
            source.write_bytes(original)
            digest = preserve_before(source, output)
            self.assertEqual(preserve_before(source, output), digest)
            self.assertEqual(source.read_bytes(), original)
            source.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                preserve_before(source, output)
            self.assertEqual(output.read_bytes(), original)

    def test_failed_attempt_is_retained_and_fourth_attempt_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "after.json"
            rows = [{"id": "same", "success": False, "attempt": i} for i in range(1, 4)]
            store_after(output, {"runs": rows}, root)
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                store_after(output, {"runs": rows + [{"id": "same"}]}, root)
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse((root / "after.pending.json").exists())

    def test_size_failure_does_not_destroy_previous_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "after.json"
            output.write_bytes(b"previous")
            with self.assertRaises(ValueError):
                store_after(output, {"runs": [{"id": "a", "text": "x" * (8 * 1024 * 1024)}]}, root)
            self.assertEqual(output.read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
