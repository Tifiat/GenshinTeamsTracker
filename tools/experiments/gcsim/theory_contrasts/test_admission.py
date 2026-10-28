"""Pure tests for the one prospective Chasca-to-Nilou admission."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from . import admission

ROOT = Path(__file__).resolve().parents[4]
RECEIPT_PATH = ROOT / "docs/optimizer-evidence/2026-10-09-theory-contrasts/chasca-01.json"
CURRENT_PROTOTYPE_SHA256 = "a" * 64


def saved_receipt():
    return json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))


def validate(result, *, receipt_sha=None, prototype_sha=None, protocol_sha=None):
    return admission.validate_prerequisite(
        result,
        admission.ORIGINAL_RECEIPT_SHA256 if receipt_sha is None else receipt_sha,
        CURRENT_PROTOTYPE_SHA256 if prototype_sha is None else prototype_sha,
        admission.CONTINUATION_SHA256 if protocol_sha is None else protocol_sha,
    )


class AdmissionTests(unittest.TestCase):
    def test_exact_receipt_is_admitted_without_mutation(self):
        result = saved_receipt()
        before = copy.deepcopy(result)
        seconds = validate(result)
        self.assertEqual(seconds, 134.9347829)
        self.assertEqual(result, before)
        info = admission.decision_info()
        self.assertEqual(info["authorized_case"], "bountiful_core")
        self.assertEqual(info["original_receipt_sha256"], admission.ORIGINAL_RECEIPT_SHA256)

    def test_wrong_receipt_digest_is_refused(self):
        with self.assertRaisesRegex(ValueError, "receipt digest"):
            validate(saved_receipt(), receipt_sha="0" * 64)

    def test_wrong_current_prototype_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Current prototype digest"):
            validate(saved_receipt(), prototype_sha="not-a-sha")

    def test_wrong_current_protocol_is_refused(self):
        with self.assertRaisesRegex(ValueError, "continuation decision"):
            validate(saved_receipt(), protocol_sha="0" * 64)

    def test_incomplete_policy_is_refused_on_reevaluation(self):
        result = saved_receipt()
        row = next(r for r in result["records"] if r.get("kind") == "light_policy_result")
        row["complete"] = False
        with self.assertRaisesRegex(ValueError, "technical acceptance no longer passes"):
            validate(result)

    def test_changed_engine_identity_is_refused(self):
        result = saved_receipt()
        result["engine"]["artifact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "technical acceptance no longer passes"):
            validate(result)

    def test_changed_capture_budget_is_refused(self):
        result = saved_receipt()
        result["capture_members_actual"] = 1
        with self.assertRaisesRegex(ValueError, "technical acceptance no longer passes"):
            validate(result)

    def test_incomplete_cleanup_is_refused(self):
        result = saved_receipt()
        result["cleanup"]["job_absent"] = False
        with self.assertRaisesRegex(ValueError, "technical acceptance no longer passes"):
            validate(result)

    def test_different_quality_failure_is_refused(self):
        result = saved_receipt()
        result["quality_gate"]["failures"] = ["light_leader_deficit_over_1_percent"]
        with self.assertRaisesRegex(ValueError, "quality failure differs"):
            validate(result)


if __name__ == "__main__":
    unittest.main()
