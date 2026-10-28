package theoryalloc

import (
	"fmt"
	"math"
)

// ValidateFull45 checks the publication witness used by the pinned team search:
// twenty mandatory initial rolls and twenty-five upgrades for every actor.
// State.Validate retains its upper-bound semantics for the allocation solver.
func ValidateFull45(state State) error {
	if err := state.Validate(45, true); err != nil {
		return err
	}
	for actor, upgrades := range state.Upgrades {
		sum := 0.0
		for _, slot := range upgrades {
			for _, x := range slot {
				sum += x
			}
		}
		if math.Abs(sum-25) > 1e-7 {
			return fmt.Errorf("actor %d has %g upgrades; full45 requires 25", actor, sum)
		}
	}
	return nil
}
