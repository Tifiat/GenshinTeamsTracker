package seteffects

import (
	"fmt"
	"go/ast"
	"go/token"
	"math"
)

func (v *ruleVM) invoke(fn any, args []any) any {
	v.tick()
	v.depth++
	defer func() { v.depth-- }()
	if v.depth > 128 {
		ruleFail("source call depth exhausted")
	}
	switch f := fn.(type) {
	case *ruleFunction:
		e := childRuleEnv(f.env)
		if v.readOnly {
			if v.readLocals == nil {
				v.readLocals = map[*ruleEnv]bool{}
			}
			v.readLocals[e] = true
			defer delete(v.readLocals, e)
		}
		previousRoot := v.readRoot
		if v.readOnly && v.readRoot == nil {
			v.readRoot = e
		}
		defer func() { v.readRoot = previousRoot }()
		if f.receiver != "" {
			e.vars[f.receiver] = f.object
		}
		index := 0
		if f.typ.Params != nil {
			for _, p := range f.typ.Params.List {
				for _, id := range p.Names {
					if _, variadic := p.Type.(*ast.Ellipsis); variadic {
						e.vars[id.Name] = &ruleSlice{values: append([]any(nil), args[index:]...)}
						index = len(args)
					} else {
						if index >= len(args) {
							ruleFail("source call missing argument")
						}
						e.vars[id.Name] = copyRuleValue(args[index])
						index++
					}
				}
			}
		}
		if index != len(args) {
			ruleFail("source call extra argument")
		}
		if f.typ.Results != nil {
			for _, result := range f.typ.Results.List {
				if len(result.Names) != 0 {
					ruleFail("named rule results are not supported")
				}
			}
		}
		c := v.block(f.body, e)
		if c.kind != token.ILLEGAL && c.kind != token.RETURN {
			ruleFail("unhandled source loop control")
		}
		if len(c.values) == 1 {
			return c.values[0]
		}
		return ruleTuple(c.values)
	case ruleType:
		if len(args) != 1 {
			ruleFail("source conversion arity")
		}
		switch f.name {
		case "int", "int32", "int64", "uint32", "uint64":
			return float64(ruleInteger(math.Trunc(ruleNumber(args[0]))))
		case "float64":
			if _, ok := args[0].(*RuleScalar); ok {
				return args[0]
			}
			return ruleNumber(args[0])
		case "bool":
			return ruleBoolean(args[0])
		case "string":
			return ruleString(args[0])
		}
		// Numeric enum conversions preserve their source value. Conversion to a
		// struct/string-backed custom type is not guessed from the operand.
		if m, member := v.typeModule(f.name); m != nil {
			if t, ok := m.types[member].(*ast.Ident); ok && t.Name == "int" {
				return ruleTypedNumber{float64(ruleInteger(args[0])), f.name}
			}
		}
		ruleFail("unsupported source conversion: " + f.name)
	case ruleNative:
		if pkg, ok := f.receiver.(rulePackage); ok && pkg == "math" && f.name == "Abs" {
			if len(args) != 1 {
				ruleFail("math.Abs arity")
			}
			if x, symbolic := args[0].(*RuleScalar); symbolic {
				// Preserve the input in the reduced program; no point-value branch.
				return scalarOp("max", x, scalarOp("multiply", float64(-1), x))
			}
			return math.Abs(ruleNumber(args[0]))
		}
		if f.receiver == nil {
			switch f.name {
			case "clear":
				if len(args) != 1 {
					ruleFail("clear arity")
				}
				a, ok := args[0].(*ruleSlice)
				if !ok || a.observed || (v.readOnly && !v.scratch[a]) {
					ruleFail("clear of unowned source storage")
				}
				for i, item := range a.values {
					if _, symbolic := item.(*RuleScalar); !symbolic {
						ruleNumber(item)
					}
					a.values[i] = float64(0)
					if written, ok := v.scratchWritten[a]; ok {
						written[i] = true
					}
				}
				return nil
			case "len":
				if len(args) != 1 {
					ruleFail("len arity")
				}
				if m, ok := args[0].(*ruleMap); ok {
					return float64(len(m.values))
				}
				if s, ok := args[0].(string); ok {
					return float64(len(s))
				}
				return float64(len(ruleArray(args[0])))
			case "append":
				if len(args) < 1 {
					ruleFail("append arity")
				}
				items := append([]any(nil), ruleArray(args[0])...)
				if len(items)+len(args)-1 > 4096 {
					ruleFail("source append size")
				}
				return &ruleSlice{values: append(items, args[1:]...)}
			case "min", "max":
				if len(args) == 0 {
					ruleFail("min/max arity")
				}
				var result any = args[0]
				for _, a := range args[1:] {
					_, x := result.(*RuleScalar)
					_, y := a.(*RuleScalar)
					if x || y {
						result = scalarOp(f.name, result, a)
						continue
					}
					if f.name == "min" {
						result = math.Min(ruleNumber(result), ruleNumber(a))
					} else {
						result = math.Max(ruleNumber(result), ruleNumber(a))
					}
				}
				return result
			}
		}
		if v.host != nil {
			if out, ok := v.host.call(f.receiver, f.name, args); ok {
				return out
			}
		}
		ruleFail(fmt.Sprintf("unsupported source API: %v.%s", f.receiver, f.name))
	}
	ruleFail("source value is not callable")
	return nil
}

