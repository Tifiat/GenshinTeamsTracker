package theoryalloc

import (
	"fmt"
	"math"
	"sort"
)

// Objective returns a score and, when requested, its gradient with respect to
// total maximum-value roll units for each actor and statKeys coordinate.
type Objective func(State, bool) (float64, [4][10]float64, error)

type Config struct {
	Budget        float64 // zero defaults to 45; otherwise [20,45]
	Method        string  // "spg" (default) or "fixed"
	MaxIterations int     // zero defaults to 80
	GridEachStep  bool    // round every proposal before evaluation
	LineSearch    bool    // monotone Armijo backtracking for SPG
	Polish        bool    // actual-objective quarter-transfer repair at the end
}

type Result struct {
	State           State
	Value           float64
	Evaluations     int
	Iterations      int
	Stop            string
	ContinuousValue float64
}

type counter struct {
	objective   Objective
	evaluations int
}

func (c *counter) evaluate(state State, gradient bool) (float64, [4][10]float64, error) {
	c.evaluations++
	value, g, err := c.objective(state, gradient)
	if err != nil {
		return 0, g, err
	}
	if !finite(value) {
		return 0, g, fmt.Errorf("objective returned non-finite value")
	}
	if gradient {
		for actor := range g {
			for stat, component := range g[actor] {
				if !finite(component) {
					return 0, g, fmt.Errorf("objective gradient actor %d stat %d is non-finite", actor, stat)
				}
			}
		}
	}
	return value, g, nil
}

func normalizedConfig(cfg Config) (Config, error) {
	cfg.Budget = normalizedBudget(cfg.Budget)
	if !finite(cfg.Budget) || cfg.Budget < 20 || cfg.Budget > 45 {
		return cfg, fmt.Errorf("budget must be finite and in [20,45]")
	}
	if cfg.Method == "" {
		cfg.Method = "spg"
	}
	if cfg.Method != "spg" && cfg.Method != "fixed" {
		return cfg, fmt.Errorf("unknown optimization method %q", cfg.Method)
	}
	if cfg.MaxIterations < 0 {
		return cfg, fmt.Errorf("negative iteration limit")
	}
	if cfg.MaxIterations == 0 {
		cfg.MaxIterations = 80
	}
	return cfg, nil
}

