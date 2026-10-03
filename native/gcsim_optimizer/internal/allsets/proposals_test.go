package allsets

import (
	"context"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestBoundedProposalsPreserveDomainAndRawAnchor(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	rb, e := os.ReadFile(filepath.Join(root, "request_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	req, e := contracts.DecodeRequest(rb)
	if e != nil {
		t.Fatal(e)
	}
	cb, e := os.ReadFile(filepath.Join(root, "compact_ir_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	compact, e := contracts.DecodeCompactIR(cb)
	if e != nil {
		t.Fatal(e)
	}
	panel, e := evaluator.Compile(req, compact)
	if e != nil {
		t.Fatal(e)
	}
	// Extra complete sets with real piece stats, plus an unavailable four-piece.
	items := append([]contracts.Artifact(nil), req.Artifacts...)
	maxID := int64(0)
	for _, a := range items {
		if a.ArtifactID > maxID {
			maxID = a.ArtifactID
		}
	}
	for _, name := range []string{"new_a", "new_b", "unknown", "new_hits"} {
		for _, a := range items {
			maxID++
			a.ArtifactID = maxID
			a.SetUID = name
			req.Artifacts = append(req.Artifacts, a)
		}
	}
	index, e := domain.Build(req, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	before := index.Incumbent
	caps := []domain.SetCapability{}
	for _, key := range []string{"new_a", "new_b", "unknown", "new_hits", "missing"} {
		caps = append(caps, domain.SetCapability{UID: key, TwoPiece: true, FourPiece: true})
	}
	hints := map[HintKey]Hint{}
	for _, w := range index.Wearers {
		hints[HintKey{w.WearerKey, "new_a", 4}] = Hint{SharedGroups: map[string]float64{"shared:buff": 50}, Shared: true}
		hints[HintKey{w.WearerKey, "new_hits", 4}] = Hint{NewOutput: true, Unresolved: true}
	}
	for _, set := range index.Wearers[1].SelectedSets {
		hints[HintKey{index.Wearers[1].WearerKey, set.SetUID, set.Count}] = Hint{SharedGroups: map[string]float64{"shared:buff": 50}, Shared: true}
	}
	result, e := Propose(context.Background(), index, panel, caps, hints, 9)
	if e != nil {
		t.Fatal(e)
	}
	if len(result.Queue) != 9 || result.Unqueued <= 0 || index.Incumbent != before {
		t.Fatal("budget or mutation", result)
	}
	seen := map[string]bool{}
	lanes := map[string]bool{}
	for _, p := range result.Queue {
		key := index.Wearers[p.Wearer].WearerKey + "/" + p.Package.Key()
		if seen[key] {
			t.Fatal("duplicate", key)
		}
		seen[key] = true
		if p.Package.Key() == "new_a:4" && math.Abs(p.Priority-p.RawAdvantage) > 1e-10 {
			t.Fatal("counted existing shared opportunity twice", p)
		}
		lanes[p.Lane] = true
		var packs [4]domain.Package
		for i, w := range index.Wearers {
			packs[i] = domain.Package{Sets: w.SelectedSets}
		}
		packs[p.Wearer] = p.Package
		view, e := index.ForPackages(packs, p.Seed, panel.Coordinates())
		if e != nil {
			t.Fatal(e)
		}
		for i := range before {
			if i != p.Wearer && before[i] != p.Seed[i] {
				t.Fatal("reserved items changed")
			}
		}
		deltas, e := view.DenseDeltas(p.Seed)
		if e != nil {
			t.Fatal(e)
		}
		actual, e := panel.EvaluateDPS(deltas)
		if e != nil || math.Abs(actual-p.RawContextDPS) > 1e-10 {
			t.Fatal("old actor scratch leaked", actual, p.RawContextDPS, e)
		}
	}
	if !lanes["new_output"] || !lanes["unresolved"] {
		t.Fatal("lost discovery lanes", lanes)
	}
	repeat, e := Propose(context.Background(), index, panel, caps, hints, 9)
	if e != nil || !reflect.DeepEqual(repeat, result) {
		t.Fatal("nondeterministic proposals", e)
	}
	// Re-anchor on a different legal assignment without rebasing away the
	// original formula reference. Other actors must keep these new stats in
	// every actor-local counterfactual of the next proposal round.
	var changedPackages [4]domain.Package
	for i, w := range index.Wearers {
		changedPackages[i] = domain.Package{Sets: w.SelectedSets}
	}
	chosen := result.Queue[0]
	changedPackages[chosen.Wearer] = chosen.Package
	changed, e := index.ForPackages(changedPackages, chosen.Seed, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	second, e := Propose(context.Background(), changed, panel, caps, hints, 9)
	if e != nil {
		t.Fatal(e)
	}
	for _, p := range second.Queue {
		packages := changedPackages
		packages[p.Wearer] = p.Package
		view, e := changed.ForPackages(packages, p.Seed, panel.Coordinates())
		if e != nil {
			t.Fatal(e)
		}
		d, e := view.DenseDeltas(p.Seed)
		if e != nil {
			t.Fatal(e)
		}
		full, e := panel.EvaluateDPS(d)
		if e != nil || math.Abs(full-p.RawContextDPS) > 1e-10 {
			t.Fatal("refresh lost current other-actor anchor", full, p.RawContextDPS, e)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e = Propose(ctx, index, panel, caps, hints, 9); e == nil {
		t.Fatal("ignored cancellation")
	}
}

func TestInventoryQueueReleasesOccupiedPiecesAndDoesNotScoreHypotheticalBonuses(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	raw, e := os.ReadFile(filepath.Join(root, "request_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	req, e := contracts.DecodeRequest(raw)
	if e != nil {
		t.Fatal(e)
	}
	raw, e = os.ReadFile(filepath.Join(root, "compact_ir_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	ir, e := contracts.DecodeCompactIR(raw)
	if e != nil {
		t.Fatal(e)
	}
	panel, e := evaluator.Compile(req, ir)
	if e != nil {
		t.Fatal(e)
	}
	// The only fourth piece is the OTHER wearer's off-piece. It is movable,
	// not locked. Keep that wearer's 4p and provide a legal replacement.
	borrowed := req.Wearers[1].CurrentArtifacts[4].ArtifactID
	for i, a := range req.Artifacts {
		if a.ArtifactID == borrowed {
			spare := a
			spare.ArtifactID = 9901
			req.Artifacts = append(req.Artifacts, spare)
			req.Artifacts[i].SetUID = "borrowed_set"
			break
		}
	}
	for slot := 0; slot < 3; slot++ {
		a := req.Artifacts[slot]
		a.ArtifactID = int64(9910 + slot)
		a.SetUID = "borrowed_set"
		req.Artifacts = append(req.Artifacts, a)
	}
	index, e := domain.Build(req, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	hints := map[HintKey]Hint{{index.Wearers[0].WearerKey, "borrowed_set", 4}: {PeakIncrement: 1e12}}
	r, e := Propose(context.Background(), index, panel, []domain.SetCapability{{UID: "borrowed_set", TwoPiece: true, FourPiece: true}}, hints, 0)
	if e != nil {
		t.Fatal(e)
	}
	found := false
	for _, p := range r.Queue {
		if p.Priority != p.RawAdvantage {
			t.Fatal("unproven activation leaked into bonus score")
		}
		if p.Wearer == 0 && p.Package.Key() == "borrowed_set:4" {
			found = true
			if p.Seed[0][4] != borrowed || p.Seed[1][4] == borrowed {
				t.Fatal("reservation was not released")
			}
		}
	}
	if !found {
		t.Fatalf("globally available package disappeared: deferred=%d", r.ReservationDeferred)
	}
}
