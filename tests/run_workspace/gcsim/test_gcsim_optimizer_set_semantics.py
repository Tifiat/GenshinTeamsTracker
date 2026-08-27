from __future__ import annotations

import unittest

from run_workspace.gcsim.optimizer_set_semantics import (
    GcsimOptimizerSetSemanticStatus,
    build_gcsim_optimizer_set_semantic_manifest,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerSetSemanticsTests(unittest.TestCase):
    def test_manifest_never_invents_four_piece_or_unknown_semantics(self) -> None:
        environment = build_oracle_account_environment()

        manifest = build_gcsim_optimizer_set_semantic_manifest(
            environment.engine
        )

        self.assertTrue(manifest.effects)
        self.assertEqual(len(manifest.identity_sha256), 64)
        for effect in manifest.effects:
            if effect.set_count == 4:
                self.assertIs(
                    effect.status,
                    GcsimOptimizerSetSemanticStatus.OPAQUE,
                )
            if effect.status is GcsimOptimizerSetSemanticStatus.OPAQUE:
                self.assertEqual(effect.stat_axis, "")
                self.assertEqual(effect.stacking_operator, "")
            else:
                self.assertEqual(effect.trigger, "unconditional")
                self.assertEqual(effect.recipient_scope, "wearer")
                self.assertEqual(
                    effect.stacking_operator,
                    "replace_same_group_add_distinct",
                )


if __name__ == "__main__":
    unittest.main()
