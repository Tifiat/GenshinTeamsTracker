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

// Portable slices of actual engine captures: expected candidate values come
// from a fresh engine capture, not from this evaluator's own baseline. Source
// extraction/operator/unknown-shape tests live in the engine patch separately.
func TestSourceDerivedNumericResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_numeric_response_samples_v1.json", 2)
}

func TestSourceDerivedAttackFieldResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_attack_field_samples_v1.json", 4)
}

func TestSourceDerivedFlatStatResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_flat_stat_samples_v1.json", 2)
}

func TestSourceDerivedHelperReturnResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_helper_return_samples_v1.json", 1)
}

func TestSourceDerivedAdditiveResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_additive_samples_v1.json", 4)
}

func checkEngineResponseSamples(t *testing.T, fixtureName string, sampleCount int) {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", fixtureName)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Samples []struct {
			Case   string
			Member contracts.IRSeedMember
			Checks []struct {
				Deltas               map[string]float64
				EngineExpectedDamage string `json:"engine_expected_damage"`
			}
		}
	}
	if err = json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Samples) != sampleCount {
		t.Fatal("missing regression samples")
	}
	for _, sample := range fixture.Samples {
		t.Run(sample.Case, func(t *testing.T) {
			if err := contracts.ValidateSeedMember(sample.Member); err != nil {
				t.Fatal(err)
			}
			baseline, err := EvaluateSeedMember(sample.Member, nil)
			if err != nil {
				t.Fatal(err)
			}
			declared, err := strconv.ParseFloat(sample.Member.Channels[0].BaselineDamage, 64)
			if err != nil {
				t.Fatal(err)
			}
			if math.Abs(baseline.Damage-declared) > math.Max(1, declared)*1e-12 {
				t.Fatal("baseline mismatch")
			}
			for _, check := range sample.Checks {
				score, err := EvaluateSeedMember(sample.Member, check.Deltas)
				if err != nil {
					t.Fatal(err)
				}
				expected, err := strconv.ParseFloat(check.EngineExpectedDamage, 64)
				if err != nil {
					t.Fatal(err)
				}
				if math.Abs(score.Damage-expected) > math.Max(1, expected)*1e-10 {
					t.Fatalf("%v: formula %g vs engine %g", check.Deltas, score.Damage, expected)
				}
			}
		})
	}
}
