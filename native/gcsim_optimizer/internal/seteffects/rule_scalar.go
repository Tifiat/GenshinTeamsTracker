package seteffects

// Source arithmetic retained after event replay. These expressions are NOT
// point estimates: every non-set stat read must later bind to an observed,
// owner/filter/time-correct neutral expression. Unbound reads cannot be scored.
// This source-only stage is pinned by rule_scalar_test and the active Emblem
// source control; neutral read-root export/integration is the next producer seam.
import (
	"fmt"
	"go/ast"
	"go/token"
	"math"
	"reflect"
)

type RuleStatRead struct {
	Owner      int
	Stat, Mode string
	Frame      int
	Order      uint64
}

type RuleScalar struct {
	Operation string
	Value     float64
	Read      *RuleStatRead
	Inputs    []*RuleScalar
}

func scalarOf(value any) *RuleScalar {
	if s, ok := value.(*RuleScalar); ok {
		return s
	}
	return &RuleScalar{Operation: "constant", Value: ruleNumber(value)}
}

func scalarOp(op string, values ...any) *RuleScalar {
	s := &RuleScalar{Operation: op, Inputs: make([]*RuleScalar, len(values))}
	for i, value := range values {
		s.Inputs[i] = scalarOf(value)
	}
	return s
}

type rulePredicate struct {
	left, right any
	invert      bool
}

func scalarBinary(op token.Token, a, b any) any {
	switch op {
	case token.ADD:
		return scalarOp("add", a, b)
	case token.SUB:
		return scalarOp("subtract", a, b)
	case token.MUL:
		return scalarOp("multiply", a, b)
	case token.QUO:
		return scalarOp("divide", a, b) // Stat-derived expressions are float64.
	case token.LSS:
		return rulePredicate{a, b, false}
	case token.GTR:
		return rulePredicate{b, a, false}
	case token.LEQ:
		return rulePredicate{b, a, true}
	case token.GEQ:
		return rulePredicate{a, b, true}
	default:
		ruleFail("stat-dependent source operation is not modeled")
	}
	return nil
}

// Evaluate is a control/debug interpreter. Production preparation binds these
// nodes into the reduced arithmetic program; it must not replay AST per item.
func (s *RuleScalar) Evaluate(read func(RuleStatRead) (float64, error)) (float64, error) {
	visits := 0
	var visit func(*RuleScalar, int) (float64, error)
	visit = func(s *RuleScalar, depth int) (float64, error) {
		visits++
		if s == nil || depth > 128 || visits > 16384 {
			return 0, fmt.Errorf("rule scalar budget")
		}
		if s.Operation == "constant" {
			if !isRuleFinite(s.Value) {
				return 0, fmt.Errorf("nonfinite constant")
			}
			return s.Value, nil
		}
		if s.Operation == "neutral_stat" {
			if s.Read == nil || read == nil {
				return 0, fmt.Errorf("unbound neutral stat read")
			}
			x, err := read(*s.Read)
			if err == nil && !isRuleFinite(x) {
				err = fmt.Errorf("nonfinite stat input")
			}
			return x, err
		}
		arity := 2
		if s.Operation == "select_lt" {
			arity = 4
		}
		if len(s.Inputs) != arity {
			return 0, fmt.Errorf("rule scalar arity")
		}
		a, err := visit(s.Inputs[0], depth+1)
		if err != nil {
			return 0, err
		}
		b, err := visit(s.Inputs[1], depth+1)
		if err != nil {
			return 0, err
		}
		if s.Operation == "select_lt" {
			if a < b {
				return visit(s.Inputs[2], depth+1)
			}
			return visit(s.Inputs[3], depth+1)
		}
		var x float64
		switch s.Operation {
		case "add":
			x = a + b
		case "subtract":
			x = a - b
		case "multiply":
			x = a * b
		case "divide":
			x = a / b
		case "min":
			x = math.Min(a, b)
		case "max":
			x = math.Max(a, b)
		default:
			return 0, fmt.Errorf("unknown scalar operation")
		}
		if !isRuleFinite(x) {
			return 0, fmt.Errorf("nonfinite scalar result")
		}
		return x, nil
	}
	return visit(s, 0)
}

