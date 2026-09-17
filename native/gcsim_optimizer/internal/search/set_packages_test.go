package search

import (
	"context"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"math"
	"strconv"
	"testing"
)

func TestPairedSetLanesCoverLegalDomainExactlyOnceAndSearchMatchesExhaustive(t *testing.T) {
	request, compact := searchFixtures(t)
	request.Legality.FixedFourPiece, request.Legality.FixedSetPackages = false, true
	request.Wearers[0].SelectedSetUID = ""
	request.Wearers[0].SelectedSets = []contracts.SetRequirement{{SetUID: "set_a", Count: 2}, {SetUID: "set_x", Count: 2}}
	var choices [5][]int64
	for slot, current := range []string{"set_a", "set_a", "set_x", "set_x", "off"} {
		request.Artifacts[slot].SetUID = current
		choices[slot] = append(choices[slot], request.Artifacts[slot].ArtifactID)
		for category, set := range []string{"set_a", "set_x", "off"} {
			if set == current {
				continue
			}
			item := request.Artifacts[slot]
			item.ArtifactID = int64(len(request.Artifacts) + 1)
			item.SetUID = set
			item.Substats = append([]contracts.StatValue(nil), item.Substats...)
			value, _ := strconv.ParseFloat(item.Substats[0].Value, 64)
			item.Substats[0].Value = strconv.FormatFloat(value+float64(slot+category+1)/100, 'f', -1, 64)
			request.Artifacts = append(request.Artifacts, item)
			choices[slot] = append(choices[slot], item.ArtifactID)
		}
	}
	compact.RequestSHA256, _ = contracts.CanonicalSHA256(request)
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	indexed, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := New(indexed, panel, Config{64, 64, 10000, 64, 1, 64})
	if err != nil {
		t.Fatal(err)
	}
	lanes := engine.lanes(indexed.Incumbent, 0)
	if len(lanes) != 50 {
		t.Fatalf("lanes=%d", len(lanes))
	}
	seen := make(map[[5]int64]int)
	for _, lane := range lanes {
		var ids [5]int64
		for slot, pool := range lane.pools {
			if len(pool) != 1 {
				t.Fatal("occupied artifacts leaked into lane")
			}
			ids[slot] = pool[0]
		}
		seen[ids]++
	}
	best := -math.MaxFloat64
	legal := 0
	var walk func(int, domain.Assignment)
	walk = func(slot int, a domain.Assignment) {
		if slot == 5 {
			if indexed.ValidateAssignment(a) != nil {
				return
			}
			legal++
			if seen[a[0]] != 1 {
				t.Fatalf("missing/duplicate pattern %v", a[0])
			}
			score, err := engine.score(a)
			if err != nil {
				t.Fatal(err)
			}
			best = math.Max(best, score)
			return
		}
		for _, id := range choices[slot] {
			a[0][slot] = id
			walk(slot+1, a)
		}
	}
	walk(0, indexed.Incumbent)
	if legal != 50 {
		t.Fatalf("legal=%d", legal)
	}
	step, err := engine.RefineWearer(context.Background(), indexed.Incumbent, 0)
	if err != nil || math.Abs(step.Finalists[0].DPS-best) > 1e-9 {
		t.Fatalf("best %v step %v err %v", best, step, err)
	}
	engine.config.MaxExpandedPerActor = 100
	step, err = engine.searchActor(context.Background(), indexed.Incumbent, 0, 1, 8)
	if err != nil || step.Expanded > 100 || step.CompleteEvaluations < 50 {
		t.Fatalf("shared budget/starved lanes: %+v %v", step, err)
	}
	for _, row := range step.Finalists {
		if err := indexed.ValidateAssignment(row.Assignment); err != nil {
			t.Fatal(err)
		}
	}
}

func TestRefineWearerRejectsInvalidBoundary(t *testing.T) {
	request, compact := searchFixtures(t)
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		t.Fatal(err)
	}
	indexed, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := New(indexed, panel, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	if _, err = engine.RefineWearer(context.Background(), indexed.Incumbent, 4); err == nil {
		t.Fatal("invalid wearer accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = engine.RefineWearer(ctx, indexed.Incumbent, 0); err != context.Canceled {
		t.Fatal(err)
	}
	broken := indexed.Incumbent
	broken[0][0] = broken[1][0]
	if _, err = engine.RefineWearer(context.Background(), broken, 0); err == nil {
		t.Fatal("illegal anchor accepted")
	}
	view := *indexed
	view.Coordinates = nil
	if _, err = New(&view, panel, DefaultConfig()); err == nil {
		t.Fatal("coordinate mismatch accepted")
	}
	view = *indexed
	view.Wearers[0].WearerKey = "other"
	if _, err = New(&view, panel, DefaultConfig()); err == nil {
		t.Fatal("owner mismatch accepted")
	}
}
