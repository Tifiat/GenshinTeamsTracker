package seteffects

// Bounded source evaluator for the neutral-event producer (trace handoff section
// 2). This is not a Go runtime: it has no IO, imports cannot execute arbitrary
// code, and unsupported operations stop the affected rule explicitly. Gameplay
// constants, branches and closures come from the bound source package. Host API
// seams live separately in the event replay adapter. Focused evaluator tests pin
// this deliberately restricted contract before product integration.
import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"math"
	"path"
	"sort"
	"strconv"
	"strings"
)

const gcsimImport = "github.com/genshinsim/gcsim/"

type ruleProgram struct {
	modules map[string]*ruleModule
	entry   string
}
type ruleModule struct {
	name      string
	files     []*ast.File
	envs      map[*ast.File]*ruleEnv
	functions map[string]*ruleFunction
	globals   map[string]ruleGlobal
	types     map[string]ast.Expr
	typeEnvs  map[string]*ruleEnv
}
type ruleGlobal struct {
	expr ast.Expr
	typ  ast.Expr
	env  *ruleEnv
	iota int
}
type ruleEnv struct {
	parent  *ruleEnv
	module  *ruleModule
	vars    map[string]any
	imports map[string]string
}
type ruleObject struct {
	flatWrite func(any, any)
	typ       string
	fields    map[string]any
	observed  bool
}
type rulePointer struct{ object *ruleObject }
type ruleSlice struct {
	values   []any
	observed bool
}
type ruleMap struct {
	values    map[any]any
	valueType ast.Expr
	env       *ruleEnv
}
type ruleFunction struct {
	typ           *ast.FuncType
	body          *ast.BlockStmt
	env           *ruleEnv
	receiver      string
	object        any
	valueReceiver bool
}
type rulePackage string
type ruleNative struct {
	receiver any
	name     string
}
type ruleType struct{ name string }
type ruleTuple []any
type ruleUnknown struct{ reason string }
type ruleTypedNumber struct {
	value float64
	typ   string
}
type ruleAbort struct{ reason string }
type ruleControl struct {
	kind   token.Token
	values []any
}

type ruleHost interface {
	field(receiver any, name string) (any, bool)
	call(receiver any, name string, args []any) (any, bool)
}
type ruleVM struct {
	program            *ruleProgram
	host               ruleHost
	remaining          int
	globals            map[*ruleModule]map[string]any
	loading            map[string]bool
	depth              int
	readOnly           bool
	flatAdd            bool
	readRoot           *ruleEnv
	readLocals         map[*ruleEnv]bool
	scratch            map[*ruleSlice]bool
	scratchWritten     map[*ruleSlice]map[int]bool
	registrationEvents map[int]bool
	amountPlans        map[*ast.BlockStmt]amountPlan
	amountPlanOrder    []*ast.BlockStmt
}

func compileRuleProgram(sources, libraries map[string][]byte) (*ruleProgram, error) {
	return compileRuleProgramCached(sources, libraries, nil)
}

