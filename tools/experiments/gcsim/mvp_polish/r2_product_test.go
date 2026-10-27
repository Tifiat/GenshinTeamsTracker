package main

import (
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"os"
	"strings"
	"testing"
)

func TestR2GroupedProductRetainsActualMixedIterations(t *testing.T) {
	request, compact := productFixtures(t)
	compactSHA, e := contracts.CanonicalSHA256(compact)
	if e != nil {
		t.Fatal(e)
	}
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{SetGroupLimit: 1, BuildsPerGroup: 2})
	request = addArtifactVariants(t, request, 2, func(int, contracts.Artifact) string { return "shared_set" })
	leader := oneSwapAssignment(request, 1, 1)
	other := oneSwapAssignment(request, 1, 2)
	winner := finalists.MeasuredCandidate{Assignment: leader, FormulaDPS: 100, MeasuredDPS: 110, StandardError: 1, FormulaResidualDPS: 10, Iterations: 500, AssignmentSHA256: strings.Repeat("7", 64), EngineResultSHA256: strings.Repeat("8", 64)}
	alternate := finalists.MeasuredCandidate{Assignment: other, FormulaDPS: 99, MeasuredDPS: 80, StandardError: 2, FormulaResidualDPS: -19, Iterations: 100, AssignmentSHA256: strings.Repeat("9", 64), EngineResultSHA256: strings.Repeat("a", 64)}
	verification := &finalists.VerificationResult{Candidates: []finalists.MeasuredCandidate{winner, alternate}, Winner: winner, Iterations: 0}
	result, e := buildGroupedProductResult(request, compactSHA, "", nil, nil, []search.ScoredAssignment{{Assignment: leader, DPS: 100}, {Assignment: other, DPS: 99}}, verification, "synthetic-r2-debug.json")
	if e != nil {
		t.Fatal(e)
	}
	if result.Measured == nil || result.Measured.Iterations != 500 || len(result.Candidates) != 2 || result.Candidates[0].Measured.Iterations != 500 || result.Candidates[1].Measured.Iterations != 100 || result.Candidates[1].Measured.StandardError != "2" {
		t.Fatalf("mixed iterations lost: %+v", result)
	}
	if path := os.Getenv("GTT_R2_UI_FIXTURE"); path != "" {
		raw, e := json.Marshal(map[string]any{"request": request, "wrapper": map[string]any{"mode": "all_sets", "product_result": result, "verification": verification}})
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(path, raw, 0600); e != nil {
			t.Fatal(e)
		}
	}
}
