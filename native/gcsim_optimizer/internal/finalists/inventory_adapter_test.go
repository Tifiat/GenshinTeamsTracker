package finalists

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func TestInventoryAdapterPreservesLegacyRowsTiesRejectionsAndJSON(t *testing.T) {
	request := fullBuildRequestFixture(false)
	assignmentB, assignmentA, assignmentRejected := domain.Assignment{}, domain.Assignment{}, domain.Assignment{}
	assignmentB[0][0], assignmentA[0][0], assignmentRejected[0][0] = 2, 1, 3
	candidates := []search.ScoredAssignment{
		{Assignment: assignmentB, DPS: 90, Source: "pair-search"},
		{Assignment: assignmentA, DPS: 80, Source: "incumbent"},
		{Assignment: assignmentRejected, DPS: 70, Source: "inventory-frontier"},
	}
	fullCandidates, originals, err := prepareInventoryCandidates(request, candidates)
	if err != nil {
		t.Fatal(err)
	}
	legacyRenderer := func(candidate search.ScoredAssignment, iterations, workers int) (RenderedConfig, error) {
		text := fmt.Sprintf("options iteration=%d workers=%d ignore_burst_energy=false;\n# inventory_id=%d\n", iterations, workers, candidate.Assignment[0][0])
		return RenderedConfig{Text: text, SHA256: contracts.TextSHA256(text)}, nil
	}
	plan := []VerificationWave{{Index: 1, StartRank: 1, CandidateCount: len(candidates), Workers: 4, Parallelism: 2}}
	runner := func(_ context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		idText, ok := strings.CutPrefix(configText, "options iteration=")
		if !ok {
			return engineclient.OrdinaryResult{}, fmt.Errorf("rendered inventory id marker is missing")
		}
		_, idText, ok = strings.Cut(idText, "# inventory_id=")
		if !ok {
			return engineclient.OrdinaryResult{}, fmt.Errorf("rendered inventory id marker is missing")
		}
		id, err := strconv.ParseInt(strings.TrimSpace(idText), 10, 64)
		if err != nil {
			return engineclient.OrdinaryResult{}, err
		}
		shortage := 0.0
		if id == assignmentRejected[0][0] {
			shortage = 9
		}
		return ordinaryFixtureResult(configText, iterations, 100, shortage), nil
	}
	full, err := verifyFullBuildsWithPlan(
		context.Background(), request, fullCandidates, inventoryCandidateRenderer(legacyRenderer),
		t.TempDir()+"/run", 500, plan, runner, false,
	)
	if err != nil {
		t.Fatal(err)
	}
	adapted, err := adaptInventoryVerification(full, request, fullCandidates, originals, 500, 4, 2, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(adapted.Candidates) != 2 || adapted.Candidates[0].Rank != 1 || adapted.Candidates[0].Source != "pair-search" || adapted.Candidates[0].Assignment != assignmentB ||
		adapted.Candidates[1].Rank != 2 || adapted.Candidates[1].Source != "incumbent" || adapted.Candidates[1].Assignment != assignmentA {
		t.Fatalf("inventory rank/source/order mapping changed: %+v", adapted.Candidates)
	}
	if adapted.Candidates[0].FormulaDPS != 90 || adapted.Candidates[0].FormulaResidualDPS != 10 || adapted.Candidates[1].FormulaDPS != 80 || adapted.Candidates[1].FormulaResidualDPS != 20 {
		t.Fatalf("inventory formula diagnostics changed: %+v", adapted.Candidates)
	}
	shaA, err := assignmentSHA256(assignmentA)
	if err != nil {
		t.Fatal(err)
	}
	shaB, err := assignmentSHA256(assignmentB)
	if err != nil {
		t.Fatal(err)
	}
	expectedWinner := shaA
	if shaB < expectedWinner {
		expectedWinner = shaB
	}
	if adapted.Winner.AssignmentSHA256 != expectedWinner {
		t.Fatalf("measured DPS tie did not use legacy assignment SHA ordering: got %s, want %s", adapted.Winner.AssignmentSHA256, expectedWinner)
	}
	if adapted.Candidates[0].AssignmentSHA256 != shaB || adapted.Candidates[1].AssignmentSHA256 != shaA {
		t.Fatalf("measured rows lost legacy assignment SHA identity: %+v", adapted.Candidates)
	}
	shaRejected, err := assignmentSHA256(assignmentRejected)
	if err != nil {
		t.Fatal(err)
	}
	if len(adapted.EnergyRejectedSHA256) != 1 || adapted.EnergyRejectedSHA256[0] != shaRejected {
		t.Fatalf("energy rejection did not map back to legacy assignment SHA: %v", adapted.EnergyRejectedSHA256)
	}

	payload, err := json.Marshal(adapted)
	if err != nil {
		t.Fatal(err)
	}
	var legacy map[string]json.RawMessage
	if err := json.Unmarshal(payload, &legacy); err != nil {
		t.Fatal(err)
	}
	if len(legacy) != 7 {
		t.Fatalf("legacy verification JSON field count changed: %s", payload)
	}
	for _, forbidden := range []string{"attempted_sha256", "failed_sha256", "candidate_sha256", "build_identity", "engine_artifact_sha256", "source_manifest_sha256"} {
		if _, exists := legacy[forbidden]; exists {
			t.Fatalf("new full-build field leaked into legacy JSON: %s", forbidden)
		}
	}
	var legacyRows []map[string]json.RawMessage
	if err := json.Unmarshal(legacy["candidates"], &legacyRows); err != nil {
		t.Fatal(err)
	}
	if len(legacyRows) != 2 || len(legacyRows[0]) != 13 {
		t.Fatalf("legacy candidate JSON field set changed: %s", payload)
	}
	for _, forbidden := range []string{"candidate_sha256", "build_identity", "engine_artifact_sha256", "source_manifest_sha256"} {
		if _, exists := legacyRows[0][forbidden]; exists {
			t.Fatalf("new full-build field leaked into legacy candidate JSON: %s", forbidden)
		}
	}
	if !strings.Contains(string(payload), `"source":"pair-search"`) {
		t.Fatalf("legacy JSON lost source provenance: %s", payload)
	}
}

func TestInventoryCandidatePreparationStillRejectsDuplicateAssignment(t *testing.T) {
	request := fullBuildRequestFixture(false)
	assignment := domain.Assignment{}
	_, _, err := prepareInventoryCandidates(request, []search.ScoredAssignment{
		{Assignment: assignment, DPS: 10, Source: "first"},
		{Assignment: assignment, DPS: 9, Source: "second"},
	})
	if err == nil || !strings.Contains(err.Error(), "duplicate finalist assignment at rank 2") {
		t.Fatalf("inventory duplicate assignment error changed: %v", err)
	}
}
