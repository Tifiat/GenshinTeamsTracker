package seteffects

// Research-only direct construction for the smallest source-backed 2p shape.
// Any ambiguity (including neutral-key overlap) uses the ordinary rule replay.
import (
	"go/ast"
	"go/parser"
	"go/token"
	"sort"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

type hypothesisFastMod struct {
	key, stat string // literal modifier key and engine StatVocabulary label
	value     float64
}

func hypothesisExtractFastLiteral2P(sources map[string][]byte, stats map[string]string) ([]hypothesisFastMod, bool) {
	if _, ok := hypothesisExtractLiteral2P(sources, stats); !ok {
		return nil, false
	}
	names := make([]string, 0, len(sources))
	for name := range sources {
		names = append(names, name)
	}
	sort.Strings(names)
	var body []ast.Stmt
	var imports map[string]string
	seenNew, seenInit := false, false
	count, wearer := "", ""
	for _, name := range names {
		f, err := parser.ParseFile(token.NewFileSet(), name, sources[name], 0)
		if err != nil {
			return nil, false
		}
		aliases := map[string]string{}
		for _, imp := range f.Imports {
			path, err := strconv.Unquote(imp.Path.Value)
			if err != nil {
				return nil, false
			}
			alias := path[strings.LastIndexByte(path, '/')+1:]
			if imp.Name != nil {
				alias = imp.Name.Name
			}
			aliases[alias] = path
		}
		for _, decl := range f.Decls {
			fn, ok := decl.(*ast.FuncDecl)
			if !ok || fn.Body == nil {
				continue
			}
			if fn.Name.Name == "Init" && fn.Recv != nil && hypothesisSetReceiver(fn.Recv) {
				if seenInit || len(fn.Body.List) != 1 {
					return nil, false
				}
				ret, ok := fn.Body.List[0].(*ast.ReturnStmt)
				if !ok || len(ret.Results) != 1 {
					return nil, false
				}
				id, ok := ret.Results[0].(*ast.Ident)
				if !ok || id.Name != "nil" {
					return nil, false
				}
				seenInit = true
			}
			if fn.Name.Name != "NewSet" || fn.Recv != nil {
				continue
			}
			if seenNew {
				return nil, false
			}
			seenNew, imports = true, aliases
			for _, field := range fn.Type.Params.List {
				for _, n := range field.Names {
					if typ, ok := field.Type.(*ast.Ident); ok && typ.Name == "int" {
						if count != "" {
							return nil, false
						}
						count = n.Name
					}
					if ptr, ok := field.Type.(*ast.StarExpr); ok {
						if sel, ok := ptr.X.(*ast.SelectorExpr); ok && sel.Sel.Name == "CharWrapper" {
							if id, ok := sel.X.(*ast.Ident); ok && aliases[id.Name] == "github.com/genshinsim/gcsim/pkg/core/player/character" {
								wearer = n.Name
							}
						}
					}
				}
			}
			if count == "" || wearer == "" {
				return nil, false
			}
			if !hypothesisFastTopLevel(fn.Body.List, count) {
				return nil, false
			}
			for _, stmt := range fn.Body.List {
				branch, ok := stmt.(*ast.IfStmt)
				if !ok {
					continue
				}
				if hypothesisCountAtLeast(branch.Cond, count, 2) {
					body = branch.Body.List
					break
				}
			}
		}
	}
	if !seenNew || !seenInit || len(body) == 0 {
		return nil, false
	}
	attrAlias, modifierAlias, charAlias := "", "", ""
	for alias, path := range imports {
		switch path {
		case "github.com/genshinsim/gcsim/pkg/core/attributes":
			attrAlias = alias
		case "github.com/genshinsim/gcsim/pkg/modifier":
			modifierAlias = alias
		case "github.com/genshinsim/gcsim/pkg/core/player/character":
			charAlias = alias
		}
	}
	if attrAlias == "" || modifierAlias == "" || charAlias == "" {
		return nil, false
	}
	vectors := map[string]map[string]float64{}
	used, keys := map[string]bool{}, map[string]bool{}
	mods := []hypothesisFastMod{}
	for _, stmt := range body {
		switch s := stmt.(type) {
		case *ast.AssignStmt:
			if len(s.Lhs) != 1 || len(s.Rhs) != 1 {
				return nil, false
			}
			if id, ok := s.Lhs[0].(*ast.Ident); ok && s.Tok == token.DEFINE {
				call, ok := s.Rhs[0].(*ast.CallExpr)
				if !ok || !hypothesisVectorMake(call, map[string]bool{attrAlias: true}) || vectors[id.Name] != nil {
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
			label, ok := hypothesisFastStatLabel(idx.Index, attrAlias, stats)
			if !ok {
				return nil, false
			}
			value, ok := hypothesisNumber(s.Rhs[0], 0)
			if !ok || !hypothesisFinite(value) {
				return nil, false
			}
			if _, duplicate := vectors[id.Name][label]; duplicate {
				return nil, false
			}
			vectors[id.Name][label] = value
		case *ast.ExprStmt:
			call, ok := s.X.(*ast.CallExpr)
			if !ok {
				return nil, false
			}
			mod, vector, ok := hypothesisFastRegistration(call, wearer, attrAlias, charAlias, modifierAlias, stats)
			if !ok || vectors[vector] == nil || used[vector] || keys[mod.key] || len(vectors[vector]) != 1 {
				return nil, false
			}
			value, ok := vectors[vector][mod.stat]
			if !ok {
				return nil, false
			}
			mod.value = value
			mods = append(mods, mod)
			used[vector], keys[mod.key] = true, true
		default:
			return nil, false
		}
	}
	return mods, len(mods) > 0 && len(used) == len(vectors)
}

// A no-call assignment is not necessarily inert: it could rebind the owner,
// mutate captured state, or alter Init. The fast path accepts only the local
// Set value's literal construction, count-tier branches, and its final return.
func hypothesisFastTopLevel(stmts []ast.Stmt, count string) bool {
	if len(stmts) < 3 {
		return false
	}
	construct, ok := stmts[0].(*ast.AssignStmt)
	if !ok || construct.Tok != token.DEFINE || len(construct.Lhs) != 1 || len(construct.Rhs) != 1 {
		return false
	}
	local, ok := construct.Lhs[0].(*ast.Ident)
	if !ok || local.Name == count {
		return false
	}
	lit, ok := construct.Rhs[0].(*ast.CompositeLit)
	if !ok {
		return false
	}
	typ, ok := lit.Type.(*ast.Ident)
	if !ok || typ.Name != "Set" {
		return false
	}
	fields := map[string]bool{}
	for _, item := range lit.Elts {
		kv, ok := item.(*ast.KeyValueExpr)
		if !ok {
			return false
		}
		key, ok := kv.Key.(*ast.Ident)
		if !ok || fields[key.Name] {
			return false
		}
		fields[key.Name] = true
		switch value := kv.Value.(type) {
		case *ast.Ident:
			if value.Name == local.Name {
				return false
			}
		case *ast.BasicLit:
		case *ast.UnaryExpr:
			if _, ok := value.X.(*ast.BasicLit); !ok || (value.Op != token.ADD && value.Op != token.SUB) {
				return false
			}
		default:
			return false
		}
	}
	seenTwo := false
	for _, stmt := range stmts[1 : len(stmts)-1] {
		branch, ok := stmt.(*ast.IfStmt)
		if !ok || branch.Init != nil || branch.Else != nil {
			return false
		}
		if hypothesisCountAtLeast(branch.Cond, count, 2) {
			if seenTwo {
				return false
			}
			seenTwo = true
			continue
		}
		if !hypothesisCountAtLeast(branch.Cond, count, 4) {
			return false
		}
	}
	if !seenTwo {
		return false
	}
	ret, ok := stmts[len(stmts)-1].(*ast.ReturnStmt)
	if !ok || len(ret.Results) != 2 {
		return false
	}
	addr, ok := ret.Results[0].(*ast.UnaryExpr)
	if !ok || addr.Op != token.AND {
		return false
	}
	returned, ok := addr.X.(*ast.Ident)
	if !ok || returned.Name != local.Name {
		return false
	}
	err, ok := ret.Results[1].(*ast.Ident)
	return ok && err.Name == "nil"
}

func hypothesisSetReceiver(list *ast.FieldList) bool {
	if len(list.List) != 1 {
		return false
	}
	ptr, ok := list.List[0].Type.(*ast.StarExpr)
	if !ok {
		return false
	}
	id, ok := ptr.X.(*ast.Ident)
	return ok && id.Name == "Set"
}

func hypothesisFastStatLabel(expr ast.Expr, alias string, stats map[string]string) (string, bool) {
	sel, ok := expr.(*ast.SelectorExpr)
	if !ok {
		return "", false
	}
	id, ok := sel.X.(*ast.Ident)
	if !ok || id.Name != alias {
		return "", false
	}
	label, ok := stats["github.com/genshinsim/gcsim/pkg/core/attributes."+sel.Sel.Name]
	if !ok {
		return "", false
	}
	_, supported := OwnerStatKey(label)
	return label, supported
}

func hypothesisFastRegistration(call *ast.CallExpr, wearer, attr, char, modifier string, stats map[string]string) (hypothesisFastMod, string, bool) {
	bad := func() (hypothesisFastMod, string, bool) { return hypothesisFastMod{}, "", false }
	method, ok := call.Fun.(*ast.SelectorExpr)
	if !ok || method.Sel.Name != "AddStatMod" || len(call.Args) != 1 {
		return bad()
	}
	receiver, ok := method.X.(*ast.Ident)
	if !ok || receiver.Name != wearer {
		return bad()
	}
	lit, ok := call.Args[0].(*ast.CompositeLit)
	if !ok {
		return bad()
	}
	typ, ok := lit.Type.(*ast.SelectorExpr)
	if !ok || typ.Sel.Name != "StatMod" {
		return bad()
	}
	alias, ok := typ.X.(*ast.Ident)
	if !ok || alias.Name != char {
		return bad()
	}
	fields := map[string]ast.Expr{}
	for _, entry := range lit.Elts {
		kv, ok := entry.(*ast.KeyValueExpr)
		if !ok {
			return bad()
		}
		field, ok := kv.Key.(*ast.Ident)
		if !ok || (field.Name != "Base" && field.Name != "AffectedStat" && field.Name != "Amount" && field.Name != "Extra") {
			return bad()
		}
		if _, duplicate := fields[field.Name]; duplicate {
			return bad()
		}
		fields[field.Name] = kv.Value
	}
	if len(fields) < 3 {
		return bad()
	}
	if extra, exists := fields["Extra"]; exists {
		id, ok := extra.(*ast.Ident)
		if !ok || id.Name != "false" {
			return bad()
		}
	}
	label, ok := hypothesisFastStatLabel(fields["AffectedStat"], attr, stats)
	if !ok {
		return bad()
	}
	base, ok := fields["Base"].(*ast.CallExpr)
	if !ok || len(base.Args) != 2 {
		return bad()
	}
	constructor, ok := base.Fun.(*ast.SelectorExpr)
	if !ok || constructor.Sel.Name != "NewBase" {
		return bad()
	}
	baseAlias, ok := constructor.X.(*ast.Ident)
	if !ok || baseAlias.Name != modifier {
		return bad()
	}
	keyLit, ok := base.Args[0].(*ast.BasicLit)
	if !ok || keyLit.Kind != token.STRING {
		return bad()
	}
	key, err := strconv.Unquote(keyLit.Value)
	if err != nil || key == "" {
		return bad()
	}
	duration, ok := hypothesisNumber(base.Args[1], 0)
	if !ok || duration != -1 {
		return bad()
	}
	fn, ok := fields["Amount"].(*ast.FuncLit)
	if !ok || len(fn.Body.List) != 1 {
		return bad()
	}
	ret, ok := fn.Body.List[0].(*ast.ReturnStmt)
	if !ok || len(ret.Results) != 1 {
		return bad()
	}
	vector, ok := ret.Results[0].(*ast.Ident)
	if !ok {
		return bad()
	}
	return hypothesisFastMod{key: key, stat: label}, vector.Name, true
}

func (b *NeutralBinding) hypothesisFastLiteralChoice(choice RuleChoice) (NeutralExpressions, bool) {
	if b == nil || b.catalog == nil || choice.Pieces < 2 || choice.Pieces >= 4 {
		return NeutralExpressions{}, false
	}
	mods := b.catalog.hypothesisFast2P[choice.Key]
	if len(mods) == 0 {
		return NeutralExpressions{}, false
	}
	foundRule := false
	for _, set := range b.catalog.Sets {
		if set.Key == choice.Key && set.rule != nil {
			foundRule = true
			break
		}
	}
	if !foundRule {
		return NeutralExpressions{}, false
	}
	// Source replay rejects neutral modifier replacement, even if the amounts
	// happen to agree. A world-wide key check is deliberately over-conservative.
	for _, member := range b.members {
		if member.neutral == nil || member.neutral.World == nil || !member.neutral.World.Complete || member.neutral.Ledger.Truncated || member.neutral.Context.DurationFrames <= 0 {
			return NeutralExpressions{}, false
		}
		for _, state := range member.neutral.World.States {
			for _, old := range state.Modifiers {
				if old.Owner != choice.Owner {
					continue
				}
				for _, mod := range mods {
					if old.Key == mod.key {
						return NeutralExpressions{}, false
					}
				}
			}
		}
		for _, port := range member.ports {
			if !port.query.StateComplete {
				continue
			}
			for _, old := range port.query.State {
				if old.Owner != choice.Owner {
					continue
				}
				for _, mod := range mods {
					if old.Key == mod.key {
						return NeutralExpressions{}, false
					}
				}
			}
		}
	}
	out := NeutralExpressions{raw: make([]float64, len(b.keys)), Effects: make(map[string]*formula.InputExpression, len(b.keys)), Boundaries: []string{}, Uncertainty: []string{}}
	for _, mod := range mods {
		out.footprint.write(ruleModifierKey(choice.Owner, -1, mod.key))
		out.footprint.writeStat(choice.Owner, mod.stat, false)
	}
	knownStats := map[string]bool{}
	for _, stat := range b.catalog.Stats {
		knownStats[stat] = true
	}
	for _, member := range b.members {
		for _, port := range member.ports {
			q := port.query
			if q.Order == 0 || q.Owner < 0 || q.Owner >= len(member.neutral.Context.Characters) {
				return NeutralExpressions{}, false
			}
			if q.Kind == "stat" && q.Owner == choice.Owner {
				if q.Mode != "stat" && q.Mode != "snapshot" && q.Mode != "non_extra_stat" {
					return NeutralExpressions{}, false
				}
				if !knownStats[q.Stat] {
					return NeutralExpressions{}, false
				}
				for _, mod := range mods {
					if q.Stat != mod.stat {
						continue
					}
					if q.StatKeys != nil {
						found := false
						for _, key := range *q.StatKeys {
							if key == mod.stat {
								found = true
								break
							}
						}
						if !found {
							continue
						}
					}
					out.raw[port.dimension] += mod.value
				}
			}
			if q.Kind != "stat" && q.Kind != "attack" && q.Kind != "reaction" && q.Kind != "resistance" && q.Kind != "heal_bonus" && q.Kind != "flat_event" {
				return NeutralExpressions{}, false
			}
			value := out.raw[port.dimension]
			if port.curve != nil {
				transformed, err := port.curve.Evaluate(port.resistance + value)
				if err != nil {
					return NeutralExpressions{}, false
				}
				value = transformed - port.observed
			}
			out.Effects[b.keys[port.dimension]] = &formula.InputExpression{Operation: "constant", Value: value}
		}
	}
	b.stats.HypothesisFastChoices++
	return out, true
}
