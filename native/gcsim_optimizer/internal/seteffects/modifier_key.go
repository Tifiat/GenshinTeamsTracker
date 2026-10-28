package seteffects

import "strconv"

// SharedModifierKey is a proposal-grouping hint, not an activation or stacking
// certificate. Only a literal key at the known modifier constructor is read.
// Dynamic per-owner keys and unknown factories remain unresolved.
func SharedModifierKey(r Recipe) string {
	if r.RecipientScope != "team_iteration_member" && r.Effect.Kind != "resistance" {
		return ""
	}
	for _, field := range r.Effect.Fields {
		x := field.Value
		if field.Name != "Base" || x.Kind != "call" || len(x.Inputs) < 2 || x.Inputs[0].Kind != "qualified" || x.Inputs[1].Kind != "literal" {
			continue
		}
		fn := x.Inputs[0].Symbol
		if fn != "github.com/genshinsim/gcsim/pkg/modifier.NewBase" && fn != "github.com/genshinsim/gcsim/pkg/modifier.NewBaseWithHitlag" {
			continue
		}
		key, e := strconv.Unquote(x.Inputs[1].Text)
		if e == nil && key != "" {
			return r.Effect.Kind + ":" + key
		}
	}
	return ""
}
