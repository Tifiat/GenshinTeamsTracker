package seteffects

import "go/ast"

// Syntax belongs to the parsed program; values and lexical bindings belong to
// each invocation. One VM retains at most this many immutable syntax plans.
const amountPlanLimit = 128

type amountPlan struct {
	storage    ast.Expr
	clearCount int
	valid      bool
}

func (v *ruleVM) amountPlan(body *ast.BlockStmt) amountPlan {
	if plan, ok := v.amountPlans[body]; ok {
		return plan
	}
	plan := buildAmountPlan(body)
	if v.amountPlans == nil {
		v.amountPlans = map[*ast.BlockStmt]amountPlan{}
	}
	if len(v.amountPlanOrder) >= amountPlanLimit {
		old := v.amountPlanOrder[0]
		v.amountPlanOrder = v.amountPlanOrder[1:]
		delete(v.amountPlans, old)
	}
	v.amountPlans[body] = plan
	v.amountPlanOrder = append(v.amountPlanOrder, body)
	return plan
}

func buildAmountPlan(body *ast.BlockStmt) amountPlan {
	plan := amountPlan{}
	if body == nil {
		return plan
	}
	name := ""
	var storage ast.Expr
	valid := true
	parents := map[ast.Node]ast.Node{}
	stack := []ast.Node{}
	ast.Inspect(body, func(n ast.Node) bool {
		if n == nil {
			stack = stack[:len(stack)-1]
			return false
		}
		if len(stack) > 0 {
			parents[n] = stack[len(stack)-1]
		}
		stack = append(stack, n)
		if _, ok := n.(*ast.FuncLit); ok {
			valid = false
		}
		if id, ok := n.(*ast.Ident); ok && id.Name == "clear" {
			if call, ok := parents[id].(*ast.CallExpr); !ok || call.Fun != id {
				valid = false
			}
		}
		if r, ok := n.(*ast.ReturnStmt); ok {
			if len(r.Results) != 1 {
				valid = false
				return true
			}
			path := ruleStoragePath(r.Results[0])
			if path == "" {
				valid = false
				return true
			}
			if path != "nil" {
				if name != "" && name != path {
					valid = false
				}
				name, storage = path, r.Results[0]
			}
		}
		return true
	})
	if !valid || name == "" {
		return plan
	}
	ast.Inspect(body, func(n ast.Node) bool {
		expr, ok := n.(ast.Expr)
		if !ok || ruleStoragePath(expr) != name {
			return true
		}
		switch p := parents[expr].(type) {
		case *ast.ReturnStmt:
			if len(p.Results) != 1 || p.Results[0] != expr {
				valid = false
			}
		case *ast.IndexExpr:
			if p.X != expr {
				valid = false
			}
		case *ast.CallExpr:
			id, ok := p.Fun.(*ast.Ident)
			if !ok || id.Name != "clear" || len(p.Args) != 1 || p.Args[0] != expr {
				valid = false
				break
			}
			plan.clearCount++
		default:
			valid = false
		}
		return true
	})
	if valid {
		plan.storage, plan.valid = storage, true
	}
	return plan
}

func (v *ruleVM) amountScratch(fn *ruleFunction) *ruleSlice {
	plan := v.amountPlan(fn.body)
	if !plan.valid {
		return v.inspectAmountScratch(fn)
	}
	// The returned object, observed flag and current clear binding can change
	// between calls even when the AST body pointer is identical.
	value, err := ruleTry(func() any { return v.eval(plan.storage, fn.env) })
	array, _ := value.(*ruleSlice)
	if err != nil || array == nil || array.observed {
		return nil
	}
	for i := 0; i < plan.clearCount; i++ {
		native, ok := v.lookup(fn.env, "clear").(ruleNative)
		if !ok || native.receiver != nil || native.name != "clear" {
			return nil
		}
	}
	return array
}
