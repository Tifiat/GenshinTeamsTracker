package seteffects

import (
	"go/ast"
	"testing"
)

func TestHypothesisAmountPlanKeepsCurrentStorageAndClearBinding(t *testing.T) {
	v := testRule(t, `func Start() any {m:=[]float64{5,6};return func() []float64 {clear(m);m[1]=9;return m}}`, nil)
	value, err := v.entry("Start")
	if err != nil { t.Fatal(err) }
	fn := value.(*ruleFunction)
	first := v.amountScratch(fn)
	if first == nil || !v.hypothesisAmountPlans[fn.body].valid { t.Fatal("safe syntax was not prepared") }
	for i := 0; i < 2; i++ {
		out, err := ruleTry(func() any { return v.invokeAmount(fn, nil) })
		if err != nil || ruleArray(out)[0] != float64(0) || ruleArray(out)[1] != float64(9) {
			t.Fatal("scratch replay changed", out, err)
		}
		if first.values[0] != float64(5) || first.values[1] != float64(6) { t.Fatal("scratch was not restored") }
	}
	second := &ruleSlice{values: []any{float64(12), float64(13)}}
	fn.env.vars["m"] = second
	if got := v.amountScratch(fn); got != second { t.Fatal("plan retained old array") }
	second.observed = true
	if got := v.amountScratch(fn); got != nil { t.Fatal("observed array admitted") }
	second.observed = false
	fn.env.vars["clear"] = float64(1)
	if got := v.amountScratch(fn); got != nil { t.Fatal("shadowed clear admitted") }
	delete(fn.env.vars, "clear")
	if len(v.hypothesisAmountPlans) != 1 || len(v.hypothesisAmountOrder) != 1 { t.Fatal("syntax plan was rebuilt") }
}

func TestHypothesisAmountPlanFallsBackForAliasAndBoundsOwnership(t *testing.T) {
	v := testRule(t, `func Start() any {m:=[]float64{5,6};return func() []float64 {alias:=m;clear(alias);return m}}`, nil)
	value, err := v.entry("Start")
	if err != nil { t.Fatal(err) }
	fn := value.(*ruleFunction)
	if got := v.amountScratch(fn); got != nil || v.hypothesisAmountPlans[fn.body].valid {
		t.Fatal("alias plan did not fall back")
	}
	if _, err := ruleTry(func() any { return v.invokeAmount(fn, nil) }); err == nil {
		t.Fatal("alias escaped legacy lifecycle boundary")
	}
	for i := 0; i < hypothesisAmountPlanLimit+9; i++ {
		body := &ast.BlockStmt{List: []ast.Stmt{&ast.ReturnStmt{Results: []ast.Expr{ast.NewIdent("m")}}}}
		v.hypothesisAmountPlan(body)
	}
	if len(v.hypothesisAmountPlans) > hypothesisAmountPlanLimit || len(v.hypothesisAmountOrder) != len(v.hypothesisAmountPlans) {
		t.Fatal("VM syntax-plan cache exceeded its bound")
	}
}
