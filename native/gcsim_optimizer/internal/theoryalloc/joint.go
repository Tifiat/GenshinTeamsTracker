package theoryalloc

import (
	"fmt"
	"math"
)

// jointConfig bounds a local whole-build search under one fixed objective
// (including its fixed set bonus). A zero Actors mask permits all four actors;
// otherwise only selected actors may change mains or lines. Upgrade searches
// still respond to all four actors' gradients.
type jointConfig struct {
	Actors                  [4]bool
	MaxPasses               int // zero defaults to two complete neighborhood passes
	InnerIterations         int // zero defaults to 16 upgrade steps per layout
	MaxMainPairs            int // zero evaluates all goblet/circlet pairs per pass
	MaxLineCandidates       int // zero evaluates all one-line replacements per pass
	DisableIndependentSeeds bool
	DisableSingleMains      bool
	DisableMainPairs        bool
	DisableLines            bool
}

// jointResult counts actual work, including rejected layouts and independent
// starts. Candidate counts are layouts evaluated after a bounded Optimize call;
// eligible counts include layouts skipped by an explicit candidate cap.
// ContinuousValue is the best relaxation score seen, possibly on a different
// layout from the returned feasible quarter-grid State.
type jointResult struct {
	State                State
	Value                float64
	ContinuousValue      float64
	Evaluations          int
	OptimizeCalls        int
	SeedLayouts          int
	SingleMainCandidates int
	MainPairEligible     int
	JointMainCandidates  int
	TruncatedMainPairs   int
	LineEligible         int
	LineCandidates       int
	TruncatedLines       int
	AcceptedMoves        int
	AcceptedSingleMains  int
	AcceptedMainPairs    int
	AcceptedLines        int
	Passes               int
	Stop                 string
}

type jointMainPair struct {
	actor           int
	goblet, circlet string
}

type jointLineChange struct {
	actor, slot, line, stat int
}

type jointWinner struct {
	state State
	value float64
	kind  string
}

// jointOptimize searches legal main/line neighborhoods while Optimize handles
// all actors' upgrades for every admitted layout. No candidate is removed by a
// frozen gradient or its unoptimized score. Main alternatives use a warm start
// plus two independent gradient-seeded line layouts unless disabled. The finite
// neighborhoods, pass limits, and optional candidate caps are heuristic; this
// does not prove a global optimum or a physical artifact roll-tier build.
func jointOptimize(obj Objective, start State, cfg Config, search jointConfig) (jointResult, error) {
	var out jointResult
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	var err error
	cfg, err = normalizedConfig(cfg)
	if err != nil {
		return out, err
	}
	if err := start.Validate(cfg.Budget, false); err != nil {
		return out, err
	}
	if search.MaxPasses < 0 || search.InnerIterations < 0 || search.MaxMainPairs < 0 || search.MaxLineCandidates < 0 {
		return out, fmt.Errorf("negative joint search limit")
	}
	if search.MaxPasses == 0 {
		search.MaxPasses = 2
	}
	if search.InnerIterations == 0 {
		search.InnerIterations = 16
	}
	inner := cfg
	inner.MaxIterations = search.InnerIterations
	selected := search.Actors
	if selected == [4]bool{} {
		selected = [4]bool{true, true, true, true}
	}
	counted := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		out.Evaluations++
		return obj(state, needGradient)
	}
	checked := counter{objective: counted}
	continuousSeen := false
	run := func(candidate State) (Result, error) {
		out.OptimizeCalls++
		r, runErr := Optimize(counted, candidate, inner)
		if runErr == nil && (!continuousSeen || r.ContinuousValue > out.ContinuousValue) {
			out.ContinuousValue = r.ContinuousValue
			continuousSeen = true
		}
		return r, runErr
	}
	finish := func(winner jointWinner, stop string) jointResult {
		out.State, out.Value, out.Stop = winner.state, winner.value, stop
		return out
	}
	first, err := run(start)
	if err != nil {
		out.Stop = "objective_error"
		return out, err
	}
	best := jointWinner{state: first.State, value: first.Value}
	if err := best.state.Validate(cfg.Budget, true); err != nil {
		return finish(best, "invalid_initial_result"), err
	}
	// Seed both line-selection patterns independently of the warm allocation.
	// Only selected actors receive new line layouts; every Optimize call can
	// still rebalance upgrades for the full team.
	if !search.DisableIndependentSeeds {
		_, gradient, gradErr := checked.evaluate(best.state, true)
		if gradErr != nil {
			return finish(best, "objective_error"), gradErr
		}
		seen := map[State]bool{best.state: true}
		for variant := 0; variant < 2; variant++ {
			seed := Seed(best.state.Mains, gradient, variant, cfg.Budget)
			candidate := best.state
			for actor := range selected {
				if selected[actor] {
					candidate.Lines[actor] = seed.Lines[actor]
					candidate.Upgrades[actor] = seed.Upgrades[actor]
				}
			}
			if seen[candidate] {
				continue
			}
			seen[candidate] = true
			out.SeedLayouts++
			r, runErr := run(candidate)
			if runErr != nil {
				return finish(best, "objective_error"), runErr
			}
			if jointBetter(r.Value, best.value) {
				best = jointWinner{state: r.State, value: r.Value, kind: "seed"}
			}
		}
	}
	truncated := false
	for pass := 0; pass < search.MaxPasses; pass++ {
		out.Passes++
		anchor := best
		winner := anchor
		_, gradient, gradErr := checked.evaluate(anchor.state, true)
		if gradErr != nil {
			return finish(best, "objective_error"), gradErr
		}
		admit := func(candidate State, kind string, mainActor int) error {
			r, runErr := run(candidate)
			if runErr != nil {
				return runErr
			}
			candidateBest := r
			if mainActor >= 0 && !search.DisableIndependentSeeds {
				_, candidateGradient, gradientErr := checked.evaluate(candidate, true)
				if gradientErr != nil {
					return gradientErr
				}
				seen := map[State]bool{candidate: true}
				for variant := 0; variant < 2; variant++ {
					seed := Seed(candidate.Mains, candidateGradient, variant, cfg.Budget)
					independent := candidate
					independent.Lines[mainActor] = seed.Lines[mainActor]
					independent.Upgrades[mainActor] = seed.Upgrades[mainActor]
					if seen[independent] {
						continue
					}
					seen[independent] = true
					out.SeedLayouts++
					alternative, altErr := run(independent)
					if altErr != nil {
						return altErr
					}
					if jointBetter(alternative.Value, candidateBest.Value) {
						candidateBest = alternative
					}
				}
			}
			if jointBetter(candidateBest.Value, winner.value) {
				winner = jointWinner{state: candidateBest.State, value: candidateBest.Value, kind: kind}
			}
			return nil
		}
		if !search.DisableSingleMains {
			for actor := range selected {
				if !selected[actor] {
					continue
				}
				for slot := 2; slot < 5; slot++ {
					for _, main := range mainChoices[slot] {
						if main == anchor.state.Mains[actor][slot] {
							continue
						}
						out.SingleMainCandidates++
						candidate := ReplaceMain(anchor.state, actor, slot, main, gradient, cfg.Budget)
						if err := admit(candidate, "single_main", actor); err != nil {
							return finish(best, "objective_error"), err
						}
					}
				}
			}
		}
		if !search.DisableMainPairs {
			pairs := jointMainPairs(anchor.state, selected)
			out.MainPairEligible += len(pairs)
			if search.MaxMainPairs > 0 && len(pairs) > search.MaxMainPairs {
				out.TruncatedMainPairs += len(pairs) - search.MaxMainPairs
				pairs = pairs[:search.MaxMainPairs]
				truncated = true
			}
			for _, pair := range pairs {
				out.JointMainCandidates++
				candidate := ReplaceMain(anchor.state, pair.actor, 3, pair.goblet, gradient, cfg.Budget)
				candidate = ReplaceMain(candidate, pair.actor, 4, pair.circlet, gradient, cfg.Budget)
				if err := admit(candidate, "main_pair", pair.actor); err != nil {
					return finish(best, "objective_error"), err
				}
			}
		}
		if !search.DisableLines {
			lines := jointLineChanges(anchor.state, selected)
			out.LineEligible += len(lines)
			if search.MaxLineCandidates > 0 && len(lines) > search.MaxLineCandidates {
				out.TruncatedLines += len(lines) - search.MaxLineCandidates
				lines = lines[:search.MaxLineCandidates]
				truncated = true
			}
			for _, change := range lines {
				out.LineCandidates++
				candidate := anchor.state
				candidate.Lines[change.actor][change.slot][change.line] = change.stat
				if err := admit(candidate, "line", -1); err != nil {
					return finish(best, "objective_error"), err
				}
			}
		}
		if !jointBetter(winner.value, anchor.value) {
			if truncated {
				return finish(best, "candidate_cap"), nil
			}
			return finish(best, "neighborhood_stable"), nil
		}
		best = winner
		out.AcceptedMoves++
		switch winner.kind {
		case "single_main":
			out.AcceptedSingleMains++
		case "main_pair":
			out.AcceptedMainPairs++
		case "line":
			out.AcceptedLines++
		}
	}
	if truncated {
		return finish(best, "pass_cap_candidate_cap"), nil
	}
	return finish(best, "pass_cap"), nil
}

