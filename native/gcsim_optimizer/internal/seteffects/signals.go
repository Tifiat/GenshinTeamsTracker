package seteffects

import (
	"fmt"
	"math/big"
)

// StatSignal is one possible owner-stat write, not the sum of a whole set or
// its averaged buff. Signals may share a modifier and represent alternative
// states; consumers must not sum them. A captured formula can cheaply measure
// each signal's influence before the package gets its own real context.
type StatSignal struct {
	EffectID   string  `json:"effect_id"`
	TermIndex  int     `json:"term_index"`
	StatKey    string  `json:"stat_key"`
	Amount     float64 `json:"amount"`
	Activation Truth   `json:"activation"`
}
type SignalCoverage struct {
	Signals           []StatSignal `json:"signals"`
	ExcludedEffects   []string     `json:"excluded_effects"`
	UnresolvedEffects []string     `json:"unresolved_effects"`
}

func (d Description) OwnerStatSignals(pieces int, vocabulary map[string]string) (SignalCoverage, error) {
	out := SignalCoverage{Signals: []StatSignal{}, ExcludedEffects: []string{}, UnresolvedEffects: []string{}}
	for _, r := range d.Recipes() {
		applicability := d.TierApplicability(r.Effect, pieces)
		if applicability == Excluded {
			out.ExcludedEffects = append(out.ExcludedEffects, r.Effect.ID)
			continue
		}
		if r.Effect.Kind != "stat" || r.RecipientScope != "owner" {
			out.UnresolvedEffects = append(out.UnresolvedEffects, r.Effect.ID)
			continue
		}
		complete := true
		for i, term := range r.Terms {
			stat, ok := OwnerStatKey(vocabulary[term.Coordinate])
			if !ok || term.Constant == "" {
				complete = false
				continue
			}
			value, ok := new(big.Rat).SetString(term.Constant)
			if !ok {
				return out, fmt.Errorf("invalid folded source amount")
			}
			amount, _ := value.Float64()
			out.Signals = append(out.Signals, StatSignal{r.Effect.ID, i, stat, amount, applicability})
		}
		if len(r.Terms) == 0 || !complete {
			out.UnresolvedEffects = append(out.UnresolvedEffects, r.Effect.ID)
		}
	}
	return out, nil
}
