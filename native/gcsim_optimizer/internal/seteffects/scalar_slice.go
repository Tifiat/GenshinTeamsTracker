package seteffects

// Bounded pure scalar slice for source-owned contextual curves. This is NOT a
// Go interpreter: one local input, scalar assignments/arithmetic and pure if
// branches only; calls, loops, escapes and ambiguous outputs reject the slice.
// Branch evaluation is lazy so an inactive rational branch cannot divide by
// zero. The normal FAST evaluator/production engine remain unchanged.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/constant"
	"go/parser"
	"go/token"
	"math"
	"sort"
	"strconv"
)

type ScalarNode struct {
	Op      string        `json:"op"`
	Value   string        `json:"value,omitempty"`
	Args    []*ScalarNode `json:"args,omitempty"`
	literal constant.Value
}
type ScalarSlice struct {
	SourceSHA256 string      `json:"source_sha256"`
	RecipeSHA256 string      `json:"recipe_sha256"`
	Function     string      `json:"function"`
	Root         *ScalarNode `json:"root"`
}
type scalarCompiler struct{ visits int }

// ExtractScalarSlices pairs actual assignments to two observer fields on the
// SAME local receiver in a function. Field names are an adapter ABI, not set or
// reaction names. The input/output must be local scalar variables; the slice
// comes from the original source and is independently checked at observed points.
func ExtractScalarSlices(source []byte, inputField, outputField string) ([]ScalarSlice, error) {
	f, e := parser.ParseFile(token.NewFileSet(), "source.go", source, 0)
	if e != nil {
		return nil, e
	}
	out := []ScalarSlice{}
	digest := sha256.Sum256(source)
	for _, decl := range f.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if !ok || fn.Body == nil {
			continue
		}
		type pair struct {
			in, out       *ast.Object
			inPos, outPos token.Pos
			ambiguous     bool
		}
		pairs := map[*ast.Object]*pair{}
		ast.Inspect(fn.Body, func(n ast.Node) bool {
			if _, ok := n.(*ast.FuncLit); ok {
				return false
			}
			a, ok := n.(*ast.AssignStmt)
			if !ok || len(a.Lhs) != 1 || len(a.Rhs) != 1 {
				return true
			}
			s, ok := a.Lhs[0].(*ast.SelectorExpr)
			if !ok || s.Sel.Name != inputField && s.Sel.Name != outputField {
				return true
			}
			recv, ok := s.X.(*ast.Ident)
			if !ok || recv.Obj == nil {
				return true
			}
			if pairs[recv.Obj] == nil {
				pairs[recv.Obj] = &pair{}
			}
			p := pairs[recv.Obj]
			value, ok := a.Rhs[0].(*ast.Ident)
			if !ok || value.Obj == nil {
				p.ambiguous = true
				return true
			}
			if s.Sel.Name == inputField {
				if p.in != nil {
					p.ambiguous = true
				}
				p.in = value.Obj
				p.inPos = a.Pos()
			} else {
				if p.out != nil {
					p.ambiguous = true
				}
				p.out = value.Obj
				p.outPos = a.Pos()
			}
			return true
		})
		for _, p := range pairs {
			if p.ambiguous || p.in == nil || p.out == nil {
				return nil, fmt.Errorf("ambiguous scalar observer assignment in %s", fn.Name.Name)
			}
			root, e := compileScalarFunction(fn, p.in, p.out, p.inPos, p.outPos)
			if e != nil {
				return nil, fmt.Errorf("%s: %w", fn.Name.Name, e)
			}
			bytes, e := json.Marshal(root)
			if e != nil {
				return nil, e
			}
			hash := sha256.Sum256(bytes)
			out = append(out, ScalarSlice{hex.EncodeToString(digest[:]), hex.EncodeToString(hash[:]), fn.Name.Name, root})
		}
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("scalar observer pair absent")
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Function != out[j].Function {
			return out[i].Function < out[j].Function
		}
		return out[i].RecipeSHA256 < out[j].RecipeSHA256
	})
	return out, nil
}