func jointBetter(value, incumbent float64) bool {
	return value > incumbent+1e-10*(1+math.Abs(incumbent))
}

func jointMainPairs(state State, selected [4]bool) []jointMainPair {
	var perActor [4][]jointMainPair
	depth := 0
	for actor := range selected {
		if !selected[actor] {
			continue
		}
		for _, goblet := range mainChoices[3] {
			if goblet == state.Mains[actor][3] {
				continue
			}
			for _, circlet := range mainChoices[4] {
				if circlet == state.Mains[actor][4] {
					continue
				}
				perActor[actor] = append(perActor[actor], jointMainPair{actor: actor, goblet: goblet, circlet: circlet})
			}
		}
		if len(perActor[actor]) > depth {
			depth = len(perActor[actor])
		}
	}
	ordered := make([]jointMainPair, 0, depth*4)
	for i := 0; i < depth; i++ {
		for actor := range perActor {
			if i < len(perActor[actor]) {
				ordered = append(ordered, perActor[actor][i])
			}
		}
	}
	return ordered
}

func jointLineChanges(state State, selected [4]bool) []jointLineChange {
	var perActor [4][]jointLineChange
	depth := 0
	for actor := range selected {
		if !selected[actor] {
			continue
		}
		for slot := range state.Lines[actor] {
			present := [10]bool{}
			for _, stat := range state.Lines[actor][slot] {
				present[stat] = true
			}
			for line := range state.Lines[actor][slot] {
				for stat := range statKeys {
					if present[stat] || statKeys[stat] == state.Mains[actor][slot] {
						continue
					}
					perActor[actor] = append(perActor[actor], jointLineChange{actor: actor, slot: slot, line: line, stat: stat})
				}
			}
		}
		if len(perActor[actor]) > depth {
			depth = len(perActor[actor])
		}
	}
	ordered := make([]jointLineChange, 0, depth*4)
	for i := 0; i < depth; i++ {
		for actor := range perActor {
			if i < len(perActor[actor]) {
				ordered = append(ordered, perActor[actor][i])
			}
		}
	}
	return ordered
}
