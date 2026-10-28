// Package theoryalloc in the disposable target adds a bounded comparison
// harness around the frozen production allocation procedures. Keep this file
// out of the production source tree.
package theoryalloc

import (
	"context"
	"fmt"
)

const (
	// These bounds mirror the Deep bundle's SlotLines and final Optimize
	// settings. Main candidates use the bundle's six-step inner allocation.
	constrainedBudget           = 45.0
	constrainedLineIterations   = 40
	constrainedLineInner        = 4
	constrainedFinalIterations = 60
	constrainedMainInner        = 6
	constrainedLinePasses       = 1
	constrainedMainSweeps       = 2
	// ConstrainedStartCount keeps the independent-start count equal by case.
	ConstrainedStartCount       = 3
)

// ConstrainedStart is one of the three equally budgeted independent starts.
// State is the actual feasible seed; later fields retain the same start's
// fixed-main checkpoint and bounded-search result.
type ConstrainedStart struct {
	Variant                     int
	State                       State
	InitialValue                float64
	FixedMainsState             State
	FixedMainsValue             float64
	FinalState                  State
	FinalValue                  float64
	Variant1FullBudgetFallback  bool
}

// ConstrainedWork reports the complete offline objective and search work.
// SlotLineReportedAccepts is the inner SlotLines count; a returned underfilled
// state is rejected by this wrapper and counted separately.
type ConstrainedWork struct {
	ObjectiveCalls          int
	OptimizeCalls           int
	SlotLineCalls           int
	SlotLineCandidates      int
	SlotLineReportedAccepts int
	MainSweeps              int
	MainCandidates          int
	AcceptedMainMoves       int
	RejectedNonFull45       int
	FullBudgetFallbacks     int
}

// ConstrainedResult separates the best result after the first fixed-main
// stage from the final result after any permitted main sweeps. BaselineValue
// scores the saved witness for reference only; it is never a warm start.
type ConstrainedResult struct {
	State                    State
	Value                    float64
	BaselineValue            float64
	DeltaFromBaseline        float64
	FixedMainsState          State
	FixedMainsValue          float64
	FixedMainsDelta          float64
	Starts                   []ConstrainedStart
	Work                     ConstrainedWork
	Stop                     string
}

type constrainedRunner struct {
	ctx   context.Context
	obj   Objective
	work  ConstrainedWork
}

func (r *constrainedRunner) evaluate(state State, gradient bool) (float64, [4][10]float64, error) {
	var zero [4][10]float64
	if err := r.ctx.Err(); err != nil {
		return 0, zero, err
	}
	r.work.ObjectiveCalls++
	value, g, err := r.obj(state, gradient)
	if err != nil {
		if ctxErr := r.ctx.Err(); ctxErr != nil {
			return 0, zero, ctxErr
		}
		return 0, g, err
	}
	if err := r.ctx.Err(); err != nil {
		return 0, zero, err
	}
	if !finite(value) {
		return 0, zero, fmt.Errorf("objective returned non-finite value")
	}
	if gradient {
		for actor := range g {
			for stat, component := range g[actor] {
				if !finite(component) {
					return 0, zero, fmt.Errorf("objective gradient actor %d stat %d is non-finite", actor, stat)
				}
			}
		}
	}
	return value, g, nil
}

func (r *constrainedRunner) optimize(state State, iterations int, polish bool) (Result, error) {
	if err := r.ctx.Err(); err != nil {
		return Result{}, err
	}
	r.work.OptimizeCalls++
	return Optimize(r.evaluate, state, Config{
		Budget: constrainedBudget, Method: "spg", MaxIterations: iterations,
		LineSearch: true, Polish: polish,
	})
}

func (r *constrainedRunner) lineStage(state State, value float64) (State, float64, error) {
	if err := r.ctx.Err(); err != nil {
		return state, value, err
	}
	r.work.SlotLineCalls++
	result, err := SlotLines(r.evaluate, state, Config{
		Budget: constrainedBudget, Method: "spg", MaxIterations: constrainedLineIterations,
		LineSearch: true,
	}, SlotLineConfig{Passes: constrainedLinePasses, InnerIterations: constrainedLineInner})
	r.work.OptimizeCalls += result.OptimizeCalls
	r.work.SlotLineCandidates += result.Candidates
	r.work.SlotLineReportedAccepts += result.Accepted
	if err != nil {
		return state, value, err
	}
	if err := r.ctx.Err(); err != nil {
		return state, value, err
	}
	if err := ValidateFull45(result.State); err != nil {
		r.work.RejectedNonFull45++
		return state, value, nil
	}
	if quarterBetter(result.Value, value) {
		return result.State, result.Value, nil
	}
	return state, value, nil
}

