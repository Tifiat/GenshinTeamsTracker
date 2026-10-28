package theoryalloc

import (
	"fmt"
	"math"
)

// FastConfig bounds a fixed-bonus whole-build heuristic. Zero Passes means
// two main sweeps and zero InnerIterations means eight SPG steps per layout.
// MainPairs and LinePasses are optional, more expensive neighborhoods.
type FastConfig struct {
	Passes          int
	InnerIterations int
	MainPairs       bool
	LinePasses      int
}

type FastResult struct {
	State                State
	Value                float64
	ContinuousValue      float64
	Evaluations          int
	OptimizeCalls        int
	SeedLayouts          int
	SingleMainCandidates int
	PairCandidates       int
	LineCandidates       int
	AcceptedSingleMains  int
	AcceptedMainPairs    int
	AcceptedLines        int
	MainPasses           int
	Stop                 string
}

// FastWhole performs Gauss-Seidel main sweeps on one fixed-bonus objective.
// Every legal sands/goblet/circlet alternative is compared after bounded
// all-actor upgrade optimization, both warm and with one actor's independently
// reseeded lines. Optional paired-main and line neighborhoods also compare
// optimized feasible witnesses. No finite neighborhood certifies a global
// optimum, and different fixed set bonuses require separate calls.
func FastWhole(obj Objective, start State, cfg Config, search FastConfig) (FastResult, error) {
	var out FastResult
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	var err error
	cfg, err = normalizedConfig(cfg)
	if err != nil {
		return out, err
	}
	if cfg.Method != "spg" {
		return out, fmt.Errorf("fast whole-build search requires spg")
	}
	if err := start.Validate(cfg.Budget, true); err != nil {
		return out, err
	}
	if search.Passes < 0 || search.Passes > 2 || search.InnerIterations < 0 || search.LinePasses < 0 || search.LinePasses > 2 {
		return out, fmt.Errorf("fast search permits at most two main and line passes")
	}
	if search.Passes == 0 {
		search.Passes = 2
	}
	if search.InnerIterations == 0 {
		search.InnerIterations = 8
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
	out.State, out.Value, out.ContinuousValue = start, initial, initial
	run := func(state State, local Config) (Result, error) {
		out.OptimizeCalls++
		r, runErr := Optimize(counted, state, local)
		if runErr == nil {
			out.ContinuousValue = math.Max(out.ContinuousValue, r.ContinuousValue)
		}
		return r, runErr
	}
	initialRun, err := run(start, inner)
	if err != nil {
		out.Stop = "objective_error"
		return out, err
	}
	if quarterBetter(initialRun.Value, out.Value) {
		out.State, out.Value = initialRun.State, initialRun.Value
	}
	_, gradient, err := counted(out.State, true)
	if err != nil {
		out.Stop = "objective_error"
		return out, err
	}
	seed := Seed(out.State.Mains, gradient, 0, cfg.Budget)
	if seed != out.State {
		out.SeedLayouts++
		r, runErr := run(seed, inner)
		if runErr != nil {
			out.Stop = "objective_error"
			return out, runErr
		}
		if quarterBetter(r.Value, out.Value) {
			out.State, out.Value = r.State, r.Value
		}
	}
	mainStable := false
	for pass := 0; pass < search.Passes; pass++ {
		out.MainPasses++
		changed := false
		for actor := range out.State.Mains {
			for slot := 2; slot < 5; slot++ {
				anchor := out.State
				bestState, bestValue := anchor, out.Value
				_, anchorGradient, gradErr := counted(anchor, true)
				if gradErr != nil {
					out.Stop = "objective_error"
					return out, gradErr
				}
				for _, main := range mainChoices[slot] {
					if main == anchor.Mains[actor][slot] {
						continue
					}
					out.SingleMainCandidates++
					candidate := ReplaceMain(anchor, actor, slot, main, anchorGradient, cfg.Budget)
					warm, runErr := run(candidate, inner)
					if runErr != nil {
						out.Stop = "objective_error"
						return out, runErr
					}
					candidateState, candidateValue := warm.State, warm.Value
					_, candidateGradient, gradErr := counted(warm.State, true)
					if gradErr != nil {
						out.Stop = "objective_error"
						return out, gradErr
					}
					independent := Seed(warm.State.Mains, candidateGradient, 0, cfg.Budget)
					reseeded := warm.State
					reseeded.Lines[actor] = independent.Lines[actor]
					reseeded.Upgrades[actor] = independent.Upgrades[actor]
					if reseeded != warm.State {
						out.SeedLayouts++
						alternative, altErr := run(reseeded, inner)
						if altErr != nil {
							out.Stop = "objective_error"
							return out, altErr
						}
						if quarterBetter(alternative.Value, candidateValue) {
							candidateState, candidateValue = alternative.State, alternative.Value
						}
					}
					if quarterBetter(candidateValue, bestValue) {
						bestState, bestValue = candidateState, candidateValue
					}
				}
				if quarterBetter(bestValue, out.Value) {
					out.State, out.Value = bestState, bestValue
					out.AcceptedSingleMains++
					changed = true
				}
			}
		}
		if !changed {
			mainStable = true
			break
		}
	}
	if search.MainPairs {
		pairCfg := inner
		pairCfg.MaxIterations = 4
		for actor := range out.State.Mains {
			var actors [4]bool
			actors[actor] = true
			pair, pairErr := jointOptimize(counted, out.State, pairCfg, jointConfig{
				Actors: actors, MaxPasses: 1, InnerIterations: 4,
				DisableIndependentSeeds: true, DisableSingleMains: true, DisableLines: true,
			})
			if pairErr != nil {
				out.Stop = "objective_error"
				return out, pairErr
			}
			out.OptimizeCalls += pair.OptimizeCalls
			out.PairCandidates += pair.JointMainCandidates
			out.ContinuousValue = math.Max(out.ContinuousValue, pair.ContinuousValue)
			if quarterBetter(pair.Value, out.Value) {
				out.State, out.Value = pair.State, pair.Value
				out.AcceptedMainPairs += pair.AcceptedMainPairs
			}
		}
	}
	if search.LinePasses > 0 {
		lineIterations := search.InnerIterations
		if lineIterations < 4 {
			lineIterations = 4
		}
		if lineIterations > 8 {
			lineIterations = 8
		}
		lines, lineErr := jointOptimize(counted, out.State, inner, jointConfig{
			MaxPasses: search.LinePasses, InnerIterations: lineIterations,
			DisableIndependentSeeds: true, DisableSingleMains: true, DisableMainPairs: true,
		})
		if lineErr != nil {
			out.Stop = "objective_error"
			return out, lineErr
		}
		out.OptimizeCalls += lines.OptimizeCalls
		out.LineCandidates += lines.LineCandidates
		out.ContinuousValue = math.Max(out.ContinuousValue, lines.ContinuousValue)
		if quarterBetter(lines.Value, out.Value) {
			out.State, out.Value = lines.State, lines.Value
			out.AcceptedLines += lines.AcceptedLines
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
	if mainStable {
		out.Stop = "main_stable_bounded_neighborhood"
	} else {
		out.Stop = "main_pass_cap_bounded_neighborhood"
	}
	return out, nil
}
