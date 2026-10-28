"""Guarded research overlay for immutable Amount syntax-plan reuse."""


def apply_amount_plan(root, replace):
    replace(root, "internal/seteffects/rule_program.go",
            "\tregistrationEvents map[int]bool",
            "\tregistrationEvents map[int]bool\n\thypothesisAmountPlans map[*ast.BlockStmt]hypothesisAmountPlan\n\thypothesisAmountOrder []*ast.BlockStmt")
    # Keep the original implementation as a complete fallback for every
    # rejected/unknown source shape; only syntactically proven plans take the
    # new path. The new method lives in a copied research-only Go source file.
    replace(root, "internal/seteffects/rule_amount.go",
            "func (v *ruleVM) amountScratch(fn *ruleFunction) *ruleSlice {",
            "func (v *ruleVM) amountScratchLegacy(fn *ruleFunction) *ruleSlice {")
