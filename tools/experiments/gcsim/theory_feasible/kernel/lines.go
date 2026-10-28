package theoryprototype

import (
	"math"
	"sort"
)

type lineProposal struct {
	actor, slot, line, stat int
	predicted               float64
}

// ImproveLines searches one-line substitutions with fixed mains. Every absent
// eligible stat is evaluated; gradient ranking affects only evaluation order.
// It accepts the best actual improvement, reoptimizes upgrades, and repeats
// for at most twelve substitutions. Iterations counts accepted substitutions.
// This local neighborhood does not certify a globally best line layout.
func ImproveLines(obj Objective, state State, cfg Config) (Result, error) {
	base, err := Optimize(obj, state, cfg)
	if err != nil {
		return base, err
	}
	c := counter{objective: obj, evaluations: base.Evaluations}
	current := base.State
	value := base.Value
	continuous := base.ContinuousValue
	changes := 0
	stop := "line_change_cap"
	for ; changes < 12; changes++ {
		_, gradient, err := c.evaluate(current, true)
		if err != nil {
			return Result{State: current, Value: value, Evaluations: c.evaluations, Iterations: changes, Stop: "objective_error", ContinuousValue: continuous}, err
		}
		proposals := make([]lineProposal, 0, 400)
		for actor := range current.Lines {
			for slot := range current.Lines[actor] {
				present := [10]bool{}
				for _, stat := range current.Lines[actor][slot] {
					present[stat] = true
				}
				for line, oldStat := range current.Lines[actor][slot] {
					amount := 1 + current.Upgrades[actor][slot][line]
					for stat := range StatKeys {
						if present[stat] || StatKeys[stat] == current.Mains[actor][slot] {
							continue
						}
						proposals = append(proposals, lineProposal{
							actor: actor, slot: slot, line: line, stat: stat,
							predicted: amount * (gradient[actor][stat] - gradient[actor][oldStat]),
						})
					}
				}
			}
		}
		sort.SliceStable(proposals, func(i, j int) bool {
			return proposals[i].predicted > proposals[j].predicted
		})
		best, bestValue := current, value
		for _, change := range proposals {
			candidate := current
			candidate.Lines[change.actor][change.slot][change.line] = change.stat
			candidateValue, _, err := c.evaluate(candidate, false)
			if err != nil {
				return Result{State: current, Value: value, Evaluations: c.evaluations, Iterations: changes, Stop: "objective_error", ContinuousValue: continuous}, err
			}
			if candidateValue > bestValue+1e-12*(1+math.Abs(bestValue)) {
				best, bestValue = candidate, candidateValue
			}
		}
		if best == current {
			stop = "line_stability"
			break
		}
		optimized, err := Optimize(obj, best, cfg)
		c.evaluations += optimized.Evaluations
		if err != nil {
			return Result{State: current, Value: value, Evaluations: c.evaluations, Iterations: changes, Stop: "objective_error", ContinuousValue: continuous}, err
		}
		if optimized.Value >= bestValue {
			current, value = optimized.State, optimized.Value
		} else {
			current, value = best, bestValue
		}
		continuous = math.Max(continuous, optimized.ContinuousValue)
	}
	return Result{State: current, Value: value, Evaluations: c.evaluations, Iterations: changes, Stop: stop, ContinuousValue: continuous}, nil
}
