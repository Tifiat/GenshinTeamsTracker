package search

import (
	"context"
	"fmt"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

// SingleReplacements is an output-only neighbourhood of one complete build.
// Every score changes exactly one physical item; it never sums independent
// deltas or changes the core search's queue, leader or work allowance.
func SingleReplacements(ctx context.Context, index *domain.Index, panel *evaluator.Panel, anchor ScoredAssignment, count int, ledger *energy.Model) ([]ScoredAssignment, error) {
	if index == nil || panel == nil || count < 0 {
		return nil, fmt.Errorf("invalid replacement domain")
	}
	if err := index.ValidateAssignment(anchor.Assignment); err != nil {
		return nil, err
	}
	if count == 0 {
		return nil, nil
	}
	dense, err := index.DenseDeltas(anchor.Assignment)
	if err != nil {
		return nil, err
	}
	var best []ScoredAssignment
	for actor := 0; actor < 4; actor++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		validator, err := index.PrepareLocalAssignmentValidator(anchor.Assignment, actor)
		if err != nil {
			return nil, err
		}
		program, err := panel.ArtifactProgram(dense, actor)
		if err != nil {
			return nil, err
		}
		vectors, reference, err := index.ArtifactVectors(actor, program.Coordinates())
		if err != nil {
			return nil, err
		}
		x := make([]float64, len(reference))
		for slot, ids := range index.CandidateIDsBySlot {
			for _, id := range ids {
				if err := ctx.Err(); err != nil {
					return nil, err
				}
				if id == anchor.Assignment[actor][slot] {
					continue
				}
				trial := anchor.Assignment
				trial[actor][slot] = id
				if validator.Validate(trial[actor]) != nil {
					continue
				}
				if ledger != nil {
					feasible, err := ledger.Assess(trial)
					if err != nil {
						return nil, err
					}
					if !feasible.Feasible {
						continue
					}
				}
				// Preserve the exact existing five-slot accumulation order.
				for j, value := range reference {
					x[j] = -value
				}
				for _, item := range trial[actor] {
					for j, value := range vectors[item] {
						x[j] += value
					}
				}
				dps, err := program.Evaluate(x)
				if err != nil {
					return nil, err
				}
				best = append(best, ScoredAssignment{Assignment: trial, DPS: dps, Source: "single_item_replacement"})
				sortScored(best)
				if len(best) > count {
					best = best[:count]
				}
			}
		}
	}
	return best, nil
}

func AssignmentDistance(a, b domain.Assignment) int {
	n := 0
	for actor := range a {
		for slot := range a[actor] {
			if a[actor][slot] != b[actor][slot] {
				n++
			}
		}
	}
	return n
}