func compileScalarFunction(fn *ast.FuncDecl, input, output *ast.Object, inPos, outPos token.Pos) (*ScalarNode, error) {
	if input == output {
		return nil, fmt.Errorf("input/output alias")
	}
	start, end, inputWrites := -1, -1, 0
	escaped := false
	for i, stmt := range fn.Body.List {
		writesOutput := false
		ast.Inspect(stmt, func(n ast.Node) bool {
			if a, ok := n.(*ast.AssignStmt); ok {
				for _, lhs := range a.Lhs {
					if id, ok := lhs.(*ast.Ident); ok {
						if id.Obj == input {
							inputWrites++
						}
						if id.Obj == output {
							writesOutput = true
						}
					}
				}
			}
			if u, ok := n.(*ast.UnaryExpr); ok && u.Op == token.AND {
				if id, ok := u.X.(*ast.Ident); ok && (id.Obj == input || id.Obj == output) {
					escaped = true
				}
			}
			if u, ok := n.(*ast.IncDecStmt); ok {
				if id, ok := u.X.(*ast.Ident); ok && (id.Obj == input || id.Obj == output) {
					escaped = true
				}
			}
			return true
		})
		if writesOutput {
			if start < 0 {
				start = i
			}
			end = i
		}
	}
	if escaped || inputWrites != 1 || start < 0 {
		return nil, fmt.Errorf("scalar source is mutable, escaped or unbound")
	}
	if inPos <= fn.Body.List[end].End() || outPos <= fn.Body.List[end].End() {
		return nil, fmt.Errorf("observer precedes final scalar write")
	}
	// The input is observed after computation. A later write would invalidate
	// that cut point even if a single input name is still visible at the end.
	inputDefinition, ok := input.Decl.(*ast.AssignStmt)
	if !ok || inputDefinition.End() >= fn.Body.List[start].Pos() {
		return nil, fmt.Errorf("input definition is not an earlier local")
	}
	env := map[*ast.Object]*ScalarNode{input: {Op: "input"}}
	c := &scalarCompiler{}
	for _, stmt := range fn.Body.List[start : end+1] {
		if e := c.statement(stmt, env); e != nil {
			return nil, e
		}
	}
	if env[output] == nil {
		return nil, fmt.Errorf("scalar result missing")
	}
	return env[output], nil
}

func (c *scalarCompiler) expression(e ast.Expr, env map[*ast.Object]*ScalarNode) (*ScalarNode, error) {
	c.visits++
	if c.visits > 256 {
		return nil, fmt.Errorf("scalar slice budget")
	}
	switch x := e.(type) {
	case *ast.Ident:
		if n := env[x.Obj]; n != nil {
			return n, nil
		}
	case *ast.ParenExpr:
		return c.expression(x.X, env)
	case *ast.BasicLit:
		if x.Kind == token.INT || x.Kind == token.FLOAT {
			return scalarLiteral(constant.MakeFromLiteral(x.Value, x.Kind, 0))
		}
	case *ast.UnaryExpr:
		if x.Op == token.SUB || x.Op == token.ADD || x.Op == token.NOT {
			a, e := c.expression(x.X, env)
			if e != nil {
				return nil, e
			}
			if a.literal != nil && x.Op != token.NOT {
				return scalarLiteral(constant.UnaryOp(x.Op, a.literal, 0))
			}
			return &ScalarNode{Op: "unary:" + x.Op.String(), Args: []*ScalarNode{a}}, nil
		}
	case *ast.BinaryExpr:
		switch x.Op {
		case token.ADD, token.SUB, token.MUL, token.QUO, token.LSS, token.LEQ, token.GTR, token.GEQ, token.EQL, token.NEQ, token.LAND, token.LOR:
			a, e := c.expression(x.X, env)
			if e != nil {
				return nil, e
			}
			b, e := c.expression(x.Y, env)
			if e != nil {
				return nil, e
			}
			// Preserve untyped constant integer division before float promotion.
			if a.literal != nil && b.literal != nil && (x.Op == token.ADD || x.Op == token.SUB || x.Op == token.MUL || x.Op == token.QUO) {
				av, bv := a.literal, b.literal
				if av.Kind() == constant.Unknown || bv.Kind() == constant.Unknown || x.Op == token.QUO && constant.Sign(bv) == 0 {
					return nil, fmt.Errorf("invalid scalar constant")
				}
				op := x.Op
				if op == token.QUO && av.Kind() == constant.Int && bv.Kind() == constant.Int {
					op = token.QUO_ASSIGN
				}
				return scalarLiteral(constant.BinaryOp(av, op, bv))
			}
			return &ScalarNode{Op: "binary:" + x.Op.String(), Args: []*ScalarNode{a, b}}, nil
		}
	}
	return nil, fmt.Errorf("unsupported scalar expression %T", e)
}
func scalarLiteral(v constant.Value) (*ScalarNode, error) {
	if v.Kind() != constant.Int && v.Kind() != constant.Float {
		return nil, fmt.Errorf("invalid scalar literal")
	}
	f, _ := constant.Float64Val(v)
	if !finite(f) {
		return nil, fmt.Errorf("nonfinite scalar literal")
	}
	return &ScalarNode{Op: "constant", Value: strconv.FormatFloat(f, 'g', -1, 64), literal: v}, nil
}

