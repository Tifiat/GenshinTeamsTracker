package formula

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// A diagnostic scalar channel from the actual support graph, not a claim that
// healing/drain is damage. The changed value is copied from a fresh engine run.
func TestForeignHealthInputResponse(t *testing.T) {
	b, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "gob11_health_input_sample_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	var sample struct {
		Member   contracts.IRSeedMember
		Deltas   map[string]float64
		Baseline float64 `json:"baseline_value"`
		Fresh    float64 `json:"fresh_engine_value"`
	}
	if err = json.Unmarshal(b, &sample); err != nil {
		t.Fatal(err)
	}
	check := func(value, want float64, err error) {
		t.Helper()
		if err != nil || math.Abs(value-want) > math.Max(1, math.Abs(want))*1e-10 {
			t.Fatalf("got %g want %g err=%v", value, want, err)
		}
	}
	base, err := EvaluateSeedMember(sample.Member, nil)
	check(base.Damage, sample.Baseline, err)
	changed, err := EvaluateSeedMember(sample.Member, sample.Deltas)
	check(changed.Damage, sample.Fresh, err)
	coordSet := map[string]bool{}
	for _, n := range sample.Member.Nodes {
		if n.Coordinate != "" {
			coordSet[n.Coordinate] = true
		}
	}
	coords := []string{}
	for key := range coordSet {
		coords = append(coords, key)
	}
	sort.Strings(coords)
	actors := []string{"bennett", "furina"}
	member := sample.Member
	member.Channels = append([]contracts.IRChannel(nil), sample.Member.Channels...)
	for i := range member.Channels {
		member.Channels[i].ActorKey = "furina"
	}
	compiled, err := CompileSeedMember(member, actors, coords)
	if err != nil {
		t.Fatal(err)
	}
	deltas := make([]float64, len(coords))
	for i, key := range coords {
		deltas[i] = sample.Deltas[key]
	}
	value, err := compiled.EvaluateDamageDense(deltas)
	check(value, sample.Fresh, err)
	value, err = compiled.EvaluateDamageDense(make([]float64, len(coords)))
	check(value, sample.Baseline, err)
	value, err = compiled.EvaluateDamageDenseForActor(deltas, 0)
	check(value, sample.Fresh, err)
}