// RunConstrained searches one capture-free case at equal full45 investment.
// The objective callback is the caller's already-prepared formula objective;
// this wrapper does not capture or call an engine. mains defines the starting
// mains; unlocked permits only those slots to change, using the allocator's
// existing legal main choices. The saved baseline is scored but never supplied
// as a search start, so one case cannot inherit a warm-start advantage. Context
// is checked at objective boundaries and between stages; callers keep their
// original shared deadline and may also close over ctx in cancellable work.
func RunConstrained(ctx context.Context, obj Objective, baseline State, mains [4][5]string, unlocked [4][5]bool) (out ConstrainedResult, resultErr error) {
	var runner *constrainedRunner
	defer func() {
		if runner != nil {
			out.Work = runner.work
		}
	}()
	if ctx == nil {
		return out, fmt.Errorf("nil context")
	}
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	if err := ctx.Err(); err != nil {
		return out, err
	}
	if err := ValidateFull45(baseline); err != nil {
		return out, fmt.Errorf("saved baseline is not a full45 witness: %w", err)
	}
	if err := validateConstrainedPolicy(mains, unlocked); err != nil {
		return out, err
	}
	runner = &constrainedRunner{ctx: ctx, obj: obj}
	baselineValue, _, err := runner.evaluate(baseline, false)
	if err != nil {
		return out, err
	}
	out.BaselineValue = baselineValue

	canonical := Seed(mains, [4][10]float64{}, 0, constrainedBudget)
	if err := ValidateFull45(canonical); err != nil {
		return out, fmt.Errorf("canonical start is not a full45 witness: %w", err)
	}
	_, gradient, err := runner.evaluate(canonical, true)
	if err != nil {
		return out, err
	}
	seeds, fallback, err := constrainedSeeds(mains, gradient)
	if err != nil {
		return out, err
	}
	out.Starts = make([]ConstrainedStart, 0, ConstrainedStartCount)
	for variant, seed := range seeds {
		if err := ctx.Err(); err != nil {
			return out, err
		}
		initialValue, _, evalErr := runner.evaluate(seed, false)
		if evalErr != nil {
			return out, evalErr
		}
		start := ConstrainedStart{
			Variant: variant, State: seed, InitialValue: initialValue,
			Variant1FullBudgetFallback: variant == 2 && fallback,
			FixedMainsState: seed, FixedMainsValue: initialValue,
			FinalState: seed, FinalValue: initialValue,
		}
		if start.Variant1FullBudgetFallback {
			runner.work.FullBudgetFallbacks++
		}
		state, value, stageErr := runner.lineStage(seed, initialValue)
		if stageErr != nil {
			return out, stageErr
		}
		start.FixedMainsState, start.FixedMainsValue = state, value
		start.FinalState, start.FinalValue = state, value
		out.Starts = append(out.Starts, start)
		if len(out.Starts) == 1 || quarterBetter(value, out.FixedMainsValue) {
			out.FixedMainsState, out.FixedMainsValue = state, value
		}
	}
	out.FixedMainsDelta = out.FixedMainsValue - out.BaselineValue

	for i := range out.Starts {
		start := &out.Starts[i]
		state, value := start.FixedMainsState, start.FixedMainsValue
		if hasUnlockedMains(unlocked) {
			for sweep := 0; sweep < constrainedMainSweeps; sweep++ {
				if err := ctx.Err(); err != nil {
					return out, err
				}
				runner.work.MainSweeps++
				state, value, err = runner.mainSweep(state, value, unlocked)
				if err != nil {
					return out, err
				}
			}
		}
		state, value, err = runner.lineStage(state, value)
		if err != nil {
			return out, err
		}
		final, finalErr := runner.optimize(state, constrainedFinalIterations, true)
		if finalErr != nil {
			return out, finalErr
		}
		if err := ctx.Err(); err != nil {
			return out, err
		}
		if fullErr := ValidateFull45(final.State); fullErr != nil {
			runner.work.RejectedNonFull45++
		} else if quarterBetter(final.Value, value) {
			state, value = final.State, final.Value
		}
		start.FinalState, start.FinalValue = state, value
	}

	bestIndex := 0
	for i := 1; i < len(out.Starts); i++ {
		if quarterBetter(out.Starts[i].FinalValue, out.Starts[bestIndex].FinalValue) {
			bestIndex = i
		}
	}
	out.State, out.Value = out.Starts[bestIndex].FinalState, out.Starts[bestIndex].FinalValue
	if err := ValidateFull45(out.FixedMainsState); err != nil {
		return out, fmt.Errorf("fixed-main checkpoint is not a full45 witness: %w", err)
	}
	if err := ValidateFull45(out.State); err != nil {
		return out, fmt.Errorf("final result is not a full45 witness: %w", err)
	}
	out.DeltaFromBaseline = out.Value - out.BaselineValue
	out.Work = runner.work
	out.Stop = "bounded_local_full45"
	return out, nil
}