func (c *scalarCompiler) statement(stmt ast.Stmt, env map[*ast.Object]*ScalarNode) error {
	switch s := stmt.(type) {
	case *ast.AssignStmt:
		if len(s.Lhs) != 1 || len(s.Rhs) != 1 || s.Tok != token.ASSIGN && s.Tok != token.DEFINE {
			return fmt.Errorf("unsupported scalar assignment")
		}
		id, ok := s.Lhs[0].(*ast.Ident)
		if !ok || id.Obj == nil {
			return fmt.Errorf("nonlocal scalar assignment")
		}
		value, e := c.expression(s.Rhs[0], env)
		if e != nil {
			return e
		}
		// A Go local is not an untyped constant. Restrict new locals to float
		// expressions depending on the observed float input; unknown integer
		// local arithmetic must not silently become floating-point arithmetic.
		if s.Tok == token.DEFINE && value.literal != nil {
			return fmt.Errorf("untyped local outside float slice")
		}
		copy := *value
		copy.literal = nil
		env[id.Obj] = &copy
		return nil
	case *ast.IfStmt:
		if s.Init != nil {
			return fmt.Errorf("if initialization unsupported")
		}
		cond, e := c.expression(s.Cond, env)
		if e != nil {
			return e
		}
		yes, no := map[*ast.Object]*ScalarNode{}, map[*ast.Object]*ScalarNode{}
		for key, value := range env {
			yes[key] = value
			no[key] = value
		}
		for _, st := range s.Body.List {
			if e = c.statement(st, yes); e != nil {
				return e
			}
		}
		if s.Else != nil {
			if e = c.statement(s.Else, no); e != nil {
				return e
			}
		}
		for key, old := range env {
			if yes[key] != old || no[key] != old {
				env[key] = &ScalarNode{Op: "select", Args: []*ScalarNode{cond, yes[key], no[key]}}
			}
		}
		return nil
	case *ast.BlockStmt:
		for _, st := range s.List {
			if e := c.statement(st, env); e != nil {
				return e
			}
		}
		return nil
	}
	return fmt.Errorf("unsupported scalar statement %T", stmt)
}

func (s ScalarSlice) Evaluate(input float64) (float64, error) {
	budget := 512
	if !finite(input) {
		return 0, fmt.Errorf("nonfinite scalar input")
	}
	return evalScalar(s.Root, input, &budget)
}
func evalScalar(n *ScalarNode, input float64, budget *int) (float64, error) {
	*budget--
	if n == nil || *budget < 0 {
		return 0, fmt.Errorf("invalid scalar program/budget")
	}
	arg := func(i int) (float64, error) {
		if i >= len(n.Args) {
			return 0, fmt.Errorf("scalar arity")
		}
		return evalScalar(n.Args[i], input, budget)
	}
	if n.Op == "input" {
		return input, nil
	}
	if n.Op == "constant" {
		x, e := strconv.ParseFloat(n.Value, 64)
		if e != nil || !finite(x) {
			return 0, fmt.Errorf("invalid scalar constant")
		}
		return x, nil
	}
	a, e := arg(0)
	if e != nil {
		return 0, e
	}
	truth := func(v bool) float64 {
		if v {
			return 1
		}
		return 0
	}
	switch n.Op {
	case "select":
		if a != 0 {
			return arg(1)
		}
		return arg(2)
	case "unary:!":
		return truth(a == 0), nil
	case "unary:-":
		return -a, nil
	case "unary:+":
		return a, nil
	case "binary:&&":
		if a == 0 {
			return 0, nil
		}
	case "binary:||":
		if a != 0 {
			return 1, nil
		}
	}
	b, e := arg(1)
	if e != nil {
		return 0, e
	}
	v := math.NaN()
	switch n.Op {
	case "binary:+":
		v = a + b
	case "binary:-":
		v = a - b
	case "binary:*":
		v = a * b
	case "binary:/":
		v = a / b
	case "binary:<":
		v = truth(a < b)
	case "binary:<=":
		v = truth(a <= b)
	case "binary:>":
		v = truth(a > b)
	case "binary:>=":
		v = truth(a >= b)
	case "binary:==":
		v = truth(a == b)
	case "binary:!=":
		v = truth(a != b)
	case "binary:&&":
		v = truth(a != 0 && b != 0)
	case "binary:||":
		v = truth(a != 0 || b != 0)
	}
	if !finite(v) {
		return 0, fmt.Errorf("unknown or nonfinite scalar operation")
	}
	return v, nil
}
