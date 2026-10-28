package seteffects

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"path"
	"reflect"
	"sort"
	"strconv"
	"strings"
)

const maxASTNodes = 100000
const maxExpressionDepth = 32

type discovery struct {
	fset            *token.FileSet
	result          Description
	imports         map[string]map[string]string
	functionIDs     map[ast.Node]string
	functionIndex   map[string]int
	objects         map[*ast.Object]string
	globalFunctions map[string]string
	objectFunctions map[*ast.Object]string
	functions       []ast.Node
	current         string
	fieldRoles      map[string]string
}

// Discover accepts the complete original non-generated Go package, supplied by
// the engine-bound catalog owner. Sorting and hashing bind all supplied bytes.
// It never opens arbitrary imports, runs source, or classifies by set name.
func Discover(sources map[string][]byte) (Description, error) {
	d := &discovery{fset: token.NewFileSet(), imports: map[string]map[string]string{}, functionIDs: map[ast.Node]string{}, functionIndex: map[string]int{}, objects: map[*ast.Object]string{}, globalFunctions: map[string]string{}, objectFunctions: map[*ast.Object]string{}, fieldRoles: map[string]string{}}
	d.result = Description{SchemaVersion: 1, Functions: []Function{}, Writes: []Write{}, Edges: []Edge{}, Effects: []Effect{}, Boundaries: []Boundary{}, Conditions: map[string]Expression{}}
	if len(sources) == 0 {
		return Description{}, fmt.Errorf("complete source package required")
	}
	names := []string{}
	for name := range sources {
		if path.IsAbs(name) || strings.Contains(name, "\\") || strings.Contains(name, "..") || !strings.HasSuffix(name, ".go") {
			return Description{}, fmt.Errorf("invalid source label")
		}
		names = append(names, name)
	}
	sort.Strings(names)
	hash := sha256.New()
	files := []*ast.File{}
	nodes := 0
	for _, name := range names {
		fmt.Fprintf(hash, "%d:%s%d:", len(name), name, len(sources[name]))
		hash.Write(sources[name])
		file, err := parser.ParseFile(d.fset, name, sources[name], 0)
		if err != nil {
			return Description{}, err
		}
		if d.result.Package != "" && file.Name.Name != d.result.Package {
			return Description{}, fmt.Errorf("mixed packages")
		}
		d.result.Package = file.Name.Name
		files = append(files, file)
		aliases := map[string]string{}
		for _, imp := range file.Imports {
			value, e := strconv.Unquote(imp.Path.Value)
			if e != nil {
				return Description{}, e
			}
			alias := path.Base(value)
			if imp.Name != nil {
				alias = imp.Name.Name
			}
			if alias == "." {
				return Description{}, fmt.Errorf("dot imports are not supported for source ownership")
			}
			aliases[alias] = value
		}
		d.imports[name] = aliases
		ast.Inspect(file, func(n ast.Node) bool {
			if n == nil {
				return false
			}
			nodes++
			if nodes > maxASTNodes {
				return false
			}
			switch f := n.(type) {
			case *ast.FuncDecl:
				d.registerFunction(f, f.Name.Name)
				if f.Recv == nil {
					d.globalFunctions[f.Name.Name] = d.functionIDs[f]
				}
			case *ast.FuncLit:
				d.registerFunction(f, "callback")
			}
			return true
		})
	}
	if nodes > maxASTNodes {
		return Description{}, fmt.Errorf("source discovery node budget exceeded")
	}
	d.result.SourceSHA256 = hex.EncodeToString(hash.Sum(nil))
	// Function-value aliases are linked only through a single declaration. Later
	// writes invalidate that link; unresolved callbacks stay visible boundaries.
	counts := map[*ast.Object]int{}
	for _, file := range files {
		ast.Inspect(file, func(n ast.Node) bool {
			if address, ok := n.(*ast.UnaryExpr); ok && address.Op == token.AND {
				if id, ok := address.X.(*ast.Ident); ok && id.Obj != nil {
					if _, parameter := id.Obj.Decl.(*ast.Field); parameter {
						counts[id.Obj] += 2
					}
				}
			}
			if v, ok := n.(*ast.ValueSpec); ok {
				for i, name := range v.Names {
					if name.Obj != nil {
						counts[name.Obj]++
						if len(v.Values) == len(v.Names) {
							if f, ok := v.Values[i].(*ast.FuncLit); ok {
								d.objectFunctions[name.Obj] = d.functionIDs[f]
							}
						}
					}
				}
			}
			if inc, ok := n.(*ast.IncDecStmt); ok {
				if id, ok := inc.X.(*ast.Ident); ok && id.Obj != nil {
					counts[id.Obj]++
				}
			}
			a, ok := n.(*ast.AssignStmt)
			if !ok {
				return true
			}
			for i, lhs := range a.Lhs {
				ident, ok := lhs.(*ast.Ident)
				if !ok || ident.Obj == nil {
					continue
				}
				counts[ident.Obj]++
				if len(a.Rhs) == len(a.Lhs) {
					if f, ok := a.Rhs[i].(*ast.FuncLit); ok {
						d.objectFunctions[ident.Obj] = d.functionIDs[f]
					}
				}
			}
			return true
		})
	}
	for obj, n := range counts {
		if n != 1 {
			delete(d.objectFunctions, obj)
		}
	}
	d.bindReturnedReceiver(counts)
	d.bindTeamRecipients(files, counts)
	d.bindAmountInputs(counts)
	for _, file := range files {
		for _, decl := range file.Decls {
			if g, ok := decl.(*ast.GenDecl); ok {
				d.current = "package"
				d.declarations(g, nil)
			}
		}
	}
	for _, node := range d.functions {
		d.current = d.functionIDs[node]
		switch f := node.(type) {
		case *ast.FuncDecl:
			if f.Body != nil {
				d.block(f.Body.List, nil)
			}
		case *ast.FuncLit:
			d.block(f.Body.List, nil)
		}
	}
	return d.result, nil
}

