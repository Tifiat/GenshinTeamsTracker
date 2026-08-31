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
