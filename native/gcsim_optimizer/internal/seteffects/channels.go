package seteffects

import (
	"fmt"
	"go/ast"
	"go/constant"
	"go/parser"
	"go/token"
	"strconv"
	"strings"
)

// AttackTagVocabulary follows the installed engine's enum order. Names, tags
// and future reactions are data, not a handwritten reaction-name registry.
func AttackTagVocabulary(source []byte) (map[string]int, error) {
	f, e := parser.ParseFile(token.NewFileSet(), "attack.go", source, 0)
	if e != nil {
		return nil, e
	}
	out := map[string]int{}
	for _, decl := range f.Decls {
		g, ok := decl.(*ast.GenDecl)
		if !ok || g.Tok != token.CONST {
			continue
		}
		matched := false
		for i, spec := range g.Specs {
			v, ok := spec.(*ast.ValueSpec)
			if !ok {
				return nil, fmt.Errorf("invalid attack enum declaration")
			}
			if i == 0 && len(v.Values) == 1 {
				t, ok := v.Type.(*ast.Ident)
				x, xok := v.Values[0].(*ast.Ident)
				matched = ok && xok && t.Name == "AttackTag" && x.Name == "iota"
			}
			if !matched {
				continue
			}
			if len(v.Names) != 1 || i > 0 && len(v.Values) > 0 {
				return nil, fmt.Errorf("unsupported AttackTag enum shape")
			}
			out["github.com/genshinsim/gcsim/pkg/core/attacks."+v.Names[0].Name] = i
		}
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("AttackTag vocabulary missing")
	}
	return out, nil
}

// TermChannelApplicability specializes only Amount-callback attack-tag filters.
// It does not infer uptime from a trigger on some other hit. In particular,
// OnEnemyDamage guards may select the buff's trigger, not its later recipients.
func (d Description) TermChannelApplicability(term Term, attackTag string, vocabulary map[string]int) Truth {
	if !strings.HasPrefix(attackTag, "tag/") {
		return Unknown
	}
	tag, e := strconv.Atoi(strings.TrimPrefix(attackTag, "tag/"))
	if e != nil || tag < 0 {
		return Unknown
	}
	state := Possible
	for _, g := range term.Guards {
		x, ok := d.Conditions[g]
		if !ok {
			state = Unknown
			continue
		}
		v := channelCondition(x, tag, vocabulary)
		if v == Excluded {
			return Excluded
		}
		if v == Unknown {
			state = Unknown
		}
	}
	return state
}

func channelCondition(e Expression, tag int, vocabulary map[string]int) Truth {
	return interpretCondition(e, func(x Expression) constant.Value {
		if x.Kind == "qualified" {
			if n, ok := vocabulary[x.Symbol]; ok {
				return constant.MakeInt64(int64(n))
			}
		}
		if x.Kind == "selector" && x.Symbol == "AttackTag" && len(x.Inputs) == 1 && strings.HasPrefix(x.Inputs[0].Symbol, "amount_attack_info:") {
			return constant.MakeInt64(int64(tag))
		}
		return literalInteger(x)
	})
}

func literalInteger(x Expression) constant.Value {
	if x.Kind == "literal" {
		if _, e := strconv.ParseInt(x.Text, 10, 64); e == nil {
			return constant.MakeFromLiteral(x.Text, token.INT, 0)
		}
	}
	return constant.MakeUnknown()
}

// Three-valued conditions: unsupported operands never become false/zero.
func interpretCondition(e Expression, value func(Expression) constant.Value) Truth {
	if e.Kind == "boolean" {
		if e.Text == "true" {
			return Possible
		}
		if e.Text == "false" {
			return Excluded
		}
	}
	if e.Kind == "unary:!" && len(e.Inputs) == 1 {
		switch interpretCondition(e.Inputs[0], value) {
		case Possible:
			return Excluded
		case Excluded:
			return Possible
		}
		return Unknown
	}
	if len(e.Inputs) != 2 {
		return Unknown
	}
	if e.Kind == "binary:&&" || e.Kind == "binary:||" {
		a, b := interpretCondition(e.Inputs[0], value), interpretCondition(e.Inputs[1], value)
		if e.Kind == "binary:&&" {
			if a == Excluded || b == Excluded {
				return Excluded
			}
			if a == Possible && b == Possible {
				return Possible
			}
		} else {
			if a == Possible || b == Possible {
				return Possible
			}
			if a == Excluded && b == Excluded {
				return Excluded
			}
		}
		return Unknown
	}
	a, b := value(e.Inputs[0]), value(e.Inputs[1])
	if a.Kind() == constant.Unknown || b.Kind() == constant.Unknown {
		return Unknown
	}
	op, ok := map[string]token.Token{"binary:<": token.LSS, "binary:<=": token.LEQ, "binary:>": token.GTR, "binary:>=": token.GEQ, "binary:==": token.EQL, "binary:!=": token.NEQ}[e.Kind]
	if !ok {
		return Unknown
	}
	if constant.Compare(a, op, b) {
		return Possible
	}
	return Excluded
}
