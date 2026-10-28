package seteffects

// Research-only source hints. A recognized two-piece literal is useful for
// proposal ordering, not proof that another package is irrelevant. Four-piece
// activation and all unrecognized two-piece shapes remain on the exact route.
import (
	"go/ast"
	"go/parser"
	"go/token"
	"math"
	"sort"
	"strconv"
	"strings"
)

// HypothesisLiteral2P returns a defensive copy of a narrowly recognized,
// unconditional two-piece owner-stat vector. false means unknown, not zero.
func (c *SourceCatalog) HypothesisLiteral2P(key string) (map[string]float64, bool) {
	if c == nil {
		return nil, false
	}
	hint, ok := c.hypothesisLiteral2P[key]
	if !ok {
		return nil, false
	}
	out := make(map[string]float64, len(hint))
	for k, v := range hint {
		out[k] = v
	}
	return out, true
}

func hypothesisExtractLiteral2P(sources map[string][]byte, stats map[string]string) (map[string]float64, bool) {
	if len(sources) == 0 || len(stats) == 0 {
		return nil, false
	}
	names := make([]string, 0, len(sources))
	for name := range sources {
		names = append(names, name)
	}
	sort.Strings(names)
	var result map[string]float64
	seenNew := false
	for _, name := range names {
		file, err := parser.ParseFile(token.NewFileSet(), name, sources[name], 0)
		if err != nil {
			return nil, false
		}
		attributes := map[string]bool{}
		for _, imp := range file.Imports {
			path, err := strconv.Unquote(imp.Path.Value)
			if err != nil {
				return nil, false
			}
			if path != "github.com/genshinsim/gcsim/pkg/core/attributes" {
				continue
			}
			alias := "attributes"
			if imp.Name != nil {
				alias = imp.Name.Name
			}
			if alias == "." || alias == "_" {
				return nil, false
			}
			attributes[alias] = true
		}
		for _, decl := range file.Decls {
			fn, ok := decl.(*ast.FuncDecl)
			if !ok || fn.Recv != nil || fn.Name.Name != "NewSet" || fn.Body == nil {
				continue
			}
			if seenNew {
				return nil, false
			}
			seenNew = true
			count := ""
			parameters := map[string]bool{}
			for _, field := range fn.Type.Params.List {
				for _, n := range field.Names {
					parameters[n.Name] = true
					if typ, ok := field.Type.(*ast.Ident); ok && typ.Name == "int" {
						if count != "" {
							return nil, false
						}
						count = n.Name
					}
				}
			}
			if count == "" {
				return nil, false
			}
			seenTwo := false
			for _, stmt := range fn.Body.List {
				if branch, ok := stmt.(*ast.IfStmt); ok {
					if branch.Init != nil || branch.Else != nil {
						return nil, false
					}
					if hypothesisCountAtLeast(branch.Cond, count, 4) {
						continue
					}
					if !hypothesisCountAtLeast(branch.Cond, count, 2) || seenTwo {
						return nil, false
					}
					parsed, ok := hypothesisLiteralBlock(branch.Body.List, attributes, stats, parameters)
					if !ok {
						return nil, false
					}
					result, seenTwo = parsed, true
					continue
				}
				// Top-level setup may assign fields and return, but cannot invoke
				// an unclassified helper that could itself register a two-piece mod.
				if !hypothesisInertTopLevel(stmt) {
					return nil, false
				}
			}
			if !seenTwo {
				return nil, false
			}
		}
	}
	return result, result != nil && len(result) != 0
}

func hypothesisCountAtLeast(expr ast.Expr, count string, floor int64) bool {
	b, ok := expr.(*ast.BinaryExpr)
	if !ok || b.Op != token.GEQ {
		return false
	}
	id, ok := b.X.(*ast.Ident)
	if !ok || id.Name != count {
		return false
	}
	lit, ok := b.Y.(*ast.BasicLit)
	if !ok || lit.Kind != token.INT {
		return false
	}
	n, err := strconv.ParseInt(lit.Value, 0, 64)
	return err == nil && n == floor
}

func hypothesisInertTopLevel(stmt ast.Stmt) bool {
	switch stmt.(type) {
	case *ast.AssignStmt, *ast.DeclStmt, *ast.ReturnStmt:
	default:
		return false
	}
	ok := true
	ast.Inspect(stmt, func(n ast.Node) bool {
		if _, call := n.(*ast.CallExpr); call {
			ok = false
			return false
		}
		return true
	})
	return ok
}

