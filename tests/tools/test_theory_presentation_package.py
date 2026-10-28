"""Exact packet retention and named legacy retirement; no engine or Git writes."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.experiments.gcsim.theory_release import package_io as io
from tools.experiments.gcsim.theory_presentation import package as packet


class PresentationPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.evidence = self.repo / packet.EVIDENCE
        (self.evidence / "package/payloads").mkdir(parents=True)

    def _manifest(self, bodies):
        records = {}
        for index, (relative, body, reused) in enumerate(bodies):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            records[str(index)] = {
                "repository_path": relative, "sha256": io.sha_bytes(body),
                "bytes": len(body), "reused_exact_prior_payload_after_fresh_replay": reused,
            }
        (self.evidence / "package/manifest.json").write_text(json.dumps({"payload_sources": records}), encoding="utf-8")

    def test_cleanup_requires_explicit_acceptance_before_reading_any_packet(self):
        with self.assertRaisesRegex(ValueError, "acceptance"):
            packet.cleanup_packet(self.repo)

    def test_cleanup_removes_only_exact_new_payloads_and_preserves_prior_and_receipts(self):
        own = packet.EVIDENCE + "/package/payloads/new.patch"
        prior = packet.PREVIOUS + "/package/theory/old.patch"
        self._manifest([(own,b"owned",False),(prior,b"old",True)])
        receipt = self.evidence / "receipt.json"; receipt.write_bytes(b"keep receipt")
        other = self.evidence / "package/payloads/unlisted.txt"; other.write_bytes(b"keep other")
        result = packet.cleanup_packet(self.repo,accepted_or_consolidated=True)
        self.assertEqual((result["removed_files"],result["removed_bytes"]),(1,5))
        self.assertFalse((self.repo/own).exists())
        self.assertEqual((self.repo/prior).read_bytes(),b"old")
        self.assertEqual(receipt.read_bytes(),b"keep receipt")
        self.assertEqual(other.read_bytes(),b"keep other")
        self.assertTrue((self.evidence/"package/manifest.json").exists())

    def test_late_modified_payload_refuses_before_any_deletion(self):
        first=packet.EVIDENCE+"/package/payloads/first.patch"
        second=packet.EVIDENCE+"/package/payloads/second.patch"
        self._manifest([(first,b"first",False),(second,b"second",False)])
        (self.repo/second).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"changed"):
            packet.cleanup_packet(self.repo,accepted_or_consolidated=True)
        self.assertEqual((self.repo/first).read_bytes(),b"first")
        self.assertEqual((self.repo/second).read_bytes(),b"changed")

    def test_foreign_cleanup_scope_is_rejected_and_preserved(self):
        foreign="ui/untouched.patch"
        self._manifest([(foreign,b"foreign",False)])
        with self.assertRaisesRegex(ValueError,"scope"):
            packet.cleanup_packet(self.repo,accepted_or_consolidated=True)
        self.assertEqual((self.repo/foreign).read_bytes(),b"foreign")

    def test_named_formatter_retirement_keeps_adjacent_live_base_helpers(self):
        body=b'from .optimizer_go_result_text import format_optimizer_warning\n\nclass Base:\n    def finite_guard(self):\n        return "retained"\n\ndef format_gcsim_optimizer_go_theory_result(payload):\n    return "obsolete"\n\ndef theory_available():\n    return True\n\n__all__ = [\n    "format_gcsim_optimizer_go_theory_result",\n    "theory_available",\n]\n'
        after=packet._retire_legacy(packet.LEGACY[0],body,self.repo)
        self.assertIn(b'def finite_guard',after)
        self.assertIn(b'def theory_available',after)
        self.assertNotIn(b'format_gcsim_optimizer_go_theory_result',after)


if __name__=="__main__":unittest.main()
