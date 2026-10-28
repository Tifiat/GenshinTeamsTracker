package theoryprototype

import (
	"fmt"
	"math"
	"math/bits"
	"sort"
)

// SlotDomain restricts one slot's main and four mandatory substat identities.
// Nil Mains permits every MainChoices option for that slot. Excluded forbids
// substat lines; Required forces their presence. Bits 0..9 index StatKeys.
type SlotDomain struct {
	Mains    []string
	Excluded uint16
	Required uint16
}

type SupportDomain [4][5]SlotDomain

// LinearWeights multiply actual stat amounts: a main uses MainValues and each
// maximum-value substat roll uses Values. Missing map entries have zero weight.
type LinearWeights [4]map[string]float64

// Support45 returns exact linear extrema over the idealized 45-unit witness
// domain, subject to the supplied main/line restrictions. The actor budget is
// an upper bound of 25 optional units, equal to five per slot; it does not
// couple slots at this budget. This is not an in-game roll-tier certificate.
func Support45(weights LinearWeights, domain SupportDomain) (lo, hi float64, err error) {
	_, lo, err = SupportWitness45(weights, domain, false)
	if err != nil {
		return 0, 0, err
	}
	_, hi, err = SupportWitness45(weights, domain, true)
	if err != nil {
		return 0, 0, err
	}
	return lo, hi, nil
}

// SupportWitness45 constructs one quarter-grid state attaining the requested
// linear extremum. For a fixed main, replacing a lower-weight optional line
// with a higher-weight one increases both the mandatory base score and the
// best available optional-upgrade score. Thus required lines plus the highest
// signed-weight remaining lines are sufficient, followed by one simplex
// vertex: zero upgrades or five on the most favorable selected line.
func SupportWitness45(weights LinearWeights, domain SupportDomain, maximize bool) (State, float64, error) {
	var state State
	if err := validateSupportWeights(weights); err != nil {
		return state, 0, err
	}
	sign := 1.0
	if !maximize {
		sign = -1
	}
	var coefficients [4][10]float64
	for actor := range weights {
		for stat, key := range StatKeys {
			coefficient := weights[actor][key] * Values[stat]
			if !finite(coefficient) {
				return state, 0, fmt.Errorf("actor %d stat %q coefficient overflows", actor, key)
			}
			coefficients[actor][stat] = sign * coefficient
		}
	}
	for actor := range domain {
		for slot, restriction := range domain[actor] {
			if err := validateSlotDomain(actor, slot, restriction); err != nil {
				return State{}, 0, err
			}
			mains := restriction.Mains
			if mains == nil {
				mains = MainChoices[slot]
			}
			bestFound := false
			bestScore := math.Inf(-1)
			var bestMain string
			var bestLines [4]int
			bestUpgradeLine := -1
			for _, main := range mains {
				selected := [4]int{}
				count := 0
				eligible := make([]int, 0, 10)
				mainExcludedRequired := false
				for stat, key := range StatKeys {
					bit := uint16(1) << stat
					if key == main {
						if restriction.Required&bit != 0 {
							mainExcludedRequired = true
						}
						continue
					}
					if restriction.Excluded&bit != 0 {
						continue
					}
					if restriction.Required&bit != 0 {
						selected[count] = stat
						count++
					} else {
						eligible = append(eligible, stat)
					}
				}
				if mainExcludedRequired || len(eligible)+count < 4 {
					continue
				}
				sort.Slice(eligible, func(i, j int) bool {
					a, b := eligible[i], eligible[j]
					if coefficients[actor][a] != coefficients[actor][b] {
						return coefficients[actor][a] > coefficients[actor][b]
					}
					return a < b
				})
				for _, stat := range eligible[:4-count] {
					selected[count] = stat
					count++
				}
				mainTerm := sign * weights[actor][main] * MainValues[main]
				if !finite(mainTerm) {
					return State{}, 0, fmt.Errorf("actor %d slot %d main coefficient overflows", actor, slot)
				}
				score := mainTerm
				upgradeLine := -1
				upgradeCoefficient := 0.0
				for line, stat := range selected {
					var addErr error
					score, addErr = supportAdd(score, coefficients[actor][stat])
					if addErr != nil {
						return State{}, 0, addErr
					}
					if coefficients[actor][stat] > upgradeCoefficient {
						upgradeCoefficient, upgradeLine = coefficients[actor][stat], line
					}
				}
				if upgradeLine >= 0 {
					bonus := 5 * upgradeCoefficient
					if !finite(bonus) {
						return State{}, 0, fmt.Errorf("actor %d slot %d upgrade coefficient overflows", actor, slot)
					}
					var addErr error
					score, addErr = supportAdd(score, bonus)
					if addErr != nil {
						return State{}, 0, addErr
					}
				}
				if !bestFound || score > bestScore {
					bestFound, bestScore = true, score
					bestMain, bestLines, bestUpgradeLine = main, selected, upgradeLine
				}
			}
			if !bestFound {
				return State{}, 0, fmt.Errorf("actor %d slot %d has no legal four-line main choice", actor, slot)
			}
			state.Mains[actor][slot] = bestMain
			state.Lines[actor][slot] = bestLines
			if bestUpgradeLine >= 0 {
				state.Upgrades[actor][slot][bestUpgradeLine] = 5
			}
		}
	}
	if err := state.Validate(45, true); err != nil {
		return State{}, 0, err
	}
	value, err := supportValue(state, weights)
	if err != nil {
		return State{}, 0, err
	}
	return state, value, nil
}

