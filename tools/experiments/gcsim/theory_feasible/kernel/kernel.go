// Package theoryprototype searches idealized legal artifact allocations. A
// feasible state is a quarter-unit witness, not a physical roll-tier build.
package theoryprototype

import (
	"fmt"
	"math"
	"sort"
)

// StatKeys and Values use the native theory solver's substat keys and maximum
// roll values in alphabetical order. Objective gradients are in roll units,
// before multiplying by Values.
var StatKeys = [10]string{
	"atk", "atk_percent", "crit_damage", "crit_rate", "def",
	"def_percent", "em", "energy_recharge", "hp", "hp_percent",
}

var Values = [10]float64{
	19.45, .0583, .0777, .0389, 23.15,
	.0729, 23.31, .0648, 298.75, .0583,
}

var MainValues = map[string]float64{
	"hp": 4780, "atk": 311, "hp_percent": .466, "atk_percent": .466,
	"def_percent": .583, "em": 186.5, "energy_recharge": .518,
	"crit_rate": .311, "crit_damage": .622, "pyro_damage_bonus": .466,
	"hydro_damage_bonus": .466, "electro_damage_bonus": .466,
	"cryo_damage_bonus": .466, "anemo_damage_bonus": .466,
	"geo_damage_bonus": .466, "dendro_damage_bonus": .466,
	"physical_damage_bonus": .583, "healing_bonus": .359,
}

