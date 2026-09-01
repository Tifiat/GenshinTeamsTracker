package formula

import (
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestCompiledMemberMatchesInterpreter(t *testing.T) {
	_, filename, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "compact_ir_v1.json")
	compact := readCompactFixture(t, path)
	member := compact.Members[0]
	coordinateSet := make(map[string]struct{})
	for _, node := range member.Nodes {
		if node.Operation == "artifact_stat" {
			coordinateSet[node.Coordinate] = struct{}{}
		}
	}
	coordinates := make([]string, 0, len(coordinateSet))
	for coordinate := range coordinateSet {
		coordinates = append(coordinates, coordinate)
	}
	sort.Strings(coordinates)
	compiled, err := CompileSeedMember(member, []string{"actor_a", "actor_b", "actor_c", "actor_d"}, coordinates)
	if err != nil {
		t.Fatal(err)
	}
	dense := make([]float64, len(coordinates))
	lookup := make(map[string]float64, len(coordinates))
	for index, coordinate := range coordinates {
		dense[index] = float64(index+1) / 100
		lookup[coordinate] = dense[index]
	}
	got, err := compiled.EvaluateDense(dense)
	if err != nil {
		t.Fatal(err)
	}
	want, err := EvaluateSeedMember(member, lookup)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(got.Damage-want.Damage) > 1e-9 {
		t.Fatalf("compiled damage %v; interpreter %v", got.Damage, want.Damage)
	}
	for index, actor := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		if math.Abs(got.ByActor[index]-want.ByActor[actor]) > 1e-9 {
			t.Fatalf("actor %s compiled damage %v; interpreter %v", actor, got.ByActor[index], want.ByActor[actor])
		}
	}
}

func TestActorEvaluationFollowsCrossActorDependencyFromAnchor(t *testing.T) {
	member := contracts.IRSeedMember{
		Seed: 1, DurationMS: 1000,
		TopologySHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Nodes: []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "100"},
			{NodeID: 2, Operation: "artifact_stat", Inputs: []contracts.IRInput{}, Coordinate: "actor_b.hp_percent"},
			{NodeID: 3, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "10"},
			{NodeID: 4, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "support_stat"}, {NodeID: 3, Relation: "support_scale"}}},
			{NodeID: 5, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base_damage"}, {NodeID: 4, Relation: "team_buff"}}},
		},
		Channels: []contracts.IRChannel{{
			ChannelID: "actor_a_skill_direct", Kind: "direct", ActorKey: "actor_a",
			AttackTag: "skill", DamageType: "synthetic", RootNodeID: 5,
			HitCount: 1, BaselineDamage: "100", ResponseCoordinates: []string{"actor_b.hp_percent"},
		}},
		OpaqueBoundaries: []contracts.IROpaqueBoundary{},
	}
	compiled, err := CompileSeedMember(
		member,
		[]string{"actor_a", "actor_b", "actor_c", "actor_d"},
		[]string{"actor_b.hp_percent"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := compiled.EvaluateDamageDenseForActor([]float64{2}, 1); err == nil {
		t.Fatal("actor hot path accepted a missing complete-team anchor")
	}
	anchor, err := compiled.EvaluateDamageDense([]float64{0})
	if err != nil || anchor != 100 {
		t.Fatalf("anchor = %v, %v; want 100", anchor, err)
	}
	fast, err := compiled.EvaluateDamageDenseForActor([]float64{2}, 1)
	if err != nil {
		t.Fatal(err)
	}
	full, err := compiled.EvaluateDense([]float64{2})
	if err != nil {
		t.Fatal(err)
	}
	if fast != 120 || fast != full.Damage {
		t.Fatalf("cross-actor support result fast=%v full=%v; want 120", fast, full.Damage)
	}
}

func readCompactFixture(t *testing.T, path string) contracts.CompactIR {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(payload)
	if err != nil {
		t.Fatal(err)
	}
	return compact
}
