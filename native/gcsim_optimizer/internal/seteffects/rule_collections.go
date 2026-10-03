package seteffects

// Narrow source-language adapters, not set mechanics. Unordered maps may only
// register independent event kinds without mutating shared state or exiting
// early. Their iteration order is then irrelevant; other map loops fail closed.
import (
	"fmt"
	"go/ast"
	"go/token"
	"sort"
	"strings"
)

func (v *ruleVM) evalTypedLiteral(expr, typ ast.Expr, env *ruleEnv) any {
	if literal, ok := expr.(*ast.CompositeLit); ok && literal.Type == nil {
		copy := *literal
		copy.Type = typ
		return v.eval(&copy, env)
	}
	return v.eval(expr, env)
}

func (v *ruleVM) registrationMapRange(stmt *ast.RangeStmt, m *ruleMap, env *ruleEnv) ruleControl {
	if v.readOnly || v.registrationEvents != nil || len(m.values) > 4096 {
		ruleFail("source map iteration lacks independent registration proof")
	}
	oldReadOnly, oldRoot := v.readOnly, v.readRoot
	v.readOnly, v.registrationEvents = true, map[int]bool{}
	defer func() { v.readOnly, v.readRoot, v.registrationEvents = oldReadOnly, oldRoot, nil }()
	keys := []any{}
	for key := range m.values {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool { return fmt.Sprint(keys[i]) < fmt.Sprint(keys[j]) })
	for _, key := range keys {
		scope := childRuleEnv(env)
		v.readRoot = scope
		if stmt.Key != nil {
			v.assign(stmt.Key, key, scope, stmt.Tok == token.DEFINE)
		}
		if stmt.Value != nil {
			v.assign(stmt.Value, m.values[key], scope, stmt.Tok == token.DEFINE)
		}
		control := v.block(stmt.Body, scope)
		if control.kind != token.ILLEGAL && control.kind != token.CONTINUE {
			ruleFail("source map iteration has order-dependent exit")
		}
	}
	return ruleControl{}
}

// All admitted key-formatting sites currently use %v. Interpret enum String
// methods from the bound source, not a numeric guess that changes modifier keys.
// An unsupported format is a boundary, never a malformed successful key.
func (v *ruleVM) formatRule(format string, args []any) string {
	var out strings.Builder
	index := 0
	for i := 0; i < len(format); i++ {
		if format[i] != '%' {
			out.WriteByte(format[i])
			continue
		}
		i++
		if i == len(format) {
			ruleFail("incomplete source format")
		}
		if format[i] == '%' {
			out.WriteByte('%')
			continue
		}
		if format[i] != 'v' || index >= len(args) {
			ruleFail("unsupported source key format")
		}
		value := args[index]
		index++
		if number, ok := value.(ruleTypedNumber); ok {
			if fn, ok := v.selectValue(number, "String").(*ruleFunction); ok {
				value = ruleString(v.invoke(fn, nil))
			} else {
				value = number.value
			}
		}
		switch value.(type) {
		case string, float64, bool:
			out.WriteString(fmt.Sprint(value))
		default:
			ruleFail("source format operand is not known")
		}
	}
	if index != len(args) {
		ruleFail("extra source format operands")
	}
	return out.String()
}
