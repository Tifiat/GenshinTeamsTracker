package seteffects

import (
	"go/ast"
	"go/token"
	"strings"
)

// Bind only the unique object actually returned from NewSet to methods of its
// concrete local type. Other same-type temporaries are NOT merged. This links
// lifecycle source recipes, not live runtime instances or modifier ownership.
func (d *discovery) bindReturnedReceiver(counts map[*ast.Object]int) {
	var constructor *ast.FuncDecl
	for _, n := range d.functions {
		if f, ok := n.(*ast.FuncDecl); ok && f.Recv == nil && f.Name.Name == "NewSet" {
			constructor = f
		}
	}
	if constructor == nil {
		return
	}
	// Bind by the registered constructor ABI and actual parameter types, not
	// by identifier spelling or by a character/set name.
	params := []*ast.Ident{}
	types := []ast.Expr{}
	for _, field := range constructor.Type.Params.List {
		for _, name := range field.Names {
			params = append(params, name)
			types = append(types, field.Type)
		}
	}
	if len(params) >= 3 {
		if pointer, ok := types[0].(*ast.StarExpr); ok {
			if selector, ok := pointer.X.(*ast.SelectorExpr); ok && selector.Sel.Name == "Core" {
				if alias, ok := selector.X.(*ast.Ident); ok && d.imports[d.at(constructor).File][alias.Name] == "github.com/genshinsim/gcsim/pkg/core" && params[0].Obj != nil && counts[params[0].Obj] == 0 {
					d.objects[params[0].Obj] = "set_core"
				}
			}
		}
		if t, ok := types[2].(*ast.Ident); ok && t.Name == "int" && params[2].Obj != nil && counts[params[2].Obj] == 0 {
			d.objects[params[2].Obj] = "set_count"
		}
		if pointer, ok := types[1].(*ast.StarExpr); ok {
			if selector, ok := pointer.X.(*ast.SelectorExpr); ok && selector.Sel.Name == "CharWrapper" {
				if alias, ok := selector.X.(*ast.Ident); ok && d.imports[d.at(constructor).File][alias.Name] == "github.com/genshinsim/gcsim/pkg/core/player/character" && params[1].Obj != nil && counts[params[1].Obj] == 0 {
					d.objects[params[1].Obj] = "set_owner"
				}
			}
		}
	}
	objects := map[*ast.Object]bool{}
	ast.Inspect(constructor.Body, func(n ast.Node) bool {
		if _, ok := n.(*ast.FuncLit); ok {
			return false
		}
		if ret, ok := n.(*ast.ReturnStmt); ok && len(ret.Results) > 0 {
			value := ret.Results[0]
			if u, ok := value.(*ast.UnaryExpr); ok {
				value = u.X
			}
			if id, ok := value.(*ast.Ident); ok && id.Obj != nil {
				objects[id.Obj] = true
			}
		}
		return true
	})
	if len(objects) != 1 {
		return
	}
	for object := range objects {
		if counts[object] != 1 {
			return
		}
		value := d.objectValue(object)
		c, ok := value.(*ast.CompositeLit)
		if !ok {
			return
		}
		typ := d.receiverType(c.Type)
		if typ == "" {
			return
		}
		key := "set_receiver:" + typ
		d.objects[object] = key
		for _, n := range d.functions {
			if f, ok := n.(*ast.FuncDecl); ok && f.Recv != nil && len(f.Recv.List) == 1 && d.receiverType(f.Recv.List[0].Type) == typ {
				for _, name := range f.Recv.List[0].Names {
					if name.Obj != nil && counts[name.Obj] == 0 {
						d.objects[name.Obj] = key
					}
				}
			}
		}
		for _, item := range c.Elts {
			if kv, ok := item.(*ast.KeyValueExpr); ok {
				field, ok := kv.Key.(*ast.Ident)
				if !ok {
					continue
				}
				value, ok := kv.Value.(*ast.Ident)
				if !ok || value.Obj == nil {
					continue
				}
				role := d.objects[value.Obj]
				if role == "set_core" || role == "set_owner" || role == "set_count" {
					d.fieldRoles[key+"."+field.Name] = role
				}
			}
		}
		// Any later direct assignment invalidates the constructor field alias.
		for _, node := range d.functions {
			ast.Inspect(node, func(n ast.Node) bool {
				// Unknown receiver escapes/aliases must not leave a stale count
				// that could exclude an effect. No general alias interpreter here.
				escapes := func(value ast.Expr) bool {
					if u, ok := value.(*ast.UnaryExpr); ok {
						value = u.X
					}
					id, ok := value.(*ast.Ident)
					return ok && id.Obj != nil && d.objects[id.Obj] == key
				}
				invalidate := func() {
					for field := range d.fieldRoles {
						if strings.HasPrefix(field, key+".") {
							delete(d.fieldRoles, field)
						}
					}
				}
				if call, ok := n.(*ast.CallExpr); ok {
					for _, arg := range call.Args {
						if escapes(arg) {
							invalidate()
						}
					}
				}
				if assignment, ok := n.(*ast.AssignStmt); ok {
					for _, rhs := range assignment.Rhs {
						if escapes(rhs) {
							invalidate()
						}
					}
				}
				if declaration, ok := n.(*ast.ValueSpec); ok {
					for _, value := range declaration.Values {
						if escapes(value) {
							invalidate()
						}
					}
				}
				if address, ok := n.(*ast.UnaryExpr); ok && address.Op == token.AND {
					if field, ok := address.X.(*ast.SelectorExpr); ok && escapes(field.X) {
						delete(d.fieldRoles, key+"."+field.Sel.Name)
					}
				}
				if inc, ok := n.(*ast.IncDecStmt); ok {
					if s, ok := inc.X.(*ast.SelectorExpr); ok {
						if root, ok := s.X.(*ast.Ident); ok && root.Obj != nil {
							delete(d.fieldRoles, d.objects[root.Obj]+"."+s.Sel.Name)
						}
					}
				}
				a, ok := n.(*ast.AssignStmt)
				if !ok {
					return true
				}
				for _, lhs := range a.Lhs {
					if s, ok := lhs.(*ast.SelectorExpr); ok {
						if root, ok := s.X.(*ast.Ident); ok && root.Obj != nil {
							delete(d.fieldRoles, d.objects[root.Obj]+"."+s.Sel.Name)
						}
					}
				}
				return true
			})
		}
	}
}