func (v *ruleVM) block(block *ast.BlockStmt, e *ruleEnv) ruleControl {
	if block == nil {
		ruleFail("source function has no body")
	}
	for _, s := range block.List {
		if c := v.stmt(s, e); c.kind != token.ILLEGAL {
			return c
		}
	}
	return ruleControl{}
}
func (v *ruleVM) stmt(stmt ast.Stmt, e *ruleEnv) ruleControl {
	v.tick()
	switch s := stmt.(type) {
	case *ast.EmptyStmt:
	case *ast.BlockStmt:
		return v.block(s, childRuleEnv(e))
	case *ast.ExprStmt:
		v.eval(s.X, e)
	case *ast.ReturnStmt:
		values := []any{}
		for _, x := range s.Results {
			value := v.eval(x, e)
			if tuple, ok := value.(ruleTuple); ok {
				values = append(values, tuple...)
			} else {
				values = append(values, copyRuleValue(value))
			}
		}
		return ruleControl{token.RETURN, values}
	case *ast.AssignStmt:
		values := []any{}
		for _, x := range s.Rhs {
			if t, ok := x.(*ast.TypeAssertExpr); ok && len(s.Lhs) == 2 && len(s.Rhs) == 1 {
				value := v.eval(t.X, e)
				matched := v.matches(value, ruleTypeName(t.Type, e))
				if !matched {
					value = nil
				}
				values = append(values, value, matched)
			} else if index, ok := x.(*ast.IndexExpr); ok && len(s.Lhs) == 2 && len(s.Rhs) == 1 {
				m, ok := v.eval(index.X, e).(*ruleMap)
				if !ok {
					ruleFail("comma-ok source index is not a map")
				}
				value, found := m.values[ruleMapKey(v.eval(index.Index, e))]
				if !found {
					value = v.zero(m.valueType, m.env)
				}
				values = append(values, value, found)
			} else {
				value := v.eval(x, e)
				if tuple, ok := value.(ruleTuple); ok {
					values = append(values, tuple...)
				} else {
					values = append(values, value)
				}
			}
		}
		if len(values) != len(s.Lhs) {
			ruleFail("source assignment arity")
		}
		for i, lhs := range s.Lhs {
			value := values[i]
			if s.Tok != token.ASSIGN && s.Tok != token.DEFINE {
				op := map[token.Token]token.Token{token.ADD_ASSIGN: token.ADD, token.SUB_ASSIGN: token.SUB, token.MUL_ASSIGN: token.MUL, token.QUO_ASSIGN: token.QUO, token.REM_ASSIGN: token.REM}[s.Tok]
				if op == token.ILLEGAL {
					ruleFail("unsupported compound source assignment")
				}
				value = ruleBinary(op, v.eval(lhs, e), value)
			}
			oldFlatAdd := v.flatAdd
			v.flatAdd = s.Tok == token.ADD_ASSIGN
			v.assign(lhs, value, e, s.Tok == token.DEFINE)
			v.flatAdd = oldFlatAdd
		}
	case *ast.IncDecStmt:
		x := ruleNumber(v.eval(s.X, e))
		if s.Tok == token.INC {
			x++
		} else {
			x--
		}
		v.assign(s.X, x, e, false)
	case *ast.DeclStmt:
		g, ok := s.Decl.(*ast.GenDecl)
		if !ok {
			ruleFail("unsupported local declaration")
		}
		var previous []ast.Expr
		for ordinal, spec := range g.Specs {
			s, ok := spec.(*ast.ValueSpec)
			if !ok {
				ruleFail("unsupported local type declaration")
			}
			values := s.Values
			if g.Tok == token.CONST && len(values) == 0 {
				values = previous
			}
			if len(values) != 0 && len(values) != len(s.Names) {
				ruleFail("unsupported local tuple declaration")
			}
			for i, name := range s.Names {
				value := v.zero(s.Type, e)
				if len(values) != 0 {
					ce := childRuleEnv(e)
					ce.vars["iota"] = float64(ordinal)
					value = v.eval(values[i], ce)
				}
				e.vars[name.Name] = copyRuleValue(value)
			}
			previous = values
		}
	case *ast.IfStmt:
		scope := childRuleEnv(e)
		if s.Init != nil {
			if c := v.stmt(s.Init, scope); c.kind != token.ILLEGAL {
				ruleFail("control in if initialization")
			}
		}
		condition := v.eval(s.Cond, scope)
		if predicate, ok := condition.(rulePredicate); ok {
			return v.symbolicBranch(s, scope, predicate)
		}
		if ruleBoolean(condition) {
			return v.block(s.Body, childRuleEnv(scope))
		}
		if s.Else != nil {
			return v.stmt(s.Else, scope)
		}
	case *ast.SwitchStmt:
		scope := childRuleEnv(e)
		if s.Init != nil {
			v.stmt(s.Init, scope)
		}
		var value any = true
		if s.Tag != nil {
			value = v.eval(s.Tag, scope)
		}
		var selected, fallback *ast.CaseClause
		for _, raw := range s.Body.List {
			c, ok := raw.(*ast.CaseClause)
			if !ok {
				ruleFail("invalid source switch")
			}
			if c.List == nil {
				fallback = c
				continue
			}
			for _, expr := range c.List {
				if ruleBoolean(ruleBinary(token.EQL, value, v.eval(expr, scope))) {
					selected = c
					break
				}
			}
			if selected != nil {
				break
			}
		}
		if selected == nil {
			selected = fallback
		}
		if selected != nil {
			for _, body := range selected.Body {
				c := v.stmt(body, scope)
				if c.kind == token.BREAK {
					break
				}
				if c.kind != token.ILLEGAL {
					return c
				}
			}
		}
	case *ast.RangeStmt:
		value := v.eval(s.X, e)
		if m, ok := value.(*ruleMap); ok {
			return v.registrationMapRange(s, m, e)
		}
		items := append([]any(nil), ruleArray(value)...)
		for i, item := range items {
			scope := childRuleEnv(e)
			if s.Key != nil {
				v.assign(s.Key, float64(i), scope, s.Tok == token.DEFINE)
			}
			if s.Value != nil {
				v.assign(s.Value, item, scope, s.Tok == token.DEFINE)
			}
			c := v.block(s.Body, scope)
			if c.kind == token.BREAK {
				break
			}
			if c.kind != token.ILLEGAL && c.kind != token.CONTINUE {
				return c
			}
		}
	case *ast.ForStmt:
		scope := childRuleEnv(e)
		if s.Init != nil {
			v.stmt(s.Init, scope)
		}
		for s.Cond == nil || ruleBoolean(v.eval(s.Cond, scope)) {
			v.tick()
			c := v.block(s.Body, childRuleEnv(scope))
			if c.kind == token.BREAK {
				break
			}
			if c.kind != token.ILLEGAL && c.kind != token.CONTINUE {
				return c
			}
			if s.Post != nil {
				v.stmt(s.Post, scope)
			}
		}
	case *ast.BranchStmt:
		if s.Label != nil || (s.Tok != token.BREAK && s.Tok != token.CONTINUE) {
			ruleFail("unsupported labeled/fallthrough source control")
		}
		return ruleControl{kind: s.Tok}
	default:
		ruleFail(fmt.Sprintf("unsupported source statement %T", stmt))
	}
	return ruleControl{}
}