func compileRuleProgramCached(sources, libraries map[string][]byte, cache *RuleParseCache) (*ruleProgram, error) {
	p := &ruleProgram{modules: map[string]*ruleModule{}}
	all := map[string][]byte{}
	for name, body := range libraries {
		all[name] = body
	}
	for name, body := range sources {
		if old, ok := all[name]; ok && string(old) != string(body) {
			return nil, fmt.Errorf("conflicting rule source")
		}
		all[name] = body
		module := gcsimImport + path.Dir(name)
		if p.entry != "" && p.entry != module {
			return nil, fmt.Errorf("mixed rule entry packages")
		}
		p.entry = module
	}
	if p.entry == "" {
		return nil, fmt.Errorf("empty rule package")
	}
	names := make([]string, 0, len(all))
	for name := range all {
		names = append(names, name)
	}
	sort.Strings(names)
	nodes := 0
	for _, name := range names {
		if path.IsAbs(name) || strings.Contains(name, "..") || strings.Contains(name, "\\") || !strings.HasSuffix(name, ".go") {
			return nil, fmt.Errorf("invalid rule source path")
		}
		var f *ast.File
		var err error
		if cache != nil {
			f, err = cache.loadFile(name, all[name])
		} else {
			f, err = parser.ParseFile(token.NewFileSet(), name, all[name], parser.SkipObjectResolution)
		}
		if err != nil {
			return nil, err
		}
		ast.Inspect(f, func(n ast.Node) bool {
			if n != nil {
				nodes++
			}
			return nodes <= maxASTNodes
		})
		if nodes > maxASTNodes {
			return nil, fmt.Errorf("rule source node budget exceeded")
		}
		module := gcsimImport + path.Dir(name)
		m := p.modules[module]
		if m == nil {
			m = &ruleModule{name: module, envs: map[*ast.File]*ruleEnv{}, functions: map[string]*ruleFunction{}, globals: map[string]ruleGlobal{}, types: map[string]ast.Expr{}, typeEnvs: map[string]*ruleEnv{}}
			p.modules[module] = m
		}
		e := &ruleEnv{module: m, vars: map[string]any{}, imports: map[string]string{}}
		for _, imp := range f.Imports {
			value, err := strconv.Unquote(imp.Path.Value)
			if err != nil {
				return nil, err
			}
			alias := path.Base(value)
			if imp.Name != nil {
				alias = imp.Name.Name
			}
			if alias == "." {
				return nil, fmt.Errorf("dot import in rule")
			}
			e.imports[alias] = value
		}
		m.files = append(m.files, f)
		m.envs[f] = e
		for _, decl := range f.Decls {
			switch d := decl.(type) {
			case *ast.FuncDecl:
				key, receiver := d.Name.Name, ""
				if d.Recv != nil {
					if len(d.Recv.List) != 1 || len(d.Recv.List[0].Names) != 1 {
						return nil, fmt.Errorf("unsupported rule receiver")
					}
					receiver = d.Recv.List[0].Names[0].Name
					key = ruleTypeName(d.Recv.List[0].Type, e) + "." + key
				}
				if _, exists := m.functions[key]; exists {
					return nil, fmt.Errorf("duplicate rule function %s", key)
				}
				byValue := false
				if d.Recv != nil {
					_, pointer := d.Recv.List[0].Type.(*ast.StarExpr)
					byValue = !pointer
				}
				m.functions[key] = &ruleFunction{typ: d.Type, body: d.Body, env: e, receiver: receiver, valueReceiver: byValue}
			case *ast.GenDecl:
				var previous []ast.Expr
				var previousType ast.Expr
				for ordinal, spec := range d.Specs {
					switch s := spec.(type) {
					case *ast.TypeSpec:
						m.types[s.Name.Name] = s.Type
						m.typeEnvs[s.Name.Name] = e
					case *ast.ValueSpec:
						values, typ := s.Values, s.Type
						if len(values) == 0 && d.Tok == token.CONST {
							values, typ = previous, previousType
						}
						if len(values) != 0 && len(values) != len(s.Names) {
							return nil, fmt.Errorf("unsupported rule global tuple")
						}
						for i, id := range s.Names {
							if id.Name == "_" {
								continue
							}
							if _, exists := m.globals[id.Name]; exists {
								return nil, fmt.Errorf("duplicate rule global")
							}
							var expr ast.Expr
							if len(values) > 0 {
								expr = values[i]
							}
							m.globals[id.Name] = ruleGlobal{expr, typ, e, ordinal}
						}
						previous, previousType = values, typ
					}
				}
			}
		}
	}
	return p, nil
}

