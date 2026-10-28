package setcontext

import (
	"math"
	"reflect"
	"testing"
)

func TestHypothesisPointCoordinatesRequireCompleteExactIdentity(t *testing.T) {
	prepared := []string{"actor_a.atk_percent", "actor_b.crit_rate", "actor_a.energy_recharge"}
	input := []string{"actor_a.energy_recharge", "actor_a.atk_percent", "actor_b.crit_rate"}
	dense := []float64{.2, .3, .4}
	got, ok, err := hypothesisPointCoordinates(prepared, input, dense)
	if err != nil || !ok || !reflect.DeepEqual(got, []float64{.3, .4, .2}) {
		t.Fatalf("permuted full vector: %v %v %v", got, ok, err)
	}
	for _, keys := range [][]string{
		{"actor_a.energy_recharge", "actor_a.atk_percent"},
		{"actor_a.energy_recharge", "actor_a.atk_percent", "missing"},
		{"actor_a.energy_recharge", "actor_a.energy_recharge", "actor_b.crit_rate"},
	} {
		if _, ok, err := hypothesisPointCoordinates(prepared, keys, dense); ok || err != nil {
			t.Fatalf("incomplete/ambiguous coordinate accepted: %v %v %v", keys, ok, err)
		}
	}
	if _, ok, err := hypothesisPointCoordinates(prepared, input, []float64{.2, math.NaN(), .4}); ok || err == nil {
		t.Fatalf("nonfinite artifact delta accepted: %v %v", ok, err)
	}
	if _, ok, err := hypothesisPointCoordinates(prepared, input, dense[:2]); ok || err != nil {
		t.Fatalf("short value vector accepted: %v %v", ok, err)
	}
	if !reflect.DeepEqual(dense, []float64{.2, .3, .4}) {
		t.Fatal("caller input mutated")
	}
}