func (v *ruleVM) assign(lhs ast.Expr, value any, e *ruleEnv, declare bool) {
	value = copyRuleValue(value)
	switch x := lhs.(type) {
	case *ast.Ident:
		if x.Name == "_" {
			return
		}
		if declare {
			v.writeLocal(e, x.Name, value)
			return
		}
		for s := e; s != nil; s = s.parent {
			if _, ok := s.vars[x.Name]; ok {
				v.writeLocal(s, x.Name, value)
				return
			}
		}
		// Set packages are instantiated independently. Mutable package globals
		// could share state across wearers and are outside this isolated subset.
		ruleFail("assignment to nonlocal source binding: " + x.Name)
	case *ast.StarExpr:
		cell, ok := v.eval(x.X, e).(*ruleCell)
		if !ok {
			ruleFail("mutation of external or unsupported source pointer")
		}
		if !v.mayWriteLocal(cell.scope) {
			ruleFail("modifier amount writes captured source pointer")
		}
		cell.value = value
	case *ast.SelectorExpr:
		if v.readOnly {
			ruleFail("modifier amount writes source object")
		}
		target := v.eval(x.X, e)
		if p, ok := target.(rulePointer); ok {
			target = p.object
		}
		if o, ok := target.(*ruleObject); ok {
			if o.observed {
				if o.flatWrite != nil && x.Sel.Name == "FlatDmg" && v.flatAdd {
					o.flatWrite(o.fields[x.Sel.Name], value)
					o.fields[x.Sel.Name] = value
					return
				}
				ruleFail("event payload mutation needs a bound output expression")
			}
			if _, exists := o.fields[x.Sel.Name]; !exists {
				ruleFail("assignment to missing source field")
			}
			o.fields[x.Sel.Name] = value
			return
		}
		ruleFail("mutation of external source object: " + x.Sel.Name)
	case *ast.IndexExpr:
		a, i := v.eval(x.X, e), v.eval(x.Index, e)
		if v.readOnly {
			if array, ok := a.(*ruleSlice); !ok || !v.scratch[array] {
				ruleFail("modifier amount writes cached array or map")
			}
		}
		if s, ok := a.(*ruleSlice); ok && s.observed {
			ruleFail("event stat mutation needs a bound output expression")
		}
		if m, ok := a.(*ruleMap); ok {
			m.values[ruleMapKey(i)] = value
			return
		}
		items := ruleArray(a)
		idx := ruleInteger(i)
		if idx < 0 || idx >= len(items) {
			ruleFail("source index assignment outside array")
		}
		items[idx] = value
		if array, ok := a.(*ruleSlice); ok && v.readOnly {
			if written, guarded := v.scratchWritten[array]; guarded {
				written[idx] = true
			}
		}
	default:
		ruleFail("unsupported source assignment target")
	}
}

// Go struct assignment copies fields; pointers and slice backing stores remain
// shared. Collapsing both to one object aliases independent closure state.
func copyRuleValue(value any) any {
	if o, ok := value.(*ruleObject); ok {
		result := &ruleObject{typ: o.typ, fields: map[string]any{}, observed: o.observed, flatWrite: o.flatWrite}
		for k, v := range o.fields {
			result.fields[k] = copyRuleValue(v)
		}
		return result
	}
	return value
}

func ruleScopeInside(scope, root *ruleEnv) bool {
	for s := scope; s != nil; s = s.parent {
		if s == root {
			return true
		}
	}
	return false
}