func (d *discovery) at(n ast.Node) Location {
	p := d.fset.Position(n.Pos())
	return Location{p.Filename, p.Line}
}
func (d *discovery) id(n ast.Node) string {
	p := d.fset.Position(n.Pos())
	return fmt.Sprintf("%s:%d", p.Filename, p.Offset)
}
func (d *discovery) text(n ast.Node) string {
	if n == nil {
		return ""
	}
	var b bytes.Buffer
	_ = format.Node(&b, d.fset, n)
	return b.String()
}
func (d *discovery) registerFunction(n ast.Node, name string) {
	id := d.id(n)
	d.functionIDs[n] = id
	d.functionIndex[id] = len(d.result.Functions)
	d.result.Functions = append(d.result.Functions, Function{ID: id, Name: name, Returns: []Return{}, At: d.at(n)})
	d.functions = append(d.functions, n)
}
func (d *discovery) boundary(reason string, n ast.Node) {
	d.result.Boundaries = append(d.result.Boundaries, Boundary{reason, d.current, d.text(n), d.at(n)})
}
func guardsWith(g []string, extra string) []string {
	out := append([]string{}, g...)
	return append(out, extra)
}

func (d *discovery) expr(n ast.Expr, depth int) Expression {
	if n == nil {
		return Expression{Kind: "absent"}
	}
	e := Expression{Kind: "opaque", Text: d.text(n)}
	if depth >= maxExpressionDepth {
		d.boundary("expression_depth", n)
		return e
	}
	child := func(v ast.Expr) Expression { return d.expr(v, depth+1) }
	switch x := n.(type) {
	case *ast.BasicLit:
		e.Kind = "literal"
	case *ast.Ident:
		e.Kind = "symbol"
		if x.Obj != nil {
			e.Symbol = d.objects[x.Obj]
			if e.Symbol == "" {
				e.Symbol = d.id(x) + ":" + x.Name
				if decl, ok := x.Obj.Decl.(ast.Node); ok {
					e.Symbol = d.id(decl) + ":" + x.Name
				}
				d.objects[x.Obj] = e.Symbol
			}
		} else {
			e.Symbol = "unbound:" + x.Name
		}
	case *ast.SelectorExpr:
		e.Kind = "selector"
		e.Symbol = x.Sel.Name
		e.Inputs = []Expression{child(x.X)}
		if role := d.fieldRoles[e.Inputs[0].Symbol+"."+x.Sel.Name]; role != "" {
			e.Kind = "bound_field"
			e.Symbol = role
		}
		if ident, ok := x.X.(*ast.Ident); ok && ident.Obj == nil {
			if imp := d.imports[d.at(n).File][ident.Name]; imp != "" {
				e.Kind = "qualified"
				e.Symbol = imp + "." + x.Sel.Name
				e.Inputs = nil
			}
		}
	case *ast.BinaryExpr:
		e.Kind = "binary:" + x.Op.String()
		e.Inputs = []Expression{child(x.X), child(x.Y)}
	case *ast.UnaryExpr:
		e.Kind = "unary:" + x.Op.String()
		e.Inputs = []Expression{child(x.X)}
	case *ast.ParenExpr:
		return child(x.X)
	case *ast.IndexExpr:
		e.Kind = "index"
		e.Inputs = []Expression{child(x.X), child(x.Index)}
	case *ast.CallExpr:
		e.Kind = "call"
		e.Inputs = append(e.Inputs, child(x.Fun))
		for _, a := range x.Args {
			e.Inputs = append(e.Inputs, child(a))
		}
	case *ast.FuncLit:
		e.Kind = "function"
		e.Symbol = d.functionIDs[x]
		e.Text = "callback"
	case *ast.CompositeLit:
		e.Kind = "composite"
		e.Symbol = d.text(x.Type)
		for _, v := range x.Elts {
			if kv, ok := v.(*ast.KeyValueExpr); ok {
				e.Inputs = append(e.Inputs, Expression{Kind: "field", Text: d.text(kv.Key), Inputs: []Expression{child(kv.Value)}})
			} else {
				e.Inputs = append(e.Inputs, child(v))
			}
		}
	case *ast.TypeAssertExpr:
		e.Kind = "type_assert"
		e.Symbol = d.text(x.Type)
		e.Inputs = []Expression{child(x.X)}
	default:
		d.boundary("expression_shape", n)
	}
	return e
}

