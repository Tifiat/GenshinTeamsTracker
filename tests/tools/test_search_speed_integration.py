"""Small contracts for the managed source-copy promotion proposal."""

import unittest

from tools.experiments.gcsim.search_hypotheses.integration_patch import (
    HELPERS, patch_file, product_relative, production_names, production_source,
)


class SearchSpeedIntegrationTests(unittest.TestCase):
    def test_exact_only_promotion_drops_unused_narrowing_wrapper(self):
        wrapper = """func (engine *Engine) RefineCandidatesHypothesisNarrow(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
\tprevious := engine.config.RecheckFrontierWidth
\tengine.config.RecheckFrontierWidth = 2
\tdefer func() { engine.config.RecheckFrontierWidth = previous }()
\treturn engine.RefineCandidates(ctx, anchor, actor, allowance)
}

"""
        original = "func unchanged() {}\n"
        relative = "internal/search/candidates.go"
        self.assertEqual(production_source(relative, wrapper + original, "player_safe_wide"), original)
        with self.assertRaisesRegex(ValueError, "Only the reviewed"):
            production_source(relative, wrapper + original, "amount_plan")
        with self.assertRaisesRegex(ValueError, "wrapper changed"):
            production_source(relative, original, "player_safe_wide")

    def test_production_names_replace_whole_tokens_only(self):
        source = (
            "hypothesisView() HypothesisRegionStats "
            "HypothesisRegionsStats hypothesisView2 "
            "otherhypothesisView _hypothesisView "
            "x.hypothesisView()"
        )
        result = production_names(source)
        self.assertIn("contextView()", result)
        self.assertIn("RegionBindingStats RegionBindingStats", result)
        self.assertIn("hypothesisView2", result)
        self.assertIn("otherhypothesisView", result)
        self.assertIn("_hypothesisView", result)
        self.assertIn("x.contextView()", result)
        self.assertEqual(production_names("TestHypothesisAmountPlan BenchmarkHypothesisRegions OtherHypothesis"),
                         "TestAmountPlan BenchmarkRegions OtherHypothesis")

    def test_patch_file_noop_add_and_update(self):
        self.assertEqual(patch_file("internal/example.go", "same\n", "same\n"), "")
        added = patch_file("internal/example.go", None, "package example\n\nfunc x() {}\n")
        self.assertEqual(added, "*** Add File: native/gcsim_optimizer/internal/example.go\n"
                         "+package example\n+\n+func x() {}\n")
        updated = patch_file("internal/example.go", "package example\nold\n",
                             "package example\nnew\n")
        self.assertTrue(updated.startswith("*** Update File: native/gcsim_optimizer/internal/example.go\n@@\n"))
        self.assertIn("-old\n+new\n", updated)
        self.assertNotIn("--- ", updated)
        self.assertNotIn("+++ ", updated)

    def test_only_explicit_product_helpers_are_promoted(self):
        self.assertIsNone(product_relative("internal/setcontext/hypothesis_point_screen.go"))
        self.assertEqual(product_relative("internal/formula/parametric_program.go"),
                         "internal/formula/parametric_program.go")
        for excluded in (
            "cmd/gtt-optimizer/hypothesis_replay_test.go",
            "cmd/gtt-optimizer/hypothesis_exact_rescore_test.go",
            "internal/search/hypothesis_player_filter.go",
            "internal/seteffects/hypothesis_bonus_approx.go",
            "internal/seteffects/hypothesis_literal_fast.go",
            "internal/seteffects/hypothesis_player_uptime.go",
            "internal/setcontext/hypothesis_point_screen_test.go",
            "internal/allsets/hypothesis_point_packages.go",
        ):
            self.assertNotIn(excluded, HELPERS)
            self.assertIsNone(product_relative(excluded), excluded)
        self.assertEqual(len(set(HELPERS.values())), len(HELPERS))


if __name__ == "__main__":
    unittest.main()