func (d *discovery) bindTeamRecipients(files []*ast.File, counts map[*ast.Object]int) {
	for _, file := range files {
		ast.Inspect(file, func(n ast.Node) bool {
			r, ok := n.(*ast.RangeStmt)
			if !ok {
				return true
			}
			id, ok := r.Value.(*ast.Ident)
			if !ok || id.Obj == nil || counts[id.Obj] != 0 {
				return true
			}
			call, ok := r.X.(*ast.CallExpr)
			if !ok || len(call.Args) != 0 {
				return true
			}
			method, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || method.Sel.Name != "Chars" {
				return true
			}
			player, ok := method.X.(*ast.SelectorExpr)
			if !ok || player.Sel.Name != "Player" {
				return true
			}
			base := d.expr(player.X, 0)
			if base.Symbol == "set_core" {
				d.objects[id.Obj] = "team_member:" + d.id(r)
			}
			return true
		})
	}
	// A single lexical alias such as `this := x` is common before a queued task.
	// Bounded passes handle short alias chains; mutable aliases remain unknown.
	for pass := 0; pass < 4; pass++ {
		changed := false
		for object, count := range counts {
			if count != 1 || d.objects[object] != "" {
				continue
			}
			id, ok := d.objectValue(object).(*ast.Ident)
			if !ok || id.Obj == nil {
				continue
			}
			role := d.objects[id.Obj]
			if role == "set_owner" || len(role) > 12 && role[:12] == "team_member:" {
				d.objects[object] = role
				changed = true
			}
		}
		if !changed {
			break
		}
	}
}
func (d *discovery) receiverType(n ast.Expr) string {
	if star, ok := n.(*ast.StarExpr); ok {
		n = star.X
	}
	if id, ok := n.(*ast.Ident); ok {
		return d.result.Package + "." + id.Name
	}
	return ""
}

func (d *discovery) objectValue(object *ast.Object) ast.Expr {
	if object == nil {
		return nil
	}
	switch decl := object.Decl.(type) {
	case *ast.AssignStmt:
		if len(decl.Lhs) != len(decl.Rhs) {
			return nil
		}
		for i, lhs := range decl.Lhs {
			if id, ok := lhs.(*ast.Ident); ok && id.Obj == object {
				return decl.Rhs[i]
			}
		}
	case *ast.ValueSpec:
		if len(decl.Names) != len(decl.Values) {
			return nil
		}
		for i, id := range decl.Names {
			if id.Obj == object {
				return decl.Values[i]
			}
		}
	}
	return nil
}
func (d *discovery) composite(n ast.Expr) *ast.CompositeLit {
	if v, ok := n.(*ast.CompositeLit); ok {
		return v
	}
	if ident, ok := n.(*ast.Ident); ok && ident.Obj != nil {
		// A payload variable can be modified after construction. Keep those
		// writes in the discovery graph and do not claim these fields final.
		if value, ok := d.objectValue(ident.Obj).(*ast.CompositeLit); ok {
			return value
		}
	}
	return nil
}
