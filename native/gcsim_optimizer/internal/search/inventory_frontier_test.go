package search

import (
	"context"
	"errors"
	"math"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func frontierFixture(t *testing.T) *Engine {
	t.Helper()
	req, ir := searchFixtures(t)
	for slot := 0; slot < 5; slot++ {
		for variant := 0; variant < 3; variant++ {
			a := req.Artifacts[slot]
			a.ArtifactID = int64(1000 + slot*3 + variant)
			a.Substats = []contracts.StatValue{{Key: "hp_percent", Value: []string{"0.1", "0.4", "0.2"}[variant]}}
			req.Artifacts = append(req.Artifacts, a)
		}
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	p, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	d, err := domain.Build(req, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	e, err := NewInventory(d, p, Config{1, 1, 100000, 8, 1, 8})
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestInventoryFrontierResumesEveryLeafWithoutRestartOrPruningUnknowns(t *testing.T) {
	e := frontierFixture(t)
	old, err := e.RefineWearer(context.Background(), e.domain.Incumbent, 0)
	if err != nil {
		t.Fatal(err)
	}
	work := -1
	for _, quantum := range []int{1, 7, 64} {
		f, err := e.NewWearerFrontier(e.domain.Incumbent, 0, math.Inf(1))
		if err != nil {
			t.Fatal(err)
		}
		steps := 0
		for !f.Done() {
			before := f.Expanded()
			if err := f.Advance(context.Background(), quantum); err != nil {
				t.Fatal(err)
			}
			if f.Expanded()-before > quantum {
				t.Fatal("renewed allowance", quantum, f.Expanded()-before)
			}
			steps++
			if steps > 10000 {
				t.Fatal("frontier did not progress")
			}
		}
		got, err := f.Snapshot()
		if err != nil {
			t.Fatal(err)
		}
		if math.Abs(got.Finalists[0].DPS-old.Finalists[0].DPS) > 1e-8 || got.BudgetUnexpanded != 0 || got.BoundPrunedBuilds != 0 {
			t.Fatal("resumption lost points or promoted an unknown bound", quantum, got)
		}
		if work != -1 && work != got.Expanded {
			t.Fatal("resumption repeated search", work, got.Expanded)
		}
		work = got.Expanded
	}
}

func TestInventoryFrontierCancellationKeepsCursorAndLegalImprovement(t *testing.T) {
	e := frontierFixture(t)
	f, err := e.NewWearerFrontier(e.domain.Incumbent, 0, math.Inf(1))
	if err != nil {
		t.Fatal(err)
	}
	if err := f.Advance(context.Background(), 1); err != nil {
		t.Fatal(err)
	}
	before := f.Expanded()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := f.Advance(ctx, 64); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	got, err := f.Snapshot()
	if err != nil {
		t.Fatal(err)
	}
	if f.Expanded() != before || got.BudgetUnexpanded == 0 || got.Finalists[0].DPS <= got.AnchorDPS || e.domain.ValidateAssignment(got.Finalists[0].Assignment) != nil {
		t.Fatal("canceled frontier lost its pending work/incumbent", got)
	}
	for !f.Done() {
		if err := f.Advance(context.Background(), 64); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := f.Snapshot(); err != nil {
		t.Fatal(err)
	}
}
