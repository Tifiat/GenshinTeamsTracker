package theoryprototype

import (
	"fmt"
	"math"
)

// QuarterExchangeConfig bounds actual-score transfer repair on a fixed main
// and line layout. Actors limits which actors can transfer upgrades; an empty
// mask selects all four. Every move keeps that actor's total upgrade cost fixed.
type QuarterExchangeConfig struct {
	Budget         float64 // zero defaults to 45
	Actors         [4]bool
	MaxMoves       int // zero defaults to eight accepted transfers
	MaxEvaluations int // zero defaults to 2048 objective evaluations
}

type QuarterExchangeResult struct {
	State         State
	Value         float64
	Evaluations   int
	EligibleMoves int
	TestedMoves   int
	Moves         int
	Passes        int
	Stop          string
}

type quarterMove struct {
	actor, fromSlot, fromLine, toSlot, toLine int
}

// QuarterExchange compares actual objective values for every feasible
// equal-cost quarter transfer in its selected fixed-layout neighborhood. It
// accepts the best observed move each pass and labels an evaluation cap rather
// than claiming local stability after an incomplete scan.
func QuarterExchange(obj Objective, start State, cfg QuarterExchangeConfig) (QuarterExchangeResult, error) {
	var out QuarterExchangeResult
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	cfg.Budget = normalizedBudget(cfg.Budget)
	if err := start.Validate(cfg.Budget, true); err != nil {
		return out, err
	}
	if cfg.MaxMoves < 0 || cfg.MaxEvaluations < 0 {
		return out, fmt.Errorf("negative quarter-exchange limit")
	}
	if cfg.MaxMoves == 0 {
		cfg.MaxMoves = 8
	}
	if cfg.MaxEvaluations == 0 {
		cfg.MaxEvaluations = 2048
	}
	selected := cfg.Actors
	if selected == [4]bool{} {
		selected = [4]bool{true, true, true, true}
	}
	c := counter{objective: obj}
	value, _, err := c.evaluate(start, false)
	if err != nil {
		return out, err
	}
	out.State, out.Value = start, value
	finish := func(stop string) QuarterExchangeResult {
		out.Evaluations, out.Stop = c.evaluations, stop
		return out
	}
	for pass := 0; pass < cfg.MaxMoves; pass++ {
		out.Passes++
		moves := quarterMoves(out.State, selected)
		out.EligibleMoves += len(moves)
		best, bestValue := out.State, out.Value
		for _, move := range moves {
			if c.evaluations >= cfg.MaxEvaluations {
				if quarterBetter(bestValue, out.Value) {
					out.State, out.Value = best, bestValue
					out.Moves++
				}
				return finish("evaluation_cap"), nil
			}
			candidate := out.State
			candidate.Upgrades[move.actor][move.fromSlot][move.fromLine] -= .25
			candidate.Upgrades[move.actor][move.toSlot][move.toLine] += .25
			candidateValue, _, evalErr := c.evaluate(candidate, false)
			out.TestedMoves++
			if evalErr != nil {
				return finish("objective_error"), evalErr
			}
			if quarterBetter(candidateValue, bestValue) {
				best, bestValue = candidate, candidateValue
			}
		}
		if !quarterBetter(bestValue, out.Value) {
			return finish("quarter_stability"), nil
		}
		out.State, out.Value = best, bestValue
		out.Moves++
	}
	return finish("move_cap"), nil
}

func quarterMoves(state State, selected [4]bool) []quarterMove {
	moves := make([]quarterMove, 0, 1600)
	for actor := range selected {
		if !selected[actor] {
			continue
		}
		var slotSums [5]float64
		for slot := range state.Upgrades[actor] {
			for _, u := range state.Upgrades[actor][slot] {
				slotSums[slot] += u
			}
		}
		for fromSlot := range state.Upgrades[actor] {
			for fromLine, u := range state.Upgrades[actor][fromSlot] {
				if u < .25-1e-9 {
					continue
				}
				for toSlot := range state.Upgrades[actor] {
					if toSlot != fromSlot && slotSums[toSlot]+.25 > 5+1e-9 {
						continue
					}
					for toLine := range state.Upgrades[actor][toSlot] {
						if fromSlot == toSlot && fromLine == toLine {
							continue
						}
						moves = append(moves, quarterMove{actor, fromSlot, fromLine, toSlot, toLine})
					}
				}
			}
		}
	}
	return moves
}

func quarterBetter(value, incumbent float64) bool {
	return value > incumbent+1e-12*(1+math.Abs(incumbent))
}