func validateSupportWeights(weights LinearWeights) error {
	known := map[string]bool{}
	for _, key := range StatKeys {
		known[key] = true
	}
	for key := range MainValues {
		known[key] = true
	}
	for actor, row := range weights {
		for key, weight := range row {
			if !known[key] {
				return fmt.Errorf("actor %d has unsupported stat key %q", actor, key)
			}
			if !finite(weight) {
				return fmt.Errorf("actor %d stat %q has non-finite weight", actor, key)
			}
		}
	}
	return nil
}

func validateSlotDomain(actor, slot int, d SlotDomain) error {
	const validMask = uint16(1<<10) - 1
	if d.Required & ^validMask != 0 || d.Excluded & ^validMask != 0 {
		return fmt.Errorf("actor %d slot %d has out-of-range stat bit", actor, slot)
	}
	if d.Required&d.Excluded != 0 || bits.OnesCount16(d.Required) > 4 {
		return fmt.Errorf("actor %d slot %d has incompatible required/excluded lines", actor, slot)
	}
	if d.Mains != nil {
		if len(d.Mains) == 0 {
			return fmt.Errorf("actor %d slot %d has no main choices", actor, slot)
		}
		seen := map[string]bool{}
		for _, main := range d.Mains {
			if !validMain(slot, main) || seen[main] {
				return fmt.Errorf("actor %d slot %d has invalid or repeated main %q", actor, slot, main)
			}
			seen[main] = true
		}
	}
	return nil
}

func supportAdd(a, b float64) (float64, error) {
	sum := a + b
	if !finite(sum) {
		return 0, fmt.Errorf("linear support score overflows")
	}
	return sum, nil
}

func supportValue(state State, weights LinearWeights) (float64, error) {
	total := 0.0
	rolls := state.Rolls()
	for actor := range state.Mains {
		for _, main := range state.Mains[actor] {
			term := weights[actor][main] * MainValues[main]
			if !finite(term) {
				return 0, fmt.Errorf("main value overflows")
			}
			var err error
			total, err = supportAdd(total, term)
			if err != nil {
				return 0, err
			}
		}
		for stat, key := range StatKeys {
			term := weights[actor][key] * Values[stat] * rolls[actor][stat]
			if !finite(term) {
				return 0, fmt.Errorf("substat value overflows")
			}
			var err error
			total, err = supportAdd(total, term)
			if err != nil {
				return 0, err
			}
		}
	}
	return total, nil
}
