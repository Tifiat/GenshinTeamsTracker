package theory

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func TestSolveUsesFormulaVisibleCarryAndSupportStatsWithinGameBudget(t *testing.T) {
	request := theoryRequestFixture(t)
	actors := []string{"actor_a", "actor_b", "actor_c", "actor_d"}
	members := []contracts.IRSeedMember{theoryMember(1), theoryMember(2)}
	panel, err := evaluator.CompileMembers(actors, []uint64{1, 2}, members)
	if err != nil {
		t.Fatal(err)
	}
	result, err := Solve(panel, request, Config{RollUnitsPerWearer: 8, MainStatCycles: 2, ExchangeIterations: 8})
	if err != nil {
		t.Fatal(err)
	}
	if result.FormulaDPS <= panel.Baseline().MeanDPS || result.FormulaEvaluations == 0 || result.MainLayoutsEvaluated < 2 {
		t.Fatalf("unexpected theory result: %#v", result)
	}
	if result.Allocations[0].MainStats["sands"] != "atk_percent" {
		t.Fatalf("carry sands = %q", result.Allocations[0].MainStats["sands"])
	}
	if result.Allocations[1].MainStats["sands"] != "hp_percent" {
		t.Fatalf("support sands = %q", result.Allocations[1].MainStats["sands"])
	}
	for _, row := range result.Allocations {
		if row.SpentRollUnits > 8+1e-9 || row.UnspentRollUnits < -1e-9 {
			t.Fatalf("wearer budget exceeded: %#v", row)
		}
		for _, stat := range row.Substats {
			if stat.RollUnits < 0 || math.IsNaN(stat.StatValue) || math.IsInf(stat.StatValue, 0) {
				t.Fatalf("invalid stat allocation: %#v", stat)
			}
		}
	}
	if len(result.Allocations[2].Substats) != 0 || len(result.Allocations[3].Substats) != 0 {
		t.Fatal("formula-invisible wearers received claimed useful rolls")
	}
}

func TestSolveIsDeterministic(t *testing.T) {
	request := theoryRequestFixture(t)
	panel, err := evaluator.CompileMembers(
		[]string{"actor_a", "actor_b", "actor_c", "actor_d"},
		[]uint64{1, 2},
		[]contracts.IRSeedMember{theoryMember(1), theoryMember(2)},
	)
	if err != nil {
		t.Fatal(err)
	}
	a, err := Solve(panel, request, Config{4, 1, 4})
	if err != nil {
		t.Fatal(err)
	}
	b, err := Solve(panel, request, Config{4, 1, 4})
	if err != nil {
		t.Fatal(err)
	}
	left, _ := json.Marshal(a)
	right, _ := json.Marshal(b)
	if string(left) != string(right) {
		t.Fatal("theory result is not deterministic")
	}
}

func theoryMember(seed uint64) contracts.IRSeedMember {
	return contracts.IRSeedMember{
		Seed: seed, DurationMS: 1000,
		TopologySHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Nodes: []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "1000"},
			{NodeID: 2, Operation: "artifact_stat", Inputs: []contracts.IRInput{}, Coordinate: "actor_a.atk_percent"},
			{NodeID: 3, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "1000"},
			{NodeID: 4, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "carry_stat"}, {NodeID: 3, Relation: "carry_scale"}}},
			{NodeID: 5, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base"}, {NodeID: 4, Relation: "carry_gain"}}},
			{NodeID: 6, Operation: "artifact_stat", Inputs: []contracts.IRInput{}, Coordinate: "actor_b.hp_percent"},
			{NodeID: 7, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "1500"},
			{NodeID: 8, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 6, Relation: "support_stat"}, {NodeID: 7, Relation: "support_scale"}}},
			{NodeID: 9, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 5, Relation: "direct"}, {NodeID: 8, Relation: "support_gain"}}},
		},
		Channels: []contracts.IRChannel{{
			ChannelID: "actor_a_skill_direct", Kind: "direct", ActorKey: "actor_a",
			AttackTag: "skill", DamageType: "synthetic", RootNodeID: 9, HitCount: 1,
			BaselineDamage: "1000", ResponseCoordinates: []string{"actor_a.atk_percent", "actor_b.hp_percent"},
		}},
		OpaqueBoundaries: []contracts.IROpaqueBoundary{},
	}
}

func theoryRequestFixture(t *testing.T) contracts.OptimizerRequest {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "request_v1.json")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	request.Artifacts = []contracts.Artifact{}
	request.Legality.FixedFourPiece = false
	request.Legality.FixedSetPackages = false
	request.Legality.TheorySearch = true
	request.Legality.MaxOffSetPiecesPerWearer = 0
	for index := range request.Wearers {
		request.Wearers[index].SelectedSetUID = ""
		request.Wearers[index].SelectedSets = nil
		request.Wearers[index].CurrentArtifacts = []contracts.ArtifactAssignment{}
		request.Wearers[index].TheoryBaseline = &contracts.TheoryArtifactBaseline{MainStats: []contracts.TheoryMainStat{
			{Slot: "flower", Key: "hp", Value: "4780"},
			{Slot: "plume", Key: "atk", Value: "311"},
			{Slot: "sands", Key: "atk_percent", Value: "0.466"},
			{Slot: "goblet", Key: "atk_percent", Value: "0.466"},
			{Slot: "circlet", Key: "crit_rate", Value: "0.311"},
		}}
	}
	expanded, err := request.ExpandTheoryBaselines()
	if err != nil {
		t.Fatal(err)
	}
	return expanded
}
