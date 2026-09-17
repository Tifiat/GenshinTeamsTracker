package seteffects

import (
	"go/ast"
	"go/token"
)

func boolNot(x Expression) Expression {
	return Expression{Kind: "unary:!", Inputs: []Expression{x}}
}
func boolJoin(op string, xs []Expression) Expression {
	if len(xs) == 0 {
		v := "false"
		if op == "&&" {
			v = "true"
		}
		return Expression{Kind: "boolean", Text: v}
	}
	out := xs[0]
	for _, x := range xs[1:] {
		out = Expression{Kind: "binary:" + op, Inputs: []Expression{out, x}}
	}
	return out
}

// Keep case guards and the complement of definitely returning cases. Empty Go
// cases reach the post-switch code; they do NOT fall through into the next case.
// Nonlocal flow/mutable joins are deliberately not specialized.
func (d *discovery) switchBlock(s *ast.SwitchStmt, g []string) []string {
	if s.Init != nil {
		d.block([]ast.Stmt{s.Init}, g)
	}
	d.calls(s.Tag, g)
	conditions := map[*ast.CaseClause]Expression{}
	all := []Expression{}
	unsafe := false
	for _, item := range s.Body.List {
		c := item.(*ast.CaseClause)
		cases := []Expression{}
		for _, v := range c.List {
			e := d.expr(v, 0)
			if s.Tag != nil {
				e = Expression{Kind: "binary:==", Inputs: []Expression{d.expr(s.Tag, 0), e}}
			}
			cases = append(cases, e)
		}
		if len(cases) > 0 {
			conditions[c] = boolJoin("||", cases)
			all = append(all, conditions[c])
		}
		ast.Inspect(c, func(n ast.Node) bool {
			if _, ok := n.(*ast.FuncLit); ok {
				return false
			}
			if b, ok := n.(*ast.BranchStmt); ok && (b.Tok == token.FALLTHROUGH || b.Tok == token.GOTO) {
				unsafe = true
			}
			return true
		})
	}
	returned := []Expression{}
	for _, item := range s.Body.List {
		c := item.(*ast.CaseClause)
		e, ok := conditions[c]
		if !ok {
			e = boolNot(boolJoin("||", all))
		}
		if unsafe {
			e = Expression{Kind: "unknown_switch_flow"}
		}
		key := "case@" + d.id(c)
		d.condition(key, e)
		d.block(c.Body, guardsWith(g, key))
		if len(c.Body) > 0 {
			if _, ok := c.Body[len(c.Body)-1].(*ast.ReturnStmt); ok {
				returned = append(returned, e)
			}
		}
	}
	if len(returned) > 0 && !unsafe {
		key := "after-switch@" + d.id(s)
		d.condition(key, boolNot(boolJoin("||", returned)))
		g = guardsWith(g, key)
	}
	d.boundary("switch_join_requires_context", s)
	return g
}
