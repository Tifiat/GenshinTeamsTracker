package formula

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// Real-capture slices pin the All Sets preflight arithmetic. This is not a
// production set-reuse policy: effect/lifecycle provenance is still required.
func TestSetStaticEffectReplacementWitnesses(t *testing.T) {
	checkEngineResponseSamples(t, "all_sets_preflight_samples_v1.json", 4)
}

func TestSetReplacementShortcutNegativeControls(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "all_sets_preflight_samples_v1.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Controls []struct {
			Case             string
			Member           contracts.IRSeedMember
			WrongDeltas      map[string]float64 `json:"wrong_deltas"`
			FreshDamage      string             `json:"fresh_engine_damage"`
			SameTopologyHash bool               `json:"same_topology_hash"`
		} `json:"negative_controls"`
	}
	if err = json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Controls) != 3 {
		t.Fatal("missing negative witnesses")
	}
	for _, sample := range fixture.Controls {
		t.Run(sample.Case, func(t *testing.T) {
			if err := contracts.ValidateSeedMember(sample.Member); err != nil {
				t.Fatal(err)
			}
			got, err := EvaluateSeedMember(sample.Member, sample.WrongDeltas)
			if err != nil {
				t.Fatal(err)
			}
			want, err := strconv.ParseFloat(sample.FreshDamage, 64)
			if err != nil {
				t.Fatal(err)
			}
			if !sample.SameTopologyHash || math.Abs(got.Damage-want) <= math.Max(1, math.Abs(want))*1e-6 {
				t.Fatal("negative witness must reject reuse despite matching topology")
			}
		})
	}
}