func validateConstrainedPolicy(mains [4][5]string, unlocked [4][5]bool) error {
	for actor := range mains {
		for slot, main := range mains[actor] {
			if !validMain(slot, main) {
				return fmt.Errorf("actor %d slot %d has illegal starting main %q", actor, slot, main)
			}
			if unlocked[actor][slot] && slot < 2 {
				return fmt.Errorf("actor %d slot %d cannot unlock a fixed flower/plume main", actor, slot)
			}
		}
	}
	return nil
}

func hasUnlockedMains(unlocked [4][5]bool) bool {
	for actor := range unlocked {
		for slot := 2; slot < 5; slot++ {
			if unlocked[actor][slot] {
				return true
			}
		}
	}
	return false
}

// constrainedSeeds uses the same three start schemes for every case. Variant
// one may deliberately leave upgrade budget unused when every gradient is
// nonpositive; in that edge case it keeps variant one's balanced line layout
// and borrows the full-budget coordinate schedule from variant zero.
func constrainedSeeds(mains [4][5]string, gradient [4][10]float64) ([]State, bool, error) {
	seeds := []State{
		Seed(mains, [4][10]float64{}, 0, constrainedBudget),
		Seed(mains, gradient, 0, constrainedBudget),
		Seed(mains, gradient, 1, constrainedBudget),
	}
	if err := ValidateFull45(seeds[0]); err != nil {
		return nil, false, fmt.Errorf("zero-gradient start is not full45: %w", err)
	}
	if err := ValidateFull45(seeds[1]); err != nil {
		return nil, false, fmt.Errorf("gradient variant zero is not full45: %w", err)
	}
	fallback := false
	if err := ValidateFull45(seeds[2]); err != nil {
		seeds[2].Upgrades = seeds[1].Upgrades
		if err := ValidateFull45(seeds[2]); err != nil {
			return nil, false, fmt.Errorf("gradient variant one cannot be made full45: %w", err)
		}
		fallback = true
	}
	return seeds, fallback, nil
}

func (r *constrainedRunner) mainSweep(state State, value float64, unlocked [4][5]bool) (State, float64, error) {
	for actor := range unlocked {
		for slot := 2; slot < 5; slot++ {
			if !unlocked[actor][slot] {
				continue
			}
			if err := r.ctx.Err(); err != nil {
				return state, value, err
			}
			anchor, anchorValue := state, value
			_, gradient, err := r.evaluate(anchor, true)
			if err != nil {
				return state, value, err
			}
			best, bestValue := anchor, anchorValue
			for _, main := range mainChoices[slot] {
				if main == anchor.Mains[actor][slot] {
					continue
				}
				candidate, err := constrainedReplaceMain(anchor, actor, slot, main, gradient)
				if err != nil {
					return state, value, err
				}
				r.work.MainCandidates++
				if err := ValidateFull45(candidate); err != nil {
					r.work.RejectedNonFull45++
					continue
				}
				optimized, err := r.optimize(candidate, constrainedMainInner, false)
				if err != nil {
					return state, value, err
				}
				if err := r.ctx.Err(); err != nil {
					return state, value, err
				}
				if err := ValidateFull45(optimized.State); err != nil {
					r.work.RejectedNonFull45++
					continue
				}
				if quarterBetter(optimized.Value, bestValue) {
					best, bestValue = optimized.State, optimized.Value
				}
			}
			if best != anchor && quarterBetter(bestValue, anchorValue) {
				state, value = best, bestValue
				r.work.AcceptedMainMoves++
			}
		}
	}
	return state, value, nil
}

// constrainedReplaceMain validates a requested move before delegating line
// repair and budget projection to the unchanged production ReplaceMain.
func constrainedReplaceMain(state State, actor, slot int, main string, gradient [4][10]float64) (State, error) {
	if actor < 0 || actor >= len(state.Mains) || slot < 2 || slot >= len(state.Mains[actor]) {
		return state, fmt.Errorf("main move actor/slot is outside the sands-to-circlet domain")
	}
	if !validMain(slot, main) {
		return state, fmt.Errorf("illegal main %q for slot %d", main, slot)
	}
	if main == state.Mains[actor][slot] {
		return state, nil
	}
	candidate := ReplaceMain(state, actor, slot, main, gradient, constrainedBudget)
	if candidate.Mains[actor][slot] != main {
		return state, fmt.Errorf("legal main move was not applied")
	}
	if err := candidate.Validate(constrainedBudget, true); err != nil {
		return state, fmt.Errorf("main move produced an invalid witness: %w", err)
	}
	return candidate, nil
}