func (d *discovery) function(n ast.Expr) string {
	switch x := n.(type) {
	case *ast.FuncLit:
		return d.functionIDs[x]
	case *ast.Ident:
		if x.Obj != nil {
			if id := d.objectFunctions[x.Obj]; id != "" {
				return id
			}
			if f, ok := x.Obj.Decl.(*ast.FuncDecl); ok {
				return d.functionIDs[f]
			}
			return ""
		}
		return d.globalFunctions[x.Name]
	case *ast.SelectorExpr:
		if ident, ok := x.X.(*ast.Ident); ok && ident.Obj != nil {
			owner := d.objects[ident.Obj]
			if strings.HasPrefix(owner, "set_receiver:") {
				for _, n := range d.functions {
					if f, ok := n.(*ast.FuncDecl); ok && f.Recv != nil && f.Name.Name == x.Sel.Name && "set_receiver:"+d.receiverType(f.Recv.List[0].Type) == owner {
						return d.functionIDs[f]
					}
				}
			}
		}
	}
	return ""
}
func (d *discovery) edge(to, kind string, trigger ast.Expr, n ast.Node, guards []string) {
	if to == "" {
		d.boundary("callback_or_helper_unresolved", n)
		return
	}
	d.result.Edges = append(d.result.Edges, Edge{d.current, to, kind, d.expr(trigger, 0), append([]string{}, guards...), d.at(n)})
}

func (d *discovery) calls(n ast.Node, guards []string) {
	if n == nil {
		return
	}
	ast.Inspect(n, func(node ast.Node) bool {
		if _, ok := node.(*ast.FuncLit); ok {
			return false
		}
		c, ok := node.(*ast.CallExpr)
		if !ok {
			return true
		}
		if target := d.function(c.Fun); target != "" {
			d.edge(target, "call", nil, c, guards)
			return true
		}
		selector, ok := c.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		method := selector.Sel.Name
		if method == "Subscribe" && len(c.Args) >= 2 {
			d.edge(d.function(c.Args[1]), "event", c.Args[0], c, guards)
		}
		for _, arg := range c.Args {
			if fn := d.function(arg); fn != "" && method != "Subscribe" {
				d.edge(fn, "callback:"+method, nil, c, guards)
			}
		}
		kind := ""
		switch method {
		case "AddStatMod":
			kind = "stat"
		case "AddAttackMod":
			kind = "attack_bonus"
		case "AddReactBonusMod":
			kind = "reaction_bonus"
		case "AddResistMod":
			kind = "resistance"
		case "AddDefMod":
			kind = "defense"
		case "QueueAttack", "QueueAttackWithSnapShot":
			kind = "new_attack"
		case "Heal":
			kind = "healing"
		case "AddEnergy":
			kind = "energy"
		}
		if kind == "" {
			if strings.HasPrefix(method, "Add") || strings.HasPrefix(method, "Queue") {
				d.boundary("unclassified_operation", c)
			}
			return true
		}
		e := Effect{ID: d.id(c), Kind: kind, Operation: method, Receiver: d.expr(selector.X, 0), Function: d.current, Guards: append([]string{}, guards...), At: d.at(c), Fields: []Field{}}
		if len(c.Args) > 0 {
			if v := d.composite(c.Args[0]); v != nil {
				for _, item := range v.Elts {
					if kv, ok := item.(*ast.KeyValueExpr); ok {
						name := d.text(kv.Key)
						e.Fields = append(e.Fields, Field{name, d.expr(kv.Value, 0)})
						if name == "Amount" {
							e.AmountFunction = d.function(kv.Value)
							if e.AmountFunction == "" {
								d.boundary("amount_helper_unresolved", kv.Value)
							}
						}
					}
				}
			} else {
				e.Fields = append(e.Fields, Field{"argument", d.expr(c.Args[0], 0)})
			}
		}
		d.result.Effects = append(d.result.Effects, e)
		return true
	})
}