// MainChoices are flower, plume, sands, goblet, and circlet, respectively.
var MainChoices = [5][]string{
	{"hp"},
	{"atk"},
	{"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
	{"anemo_damage_bonus", "atk_percent", "cryo_damage_bonus", "def_percent", "dendro_damage_bonus", "electro_damage_bonus", "em", "geo_damage_bonus", "hp_percent", "hydro_damage_bonus", "physical_damage_bonus", "pyro_damage_bonus"},
	{"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
}

// Each slot has four distinct substat lines. Every line starts with one
// maximum-value roll, and Upgrades are additional nonnegative roll units.
type State struct {
	Mains    [4][5]string
	Lines    [4][5][4]int
	Upgrades [4][5][4]float64
}

func (s State) Clone() State { return s }

func (s State) Rolls() [4][10]float64 {
	var rolls [4][10]float64
	for actor := range s.Lines {
		for slot := range s.Lines[actor] {
			for line, stat := range s.Lines[actor][slot] {
				if stat >= 0 && stat < len(StatKeys) {
					rolls[actor][stat] += 1 + s.Upgrades[actor][slot][line]
				}
			}
		}
	}
	return rolls
}

// Validate checks the idealized feasible domain. Grid requires upgrades on the
// quarter-unit lattice; base line rolls are always one unit each. Budget must
// be in [20,45]. It is an upper bound, so unprofitable upgrades may stay unused.
func (s State) Validate(budget float64, grid bool) error {
	if !finite(budget) || budget < 20 || budget > 45 {
		return fmt.Errorf("budget must be finite and in [20,45]")
	}
	for actor := range s.Mains {
		actorExtra := 0.0
		for slot := range s.Mains[actor] {
			main := s.Mains[actor][slot]
			if !validMain(slot, main) {
				return fmt.Errorf("actor %d slot %d has illegal main %q", actor, slot, main)
			}
			seen := [10]bool{}
			slotExtra := 0.0
			for line, stat := range s.Lines[actor][slot] {
				if stat < 0 || stat >= len(StatKeys) {
					return fmt.Errorf("actor %d slot %d line %d has invalid stat index %d", actor, slot, line, stat)
				}
				if seen[stat] || StatKeys[stat] == main {
					return fmt.Errorf("actor %d slot %d has duplicate or main-matching line %q", actor, slot, StatKeys[stat])
				}
				seen[stat] = true
				u := s.Upgrades[actor][slot][line]
				if !finite(u) || u < -1e-9 {
					return fmt.Errorf("actor %d slot %d line %d has invalid upgrade %g", actor, slot, line, u)
				}
				if grid && math.Abs(u*4-math.Round(u*4)) > 1e-8 {
					return fmt.Errorf("actor %d slot %d line %d is off the quarter grid", actor, slot, line)
				}
				slotExtra += u
			}
			if slotExtra > 5+1e-8 {
				return fmt.Errorf("actor %d slot %d exceeds five upgrades", actor, slot)
			}
			actorExtra += slotExtra
		}
		if actorExtra > budget-20+1e-8 {
			return fmt.Errorf("actor %d exceeds budget %g", actor, budget)
		}
	}
	return nil
}

func finite(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }

func validMain(slot int, main string) bool {
	if slot < 0 || slot >= len(MainChoices) {
		return false
	}
	for _, choice := range MainChoices[slot] {
		if choice == main {
			return true
		}
	}
	return false
}

func normalizedBudget(budget float64) float64 {
	// Zero is a documented shorthand for the normal 45-roll theory budget.
	if budget == 0 {
		return 45
	}
	return budget
}

// Seed fixes the given legal mains and selects four eligible lines per slot.
// Variant zero takes the highest-gradient lines and spreads upgrades evenly;
// variant one balances line diversity within each actor and spends positive
// gradient upgrades greedily. Neither variant searches main choices.
func Seed(mains [4][5]string, gradient [4][10]float64, variant int, budget float64) State {
	budget = normalizedBudget(budget)
	state := State{Mains: mains}
	for actor := range mains {
		used := [10]int{}
		for slot := range mains[actor] {
			candidates := make([]int, 0, len(StatKeys))
			for stat := range StatKeys {
				if StatKeys[stat] != mains[actor][slot] {
					candidates = append(candidates, stat)
				}
			}
			sort.SliceStable(candidates, func(i, j int) bool {
				a, b := candidates[i], candidates[j]
				if variant == 1 && used[a] != used[b] {
					return used[a] < used[b]
				}
				if gradient[actor][a] != gradient[actor][b] {
					return gradient[actor][a] > gradient[actor][b]
				}
				return a < b
			})
			for line := range state.Lines[actor][slot] {
				state.Lines[actor][slot][line] = candidates[line]
				used[candidates[line]]++
			}
		}
		extra := math.Max(0, math.Min(25, budget-20))
		if variant != 1 {
			for slot := range state.Upgrades[actor] {
				for line := range state.Upgrades[actor][slot] {
					state.Upgrades[actor][slot][line] = extra / 20
				}
			}
			continue
		}
		type coordinate struct{ slot, line, stat int }
		coords := make([]coordinate, 0, 20)
		for slot := range state.Lines[actor] {
			for line, stat := range state.Lines[actor][slot] {
				coords = append(coords, coordinate{slot, line, stat})
			}
		}
		sort.SliceStable(coords, func(i, j int) bool {
			a, b := coords[i], coords[j]
			if gradient[actor][a.stat] != gradient[actor][b.stat] {
				return gradient[actor][a.stat] > gradient[actor][b.stat]
			}
			if a.slot != b.slot {
				return a.slot < b.slot
			}
			return a.line < b.line
		})
		for _, c := range coords {
			if extra <= 0 || gradient[actor][c.stat] <= 0 {
				break
			}
			slotExtra := 0.0
			for _, u := range state.Upgrades[actor][c.slot] {
				slotExtra += u
			}
			allocation := math.Min(extra, 5-slotExtra)
			state.Upgrades[actor][c.slot][c.line] = allocation
			extra -= allocation
		}
	}
	return state
}

// ReplaceMain changes one legal main, repairs any line that now matches it,
// and projects upgrades back into the slot and actor budget constraints.
// Invalid actor, slot, or main requests return the original state unchanged.
func ReplaceMain(state State, actor, slot int, main string, gradient [4][10]float64, budget float64) State {
	if actor < 0 || actor >= 4 || !validMain(slot, main) {
		return state
	}
	state.Mains[actor][slot] = main
	used := [10]bool{}
	for _, stat := range state.Lines[actor][slot] {
		if stat >= 0 && stat < len(StatKeys) && StatKeys[stat] != main {
			used[stat] = true
		}
	}
	for line, stat := range state.Lines[actor][slot] {
		if stat >= 0 && stat < len(StatKeys) && StatKeys[stat] != main {
			continue
		}
		best := -1
		for candidate := range StatKeys {
			if StatKeys[candidate] == main || used[candidate] {
				continue
			}
			if best < 0 || gradient[actor][candidate] > gradient[actor][best] {
				best = candidate
			}
		}
		if best >= 0 {
			state.Lines[actor][slot][line] = best
			used[best] = true
		}
	}
	projectState(&state, normalizedBudget(budget))
	return state
}

// projectState is the exact Euclidean projection for each actor's upgrade
// coordinates onto x>=0, each slot sum<=5, and the actor sum<=budget-20.
func projectState(state *State, budget float64) {
	cap := math.Max(0, math.Min(25, budget-20))
	for actor := range state.Upgrades {
		v := state.Upgrades[actor]
		state.Upgrades[actor] = projectActor(v, cap)
	}
}

func projectActor(v [5][4]float64, cap float64) [5][4]float64 {
	if cap <= 0 {
		return [5][4]float64{}
	}
	projectAt := func(lambda float64) ([5][4]float64, float64) {
		var out [5][4]float64
		total := 0.0
		for slot := range v {
			shifted := v[slot]
			for line := range shifted {
				shifted[line] -= lambda
			}
			out[slot] = projectSlot(shifted)
			for _, u := range out[slot] {
				total += u
			}
		}
		return out, total
	}
	out, total := projectAt(0)
	if total <= cap+1e-12 {
		return out
	}
	hi := 0.0
	for slot := range v {
		for _, u := range v[slot] {
			if u > hi {
				hi = u
			}
		}
	}
	lo := 0.0
	for i := 0; i < 80; i++ {
		mid := (lo + hi) / 2
		_, total = projectAt(mid)
		if total > cap {
			lo = mid
		} else {
			hi = mid
		}
	}
	out, _ = projectAt(hi)
	return out
}

func projectSlot(v [4]float64) [4]float64 {
	out := v
	total := 0.0
	for i := range out {
		out[i] = math.Max(0, out[i])
		total += out[i]
	}
	if total <= 5 {
		return out
	}
	sorted := v
	sort.Slice(sorted[:], func(i, j int) bool { return sorted[i] > sorted[j] })
	prefix := 0.0
	theta := 0.0
	for i, value := range sorted {
		prefix += value
		candidate := (prefix - 5) / float64(i+1)
		if value > candidate {
			theta = candidate
		}
	}
	for i := range out {
		out[i] = math.Max(0, v[i]-theta)
	}
	return out
}
