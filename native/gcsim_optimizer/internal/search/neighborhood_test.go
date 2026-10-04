package search

import (
	"context"
	"errors"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestNeighborhoodFallbackAndCancellation(t *testing.T) {
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
	r := &candidateRun{ctx: context.Background(), localValidator: validator}
	plan, err := r.prepareNeighborhood(base, pools)
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
			plan, err := r.prepareNeighborhood(base, invalid)
			if plan != nil || err != nil {
				t.Fatal("unsupported pool must preserve original route", plan, err)
			}
		})
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r.ctx = ctx
	plan, err = r.prepareNeighborhood(base, pools)
	if plan != nil || !errors.Is(err, context.Canceled) {
		t.Fatal("cancellation must propagate, not fall back", plan, err)
	}
}
