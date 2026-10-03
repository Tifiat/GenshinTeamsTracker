package seteffects

// A source Amount often rewrites a cached return vector as scratch storage.
// Admit only direct, stateless cell assignments in that exact returned vector;
// restore the storage after observing the value. Counters, aliases, old-cell
// reads and other captured mutations remain explicit lifecycle boundaries.
import "go/ast"

func ruleStoragePath(expr ast.Expr) string {
	switch x := expr.(type) {
	case *ast.Ident:
		return x.Name
	case *ast.SelectorExpr:
		if prefix := ruleStoragePath(x.X); prefix != "" {
			return prefix + "." + x.Sel.Name
		}
	}
	return ""
}

func (v *ruleVM) inspectAmountScratch(fn *ruleFunction) *ruleSlice {
	name := ""
	var storage ast.Expr
	valid := true
	parents := map[ast.Node]ast.Node{}
	stack := []ast.Node{}
	ast.Inspect(fn.body, func(n ast.Node) bool {
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
			// A local shadow must not turn the special scratch operation into an
			// arbitrary function that receives an alias to the captured storage.
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
		return nil
	}
	value, err := ruleTry(func() any { return v.eval(storage, fn.env) })
	array, _ := value.(*ruleSlice)
	if err != nil || array == nil || array.observed {
		return nil
	}
	ast.Inspect(fn.body, func(n ast.Node) bool {
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
			// A cell read is checked dynamically: it must have been assigned
			// on this invocation's actual path. This admits m[i]=x; m[i]+=y,
			// but not a retained counter, old-cell dependency or an alias.
			if p.X != expr {
				valid = false
			}
		case *ast.CallExpr:
			id, ok := p.Fun.(*ast.Ident)
			if !ok || id.Name != "clear" || len(p.Args) != 1 || p.Args[0] != expr {
				valid = false
				break
			}
			native, ok := v.lookup(fn.env, "clear").(ruleNative)
			if !ok || native.receiver != nil || native.name != "clear" {
				valid = false
			}
		default:
			valid = false
		}
		return true
	})
	if !valid {
		return nil
	}
	return array
}

func (v *ruleVM) invokeAmount(fn *ruleFunction, args []any) any {
	oldReadOnly, oldScratch, oldWritten := v.readOnly, v.scratch, v.scratchWritten
	v.readOnly = true
	v.scratch = map[*ruleSlice]bool{}
	v.scratchWritten = map[*ruleSlice]map[int]bool{}
	array := v.amountScratch(fn)
	var saved []any
	if array != nil {
		saved = append([]any(nil), array.values...)
		v.scratch[array] = true
		v.scratchWritten[array] = map[int]bool{}
	}
	defer func() {
		if array != nil {
			copy(array.values, saved)
		}
		v.readOnly, v.scratch, v.scratchWritten = oldReadOnly, oldScratch, oldWritten
	}()
	value := v.invoke(fn, args)
	if vector, ok := value.(*ruleSlice); ok {
		return &ruleSlice{values: append([]any(nil), vector.values...)}
	}
	return value
}