func hypothesisLiteralBlock(stmts []ast.Stmt, attributes map[string]bool, stats map[string]string, parameters map[string]bool) (map[string]float64, bool) {
	vectors := map[string]map[string]float64{}
	used := map[string]bool{}
	out := map[string]float64{}
	mods := 0
	for _, stmt := range stmts {
		switch s := stmt.(type) {
		case *ast.AssignStmt:
			if len(s.Lhs) != 1 || len(s.Rhs) != 1 {
				return nil, false
			}
			if id, ok := s.Lhs[0].(*ast.Ident); ok && s.Tok == token.DEFINE {
				call, ok := s.Rhs[0].(*ast.CallExpr)
				if !ok || !hypothesisVectorMake(call, attributes) || vectors[id.Name] != nil {
					return nil, false
				}
				vectors[id.Name] = map[string]float64{}
				continue
			}
			idx, ok := s.Lhs[0].(*ast.IndexExpr)
			if !ok || s.Tok != token.ASSIGN {
				return nil, false
			}
			id, ok := idx.X.(*ast.Ident)
			if !ok || vectors[id.Name] == nil || used[id.Name] {
				return nil, false
			}
			key, ok := hypothesisStatKey(idx.Index, attributes, stats)
			if !ok {
				return nil, false
			}
			value, ok := hypothesisNumber(s.Rhs[0], 0)
			if !ok || !hypothesisFinite(value) {
				return nil, false
			}
			if _, duplicate := vectors[id.Name][key]; duplicate {
				return nil, false
			}
			vectors[id.Name][key] = value
		case *ast.ExprStmt:
			call, ok := s.X.(*ast.CallExpr)
			if !ok {
				return nil, false
			}
			name, key, ok := hypothesisStatMod(call, attributes, stats, parameters)
			if !ok || vectors[name] == nil || used[name] || len(vectors[name]) != 1 {
				return nil, false
			}
			value, ok := vectors[name][key]
			if !ok {
				return nil, false
			}
			out[key] += value
			used[name], mods = true, mods+1
		default:
			return nil, false
		}
	}
	if mods == 0 || len(used) != len(vectors) {
		return nil, false
	}
	return out, true
}

func hypothesisVectorMake(call *ast.CallExpr, attributes map[string]bool) bool {
	fn, ok := call.Fun.(*ast.Ident)
	if !ok || fn.Name != "make" || len(call.Args) != 2 {
		return false
	}
	arr, ok := call.Args[0].(*ast.ArrayType)
	if !ok || arr.Len != nil {
		return false
	}
	elt, ok := arr.Elt.(*ast.Ident)
	if !ok || elt.Name != "float64" {
		return false
	}
	selector, ok := call.Args[1].(*ast.SelectorExpr)
	if !ok || selector.Sel.Name != "EndStatType" {
		return false
	}
	alias, ok := selector.X.(*ast.Ident)
	return ok && attributes[alias.Name]
}

func hypothesisStatKey(expr ast.Expr, attributes map[string]bool, stats map[string]string) (string, bool) {
	selector, ok := expr.(*ast.SelectorExpr)
	if !ok {
		return "", false
	}
	alias, ok := selector.X.(*ast.Ident)
	if !ok || !attributes[alias.Name] {
		return "", false
	}
	engineKey, ok := stats["github.com/genshinsim/gcsim/pkg/core/attributes."+selector.Sel.Name]
	if !ok {
		return "", false
	}
	return OwnerStatKey(engineKey)
}

func hypothesisStatMod(call *ast.CallExpr, attributes map[string]bool, stats map[string]string, parameters map[string]bool) (string, string, bool) {
	method, ok := call.Fun.(*ast.SelectorExpr)
	if !ok || method.Sel.Name != "AddStatMod" || len(call.Args) != 1 {
		return "", "", false
	}
	receiver, ok := method.X.(*ast.Ident)
	if !ok || !parameters[receiver.Name] {
		return "", "", false
	}
	lit, ok := call.Args[0].(*ast.CompositeLit)
	if !ok {
		return "", "", false
	}
	typ, ok := lit.Type.(*ast.SelectorExpr)
	if !ok || typ.Sel.Name != "StatMod" {
		return "", "", false
	}
	fields := map[string]ast.Expr{}
	for _, entry := range lit.Elts {
		kv, ok := entry.(*ast.KeyValueExpr)
		if !ok {
			return "", "", false
		}
		field, ok := kv.Key.(*ast.Ident)
		if !ok {
			return "", "", false
		}
		fields[field.Name] = kv.Value
	}
	key, ok := hypothesisStatKey(fields["AffectedStat"], attributes, stats)
	if !ok {
		return "", "", false
	}
	fn, ok := fields["Amount"].(*ast.FuncLit)
	if !ok || len(fn.Body.List) != 1 {
		return "", "", false
	}
	ret, ok := fn.Body.List[0].(*ast.ReturnStmt)
	if !ok || len(ret.Results) != 1 {
		return "", "", false
	}
	vector, ok := ret.Results[0].(*ast.Ident)
	if !ok {
		return "", "", false
	}
	return vector.Name, key, true
}

func hypothesisNumber(expr ast.Expr, depth int) (float64, bool) {
	if depth > 8 {
		return 0, false
	}
	switch x := expr.(type) {
	case *ast.ParenExpr:
		return hypothesisNumber(x.X, depth+1)
	case *ast.BasicLit:
		if x.Kind != token.INT && x.Kind != token.FLOAT {
			return 0, false
		}
		v, err := strconv.ParseFloat(strings.ReplaceAll(x.Value, "_", ""), 64)
		return v, err == nil && hypothesisFinite(v)
	case *ast.UnaryExpr:
		v, ok := hypothesisNumber(x.X, depth+1)
		if x.Op == token.SUB {
			return -v, ok
		}
		return v, ok && x.Op == token.ADD
	case *ast.BinaryExpr:
		a, okA := hypothesisNumber(x.X, depth+1)
		b, okB := hypothesisNumber(x.Y, depth+1)
		if !okA || !okB {
			return 0, false
		}
		var v float64
		switch x.Op {
		case token.ADD:
			v = a + b
		case token.SUB:
			v = a - b
		case token.MUL:
			v = a * b
		case token.QUO:
			if b == 0 {
				return 0, false
			}
			v = a / b
		default:
			return 0, false
		}
		return v, hypothesisFinite(v)
	}
	return 0, false
}

func hypothesisFinite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }
