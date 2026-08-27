from __future__ import annotations

import unittest

from run_workspace.gcsim.optimizer_effect_observation import GcsimEffectObservationRequest
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimSetResponseChange,
    GcsimStatResponseChange,
    GcsimStatResponseChangeMode,
    GcsimStatResponseIntervention,
    GcsimStatResponseObjective,
    GcsimStatResponseRequest,
)


class M3CrossLanguageCanonicalHashTests(unittest.TestCase):
    def test_stat_only_omits_set_fields(self):
        payload = GcsimStatResponseChange(0, "cr", GcsimStatResponseChangeMode.ADD, .1).to_dict()
        self.assertNotIn("set_key", payload)
        self.assertNotIn("set_count", payload)

    def test_explicit_counts_match_go_hashes_for_both_contracts(self):
        expected_stat = {
            0: "6a6ad6409975f3c564d30f396144b76782ac6d6406fcfe6f9a734a79ecfa508a",
            2: "194252b86707c1179f0a4f7041ebf8d980c65c5263c27aa8ae65ee8991291baa",
            4: "5132909fd5d181e8121df46719be5f49907db7a8558938a25376f6225783ffcb",
        }
        expected_effect = {
            0: "611e5326f3997205adc9efb576240bcacd44e310adecc17951604ff5e9d43dc6",
            2: "dd8e17ac6da6026081f843d26dbfaed66d5842931591cadd0b332eccbb85f0f5",
            4: "f68d12357cc4b4208df53ed0a49befa9601b6f2959bd2f419cfc81925fc368c5",
        }
        for count in (0, 2, 4):
            with self.subTest(count=count):
                change = GcsimSetResponseChange(0, "noblesse", count)
                self.assertEqual(change.to_dict()["set_count"], count)
                rows = (GcsimStatResponseIntervention(f"set-{count}", (change,)),)
                stat = GcsimStatResponseRequest("a"*64, GcsimStatResponseObjective.DPS, 8, 1, 123, (), rows)
                effect = GcsimEffectObservationRequest("a"*64, GcsimStatResponseObjective.DPS, 8, 1, 123, (), rows)
                self.assertEqual(stat.request_sha256, expected_stat[count])
                self.assertEqual(effect.request_sha256, expected_effect[count])


if __name__ == "__main__": unittest.main()
