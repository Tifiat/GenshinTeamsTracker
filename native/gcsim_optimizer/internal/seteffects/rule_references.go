package seteffects

// Local scalar addresses keep identity across queued source callbacks. External
// live references are read-only and require an explicit host capability; taking
// an address must never freeze the engine frame at constructor time. This is a
// bounded language adapter, not a second implementation of stack mechanics.
import (
	"go/ast"
)

type ruleCell struct {
	value any
	scope *ruleEnv
}
type ruleAddressBinding struct{ cell *ruleCell }
type ruleLiveField struct {
	receiver any
	name     string
}

func (v *ruleVM) address(expr ast.Expr, env *ruleEnv) any {
	if p, ok := expr.(*ast.ParenExpr); ok {
		return v.address(p.X, env)
	}
	if id, ok := expr.(*ast.Ident); ok {
		for scope := env; scope != nil; scope = scope.parent {
			value, found := scope.vars[id.Name]
			if !found {
				continue
			}
			if binding, ok := value.(ruleAddressBinding); ok {
				return binding.cell
			}
			if object, ok := value.(*ruleObject); ok {
				return rulePointer{object}
			}
			switch value.(type) {
			case float64, bool, string, ruleTypedNumber:
				cell := &ruleCell{value: value, scope: scope}
				scope.vars[id.Name] = ruleAddressBinding{cell}
				return cell
			}
			ruleFail("unsupported addressed source local")
		}
	}
	if field, ok := expr.(*ast.SelectorExpr); ok && v.host != nil {
		receiver := v.eval(field.X, env)
		if allowed, known := v.host.field(receiver, "$address:"+field.Sel.Name); known && ruleBoolean(allowed) {
			return ruleLiveField{receiver, field.Sel.Name}
		}
		ruleFail("unbound external source address: " + field.Sel.Name)
	}
	if literal, ok := expr.(*ast.CompositeLit); ok {
		if object, ok := v.eval(literal, env).(*ruleObject); ok {
			return rulePointer{object}
		}
	}
	ruleFail("unsupported source address target")
	return nil
}

func (v *ruleVM) dereference(value any) any {
	switch p := value.(type) {
	case rulePointer:
		return p.object
	case *ruleCell:
		return p.value
	case ruleLiveField:
		if v.host != nil {
			if value, ok := v.host.field(p.receiver, p.name); ok {
				return value
			}
		}
	}
	ruleFail("unsupported source dereference")
	return nil
}

func (v *ruleVM) mayWriteLocal(scope *ruleEnv) bool {
	if !v.readOnly || ruleScopeInside(scope, v.readRoot) {
		return true
	}
	for root := range v.readLocals {
		if ruleScopeInside(scope, root) {
			return true
		}
	}
	return false
}

func (v *ruleVM) writeLocal(scope *ruleEnv, name string, value any) {
	if !v.mayWriteLocal(scope) {
		ruleFail("modifier amount writes captured source state")
	}
	if binding, ok := scope.vars[name].(ruleAddressBinding); ok {
		binding.cell.value = value
		return
	}
	scope.vars[name] = value
}
