package evaluator

import (
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/stochastic"
)

func TestCompiledPanelMatchesReferenceAggregator(t *testing.T) {
	request, compact := fixtures(t)
	panel, err := Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	dense := make([]float64, len(panel.Coordinates()))
	deltaMap := make(map[string]float64, len(dense))
	for index, coordinate := range panel.Coordinates() {
		dense[index] = float64(index+1) / 100
		deltaMap[coordinate] = dense[index]
	}
	got, err := panel.Evaluate(dense)
	if err != nil {
		t.Fatal(err)
	}
	want, err := stochastic.AggregateFixedPanel(request, compact, deltaMap)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(got.MeanDPS-want.CandidateMeanDPS) > 1e-9 || math.Abs(got.SampleSDDPS-want.SampleStandardDeviationDPS) > 1e-9 {
		t.Fatalf("compiled panel differs: %#v vs %#v", got, want)
	}
	for index, actor := range panel.ActorKeys() {
		if actor != want.CandidateByActor[index].ActorKey || math.Abs(got.ByActorDPS[index]-want.CandidateByActor[index].DPS) > 1e-9 {
			t.Fatalf("actor %s differs", actor)
		}
	}
}

func TestCompiledPanelUsesEachSeedsOwnDuration(t *testing.T) {
	request, compact := fixtures(t)
	compact.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	compact.Members[1].DurationMS = 10000
	panel, err := Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	got, err := panel.Evaluate(make([]float64, len(panel.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	want := (105.0/20.0 + 114.0/10.0) / 2.0
	if math.Abs(got.MeanDPS-want) > 1e-12 || math.Abs(got.ByActorDPS[0]-want) > 1e-12 {
		t.Fatalf("per-seed duration lost: got %#v want DPS %v", got, want)
	}
	fast, err := panel.EvaluateDPS(make([]float64, len(panel.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(fast-want) > 1e-12 {
		t.Fatalf("hot path duration lost: got %v want %v", fast, want)
	}
}

func fixtures(t *testing.T) (contracts.OptimizerRequest, contracts.CompactIR) {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	requestBytes, err := os.ReadFile(filepath.Join(root, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compactBytes, err := os.ReadFile(filepath.Join(root, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(requestBytes)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(compactBytes)
	if err != nil {
		t.Fatal(err)
	}
	return request, compact
}
