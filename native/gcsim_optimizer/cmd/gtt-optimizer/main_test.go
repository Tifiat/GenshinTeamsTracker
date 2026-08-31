package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func TestProgressEmitterWritesStrictMonotonicRecords(t *testing.T) {
	var buffer bytes.Buffer
	emitter := newProgressEmitter(&buffer, strings.Repeat("a", 64))
	if err := emitter.emit("searching", 1, 5, false); err != nil {
		t.Fatal(err)
	}
	if err := emitter.emit("completed", 5, 5, false); err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(&buffer)
	for expectedSequence := int64(0); expectedSequence < 2; expectedSequence++ {
		var record contracts.ProgressRecord
		if err := decoder.Decode(&record); err != nil {
			t.Fatal(err)
		}
		if err := record.Validate(); err != nil {
			t.Fatal(err)
		}
		if record.Sequence != expectedSequence {
			t.Fatalf("sequence = %d, want %d", record.Sequence, expectedSequence)
		}
	}
}

func TestCancelledContextStopsBeforeReadingRequest(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := run(ctx, []string{"validate-request", "missing.json"})
	if err == nil || !strings.Contains(err.Error(), "cancelled") {
		t.Fatalf("cancelled context should stop command, got %v", err)
	}
}

func TestBuildProductResultMatchesStrictContract(t *testing.T) {
	request, compact := productFixtures(t)
	var assignment domain.Assignment
	for wearerIndex, wearer := range request.Wearers {
		for slotIndex, row := range wearer.CurrentArtifacts {
			assignment[wearerIndex][slotIndex] = row.ArtifactID
		}
	}
	winner := finalists.MeasuredCandidate{
		Assignment: assignment, FormulaDPS: 100, MeasuredDPS: 110,
		StandardError: 2, FormulaResidualDPS: 10, Iterations: 1000,
		AssignmentSHA256:   strings.Repeat("7", 64),
		EngineResultSHA256: strings.Repeat("8", 64),
	}
	alternate := assignment
	alternate[0][0], alternate[0][1] = alternate[0][1], alternate[0][0]
	verification := finalists.VerificationResult{
		Winner: winner,
		Candidates: []finalists.MeasuredCandidate{
			winner,
			{
				Assignment: alternate, FormulaDPS: 99, MeasuredDPS: 109,
				StandardError: 2, FormulaResidualDPS: 10, Iterations: 1000,
				AssignmentSHA256:   strings.Repeat("9", 64),
				EngineResultSHA256: strings.Repeat("a", 64),
			},
		},
	}
	result, err := buildProductResult(
		request,
		compact,
		search.Result{OpaqueReasons: []string{"unknown"}},
		verification,
		"debug/gob7-result.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := result.Validate(); err != nil {
		t.Fatal(err)
	}
	if len(result.Winner) != 20 || len(result.Candidates) != 2 || result.Measured == nil || result.Measured.DPS != "110" || result.FormulaResidual != "10" {
		t.Fatalf("unexpected product result: %+v", result)
	}
	if result.Candidates[0].Rank != 1 || result.Candidates[0].Measured.DPS != "110" || result.Candidates[1].Measured.DPS != "109" {
		t.Fatalf("unexpected ranked candidates: %+v", result.Candidates)
	}
	if !containsString(result.Warnings, "measured_top_confidence_overlap") {
		t.Fatalf("missing confidence-overlap warning: %v", result.Warnings)
	}
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func TestBoundedN1000FinalistsKeepsMeasuredFormulaAndCurrent(t *testing.T) {
	assignment := func(id int64) domain.Assignment {
		var value domain.Assignment
		value[0][0] = id
		return value
	}
	rows := make([]finalists.MeasuredCandidate, 0, 8)
	for rank := 1; rank <= 8; rank++ {
		rows = append(rows, finalists.MeasuredCandidate{
			Rank: rank, Assignment: assignment(int64(rank)), AssignmentSHA256: string(rune('a' + rank)),
			FormulaDPS: float64(100 - rank), MeasuredDPS: float64(rank), Source: "screen",
		})
	}
	result := search.Result{
		Initial: search.ScoredAssignment{Assignment: assignment(20), DPS: 20, Source: "incumbent"},
		Leader:  search.ScoredAssignment{Assignment: assignment(1), DPS: 100, Source: "leader"},
	}
	selected := boundedN1000Finalists(finalists.VerificationResult{Candidates: rows}, result, 5)
	if len(selected) != 7 {
		t.Fatalf("selected %d; expected five measured plus leader and current", len(selected))
	}
	wanted := map[domain.Assignment]bool{assignment(8): true, assignment(7): true, assignment(6): true, assignment(5): true, assignment(4): true, assignment(1): true, assignment(20): true}
	for _, row := range selected {
		delete(wanted, row.Assignment)
	}
	if len(wanted) != 0 {
		t.Fatalf("missing mandatory assignments: %v", wanted)
	}
}

func productFixtures(t *testing.T) (contracts.OptimizerRequest, contracts.CompactIR) {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	directory := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	requestPayload, err := os.ReadFile(filepath.Join(directory, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compactPayload, err := os.ReadFile(filepath.Join(directory, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		t.Fatal(err)
	}
	return request, compact
}
