package search

import (
	"context"
	"errors"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// Unsupported pool metadata falls back, never silently rejects candidates.
// Cancellation is different: it must propagate to the existing Finish path.
func TestHypothesisNeighborhoodFallbackAndCancellation(t *testing.T) {
	req, _ := searchFixtures(t)
	index, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	validator, err := index.PrepareLocalAssignmentValidator(index.Incumbent, 0)
	if err != nil {
		t.Fatal(err)
	}
	base := index.Incumbent[0]
	var pools [5][]int64
	for slot, id := range base {
		pools[slot] = []int64{id}
	}
	wasEnabled := hypothesisNeighborhoodEnabled
	hypothesisNeighborhoodEnabled = true
	t.Cleanup(func() { hypothesisNeighborhoodEnabled = wasEnabled })
	r := &candidateRun{ctx: context.Background(), localValidator: validator}
	plan, err := hypothesisPrepareGate(r, base, pools)
	if err != nil || plan == nil {
		t.Fatal("valid domain did not prepare", plan, err)
	}
	for _, control := range []struct {
		name string
		id   int64
	}{
		{"unknown", -987654321},
		{"wrong_slot", base[1]},
		{"occupied", index.Incumbent[1][0]},
	} {
		t.Run(control.name, func(t *testing.T) {
			invalid := pools
			invalid[0] = []int64{control.id}
			before := hypothesisCounters.Fallbacks
			plan, err := hypothesisPrepareGate(r, base, invalid)
			if plan != nil || err != nil || hypothesisCounters.Fallbacks != before+1 {
				t.Fatal("unsupported pool must preserve original route", plan, err)
			}
		})
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r.ctx = ctx
	before := hypothesisCounters.Fallbacks
	plan, err = hypothesisPrepareGate(r, base, pools)
	if plan != nil || !errors.Is(err, context.Canceled) || hypothesisCounters.Fallbacks != before {
		t.Fatal("cancellation must propagate, not count as fallback", plan, err)
	}
}
