package main

import (
	"context"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

// Keep the existing Search envelope and record the new work explicitly without
// duplicating its response ledger or full assignment history in the receipt.
type selectedSearchReceipt struct {
	Algorithm     string                      `json:"algorithm"`
	Evaluations   int                         `json:"evaluations"`
	WorkLimit     int                         `json:"work_limit"`
	CandidateWork []search.FixedCandidateWork `json:"candidate_work"`
	Stabilization []search.Stabilization      `json:"stabilization"`
}

func runSelectedSearch(ctx context.Context, index *domain.Index, panel *evaluator.Panel, energyModel *energy.Model, outputLimits ...int) (search.Result, *selectedSearchReceipt, error) {
	config := search.DefaultConfig()
	// The complete-candidate/stabilization APIs do not yet impose ER deadlines.
	// Keep the accepted finite-energy path, rather than silently dropping them.
	if energyModel != nil {
		engine, err := search.New(index, panel, config, energyModel)
		if err != nil {
			return search.Result{}, nil, err
		}
		result, err := engine.Run(ctx)
		return result, nil, err
	}
	engine, err := search.NewInventory(index, panel, config)
	if err != nil {
		return search.Result{}, nil, err
	}
	// Reuse the old actor-stage ceiling for the entire candidate + stabilization
	// trial budget. Gradient/preparation work is recorded separately, not trials.
	workLimit := len(index.Wearers) * config.MaxCycles * config.MaxExpandedPerActor
	result, err := engine.RunFixedCandidates(ctx, workLimit, 6, outputLimits...)
	return result.Search, &selectedSearchReceipt{
		Algorithm: result.Algorithm, Evaluations: result.Evaluations, WorkLimit: workLimit,
		CandidateWork: result.CandidateWork, Stabilization: result.Stabilization,
	}, err
}

// Only search candidates, never a reserved equipped/control row.
func fixedSelectedFinalists(result search.Result) []search.ScoredAssignment {
	rows := uniqueCandidates(append([]search.ScoredAssignment{result.Leader}, result.Finalists...))
	return rows
}

func fixedSelectedWarnings(result search.Result, receipt *selectedSearchReceipt) []string {
	if receipt == nil {
		return nil
	}
	warnings := []string{"selected_bounded_search"}
	if strings.Contains(result.StopReason, "budget") {
		warnings = append(warnings, "selected_search_budget_limited")
	}
	for _, status := range receipt.Stabilization {
		if status.Stop != "single_stationary_sampled_pairs_stable" {
			warnings = append(warnings, "selected_finalist_stabilization_incomplete")
			break
		}
	}
	return warnings
}
