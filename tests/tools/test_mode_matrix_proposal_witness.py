"""The disposable Theory run must retain its bounded shortlist receipt."""

import json
from pathlib import Path
import tempfile
import unittest

from tools.experiments.gcsim.mode_matrix.run_product_matrix import _theory_proposal_witness


class TheoryProposalWitnessTest(unittest.TestCase):
    def test_selects_nested_wrapper_not_lexically_later_product_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "theory-result.json").write_text(
                json.dumps({"status": "success", "candidates": []}), encoding="utf-8"
            )
            nested = root / "theory"
            nested.mkdir()
            (nested / "theory-result.json").write_text(
                json.dumps({
                    "proposal_report": {
                        "packages_considered": 12,
                        "unqueued": 11,
                        "queue": [{
                            "wearer": 2,
                            "lane": "wearer",
                            "priority_not_candidate_dps": 10.0,
                            "package": {"sets": [{"set_uid": "example", "count": 4}]},
                        }],
                    }
                }), encoding="utf-8"
            )

            receipt = _theory_proposal_witness(root)

        self.assertEqual(receipt["packages_considered"], 12)
        self.assertEqual(receipt["unqueued"], 11)
        self.assertEqual(receipt["queue"][0]["wearer_index"], 2)
        self.assertEqual(receipt["queue"][0]["sets"], [{"set_uid": "example", "count": 4}])


if __name__ == "__main__":
    unittest.main()