func newRuleVM(p *ruleProgram, h ruleHost, budget int) *ruleVM {
	return &ruleVM{program: p, host: h, remaining: budget, globals: map[*ruleModule]map[string]any{}, loading: map[string]bool{}}
}
func (v *ruleVM) tick() {
	v.remaining--
	if v.remaining < 0 {
		ruleFail("source evaluation budget exhausted")
	}
}
func ruleFail(reason string) { panic(ruleAbort{reason}) }
func ruleTry(fn func() any) (out any, err error) {
	defer func() {
		if failure := recover(); failure != nil {
			if r, ok := failure.(ruleAbort); ok {
				err = fmt.Errorf("%s", r.reason)
			} else {
				panic(failure)
			}
		}
	}()
	return fn(), nil
}
func (v *ruleVM) entry(name string, args ...any) (any, error) {
	return ruleTry(func() any {
		return v.invoke(v.lookup(v.program.modules[v.program.entry].envs[v.program.modules[v.program.entry].files[0]], name), args)
	})
}
func childRuleEnv(e *ruleEnv) *ruleEnv {
	return &ruleEnv{parent: e, module: e.module, vars: map[string]any{}}
}
func (v *ruleVM) lookup(e *ruleEnv, name string) any {
	for scope := e; scope != nil; scope = scope.parent {
		if value, ok := scope.vars[name]; ok {
			if binding, ok := value.(ruleAddressBinding); ok {
				return binding.cell.value
			}
			return value
		}
		if module, ok := scope.imports[name]; ok {
			return rulePackage(module)
		}
	}
	switch name {
	case "true":
		return true
	case "false":
		return false
	case "nil":
		return nil
	case "len", "make", "append", "copy", "min", "max", "clear":
		return ruleNative{name: name}
	case "float64", "float32", "int", "int64", "uint64", "int32", "uint32", "string", "bool":
		return ruleType{name}
	}
	if f, ok := e.module.functions[name]; ok {
		return f
	}
	if _, ok := e.module.types[name]; ok {
		return ruleType{e.module.name + "." + name}
	}
	if g, ok := e.module.globals[name]; ok {
		if v.globals[e.module] == nil {
			v.globals[e.module] = map[string]any{}
		}
		if value, ok := v.globals[e.module][name]; ok {
			return value
		}
		key := e.module.name + "." + name
		if v.loading[key] {
			ruleFail("cyclic rule global: " + key)
		}
		v.loading[key] = true
		env := childRuleEnv(g.env)
		env.vars["iota"] = float64(g.iota)
		value := v.zero(g.typ, env)
		if g.expr != nil {
			value = v.eval(g.expr, env)
		}
		name := ruleTypeName(g.typ, env)
		if m, member := v.typeModule(name); m != nil {
			if base, ok := m.types[member].(*ast.Ident); ok && base.Name == "int" {
				value = ruleTypedNumber{ruleNumber(value), name}
			}
		}
		v.globals[e.module][name] = value
		delete(v.loading, key)
		return value
	}
	ruleFail("unknown source symbol: " + e.module.name + "." + name)
	return nil
}
func ruleTypeName(t ast.Expr, e *ruleEnv) string {
	switch x := t.(type) {
	case *ast.Ident:
		switch x.Name {
		case "float64", "float32", "int", "int64", "uint64", "int32", "uint32", "string", "bool", "any", "error":
			return x.Name
		}
		return e.module.name + "." + x.Name
	case *ast.SelectorExpr:
		if id, ok := x.X.(*ast.Ident); ok {
			for s := e; s != nil; s = s.parent {
				if p, ok := s.imports[id.Name]; ok {
					return p + "." + x.Sel.Name
				}
			}
		}
	case *ast.StarExpr:
		return ruleTypeName(x.X, e)
	}
	return ""
}
func (v *ruleVM) zero(t ast.Expr, e *ruleEnv) any {
	if t == nil {
		return nil
	}
	switch x := t.(type) {
	case *ast.StarExpr, *ast.FuncType, *ast.InterfaceType:
		return nil
	case *ast.MapType:
		return nil
	case *ast.ArrayType:
		if x.Len == nil {
			return nil
		}
		n := ruleInteger(v.eval(x.Len, e))
		if n < 0 || n > 4096 {
			ruleFail("rule array size")
		}
		a := &ruleSlice{values: make([]any, n)}
		for i := range a.values {
			a.values[i] = v.zero(x.Elt, e)
		}
		return a
	case *ast.StructType:
		o := &ruleObject{fields: map[string]any{}}
		for _, field := range x.Fields.List {
			for _, id := range field.Names {
				o.fields[id.Name] = v.zero(field.Type, e)
			}
		}
		return o
	}
	name := ruleTypeName(t, e)
	switch name {
	case "bool":
		return false
	case "string":
		return ""
	case "any", "error":
		return nil
	case "int", "int64", "int32", "uint64", "uint32", "float64", "float32":
		return float64(0)
	}
	if m, member := v.typeModule(name); m != nil {
		if typ, ok := m.types[member]; ok {
			value := v.zero(typ, m.typeEnvs[member])
			if o, ok := value.(*ruleObject); ok {
				o.typ = name
			}
			return value
		}
	}
	return ruleUnknown{"external zero-value type is not bound: " + name}
}
func (v *ruleVM) typeModule(name string) (*ruleModule, string) {
	i := strings.LastIndex(name, ".")
	if i < 0 {
		return nil, name
	}
	return v.program.modules[name[:i]], name[i+1:]
}