// Only pure local numeric assignments can be merged across a symbolic branch.
// A condition which changes callbacks, output, lifetime, recipients or loops is
// a schedule/activation boundary, not permission to pick its observed branch.
func pureRuleBranch(stmt ast.Stmt) bool {
	if stmt == nil {
		return true
	}
	switch s := stmt.(type) {
	case *ast.BlockStmt:
		for _, child := range s.List {
			if !pureRuleBranch(child) {
				return false
			}
		}
		return true
	case *ast.AssignStmt:
		if len(s.Lhs) != 1 || len(s.Rhs) != 1 {
			return false
		}
		if _, ok := s.Lhs[0].(*ast.Ident); !ok {
			return false
		}
		return pureRuleExpression(s.Rhs[0])
	case *ast.IfStmt:
		return s.Init == nil && pureRuleExpression(s.Cond) && pureRuleBranch(s.Body) && pureRuleBranch(s.Else)
	}
	return false
}
func pureRuleExpression(expr ast.Expr) bool {
	switch e := expr.(type) {
	case *ast.Ident, *ast.BasicLit:
		return true
	case *ast.ParenExpr:
		return pureRuleExpression(e.X)
	case *ast.UnaryExpr:
		return (e.Op == token.SUB || e.Op == token.ADD) && pureRuleExpression(e.X)
	case *ast.BinaryExpr:
		return pureRuleExpression(e.X) && pureRuleExpression(e.Y)
	case *ast.CallExpr:
		id, ok := e.Fun.(*ast.Ident)
		if !ok || (id.Name != "min" && id.Name != "max" && id.Name != "float64") {
			return false
		}
		for _, a := range e.Args {
			if !pureRuleExpression(a) {
				return false
			}
		}
		return true
	}
	return false
}
func (v *ruleVM) symbolicBranch(s *ast.IfStmt, scope *ruleEnv, condition rulePredicate) ruleControl {
	if !pureRuleBranch(s.Body) || !pureRuleBranch(s.Else) {
		ruleFail("stat-dependent branch changes nonnumeric source behavior")
	}
	// A local function may shadow min/max/float64. Syntax alone does not make
	// that call pure, and branch-local shadow declarations must not be used.
	for _, branch := range []ast.Node{s.Body, s.Else} {
		if branch == nil {
			continue
		}
		ast.Inspect(branch, func(n ast.Node) bool {
			if assignment, ok := n.(*ast.AssignStmt); ok && assignment.Tok == token.DEFINE {
				if id, ok := assignment.Lhs[0].(*ast.Ident); ok && (id.Name == "min" || id.Name == "max" || id.Name == "float64") {
					ruleFail("symbolic branch shadows numeric builtin")
				}
			}
			if call, ok := n.(*ast.CallExpr); ok {
				name := call.Fun.(*ast.Ident).Name
				bound := v.lookup(scope, name)
				switch b := bound.(type) {
				case ruleNative:
					if b.receiver != nil || (b.name != "min" && b.name != "max") {
						ruleFail("symbolic branch calls shadowed builtin")
					}
				case ruleType:
					if b.name != "float64" {
						ruleFail("symbolic branch calls shadowed conversion")
					}
				default:
					ruleFail("symbolic branch calls shadowed builtin")
				}
			}
			return true
		})
	}
	clone := func() (*ruleEnv, map[*ruleEnv]*ruleEnv) {
		mapped := map[*ruleEnv]*ruleEnv{}
		var copyEnv func(*ruleEnv) *ruleEnv
		copyEnv = func(e *ruleEnv) *ruleEnv {
			if e == nil {
				return nil
			}
			x := &ruleEnv{parent: copyEnv(e.parent), module: e.module, imports: e.imports, vars: map[string]any{}}
			for k, value := range e.vars {
				if _, addressed := value.(ruleAddressBinding); addressed {
					ruleFail("symbolic branch crosses addressed source binding")
				}
				x.vars[k] = value
			}
			mapped[e] = x
			return x
		}
		return copyEnv(scope), mapped
	}
	left, lm := clone()
	right, rm := clone()
	previous := v.readRoot
	previousLocals := v.readLocals
	mapLocals := func(mapping map[*ruleEnv]*ruleEnv) map[*ruleEnv]bool {
		out := map[*ruleEnv]bool{}
		for root := range previousLocals {
			if mapped := mapping[root]; mapped != nil {
				out[mapped] = true
			}
		}
		return out
	}
	defer func() { v.readRoot, v.readLocals = previous, previousLocals }()
	if previous != nil {
		v.readRoot = lm[previous]
	}
	v.readLocals = mapLocals(lm)
	a := v.block(s.Body, childRuleEnv(left))
	if previous != nil {
		v.readRoot = rm[previous]
	}
	v.readLocals = mapLocals(rm)
	b := ruleControl{}
	if s.Else != nil {
		b = v.stmt(s.Else, right)
	}
	v.readRoot, v.readLocals = previous, previousLocals
	if a.kind != token.ILLEGAL || b.kind != token.ILLEGAL {
		ruleFail("symbolic source control cannot be merged")
	}
	for original, l := range lm {
		r := rm[original]
		for name, old := range original.vars {
			lv, rv := l.vars[name], r.vars[name]
			// Numeric identities are comparable; containers are not assigned in
			// admitted branches and need not be examined recursively.
			if sameRuleScalarValue(old, lv) && sameRuleScalarValue(old, rv) {
				continue
			}
			if condition.invert {
				lv, rv = rv, lv
			}
			original.vars[name] = scalarOp("select_lt", condition.left, condition.right, lv, rv)
		}
	}
	return ruleControl{}
}
func sameRuleScalarValue(a, b any) bool {
	switch x := a.(type) {
	case nil:
		return b == nil
	case float64:
		y, ok := b.(float64)
		return ok && x == y
	case *RuleScalar:
		y, ok := b.(*RuleScalar)
		return ok && x == y
	}
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	if reflect.TypeOf(a) != reflect.TypeOf(b) {
		return false
	}
	if !reflect.TypeOf(a).Comparable() {
		ruleFail("unmergeable source binding")
	}
	return a == b
}
