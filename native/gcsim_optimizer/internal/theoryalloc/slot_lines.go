package theoryalloc

import "fmt"

// SlotLineConfig bounds the fixed-main, one-line-at-a-time search. Zero
// Passes defaults to two; zero InnerIterations defaults to four upgrade steps.
type SlotLineConfig struct {
	Passes          int
	InnerIterations int
}

type SlotLineResult struct {
	State         State
	Value         float64
	Evaluations   int
	OptimizeCalls int
	Candidates    int
	Accepted      int
	Passes        int
	Stop          string
}

// SlotLines searches one legal line replacement per actor/slot at a time.
// Each candidate is scored after bounded upgrade optimization, without a
// frozen-gradient or immediate-score cutoff. The slot winner becomes the next
// slot's anchor. This finite neighborhood is a heuristic, not a global or
// physical roll-tier certificate.
func SlotLines(obj Objective, start State, cfg Config, search SlotLineConfig) (SlotLineResult, error) {
	var out SlotLineResult
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	var err error
	cfg, err = normalizedConfig(cfg)
	if err != nil {
		return out, err
	}
	if err := start.Validate(cfg.Budget, true); err != nil {
		return out, err
	}
	if search.Passes < 0 || search.Passes > 2 || search.InnerIterations < 0 {
		return out, fmt.Errorf("slot-line search allows at most two passes and nonnegative iterations")
	}
	if search.Passes == 0 {
		search.Passes = 2
	}
	if search.InnerIterations == 0 {
		search.InnerIterations = 4
	}
	inner := cfg
	inner.MaxIterations = search.InnerIterations
	inner.Polish = false
	counted := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		out.Evaluations++
		return obj(state, needGradient)
	}
	initial, _, err := counted(start, false)
	if err != nil {
		return out, err
	}
	if !finite(initial) {
		return out, fmt.Errorf("non-finite initial objective")
	}
	out.State, out.Value = start, initial
	run := func(state State, local Config) (Result, error) {
		out.OptimizeCalls++
		return Optimize(counted, state, local)
	}
	first, err := run(start, inner)
	if err != nil {
		out.Stop = "objective_error"
		return out, err
	}
	if quarterBetter(first.Value, out.Value) {
		out.State, out.Value = first.State, first.Value
	}
	stable := false
	for pass := 0; pass < search.Passes; pass++ {
		out.Passes++
		changed := false
		for actor := range out.State.Lines {
			for slot := range out.State.Lines[actor] {
				anchor := out.State
				bestState, bestValue := anchor, out.Value
				present := [10]bool{}
				for _, stat := range anchor.Lines[actor][slot] {
					present[stat] = true
				}
				for line := range anchor.Lines[actor][slot] {
					for stat := range statKeys {
						if present[stat] || statKeys[stat] == anchor.Mains[actor][slot] {
							continue
						}
						candidate := anchor
						candidate.Lines[actor][slot][line] = stat
						out.Candidates++
						result, runErr := run(candidate, inner)
						if runErr != nil {
							out.Stop = "objective_error"
							return out, runErr
						}
						if quarterBetter(result.Value, bestValue) {
							bestState, bestValue = result.State, result.Value
						}
					}
				}
				if quarterBetter(bestValue, out.Value) {
					out.State, out.Value = bestState, bestValue
					out.Accepted++
					changed = true
				}
			}
		}
		if !changed {
			stable = true
			break
		}
	}
	finalCfg := cfg
	finalCfg.Polish = true
	final, err := run(out.State, finalCfg)
	if err != nil {
		out.Stop = "objective_error"
		return out, err
	}
	if quarterBetter(final.Value, out.Value) {
		out.State, out.Value = final.State, final.Value
	}
	if err := out.State.Validate(cfg.Budget, true); err != nil {
		out.Stop = "invalid_final_state"
		return out, err
	}
	if stable {
		out.Stop = "slot_stable"
	} else {
		out.Stop = "pass_cap"
	}
	return out, nil
}