// Optimize changes only upgrades while keeping mains and four line identities
// fixed. It searches a continuous relaxation and returns one feasible quarter
// witness, with the pre-rounding best score in ContinuousValue. Stop labels
// describe this local search, never a global optimum.
func Optimize(obj Objective, state State, cfg Config) (Result, error) {
	var result Result
	if obj == nil {
		return result, fmt.Errorf("nil objective")
	}
	var err error
	cfg, err = normalizedConfig(cfg)
	if err != nil {
		return result, err
	}
	if err := state.Validate(cfg.Budget, false); err != nil {
		return result, err
	}
	input := state
	inputOnGrid := state.Validate(cfg.Budget, true) == nil
	c := counter{objective: obj}
	value, gradient, err := c.evaluate(state, true)
	if err != nil {
		return result, err
	}
	inputValue := value
	if cfg.GridEachStep {
		quarter := roundQuarter(state, gradient, cfg.Budget)
		if quarter != state {
			state = quarter
			value, gradient, err = c.evaluate(state, true)
			if err != nil {
				return result, err
			}
		}
	}
	best, bestValue, bestGradient := state, value, gradient
	step := initialStep(state, gradient)
	stop := "iteration_cap"
	iterations := 0
	for ; iterations < cfg.MaxIterations; iterations++ {
		var next State
		var nextValue float64
		accepted := false
		stationary := false
		if cfg.Method == "fixed" {
			next, nextValue, accepted, stationary, err = fixedStep(&c, state, value, gradient, cfg)
		} else {
			next, nextValue, accepted, stationary, err = spectralStep(&c, state, value, gradient, step, cfg)
		}
		if err != nil {
			return Result{State: best, Value: bestValue, Evaluations: c.evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: bestValue}, err
		}
		if !accepted {
			if stationary {
				stop = "stationarity"
			} else if cfg.GridEachStep {
				stop = "grid_stalled"
			} else {
				stop = "step_stalled"
			}
			break
		}
		nextValue, nextGradient, evalErr := c.evaluate(next, true)
		if evalErr != nil {
			return Result{State: best, Value: bestValue, Evaluations: c.evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: bestValue}, evalErr
		}
		if nextValue > bestValue {
			best, bestValue, bestGradient = next, nextValue, nextGradient
		}
		if cfg.Method == "spg" {
			step = spectralScale(state, next, gradient, nextGradient, step)
		}
		state, value, gradient = next, nextValue, nextGradient
	}
	if iterations == cfg.MaxIterations {
		stop = "iteration_cap"
	}
	quarter := roundQuarter(best, bestGradient, cfg.Budget)
	quarterValue := bestValue
	if quarter != best {
		quarterValue, _, err = c.evaluate(quarter, false)
		if err != nil {
			return Result{State: best, Value: bestValue, Evaluations: c.evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: bestValue}, err
		}
	}
	if cfg.Polish {
		quarter, quarterValue, err = polishQuarter(&c, quarter, quarterValue, cfg.Budget)
		if err != nil {
			return Result{State: quarter, Value: quarterValue, Evaluations: c.evaluations, Iterations: iterations, Stop: "objective_error", ContinuousValue: bestValue}, err
		}
	}
	if inputOnGrid && inputValue > quarterValue {
		quarter, quarterValue = input, inputValue
	}
	if err := quarter.Validate(cfg.Budget, true); err != nil {
		return Result{State: quarter, Value: quarterValue, Evaluations: c.evaluations, Iterations: iterations, Stop: "invalid_final_state", ContinuousValue: bestValue}, err
	}
	result = Result{State: quarter, Value: quarterValue, Evaluations: c.evaluations, Iterations: iterations, Stop: stop, ContinuousValue: bestValue}
	return result, nil
}

func initialStep(state State, g [4][10]float64) float64 {
	maxComponent := 0.0
	for actor := range state.Lines {
		for slot := range state.Lines[actor] {
			for _, stat := range state.Lines[actor][slot] {
				maxComponent = math.Max(maxComponent, math.Abs(g[actor][stat]))
			}
		}
	}
	if maxComponent == 0 {
		return 1
	}
	return 1 / maxComponent
}

func proposal(state State, g [4][10]float64, step float64, cfg Config) State {
	next := state
	for actor := range next.Upgrades {
		for slot := range next.Upgrades[actor] {
			for line := range next.Upgrades[actor][slot] {
				stat := next.Lines[actor][slot][line]
				next.Upgrades[actor][slot][line] += step * g[actor][stat]
			}
		}
	}
	projectState(&next, cfg.Budget)
	if cfg.GridEachStep {
		next = roundQuarter(next, g, cfg.Budget)
	}
	return next
}

func difference(state, next State, g [4][10]float64) (norm2, predicted float64) {
	for actor := range state.Upgrades {
		for slot := range state.Upgrades[actor] {
			for line, old := range state.Upgrades[actor][slot] {
				d := next.Upgrades[actor][slot][line] - old
				norm2 += d * d
				predicted += g[actor][state.Lines[actor][slot][line]] * d
			}
		}
	}
	return norm2, predicted
}

func fixedStep(c *counter, state State, value float64, g [4][10]float64, cfg Config) (State, float64, bool, bool, error) {
	normSquared := 0.0
	for actor := range state.Lines {
		for slot := range state.Lines[actor] {
			for _, stat := range state.Lines[actor][slot] {
				component := g[actor][stat]
				normSquared += component * component
			}
		}
	}
	if normSquared == 0 {
		return state, value, false, true, nil
	}
	norm := math.Sqrt(normSquared)
	best, bestValue := state, value
	projectedMovement := 0.0
	for _, length := range [4]float64{.25, 1, 4, 16} {
		candidate := proposal(state, g, length/norm, cfg)
		norm2, predicted := difference(state, candidate, g)
		projectedMovement = math.Max(projectedMovement, norm2)
		if norm2 < 1e-18 {
			continue
		}
		candidateValue, _, err := c.evaluate(candidate, false)
		if err != nil {
			return state, value, false, false, err
		}
		if cfg.LineSearch && candidateValue < value+1e-4*predicted {
			continue
		}
		if candidateValue > bestValue+1e-12*(1+math.Abs(bestValue)) {
			best, bestValue = candidate, candidateValue
		}
	}
	return best, bestValue, best != state, projectedMovement < 1e-14, nil
}