func (v *ruleVM) selectValue(value any, name string) any {
	if pointer, ok := value.(rulePointer); ok {
		value = pointer.object
	}
	if x, ok := value.(ruleUnknown); ok {
		ruleFail(x.reason)
	}
	if number, ok := value.(ruleTypedNumber); ok {
		if m, _ := v.typeModule(number.typ); m != nil {
			if f := m.functions[number.typ+"."+name]; f != nil {
				bound := *f
				bound.object = number
				return &bound
			}
		}
	}
	if p, ok := value.(rulePackage); ok {
		if m := v.program.modules[string(p)]; m != nil {
			if _, ok := m.globals[name]; ok {
				return v.lookup(m.envs[m.files[0]], name)
			}
			if f, ok := m.functions[name]; ok {
				return f
			}
			if _, ok := m.types[name]; ok {
				return ruleType{string(p) + "." + name}
			}
		}
		return ruleNative{p, name}
	}
	if o, ok := value.(*ruleObject); ok {
		if f, ok := o.fields[name]; ok {
			return f
		}
		if m, _ := v.typeModule(o.typ); m != nil {
			if f := m.functions[o.typ+"."+name]; f != nil {
				bound := *f
				bound.object = o
				if f.valueReceiver {
					bound.object = copyRuleValue(o)
				}
				return &bound
			}
		}
	}
	if v.host != nil {
		if result, ok := v.host.field(value, name); ok {
			return result
		}
	}
	return ruleNative{value, name}
}
func (v *ruleVM) eval(expr ast.Expr, e *ruleEnv) any {
	v.tick()
	switch x := expr.(type) {
	case *ast.ParenExpr:
		return v.eval(x.X, e)
	case *ast.Ident:
		return v.lookup(e, x.Name)
	case *ast.BasicLit:
		if x.Kind == token.STRING {
			s, err := strconv.Unquote(x.Value)
			if err != nil {
				ruleFail("invalid rule string")
			}
			return s
		}
		if x.Kind == token.INT || x.Kind == token.FLOAT {
			n, err := strconv.ParseFloat(x.Value, 64)
			if err != nil || !isRuleFinite(n) {
				ruleFail("invalid rule number")
			}
			return n
		}
	case *ast.SelectorExpr:
		return v.selectValue(v.eval(x.X, e), x.Sel.Name)
	case *ast.UnaryExpr:
		if x.Op == token.AND {
			return v.address(x.X, e)
		}
		a := v.eval(x.X, e)
		switch x.Op {
		case token.NOT:
			return !ruleBoolean(a)
		case token.ADD:
			if _, ok := a.(*RuleScalar); ok {
				return a
			}
			return ruleNumber(a)
		case token.SUB:
			if _, ok := a.(*RuleScalar); ok {
				return scalarOp("multiply", -1.0, a)
			}
			return -ruleNumber(a)
		}
	case *ast.StarExpr:
		return v.dereference(v.eval(x.X, e))
	case *ast.BinaryExpr:
		a := v.eval(x.X, e)
		if x.Op == token.LAND && !ruleBoolean(a) {
			return false
		}
		if x.Op == token.LOR && ruleBoolean(a) {
			return true
		}
		return ruleBinary(x.Op, a, v.eval(x.Y, e))
	case *ast.FuncLit:
		return &ruleFunction{typ: x.Type, body: x.Body, env: e}
	case *ast.CallExpr:
		if id, ok := x.Fun.(*ast.Ident); ok && id.Name == "make" {
			if len(x.Args) == 0 {
				ruleFail("make without type")
			}
			switch t := x.Args[0].(type) {
			case *ast.ArrayType:
				if len(x.Args) < 2 || len(x.Args) > 3 {
					ruleFail("unsupported make slice")
				}
				n := ruleInteger(v.eval(x.Args[1], e))
				if n < 0 || n > 4096 {
					ruleFail("rule slice size")
				}
				a := &ruleSlice{values: make([]any, n)}
				if v.readOnly && v.scratch != nil {
					v.scratch[a] = true
				}
				for i := range a.values {
					a.values[i] = v.zero(t.Elt, e)
				}
				return a
			case *ast.MapType:
				return &ruleMap{map[any]any{}, t.Value, e}
			}
			ruleFail("unsupported make type")
		}
		fn := v.eval(x.Fun, e)
		args := []any{}
		for i, a := range x.Args {
			value := v.eval(a, e)
			if x.Ellipsis.IsValid() && i == len(x.Args)-1 {
				args = append(args, ruleArray(value)...)
			} else {
				args = append(args, value)
			}
		}
		return v.invoke(fn, args)
	case *ast.IndexExpr:
		a, i := v.eval(x.X, e), v.eval(x.Index, e)
		if m, ok := a.(*ruleMap); ok {
			if r, ok := m.values[ruleMapKey(i)]; ok {
				return r
			}
			return v.zero(m.valueType, m.env)
		}
		items := ruleArray(a)
		idx := ruleInteger(i)
		if idx < 0 || idx >= len(items) {
			ruleFail("rule index outside observed value")
		}
		if array, ok := a.(*ruleSlice); ok && v.readOnly {
			if written, guarded := v.scratchWritten[array]; guarded && !written[idx] {
				ruleFail("modifier amount reads previous cached cell")
			}
		}
		return items[idx]
	case *ast.TypeAssertExpr:
		value := v.eval(x.X, e)
		if !v.matches(value, ruleTypeName(x.Type, e)) {
			ruleFail("rule type assertion failed")
		}
		return value
	case *ast.CompositeLit:
		switch t := x.Type.(type) {
		case *ast.ArrayType:
			n := len(x.Elts)
			if t.Len != nil {
				if _, inferred := t.Len.(*ast.Ellipsis); !inferred {
					n = ruleInteger(v.eval(t.Len, e))
				}
			}
			if n < 0 || n > 4096 {
				ruleFail("rule literal size")
			}
			a := &ruleSlice{values: make([]any, n)}
			for i := range a.values {
				a.values[i] = v.zero(t.Elt, e)
			}
			for i, item := range x.Elts {
				if kv, ok := item.(*ast.KeyValueExpr); ok {
					i = ruleInteger(v.eval(kv.Key, e))
					item = kv.Value
				}
				if i < 0 || i >= n {
					ruleFail("rule literal index")
				}
				a.values[i] = v.evalTypedLiteral(item, t.Elt, e)
			}
			return a
		case *ast.MapType:
			m := &ruleMap{map[any]any{}, t.Value, e}
			for _, item := range x.Elts {
				kv, ok := item.(*ast.KeyValueExpr)
				if !ok {
					ruleFail("unkeyed map")
				}
				m.values[ruleMapKey(v.eval(kv.Key, e))] = v.evalTypedLiteral(kv.Value, t.Value, e)
			}
			return m
		}
		name := ruleTypeName(x.Type, e)
		o, ok := v.zero(x.Type, e).(*ruleObject)
		if !ok {
			o = &ruleObject{typ: name, fields: map[string]any{}}
		}
		o.typ = name
		for _, item := range x.Elts {
			kv, ok := item.(*ast.KeyValueExpr)
			if !ok {
				ruleFail("unkeyed rule struct")
			}
			id, ok := kv.Key.(*ast.Ident)
			if !ok {
				ruleFail("invalid struct key")
			}
			o.fields[id.Name] = v.eval(kv.Value, e)
		}
		return o
	}
	ruleFail(fmt.Sprintf("unsupported source expression %T", expr))
	return nil
}
func (v *ruleVM) matches(value any, name string) bool {
	if p, ok := value.(rulePointer); ok {
		value = p.object
	}
	if u, ok := value.(ruleUnknown); ok {
		ruleFail(u.reason)
	}
	if n, ok := value.(ruleTypedNumber); ok {
		return n.typ == name
	}
	switch name {
	case "any":
		return true
	case "int", "float64", "uint64", "int64":
		_, ok := value.(float64)
		return ok
	case "bool":
		_, ok := value.(bool)
		return ok
	case "string":
		_, ok := value.(string)
		return ok
	}
	if o, ok := value.(*ruleObject); ok {
		if o.typ == name {
			return true
		}
		if o.observed {
			ruleFail("observed interface implementation is unavailable: " + name)
		}
		return false
	}
	if v.host != nil {
		if matched, ok := v.host.field(value, "$implements:"+name); ok {
			return ruleBoolean(matched)
		}
		if typ, ok := v.host.field(value, "$type"); ok {
			if typ == name {
				return true
			}
			ruleFail("observed interface implementation is unavailable: " + name)
		}
	}
	return false
}
func ruleRefsEqual(a, b ruleRef) bool {
	// Event refs may carry immutable target facts that world/query refs do not.
	// A target reference still denotes its stable target key, not its evidence.
	if a.kind == "target" && b.kind == "target" {
		return a.index == b.index && a.typ == b.typ
	}
	return a == b
}

