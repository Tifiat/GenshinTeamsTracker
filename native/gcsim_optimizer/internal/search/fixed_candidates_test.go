package search

import (
	"context"
	"errors"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	energyconstraint "genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func fixedCandidateEngine(t *testing.T, request contracts.OptimizerRequest, ir contracts.CompactIR, config Config) (*Engine, *domain.Index) {
	t.Helper()
	var err error
	ir.RequestSHA256, err = contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	panel, err := evaluator.Compile(request, ir)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := NewInventory(index, panel, config)
	if err != nil {
		t.Fatal(err)
	}
	return engine, index
}

func TestFixedCandidatesAcceptsExpandedOutputWithoutFillingAbsentRows(t *testing.T) {
	req, ir := searchFixtures(t)
	engine, _ := fixedCandidateEngine(t, req, ir, DefaultConfig())
	result, err := engine.RunFixedCandidates(context.Background(), 50, 1, contracts.MaxResultBuildsPerGroup)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Search.Finalists) > contracts.MaxResultBuildsPerGroup {
		t.Fatal("output exceeded requested count")
	}
}

func fixedTwoPlusTwoEngine(t *testing.T, config Config) (*Engine, *domain.Index) {
	t.Helper()
	request, ir := searchFixtures(t)
	request.Legality.FixedFourPiece = false
	request.Legality.FixedSetPackages = true

	sets := [4][5]string{
		{"set_a", "set_a", "set_b", "set_b", "set_c"},
		{"set_b", "set_b", "set_a", "set_a", "set_d"},
		{"set_c", "set_d", "set_c", "set_d", "set_a"},
		{"set_d", "set_c", "set_d", "set_c", "set_b"},
	}
	setByID := make(map[int64]string, 20)
	for actor := range request.Wearers {
		wearer := &request.Wearers[actor]
		wearer.SelectedSetUID = ""
		if actor < 2 {
			wearer.SelectedSets = []contracts.SetRequirement{{SetUID: "set_a", Count: 2}, {SetUID: "set_b", Count: 2}}
		} else {
			wearer.SelectedSets = []contracts.SetRequirement{{SetUID: "set_c", Count: 2}, {SetUID: "set_d", Count: 2}}
		}
		for slot := 0; slot < 5; slot++ {
			setByID[int64(actor*5+slot+1)] = sets[actor][slot]
		}
	}
	for i := range request.Artifacts {
		setUID, ok := setByID[request.Artifacts[i].ArtifactID]
		if !ok {
			t.Fatalf("fixture artifact %d has no fixed package mapping", request.Artifacts[i].ArtifactID)
		}
		request.Artifacts[i].SetUID = setUID
	}
	return fixedCandidateEngine(t, request, ir, config)
}

func assertFixedCandidateResult(t *testing.T, engine *Engine, index *domain.Index, result FixedResult, workLimit, finalistLimit int) {
	t.Helper()
	if result.Algorithm != fixedCandidateAlgorithm {
		t.Fatalf("unexpected algorithm %q", result.Algorithm)
	}
	if result.Evaluations > workLimit {
		t.Fatalf("work cap exceeded: got %d, limit %d", result.Evaluations, workLimit)
	}
	if result.Search.Initial.Assignment != index.Incumbent {
		t.Fatal("initial assignment was not preserved separately")
	}
	if len(result.Search.Finalists) > finalistLimit || len(result.Stabilization) > finalistLimit {
		t.Fatalf("finalist cap exceeded: finalists=%d stabilizations=%d limit=%d", len(result.Search.Finalists), len(result.Stabilization), finalistLimit)
	}
	if len(result.Search.Steps) != len(result.CandidateWork) {
		t.Fatalf("candidate stage accounting mismatch: steps=%d work records=%d", len(result.Search.Steps), len(result.CandidateWork))
	}
	candidateEvaluations, stabilizationEvaluations := 0, 0
	for _, step := range result.Search.Steps {
		candidateEvaluations += step.Expanded
		if len(step.Finalists) != 0 || step.BoundEvaluations != 0 || step.BoundPrunedBuilds != 0 {
			t.Fatalf("pre-stabilization or regional-bound output leaked into result: %+v", step)
		}
	}
	for _, work := range result.CandidateWork {
		if work.Stage != "screen" && work.Stage != "refine" {
			t.Fatalf("unexpected candidate stage %q", work.Stage)
		}
	}
	for _, status := range result.Stabilization {
		stabilizationEvaluations += status.Evaluations
	}
	if candidateEvaluations+stabilizationEvaluations != result.Evaluations {
		t.Fatalf("evaluation accounting mismatch: candidate=%d stabilization=%d total=%d", candidateEvaluations, stabilizationEvaluations, result.Evaluations)
	}
	if len(result.Search.Finalists) == 0 {
		if result.Search.Leader.Assignment != index.Incumbent {
			t.Fatal("empty final shortlist displaced the incumbent")
		}
		return
	}
	if result.Search.Leader != result.Search.Finalists[0] {
		t.Fatal("leader is not the best returned stabilized finalist")
	}
	if result.Search.Leader.DPS+1e-9 < result.Search.Initial.DPS {
		t.Fatal("final leader regressed below initial assignment")
	}
	for _, row := range result.Search.Finalists {
		if err := index.ValidateAssignment(row.Assignment); err != nil {
			t.Fatalf("returned finalist is illegal: %v", err)
		}
		counts, err := index.SelectedSetCounts(row.Assignment)
		if err != nil {
			t.Fatal(err)
		}
		for actor, requirements := range index.Wearers {
			for _, requirement := range requirements.SelectedSets {
				found := false
				for _, count := range counts[actor] {
					if count.SetUID == requirement.SetUID && count.Count >= requirement.Count {
						found = true
						break
					}
				}
				if !found {
					t.Fatalf("finalist lost package %s:%d for actor %d", requirement.SetUID, requirement.Count, actor)
				}
			}
		}
	}
	if len(result.Search.Finalists) > 0 && len(result.Stabilization) == 0 {
		t.Fatal("finalists were returned without stabilization statuses")
	}
	_ = engine // keeps the helper signature convenient for callers inspecting engine-owned scoring.
}