func spectralStep(c *counter, state State, value float64, g [4][10]float64, step float64, cfg Config) (State, float64, bool, bool, error) {
	continuousCfg := cfg
	continuousCfg.GridEachStep = false
	base := proposal(state, g, initialStep(state, g), continuousCfg)
	baseMovement, _ := difference(state, base, g)
	if baseMovement < 1e-14 {
		return state, value, false, true, nil
	}
	limit := 1
	if cfg.LineSearch {
		limit = 24
	}
	for trial := 0; trial < limit; trial++ {
		candidate := proposal(state, g, step, cfg)
		norm2, predicted := difference(state, candidate, g)
		if norm2 < 1e-18 {
			if cfg.GridEachStep {
				step *= 2
				continue
			}
			step *= .5
			continue
		}
		candidateValue, _, err := c.evaluate(candidate, false)
		if err != nil {
			return state, value, false, false, err
		}
		threshold := value + 1e-12*(1+math.Abs(value))
		if cfg.LineSearch {
			threshold = math.Max(threshold, value+1e-4*predicted)
		}
		if candidateValue > threshold {
			return candidate, candidateValue, true, false, nil
		}
		step *= .5
	}
	return state, value, false, false, nil
}

func spectralScale(old, next State, oldG, nextG [4][10]float64, previous float64) float64 {
	ss, sy := 0.0, 0.0
	for actor := range old.Upgrades {
		for slot := range old.Upgrades[actor] {
			for line, u := range old.Upgrades[actor][slot] {
				stat := old.Lines[actor][slot][line]
				d := next.Upgrades[actor][slot][line] - u
				ss += d * d
				sy += d * (nextG[actor][stat] - oldG[actor][stat])
			}
		}
	}
	if ss < 1e-18 {
		return previous
	}
	if math.Abs(sy) < 1e-16 {
		return math.Min(previous*2, 16*initialStep(next, nextG))
	}
	return math.Max(1e-12, math.Min(1e12, ss/math.Abs(sy)))
}

func roundQuarter(state State, g [4][10]float64, budget float64) State {
	quarter := state
	maxActorUnits := int(math.Floor((budget-20)*4 + 1e-9))
	for actor := range quarter.Upgrades {
		original := state.Upgrades[actor]
		originalTotal := 0.0
		used := 0
		slotUsed := [5]int{}
		deficit := [10]float64{}
		for slot := range quarter.Upgrades[actor] {
			for line, u := range quarter.Upgrades[actor][slot] {
				originalTotal += u
				units := int(math.Floor(math.Max(0, u)*4 + 1e-9))
				quarter.Upgrades[actor][slot][line] = float64(units) / 4
				deficit[quarter.Lines[actor][slot][line]] += u - quarter.Upgrades[actor][slot][line]
				used += units
				slotUsed[slot] += units
			}
		}
		target := int(math.Round(originalTotal * 4))
		if target > maxActorUnits {
			target = maxActorUnits
		}
		for used < target {
			bestSlot, bestLine := -1, -1
			bestDeficit := math.Inf(-1)
			bestGradient := math.Inf(-1)
			bestRemainder := math.Inf(-1)
			for slot := range quarter.Lines[actor] {
				if slotUsed[slot] >= 20 {
					continue
				}
				for line, stat := range quarter.Lines[actor][slot] {
					component := g[actor][stat]
					remainder := original[slot][line] - quarter.Upgrades[actor][slot][line]
					if bestSlot < 0 || deficit[stat] > bestDeficit+1e-12 ||
						(math.Abs(deficit[stat]-bestDeficit) <= 1e-12 &&
							(component > bestGradient+1e-12 ||
								(math.Abs(component-bestGradient) <= 1e-12 && remainder > bestRemainder+1e-12))) {
						bestDeficit = deficit[stat]
						bestGradient = component
						bestRemainder = remainder
						bestSlot, bestLine = slot, line
					}
				}
			}
			if bestSlot < 0 {
				break
			}
			quarter.Upgrades[actor][bestSlot][bestLine] += .25
			deficit[quarter.Lines[actor][bestSlot][bestLine]] -= .25
			slotUsed[bestSlot]++
			used++
		}
	}
	return quarter
}

