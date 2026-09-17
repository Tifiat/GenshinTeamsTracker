package seteffects

import (
	"go/constant"
)

type Truth string

const (
	Unknown  Truth = "unknown"
	Possible Truth = "possible"
	Excluded Truth = "excluded"
)

// TierApplicability only specializes the known number of equipped pieces. It
// does NOT interpret event uptime, ownership, mutable stacks or attack filters.
// Missing or mixed-context conditions yield unknown and retain the candidate.
func (d Description) TierApplicability(effect Effect, pieces int) Truth {
	if pieces < 0 || pieces > 5 {
		return Unknown
	}
	paths := d.EffectPaths(effect)
	if paths.Incomplete || len(paths.Paths) == 0 {
		return Unknown
	}
	anyUnknown := false
	for _, p := range paths.Paths {
		state := Possible
		for _, g := range p.Guards {
			if value, ok := d.Conditions[g]; ok {
				v := tierCondition(value, pieces)
				if v == Excluded {
					state = Excluded
					break
				}
				if v == Unknown {
					state = Unknown
				}
			} else {
				state = Unknown
			}
		}
		if state == Possible {
			return Possible
		}
		anyUnknown = anyUnknown || state == Unknown
	}
	if anyUnknown {
		return Unknown
	}
	return Excluded
}

func tierCondition(e Expression, pieces int) Truth {
	return interpretCondition(e, func(x Expression) constant.Value {
		if (x.Kind == "symbol" || x.Kind == "bound_field") && x.Symbol == "set_count" {
			return constant.MakeInt64(int64(pieces))
		}
		return literalInteger(x)
	})
}