func (d *discovery) write(target ast.Expr, op string, value ast.Expr, g []string, n ast.Node) {
	d.result.Writes = append(d.result.Writes, Write{d.expr(target, 0), op, d.expr(value, 0), d.current, append([]string{}, g...), d.at(n)})
}
func (d *discovery) declarations(g *ast.GenDecl, guards []string) {
	for _, spec := range g.Specs {
		v, ok := spec.(*ast.ValueSpec)
		if !ok {
			continue
		}
		for i, name := range v.Names {
			if i < len(v.Values) {
				d.write(name, g.Tok.String(), v.Values[i], guards, v)
				d.calls(v.Values[i], guards)
			} else {
				d.boundary("implicit_or_multi_value_declaration", v)
			}
		}
	}
}
func exits(list []ast.Stmt) bool {
	if len(list) == 0 {
		return false
	}
	switch s := list[len(list)-1].(type) {
	case *ast.ReturnStmt:
		return true
	case *ast.BranchStmt:
		return s.Tok == token.CONTINUE || s.Tok == token.BREAK
	case *ast.BlockStmt:
		return exits(s.List)
	}
	return false
}

func (d *discovery) block(stmts []ast.Stmt, guards []string) {
	g := append([]string{}, guards...)
	for _, stmt := range stmts {
		switch s := stmt.(type) {
		case *ast.BlockStmt:
			d.block(s.List, g)
		case *ast.AssignStmt:
			for i, lhs := range s.Lhs {
				if len(s.Rhs) == len(s.Lhs) {
					d.write(lhs, s.Tok.String(), s.Rhs[i], g, s)
				} else {
					d.boundary("multi_value_assignment", s)
				}
			}
			for _, rhs := range s.Rhs {
				d.calls(rhs, g)
			}
		case *ast.DeclStmt:
			if gen, ok := s.Decl.(*ast.GenDecl); ok {
				d.declarations(gen, g)
			}
		case *ast.ExprStmt:
			d.calls(s.X, g)
		case *ast.ReturnStmt:
			values := []Expression{}
			for _, v := range s.Results {
				values = append(values, d.expr(v, 0))
				d.calls(v, g)
				if _, ok := v.(*ast.FuncLit); ok {
					d.edge(d.function(v), "returned_callback", nil, s, g)
				}
			}
			i := d.functionIndex[d.current]
			d.result.Functions[i].Returns = append(d.result.Functions[i].Returns, Return{values, append([]string{}, g...), d.at(s)})
			return
		case *ast.IfStmt:
			if s.Init != nil {
				d.block([]ast.Stmt{s.Init}, g)
			}
			d.calls(s.Cond, g)
			cond := d.text(s.Cond)
			d.condition(cond, d.expr(s.Cond, 0))
			d.condition("!("+cond+")", Expression{Kind: "unary:!", Text: "!(" + cond + ")", Inputs: []Expression{d.expr(s.Cond, 0)}})
			d.block(s.Body.List, guardsWith(g, cond))
			if s.Else != nil {
				d.block([]ast.Stmt{s.Else}, guardsWith(g, "!("+cond+")"))
			}
			if exits(s.Body.List) {
				g = guardsWith(g, "!("+cond+")")
			}
		case *ast.RangeStmt:
			d.calls(s.X, g)
			d.block(s.Body.List, guardsWith(g, "range "+d.text(s.X)))
			d.boundary("iteration_membership_requires_context", s.X)
		case *ast.ForStmt:
			if s.Init != nil {
				d.block([]ast.Stmt{s.Init}, g)
			}
			d.block(s.Body.List, guardsWith(g, "loop "+d.text(s.Cond)))
			if s.Post != nil {
				d.block([]ast.Stmt{s.Post}, g)
			}
			d.boundary("iteration_count_requires_context", s)
		case *ast.SwitchStmt:
			g = d.switchBlock(s, g)
		case *ast.IncDecStmt:
			d.write(s.X, s.Tok.String(), nil, g, s)
		case *ast.BranchStmt:
			if s.Tok == token.FALLTHROUGH || s.Tok == token.GOTO {
				d.boundary("nonlocal_control_flow", s)
			}
			return
		default:
			d.boundary("statement_shape", s)
		}
	}
}

func (d *discovery) condition(key string, e Expression) {
	if old, ok := d.result.Conditions[key]; ok && !reflect.DeepEqual(old, e) {
		// Identical display text can refer to shadowed locals. Until guards get
		// occurrence IDs, ambiguous text may NEVER authorize tier exclusion.
		d.result.Conditions[key] = Expression{Kind: "ambiguous_condition", Text: key}
		return
	}
	d.result.Conditions[key] = e
}
