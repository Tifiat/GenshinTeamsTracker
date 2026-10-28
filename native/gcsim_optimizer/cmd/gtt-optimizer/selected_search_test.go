package main

import (
	"context"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func TestSelectedCompleteCandidateRouteHasBoundedWorkAndLegalFinalists(t *testing.T) {
	request, compact := productFixtures(t)
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	result, receipt, err := runSelectedSearch(context.Background(), index, panel, nil)
	if err != nil {
		t.Fatal(err)
	}
	if receipt == nil || receipt.Algorithm != "fixed-package-screen-refine-stabilize-v1" || receipt.WorkLimit != 160000 || receipt.Evaluations > receipt.WorkLimit {
		t.Fatalf("wrong Selected route/work envelope: %+v", receipt)
	}
	if result.Leader.DPS < result.Initial.DPS || len(receipt.Stabilization) == 0 || len(receipt.Stabilization) > 6 {
		t.Fatalf("unpolished/worse formula result: %+v", result)
	}
	for _, row := range fixedSelectedFinalists(result) {
		if err := index.ValidateAssignment(row.Assignment); err != nil {
			t.Fatal(err)
		}
	}
}

func TestFixedSelectedFinalistsNeverReserveInputControl(t *testing.T) {
	row := func(id int64) search.ScoredAssignment {
		var assignment domain.Assignment
		assignment[0][0] = id
		return search.ScoredAssignment{Assignment: assignment, DPS: float64(id)}
	}
	result := search.Result{Initial: row(90), Leader: row(1)}
	for i := int64(1); i <= 20; i++ {
		result.Finalists = append(result.Finalists, row(i))
	}
	rows := fixedSelectedFinalists(result)
	if len(rows) != 20 || rows[0].Assignment != result.Leader.Assignment {
		t.Fatalf("already bounded search rows were lost or repeated: %+v", rows)
	}
	for _, candidate := range rows {
		if candidate.Assignment == result.Initial.Assignment {
			t.Fatal("input control was injected")
		}
	}
	result.Initial = result.Leader
	if got := fixedSelectedFinalists(result); len(got) != 20 {
		t.Fatal("duplicate control measured twice", got)
	}
}

func TestFixedSelectedWarningsDoNotClaimExhaustiveSearch(t *testing.T) {
	receipt := &selectedSearchReceipt{Stabilization: []search.Stabilization{{Stop: "single_stationary_sampled_pairs_stable"}}}
	result := search.Result{StopReason: "fixed_candidates_sampled_coordinate_pass_stable"}
	if got := fixedSelectedWarnings(result, receipt); len(got) != 1 || got[0] != "selected_bounded_search" {
		t.Fatal(got)
	}
	result.StopReason = "fixed_candidates_cycle_budget+stabilization_budget"
	receipt.Stabilization[0].Stop = "single_budget"
	if got := fixedSelectedWarnings(result, receipt); len(got) != 3 {
		t.Fatal(got)
	}
	if got := fixedSelectedWarnings(result, nil); len(got) != 0 {
		t.Fatal("legacy route relabeled", got)
	}
}
