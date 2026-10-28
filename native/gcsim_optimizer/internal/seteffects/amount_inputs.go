package seteffects

import "go/ast"

// Bind the value parameter of an actual modifier Amount callback, not arbitrary
// locals named ai/atk or event arguments belonging to a different hit. This is
// only filter discovery; mutable arguments remain unknown.
func (d *discovery) bindAmountInputs(counts map[*ast.Object]int) {
	for _, node := range d.functions {
		ast.Inspect(node, func(n ast.Node) bool {
			call, ok := n.(*ast.CallExpr)
			if !ok {
				return true
			}
			method, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || len(call.Args) == 0 {
				return true
			}
			if method.Sel.Name != "AddAttackMod" && method.Sel.Name != "AddReactBonusMod" {
				return true
			}
			payload := d.composite(call.Args[0])
			if payload == nil {
				return true
			}
			for _, item := range payload.Elts {
				kv, ok := item.(*ast.KeyValueExpr)
				if !ok {
					continue
				}
				key, ok := kv.Key.(*ast.Ident)
				if !ok || key.Name != "Amount" {
					continue
				}
				fn := d.function(kv.Value)
				for _, candidate := range d.functions {
					if d.functionIDs[candidate] != fn {
						continue
					}
					var params *ast.FieldList
					switch f := candidate.(type) {
					case *ast.FuncDecl:
						params = f.Type.Params
					case *ast.FuncLit:
						params = f.Type.Params
					}
					if params == nil || len(params.List) != 1 {
						continue
					}
					field := params.List[0]
					selector, ok := field.Type.(*ast.SelectorExpr)
					if !ok || selector.Sel.Name != "AttackInfo" {
						continue
					}
					alias, ok := selector.X.(*ast.Ident)
					if !ok || d.imports[d.at(candidate).File][alias.Name] != "github.com/genshinsim/gcsim/pkg/core/info" {
						continue
					}
					for _, name := range field.Names {
						if name.Obj != nil && counts[name.Obj] == 0 && !writtenInputField(candidate, name.Obj) {
							d.objects[name.Obj] = "amount_attack_info:" + fn
						}
					}
				}
			}
			return true
		})
	}
}

func writtenInputField(node ast.Node, object *ast.Object) bool {
	root := func(x ast.Expr) bool {
		for {
			s, ok := x.(*ast.SelectorExpr)
			if !ok {
				break
			}
			x = s.X
		}
		id, ok := x.(*ast.Ident)
		return ok && id.Obj == object
	}
	unsafe := false
	ast.Inspect(node, func(n ast.Node) bool {
		switch x := n.(type) {
		case *ast.AssignStmt:
			for _, lhs := range x.Lhs {
				unsafe = unsafe || root(lhs)
			}
		case *ast.IncDecStmt:
			unsafe = unsafe || root(x.X)
		case *ast.UnaryExpr:
			if x.Op.String() == "&" {
				unsafe = unsafe || root(x.X)
			}
		}
		return true
	})
	return unsafe
}
