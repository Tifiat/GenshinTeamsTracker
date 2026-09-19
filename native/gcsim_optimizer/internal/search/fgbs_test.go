package search

import (
	"context"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	energyconstraint "genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func TestEnergyConstraintRetainsFormulaInvisibleERAndFindsFeasibleBuild(t *testing.T) {
	request, compact := searchFixtures(t)
	alternative := request.Artifacts[0]
	alternative.ArtifactID = 99001
	alternative.Substats = []contracts.StatValue{{Key: "energy_recharge", Value: "0.8"}}
	request.Artifacts = append(request.Artifacts, alternative)
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	compact.RequestSHA256 = requestSHA
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	indexed, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	incumbentER, err := indexed.IncumbentStat(0, "energy_recharge")
	if err != nil {
		t.Fatal(err)
	}
	states := make([]contracts.IREnergyCharacterState, 4)
	for actor, wearer := range indexed.Wearers {
		states[actor] = contracts.IREnergyCharacterState{CharacterIndex: actor, CharacterKey: wearer.WearerKey, Energy: "60", EnergyMax: "60"}
	}
	key := indexed.Wearers[0].WearerKey
	raw := "40"
	observed := strconv.FormatFloat(1+incumbentER, 'f', -1, 64)
	onField := true
	ledger := &contracts.IREnergyLedger{
		InitialStates: states,
		Events: []contracts.IREnergyEvent{
			{SequenceIndex: 0, Frame: 1, CharacterIndex: 0, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: "60", EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
			{SequenceIndex: 1, Frame: 2, CharacterIndex: 0, CharacterKey: key, Kind: "particle", Source: "skill", EnergyBefore: "0", EnergyAfter: raw, EnergyMax: "60", Amount: raw, RawAtER100: &raw, ObservedER: &observed, OnField: &onField},
			{SequenceIndex: 2, Frame: 3, CharacterIndex: 0, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: raw, EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
		},
		UncertaintyCodes: []string{"energy_source_schedule_observed_not_symbolic"},
	}
	for memberIndex := range compact.Members {
		compact.Members[memberIndex].EnergyLedger = ledger
	}
	energyModel, err := energyconstraint.Compile(indexed, compact.Members)
	if err != nil {
		t.Fatal(err)
	}
	engine, err := New(indexed, panel, Config{64, 64, 10000, 16, 1, 16}, energyModel)
	if err != nil {
		t.Fatal(err)
	}
	step, err := engine.searchActor(context.Background(), indexed.Incumbent, 0, 1, 64)
	if err != nil {
		t.Fatal(err)
	}
	if step.Finalists[0].Assignment[0][0] != alternative.ArtifactID {
		t.Fatalf("energy-feasible formula-invisible artifact was lost: %#v", step.Finalists[0].Assignment[0])
	}
	assessment, err := energyModel.Assess(step.Finalists[0].Assignment)
	if err != nil || !assessment.Feasible {
		t.Fatalf("leader energy assessment = %#v, %v", assessment, err)
	}
}

func TestReducedActorSearchMatchesExhaustiveAndPreservesLegality(t *testing.T) {
	request, compact := searchFixtures(t)
	choices := make([][]int64, 5)
	for slot := 0; slot < 5; slot++ {
		base := request.Artifacts[slot]
		alternative := base
		alternative.ArtifactID = int64(21 + slot)
		if len(alternative.Substats) == 0 {
			t.Fatal("fixture artifact needs a substat")
		}
		value, _ := strconv.ParseFloat(alternative.Substats[0].Value, 64)
		alternative.Substats[0].Value = strconv.FormatFloat(value+float64(slot+1)/100, 'f', -1, 64)
		request.Artifacts = append(request.Artifacts, alternative)
		choices[slot] = []int64{base.ArtifactID, alternative.ArtifactID}
	}
	off := request.Artifacts[3]
	off.ArtifactID = 26
	off.SetUID = "set_x"
	value, _ := strconv.ParseFloat(off.Substats[0].Value, 64)
	off.Substats[0].Value = strconv.FormatFloat(value+0.25, 'f', -1, 64)
	request.Artifacts = append(request.Artifacts, off)
	choices[3] = append(choices[3], off.ArtifactID)
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	compact.RequestSHA256 = requestSHA
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	indexed, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := New(indexed, panel, Config{64, 64, 10000, 16, 1, 16})
	if err != nil {
		t.Fatal(err)
	}
	step, err := engine.searchActor(context.Background(), indexed.Incumbent, 0, 1, 64)
	if err != nil {
		t.Fatal(err)
	}

	best := -math.MaxFloat64
	var walk func(int, domain.Assignment)
	walk = func(slot int, assignment domain.Assignment) {
		if slot == 5 {
			if indexed.ValidateAssignment(assignment) != nil {
				return
			}
			dps, err := engine.score(assignment)
			if err != nil {
				t.Fatal(err)
			}
			if dps > best {
				best = dps
			}
			return
		}
		for _, id := range choices[slot] {
			next := assignment
			next[0][slot] = id
			walk(slot+1, next)
		}
	}
	walk(0, indexed.Incumbent)
	if math.Abs(step.Finalists[0].DPS-best) > 1e-9 {
		t.Fatalf("FGBS leader %.12f; exhaustive %.12f", step.Finalists[0].DPS, best)
	}
	if err := indexed.ValidateAssignment(step.Finalists[0].Assignment); err != nil {
		t.Fatalf("leader is illegal: %v", err)
	}
}

func searchFixtures(t *testing.T) (contracts.OptimizerRequest, contracts.CompactIR) {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	raw, err := os.ReadFile(filepath.Join(root, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(raw)
	if err != nil {
		t.Fatal(err)
	}
	raw, err = os.ReadFile(filepath.Join(root, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(raw)
	if err != nil {
		t.Fatal(err)
	}
	return request, compact
}
