package formula

import (
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestEvaluateSharedCompactFixture(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "compact_ir_v1.json")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(payload)
	if err != nil {
		t.Fatal(err)
	}
	for _, member := range compact.Members {
		baseline, err := EvaluateSeedMember(member, nil)
		if err != nil {
			t.Fatal(err)
		}
		var declared float64
		for _, channel := range member.Channels {
			value, err := strconv.ParseFloat(channel.BaselineDamage, 64)
			if err != nil {
				t.Fatal(err)
			}
			declared += value
		}
		if baseline.Damage != declared {
			t.Fatalf("seed %d baseline damage = %v, declared %v", member.Seed, baseline.Damage, declared)
		}
	}
	score, err := EvaluateSeedMember(compact.Members[0], map[string]float64{"actor_a.hp_percent": 1})
	if err != nil {
		t.Fatal(err)
	}
	if score.Damage != 205 {
		t.Fatalf("candidate damage = %v, want 205", score.Damage)
	}
}

func TestEvaluateSupportedArithmeticAndActorTotals(t *testing.T) {
	input := func(nodeID uint32) contracts.IRInput {
		return contracts.IRInput{NodeID: nodeID, Relation: "test"}
	}
	member := contracts.IRSeedMember{
		Nodes: []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "10"},
			{NodeID: 2, Operation: "artifact_stat", Inputs: []contracts.IRInput{}, Coordinate: "actor.hp_percent"},
			{NodeID: 3, Operation: "add", Inputs: []contracts.IRInput{input(1), input(2)}},
			{NodeID: 4, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "2"},
			{NodeID: 5, Operation: "power", Inputs: []contracts.IRInput{input(3), input(4)}},
			{NodeID: 6, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "200"},
			{NodeID: 7, Operation: "min", Inputs: []contracts.IRInput{input(5), input(6)}},
			{NodeID: 8, Operation: "opaque_frozen", Inputs: []contracts.IRInput{}, Value: "3"},
			{NodeID: 9, Operation: "max", Inputs: []contracts.IRInput{input(7), input(8)}},
		},
		Channels: []contracts.IRChannel{
			{ChannelID: "known", ActorKey: "actor", RootNodeID: 9},
			{ChannelID: "opaque", ActorKey: "other", RootNodeID: 8},
		},
	}
	score, err := EvaluateSeedMember(member, map[string]float64{"actor.hp_percent": 4})
	if err != nil {
		t.Fatal(err)
	}
	if score.Damage != 199 || score.ByActor["actor"] != 196 || score.ByActor["other"] != 3 {
		t.Fatalf("score = %#v", score)
	}
}