type quarterTransfer struct {
	actor, fromSlot, fromLine, toSlot, toLine int
	predicted                                 float64
}

// polishQuarter searches bounded same-actor quarter transfers and single-unit
// additions/removals. Gradient ranking keeps this repair cheap; actual scores
// decide every accepted move.
func polishQuarter(c *counter, state State, value, budget float64) (State, float64, error) {
	const (
		maxRounds    = 3
		maxProposals = 96
	)
	for round := 0; round < maxRounds; round++ {
		_, gradient, err := c.evaluate(state, true)
		if err != nil {
			return state, value, err
		}
		proposals := make([]quarterTransfer, 0, 1600)
		for actor := range state.Upgrades {
			actorTotal := 0.0
			var slotSums [5]float64
			for slot := range state.Upgrades[actor] {
				for _, u := range state.Upgrades[actor][slot] {
					slotSums[slot] += u
					actorTotal += u
				}
			}
			if actorTotal+.25 <= budget-20+1e-9 {
				for toSlot := range state.Upgrades[actor] {
					if slotSums[toSlot]+.25 > 5+1e-9 {
						continue
					}
					for toLine, stat := range state.Lines[actor][toSlot] {
						proposals = append(proposals, quarterTransfer{
							actor: actor, fromSlot: -1, toSlot: toSlot,
							toLine: toLine, predicted: gradient[actor][stat],
						})
					}
				}
			}
			for fromSlot := range state.Upgrades[actor] {
				for fromLine, from := range state.Upgrades[actor][fromSlot] {
					if from < .25-1e-9 {
						continue
					}
					fromStat := state.Lines[actor][fromSlot][fromLine]
					proposals = append(proposals, quarterTransfer{
						actor: actor, fromSlot: fromSlot, fromLine: fromLine,
						toSlot: -1, predicted: -gradient[actor][fromStat],
					})
					for toSlot := range state.Upgrades[actor] {
						if toSlot != fromSlot && slotSums[toSlot]+.25 > 5+1e-9 {
							continue
						}
						for toLine, toStat := range state.Lines[actor][toSlot] {
							if fromSlot == toSlot && fromLine == toLine || fromStat == toStat {
								continue
							}
							proposals = append(proposals, quarterTransfer{
								actor: actor, fromSlot: fromSlot, fromLine: fromLine,
								toSlot: toSlot, toLine: toLine,
								predicted: gradient[actor][toStat] - gradient[actor][fromStat],
							})
						}
					}
				}
			}
		}
		sort.SliceStable(proposals, func(i, j int) bool { return proposals[i].predicted > proposals[j].predicted })
		if len(proposals) > maxProposals {
			proposals = proposals[:maxProposals]
		}
		best, bestValue := state, value
		for _, move := range proposals {
			candidate := state
			if move.fromSlot >= 0 {
				candidate.Upgrades[move.actor][move.fromSlot][move.fromLine] -= .25
			}
			if move.toSlot >= 0 {
				candidate.Upgrades[move.actor][move.toSlot][move.toLine] += .25
			}
			candidateValue, _, err := c.evaluate(candidate, false)
			if err != nil {
				return state, value, err
			}
			if candidateValue > bestValue+1e-12*(1+math.Abs(bestValue)) {
				best, bestValue = candidate, candidateValue
			}
		}
		if best == state {
			break
		}
		state, value = best, bestValue
	}
	return state, value, state.Validate(budget, true)
}
