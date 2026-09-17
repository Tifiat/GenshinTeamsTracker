package seteffects

import (
	"fmt"
	"go/constant"
	"go/token"
	"strconv"
)

// Term is a POSSIBLE source amount under its retained guards, never a promised
// uptime or a complete replacement. Multiple writes/returns are alternatives,
// not contributions to sum. Numerical folding uses source literals only.
type Term struct {
	Coordinate string     `json:"coordinate"`
	Expression Expression `json:"expression"`
	Constant   string     `json:"constant,omitempty"`
	Guards     []string   `json:"guards"`
	At         Location   `json:"at"`
}
type Recipe struct {
	Effect         Effect       `json:"effect"`
	Terms          []Term       `json:"terms"`
	Unresolved     []string     `json:"unresolved"`
	Activation     Reachability `json:"activation"`
	RecipientScope string       `json:"recipient_scope"`
}

// Recipes follows amount callbacks to scalar returns or indexed vector writes.
// It does not erase source control flow, alias uncertainty or mutable stacking.
// This is deliberately separate from setcontext proof production and scoring.
func (d Description) Recipes() []Recipe {
	functions := map[string]Function{}
	for _, f := range d.Functions {
		functions[f.ID] = f
	}
	defs := map[string][]Write{}
	for _, w := range d.Writes {
		if w.Target.Kind == "symbol" {
			defs[w.Target.Symbol] = append(defs[w.Target.Symbol], w)
		}
	}
	term := func(coord string, e Expression, g []string, at Location) Term {
		out := Term{Coordinate: coord, Expression: e, Guards: g, At: at}
		if v := number(e, defs, map[string]bool{}, 0); v.Kind() != constant.Unknown {
			out.Constant = v.ExactString()
		}
		return out
	}
	out := []Recipe{}
	for _, effect := range d.Effects {
		r := Recipe{Effect: effect, Terms: []Term{}, Unresolved: []string{"activation_and_recipient_require_context", "not_replacement_certificate"}, Activation: d.EffectPaths(effect)}
		r.RecipientScope = recipientScope(effect)
		if effect.AmountFunction != "" {
			f, ok := functions[effect.AmountFunction]
			if !ok {
				r.Unresolved = append(r.Unresolved, "amount_function_missing")
			} else {
				for _, ret := range f.Returns {
					if len(ret.Values) != 1 {
						r.Unresolved = append(r.Unresolved, "multi_return_amount")
						continue
					}
					value := ret.Values[0]
					if value.Kind == "symbol" && value.Symbol == "unbound:nil" {
						continue
					}
					found := false
					for _, w := range d.Writes {
						if w.Target.Kind == "index" && len(w.Target.Inputs) == 2 && sameReference(w.Target.Inputs[0], value) {
							coord := w.Target.Inputs[1].Symbol
							if w.Target.Inputs[1].Kind != "qualified" {
								coord = w.Target.Inputs[1].Text
								r.Unresolved = append(r.Unresolved, "dynamic_vector_index")
							}
							g := append(append([]string{}, w.Guards...), ret.Guards...)
							r.Terms = append(r.Terms, term(coord, w.Value, g, w.At))
							found = true
							if w.Operator != "=" && w.Operator != ":=" {
								r.Unresolved = append(r.Unresolved, "mutable_vector_accumulation")
							}
						}
					}
					if !found {
						r.Terms = append(r.Terms, term("scalar_or_unresolved_vector", value, ret.Guards, ret.At))
						if value.Kind == "symbol" || value.Kind == "selector" {
							r.Unresolved = append(r.Unresolved, "scalar_or_vector_lineage_requires_context")
						}
					}
				}
			}
		} else {
			for _, f := range effect.Fields {
				if f.Name == "Value" || f.Name == "FlatDmg" || f.Name == "Mult" {
					r.Terms = append(r.Terms, term(f.Name, f.Value, effect.Guards, effect.At))
				}
			}
			if len(r.Terms) == 0 {
				r.Unresolved = append(r.Unresolved, "effect_payload_requires_resolution")
			}
		}
		out = append(out, r)
	}
	return out
}

func sameReference(a, b Expression) bool {
	if a.Kind != b.Kind {
		return false
	}
	if a.Kind == "symbol" {
		return a.Symbol != "" && a.Symbol == b.Symbol
	}
	if a.Kind == "selector" && a.Symbol == b.Symbol && len(a.Inputs) == 1 && len(b.Inputs) == 1 {
		return sameReference(a.Inputs[0], b.Inputs[0])
	}
	return false
}

func number(e Expression, defs map[string][]Write, active map[string]bool, depth int) constant.Value {
	unknown := constant.MakeUnknown()
	if depth > maxExpressionDepth {
		return unknown
	}
	switch e.Kind {
	case "literal":
		if _, err := strconv.ParseFloat(e.Text, 64); err != nil {
			return unknown
		}
		tok := token.INT
		if stringsContainsFloat(e.Text) {
			tok = token.FLOAT
		}
		return constant.MakeFromLiteral(e.Text, tok, 0)
	case "symbol":
		rows := defs[e.Symbol]
		if len(rows) != 1 || active[e.Symbol] || rows[0].Operator == "++" || rows[0].Operator == "--" {
			return unknown
		}
		switch rows[0].Operator {
		case "=", ":=", "var", "const":
		default:
			return unknown
		}
		active[e.Symbol] = true
		v := number(rows[0].Value, defs, active, depth+1)
		delete(active, e.Symbol)
		return v
	case "unary:+", "unary:-":
		if len(e.Inputs) != 1 {
			return unknown
		}
		op := token.ADD
		if e.Kind == "unary:-" {
			op = token.SUB
		}
		return constant.UnaryOp(op, number(e.Inputs[0], defs, active, depth+1), 0)
	case "binary:+", "binary:-", "binary:*", "binary:/":
		if len(e.Inputs) != 2 {
			return unknown
		}
		a, b := number(e.Inputs[0], defs, active, depth+1), number(e.Inputs[1], defs, active, depth+1)
		if a.Kind() == constant.Unknown || b.Kind() == constant.Unknown {
			return unknown
		}
		op := map[string]token.Token{"binary:+": token.ADD, "binary:-": token.SUB, "binary:*": token.MUL, "binary:/": token.QUO}[e.Kind]
		if op == token.QUO && constant.Sign(b) == 0 {
			return unknown
		}
		if op == token.QUO && a.Kind() == constant.Int && b.Kind() == constant.Int {
			op = token.QUO_ASSIGN
		}
		return constant.BinaryOp(a, op, b)
	}
	return unknown
}
func stringsContainsFloat(s string) bool {
	for _, r := range s {
		if r == '.' || r == 'e' || r == 'E' || r == 'p' || r == 'P' {
			return true
		}
	}
	return false
}

func (d Description) ValidateDiscovery() error {
	if d.ReplacementCertified {
		return fmt.Errorf("source discovery cannot certify replacement")
	}
	ids := map[string]bool{}
	for _, f := range d.Functions {
		if ids[f.ID] {
			return fmt.Errorf("duplicate function")
		}
		ids[f.ID] = true
	}
	for _, e := range d.Edges {
		if !ids[e.From] || !ids[e.To] {
			return fmt.Errorf("dangling callback edge")
		}
	}
	for _, e := range d.Effects {
		if !ids[e.Function] || (e.AmountFunction != "" && !ids[e.AmountFunction]) {
			return fmt.Errorf("dangling effect function")
		}
	}
	return nil
}