func TestRunFixedCandidatesPreservesFourPieceAndTwoPlusTwoPackages(t *testing.T) {
	config := DefaultConfig()
	config.MaxExpandedPerActor = 32
	config.MaxCycles = 1
	for _, fixture := range []struct {
		name    string
		prepare func(*testing.T) (*Engine, *domain.Index)
	}{
		{
			name: "four_piece",
			prepare: func(t *testing.T) (*Engine, *domain.Index) {
				request, ir := searchFixtures(t)
				return fixedCandidateEngine(t, request, ir, config)
			},
		},
		{
			name: "two_plus_two",
			prepare: func(t *testing.T) (*Engine, *domain.Index) {
				return fixedTwoPlusTwoEngine(t, config)
			},
		},
	} {
		t.Run(fixture.name, func(t *testing.T) {
			engine, index := fixture.prepare(t)
			result, err := engine.RunFixedCandidates(context.Background(), 64, 4)
			if err != nil {
				t.Fatal(err)
			}
			assertFixedCandidateResult(t, engine, index, result, 64, 4)
			if result.Search.StopReason == "" {
				t.Fatal("missing heuristic/budget stop reason")
			}
		})
	}
}

func TestRunFixedCandidatesBudgetCancelAndFailClosed(t *testing.T) {
	request, ir := searchFixtures(t)
	engine, index := fixedCandidateEngine(t, request, ir, DefaultConfig())
	zero, err := engine.RunFixedCandidates(context.Background(), 0, 2)
	if err != nil {
		t.Fatal(err)
	}
	assertFixedCandidateResult(t, engine, index, zero, 0, 2)
	if len(zero.Search.Finalists) != 1 || len(zero.Stabilization) != 1 || zero.Stabilization[0].Stop != "stabilization_budget" {
		t.Fatalf("zero-budget result is not explicitly budget-limited: %+v", zero)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	cancelled, err := engine.RunFixedCandidates(ctx, 100, 2)
	if !errors.Is(err, context.Canceled) || cancelled.Search.StopReason != "fixed_candidates_cancelled" || len(cancelled.Search.Finalists) != 0 {
		t.Fatalf("cancel was not preserved honestly: %+v %v", cancelled, err)
	}

	nonInventory, err := New(index, engine.panel, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := nonInventory.RunFixedCandidates(context.Background(), 100, 2); err == nil {
		t.Fatal("fixed-candidate route accepted a non-inventory engine")
	}
	engine.energy = &energyconstraint.Model{}
	if _, err := engine.RunFixedCandidates(context.Background(), 100, 2); err == nil {
		t.Fatal("fixed-candidate route accepted finite-energy mode")
	}
}

func TestRunFixedCandidatesStabilizesCoupledPhysicalExchange(t *testing.T) {
	config := DefaultConfig()
	config.MaxExpandedPerActor = 64
	config.MaxCycles = 1
	config.PairFinalistLimit = 2
	engine, index := coupledStabilization(t)
	engine.config = config
	result, err := engine.RunFixedCandidates(context.Background(), 4000, 1)
	if err != nil {
		t.Fatal(err)
	}
	assertFixedCandidateResult(t, engine, index, result, 4000, 1)
	if len(result.Search.Finalists) != 1 || len(result.Stabilization) != 1 || result.Search.Leader.DPS <= result.Search.Initial.DPS {
		t.Fatalf("joint stabilization did not improve the team: %+v", result)
	}
	flowers := result.Search.Leader.Assignment[0][0] + result.Search.Leader.Assignment[1][0]
	if flowers != 2001 || result.Search.Leader.Assignment[0][0] < 1000 || result.Search.Leader.Assignment[1][0] < 1000 {
		t.Fatalf("physical exchange was not retained: %+v", result.Search.Leader.Assignment)
	}
}