type RollWindowConfig struct {
	MinTotal       int
	MaxTotal       int
	Center         int
	HalfWidth      int // zero defaults to two integer roll units
	MaxExpansions  int // zero defaults to four doublings
	MaxEvaluations int // zero defaults to 256 distinct totals
}

type RollWindowResult struct {
	BestTotal   int
	Value       float64
	Evaluations int
	Expansions  int
	CoveredMin  int // limits of the last fully evaluated window, or -1 if none
	CoveredMax  int
	Stop        string
}

// AdaptiveRollWindow explores integer total-roll counts around Center. A best
// value on either observed boundary doubles the window, within the configured
// limits. An interior stop is only local evidence; an outside peak may remain.
// The callback can perform its own bounded allocation solve for each total.
func AdaptiveRollWindow(score func(int) (float64, error), cfg RollWindowConfig) (RollWindowResult, error) {
	var out RollWindowResult
	if score == nil {
		return out, fmt.Errorf("nil roll-window score")
	}
	if cfg.MinTotal > cfg.MaxTotal || cfg.Center < cfg.MinTotal || cfg.Center > cfg.MaxTotal ||
		cfg.HalfWidth < 0 || cfg.MaxExpansions < 0 || cfg.MaxEvaluations < 0 {
		return out, fmt.Errorf("invalid roll-window domain or limit")
	}
	if cfg.HalfWidth == 0 {
		cfg.HalfWidth = 2
	}
	if cfg.MaxExpansions == 0 {
		cfg.MaxExpansions = 4
	}
	if cfg.MaxEvaluations == 0 {
		cfg.MaxEvaluations = 256
	}
	out.CoveredMin, out.CoveredMax = -1, -1
	values := map[int]float64{}
	halfWidth := cfg.HalfWidth
	for {
		lo := cfg.Center - halfWidth
		hi := cfg.Center + halfWidth
		if lo < cfg.MinTotal {
			lo = cfg.MinTotal
		}
		if hi > cfg.MaxTotal {
			hi = cfg.MaxTotal
		}
		for total := lo; total <= hi; total++ {
			if _, seen := values[total]; seen {
				continue
			}
			if out.Evaluations >= cfg.MaxEvaluations {
				out.Stop = "evaluation_cap"
				return out, nil
			}
			value, err := score(total)
			out.Evaluations++
			if err != nil {
				out.Stop = "score_error"
				return out, err
			}
			if !finite(value) {
				out.Stop = "score_error"
				return out, fmt.Errorf("non-finite roll-window score at %d", total)
			}
			values[total] = value
			if out.Evaluations == 1 || value > out.Value ||
				(value == out.Value && total < out.BestTotal) {
				out.BestTotal, out.Value = total, value
			}
		}
		out.CoveredMin, out.CoveredMax = lo, hi
		bestValue := math.Inf(-1)
		for total := lo; total <= hi; total++ {
			if value := values[total]; value > bestValue {
				bestValue = value
				out.BestTotal = total
			}
		}
		out.Value = bestValue
		if lo == cfg.MinTotal && hi == cfg.MaxTotal {
			out.Stop = "full_domain"
			return out, nil
		}
		if out.BestTotal != lo && out.BestTotal != hi {
			out.Stop = "interior_window"
			return out, nil
		}
		if out.Expansions >= cfg.MaxExpansions {
			out.Stop = "window_cap"
			return out, nil
		}
		nextWidth := halfWidth * 2
		if nextWidth <= halfWidth {
			out.Stop = "window_cap"
			return out, nil
		}
		halfWidth = nextWidth
		out.Expansions++
	}
}

// pureCritPairContinuous is an isolated two-stat expected-value toy. Before
// the rate cap, the derivative with respect to rate units q is
// u*(d+v*T)-r*v-2*u*v*q; beyond the cap, spending on rate only reduces damage.
// This clipped vertex does not represent a universal crit factor for multi-hit
// or stateful formulas.
func pureCritPairContinuous(baseRate, baseDamage, rateBonus, total float64) (rateUnits, value, capUnits float64) {
	const ratePerUnit = .0389
	const damagePerUnit = .0777
	effectiveRate := baseRate + rateBonus
	capUnits = math.Max(0, (1-effectiveRate)/ratePerUnit)
	vertex := total/2 + baseDamage/(2*damagePerUnit) - effectiveRate/(2*ratePerUnit)
	rateUnits = math.Max(0, math.Min(vertex, math.Min(total, capUnits)))
	value = 1 + math.Min(1, effectiveRate+ratePerUnit*rateUnits)*(baseDamage+damagePerUnit*(total-rateUnits))
	return rateUnits, value, capUnits
}