func ruleMapKey(value any) any {
	if number, ok := value.(ruleTypedNumber); ok {
		value = number.value
	}
	switch value.(type) {
	case string, float64, bool:
		return value
	}
	ruleFail("unsupported map key")
	return nil
}
func ruleNumber(a any) float64 {
	if _, ok := a.(rulePieceTier); ok {
		ruleFail("piece count escaped package activation comparison")
	}
	if n, ok := a.(ruleTypedNumber); ok {
		a = n.value
	}
	n, ok := a.(float64)
	if !ok || !isRuleFinite(n) {
		if u, ok := a.(ruleUnknown); ok {
			ruleFail(u.reason)
		}
		ruleFail("source number is not known")
	}
	return n
}
func ruleInteger(a any) int {
	n := ruleNumber(a)
	if math.Trunc(n) != n || math.Abs(n) > 1<<31 {
		ruleFail("source integer outside supported range")
	}
	return int(n)
}
func ruleBoolean(a any) bool {
	n, ok := a.(bool)
	if !ok {
		if u, ok := a.(ruleUnknown); ok {
			ruleFail(u.reason)
		}
		ruleFail("source condition is not known")
	}
	return n
}
func ruleString(a any) string {
	s, ok := a.(string)
	if !ok {
		ruleFail("source string is not known")
	}
	return s
}
func ruleArray(a any) []any {
	if a == nil {
		return nil
	}
	s, ok := a.(*ruleSlice)
	if !ok {
		ruleFail("source array is not known")
	}
	return s.values
}
func isRuleFinite(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }
func ruleBinary(op token.Token, a, b any) any {
	if _, ok := a.(rulePieceTier); ok {
		return pieceTierComparison(op, a, b)
	}
	if _, ok := b.(rulePieceTier); ok {
		return pieceTierComparison(op, a, b)
	}
	if _, ok := a.(*RuleScalar); ok {
		return scalarBinary(op, a, b)
	}
	if _, ok := b.(*RuleScalar); ok {
		return scalarBinary(op, a, b)
	}
	if n, ok := a.(ruleTypedNumber); ok {
		a = n.value
	}
	if n, ok := b.(ruleTypedNumber); ok {
		b = n.value
	}
	if u, ok := a.(ruleUnknown); ok {
		ruleFail(u.reason)
	}
	if u, ok := b.(ruleUnknown); ok {
		ruleFail(u.reason)
	}
	if op == token.EQL || op == token.NEQ {
		var equal bool
		if a == nil || b == nil {
			equal = a == nil && b == nil
		} else {
			switch x := a.(type) {
			case float64:
				equal = x == ruleNumber(b)
			case string:
				equal = x == ruleString(b)
			case bool:
				equal = x == ruleBoolean(b)
			case ruleRef:
				y, ok := b.(ruleRef)
				if !ok {
					ruleFail("incompatible source reference equality")
				}
				equal = ruleRefsEqual(x, y)
			case *ruleCell:
				y, ok := b.(*ruleCell)
				if !ok {
					ruleFail("incompatible source pointer equality")
				}
				equal = x == y
			case rulePointer:
				y, ok := b.(rulePointer)
				if !ok {
					ruleFail("incompatible source pointer equality")
				}
				equal = x.object == y.object
			default:
				ruleFail("unsupported source equality")
			}
		}
		if op == token.NEQ {
			equal = !equal
		}
		return equal
	}
	if op == token.LAND {
		return ruleBoolean(a) && ruleBoolean(b)
	}
	if op == token.LOR {
		return ruleBoolean(a) || ruleBoolean(b)
	}
	if op == token.ADD {
		if x, ok := a.(string); ok {
			return x + ruleString(b)
		}
	}
	x, y := ruleNumber(a), ruleNumber(b)
	var n float64
	switch op {
	case token.ADD:
		n = x + y
	case token.SUB:
		n = x - y
	case token.MUL:
		n = x * y
	case token.QUO:
		ruleFail("division requires retained source numeric types")
	case token.REM:
		n = math.Mod(x, y)
	case token.LSS:
		return x < y
	case token.LEQ:
		return x <= y
	case token.GTR:
		return x > y
	case token.GEQ:
		return x >= y
	default:
		ruleFail("unsupported source numeric operation")
	}
	if !isRuleFinite(n) {
		ruleFail("nonfinite source arithmetic")
	}
	return n
}
